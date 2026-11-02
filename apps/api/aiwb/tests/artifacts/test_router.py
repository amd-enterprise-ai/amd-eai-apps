# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""TestClient tests for the artifact endpoints (create, list, get, delete).

These tests cover HTTP-level behaviour: status codes, camelCase serialization,
and error response shapes.
Service functions are patched so these tests exercise only the router layer.
"""

import datetime
from unittest.mock import patch
from uuid import UUID

from fastapi import status
from fastapi.testclient import TestClient

from api_common.collections import PaginationMetadata
from api_common.exceptions import (
    ConflictException,
    DeletionConflictException,
    ExternalServiceError,
    NotFoundException,
    UnhealthyException,
    ValidationException,
)
from app import app  # type: ignore[attr-defined]
from app.aims.crds import AIMArtifactResource, AIMArtifactSpec
from app.artifacts.manifest import ADAPTER_MANIFEST_FILENAME
from app.artifacts.schemas import (
    MAX_ARTIFACT_FILES,
    ArtifactDownloadResponse,
    ArtifactResponse,
    ArtifactsList,
    ArtifactStorage,
    ArtifactType,
    CreateArtifactResponse,
    DownloadInstruction,
    ReadinessState,
    UploadInstruction,
)
from app.dispatch.crds import K8sMetadata
from app.minio import get_minio_client, get_minio_client_optional, get_minio_external_client
from tests.dependency_overrides import BASE_OVERRIDES, override_dependencies

ARTIFACT_OVERRIDES = {
    **BASE_OVERRIDES,
    get_minio_client: lambda: None,
    get_minio_client_optional: lambda: None,
    get_minio_external_client: lambda: None,
}

# Stands in for a configured storage client, so a test can prove the router hands the service the
# object it resolved rather than some other value.
_MINIO_SENTINEL = object()

# Its counterpart on the external endpoint, so a route resolving both can be shown to keep them apart.
_EXTERNAL_MINIO_SENTINEL = object()

URL = "/v1/projects/test-namespace/artifacts"
GET_URL = "/v1/projects/test-namespace/artifacts/my-adapter"
DELETE_URL = "/v1/projects/test-namespace/artifacts/my-adapter"
DOWNLOAD_URL = "/v1/projects/test-namespace/artifacts/my-adapter/download"


def _raise_minio_unavailable() -> None:
    """Stands in for the strict storage dependency on a deployment where storage is unconfigured."""
    raise ExternalServiceError(
        "Object storage is not available. It may not be configured for this deployment, or its client "
        "failed to initialize at startup."
    )


def _make_adapter(
    name: str = "my-adapter",
    storage_uri: str = "s3://default-bucket/test-namespace/adapters/my-adapter/",
    readiness: ReadinessState = ReadinessState.READY,
    servable: bool | None = None,
) -> ArtifactResponse:
    """Build a response row: what storage says about the files, plus the CR that claims them.

    ``servable`` defaults to absent, which is what a listing the caller asked no deployment question
    of returns.
    """
    return ArtifactResponse(
        storage=ArtifactStorage(uri=storage_uri, readiness=readiness),
        artifact=AIMArtifactResource(
            metadata=K8sMetadata(name=name, namespace="test-namespace"),
            spec=AIMArtifactSpec(
                type="adapter",
                source_uri=storage_uri,
                model_id="org/my-adapter",
                compatible_with=["org/base-model"],
                rank=16,
            ),
        ),
        servable=servable,
    )


def _make_create_response(
    readiness: ReadinessState = ReadinessState.READY,
    uploads: list[UploadInstruction] | None = None,
) -> CreateArtifactResponse:
    """The created adapter in the flat shape the endpoint returns: a list row plus its upload URLs."""
    row = _make_adapter(name="adapter-abcd1234", readiness=readiness)
    return CreateArtifactResponse(
        storage=row.storage,
        artifact=row.artifact,
        uploads=uploads or [],
    )


_EXPIRES_AT = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)

_UPLOAD_RESPONSE = _make_create_response(
    readiness=ReadinessState.NOT_READY,
    uploads=[
        UploadInstruction(
            path="adapter_config.json",
            url="https://minio.example.com/presigned-url-1",
            expires_at=_EXPIRES_AT,
        ),
        UploadInstruction(
            path="adapter_model.safetensors",
            url="https://minio.example.com/presigned-url-2",
            expires_at=_EXPIRES_AT,
        ),
    ],
)

_S3_SOURCE_RESPONSE = _make_create_response()

_VALID_BODY = {
    "type": "adapter",
    "source": {"type": "upload"},
    "modelId": "org/base-model",
    "compatibleWith": ["org/base-model"],
    "files": ["adapter_config.json", "adapter_model.safetensors"],
}

_S3_BODY = {
    "type": "adapter",
    "source": {"type": "s3", "uri": "s3://test-bucket/adapters/my-adapter/"},
    "modelId": "org/base-model",
    "compatibleWith": ["org/base-model"],
}


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.create_adapter_artifact", return_value=_UPLOAD_RESPONSE)
def test_create_artifact_returns_201(mock_create) -> None:  # type: ignore[misc, no-untyped-def]
    """POST with valid upload source returns 201 and a well-formed camelCase body."""
    with TestClient(app) as client:
        response = client.post(URL, json=_VALID_BODY)
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert "storage" in body
    assert "uploads" in body
    assert len(body["uploads"]) == 2


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.create_adapter_artifact", return_value=_UPLOAD_RESPONSE)
def test_create_artifact_camelcase_response(mock_create) -> None:  # type: ignore[misc, no-untyped-def]
    """Response uses camelCase field names."""
    with TestClient(app) as client:
        response = client.post(URL, json=_VALID_BODY)
    body = response.json()
    assert body["storage"]["uri"] == "s3://default-bucket/test-namespace/adapters/my-adapter/"
    assert body["artifact"]["spec"]["sourceUri"] == "s3://default-bucket/test-namespace/adapters/my-adapter/"
    assert body["artifact"]["spec"]["modelId"] == "org/my-adapter"
    assert body["artifact"]["spec"]["compatibleWith"] == ["org/base-model"]
    upload = body["uploads"][0]
    assert "expiresAt" in upload
    assert upload["method"] == "PUT"


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.create_adapter_artifact", return_value=_UPLOAD_RESPONSE)
def test_create_artifact_returns_the_list_item_shape(mock_create) -> None:  # type: ignore[misc, no-untyped-def]
    """The created adapter carries the list row's own fields at the top level, next to `uploads`, so
    a client can drop it straight into the collection it is already rendering."""
    with TestClient(app) as client:
        response = client.post(URL, json=_VALID_BODY)
    body = response.json()
    assert body.keys() == {"storage", "artifact", "uploads", "servable"}
    assert body["storage"]["readiness"] == "NotReady"
    # A create names no deployment, so the row carries no verdict rather than a negative one.
    assert body["servable"] is None


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_missing_required_fields_returns_422() -> None:
    """POST without required fields returns 422."""
    with TestClient(app) as client:
        response = client.post(
            URL,
            json={
                "type": "adapter",
                "source": {"type": "upload"},
                # missing modelId and compatibleWith
                "files": ["adapter_config.json"],
            },
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_upload_omitted_files_returns_422() -> None:
    """POST with upload source but no files field returns 422 — files are required for uploads."""
    body = {k: v for k, v in _VALID_BODY.items() if k != "files"}
    with TestClient(app) as client:
        response = client.post(URL, json=body)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_upload_empty_files_returns_422() -> None:
    """POST with upload source and files=[] returns 422 — files must be non-empty for uploads."""
    with TestClient(app) as client:
        response = client.post(URL, json={**_VALID_BODY, "files": []})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_traversal_file_path_returns_422() -> None:
    """POST with a file path escaping the prefix returns 422 — keys are built as
    f"{prefix}{file_path}" against a bucket shared by every namespace, so a '..'
    segment would grant write access into another project's storage."""
    with TestClient(app) as client:
        response = client.post(
            URL,
            json={**_VALID_BODY, "files": ["../../other-project/adapters/x/adapter_config.json"]},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_current_directory_file_path_returns_422() -> None:
    """POST with a './' file path returns 422 — the segment resolves away, and a key holding one is
    refused on download, so accepting it would register an artifact that cannot be handed back."""
    with TestClient(app) as client:
        response = client.post(
            URL,
            json={**_VALID_BODY, "files": ["adapter_config.json", "adapter_model.safetensors", "./config.json"]},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_interior_current_directory_file_path_returns_422() -> None:
    """The segment resolves away wherever it sits, so a nested './' is refused on the way in for the
    same reason a leading one is."""
    with TestClient(app) as client:
        response = client.post(
            URL,
            json={
                **_VALID_BODY,
                "files": ["adapter_config.json", "adapter_model.safetensors", "checkpoint-500/./optimizer.pt"],
            },
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_windows_drive_qualified_file_path_returns_422() -> None:
    """POST with a drive-qualified file path returns 422 — on Windows, joining a destination
    directory to a drive-qualified path discards that directory, the same escape a POSIX absolute
    path is already refused for."""
    with TestClient(app) as client:
        response = client.post(
            URL,
            json={
                **_VALID_BODY,
                "files": ["adapter_config.json", "adapter_model.safetensors", "C:/outside/file.bin"],
            },
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_drive_relative_file_path_returns_422() -> None:
    """A drive designator followed by a name is drive-relative, not a bare designator: joining it to
    a destination directory discards that directory just as 'C:' alone does, so the whole
    drive-qualified opening is refused rather than only the designator on its own."""
    with TestClient(app) as client:
        response = client.post(
            URL,
            json={
                **_VALID_BODY,
                "files": ["adapter_config.json", "adapter_model.safetensors", "C:outside/file.bin"],
            },
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_lowercase_drive_relative_file_path_returns_422() -> None:
    """Drive letters are case-insensitive on Windows, so a lowercase one escapes exactly as an
    uppercase one does."""
    with TestClient(app) as client:
        response = client.post(
            URL,
            json={**_VALID_BODY, "files": ["adapter_config.json", "adapter_model.safetensors", "c:evil.bin"]},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_backslash_traversal_file_path_returns_422() -> None:
    """A backslash is a separator on Windows, so a segment holding one is several components there —
    components this rule never sees, and which can traverse out of the destination."""
    with TestClient(app) as client:
        response = client.post(
            URL,
            json={
                **_VALID_BODY,
                "files": ["adapter_config.json", "adapter_model.safetensors", "checkpoint-500\\..\\..\\stolen.bin"],
            },
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_backslash_rooted_file_path_returns_422() -> None:
    """A leading backslash roots the path at the destination's drive on Windows, discarding the rest
    of the destination — the same escape a leading '/' is already refused for."""
    with TestClient(app) as client:
        response = client.post(
            URL,
            json={**_VALID_BODY, "files": ["adapter_config.json", "adapter_model.safetensors", "\\outside\\file.bin"]},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_path_with_non_drive_colon_segment_is_accepted() -> None:
    """A colon that does not sit alone in the first segment is not a drive designator, so it is
    accepted — both nested in a path and as a multi-character first segment."""
    with (
        TestClient(app) as client,
        patch("app.artifacts.router.create_adapter_artifact", return_value=_UPLOAD_RESPONSE),
    ):
        response = client.post(
            URL,
            json={
                **_VALID_BODY,
                "files": [
                    "adapter_config.json",
                    "adapter_model.safetensors",
                    "weights/a:b/file.bin",
                    "CC:/file.bin",
                ],
            },
        )
    assert response.status_code == status.HTTP_201_CREATED


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_nested_optional_file_alongside_root_required_files_accepted() -> None:
    """POST with the required PEFT files at the prefix root, plus an extra file nested under a
    subdirectory, is accepted — nesting is only disallowed for the required files themselves."""
    with (
        TestClient(app) as client,
        patch("app.artifacts.router.create_adapter_artifact", return_value=_UPLOAD_RESPONSE),
    ):
        response = client.post(
            URL,
            json={
                **_VALID_BODY,
                "files": ["adapter_config.json", "adapter_model.safetensors", "subdir/extra_file.json"],
            },
        )
    assert response.status_code == status.HTTP_201_CREATED


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_nested_required_file_returns_422() -> None:
    """A required PEFT file nested under a subdirectory returns 422 — readiness stats and
    aim-engine both read required files at the prefix root, so a nested one could never be found
    and the artifact could never become Ready."""
    with TestClient(app) as client:
        response = client.post(
            URL,
            json={**_VALID_BODY, "files": ["subdir/adapter_config.json", "adapter_model.safetensors"]},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_declaring_every_file_it_may_plus_the_manifest_returns_201() -> None:
    """A download hands back the caller's full complement of files with AIWB's manifest on top, and
    an export is only an export if what it hands over can be handed in again. Counting that manifest
    against the same cap the download exempts it from would refuse the largest artifact this API can
    produce, at the one moment the caller has no way to know which entry to drop."""
    files = [
        "adapter_config.json",
        "adapter_model.safetensors",
        *(f"shard-{i}.bin" for i in range(MAX_ARTIFACT_FILES - 2)),
        ADAPTER_MANIFEST_FILENAME,
    ]
    assert len(files) == MAX_ARTIFACT_FILES + 1
    with (
        TestClient(app) as client,
        patch("app.artifacts.router.create_adapter_artifact", return_value=_UPLOAD_RESPONSE),
    ):
        response = client.post(URL, json={**_VALID_BODY, "files": files})
    assert response.status_code == status.HTTP_201_CREATED


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_declaring_more_files_than_one_upload_covers_returns_422() -> None:
    """Exempting the manifest does not raise what a caller may declare: one file of their own past
    the cap is refused whether or not a manifest is listed beside it. Each declared file costs a
    signing call, which is what the cap is there to bound."""
    files = [
        "adapter_config.json",
        "adapter_model.safetensors",
        *(f"shard-{i}.bin" for i in range(MAX_ARTIFACT_FILES - 1)),
    ]
    with TestClient(app) as client:
        response = client.post(URL, json={**_VALID_BODY, "files": files})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "files one upload covers" in response.json()["detail"][0]["msg"]


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_counts_a_manifest_nested_below_the_prefix_as_a_file() -> None:
    """Only the one root key AIWB writes is exempt, matching what the download side skips. A copy
    under a subdirectory is a file of the caller's, and exempting it too would let the cap be evaded
    a directory at a time."""
    files = [
        "adapter_config.json",
        "adapter_model.safetensors",
        *(f"shard-{i}.bin" for i in range(MAX_ARTIFACT_FILES - 2)),
        f"checkpoint-500/{ADAPTER_MANIFEST_FILENAME}",
    ]
    with TestClient(app) as client:
        response = client.post(URL, json={**_VALID_BODY, "files": files})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "files one upload covers" in response.json()["detail"][0]["msg"]


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_repeating_the_manifest_does_not_unbound_the_list() -> None:
    """The exemption reads a list the way the download side reads storage, and the two differ in
    kind: storage holds one object per key, so a download meets at most one manifest, while a
    declaration may name it as often as the caller likes. Without a bound on the list itself, a
    declaration of nothing but manifests counts as no files at all and is accepted at any length."""
    files = ["adapter_config.json", "adapter_model.safetensors", *([ADAPTER_MANIFEST_FILENAME] * 10_000)]
    with TestClient(app) as client:
        response = client.post(URL, json={**_VALID_BODY, "files": files})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_cannot_spend_a_second_manifest_entry_on_another_file() -> None:
    """One root manifest is exempt because one is all a download can hand back. A second entry buys
    no room: the caller's own files still stop at the cap, and the list stops one past it."""
    files = [
        "adapter_config.json",
        "adapter_model.safetensors",
        *(f"shard-{i}.bin" for i in range(MAX_ARTIFACT_FILES - 2)),
        ADAPTER_MANIFEST_FILENAME,
        ADAPTER_MANIFEST_FILENAME,
    ]
    with TestClient(app) as client:
        response = client.post(URL, json={**_VALID_BODY, "files": files})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_unprefixed_compatible_with_returns_422() -> None:
    """A bare model name has no org prefix, which the AIMArtifact CRD's own pattern rejects. Caught
    here so the caller gets a field-level 422 naming the value rather than an API-server failure."""
    with TestClient(app) as client:
        response = client.post(URL, json={**_VALID_BODY, "compatibleWith": ["gemma-3-1b"]})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_duplicate_compatible_with_returns_422() -> None:
    """spec.compatibleWith is a set on the CRD, so a repeated entry is refused. Rejected at the edge
    where the response can name the duplicate."""
    with TestClient(app) as client:
        response = client.post(URL, json={**_VALID_BODY, "compatibleWith": ["org/base-model", "org/base-model"]})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_invalid_source_type_returns_422() -> None:
    """POST with invalid source.type returns 422."""
    with TestClient(app) as client:
        response = client.post(
            URL,
            json={**_VALID_BODY, "source": {"type": "hf"}},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
@patch(
    "app.artifacts.router.create_adapter_artifact",
    side_effect=ConflictException("AIMArtifact already exists"),
)
def test_create_artifact_conflict_returns_409(mock_create) -> None:  # type: ignore[misc, no-untyped-def]
    """When K8s returns 409 the endpoint returns 409."""
    with TestClient(app) as client:
        response = client.post(URL, json=_VALID_BODY)
    assert response.status_code == status.HTTP_409_CONFLICT


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_empty_compatible_with_returns_422() -> None:
    """An adapter that declares no compatible base model could never be attached to one, so an empty
    list is rejected rather than stored."""
    body = {**_VALID_BODY, "compatibleWith": []}
    with TestClient(app) as client:
        response = client.post(URL, json=body)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.create_adapter_artifact", return_value=_UPLOAD_RESPONSE)
def test_create_artifact_with_rank(mock_create) -> None:  # type: ignore[misc, no-untyped-def]
    """POST with optional rank field is accepted."""
    body = {**_VALID_BODY, "rank": 16}
    with TestClient(app) as client:
        response = client.post(URL, json=body)
    assert response.status_code == status.HTTP_201_CREATED
    mock_create.assert_called_once()
    call_request = mock_create.call_args.kwargs["request"]
    assert call_request.rank == 16


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.create_adapter_artifact", return_value=_UPLOAD_RESPONSE)
def test_create_artifact_upload_source_returns_presigned_urls(mock_create) -> None:  # type: ignore[misc, no-untyped-def]
    """Upload source returns presigned PUT URLs for declared files."""
    with TestClient(app) as client:
        response = client.post(URL, json=_VALID_BODY)
    body = response.json()
    assert body["uploads"]
    for upload in body["uploads"]:
        assert upload["url"].startswith("https://")
        assert upload["method"] == "PUT"


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.create_adapter_artifact", return_value=_S3_SOURCE_RESPONSE)
def test_create_artifact_s3_source_returns_201_no_uploads(mock_create) -> None:  # type: ignore[misc, no-untyped-def]
    """POST with S3 source returns 201 with no presigned upload URLs."""
    with TestClient(app) as client:
        response = client.post(URL, json=_S3_BODY)
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["storage"]["readiness"] == "Ready"
    assert body["uploads"] == []


@override_dependencies(ARTIFACT_OVERRIDES)
@patch(
    "app.artifacts.router.create_adapter_artifact",
    side_effect=ValidationException("Required LoRA files not found"),
)
def test_create_artifact_s3_source_missing_files_returns_400(mock_create) -> None:  # type: ignore[misc, no-untyped-def]
    """When required LoRA files are missing at S3 source, endpoint returns 400."""
    with TestClient(app) as client:
        response = client.post(URL, json=_S3_BODY)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@override_dependencies(ARTIFACT_OVERRIDES)
@patch(
    "app.artifacts.router.create_adapter_artifact",
    side_effect=ExternalServiceError("Failed to create AIMArtifact 'my-adapter' in namespace 'test-namespace'"),
)
def test_create_artifact_cluster_failure_returns_502(mock_create) -> None:  # type: ignore[misc, no-untyped-def]
    """A cluster fault while creating the AIMArtifact surfaces as 502, not a generic 500."""
    with TestClient(app) as client:
        response = client.post(URL, json=_VALID_BODY)
    assert response.status_code == status.HTTP_502_BAD_GATEWAY


@override_dependencies({**ARTIFACT_OVERRIDES, get_minio_client: _raise_minio_unavailable})
def test_create_artifact_requires_configured_storage() -> None:
    """Create allocates a prefix and signs upload URLs, so it takes the strict dependency: on a
    deployment without storage it reports the same 502 the download does, naming the cause."""
    with TestClient(app) as client:
        response = client.post(URL, json=_VALID_BODY)
    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert "Object storage is not available" in response.json()["detail"]


@override_dependencies(ARTIFACT_OVERRIDES)
@patch(
    "app.artifacts.router.create_adapter_artifact",
    side_effect=UnhealthyException("Object storage endpoint is not reachable from outside the cluster"),
)
def test_create_artifact_unusable_storage_endpoint_returns_503(mock_create) -> None:  # type: ignore[misc, no-untyped-def]
    """An install the caller cannot fix by changing the request surfaces as 503, not a generic 500,
    so it is not confused with the 400s that do invite a corrected retry."""
    with TestClient(app) as client:
        response = client.post(URL, json=_VALID_BODY)
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@override_dependencies(ARTIFACT_OVERRIDES)
def test_create_artifact_s3_source_missing_uri_returns_422() -> None:
    """POST with S3 source but missing uri returns 422."""
    with TestClient(app) as client:
        response = client.post(
            URL,
            json={**_S3_BODY, "source": {"type": "s3"}},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def _make_list(adapters: list[ArtifactResponse], page: int = 1, page_size: int = 10) -> ArtifactsList:
    return ArtifactsList(
        data=adapters,
        pagination=PaginationMetadata(page=page, page_size=page_size, total=len(adapters)),
    )


# ---------------------------------------------------------------------------
# List adapters
# ---------------------------------------------------------------------------


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.list_project_adapter_artifacts", return_value=_make_list([_make_adapter()]))
def test_list_artifacts_returns_200(mock_list) -> None:  # type: ignore[misc, no-untyped-def]
    """GET list returns 200 and a well-formed paginated camelCase envelope."""
    with TestClient(app) as client:
        response = client.get(URL)
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["pagination"] == {"page": 1, "pageSize": 10, "total": 1}


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.list_project_adapter_artifacts", return_value=_make_list([_make_adapter()]))
def test_list_artifacts_item_camelcase(mock_list) -> None:  # type: ignore[misc, no-untyped-def]
    """An item is two halves in camelCase: what storage says, and the CR verbatim."""
    with TestClient(app) as client:
        response = client.get(URL)
    item = response.json()["data"][0]
    assert item.keys() == {"storage", "artifact", "servable"}
    assert item["storage"]["readiness"] == "Ready"
    assert item["servable"] is None
    assert item["storage"]["uri"] == "s3://default-bucket/test-namespace/adapters/my-adapter/"
    assert item["artifact"]["metadata"]["name"] == "my-adapter"
    assert item["artifact"]["spec"]["sourceUri"] == item["storage"]["uri"]
    assert item["artifact"]["spec"]["compatibleWith"] == ["org/base-model"]


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.list_project_adapter_artifacts", return_value=_make_list([]))
def test_list_artifacts_empty_returns_200(mock_list) -> None:  # type: ignore[misc, no-untyped-def]
    """List endpoint returns 200 with an empty data array when no artifacts exist."""
    with TestClient(app) as client:
        response = client.get(URL)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"] == []


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.list_project_adapter_artifacts", return_value=_make_list([]))
def test_list_artifacts_default_query_forwarded(mock_list) -> None:  # type: ignore[misc, no-untyped-def]
    """With no query params the service receives the pagination defaults and no filters."""
    with TestClient(app) as client:
        client.get(URL)
    query = mock_list.call_args.kwargs["query"]
    assert (query.page, query.page_size) == (1, 10)
    assert query.type is None
    assert query.readiness is None
    assert query.servable_by is None


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.list_project_adapter_artifacts", return_value=_make_list([]))
def test_list_artifacts_query_params_forwarded(mock_list) -> None:  # type: ignore[misc, no-untyped-def]
    """?page and ?pageSize are parsed and forwarded to the service."""
    with TestClient(app) as client:
        client.get(URL, params={"page": 2, "pageSize": 5})
    query = mock_list.call_args.kwargs["query"]
    assert (query.page, query.page_size) == (2, 5)


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.list_project_adapter_artifacts", return_value=_make_list([]))
def test_list_artifacts_readiness_filter_forwarded(mock_list) -> None:  # type: ignore[misc, no-untyped-def]
    """?readiness=Ready reaches the service as a parsed enum list."""
    with TestClient(app) as client:
        client.get(URL, params={"readiness": "Ready"})
    query = mock_list.call_args.kwargs["query"]
    assert query.readiness == [ReadinessState.READY]


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.list_project_adapter_artifacts", return_value=_make_list([]))
def test_list_artifacts_type_filter_forwarded(mock_list) -> None:  # type: ignore[misc, no-untyped-def]
    """?type=adapter reaches the service as a parsed enum list."""
    with TestClient(app) as client:
        client.get(URL, params={"type": "adapter"})
    query = mock_list.call_args.kwargs["query"]
    assert query.type == [ArtifactType.ADAPTER]


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.list_project_adapter_artifacts", return_value=_make_list([]))
def test_list_artifacts_servable_by_forwarded(mock_list) -> None:  # type: ignore[misc, no-untyped-def]
    """?servableBy reaches the service as a parsed id, so a deployment is named the same way the
    rest of the API names one rather than as free text the service would have to interpret."""
    with TestClient(app) as client:
        client.get(URL, params={"servableBy": "11111111-2222-3333-4444-555555555555"})
    query = mock_list.call_args.kwargs["query"]
    assert query.servable_by == UUID("11111111-2222-3333-4444-555555555555")


@override_dependencies(ARTIFACT_OVERRIDES)
def test_list_artifacts_non_uuid_servable_by_returns_422() -> None:
    """A deployment reference that is not an id is rejected at the query boundary, rather than
    reaching the service and silently resolving to no deployment at all."""
    with TestClient(app) as client:
        response = client.get(URL, params={"servableBy": "not-a-deployment-id"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
@patch(
    "app.artifacts.router.list_project_adapter_artifacts",
    return_value=_make_list(
        [
            _make_adapter(name="servable-one", servable=True),
            _make_adapter(name="unservable-one", servable=False),
            _make_adapter(name="unevaluated-one"),
        ]
    ),
)
def test_list_artifacts_servable_verdict_round_trips(mock_list) -> None:  # type: ignore[misc, no-untyped-def]
    """All three verdicts reach the client distinctly: an unevaluated row serializes as null rather
    than collapsing into the negative one a client would render as "cannot serve"."""
    with TestClient(app) as client:
        response = client.get(URL)
    assert [item["servable"] for item in response.json()["data"]] == [True, False, None]


@override_dependencies(ARTIFACT_OVERRIDES)
def test_list_artifacts_unexposed_type_returns_422() -> None:
    """A CRD type this collection does not expose is rejected rather than quietly returning nothing:
    the delete guard and the readiness check are adapter-specific, so widening is a deliberate act."""
    with TestClient(app) as client:
        response = client.get(URL, params={"type": "model"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_list_artifacts_unknown_readiness_value_returns_422() -> None:
    """A value outside the enum is rejected at the query boundary rather than silently ignored."""
    with TestClient(app) as client:
        response = client.get(URL, params={"readiness": "Stale"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_list_artifacts_over_long_readiness_filter_returns_422() -> None:
    """The repeatable filter is capped at its own enum size, so a caller cannot inflate the list
    past the number of states that exist."""
    with TestClient(app) as client:
        response = client.get(URL, params=[("readiness", "Ready")] * (len(ReadinessState) + 1))
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(ARTIFACT_OVERRIDES)
def test_list_artifacts_page_size_over_cap_returns_422() -> None:
    """pageSize above the 100 cap is rejected at the query boundary."""
    with TestClient(app) as client:
        response = client.get(URL, params={"pageSize": 500})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies({**ARTIFACT_OVERRIDES, get_minio_client: _raise_minio_unavailable})
@patch("app.artifacts.router.list_project_adapter_artifacts", return_value=_make_list([]))
def test_list_artifacts_unaffected_by_the_strict_minio_dependency(mock_list) -> None:  # type: ignore[misc, no-untyped-def]
    """List uses the optional Minio dependency, not the one create requires — an unconfigured
    Minio client degrades the readiness signal rather than failing the whole request."""
    with TestClient(app) as client:
        response = client.get(URL)
    assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Get single artifact
# ---------------------------------------------------------------------------


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.get_project_adapter_artifact", return_value=_make_adapter())
def test_get_artifact_returns_200(mock_get) -> None:  # type: ignore[misc, no-untyped-def]
    """GET single artifact returns 200 in the same shape the list returns."""
    with TestClient(app) as client:
        response = client.get(GET_URL)
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["artifact"]["metadata"]["name"] == "my-adapter"
    assert body["storage"]["readiness"] == "Ready"


@override_dependencies(ARTIFACT_OVERRIDES)
@patch(
    "app.artifacts.router.get_project_adapter_artifact",
    side_effect=NotFoundException("Artifact 'my-adapter' not found in namespace 'test-namespace'"),
)
def test_get_artifact_not_found_returns_404(mock_get) -> None:  # type: ignore[misc, no-untyped-def]
    """NotFoundException from the service maps to 404."""
    with TestClient(app) as client:
        response = client.get(GET_URL)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(ARTIFACT_OVERRIDES)
def test_get_artifact_invalid_name_returns_422() -> None:
    """A name violating the DNS-label pattern is rejected before the service is reached."""
    with TestClient(app) as client:
        response = client.get("/v1/projects/test-namespace/artifacts/Invalid_Name!")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies({**ARTIFACT_OVERRIDES, get_minio_client: _raise_minio_unavailable})
@patch("app.artifacts.router.get_project_adapter_artifact", return_value=_make_adapter())
def test_get_artifact_unaffected_by_the_strict_minio_dependency(mock_get) -> None:  # type: ignore[misc, no-untyped-def]
    """Get uses the optional Minio dependency, not the one create requires — an unconfigured
    Minio client degrades the readiness signal rather than failing the whole request."""
    with TestClient(app) as client:
        response = client.get(GET_URL)
    assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Delete artifact
# ---------------------------------------------------------------------------


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.delete_project_adapter_artifact", return_value=True)
def test_delete_artifact_returns_202_when_deleted(mock_delete) -> None:  # type: ignore[misc, no-untyped-def]
    """Service returning True (artifact existed and was deleted) maps to 202."""
    with TestClient(app) as client:
        response = client.delete(DELETE_URL)
    assert response.status_code == status.HTTP_202_ACCEPTED


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.delete_project_adapter_artifact", return_value=False)
def test_delete_artifact_returns_204_when_already_missing(mock_delete) -> None:  # type: ignore[misc, no-untyped-def]
    """Service returning False (artifact already absent) maps to 204 No Content."""
    with TestClient(app) as client:
        response = client.delete(DELETE_URL)
    assert response.status_code == status.HTTP_204_NO_CONTENT


@override_dependencies(ARTIFACT_OVERRIDES)
@patch(
    "app.artifacts.router.delete_project_adapter_artifact",
    side_effect=DeletionConflictException("Artifact 'my-adapter' is referenced by AIMService(s): my-service"),
)
def test_delete_artifact_conflict_returns_409(mock_delete) -> None:  # type: ignore[misc, no-untyped-def]
    """A blocking AIMService reference (DeletionConflictException) maps to 409."""
    with TestClient(app) as client:
        response = client.delete(DELETE_URL)
    assert response.status_code == status.HTTP_409_CONFLICT


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.delete_project_adapter_artifact", return_value=False)
def test_delete_artifact_defaults_to_no_force(mock_delete) -> None:  # type: ignore[misc, no-untyped-def]
    """Omitting the flag keeps the reference guard in force."""
    with TestClient(app) as client:
        client.delete(DELETE_URL)
    assert mock_delete.await_args.kwargs["force"] is False


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.delete_project_adapter_artifact", return_value=True)
def test_delete_artifact_forwards_force_flag(mock_delete) -> None:  # type: ignore[misc, no-untyped-def]
    """force=true on the query string reaches the service as force."""
    with TestClient(app) as client:
        response = client.delete(f"{DELETE_URL}?force=true")
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert mock_delete.await_args.kwargs["force"] is True


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.delete_project_adapter_artifact", return_value=True)
def test_delete_artifact_force_false_is_honoured(mock_delete) -> None:  # type: ignore[misc, no-untyped-def]
    """An explicit force=false is not mistaken for the flag being present."""
    with TestClient(app) as client:
        client.delete(f"{DELETE_URL}?force=false")
    assert mock_delete.await_args.kwargs["force"] is False


@override_dependencies(ARTIFACT_OVERRIDES)
def test_delete_artifact_non_boolean_force_returns_422() -> None:
    """A non-boolean force is a clean 422 rather than a silently ignored value."""
    with TestClient(app) as client:
        response = client.delete(f"{DELETE_URL}?force=maybe")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies({**ARTIFACT_OVERRIDES, get_minio_client_optional: lambda: _MINIO_SENTINEL})
@patch("app.artifacts.router.delete_project_adapter_artifact", return_value=True)
def test_delete_artifact_forwards_the_storage_client(mock_delete) -> None:  # type: ignore[misc, no-untyped-def]
    """The delete reclaims storage, so it has to be handed the client that can reach it."""
    with TestClient(app) as client:
        client.delete(DELETE_URL)
    assert mock_delete.await_args.kwargs["minio_client"] is _MINIO_SENTINEL


@override_dependencies(ARTIFACT_OVERRIDES)
@patch(
    "app.artifacts.router.delete_project_adapter_artifact",
    side_effect=ExternalServiceError("Artifact 'my-adapter' owns weights that cannot be reclaimed"),
)
def test_delete_artifact_storage_failure_returns_502(mock_delete) -> None:  # type: ignore[misc, no-untyped-def]
    """A cleanup the service could not complete surfaces as 502, not a successful delete."""
    with TestClient(app) as client:
        response = client.delete(DELETE_URL)
    assert response.status_code == status.HTTP_502_BAD_GATEWAY


# ---------------------------------------------------------------------------
# Download an artifact
# ---------------------------------------------------------------------------

_LINK_EXPIRY = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)


def _make_download_response() -> ArtifactDownloadResponse:
    """A download as the service returns it: a link per file, and when they stop working."""
    return ArtifactDownloadResponse(
        files=[
            DownloadInstruction(
                path="adapter_config.json",
                url="https://storage.example.com/presigned",
                size_bytes=1024,
            )
        ],
        expires_at=_LINK_EXPIRY,
    )


@override_dependencies(ARTIFACT_OVERRIDES)
@patch("app.artifacts.router.download_project_artifact", return_value=_make_download_response())
def test_download_artifact_returns_200(mock_download) -> None:  # type: ignore[misc, no-untyped-def]
    """The response carries one link per file, in camelCase, and describes nothing else."""
    with TestClient(app) as client:
        response = client.get(DOWNLOAD_URL)
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert set(body) == {"files", "expiresAt"}
    assert body["files"][0]["method"] == "GET"
    assert body["files"][0]["path"] == "adapter_config.json"
    assert body["files"][0]["sizeBytes"] == 1024
    # One deadline covers the batch, so a per-file copy of it would be redundancy posing as precision.
    assert "expiresAt" not in body["files"][0]
    assert body["expiresAt"]
    # The links are credentials that work until they expire, so nothing between here and the caller
    # may keep a copy of them to serve again.
    assert response.headers["cache-control"] == "no-store"


@override_dependencies(ARTIFACT_OVERRIDES)
@patch(
    "app.artifacts.router.download_project_artifact",
    side_effect=NotFoundException("Artifact 'my-adapter' not found in namespace 'test-namespace'"),
)
def test_download_artifact_not_found_returns_404(mock_download) -> None:  # type: ignore[misc, no-untyped-def]
    """NotFoundException from the service maps to 404."""
    with TestClient(app) as client:
        response = client.get(DOWNLOAD_URL)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(ARTIFACT_OVERRIDES)
@patch(
    "app.artifacts.router.download_project_artifact",
    side_effect=ConflictException("Artifact 'my-adapter' cannot be downloaded: its weights are not present"),
)
def test_download_artifact_without_weights_returns_409(mock_download) -> None:  # type: ignore[misc, no-untyped-def]
    """An artifact whose files are not usable as it stands is a conflict, not an empty download."""
    with TestClient(app) as client:
        response = client.get(DOWNLOAD_URL)
    assert response.status_code == status.HTTP_409_CONFLICT


@override_dependencies(ARTIFACT_OVERRIDES)
@patch(
    "app.artifacts.router.download_project_artifact",
    side_effect=ExternalServiceError("Failed to read the files of artifact 'my-adapter'"),
)
def test_download_artifact_storage_failure_returns_502(mock_download) -> None:  # type: ignore[misc, no-untyped-def]
    """Storage the service could not read surfaces as 502, not an artifact the caller got wrong."""
    with TestClient(app) as client:
        response = client.get(DOWNLOAD_URL)
    assert response.status_code == status.HTTP_502_BAD_GATEWAY


@override_dependencies(ARTIFACT_OVERRIDES)
@patch(
    "app.artifacts.router.download_project_artifact",
    side_effect=UnhealthyException("Object storage endpoint is not reachable from outside the cluster"),
)
def test_download_artifact_unusable_storage_endpoint_returns_503(mock_download) -> None:  # type: ignore[misc, no-untyped-def]
    """An install the caller cannot fix by changing the request surfaces as 503, not a generic 500,
    so it is not confused with the 400s that do invite a corrected retry."""
    with TestClient(app) as client:
        response = client.get(DOWNLOAD_URL)
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@override_dependencies(ARTIFACT_OVERRIDES)
def test_download_artifact_invalid_name_returns_422() -> None:
    """A name violating the DNS-label pattern is rejected before the service is reached."""
    with TestClient(app) as client:
        response = client.get("/v1/projects/test-namespace/artifacts/Invalid_Name!/download")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(
    {
        **ARTIFACT_OVERRIDES,
        get_minio_client: lambda: _MINIO_SENTINEL,
        get_minio_external_client: lambda: _EXTERNAL_MINIO_SENTINEL,
    }
)
@patch("app.artifacts.router.download_project_artifact", return_value=_make_download_response())
def test_download_artifact_forwards_both_storage_clients(mock_download) -> None:  # type: ignore[misc, no-untyped-def]
    """Listing runs in-cluster while the links are signed for the outside, so the two endpoints
    reach the service distinctly rather than one standing in for both."""
    with TestClient(app) as client:
        client.get(DOWNLOAD_URL)
    assert mock_download.await_args.kwargs["minio_client"] is _MINIO_SENTINEL
    assert mock_download.await_args.kwargs["minio_external_client"] is _EXTERNAL_MINIO_SENTINEL


@override_dependencies({**ARTIFACT_OVERRIDES, get_minio_client: _raise_minio_unavailable})
def test_download_artifact_requires_configured_storage() -> None:
    """Unlike get and list, a download cannot degrade: with no storage there is nothing to sign, so
    it takes the strict dependency and refuses rather than answering with an empty file set. Storage
    that is absent is reported as the same upstream failure as storage that cannot be reached, so the
    caller is told what is wrong instead of receiving an unexplained 500."""
    with TestClient(app) as client:
        response = client.get(DOWNLOAD_URL)
    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert "Object storage is not available" in response.json()["detail"]
