# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Unit tests for artifact onboarding service logic."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
import yaml
from kubernetes_asyncio.client import ApiException
from minio import Minio
from minio.error import S3Error

from api_common.exceptions import (
    ConflictException,
    DeletionConflictException,
    ExternalServiceError,
    ForbiddenException,
    NotFoundException,
    UnhealthyException,
    ValidationException,
)
from app.aims.constants import ADAPTER_PROFILE_FEATURE
from app.aims.crds import (
    AIMArtifactResource,
    AIMArtifactSpec,
    AIMArtifactStatusFields,
    AIMProfileResource,
    AIMProfileSpec,
    AIMServiceResource,
    AIMServiceStatusFields,
    ResolvedRef,
)
from app.aims.enums import ResolutionScope
from app.artifacts.manifest import ADAPTER_MANIFEST_FILENAME
from app.artifacts.schemas import (
    MAX_ARTIFACT_FILES,
    MAX_ARTIFACT_LISTING_ENTRIES,
    ArtifactDownloadResponse,
    ArtifactType,
    CreateArtifactRequest,
    ListArtifactsQuery,
    ReadinessState,
)
from app.artifacts.service import (
    _PRESIGNED_URL_EXPIRY,
    MANAGED_STORAGE_URI_ANNOTATION,
    create_adapter_artifact,
    delete_project_adapter_artifact,
    download_project_artifact,
    get_project_adapter_artifact,
    list_project_adapter_artifacts,
)
from app.dispatch.crds import K8sMetadata
from app.dispatch.kube_client import KubernetesClient
from app.minio import MinioClient
from app.minio.config import (
    MINIO_BUCKET,
    MINIO_CREDENTIALS_ACCESS_KEY_KEY,
    MINIO_CREDENTIALS_SECRET_KEY_KEY,
    MINIO_CREDENTIALS_SECRET_NAME,
    MINIO_URL,
)
from app.workloads.constants import DESCRIPTION_ANNOTATION, DISPLAY_NAME_ANNOTATION

_RESOURCE_NAME_RE = re.compile(r"^adapter-[0-9a-f]{8}$")

_REQUEST = CreateArtifactRequest(
    type="adapter",
    source={"type": "upload"},
    model_id="org/base-model",
    compatible_with=["org/base-model"],
    files=["adapter_config.json", "adapter_model.safetensors"],
)

_REQUEST_WITH_RANK = CreateArtifactRequest(
    type="adapter",
    source={"type": "upload"},
    model_id="org/base-model",
    compatible_with=["org/base-model"],
    rank=16,
    files=["adapter_config.json", "adapter_model.safetensors"],
)

_S3_SOURCE_PREFIX = "test-namespace/adapters/my-adapter/"
_S3_SOURCE_URI = f"s3://{MINIO_BUCKET}/{_S3_SOURCE_PREFIX}"

_S3_REQUEST = CreateArtifactRequest(
    type="adapter",
    source={"type": "s3", "uri": _S3_SOURCE_URI},
    model_id="org/base-model",
    compatible_with=["org/base-model"],
)

_S3_REQUEST_WITH_RANK = CreateArtifactRequest(
    type="adapter",
    source={"type": "s3", "uri": _S3_SOURCE_URI},
    model_id="org/base-model",
    compatible_with=["org/base-model"],
    rank=24,
)


def _make_kube_client(resource_name: str = "adapter-abcd1234") -> AsyncMock:
    """Build a mock kube_client that returns a valid AIMArtifactResource.

    ``custom_objects`` is an instance attribute the real client sets in ``__init__``, not a class
    attribute, so ``spec=KubernetesClient`` alone won't expose it; it is attached explicitly here so
    the rest of the mock still catches accidental typos against the real interface.
    """
    artifact = AIMArtifactResource(
        metadata=K8sMetadata(name=resource_name, namespace="test-namespace"),
        spec=AIMArtifactSpec(type="adapter"),
        status=AIMArtifactStatusFields(),
    )
    mock = AsyncMock(spec=KubernetesClient)
    mock.custom_objects = AsyncMock()
    mock.core_v1 = AsyncMock()
    mock.custom_objects.create_namespaced_custom_object = AsyncMock(return_value=artifact.model_dump(by_alias=True))
    return mock


def _kube_client() -> AsyncMock:
    """Kube client for list/get/delete tests, whose gateway calls are patched directly.

    ``spec=KubernetesClient`` catches accidental typos against the real interface even though the
    mock is never actually exercised — the patched gateway functions never touch it.
    """
    return AsyncMock(spec=KubernetesClient)


def _s3_error(code: str) -> S3Error:
    """Build the S3Error minio-py would raise for the given error code."""
    return S3Error(
        code=code,
        message=code,
        resource="/bucket/object",
        request_id="request123",
        host_id="host123",
        response=MagicMock(status=404 if code == "NoSuchKey" else 503),
    )


def _make_minio_client() -> MagicMock:
    """Build a mock MinioClient that returns a fake presigned URL."""
    mock = MagicMock(spec=MinioClient)
    mock.generate_presigned_upload_url.return_value = "https://minio.example.com/presigned"
    # No manifest exists beside the weights yet, so a read reports the object missing.
    mock.download_object.side_effect = _s3_error("NoSuchKey")
    return mock


def _make_s3_minio_client() -> MagicMock:
    """MinioClient for S3-source tests: no manifest sits beside the weights yet, so a manifest read
    reports the object missing and the service falls back to writing its own."""
    mock = MagicMock(spec=MinioClient)
    mock.download_object.side_effect = _s3_error("NoSuchKey")
    return mock


@pytest.mark.asyncio
async def test_resource_name_format() -> None:
    """Service generates resource names of the form 'adapter-<8 hex chars>'."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    called_manifest = mock_create.call_args.args[2]
    resource_name = called_manifest["metadata"]["name"]
    assert _RESOURCE_NAME_RE.match(resource_name), f"Unexpected resource name: {resource_name}"


@pytest.mark.asyncio
async def test_s3_prefix_construction() -> None:
    """S3 prefix uses slugified namespace and adapter resource name."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    called_manifest = mock_create.call_args.args[2]
    resource_name = called_manifest["metadata"]["name"]
    source_uri = called_manifest["spec"]["sourceUri"]
    # Prefix must end with a slash and contain the slugified namespace + resource name
    assert source_uri.startswith("s3://")
    assert "test-namespace" in source_uri
    assert resource_name in source_uri
    assert source_uri.endswith("/")


@pytest.mark.asyncio
async def test_presigned_url_count_matches_files() -> None:
    """Service generates one upload instruction per file in the request."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        result = await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    assert len(result.uploads) == len(_REQUEST.files or [])
    paths = {u.path for u in result.uploads}
    assert paths == set(_REQUEST.files or [])


@pytest.mark.asyncio
async def test_manifest_labels_and_spec_fields() -> None:
    """Manifest carries required labels and spec fields."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    assert manifest["metadata"]["labels"]["app.kubernetes.io/managed-by"] == "aiwb"
    assert manifest["spec"]["type"] == "adapter"
    assert manifest["spec"]["modelId"] == "org/base-model"
    assert manifest["spec"]["compatibleWith"] == ["org/base-model"]


@pytest.mark.asyncio
async def test_rank_included_in_manifest_when_provided() -> None:
    """When rank is present in the request it is included in the CR spec."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST_WITH_RANK,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    assert manifest["spec"]["rank"] == 16


@pytest.mark.asyncio
async def test_rank_omitted_from_manifest_when_none() -> None:
    """When rank is None it is not included in the CR spec."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    assert "rank" not in manifest["spec"]


@pytest.mark.asyncio
async def test_upload_instructions_have_put_method() -> None:
    """All upload instructions specify PUT method."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        result = await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    for upload in result.uploads:
        assert upload.method == "PUT"


@pytest.mark.asyncio
async def test_upload_source_returns_presigned_urls() -> None:
    """Upload-backed mode generates presigned PUT URLs for each declared file."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        result = await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    assert len(result.uploads) == 2
    for upload in result.uploads:
        assert upload.url.startswith("https://")
        assert upload.method == "PUT"


@pytest.mark.asyncio
async def test_created_adapter_reports_the_base_models_the_cluster_accepted() -> None:
    """The response carries the accepted resource rather than echoing the request, so a cluster that
    pruned compatibleWith would report an adapter without it instead of one that has it."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(compatible_with=["org/base-model"]),
            status=AIMArtifactStatusFields(),
        )
        result = await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    assert result.artifact is not None
    assert result.artifact.spec.compatible_with == ["org/base-model"]


@pytest.mark.asyncio
async def test_s3_source_returns_artifact_with_no_uploads() -> None:
    """S3 source creates an artifact with no presigned upload instructions."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        result = await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    assert result.uploads == []
    assert result.artifact is not None


@pytest.mark.asyncio
async def test_s3_source_verifies_required_files() -> None:
    """S3 source calls stat_object for both required LoRA PEFT files."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    assert minio_client.stat_object.call_count == 2
    object_names = {call.args[1] for call in minio_client.stat_object.call_args_list}
    assert object_names == {
        f"{_S3_SOURCE_PREFIX}adapter_config.json",
        f"{_S3_SOURCE_PREFIX}adapter_model.safetensors",
    }


@pytest.mark.asyncio
async def test_s3_source_stores_canonical_uri() -> None:
    """S3 source stores the canonical bucket + normalized prefix in spec.sourceUri, not the raw
    request URI: a slash-less request prefix (verified with a trailing slash) is stored with one,
    matching where verification confirmed the files and the form the upload path writes."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    request = CreateArtifactRequest(
        type="adapter",
        source={"type": "s3", "uri": _S3_SOURCE_URI.rstrip("/")},
        model_id="org/base-model",
        compatible_with=["org/base-model"],
    )

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=request,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    assert manifest["spec"]["sourceUri"] == _S3_SOURCE_URI


@pytest.mark.asyncio
async def test_s3_source_missing_file_raises_validation_error() -> None:
    """When a required LoRA file is missing, service raises ValidationException."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_client.stat_object.side_effect = _s3_error("NoSuchKey")

    with pytest.raises(ValidationException) as exc_info:
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    assert "adapter_config.json" in exc_info.value.message
    assert "adapter_model.safetensors" in exc_info.value.message


@pytest.mark.asyncio
async def test_s3_source_stat_bucket_uses_parsed_bucket() -> None:
    """Verification reads the bucket parsed from the URI, which scoping has pinned to the platform
    bucket, so a caller cannot redirect the stat at storage the platform does not own."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    buckets_used = {call.args[0] for call in minio_client.stat_object.call_args_list}
    assert buckets_used == {MINIO_BUCKET}


@pytest.mark.asyncio
async def test_manifest_uses_aim_artifact_api_version() -> None:
    """AIMArtifact manifests must carry aim.eai.amd.com/v1alpha1, not the v1alpha2 used by other AIM kinds."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    assert manifest["apiVersion"] == "aim.eai.amd.com/v1alpha1"


@pytest.mark.asyncio
async def test_s3_source_manifest_has_managed_by_label() -> None:
    """S3 source path stamps app.kubernetes.io/managed-by: aiwb on the manifest."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    assert manifest["metadata"]["labels"]["app.kubernetes.io/managed-by"] == "aiwb"


_REQUEST_WITH_DISPLAY_NAME = CreateArtifactRequest(
    type="adapter",
    source={"type": "upload"},
    model_id="org/base-model",
    compatible_with=["org/base-model"],
    display_name="My Adapter",
    files=["adapter_config.json", "adapter_model.safetensors"],
)

_S3_REQUEST_WITH_DISPLAY_NAME = CreateArtifactRequest(
    type="adapter",
    source={"type": "s3", "uri": _S3_SOURCE_URI},
    model_id="org/base-model",
    compatible_with=["org/base-model"],
    display_name="My S3 Adapter",
)


@pytest.mark.asyncio
async def test_upload_manifest_includes_display_name_annotation() -> None:
    """When displayName is provided, it is stamped as a metadata annotation on upload manifests."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST_WITH_DISPLAY_NAME,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    assert manifest["metadata"]["annotations"][DISPLAY_NAME_ANNOTATION] == "My Adapter"


@pytest.mark.asyncio
async def test_s3_manifest_includes_display_name_annotation() -> None:
    """When displayName is provided, it is stamped as a metadata annotation on S3 source manifests."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST_WITH_DISPLAY_NAME,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    assert manifest["metadata"]["annotations"][DISPLAY_NAME_ANNOTATION] == "My S3 Adapter"


@pytest.mark.asyncio
async def test_manifest_omits_display_name_annotation_when_not_provided() -> None:
    """When displayName is omitted, no display-name annotation key is added to the manifest."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    assert DISPLAY_NAME_ANNOTATION not in manifest["metadata"]["annotations"]
    assert DESCRIPTION_ANNOTATION not in manifest["metadata"]["annotations"]


@pytest.mark.asyncio
async def test_upload_manifest_records_the_storage_it_allocated() -> None:
    """An uploaded adapter records the prefix AIWB allocated, which is what makes it reclaimable."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    resource_name = manifest["metadata"]["name"]
    allocated = f"s3://{MINIO_BUCKET}/test-namespace/adapters/{resource_name}/"
    assert manifest["metadata"]["annotations"][MANAGED_STORAGE_URI_ANNOTATION] == allocated
    # The same prefix the presigned URLs write to, so the record and the storage cannot diverge.
    assert manifest["spec"]["sourceUri"] == allocated


@pytest.mark.asyncio
async def test_s3_manifest_records_no_managed_storage() -> None:
    """An adapter onboarded from the caller's own files claims no storage, so none is reclaimed."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    assert MANAGED_STORAGE_URI_ANNOTATION not in manifest["metadata"]["annotations"]


@pytest.mark.asyncio
async def test_upload_stamps_description_on_the_cr_and_the_recovery_manifest() -> None:
    """The description is free text the caller owns, so it is written to both records that describe
    the adapter -- the CR the platform reads and the mirror that survives the CR."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()
    request = _REQUEST.model_copy(update={"description": "Tuned on support transcripts."})

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=request,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    assert manifest["metadata"]["annotations"][DESCRIPTION_ANNOTATION] == "Tuned on support transcripts."
    written = yaml.safe_load(minio_client.upload_object.call_args.kwargs["data"])
    assert written["description"] == "Tuned on support transcripts."


@pytest.mark.asyncio
async def test_s3_source_recovers_description_from_existing_manifest() -> None:
    """A description mirrored beside the weights is ground truth, so it restores the CR annotation
    even when the request omitted one."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_client.download_object.side_effect = None
    minio_client.download_object.return_value = yaml.safe_dump(
        {"modelId": "engine/produced-adapter", "description": "Recovered blurb."}
    ).encode("utf-8")

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    assert manifest["metadata"]["annotations"][DESCRIPTION_ANNOTATION] == "Recovered blurb."


@pytest.mark.asyncio
async def test_upload_urls_are_signed_by_the_external_client() -> None:
    """Upload URLs must come from the external endpoint: SigV4 signs the Host header, so a URL
    signed for the in-cluster service name is unusable by callers outside the cluster."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_client.generate_presigned_upload_url.return_value = "http://internal.invalid/presigned"
    minio_external_client = MagicMock(spec=MinioClient)
    minio_external_client.generate_presigned_upload_url.return_value = "https://external.example.com/presigned"

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        result = await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_external_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    minio_client.generate_presigned_upload_url.assert_not_called()
    assert minio_external_client.generate_presigned_upload_url.call_count == len(_REQUEST.files or [])
    for upload in result.uploads:
        assert upload.url == "https://external.example.com/presigned"


@pytest.mark.asyncio
async def test_upload_is_refused_when_the_signing_endpoint_is_not_externally_addressable() -> None:
    """A URL signed against a host the caller cannot resolve is unrepairable, so the request is
    refused instead of answered with a 201 nobody can act on, and nothing is created.

    The sibling upload tests need no change: their ``MagicMock(spec=MinioClient)`` answers the
    predicate with a truthy mock, so they keep taking the accepting path.
    """
    kube_client = _make_kube_client()
    minio_external_client = MagicMock(spec=MinioClient)
    minio_external_client.is_externally_addressable.return_value = False
    minio_external_client.host = "http://filer-s3.example.svc.cluster.local:80"

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        with pytest.raises(UnhealthyException, match="minio.externalUrl"):
            await create_adapter_artifact(
                kube_client=kube_client,
                minio_client=_make_minio_client(),
                minio_external_client=minio_external_client,
                namespace="test-namespace",
                request=_REQUEST,
                submitter="test@example.com",
            )

    mock_create.assert_not_called()
    minio_external_client.generate_presigned_upload_url.assert_not_called()


@pytest.mark.asyncio
async def test_s3_source_is_accepted_when_the_signing_endpoint_is_not_externally_addressable() -> None:
    """Registering weights already in object storage signs no URL, so it must not inherit the
    upload path's refusal — that path is the remaining way to onboard on such an install."""
    kube_client = _make_kube_client()
    minio_external_client = MagicMock(spec=MinioClient)
    minio_external_client.is_externally_addressable.return_value = False

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        result = await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=_make_s3_minio_client(),
            minio_external_client=minio_external_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    assert result.storage.readiness == ReadinessState.READY
    assert result.uploads == []


@pytest.mark.asyncio
async def test_upload_links_all_expire_at_the_advertised_instant() -> None:
    """A signature dies a fixed span after a timestamp carried inside it, and links are minted one
    after another — so letting each take its own reading of the signing clock would leave the last
    alive past the single instant every instruction advertises. Every link is stamped with one
    instant for the batch instead, which is exactly the instant those deadlines are measured from."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_external_client = MagicMock(spec=MinioClient)
    minio_external_client.generate_presigned_upload_url.return_value = "https://external.example.com/presigned"

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        result = await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_external_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    calls = minio_external_client.generate_presigned_upload_url.call_args_list
    assert len(calls) == len(result.uploads) > 1
    deadlines = {u.expires_at for u in result.uploads}
    assert len(deadlines) == 1
    assert {c.kwargs["expires"] for c in calls} == {_PRESIGNED_URL_EXPIRY}
    assert {c.kwargs["request_date"] for c in calls} == {deadlines.pop() - _PRESIGNED_URL_EXPIRY}


@pytest.mark.asyncio
async def test_s3_verification_uses_the_internal_client() -> None:
    """Source verification runs server-side and must stay on the in-cluster endpoint rather than
    routing reads back out through the gateway."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_external_client = MagicMock(spec=MinioClient)

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_external_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    assert minio_client.stat_object.call_count == 2
    minio_external_client.stat_object.assert_not_called()


@pytest.mark.asyncio
async def test_upload_object_keys_are_independent_of_signing_endpoint() -> None:
    """Switching the signing endpoint must not change where bytes land: the artifact's sourceUri
    and the signed object keys have to stay in the same prefix."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_external_client = MagicMock(spec=MinioClient)
    minio_external_client.generate_presigned_upload_url.return_value = "https://external.example.com/presigned"

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_external_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    source_uri = mock_create.call_args.args[2]["spec"]["sourceUri"]
    prefix = source_uri.removeprefix("s3://").split("/", 1)[1]
    signed_keys = {
        call.kwargs["object_name"] for call in minio_external_client.generate_presigned_upload_url.call_args_list
    }
    assert signed_keys == {f"{prefix}{f}" for f in _REQUEST.files or []}


@pytest.mark.parametrize("request_payload", [_REQUEST, _S3_REQUEST], ids=["upload", "s3_source"])
@pytest.mark.asyncio
async def test_manifest_carries_s3_credentials(request_payload: CreateArtifactRequest) -> None:
    """Without credentials on the spec, aim-engine cannot read the artifact's S3 source and the
    artifact never leaves pending, regardless of how the source was supplied."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=request_payload,
            submitter="test@example.com",
        )

    env = {var["name"]: var for var in mock_create.call_args.args[2]["spec"]["env"]}
    assert set(env) == {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ENDPOINT_URL"}

    access_key_ref = env["AWS_ACCESS_KEY_ID"]["valueFrom"]["secretKeyRef"]
    assert access_key_ref == {"name": MINIO_CREDENTIALS_SECRET_NAME, "key": MINIO_CREDENTIALS_ACCESS_KEY_KEY}

    secret_key_ref = env["AWS_SECRET_ACCESS_KEY"]["valueFrom"]["secretKeyRef"]
    assert secret_key_ref == {"name": MINIO_CREDENTIALS_SECRET_NAME, "key": MINIO_CREDENTIALS_SECRET_KEY_KEY}


@pytest.mark.asyncio
async def test_manifest_credentials_point_at_the_internal_endpoint() -> None:
    """The credentials are consumed by in-cluster reconciliation jobs, so they must target the
    internal endpoint even though upload URLs are signed for the external one."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    env = {var["name"]: var for var in mock_create.call_args.args[2]["spec"]["env"]}
    assert env["AWS_ENDPOINT_URL"]["value"] == MINIO_URL


@pytest.mark.asyncio
async def test_creation_is_rejected_when_the_credentials_secret_is_missing() -> None:
    """The manifest names the credentials secret rather than embedding them, so a namespace without
    it yields an artifact that is accepted and then never reconciles. Fail the request instead."""
    kube_client = _make_kube_client()
    kube_client.core_v1.read_namespaced_secret.side_effect = ApiException(status=404)
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        with pytest.raises(ValidationException, match=MINIO_CREDENTIALS_SECRET_NAME):
            await create_adapter_artifact(
                kube_client=kube_client,
                minio_client=minio_client,
                minio_external_client=minio_client,
                namespace="test-namespace",
                request=_REQUEST,
                submitter="test@example.com",
            )

    mock_create.assert_not_called()
    minio_client.generate_presigned_upload_url.assert_not_called()


@pytest.mark.parametrize(
    "uri",
    [
        f"s3://other-bucket/{_S3_SOURCE_PREFIX}",
        f"s3://{MINIO_BUCKET}/other-namespace/adapters/my-adapter/",
        f"s3://{MINIO_BUCKET}/test-namespace-2/adapters/my-adapter/",
        f"s3://{MINIO_BUCKET}/test-namespace/../other-namespace/adapters/",
        f"s3://{MINIO_BUCKET}/",
        f"s3://{MINIO_BUCKET}",
        f"http://{MINIO_BUCKET}/test-namespace/adapters/my-adapter/",
    ],
    ids=[
        "foreign_bucket",
        "foreign_namespace",
        "namespace_prefix_overlap",
        "traversal",
        "bucket_root",
        "no_prefix",
        "invalid_scheme",
    ],
)
@pytest.mark.asyncio
async def test_s3_source_outside_the_project_is_rejected(uri: str) -> None:
    """One bucket is shared by every project, so an unscoped URI would let a caller stat another
    project's objects and learn whether they exist. Reject before any storage call is made."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    request = CreateArtifactRequest(
        type="adapter",
        source={"type": "s3", "uri": uri},
        model_id="org/base-model",
        compatible_with=["org/base-model"],
    )

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        with pytest.raises(ValidationException):
            await create_adapter_artifact(
                kube_client=kube_client,
                minio_client=minio_client,
                minio_external_client=minio_client,
                namespace="test-namespace",
                request=request,
                submitter="test@example.com",
            )

    minio_client.stat_object.assert_not_called()
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_s3_source_accepts_any_prefix_within_the_project() -> None:
    """Adapters produced by other features do not live under adapters/, so scoping draws the line
    at the project's tree rather than at one subdirectory of it."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    request = CreateArtifactRequest(
        type="adapter",
        source={"type": "s3", "uri": f"s3://{MINIO_BUCKET}/test-namespace/finetuned-models/run-1/"},
        model_id="org/base-model",
        compatible_with=["org/base-model"],
    )

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        result = await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=request,
            submitter="test@example.com",
        )

    assert result.artifact is not None


@pytest.mark.asyncio
async def test_unreachable_storage_is_not_reported_as_missing_files() -> None:
    """A throttled or failing backend must surface as a storage error, not as a 400 telling the
    caller their adapter files are absent when nothing is known about them."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_client.stat_object.side_effect = _s3_error("SlowDown")

    with pytest.raises(ExternalServiceError):
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )


@pytest.mark.asyncio
async def test_s3_source_existing_manifest_wins_over_request() -> None:
    """A manifest already beside the weights is ground truth for what those files are, so its
    modelId and rank override whatever the request declared, and no manifest is rewritten."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_client.download_object.side_effect = None
    minio_client.download_object.return_value = yaml.safe_dump(
        {"modelId": "engine/produced-adapter", "compatibleWith": ["org/base-model"], "rank": 32}
    ).encode("utf-8")

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    spec = mock_create.call_args.args[2]["spec"]
    assert spec["modelId"] == "engine/produced-adapter"
    assert spec["rank"] == 32
    minio_client.upload_object.assert_not_called()


@pytest.mark.asyncio
async def test_s3_source_keeps_request_rank_when_manifest_states_none() -> None:
    """A manifest written without a rank — as the fine-tuning engine may leave it — states nothing
    for the CR to inherit, so the rank the caller declared is kept rather than silently dropped."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_client.download_object.side_effect = None
    minio_client.download_object.return_value = yaml.safe_dump(
        {"modelId": "engine/produced-adapter", "compatibleWith": ["org/base-model"]}
    ).encode("utf-8")

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST_WITH_RANK,
            submitter="test@example.com",
        )

    assert mock_create.call_args.args[2]["spec"]["rank"] == 24


@pytest.mark.asyncio
async def test_s3_source_manifest_rank_wins_over_declared_request_rank() -> None:
    """Falling back to the request only covers a manifest that is silent: where the manifest does
    record a rank it stays ground truth, even against a request declaring a different one."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_client.download_object.side_effect = None
    minio_client.download_object.return_value = yaml.safe_dump(
        {"modelId": "engine/produced-adapter", "compatibleWith": ["org/base-model"], "rank": 32}
    ).encode("utf-8")

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST_WITH_RANK,
            submitter="test@example.com",
        )

    assert mock_create.call_args.args[2]["spec"]["rank"] == 32


@pytest.mark.asyncio
async def test_s3_source_manifest_rank_of_zero_is_not_treated_as_absent() -> None:
    """The manifest may record a rank the request schema itself forbids, so falsiness is not a safe
    proxy for absence: a stated rank of zero is still something the manifest asserts, and stays
    ground truth against a request declaring its own."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_client.download_object.side_effect = None
    minio_client.download_object.return_value = yaml.safe_dump(
        {"modelId": "engine/produced-adapter", "compatibleWith": ["org/base-model"], "rank": 0}
    ).encode("utf-8")

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST_WITH_RANK,
            submitter="test@example.com",
        )

    assert mock_create.call_args.args[2]["spec"]["rank"] == 0


@pytest.mark.asyncio
async def test_s3_source_manifest_without_compatibility_is_not_a_conflict() -> None:
    """A manifest written before compatibleWith existed states nothing about compatibility, so it
    cannot contradict the request — the adapter onboards with the declared compatibility."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_client.download_object.side_effect = None
    minio_client.download_object.return_value = yaml.safe_dump(
        {"modelId": "engine/produced-adapter", "rank": 32}
    ).encode("utf-8")

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    assert mock_create.call_args.args[2]["spec"]["compatibleWith"] == ["org/base-model"]


@pytest.mark.asyncio
async def test_s3_source_existing_manifest_compatibility_mismatch_is_rejected() -> None:
    """When the manifest records what the adapter was trained against, a request declaring different
    compatibility is a contradiction — onboarding it would advertise the adapter against a base it
    cannot serve, so the request is rejected before the CR is created."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_client.download_object.side_effect = None
    minio_client.download_object.return_value = yaml.safe_dump(
        {"modelId": "engine/produced-adapter", "compatibleWith": ["engine/different-base"], "rank": 32}
    ).encode("utf-8")

    with (
        patch("app.artifacts.service.create_aim_artifact") as mock_create,
        pytest.raises(ValidationException, match="different-base"),
    ):
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_s3_source_writes_recovery_manifest_when_absent() -> None:
    """With no manifest beside the weights, the service resolves the parent's model id and writes
    its own recovery mirror using the request's declared values."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    minio_client.upload_object.assert_called_once()
    kwargs = minio_client.upload_object.call_args.kwargs
    assert kwargs["bucket_name"] == MINIO_BUCKET
    assert kwargs["object_name"] == f"{_S3_SOURCE_PREFIX}{ADAPTER_MANIFEST_FILENAME}"
    written = yaml.safe_load(kwargs["data"])
    assert written == {"modelId": "org/base-model", "compatibleWith": ["org/base-model"]}


@pytest.mark.asyncio
async def test_upload_writes_recovery_manifest_beside_weights() -> None:
    """The upload path writes a recovery manifest into the artifact's prefix on the in-cluster
    client, mirroring the compatibility declared by the request."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST_WITH_RANK,
            submitter="test@example.com",
        )

    prefix = mock_create.call_args.args[2]["spec"]["sourceUri"].removeprefix(f"s3://{MINIO_BUCKET}/")
    minio_client.upload_object.assert_called_once()
    kwargs = minio_client.upload_object.call_args.kwargs
    assert kwargs["bucket_name"] == MINIO_BUCKET
    assert kwargs["object_name"] == f"{prefix}{ADAPTER_MANIFEST_FILENAME}"
    written = yaml.safe_load(kwargs["data"])
    assert written == {"modelId": "org/base-model", "compatibleWith": ["org/base-model"], "rank": 16}


@pytest.mark.asyncio
async def test_upload_writes_display_name_into_recovery_manifest() -> None:
    """A supplied displayName is mirrored into the S3 recovery manifest, not only the CR annotation, so
    a rebuild from object storage restores the human-facing label."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST_WITH_DISPLAY_NAME,
            submitter="test@example.com",
        )

    written = yaml.safe_load(minio_client.upload_object.call_args.kwargs["data"])
    assert written["displayName"] == "My Adapter"


@pytest.mark.asyncio
async def test_s3_source_recovers_display_name_from_existing_manifest() -> None:
    """A displayName mirrored beside the weights is ground truth, so it restores the CR's display-name
    annotation even when the request omitted one."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    minio_client.download_object.side_effect = None
    minio_client.download_object.return_value = yaml.safe_dump(
        {
            "modelId": "engine/produced-adapter",
            "rank": 32,
            "displayName": "Recovered Adapter",
        }
    ).encode("utf-8")

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    manifest = mock_create.call_args.args[2]
    assert manifest["metadata"]["annotations"][DISPLAY_NAME_ANNOTATION] == "Recovered Adapter"
    minio_client.upload_object.assert_not_called()


@pytest.mark.asyncio
async def test_recovery_manifest_write_failure_does_not_fail_the_request() -> None:
    """The CR is authoritative and already exists once the manifest write runs, so a failed mirror
    write is swallowed rather than failing the caller and throwing away the presigned upload URLs."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()
    # AccessDenied maps to a non-transient ForbiddenException, so the write fails immediately (no
    # retry backoff) — the service must log and continue rather than propagate.
    minio_client.upload_object.side_effect = _s3_error("AccessDenied")

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        result = await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_REQUEST,
            submitter="test@example.com",
        )

    mock_create.assert_called_once()
    assert result.artifact is not None
    assert len(result.uploads) == 2


@pytest.mark.asyncio
async def test_s3_source_recovery_manifest_write_failure_does_not_fail_the_request() -> None:
    """The S3-source path is best-effort about the mirror too: the files are already in place and the
    CR is authoritative, so even a non-domain failure (here a raw connection error, which the mapped
    domain exceptions would not cover) is swallowed rather than failing the onboard."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()

    with (
        patch("app.artifacts.service.create_aim_artifact") as mock_create,
        patch("app.artifacts.service.write_adapter_manifest", side_effect=ConnectionError("minio unreachable")),
    ):
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        result = await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=_S3_REQUEST,
            submitter="test@example.com",
        )

    mock_create.assert_called_once()
    assert result.artifact is not None
    assert result.uploads == []


@pytest.mark.asyncio
async def test_upload_drops_manifest_filename_from_presigned_set() -> None:
    """AIWB is the sole author of the manifest, so a client-listed copy of adapter-manifest.yaml is
    dropped from the presigned upload set to avoid racing the service's own write for that key."""
    kube_client = _make_kube_client()
    minio_client = _make_minio_client()
    request = CreateArtifactRequest(
        type="adapter",
        source={"type": "upload"},
        model_id="org/base-model",
        compatible_with=["org/base-model"],
        files=["adapter_config.json", "adapter_model.safetensors", ADAPTER_MANIFEST_FILENAME],
    )

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        result = await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=request,
            submitter="test@example.com",
        )

    paths = {u.path for u in result.uploads}
    assert paths == {"adapter_config.json", "adapter_model.safetensors"}
    assert ADAPTER_MANIFEST_FILENAME not in paths


def _sweeping_minio() -> MagicMock:
    """A storage client for delete tests, whose object removals succeed."""
    return MagicMock(spec=MinioClient)


def _unreadable_minio() -> MagicMock:
    """A storage client whose stats always fail transiently, so readiness stays unknown.

    For the listing tests that assert on paging, filtering and ordering rather than readiness.
    """
    client = MagicMock(spec=MinioClient)
    client.stat_object.side_effect = _s3_error("SlowDown")
    return client


_ADAPTERS_ROOT = "test-namespace/adapters/"


def _scanning_minio(*keys: str) -> MagicMock:
    """A storage client whose recursive listing of the project's adapter tree returns ``keys``.

    ``client`` is an instance attribute the real MinioClient sets in ``__init__``, so the outer
    ``spec=`` does not expose it and it is attached explicitly, specced in its own right. Stats keep
    failing transiently so any test that ends up statting reports Unknown visibly rather than
    passing by accident.
    """
    client = _unreadable_minio()
    client.client = MagicMock(spec=Minio)
    client.client.list_objects.return_value = [SimpleNamespace(object_name=k) for k in keys]
    return client


def _peft_keys(prefix: str) -> list[str]:
    return [f"{prefix}adapter_config.json", f"{prefix}adapter_model.safetensors"]


def _adapter_resource(
    name: str,
    artifact_type: str = "adapter",
    managed_by: str = "aiwb",
    source_uri: str = f"s3://{MINIO_BUCKET}/test-namespace/adapters/a/",
    created: datetime | None = None,
    compatible_with: list[str] | None = None,
    managed_storage_uri: str | None = None,
    model_id: str | None = None,
    rank: int | None = None,
    display_name: str | None = None,
    description: str | None = None,
) -> AIMArtifactResource:
    """Build an AIMArtifactResource as the gateway would return it from a list/get.

    ``managed_storage_uri`` stamps the create-time annotation that marks an adapter as upload-backed;
    leaving it unset produces the un-annotated resource an S3 onboard, the fine-tuning engine, or a
    create predating the annotation would leave behind.
    """
    annotations = {}
    if managed_storage_uri:
        annotations[MANAGED_STORAGE_URI_ANNOTATION] = managed_storage_uri
    if display_name:
        annotations[DISPLAY_NAME_ANNOTATION] = display_name
    if description:
        annotations[DESCRIPTION_ANNOTATION] = description
    return AIMArtifactResource(
        metadata=K8sMetadata(
            name=name,
            namespace="test-namespace",
            labels={"app.kubernetes.io/managed-by": managed_by},
            annotations=annotations,
            creation_timestamp=created,
        ),
        spec=AIMArtifactSpec(
            type=artifact_type,
            source_uri=source_uri,
            model_id=model_id,
            compatible_with=compatible_with,
            rank=rank,
        ),
        status=AIMArtifactStatusFields(),
    )


@contextmanager
def _patch_list(artifacts: list[AIMArtifactResource]) -> Iterator[None]:
    """Stub the artifact read the listing makes."""
    with patch("app.artifacts.service.list_aim_artifacts_by_label_selector", AsyncMock(return_value=artifacts)):
        yield


@pytest.mark.asyncio
async def test_list_returns_paginated_adapters():
    """The listing wraps platform artifacts in the paginated envelope with an accurate total."""
    artifacts = [_adapter_resource(f"adapter-{i}") for i in range(3)]
    with _patch_list(artifacts):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert result.pagination.total == 3
    assert len(result.data) == 3
    # Storage cannot be reached, so readiness is Unknown rather than a definite Ready/NotReady.
    assert all(a.storage.readiness == ReadinessState.UNKNOWN for a in result.data)


@pytest.mark.asyncio
async def test_list_excludes_platform_managed_artifacts_of_another_type():
    """A platform-managed CR of another type is outside this API's collection."""
    artifacts = [
        _adapter_resource("an-adapter", artifact_type="adapter"),
        _adapter_resource("a-model", artifact_type="model"),
    ]
    with _patch_list(artifacts):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert result.pagination.total == 1
    assert result.data[0].artifact.metadata.name == "an-adapter"


@pytest.mark.asyncio
async def test_list_type_filter_keeps_adapters():
    """Adapters are the only type this collection exposes, so a filter naming them keeps every row
    rather than narrowing the list to nothing."""
    with _patch_list([_adapter_resource("a-1")]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, type=[ArtifactType.ADAPTER]),
        )

    assert [a.artifact.metadata.name for a in result.data] == ["a-1"]


@pytest.mark.asyncio
async def test_list_sorted_newest_first():
    """The most recently created adapter leads the page regardless of the gateway's order."""
    older = _adapter_resource("older", created=datetime(2020, 1, 1, tzinfo=UTC))
    newer = _adapter_resource("newer", created=datetime(2024, 1, 1, tzinfo=UTC))
    with _patch_list([older, newer]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert [a.artifact.metadata.name for a in result.data] == ["newer", "older"]


@pytest.mark.asyncio
async def test_list_sorts_mixed_aware_naive_and_missing_timestamps():
    """A naive or absent timestamp must not make the sort raise and fail the whole listing."""
    aware = _adapter_resource("aware", created=datetime(2024, 1, 1, tzinfo=UTC))
    naive = _adapter_resource("naive", created=datetime(2022, 1, 1))
    missing = _adapter_resource("missing", created=None)
    with _patch_list([naive, missing, aware]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert [a.artifact.metadata.name for a in result.data] == ["aware", "naive", "missing"]


@pytest.mark.asyncio
async def test_list_paginates_to_requested_page():
    """page/page_size slice the sorted collection and are echoed back in the metadata."""
    artifacts = [_adapter_resource(f"adapter-{i}", created=datetime(2020, 1, 1 + i, tzinfo=UTC)) for i in range(5)]
    with _patch_list(artifacts):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=2, page_size=2),
        )

    assert result.pagination.total == 5
    assert result.pagination.page == 2
    assert result.pagination.page_size == 2
    assert len(result.data) == 2


@pytest.mark.asyncio
async def test_list_rows_are_addressable_by_name():
    """A row carries the resource name the by-name GET and DELETE address it by."""
    with _patch_list([_adapter_resource("a-1")]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert result.data[0].artifact.metadata.name == "a-1"
    assert result.data[0].storage.uri == f"s3://{MINIO_BUCKET}/{_ADAPTERS_ROOT}a/"


@pytest.mark.asyncio
async def test_list_reports_the_base_models_the_adapter_declares():
    """The declaration travels with the resource rather than being restated beside it, so a listed
    adapter says what it attaches to without the caller fetching it again."""
    with _patch_list([_adapter_resource("a-1", compatible_with=["org/base-model"])]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert result.data[0].artifact.spec.compatible_with == ["org/base-model"]


@pytest.mark.asyncio
async def test_list_marks_weights_ready_when_files_present():
    """With every required weight file stat-able, the adapter reports ready weights."""
    minio_client = MagicMock(spec=MinioClient)
    minio_client.stat_object.return_value = MagicMock()
    with _patch_list([_adapter_resource("a-1")]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=minio_client,
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert result.data[0].storage.readiness == ReadinessState.READY


@pytest.mark.asyncio
async def test_list_marks_weights_not_ready_when_file_missing():
    """A genuine not-found on a required file yields a definite NotReady verdict."""
    minio_client = MagicMock(spec=MinioClient)
    minio_client.stat_object.side_effect = _s3_error("NoSuchKey")
    with _patch_list([_adapter_resource("a-1")]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=minio_client,
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert result.data[0].storage.readiness == ReadinessState.NOT_READY


@pytest.mark.asyncio
async def test_list_leaves_weights_unknown_on_transient_storage_error():
    """A non-404 storage failure means the check could not run, so the verdict is Unknown — a
    different claim from NotReady, and one that must not be collapsed into it."""
    with _patch_list([_adapter_resource("a-1")]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert result.data[0].storage.readiness == ReadinessState.UNKNOWN


@pytest.mark.asyncio
async def test_list_reports_readiness_for_fine_tuning_authored_adapters():
    """Fine-tuning writes its adapters into the same storage this API reads, so their weights are
    checked the same way an onboarded adapter's are."""
    minio_client = MagicMock(spec=MinioClient)
    minio_client.stat_object.return_value = MagicMock()
    with _patch_list([_adapter_resource("ft-adapter", managed_by="fine-tuning")]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=minio_client,
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert result.data[0].storage.readiness == ReadinessState.READY


@pytest.mark.asyncio
async def test_list_reports_unknown_readiness_when_minio_client_unavailable():
    """No Minio client (unconfigured storage) degrades readiness to Unknown rather than failing
    the list."""
    with _patch_list([_adapter_resource("a-1")]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=None,
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert result.data[0].storage.readiness == ReadinessState.UNKNOWN


@pytest.mark.asyncio
async def test_list_reports_only_records_and_does_not_sweep_storage():
    """Weights lying in storage that no CR claims are not adapters the project owns, so plain
    browsing neither reports them nor pays for the recursive listing that would find them."""
    minio_client = _scanning_minio(*_peft_keys(f"{_ADAPTERS_ROOT}orphan/"))
    with _patch_list([_adapter_resource("a-1")]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=minio_client,
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert result.pagination.total == 1
    assert [a.artifact.metadata.name for a in result.data] == ["a-1"]
    minio_client.client.list_objects.assert_not_called()


@pytest.mark.asyncio
async def test_readiness_filter_does_not_turn_swept_prefixes_into_rows():
    """The sweep exists to answer readiness, not to discover artifacts. Weights no CR claims are
    not adapters the project owns, so a prefix the listing turned up is not a row."""
    minio_client = _scanning_minio(
        *_peft_keys(f"{_ADAPTERS_ROOT}a/"),
        *_peft_keys(f"{_ADAPTERS_ROOT}orphan/"),
    )
    with _patch_list([_adapter_resource("a-1")]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=minio_client,
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, readiness=[ReadinessState.READY]),
        )

    assert result.pagination.total == 1
    assert [a.artifact.metadata.name for a in result.data] == ["a-1"]


@pytest.mark.asyncio
async def test_readiness_ignores_weights_nested_below_the_prefix():
    """aim-engine reads the PEFT files at the top level of the adapter prefix, so weights buried a
    directory deeper leave the adapter not ready — and the listing says so definitely, never
    Unknown."""
    nested = _adapter_resource("nested", source_uri=f"s3://{MINIO_BUCKET}/{_ADAPTERS_ROOT}nested/")
    minio_client = _scanning_minio(
        f"{_ADAPTERS_ROOT}nested/{ADAPTER_MANIFEST_FILENAME}",
        *_peft_keys(f"{_ADAPTERS_ROOT}nested/checkpoint-1/"),
    )
    with _patch_list([nested]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=minio_client,
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, readiness=[ReadinessState.NOT_READY]),
        )

    assert [a.artifact.metadata.name for a in result.data] == ["nested"]
    minio_client.stat_object.assert_not_called()


@pytest.mark.asyncio
async def test_list_survives_a_storage_sweep_failure():
    """A sweep that cannot reach storage degrades to the per-item stat rather than failing a
    listing that is otherwise answerable."""
    minio_client = _scanning_minio()
    minio_client.client.list_objects.side_effect = OSError("storage unreachable")
    minio_client.stat_object.side_effect = None
    with _patch_list([_adapter_resource("a-1")]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=minio_client,
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, readiness=[ReadinessState.READY]),
        )

    assert [a.artifact.metadata.name for a in result.data] == ["a-1"]


@pytest.mark.asyncio
async def test_list_weights_filter_drops_rows_that_do_not_match():
    """A readiness filter has to hold for the whole collection before it can be paginated, so it is
    applied before the page is sliced rather than to the rows that happen to land on it."""
    ready = _adapter_resource("ready-one", source_uri=f"s3://{MINIO_BUCKET}/{_ADAPTERS_ROOT}a/")
    elsewhere = _adapter_resource("elsewhere", source_uri=f"s3://{MINIO_BUCKET}/some-other-tree/x/")

    def stat(bucket: str, key: str) -> None:
        # Only the first adapter's weights are all present; the other's stats keep failing, so it
        # resolves to Unknown and the filter has to drop it.
        if not key.startswith(f"{_ADAPTERS_ROOT}a/"):
            raise _s3_error("SlowDown")

    minio_client = _unreadable_minio()
    minio_client.stat_object.side_effect = stat
    with _patch_list([ready, elsewhere]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=minio_client,
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, readiness=[ReadinessState.READY]),
        )

    assert [a.artifact.metadata.name for a in result.data] == ["ready-one"]
    assert result.pagination.total == 1


@pytest.mark.asyncio
async def test_readiness_filter_answers_registered_adapters_from_one_listing():
    """Filtering on readiness sweeps storage even though only registered adapters were asked for.
    One recursive listing settles every prefix in the tree; the alternative is a stat per CR against
    a thread pool the whole service shares, which a large project would monopolise."""
    resources = [
        _adapter_resource(f"a-{i}", source_uri=f"s3://{MINIO_BUCKET}{'/'}{_ADAPTERS_ROOT}a-{i}/") for i in range(5)
    ]
    minio_client = _scanning_minio(*[k for i in range(5) for k in _peft_keys(f"{_ADAPTERS_ROOT}a-{i}/")])

    with _patch_list(resources):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=minio_client,
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, readiness=[ReadinessState.READY]),
        )

    assert result.pagination.total == 5
    minio_client.client.list_objects.assert_called_once()
    # _scanning_minio's stats always fail, so any fallback would have resolved these to Unknown and
    # the filter would have dropped them.
    minio_client.stat_object.assert_not_called()


@pytest.mark.asyncio
async def test_readiness_filter_still_stats_adapters_stored_outside_the_tree():
    """The sweep only covers the platform's own tree, so an adapter sourced from elsewhere is still
    resolved individually rather than being judged on a listing that never looked at it."""
    outside = _adapter_resource("elsewhere", source_uri=f"s3://{MINIO_BUCKET}/other-tree/x/")
    minio_client = _scanning_minio(*_peft_keys(f"{_ADAPTERS_ROOT}a/"))
    minio_client.stat_object.side_effect = None

    with _patch_list([outside]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=minio_client,
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, readiness=[ReadinessState.READY]),
        )

    assert [a.artifact.metadata.name for a in result.data] == ["elsewhere"]
    assert {c.args[1] for c in minio_client.stat_object.call_args_list} == set(_peft_keys("other-tree/x/"))


@pytest.mark.asyncio
async def test_list_adapter_outside_the_adapter_tree_is_still_listed():
    """Only the tree the platform allocates is swept, but a record pointing elsewhere is a record
    all the same — it falls back to a per-item stat rather than disappearing from the list."""
    elsewhere = _adapter_resource("elsewhere", source_uri=f"s3://{MINIO_BUCKET}/some-other-tree/x/")
    minio_client = _scanning_minio()
    with _patch_list([elsewhere]):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=minio_client,
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert [a.artifact.metadata.name for a in result.data] == ["elsewhere"]
    assert result.data[0].storage.readiness == ReadinessState.UNKNOWN
    # Unknown has to mean "the stat ran and could not answer", not "nobody looked" — without this
    # the assertion above would pass just as well if the fallback had silently never fired.
    assert {c.args for c in minio_client.stat_object.call_args_list} == {
        (MINIO_BUCKET, key) for key in _peft_keys("some-other-tree/x/")
    }


def _deployed_service(resolved: ResolvedRef | None) -> AIMServiceResource:
    """An AIMService carrying the profile aim-engine resolved for it, or nothing resolved yet."""
    return AIMServiceResource(
        metadata=K8sMetadata(name="deployment-1", namespace="test-namespace"),
        status=AIMServiceStatusFields(resolved_profile=resolved),
    )


def _resolved_profile(model_id: str | None, features: list[str] | None = None) -> AIMProfileResource:
    """A profile as the deployment resolved it: the weights it serves and what its runtime supports.

    Defaults to advertising the adapter capability, since that is the precondition every servable
    verdict is measured under; a test about a runtime that cannot host adapters passes its own list.
    """
    return AIMProfileResource(
        metadata=K8sMetadata(name="profile-1"),
        spec=AIMProfileSpec(model_id=model_id, features=[ADAPTER_PROFILE_FEATURE] if features is None else features),
    )


@contextmanager
def _patch_deployment(
    service: AIMServiceResource | None,
    profile: AIMProfileResource | None = None,
) -> Iterator[SimpleNamespace]:
    """Stub the deployment read and the two scoped profile reads the verdict is answered from.

    The scope dispatch itself is left unstubbed, so a test asserting which scope was consulted
    exercises the real choice. Both lookups return the same resource, so that assertion proves
    itself from the call rather than from the verdict happening to differ.
    """
    with (
        patch("app.artifacts.service.get_aim_service_by_id", AsyncMock(return_value=service)) as deployment,
        patch("app.aims.gateway.get_aim_profile_by_name", AsyncMock(return_value=profile)) as namespaced,
        patch("app.aims.gateway.get_aim_cluster_profile_by_name", AsyncMock(return_value=profile)) as cluster,
    ):
        yield SimpleNamespace(deployment=deployment, namespaced_profile=namespaced, cluster_profile=cluster)


_DEPLOYMENT_ID = UUID("11111111-2222-3333-4444-555555555555")

_CLUSTER_RESOLUTION = ResolvedRef(name="profile-1", scope=ResolutionScope.CLUSTER)


@pytest.mark.asyncio
async def test_list_leaves_servable_unset_when_the_query_does_not_ask():
    """Without a deployment to measure against, no verdict is reported and no cluster read happens —
    a listing that nobody asked a servability question of must not pay for one."""
    with (
        _patch_list([_adapter_resource("a-1", compatible_with=["org/base-model"])]),
        _patch_deployment(_deployed_service(_CLUSTER_RESOLUTION), _resolved_profile("org/base-model")) as gateways,
    ):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10),
        )

    assert [a.servable for a in result.data] == [None]
    gateways.deployment.assert_not_awaited()
    gateways.namespaced_profile.assert_not_awaited()
    gateways.cluster_profile.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_marks_a_row_servable_when_the_deployment_runs_weights_it_declares():
    """An adapter naming the weights the deployment's resolved profile serves is reported servable,
    so a caller choosing an adapter for that deployment does not have to compare model ids itself."""
    with (
        _patch_list([_adapter_resource("a-1", compatible_with=["org/base-model"])]),
        _patch_deployment(_deployed_service(_CLUSTER_RESOLUTION), _resolved_profile("org/base-model")),
    ):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, servable_by=_DEPLOYMENT_ID),
        )

    assert [a.servable for a in result.data] == [True]


@pytest.mark.asyncio
async def test_list_marks_a_row_unservable_when_the_adapter_declares_other_weights():
    """A model groups variants built from different weights, so an adapter built for another set is
    a definite no even though both sit under the same model."""
    with (
        _patch_list([_adapter_resource("a-1", compatible_with=["org/other-model"])]),
        _patch_deployment(_deployed_service(_CLUSTER_RESOLUTION), _resolved_profile("org/base-model")),
    ):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, servable_by=_DEPLOYMENT_ID),
        )

    assert [a.servable for a in result.data] == [False]


@pytest.mark.asyncio
async def test_list_marks_every_row_unservable_when_the_profile_cannot_host_adapters():
    """A runtime without the adapter capability can load none of them, and that is a settled no
    rather than an unknown. The stand-in for "no weights on offer" must match nothing, including an
    adapter that happens to declare the profile's own model."""
    adapters = [
        _adapter_resource("declares-the-profile-model", compatible_with=["org/base-model"]),
        _adapter_resource("declares-another-model", compatible_with=["org/other-model"]),
    ]
    with (
        _patch_list(adapters),
        _patch_deployment(
            _deployed_service(_CLUSTER_RESOLUTION),
            _resolved_profile("org/base-model", features=["quantization"]),
        ),
    ):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, servable_by=_DEPLOYMENT_ID),
        )

    assert {a.artifact.metadata.name: a.servable for a in result.data} == {
        "declares-the-profile-model": False,
        "declares-another-model": False,
    }


@pytest.mark.asyncio
async def test_list_marks_a_row_unservable_when_the_profile_names_no_weights():
    """A profile that advertises adapter support but names no weights can be matched by nothing, and
    an adapter declaring no bases matches nothing either — the pair settles to a no, not an error."""
    with (
        _patch_list([_adapter_resource("a-1", compatible_with=None)]),
        _patch_deployment(_deployed_service(_CLUSTER_RESOLUTION), _resolved_profile(None)),
    ):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, servable_by=_DEPLOYMENT_ID),
        )

    assert [a.servable for a in result.data] == [False]


@pytest.mark.asyncio
async def test_list_refuses_to_measure_against_a_deployment_that_does_not_exist():
    """Naming a deployment nothing can be read from is a mistake in the request, not an answer.
    Serving the page with every verdict absent would read to the caller as a settled "none of
    these", so the listing is refused and the caller is told the deployment is the problem."""
    with (
        _patch_list([_adapter_resource("a-1", compatible_with=["org/base-model"])]),
        _patch_deployment(None),
        pytest.raises(NotFoundException, match=str(_DEPLOYMENT_ID)),
    ):
        await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, servable_by=_DEPLOYMENT_ID),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resolved",
    [None, ResolvedRef(namespace="test-namespace")],
    ids=["nothing_resolved", "reference_without_a_name"],
)
async def test_list_leaves_servable_unknown_until_the_deployment_resolves_a_profile(resolved):
    """Until aim-engine records which profile a deployment resolved, what it serves is unknown — and
    a half-written reference naming no profile is just as unanswerable as no reference at all."""
    with (
        _patch_list([_adapter_resource("a-1", compatible_with=["org/base-model"])]),
        _patch_deployment(_deployed_service(resolved), _resolved_profile("org/base-model")) as gateways,
    ):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, servable_by=_DEPLOYMENT_ID),
        )

    assert all(a.servable is None for a in result.data)
    # Nothing to look up, so neither scope is consulted — without this the verdict alone would pass
    # just as well if the service had read a profile named by nothing.
    gateways.namespaced_profile.assert_not_awaited()
    gateways.cluster_profile.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_leaves_servable_unknown_when_the_resolved_profile_is_missing():
    """A profile the deployment names but that no longer exists leaves the weights unknown, rather
    than being read as a deployment that serves nothing."""
    with (
        _patch_list([_adapter_resource("a-1", compatible_with=["org/base-model"])]),
        _patch_deployment(_deployed_service(_CLUSTER_RESOLUTION), None),
    ):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, servable_by=_DEPLOYMENT_ID),
        )

    assert all(a.servable is None for a in result.data)


@pytest.mark.asyncio
async def test_list_reads_the_namespaced_profile_the_deployment_resolved():
    """A resolution stating Namespace scope is read from that namespace: a service-owned profile
    copy shadows the cluster catalogue entry of the same name, so the cluster lookup must not
    decide."""
    kube_client = _kube_client()
    with (
        _patch_list([_adapter_resource("a-1", compatible_with=["org/base-model"])]),
        _patch_deployment(
            _deployed_service(
                ResolvedRef(name="profile-1", namespace="test-namespace", scope=ResolutionScope.NAMESPACE)
            ),
            _resolved_profile("org/base-model"),
        ) as gateways,
    ):
        result = await list_project_adapter_artifacts(
            kube_client=kube_client,
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, servable_by=_DEPLOYMENT_ID),
        )

    gateways.namespaced_profile.assert_awaited_once_with(kube_client, "test-namespace", "profile-1")
    gateways.cluster_profile.assert_not_awaited()
    assert [a.servable for a in result.data] == [True]


@pytest.mark.asyncio
async def test_list_reads_the_cluster_profile_the_deployment_resolved():
    """A resolution stating Cluster scope is read from the cluster catalogue rather than looked for
    in the project, where a same-named namespaced profile serving other weights may sit."""
    kube_client = _kube_client()
    with (
        _patch_list([_adapter_resource("a-1", compatible_with=["org/base-model"])]),
        _patch_deployment(_deployed_service(_CLUSTER_RESOLUTION), _resolved_profile("org/base-model")) as gateways,
    ):
        result = await list_project_adapter_artifacts(
            kube_client=kube_client,
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, servable_by=_DEPLOYMENT_ID),
        )

    gateways.deployment.assert_awaited_once_with(kube_client, "test-namespace", _DEPLOYMENT_ID)
    gateways.cluster_profile.assert_awaited_once_with(kube_client, "profile-1")
    gateways.namespaced_profile.assert_not_awaited()
    assert [a.servable for a in result.data] == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope",
    [None, ResolutionScope.MERGED, ResolutionScope.UNKNOWN, "SomethingNewerThanThisCode"],
    ids=["no_scope", "merged", "unknown", "unrecognised"],
)
async def test_list_falls_back_to_either_scope_when_the_resolution_states_none_it_can_act_on(scope):
    """A reference that identifies no single object to read is answered from whichever scope has
    the name, project copy first. Refusing to look would leave every row unevaluated over a scope
    field, and picking one scope blind would risk reading a namesake's weights."""
    kube_client = _kube_client()
    with (
        _patch_list([_adapter_resource("a-1", compatible_with=["org/base-model"])]),
        _patch_deployment(
            _deployed_service(ResolvedRef(name="profile-1", scope=scope)),
            _resolved_profile("org/base-model"),
        ) as gateways,
    ):
        result = await list_project_adapter_artifacts(
            kube_client=kube_client,
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=10, servable_by=_DEPLOYMENT_ID),
        )

    gateways.namespaced_profile.assert_awaited_once_with(kube_client, "test-namespace", "profile-1")
    gateways.cluster_profile.assert_awaited_once_with(kube_client, "profile-1")
    assert [a.servable for a in result.data] == [True]


@pytest.mark.asyncio
async def test_list_resolves_the_deployment_once_for_the_whole_page():
    """Every row on a page is measured against the same deployment, so the profile is resolved once
    for the page rather than once per row — a page of adapters must not multiply into cluster reads."""
    adapters = [_adapter_resource(f"a-{i}", compatible_with=["org/base-model"]) for i in range(5)]
    with (
        _patch_list(adapters),
        _patch_deployment(_deployed_service(_CLUSTER_RESOLUTION), _resolved_profile("org/base-model")) as gateways,
    ):
        result = await list_project_adapter_artifacts(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            query=ListArtifactsQuery(page=1, page_size=3, servable_by=_DEPLOYMENT_ID),
        )

    assert [a.servable for a in result.data] == [True, True, True]
    assert gateways.deployment.await_count == 1
    assert gateways.cluster_profile.await_count == 1


@pytest.mark.asyncio
async def test_get_returns_the_adapter_projection():
    """A get returns the named adapter in the same shape the list returns."""
    with patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=_adapter_resource("a-1"))):
        result = await get_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            name="a-1",
        )

    assert result.artifact.metadata.name == "a-1"
    assert result.storage.readiness == ReadinessState.UNKNOWN


@pytest.mark.asyncio
async def test_get_reports_unknown_readiness_when_minio_client_unavailable():
    """No Minio client (unconfigured storage) degrades readiness to Unknown rather than failing
    the get."""
    with patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=_adapter_resource("a-1"))):
        result = await get_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=None,
            namespace="test-namespace",
            name="a-1",
        )

    assert result.storage.readiness == ReadinessState.UNKNOWN


@pytest.mark.asyncio
async def test_get_artifact_of_non_adapter_type_raises_not_found():
    """A platform-managed CR of a different type (e.g. a model) is outside this API's collection,
    even though the managed-by label matches."""
    non_adapter = _adapter_resource("a-1", artifact_type="model")
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=non_adapter)),
        pytest.raises(NotFoundException, match="a-1"),
    ):
        await get_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            name="a-1",
        )


@pytest.mark.asyncio
async def test_get_missing_artifact_raises_not_found():
    """A get for an absent artifact raises NotFoundException (mapped to 404)."""
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=None)),
        pytest.raises(NotFoundException, match="a-1"),
    ):
        await get_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            name="a-1",
        )


@pytest.mark.asyncio
async def test_get_artifact_outside_platform_collection_raises_not_found():
    """An artifact the platform did not author is absent from this API, even by name."""
    foreign = _adapter_resource("a-1", managed_by="some-other-operator")
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=foreign)),
        pytest.raises(NotFoundException, match="a-1"),
    ):
        await get_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_unreadable_minio(),
            namespace="test-namespace",
            name="a-1",
        )


@pytest.mark.asyncio
async def test_delete_returns_true_when_accepted():
    """An unreferenced artifact is deleted and the accepted delete reports True (202)."""
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=_adapter_resource("a-1"))),
        patch("app.artifacts.service.list_aim_services_referencing_artifact", AsyncMock(return_value=set())),
        patch("app.artifacts.service.delete_aim_artifact", AsyncMock(return_value=True)) as mock_delete,
    ):
        result = await delete_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_sweeping_minio(),
            namespace="test-namespace",
            name="a-1",
        )

    assert result is True
    mock_delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_returns_true_for_fine_tuning_authored_artifact():
    """Adapters produced by the fine-tuning engine are part of the collection and deletable."""
    produced = _adapter_resource("a-1", managed_by="fine-tuning")
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=produced)),
        patch("app.artifacts.service.list_aim_services_referencing_artifact", AsyncMock(return_value=set())),
        patch("app.artifacts.service.delete_aim_artifact", AsyncMock(return_value=True)),
    ):
        result = await delete_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_sweeping_minio(),
            namespace="test-namespace",
            name="a-1",
        )

    assert result is True


@pytest.mark.asyncio
async def test_delete_returns_false_when_already_gone():
    """A delete of an artifact that no longer exists reports False (204) without touching storage."""
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=None)),
        patch("app.artifacts.service.delete_aim_artifact", AsyncMock()) as mock_delete,
    ):
        result = await delete_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_sweeping_minio(),
            namespace="test-namespace",
            name="a-1",
        )

    assert result is False
    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_returns_false_when_removed_concurrently():
    """An artifact deleted between the read and the delete still reports False (204)."""
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=_adapter_resource("a-1"))),
        patch("app.artifacts.service.list_aim_services_referencing_artifact", AsyncMock(return_value=set())),
        patch("app.artifacts.service.delete_aim_artifact", AsyncMock(return_value=False)),
    ):
        result = await delete_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_sweeping_minio(),
            namespace="test-namespace",
            name="a-1",
        )

    assert result is False


@pytest.mark.asyncio
async def test_delete_leaves_artifact_outside_platform_collection_untouched():
    """A name that resolves to a foreign artifact reports 204 rather than destroying it."""
    foreign = _adapter_resource("a-1", managed_by="some-other-operator")
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=foreign)),
        patch("app.artifacts.service.delete_aim_artifact", AsyncMock()) as mock_delete,
    ):
        result = await delete_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_sweeping_minio(),
            namespace="test-namespace",
            name="a-1",
        )

    assert result is False
    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_leaves_non_adapter_type_artifact_untouched():
    """A platform-managed CR of a different type (e.g. a model) is outside this API's collection,
    even though the managed-by label matches — a guessed name must not delete it."""
    non_adapter = _adapter_resource("a-1", artifact_type="model")
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=non_adapter)),
        patch("app.artifacts.service.delete_aim_artifact", AsyncMock()) as mock_delete,
    ):
        result = await delete_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_sweeping_minio(),
            namespace="test-namespace",
            name="a-1",
        )

    assert result is False
    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_blocked_when_referenced_by_service():
    """A live AIMService reference blocks deletion with a conflict and never issues the delete."""
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=_adapter_resource("a-1"))),
        patch(
            "app.artifacts.service.list_aim_services_referencing_artifact",
            AsyncMock(return_value={"serving-svc"}),
        ),
        patch("app.artifacts.service.delete_aim_artifact", AsyncMock()) as mock_delete,
        pytest.raises(DeletionConflictException, match="serving-svc"),
    ):
        await delete_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_sweeping_minio(),
            namespace="test-namespace",
            name="a-1",
        )

    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_conflict_names_the_force_override():
    """The refusal tells the caller how to override it, not just that it was refused."""
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=_adapter_resource("a-1"))),
        patch(
            "app.artifacts.service.list_aim_services_referencing_artifact",
            AsyncMock(return_value={"serving-svc"}),
        ),
        patch("app.artifacts.service.delete_aim_artifact", AsyncMock()),
        pytest.raises(DeletionConflictException, match="force=true"),
    ):
        await delete_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_sweeping_minio(),
            namespace="test-namespace",
            name="a-1",
        )


@pytest.mark.asyncio
async def test_force_deletes_despite_referencing_service():
    """force waives the reference guard and the artifact is deleted anyway."""
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=_adapter_resource("a-1"))),
        patch(
            "app.artifacts.service.list_aim_services_referencing_artifact",
            AsyncMock(return_value={"serving-svc"}),
        ),
        patch("app.artifacts.service.delete_aim_artifact", AsyncMock(return_value=True)) as mock_delete,
    ):
        deleted = await delete_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_sweeping_minio(),
            namespace="test-namespace",
            name="a-1",
            force=True,
        )

    assert deleted is True
    mock_delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_force_leaves_referencing_services_untouched():
    """force removes only the artifact — the deployments serving it are not deleted or detached."""
    referencing = AsyncMock(return_value={"serving-svc"})
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=_adapter_resource("a-1"))),
        patch("app.artifacts.service.list_aim_services_referencing_artifact", referencing),
        patch("app.artifacts.service.delete_aim_artifact", AsyncMock(return_value=True)),
    ):
        kube_client = _kube_client()
        kube_client.custom_objects = AsyncMock()
        await delete_project_adapter_artifact(
            kube_client=kube_client,
            minio_client=_sweeping_minio(),
            namespace="test-namespace",
            name="a-1",
            force=True,
        )

    # No AIMService write of any kind: the guard is waived, the deployments are left as they are.
    kube_client.custom_objects.delete_namespaced_custom_object.assert_not_called()
    kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
async def test_force_does_not_reach_artifacts_outside_platform_collection():
    """force waives the reference guard, never the ownership boundary."""
    foreign = _adapter_resource("a-1", managed_by="some-other-operator")
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=foreign)),
        patch("app.artifacts.service.delete_aim_artifact", AsyncMock()) as mock_delete,
    ):
        deleted = await delete_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_sweeping_minio(),
            namespace="test-namespace",
            name="a-1",
            force=True,
        )

    assert deleted is False
    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_force_on_absent_artifact_still_reports_nothing_deleted():
    """force does not invent a delete for an artifact that was never there."""
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=None)),
        patch("app.artifacts.service.delete_aim_artifact", AsyncMock()) as mock_delete,
    ):
        deleted = await delete_project_adapter_artifact(
            kube_client=_kube_client(),
            minio_client=_sweeping_minio(),
            namespace="test-namespace",
            name="gone",
            force=True,
        )

    assert deleted is False
    mock_delete.assert_not_called()


# ---------------------------------------------------------------------------
# Delete: reclaiming the storage AIWB allocated
# ---------------------------------------------------------------------------

_MANAGED_PREFIX = f"{_ADAPTERS_ROOT}a-1/"
_MANAGED_URI = f"s3://{MINIO_BUCKET}/{_MANAGED_PREFIX}"


def _uploaded_adapter(name: str = "a-1") -> AIMArtifactResource:
    """An adapter whose weights were uploaded through this API, so AIWB owns its prefix."""
    return _adapter_resource(name, source_uri=_MANAGED_URI, managed_storage_uri=_MANAGED_URI)


@contextmanager
def _patch_delete(
    artifact: AIMArtifactResource | None,
    referencing: set[str] | None = None,
    claimants: list[AIMArtifactResource] | None = None,
    unparseable_claimants: dict[str, str] | None = None,
    sweep: AsyncMock | None = None,
    marker: AsyncMock | None = None,
) -> Iterator[tuple[AsyncMock, AsyncMock]]:
    """Stub the delete path's reads and yield its two writes: the storage sweep and the CR delete.

    ``claimants`` is what the unselected artifact listing holds; it defaults to just the artifact
    under deletion, which is what the cluster really holds when nothing else points at the prefix.
    ``unparseable_claimants`` adds artifacts that never parse into a resource at all, keyed by name
    to the source URI they record — what the cluster holds when a neighbour is malformed or only
    half written. ``marker`` captures the follow-up removal of the prefix's directory marker.
    """
    mock_sweep = sweep if sweep is not None else AsyncMock()
    mock_delete = AsyncMock(return_value=True)
    listed = claimants if claimants is not None else ([artifact] if artifact is not None else [])
    source_uris = {a.metadata.name: a.spec.source_uri for a in listed if a.spec.source_uri}
    source_uris.update(unparseable_claimants or {})
    with (
        patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=artifact)),
        patch(
            "app.artifacts.service.list_aim_services_referencing_artifact",
            AsyncMock(return_value=referencing or set()),
        ),
        patch("app.artifacts.service.list_aim_artifact_source_uris", AsyncMock(return_value=source_uris)),
        patch("app.artifacts.service.delete_from_s3", mock_sweep),
        patch("app.artifacts.service.delete_object_from_s3", marker if marker is not None else AsyncMock()),
        patch("app.artifacts.service.delete_aim_artifact", mock_delete),
    ):
        yield mock_sweep, mock_delete


async def _delete(artifact_name: str = "a-1", force: bool = False) -> bool:
    """Issue the delete under test against reachable object storage."""
    return await delete_project_adapter_artifact(
        kube_client=_kube_client(),
        minio_client=_sweeping_minio(),
        namespace="test-namespace",
        name=artifact_name,
        force=force,
    )


async def _delete_without_storage(artifact_name: str = "a-1") -> bool:
    """Issue the delete under test in an installation with no object storage configured."""
    return await delete_project_adapter_artifact(
        kube_client=_kube_client(),
        minio_client=None,
        namespace="test-namespace",
        name=artifact_name,
    )


@pytest.mark.asyncio
async def test_delete_reclaims_the_storage_it_allocated():
    """An uploaded adapter's weights are swept, and reported as adapter weights rather than a model's."""
    with _patch_delete(_uploaded_adapter()) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    assert sweep.await_args.args[0] == _MANAGED_PREFIX
    assert sweep.await_args.kwargs["operation"] == "deleting adapter weights"


@pytest.mark.asyncio
async def test_delete_of_onboarded_adapter_leaves_the_callers_files_alone():
    """Files the caller owned before onboarding are not the platform's to reclaim."""
    onboarded = _adapter_resource("a-1", source_uri=f"s3://{MINIO_BUCKET}/test-namespace/my-own-weights/")
    with _patch_delete(onboarded) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_of_adapter_predating_the_annotation_leaves_storage_alone():
    """Sitting in the platform's adapter tree is not proof the platform put it there.

    An artifact created before deletion recorded its own storage is indistinguishable from one
    onboarded against caller-owned files, so its prefix is left rather than risk deleting theirs.
    """
    legacy = _adapter_resource("a-1", source_uri=_MANAGED_URI)
    with _patch_delete(legacy) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()


_RUN_ID = "6f87238d-93ef-451c-95da-4a83f467b6c6"
_RUN_PREFIX = f"test-namespace/finetuned-models/org/base-model/{_RUN_ID}/"


def _fine_tuned_adapter(
    source_uri: str = f"s3://{MINIO_BUCKET}/{_RUN_PREFIX}checkpoint-final-adapter",
) -> AIMArtifactResource:
    """An adapter a fine-tuning job produced, recording the weights directory inside its run folder."""
    return _adapter_resource("a-1", managed_by="fine-tuning", source_uri=source_uri)


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_dir", ["checkpoint-final-adapter", "adapter", "checkpoint-final-adapter/"])
async def test_delete_of_fine_tuned_adapter_reclaims_its_whole_run_folder(terminal_dir: str) -> None:
    """The run's manifest and metadata sit beside the weights, so the sweep takes the run, not just the weights."""
    marker = AsyncMock()
    produced = _fine_tuned_adapter(f"s3://{MINIO_BUCKET}/{_RUN_PREFIX}{terminal_dir}")
    with _patch_delete(produced, marker=marker) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    assert [call.args[0] for call in sweep.await_args_list] == [_RUN_PREFIX]
    assert [call.args[0] for call in marker.await_args_list] == [_RUN_PREFIX]


@pytest.mark.asyncio
async def test_failed_sweep_of_fine_tuned_adapter_leaves_the_artifact_in_place():
    """The run folder is only reclaimable while a CR still points at it, so a failed sweep keeps the CR."""
    sweep = AsyncMock(side_effect=ExternalServiceError("object storage unreachable"))
    with (
        _patch_delete(_fine_tuned_adapter(), sweep=sweep) as (_, delete),
        pytest.raises(ExternalServiceError, match="unreachable"),
    ):
        await _delete()

    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_of_fine_tuned_adapter_without_object_storage_is_refused():
    """Dropping the CR while storage is unreachable would strand gigabytes of weights nothing tracks."""
    with (
        _patch_delete(_fine_tuned_adapter()) as (sweep, delete),
        pytest.raises(ExternalServiceError, match="a-1"),
    ):
        await _delete_without_storage()

    delete.assert_not_awaited()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_fine_tuned_run_folder_another_adapter_points_into_is_left_in_place():
    """An adapter onboarded from the same run's weights would break if the run were swept."""
    target = _fine_tuned_adapter()
    onboarded = _adapter_resource("a-2", source_uri=f"s3://{MINIO_BUCKET}/{_RUN_PREFIX}checkpoint-final-adapter/")
    with _patch_delete(target, claimants=[target, onboarded]) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_uri",
    [
        pytest.param(_MANAGED_URI, id="adapter-upload-tree"),
        pytest.param(f"s3://{MINIO_BUCKET}/other-project/finetuned-models/org/m/{_RUN_ID}/adapter", id="other-project"),
        pytest.param(f"s3://other-bucket/{_RUN_PREFIX}checkpoint-final-adapter", id="other-bucket"),
        pytest.param(f"s3://{MINIO_BUCKET}/test-namespace/finetuned-models/{_RUN_ID}/adapter", id="too-shallow"),
        pytest.param(f"s3://{MINIO_BUCKET}/test-namespace/finetuned-models/org/m/run-1/adapter", id="run-not-a-uuid"),
        pytest.param(f"s3://{MINIO_BUCKET}/{_RUN_PREFIX}checkpoint-final", id="not-an-adapter-dir"),
        pytest.param(f"s3://{MINIO_BUCKET}/{_RUN_PREFIX}", id="run-folder-itself"),
        pytest.param(
            f"s3://{MINIO_BUCKET}/test-namespace/finetuned-models/../adapters/{_RUN_ID}/adapter", id="dot-dot"
        ),
        pytest.param(f"s3://{MINIO_BUCKET}//{_RUN_PREFIX}adapter", id="doubled-leading-separator"),
        pytest.param(f"s3://{MINIO_BUCKET}/{_RUN_PREFIX.replace('/org/', '//org/')}adapter", id="empty-segment"),
    ],
)
async def test_fine_tuned_adapter_outside_a_run_folder_leaves_storage_alone(source_uri: str) -> None:
    """The recorded source is patchable, so only this project's run-folder shape is ever swept."""
    with _patch_delete(_fine_tuned_adapter(source_uri)) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_onboarded_adapter_pointing_at_a_fine_tuning_run_leaves_it_alone():
    """Only the adapter the training job authored owns its run; one onboarded from it does not."""
    onboarded = _adapter_resource("a-1", source_uri=f"s3://{MINIO_BUCKET}/{_RUN_PREFIX}checkpoint-final-adapter")
    with _patch_delete(onboarded) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_of_absent_artifact_touches_no_storage():
    """Nothing is known about an artifact that is already gone, so nothing is swept."""
    with _patch_delete(None) as (sweep, delete):
        result = await _delete("gone")

    assert result is False
    delete.assert_not_awaited()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_of_foreign_artifact_touches_no_storage():
    """The ownership boundary is checked before the sweep, so a foreign record's files survive."""
    foreign = _adapter_resource("a-1", managed_by="some-other-operator", managed_storage_uri=_MANAGED_URI)
    with _patch_delete(foreign) as (sweep, delete):
        result = await _delete()

    assert result is False
    delete.assert_not_awaited()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_storage_reclaim_leaves_the_artifact_in_place():
    """A sweep that fails aborts the delete, so the caller keeps a visible artifact to retry."""
    sweep = AsyncMock(side_effect=ExternalServiceError("object storage unreachable"))
    with (
        _patch_delete(_uploaded_adapter(), sweep=sweep) as (_, delete),
        pytest.raises(ExternalServiceError, match="unreachable"),
    ):
        await _delete()

    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_without_object_storage_refuses_to_drop_an_uploaded_adapter():
    """Unreachable storage is a failed delete, never a silent one that orphans the weights."""
    with (
        _patch_delete(_uploaded_adapter()) as (sweep, delete),
        pytest.raises(ExternalServiceError, match="a-1"),
    ):
        await _delete_without_storage()

    delete.assert_not_awaited()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_without_object_storage_still_removes_an_adapter_owning_none():
    """A delete that would sweep nothing does not need storage to be reachable at all."""
    with _patch_delete(_adapter_resource("a-1")) as (sweep, delete):
        result = await _delete_without_storage()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_claimed_by_another_adapter_is_left_in_place():
    """Sweeping weights a second adapter still points at would break it, so the files stay."""
    target = _uploaded_adapter()
    other = _adapter_resource("a-2", source_uri=_MANAGED_URI)
    with _patch_delete(target, claimants=[target, other]) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_claimed_at_a_nested_prefix_is_left_in_place():
    """A neighbour onboarded inside the prefix goes with it, because the sweep is recursive."""
    target = _uploaded_adapter()
    nested = _adapter_resource("a-2", source_uri=f"s3://{MINIO_BUCKET}/{_MANAGED_PREFIX}checkpoint-1/")
    with _patch_delete(target, claimants=[target, nested]) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_claimed_at_an_enclosing_prefix_does_not_block_the_sweep():
    """Files above the swept prefix survive it, and blocking on them would strand every adapter."""
    target = _uploaded_adapter()
    enclosing = _adapter_resource("a-2", source_uri=f"s3://{MINIO_BUCKET}/{_ADAPTERS_ROOT}")
    with _patch_delete(target, claimants=[target, enclosing]) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    assert sweep.await_args.args[0] == _MANAGED_PREFIX


@pytest.mark.asyncio
async def test_storage_claimed_by_a_foreign_record_is_left_in_place():
    """A record this API does not expose claims a prefix just as effectively as one it authored."""
    target = _uploaded_adapter()
    foreign = _adapter_resource("a-2", managed_by="some-other-operator", source_uri=_MANAGED_URI)
    with _patch_delete(target, claimants=[target, foreign]) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_claimed_by_an_unparseable_record_is_left_in_place():
    """A neighbour too malformed to read back is still pointing at the prefix, so the files stay.

    The typed listing drops an artifact of an unexpected shape, which would read as "nothing claims
    this" and sweep weights that record still owns.
    """
    target = _uploaded_adapter()
    with _patch_delete(target, unparseable_claimants={"a-2": _MANAGED_URI}) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_unparseable_record_claiming_a_different_prefix_does_not_block_the_sweep():
    """Being unreadable is not itself an objection: only pointing at these files is."""
    target = _uploaded_adapter()
    with _patch_delete(target, unparseable_claimants={"a-2": f"s3://{MINIO_BUCKET}/{_ADAPTERS_ROOT}a-2/"}) as (
        sweep,
        delete,
    ):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_awaited_once()


@pytest.mark.asyncio
async def test_storage_no_neighbour_claims_is_reclaimed():
    """A project full of other adapters still sweeps, as long as none of them owns this prefix."""
    target = _uploaded_adapter()
    neighbours = [_adapter_resource(f"a-{i}", source_uri=f"s3://{MINIO_BUCKET}/{_ADAPTERS_ROOT}a-{i}/") for i in (2, 3)]
    with _patch_delete(target, claimants=[target, *neighbours]) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    assert sweep.await_args.args[0] == _MANAGED_PREFIX


@pytest.mark.asyncio
async def test_artifact_being_deleted_does_not_claim_its_own_storage():
    """The artifact under deletion appears in the listing; counting it would block every sweep."""
    target = _uploaded_adapter()
    with _patch_delete(target, claimants=[target]) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_awaited_once()


@pytest.mark.asyncio
async def test_same_prefix_in_another_bucket_does_not_claim_the_storage():
    """The swept keys live in one bucket, so the same path elsewhere names different files."""
    target = _uploaded_adapter()
    elsewhere = _adapter_resource("a-2", source_uri=f"s3://other-bucket/{_MANAGED_PREFIX}")
    with _patch_delete(target, claimants=[target, elsewhere]) as (sweep, delete):
        result = await _delete()

    assert result is True
    sweep.assert_awaited_once()


@pytest.mark.asyncio
async def test_storage_recorded_outside_the_projects_adapter_tree_is_not_swept():
    """The annotation is caller-patchable, so a delete never sweeps what it points at unchecked."""
    tampered = _adapter_resource("a-1", managed_storage_uri=f"s3://{MINIO_BUCKET}/other-project/adapters/victim/")
    with _patch_delete(tampered) as (sweep, delete), patch("app.artifacts.service.logger") as mock_logger:
        result = await _delete()

    # Skipped rather than refused: tampering must not make the artifact undeletable through the API.
    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()
    mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_storage_recorded_as_the_whole_adapter_tree_is_not_swept():
    """A prefix naming the project's entire adapter root would take every adapter with it."""
    tampered = _adapter_resource("a-1", managed_storage_uri=f"s3://{MINIO_BUCKET}/{_ADAPTERS_ROOT}")
    with _patch_delete(tampered) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_recorded_inside_another_adapters_directory_is_not_swept():
    """A prefix one level down still names files another adapter owns, so it is not the caller's."""
    tampered = _adapter_resource("a-1", managed_storage_uri=f"s3://{MINIO_BUCKET}/{_ADAPTERS_ROOT}victim/weights/")
    victim = _adapter_resource("victim", source_uri=f"s3://{MINIO_BUCKET}/{_ADAPTERS_ROOT}victim/")
    with _patch_delete(tampered, claimants=[tampered, victim]) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_nested_storage_is_not_swept_even_when_no_adapter_claims_the_directory():
    """Depth alone disqualifies a prefix: nothing points at a nested path, so nothing would object."""
    tampered = _adapter_resource("a-1", managed_storage_uri=f"s3://{MINIO_BUCKET}/{_ADAPTERS_ROOT}victim/weights/")
    with _patch_delete(tampered) as (sweep, delete), patch("app.artifacts.service.logger") as mock_logger:
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()
    mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_storage_recorded_as_a_sibling_adapters_prefix_is_not_swept():
    """A prefix beside this artifact's own is the platform's shape but not the platform's promise.

    Nothing claims a sibling that never got a CR — the upload path signs URLs before creating one —
    so the co-claimant check would raise no objection to sweeping files another caller uploaded.
    """
    sibling = _adapter_resource("a-1", managed_storage_uri=f"s3://{MINIO_BUCKET}/{_ADAPTERS_ROOT}a-2/")
    with _patch_delete(sibling) as (sweep, delete), patch("app.artifacts.service.logger") as mock_logger:
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()
    mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_storage_recorded_under_a_stale_name_is_not_swept():
    """The prefix an artifact owns is the one its own name derives to, not one that merely looks it."""
    target = _adapter_resource("a-1", managed_storage_uri=f"s3://{MINIO_BUCKET}/{_ADAPTERS_ROOT}a-1-superseded/")
    with _patch_delete(target) as (sweep, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_already_absent_counts_as_reclaimed():
    """A prefix that is already gone is the end state the delete asks for, not a failure."""
    sweep = AsyncMock(side_effect=NotFoundException("File not found in storage"))
    with _patch_delete(_uploaded_adapter(), sweep=sweep) as (_, delete):
        result = await _delete()

    assert result is True
    delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_unreachable_storage_reports_an_upstream_failure():
    """A transport failure is the storage backend's, not a bug in the request or a missing file."""
    sweep = AsyncMock(side_effect=OSError("connection reset by peer"))
    with (
        _patch_delete(_uploaded_adapter(), sweep=sweep) as (_, delete),
        pytest.raises(ExternalServiceError) as raised,
    ):
        await _delete()

    assert "connection reset by peer" in str(raised.value.detail)
    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_refusing_the_platforms_own_credentials_is_not_reported_as_the_callers_fault():
    """AIWB sweeps with its own credentials, so their rejection is an upstream fault, never a 403."""
    sweep = AsyncMock(side_effect=ForbiddenException("Access denied to storage"))
    with (
        _patch_delete(_uploaded_adapter(), sweep=sweep) as (_, delete),
        pytest.raises(ExternalServiceError) as raised,
    ):
        await _delete()

    assert "Access denied" in str(raised.value.detail)
    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_force_still_reclaims_the_storage():
    """force waives the reference check only — the weights are still reclaimed."""
    with _patch_delete(_uploaded_adapter(), referencing={"serving-svc"}) as (sweep, delete):
        result = await _delete(force=True)

    assert result is True
    delete.assert_awaited_once()
    sweep.assert_awaited_once()


# ---------------------------------------------------------------------------
# Download an artifact
# ---------------------------------------------------------------------------

_DOWNLOAD_PREFIX = f"{_ADAPTERS_ROOT}a-1/"
_DOWNLOAD_URI = f"s3://{MINIO_BUCKET}/{_DOWNLOAD_PREFIX}"
_FINE_TUNED_PREFIX = "test-namespace/finetuned-models/run-1/adapter/"
_FINE_TUNED_URI = f"s3://{MINIO_BUCKET}/{_FINE_TUNED_PREFIX}"
_EXTERNAL_URL = "https://storage.example.com/presigned"


def _listing_minio(*keys: str, size: int | None = 128, marker_size: int | None = 0) -> MagicMock:
    """A storage client whose listing of the adapter's prefix returns ``keys``.

    ``client`` is an instance attribute the real MinioClient sets in ``__init__``, so the outer
    ``spec=`` does not expose it and it is attached explicitly, specced in its own right.

    A key ending in "/" is sized by ``marker_size`` rather than ``size``, because a directory marker
    is an empty object in storage and a test naming one means the real thing. ``marker_size`` is
    what a test overrides to model the object that only looks like one.
    """
    client = MagicMock(spec=MinioClient)
    client.client = MagicMock(spec=Minio)
    client.client.list_objects.return_value = [
        SimpleNamespace(object_name=k, size=marker_size if k.endswith("/") else size) for k in keys
    ]
    return client


def _signing_minio(url: str = _EXTERNAL_URL) -> MagicMock:
    """The external-endpoint client, whose signatures are the ones callers outside the cluster use."""
    client = MagicMock(spec=MinioClient)
    client.generate_presigned_download_url.return_value = url
    return client


def _downloadable(name: str = "a-1", **overrides) -> AIMArtifactResource:  # type: ignore[no-untyped-def]
    """A complete, platform-authored adapter: the shape every download test starts from.

    Every field is a default rather than a fixture, so a test about one of them overrides it here
    instead of rebuilding the resource and drifting from what the others exercise.
    """
    overrides.setdefault("source_uri", _DOWNLOAD_URI)
    overrides.setdefault("model_id", "org/my-adapter")
    overrides.setdefault("compatible_with", ["org/base-model"])
    overrides.setdefault("rank", 16)
    return _adapter_resource(name, **overrides)


async def _download(
    artifact: AIMArtifactResource | None,
    minio_client: MagicMock,
    minio_external_client: MagicMock | None = None,
    name: str = "a-1",
    namespace: str = "test-namespace",
) -> ArtifactDownloadResponse:
    with patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=artifact)):
        return await download_project_artifact(
            kube_client=_kube_client(),
            minio_client=minio_client,
            minio_external_client=minio_external_client or _signing_minio(),
            namespace=namespace,
            name=name,
        )


@pytest.mark.asyncio
async def test_download_returns_one_link_per_file_at_the_prefix():
    """Every file the adapter is made of is addressable, by a path relative to its prefix, so the
    caller can rebuild the directory as it stands."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX), f"{_DOWNLOAD_PREFIX}README.md")

    result = await _download(_downloadable(), minio_client)

    assert {f.path for f in result.files} == {"adapter_config.json", "adapter_model.safetensors", "README.md"}
    assert all(f.method == "GET" and f.url == _EXTERNAL_URL for f in result.files)


@pytest.mark.asyncio
async def test_download_reports_the_size_storage_reports():
    """Size travels with each link so a caller can size the transfer before starting it."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX), size=4096)

    result = await _download(_downloadable(), minio_client)

    assert {f.size_bytes for f in result.files} == {4096}


@pytest.mark.asyncio
async def test_download_includes_the_recovery_manifest_when_present():
    """The manifest is part of what makes the adapter portable, so it travels with the weights."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX), f"{_DOWNLOAD_PREFIX}{ADAPTER_MANIFEST_FILENAME}")

    result = await _download(_downloadable(), minio_client)

    assert ADAPTER_MANIFEST_FILENAME in {f.path for f in result.files}


@pytest.mark.asyncio
async def test_download_links_are_signed_by_the_external_client():
    """SigV4 signs the Host header, so a URL signed for the in-cluster service name is unusable by
    the caller the link is handed to."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX))
    minio_external_client = _signing_minio()

    result = await _download(_downloadable(), minio_client, minio_external_client)

    minio_client.generate_presigned_download_url.assert_not_called()
    assert minio_external_client.generate_presigned_download_url.call_count == len(result.files)
    assert {c.kwargs["object_name"] for c in minio_external_client.generate_presigned_download_url.call_args_list} == {
        f"{_DOWNLOAD_PREFIX}adapter_config.json",
        f"{_DOWNLOAD_PREFIX}adapter_model.safetensors",
    }


@pytest.mark.asyncio
async def test_download_is_refused_when_the_signing_endpoint_is_not_externally_addressable() -> None:
    """A link signed against a host the caller cannot resolve is unrepairable, so the request is
    refused instead of answered with a 200 carrying links nobody can fetch.

    The sibling download tests need no change: their ``MagicMock(spec=MinioClient)`` answers the
    predicate with a truthy mock, so they keep taking the accepting path.
    """
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX))
    minio_external_client = _signing_minio()
    minio_external_client.is_externally_addressable.return_value = False
    minio_external_client.host = "http://filer-s3.example.svc.cluster.local:80"

    with pytest.raises(UnhealthyException, match="minio.externalUrl"):
        await _download(_downloadable(), minio_client, minio_external_client)

    minio_client.client.list_objects.assert_not_called()
    minio_external_client.generate_presigned_download_url.assert_not_called()


@pytest.mark.asyncio
async def test_download_is_served_when_the_signing_endpoint_is_externally_addressable() -> None:
    """The refusal is conditional on the endpoint, not a blanket one: an install configured with a
    reachable external address hands the links out as normal."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX))
    minio_external_client = _signing_minio()
    minio_external_client.is_externally_addressable.return_value = True

    result = await _download(_downloadable(), minio_client, minio_external_client)

    assert {f.path for f in result.files} == {"adapter_config.json", "adapter_model.safetensors"}


@pytest.mark.asyncio
async def test_download_returns_objects_nested_below_the_prefix():
    """Onboarding accepts a nested extra and signs an upload URL for it, so refusing to hand it back
    would leave a file the API itself put there unreachable. Its path comes back as stored, so the
    caller can write it where it belongs."""
    minio_client = _listing_minio(
        *_peft_keys(_DOWNLOAD_PREFIX),
        f"{_DOWNLOAD_PREFIX}checkpoint-500/optimizer.pt",
    )

    result = await _download(_downloadable(), minio_client)

    assert "checkpoint-500/optimizer.pt" in {f.path for f in result.files}
    assert minio_client.client.list_objects.call_args.kwargs["recursive"] is True


@pytest.mark.asyncio
async def test_download_of_an_adapter_whose_location_has_no_trailing_slash():
    """Recorded locations need not end in "/" — fine-tuning ones do not — and an S3 prefix is matched
    literally, so listing one without the separator would also sweep in every sibling key sharing
    those characters and hand back paths that belong to another artifact."""
    artifact = _downloadable(source_uri=f"s3://{MINIO_BUCKET}/{_FINE_TUNED_PREFIX.rstrip('/')}")
    minio_client = _listing_minio(*_peft_keys(_FINE_TUNED_PREFIX))

    result = await _download(artifact, minio_client)

    assert minio_client.client.list_objects.call_args.kwargs["prefix"] == _FINE_TUNED_PREFIX
    assert {f.path for f in result.files} == {"adapter_config.json", "adapter_model.safetensors"}


@pytest.mark.asyncio
async def test_download_of_a_fine_tuning_produced_adapter():
    """The engine stamps its own managed-by and writes to its own tree, neither of which the upload
    path produces. Such an adapter is still the platform's to hand out."""
    artifact = _downloadable(managed_by="fine-tuning", source_uri=_FINE_TUNED_URI)
    minio_client = _listing_minio(*_peft_keys(_FINE_TUNED_PREFIX))

    result = await _download(artifact, minio_client)

    assert {f.path for f in result.files} == {"adapter_config.json", "adapter_model.safetensors"}


@pytest.mark.asyncio
async def test_download_refuses_storage_outside_the_project():
    """One bucket is shared by every project, so a recorded location outside this one is never
    signed — a tampered or mis-reconciled sourceUri must not become readable links into another
    tenant's data."""
    artifact = _downloadable(source_uri=f"s3://{MINIO_BUCKET}/other-namespace/adapters/a-1/")

    with pytest.raises(ConflictException, match="not inside this project's storage"):
        await _download(artifact, _listing_minio(*_peft_keys("other-namespace/adapters/a-1/")))


@pytest.mark.asyncio
async def test_download_admits_a_cross_tenant_read_when_two_namespaces_slug_alike():
    """Unlike its neighbours, this pins a hole rather than a defence — read the assertion that way.

    Confinement compares against the caller's *slugified* namespace, so a caller in 'data--science'
    is admitted to the 'data-science/' tree: the names are distinct, the slugs are not. Nothing in
    aiwb closes that. AIRM does, by refusing to create a namespace whose slug an existing one
    already holds, and this records what aiwb is relying on it for.
    """
    prefix = "data-science/adapters/a-1/"
    artifact = _downloadable(source_uri=f"s3://{MINIO_BUCKET}/{prefix}")

    result = await _download(artifact, _listing_minio(*_peft_keys(prefix)), namespace="data--science")

    # Should this start raising, find out which happened before restoring it: aiwb grew a check of
    # its own on raw namespaces, in which case delete this test, or AIRM's naming rule was weakened,
    # in which case the cross-tenant read is live again.
    assert {f.path for f in result.files} == {"adapter_config.json", "adapter_model.safetensors"}


@pytest.mark.asyncio
async def test_download_refuses_storage_that_traverses_out_of_the_project():
    """A ".." segment clears a naive startswith test on the namespace prefix while still escaping
    the project tree in intent, so it must be refused rather than silently listing nothing."""
    artifact = _downloadable(source_uri=f"s3://{MINIO_BUCKET}/test-namespace/../other-namespace/adapters/a-1/")

    with pytest.raises(ConflictException, match="not inside this project's storage"):
        await _download(artifact, _listing_minio())


@pytest.mark.asyncio
async def test_download_refuses_storage_with_an_empty_path_segment():
    """A doubled separator in the prefix is another shape a naive startswith test would pass
    through silently instead of refusing."""
    artifact = _downloadable(source_uri=f"s3://{MINIO_BUCKET}/test-namespace//adapters/a-1/")

    with pytest.raises(ConflictException, match="not inside this project's storage"):
        await _download(artifact, _listing_minio())


@pytest.mark.asyncio
async def test_download_refuses_storage_in_another_namespace_behind_a_leading_separator():
    """Splitting the URI strips leading separators, so "//other-namespace/..." names the same prefix
    "other-namespace/..." does. That normalization is what the namespace test runs against, so the
    extra separator buys nothing: the prefix still has to start inside this project's tree."""
    artifact = _downloadable(source_uri=f"s3://{MINIO_BUCKET}//other-namespace/adapters/a-1/")

    with pytest.raises(ConflictException, match="not inside this project's storage"):
        await _download(artifact, _listing_minio(*_peft_keys("other-namespace/adapters/a-1/")))


@pytest.mark.asyncio
async def test_download_of_an_adapter_whose_location_carries_a_leading_separator():
    """The same normalization makes a leading separator inside the caller's own namespace harmless:
    it resolves to the artifact's real prefix and is listed there. Readiness and delete-time storage
    reclamation split a recorded URI identically, so refusing this only here would leave an artifact
    that reports ready and reclaims correctly yet cannot be handed out."""
    artifact = _downloadable(source_uri=f"s3://{MINIO_BUCKET}//{_DOWNLOAD_PREFIX}")
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX))

    result = await _download(artifact, minio_client)

    assert minio_client.client.list_objects.call_args.kwargs["prefix"] == _DOWNLOAD_PREFIX
    assert {f.path for f in result.files} == {"adapter_config.json", "adapter_model.safetensors"}


@pytest.mark.asyncio
async def test_download_of_an_adapter_whose_location_carries_a_current_directory_segment():
    """A '.' segment in a stored prefix names a real, distinct key prefix: object keys are literal,
    so nothing resolves it away and the namespace test still confines it. Onboarding accepts such a
    source, so refusing it here is what would leave an artifact Ready and permanently
    undownloadable."""
    prefix = "test-namespace/./adapters/a-1/"
    minio_client = _listing_minio(*_peft_keys(prefix))

    result = await _download(_downloadable(source_uri=f"s3://{MINIO_BUCKET}/{prefix}"), minio_client)

    assert minio_client.client.list_objects.call_args.kwargs["prefix"] == prefix
    assert {f.path for f in result.files} == {"adapter_config.json", "adapter_model.safetensors"}


@pytest.mark.asyncio
async def test_download_of_an_adapter_whose_location_carries_a_backslash():
    """A backslash is an ordinary character in an object key, and nothing joins a stored prefix onto
    a local destination, so it names a prefix inside the project like any other character does. The
    stricter rule that refuses it applies to the paths handed back, which a caller does join."""
    prefix = "test-namespace/adapters/a\\1/"
    minio_client = _listing_minio(*_peft_keys(prefix))

    result = await _download(_downloadable(source_uri=f"s3://{MINIO_BUCKET}/{prefix}"), minio_client)

    assert minio_client.client.list_objects.call_args.kwargs["prefix"] == prefix
    assert {f.path for f in result.files} == {"adapter_config.json", "adapter_model.safetensors"}


@pytest.mark.asyncio
async def test_an_s3_source_with_a_current_directory_segment_onboards_and_then_downloads() -> None:
    """Onboarding and download have to agree on what a stored prefix may look like. Onboarding
    accepts this URI, so the location it records must be one download will sign — otherwise the
    artifact reports Ready and answers every download with a conflict, forever."""
    kube_client = _make_kube_client()
    minio_client = _make_s3_minio_client()
    request = CreateArtifactRequest(
        type="adapter",
        source={"type": "s3", "uri": f"s3://{MINIO_BUCKET}/test-namespace/./adapters/my-adapter/"},
        model_id="org/base-model",
        compatible_with=["org/base-model"],
    )

    with patch("app.artifacts.service.create_aim_artifact") as mock_create:
        mock_create.return_value = AIMArtifactResource(
            metadata=K8sMetadata(name="adapter-abcd1234", namespace="test-namespace"),
            spec=AIMArtifactSpec(),
            status=AIMArtifactStatusFields(),
        )
        await create_adapter_artifact(
            kube_client=kube_client,
            minio_client=minio_client,
            minio_external_client=minio_client,
            namespace="test-namespace",
            request=request,
            submitter="test@example.com",
        )

    recorded_uri = mock_create.call_args.args[2]["spec"]["sourceUri"]
    recorded_prefix = recorded_uri.removeprefix(f"s3://{MINIO_BUCKET}/")

    result = await _download(_downloadable(source_uri=recorded_uri), _listing_minio(*_peft_keys(recorded_prefix)))

    assert {f.path for f in result.files} == {"adapter_config.json", "adapter_model.safetensors"}


@pytest.mark.asyncio
async def test_download_refuses_storage_in_a_sibling_namespace_sharing_a_prefix():
    """The namespace prefix carries its own trailing separator, so a sibling namespace whose slug
    merely starts with the same characters cannot pass as this project's storage. Losing that
    separator would silently reopen a cross-tenant read."""
    artifact = _downloadable(source_uri=f"s3://{MINIO_BUCKET}/test-namespace-2/adapters/a-1/")

    with pytest.raises(ConflictException, match="not inside this project's storage"):
        await _download(artifact, _listing_minio())


@pytest.mark.asyncio
async def test_download_refuses_an_unparseable_storage_location():
    """A recorded location that is not an S3 URI names nothing that can be signed."""
    artifact = _downloadable(source_uri="not-a-uri")

    with pytest.raises(ConflictException, match="not inside this project's storage"):
        await _download(artifact, _listing_minio())


@pytest.mark.asyncio
async def test_download_refuses_an_object_whose_path_escapes_the_prefix():
    """Each entry is handed back for the caller to write at its own path, so a stored key with a ".."
    segment would land outside the directory they are rebuilding. Onboarding rejects the same shape
    on the way in; refusing rather than dropping it keeps a partial export from passing as whole."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX), f"{_DOWNLOAD_PREFIX}../a-2/stolen.bin")

    with pytest.raises(ConflictException, match="escapes it"):
        await _download(_downloadable(), minio_client)


@pytest.mark.asyncio
async def test_download_refuses_an_object_whose_path_holds_an_interior_empty_segment():
    """An empty segment between two names is a key no directory can be rebuilt from faithfully: it
    resolves away, so the caller writes somewhere other than where the listing said. Unlike a
    trailing one it names no directory, so there is nothing to skip and the artifact is refused."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX), f"{_DOWNLOAD_PREFIX}checkpoint-500//optimizer.pt")

    with pytest.raises(ConflictException, match="escapes it"):
        await _download(_downloadable(), minio_client)


@pytest.mark.asyncio
async def test_download_refuses_an_object_whose_path_holds_a_current_directory_segment():
    """A '.' segment stays inside the prefix but resolves away, so the caller writes the object
    somewhere other than the path the listing gave — and onto whatever it collides with there.
    Refused for the same reason an empty segment is: the path handed back has to be the path."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX), f"{_DOWNLOAD_PREFIX}./config.json")

    with pytest.raises(ConflictException, match="escapes it"):
        await _download(_downloadable(), minio_client)


@pytest.mark.asyncio
async def test_download_refuses_an_object_whose_path_holds_an_interior_current_directory_segment():
    """The segment resolves away wherever it sits, so a nested one is no more faithful than a
    leading one."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX), f"{_DOWNLOAD_PREFIX}checkpoint-500/./optimizer.pt")

    with pytest.raises(ConflictException, match="escapes it"):
        await _download(_downloadable(), minio_client)


@pytest.mark.asyncio
async def test_download_refuses_an_object_whose_path_is_windows_drive_qualified():
    """A drive-qualified path is absolute on Windows, where joining it to a destination directory
    discards that directory — the same escape a POSIX absolute path (an empty first segment) is
    already refused for."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX), f"{_DOWNLOAD_PREFIX}C:/outside/file.bin")

    with pytest.raises(ConflictException, match="escapes it"):
        await _download(_downloadable(), minio_client)


@pytest.mark.asyncio
async def test_download_refuses_an_object_whose_path_is_drive_relative():
    """A drive designator followed by a name is drive-qualified too, so it discards the destination
    the caller is rebuilding into just as a bare designator does."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX), f"{_DOWNLOAD_PREFIX}C:outside/file.bin")

    with pytest.raises(ConflictException, match="escapes it"):
        await _download(_downloadable(), minio_client)


@pytest.mark.asyncio
async def test_download_refuses_an_object_whose_path_holds_a_backslash():
    """A backslash is a separator on Windows, so a key holding one is several components on the
    machine writing the files out — components this rule cannot see, traversal among them."""
    minio_client = _listing_minio(
        *_peft_keys(_DOWNLOAD_PREFIX), f"{_DOWNLOAD_PREFIX}checkpoint-500\\..\\..\\stolen.bin"
    )

    with pytest.raises(ConflictException, match="escapes it"):
        await _download(_downloadable(), minio_client)


@pytest.mark.asyncio
async def test_download_skips_a_nested_directory_marker():
    """A console's "create folder" leaves an object naming a directory, which a download rebuilds
    from the files under it anyway. It is not a file, and it is the same kind of object as the
    prefix's own marker, so it is passed over rather than made to refuse the whole adapter."""
    minio_client = _listing_minio(
        *_peft_keys(_DOWNLOAD_PREFIX),
        f"{_DOWNLOAD_PREFIX}checkpoint-500/",
        f"{_DOWNLOAD_PREFIX}checkpoint-500/optimizer.pt",
    )

    result = await _download(_downloadable(), minio_client)

    assert {f.path for f in result.files} == {
        "adapter_config.json",
        "adapter_model.safetensors",
        "checkpoint-500/optimizer.pt",
    }


@pytest.mark.asyncio
async def test_download_refuses_a_directory_ending_key_that_holds_bytes():
    """What makes a marker a marker is that it is empty. A key ending in "/" that holds content is
    an object with no file path a caller could write it at — the response would name a directory —
    so it can neither be handed back nor quietly left out of an adapter said to be complete."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX), f"{_DOWNLOAD_PREFIX}checkpoint-500/", marker_size=4096)

    with pytest.raises(ConflictException, match="names a directory yet carries bytes"):
        await _download(_downloadable(), minio_client)


@pytest.mark.asyncio
async def test_download_refuses_a_prefix_marker_that_holds_bytes():
    """The prefix's own key ends in "/" exactly as a nested marker does, so an object stored under
    that name and holding content is the same thing: bytes with no file path a caller could write
    them at. Passing it over would hand back an adapter reported complete without them."""
    minio_client = _listing_minio(_DOWNLOAD_PREFIX, *_peft_keys(_DOWNLOAD_PREFIX), marker_size=4096)

    with pytest.raises(ConflictException, match="names a directory yet carries bytes"):
        await _download(_downloadable(), minio_client)


@pytest.mark.asyncio
async def test_download_still_serves_ordinarily_nested_objects():
    """The escape check bites on the segments, not on nesting: an object several directories down is
    a layout onboarding accepts and a download must keep handing back."""
    nested = "checkpoint-500/global_step/optimizer.pt"
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX), f"{_DOWNLOAD_PREFIX}{nested}")

    result = await _download(_downloadable(), minio_client)

    assert nested in {f.path for f in result.files}


@pytest.mark.asyncio
async def test_download_refuses_when_the_weights_are_absent():
    """A prefix holding no weights is a registered adapter that never landed. Handing back links to
    what is there would look like a successful export of an unusable adapter."""
    minio_client = _listing_minio(f"{_DOWNLOAD_PREFIX}adapter_config.json")

    with pytest.raises(ConflictException, match="weights are not present"):
        await _download(_downloadable(), minio_client)


@pytest.mark.asyncio
async def test_download_is_not_satisfied_by_weights_nested_below_the_prefix():
    """aim-engine reads the PEFT files at the top of the prefix, so a nested copy leaves the adapter
    just as unusable. Now that a nested object is handed back, it must still not pass for one."""
    minio_client = _listing_minio(*_peft_keys(f"{_DOWNLOAD_PREFIX}checkpoint-500/"))

    with pytest.raises(ConflictException, match="weights are not present"):
        await _download(_downloadable(), minio_client)


@pytest.mark.asyncio
async def test_download_pins_that_a_second_artifact_type_would_not_require_peft_weights():
    """PEFT completeness is what an adapter means, not what an artifact means, so the weights check
    is gated on the type rather than applied to everything a download reaches.

    No second type exists yet — ``is_platform_managed`` admits only adapters, and a download of
    anything else is a 404 — so the state this exercises is unreachable today and the membership
    test is patched to reach it. It pins the gate as forward compatibility, not current behavior:
    dropping it would make the next type inherit an adapter's requirement silently."""
    artifact = _downloadable(artifact_type="model")
    minio_client = _listing_minio(f"{_DOWNLOAD_PREFIX}config.json", f"{_DOWNLOAD_PREFIX}model.safetensors")

    with patch("app.artifacts.service.is_platform_managed", return_value=True):
        result = await _download(artifact, minio_client)

    assert {f.path for f in result.files} == {"config.json", "model.safetensors"}


@pytest.mark.asyncio
async def test_download_of_an_adapter_holding_exactly_what_one_download_covers():
    """The cap is the largest prefix still served, not the first one refused."""
    keys = [
        *_peft_keys(_DOWNLOAD_PREFIX),
        *(f"{_DOWNLOAD_PREFIX}shard-{i}.bin" for i in range(MAX_ARTIFACT_FILES - 2)),
    ]

    result = await _download(_downloadable(), _listing_minio(*keys))

    assert len(result.files) == MAX_ARTIFACT_FILES


@pytest.mark.asyncio
async def test_download_of_an_adapter_holding_every_file_an_upload_may_declare_and_the_manifest():
    """An upload may declare exactly as many files as one download covers, and AIWB writes its
    manifest into the same prefix. Counting that manifest against the same cap would leave the
    documented maximum upload permanently undownloadable, with nothing to signal it before the
    download that fails and no recovery short of deleting the artifact."""
    keys = [
        *_peft_keys(_DOWNLOAD_PREFIX),
        *(f"{_DOWNLOAD_PREFIX}shard-{i}.bin" for i in range(MAX_ARTIFACT_FILES - 2)),
        f"{_DOWNLOAD_PREFIX}{ADAPTER_MANIFEST_FILENAME}",
    ]

    result = await _download(_downloadable(), _listing_minio(*keys))

    assert {f.path for f in result.files} == {k.removeprefix(_DOWNLOAD_PREFIX) for k in keys}
    assert len(result.files) == MAX_ARTIFACT_FILES + 1


@pytest.mark.asyncio
async def test_download_counts_a_manifest_nested_below_the_prefix_as_a_file():
    """Only the one key AIWB writes is exempt. A copy the caller stored under a subdirectory is a
    file of theirs, and exempting it too would let the cap be evaded a directory at a time."""
    keys = [
        *_peft_keys(_DOWNLOAD_PREFIX),
        *(f"{_DOWNLOAD_PREFIX}shard-{i}.bin" for i in range(MAX_ARTIFACT_FILES - 2)),
        f"{_DOWNLOAD_PREFIX}{ADAPTER_MANIFEST_FILENAME}",
        f"{_DOWNLOAD_PREFIX}checkpoint-500/{ADAPTER_MANIFEST_FILENAME}",
    ]

    with pytest.raises(ConflictException, match="files one download covers"):
        await _download(_downloadable(), _listing_minio(*keys))


@pytest.mark.asyncio
async def test_download_refuses_more_files_than_one_download_covers():
    """Each file costs a signing call, so an unbounded prefix is a request-sized amplifier."""
    keys = [*_peft_keys(_DOWNLOAD_PREFIX), *(f"{_DOWNLOAD_PREFIX}shard-{i}.bin" for i in range(MAX_ARTIFACT_FILES))]

    with pytest.raises(ConflictException, match="files one download covers"):
        await _download(_downloadable(), _listing_minio(*keys))


@pytest.mark.asyncio
async def test_download_of_an_adapter_at_the_cap_beside_directory_markers():
    """The cap counts files a caller is handed, which is what it is stated in. Markers are read but
    never served, so a full complement of files with markers beside it is still within the cap — and
    the bound on entries read has to leave room for them rather than doubling as the file cap."""
    keys = [
        _DOWNLOAD_PREFIX,
        *_peft_keys(_DOWNLOAD_PREFIX),
        *(f"{_DOWNLOAD_PREFIX}checkpoint-{i}/" for i in range(8)),
        *(f"{_DOWNLOAD_PREFIX}shard-{i}.bin" for i in range(MAX_ARTIFACT_FILES - 2)),
    ]

    result = await _download(_downloadable(), _listing_minio(*keys))

    assert len(result.files) == MAX_ARTIFACT_FILES


@pytest.mark.asyncio
async def test_download_refuses_more_files_than_one_download_covers_under_a_prefix_marker():
    """Excluding the marker from the count does not raise what a prefix may hold: one file past the
    cap is refused whether or not a marker sits beside it."""
    keys = [
        _DOWNLOAD_PREFIX,
        *_peft_keys(_DOWNLOAD_PREFIX),
        *(f"{_DOWNLOAD_PREFIX}shard-{i}.bin" for i in range(MAX_ARTIFACT_FILES - 1)),
    ]

    with pytest.raises(ConflictException, match="files one download covers"):
        await _download(_downloadable(), _listing_minio(*keys))


@pytest.mark.asyncio
async def test_download_serves_every_object_the_cap_counted():
    """Nesting does not change what the file cap counts: a prefix accepted as within it hands back
    every object counted towards it, however deep the object sits. The cap is on files served, not
    on files at the top of the prefix."""
    keys = [
        *_peft_keys(_DOWNLOAD_PREFIX),
        *(f"{_DOWNLOAD_PREFIX}checkpoint-{i}/optimizer.pt" for i in range(MAX_ARTIFACT_FILES - 2)),
    ]

    result = await _download(_downloadable(), _listing_minio(*keys))

    assert {f.path for f in result.files} == {k.removeprefix(_DOWNLOAD_PREFIX) for k in keys}
    assert len(result.files) == MAX_ARTIFACT_FILES


@pytest.mark.asyncio
async def test_download_of_an_adapter_naming_no_model():
    """A download hands over files, so nothing about it depends on what the record says they are."""
    artifact = _downloadable(model_id=None)

    result = await _download(artifact, _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX)))

    assert {f.path for f in result.files} == {"adapter_config.json", "adapter_model.safetensors"}


@pytest.mark.asyncio
async def test_download_reports_a_storage_failure_as_upstream():
    """An unreachable bucket is an upstream failure, not an adapter the caller got wrong."""
    minio_client = _listing_minio()
    minio_client.client.list_objects.side_effect = _s3_error("SlowDown")

    with pytest.raises(ExternalServiceError, match="Failed to read the files"):
        await _download(_downloadable(), minio_client)


@pytest.mark.asyncio
async def test_download_of_missing_artifact_raises_not_found():
    """A download for an absent artifact raises NotFoundException (mapped to 404)."""
    with pytest.raises(NotFoundException, match="a-1"):
        await _download(None, _listing_minio())


@pytest.mark.asyncio
async def test_download_of_artifact_outside_platform_collection_raises_not_found():
    """An artifact the platform did not author is absent from this API, even by name."""
    artifact = _downloadable(managed_by="some-other-operator")

    with pytest.raises(NotFoundException, match="a-1"):
        await _download(artifact, _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX)))


@pytest.mark.asyncio
async def test_download_of_non_adapter_type_raises_not_found():
    """A platform-managed CR of another type is outside this API's collection, label match or not."""
    artifact = _downloadable(artifact_type="model")

    with pytest.raises(NotFoundException, match="a-1"):
        await _download(artifact, _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX)))


@pytest.mark.asyncio
async def test_download_of_an_adapter_in_another_project_raises_not_found():
    """Namespaces are read separately, so a name that exists elsewhere is simply absent here."""
    with patch("app.artifacts.service.get_aim_artifact", AsyncMock(return_value=None)) as mock_get:
        with pytest.raises(NotFoundException, match="other-namespace"):
            await download_project_artifact(
                kube_client=_kube_client(),
                minio_client=_listing_minio(),
                minio_external_client=_signing_minio(),
                namespace="other-namespace",
                name="a-1",
            )

    assert mock_get.await_args.args[1] == "other-namespace"


@pytest.mark.asyncio
async def test_download_carries_one_deadline_for_the_whole_set():
    """Every link is signed in one batch off one clock reading, so the set has a single deadline and
    a client plans one transfer window rather than tracking a per-file one."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX))

    result = await _download(_downloadable(), minio_client)

    assert result.expires_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_download_refuses_storage_in_another_bucket():
    """The namespace prefix alone is not the bar: a URI naming a bucket AIWB does not own can carry
    a matching prefix and still point somewhere the platform has no claim on."""
    artifact = _downloadable(source_uri=f"s3://other-bucket/{_DOWNLOAD_PREFIX}")

    with pytest.raises(ConflictException, match="not inside this project's storage"):
        await _download(artifact, _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX)))


@pytest.mark.asyncio
async def test_download_excludes_the_prefix_directory_marker():
    """A prefix created as an explicit object lists as an entry equal to the prefix itself. It is a
    marker, not a file, and would otherwise become a link with an empty path."""
    minio_client = _listing_minio(_DOWNLOAD_PREFIX, *_peft_keys(_DOWNLOAD_PREFIX))

    result = await _download(_downloadable(), minio_client)

    assert {f.path for f in result.files} == {"adapter_config.json", "adapter_model.safetensors"}


@pytest.mark.asyncio
async def test_download_leaves_the_size_unknown_when_storage_gives_none():
    """Size is advisory — it lets a caller plan the transfer — so an entry storage reports without
    one is still handed out, with the size left null rather than the link withheld. Null and zero
    stay distinct: zero is a genuinely empty object, which a caller may act on differently."""
    minio_client = _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX), size=None)

    result = await _download(_downloadable(), minio_client)

    assert {f.size_bytes for f in result.files} == {None}


@pytest.mark.asyncio
async def test_download_reports_a_signing_failure_as_upstream():
    """Presigning is not offline: with no region configured the client resolves the bucket's
    location over the network first. A failure there is upstream (502), not the caller's fault."""
    minio_external_client = _signing_minio()
    minio_external_client.generate_presigned_download_url.side_effect = _s3_error("SlowDown")

    with pytest.raises(ExternalServiceError, match="Failed to sign download links"):
        await _download(_downloadable(), _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX)), minio_external_client)


def _lazy_listing_minio(*keys: str, fail_after: int | None = None) -> tuple[MagicMock, list[str]]:
    """A storage client whose listing is consumed lazily, recording what was actually pulled from it.

    The real listing is a paged iterator that fetches as it is read, so how much of it the service
    consumes is how much it fetches and holds. A list fixture cannot show that, and cannot fail
    partway through a read either.
    """
    pulled: list[str] = []

    def _entries() -> Iterator[SimpleNamespace]:
        for index, key in enumerate(keys):
            if index == fail_after:
                raise _s3_error("SlowDown")
            pulled.append(key)
            yield SimpleNamespace(object_name=key, size=0 if key.endswith("/") else 128)

    client = MagicMock(spec=MinioClient)
    client.client = MagicMock(spec=Minio)
    client.client.list_objects.return_value = _entries()
    return client, pulled


@pytest.mark.asyncio
async def test_download_stops_reading_the_prefix_once_the_cap_is_settled():
    """A prefix is refused for holding more files than one download covers, and reading it to the end
    to find that out would let stored contents, rather than the request, decide how much this pod
    fetches. One entry past the cap already settles it."""
    keys = [
        *_peft_keys(_DOWNLOAD_PREFIX),
        *(f"{_DOWNLOAD_PREFIX}shard-{i}.bin" for i in range(MAX_ARTIFACT_FILES * 4)),
    ]
    minio_client, pulled = _lazy_listing_minio(*keys)

    with pytest.raises(ConflictException, match="files one download covers"):
        await _download(_downloadable(), minio_client)

    assert len(pulled) == MAX_ARTIFACT_FILES + 1


@pytest.mark.asyncio
async def test_download_refuses_a_prefix_of_more_entries_than_one_download_reads():
    """Markers are skipped before the file cap counts them, so a prefix of nothing but markers would
    never reach that cutoff and would be read to the end however large it is. The bound on entries
    read settles it instead, and settles it where it is met rather than after the whole prefix."""
    keys = [f"{_DOWNLOAD_PREFIX}checkpoint-{i}/" for i in range(MAX_ARTIFACT_LISTING_ENTRIES * 2)]
    minio_client, pulled = _lazy_listing_minio(*keys)

    with pytest.raises(ConflictException, match="entries one download reads"):
        await _download(_downloadable(), minio_client)

    assert len(pulled) == MAX_ARTIFACT_LISTING_ENTRIES + 1


@pytest.mark.asyncio
async def test_download_of_a_prefix_holding_exactly_as_many_entries_as_one_download_reads():
    """The entry bound is the largest prefix still read through, not the first one refused."""
    keys = [
        *_peft_keys(_DOWNLOAD_PREFIX),
        *(f"{_DOWNLOAD_PREFIX}checkpoint-{i}/" for i in range(MAX_ARTIFACT_LISTING_ENTRIES - 2)),
    ]

    result = await _download(_downloadable(), _listing_minio(*keys))

    assert {f.path for f in result.files} == {"adapter_config.json", "adapter_model.safetensors"}


@pytest.mark.asyncio
async def test_download_refuses_a_prefix_one_entry_past_what_one_download_reads():
    """A prefix that only just exceeds the bound is refused like any other, so the cutoff sits where
    the bound is stated rather than one entry above it."""
    keys = [
        *_peft_keys(_DOWNLOAD_PREFIX),
        *(f"{_DOWNLOAD_PREFIX}checkpoint-{i}/" for i in range(MAX_ARTIFACT_LISTING_ENTRIES - 1)),
    ]

    with pytest.raises(ConflictException, match="entries one download reads"):
        await _download(_downloadable(), _listing_minio(*keys))


@pytest.mark.asyncio
async def test_download_reports_a_storage_failure_partway_through_the_listing_as_upstream():
    """The listing pages as it is read, so storage can fail after the read has started rather than at
    the call that begins it. That is still an upstream failure, not a missing adapter."""
    minio_client, _ = _lazy_listing_minio(*_peft_keys(_DOWNLOAD_PREFIX), fail_after=1)

    with pytest.raises(ExternalServiceError, match="Failed to read the files"):
        await _download(_downloadable(), minio_client)


@pytest.mark.asyncio
async def test_download_links_all_expire_at_the_advertised_instant():
    """A signature dies a fixed span after a timestamp carried inside it, and links are minted one
    after another — so letting each take its own reading of the signing clock would leave the last
    alive past the single instant the response advertises. Every link is stamped with one instant
    for the batch instead, which is exactly the instant the response is measured from."""
    minio_external_client = _signing_minio()

    result = await _download(_downloadable(), _listing_minio(*_peft_keys(_DOWNLOAD_PREFIX)), minio_external_client)

    calls = minio_external_client.generate_presigned_download_url.call_args_list
    assert len(calls) == len(result.files) > 1
    assert {c.kwargs["expires"] for c in calls} == {_PRESIGNED_URL_EXPIRY}
    assert {c.kwargs["request_date"] for c in calls} == {result.expires_at - _PRESIGNED_URL_EXPIRY}
