# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""TestClient tests for custom-model preview, onboard, and list endpoints.

All endpoints live on the project-scoped router in app/projects/router.py.
These tests cover HTTP-level behaviour: status codes, camelCase serialization,
project auth enforcement, and error response shapes.
"""

from unittest.mock import MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from api_common.exceptions import (
    ConflictException,
    ExternalServiceError,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app import app  # type: ignore[attr-defined]
from app.aims.crds import AIMModelSpec
from app.custom_models.enums import OnboardPhase
from app.custom_models.schemas import (
    CustomModelOnboardStatus,
    CustomModelPatchResponse,
    CustomModelResponse,
    PreviewResponse,
    WeightFile,
)
from app.dispatch.crds import K8sMetadata
from app.minio import get_minio_client
from tests.dependency_overrides import BASE_OVERRIDES, override_dependencies

PREVIEW_OVERRIDES = {**BASE_OVERRIDES}
ONBOARD_OVERRIDES = {**BASE_OVERRIDES, get_minio_client: lambda: None}

PREVIEW_URL = "/v1/projects/test-namespace/models/preview"
ONBOARD_URL = "/v1/projects/test-namespace/models/onboard"
PATCH_URL = "/v1/projects/test-namespace/models/llama-3-8b-import-12345678"
COPY_URL = "/v1/projects/test-namespace/models/source-model/copy"

PATCH_OVERRIDES = {**BASE_OVERRIDES, get_minio_client: lambda: None}

_PATCH_RESPONSE = CustomModelPatchResponse(
    name="llama-3-8b-import-12345678",
    display_name="Renamed Model",
    description="Updated description.",
    tags=["llama", "chat"],
)

_PREVIEW_RESPONSE = PreviewResponse(
    repo_id="meta-llama/Meta-Llama-3-8B-Instruct",
    revision="main",
    sha="abc123",
    display_name="Meta Llama 3 8B Instruct",
    description="A great model.",
    tags=["llama", "text-generation"],
    pipeline_tag="text-generation",
    gated=True,
    hf_token_recommended=True,
    weight_files=[
        WeightFile(path="model-00001-of-00002.safetensors", size_bytes=4_000_000_000, role="shard"),
        WeightFile(path="model-00002-of-00002.safetensors", size_bytes=4_000_000_000, role="shard"),
        WeightFile(path="config.json", size_bytes=820, role="config"),
    ],
    layout_hint="safetensors",
)

_ONBOARD_BODY = {
    "repoId": "meta-llama/Meta-Llama-3-8B-Instruct",
    "revision": "main",
    "sha": "abc123",
    "displayName": "Meta Llama 3 8B Instruct",
    "description": "A great model.",
    "image": "docker.io/amd/tinyllama:1.0.0",
}


@override_dependencies(PREVIEW_OVERRIDES)
@patch("app.projects.router.preview_model_source", return_value=_PREVIEW_RESPONSE)
def test_preview_returns_200(mock_preview) -> None:  # type: ignore[misc, no-untyped-def]
    """POST preview returns 200 and a well-formed camelCase body."""
    with TestClient(app) as client:
        response = client.post(
            PREVIEW_URL,
            json={"source": "meta-llama/Meta-Llama-3-8B-Instruct"},
        )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["sourceType"] == "huggingFace"
    assert body["repoId"] == "meta-llama/Meta-Llama-3-8B-Instruct"
    assert body["revision"] == "main"
    assert body["sha"] == "abc123"
    assert body["displayName"] == "Meta Llama 3 8B Instruct"
    assert body["gated"] is True
    assert body["hfTokenRecommended"] is True
    assert body["layoutHint"] == "safetensors"


@override_dependencies(PREVIEW_OVERRIDES)
@patch("app.projects.router.preview_model_source", return_value=_PREVIEW_RESPONSE)
def test_preview_weight_files_serialized(mock_preview) -> None:  # type: ignore[misc, no-untyped-def]
    """Weight files are serialized with camelCase field names."""
    with TestClient(app) as client:
        response = client.post(PREVIEW_URL, json={"source": "org/model"})
    body = response.json()
    weight_files = body["weightFiles"]
    assert len(weight_files) == 3
    first_shard = weight_files[0]
    assert "path" in first_shard
    assert "sizeBytes" in first_shard
    assert "role" in first_shard


@override_dependencies(PREVIEW_OVERRIDES)
@patch("app.projects.router.preview_model_source", return_value=_PREVIEW_RESPONSE)
def test_preview_with_hf_token_secret(mock_preview) -> None:  # type: ignore[misc, no-untyped-def]
    """The optional hfTokenSecretName field is accepted in the request body."""
    with TestClient(app) as client:
        response = client.post(
            PREVIEW_URL,
            json={
                "source": "org/model",
                "hfTokenSecretName": "my-hf-secret",
            },
        )
    assert response.status_code == status.HTTP_200_OK
    mock_preview.assert_called_once()
    call_request = mock_preview.call_args.kwargs["request"]
    assert call_request.hf_token_secret_name == "my-hf-secret"


@override_dependencies(PREVIEW_OVERRIDES)
@patch("app.projects.router.preview_model_source", return_value=_PREVIEW_RESPONSE)
def test_preview_accepts_s3_source_fields(mock_preview) -> None:  # type: ignore[misc, no-untyped-def]
    """S3 preview requests accept sourceType='s3' and a valid s3StorageName."""
    with TestClient(app) as client:
        response = client.post(
            PREVIEW_URL,
            json={
                "sourceType": "s3",
                "source": "s3://my-bucket/path/to/model",
                "s3StorageName": "my-s3-storage",
            },
        )
    assert response.status_code == status.HTTP_200_OK
    call_request = mock_preview.call_args.kwargs["request"]
    assert call_request.source_type == "s3"
    assert call_request.s3_storage_name == "my-s3-storage"


@override_dependencies(PREVIEW_OVERRIDES)
def test_preview_s3_source_requires_s3_storage_name() -> None:
    """sourceType='s3' without s3StorageName fails request validation."""
    with TestClient(app) as client:
        response = client.post(
            PREVIEW_URL,
            json={"sourceType": "s3", "source": "s3://my-bucket/path/to/model"},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(PREVIEW_OVERRIDES)
def test_preview_s3_source_rejects_hf_token_secret_name() -> None:
    """sourceType='s3' rejects hfTokenSecretName to avoid mixed-source payloads."""
    with TestClient(app) as client:
        response = client.post(
            PREVIEW_URL,
            json={
                "sourceType": "s3",
                "source": "s3://my-bucket/path/to/model",
                "s3StorageName": "my-s3-storage",
                "hfTokenSecretName": "my-hf-secret",
            },
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(PREVIEW_OVERRIDES)
def test_preview_hf_source_rejects_s3_storage_name() -> None:
    """sourceType='huggingFace' rejects s3StorageName to avoid mixed-source payloads."""
    with TestClient(app) as client:
        response = client.post(
            PREVIEW_URL,
            json={
                "sourceType": "huggingFace",
                "source": "org/model",
                "s3StorageName": "my-s3-storage",
            },
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(PREVIEW_OVERRIDES)
def test_preview_extra_unknown_fields_are_ignored() -> None:
    """Unknown body fields (e.g. a stale 'revision' from an old client) are ignored."""
    with patch("app.projects.router.preview_model_source", return_value=_PREVIEW_RESPONSE):
        with TestClient(app) as client:
            response = client.post(
                PREVIEW_URL,
                json={"source": "org/model", "revision": "v2.0"},
            )
    assert response.status_code == status.HTTP_200_OK


@override_dependencies(PREVIEW_OVERRIDES)
def test_preview_missing_source_returns_422() -> None:
    """Request body without 'source' field is rejected with 422."""
    with TestClient(app) as client:
        response = client.post(PREVIEW_URL, json={})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(PREVIEW_OVERRIDES)
@patch("app.projects.router.preview_model_source", return_value=_PREVIEW_RESPONSE)
def test_preview_invalid_hf_token_secret_name_returns_422(mock_preview) -> None:  # type: ignore[misc, no-untyped-def]
    """Malformed hfTokenSecretName fails request validation before service call."""
    with TestClient(app) as client:
        response = client.post(
            PREVIEW_URL,
            json={"source": "org/model", "hfTokenSecretName": "Invalid_Secret"},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    mock_preview.assert_not_called()


@override_dependencies(PREVIEW_OVERRIDES)
@patch(
    "app.projects.router.preview_model_source",
    side_effect=ValidationException("Invalid Hugging Face source 'bad'"),
)
def test_preview_invalid_source_returns_400(mock_preview) -> None:  # type: ignore[misc, no-untyped-def]
    """ValidationException from normalization maps to 400."""
    with TestClient(app) as client:
        response = client.post(PREVIEW_URL, json={"source": "bad"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@override_dependencies(PREVIEW_OVERRIDES)
@patch(
    "app.projects.router.preview_model_source",
    side_effect=NotFoundException("Secret 'x' not found"),
)
def test_preview_secret_not_found_returns_404(mock_preview) -> None:  # type: ignore[misc, no-untyped-def]
    """NotFoundException (missing secret or Hub 404) maps to 404."""
    with TestClient(app) as client:
        response = client.post(PREVIEW_URL, json={"source": "org/model", "hfTokenSecretName": "missing-secret"})
    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(PREVIEW_OVERRIDES)
@patch(
    "app.projects.router.preview_model_source",
    side_effect=ForbiddenException("Hub denied access"),
)
def test_preview_hub_auth_error_returns_403(mock_preview) -> None:  # type: ignore[misc, no-untyped-def]
    """ForbiddenException from Hub 401/403 maps to 403."""
    with TestClient(app) as client:
        response = client.post(PREVIEW_URL, json={"source": "org/gated-model"})
    assert response.status_code == status.HTTP_403_FORBIDDEN


@override_dependencies(PREVIEW_OVERRIDES)
@patch(
    "app.projects.router.preview_model_source",
    side_effect=ForbiddenException(
        "Model 'meta-llama/Meta-Llama-3-8B-Instruct' is a gated repository. "
        "Provide a Hugging Face token via 'hfTokenSecretName' to access it."
    ),
)
def test_preview_gated_repo_no_token_returns_403(mock_preview) -> None:  # type: ignore[misc, no-untyped-def]
    """Gated repo without a token maps to 403.

    HF returns 200 with gated='manual'; the service detects this and raises
    ForbiddenException before returning preview metadata.
    """
    with TestClient(app) as client:
        response = client.post(PREVIEW_URL, json={"source": "meta-llama/Meta-Llama-3-8B-Instruct"})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "hfTokenSecretName" in response.json()["detail"]


@override_dependencies(PREVIEW_OVERRIDES)
@patch(
    "app.projects.router.preview_model_source",
    side_effect=NotFoundException("Model not found on Hub"),
)
def test_preview_hub_not_found_returns_404(mock_preview) -> None:  # type: ignore[misc, no-untyped-def]
    """Hub 404 (unknown repo) maps to 404."""
    with TestClient(app) as client:
        response = client.post(PREVIEW_URL, json={"source": "org/nonexistent"})
    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(PREVIEW_OVERRIDES)
@patch(
    "app.projects.router.preview_model_source",
    side_effect=ExternalServiceError("Hub timed out"),
)
def test_preview_hub_timeout_returns_502(mock_preview) -> None:  # type: ignore[misc, no-untyped-def]
    """ExternalServiceError (Hub timeout or 5xx) maps to 502."""
    with TestClient(app) as client:
        response = client.post(PREVIEW_URL, json={"source": "org/model"})
    assert response.status_code == status.HTTP_502_BAD_GATEWAY


def test_preview_unauthenticated_returns_401() -> None:
    """Request without auth headers is rejected with 401 (no dependency overrides)."""
    with TestClient(app) as client:
        response = client.post(PREVIEW_URL, json={"source": "org/model"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@override_dependencies(ONBOARD_OVERRIDES)
@patch("app.projects.router.onboard_custom_model_source")
def test_onboard_returns_204(mock_onboard) -> None:  # type: ignore[misc, no-untyped-def]
    """POST onboard returns 204 when the service succeeds."""
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json=_ONBOARD_BODY)
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
    mock_onboard.assert_called_once()


@override_dependencies(ONBOARD_OVERRIDES)
@patch("app.projects.router.onboard_custom_model_source")
def test_onboard_accepts_custom_profile(mock_onboard) -> None:  # type: ignore[misc, no-untyped-def]
    """Optional customProfile is accepted as an opaque pass-through field."""
    body = {**_ONBOARD_BODY, "customProfile": {"precision": "fp16", "gpuCount": 1}}
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json=body)
    assert response.status_code == status.HTTP_204_NO_CONTENT
    call_request = mock_onboard.call_args.kwargs["request"]
    assert call_request.custom_profile == {"precision": "fp16", "gpuCount": 1}


@override_dependencies(ONBOARD_OVERRIDES)
@patch("app.projects.router.onboard_custom_model_source")
def test_onboard_accepts_s3_source_fields(mock_onboard) -> None:  # type: ignore[misc, no-untyped-def]
    """S3 onboarding payload accepts sourceType='s3' and s3StorageName."""
    body = {
        **_ONBOARD_BODY,
        "sourceType": "s3",
        "repoId": "s3://my-bucket/path/to/model",
        "revision": "s3",
        "sha": "s3",
        "s3StorageName": "my-s3-storage",
    }
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json=body)
    assert response.status_code == status.HTTP_204_NO_CONTENT
    call_request = mock_onboard.call_args.kwargs["request"]
    assert call_request.source_type == "s3"
    assert call_request.s3_storage_name == "my-s3-storage"


@override_dependencies(ONBOARD_OVERRIDES)
def test_onboard_s3_source_requires_s3_storage_name() -> None:
    """sourceType='s3' without s3StorageName fails request validation."""
    body = {
        **_ONBOARD_BODY,
        "sourceType": "s3",
        "repoId": "s3://my-bucket/path/to/model",
        "revision": "s3",
        "sha": "s3",
    }
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json=body)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ONBOARD_OVERRIDES)
def test_onboard_s3_source_rejects_hf_token_secret_name() -> None:
    """sourceType='s3' rejects hfTokenSecretName to avoid mixed-source payloads."""
    body = {
        **_ONBOARD_BODY,
        "sourceType": "s3",
        "repoId": "s3://my-bucket/path/to/model",
        "revision": "s3",
        "sha": "s3",
        "s3StorageName": "my-s3-storage",
        "hfTokenSecretName": "my-hf-secret",
    }
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json=body)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ONBOARD_OVERRIDES)
def test_onboard_hf_source_rejects_s3_storage_name() -> None:
    """sourceType='huggingFace' rejects s3StorageName to avoid mixed-source payloads."""
    with TestClient(app) as client:
        response = client.post(
            ONBOARD_URL,
            json={**_ONBOARD_BODY, "sourceType": "huggingFace", "s3StorageName": "my-s3-storage"},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ONBOARD_OVERRIDES)
def test_onboard_missing_image_returns_422() -> None:
    """Onboard requires a non-empty image field."""
    body = {key: value for key, value in _ONBOARD_BODY.items() if key != "image"}
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json=body)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ONBOARD_OVERRIDES)
def test_onboard_empty_image_returns_422() -> None:
    """Empty image strings fail request validation."""
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json={**_ONBOARD_BODY, "image": ""})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ONBOARD_OVERRIDES)
@patch(
    "app.projects.router.onboard_custom_model_source",
    side_effect=ValidationException("'foo' is not a valid Hugging Face repo id"),
)
def test_onboard_invalid_repo_id_returns_400(mock_onboard) -> None:  # type: ignore[misc, no-untyped-def]
    """A malformed repo_id raises ValidationException at the service boundary which
    maps to 400 via the global handler."""
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json={**_ONBOARD_BODY, "repoId": "foo"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@override_dependencies(ONBOARD_OVERRIDES)
@patch(
    "app.projects.router.onboard_custom_model_source",
    side_effect=ValidationException(
        "Submitted sha 'abc123' does not match the current Hub sha 'def456' for "
        "'org/model' at revision 'main'. Re-preview the model to refresh the pin."
    ),
)
def test_onboard_sha_mismatch_returns_400(mock_onboard) -> None:  # type: ignore[misc, no-untyped-def]
    """The Hub re-verify rejects a stale or forged sha as ValidationException,
    which the global handler surfaces as 400 with the re-preview hint."""
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json=_ONBOARD_BODY)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Re-preview" in response.json()["detail"]


@override_dependencies(ONBOARD_OVERRIDES)
@patch(
    "app.projects.router.onboard_custom_model_source",
    side_effect=ForbiddenException("Hub denied access"),
)
def test_onboard_hub_auth_error_returns_403(mock_onboard) -> None:  # type: ignore[misc, no-untyped-def]
    """Hub 401/403 during onboard re-verify maps to 403, mirroring preview."""
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json=_ONBOARD_BODY)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@override_dependencies(ONBOARD_OVERRIDES)
@patch(
    "app.projects.router.onboard_custom_model_source",
    side_effect=NotFoundException("Model not found on Hub"),
)
def test_onboard_hub_not_found_returns_404(mock_onboard) -> None:  # type: ignore[misc, no-untyped-def]
    """Hub 404 during onboard re-verify maps to 404 — same handler as a missing
    HF token secret, distinguished by the detail message."""
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json=_ONBOARD_BODY)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(ONBOARD_OVERRIDES)
@patch(
    "app.projects.router.onboard_custom_model_source",
    side_effect=ExternalServiceError("Hub timed out"),
)
def test_onboard_hub_timeout_returns_502(mock_onboard) -> None:  # type: ignore[misc, no-untyped-def]
    """Hub timeout/5xx during onboard re-verify maps to 502 just like preview."""
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json=_ONBOARD_BODY)
    assert response.status_code == status.HTTP_502_BAD_GATEWAY


@override_dependencies(ONBOARD_OVERRIDES)
@patch(
    "app.projects.router.onboard_custom_model_source",
    side_effect=ConflictException("display name in use with a different source"),
)
def test_onboard_display_name_conflict_returns_409(mock_onboard) -> None:  # type: ignore[misc, no-untyped-def]
    """A second onboard of the same display name with a different source maps to 409."""
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json=_ONBOARD_BODY)
    assert response.status_code == status.HTTP_409_CONFLICT


def test_onboard_unauthenticated_returns_401() -> None:
    """Onboard without auth headers is rejected with 401."""
    with TestClient(app) as client:
        response = client.post(ONBOARD_URL, json=_ONBOARD_BODY)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@override_dependencies(ONBOARD_OVERRIDES)
@patch("app.projects.router.copy_custom_model")
def test_copy_returns_204(mock_copy) -> None:  # type: ignore[misc, no-untyped-def]
    """POST copy returns 204 when the service succeeds."""
    with TestClient(app) as client:
        response = client.post(COPY_URL)
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
    mock_copy.assert_called_once()


@override_dependencies(ONBOARD_OVERRIDES)
@patch(
    "app.projects.router.copy_custom_model",
    side_effect=NotFoundException("Custom model not found"),
)
def test_copy_not_found_returns_404(mock_copy) -> None:  # type: ignore[misc, no-untyped-def]
    """Copying a missing model returns 404."""
    with TestClient(app) as client:
        response = client.post(COPY_URL)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_copy_unauthenticated_returns_401() -> None:
    """Copy without auth headers is rejected with 401."""
    with TestClient(app) as client:
        response = client.post(COPY_URL)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# GET /projects/{project}/models — list custom models
# ============================================================================

LIST_URL = "/v1/projects/test-namespace/models"

_NAMESPACE = "test-namespace"

_LIST_RESPONSE = [
    CustomModelResponse(
        metadata=K8sMetadata(name="llama-3-8b-import-abc12345", namespace=_NAMESPACE),
        spec=AIMModelSpec(image="docker.io/amd/llama-3-8b:1.0.0"),
        phase=CustomModelOnboardStatus(
            state=OnboardPhase.READY,
            status="Ready",
            template_ready=True,
        ),
    ),
    CustomModelResponse(
        metadata=K8sMetadata(name="mistral-7b-import-def67890", namespace=_NAMESPACE),
        spec=AIMModelSpec(image="docker.io/amd/mistral-7b:1.0.0"),
        phase=CustomModelOnboardStatus(
            state=OnboardPhase.IMPORTING,
            status="Importing",
            template_ready=False,
            artifact_phase="Importing",
        ),
    ),
]


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.list_custom_models", return_value=_LIST_RESPONSE)
def test_list_custom_models_endpoint_returns_200(mock_list: MagicMock) -> None:
    """GET /projects/{project}/models returns 200 with a data-wrapped list."""
    with TestClient(app) as client:
        response = client.get(LIST_URL)
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert "data" in body
    assert len(body["data"]) == 2
    assert body["data"][0]["metadata"]["name"] == "llama-3-8b-import-abc12345"
    assert body["data"][1]["metadata"]["name"] == "mistral-7b-import-def67890"
    mock_list.assert_called_once()


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.list_custom_models", return_value=[])
def test_list_custom_models_endpoint_returns_empty_list(mock_list: MagicMock) -> None:
    """GET /projects/{project}/models returns an empty data array when no models exist."""
    with TestClient(app) as client:
        response = client.get(LIST_URL)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"data": []}


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.list_custom_models", return_value=_LIST_RESPONSE)
def test_list_custom_models_endpoint_camel_case_fields(mock_list: MagicMock) -> None:
    """Response fields are serialized in camelCase."""
    with TestClient(app) as client:
        response = client.get(LIST_URL)
    first = response.json()["data"][0]
    assert "templateReady" in first["phase"]
    assert "artifactPhase" in first["phase"]
    assert "artifactLastError" in first["phase"]


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.list_custom_models", return_value=_LIST_RESPONSE)
def test_list_custom_models_endpoint_includes_onboard_status(mock_list: MagicMock) -> None:
    """Each item in the list carries a composed onboard status with phase."""
    with TestClient(app) as client:
        response = client.get(LIST_URL)
    items = response.json()["data"]
    assert items[0]["phase"]["state"] == "Ready"
    assert items[0]["phase"]["templateReady"] is True
    assert items[1]["phase"]["state"] == "Importing"
    assert items[1]["phase"]["artifactPhase"] == "Importing"


def test_list_custom_models_endpoint_returns_401_without_auth() -> None:
    """GET /projects/{project}/models without auth headers is rejected with 401."""
    with TestClient(app) as client:
        response = client.get(LIST_URL)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@override_dependencies(PATCH_OVERRIDES)
@patch("app.projects.router.patch_onboarded_model", return_value=_PATCH_RESPONSE)
def test_patch_display_metadata_returns_200(mock_patch) -> None:  # type: ignore[misc, no-untyped-def]
    """PATCH returns 200 and a camelCase display metadata body."""
    with TestClient(app) as client:
        response = client.patch(
            PATCH_URL,
            json={"displayName": "Renamed Model", "tags": ["llama", "chat"]},
        )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["name"] == "llama-3-8b-import-12345678"
    assert body["displayName"] == "Renamed Model"
    assert body["tags"] == ["llama", "chat"]


@override_dependencies(PATCH_OVERRIDES)
@patch(
    "app.projects.router.patch_onboarded_model",
    side_effect=ValidationException("At least one of displayName, description, or tags must be provided."),
)
def test_patch_empty_body_returns_400(mock_patch) -> None:  # type: ignore[misc, no-untyped-def]
    with TestClient(app) as client:
        response = client.patch(PATCH_URL, json={})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@override_dependencies(PATCH_OVERRIDES)
@patch(
    "app.projects.router.patch_onboarded_model",
    side_effect=NotFoundException("Custom onboarded model 'missing' not found"),
)
def test_patch_not_found_returns_404(mock_patch) -> None:  # type: ignore[misc, no-untyped-def]
    with TestClient(app) as client:
        response = client.patch(
            "/v1/projects/test-namespace/models/missing",
            json={"displayName": "New Name"},
        )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(PATCH_OVERRIDES)
@patch(
    "app.projects.router.patch_onboarded_model",
    side_effect=ConflictException("display name already in use"),
)
def test_patch_display_name_conflict_returns_409(mock_patch) -> None:  # type: ignore[misc, no-untyped-def]
    with TestClient(app) as client:
        response = client.patch(PATCH_URL, json={"displayName": "Taken Name"})
    assert response.status_code == status.HTTP_409_CONFLICT


@override_dependencies(PATCH_OVERRIDES)
@patch("app.projects.router.patch_onboarded_model", return_value=_PATCH_RESPONSE)
def test_patch_empty_display_name_returns_422(mock_patch) -> None:  # type: ignore[misc, no-untyped-def]
    with TestClient(app) as client:
        response = client.patch(PATCH_URL, json={"displayName": ""})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    mock_patch.assert_not_called()


@override_dependencies(PATCH_OVERRIDES)
@patch("app.projects.router.patch_onboarded_model", return_value=_PATCH_RESPONSE)
def test_patch_conflicting_image_refs_returns_422(mock_patch) -> None:  # type: ignore[misc, no-untyped-def]
    # The request validator rejects a customProfile.image that disagrees with the
    # top-level image before the service is ever invoked.
    with TestClient(app) as client:
        response = client.patch(
            PATCH_URL,
            json={"image": "docker.io/x:1", "customProfile": {"image": "docker.io/y:2"}},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    mock_patch.assert_not_called()


@override_dependencies(PATCH_OVERRIDES)
@patch("app.projects.router.patch_onboarded_model", return_value=_PATCH_RESPONSE)
def test_patch_runtime_profile_forwards_image_and_custom_profile(mock_patch) -> None:  # type: ignore[misc, no-untyped-def]
    """A runtime-profile edit forwards image + customProfile to the service unchanged."""
    with TestClient(app) as client:
        response = client.patch(
            PATCH_URL,
            json={"image": "docker.io/x:2", "customProfile": {"engine": "vllm"}},
        )
    assert response.status_code == status.HTTP_200_OK
    forwarded = mock_patch.call_args.kwargs["request"]
    assert forwarded.image == "docker.io/x:2"
    assert forwarded.custom_profile == {"engine": "vllm"}


def test_patch_unauthenticated_returns_401() -> None:
    with TestClient(app) as client:
        response = client.patch(PATCH_URL, json={"displayName": "New Name"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# DELETE /projects/{project}/models/{model_name} — delete custom model
# ============================================================================

DELETE_URL = "/v1/projects/test-namespace/models/llama-3-8b-import-12345678"
DELETE_OVERRIDES = {**BASE_OVERRIDES, get_minio_client: lambda: None}


@override_dependencies(DELETE_OVERRIDES)
@patch("app.projects.router.delete_onboarded_model")
def test_delete_returns_204(mock_delete) -> None:  # type: ignore[misc, no-untyped-def]
    """DELETE returns 204 with an empty body when the service succeeds."""
    with TestClient(app) as client:
        response = client.delete(DELETE_URL)
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
    mock_delete.assert_called_once()


@override_dependencies(DELETE_OVERRIDES)
@patch(
    "app.projects.router.delete_onboarded_model",
    side_effect=NotFoundException("Custom model 'missing' not found in project 'test-namespace'."),
)
def test_delete_not_found_returns_404(mock_delete) -> None:  # type: ignore[misc, no-untyped-def]
    with TestClient(app) as client:
        response = client.delete("/v1/projects/test-namespace/models/missing")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(DELETE_OVERRIDES)
@patch(
    "app.projects.router.delete_onboarded_model",
    side_effect=ConflictException(
        "Custom model 'llama-3-8b-import-12345678' cannot be deleted while 1 AIMService(s) "
        "reference it: svc-alpha. Delete those deployments first."
    ),
)
def test_delete_blocked_by_deployment_returns_409(mock_delete) -> None:  # type: ignore[misc, no-untyped-def]
    with TestClient(app) as client:
        response = client.delete(DELETE_URL)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "svc-alpha" in response.json()["detail"]


def test_delete_unauthenticated_returns_401() -> None:
    """DELETE without auth headers is rejected with 401."""
    with TestClient(app) as client:
        response = client.delete(DELETE_URL)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
