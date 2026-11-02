# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Unit tests for the adapter recovery manifest read/write."""

from unittest.mock import MagicMock

import pytest
import yaml
from minio.error import S3Error

from api_common.exceptions import ExternalServiceError, ForbiddenException
from app.artifacts.manifest import AdapterManifest, read_adapter_manifest, write_adapter_manifest
from app.minio import MinioClient

_BUCKET = "default-bucket"
_KEY = "test-namespace/adapters/my-adapter/adapter-manifest.yaml"


def _s3_error(code: str) -> S3Error:
    """Build the S3Error minio-py would raise for the given error code."""
    return S3Error(
        code=code,
        message=code,
        resource=f"/{_BUCKET}/{_KEY}",
        request_id="request123",
        host_id="host123",
        response=MagicMock(status=404 if code == "NoSuchKey" else 503),
    )


def _make_minio_client() -> MagicMock:
    return MagicMock(spec=MinioClient)


@pytest.mark.asyncio
async def test_read_returns_none_when_object_missing() -> None:
    """A genuine not-found is the common case and yields None so the caller can write one."""
    minio_client = _make_minio_client()
    minio_client.download_object.side_effect = _s3_error("NoSuchKey")

    assert await read_adapter_manifest(minio_client, _BUCKET, _KEY) is None


@pytest.mark.asyncio
async def test_read_raises_on_malformed_yaml() -> None:
    """Corrupt YAML is distinct from a missing file and surfaces as a storage error."""
    minio_client = _make_minio_client()
    minio_client.download_object.return_value = b"modelId: [unterminated"

    with pytest.raises(ExternalServiceError):
        await read_adapter_manifest(minio_client, _BUCKET, _KEY)


@pytest.mark.asyncio
async def test_read_raises_when_body_is_not_a_mapping() -> None:
    """A YAML document that parses to a non-mapping cannot be a manifest."""
    minio_client = _make_minio_client()
    minio_client.download_object.return_value = b"- just\n- a\n- list\n"

    with pytest.raises(ExternalServiceError):
        await read_adapter_manifest(minio_client, _BUCKET, _KEY)


@pytest.mark.asyncio
async def test_read_raises_when_body_fails_validation() -> None:
    """A well-formed mapping that omits the required adapter id is corruption, not a valid manifest."""
    minio_client = _make_minio_client()
    minio_client.download_object.return_value = b"compatibleWith:\n  - org/base-model\nrank: 8\n"

    with pytest.raises(ExternalServiceError):
        await read_adapter_manifest(minio_client, _BUCKET, _KEY)


@pytest.mark.asyncio
async def test_read_maps_other_s3_errors_to_domain_exceptions() -> None:
    """Errors other than not-found flow through the shared S3 error mapper (AccessDenied -> 403)."""
    minio_client = _make_minio_client()
    minio_client.download_object.side_effect = _s3_error("AccessDenied")

    with pytest.raises(ForbiddenException):
        await read_adapter_manifest(minio_client, _BUCKET, _KEY)


@pytest.mark.asyncio
async def test_write_serializes_flat_yaml_and_uploads() -> None:
    """The manifest is written as a flat camelCase YAML mapping with None fields omitted."""
    minio_client = _make_minio_client()
    manifest = AdapterManifest(
        model_id="org/my-adapter", compatible_with=["org/base-model"], rank=8, display_name="My Adapter"
    )

    await write_adapter_manifest(minio_client, _BUCKET, _KEY, manifest)

    minio_client.upload_object.assert_called_once()
    kwargs = minio_client.upload_object.call_args.kwargs
    assert kwargs["bucket_name"] == _BUCKET
    assert kwargs["object_name"] == _KEY
    loaded = yaml.safe_load(kwargs["data"])
    assert loaded == {
        "modelId": "org/my-adapter",
        "compatibleWith": ["org/base-model"],
        "rank": 8,
        "displayName": "My Adapter",
    }


@pytest.mark.asyncio
async def test_write_does_not_retry_non_transient_errors() -> None:
    """A mapped domain error (auth here) is deterministic, so the write fails on the first attempt
    rather than burning the retry budget on an outcome that cannot change."""
    minio_client = _make_minio_client()
    minio_client.upload_object.side_effect = _s3_error("AccessDenied")

    with pytest.raises(ForbiddenException):
        await write_adapter_manifest(minio_client, _BUCKET, _KEY, AdapterManifest(model_id="org/my-adapter"))

    minio_client.upload_object.assert_called_once()


@pytest.mark.asyncio
async def test_write_omits_none_fields() -> None:
    """Unresolved optional fields are dropped rather than serialized as null."""
    minio_client = _make_minio_client()
    manifest = AdapterManifest(model_id="org/my-adapter")

    await write_adapter_manifest(minio_client, _BUCKET, _KEY, manifest)

    loaded = yaml.safe_load(minio_client.upload_object.call_args.kwargs["data"])
    assert loaded == {"modelId": "org/my-adapter"}
    assert "compatibleWith" not in loaded
    assert "rank" not in loaded


@pytest.mark.asyncio
async def test_write_then_read_round_trips() -> None:
    """What the writer serializes is exactly what the reader reconstructs."""
    minio_client = _make_minio_client()
    original = AdapterManifest(
        model_id="org/my-adapter", compatible_with=["org/base-model"], rank=16, display_name="My Adapter"
    )

    await write_adapter_manifest(minio_client, _BUCKET, _KEY, original)
    payload = minio_client.upload_object.call_args.kwargs["data"]

    minio_client.download_object.return_value = payload
    recovered = await read_adapter_manifest(minio_client, _BUCKET, _KEY)

    assert recovered == original
