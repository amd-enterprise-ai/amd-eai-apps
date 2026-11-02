# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for lazily narrowing an existing custom model's Default selector on edit.

Editing a custom model's Default (a runtime-profile PATCH) is the opportunity to
narrow the engine-owned derivation from its broad ``role: base`` + ``modelRef``
selector — which fans out to every base combination — down to the single profile
identified by the submitted runtime axes. Narrowing is best-effort: an unnarrowed
Default is fully functional, so anything that cannot be resolved to exactly one
base profile is left broad rather than emptied.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kubernetes_asyncio.client import CustomObjectsApi
from kubernetes_asyncio.client.exceptions import ApiException

from api_common.exceptions import ConflictException
from app.aims.constants import (
    AIM_MODEL_LABEL,
    AIM_PROFILE_PLURAL,
    AIM_PROFILE_ROLE_LABEL,
    AIM_PROFILE_SET_PLURAL,
    AIM_PROFILE_SET_RESOURCE,
    AIM_SERVICE_PLURAL,
)
from app.aims.crds import AIMModelResource, AIMProfileResource, AIMProfileSetResource, AIMServiceResource
from app.custom_models.constants import MODEL_PRECISION_ANNOTATION
from app.custom_models.schemas import CustomModelPatchRequest
from app.custom_models.service import (
    _compose_narrowed_default_patch,
    _narrowing_axes_from_profile,
    _resolve_narrowing_base_profile,
    patch_onboarded_model,
)
from app.dispatch.crds import K8sMetadata
from app.dispatch.kube_client import KubernetesClient
from app.minio import MinioClient
from app.workloads.constants import DISPLAY_NAME_ANNOTATION, MODEL_NAME_LABEL, MODEL_SOURCE_TYPE_LABEL
from app.workloads.enums import ModelSourceType

_NS = "test-namespace"
_MODEL_NAME = "llama-3-8b-import-12345678"
_DEFAULT_SET_NAME = "llama-3-8b-profiles-abcd1234"
_REPO_ID = "meta-llama/Meta-Llama-3-8B-Instruct"
_IMAGE = "docker.io/amdenterpriseai/aim:1.0.0"
_BASE_MODEL = "aim-base"


def _model(*, selector_extra: dict[str, Any] | None = None, precision: str | None = None) -> AIMModelResource:
    selector: dict[str, Any] = {"role": "base", "modelRef": {"name": _BASE_MODEL, "scope": "Namespace"}}
    if selector_extra:
        selector.update(selector_extra)
    annotations = {DISPLAY_NAME_ANNOTATION: "Llama 3 8B"}
    if precision is not None:
        annotations[MODEL_PRECISION_ANNOTATION] = precision
    return AIMModelResource(
        metadata=K8sMetadata(
            name=_MODEL_NAME,
            namespace=_NS,
            labels={MODEL_NAME_LABEL: "Llama-3-8B", MODEL_SOURCE_TYPE_LABEL: ModelSourceType.CUSTOM},
            annotations=annotations,
        ),
        spec={
            "profiles": {
                "derivedFrom": {"selector": selector},
                "versionPolicy": "all",
                "overrides": {
                    "aimId": _REPO_ID,
                    "modelId": _REPO_ID,
                    "image": _IMAGE,
                    "modelSources": [{"modelId": _REPO_ID, "sourceUri": "s3://b/k/"}],
                },
            }
        },
    )


def _default_set() -> AIMProfileSetResource:
    # No PROFILE_ORIGIN_LABEL => classified as the engine-owned Default.
    return AIMProfileSetResource(
        metadata=K8sMetadata(name=_DEFAULT_SET_NAME, namespace=_NS, labels={AIM_MODEL_LABEL: _MODEL_NAME}),
        spec={"selector": {"role": "base", "modelRef": {"name": _BASE_MODEL, "scope": "Namespace"}}, "overrides": {}},
    )


def _profile(
    name: str,
    *,
    accelerator_model: str = "MI300X",
    accelerator_count: int = 2,
    precision: str = "fp16",
    metric: str = "latency",
    ready: bool = True,
    owned_by_default: bool = True,
) -> AIMProfileResource:
    owner_references = [{"kind": AIM_PROFILE_SET_RESOURCE, "name": _DEFAULT_SET_NAME}] if owned_by_default else []
    return AIMProfileResource(
        metadata=K8sMetadata(
            name=name,
            namespace=_NS,
            labels={AIM_MODEL_LABEL: _MODEL_NAME},
            owner_references=owner_references,
        ),
        spec={
            "acceleratorModel": accelerator_model,
            "acceleratorCount": accelerator_count,
            "precision": precision,
            "metric": metric,
        },
        status={"status": "Ready" if ready else "Pending"},
    )


def _base_profile(
    *, accelerator_model: str = "MI300X", accelerator_count: int = 2, precision: str = "fp16", metric: str = "latency"
) -> AIMProfileResource:
    return _profile(
        f"base-{accelerator_model}-{accelerator_count}-{precision}-{metric}",
        accelerator_model=accelerator_model,
        accelerator_count=accelerator_count,
        precision=precision,
        metric=metric,
        owned_by_default=False,
    )


def _service(name: str, *, pinned_profile: str) -> AIMServiceResource:
    return AIMServiceResource(
        metadata=K8sMetadata(name=name, namespace=_NS),
        spec={"model": {"name": _MODEL_NAME}, "profile": {"name": pinned_profile}},
    )


# ---------------------------------------------------------------------------
# Pure composition helper
# ---------------------------------------------------------------------------


def test_narrowing_axes_from_profile_reads_the_spec_tuple() -> None:
    profile = _profile("p", accelerator_model="MI300X", accelerator_count=4, precision="fp8", metric="throughput")
    assert _narrowing_axes_from_profile(profile) == {
        "acceleratorModel": "MI300X",
        "acceleratorCount": 4,
        "precision": "fp8",
        "metric": "throughput",
    }


def test_compose_narrows_selector_and_overrides_from_target_axes() -> None:
    target_axes = {
        "acceleratorModel": "MI300X",
        "acceleratorCount": 2,
        "precision": "fp16",
        "metric": "latency",
    }
    fragment = _compose_narrowed_default_patch(_model(), target_axes)

    assert fragment is not None
    selector = fragment["derivedFrom"]["selector"]
    # Base derivation is preserved, axes are added.
    assert selector["role"] == "base"
    assert selector["modelRef"] == {"name": _BASE_MODEL, "scope": "Namespace"}
    assert selector["acceleratorCount"] == 2
    assert selector["precision"] == "fp16"
    # count == tensor-parallel-size: the overrides count is composed from the same
    # source as the selector, so the two can never disagree.
    assert fragment["overrides"]["acceleratorCount"] == selector["acceleratorCount"]
    assert fragment["overrides"]["precision"] == "fp16"
    assert fragment["overrides"]["metric"] == "latency"


def test_compose_is_idempotent_when_selector_already_narrowed() -> None:
    already = {"acceleratorModel": "MI300X", "acceleratorCount": 2, "precision": "fp16", "metric": "latency"}
    fragment = _compose_narrowed_default_patch(_model(selector_extra=already), already)
    assert fragment is None


def test_compose_skips_when_model_has_no_base_derivation() -> None:
    model = _model()
    model.spec.profiles.derived_from.selector.role = None
    axes = _narrowing_axes_from_profile(_profile("p"))
    assert _compose_narrowed_default_patch(model, axes) is None


def test_target_axes_use_the_unique_base_profile_matching_the_submission() -> None:
    base_profiles = [
        _base_profile(accelerator_count=2, precision="fp16"),
        _base_profile(accelerator_count=1, precision="fp8"),
    ]
    base = _resolve_narrowing_base_profile(
        {"acceleratorModel": "MI300X", "acceleratorCount": 1, "precision": "fp8"},
        base_profiles,
    )
    assert base is not None
    assert _narrowing_axes_from_profile(base) == {
        "acceleratorModel": "MI300X",
        "acceleratorCount": 1,
        "precision": "fp8",
        "metric": "latency",
    }


def test_target_axes_skip_rather_than_empty_when_submission_matches_no_base_profile() -> None:
    base_profiles = [
        _base_profile(accelerator_count=1),
        _base_profile(accelerator_count=2),
        _base_profile(accelerator_count=4),
    ]
    assert _resolve_narrowing_base_profile({"acceleratorCount": 8}, base_profiles) is None


def test_target_axes_skip_when_submission_matches_multiple_base_profiles() -> None:
    duplicate = [
        _base_profile(accelerator_count=2, precision="fp16"),
        _base_profile(accelerator_count=2, precision="fp16"),
    ]
    assert _resolve_narrowing_base_profile({"acceleratorCount": 2}, duplicate) is None


# ---------------------------------------------------------------------------
# Integration through the PATCH path
# ---------------------------------------------------------------------------


def _list_side_effect(
    *,
    profile_sets: list[AIMProfileSetResource],
    model_profiles: list[AIMProfileResource],
    base_profiles: list[AIMProfileResource],
    services: list[AIMServiceResource] | None = None,
) -> Any:
    async def _dispatch(**kwargs: Any) -> dict[str, Any]:
        plural = kwargs.get("plural")
        label = kwargs.get("label_selector") or ""
        if plural == AIM_PROFILE_SET_PLURAL:
            return {"items": [s.model_dump(by_alias=True) for s in profile_sets]}
        if plural == AIM_PROFILE_PLURAL:
            if label.startswith(AIM_PROFILE_ROLE_LABEL):
                return {"items": [p.model_dump(by_alias=True) for p in base_profiles]}
            return {"items": [p.model_dump(by_alias=True) for p in model_profiles]}
        if plural == AIM_SERVICE_PLURAL:
            return {"items": [s.model_dump(by_alias=True) for s in (services or [])]}
        return {"items": []}

    return _dispatch


@pytest.fixture
def mock_minio_client() -> MagicMock:
    return MagicMock(spec=MinioClient)


@pytest.fixture
def mock_profile_gateway() -> Any:
    """Stub the live AIMProfile readiness lookup and image-ref repatch used by a runtime edit."""
    profile = _profile("live-profile")
    with (
        patch(
            "app.custom_models.service._default_effective_profile",
            new_callable=AsyncMock,
            return_value=profile,
        ) as find_mock,
        patch(
            "app.custom_models.service.patch_aim_profile",
            new_callable=AsyncMock,
            return_value=profile,
        ) as patch_mock,
    ):
        yield find_mock, patch_mock


def _kube_client(model: AIMModelResource, list_side_effect: Any) -> MagicMock:
    mock = MagicMock(spec=KubernetesClient)
    mock.custom_objects = MagicMock(spec=CustomObjectsApi)
    mock.custom_objects.get_namespaced_custom_object = AsyncMock(return_value=model.model_dump(by_alias=True))
    mock.custom_objects.patch_namespaced_custom_object = AsyncMock(return_value=model.model_dump(by_alias=True))
    mock.custom_objects.list_namespaced_custom_object = AsyncMock(side_effect=list_side_effect)
    return mock


async def _run_patch(
    mock_kube_client: MagicMock, mock_minio_client: MagicMock, request: CustomModelPatchRequest
) -> None:
    with patch("app.custom_models.service._upsert_manifest_documents_to_s3_unlocked", new_callable=AsyncMock):
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace=_NS,
            name=_MODEL_NAME,
            request=request,
        )


def _runtime_patch(
    *,
    accelerator_count: int = 2,
    precision: str = "fp16",
    metric: str | None = "latency",
) -> CustomModelPatchRequest:
    custom_profile: dict[str, Any] = {
        "acceleratorModel": "MI300X",
        "acceleratorCount": accelerator_count,
        "precision": precision,
    }
    if metric is not None:
        custom_profile["metric"] = metric
    return CustomModelPatchRequest(image=_IMAGE, custom_profile=custom_profile)


async def test_patch_narrows_default_to_submitted_configuration_with_count_agreeing(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    model = _model()
    profiles = [_profile("p-fp16-tp2", accelerator_count=2, precision="fp16")]
    base = [_base_profile(accelerator_count=2, precision="fp16"), _base_profile(accelerator_count=1, precision="fp8")]
    mock_kube_client = _kube_client(
        model, _list_side_effect(profile_sets=[_default_set()], model_profiles=profiles, base_profiles=base)
    )

    await _run_patch(mock_kube_client, mock_minio_client, _runtime_patch())

    body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    selector = body["spec"]["profiles"]["derivedFrom"]["selector"]
    overrides = body["spec"]["profiles"]["overrides"]
    assert selector["acceleratorCount"] == 2
    assert selector["precision"] == "fp16"
    # count == tensor-parallel-size after narrowing.
    assert overrides["acceleratorCount"] == selector["acceleratorCount"]


async def test_patch_narrows_to_the_profile_id_match_when_derived_profile_axes_collapse(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    _, patch_profile_mock = mock_profile_gateway
    model = _model()
    base = [
        _base_profile(accelerator_count=2, metric="latency"),
        _base_profile(accelerator_count=2, metric="throughput"),
    ]
    for profile, profile_id in zip(base, ("tp2-latency", "tp2-throughput"), strict=True):
        profile.spec.profile_id = profile_id
    # Onboard overrides collapse the derived profiles onto the same axes (both
    # read metric=latency), so only profileId tells them apart.
    derived = [
        _profile(f"d-{pid}", accelerator_count=2, metric=metric)
        for pid, metric in (("tp2-latency", "latency"), ("tp2-throughput", "latency"))
    ]
    for profile, profile_id in zip(derived, ("tp2-latency", "tp2-throughput"), strict=True):
        profile.spec.profile_id = profile_id
    mock_kube_client = _kube_client(
        model, _list_side_effect(profile_sets=[_default_set()], model_profiles=derived, base_profiles=base)
    )

    await _run_patch(mock_kube_client, mock_minio_client, _runtime_patch(metric="throughput"))

    body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    selector = body["spec"]["profiles"]["derivedFrom"]["selector"]
    assert selector["acceleratorCount"] == 2
    assert selector["metric"] == "throughput"
    assert patch_profile_mock.call_args.kwargs["profile_name"] == "d-tp2-throughput"


async def test_patch_skips_narrowing_when_no_derived_profile_carries_the_base_profile_id(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    model = _model()
    base = [_base_profile(accelerator_count=2, metric="latency")]
    base[0].spec.profile_id = "tp2-latency"
    derived = [_profile("d-unstamped", accelerator_count=2, metric="latency")]
    mock_kube_client = _kube_client(
        model, _list_side_effect(profile_sets=[_default_set()], model_profiles=derived, base_profiles=base)
    )

    await _run_patch(mock_kube_client, mock_minio_client, _runtime_patch())

    body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    assert "derivedFrom" not in body["spec"]["profiles"]


async def test_patch_narrowing_uses_submitted_axes_instead_of_old_effective_profile(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    # The old effective profile is fp16/tp2, but the edit explicitly submits
    # fp8/tp1. Narrowing must follow the submitted configuration.
    model = _model()
    profiles = [
        _profile("p-fp16-tp2", accelerator_count=2, precision="fp16"),
        _profile("p-fp8-tp1", accelerator_count=1, precision="fp8"),
    ]
    base = [_base_profile(accelerator_count=2, precision="fp16"), _base_profile(accelerator_count=1, precision="fp8")]
    mock_kube_client = _kube_client(
        model, _list_side_effect(profile_sets=[_default_set()], model_profiles=profiles, base_profiles=base)
    )

    await _run_patch(
        mock_kube_client,
        mock_minio_client,
        _runtime_patch(accelerator_count=1, precision="fp8"),
    )

    selector = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]["spec"][
        "profiles"
    ]["derivedFrom"]["selector"]
    assert selector["precision"] == "fp8"
    assert selector["acceleratorCount"] == 1


async def test_patch_narrowing_resolves_unique_metric_when_edit_does_not_submit_one(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    model = _model()
    profiles = [
        _profile("p-fp16-tp2", accelerator_count=2, precision="fp16"),
        _profile("p-fp8-tp1", accelerator_count=1, precision="fp8"),
    ]
    base = [_base_profile(accelerator_count=2, precision="fp16"), _base_profile(accelerator_count=1, precision="fp8")]
    mock_kube_client = _kube_client(
        model, _list_side_effect(profile_sets=[_default_set()], model_profiles=profiles, base_profiles=base)
    )

    await _run_patch(
        mock_kube_client,
        mock_minio_client,
        _runtime_patch(accelerator_count=1, precision="fp8", metric=None),
    )

    selector = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]["spec"][
        "profiles"
    ]["derivedFrom"]["selector"]
    assert selector["precision"] == "fp8"
    assert selector["acceleratorCount"] == 1
    assert selector["metric"] == "latency"


async def test_patch_image_only_does_not_infer_a_narrowing_target(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    model = _model()
    profiles = [_profile("p-fp16-tp2")]
    base = [_base_profile()]
    mock_kube_client = _kube_client(
        model, _list_side_effect(profile_sets=[_default_set()], model_profiles=profiles, base_profiles=base)
    )

    await _run_patch(mock_kube_client, mock_minio_client, CustomModelPatchRequest(image="docker.io/x:2"))

    body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    assert "derivedFrom" not in body["spec"]["profiles"]


async def test_patch_is_idempotent_when_default_already_narrowed(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    # A model whose selector already carries the effective axes must not re-emit
    # a derivedFrom rewrite; only the overrides edit lands.
    already = {"acceleratorModel": "MI300X", "acceleratorCount": 2, "precision": "fp16", "metric": "latency"}
    model = _model(selector_extra=already)
    profiles = [_profile("p-fp16-tp2", accelerator_count=2, precision="fp16")]
    base = [_base_profile(accelerator_count=2, precision="fp16")]
    mock_kube_client = _kube_client(
        model, _list_side_effect(profile_sets=[_default_set()], model_profiles=profiles, base_profiles=base)
    )

    await _run_patch(mock_kube_client, mock_minio_client, _runtime_patch())

    body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    assert "derivedFrom" not in body["spec"]["profiles"]
    assert body["spec"]["profiles"]["overrides"]["image"] == _IMAGE


async def test_patch_leaves_default_broad_when_effective_matches_no_base_profile(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    # The effective profile records tp8 but the base only emits tp1/tp2/tp4:
    # narrowing is skipped (not emptied) and the image edit still applies.
    model = _model()
    profiles = [_profile("p-fp16-tp2", accelerator_count=2, precision="fp16")]
    base = [_base_profile(accelerator_count=1), _base_profile(accelerator_count=2), _base_profile(accelerator_count=4)]
    mock_kube_client = _kube_client(
        model, _list_side_effect(profile_sets=[_default_set()], model_profiles=profiles, base_profiles=base)
    )

    await _run_patch(
        mock_kube_client,
        mock_minio_client,
        _runtime_patch(accelerator_count=8),
    )

    body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    assert "derivedFrom" not in body["spec"]["profiles"]
    assert body["spec"]["profiles"]["overrides"]["image"] == _IMAGE


async def test_patch_mirrors_narrowed_selector_to_s3(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    model = _model()
    profiles = [_profile("p-fp16-tp2", accelerator_count=2, precision="fp16")]
    base = [_base_profile(accelerator_count=2, precision="fp16")]
    mock_kube_client = _kube_client(
        model, _list_side_effect(profile_sets=[_default_set()], model_profiles=profiles, base_profiles=base)
    )
    # The mirror reflects the patched CR the API returns, so return a narrowed CR.
    narrowed = _model(
        selector_extra={"acceleratorCount": 2, "precision": "fp16", "metric": "latency", "acceleratorModel": "MI300X"}
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=narrowed.model_dump(by_alias=True)
    )

    with patch(
        "app.custom_models.service._upsert_manifest_documents_to_s3_unlocked", new_callable=AsyncMock
    ) as sync_mock:
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace=_NS,
            name=_MODEL_NAME,
            request=_runtime_patch(),
        )

    documents = sync_mock.call_args.args[2]
    model_doc = next(doc for doc in documents if doc["kind"] == "AIMModel")
    selector = model_doc["spec"]["profiles"]["derivedFrom"]["selector"]
    assert selector["acceleratorCount"] == 2
    assert selector["precision"] == "fp16"


async def test_patch_refuses_narrowing_when_a_deployment_pins_a_default_profile(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    _, patch_profile_mock = mock_profile_gateway
    # Narrowing would prune the Default's other derived profiles; a live deployment
    # pinning one of them means the edit must be refused (409) with nothing written,
    # rather than silently breaking the workload.
    model = _model()
    profiles = [
        _profile("p-fp16-tp2", accelerator_count=2, precision="fp16"),
        _profile("p-fp8-tp1", accelerator_count=1, precision="fp8"),
    ]
    base = [_base_profile(accelerator_count=2, precision="fp16"), _base_profile(accelerator_count=1, precision="fp8")]
    # The deployment pins the fp8 profile, which narrowing to fp16/tp2 would prune.
    services = [_service("summarizer-prod", pinned_profile="p-fp8-tp1")]
    mock_kube_client = _kube_client(
        model,
        _list_side_effect(
            profile_sets=[_default_set()], model_profiles=profiles, base_profiles=base, services=services
        ),
    )

    with pytest.raises(ConflictException) as exc_info:
        await _run_patch(mock_kube_client, mock_minio_client, _runtime_patch())

    # Refused before any write: the AIMModel is never patched.
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()
    patch_profile_mock.assert_not_called()
    assert exc_info.value.detail == {
        "blockingServices": [{"serviceId": services[0].id, "displayName": "summarizer-prod"}]
    }


async def test_patch_narrows_when_deployment_pins_the_retained_default_profile(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    # The retained profile survives narrowing, so a deployment pinning it is safe.
    model = _model()
    profiles = [
        _profile("p-fp16-tp2", accelerator_count=2, precision="fp16"),
        _profile("p-fp8-tp1", accelerator_count=1, precision="fp8"),
    ]
    base = [_base_profile(accelerator_count=2, precision="fp16"), _base_profile(accelerator_count=1, precision="fp8")]
    services = [_service("retained-deploy", pinned_profile="p-fp16-tp2")]
    mock_kube_client = _kube_client(
        model,
        _list_side_effect(
            profile_sets=[_default_set()], model_profiles=profiles, base_profiles=base, services=services
        ),
    )

    await _run_patch(mock_kube_client, mock_minio_client, _runtime_patch())

    selector = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]["spec"][
        "profiles"
    ]["derivedFrom"]["selector"]
    assert selector["acceleratorCount"] == 2


async def test_patch_repatches_the_retained_profile_not_arbitrary_first_item(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    _, patch_profile_mock = mock_profile_gateway
    model = _model()
    profiles = [
        _profile("p-fp16-tp2", accelerator_count=2, precision="fp16"),
        _profile("p-fp8-tp1", accelerator_count=1, precision="fp8"),
    ]
    base = [_base_profile(accelerator_count=2, precision="fp16"), _base_profile(accelerator_count=1, precision="fp8")]
    mock_kube_client = _kube_client(
        model, _list_side_effect(profile_sets=[_default_set()], model_profiles=profiles, base_profiles=base)
    )

    await _run_patch(
        mock_kube_client,
        mock_minio_client,
        _runtime_patch(accelerator_count=1, precision="fp8"),
    )

    assert patch_profile_mock.call_args.kwargs["profile_name"] == "p-fp8-tp1"


async def test_patch_skips_narrowing_when_deployment_lookup_fails(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    model = _model()
    profiles = [_profile("p-fp16-tp2", accelerator_count=2, precision="fp16")]
    base = [_base_profile(accelerator_count=2, precision="fp16")]
    dispatch = _list_side_effect(
        profile_sets=[_default_set()],
        model_profiles=profiles,
        base_profiles=base,
    )

    async def fail_service_lookup(**kwargs: Any) -> dict[str, Any]:
        if kwargs.get("plural") == AIM_SERVICE_PLURAL:
            raise ApiException(status=500, reason="unavailable")
        return await dispatch(**kwargs)

    mock_kube_client = _kube_client(model, fail_service_lookup)

    await _run_patch(mock_kube_client, mock_minio_client, _runtime_patch())

    body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    assert "derivedFrom" not in body["spec"]["profiles"]
    assert body["spec"]["profiles"]["overrides"]["acceleratorCount"] == 2


async def test_patch_skips_narrowing_when_target_profile_has_not_been_derived(
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    model = _model()
    profiles = [_profile("p-fp16-tp2", accelerator_count=2, precision="fp16")]
    base = [
        _base_profile(accelerator_count=2, precision="fp16"),
        _base_profile(accelerator_count=1, precision="fp8"),
    ]
    mock_kube_client = _kube_client(
        model,
        _list_side_effect(profile_sets=[_default_set()], model_profiles=profiles, base_profiles=base),
    )

    await _run_patch(
        mock_kube_client,
        mock_minio_client,
        _runtime_patch(accelerator_count=1, precision="fp8"),
    )

    body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    assert "derivedFrom" not in body["spec"]["profiles"]
    assert body["spec"]["profiles"]["overrides"]["precision"] == "fp8"
