# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for BYOM onboarding: manifest builder and upsert orchestration.

These tests target the upsert orchestration in `onboard_custom_model_source`
and the manifest builder `_build_custom_aim_model_manifest`. The Hub-fetch +
preview shape are covered in test_service.py; here we exercise AIMModel CR
creation/patch, conflict detection, and the k8s-first ordering guarantee:
the CR is the source of truth and is written before the S3 manifest mirror.
"""

import base64
import re
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import tenacity
import yaml
from kubernetes_asyncio.client import ApiException
from minio.error import S3Error
from pydantic import ValidationError

from api_common.exceptions import (
    ConflictException,
    ExternalServiceError,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app.aims.crds import AIMModelResource, AIMProfileResource, AIMProfileSpec
from app.custom_models.constants import (
    AIM_BASE_MODEL_NAME,
    AUDIO_CAPABLE_BASE_REPOSITORIES,
    CANONICAL_REPO_ID_ANNOTATION,
    COMPONENT_ID_ANNOTATION,
    DEFAULT_AIM_DEPLOYMENT_IMAGE_REF,
    MODEL_DISPLAY_NAME_ANNOTATION,
    MODEL_PRECISION_ANNOTATION,
    RADEON_AIM_DEPLOYMENT_IMAGE_REF,
    REVISION_ANNOTATION,
    SOURCE_DESCRIPTION_ANNOTATION,
    SOURCE_SHA_ANNOTATION,
    SOURCE_URI_ANNOTATION,
)
from app.custom_models.manifest import write_manifest_to_s3
from app.custom_models.schemas import OnboardRequest, PreviewRequest
from app.custom_models.service import (
    _base_model_name_from_image_ref,
    _build_aim_base_model_manifest,
    _build_custom_aim_model_manifest,
    ensure_namespace_aim_base_model,
    onboard_custom_model_source,
    preview_model_source,
)
from app.dispatch.crds import K8sMetadata
from app.minio.config import (
    MINIO_BUCKET,
    MINIO_URL,
)
from app.storages.constants import STORAGE_CONFIGMAP_LABEL, STORAGE_TYPE_LABEL
from app.storages.enums import StorageType
from app.workloads.constants import (
    CANONICAL_NAME_LABEL,
    DISPLAY_NAME_ANNOTATION,
    MODEL_NAME_LABEL,
)


@pytest.fixture(autouse=True)
def _disable_write_manifest_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Short-circuit the tenacity retry on the shared manifest writer.

    Onboard tests exercise the upsert orchestration around the S3 write
    (read → upsert → write), not the retry timing itself. Without this
    fixture, an S3-failure test would block on three exponential-backoff
    sleeps before the exception surfaces to the assertion.
    """
    monkeypatch.setattr(write_manifest_to_s3.retry, "wait", tenacity.wait_none())
    monkeypatch.setattr(write_manifest_to_s3.retry, "stop", tenacity.stop_after_attempt(1))


HUB_RESPONSE = {
    "id": "meta-llama/Meta-Llama-3-8B-Instruct",
    "sha": "abc123",
    "tags": [],
    "pipeline_tag": "text-generation",
    "gated": False,
    "private": False,
    "cardData": {"model_name": "Llama 3 8B", "description": "An open model."},
    "siblings": [],
}

TEST_IMAGE = "docker.io/amd/tinyllama:1.0.0"
TEST_SUBMITTER = "alice@example.com"


def _cluster_model_item(
    name: str,
    image: str,
    *,
    base_only: bool = True,
    discovered_supported: int = 1,
) -> dict[str, Any]:
    managed_profiles = (
        {"base": 1, "ready": 1, "total": 1} if base_only else {"base": 1, "inference": 1, "ready": 2, "total": 2}
    )
    return {
        "metadata": {"name": name},
        "spec": {"image": image},
        "status": {
            "managedProfiles": managed_profiles,
            "discoveredProfiles": {"supported": discovered_supported},
        },
    }


# Sha used by the default `_make_request` payload and by the autouse Hub
# re-verify mock; keep these aligned so the happy path stays a no-op.
_DEFAULT_REQUEST_SHA = "abc123"


def _make_s3_storage_config_map(
    *,
    secret_name: str = "my-s3-secret",
    bucket_url: str | None = None,
    region: str | None = None,
    access_key_name: str = "minio-access-key",
    secret_key_name: str = "minio-secret-key",
) -> MagicMock:
    data: dict[str, str] = {
        "TYPE": StorageType.S3.value,
        "SECRET_NAME": secret_name,
    }
    if bucket_url:
        data["BUCKET_URL"] = bucket_url
    if region:
        data["REGION"] = region
    data["ACCESS_KEY_NAME"] = access_key_name
    data["SECRET_KEY_NAME"] = secret_key_name
    return MagicMock(
        data=data,
        metadata=MagicMock(labels={STORAGE_CONFIGMAP_LABEL: "true", STORAGE_TYPE_LABEL: StorageType.S3.value}),
    )


@pytest.fixture(autouse=True)
def stub_onboard_hub_reverify() -> Iterator[dict[str, AsyncMock]]:
    """Stub the onboard Hub re-verify path so existing tests stay focused on
    the K8s/S3 orchestration rather than the Hub fetch.

    Defaults match the sha used in `_make_request` so the verify step is a
    no-op on the happy path. Tests covering the verify failure modes (sha
    mismatch, Hub auth, Hub 404, etc.) override `return_value`/`side_effect`
    on the yielded mocks (or re-patch inside the test body); either way the
    fixture's defaults are restored once the test exits.
    """
    with (
        patch("app.custom_models.service._fetch_hub_model") as fetch_mock,
        patch("app.custom_models.service._get_hf_token") as token_mock,
    ):
        fetch_mock.return_value = {"sha": _DEFAULT_REQUEST_SHA}
        token_mock.return_value = "fake-hf-token"
        yield {"fetch": fetch_mock, "token": token_mock}


def _no_such_key_s3_error() -> S3Error:
    """Synthetic ``NoSuchKey`` for the default "no prior manifest" state."""
    return S3Error(
        code="NoSuchKey",
        message="no such key",
        resource="key",
        request_id="r",
        host_id="h",
        response=MagicMock(status=404),
    )


@pytest.fixture
def mock_minio_client() -> MagicMock:
    """Local MinioClient mock; the global fixture in tests/conftest.py is broken.

    ``download_object`` defaults to raising ``NoSuchKey`` so a first-onboard
    test exercises the realistic "no prior manifest" branch in
    ``read_manifest_from_s3`` without needing per-test setup. Tests that
    want to exercise re-onboard append semantics override this to return
    the bytes of a prior manifest.
    """
    mock = MagicMock()
    mock.download_object.side_effect = _no_such_key_s3_error()
    return mock


_CREATED_AIM_MODEL_STUB = {
    "apiVersion": "aim.eai.amd.com/v1alpha2",
    "kind": "AIMModel",
    "metadata": {"name": "llama-3-8b-abc12345", "namespace": "test-namespace"},
    "spec": {},
}

_BASE_MODEL_STUBS = {
    name: _build_aim_base_model_manifest(namespace="test-namespace", image_ref=image_ref, model_name=name)
    for name, image_ref in (
        (AIM_BASE_MODEL_NAME, DEFAULT_AIM_DEPLOYMENT_IMAGE_REF),
        (_base_model_name_from_image_ref(TEST_IMAGE), TEST_IMAGE),
    )
}


@pytest.fixture
def mock_kube_client() -> AsyncMock:
    """Local kube client mock with the custom_objects API surface populated."""
    mock = AsyncMock()
    mock.custom_objects = AsyncMock()
    mock.custom_objects.list_namespaced_custom_object = AsyncMock(return_value={"items": []})

    async def get_namespaced_custom_object(*_args: Any, name: str, **_kwargs: Any) -> dict:
        stub = _BASE_MODEL_STUBS.get(name)
        if stub is not None:
            return stub
        raise ApiException(status=404, reason="Not Found")

    mock.custom_objects.get_namespaced_custom_object = AsyncMock(side_effect=get_namespaced_custom_object)
    # Gateway helpers parse the server response into AIMModelResource, so we
    # default to a valid-shaped payload; individual tests override as needed.
    mock.custom_objects.create_namespaced_custom_object = AsyncMock(return_value=_CREATED_AIM_MODEL_STUB)
    mock.custom_objects.patch_namespaced_custom_object = AsyncMock(return_value=_CREATED_AIM_MODEL_STUB)
    mock.core_v1 = AsyncMock()
    mock.core_v1.read_namespaced_config_map = AsyncMock(return_value=_make_s3_storage_config_map())
    mock.core_v1.read_namespaced_secret = AsyncMock(return_value=MagicMock())
    return mock


_EXISTING_COMPONENT_ID = "11111111-2222-3333-4444-555555555555"


def _make_existing_aim_model(
    *,
    name: str = "llama-3-8b-import-12345678",
    display_name: str = "Llama 3 8B",
    repo_id: str = "meta-llama/Meta-Llama-3-8B-Instruct",
    source_uri: str | None = None,
    component_id: str | None = _EXISTING_COMPONENT_ID,
) -> AIMModelResource:
    # HF onboarding now keeps the upstream Hugging Face source URI directly.
    # Tests that care about exact shape override this explicitly.
    # component_id defaults to a stable value so patch-path tests can assert it's
    # preserved across idempotent calls; pass None to simulate a legacy CR.
    annotations: dict[str, str] = {}
    if component_id is not None:
        annotations[COMPONENT_ID_ANNOTATION] = component_id
    # v1alpha2 shape: identity + weights live under spec.profiles.overrides, not
    # the legacy flat spec.modelSources. Conflict detection reads the repo id
    # back from overrides, so the fixture must mirror what the builder emits.
    return AIMModelResource(
        metadata=K8sMetadata(
            name=name,
            namespace="test-namespace",
            labels={MODEL_NAME_LABEL: display_name.replace(" ", "-")},
            annotations=annotations,
        ),
        spec={
            "profiles": {
                "derivedFrom": {"selector": {"role": "base", "modelRef": {"name": "aim-base", "scope": "Namespace"}}},
                "versionPolicy": "all",
                "overrides": {
                    "aimId": repo_id,
                    "modelId": repo_id,
                    "image": TEST_IMAGE,
                    "modelSources": [
                        {
                            "modelId": repo_id,
                            "sourceUri": source_uri or f"hf://{repo_id}",
                        }
                    ],
                },
            }
        },
    )


# --- OnboardRequest schema validation ---


@pytest.mark.parametrize("field", ["repo_id", "revision", "sha", "display_name"])
def test_onboard_request_rejects_empty_required_string(field: str) -> None:
    """Required identifier fields must be non-empty. An empty ``display_name``
    in particular sanitizes to an empty ``DISPLAY_NAME_LABEL`` value, which
    turns conflict detection into a ``display-name=`` selector that matches
    every AIMModel missing the label — the schema must fail-fast at the
    boundary so service code never sees that state."""
    payload: dict[str, Any] = {
        "repo_id": "meta-llama/Llama-3-8B",
        "revision": "main",
        "sha": "abc123",
        "display_name": "Llama 3 8B",
        "image": TEST_IMAGE,
    }
    payload[field] = ""

    with pytest.raises(ValidationError) as exc_info:
        OnboardRequest(**payload)
    assert any(err["loc"] == (field,) for err in exc_info.value.errors())


def test_onboard_request_s3_source_requires_s3_storage_name() -> None:
    """S3 onboarding payloads require s3StorageName."""
    payload = {
        "source_type": "s3",
        "repo_id": "s3://my-bucket/path/to/model",
        "revision": "s3",
        "sha": "s3",
        "display_name": "S3 model",
        "image": TEST_IMAGE,
    }
    with pytest.raises(ValidationError, match="s3StorageName is required when sourceType is 's3'"):
        OnboardRequest(**payload)


def test_onboard_request_s3_source_rejects_hf_token_secret_name() -> None:
    """S3 onboarding payloads reject hfTokenSecretName to avoid mixed source credentials."""
    payload = {
        "source_type": "s3",
        "repo_id": "s3://my-bucket/path/to/model",
        "revision": "s3",
        "sha": "s3",
        "display_name": "S3 model",
        "image": TEST_IMAGE,
        "s3_storage_name": "my-s3-storage",
        "hf_token_secret_name": "my-hf-secret",
    }
    with pytest.raises(ValidationError, match="hfTokenSecretName is only supported when sourceType is 'huggingFace'"):
        OnboardRequest(**payload)


# --- _build_custom_aim_model_manifest ---


_RESOURCE_NAME = "llama-3-8b-import-abc12345"
_SOURCE_URI = "hf://meta-llama/Llama-3-8B"
_BUILDER_COMPONENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _make_request(**overrides: Any) -> OnboardRequest:
    """Default OnboardRequest used across builder and orchestrator tests.

    Centralizing defaults here means future fields on `OnboardRequest` only
    touch this factory, not every test body.
    """
    defaults: dict = {
        "source_type": "huggingFace",
        "repo_id": "meta-llama/Llama-3-8B",
        "revision": "main",
        "sha": "abc123",
        "display_name": "Llama 3 8B",
        "description": "A great model.",
        "image": TEST_IMAGE,
        "hf_token_secret_name": None,
    }
    defaults.update(overrides)
    return OnboardRequest(**defaults)


def _build_manifest(source: OnboardRequest | None = None, **overrides: Any) -> dict:
    source = source if source is not None else _make_request()
    return _build_custom_aim_model_manifest(
        namespace=overrides.pop("namespace", "test-namespace"),
        resource_name=overrides.pop("resource_name", _RESOURCE_NAME),
        source=source,
        source_uri=overrides.pop("source_uri", _SOURCE_URI),
        submitter=overrides.pop("submitter", TEST_SUBMITTER),
        component_id=overrides.pop("component_id", _BUILDER_COMPONENT_ID),
        base_model_name=_base_model_name_from_image_ref(source.image),
    )


def test_manifest_carries_required_kind_and_api_version() -> None:
    manifest = _build_manifest()

    assert manifest["apiVersion"] == "aim.eai.amd.com/v1alpha2"
    assert manifest["kind"] == "AIMModel"
    assert manifest["metadata"]["name"] == _RESOURCE_NAME
    assert manifest["metadata"]["namespace"] == "test-namespace"


def test_manifest_emits_only_profiles_spec_no_flat_fields() -> None:
    """v1alpha2 CEL forbids spec.image / spec.modelSources / spec.env /
    spec.imageMetadata alongside spec.profiles. The builder must emit a
    profiles-only spec so the manifest is admissible."""
    manifest = _build_manifest(_make_request(description="", hf_token_secret_name="my-hf-secret"))

    spec = manifest["spec"]
    assert set(spec.keys()) == {"profiles"}
    for forbidden in ("image", "modelSources", "env", "imageMetadata"):
        assert forbidden not in spec


def test_manifest_derives_from_base_image_model() -> None:
    """The custom model derives from base-role profiles emitted by the
    configured base-image AIMModel; identity filters are forbidden by CEL
    when role=base, so the selector carries only role + modelRef."""
    manifest = _build_manifest(_make_request(description="", image=DEFAULT_AIM_DEPLOYMENT_IMAGE_REF))

    profiles = manifest["spec"]["profiles"]
    selector = profiles["derivedFrom"]["selector"]
    assert selector["role"] == "base"
    assert selector["modelRef"]["name"] == "aim-base"
    assert selector["modelRef"]["scope"] == "Namespace"
    # versionPolicy=all copies every matched base version; pinned would require
    # a concrete source version we do not have, and CEL forbids version here.
    assert profiles["versionPolicy"] == "all"
    assert "version" not in profiles
    assert "aimId" not in selector and "modelId" not in selector


def test_manifest_derives_from_radeon_base_when_selected_image_is_radeon() -> None:
    manifest = _build_manifest(_make_request(description="", image=RADEON_AIM_DEPLOYMENT_IMAGE_REF))

    selector = manifest["spec"]["profiles"]["derivedFrom"]["selector"]
    assert selector["role"] == "base"
    assert selector["modelRef"]["name"] == "aim-radeon-base"
    assert selector["modelRef"]["scope"] == "Namespace"


def test_manifest_derives_from_any_base_family_name() -> None:
    manifest = _build_manifest(_make_request(description="", image="docker.io/amd/aim-mi300x-base:1.0"))

    selector = manifest["spec"]["profiles"]["derivedFrom"]["selector"]
    assert selector["modelRef"]["name"] == "aim-mi300x-base"


def test_manifest_uses_repository_tail_for_non_base_image_name() -> None:
    manifest = _build_manifest(_make_request(description="", image="docker.io/amd/tinyllama:1.0.0"))

    selector = manifest["spec"]["profiles"]["derivedFrom"]["selector"]
    assert selector["modelRef"]["name"] == "tinyllama"


def test_base_model_name_from_image_ref_falls_back_for_invalid_ref() -> None:
    assert _base_model_name_from_image_ref("not-a-valid-tagged-ref") == AIM_BASE_MODEL_NAME


def test_base_model_name_from_image_ref_rejects_invalid_selected_ref() -> None:
    with pytest.raises(ValidationException, match="does not identify a supported runtime family"):
        _base_model_name_from_image_ref("registry.example.com/custom-base", fallback=False)


def test_manifest_overrides_stamp_identity_required_for_base_role() -> None:
    """role=base requires overrides.aimId and overrides.modelId (base profiles
    carry no identity of their own); the builder sets both to the repo id."""
    manifest = _build_manifest(_make_request(description=""))

    overrides = manifest["spec"]["profiles"]["overrides"]
    assert overrides["aimId"] == "meta-llama/Llama-3-8B"
    assert overrides["modelId"] == "meta-llama/Llama-3-8B"


def test_manifest_stamps_display_and_canonical_labels_only() -> None:
    """Labels carry only sanitised model-name and canonical-name for selector
    queries. The human-readable display name lives in DISPLAY_NAME_ANNOTATION.
    No WORKLOAD_ID_LABEL since a BYOM import is not a workload."""
    manifest = _build_manifest(_make_request(description=""))

    labels = manifest["metadata"]["labels"]
    assert labels[MODEL_NAME_LABEL] == "Llama-3-8B"
    assert labels[CANONICAL_NAME_LABEL] == "meta-llama-Llama-3-8B"
    assert DISPLAY_NAME_ANNOTATION not in labels  # annotation, not label
    # Workload-id has no meaning for BYOM and must not be stamped.
    workload_id_label_key = "apps.eai.amd.com/workload-id"
    assert workload_id_label_key not in labels

    annotations = manifest["metadata"]["annotations"]
    assert annotations[DISPLAY_NAME_ANNOTATION] == "Llama 3 8B"


def test_manifest_carries_source_annotations() -> None:
    """Revision, sha, and description live in annotations because they aren't
    first-class spec fields on the AIMModel CR — but we still want to round-trip
    them between preview calls."""
    manifest = _build_manifest(_make_request(revision="dev-branch", description="An open model."))

    annotations = manifest["metadata"]["annotations"]
    assert annotations[REVISION_ANNOTATION] == "dev-branch"
    assert annotations[SOURCE_SHA_ANNOTATION] == "abc123"
    assert annotations[SOURCE_DESCRIPTION_ANNOTATION] == "An open model."


def test_manifest_stamps_precision_annotation_from_custom_profile() -> None:
    """The chosen precision is pruned from spec.profiles.overrides by the AIMModel
    CRD, so the builder must also record it on a durable annotation the edit
    prefill and deploy default read back."""
    manifest = _build_manifest(_make_request(description="", custom_profile={"precision": "fp8"}))

    assert manifest["metadata"]["annotations"][MODEL_PRECISION_ANNOTATION] == "fp8"


def test_manifest_omits_precision_annotation_when_not_chosen() -> None:
    """No customProfile precision means no precision annotation is stamped."""
    manifest = _build_manifest(_make_request(description=""))

    assert MODEL_PRECISION_ANNOTATION not in manifest["metadata"]["annotations"]


def test_manifest_carries_airm_provenance_annotations() -> None:
    """component-id, source-uri, and revision live under the airm.silogen.ai
    prefix as a cross-app contract: AIRM-side tooling reads these to identify
    the BYOM source independently of AIWB internals."""
    manifest = _build_manifest(_make_request(revision="dev-branch", description=""))

    annotations = manifest["metadata"]["annotations"]
    assert annotations[COMPONENT_ID_ANNOTATION] == _BUILDER_COMPONENT_ID
    assert annotations[SOURCE_URI_ANNOTATION] == _SOURCE_URI
    assert annotations[REVISION_ANNOTATION] == "dev-branch"


def test_manifest_keeps_raw_display_name_and_repo_id_on_dedicated_annotation_keys() -> None:
    """Raw display name and repo id live on dedicated annotation keys distinct
    from the label keys. Mixing the two maps under the same key would let a
    downstream reader pick up the sanitized label value when it wanted the
    raw string (or vice versa) depending on which map it grabs first."""
    manifest = _build_manifest(_make_request(description=""))

    annotations = manifest["metadata"]["annotations"]
    labels = manifest["metadata"]["labels"]
    assert annotations[MODEL_DISPLAY_NAME_ANNOTATION] == "Llama 3 8B"
    assert annotations[CANONICAL_REPO_ID_ANNOTATION] == "meta-llama/Llama-3-8B"
    # The MODEL_NAME_LABEL / CANONICAL_NAME_LABEL keys must remain label-only —
    # never carry an annotation entry with the same key but a different value.
    assert MODEL_NAME_LABEL not in annotations
    assert CANONICAL_NAME_LABEL not in annotations
    assert labels[MODEL_NAME_LABEL] != annotations[MODEL_DISPLAY_NAME_ANNOTATION]


def test_manifest_stamps_description_annotation_even_when_blank() -> None:
    """Always stamped so a re-onboard with a cleared description merge-patches the
    annotation back to empty rather than leaving a stale value behind."""
    manifest = _build_manifest(_make_request(description=""))

    assert manifest["metadata"]["annotations"][SOURCE_DESCRIPTION_ANNOTATION] == ""


def test_manifest_pins_source_in_model_sources() -> None:
    """overrides.modelSources is the engine's source of truth for where to load
    the BYO weights from. modelId is the logical HF id; sourceUri is hf://."""
    manifest = _build_manifest(_make_request(description=""))

    sources = manifest["spec"]["profiles"]["overrides"]["modelSources"]
    assert len(sources) == 1
    assert sources[0]["modelId"] == "meta-llama/Llama-3-8B"
    assert sources[0]["sourceUri"] == "hf://meta-llama/Llama-3-8B"


def test_manifest_sets_user_provided_image() -> None:
    manifest = _build_manifest(_make_request(description="", image="registry.example.com/byom:v2"))

    assert manifest["spec"]["profiles"]["overrides"]["image"] == "registry.example.com/byom:v2"


def test_manifest_hf_source_omits_s3_credentials() -> None:
    """HF onboarding no longer stages weights through internal S3, so model source
    env must not include AWS credential wiring."""
    manifest = _build_manifest(_make_request(description=""))

    source = manifest["spec"]["profiles"]["overrides"]["modelSources"][0]
    assert "env" not in source


def test_manifest_wires_hf_token_when_secret_name_given() -> None:
    """Gated/private models need HF_TOKEN wiring on the HF source."""
    manifest = _build_manifest(_make_request(description="", hf_token_secret_name="my-hf-secret"))

    env = manifest["spec"]["profiles"]["overrides"]["modelSources"][0]["env"]
    env_names = [e["name"] for e in env]

    assert env_names == ["HF_TOKEN"]

    hf_entry = next(e for e in env if e["name"] == "HF_TOKEN")
    assert hf_entry == {
        "name": "HF_TOKEN",
        "valueFrom": {"secretKeyRef": {"name": "my-hf-secret", "key": "token"}},
    }


def test_manifest_omits_hf_token_when_no_secret_name_given() -> None:
    """Public models do not need HF_TOKEN; omit model-source env entirely."""
    manifest = _build_manifest(_make_request(description=""))

    source = manifest["spec"]["profiles"]["overrides"]["modelSources"][0]
    assert "env" not in source


# --- derivedFrom bootstrap (aim-base) ---


def test_aim_base_manifest_uses_configured_image() -> None:
    manifest = _build_aim_base_model_manifest(namespace="test-namespace", image_ref=DEFAULT_AIM_DEPLOYMENT_IMAGE_REF)

    assert manifest["apiVersion"] == "aim.eai.amd.com/v1alpha2"
    assert manifest["kind"] == "AIMModel"
    assert manifest["metadata"]["name"] == AIM_BASE_MODEL_NAME
    assert manifest["metadata"]["namespace"] == "test-namespace"
    assert manifest["spec"] == {"image": DEFAULT_AIM_DEPLOYMENT_IMAGE_REF}


@pytest.mark.asyncio
async def test_ensure_namespace_aim_base_model_creates_when_missing(mock_kube_client: AsyncMock) -> None:
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    await ensure_namespace_aim_base_model(mock_kube_client, "test-namespace")

    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_called_once()
    create_kwargs = mock_kube_client.custom_objects.create_namespaced_custom_object.call_args.kwargs
    body = create_kwargs["body"]
    assert body["metadata"]["name"] == AIM_BASE_MODEL_NAME
    assert body["spec"]["image"] == DEFAULT_AIM_DEPLOYMENT_IMAGE_REF


@pytest.mark.asyncio
async def test_ensure_namespace_aim_base_model_skips_when_present(mock_kube_client: AsyncMock) -> None:
    await ensure_namespace_aim_base_model(mock_kube_client, "test-namespace")

    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_namespace_aim_base_model_honors_custom_image_ref(mock_kube_client: AsyncMock) -> None:
    custom_image = "docker.io/amd/custom-base:9.9"
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    await ensure_namespace_aim_base_model(mock_kube_client, "test-namespace", image_ref=custom_image)

    body = mock_kube_client.custom_objects.create_namespaced_custom_object.call_args.kwargs["body"]
    assert body["spec"]["image"] == custom_image


@pytest.mark.asyncio
async def test_ensure_namespace_aim_base_model_rejects_selected_tag_collision(
    mock_kube_client: AsyncMock,
) -> None:
    existing = _make_existing_aim_model(name="aim-radeon-base", source_uri=None)
    existing.spec.image = "docker.io/amdenterpriseai/aim-radeon-base:0.11"
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = None
    mock_kube_client.custom_objects.get_namespaced_custom_object.return_value = existing.model_dump(
        by_alias=True, exclude_none=True
    )

    with pytest.raises(ConflictException, match="conflicts with requested image"):
        await ensure_namespace_aim_base_model(
            mock_kube_client,
            "test-namespace",
            image_ref=RADEON_AIM_DEPLOYMENT_IMAGE_REF,
        )

    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing_image", "selected_image"),
    [
        ("docker.io/amdenterpriseai/aim-radeon-base:0.12", "amdenterpriseai/aim-radeon-base:0.12"),
        ("amdenterpriseai/aim-radeon-base:0.12", "docker.io/amdenterpriseai/aim-radeon-base:0.12"),
    ],
)
async def test_ensure_namespace_aim_base_model_accepts_registry_alias_of_existing_image(
    mock_kube_client: AsyncMock, existing_image: str, selected_image: str
) -> None:
    existing = _make_existing_aim_model(name="aim-radeon-base", source_uri=None)
    existing.spec.image = existing_image
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = None
    mock_kube_client.custom_objects.get_namespaced_custom_object.return_value = existing.model_dump(
        by_alias=True, exclude_none=True
    )

    model_name = await ensure_namespace_aim_base_model(
        mock_kube_client,
        "test-namespace",
        image_ref=selected_image,
    )

    assert model_name == "aim-radeon-base"
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_namespace_aim_base_model_accepts_create_race_registry_alias(
    mock_kube_client: AsyncMock,
) -> None:
    existing = _make_existing_aim_model(name="aim-radeon-base", source_uri=None)
    existing.spec.image = f"docker.io/{RADEON_AIM_DEPLOYMENT_IMAGE_REF}"
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = [
        ApiException(status=404),
        existing.model_dump(by_alias=True, exclude_none=True),
    ]
    mock_kube_client.custom_objects.create_namespaced_custom_object.side_effect = ApiException(status=409)

    model_name = await ensure_namespace_aim_base_model(
        mock_kube_client,
        "test-namespace",
        image_ref=RADEON_AIM_DEPLOYMENT_IMAGE_REF,
    )

    assert model_name == "aim-radeon-base"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image_ref",
    [
        "docker.io/vendor/aim_base:1",
        "docker.io/vendor/aim..base:1",
        "docker.io/vendor/aim-.base:1",
        f"docker.io/vendor/{'a' * 64}.base:1",
    ],
)
async def test_ensure_namespace_aim_base_model_rejects_invalid_k8s_family_name(
    mock_kube_client: AsyncMock,
    image_ref: str,
) -> None:
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    with pytest.raises(ValidationException, match="does not identify a supported runtime family"):
        await ensure_namespace_aim_base_model(
            mock_kube_client,
            "test-namespace",
            image_ref=image_ref,
        )

    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image_ref",
    [
        "registry.example.com/custom-base",
        "registry.example.com:5000/custom-base",
    ],
)
async def test_ensure_namespace_aim_base_model_rejects_unparseable_selected_image(
    mock_kube_client: AsyncMock,
    image_ref: str,
) -> None:
    with pytest.raises(ValidationException, match="does not identify a supported runtime family"):
        await ensure_namespace_aim_base_model(
            mock_kube_client,
            "test-namespace",
            image_ref=image_ref,
        )

    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.get_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_namespace_aim_base_model_accepts_dotted_family_name(mock_kube_client: AsyncMock) -> None:
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    await ensure_namespace_aim_base_model(
        mock_kube_client,
        "test-namespace",
        image_ref="docker.io/vendor/aim-base.v2:1",
    )

    body = mock_kube_client.custom_objects.create_namespaced_custom_object.call_args.kwargs["body"]
    assert body["metadata"]["name"] == "aim-base.v2"
    assert body["spec"]["image"] == "docker.io/vendor/aim-base.v2:1"


@pytest.mark.asyncio
async def test_ensure_namespace_aim_base_model_honors_custom_model_name(mock_kube_client: AsyncMock) -> None:
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    await ensure_namespace_aim_base_model(
        mock_kube_client,
        "test-namespace",
        image_ref="docker.io/amd/tinyllama:1.0.0",
        model_name="tinyllama",
    )

    body = mock_kube_client.custom_objects.create_namespaced_custom_object.call_args.kwargs["body"]
    assert body["metadata"]["name"] == "tinyllama"
    assert body["spec"]["image"] == "docker.io/amd/tinyllama:1.0.0"


@pytest.mark.asyncio
async def test_ensure_namespace_aim_base_model_derives_name_from_discovered_image(mock_kube_client: AsyncMock) -> None:
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)
    discovered_image = "docker.io/silogenai/aim-radeon-base:0.12-preview"

    with patch("app.custom_models.service.get_cluster_base_image_refs", AsyncMock(return_value=[discovered_image])):
        model_name = await ensure_namespace_aim_base_model(mock_kube_client, "test-namespace")

    body = mock_kube_client.custom_objects.create_namespaced_custom_object.call_args.kwargs["body"]
    assert model_name == "aim-radeon-base"
    assert body["metadata"]["name"] == "aim-radeon-base"
    assert body["spec"]["image"] == discovered_image


@pytest.mark.asyncio
async def test_ensure_namespace_aim_base_model_repoints_existing_image_mismatch(mock_kube_client: AsyncMock) -> None:
    existing = _make_existing_aim_model(name="aim-radeon-base", source_uri=None)
    existing.spec.image = "docker.io/amd/aim-radeon-base:old"

    async def get_namespaced_custom_object(*_args: Any, name: str, **_kwargs: Any) -> dict:
        if name == "aim-radeon-base":
            return existing.model_dump(by_alias=True)
        raise ApiException(status=404)

    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(side_effect=get_namespaced_custom_object)
    discovered_image = "docker.io/silogenai/aim-radeon-base:0.12-preview"

    with patch("app.custom_models.service.get_cluster_base_image_refs", AsyncMock(return_value=[discovered_image])):
        model_name = await ensure_namespace_aim_base_model(mock_kube_client, "test-namespace")

    assert model_name == "aim-radeon-base"
    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()
    patch_kwargs = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs
    assert patch_kwargs["name"] == "aim-radeon-base"
    assert patch_kwargs["body"] == {"spec": {"image": discovered_image}}


@pytest.mark.asyncio
async def test_ensure_namespace_aim_base_model_tolerates_create_race_conflict(mock_kube_client: AsyncMock) -> None:
    existing = _build_aim_base_model_manifest(
        namespace="test-namespace",
        image_ref=DEFAULT_AIM_DEPLOYMENT_IMAGE_REF,
    )
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = [
        ApiException(status=404),
        existing,
    ]
    mock_kube_client.custom_objects.create_namespaced_custom_object.side_effect = ApiException(status=409)

    with patch(
        "app.custom_models.service.get_cluster_base_image_refs",
        AsyncMock(return_value=[DEFAULT_AIM_DEPLOYMENT_IMAGE_REF]),
    ):
        await ensure_namespace_aim_base_model(mock_kube_client, "test-namespace")


@pytest.mark.asyncio
async def test_ensure_namespace_aim_base_model_rejects_create_race_tag_mismatch(
    mock_kube_client: AsyncMock,
) -> None:
    existing = _make_existing_aim_model(name="aim-radeon-base", source_uri=None)
    existing.spec.image = "docker.io/amdenterpriseai/aim-radeon-base:0.11"
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = [
        ApiException(status=404),
        existing.model_dump(by_alias=True, exclude_none=True),
    ]
    mock_kube_client.custom_objects.create_namespaced_custom_object.side_effect = ApiException(status=409)

    with pytest.raises(ConflictException, match="conflicts with requested image"):
        await ensure_namespace_aim_base_model(
            mock_kube_client,
            "test-namespace",
            image_ref=RADEON_AIM_DEPLOYMENT_IMAGE_REF,
        )


@pytest.mark.asyncio
async def test_ensure_namespace_aim_base_model_noop_when_scope_not_namespace(mock_kube_client: AsyncMock) -> None:
    with patch("app.custom_models.service.AIM_BASE_MODEL_SCOPE", "Cluster"):
        model_name = await ensure_namespace_aim_base_model(mock_kube_client, "test-namespace")

    assert model_name == AIM_BASE_MODEL_NAME
    mock_kube_client.custom_objects.get_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_cluster_scope_returns_selected_family_without_provisioning(
    mock_kube_client: AsyncMock,
) -> None:
    cluster_models = [_cluster_model_item("aim-radeon-base-012", RADEON_AIM_DEPLOYMENT_IMAGE_REF)]
    with (
        patch("app.custom_models.service.AIM_BASE_MODEL_SCOPE", "Cluster"),
        patch("app.custom_models.service.aims_gateway.list_aim_cluster_models", return_value=cluster_models),
    ):
        model_name = await ensure_namespace_aim_base_model(
            mock_kube_client,
            "test-namespace",
            image_ref=RADEON_AIM_DEPLOYMENT_IMAGE_REF,
        )

    assert model_name == "aim-radeon-base-012"
    mock_kube_client.custom_objects.get_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_cluster_scope_matches_image_independent_of_resource_name(
    mock_kube_client: AsyncMock,
) -> None:
    cluster_models = [_cluster_model_item("aim-base-013", "amdenterpriseai/aim-base:0.13")]
    with (
        patch("app.custom_models.service.AIM_BASE_MODEL_SCOPE", "Cluster"),
        patch("app.custom_models.service.aims_gateway.list_aim_cluster_models", return_value=cluster_models),
    ):
        model_name = await ensure_namespace_aim_base_model(
            mock_kube_client,
            "test-namespace",
            image_ref="docker.io/amdenterpriseai/aim-base:0.13",
        )

    assert model_name == "aim-base-013"


@pytest.mark.asyncio
async def test_ensure_cluster_scope_ignores_non_base_cluster_models_with_same_image(
    mock_kube_client: AsyncMock,
) -> None:
    cluster_models = [
        _cluster_model_item("aaa-inference", "amdenterpriseai/aim-base:0.13", base_only=False),
        _cluster_model_item("aim-base-013", "amdenterpriseai/aim-base:0.13"),
    ]
    with (
        patch("app.custom_models.service.AIM_BASE_MODEL_SCOPE", "Cluster"),
        patch("app.custom_models.service.aims_gateway.list_aim_cluster_models", return_value=cluster_models),
    ):
        model_name = await ensure_namespace_aim_base_model(
            mock_kube_client,
            "test-namespace",
            image_ref="amdenterpriseai/aim-base:0.13",
        )

    assert model_name == "aim-base-013"


@pytest.mark.asyncio
async def test_ensure_cluster_scope_rejects_when_only_non_base_cluster_model_matches(
    mock_kube_client: AsyncMock,
) -> None:
    cluster_models = [
        _cluster_model_item("aaa-inference", RADEON_AIM_DEPLOYMENT_IMAGE_REF, base_only=False),
        _cluster_model_item("unsupported-base", RADEON_AIM_DEPLOYMENT_IMAGE_REF, discovered_supported=0),
    ]
    with (
        patch("app.custom_models.service.AIM_BASE_MODEL_SCOPE", "Cluster"),
        patch("app.custom_models.service.aims_gateway.list_aim_cluster_models", return_value=cluster_models),
    ):
        with pytest.raises(NotFoundException, match="No AIMClusterModel found"):
            await ensure_namespace_aim_base_model(
                mock_kube_client,
                "test-namespace",
                image_ref=RADEON_AIM_DEPLOYMENT_IMAGE_REF,
            )


@pytest.mark.asyncio
async def test_ensure_cluster_scope_rejects_when_no_cluster_model_matches(
    mock_kube_client: AsyncMock,
) -> None:
    with (
        patch("app.custom_models.service.AIM_BASE_MODEL_SCOPE", "Cluster"),
        patch("app.custom_models.service.aims_gateway.list_aim_cluster_models", return_value=[]),
    ):
        with pytest.raises(NotFoundException, match="No AIMClusterModel found"):
            await ensure_namespace_aim_base_model(
                mock_kube_client,
                "test-namespace",
                image_ref=RADEON_AIM_DEPLOYMENT_IMAGE_REF,
            )


@pytest.mark.asyncio
async def test_ensure_cluster_scope_rejects_unparseable_selected_image(mock_kube_client: AsyncMock) -> None:
    with patch("app.custom_models.service.AIM_BASE_MODEL_SCOPE", "Cluster"):
        with pytest.raises(ValidationException, match="does not identify a supported runtime family"):
            await ensure_namespace_aim_base_model(
                mock_kube_client,
                "test-namespace",
                image_ref="registry.example.com/custom-base",
            )


@pytest.mark.asyncio
async def test_onboard_cluster_scope_derives_from_selected_family(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)
    cluster_models = [_cluster_model_item("tinyllama-cluster", TEST_IMAGE)]

    with (
        patch("app.custom_models.service.AIM_BASE_MODEL_SCOPE", "Cluster"),
        patch("app.custom_models.service.aims_gateway.list_aim_cluster_models", return_value=cluster_models),
    ):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(repo_id="meta-llama/Llama-3-8B"),
        )

    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_called_once()
    body = mock_kube_client.custom_objects.create_namespaced_custom_object.call_args.kwargs["body"]
    selector = body["spec"]["profiles"]["derivedFrom"]["selector"]
    assert selector["modelRef"]["name"] == "tinyllama-cluster"
    assert selector["modelRef"]["scope"] == "Cluster"


@pytest.mark.asyncio
async def test_onboard_provisions_base_model_for_selected_image(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    create_calls: list[dict] = []
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    def record_create(*_args: Any, body: dict, **_kwargs: Any) -> dict:
        create_calls.append(body)
        return body

    mock_kube_client.custom_objects.create_namespaced_custom_object.side_effect = record_create

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(repo_id="meta-llama/Llama-3-8B"),
    )

    assert len(create_calls) == 2
    assert create_calls[0]["metadata"]["name"] == _base_model_name_from_image_ref(TEST_IMAGE)
    assert create_calls[0]["spec"]["image"] == TEST_IMAGE
    selector = create_calls[1]["spec"]["profiles"]["derivedFrom"]["selector"]
    assert selector["modelRef"]["name"] == _base_model_name_from_image_ref(TEST_IMAGE)


@pytest.mark.asyncio
async def test_onboard_provisions_radeon_base_before_custom_model_create(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    create_calls: list[dict] = []
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    def record_create(*_args: Any, body: dict, **_kwargs: Any) -> dict:
        create_calls.append(body)
        return body

    mock_kube_client.custom_objects.create_namespaced_custom_object.side_effect = record_create

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(repo_id="meta-llama/Llama-3-8B", image=RADEON_AIM_DEPLOYMENT_IMAGE_REF),
    )

    assert len(create_calls) == 2
    assert create_calls[0]["metadata"]["name"] == "aim-radeon-base"
    assert create_calls[0]["spec"]["image"] == RADEON_AIM_DEPLOYMENT_IMAGE_REF
    selector = create_calls[1]["spec"]["profiles"]["derivedFrom"]["selector"]
    assert selector["modelRef"]["name"] == "aim-radeon-base"


@pytest.mark.asyncio
async def test_onboard_provisions_any_base_family_before_custom_model_create(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    create_calls: list[dict] = []
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    def record_create(*_args: Any, body: dict, **_kwargs: Any) -> dict:
        create_calls.append(body)
        return body

    mock_kube_client.custom_objects.create_namespaced_custom_object.side_effect = record_create

    custom_base_image = "docker.io/amd/aim-mi300x-base:1.0"
    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(repo_id="meta-llama/Llama-3-8B", image=custom_base_image),
    )

    assert len(create_calls) == 2
    assert create_calls[0]["metadata"]["name"] == "aim-mi300x-base"
    selector = create_calls[1]["spec"]["profiles"]["derivedFrom"]["selector"]
    assert selector["modelRef"]["name"] == "aim-mi300x-base"


@pytest.mark.asyncio
async def test_onboard_skips_selected_base_model_create_when_already_present(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    base_model_name = _base_model_name_from_image_ref(TEST_IMAGE)
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(repo_id="meta-llama/Llama-3-8B"),
    )

    create_call = mock_kube_client.custom_objects.create_namespaced_custom_object.await_args
    assert create_call is not None
    created_body = create_call.kwargs.get("body") or create_call.args[-1]
    assert created_body["metadata"]["name"] != base_model_name


@pytest.mark.asyncio
async def test_onboard_repatches_existing_model_after_ensuring_selected_base(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """Re-onboard provisions the selected base when missing before patching."""
    existing = _make_existing_aim_model()
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [existing.model_dump(by_alias=True)]
    }
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)
    mock_kube_client.custom_objects.patch_namespaced_custom_object.return_value = existing.model_dump(by_alias=True)

    create_calls: list[dict] = []

    def record_create(*_args: Any, body: dict, **_kwargs: Any) -> dict:
        create_calls.append(body)
        return body

    mock_kube_client.custom_objects.create_namespaced_custom_object.side_effect = record_create

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(repo_id="meta-llama/Meta-Llama-3-8B-Instruct", description="An open model."),
    )

    assert len(create_calls) == 1
    assert create_calls[0]["metadata"]["name"] == _base_model_name_from_image_ref(TEST_IMAGE)
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_called_once()
    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_called_once()


# --- onboard_custom_model_source ---


@pytest.mark.asyncio
async def test_onboard_rejects_malformed_repo_id_before_touching_k8s_or_s3(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock, stub_onboard_hub_reverify: dict[str, AsyncMock]
) -> None:
    """Repo id validation runs at the service boundary so a malformed value never
    reaches the K8s API (where it would otherwise produce a malformed label and a
    confusing admission error). It also fails before the Hub re-verify fetch so
    we don't burn a Hub call on a request we already know is bad."""
    with pytest.raises(ValidationException, match="not a valid Hugging Face repo id"):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(repo_id="not-a-valid-repo"),
        )

    stub_onboard_hub_reverify["fetch"].assert_not_called()
    mock_kube_client.custom_objects.list_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()
    mock_minio_client.upload_object.assert_not_called()


@pytest.mark.asyncio
async def test_onboard_accepts_custom_profile_without_warning(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """customProfile is now wired end-to-end; the legacy "wiring not implemented" warning must not fire."""
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    with patch("app.custom_models.service.logger") as mock_logger:
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(repo_id="meta-llama/Llama-3-8B", custom_profile={"precision": "fp16"}),
        )

    warning_messages = [call.args[0] for call in mock_logger.warning.call_args_list]
    assert not any("customProfile" in msg and "profile wiring" in msg for msg in warning_messages)


def test_manifest_writes_custom_profile_to_aim_model_overrides() -> None:
    """customProfile lands on AIMModel.spec.profiles.overrides so aim-engine bakes it into each AIMProfile."""
    manifest = _build_manifest(
        _make_request(
            description="",
            custom_profile={
                "precision": "fp16",
                "engine": "vllm",
                "engineArgs": {"max-model-len": 4096},
            },
        )
    )

    overrides = manifest["spec"]["profiles"]["overrides"]
    assert overrides["precision"] == "fp16"
    assert overrides["engine"] == "vllm"
    assert overrides["engineArgs"] == {"max-model-len": 4096}


def test_manifest_persists_runtime_profile_fields_from_onboard_wizard() -> None:
    """The onboard wizard's customProfile (canonical acceleratorModel, precision, engineArgs/engineEnv) must persist verbatim onto overrides."""
    manifest = _build_manifest(
        _make_request(
            description="",
            custom_profile={
                "imageFamilyId": "aim-base",
                "acceleratorType": "gpu",
                "acceleratorModel": "MI300X",
                "acceleratorCount": 1,
                "precision": "fp16",
                "engineArgs": {"max-model-len": 4096, "attention-backend": "TRITON_ATTN"},
                # Env vars arrive as name/value entries (UPPER_SNAKE_CASE names ride as
                # values to clear the camelCase contract) and collapse to a map on write.
                "engineEnv": [{"name": "VLLM_ROCM_USE_AITER", "value": "1"}],
            },
        )
    )

    overrides = manifest["spec"]["profiles"]["overrides"]
    # Precision and the canonical model name (not a device id) reach the spec.
    assert overrides["acceleratorModel"] == "MI300X"
    assert overrides["precision"] == "fp16"
    # Engine args / env vars persist as structured maps, not empty.
    assert overrides["engineArgs"] == {"max-model-len": 4096, "attention-backend": "TRITON_ATTN"}
    assert overrides["engineEnv"] == {"VLLM_ROCM_USE_AITER": "1"}


def test_manifest_stamped_fields_win_over_conflicting_custom_profile_keys() -> None:
    """customProfile must not override system-stamped aimId, modelId, image, or modelSources."""
    manifest = _build_manifest(
        _make_request(
            custom_profile={
                "aimId": "evil/evil",
                "modelId": "evil/evil",
                "image": TEST_IMAGE,
                "modelSources": [{"modelId": "evil", "sourceUri": "s3://evil/weights/"}],
                "precision": "fp16",
            },
        )
    )

    overrides = manifest["spec"]["profiles"]["overrides"]
    assert overrides["aimId"] == "meta-llama/Llama-3-8B"
    assert overrides["modelId"] == "meta-llama/Llama-3-8B"
    assert overrides["image"] == TEST_IMAGE
    assert overrides["modelSources"][0]["modelId"] == "meta-llama/Llama-3-8B"
    assert overrides["modelSources"][0]["sourceUri"] == _SOURCE_URI
    assert overrides["precision"] == "fp16"


def test_manifest_without_custom_profile_omits_runtime_override_keys() -> None:
    """v1alpha2 always emits spec.profiles; customProfile only adds extra override keys."""
    manifest = _build_manifest(_make_request(description=""))

    overrides = manifest["spec"]["profiles"]["overrides"]
    assert overrides["aimId"] == "meta-llama/Llama-3-8B"
    assert "precision" not in overrides
    assert "engine" not in overrides


def test_manifest_treats_empty_custom_profile_as_no_extra_overrides() -> None:
    """Empty customProfile ({}) must not add runtime override keys beyond the base stamp."""
    manifest = _build_manifest(_make_request(description="", custom_profile={}))

    overrides = manifest["spec"]["profiles"]["overrides"]
    assert overrides["aimId"] == "meta-llama/Llama-3-8B"
    assert "precision" not in overrides


def test_manifest_preserves_non_identifier_override_keys() -> None:
    """customProfile is an opaque pass-through: keys that aren't valid Python identifiers must round-trip."""
    manifest = _build_manifest(
        _make_request(
            description="",
            custom_profile={"engine-args": {"max-model-len": 4096}, "foo.bar": "baz"},
        )
    )

    overrides = manifest["spec"]["profiles"]["overrides"]
    assert overrides["engine-args"] == {"max-model-len": 4096}
    assert overrides["foo.bar"] == "baz"


def test_onboard_request_rejects_conflicting_image_in_custom_profile() -> None:
    """Top-level and customProfile images must agree to avoid two image refs on the emitted profile."""
    with pytest.raises(ValidationError) as exc_info:
        OnboardRequest(
            repo_id="meta-llama/Llama-3-8B",
            revision="main",
            sha="abc123",
            display_name="Llama 3 8B",
            image="docker.io/amd/tinyllama:1.0.0",
            custom_profile={"image": "docker.io/other/image:v9"},
        )

    message = str(exc_info.value)
    assert "docker.io/other/image:v9" in message
    assert "docker.io/amd/tinyllama:1.0.0" in message


def test_onboard_request_allows_matching_image_in_custom_profile() -> None:
    """The matching-image case is a no-op redundancy from the UI and must pass."""
    request = OnboardRequest(
        repo_id="meta-llama/Llama-3-8B",
        revision="main",
        sha="abc123",
        display_name="Llama 3 8B",
        image="docker.io/amd/tinyllama:1.0.0",
        custom_profile={"image": "docker.io/amd/tinyllama:1.0.0", "precision": "fp16"},
    )
    assert request.custom_profile == {"image": "docker.io/amd/tinyllama:1.0.0", "precision": "fp16"}


def test_onboard_request_allows_omitted_image_in_custom_profile() -> None:
    """customProfile without an ``image`` key inherits the top-level image."""
    request = OnboardRequest(
        repo_id="meta-llama/Llama-3-8B",
        revision="main",
        sha="abc123",
        display_name="Llama 3 8B",
        image="docker.io/amd/tinyllama:1.0.0",
        custom_profile={"precision": "fp16"},
    )
    assert request.custom_profile == {"precision": "fp16"}


def test_onboard_request_rejects_empty_image_in_custom_profile() -> None:
    """Empty customProfile.image must 422 — same rule as the required top-level image field."""
    with pytest.raises(ValidationError) as exc_info:
        OnboardRequest(
            repo_id="meta-llama/Llama-3-8B",
            revision="main",
            sha="abc123",
            display_name="Llama 3 8B",
            image="docker.io/amd/tinyllama:1.0.0",
            custom_profile={"image": ""},
        )

    assert "empty string" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_repatch_clears_custom_override_keys_when_custom_profile_omitted(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
) -> None:
    """Re-onboard without customProfile must rewrite the v1alpha2 profiles block without prior override keys."""
    existing = _make_existing_aim_model()
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [existing.model_dump(by_alias=True)]
    }
    mock_kube_client.custom_objects.patch_namespaced_custom_object.return_value = existing.model_dump(by_alias=True)

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(repo_id="meta-llama/Meta-Llama-3-8B-Instruct"),
    )

    patch_call = mock_kube_client.custom_objects.patch_namespaced_custom_object.await_args
    assert patch_call is not None
    patch_body = patch_call.kwargs.get("body") or patch_call.args[-1]
    profiles = patch_body["spec"]["profiles"]
    assert profiles["derivedFrom"]["selector"]["role"] == "base"
    overrides = profiles["overrides"]
    assert overrides["aimId"] == "meta-llama/Meta-Llama-3-8B-Instruct"
    assert "precision" not in overrides


@pytest.mark.asyncio
async def test_repatch_merges_custom_profile_into_profiles_overrides(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
) -> None:
    """Re-onboard with customProfile must merge runtime keys into the v1alpha2 overrides stamp."""
    existing = _make_existing_aim_model()
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [existing.model_dump(by_alias=True)]
    }
    mock_kube_client.custom_objects.patch_namespaced_custom_object.return_value = existing.model_dump(by_alias=True)

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(
            repo_id="meta-llama/Meta-Llama-3-8B-Instruct",
            custom_profile={"precision": "bf16"},
        ),
    )

    patch_call = mock_kube_client.custom_objects.patch_namespaced_custom_object.await_args
    assert patch_call is not None
    patch_body = patch_call.kwargs.get("body") or patch_call.args[-1]
    overrides = patch_body["spec"]["profiles"]["overrides"]
    assert overrides["precision"] == "bf16"
    assert overrides["aimId"] == "meta-llama/Meta-Llama-3-8B-Instruct"


@pytest.mark.asyncio
async def test_onboard_creates_cr_then_uploads_manifest_when_absent(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """First call onboards: provisions aim-base when absent, creates the custom AIMModel CR, then mirrors to S3."""
    call_order: list[str] = []
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    def record_k8s_create(*_args: Any, **_kwargs: Any) -> dict:
        call_order.append("k8s_create")
        return _CREATED_AIM_MODEL_STUB

    def record_s3_upload(**_kwargs: Any) -> None:
        call_order.append("s3_upload")

    mock_kube_client.custom_objects.create_namespaced_custom_object.side_effect = record_k8s_create
    mock_minio_client.upload_object.side_effect = record_s3_upload

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(repo_id="meta-llama/Llama-3-8B", description="An open model."),
    )

    assert call_order == ["k8s_create", "k8s_create", "s3_upload"]

    mock_minio_client.upload_object.assert_called_once()
    upload_kwargs = mock_minio_client.upload_object.call_args.kwargs
    assert upload_kwargs["object_name"].startswith("test-namespace/custom-models/")
    assert upload_kwargs["object_name"].endswith("/manifest.yaml")
    payload = upload_kwargs["data"].decode("utf-8")
    assert payload.startswith("---"), "Manifest must start with a YAML document marker"
    documents = list(yaml.safe_load_all(payload))
    assert len(documents) == 1
    assert documents[0]["kind"] == "AIMModel"
    source = documents[0]["spec"]["profiles"]["overrides"]["modelSources"][0]
    assert source["sourceUri"] == "hf://meta-llama/Llama-3-8B"
    assert "env" not in source

    assert mock_kube_client.custom_objects.create_namespaced_custom_object.await_count == 2


@pytest.mark.asyncio
async def test_onboard_stamps_fresh_component_id_on_create(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """Each new onboarded CR gets a freshly generated component-id UUID stamped
    under the AIRM-prefixed annotation."""
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(repo_id="meta-llama/Llama-3-8B", description=""),
    )

    create_kwargs = mock_kube_client.custom_objects.create_namespaced_custom_object.call_args.kwargs
    body = create_kwargs["body"]
    assert "profiles" in body["spec"]
    component_id = body["metadata"]["annotations"][COMPONENT_ID_ANNOTATION]
    uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    assert uuid_pattern.match(component_id), f"Expected UUID-shaped component-id, got {component_id!r}"


@pytest.mark.asyncio
async def test_onboard_is_idempotent_on_same_display_name_and_source(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """Second call with same (display name, repo) patches the CR and overwrites the manifest."""
    existing = _make_existing_aim_model()
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [existing.model_dump(by_alias=True)]
    }
    mock_kube_client.custom_objects.patch_namespaced_custom_object.return_value = existing.model_dump(by_alias=True)

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(repo_id="meta-llama/Meta-Llama-3-8B-Instruct", description="An open model."),
    )

    mock_minio_client.upload_object.assert_called_once()
    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_called_once()


@pytest.mark.asyncio
async def test_onboard_re_submission_preserves_appended_aim_profile(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """Re-onboarding must not erase an AIMProfile document already in the manifest.

    The upsert path replaces the AIMModel document by ``(kind, name)`` identity
    while leaving sibling documents (e.g. an AIMProfile appended separately)
    intact.
    """
    existing = _make_existing_aim_model()
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [existing.model_dump(by_alias=True)]
    }
    mock_kube_client.custom_objects.patch_namespaced_custom_object.return_value = existing.model_dump(by_alias=True)

    aim_profile_doc = {
        "apiVersion": "aim.eai.amd.com/v1alpha2",
        "kind": "AIMProfile",
        "metadata": {
            "name": f"{existing.metadata.name}-default",
            "namespace": "test-namespace",
            "annotations": {"aim.eai.amd.com/deployment-image-ref": "amdenterpriseai/aim-base:0.11"},
        },
        "spec": {"aimId": existing.metadata.name, "image": "amdenterpriseai/aim-base:0.11"},
    }
    prior_aim_model_doc = {
        "apiVersion": "aim.eai.amd.com/v1alpha1",
        "kind": "AIMModel",
        "metadata": {"name": existing.metadata.name, "namespace": "test-namespace"},
        "spec": {"modelSources": [{"modelId": "meta-llama/Meta-Llama-3-8B-Instruct", "sourceUri": "s3://prior"}]},
    }
    prior_manifest = yaml.safe_dump_all(
        [prior_aim_model_doc, aim_profile_doc], sort_keys=False, explicit_start=True
    ).encode("utf-8")
    mock_minio_client.download_object.side_effect = None
    mock_minio_client.download_object.return_value = prior_manifest

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(repo_id="meta-llama/Meta-Llama-3-8B-Instruct", description="An open model."),
    )

    mock_minio_client.upload_object.assert_called_once()
    upload_kwargs = mock_minio_client.upload_object.call_args.kwargs
    written_documents = list(yaml.safe_load_all(upload_kwargs["data"]))

    kinds_in_order = [doc["kind"] for doc in written_documents]
    assert kinds_in_order == ["AIMModel", "AIMProfile"], (
        "Re-onboard must replace the AIMModel document in place and leave sibling documents untouched."
    )
    assert written_documents[1] == aim_profile_doc, (
        "AIMProfile document was modified by re-onboard; only its sibling AIMModel doc may change on re-submission."
    )


@pytest.mark.asyncio
async def test_onboard_preserves_component_id_on_patch(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """An idempotent re-submission must reuse the existing CR's component-id so
    the stable identity survives across patches."""
    existing = _make_existing_aim_model()
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [existing.model_dump(by_alias=True)]
    }
    mock_kube_client.custom_objects.patch_namespaced_custom_object.return_value = existing.model_dump(by_alias=True)

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(repo_id="meta-llama/Meta-Llama-3-8B-Instruct", description=""),
    )

    patch_kwargs = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs
    annotations = patch_kwargs["body"]["metadata"]["annotations"]
    assert annotations[COMPONENT_ID_ANNOTATION] == _EXISTING_COMPONENT_ID


@pytest.mark.asyncio
async def test_onboard_backfills_component_id_for_legacy_cr_on_patch(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """Legacy CRs predating the AIRM annotation must get a freshly stamped
    component-id on first patch so subsequent calls have something to preserve."""
    existing = _make_existing_aim_model(component_id=None)
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [existing.model_dump(by_alias=True)]
    }
    mock_kube_client.custom_objects.patch_namespaced_custom_object.return_value = existing.model_dump(by_alias=True)

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(repo_id="meta-llama/Meta-Llama-3-8B-Instruct", description=""),
    )

    patch_kwargs = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs
    annotations = patch_kwargs["body"]["metadata"]["annotations"]
    uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    assert uuid_pattern.match(annotations[COMPONENT_ID_ANNOTATION])


@pytest.mark.asyncio
async def test_onboard_conflict_on_same_display_name_different_repo(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """Same display name but a different HF repo must raise so the FE prompts for a new name.
    The conflict key is modelId (the HF repo), not sourceUri (the s3:// path the system assigns)."""
    existing = _make_existing_aim_model(repo_id="meta-llama/Meta-Llama-3-8B-Instruct")
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [existing.model_dump(by_alias=True)]
    }

    with pytest.raises(ConflictException, match="already exists"):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(
                repo_id="other/Model",
                description="",
                image="docker.io/amd/new-runtime-family:1.0.0",
            ),
        )

    mock_minio_client.upload_object.assert_not_called()
    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
async def test_onboard_re_submission_with_bumped_family_tag_conflicts(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """Same model, new tag of an already-provisioned family, must 409.

    Idempotency covers the same form including image. Changing the runtime tag
    would otherwise repoint the shared base-model CR; update the model instead.
    """
    existing = _make_existing_aim_model()
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [existing.model_dump(by_alias=True)]
    }

    with pytest.raises(ConflictException, match="already uses image"):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(
                repo_id="meta-llama/Meta-Llama-3-8B-Instruct",
                description="",
                image="docker.io/amd/tinyllama:2.0.0",
            ),
        )

    mock_minio_client.upload_object.assert_not_called()
    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
async def test_onboard_skips_s3_when_k8s_create_fails(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """k8s-first ordering: when the CR create fails, S3 is never touched — so there's
    nothing to compensate and the next retry starts from a clean slate."""
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}
    mock_kube_client.custom_objects.create_namespaced_custom_object.side_effect = RuntimeError("kube boom")

    with pytest.raises(RuntimeError, match="kube boom"):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(repo_id="meta-llama/Llama-3-8B", description=""),
        )

    mock_minio_client.upload_object.assert_not_called()
    mock_minio_client.delete_object.assert_not_called()


@pytest.mark.asyncio
async def test_onboard_skips_s3_when_k8s_patch_fails(mock_kube_client: AsyncMock, mock_minio_client: MagicMock) -> None:
    """k8s-first ordering: when the CR patch fails, S3 is never overwritten — so the
    existing mirror is unchanged and the next idempotent call retries cleanly.
    """
    existing = _make_existing_aim_model()
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [existing.model_dump(by_alias=True)]
    }
    mock_kube_client.custom_objects.patch_namespaced_custom_object.side_effect = ApiException(
        status=500, reason="Internal Server Error"
    )

    with pytest.raises(ExternalServiceError, match="Failed to patch AIMModel"):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(repo_id="meta-llama/Meta-Llama-3-8B-Instruct", description=""),
        )

    mock_minio_client.upload_object.assert_not_called()
    mock_minio_client.delete_object.assert_not_called()


@pytest.mark.asyncio
async def test_onboard_rolls_back_cr_when_s3_upload_fails(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """A failed S3 manifest sync deletes the just-created CR so the next call
    can retry from a clean slate instead of finding a CR without a manifest."""
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    with patch(
        "app.custom_models.service.write_manifest_to_s3",
        side_effect=RuntimeError("s3 down"),
    ):
        with pytest.raises(RuntimeError, match="s3 down"):
            await onboard_custom_model_source(
                mock_kube_client,
                mock_minio_client,
                "test-namespace",
                TEST_SUBMITTER,
                _make_request(repo_id="meta-llama/Llama-3-8B", description=""),
            )

    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_called_once()
    mock_kube_client.custom_objects.delete_namespaced_custom_object.assert_called_once()


# --- onboard Hub re-verify ---


@pytest.mark.asyncio
async def test_onboard_reverifies_sha_with_hub_before_touching_k8s(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    stub_onboard_hub_reverify: dict[str, AsyncMock],
) -> None:
    """Onboard re-fetches Hub with the request's (repo_id, revision) before any
    K8s read/write so a stale or forged sha is caught at the API boundary, not
    after a partial CR write."""
    call_order: list[str] = []

    def record_hub_fetch(*_args: Any, **_kwargs: Any) -> dict:
        call_order.append("hub_fetch")
        return {"sha": _DEFAULT_REQUEST_SHA}

    stub_onboard_hub_reverify["fetch"].side_effect = record_hub_fetch

    def record_list(*_args: Any, **_kwargs: Any) -> dict:
        call_order.append("k8s_list")
        return {"items": []}

    mock_kube_client.custom_objects.list_namespaced_custom_object.side_effect = record_list

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(),
    )

    assert call_order[:2] == ["hub_fetch", "k8s_list"]
    stub_onboard_hub_reverify["fetch"].assert_called_once()
    # Hub is asked about exactly what the client claims, so the verification can
    # actually detect a mismatch — passing canonicalised values here would mask
    # the very forgery we're guarding against.
    fetch_args = stub_onboard_hub_reverify["fetch"].call_args.args
    assert fetch_args[0] == "meta-llama/Llama-3-8B"
    assert fetch_args[1] == "main"


@pytest.mark.asyncio
async def test_onboard_resolves_hf_token_and_forwards_to_hub_reverify(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    stub_onboard_hub_reverify: dict[str, AsyncMock],
) -> None:
    """When the request names an HF token secret, the re-verify Hub call must
    use that token — otherwise gated repos would 401/403 on re-verify even
    when the user supplied valid credentials."""
    stub_onboard_hub_reverify["token"].return_value = "hf_real_token"

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(hf_token_secret_name="my-hf-secret"),
    )

    stub_onboard_hub_reverify["token"].assert_called_once()
    token_call_args = stub_onboard_hub_reverify["token"].call_args.args
    assert token_call_args[1] == "test-namespace"
    assert token_call_args[2] == "my-hf-secret"
    fetch_args = stub_onboard_hub_reverify["fetch"].call_args.args
    assert fetch_args[2] == "hf_real_token"


@pytest.mark.asyncio
async def test_onboard_skips_token_fetch_when_no_secret_supplied(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    stub_onboard_hub_reverify: dict[str, AsyncMock],
) -> None:
    """A public repo onboard must not read any secret, and must call Hub
    anonymously — both for least-privilege and so the Hub 401-without-token
    message is the one users see."""
    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(hf_token_secret_name=None),
    )

    stub_onboard_hub_reverify["token"].assert_not_called()
    assert stub_onboard_hub_reverify["fetch"].call_args.args[2] is None
    mock_kube_client.core_v1.read_namespaced_secret.assert_not_called()


@pytest.mark.asyncio
async def test_onboard_s3_source_reuses_preview_validation_and_skips_hf_import_path(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    stub_onboard_hub_reverify: dict[str, AsyncMock],
) -> None:
    """S3 onboard reuses preview-grade validation and does not run HF reverify/import logic."""
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(
        return_value=MagicMock(
            metadata=MagicMock(labels={}),
            data={
                "minio-access-key": base64.b64encode(b"access-key").decode(),
                "minio-secret-key": base64.b64encode(b"secret-key").decode(),
            },
        )
    )

    with patch(
        "app.custom_models.service._build_s3_preview_response",
        return_value=MagicMock(warnings=["missing tokenizer.json"]),
    ) as preview_validation:
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(
                source_type="s3",
                repo_id="s3://my-bucket/path/to/model",
                revision="s3",
                sha="s3",
                s3_storage_name="my-s3-storage",
                hf_token_secret_name=None,
            ),
        )

    preview_validation.assert_called_once_with(
        kube_client=mock_kube_client,
        namespace="test-namespace",
        source="s3://my-bucket/path/to/model",
        storage_name="my-s3-storage",
    )
    stub_onboard_hub_reverify["fetch"].assert_not_called()
    stub_onboard_hub_reverify["token"].assert_not_called()


@pytest.mark.asyncio
async def test_onboard_s3_source_uses_s3_source_uri_and_secret_refs(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
) -> None:
    """S3 onboard keeps source URI and pulls endpoint/region from storage config."""
    mock_kube_client.core_v1.read_namespaced_config_map = AsyncMock(
        return_value=_make_s3_storage_config_map(
            bucket_url="http://minio.example:9000/my-bucket",
            region="us-east-1",
            access_key_name="minio-access-key",
            secret_key_name="minio-secret-key",
        )
    )
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(
        return_value=MagicMock(
            metadata=MagicMock(labels={}),
            data={
                "minio-access-key": base64.b64encode(b"access-key").decode(),
                "minio-secret-key": base64.b64encode(b"secret-key").decode(),
            },
        )
    )

    with patch("app.custom_models.service._build_s3_preview_response", return_value=MagicMock(warnings=[])):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(
                source_type="s3",
                repo_id="s3://my-bucket/path/to/model",
                revision="s3",
                sha="s3",
                s3_storage_name="my-s3-storage",
                hf_token_secret_name=None,
            ),
        )

    create_kwargs = mock_kube_client.custom_objects.create_namespaced_custom_object.call_args.kwargs
    body = create_kwargs["body"]
    overrides = body["spec"]["profiles"]["overrides"]
    expected_source_model_id = f"s3/{body['metadata']['name']}"
    assert overrides["aimId"] == expected_source_model_id
    assert overrides["modelId"] == expected_source_model_id
    model_source = overrides["modelSources"][0]
    assert model_source["modelId"] == expected_source_model_id
    assert model_source["sourceUri"] == "s3://my-bucket/path/to/model"
    env_by_name = {entry["name"]: entry for entry in model_source["env"]}
    assert env_by_name["AWS_ACCESS_KEY_ID"]["valueFrom"]["secretKeyRef"] == {
        "name": "my-s3-secret",
        "key": "minio-access-key",
    }
    assert env_by_name["AWS_SECRET_ACCESS_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "my-s3-secret",
        "key": "minio-secret-key",
    }
    assert env_by_name["AWS_ENDPOINT_URL"]["value"] == "http://minio.example:9000"
    assert env_by_name["AWS_DEFAULT_REGION"]["value"] == "us-east-1"


@pytest.mark.asyncio
async def test_onboard_s3_source_defaults_endpoint_to_minio_url_when_storage_omits_bucket_url(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
) -> None:
    """S3 onboard falls back to MINIO_URL when storage omits bucketUrl."""
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(
        return_value=MagicMock(
            metadata=MagicMock(labels={}),
            data={
                "minio-access-key": base64.b64encode(b"access-key").decode(),
                "minio-secret-key": base64.b64encode(b"secret-key").decode(),
            },
        )
    )

    with patch("app.custom_models.service._build_s3_preview_response", return_value=MagicMock(warnings=[])):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(
                source_type="s3",
                repo_id=f"s3://{MINIO_BUCKET}/path/to/model",
                revision="s3",
                sha="s3",
                s3_storage_name="my-s3-storage",
                hf_token_secret_name=None,
            ),
        )

    create_kwargs = mock_kube_client.custom_objects.create_namespaced_custom_object.call_args.kwargs
    body = create_kwargs["body"]
    model_source = body["spec"]["profiles"]["overrides"]["modelSources"][0]
    env_by_name = {entry["name"]: entry for entry in model_source["env"]}
    assert env_by_name["AWS_ACCESS_KEY_ID"]["valueFrom"]["secretKeyRef"] == {
        "name": "my-s3-secret",
        "key": "minio-access-key",
    }
    assert env_by_name["AWS_SECRET_ACCESS_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "my-s3-secret",
        "key": "minio-secret-key",
    }
    assert env_by_name["AWS_ENDPOINT_URL"]["value"] == MINIO_URL
    assert "AWS_DEFAULT_REGION" not in env_by_name


@pytest.mark.asyncio
async def test_onboard_s3_source_accepts_api_camelcase_secret_keys(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
) -> None:
    """S3 onboard accepts API camelCase credential keys from storage config."""
    mock_kube_client.core_v1.read_namespaced_config_map = AsyncMock(
        return_value=_make_s3_storage_config_map(
            bucket_url="http://minio.example:9000/my-bucket",
            region="us-east-1",
            access_key_name="awsAccessKeyId",
            secret_key_name="awsSecretAccessKey",
        )
    )
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(
        return_value=MagicMock(
            metadata=MagicMock(labels={}),
            data={
                "awsAccessKeyId": base64.b64encode(b"access-key").decode(),
                "awsSecretAccessKey": base64.b64encode(b"secret-key").decode(),
            },
        )
    )

    with patch("app.custom_models.service._build_s3_preview_response", return_value=MagicMock(warnings=[])):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(
                source_type="s3",
                repo_id="s3://my-bucket/path/to/model",
                revision="s3",
                sha="s3",
                s3_storage_name="my-s3-storage",
                hf_token_secret_name=None,
            ),
        )

    create_kwargs = mock_kube_client.custom_objects.create_namespaced_custom_object.call_args.kwargs
    body = create_kwargs["body"]
    model_source = body["spec"]["profiles"]["overrides"]["modelSources"][0]
    env_by_name = {entry["name"]: entry for entry in model_source["env"]}
    assert env_by_name["AWS_ACCESS_KEY_ID"]["valueFrom"]["secretKeyRef"] == {
        "name": "my-s3-secret",
        "key": "awsAccessKeyId",
    }
    assert env_by_name["AWS_SECRET_ACCESS_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "my-s3-secret",
        "key": "awsSecretAccessKey",
    }
    assert env_by_name["AWS_ENDPOINT_URL"]["value"] == "http://minio.example:9000"
    assert env_by_name["AWS_DEFAULT_REGION"]["value"] == "us-east-1"


@pytest.mark.asyncio
async def test_onboard_s3_source_aborts_when_preview_revalidation_fails(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    stub_onboard_hub_reverify: dict[str, AsyncMock],
) -> None:
    """A hard S3 revalidation error should stop onboard before any CR or manifest writes."""
    with patch(
        "app.custom_models.service._build_s3_preview_response",
        side_effect=ValidationException("S3 source 's3://my-bucket/path/to/model' does not exist."),
    ):
        with pytest.raises(ValidationException, match="does not exist"):
            await onboard_custom_model_source(
                mock_kube_client,
                mock_minio_client,
                "test-namespace",
                TEST_SUBMITTER,
                _make_request(
                    source_type="s3",
                    repo_id="s3://my-bucket/path/to/model",
                    revision="s3",
                    sha="s3",
                    s3_storage_name="my-s3-storage",
                    hf_token_secret_name=None,
                ),
            )

    stub_onboard_hub_reverify["fetch"].assert_not_called()
    stub_onboard_hub_reverify["token"].assert_not_called()
    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()
    mock_minio_client.upload_object.assert_not_called()


@pytest.mark.asyncio
async def test_onboard_rejects_when_hub_sha_differs_from_request_sha(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    stub_onboard_hub_reverify: dict[str, AsyncMock],
) -> None:
    """The named revision moved between preview and onboard (or the caller
    forged a sha). Reject as 400-mapped ValidationException naming both shas
    so the FE can prompt the user to re-preview."""
    stub_onboard_hub_reverify["fetch"].return_value = {"sha": "deadbeef_current_hub_sha"}

    with pytest.raises(ValidationException) as exc_info:
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(sha="abc123_stale_sha"),
        )

    message = str(exc_info.value)
    assert "abc123_stale_sha" in message
    assert "deadbeef_current_hub_sha" in message
    assert "Re-preview" in message

    mock_kube_client.custom_objects.list_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()
    mock_minio_client.upload_object.assert_not_called()


@pytest.mark.asyncio
async def test_onboard_rejects_when_hub_returns_no_sha(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    stub_onboard_hub_reverify: dict[str, AsyncMock],
) -> None:
    """Mirrors the preview semantics: an unpinnable Hub response is an upstream
    error, not a client error."""
    stub_onboard_hub_reverify["fetch"].return_value = {"sha": ""}

    with pytest.raises(ExternalServiceError, match="did not return a SHA"):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(),
        )

    mock_kube_client.custom_objects.list_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
async def test_onboard_propagates_hub_forbidden_unchanged(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    stub_onboard_hub_reverify: dict[str, AsyncMock],
) -> None:
    """ForbiddenException from the re-verify fetch must propagate so the global
    handler surfaces 403 — same mapping preview uses. Re-wrapping would mask
    a gated-repo failure as a generic onboard error."""
    stub_onboard_hub_reverify["fetch"].side_effect = ForbiddenException("Hub denied access")

    with pytest.raises(ForbiddenException):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(),
        )

    mock_kube_client.custom_objects.list_namespaced_custom_object.assert_not_called()


# --- preview side-effect guard ---


@pytest.mark.asyncio
async def test_preview_does_not_onboard(mock_kube_client: AsyncMock, mock_minio_client: MagicMock) -> None:
    """Preview remains read-only and does not touch k8s or S3."""
    with patch("app.custom_models.service._fetch_hub_model", return_value=HUB_RESPONSE):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace="test-namespace",
            request=PreviewRequest(source="meta-llama/Meta-Llama-3-8B-Instruct"),
        )

    assert result.display_name == "Llama 3 8B"
    mock_minio_client.upload_object.assert_not_called()
    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()


# --- speech-to-text onboarding ---


_AUDIO_BASE_MODEL = min(AUDIO_CAPABLE_BASE_REPOSITORIES)
_AUDIO_IMAGE = f"amdenterpriseai/{_AUDIO_BASE_MODEL}:1.0"
_ASR_TAGS = ["transformers", "whisper", "automatic-speech-recognition", "audio"]


def _make_base_profile(
    precision: str = "bf16", metric: str = "latency", profile_type: str = "unoptimized"
) -> AIMProfileResource:
    """Base-role AIMProfile carrying the identity axes the ASR preset reads."""
    return AIMProfileResource(
        metadata=K8sMetadata(name=f"aim-audio-base-{precision}-{metric}", namespace="test-namespace"),
        spec=AIMProfileSpec(
            aim_id="",
            accelerator_model="MI300X",
            accelerator_count=1,
            precision=precision,
            metric=metric,
            type=profile_type,
        ),
    )


async def _onboard_asr_body(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    *,
    base_profiles: list[AIMProfileResource] | None = None,
    **request_overrides: Any,
) -> dict:
    """Onboard a speech model and return the created custom AIMModel manifest."""
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    created_bodies: list[dict] = []

    def record_create(*_args: Any, body: dict, **_kwargs: Any) -> dict:
        created_bodies.append(body)
        return body

    mock_kube_client.custom_objects.create_namespaced_custom_object.side_effect = record_create

    profiles = base_profiles if base_profiles is not None else [_make_base_profile()]
    with patch("app.custom_models.service.list_base_role_profiles", return_value=profiles):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(repo_id="openai/whisper-large-v3", tags=_ASR_TAGS, image=_AUDIO_IMAGE, **request_overrides),
        )

    # The base-image AIMModel is created first, the custom model second.
    return created_bodies[-1]


async def _onboard_asr(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    **kwargs: Any,
) -> dict:
    """Onboard a speech model and return the created AIMModel's profile overrides."""
    body = await _onboard_asr_body(mock_kube_client, mock_minio_client, **kwargs)
    return body["spec"]["profiles"]["overrides"]


@pytest.mark.asyncio
async def test_onboard_speech_model_stamps_asr_engine_args(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """A speech model needs the audio prompt limit and Whisper's decoder context to serve transcriptions."""
    overrides = await _onboard_asr(mock_kube_client, mock_minio_client)

    assert overrides["engineArgs"]["limit-mm-per-prompt"] == {"audio": 1}
    assert overrides["engineArgs"]["max-model-len"] == 448


@pytest.mark.asyncio
async def test_onboard_speech_model_populates_identity_axes_from_base_profiles(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """Stamped axes must come from the base profiles being derived from, never invented:
    a value outside that matrix narrows the derivation instead of describing it."""
    overrides = await _onboard_asr(mock_kube_client, mock_minio_client)

    assert overrides["precision"] == "bf16"
    assert overrides["metric"] == "latency"
    assert overrides["type"] == "unoptimized"
    # dtype tracks the resolved precision rather than a fixed value.
    assert overrides["engineArgs"]["dtype"] == "bfloat16"


@pytest.mark.asyncio
async def test_onboard_speech_model_records_backfilled_precision_on_the_annotation(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """The CRD prunes precision from overrides, so the annotation is where it survives for the UI."""
    body = await _onboard_asr_body(mock_kube_client, mock_minio_client)

    assert body["metadata"]["annotations"][MODEL_PRECISION_ANNOTATION] == "bf16"


@pytest.mark.asyncio
async def test_onboard_speech_model_leaves_ambiguous_axis_to_the_derived_profile(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """Two base metrics give no single right answer; stamping either would narrow the derivation wrongly."""
    overrides = await _onboard_asr(
        mock_kube_client,
        mock_minio_client,
        base_profiles=[_make_base_profile(metric="latency"), _make_base_profile(metric="throughput")],
    )

    assert "metric" not in overrides
    assert overrides["precision"] == "bf16"


@pytest.mark.asyncio
async def test_onboard_speech_model_keeps_user_tuned_engine_args(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """A value the user set in the wizard must survive the preset merge."""
    overrides = await _onboard_asr(
        mock_kube_client,
        mock_minio_client,
        custom_profile={"engineArgs": {"max-model-len": 1024}},
    )

    assert overrides["engineArgs"]["max-model-len"] == 1024
    assert overrides["engineArgs"]["limit-mm-per-prompt"] == {"audio": 1}


@pytest.mark.asyncio
async def test_onboard_speech_model_rejects_base_image_without_audio_runtime(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock, stub_onboard_hub_reverify: dict[str, AsyncMock]
) -> None:
    """Rejecting here beats deploying a model that reports healthy and fails every transcription call.

    The rejection runs at the service boundary, so it leaves nothing behind: no
    base AIMModel, no Hub call. A request the API refuses must not half-onboard.
    """
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    with pytest.raises(ValidationException, match="audio runtime"):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(repo_id="openai/whisper-large-v3", tags=_ASR_TAGS, image=TEST_IMAGE),
        )

    stub_onboard_hub_reverify["fetch"].assert_not_called()
    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()
    mock_minio_client.upload_object.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("image_ref", ["registry.example.com/custom-base", "repo-only"])
async def test_onboard_speech_model_blames_the_malformed_image_not_the_audio_runtime(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock, image_ref: str
) -> None:
    """An unparseable ref is not an audio problem. Telling a user to pick an
    audio-capable image would send them hunting for a different image when the
    one they picked is malformed, so the runtime-family error still wins."""
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    with pytest.raises(ValidationException, match="does not identify a supported runtime family"):
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(repo_id="openai/whisper-large-v3", tags=_ASR_TAGS, image=image_ref),
        )

    mock_kube_client.custom_objects.create_namespaced_custom_object.assert_not_called()
    mock_minio_client.upload_object.assert_not_called()


@pytest.mark.asyncio
async def test_onboard_speech_model_surfaces_a_kubernetes_failure_resolving_axes(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """A transient K8s failure must not masquerade as "this namespace has no base
    profiles". Both yield an empty list under strict=False, but only one of them
    means the resolved axes are trustworthy."""
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    with patch(
        "app.custom_models.service.list_base_role_profiles",
        new=AsyncMock(side_effect=ExternalServiceError("kube unavailable")),
    ) as mock_list:
        with pytest.raises(ExternalServiceError):
            await onboard_custom_model_source(
                mock_kube_client,
                mock_minio_client,
                "test-namespace",
                TEST_SUBMITTER,
                _make_request(repo_id="openai/whisper-large-v3", tags=_ASR_TAGS, image=_AUDIO_IMAGE),
            )

    mock_list.assert_awaited_once()
    mock_minio_client.upload_object.assert_not_called()


@pytest.mark.asyncio
async def test_onboard_speech_model_resolves_axes_from_the_audio_base_only(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """A namespace that already onboarded a chat model also holds aim-base, and its
    base profiles carry the same role label. Reading those would pin Whisper to the
    chat image's precision — and through it a foreign dtype — so the lookup has to
    name the audio base rather than trust the role label alone."""
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    with patch(
        "app.custom_models.service.list_base_role_profiles",
        new=AsyncMock(return_value=[_make_base_profile()]),
    ) as mock_list:
        await onboard_custom_model_source(
            mock_kube_client,
            mock_minio_client,
            "test-namespace",
            TEST_SUBMITTER,
            _make_request(repo_id="openai/whisper-large-v3", tags=_ASR_TAGS, image=_AUDIO_IMAGE),
        )

    mock_list.assert_awaited_once_with(mock_kube_client, "test-namespace", model_name=_AUDIO_BASE_MODEL, strict=True)


@pytest.mark.asyncio
async def test_onboard_speech_model_leaves_axes_unset_when_no_base_profiles_exist_yet(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """The audio base is a different image from the chat base, so the first speech
    onboard into a namespace creates it and reads back nothing — aim-engine has not
    reconciled yet. Onboard still succeeds; the axes and the dtype stay unset."""
    overrides = await _onboard_asr(mock_kube_client, mock_minio_client, base_profiles=[])

    for axis in ("precision", "metric", "type"):
        assert axis not in overrides
    assert "dtype" not in overrides["engineArgs"]
    assert overrides["engineArgs"]["max-model-len"] == 448


@pytest.mark.asyncio
async def test_onboard_non_speech_model_is_untouched_by_the_asr_path(
    mock_kube_client: AsyncMock, mock_minio_client: MagicMock
) -> None:
    """A chat model must onboard exactly as before, even onto an audio-capable base."""
    mock_kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}
    mock_kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    created_bodies: list[dict] = []

    def record_create(*_args: Any, body: dict, **_kwargs: Any) -> dict:
        created_bodies.append(body)
        return body

    mock_kube_client.custom_objects.create_namespaced_custom_object.side_effect = record_create

    await onboard_custom_model_source(
        mock_kube_client,
        mock_minio_client,
        "test-namespace",
        TEST_SUBMITTER,
        _make_request(repo_id="meta-llama/Llama-3-8B", tags=["text-generation", "llama"], image=_AUDIO_IMAGE),
    )

    overrides = created_bodies[-1]["spec"]["profiles"]["overrides"]
    assert "engineArgs" not in overrides
    assert "precision" not in overrides
    assert "metric" not in overrides
