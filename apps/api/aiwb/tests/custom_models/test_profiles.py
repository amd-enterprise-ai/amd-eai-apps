# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Unit tests for the custom-model profile read and create endpoints.

Covers:
* list_custom_model_profiles — Default classification, default-first ordering,
  effective-profile selection (precision + fallback), inUseBy population,
  single-Default models, InconsistentStateException propagation, and restamping
  named-set identity when it has drifted from the AIMModel.
* get_custom_model_profile — the ``default`` alias, get-by-resource-name,
  cross-model/project not-found, and model-not-found.
* create_custom_model_profile — AIWB-authored set composition (narrowed selector +
  overrides agreeing on count), duplicate-name conflict, reserved/invalid names,
  axes not resolving to one base profile, model-not-found, and upstream failure.
* Router: GET/POST .../models/{model}/profiles and GET .../profiles/{profile}.
"""

import re
from contextlib import AbstractContextManager, ExitStack
from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from kubernetes_asyncio.client import ApiException
from pydantic import ValidationError

from api_common.exceptions import (
    ConflictException,
    ExternalServiceError,
    InconsistentStateException,
    NotFoundException,
    ValidationException,
)
from app import app  # type: ignore[attr-defined]
from app.aims.constants import AIM_MODEL_LABEL, PROFILE_ORIGIN_AIWB, PROFILE_ORIGIN_LABEL
from app.aims.crds import (
    AIMModelProfilesDerivedFrom,
    AIMModelResource,
    AIMProfileResource,
    AIMProfileSetResource,
    AIMServiceResource,
)
from app.custom_models.constants import (
    CANONICAL_REPO_ID_ANNOTATION,
    MODEL_PRECISION_ANNOTATION,
    PROFILE_DISPLAY_NAME_ANNOTATION,
    REVISION_ANNOTATION,
)
from app.custom_models.schemas import (
    CustomProfileCreateRequest,
    CustomProfilePatchRequest,
    CustomProfileResponse,
    CustomProfileStatus,
    ProfileInUseRef,
)
from app.custom_models.service import (
    _K8S_LABEL_VALUE_MAX_LENGTH,
    _PROFILE_SET_NAME_MAX_LENGTH,
    _RESOURCE_NAME_SLUG_MAX_LENGTH,
    DefaultProfileImmutableError,
    _assert_unique_profile_display_name,
    _custom_profile_set_resource_name,
    create_custom_model_profile,
    delete_custom_model_profile,
    get_custom_model_profile,
    list_custom_model_profiles,
    update_custom_model_profile,
)
from app.dispatch.crds import K8sMetadata
from app.minio import get_minio_client
from app.workloads.constants import DISPLAY_NAME_ANNOTATION, WORKLOAD_ID_LABEL
from tests.dependency_overrides import BASE_OVERRIDES, override_dependencies
from tests.factory import make_aim_profile_set

_NAMESPACE = "test-namespace"
_MODEL_NAME = "tinyllama-import-abc12345"
_DEFAULT_SET = f"{_MODEL_NAME}-profiles-5935b717"
_NAMED_SET = f"{_MODEL_NAME}-high-speed-7f3b6c8e"

_SERVICE_PATCH_BASE = "app.custom_models.service"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _make_model_cr(precision: str | None = None) -> MagicMock:
    """A custom-model AIMModel CR stub carrying the revision (and optional precision) annotations."""
    annotations = {REVISION_ANNOTATION: "main"}
    if precision:
        annotations[MODEL_PRECISION_ANNOTATION] = precision
    cr = MagicMock()
    cr.metadata = K8sMetadata(name=_MODEL_NAME, namespace=_NAMESPACE, annotations=annotations)
    return cr


def _make_profile(
    name: str,
    *,
    owner_set: str,
    aim_id: str = _MODEL_NAME,
    precision: str = "fp16",
    metric: str = "latency",
    profile_status: str = "Ready",
    primary: bool = False,
    optimization_type: str = "general",
) -> AIMProfileResource:
    """An AIMProfile owned by ``owner_set`` (the durable set→profile link)."""
    return AIMProfileResource.model_validate(
        {
            "metadata": {
                "name": name,
                "namespace": _NAMESPACE,
                "labels": {AIM_MODEL_LABEL: _MODEL_NAME},
                "ownerReferences": [{"kind": "AIMProfileSet", "name": owner_set, "controller": True}],
            },
            "spec": {
                "aimId": aim_id,
                "precision": precision,
                "metric": metric,
                "type": optimization_type,
                "primary": primary,
                "image": "amdenterpriseai/aim-base:0.11",
            },
            "status": {"status": profile_status, "hardwareSummary": "1 x MI300X"},
        }
    )


def _make_service(profile_name: str, display_name: str = "summarizer-prod") -> AIMServiceResource:
    wid = uuid4()
    return AIMServiceResource.model_validate(
        {
            "metadata": {
                "name": f"wb-aim-{str(wid)[:8]}",
                "namespace": _NAMESPACE,
                "labels": {WORKLOAD_ID_LABEL: str(wid)},
                "annotations": {DISPLAY_NAME_ANNOTATION: display_name},
            },
            "spec": {"model": {"name": _MODEL_NAME}, "profile": {"name": profile_name}},
        }
    )


def _patch_context(
    *,
    cr: MagicMock | None,
    profile_sets: list,
    profiles: list[AIMProfileResource],
    services: list[AIMServiceResource],
) -> tuple[AbstractContextManager[Any], ...]:
    """Patch the four Kubernetes reads the profile service fans out over."""
    return (
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.get_aim_model", AsyncMock(return_value=cr)),
        patch(
            f"{_SERVICE_PATCH_BASE}.aims_gateway.list_aim_profile_sets_for_model",
            AsyncMock(return_value=profile_sets),
        ),
        patch(f"{_SERVICE_PATCH_BASE}.list_aim_profiles", AsyncMock(return_value=profiles)),
        patch(
            f"{_SERVICE_PATCH_BASE}.aims_gateway.list_aim_services_for_model",
            AsyncMock(return_value=services),
        ),
    )


# ---------------------------------------------------------------------------
# list_custom_model_profiles — service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_single_default_returns_one_row() -> None:
    """A model with only the engine-created set lists exactly one Default row."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    profile = _make_profile("tinyllama-tp1-latency", owner_set=_DEFAULT_SET)
    patches = _patch_context(cr=_make_model_cr(), profile_sets=[default_set], profiles=[profile], services=[])
    with patches[0], patches[1], patches[2], patches[3]:
        result = await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    assert len(result) == 1
    row = result[0]
    assert row.is_default is True
    assert row.name == "default"
    assert row.display_name == "Default"
    assert row.resource_name == _DEFAULT_SET
    assert row.profile is not None
    assert row.status.state == "Ready"
    assert row.in_use_by == []


@pytest.mark.asyncio
async def test_list_orders_default_first() -> None:
    """The Default is returned first regardless of set ordering from the API."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named_set = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    default_profile = _make_profile("tinyllama-tp1-latency", owner_set=_DEFAULT_SET)
    named_profile = _make_profile("tinyllama-tp4-latency", owner_set=_NAMED_SET)
    # Named set listed first on purpose; classification + sort must still surface Default first.
    patches = _patch_context(
        cr=_make_model_cr(),
        profile_sets=[named_set, default_set],
        profiles=[default_profile, named_profile],
        services=[],
    )
    with patches[0], patches[1], patches[2], patches[3]:
        result = await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    assert [r.is_default for r in result] == [True, False]
    assert result[0].name == "default"
    assert result[1].name == _NAMED_SET


@pytest.mark.asyncio
async def test_list_uses_profile_display_name_and_sanitizes_custom_profile() -> None:
    """Named rows use the profile annotation and only surface allowlisted override keys.

    customProfile is an allowlist, so composed identity/model-source/selector
    fields and any unknown engine-authored key (here ``sourceRef``) are dropped
    rather than leaked — the response fails closed. The authored runtime knobs
    survive so the edit drawer can prefill from them, ``acceleratorType``
    included even though the adjacent accelerator axes are selector-composed.
    """
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named_set = make_aim_profile_set(
        name=_NAMED_SET,
        model_name=_MODEL_NAME,
        namespace=_NAMESPACE,
        is_aiwb_authored=True,
        extra_spec={
            "overrides": {
                "aimId": "org/model",
                "modelId": "org/model",
                "modelSources": [
                    {
                        "sourceUri": "s3://internal-bucket/model",
                        "env": [{"name": "HF_TOKEN", "valueFrom": {"secretKeyRef": {"name": "secret-name"}}}],
                    }
                ],
                "acceleratorCount": 4,
                "precision": "fp16",
                "acceleratorType": "gpu",
                "sourceRef": "internal-source-ref",
                "image": "example.com/aim:latest",
                "engineArgs": {"max-model-len": 32768},
            }
        },
    )
    named_set.metadata.annotations = {
        PROFILE_DISPLAY_NAME_ANNOTATION: "High speed",
        DISPLAY_NAME_ANNOTATION: "wrong-generic-name",
    }
    patches = _patch_context(
        cr=_make_model_cr(),
        profile_sets=[default_set, named_set],
        profiles=[],
        services=[],
    )
    with patches[0], patches[1], patches[2], patches[3]:
        result = await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    named_row = next(row for row in result if not row.is_default)
    assert named_row.display_name == "High speed"
    assert named_row.custom_profile.model_dump(by_alias=True, exclude_none=True, exclude_defaults=True) == {
        "image": "example.com/aim:latest",
        "acceleratorType": "gpu",
        "engineArgs": {"max-model-len": 32768},
    }


@pytest.mark.asyncio
async def test_list_surfaces_non_ready_profile_message() -> None:
    """A non-ready row carries the controller's Ready-condition message."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    profile = _make_profile(
        "tinyllama-unavailable",
        owner_set=_DEFAULT_SET,
        profile_status="NotAvailable",
    )
    profile.status.conditions = [
        {
            "type": "Ready",
            "status": "False",
            "reason": "HardwareNotAvailable",
            "message": "No cluster nodes match accelerator labels and resource requests",
        }
    ]
    patches = _patch_context(cr=_make_model_cr(), profile_sets=[default_set], profiles=[profile], services=[])
    with patches[0], patches[1], patches[2], patches[3]:
        result = await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    assert result[0].status.state == "NotAvailable"
    assert result[0].status.message == "No cluster nodes match accelerator labels and resource requests"


@pytest.mark.asyncio
async def test_list_populates_in_use_by_on_the_referencing_row_only() -> None:
    """inUseBy lands on the set whose derived profile a deployment pins, not others."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named_set = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    default_profile = _make_profile("tinyllama-tp1-latency", owner_set=_DEFAULT_SET)
    named_profile = _make_profile("tinyllama-tp4-latency", owner_set=_NAMED_SET)
    service = _make_service(profile_name="tinyllama-tp4-latency", display_name="summarizer-prod")

    patches = _patch_context(
        cr=_make_model_cr(),
        profile_sets=[default_set, named_set],
        profiles=[default_profile, named_profile],
        services=[service],
    )
    with patches[0], patches[1], patches[2], patches[3]:
        result = await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    by_name = {r.name: r for r in result}
    assert by_name["default"].in_use_by == []
    named_row = by_name[_NAMED_SET]
    assert [ref.display_name for ref in named_row.in_use_by] == ["summarizer-prod"]
    assert named_row.in_use_by[0].service_id == service.id


@pytest.mark.asyncio
async def test_list_effective_profile_prefers_precision_match() -> None:
    """When the model pins a precision, the effective profile is the matching Ready one."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    fp8 = _make_profile("tinyllama-fp8", owner_set=_DEFAULT_SET, precision="fp8")
    fp16 = _make_profile("tinyllama-fp16", owner_set=_DEFAULT_SET, precision="fp16")
    patches = _patch_context(
        cr=_make_model_cr(precision="fp8"),
        profile_sets=[default_set],
        profiles=[fp16, fp8],
        services=[],
    )
    with patches[0], patches[1], patches[2], patches[3]:
        result = await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    assert result[0].profile.spec.precision == "fp8"


@pytest.mark.asyncio
async def test_list_effective_profile_falls_back_to_first_when_no_precision() -> None:
    """Without a precision annotation, the effective profile falls back to the first derived one."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    first = _make_profile("tinyllama-a", owner_set=_DEFAULT_SET, precision="fp16")
    second = _make_profile("tinyllama-b", owner_set=_DEFAULT_SET, precision="bf16")
    patches = _patch_context(
        cr=_make_model_cr(),
        profile_sets=[default_set],
        profiles=[first, second],
        services=[],
    )
    with patches[0], patches[1], patches[2], patches[3]:
        result = await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    assert result[0].profile.metadata.name == "tinyllama-a"


@pytest.mark.asyncio
async def test_list_raises_when_model_not_found() -> None:
    """A missing (or non-custom) model reads as not-found rather than leaking data."""
    patches = _patch_context(cr=None, profile_sets=[], profiles=[], services=[])
    with patches[0], patches[1], patches[2], patches[3]:
        with pytest.raises(NotFoundException):
            await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)


@pytest.mark.asyncio
async def test_list_raises_when_no_default_present() -> None:
    """Zero classifiable Defaults is an inconsistent state, surfaced rather than guessed."""
    only_authored = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    patches = _patch_context(cr=_make_model_cr(), profile_sets=[only_authored], profiles=[], services=[])
    with patches[0], patches[1], patches[2], patches[3]:
        with pytest.raises(InconsistentStateException):
            await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)


@pytest.mark.asyncio
async def test_list_wraps_upstream_errors_as_external_service_error() -> None:
    """A Kubernetes read failure surfaces as 502-mapped ExternalServiceError."""
    with (
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.get_aim_model", AsyncMock(return_value=_make_model_cr())),
        patch(
            f"{_SERVICE_PATCH_BASE}.aims_gateway.list_aim_profile_sets_for_model",
            AsyncMock(side_effect=ApiException(status=500, reason="boom")),
        ),
        patch(f"{_SERVICE_PATCH_BASE}.list_aim_profiles", AsyncMock(return_value=[])),
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.list_aim_services_for_model", AsyncMock(return_value=[])),
    ):
        with pytest.raises(ExternalServiceError):
            await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)


@pytest.mark.asyncio
async def test_list_requires_strict_profile_reads() -> None:
    """Profile-list failures must surface as the endpoint's documented 502, not a partial 200."""
    with (
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.get_aim_model", AsyncMock(return_value=_make_model_cr())),
        patch(
            f"{_SERVICE_PATCH_BASE}.aims_gateway.list_aim_profile_sets_for_model",
            AsyncMock(return_value=[]),
        ),
        patch(
            f"{_SERVICE_PATCH_BASE}.list_aim_profiles",
            AsyncMock(side_effect=ExternalServiceError("profile list failed")),
        ) as mock_profiles,
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.list_aim_services_for_model", AsyncMock(return_value=[])),
    ):
        with pytest.raises(ExternalServiceError):
            await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    mock_profiles.assert_awaited_once_with(ANY, _NAMESPACE, model_name=_MODEL_NAME, strict=True)


_MODEL_IDENTITY = {
    "aimId": "org/model",
    "modelId": "org/model",
    "modelSources": [{"modelId": "org/model", "sourceUri": "s3://bucket/model"}],
}
_DRIFTED_IDENTITY = {
    "aimId": "org/model-a",
    "modelId": "org/model-a",
    "modelSources": [{"modelId": "org/model-a", "sourceUri": "hf://org/model-a"}],
}
_MATCHING_SET = f"{_MODEL_NAME}-matching-aaaaaaaa"


def _profile_set_with_identity(
    *,
    name: str,
    is_aiwb_authored: bool,
    identity: dict[str, Any],
    extra_overrides: dict[str, Any] | None = None,
) -> AIMProfileSetResource:
    overrides = dict(identity)
    if extra_overrides:
        overrides.update(extra_overrides)
    return make_aim_profile_set(
        name=name,
        model_name=_MODEL_NAME,
        namespace=_NAMESPACE,
        is_aiwb_authored=is_aiwb_authored,
        extra_spec={"overrides": overrides},
    )


@pytest.mark.asyncio
async def test_list_restamps_drifted_named_set_identity_only() -> None:
    """Named sets whose identity drifted are restamped; Default and matching siblings are not."""
    default_set = _profile_set_with_identity(name=_DEFAULT_SET, is_aiwb_authored=False, identity=_DRIFTED_IDENTITY)
    matching_set = _profile_set_with_identity(
        name=_MATCHING_SET,
        is_aiwb_authored=True,
        identity=_MODEL_IDENTITY,
        extra_overrides={"engineArgs": {"max-model-len": 4096}, "acceleratorCount": 4},
    )
    drifted_set = _profile_set_with_identity(
        name=_NAMED_SET,
        is_aiwb_authored=True,
        identity=_DRIFTED_IDENTITY,
        extra_overrides={"engineArgs": {"max-model-len": 2048}},
    )
    restamped = _profile_set_with_identity(name=_NAMED_SET, is_aiwb_authored=True, identity=_MODEL_IDENTITY)
    patch_set = AsyncMock(return_value=restamped)
    patches = _patch_context(
        cr=_make_custom_model(),
        profile_sets=[drifted_set, matching_set, default_set],
        profiles=[],
        services=[],
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.patch_aim_profile_set", patch_set),
    ):
        result = await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    patch_set.assert_awaited_once()
    assert patch_set.await_args is not None
    _, namespace, name, body = patch_set.await_args.args
    assert namespace == _NAMESPACE
    assert name == _NAMED_SET
    assert body == {"spec": {"overrides": _MODEL_IDENTITY}}
    assert [row.resource_name for row in result] == [_DEFAULT_SET, _NAMED_SET, _MATCHING_SET]


@pytest.mark.asyncio
async def test_list_skips_identity_restamp_when_named_set_already_matches() -> None:
    """A named set that already carries the live AIMModel identity is left untouched."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named_set = _profile_set_with_identity(name=_NAMED_SET, is_aiwb_authored=True, identity=_MODEL_IDENTITY)
    patch_set = AsyncMock()
    patches = _patch_context(
        cr=_make_custom_model(),
        profile_sets=[named_set, default_set],
        profiles=[],
        services=[],
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.patch_aim_profile_set", patch_set),
    ):
        result = await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    patch_set.assert_not_awaited()
    assert [row.resource_name for row in result] == [_DEFAULT_SET, _NAMED_SET]


@pytest.mark.asyncio
async def test_list_recreates_unpinned_derived_profile_with_stale_immutable_identity() -> None:
    """After aligning the set, a stale unpinned derived profile is deleted for engine recreation."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    drifted_set = _profile_set_with_identity(name=_NAMED_SET, is_aiwb_authored=True, identity=_DRIFTED_IDENTITY)
    restamped = _profile_set_with_identity(name=_NAMED_SET, is_aiwb_authored=True, identity=_MODEL_IDENTITY)
    stale_profile = _make_profile("stale-derived", owner_set=_NAMED_SET, aim_id="org/model-a")
    patch_set = AsyncMock(return_value=restamped)
    delete_profile = AsyncMock()
    patches = _patch_context(
        cr=_make_custom_model(),
        profile_sets=[drifted_set, default_set],
        profiles=[stale_profile],
        services=[],
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.patch_aim_profile_set", patch_set),
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.delete_aim_profile", delete_profile),
    ):
        await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    patch_set.assert_awaited_once()
    delete_profile.assert_awaited_once_with(ANY, _NAMESPACE, "stale-derived")


@pytest.mark.asyncio
async def test_list_keeps_stale_derived_profile_while_deployment_pins_it() -> None:
    """A stale profile serving a deployment is not disrupted; a later read retries after undeploy."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    matching_set = _profile_set_with_identity(name=_NAMED_SET, is_aiwb_authored=True, identity=_MODEL_IDENTITY)
    stale_profile = _make_profile("stale-derived", owner_set=_NAMED_SET, aim_id="org/model-a")
    service = _make_service("stale-derived")
    patch_set = AsyncMock()
    delete_profile = AsyncMock()
    patches = _patch_context(
        cr=_make_custom_model(),
        profile_sets=[matching_set, default_set],
        profiles=[stale_profile],
        services=[service],
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.patch_aim_profile_set", patch_set),
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.delete_aim_profile", delete_profile),
    ):
        await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    patch_set.assert_not_awaited()
    delete_profile.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_keeps_stale_derived_profile_a_service_resolved_without_pinning() -> None:
    """A profile bound via selector/auto-resolution (status.resolvedProfile) counts as in use."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    matching_set = _profile_set_with_identity(name=_NAMED_SET, is_aiwb_authored=True, identity=_MODEL_IDENTITY)
    stale_profile = _make_profile("stale-derived", owner_set=_NAMED_SET, aim_id="org/model-a")
    # A service that let the engine resolve its profile: spec.profile carries no
    # name, and the concrete profile is recorded on status.resolvedProfile.
    resolving_service = AIMServiceResource.model_validate(
        {
            "metadata": {
                "name": "wb-aim-resolved",
                "namespace": _NAMESPACE,
                "labels": {WORKLOAD_ID_LABEL: str(uuid4())},
            },
            "spec": {"model": {"name": _MODEL_NAME}},
            "status": {"resolvedProfile": {"name": "stale-derived", "namespace": _NAMESPACE}},
        }
    )
    delete_profile = AsyncMock()
    patches = _patch_context(
        cr=_make_custom_model(),
        profile_sets=[matching_set, default_set],
        profiles=[stale_profile],
        services=[resolving_service],
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.delete_aim_profile", delete_profile),
    ):
        await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    delete_profile.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_retries_stale_profile_recreation_after_set_is_already_aligned() -> None:
    """A failed or previously blocked cleanup is retried even when the set no longer needs patching."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    matching_set = _profile_set_with_identity(name=_NAMED_SET, is_aiwb_authored=True, identity=_MODEL_IDENTITY)
    stale_profile = _make_profile("stale-derived", owner_set=_NAMED_SET, aim_id="org/model-a")
    patch_set = AsyncMock()
    delete_profile = AsyncMock()
    patches = _patch_context(
        cr=_make_custom_model(),
        profile_sets=[matching_set, default_set],
        profiles=[stale_profile],
        services=[],
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.patch_aim_profile_set", patch_set),
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.delete_aim_profile", delete_profile),
    ):
        await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    patch_set.assert_not_awaited()
    delete_profile.assert_awaited_once_with(ANY, _NAMESPACE, "stale-derived")


@pytest.mark.asyncio
async def test_list_keeps_derived_profile_with_current_identity() -> None:
    """A current derived profile is never deleted."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    matching_set = _profile_set_with_identity(name=_NAMED_SET, is_aiwb_authored=True, identity=_MODEL_IDENTITY)
    current_profile = _make_profile("current-derived", owner_set=_NAMED_SET, aim_id="org/model")
    delete_profile = AsyncMock()
    patches = _patch_context(
        cr=_make_custom_model(),
        profile_sets=[matching_set, default_set],
        profiles=[current_profile],
        services=[],
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.delete_aim_profile", delete_profile),
    ):
        await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    delete_profile.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_returns_rows_when_identity_restamp_fails() -> None:
    """A restamp failure must not turn the profiles list into a 502."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    drifted_set = _profile_set_with_identity(name=_NAMED_SET, is_aiwb_authored=True, identity=_DRIFTED_IDENTITY)
    patch_set = AsyncMock(side_effect=ExternalServiceError("patch failed"))
    patches = _patch_context(
        cr=_make_custom_model(),
        profile_sets=[drifted_set, default_set],
        profiles=[],
        services=[],
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.patch_aim_profile_set", patch_set),
    ):
        result = await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    patch_set.assert_awaited_once()
    assert [row.resource_name for row in result] == [_DEFAULT_SET, _NAMED_SET]


@pytest.mark.asyncio
async def test_list_returns_rows_when_identity_restamp_response_is_unparseable() -> None:
    """An unparseable patch response must not 500 the list."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    drifted_set = _profile_set_with_identity(name=_NAMED_SET, is_aiwb_authored=True, identity=_DRIFTED_IDENTITY)
    with pytest.raises(ValidationError) as exc_info:
        AIMProfileSetResource.model_validate({})
    patch_set = AsyncMock(side_effect=exc_info.value)
    patches = _patch_context(
        cr=_make_custom_model(),
        profile_sets=[drifted_set, default_set],
        profiles=[],
        services=[],
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.patch_aim_profile_set", patch_set),
    ):
        result = await list_custom_model_profiles(AsyncMock(), _NAMESPACE, _MODEL_NAME)

    patch_set.assert_awaited_once()
    assert [row.resource_name for row in result] == [_DEFAULT_SET, _NAMED_SET]


@pytest.mark.asyncio
async def test_get_restamps_drifted_named_set_identity() -> None:
    """Reading a single named profile restamps it when identity has drifted."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    drifted_set = _profile_set_with_identity(name=_NAMED_SET, is_aiwb_authored=True, identity=_DRIFTED_IDENTITY)
    restamped = _profile_set_with_identity(name=_NAMED_SET, is_aiwb_authored=True, identity=_MODEL_IDENTITY)
    patch_set = AsyncMock(return_value=restamped)
    patches = _patch_context(
        cr=_make_custom_model(),
        profile_sets=[drifted_set, default_set],
        profiles=[],
        services=[],
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.patch_aim_profile_set", patch_set),
    ):
        row = await get_custom_model_profile(AsyncMock(), _NAMESPACE, _MODEL_NAME, _NAMED_SET)

    patch_set.assert_awaited_once()
    assert row.resource_name == _NAMED_SET


@pytest.mark.asyncio
async def test_get_does_not_restamp_unrelated_sibling_sets() -> None:
    """A single-profile GET heals only the requested set, never drifted siblings."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    requested_set = _profile_set_with_identity(name=_NAMED_SET, is_aiwb_authored=True, identity=_MODEL_IDENTITY)
    drifted_sibling = _profile_set_with_identity(name=_MATCHING_SET, is_aiwb_authored=True, identity=_DRIFTED_IDENTITY)
    patch_set = AsyncMock()
    patches = _patch_context(
        cr=_make_custom_model(),
        profile_sets=[requested_set, drifted_sibling, default_set],
        profiles=[],
        services=[],
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.patch_aim_profile_set", patch_set),
    ):
        row = await get_custom_model_profile(AsyncMock(), _NAMESPACE, _MODEL_NAME, _NAMED_SET)

    # Requested set already matches, so no patch; the drifted sibling is untouched.
    patch_set.assert_not_awaited()
    assert row.resource_name == _NAMED_SET


# ---------------------------------------------------------------------------
# get_custom_model_profile — service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_default_alias_resolves_to_default_set() -> None:
    """The reserved literal 'default' resolves to the engine-created set."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    profile = _make_profile("tinyllama-tp1-latency", owner_set=_DEFAULT_SET)
    patches = _patch_context(cr=_make_model_cr(), profile_sets=[default_set], profiles=[profile], services=[])
    with patches[0], patches[1], patches[2], patches[3]:
        row = await get_custom_model_profile(AsyncMock(), _NAMESPACE, _MODEL_NAME, "default")

    assert row.is_default is True
    assert row.name == "default"
    assert row.resource_name == _DEFAULT_SET


@pytest.mark.asyncio
async def test_get_named_profile_by_resource_name() -> None:
    """A named set is fetched by its real resource name and is not flagged Default."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named_set = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    named_profile = _make_profile("tinyllama-tp4-latency", owner_set=_NAMED_SET)
    patches = _patch_context(
        cr=_make_model_cr(),
        profile_sets=[default_set, named_set],
        profiles=[named_profile],
        services=[],
    )
    with patches[0], patches[1], patches[2], patches[3]:
        row = await get_custom_model_profile(AsyncMock(), _NAMESPACE, _MODEL_NAME, _NAMED_SET)

    assert row.is_default is False
    assert row.name == _NAMED_SET
    assert row.resource_name == _NAMED_SET


@pytest.mark.asyncio
async def test_get_unknown_profile_returns_not_found() -> None:
    """A profile name not belonging to this model reads as not-found."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    patches = _patch_context(cr=_make_model_cr(), profile_sets=[default_set], profiles=[], services=[])
    with patches[0], patches[1], patches[2], patches[3]:
        with pytest.raises(NotFoundException):
            await get_custom_model_profile(AsyncMock(), _NAMESPACE, _MODEL_NAME, "no-such-profile")


# ---------------------------------------------------------------------------
# Router — HTTP layer
# ---------------------------------------------------------------------------

_LIST_URL = f"/v1/projects/{_NAMESPACE}/models/{_MODEL_NAME}/profiles"
_GET_URL = f"/v1/projects/{_NAMESPACE}/models/{_MODEL_NAME}/profiles/default"


def _sample_row(is_default: bool = True) -> CustomProfileResponse:
    return CustomProfileResponse(
        name="default" if is_default else _NAMED_SET,
        display_name="Default" if is_default else "High speed",
        is_default=is_default,
        resource_name=_DEFAULT_SET if is_default else _NAMED_SET,
        status=CustomProfileStatus(state="Ready"),
        in_use_by=[ProfileInUseRef(service_id="svc-1", display_name="summarizer-prod")],
    )


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.list_custom_model_profiles", new_callable=AsyncMock)
def test_list_endpoint_returns_200(mock_list: AsyncMock) -> None:
    mock_list.return_value = [_sample_row(is_default=True), _sample_row(is_default=False)]
    with TestClient(app) as client:
        response = client.get(_LIST_URL)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 2
    assert body["data"][0]["isDefault"] is True
    assert body["data"][0]["name"] == "default"
    assert body["data"][0]["resourceName"] == _DEFAULT_SET
    assert body["data"][0]["inUseBy"][0]["displayName"] == "summarizer-prod"


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.list_custom_model_profiles", new_callable=AsyncMock, side_effect=NotFoundException("nope"))
def test_list_endpoint_returns_404_when_model_missing(mock_list: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.get(_LIST_URL)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(BASE_OVERRIDES)
@patch(
    "app.projects.router.list_custom_model_profiles",
    new_callable=AsyncMock,
    side_effect=ExternalServiceError("k8s down"),
)
def test_list_endpoint_returns_502_on_upstream_failure(mock_list: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.get(_LIST_URL)
    assert response.status_code == status.HTTP_502_BAD_GATEWAY


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.get_custom_model_profile", new_callable=AsyncMock)
def test_get_endpoint_returns_200(mock_get: AsyncMock) -> None:
    mock_get.return_value = _sample_row(is_default=True)
    with TestClient(app) as client:
        response = client.get(_GET_URL)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["name"] == "default"
    assert body["isDefault"] is True


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.get_custom_model_profile", new_callable=AsyncMock, side_effect=NotFoundException("nope"))
def test_get_endpoint_returns_404(mock_get: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.get(_GET_URL)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(BASE_OVERRIDES)
@patch(
    "app.projects.router.get_custom_model_profile", new_callable=AsyncMock, side_effect=ExternalServiceError("k8s down")
)
def test_get_endpoint_returns_502_on_upstream_failure(mock_get: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.get(_GET_URL)
    assert response.status_code == status.HTTP_502_BAD_GATEWAY


# ---------------------------------------------------------------------------
# create_custom_model_profile — schema validation
# ---------------------------------------------------------------------------


def _create_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "displayName": "High speed fun",
        "acceleratorModel": "MI300X",
        "acceleratorCount": 8,
        "precision": "fp8",
        "metric": "latency",
        "image": "amdenterpriseai/aim-base:0.11",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("display_name", ["High speed fun", "Mixed CASE", "Café profile", "高速設定"])
def test_create_request_accepts_and_preserves_free_text_display_name(display_name: str) -> None:
    """Human-facing names are stored as entered rather than constrained by K8s naming rules."""
    request = CustomProfileCreateRequest.model_validate(_create_payload(displayName=display_name))
    assert request.display_name == display_name


@pytest.mark.parametrize("display_name", ["Default", "default", "DEFAULT", " DeFaUlT "])
def test_create_request_rejects_reserved_default_name(display_name: str) -> None:
    """'Default' (any casing) is reserved for the engine-owned set."""
    with pytest.raises(ValidationError):
        CustomProfileCreateRequest.model_validate(_create_payload(displayName=display_name))


def test_create_request_rejects_blank_display_name() -> None:
    """A whitespace-only name passes min_length=1 but is blank after strip and must be rejected."""
    with pytest.raises(ValidationError):
        CustomProfileCreateRequest.model_validate(_create_payload(displayName="   "))


def test_create_request_rejects_conflicting_image() -> None:
    """A customProfile.image disagreeing with the top-level image is rejected."""
    with pytest.raises(ValidationError):
        CustomProfileCreateRequest.model_validate(
            _create_payload(customProfile={"image": "example.com/other:1"}),
        )


@pytest.mark.parametrize(
    "axis_payload",
    [
        {"acceleratorModel": "MI300X"},
        {"acceleratorCount": 8},
        {"precision": "fp8"},
        {"metric": "latency"},
        {"accelerator_count": 8},
    ],
)
def test_create_request_rejects_narrowing_axes_in_custom_profile(axis_payload: dict[str, Any]) -> None:
    """Restating a narrowing axis under customProfile is a 422, not a silent overwrite."""
    with pytest.raises(ValidationError):
        CustomProfileCreateRequest.model_validate(_create_payload(customProfile=axis_payload))


# ---------------------------------------------------------------------------
# _custom_profile_set_resource_name — naming
# ---------------------------------------------------------------------------

_HASH_SUFFIX = r"[0-9a-f]{8}"
_DNS_SUBDOMAIN = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?(?:\.[a-z0-9](?:[-a-z0-9]*[a-z0-9])?)*$")


def test_resource_name_uses_model_prefix_slug_and_hash() -> None:
    """The name is <model>-<slug>-<hash> so it is distinguishable from the engine's Default set."""
    name = _custom_profile_set_resource_name("tinyllama-import-abc12345", "High Speed Fun")
    assert re.fullmatch(rf"tinyllama-import-abc12345-high-speed-fun-{_HASH_SUFFIX}", name)


def test_same_display_name_on_different_models_has_distinct_resource_names() -> None:
    """The model prefix lets two models use the same profile display name."""
    first = _custom_profile_set_resource_name("first-model", "High speed fun")
    second = _custom_profile_set_resource_name("second-model", "High speed fun")
    assert first.startswith("first-model-high-speed-fun-")
    assert second.startswith("second-model-high-speed-fun-")
    assert first != second


def test_resource_name_is_deterministic_and_case_insensitive() -> None:
    """The suffix is a deterministic digest so a duplicate create collides on metadata.name.

    Repeated calls yield the same name, and casing/whitespace variants the
    uniqueness check treats as equal resolve to the same name — so the K8s API
    server rejects a racing duplicate atomically rather than admitting two sets.
    """
    base = _custom_profile_set_resource_name("mymodel-import-abc12345", "High Speed Fun")
    assert base == _custom_profile_set_resource_name("mymodel-import-abc12345", "High Speed Fun")
    assert base == _custom_profile_set_resource_name("mymodel-import-abc12345", "  high speed fun ")

    # Unicode case variants the uniqueness check folds together must also resolve
    # to one resource name: the slug and digest share the same case-folded key,
    # so a slug divergence cannot let a racing duplicate slip past the 409.
    strasse = _custom_profile_set_resource_name("mymodel-import-abc12345", "Straße")
    assert strasse == _custom_profile_set_resource_name("mymodel-import-abc12345", "STRASSE")


def test_resource_name_differs_for_distinct_names_on_same_model() -> None:
    """Distinct display names on one model resolve to distinct resource names."""
    first = _custom_profile_set_resource_name("mymodel-import-abc12345", "Fast")
    second = _custom_profile_set_resource_name("mymodel-import-abc12345", "Slow")
    assert first != second


def test_resource_name_avoids_engine_default_pattern() -> None:
    """A name that slugs to 'profiles' must not reproduce the engine's <model>-profiles-<hash> shape."""
    name = _custom_profile_set_resource_name("mymodel-import-abc12345", "Profiles")
    assert re.fullmatch(rf"mymodel-import-abc12345-profile-{_HASH_SUFFIX}", name)
    assert not re.fullmatch(rf"mymodel-import-abc12345-profiles-{_HASH_SUFFIX}", name)


def test_resource_name_avoids_engine_pattern_after_length_truncation() -> None:
    """Truncating a longer slug must not produce the engine-reserved 'profiles' component."""
    # Size the model so the slug budget is exactly 8, so "profiles-extra" truncates
    # to "profiles" and the guard must still nudge it to "profile".
    long_model = "m" * (_PROFILE_SET_NAME_MAX_LENGTH - 18)
    name = _custom_profile_set_resource_name(long_model, "Profiles extra")
    assert re.fullmatch(rf"{long_model}-profile-{_HASH_SUFFIX}", name)
    assert len(name) <= _PROFILE_SET_NAME_MAX_LENGTH


def test_resource_name_falls_back_when_display_name_slugs_empty() -> None:
    """A display name with no slug-able characters falls back to the literal 'profile'."""
    name = _custom_profile_set_resource_name("mymodel-import-abc12345", "!!!")
    assert re.fullmatch(rf"mymodel-import-abc12345-profile-{_HASH_SUFFIX}", name)


@pytest.mark.parametrize(
    ("display_name", "expected_slug"),
    [
        pytest.param("Fast_Profile", "fast-profile", id="underscore"),
        pytest.param("Café profile", "cafe-profile", id="unicode-diacritic"),
        pytest.param("高速設定", "profile", id="non-ascii-only"),
    ],
)
def test_resource_name_converts_free_text_to_dns_safe_slug(display_name: str, expected_slug: str) -> None:
    """Free-text names remain annotations while their resource slugs obey K8s DNS rules."""
    name = _custom_profile_set_resource_name("mymodel-import-abc12345", display_name)
    assert re.fullmatch(rf"mymodel-import-abc12345-{expected_slug}-{_HASH_SUFFIX}", name)
    assert _DNS_SUBDOMAIN.fullmatch(name)


def test_resource_name_stays_within_k8s_label_value_limit() -> None:
    """A pathologically long model/display name is capped so it fits a K8s label value.

    aim-engine copies the whole set name into a label value on the derived
    AIMProfile, and label values cap at 63 characters, so the set name must too.
    """
    long_model = "m" * 300
    long_display = "x " * 100
    name = _custom_profile_set_resource_name(long_model, long_display)
    assert len(name) == _PROFILE_SET_NAME_MAX_LENGTH
    assert _PROFILE_SET_NAME_MAX_LENGTH <= _K8S_LABEL_VALUE_MAX_LENGTH
    assert _DNS_SUBDOMAIN.fullmatch(name)


def test_resource_name_fits_label_limit_for_realistic_long_name() -> None:
    """A realistic model name plus a short display name must still fit a label value.

    This pairing composed a 64-character set name under the old subdomain-based
    cap, which aim-engine then rejected when stamping it into a 63-char label
    value — leaving the set Progressing with no derived AIMProfile and a blank
    profile row in the UI.
    """
    name = _custom_profile_set_resource_name("llama-3-2-1b-kw-test-import-7bfcadd1", "custom-profile-001")
    assert len(name) <= _K8S_LABEL_VALUE_MAX_LENGTH
    assert _DNS_SUBDOMAIN.fullmatch(name)


def test_resource_name_of_normal_model_keeps_full_model_and_readable_slug() -> None:
    """A typical model keeps its whole name and a readable slug — truncation is only for outliers."""
    model = "tinyllama-import-abc12345"
    name = _custom_profile_set_resource_name(model, "A profile name long enough to require truncation")
    assert name.startswith(f"{model}-a-profile-name-long-enough-")
    assert len(name) <= _PROFILE_SET_NAME_MAX_LENGTH


def test_resource_name_caps_onboarded_max_length_model_and_keeps_suffix() -> None:
    """An onboarded model whose slug alone is 200 chars is truncated to the cap, keeping its suffix.

    The engine prefixes/appends when naming derived AIMProfiles, so the set name
    must stay under the engine-safe cap even for the longest onboarded model name.
    """
    model = f"{'m' * _RESOURCE_NAME_SLUG_MAX_LENGTH}-import-12345678"
    name = _custom_profile_set_resource_name(model, "A profile name long enough to require truncation")
    assert len(name) <= _PROFILE_SET_NAME_MAX_LENGTH
    assert _DNS_SUBDOMAIN.fullmatch(name)
    # The model's terminal unique suffix survives even when its readable head is dropped.
    assert "import-12345678" in name


def test_resource_name_retains_terminal_suffix_when_model_exceeds_prefix_budget() -> None:
    """A model too long to fit whole keeps its terminal unique suffix, dropping the readable head."""
    model = "m" * 250 + "-import-abcd1234"
    name = _custom_profile_set_resource_name(model, "Fast")
    assert len(name) <= _PROFILE_SET_NAME_MAX_LENGTH
    assert _DNS_SUBDOMAIN.fullmatch(name)
    # The unique suffix survives even though the readable head is truncated away.
    assert "import-abcd1234" in name


def test_resource_name_trims_trailing_hyphen_on_truncated_prefix() -> None:
    """Truncating the model prefix mid-hyphen must not leave a double hyphen before the slug."""
    model = "a" * 241 + "-tail"
    name = _custom_profile_set_resource_name(model, "Fast")
    assert "--" not in name


# ---------------------------------------------------------------------------
# _assert_unique_profile_display_name — uniqueness
# ---------------------------------------------------------------------------


def test_unique_name_helper_rejects_case_and_whitespace_variants() -> None:
    """A name matching an existing profile ignoring case/surrounding whitespace conflicts."""
    existing = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    existing.metadata.annotations = {PROFILE_DISPLAY_NAME_ANNOTATION: "High Speed Fun"}
    with pytest.raises(ConflictException):
        _assert_unique_profile_display_name(
            [existing], "  high speed fun ", namespace=_NAMESPACE, model_name=_MODEL_NAME
        )


def test_unique_name_helper_uses_unicode_casefolding() -> None:
    """Unicode case variants that users perceive as the same name conflict."""
    existing = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    existing.metadata.annotations = {PROFILE_DISPLAY_NAME_ANNOTATION: "Straße"}
    with pytest.raises(ConflictException):
        _assert_unique_profile_display_name([existing], "STRASSE", namespace=_NAMESPACE, model_name=_MODEL_NAME)


def test_unique_name_helper_ignores_engine_default_without_display_name() -> None:
    """The engine Default carries no display-name annotation, so any name is free against it."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    _assert_unique_profile_display_name([default_set], "High Speed Fun", namespace=_NAMESPACE, model_name=_MODEL_NAME)


def test_unique_name_helper_excludes_named_set_for_rename() -> None:
    """A rename re-asserting the same name on the set being renamed does not self-conflict."""
    renaming = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    renaming.metadata.annotations = {PROFILE_DISPLAY_NAME_ANNOTATION: "High Speed Fun"}
    _assert_unique_profile_display_name(
        [renaming],
        "High Speed Fun",
        namespace=_NAMESPACE,
        model_name=_MODEL_NAME,
        exclude_resource_name=_NAMED_SET,
    )


# ---------------------------------------------------------------------------
# create_custom_model_profile — service
# ---------------------------------------------------------------------------


def _make_custom_model() -> AIMModelResource:
    """A v1alpha2 custom AIMModel with a base derivation and BYO weights to copy."""
    return AIMModelResource.model_validate(
        {
            "metadata": {
                "name": _MODEL_NAME,
                "namespace": _NAMESPACE,
                "uid": "model-uid-123",
                "annotations": {REVISION_ANNOTATION: "main", CANONICAL_REPO_ID_ANNOTATION: "org/model"},
                "labels": {AIM_MODEL_LABEL: _MODEL_NAME},
            },
            "spec": {
                "profiles": {
                    "derivedFrom": {
                        "selector": {"role": "base", "modelRef": {"name": "aim-base", "scope": "Namespace"}}
                    },
                    "versionPolicy": "all",
                    "overrides": {
                        "aimId": "org/model",
                        "modelId": "org/model",
                        "image": "amdenterpriseai/aim-base:0.11",
                        "modelSources": [{"modelId": "org/model", "sourceUri": "s3://bucket/model"}],
                    },
                }
            },
        }
    )


def _make_base_role_profile(
    accelerator_model: str = "MI300X",
    accelerator_count: int = 8,
    precision: str = "fp8",
    metric: str = "latency",
) -> AIMProfileResource:
    return AIMProfileResource.model_validate(
        {
            "metadata": {"name": f"aim-base-{precision}-{metric}-{accelerator_count}", "namespace": _NAMESPACE},
            "spec": {
                "acceleratorModel": accelerator_model,
                "acceleratorCount": accelerator_count,
                "precision": precision,
                "metric": metric,
                "type": "general",
            },
            "status": {"status": "Ready"},
        }
    )


def _make_create_request(**overrides: Any) -> CustomProfileCreateRequest:
    return CustomProfileCreateRequest.model_validate(_create_payload(**overrides))


@pytest.mark.asyncio
async def test_create_composes_narrowed_set_and_returns_row() -> None:
    """Happy path: an AIWB-authored set is created with selector and overrides agreeing on count."""
    model = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    created = make_aim_profile_set(name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True)
    created.metadata.annotations = {PROFILE_DISPLAY_NAME_ANNOTATION: "High speed fun"}
    patches = _patch_context(cr=model, profile_sets=[default_set], profiles=[], services=[])
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.list_base_role_profiles", AsyncMock(return_value=[_make_base_role_profile()])),
        patch(
            f"{_SERVICE_PATCH_BASE}.aims_gateway.create_aim_profile_set",
            AsyncMock(return_value=created),
        ) as mock_create,
    ):
        row = await create_custom_model_profile(
            AsyncMock(), _NAMESPACE, _MODEL_NAME, "user@example.com", _make_create_request()
        )

    assert row.is_default is False
    assert row.display_name == "High speed fun"
    assert row.resource_name == _NAMED_SET
    # No derived profile has been emitted for the brand-new set yet.
    assert row.profile is None

    assert mock_create.await_args is not None
    manifest = mock_create.await_args.args[2]
    # The generated set name is prefixed with the model so it is distinguishable
    # from the engine's Default set (<model>-profiles-<hash>) in kubectl/logs.
    assert manifest["metadata"]["name"].startswith(f"{_MODEL_NAME}-high-speed-fun-")
    assert manifest["metadata"]["annotations"][PROFILE_DISPLAY_NAME_ANNOTATION] == "High speed fun"
    selector = manifest["spec"]["selector"]
    assert selector["role"] == "base"
    assert selector["acceleratorModel"] == "MI300X"
    assert selector["acceleratorCount"] == 8
    assert selector["precision"] == "fp8"
    assert selector["metric"] == "latency"
    overrides = manifest["spec"]["overrides"]
    # Count is composed from the single typed field, so selector and overrides cannot drift.
    assert overrides["acceleratorCount"] == selector["acceleratorCount"]
    # Weights/identity copied from the model so the profile is self-contained.
    assert overrides["modelSources"] == [{"modelId": "org/model", "sourceUri": "s3://bucket/model"}]
    labels = manifest["metadata"]["labels"]
    assert labels[PROFILE_ORIGIN_LABEL] == PROFILE_ORIGIN_AIWB
    assert labels[AIM_MODEL_LABEL] == _MODEL_NAME
    owner = manifest["metadata"]["ownerReferences"][0]
    assert owner["uid"] == "model-uid-123"
    assert owner["controller"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "derivation",
    [
        pytest.param({}, id="no-derivation"),
        pytest.param({"selector": {"role": "base"}}, id="no-model-ref"),
        pytest.param({"selector": {"modelRef": {"name": "aim-base"}}}, id="no-role"),
    ],
)
async def test_create_rejects_model_without_a_base_derivation(derivation: dict[str, Any]) -> None:
    """A new set narrows the model's own derivation, so a model missing one is refused as a 400.

    Composing from an absent role/modelRef would leave a selector carrying only
    the axes, which matches base profiles the model never derived from.
    """
    model = _make_custom_model()
    model.spec.profiles.derived_from = AIMModelProfilesDerivedFrom.model_validate(derivation)
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    patches = _patch_context(cr=model, profile_sets=[default_set], profiles=[], services=[])
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        # Resolvable axes, so the derivation guard is the only reason to refuse.
        patch(f"{_SERVICE_PATCH_BASE}.list_base_role_profiles", AsyncMock(return_value=[_make_base_role_profile()])),
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.create_aim_profile_set", AsyncMock()) as mock_create,
    ):
        with pytest.raises(ValidationException):
            await create_custom_model_profile(
                AsyncMock(), _NAMESPACE, _MODEL_NAME, "user@example.com", _make_create_request()
            )
    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_rejects_duplicate_display_name() -> None:
    """A display name already used by another profile on the model is a conflict (409)."""
    model = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    duplicate = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    duplicate.metadata.annotations = {PROFILE_DISPLAY_NAME_ANNOTATION: "High Speed Fun"}
    patches = _patch_context(cr=model, profile_sets=[default_set, duplicate], profiles=[], services=[])
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.list_base_role_profiles", AsyncMock(return_value=[_make_base_role_profile()])),
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.create_aim_profile_set", AsyncMock()) as mock_create,
    ):
        with pytest.raises(ConflictException):
            await create_custom_model_profile(
                AsyncMock(), _NAMESPACE, _MODEL_NAME, "user@example.com", _make_create_request()
            )
    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_translates_apply_conflict_into_duplicate_name_error() -> None:
    """A racing duplicate that slips past the pre-check hits the deterministic-name 409.

    Two concurrent creates for the same normalized name read the same snapshot and
    both pass the in-memory uniqueness check; the loser's apply collides on the
    deterministic ``metadata.name`` and the API server returns 409, which must
    surface as the same display-name conflict rather than a raw upstream error.
    """
    model = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    patches = _patch_context(cr=model, profile_sets=[default_set], profiles=[], services=[])
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.list_base_role_profiles", AsyncMock(return_value=[_make_base_role_profile()])),
        patch(
            f"{_SERVICE_PATCH_BASE}.aims_gateway.create_aim_profile_set",
            AsyncMock(side_effect=ConflictException("AIMProfileSet already exists")),
        ),
    ):
        with pytest.raises(ConflictException, match="already exists for custom model"):
            await create_custom_model_profile(
                AsyncMock(), _NAMESPACE, _MODEL_NAME, "user@example.com", _make_create_request()
            )


@pytest.mark.asyncio
async def test_create_rejects_axes_that_match_no_base_profile() -> None:
    """Axes that resolve to zero base profiles are a client error (400), not an apply."""
    model = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    patches = _patch_context(cr=model, profile_sets=[default_set], profiles=[], services=[])
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(
            f"{_SERVICE_PATCH_BASE}.list_base_role_profiles",
            AsyncMock(return_value=[_make_base_role_profile(precision="fp16")]),
        ),
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.create_aim_profile_set", AsyncMock()) as mock_create,
    ):
        with pytest.raises(ValidationException):
            await create_custom_model_profile(
                AsyncMock(), _NAMESPACE, _MODEL_NAME, "user@example.com", _make_create_request()
            )
    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_rejects_axes_that_match_multiple_base_profiles() -> None:
    """Ambiguous axes (more than one base profile) are a client error (400)."""
    model = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    dupe_a = _make_base_role_profile()
    dupe_b = _make_base_role_profile()
    patches = _patch_context(cr=model, profile_sets=[default_set], profiles=[], services=[])
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.list_base_role_profiles", AsyncMock(return_value=[dupe_a, dupe_b])),
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.create_aim_profile_set", AsyncMock()) as mock_create,
    ):
        with pytest.raises(ValidationException):
            await create_custom_model_profile(
                AsyncMock(), _NAMESPACE, _MODEL_NAME, "user@example.com", _make_create_request()
            )
    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_validates_default_invariant_before_mutating() -> None:
    """An inconsistent model (no unique Default) fails with 500 before any set is created."""
    model = _make_custom_model()
    # Only an AIWB-authored set exists, so there is no engine Default to classify.
    authored_only = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    patches = _patch_context(cr=model, profile_sets=[authored_only], profiles=[], services=[])
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.list_base_role_profiles", AsyncMock(return_value=[_make_base_role_profile()])),
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.create_aim_profile_set", AsyncMock()) as mock_create,
    ):
        with pytest.raises(InconsistentStateException):
            await create_custom_model_profile(
                AsyncMock(), _NAMESPACE, _MODEL_NAME, "user@example.com", _make_create_request()
            )
    # The invariant is checked before mutating, so no set is applied on this error path.
    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_raises_when_model_not_found() -> None:
    """Creating a profile on a missing/non-custom model reads as not-found."""
    patches = _patch_context(cr=None, profile_sets=[], profiles=[], services=[])
    with patches[0], patches[1], patches[2], patches[3]:
        with pytest.raises(NotFoundException):
            await create_custom_model_profile(
                AsyncMock(), _NAMESPACE, _MODEL_NAME, "user@example.com", _make_create_request()
            )


@pytest.mark.asyncio
async def test_create_surfaces_base_profile_list_failure_as_external_service_error() -> None:
    """A K8s failure listing base profiles must surface as 502, not a misleading 400 (zero base profiles)."""
    model = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    patches = _patch_context(cr=model, profile_sets=[default_set], profiles=[], services=[])
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(
            f"{_SERVICE_PATCH_BASE}.list_base_role_profiles",
            AsyncMock(side_effect=ExternalServiceError("k8s down")),
        ) as mock_base,
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.create_aim_profile_set", AsyncMock()) as mock_create,
    ):
        with pytest.raises(ExternalServiceError):
            await create_custom_model_profile(
                AsyncMock(), _NAMESPACE, _MODEL_NAME, "user@example.com", _make_create_request()
            )
    # The list is requested in strict mode so upstream failures propagate instead of degrading to [].
    mock_base.assert_awaited_once_with(ANY, _NAMESPACE, strict=True)
    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_propagates_upstream_apply_failure() -> None:
    """A Kubernetes apply failure surfaces as the documented 502-mapped error."""
    model = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    patches = _patch_context(cr=model, profile_sets=[default_set], profiles=[], services=[])
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(f"{_SERVICE_PATCH_BASE}.list_base_role_profiles", AsyncMock(return_value=[_make_base_role_profile()])),
        patch(
            f"{_SERVICE_PATCH_BASE}.aims_gateway.create_aim_profile_set",
            AsyncMock(side_effect=ExternalServiceError("apply failed")),
        ),
    ):
        with pytest.raises(ExternalServiceError):
            await create_custom_model_profile(
                AsyncMock(), _NAMESPACE, _MODEL_NAME, "user@example.com", _make_create_request()
            )


# ---------------------------------------------------------------------------
# create_custom_model_profile — router
# ---------------------------------------------------------------------------

_CREATE_URL = f"/v1/projects/{_NAMESPACE}/models/{_MODEL_NAME}/profiles"


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.create_custom_model_profile", new_callable=AsyncMock)
def test_create_endpoint_returns_201(mock_create: AsyncMock) -> None:
    mock_create.return_value = _sample_row(is_default=False)
    with TestClient(app) as client:
        response = client.post(_CREATE_URL, json=_create_payload())

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["name"] == _NAMED_SET
    assert body["isDefault"] is False


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.create_custom_model_profile", new_callable=AsyncMock)
def test_create_endpoint_rejects_reserved_name_with_422(mock_create: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.post(_CREATE_URL, json=_create_payload(displayName="Default"))
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    mock_create.assert_not_awaited()


@override_dependencies(BASE_OVERRIDES)
@patch(
    "app.projects.router.create_custom_model_profile",
    new_callable=AsyncMock,
    side_effect=ConflictException("dup"),
)
def test_create_endpoint_returns_409_on_duplicate(mock_create: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.post(_CREATE_URL, json=_create_payload())
    assert response.status_code == status.HTTP_409_CONFLICT


@override_dependencies(BASE_OVERRIDES)
@patch(
    "app.projects.router.create_custom_model_profile",
    new_callable=AsyncMock,
    side_effect=ValidationException("axes do not resolve"),
)
def test_create_endpoint_returns_400_on_unresolvable_axes(mock_create: AsyncMock) -> None:
    """Service-layer ValidationException maps to 400 (the codebase convention)."""
    with TestClient(app) as client:
        response = client.post(_CREATE_URL, json=_create_payload())
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@override_dependencies(BASE_OVERRIDES)
@patch(
    "app.projects.router.create_custom_model_profile",
    new_callable=AsyncMock,
    side_effect=NotFoundException("nope"),
)
def test_create_endpoint_returns_404_when_model_missing(mock_create: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.post(_CREATE_URL, json=_create_payload())
    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(BASE_OVERRIDES)
@patch(
    "app.projects.router.create_custom_model_profile",
    new_callable=AsyncMock,
    side_effect=ExternalServiceError("k8s down"),
)
def test_create_endpoint_returns_502_on_upstream_failure(mock_create: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.post(_CREATE_URL, json=_create_payload())
    assert response.status_code == status.HTTP_502_BAD_GATEWAY


# ---------------------------------------------------------------------------
# update_custom_model_profile — schema validation
# ---------------------------------------------------------------------------


def test_patch_request_empty_body_is_valid_but_carries_no_updates() -> None:
    """Every field is optional, so an empty body validates; the emptiness is a service-layer 400."""
    request = CustomProfilePatchRequest()
    assert request.model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize("display_name", ["Default", "default", " DeFaUlT "])
def test_patch_request_rejects_reserved_default_name(display_name: str) -> None:
    """Renaming to the reserved 'Default' (any casing) is rejected at the request boundary (422)."""
    with pytest.raises(ValidationError):
        CustomProfilePatchRequest.model_validate({"displayName": display_name})


def test_patch_request_rejects_blank_display_name() -> None:
    """A whitespace-only rename is blank after strip and must be rejected."""
    with pytest.raises(ValidationError):
        CustomProfilePatchRequest.model_validate({"displayName": "   "})


def test_patch_request_rejects_conflicting_image() -> None:
    """A customProfile.image disagreeing with the top-level image is rejected (422)."""
    with pytest.raises(ValidationError):
        CustomProfilePatchRequest.model_validate({"image": "a:1", "customProfile": {"image": "b:2"}})


# ---------------------------------------------------------------------------
# update_custom_model_profile — service
# ---------------------------------------------------------------------------


def _make_named_set(display_name: str = "High speed", accelerator_count: int = 8) -> AIMProfileSetResource:
    """An AIWB-authored named set narrowed on the four axes, with weights/identity in overrides."""
    named = make_aim_profile_set(
        name=_NAMED_SET,
        model_name=_MODEL_NAME,
        namespace=_NAMESPACE,
        is_aiwb_authored=True,
        extra_spec={
            "selector": {
                "role": "base",
                "modelRef": {"name": "aim-base", "scope": "Namespace"},
                "acceleratorModel": "MI300X",
                "acceleratorCount": accelerator_count,
                "precision": "fp8",
                "metric": "latency",
            },
            "overrides": {
                "aimId": "org/model",
                "modelId": "org/model",
                "image": "amdenterpriseai/aim-base:0.11",
                "modelSources": [{"modelId": "org/model", "sourceUri": "s3://bucket/model"}],
                "acceleratorModel": "MI300X",
                "acceleratorCount": accelerator_count,
                "precision": "fp8",
                "metric": "latency",
                "engineArgs": {"max-model-len": 32768},
            },
        },
    )
    named.metadata.annotations = {PROFILE_DISPLAY_NAME_ANNOTATION: display_name}
    return named


def _patch_update_environment(
    *,
    cr: AIMModelResource | None,
    profile_sets: list,
    profiles: list[AIMProfileResource],
    services: list[AIMServiceResource],
    patched: AIMProfileSetResource | None = None,
    base_profiles: list[AIMProfileResource] | None = None,
) -> tuple[AbstractContextManager[Any], ...]:
    """Patch the reads/writes update_custom_model_profile fans out over."""
    context = _patch_context(cr=cr, profile_sets=profile_sets, profiles=profiles, services=services)
    return (
        *context,
        patch(
            f"{_SERVICE_PATCH_BASE}.list_base_role_profiles",
            AsyncMock(return_value=base_profiles if base_profiles is not None else [_make_base_role_profile()]),
        ),
        patch(
            f"{_SERVICE_PATCH_BASE}.aims_gateway.patch_aim_profile_set",
            AsyncMock(return_value=patched if patched is not None else _make_named_set()),
        ),
        patch(f"{_SERVICE_PATCH_BASE}._upsert_manifest_documents_to_s3_unlocked", AsyncMock()),
    )


@pytest.mark.asyncio
async def test_update_rename_only_patches_display_name_annotation() -> None:
    """A rename rewrites only the display-name annotation; the resource name is untouched, no spec change."""
    cr = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named = _make_named_set(display_name="High speed")
    patched = _make_named_set(display_name="High speed v2")
    env = _patch_update_environment(cr=cr, profile_sets=[default_set, named], profiles=[], services=[], patched=patched)
    with env[0], env[1], env[2], env[3], env[4], env[5] as mock_patch, env[6]:
        row = await update_custom_model_profile(
            AsyncMock(),
            AsyncMock(),
            _NAMESPACE,
            _MODEL_NAME,
            _NAMED_SET,
            CustomProfilePatchRequest(display_name="High speed v2"),
        )

    assert row.display_name == "High speed v2"
    assert row.resource_name == _NAMED_SET
    assert row.is_default is False
    name_arg, patch_body = mock_patch.await_args.args[2], mock_patch.await_args.args[3]
    assert name_arg == _NAMED_SET
    assert patch_body["metadata"]["annotations"][PROFILE_DISPLAY_NAME_ANNOTATION] == "High speed v2"
    assert "spec" not in patch_body


@pytest.mark.asyncio
async def test_update_config_change_rewrites_selector_and_overrides_together() -> None:
    """A config edit rebuilds selector and overrides from one axis set so the count cannot drift."""
    cr = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named = _make_named_set(accelerator_count=8)
    base = _make_base_role_profile(accelerator_count=4)
    env = _patch_update_environment(
        cr=cr, profile_sets=[default_set, named], profiles=[], services=[], base_profiles=[base]
    )
    with env[0], env[1], env[2], env[3], env[4], env[5] as mock_patch, env[6]:
        await update_custom_model_profile(
            AsyncMock(),
            AsyncMock(),
            _NAMESPACE,
            _MODEL_NAME,
            _NAMED_SET,
            # Only the count changes; the other axes are carried over from the set.
            CustomProfilePatchRequest(accelerator_count=4),
        )

    patch_body = mock_patch.await_args.args[3]
    selector = patch_body["spec"]["selector"]
    overrides = patch_body["spec"]["overrides"]
    assert selector["acceleratorCount"] == 4
    assert overrides["acceleratorCount"] == selector["acceleratorCount"]
    assert selector["acceleratorModel"] == "MI300X"
    assert selector["precision"] == "fp8"
    assert selector["metric"] == "latency"
    # Weights/identity are carried from the model so the profile stays self-contained.
    assert overrides["modelSources"] == [{"modelId": "org/model", "sourceUri": "s3://bucket/model"}]


@pytest.mark.asyncio
async def test_update_rejects_default_alias() -> None:
    """The reserved 'default' alias is refused before any read (edited through model settings)."""
    with pytest.raises(ValidationException):
        await update_custom_model_profile(
            AsyncMock(),
            AsyncMock(),
            _NAMESPACE,
            _MODEL_NAME,
            "default",
            CustomProfilePatchRequest(display_name="New"),
        )


@pytest.mark.asyncio
async def test_update_rejects_targeting_default_set_by_name() -> None:
    """Targeting the classified Default set by its real resource name is refused."""
    cr = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    env = _patch_update_environment(cr=cr, profile_sets=[default_set], profiles=[], services=[])
    with env[0], env[1], env[2], env[3], env[4], env[5], env[6]:
        with pytest.raises(ValidationException):
            await update_custom_model_profile(
                AsyncMock(),
                AsyncMock(),
                _NAMESPACE,
                _MODEL_NAME,
                _DEFAULT_SET,
                CustomProfilePatchRequest(display_name="New"),
            )


@pytest.mark.asyncio
async def test_update_rejects_empty_body() -> None:
    """A body carrying no recognised field is a 400 after exclude_unset."""
    cr = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named = _make_named_set()
    env = _patch_update_environment(cr=cr, profile_sets=[default_set, named], profiles=[], services=[])
    with env[0], env[1], env[2], env[3], env[4], env[5], env[6]:
        with pytest.raises(ValidationException):
            await update_custom_model_profile(
                AsyncMock(), AsyncMock(), _NAMESPACE, _MODEL_NAME, _NAMED_SET, CustomProfilePatchRequest()
            )


@pytest.mark.asyncio
async def test_update_rejects_duplicate_display_name() -> None:
    """Renaming to a name already used by a sibling profile is a conflict (409)."""
    cr = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named = _make_named_set(display_name="High speed")
    sibling = make_aim_profile_set(
        name=f"{_MODEL_NAME}-taken-aaaaaaaa", model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    sibling.metadata.annotations = {PROFILE_DISPLAY_NAME_ANNOTATION: "Taken"}
    env = _patch_update_environment(cr=cr, profile_sets=[default_set, named, sibling], profiles=[], services=[])
    with env[0], env[1], env[2], env[3], env[4], env[5] as mock_patch, env[6]:
        with pytest.raises(ConflictException):
            await update_custom_model_profile(
                AsyncMock(),
                AsyncMock(),
                _NAMESPACE,
                _MODEL_NAME,
                _NAMED_SET,
                CustomProfilePatchRequest(display_name="Taken"),
            )
    mock_patch.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_refused_while_profile_in_use() -> None:
    """An edit is refused (nothing written) while a deployment pins the set's derived profile."""
    cr = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named = _make_named_set()
    derived = _make_profile("tinyllama-tp8-latency", owner_set=_NAMED_SET)
    service = _make_service("tinyllama-tp8-latency", display_name="summarizer-prod")
    env = _patch_update_environment(cr=cr, profile_sets=[default_set, named], profiles=[derived], services=[service])
    with env[0], env[1], env[2], env[3], env[4], env[5] as mock_patch, env[6]:
        with pytest.raises(ConflictException) as exc:
            await update_custom_model_profile(
                AsyncMock(),
                AsyncMock(),
                _NAMESPACE,
                _MODEL_NAME,
                _NAMED_SET,
                CustomProfilePatchRequest(display_name="High speed v2"),
            )
    assert exc.value.detail is not None
    blocking = exc.value.detail["blockingServices"]
    assert blocking[0]["displayName"] == "summarizer-prod"
    mock_patch.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_reasserts_in_use_guard_inside_lock_before_patch() -> None:
    """The in-use guard re-reads AIMServices inside the lock, not from the initial context load."""
    cr = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named = _make_named_set()
    derived = _make_profile("tinyllama-tp8-latency", owner_set=_NAMED_SET)
    service = _make_service("tinyllama-tp8-latency")
    list_services = AsyncMock(side_effect=[[], [service]])
    env = _patch_update_environment(cr=cr, profile_sets=[default_set, named], profiles=[derived], services=[])
    with env[0], env[1], env[2], env[3], env[4], env[5] as mock_patch, env[6]:
        with patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.list_aim_services_for_model", list_services):
            with pytest.raises(ConflictException):
                await update_custom_model_profile(
                    AsyncMock(),
                    AsyncMock(),
                    _NAMESPACE,
                    _MODEL_NAME,
                    _NAMED_SET,
                    CustomProfilePatchRequest(display_name="High speed v2"),
                )
    mock_patch.assert_not_awaited()
    assert list_services.await_count == 2


@pytest.mark.asyncio
async def test_update_rejects_unresolvable_axes() -> None:
    """A config edit whose axes match no base profile is a 400."""
    cr = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named = _make_named_set()
    env = _patch_update_environment(
        cr=cr,
        profile_sets=[default_set, named],
        profiles=[],
        services=[],
        base_profiles=[_make_base_role_profile(accelerator_count=8)],
    )
    with env[0], env[1], env[2], env[3], env[4], env[5] as mock_patch, env[6]:
        with pytest.raises(ValidationException):
            await update_custom_model_profile(
                AsyncMock(),
                AsyncMock(),
                _NAMESPACE,
                _MODEL_NAME,
                _NAMED_SET,
                CustomProfilePatchRequest(accelerator_count=99),
            )
    mock_patch.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_raises_when_model_not_found() -> None:
    """A missing (or non-custom) model reads as not-found."""
    env = _patch_update_environment(cr=None, profile_sets=[], profiles=[], services=[])
    with env[0], env[1], env[2], env[3], env[4], env[5], env[6]:
        with pytest.raises(NotFoundException):
            await update_custom_model_profile(
                AsyncMock(),
                AsyncMock(),
                _NAMESPACE,
                _MODEL_NAME,
                _NAMED_SET,
                CustomProfilePatchRequest(display_name="New"),
            )


@pytest.mark.asyncio
async def test_update_raises_when_profile_not_found() -> None:
    """A set that does not belong to the model reads as not-found."""
    cr = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    env = _patch_update_environment(cr=cr, profile_sets=[default_set], profiles=[], services=[])
    with env[0], env[1], env[2], env[3], env[4], env[5], env[6]:
        with pytest.raises(NotFoundException):
            await update_custom_model_profile(
                AsyncMock(),
                AsyncMock(),
                _NAMESPACE,
                _MODEL_NAME,
                f"{_MODEL_NAME}-ghost-99999999",
                CustomProfilePatchRequest(display_name="New"),
            )


@pytest.mark.asyncio
async def test_update_propagates_upstream_patch_failure() -> None:
    """A Kubernetes patch failure surfaces as an external-service error (502)."""
    cr = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named = _make_named_set()
    context = _patch_context(cr=cr, profile_sets=[default_set, named], profiles=[], services=[])
    with (
        context[0],
        context[1],
        context[2],
        context[3],
        patch(f"{_SERVICE_PATCH_BASE}.list_base_role_profiles", AsyncMock(return_value=[_make_base_role_profile()])),
        patch(
            f"{_SERVICE_PATCH_BASE}.aims_gateway.patch_aim_profile_set",
            AsyncMock(side_effect=ExternalServiceError("k8s down")),
        ),
        patch(f"{_SERVICE_PATCH_BASE}._upsert_manifest_documents_to_s3_unlocked", AsyncMock()),
    ):
        with pytest.raises(ExternalServiceError):
            await update_custom_model_profile(
                AsyncMock(),
                AsyncMock(),
                _NAMESPACE,
                _MODEL_NAME,
                _NAMED_SET,
                CustomProfilePatchRequest(display_name="High speed v2"),
            )


@pytest.mark.asyncio
async def test_update_s3_mirror_failure_is_non_fatal() -> None:
    """The CR patch is authoritative: an S3 mirror failure is logged, not surfaced."""
    cr = _make_custom_model()
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named = _make_named_set(display_name="High speed")
    patched = _make_named_set(display_name="High speed v2")
    context = _patch_context(cr=cr, profile_sets=[default_set, named], profiles=[], services=[])
    with (
        context[0],
        context[1],
        context[2],
        context[3],
        patch(f"{_SERVICE_PATCH_BASE}.list_base_role_profiles", AsyncMock(return_value=[_make_base_role_profile()])),
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.patch_aim_profile_set", AsyncMock(return_value=patched)),
        patch(
            f"{_SERVICE_PATCH_BASE}._upsert_manifest_documents_to_s3_unlocked",
            AsyncMock(side_effect=RuntimeError("minio down")),
        ),
    ):
        row = await update_custom_model_profile(
            AsyncMock(),
            AsyncMock(),
            _NAMESPACE,
            _MODEL_NAME,
            _NAMED_SET,
            CustomProfilePatchRequest(display_name="High speed v2"),
        )

    assert row.display_name == "High speed v2"
    assert row.resource_name == _NAMED_SET


# ---------------------------------------------------------------------------
# update_custom_model_profile — router
# ---------------------------------------------------------------------------

_UPDATE_URL = f"/v1/projects/{_NAMESPACE}/models/{_MODEL_NAME}/profiles/{_NAMED_SET}"
_UPDATE_DEFAULT_URL = f"/v1/projects/{_NAMESPACE}/models/{_MODEL_NAME}/profiles/default"
# The endpoint depends on the Minio client (for the S3 mirror refresh), which is
# not stubbed by BASE_OVERRIDES — mirror the patch/onboard endpoint tests.
_UPDATE_OVERRIDES = {**BASE_OVERRIDES, get_minio_client: lambda: None}


@override_dependencies(_UPDATE_OVERRIDES)
@patch("app.projects.router.update_custom_model_profile", new_callable=AsyncMock)
def test_update_endpoint_returns_200(mock_update: AsyncMock) -> None:
    mock_update.return_value = _sample_row(is_default=False)
    with TestClient(app) as client:
        response = client.patch(_UPDATE_URL, json={"displayName": "High speed v2"})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["name"] == _NAMED_SET
    assert body["isDefault"] is False


@override_dependencies(_UPDATE_OVERRIDES)
@patch("app.projects.router.update_custom_model_profile", new_callable=AsyncMock)
def test_update_endpoint_rejects_default_literal_with_422(mock_update: AsyncMock) -> None:
    """The 'default' path segment is refused at the path boundary before the service runs."""
    with TestClient(app) as client:
        response = client.patch(_UPDATE_DEFAULT_URL, json={"displayName": "High speed v2"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    mock_update.assert_not_awaited()


@override_dependencies(_UPDATE_OVERRIDES)
@patch("app.projects.router.update_custom_model_profile", new_callable=AsyncMock)
def test_update_endpoint_rejects_reserved_name_with_422(mock_update: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.patch(_UPDATE_URL, json={"displayName": "Default"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    mock_update.assert_not_awaited()


@override_dependencies(_UPDATE_OVERRIDES)
@patch(
    "app.projects.router.update_custom_model_profile",
    new_callable=AsyncMock,
    side_effect=ConflictException("in use", detail={"blockingServices": [{"displayName": "summarizer-prod"}]}),
)
def test_update_endpoint_returns_409(mock_update: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.patch(_UPDATE_URL, json={"displayName": "High speed v2"})
    assert response.status_code == status.HTTP_409_CONFLICT


@override_dependencies(_UPDATE_OVERRIDES)
@patch(
    "app.projects.router.update_custom_model_profile",
    new_callable=AsyncMock,
    side_effect=ValidationException("empty body"),
)
def test_update_endpoint_returns_400(mock_update: AsyncMock) -> None:
    """Service-layer ValidationException maps to 400 (empty body, unresolvable axes)."""
    with TestClient(app) as client:
        response = client.patch(_UPDATE_URL, json={"acceleratorCount": 99})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@override_dependencies(_UPDATE_OVERRIDES)
@patch(
    "app.projects.router.update_custom_model_profile",
    new_callable=AsyncMock,
    side_effect=NotFoundException("nope"),
)
def test_update_endpoint_returns_404(mock_update: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.patch(_UPDATE_URL, json={"displayName": "High speed v2"})
    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(_UPDATE_OVERRIDES)
@patch(
    "app.projects.router.update_custom_model_profile",
    new_callable=AsyncMock,
    side_effect=ExternalServiceError("k8s down"),
)
def test_update_endpoint_returns_502_on_upstream_failure(mock_update: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.patch(_UPDATE_URL, json={"displayName": "High speed v2"})
    assert response.status_code == status.HTTP_502_BAD_GATEWAY


# ---------------------------------------------------------------------------
# delete_custom_model_profile — service
# ---------------------------------------------------------------------------

_NAMED_DERIVED_PROFILE = "tinyllama-tp4-latency"


def _manifest_doc(kind: str, name: str) -> dict[str, Any]:
    return {
        "apiVersion": "aim.eai.amd.com/v1alpha2",
        "kind": kind,
        "metadata": {"name": name, "namespace": _NAMESPACE},
    }


def _patch_delete_environment(
    *,
    cr: MagicMock | None,
    profile_sets: list,
    profiles: list[AIMProfileResource],
    services: list[AIMServiceResource],
    existing_manifest: list[dict[str, Any]] | None = None,
    delete_mock: AsyncMock | None = None,
    write_mock: AsyncMock | None = None,
    manifest_delete_mock: AsyncMock | None = None,
) -> tuple[tuple[AbstractContextManager[Any], ...], AsyncMock, AsyncMock]:
    """Patch the profile reads plus the profile-set delete and manifest read/write/delete."""
    delete_mock = delete_mock or AsyncMock()
    write_mock = write_mock or AsyncMock()
    read_mock = AsyncMock(return_value=list(existing_manifest or []))
    ctx = (
        *_patch_context(cr=cr, profile_sets=profile_sets, profiles=profiles, services=services),
        patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.delete_aim_profile_set", delete_mock),
        patch(f"{_SERVICE_PATCH_BASE}.read_manifest_from_s3", read_mock),
        patch(f"{_SERVICE_PATCH_BASE}.write_manifest_to_s3", write_mock),
        patch(f"{_SERVICE_PATCH_BASE}.delete_manifest_from_s3", manifest_delete_mock or AsyncMock()),
    )
    return ctx, delete_mock, write_mock


@pytest.mark.asyncio
async def test_delete_removes_set_and_drops_derived_doc() -> None:
    """A named-profile delete removes its set and drops the derived profile's mirror doc."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named_set = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    derived = _make_profile(_NAMED_DERIVED_PROFILE, owner_set=_NAMED_SET)
    model_doc = _manifest_doc("AIMModel", _MODEL_NAME)
    profile_doc = _manifest_doc("AIMProfile", _NAMED_DERIVED_PROFILE)

    ctx, delete_mock, write_mock = _patch_delete_environment(
        cr=_make_model_cr(),
        profile_sets=[default_set, named_set],
        profiles=[derived],
        services=[],
        existing_manifest=[model_doc, profile_doc],
    )
    with ExitStack() as stack:
        for c in ctx:
            stack.enter_context(c)
        await delete_custom_model_profile(AsyncMock(), MagicMock(), _NAMESPACE, _MODEL_NAME, _NAMED_SET)

    delete_mock.assert_awaited_once_with(ANY, _NAMESPACE, _NAMED_SET)
    # The AIMModel scaffold survives; only the derived AIMProfile doc is dropped.
    write_mock.assert_awaited_once()
    assert write_mock.await_args is not None
    written_docs = write_mock.await_args.args[-1]
    assert written_docs == [model_doc]


@pytest.mark.asyncio
async def test_delete_skips_s3_write_when_nothing_mirrored() -> None:
    """When the derived profile was never mirrored, the delete still succeeds without a write."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named_set = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    derived = _make_profile(_NAMED_DERIVED_PROFILE, owner_set=_NAMED_SET)

    ctx, delete_mock, write_mock = _patch_delete_environment(
        cr=_make_model_cr(),
        profile_sets=[default_set, named_set],
        profiles=[derived],
        services=[],
        existing_manifest=[_manifest_doc("AIMModel", _MODEL_NAME)],
    )
    with ExitStack() as stack:
        for c in ctx:
            stack.enter_context(c)
        await delete_custom_model_profile(AsyncMock(), MagicMock(), _NAMESPACE, _MODEL_NAME, _NAMED_SET)

    delete_mock.assert_awaited_once_with(ANY, _NAMESPACE, _NAMED_SET)
    write_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_removes_manifest_object_when_last_document_dropped() -> None:
    """A manifest left with no documents is removed, not left holding the stale profile."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named_set = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    derived = _make_profile(_NAMED_DERIVED_PROFILE, owner_set=_NAMED_SET)
    manifest_delete_mock = AsyncMock()

    ctx, delete_mock, write_mock = _patch_delete_environment(
        cr=_make_model_cr(),
        profile_sets=[default_set, named_set],
        profiles=[derived],
        services=[],
        # A manifest missing the AIMModel scaffold: hand-edited or written by an older version.
        existing_manifest=[_manifest_doc("AIMProfile", _NAMED_DERIVED_PROFILE)],
        manifest_delete_mock=manifest_delete_mock,
    )
    with ExitStack() as stack:
        for c in ctx:
            stack.enter_context(c)
        await delete_custom_model_profile(AsyncMock(), MagicMock(), _NAMESPACE, _MODEL_NAME, _NAMED_SET)

    delete_mock.assert_awaited_once_with(ANY, _NAMESPACE, _NAMED_SET)
    # An empty manifest cannot be serialized, so the object goes away instead.
    write_mock.assert_not_awaited()
    manifest_delete_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_rejects_default_alias() -> None:
    """Deleting the literal ``default`` is refused before any cluster read."""
    ctx, delete_mock, _ = _patch_delete_environment(cr=_make_model_cr(), profile_sets=[], profiles=[], services=[])
    with ExitStack() as stack:
        for c in ctx:
            stack.enter_context(c)
        with pytest.raises(DefaultProfileImmutableError):
            await delete_custom_model_profile(AsyncMock(), MagicMock(), _NAMESPACE, _MODEL_NAME, "default")
    delete_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_rejects_default_by_resource_name() -> None:
    """Deleting the Default addressed by its engine set name is refused (both spellings)."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    ctx, delete_mock, _ = _patch_delete_environment(
        cr=_make_model_cr(), profile_sets=[default_set], profiles=[], services=[]
    )
    with ExitStack() as stack:
        for c in ctx:
            stack.enter_context(c)
        with pytest.raises(DefaultProfileImmutableError):
            await delete_custom_model_profile(AsyncMock(), MagicMock(), _NAMESPACE, _MODEL_NAME, _DEFAULT_SET)
    delete_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_raises_not_found_when_model_missing() -> None:
    """A missing (or non-custom) model reads as not-found."""
    ctx, delete_mock, _ = _patch_delete_environment(cr=None, profile_sets=[], profiles=[], services=[])
    with ExitStack() as stack:
        for c in ctx:
            stack.enter_context(c)
        with pytest.raises(NotFoundException):
            await delete_custom_model_profile(AsyncMock(), MagicMock(), _NAMESPACE, _MODEL_NAME, _NAMED_SET)
    delete_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_raises_not_found_when_profile_missing() -> None:
    """A resource name that belongs to no set on this model reads as not-found."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    ctx, delete_mock, _ = _patch_delete_environment(
        cr=_make_model_cr(), profile_sets=[default_set], profiles=[], services=[]
    )
    with ExitStack() as stack:
        for c in ctx:
            stack.enter_context(c)
        with pytest.raises(NotFoundException):
            await delete_custom_model_profile(AsyncMock(), MagicMock(), _NAMESPACE, _MODEL_NAME, "no-such-set")
    delete_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_refuses_when_in_use_by_deployment() -> None:
    """A live deployment pinning a derived profile blocks the delete with a 409 conflict."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named_set = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    derived = _make_profile(_NAMED_DERIVED_PROFILE, owner_set=_NAMED_SET)
    pinning_service = _make_service(_NAMED_DERIVED_PROFILE, display_name="summarizer-prod")

    ctx, delete_mock, _ = _patch_delete_environment(
        cr=_make_model_cr(),
        profile_sets=[default_set, named_set],
        profiles=[derived],
        services=[pinning_service],
    )
    with ExitStack() as stack:
        for c in ctx:
            stack.enter_context(c)
        with pytest.raises(ConflictException) as exc_info:
            await delete_custom_model_profile(AsyncMock(), MagicMock(), _NAMESPACE, _MODEL_NAME, _NAMED_SET)

    assert exc_info.value.detail is not None
    blocking = exc_info.value.detail["blockingServices"]
    assert blocking[0]["displayName"] == "summarizer-prod"
    delete_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_reasserts_in_use_guard_inside_lock_before_delete() -> None:
    """The in-use guard re-reads AIMServices inside the lock, not just from the initial context load.

    A deployment that pins the derived profile only after the endpoint's first
    read still blocks the delete: the under-lock re-check sees it and refuses,
    so aim-engine never garbage-collects a profile a live workload deployed.
    """
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named_set = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    derived = _make_profile(_NAMED_DERIVED_PROFILE, owner_set=_NAMED_SET)
    pinning_service = _make_service(_NAMED_DERIVED_PROFILE, display_name="summarizer-prod")
    # Empty on the initial context load, pinned on the under-lock re-check.
    list_services = AsyncMock(side_effect=[[], [pinning_service]])

    ctx, delete_mock, _ = _patch_delete_environment(
        cr=_make_model_cr(),
        profile_sets=[default_set, named_set],
        profiles=[derived],
        services=[],
    )
    with ExitStack() as stack:
        for c in ctx:
            stack.enter_context(c)
        stack.enter_context(patch(f"{_SERVICE_PATCH_BASE}.aims_gateway.list_aim_services_for_model", list_services))
        with pytest.raises(ConflictException):
            await delete_custom_model_profile(AsyncMock(), MagicMock(), _NAMESPACE, _MODEL_NAME, _NAMED_SET)

    delete_mock.assert_not_awaited()
    assert list_services.await_count == 2


@pytest.mark.asyncio
async def test_delete_propagates_upstream_delete_failure() -> None:
    """A Kubernetes failure deleting the set surfaces as an external-service error (502)."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named_set = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    derived = _make_profile(_NAMED_DERIVED_PROFILE, owner_set=_NAMED_SET)
    delete_mock = AsyncMock(side_effect=ExternalServiceError("k8s down"))

    ctx, _, write_mock = _patch_delete_environment(
        cr=_make_model_cr(),
        profile_sets=[default_set, named_set],
        profiles=[derived],
        services=[],
        delete_mock=delete_mock,
    )
    with ExitStack() as stack:
        for c in ctx:
            stack.enter_context(c)
        with pytest.raises(ExternalServiceError):
            await delete_custom_model_profile(AsyncMock(), MagicMock(), _NAMESPACE, _MODEL_NAME, _NAMED_SET)
    write_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_s3_failure_is_non_fatal() -> None:
    """The CR delete is authoritative: a failing S3 mirror refresh does not fail the request."""
    default_set = make_aim_profile_set(name=_DEFAULT_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE)
    named_set = make_aim_profile_set(
        name=_NAMED_SET, model_name=_MODEL_NAME, namespace=_NAMESPACE, is_aiwb_authored=True
    )
    derived = _make_profile(_NAMED_DERIVED_PROFILE, owner_set=_NAMED_SET)
    write_mock = AsyncMock(side_effect=ExternalServiceError("s3 down"))

    ctx, delete_mock, _ = _patch_delete_environment(
        cr=_make_model_cr(),
        profile_sets=[default_set, named_set],
        profiles=[derived],
        services=[],
        existing_manifest=[_manifest_doc("AIMModel", _MODEL_NAME), _manifest_doc("AIMProfile", _NAMED_DERIVED_PROFILE)],
        write_mock=write_mock,
    )
    with ExitStack() as stack:
        for c in ctx:
            stack.enter_context(c)
        # No exception despite the S3 write failing.
        await delete_custom_model_profile(AsyncMock(), MagicMock(), _NAMESPACE, _MODEL_NAME, _NAMED_SET)

    delete_mock.assert_awaited_once_with(ANY, _NAMESPACE, _NAMED_SET)
    write_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# delete_custom_model_profile — router
# ---------------------------------------------------------------------------

_DELETE_OVERRIDES: dict[Any, Any] = {**BASE_OVERRIDES, get_minio_client: lambda: None}
_DELETE_URL = f"/v1/projects/{_NAMESPACE}/models/{_MODEL_NAME}/profiles/{_NAMED_SET}"


@override_dependencies(_DELETE_OVERRIDES)
@patch("app.projects.router.delete_custom_model_profile", new_callable=AsyncMock)
def test_delete_endpoint_returns_204(mock_delete: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.delete(_DELETE_URL)
    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_delete.assert_awaited_once()


@override_dependencies(_DELETE_OVERRIDES)
@patch(
    "app.projects.router.delete_custom_model_profile",
    new_callable=AsyncMock,
    side_effect=DefaultProfileImmutableError("cannot delete Default"),
)
def test_delete_endpoint_returns_422_on_default(mock_delete: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.delete(f"/v1/projects/{_NAMESPACE}/models/{_MODEL_NAME}/profiles/default")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(_DELETE_OVERRIDES)
@patch(
    "app.projects.router.delete_custom_model_profile",
    new_callable=AsyncMock,
    side_effect=ConflictException("in use", detail={"blockingServices": [{"displayName": "summarizer-prod"}]}),
)
def test_delete_endpoint_returns_409_when_in_use(mock_delete: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.delete(_DELETE_URL)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["additionalInfo"]["blockingServices"][0]["displayName"] == "summarizer-prod"


@override_dependencies(_DELETE_OVERRIDES)
@patch(
    "app.projects.router.delete_custom_model_profile",
    new_callable=AsyncMock,
    side_effect=NotFoundException("nope"),
)
def test_delete_endpoint_returns_404(mock_delete: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.delete(_DELETE_URL)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(_DELETE_OVERRIDES)
@patch(
    "app.projects.router.delete_custom_model_profile",
    new_callable=AsyncMock,
    side_effect=ExternalServiceError("k8s down"),
)
def test_delete_endpoint_returns_502_on_upstream_failure(mock_delete: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.delete(_DELETE_URL)
    assert response.status_code == status.HTTP_502_BAD_GATEWAY
