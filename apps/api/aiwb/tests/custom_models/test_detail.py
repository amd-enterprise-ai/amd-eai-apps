# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Unit tests for the custom-model detail endpoint.

Covers:
* _compose_onboard_status — all phase transitions
* _resolve_image_metadata — status preference and annotation fallback
* extract_hf_token_secret_name — overrides.modelSources[].env extraction
* list_custom_models — bulk join, non-custom CR filtering
* get_custom_model — happy path, CR not found, non-custom CR
* Router: GET /projects/{project}/models/{model_name} — HTTP layer
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from api_common.exceptions import NotFoundException
from app import app  # type: ignore[attr-defined]
from app.aims.constants import AIM_MODEL_LABEL
from app.aims.crds import (
    AIMImageMetadata,
    AIMModelProfilesDerivedFrom,
    AIMModelProfilesSpec,
    AIMModelResource,
    AIMModelSource,
    AIMModelSpec,
    AIMModelStatusFields,
    AIMProfileResource,
    AIMProfileSetResource,
    AIMProfileSpec,
    AIMProfileStatus,
    ProfileOverrides,
    ProfileSelector,
    ProfileSelectorModelRef,
)
from app.custom_models.constants import (
    AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION,
    CANONICAL_REPO_ID_ANNOTATION,
    IMPORT_ERROR_ANNOTATION,
    IMPORT_STATE_ANNOTATION,
    MODEL_DISPLAY_NAME_ANNOTATION,
    MODEL_PRECISION_ANNOTATION,
    REVISION_ANNOTATION,
    SOURCE_DESCRIPTION_ANNOTATION,
    SOURCE_SHA_ANNOTATION,
    SOURCE_TAGS_ANNOTATION,
    SOURCE_URI_ANNOTATION,
)
from app.custom_models.enums import OnboardPhase
from app.custom_models.schemas import (
    BaseImageRuntimeProfileOptions,
    CustomModelOnboardStatus,
    CustomModelResponse,
    RuntimeProfileCombination,
    RuntimeProfileOptions,
)
from app.custom_models.service import (
    _compose_onboard_status,
    get_base_image_runtime_profile_options,
    get_base_runtime_profile_options,
    get_custom_model,
    list_custom_models,
)
from app.custom_models.utils import extract_hf_token_secret_name
from app.dispatch.crds import K8sMetadata
from app.dispatch.kube_client import KubernetesClient
from app.workloads.constants import MODEL_SOURCE_TYPE_LABEL
from app.workloads.enums import ModelSourceType
from tests.dependency_overrides import BASE_OVERRIDES, override_dependencies
from tests.factory import make_aim_profile_set

# ---------------------------------------------------------------------------
# Shared fixtures / builders
# ---------------------------------------------------------------------------

_NAMESPACE = "test-namespace"
_MODEL_NAME = "tinyllama-import-abc12345"
_REPO_ID = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"


def _make_profiles_spec(
    *,
    repo_id: str = _REPO_ID,
    image: str = "docker.io/amd/tinyllama:1.0.0",
    env: list | None = None,
) -> AIMModelProfilesSpec:
    """Build the v1alpha2 spec.profiles block an onboarded custom model carries.

    ``env`` (e.g. an HF_TOKEN entry) rides on the weights source it authorizes,
    matching what the onboard builder emits.
    """
    return AIMModelProfilesSpec(
        derived_from=AIMModelProfilesDerivedFrom(
            selector=ProfileSelector(
                role="base",
                model_ref=ProfileSelectorModelRef(name="aim-base", scope="Namespace"),
            ),
        ),
        version_policy="all",
        overrides=ProfileOverrides(
            aim_id=repo_id,
            model_id=repo_id,
            image=image,
            model_sources=[
                AIMModelSource(
                    model_id=repo_id,
                    source_uri=f"s3://bucket/{_NAMESPACE}/custom-models/weights/",
                    env=env,
                )
            ],
        ),
    )


def _make_cr(
    name: str = _MODEL_NAME,
    aim_model_status: str = "NotAvailable",  # maps to cr.status.status; must be a valid AIMModelStatus
    annotations: dict | None = None,
    env: list | None = None,
    image_metadata: AIMImageMetadata | None = None,
) -> AIMModelResource:
    """Build a minimal v1alpha2 (profiles-shaped) AIMModelResource for testing."""
    base_annotations = {
        REVISION_ANNOTATION: "main",
        SOURCE_SHA_ANNOTATION: "abc123",
        SOURCE_URI_ANNOTATION: f"s3://bucket/{_NAMESPACE}/custom-models/{name}/weights/",
        MODEL_DISPLAY_NAME_ANNOTATION: "TinyLlama Chat",
        CANONICAL_REPO_ID_ANNOTATION: _REPO_ID,
        SOURCE_DESCRIPTION_ANNOTATION: "A tiny model.",
        SOURCE_TAGS_ANNOTATION: json.dumps(["text-generation", "llama"]),
    }
    if annotations:
        base_annotations.update(annotations)

    return AIMModelResource(
        metadata=K8sMetadata(name=name, namespace=_NAMESPACE, annotations=base_annotations),
        spec=AIMModelSpec(profiles=_make_profiles_spec(env=env)),
        status=AIMModelStatusFields(
            status=aim_model_status,
            image_metadata=image_metadata or AIMImageMetadata(),
        ),
    )


def _default_set_name(model_name: str = _MODEL_NAME) -> str:
    return f"{model_name}-profiles-abc123"


def _make_default_set(model_name: str = _MODEL_NAME) -> AIMProfileSetResource:
    """The engine-owned Default AIMProfileSet for a model (no AIWB origin label)."""
    return make_aim_profile_set(name=_default_set_name(model_name), model_name=model_name, namespace=_NAMESPACE)


def _make_profile(
    model_name: str = _MODEL_NAME,
    with_image_ref: bool = True,
    *,
    owner_set: str | None = None,
    name: str | None = None,
    precision: str = "fp16",
    ready: bool = False,
) -> AIMProfileResource:
    """Build a minimal AIMProfileResource owned by its model's Default set.

    The ownerReference is the durable set→profile link the profile composer joins
    on; default it to the model's Default set so a single profile surfaces as the
    Default row. Pass ``ready=True`` to stamp a Ready status, which
    ``effective_profile_for_set`` requires before it will prefer a precision-matched
    profile over the first-derived fallback.
    """
    annotations = {}
    if with_image_ref:
        annotations[AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION] = "amdenterpriseai/aim-base:0.11"
    return AIMProfileResource(
        metadata=K8sMetadata(
            name=name or f"{model_name}-default",
            namespace=_NAMESPACE,
            labels={AIM_MODEL_LABEL: model_name},
            annotations=annotations,
            owner_references=[{"kind": "AIMProfileSet", "name": owner_set or _default_set_name(model_name)}],
        ),
        spec=AIMProfileSpec(aim_id=model_name, image="amdenterpriseai/aim-base:0.11", precision=precision),
        status=AIMProfileStatus(status="Ready") if ready else AIMProfileStatus(),
    )


# ---------------------------------------------------------------------------
# _compose_onboard_status — phase transition rules
# ---------------------------------------------------------------------------


def test_compose_status_pending_when_no_profile() -> None:
    cr = _make_cr(aim_model_status="Progressing")
    result = _compose_onboard_status(cr, profile=None)
    assert result.state == OnboardPhase.PENDING
    assert result.status == "Progressing"
    assert result.template_ready is False
    assert result.artifact_phase is None


def test_compose_status_ready_when_aim_ready_and_profile_exists() -> None:
    """For v1alpha2 spec.profiles derivation, aim-engine does not stamp the legacy
    deployment-image-ref annotation — profile existence alone is the correct
    readiness signal."""
    cr = _make_cr(aim_model_status="Ready")
    profile = _make_profile(with_image_ref=False)
    result = _compose_onboard_status(cr, profile=profile)
    assert result.state == OnboardPhase.READY
    assert result.template_ready is True


def test_compose_status_ready_when_aim_ready_and_profile_annotated() -> None:
    cr = _make_cr(aim_model_status="Ready")
    profile = _make_profile(with_image_ref=True)
    result = _compose_onboard_status(cr, profile=profile)
    assert result.state == OnboardPhase.READY
    assert result.template_ready is True
    assert result.status == "Ready"


def test_compose_status_failed_when_aim_model_status_is_failed_variant() -> None:
    cr = _make_cr(aim_model_status="Failed")
    result = _compose_onboard_status(cr, profile=None)
    assert result.state == OnboardPhase.FAILED


def test_compose_status_failed_when_aim_model_status_is_error_variant() -> None:
    """``Error`` is the second failure-class status the engine can emit (alongside
    ``Failed``); ``resolve_onboard_phase`` recognises both via explicit
    ``AIMModelStatus`` membership rather than substring matching."""
    cr = _make_cr(aim_model_status="Error")
    result = _compose_onboard_status(cr, profile=None)
    assert result.state == OnboardPhase.FAILED


def test_compose_status_importing_gates_ready_model_and_profile() -> None:
    """An in-flight import (signalled via annotation) gates readiness even when
    the AIMModel is Ready and a profile exists."""
    cr = _make_cr(
        aim_model_status="Ready",
        annotations={IMPORT_STATE_ANNOTATION: "Importing"},
    )
    profile = _make_profile(with_image_ref=True)
    result = _compose_onboard_status(cr, profile=profile)
    assert result.state == OnboardPhase.IMPORTING


def test_compose_status_no_annotation_fields_are_none() -> None:
    cr = _make_cr()
    result = _compose_onboard_status(cr, profile=None)
    assert result.artifact_phase is None
    assert result.artifact_last_error is None


def test_compose_status_import_annotation_drives_importing() -> None:
    """The workbench-owned import annotations are the weight-import signal."""
    cr = _make_cr(
        aim_model_status="Progressing",
        annotations={IMPORT_STATE_ANNOTATION: "Importing"},
    )
    result = _compose_onboard_status(cr, profile=None)
    assert result.state == OnboardPhase.IMPORTING
    assert result.artifact_phase == "Importing"


def test_compose_status_import_annotation_failed_with_error() -> None:
    cr = _make_cr(
        aim_model_status="Progressing",
        annotations={
            IMPORT_STATE_ANNOTATION: "Failed",
            IMPORT_ERROR_ANNOTATION: "HF 401 unauthorized",
        },
    )
    result = _compose_onboard_status(cr, profile=None)
    assert result.state == OnboardPhase.FAILED
    assert result.artifact_last_error == "HF 401 unauthorized"


def test_compose_status_import_annotation_ready_gates_on_model_and_profile() -> None:
    """Import done + model Ready + profile present → Ready."""
    cr = _make_cr(aim_model_status="Ready", annotations={IMPORT_STATE_ANNOTATION: "Ready"})
    profile = _make_profile(with_image_ref=False)
    result = _compose_onboard_status(cr, profile=profile)
    assert result.state == OnboardPhase.READY


# ---------------------------------------------------------------------------
# extract_hf_token_secret_name
# ---------------------------------------------------------------------------


def test_extract_hf_token_secret_name_returns_secret_name() -> None:
    env = [{"name": "HF_TOKEN", "valueFrom": {"secretKeyRef": {"name": "my-hf-secret", "key": "token"}}}]
    cr = _make_cr(env=env)
    assert extract_hf_token_secret_name(cr) == "my-hf-secret"


def test_extract_hf_token_secret_name_returns_none_when_no_hf_token_entry() -> None:
    env = [{"name": "SOME_OTHER_VAR", "value": "foo"}]
    cr = _make_cr(env=env)
    assert extract_hf_token_secret_name(cr) is None


def test_extract_hf_token_secret_name_returns_none_when_env_is_empty() -> None:
    cr = _make_cr(env=[])
    assert extract_hf_token_secret_name(cr) is None


def test_extract_hf_token_secret_name_returns_none_when_not_profiles_shaped() -> None:
    """A CR with no spec.profiles (e.g. a non-custom model) yields no secret."""
    cr = AIMModelResource(
        metadata=K8sMetadata(name=_MODEL_NAME, namespace=_NAMESPACE, annotations={}),
        spec=AIMModelSpec(),
    )
    assert extract_hf_token_secret_name(cr) is None


def test_extract_hf_token_secret_name_returns_none_when_hf_token_entry_lacks_value_from() -> None:
    """An HF_TOKEN env entry that uses a literal value instead of secretKeyRef returns None."""
    env = [{"name": "HF_TOKEN", "value": "hf_plaintext"}]
    cr = _make_cr(env=env)
    assert extract_hf_token_secret_name(cr) is None


# ---------------------------------------------------------------------------
# list_custom_models — async service function
# ---------------------------------------------------------------------------


def _patch_list_reads(
    *,
    models: list,
    profiles: list | None = None,
    profile_sets: list | None = None,
    services: list | None = None,
) -> tuple:
    """Patch the namespace-wide reads list_custom_models fans out over."""
    return (
        patch("app.custom_models.service.aims_gateway.list_aim_models", AsyncMock(return_value=models)),
        patch("app.custom_models.service.list_aim_profiles", AsyncMock(return_value=profiles or [])),
        patch(
            "app.custom_models.service.aims_gateway.list_aim_profile_sets_for_model",
            AsyncMock(return_value=profile_sets or []),
        ),
        patch(
            "app.custom_models.service.aims_gateway.list_aim_services_for_model",
            AsyncMock(return_value=services or []),
        ),
    )


def _patch_detail_reads(
    *,
    cr: AIMModelResource,
    profiles: list | None = None,
    profile_sets: list | None = None,
    services: list | None = None,
) -> tuple:
    """Patch the reads get_custom_model fans out over (the shared profile context)."""
    return (
        patch("app.custom_models.service.aims_gateway.get_aim_model", AsyncMock(return_value=cr)),
        patch("app.custom_models.service.list_aim_profiles", AsyncMock(return_value=profiles or [])),
        patch(
            "app.custom_models.service.aims_gateway.list_aim_profile_sets_for_model",
            AsyncMock(return_value=profile_sets or []),
        ),
        patch(
            "app.custom_models.service.aims_gateway.list_aim_services_for_model",
            AsyncMock(return_value=services or []),
        ),
    )


@pytest.mark.asyncio
async def test_list_custom_models_returns_only_custom_crs() -> None:
    """list_custom_models delegates filtering to the k8s label selector; the
    service includes whatever list_aim_models returns without re-filtering."""
    custom_cr = _make_cr(name="custom-model")
    kube = AsyncMock()
    p = _patch_list_reads(models=[custom_cr])
    with p[0], p[1], p[2], p[3]:
        results = await list_custom_models(kube, _NAMESPACE)

    assert len(results) == 1
    assert results[0].metadata.name == "custom-model"
    # No profile sets yet (still onboarding) → empty collection, no 500.
    assert results[0].profiles == []


@pytest.mark.asyncio
async def test_list_custom_models_passes_custom_label_selector_to_gateway() -> None:
    """The label selector that restricts results to custom-source models must be
    forwarded to the gateway so that non-custom CRs are excluded at the API
    server rather than filtered client-side."""
    kube = AsyncMock()
    mock_list = AsyncMock(return_value=[])
    with (
        patch("app.custom_models.service.aims_gateway.list_aim_models", mock_list),
        patch("app.custom_models.service.list_aim_profiles", AsyncMock(return_value=[])),
        patch("app.custom_models.service.aims_gateway.list_aim_profile_sets_for_model", AsyncMock(return_value=[])),
        patch("app.custom_models.service.aims_gateway.list_aim_services_for_model", AsyncMock(return_value=[])),
    ):
        await list_custom_models(kube, _NAMESPACE)

    expected_selector = f"{MODEL_SOURCE_TYPE_LABEL}={ModelSourceType.CUSTOM}"
    mock_list.assert_called_once_with(kube, _NAMESPACE, label_selector=expected_selector)


@pytest.mark.asyncio
async def test_list_custom_models_joins_profiles_by_model_name() -> None:
    """The Default profile row is matched to the CR by the model.name label, and an
    in-flight import (annotation) gates readiness even when the model is Ready + profiled."""
    cr = _make_cr(aim_model_status="Ready", annotations={IMPORT_STATE_ANNOTATION: "Importing"})
    default_set = _make_default_set()
    profile = _make_profile(model_name=_MODEL_NAME, with_image_ref=True)

    kube = AsyncMock()
    p = _patch_list_reads(models=[cr], profiles=[profile], profile_sets=[default_set])
    with p[0], p[1], p[2], p[3]:
        results = await list_custom_models(kube, _NAMESPACE)

    assert len(results) == 1
    row = results[0]
    assert [r.is_default for r in row.profiles] == [True]
    assert row.profiles[0].name == "default"
    assert row.phase.state == OnboardPhase.IMPORTING
    assert row.phase.template_ready is True
    assert row.phase.artifact_phase == "Importing"


@pytest.mark.asyncio
async def test_list_custom_models_default_first_with_named_row() -> None:
    """A model with a Default and a named set lists both, Default first."""
    cr = _make_cr(aim_model_status="Ready")
    default_set = _make_default_set()
    named_set = make_aim_profile_set(
        name=f"{_MODEL_NAME}-high-speed-7f3b6c8e",
        model_name=_MODEL_NAME,
        namespace=_NAMESPACE,
        is_aiwb_authored=True,
    )
    default_profile = _make_profile(name=f"{_MODEL_NAME}-default", owner_set=default_set.metadata.name)
    named_profile = _make_profile(name=f"{_MODEL_NAME}-tp4", owner_set=named_set.metadata.name)

    kube = AsyncMock()
    p = _patch_list_reads(
        models=[cr],
        profiles=[named_profile, default_profile],
        profile_sets=[named_set, default_set],
    )
    with p[0], p[1], p[2], p[3]:
        results = await list_custom_models(kube, _NAMESPACE)

    profiles = results[0].profiles
    assert [r.is_default for r in profiles] == [True, False]
    assert len(profiles) == 2
    assert profiles[0].name == "default"
    assert profiles[1].name == named_set.metadata.name


@pytest.mark.asyncio
async def test_list_custom_models_two_default_profiles_pick_by_precision_not_first() -> None:
    """Two derived profiles under the Default do not last-win/first-item: template_ready
    reflects the Default's effective (precision-matched) profile, not an arbitrary one."""
    cr = _make_cr(aim_model_status="Ready", annotations={MODEL_PRECISION_ANNOTATION: "fp8"})
    default_set = _make_default_set()
    fp16 = _make_profile(name=f"{_MODEL_NAME}-fp16", precision="fp16", ready=True)
    fp8 = _make_profile(name=f"{_MODEL_NAME}-fp8", precision="fp8", ready=True)

    kube = AsyncMock()
    p = _patch_list_reads(models=[cr], profiles=[fp16, fp8], profile_sets=[default_set])
    with p[0], p[1], p[2], p[3]:
        results = await list_custom_models(kube, _NAMESPACE)

    default_row = results[0].profiles[0]
    assert default_row.is_default is True
    assert default_row.profile.spec.precision == "fp8"
    assert results[0].phase.template_ready is True


@pytest.mark.asyncio
async def test_list_custom_models_unmatched_set_is_ignored() -> None:
    """A profile set for a different model name does not affect this model's composition."""
    cr = _make_cr(name="model-a", aim_model_status="Progressing")
    set_for_other = _make_default_set(model_name="model-b")
    profile_for_other = _make_profile(model_name="model-b", owner_set=set_for_other.metadata.name)

    kube = AsyncMock()
    p = _patch_list_reads(models=[cr], profiles=[profile_for_other], profile_sets=[set_for_other])
    with p[0], p[1], p[2], p[3]:
        results = await list_custom_models(kube, _NAMESPACE)

    assert results[0].profiles == []
    assert results[0].phase.state == OnboardPhase.PENDING
    assert results[0].phase.template_ready is False


@pytest.mark.asyncio
async def test_list_custom_models_inconsistent_default_omits_profiles_without_failing_grid() -> None:
    """Two Default sets for one model cannot classify a unique Default; that model's
    profiles are omitted rather than 500-ing the whole list."""
    cr = _make_cr(aim_model_status="Ready")
    default_a = _make_default_set()
    default_b = make_aim_profile_set(
        name=f"{_MODEL_NAME}-profiles-second", model_name=_MODEL_NAME, namespace=_NAMESPACE
    )

    kube = AsyncMock()
    p = _patch_list_reads(models=[cr], profile_sets=[default_a, default_b])
    with p[0], p[1], p[2], p[3]:
        results = await list_custom_models(kube, _NAMESPACE)

    assert len(results) == 1
    assert results[0].profiles == []
    assert results[0].phase.template_ready is False


@pytest.mark.asyncio
async def test_list_custom_models_includes_composed_phase() -> None:
    """list_custom_models populates the phase field for every returned model."""
    cr = _make_cr(aim_model_status="Progressing")
    kube = AsyncMock()
    p = _patch_list_reads(models=[cr])
    with p[0], p[1], p[2], p[3]:
        results = await list_custom_models(kube, _NAMESPACE)

    assert results[0].phase is not None
    assert results[0].phase.state == OnboardPhase.PENDING


# ---------------------------------------------------------------------------
# get_custom_model — async service function
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_custom_model_returns_composed_response() -> None:
    cr = _make_cr(aim_model_status="Ready")
    default_set = _make_default_set()
    profile = _make_profile(with_image_ref=True)

    kube = AsyncMock()
    p = _patch_detail_reads(cr=cr, profiles=[profile], profile_sets=[default_set])
    with p[0], p[1], p[2], p[3]:
        result = await get_custom_model(kube, _NAMESPACE, _MODEL_NAME)

    assert result.metadata.name == _MODEL_NAME
    assert result.phase.state == OnboardPhase.READY
    assert result.phase.template_ready is True
    assert [r.is_default for r in result.profiles] == [True]


@pytest.mark.asyncio
async def test_get_custom_model_returns_persisted_runtime_overrides() -> None:
    """Runtime knobs persisted on spec.profiles.overrides must round-trip on GET so the edit form can prefill them."""
    cr = _make_cr(aim_model_status="Ready")
    cr.spec.profiles.overrides = ProfileOverrides.model_validate(
        {
            "aimId": _REPO_ID,
            "modelId": _REPO_ID,
            "image": "docker.io/amd/tinyllama:1.0.0",
            "acceleratorModel": "MI300X",
            "precision": "fp16",
            "engineArgs": {"max-model-len": 4096},
            "engineEnv": {"VLLM_ROCM_USE_AITER": "1"},
        }
    )
    default_set = _make_default_set()
    profile = _make_profile(with_image_ref=True)

    kube = AsyncMock()
    p = _patch_detail_reads(cr=cr, profiles=[profile], profile_sets=[default_set])
    with p[0], p[1], p[2], p[3]:
        result = await get_custom_model(kube, _NAMESPACE, _MODEL_NAME)

    overrides = result.spec.profiles.overrides.model_dump(by_alias=True)
    assert overrides["acceleratorModel"] == "MI300X"
    assert overrides["precision"] == "fp16"
    assert overrides["engineArgs"] == {"max-model-len": 4096}
    assert overrides["engineEnv"] == {"VLLM_ROCM_USE_AITER": "1"}


@pytest.mark.asyncio
async def test_get_custom_model_raises_not_found_when_cr_absent() -> None:
    kube = AsyncMock()
    p = _patch_detail_reads(cr=None)
    with p[0], p[1], p[2], p[3]:
        with pytest.raises(NotFoundException):
            await get_custom_model(kube, _NAMESPACE, "nonexistent-model")


@pytest.mark.asyncio
async def test_get_custom_model_raises_not_found_for_non_custom_cr() -> None:
    """A CR without REVISION_ANNOTATION (e.g. fine-tuned) must not be returned."""
    non_custom_cr = AIMModelResource(
        metadata=K8sMetadata(name="fine-tuned-model", namespace=_NAMESPACE, annotations={}),
        spec=AIMModelSpec(),
        status=AIMModelStatusFields(),
    )
    kube = AsyncMock()
    p = _patch_detail_reads(cr=non_custom_cr)
    with p[0], p[1], p[2], p[3]:
        with pytest.raises(NotFoundException):
            await get_custom_model(kube, _NAMESPACE, "fine-tuned-model")


@pytest.mark.asyncio
async def test_get_custom_model_passes_model_name_to_gateway_fetches() -> None:
    """The profile context is fetched scoped to this model_name so only that
    model's resources are read, not the whole namespace."""
    cr = _make_cr(aim_model_status="Ready")

    kube = AsyncMock()
    p = _patch_detail_reads(cr=cr)
    with p[0] as mock_get, p[1] as mock_profiles, p[2] as mock_sets, p[3] as mock_services:
        await get_custom_model(kube, _NAMESPACE, _MODEL_NAME)

    mock_get.assert_called_once_with(kube, _NAMESPACE, _MODEL_NAME)
    mock_profiles.assert_called_once_with(kube, _NAMESPACE, model_name=_MODEL_NAME, strict=True)
    mock_sets.assert_called_once_with(kube, _NAMESPACE, _MODEL_NAME)
    mock_services.assert_called_once_with(kube, _NAMESPACE, _MODEL_NAME)


@pytest.mark.asyncio
async def test_get_custom_model_with_import_in_progress() -> None:
    cr = _make_cr(aim_model_status="Progressing", annotations={IMPORT_STATE_ANNOTATION: "Importing"})

    kube = AsyncMock()
    p = _patch_detail_reads(cr=cr)
    with p[0], p[1], p[2], p[3]:
        result = await get_custom_model(kube, _NAMESPACE, _MODEL_NAME)

    assert result.phase.state == OnboardPhase.IMPORTING
    assert result.phase.artifact_phase == "Importing"


# ---------------------------------------------------------------------------
# get_base_runtime_profile_options — base-template runtime options
# ---------------------------------------------------------------------------


def _make_base_profile(
    *,
    accelerator_model: str = "MI300X",
    precision: str = "fp16",
    accelerator_count: int = 1,
    profile_type: str = "general",
    metric: str = "latency",
) -> AIMProfileResource:
    """Build a base-role AIMProfile carrying the runtime fields the wizard reads."""
    return AIMProfileResource(
        metadata=K8sMetadata(name=f"aim-base-{precision}-tp{accelerator_count}-{metric}", namespace=_NAMESPACE),
        spec=AIMProfileSpec(
            aim_id="",
            accelerator_model=accelerator_model,
            precision=precision,
            accelerator_count=accelerator_count,
            type=profile_type,
            metric=metric,
        ),
    )


@pytest.mark.asyncio
async def test_base_runtime_profile_options_aggregates_distinct_sorted_values() -> None:
    """Distinct accelerator/precision/count/type values across base-role profiles are returned, deduped and sorted."""
    profiles = [
        _make_base_profile(accelerator_count=1),
        _make_base_profile(accelerator_count=2),
        _make_base_profile(accelerator_count=8),
        _make_base_profile(accelerator_count=4),
        _make_base_profile(accelerator_count=1),  # duplicate
    ]
    kube = AsyncMock()
    with patch("app.custom_models.service.list_base_role_profiles", return_value=profiles):
        options = await get_base_runtime_profile_options(kube, _NAMESPACE)

    assert options.accelerator_models == ["MI300X"]
    assert options.precisions == ["fp16"]
    assert options.accelerator_counts == [1, 2, 4, 8]
    assert options.optimization_classes == ["general"]


@pytest.mark.asyncio
async def test_base_runtime_profile_options_ignores_non_positive_accelerator_counts() -> None:
    """AIMProfile specs with zero or negative accelerator_count must not pollute the options list."""
    profiles = [
        _make_base_profile(accelerator_count=1),
        _make_base_profile(accelerator_count=0),
        _make_base_profile(accelerator_count=-2),
        _make_base_profile(accelerator_count=2),
    ]
    kube = AsyncMock()
    with patch("app.custom_models.service.list_base_role_profiles", return_value=profiles):
        options = await get_base_runtime_profile_options(kube, _NAMESPACE)

    assert options.accelerator_counts == [1, 2]


@pytest.mark.asyncio
async def test_base_runtime_profile_options_empty_when_no_base_profiles() -> None:
    """No base-role profiles (base model not emitted yet) yields empty option lists for client fallback."""
    kube = AsyncMock(spec=KubernetesClient)
    with patch("app.custom_models.service.list_base_role_profiles", return_value=[]):
        options = await get_base_runtime_profile_options(kube, _NAMESPACE)

    assert options == RuntimeProfileOptions()
    assert options.precisions == []
    assert options.combinations == []
    # Nothing emitted yet: the client falls back to defaults rather than blocking.
    assert options.profiles_available is False


@pytest.mark.asyncio
async def test_base_runtime_profile_options_reports_only_emitted_combinations() -> None:
    """A base matrix that is not a full cross product surfaces only the tuples it emits.

    ``fp16`` exists at count 1 and ``fp8`` at count 8, but ``fp16/8`` and ``fp8/1``
    are never emitted. The distinct lists carry both precisions and both counts, so
    their cross product would offer four tuples; ``combinations`` must carry only the
    two that a create/update could resolve to a single base profile.
    """
    profiles = [
        _make_base_profile(precision="fp16", accelerator_count=1, metric="latency"),
        _make_base_profile(precision="fp8", accelerator_count=8, metric="throughput"),
    ]
    kube = AsyncMock(spec=KubernetesClient)
    with patch("app.custom_models.service.list_base_role_profiles", return_value=profiles):
        options = await get_base_runtime_profile_options(kube, _NAMESPACE)

    assert options.precisions == ["fp16", "fp8"]
    assert options.accelerator_counts == [1, 8]
    assert options.metrics == ["latency", "throughput"]
    assert options.combinations == [
        RuntimeProfileCombination(accelerator_model="MI300X", accelerator_count=1, precision="fp16", metric="latency"),
        RuntimeProfileCombination(
            accelerator_model="MI300X", accelerator_count=8, precision="fp8", metric="throughput"
        ),
    ]
    assert options.profiles_available is True


@pytest.mark.asyncio
async def test_base_runtime_profile_options_omits_ambiguous_combinations() -> None:
    """A tuple two base profiles share (differing only by optimization type) is not offered.

    Create/update require the four axes to resolve to exactly one base profile, so an
    ambiguous tuple would be accepted by the form yet rejected by the API with a 400.
    The distinct lists still carry every value; only the ambiguous tuple is withheld.
    """
    profiles = [
        _make_base_profile(precision="fp16", accelerator_count=1, metric="latency", profile_type="general"),
        _make_base_profile(precision="fp16", accelerator_count=1, metric="latency", profile_type="optimized"),
        _make_base_profile(precision="fp8", accelerator_count=8, metric="throughput"),
    ]
    kube = AsyncMock(spec=KubernetesClient)
    with patch("app.custom_models.service.list_base_role_profiles", return_value=profiles):
        options = await get_base_runtime_profile_options(kube, _NAMESPACE)

    assert options.precisions == ["fp16", "fp8"]
    assert options.optimization_classes == ["general", "optimized"]
    # The ambiguous MI300X/1/fp16/latency tuple is withheld; the unambiguous one remains.
    assert options.combinations == [
        RuntimeProfileCombination(accelerator_model="MI300X", accelerator_count=8, precision="fp8", metric="throughput")
    ]
    assert options.profiles_available is True


@pytest.mark.asyncio
async def test_base_runtime_profile_options_flags_ambiguous_only_matrix() -> None:
    """Profiles exist but every tuple is ambiguous: combinations is empty yet profilesAvailable is true.

    The client must distinguish this from 'nothing emitted' — here it has to offer no
    runtime choices and block the save rather than fall back to the per-axis lists.
    """
    profiles = [
        _make_base_profile(precision="fp16", accelerator_count=1, metric="latency", profile_type="general"),
        _make_base_profile(precision="fp16", accelerator_count=1, metric="latency", profile_type="optimized"),
    ]
    kube = AsyncMock(spec=KubernetesClient)
    with patch("app.custom_models.service.list_base_role_profiles", return_value=profiles):
        options = await get_base_runtime_profile_options(kube, _NAMESPACE)

    assert options.combinations == []
    assert options.precisions == ["fp16"]
    assert options.profiles_available is True


@pytest.mark.asyncio
async def test_base_runtime_profile_options_omits_combinations_missing_an_axis() -> None:
    """A base profile missing a narrowing axis (or with a non-positive count) is not a valid combination."""
    no_metric = AIMProfileResource(
        metadata=K8sMetadata(name="aim-base-no-metric", namespace=_NAMESPACE),
        spec=AIMProfileSpec(aim_id="", accelerator_model="MI300X", precision="fp16", accelerator_count=1),
    )
    zero_count = _make_base_profile(precision="fp8", accelerator_count=0, metric="latency")
    valid = _make_base_profile(precision="fp16", accelerator_count=2, metric="latency")
    kube = AsyncMock(spec=KubernetesClient)
    with patch("app.custom_models.service.list_base_role_profiles", return_value=[no_metric, zero_count, valid]):
        options = await get_base_runtime_profile_options(kube, _NAMESPACE)

    assert options.combinations == [
        RuntimeProfileCombination(accelerator_model="MI300X", accelerator_count=2, precision="fp16", metric="latency")
    ]


@pytest.mark.asyncio
async def test_base_image_runtime_profile_options_reads_discovered_profiles_matrix() -> None:
    cluster_models = [
        {
            "spec": {"image": "amdenterpriseai/aim-base:0.13.1"},
            "status": {
                "discoveredProfiles": {
                    "byHardware": [
                        {
                            "acceleratorType": "gpu",
                            "acceleratorModel": "MI300X",
                            "acceleratorCount": 1,
                            "profiles": [
                                {"metric": "latency", "precision": "fp16"},
                                {"metric": "throughput", "precision": "fp16"},
                            ],
                        },
                        {
                            "acceleratorType": "gpu",
                            "acceleratorModel": "MI300X",
                            "acceleratorCount": 8,
                            "profiles": [
                                {"metric": "latency", "precision": "fp16"},
                                {"metric": "throughput", "precision": "fp16"},
                            ],
                        },
                        {
                            "acceleratorType": "gpu",
                            "acceleratorModel": "MI325X",
                            "acceleratorCount": 4,
                            "profiles": [{"metric": "latency", "precision": "fp8"}],
                        },
                    ]
                }
            },
        }
    ]
    kube = AsyncMock()
    with patch("app.custom_models.service.aims_gateway.list_aim_cluster_models", return_value=cluster_models):
        options = await get_base_image_runtime_profile_options(
            kube,
            image_repository="amdenterpriseai/aim-base",
            image_tag="0.13.1",
        )

    assert options.image_repository == "amdenterpriseai/aim-base"
    assert options.image_tag == "0.13.1"
    assert options.accelerator_types == ["gpu"]
    assert options.accelerator_models == ["MI300X", "MI325X"]
    assert options.accelerator_counts_by_model == {"MI300X": [1, 8], "MI325X": [4]}
    assert options.precisions_by_model == {"MI300X": ["fp16"], "MI325X": ["fp8"]}
    assert options.metrics_by_model == {
        "MI300X": ["latency", "throughput"],
        "MI325X": ["latency"],
    }
    # Only the tuples the matrix actually pairs are emitted: MI325X exists solely
    # at count 4 / fp8 / latency, so no MI325X/fp16 or MI325X/throughput leaks in
    # from the other model's per-axis lists.
    assert options.combinations == [
        RuntimeProfileCombination(accelerator_model="MI300X", accelerator_count=1, precision="fp16", metric="latency"),
        RuntimeProfileCombination(
            accelerator_model="MI300X", accelerator_count=1, precision="fp16", metric="throughput"
        ),
        RuntimeProfileCombination(accelerator_model="MI300X", accelerator_count=8, precision="fp16", metric="latency"),
        RuntimeProfileCombination(
            accelerator_model="MI300X", accelerator_count=8, precision="fp16", metric="throughput"
        ),
        RuntimeProfileCombination(accelerator_model="MI325X", accelerator_count=4, precision="fp8", metric="latency"),
    ]
    assert options.profiles_available is True


@pytest.mark.asyncio
async def test_base_image_runtime_profile_options_surfaces_audio_capable_instinct_base() -> None:
    """runtime-profile-options returns the MI300X matrix for an audio-enabled base image.

    The onboard wizard reads a base image's runtime options straight from the
    AIMClusterModel discovered-profile matrix, with no capability-specific
    handling, so an audio-capable base is surfaced the moment it is registered.
    Regression lock for that path.
    """
    cluster_models = [
        {
            "spec": {"image": "amdenterpriseai/aim-instinct-audio-base:2026.10"},
            "status": {
                "discoveredProfiles": {
                    "byHardware": [
                        {
                            "acceleratorType": "gpu",
                            "acceleratorModel": "MI300X",
                            "acceleratorCount": 1,
                            "profiles": [
                                {"metric": "latency", "precision": "fp16"},
                                {"metric": "throughput", "precision": "fp16"},
                            ],
                        },
                    ]
                }
            },
        }
    ]
    kube = AsyncMock()
    with patch("app.custom_models.service.aims_gateway.list_aim_cluster_models", return_value=cluster_models):
        options = await get_base_image_runtime_profile_options(
            kube,
            image_repository="amdenterpriseai/aim-instinct-audio-base",
            image_tag="2026.10",
        )

    assert options.image_repository == "amdenterpriseai/aim-instinct-audio-base"
    assert options.image_tag == "2026.10"
    assert options.accelerator_types == ["gpu"]
    assert options.accelerator_models == ["MI300X"]
    assert options.accelerator_counts_by_model == {"MI300X": [1]}
    assert options.precisions_by_model == {"MI300X": ["fp16"]}
    assert options.metrics_by_model == {"MI300X": ["latency", "throughput"]}
    assert options.combinations == [
        RuntimeProfileCombination(accelerator_model="MI300X", accelerator_count=1, precision="fp16", metric="latency"),
        RuntimeProfileCombination(
            accelerator_model="MI300X", accelerator_count=1, precision="fp16", metric="throughput"
        ),
    ]
    assert options.profiles_available is True


@pytest.mark.asyncio
async def test_base_image_runtime_profile_options_dedupes_tuples_across_duplicate_models() -> None:
    """Identical tuples reported by two cluster models for the same image are kept, not dropped.

    Kubernetes does not enforce image-reference uniqueness, so a valid tuple can appear
    once in each of two AIMClusterModels. That is duplication, not ambiguity, so the
    tuple must still be offered.
    """
    hardware = [
        {
            "acceleratorType": "gpu",
            "acceleratorModel": "MI300X",
            "acceleratorCount": 1,
            "profiles": [{"metric": "latency", "precision": "fp16"}],
        }
    ]
    cluster_models = [
        {
            "spec": {"image": "amdenterpriseai/aim-base:0.13.1"},
            "status": {"discoveredProfiles": {"byHardware": hardware}},
        },
        {
            "spec": {"image": "amdenterpriseai/aim-base:0.13.1"},
            "status": {"discoveredProfiles": {"byHardware": hardware}},
        },
    ]
    kube = AsyncMock(spec=KubernetesClient)
    with patch("app.custom_models.service.aims_gateway.list_aim_cluster_models", return_value=cluster_models):
        options = await get_base_image_runtime_profile_options(
            kube, image_repository="amdenterpriseai/aim-base", image_tag="0.13.1"
        )

    assert options.combinations == [
        RuntimeProfileCombination(accelerator_model="MI300X", accelerator_count=1, precision="fp16", metric="latency")
    ]
    assert options.profiles_available is True


@pytest.mark.asyncio
async def test_base_image_runtime_profile_options_flags_ambiguous_only_matrix() -> None:
    """Two profiles of one model share a tuple: it is withheld, but profilesAvailable stays true.

    combinations is empty because the only tuple is ambiguous within the model; the
    client must block the save rather than fall back to the per-model lists.
    """
    cluster_models = [
        {
            "spec": {"image": "amdenterpriseai/aim-base:0.13.1"},
            "status": {
                "discoveredProfiles": {
                    "byHardware": [
                        {
                            "acceleratorType": "gpu",
                            "acceleratorModel": "MI300X",
                            "acceleratorCount": 1,
                            "profiles": [
                                {"metric": "latency", "precision": "fp16", "type": "general"},
                                {"metric": "latency", "precision": "fp16", "type": "optimized"},
                            ],
                        }
                    ]
                }
            },
        }
    ]
    kube = AsyncMock(spec=KubernetesClient)
    with patch("app.custom_models.service.aims_gateway.list_aim_cluster_models", return_value=cluster_models):
        options = await get_base_image_runtime_profile_options(
            kube, image_repository="amdenterpriseai/aim-base", image_tag="0.13.1"
        )

    assert options.combinations == []
    assert options.accelerator_models == ["MI300X"]
    assert options.profiles_available is True


@pytest.mark.asyncio
async def test_base_image_runtime_profile_options_not_available_when_group_has_no_profiles() -> None:
    """A hardware group with an empty profiles list records a model but no profile.

    profilesAvailable must stay false so the client uses its not-ready fallback
    rather than blocking on a matrix that emitted nothing.
    """
    cluster_models = [
        {
            "spec": {"image": "amdenterpriseai/aim-base:0.13.1"},
            "status": {
                "discoveredProfiles": {
                    "byHardware": [
                        {
                            "acceleratorType": "gpu",
                            "acceleratorModel": "MI300X",
                            "acceleratorCount": 1,
                            "profiles": [],
                        }
                    ]
                }
            },
        }
    ]
    kube = AsyncMock(spec=KubernetesClient)
    with patch("app.custom_models.service.aims_gateway.list_aim_cluster_models", return_value=cluster_models):
        options = await get_base_image_runtime_profile_options(
            kube, image_repository="amdenterpriseai/aim-base", image_tag="0.13.1"
        )

    assert options.accelerator_models == ["MI300X"]
    assert options.combinations == []
    assert options.profiles_available is False


@pytest.mark.asyncio
async def test_base_image_runtime_profile_options_404_when_image_not_found() -> None:
    kube = AsyncMock()
    with patch("app.custom_models.service.aims_gateway.list_aim_cluster_models", return_value=[]):
        with pytest.raises(NotFoundException):
            await get_base_image_runtime_profile_options(
                kube,
                image_repository="amdenterpriseai/aim-base",
                image_tag="0.13.1",
            )


@pytest.mark.asyncio
async def test_base_image_runtime_profile_options_matches_docker_io_repository_variant() -> None:
    cluster_models = [
        {
            "spec": {"image": "amdenterpriseai/aim-base:0.13.1"},
            "status": {
                "discoveredProfiles": {
                    "byHardware": [
                        {
                            "acceleratorType": "gpu",
                            "acceleratorModel": "MI300X",
                            "acceleratorCount": 1,
                            "profiles": [{"metric": "latency", "precision": "fp16"}],
                        }
                    ]
                }
            },
        }
    ]
    kube = AsyncMock()
    with patch("app.custom_models.service.aims_gateway.list_aim_cluster_models", return_value=cluster_models):
        options = await get_base_image_runtime_profile_options(
            kube,
            image_repository="docker.io/amdenterpriseai/aim-base",
            image_tag="0.13.1",
        )

    assert options.accelerator_models == ["MI300X"]


# ---------------------------------------------------------------------------
# Router: GET /projects/{project}/models/{model_name}
# ---------------------------------------------------------------------------

_GET_URL = f"/v1/projects/{_NAMESPACE}/models/{_MODEL_NAME}"


def _make_detail_response():
    return CustomModelResponse(
        metadata=K8sMetadata(name=_MODEL_NAME, namespace=_NAMESPACE),
        spec=AIMModelSpec(image="docker.io/amd/tinyllama:1.0.0"),
        phase=CustomModelOnboardStatus(
            state=OnboardPhase.READY,
            status="Ready",
            template_ready=True,
        ),
    )


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.get_custom_model")
def test_get_custom_model_endpoint_returns_200(mock_get: MagicMock) -> None:
    mock_get.return_value = _make_detail_response()
    with TestClient(app) as client:
        response = client.get(_GET_URL)
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["metadata"]["name"] == _MODEL_NAME
    assert body["phase"]["state"] == "Ready"
    assert body["phase"]["templateReady"] is True


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.get_custom_model")
def test_get_custom_model_endpoint_camel_case_status_fields(mock_get: MagicMock) -> None:
    mock_get.return_value = _make_detail_response()
    with TestClient(app) as client:
        response = client.get(_GET_URL)
    body = response.json()
    assert "state" in body["phase"]
    assert "templateReady" in body["phase"]
    assert "artifactPhase" in body["phase"]
    assert "artifactLastError" in body["phase"]
    assert "imageMetadata" in body["status"]


@override_dependencies(BASE_OVERRIDES)
@patch(
    "app.projects.router.get_custom_model",
    side_effect=NotFoundException("Custom model 'x' not found"),
)
def test_get_custom_model_endpoint_returns_404_when_not_found(mock_get: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.get(_GET_URL)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_custom_model_endpoint_returns_401_without_auth() -> None:
    with TestClient(app) as client:
        response = client.get(_GET_URL)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.get_custom_model")
def test_get_custom_model_endpoint_top_level_fields_present(mock_get: MagicMock) -> None:
    """Top-level response fields are present: phase, profiles, spec, status, metadata."""
    mock_get.return_value = CustomModelResponse(
        metadata=K8sMetadata(name=_MODEL_NAME, namespace=_NAMESPACE),
        spec=AIMModelSpec(image="docker.io/amd/tinyllama:1.0.0"),
        phase=CustomModelOnboardStatus(state=OnboardPhase.READY, status="Ready"),
    )
    with TestClient(app) as client:
        response = client.get(_GET_URL)
    body = response.json()
    assert "phase" in body
    assert "profiles" in body
    assert "profile" not in body
    assert "spec" in body
    assert "status" in body
    assert "metadata" in body


_RUNTIME_OPTIONS_URL = f"/v1/projects/{_NAMESPACE}/models/runtime-profile-options"
_RUNTIME_OPTIONS_BY_IMAGE_URL = f"{_RUNTIME_OPTIONS_URL}/base-image"


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.get_base_runtime_profile_options")
def test_runtime_profile_options_endpoint_returns_camelcase_options(mock_options: MagicMock) -> None:
    """The runtime-options endpoint resolves ahead of the /{model_name} route and serializes camelCase."""
    mock_options.return_value = RuntimeProfileOptions(
        accelerator_models=["MI300X"],
        precisions=["fp16"],
        accelerator_counts=[1, 2, 4, 8],
        optimization_classes=["general"],
        metrics=["latency"],
        combinations=[
            RuntimeProfileCombination(
                accelerator_model="MI300X", accelerator_count=1, precision="fp16", metric="latency"
            )
        ],
        profiles_available=True,
    )
    with TestClient(app) as client:
        response = client.get(_RUNTIME_OPTIONS_URL)
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["acceleratorModels"] == ["MI300X"]
    assert body["precisions"] == ["fp16"]
    assert body["acceleratorCounts"] == [1, 2, 4, 8]
    assert body["optimizationClasses"] == ["general"]
    assert body["combinations"] == [
        {"acceleratorModel": "MI300X", "acceleratorCount": 1, "precision": "fp16", "metric": "latency"}
    ]
    assert body["profilesAvailable"] is True


def test_runtime_profile_options_endpoint_returns_401_without_auth() -> None:
    with TestClient(app) as client:
        response = client.get(_RUNTIME_OPTIONS_URL)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.get_base_image_runtime_profile_options")
def test_runtime_profile_options_by_image_endpoint_returns_camelcase_options(mock_options: MagicMock) -> None:
    mock_options.return_value = BaseImageRuntimeProfileOptions(
        image_repository="amdenterpriseai/aim-base",
        image_tag="0.13.1",
        accelerator_types=["gpu"],
        accelerator_models=["MI300X"],
        accelerator_counts_by_model={"MI300X": [1, 2, 4, 8]},
        precisions_by_model={"MI300X": ["fp16"]},
        metrics_by_model={"MI300X": ["latency", "throughput"]},
        optimization_classes_by_model={},
        combinations=[
            RuntimeProfileCombination(
                accelerator_model="MI300X", accelerator_count=1, precision="fp16", metric="latency"
            )
        ],
        profiles_available=True,
    )
    with TestClient(app) as client:
        response = client.get(
            _RUNTIME_OPTIONS_BY_IMAGE_URL,
            params={"imageRepository": "amdenterpriseai/aim-base", "imageTag": "0.13.1"},
        )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["imageRepository"] == "amdenterpriseai/aim-base"
    assert body["imageTag"] == "0.13.1"
    assert body["acceleratorTypes"] == ["gpu"]
    assert body["acceleratorModels"] == ["MI300X"]
    assert body["acceleratorCountsByModel"] == {"MI300X": [1, 2, 4, 8]}
    assert body["precisionsByModel"] == {"MI300X": ["fp16"]}
    assert body["combinations"] == [
        {"acceleratorModel": "MI300X", "acceleratorCount": 1, "precision": "fp16", "metric": "latency"}
    ]
    assert body["profilesAvailable"] is True


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.get_base_image_runtime_profile_options")
def test_runtime_profile_options_by_image_endpoint_requires_query_params(_mock_options: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.get(_RUNTIME_OPTIONS_BY_IMAGE_URL)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.get_custom_model")
def test_get_custom_model_endpoint_importing_phase_with_artifact(mock_get: MagicMock) -> None:
    """An in-progress import is represented correctly at the HTTP layer."""
    mock_get.return_value = CustomModelResponse(
        metadata=K8sMetadata(name=_MODEL_NAME, namespace=_NAMESPACE),
        spec=AIMModelSpec(image="docker.io/amd/tinyllama:1.0.0"),
        phase=CustomModelOnboardStatus(
            state=OnboardPhase.IMPORTING,
            status="Importing",
            template_ready=False,
            artifact_phase="Importing",
        ),
    )
    with TestClient(app) as client:
        response = client.get(_GET_URL)
    assert response.status_code == status.HTTP_200_OK
    s = response.json()["phase"]
    assert s["state"] == "Importing"
    assert s["templateReady"] is False
    assert s["artifactPhase"] == "Importing"
