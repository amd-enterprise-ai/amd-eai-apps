# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT


import base64
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from kubernetes_asyncio.client import ApiException, V1ConfigMap, V1ObjectMeta, V1Secret

from api_common.exceptions import (
    ExternalServiceError,
    ForbiddenException,
    NotFoundException,
    PreconditionNotMetException,
    ValidationException,
)
from api_common.secrets import SecretUseCase
from app.aims.crds import AIMProfileResource
from app.custom_models.constants import (
    AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION,
    HF_MAX_RESPONSE_BYTES,
    SOURCE_METADATA_MAX_BYTES,
)
from app.custom_models.schemas import PreviewRequest
from app.custom_models.service import (
    _fetch_hub_model,
    _profile_resource_to_manifest_document,
    finalize_aim_profile_for_onboarded_model,
    preview_model_source,
)
from app.minio import MinioClient
from app.minio.config import MINIO_BUCKET, MINIO_URL
from app.secrets.constants import AIRM_USE_CASE_LABEL, USE_CASE_LABEL
from app.storages.constants import STORAGE_CONFIGMAP_LABEL, STORAGE_TYPE_LABEL
from app.storages.enums import StorageType

HUB_RESPONSE = {
    "id": "meta-llama/Meta-Llama-3-8B-Instruct",
    "sha": "abc123",
    "tags": ["llama", "text-generation"],
    "pipeline_tag": "text-generation",
    "gated": "manual",
    "private": False,
    "cardData": {
        "model_name": "Meta Llama 3 8B Instruct",
        "description": "A great model.",
    },
    "siblings": [
        {"rfilename": "model-00001-of-00002.safetensors", "lfs": {"size": 4_000_000_000}},
        {"rfilename": "model-00002-of-00002.safetensors", "lfs": {"size": 4_000_000_000}},
        {"rfilename": "config.json", "size": 820},
    ],
}


def _make_k8s_secret(token: str = "hf_test_token") -> V1Secret:
    """Build a typed K8s V1Secret with a base64-encoded 'token' key."""
    return V1Secret(
        data={"token": base64.b64encode(token.encode()).decode()},
        metadata=V1ObjectMeta(labels={}),
    )


def _make_k8s_secret_from_raw_token_value(raw_token_value: str) -> V1Secret:
    """Build a typed K8s V1Secret using the raw stored token string."""
    return V1Secret(
        data={"token": raw_token_value},
        metadata=V1ObjectMeta(labels={}),
    )


def _make_k8s_secret_with_data(data: dict[str, str], labels: dict[str, str] | None = None) -> V1Secret:
    """Build a typed K8s V1Secret with arbitrary pre-encoded data keys."""
    return V1Secret(
        data=data,
        metadata=V1ObjectMeta(labels=labels or {}),
    )


def _make_s3_storage_config_map(
    secret_name: str = "s3-creds",
    bucket_url: str | None = None,
    region: str | None = None,
    access_key_name: str = "AWS_ACCESS_KEY_ID",
    secret_key_name: str = "AWS_SECRET_ACCESS_KEY",
) -> V1ConfigMap:
    """Build a typed S3 storage ConfigMap that points to a credentials secret."""
    data: dict[str, str] = {
        "TYPE": StorageType.S3.value,
        "SECRET_NAME": secret_name,
        "ACCESS_KEY_NAME": access_key_name,
        "SECRET_KEY_NAME": secret_key_name,
    }
    if bucket_url:
        data["BUCKET_URL"] = bucket_url
    if region:
        data["REGION"] = region
    return V1ConfigMap(
        data=data,
        metadata=V1ObjectMeta(labels={STORAGE_CONFIGMAP_LABEL: "true", STORAGE_TYPE_LABEL: StorageType.S3.value}),
    )


@pytest.fixture(autouse=True)
def _default_s3_storage_config(mock_kube_client: AsyncMock) -> None:
    """Default every test to a valid S3 storage config for preview lookups."""
    mock_kube_client.core_v1.read_namespaced_config_map = AsyncMock(return_value=_make_s3_storage_config_map())


def _mock_hub_response(status_code: int, body: bytes, chunk_size: int | None = None):  # type: ignore[no-untyped-def]
    """Patch httpx.AsyncClient so ``client.stream(...)`` yields ``body`` in chunks
    with the given status.

    The service streams responses (``client.stream`` + ``aiter_bytes``) so the body
    cap can short-circuit before the full payload is read. Tests can pass an
    explicit ``chunk_size`` to exercise multi-chunk consumption (used by the
    oversized-body test); when omitted the body is delivered as a single chunk.
    """
    if chunk_size is None:
        chunks = [body]
    else:
        chunks = [body[i : i + chunk_size] for i in range(0, len(body), chunk_size)] or [b""]

    async def _aiter_bytes():
        for c in chunks:
            yield c

    mock_response = MagicMock(spec_set=["status_code", "aiter_bytes"])
    mock_response.status_code = status_code
    mock_response.aiter_bytes = MagicMock(side_effect=_aiter_bytes)

    mock_stream_ctx = MagicMock(spec_set=["__aenter__", "__aexit__"])
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    return patch("httpx.AsyncClient", return_value=mock_client)


@pytest.mark.asyncio
async def test_preview_success_basic(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """Preview returns correct metadata for a gated model accessed with a token."""
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_make_k8s_secret("hf_mytoken"))

    with patch("app.custom_models.service._fetch_hub_model", return_value=HUB_RESPONSE):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source="meta-llama/Meta-Llama-3-8B-Instruct",
                hf_token_secret_name="my-hf-secret",
            ),
        )

    assert result.repo_id == "meta-llama/Meta-Llama-3-8B-Instruct"
    assert result.revision == "abc123"
    assert result.sha == "abc123"
    assert result.display_name == "Meta Llama 3 8B Instruct"
    assert result.description == "A great model."
    assert "llama" in result.tags
    assert result.pipeline_tag == "text-generation"
    assert result.gated is True
    assert result.hf_token_recommended is True
    assert result.layout_hint == "safetensors"
    assert result.warnings == []


@pytest.mark.asyncio
async def test_preview_hf_source_does_not_read_source_files_for_tags(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """Hub preview keeps using Hub tags directly; S3-only file discovery must not leak into it."""
    with (
        patch("app.custom_models.service._fetch_hub_model", return_value={**HUB_RESPONSE, "gated": False}),
        patch("app.custom_models.service._discover_s3_tags") as mock_discover,
    ):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(source="meta-llama/Meta-Llama-3-8B-Instruct"),
        )

    mock_discover.assert_not_called()
    assert result.tags == HUB_RESPONSE["tags"]


@pytest.mark.asyncio
async def test_preview_s3_source_validates_layout_and_returns_metadata(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """S3 preview validates source/secret and returns discovered weight metadata."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(
        return_value=_make_k8s_secret_with_data(secret_data, labels={USE_CASE_LABEL: SecretUseCase.S3.value})
    )

    listed_objects = [
        MagicMock(object_name="path/to/model/model-00001-of-00002.safetensors", size=4_000_000_000),
        MagicMock(object_name="path/to/model/model-00002-of-00002.safetensors", size=4_000_000_000),
        MagicMock(object_name="path/to/model/model.safetensors.index.json", size=3_012),
        MagicMock(object_name="path/to/model/config.json", size=820),
        MagicMock(object_name="path/to/model/tokenizer.json", size=1_024),
    ]
    minio_client = MagicMock()
    minio_client.client.list_objects = MagicMock(return_value=listed_objects)

    with (
        patch("app.custom_models.service._fetch_hub_model") as mock_fetch,
        patch("app.custom_models.service.MinioClient", return_value=minio_client),
    ):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source="s3://my-bucket/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )
    mock_fetch.assert_not_called()
    minio_client.client.list_objects.assert_called_once_with("my-bucket", prefix="path/to/model/", recursive=True)
    assert result.source_type == "s3"
    assert result.repo_id == "s3://my-bucket/path/to/model"
    assert result.display_name == "model"
    assert result.layout_hint == "safetensors"
    assert result.tags == []
    assert len(result.weight_files) == 4
    assert result.warnings == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("access_alias", "secret_alias"),
    [
        ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"),
        ("awsAccessKeyId", "awsSecretAccessKey"),
        ("S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"),
        ("MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"),
        ("ACCESS_KEY", "SECRET_KEY"),
    ],
)
async def test_preview_s3_source_accepts_common_credential_aliases(
    mock_kube_client: AsyncMock,
    test_namespace: str,
    access_alias: str,
    secret_alias: str,
) -> None:
    """S3 preview uses credential key names configured on the S3 storage."""
    mock_kube_client.core_v1.read_namespaced_config_map = AsyncMock(
        return_value=_make_s3_storage_config_map(
            bucket_url="https://s3.us-west-2.amazonaws.com/my-bucket",
            region="us-west-2",
            access_key_name=access_alias,
            secret_key_name=secret_alias,
        )
    )
    secret_data = {
        access_alias: base64.b64encode(b"access-key").decode(),
        secret_alias: base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_make_k8s_secret_with_data(secret_data))

    listed_objects = [
        MagicMock(object_name="path/to/model/model-00001-of-00001.safetensors", size=4_000_000_000),
        MagicMock(object_name="path/to/model/config.json", size=820),
        MagicMock(object_name="path/to/model/tokenizer.json", size=1_024),
    ]
    minio_client = MagicMock()
    minio_client.client.list_objects = MagicMock(return_value=listed_objects)

    with patch("app.custom_models.service.MinioClient", return_value=minio_client) as mock_minio_client:
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source="s3://my-bucket/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )

    mock_minio_client.assert_called_once_with(
        host="https://s3.us-west-2.amazonaws.com",
        access_key="access-key",
        secret_key="secret-key",
        region="us-west-2",
    )
    assert result.source_type == "s3"
    assert result.repo_id == "s3://my-bucket/path/to/model"
    assert result.warnings == []


@pytest.mark.asyncio
async def test_preview_s3_source_without_bucket_url_uses_default_minio_for_default_bucket(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """Missing storage bucketUrl falls back to MINIO_URL for default bucket."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_make_k8s_secret_with_data(secret_data))

    listed_objects = [
        MagicMock(object_name="path/to/model/model-00001-of-00001.safetensors", size=4_000_000_000),
        MagicMock(object_name="path/to/model/config.json", size=820),
        MagicMock(object_name="path/to/model/tokenizer.json", size=1_024),
    ]
    minio_client = MagicMock()
    minio_client.client.list_objects = MagicMock(return_value=listed_objects)

    with patch("app.custom_models.service.MinioClient", return_value=minio_client) as mock_minio_client:
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source=f"s3://{MINIO_BUCKET}/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )

    mock_minio_client.assert_called_once_with(
        host=MINIO_URL,
        access_key="access-key",
        secret_key="secret-key",
        region=None,
    )
    assert result.repo_id == f"s3://{MINIO_BUCKET}/path/to/model"


@pytest.mark.asyncio
async def test_preview_s3_source_without_bucket_url_uses_default_minio_for_non_default_bucket(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """Missing storage bucketUrl falls back to MINIO_URL for non-default bucket."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_make_k8s_secret_with_data(secret_data))

    listed_objects = [
        MagicMock(object_name="path/to/model/model-00001-of-00001.safetensors", size=4_000_000_000),
        MagicMock(object_name="path/to/model/config.json", size=820),
        MagicMock(object_name="path/to/model/tokenizer.json", size=1_024),
    ]
    minio_client = MagicMock()
    minio_client.client.list_objects = MagicMock(return_value=listed_objects)

    with patch("app.custom_models.service.MinioClient", return_value=minio_client) as mock_minio_client:
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source="s3://external-bucket/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )

    mock_minio_client.assert_called_once_with(
        host=MINIO_URL,
        access_key="access-key",
        secret_key="secret-key",
        region=None,
    )
    assert result.repo_id == "s3://external-bucket/path/to/model"


@pytest.mark.asyncio
async def test_preview_s3_source_requires_s3_secret_keys(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """S3 preview fails fast when required credential keys are missing from the secret."""
    secret_data = {"AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode()}
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_make_k8s_secret_with_data(secret_data))

    with pytest.raises(ValidationException, match="missing required secret key"):
        await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source="s3://my-bucket/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )


@pytest.mark.asyncio
async def test_preview_s3_source_warns_on_missing_required_layout_files(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """S3 preview succeeds with warnings when HF-compatible layout files are missing."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_make_k8s_secret_with_data(secret_data))

    listed_objects = [MagicMock(object_name="path/to/model/model-00001-of-00001.safetensors", size=4_000_000_000)]
    minio_client = MagicMock()
    minio_client.client.list_objects = MagicMock(return_value=listed_objects)

    with patch("app.custom_models.service.MinioClient", return_value=minio_client):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source="s3://my-bucket/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )
    assert any("missing recommended file(s): config.json" in warning for warning in result.warnings)
    assert any("should include tokenizer.json or tokenizer_config.json" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_preview_s3_source_warns_when_sharded_safetensors_missing_index(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """Sharded safetensors without an index should succeed with a warning."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_make_k8s_secret_with_data(secret_data))

    listed_objects = [
        MagicMock(object_name="path/to/model/model-00001-of-00002.safetensors", size=4_000_000_000),
        MagicMock(object_name="path/to/model/model-00002-of-00002.safetensors", size=4_000_000_000),
        MagicMock(object_name="path/to/model/config.json", size=820),
        MagicMock(object_name="path/to/model/tokenizer.json", size=1_024),
    ]
    minio_client = MagicMock()
    minio_client.client.list_objects = MagicMock(return_value=listed_objects)

    with patch("app.custom_models.service.MinioClient", return_value=minio_client):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source="s3://my-bucket/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )
    assert any("missing a '*.safetensors.index.json' file" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_preview_s3_source_warns_when_no_safetensors_found(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """No safetensors should succeed with a warning instead of blocking preview."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_make_k8s_secret_with_data(secret_data))

    listed_objects = [
        MagicMock(object_name="path/to/model/config.json", size=820),
        MagicMock(object_name="path/to/model/tokenizer.json", size=1_024),
    ]
    minio_client = MagicMock()
    minio_client.client.list_objects = MagicMock(return_value=listed_objects)

    with patch("app.custom_models.service.MinioClient", return_value=minio_client):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source="s3://my-bucket/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )
    assert any("should include at least one '*.safetensors' weight file" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_preview_s3_source_root_with_nested_weights_avoids_false_layout_warnings(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """Root prefixes with a weights/ subtree should pass layout checks."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_make_k8s_secret_with_data(secret_data))

    listed_objects = [
        MagicMock(object_name="path/to/model/manifest.yaml", size=2_048),
        MagicMock(object_name="path/to/model/weights/config.json", size=820),
        MagicMock(object_name="path/to/model/weights/tokenizer.json", size=1_024),
        MagicMock(object_name="path/to/model/weights/model.safetensors", size=4_000_000_000),
    ]
    minio_client = MagicMock()
    minio_client.client.list_objects = MagicMock(return_value=listed_objects)

    with patch("app.custom_models.service.MinioClient", return_value=minio_client):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source="s3://my-bucket/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )

    assert not any("missing recommended file(s): config.json" in warning for warning in result.warnings)
    assert not any("should include tokenizer.json or tokenizer_config.json" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_preview_s3_source_rejects_missing_prefix_listing(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """S3 preview reports a dedicated missing-folder error when the prefix does not exist."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_make_k8s_secret_with_data(secret_data))

    minio_client = MagicMock()
    minio_client.client.list_objects = MagicMock(return_value=[])

    with patch("app.custom_models.service.MinioClient", return_value=minio_client):
        with pytest.raises(ValidationException, match="does not exist"):
            await preview_model_source(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                request=PreviewRequest(
                    source_type="s3",
                    source="s3://my-bucket/path/to/model/",
                    s3_storage_name="s3-storage",
                ),
            )


@pytest.mark.asyncio
async def test_preview_s3_source_rejects_empty_prefix_listing(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """S3 preview reports a separate empty-folder error when the prefix marker exists but has no files."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_make_k8s_secret_with_data(secret_data))

    minio_client = MagicMock()
    minio_client.client.list_objects = MagicMock(return_value=[MagicMock(object_name="path/to/model/", size=0)])

    with patch("app.custom_models.service.MinioClient", return_value=minio_client):
        with pytest.raises(ValidationException, match="is empty"):
            await preview_model_source(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                request=PreviewRequest(
                    source_type="s3",
                    source="s3://my-bucket/path/to/model/",
                    s3_storage_name="s3-storage",
                ),
            )


@pytest.mark.asyncio
async def test_preview_s3_source_rejects_unknown_use_case_label(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """S3 preview raises 400 when the secret carries an unrecognized use-case label value."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(
        return_value=_make_k8s_secret_with_data(secret_data, labels={USE_CASE_LABEL: "not-a-valid-use-case"})
    )

    with pytest.raises(ValidationException, match="unrecognized use-case label value"):
        await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source="s3://my-bucket/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )


@pytest.mark.asyncio
async def test_preview_s3_source_rejects_non_s3_airm_fallback_use_case_secret(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """S3 preview should reject non-S3 use-case labels on the AIRM fallback key too."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(
        return_value=_make_k8s_secret_with_data(
            secret_data, labels={AIRM_USE_CASE_LABEL: SecretUseCase.HUGGING_FACE.value}
        )
    )

    with pytest.raises(ForbiddenException, match="cannot be used for S3 preview"):
        await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source="s3://my-bucket/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )


@pytest.mark.asyncio
async def test_preview_s3_source_rejects_non_s3_use_case_secret(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """S3 preview returns a distinct forbidden error for non-S3 secret labels."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(
        return_value=_make_k8s_secret_with_data(secret_data, labels={USE_CASE_LABEL: SecretUseCase.HUGGING_FACE.value})
    )

    with pytest.raises(ForbiddenException, match="cannot be used for S3 preview"):
        await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source="s3://my-bucket/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )


S3_CARD_WITH_PROVENANCE = b"""---
base_model: mistralai/Mistral-7B-v0.1
tags:
  - conversational
---

# Fine-tuned model
"""

S3_CONFIG_JSON = b'{"model_type": "mistral", "architectures": ["MistralForCausalLM"]}'


def _make_s3_object_reader(contents: dict[str, bytes]) -> MagicMock:
    """Build a get_object stub serving ``contents`` keyed by full object name.

    Object names absent from ``contents`` raise, mirroring a denied or missing
    read so tests can assert discovery degrades instead of failing.
    """

    def _get_object(bucket: str, object_name: str) -> MagicMock:
        if object_name not in contents:
            raise RuntimeError(f"no such object: {object_name}")
        payload = contents[object_name]
        response = MagicMock(spec_set=["read", "close", "release_conn"])
        response.read = MagicMock(return_value=payload)
        return response

    return MagicMock(side_effect=_get_object)


def _make_s3_preview_client(listed_objects: list[MagicMock], contents: dict[str, bytes]) -> MagicMock:
    minio_client = MagicMock()
    minio_client.client.list_objects = MagicMock(return_value=listed_objects)
    minio_client.client.get_object = _make_s3_object_reader(contents)
    return minio_client


def _s3_listing(*relative_paths: str) -> list[MagicMock]:
    return [MagicMock(object_name=f"path/to/model/{relative_path}", size=1_024) for relative_path in relative_paths]


async def _preview_s3_with(
    mock_kube_client: AsyncMock,
    test_namespace: str,
    minio_client: MagicMock,
    hub_patch: Any = None,
) -> Any:
    """Run an S3 preview against a prepared MinIO stub with valid credentials."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(
        return_value=_make_k8s_secret_with_data(secret_data, labels={USE_CASE_LABEL: SecretUseCase.S3.value})
    )

    with (
        patch("app.custom_models.service.MinioClient", return_value=minio_client),
        patch("app.custom_models.service._fetch_hub_model", **(hub_patch or {"return_value": {}})) as mock_fetch,
    ):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source="s3://my-bucket/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )
    return result, mock_fetch


@pytest.mark.asyncio
async def test_preview_s3_source_resolves_tags_from_base_model_provenance(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """A card citing a resolvable base model yields that model's catalog tags."""
    minio_client = _make_s3_preview_client(
        _s3_listing("model.safetensors", "config.json", "README.md", "tokenizer.json"),
        {
            "path/to/model/README.md": S3_CARD_WITH_PROVENANCE,
            "path/to/model/config.json": S3_CONFIG_JSON,
        },
    )
    hub_payload = {"tags": ["text-generation", "mistral"], "pipeline_tag": "text-generation"}

    result, mock_fetch = await _preview_s3_with(
        mock_kube_client, test_namespace, minio_client, {"return_value": hub_payload}
    )

    assert result.tags == [
        "text-generation",
        "mistral",
        "conversational",
    ]
    assert result.pipeline_tag == "text-generation"
    # Provenance is resolved by repo id against the fixed Hub base, with no
    # revision and — critically — no namespace token attached.
    mock_fetch.assert_awaited_once_with("mistralai/Mistral-7B-v0.1", None, None)


@pytest.mark.asyncio
async def test_preview_s3_source_falls_back_to_card_tags_when_hub_lookup_fails(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """An unreachable base model degrades to author-written card tags, not an error."""
    minio_client = _make_s3_preview_client(
        _s3_listing("model.safetensors", "config.json", "README.md", "tokenizer.json"),
        {
            "path/to/model/README.md": S3_CARD_WITH_PROVENANCE,
            "path/to/model/config.json": S3_CONFIG_JSON,
        },
    )

    result, _ = await _preview_s3_with(
        mock_kube_client,
        test_namespace,
        minio_client,
        {"side_effect": ExternalServiceError("hub is down")},
    )

    assert result.tags == ["conversational"]


@pytest.mark.asyncio
async def test_preview_s3_source_returns_no_tags_when_only_config_exists(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """Framework configuration is not treated as display metadata."""
    minio_client = _make_s3_preview_client(
        _s3_listing("model.safetensors", "config.json", "tokenizer.json"),
        {"path/to/model/config.json": S3_CONFIG_JSON},
    )

    result, mock_fetch = await _preview_s3_with(mock_kube_client, test_namespace, minio_client)

    assert result.tags == []
    mock_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_preview_s3_source_returns_no_tags_when_nothing_is_discoverable(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """With no card and no usable config, preview succeeds reporting no discoverable tags."""
    minio_client = _make_s3_preview_client(
        _s3_listing("model.safetensors", "config.json", "tokenizer.json"),
        {"path/to/model/config.json": b'{"hidden_size": 4096}'},
    )

    result, _ = await _preview_s3_with(mock_kube_client, test_namespace, minio_client)

    assert result.tags == []


@pytest.mark.asyncio
async def test_preview_s3_source_succeeds_when_metadata_objects_cannot_be_read(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """Tag discovery is display metadata: an unreadable card must not fail the preview."""
    minio_client = _make_s3_preview_client(
        _s3_listing("model.safetensors", "config.json", "README.md", "tokenizer.json"),
        {},
    )

    result, _ = await _preview_s3_with(mock_kube_client, test_namespace, minio_client)

    assert result.tags == []
    assert result.layout_hint == "safetensors"


@pytest.mark.asyncio
async def test_preview_s3_source_ignores_non_utf8_model_card(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """A binary model card yields no tags rather than raising."""
    minio_client = _make_s3_preview_client(
        _s3_listing("model.safetensors", "README.md"),
        {"path/to/model/README.md": b"\xff\xfe\x00binary"},
    )

    result, _ = await _preview_s3_with(mock_kube_client, test_namespace, minio_client)

    assert result.tags == []
    assert result.layout_hint == "safetensors"


@pytest.mark.asyncio
async def test_preview_s3_source_bounds_metadata_reads(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """Metadata reads are capped so an oversized object cannot be streamed during preview."""
    reader = MagicMock(spec_set=["read", "close", "release_conn"])
    reader.read = MagicMock(return_value=S3_CARD_WITH_PROVENANCE)
    minio_client = MagicMock()
    minio_client.client.list_objects = MagicMock(return_value=_s3_listing("model.safetensors", "README.md"))
    minio_client.client.get_object = MagicMock(return_value=reader)

    await _preview_s3_with(mock_kube_client, test_namespace, minio_client)

    reader.read.assert_called_once_with(SOURCE_METADATA_MAX_BYTES)
    reader.release_conn.assert_called_once()


@pytest.mark.asyncio
async def test_preview_s3_source_ignores_nested_readme(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """A nested README is not treated as the model's own card."""
    minio_client = _make_s3_preview_client(
        _s3_listing("model.safetensors", "examples/README.md"),
        {"path/to/model/examples/README.md": S3_CARD_WITH_PROVENANCE},
    )

    result, mock_fetch = await _preview_s3_with(mock_kube_client, test_namespace, minio_client)

    assert result.tags == []
    mock_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_preview_s3_source_does_not_resolve_non_repo_id_provenance(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """A card citing a URL as its base model must not steer an outbound request."""
    card = b"---\nbase_model: https://evil.example/owner/model\ntags:\n  - vision\n---\n"
    minio_client = _make_s3_preview_client(
        _s3_listing("model.safetensors", "README.md"),
        {"path/to/model/README.md": card},
    )

    result, mock_fetch = await _preview_s3_with(mock_kube_client, test_namespace, minio_client)

    mock_fetch.assert_not_awaited()
    assert result.tags == ["vision"]


@pytest.mark.asyncio
async def test_preview_s3_source_requires_required_layout_files(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """S3 preview succeeds with warnings when recommended layout files are missing."""
    secret_data = {
        "AWS_ACCESS_KEY_ID": base64.b64encode(b"access-key").decode(),
        "AWS_SECRET_ACCESS_KEY": base64.b64encode(b"secret-key").decode(),
    }
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_make_k8s_secret_with_data(secret_data))

    listed_objects = [MagicMock(object_name="path/to/model/model-00001-of-00001.safetensors", size=4_000_000_000)]
    minio_client = MagicMock()
    minio_client.client.list_objects = MagicMock(return_value=listed_objects)

    with patch("app.custom_models.service.MinioClient", return_value=minio_client):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(
                source_type="s3",
                source="s3://my-bucket/path/to/model/",
                s3_storage_name="s3-storage",
            ),
        )

    assert any("missing recommended file(s): config.json" in warning for warning in result.warnings)
    assert any("should include tokenizer.json or tokenizer_config.json" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_preview_weight_files_classified(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """Preview weight files are correctly classified as shards and config."""
    hub_data = {**HUB_RESPONSE, "gated": False}
    with patch("app.custom_models.service._fetch_hub_model", return_value=hub_data):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(source="meta-llama/Meta-Llama-3-8B-Instruct"),
        )

    shards = [f for f in result.weight_files if f.role == "shard"]
    configs = [f for f in result.weight_files if f.role == "config"]
    assert len(shards) == 2
    assert len(configs) == 1
    assert configs[0].path == "config.json"


@pytest.mark.asyncio
async def test_preview_not_gated_model(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """Non-gated public model sets gated=False and hf_token_recommended=False."""
    hub_data = {**HUB_RESPONSE, "gated": False, "private": False}
    with patch("app.custom_models.service._fetch_hub_model", return_value=hub_data):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(source="org/model"),
        )
    assert result.gated is False
    assert result.hf_token_recommended is False


@pytest.mark.asyncio
async def test_preview_private_model_sets_token_recommended(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """Private model (not gated) still sets hf_token_recommended=True."""
    hub_data = {**HUB_RESPONSE, "gated": False, "private": True}
    with patch("app.custom_models.service._fetch_hub_model", return_value=hub_data):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(source="org/model"),
        )
    assert result.hf_token_recommended is True


@pytest.mark.asyncio
async def test_preview_gated_repo_without_token_raises_forbidden(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """Gated model without a token raises ForbiddenException.

    HF returns HTTP 200 with gated='manual' or gated='auto' for gated repos
    regardless of whether a token is supplied. The service must reject the
    request before returning metadata so callers are told to provide a token.
    """
    hub_data = {**HUB_RESPONSE, "gated": "manual"}
    with patch("app.custom_models.service._fetch_hub_model", return_value=hub_data):
        with pytest.raises(ForbiddenException, match="hfTokenSecretName"):
            await preview_model_source(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                request=PreviewRequest(source="meta-llama/Meta-Llama-3-8B-Instruct"),
            )


@pytest.mark.asyncio
async def test_preview_url_embedded_revision_is_used(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """A revision embedded in the source URL is forwarded to the Hub call."""
    hub_data = {**HUB_RESPONSE, "gated": False}
    with patch("app.custom_models.service._fetch_hub_model", return_value=hub_data) as mock_fetch:
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(source="https://huggingface.co/org/model/tree/dev-branch"),
        )
    mock_fetch.assert_called_once_with("org/model", "dev-branch", None)
    assert result.revision == "dev-branch"


@pytest.mark.asyncio
async def test_preview_no_url_revision_omits_param_and_returns_sha(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """A bare repo id source results in revision=None being passed to the Hub
    call (so Hub picks the default branch) and the response revision falls back
    to the resolved SHA."""
    hub_data = {**HUB_RESPONSE, "gated": False}
    with patch("app.custom_models.service._fetch_hub_model", return_value=hub_data) as mock_fetch:
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(source="org/model"),
        )
    mock_fetch.assert_called_once_with("org/model", None, None)
    assert result.revision == "abc123"
    assert result.sha == "abc123"


@pytest.mark.asyncio
async def test_preview_hub_response_without_sha_raises_external_service_error(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """If the Hub returns 200 but no SHA, we have nothing to pin against and
    cannot honour the response contract; surface as ExternalServiceError."""
    hub_data = {**HUB_RESPONSE, "gated": False}
    hub_data.pop("sha", None)
    with patch("app.custom_models.service._fetch_hub_model", return_value=hub_data):
        with pytest.raises(ExternalServiceError, match="did not return a SHA"):
            await preview_model_source(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                request=PreviewRequest(source="org/model"),
            )


@pytest.mark.asyncio
async def test_preview_url_revision_without_sha_still_raises_external_service_error(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """Missing SHA is an upstream error even when the caller supplied a URL
    revision."""
    hub_data = {**HUB_RESPONSE, "gated": False}
    hub_data.pop("sha", None)
    with patch("app.custom_models.service._fetch_hub_model", return_value=hub_data):
        with pytest.raises(ExternalServiceError, match="did not return a SHA"):
            await preview_model_source(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                request=PreviewRequest(source="https://huggingface.co/org/model/tree/v1.0"),
            )


@pytest.mark.asyncio
async def test_preview_empty_sha_string_is_treated_as_missing(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """An empty-string SHA is just as un-pinnable as a missing one."""
    hub_data = {**HUB_RESPONSE, "gated": False, "sha": ""}
    with patch("app.custom_models.service._fetch_hub_model", return_value=hub_data):
        with pytest.raises(ExternalServiceError, match="did not return a SHA"):
            await preview_model_source(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                request=PreviewRequest(source="org/model"),
            )


@pytest.mark.asyncio
async def test_preview_display_name_falls_back_to_repo_id(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """Display name is derived from repo id when cardData has no model_name."""
    hub_data = {**HUB_RESPONSE, "gated": False, "cardData": {}}
    with patch("app.custom_models.service._fetch_hub_model", return_value=hub_data):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(source="org/My-Cool-Model"),
        )
    assert result.display_name == "My Cool Model"


@pytest.mark.asyncio
async def test_preview_empty_siblings_returns_no_weight_files(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """Empty siblings list results in an empty weight_files list without error."""
    hub_data = {**HUB_RESPONSE, "gated": False, "siblings": []}
    with patch("app.custom_models.service._fetch_hub_model", return_value=hub_data):
        result = await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(source="org/model"),
        )
    assert result.weight_files == []
    assert result.layout_hint is None


@pytest.mark.asyncio
async def test_preview_resolves_hf_token_and_passes_to_hub(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """When hfTokenSecretName is given, the token is read from K8s and passed to Hub."""
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_make_k8s_secret("hf_mytoken"))
    with patch("app.custom_models.service._fetch_hub_model", return_value=HUB_RESPONSE) as mock_fetch:
        await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(source="org/model", hf_token_secret_name="my-hf-secret"),
        )
    mock_fetch.assert_called_once_with("org/model", None, "hf_mytoken")


@pytest.mark.asyncio
async def test_preview_secret_not_found_raises_not_found(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """NotFoundException is raised when the referenced K8s secret does not exist."""
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(side_effect=ApiException(status=404))
    with pytest.raises(NotFoundException, match="not found"):
        await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(source="org/model", hf_token_secret_name="missing-secret"),
        )


@pytest.mark.asyncio
async def test_preview_secret_missing_token_key_raises_validation(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """ValidationException is raised when the secret exists but has no 'token' key."""
    secret = _make_k8s_secret()
    secret.data = {"other_key": "value"}
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=secret)

    with pytest.raises(ValidationException, match="'token' key"):
        await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(source="org/model", hf_token_secret_name="bad-secret"),
        )


@pytest.mark.asyncio
async def test_preview_empty_token_value_raises_validation(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """An empty (or whitespace-only) decoded token must fail fast with a
    ValidationException rather than silently falling through to an anonymous
    Hub request that would surface as a confusing 401/403."""
    secret = _make_k8s_secret_from_raw_token_value(base64.b64encode(b"   \n\t ").decode())
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=secret)

    with patch("app.custom_models.service._fetch_hub_model") as mock_fetch:
        with pytest.raises(ValidationException, match="empty 'token' value"):
            await preview_model_source(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                request=PreviewRequest(source="org/model", hf_token_secret_name="empty-secret"),
            )
        mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_preview_malformed_token_value_does_not_leak_raw_bytes(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """A malformed base64 'token' value must not leak partial bytes into the
    user-facing ValidationException — ``binascii.Error`` stringifications can
    include slices of the offending input, which on a partially-correct secret
    would expose token material."""
    secret = _make_k8s_secret_from_raw_token_value("hf_secret_marker_!!!not_base64")
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=secret)

    with pytest.raises(ValidationException) as exc_info:
        await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(source="org/model", hf_token_secret_name="malformed-secret"),
        )
    message = str(exc_info.value)
    assert "hf_secret_marker" not in message
    assert "!!!not_base64" not in message
    assert "invalid 'token' value" in message


@pytest.mark.asyncio
async def test_preview_token_with_stray_non_base64_chars_is_rejected(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    secret = _make_k8s_secret_from_raw_token_value("YWJj!ZA==")
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=secret)

    with patch("app.custom_models.service._fetch_hub_model") as mock_fetch:
        with pytest.raises(ValidationException, match="invalid 'token' value"):
            await preview_model_source(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                request=PreviewRequest(source="org/model", hf_token_secret_name="stray-chars-secret"),
            )
        mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_preview_unlabelled_secret_with_token_key_is_accepted(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """A secret without any HF use-case label is fine as long as it has a 'token' key.

    We trust the caller's choice: they have namespace access and could read the
    same secret with kubectl directly.
    """
    secret = _make_k8s_secret("hf_unlabelled_token")
    secret.metadata.labels = {}
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=secret)

    with patch("app.custom_models.service._fetch_hub_model", return_value=HUB_RESPONSE) as mock_fetch:
        await preview_model_source(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            request=PreviewRequest(source="org/model", hf_token_secret_name="any-secret"),
        )
    mock_fetch.assert_called_once_with("org/model", None, "hf_unlabelled_token")


@pytest.mark.asyncio
async def test_preview_propagates_forbidden_from_fetch(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """preview_model_source propagates ForbiddenException from _fetch_hub_model unchanged.

    The exact (status, token) → message mapping is verified in the
    ``raise_for_hub_status`` tests in test_utils.py; here we only confirm the
    service does not swallow or re-wrap the exception.
    """
    with patch("app.custom_models.service._fetch_hub_model", side_effect=ForbiddenException("Denied")):
        with pytest.raises(ForbiddenException):
            await preview_model_source(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                request=PreviewRequest(source="org/gated-model"),
            )


@pytest.mark.asyncio
async def test_preview_hub_404_raises_not_found(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """Hub 404 maps to NotFoundException."""
    with patch("app.custom_models.service._fetch_hub_model", side_effect=NotFoundException("Not found")):
        with pytest.raises(NotFoundException):
            await preview_model_source(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                request=PreviewRequest(source="org/nonexistent-model"),
            )


@pytest.mark.asyncio
async def test_preview_hub_timeout_raises_external_service_error(
    mock_kube_client: AsyncMock, test_namespace: str
) -> None:
    """Hub timeout maps to ExternalServiceError."""
    with patch("app.custom_models.service._fetch_hub_model", side_effect=ExternalServiceError("Timeout")):
        with pytest.raises(ExternalServiceError):
            await preview_model_source(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                request=PreviewRequest(source="org/model"),
            )


@pytest.mark.asyncio
async def test_preview_invalid_source_raises_validation_error(mock_kube_client: AsyncMock, test_namespace: str) -> None:
    """Malformed source raises ValidationException before any Hub call is made."""
    with patch("app.custom_models.service._fetch_hub_model") as mock_fetch:
        with pytest.raises(ValidationException):
            await preview_model_source(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                request=PreviewRequest(source="not-a-valid-repo"),
            )
        mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_hub_model_sends_auth_header() -> None:
    """Token is forwarded as Authorization Bearer header."""
    body = json.dumps(HUB_RESPONSE).encode()
    with _mock_hub_response(200, body) as mock_ctx:
        mock_client = mock_ctx.return_value.__aenter__.return_value
        await _fetch_hub_model("org/model", "main", "hf_tok")
    assert mock_client.stream.call_args.kwargs["headers"]["Authorization"] == "Bearer hf_tok"


@pytest.mark.asyncio
async def test_fetch_hub_model_sends_revision_param_when_provided() -> None:
    """A non-None revision is forwarded as a `revision` query parameter."""
    body = json.dumps(HUB_RESPONSE).encode()
    with _mock_hub_response(200, body) as mock_ctx:
        mock_client = mock_ctx.return_value.__aenter__.return_value
        await _fetch_hub_model("org/model", "v1.0", None)
    assert mock_client.stream.call_args.kwargs["params"] == {"blobs": "true", "revision": "v1.0"}


@pytest.mark.asyncio
async def test_fetch_hub_model_omits_revision_param_when_none() -> None:
    """When revision is None, no `revision` query parameter is sent so Hub resolves
    the actual default branch rather than assuming 'main'."""
    body = json.dumps(HUB_RESPONSE).encode()
    with _mock_hub_response(200, body) as mock_ctx:
        mock_client = mock_ctx.return_value.__aenter__.return_value
        await _fetch_hub_model("org/model", None, None)
    assert mock_client.stream.call_args.kwargs["params"] == {"blobs": "true"}


@pytest.mark.asyncio
async def test_fetch_hub_model_401_with_token_raises_forbidden_invalid_token() -> None:
    """Hub 401 + a token → 'invalid or expired' message."""
    with _mock_hub_response(401, b""):
        with pytest.raises(ForbiddenException) as exc_info:
            await _fetch_hub_model("org/model", "main", "hf_tok")
    assert "invalid or expired" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_hub_model_401_without_token_raises_forbidden_requires_token() -> None:
    """Hub 401 + no token → message says a token is required."""
    with _mock_hub_response(401, b""):
        with pytest.raises(ForbiddenException) as exc_info:
            await _fetch_hub_model("org/gated-model", "main", None)
    assert "requires a Hugging Face token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_hub_model_403_with_token_raises_forbidden() -> None:
    """Hub 403 + a token → access denied message for that repo."""
    with _mock_hub_response(403, b""):
        with pytest.raises(ForbiddenException) as exc_info:
            await _fetch_hub_model("org/gated-model", "main", "hf_tok")
    assert "does not have access" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_hub_model_403_without_token_raises_forbidden_requires_token() -> None:
    """Hub 403 + no token → message says a token is required."""
    with _mock_hub_response(403, b""):
        with pytest.raises(ForbiddenException) as exc_info:
            await _fetch_hub_model("org/gated-model", "main", None)
    assert "requires a Hugging Face token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_hub_model_auth_error_does_not_leak_token() -> None:
    """The 401/403 message text never includes the token value."""
    with _mock_hub_response(401, b""):
        with pytest.raises(ForbiddenException) as exc_info:
            await _fetch_hub_model("org/model", "main", "hf_secret_value_xyz")
    assert "hf_secret_value_xyz" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_hub_model_404_raises_not_found() -> None:
    with _mock_hub_response(404, b""):
        with pytest.raises(NotFoundException):
            await _fetch_hub_model("org/model", "main", None)


@pytest.mark.asyncio
async def test_fetch_hub_model_401_invalid_credentials_raises_not_found() -> None:
    """HF returns 401 'Invalid username or password.' for nonexistent orgs/repos.

    This is distinct from 401 on a gated model (which also returns 401 but with
    a different error body). The service must surface this as NotFoundException
    so the API returns 404 rather than 403.
    """
    with _mock_hub_response(401, b'{"error":"Invalid username or password."}'):
        with pytest.raises(NotFoundException):
            await _fetch_hub_model("org/nonexistent", None, None)


@pytest.mark.asyncio
async def test_fetch_hub_model_500_raises_external_service_error() -> None:
    with _mock_hub_response(500, b""):
        with pytest.raises(ExternalServiceError):
            await _fetch_hub_model("org/model", "main", None)


@pytest.mark.asyncio
async def test_fetch_hub_model_timeout_raises_external_service_error() -> None:
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(side_effect=httpx.TimeoutException("timeout"))
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ExternalServiceError, match="Timed out"):
            await _fetch_hub_model("org/model", "main", None)


@pytest.mark.asyncio
async def test_fetch_hub_model_request_error_does_not_leak_token_repr() -> None:
    """When httpx raises a RequestError the user-facing message must not contain the token."""
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(side_effect=httpx.ConnectError("boom token=hf_secret"))
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ExternalServiceError) as exc_info:
            await _fetch_hub_model("org/model", "main", "hf_secret")
    assert "hf_secret" not in str(exc_info.value)
    assert "ConnectError" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_hub_model_unparseable_body_raises_external_service_error() -> None:
    with _mock_hub_response(200, b"not valid json {"):
        with pytest.raises(ExternalServiceError, match="unparseable"):
            await _fetch_hub_model("org/model", "main", None)


@pytest.mark.asyncio
async def test_fetch_hub_model_non_object_json_raises_external_service_error() -> None:
    with _mock_hub_response(200, json.dumps(["not", "an", "object"]).encode()):
        with pytest.raises(ExternalServiceError, match="invalid response shape"):
            await _fetch_hub_model("org/model", "main", None)


@pytest.mark.asyncio
async def test_fetch_hub_model_invalid_siblings_type_raises_external_service_error() -> None:
    body = json.dumps({**HUB_RESPONSE, "siblings": "not-a-list"}).encode()
    with _mock_hub_response(200, body):
        with pytest.raises(ExternalServiceError, match="invalid 'siblings' field"):
            await _fetch_hub_model("org/model", "main", None)


@pytest.mark.asyncio
async def test_fetch_hub_model_oversized_body_raises_external_service_error() -> None:
    """A Hub response that exceeds ``HF_MAX_RESPONSE_BYTES`` short-circuits the
    stream and raises before the full body is buffered into memory."""
    oversized_body = b"x" * (HF_MAX_RESPONSE_BYTES + 1)
    with _mock_hub_response(200, oversized_body, chunk_size=64 * 1024):
        with pytest.raises(ExternalServiceError, match="exceeded"):
            await _fetch_hub_model("org/model", "main", None)


# ---------------------------------------------------------------------------
# finalize_aim_profile_for_onboarded_model
# ---------------------------------------------------------------------------


def _aim_model_manifest_doc(name: str = "llama-3-8b", namespace: str = "kw-test-project") -> dict:
    return {
        "apiVersion": "aim.eai.amd.com/v1alpha1",
        "kind": "AIMModel",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {"aimId": "meta-llama/Llama-3-8B"},
    }


def _make_patched_profile(
    name: str = "llama-3-8b-default",
    namespace: str = "kw-test-project",
    image_ref: str = "amdenterpriseai/aim-base:0.11",
) -> AIMProfileResource:
    return AIMProfileResource.model_validate(
        {
            "metadata": {
                "name": name,
                "namespace": namespace,
                "annotations": {AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION: image_ref},
            },
            "spec": {"aimId": "llama-3-8b", "image": image_ref or "amdenterpriseai/aim-base:0.11"},
            "status": {},
        }
    )


@pytest.mark.asyncio
async def test_finalize_profile_waits_patches_and_writes_multi_doc_manifest(
    mock_kube_client: AsyncMock,
) -> None:
    """Happy path: the helper composes wait → patch → S3 upsert and leaves the
    DR manifest containing both the AIMModel and the now-annotated
    AIMProfile."""
    minio_client = MagicMock(spec=MinioClient)
    patched_profile = _make_patched_profile()

    with (
        patch(
            "app.custom_models.service.wait_for_aim_profile",
            new=AsyncMock(return_value=_make_patched_profile(image_ref="")),
        ) as mock_wait,
        patch(
            "app.custom_models.service.patch_aim_profile",
            new=AsyncMock(return_value=patched_profile),
        ) as mock_patch,
        patch(
            "app.custom_models.service.read_manifest_from_s3",
            return_value=[_aim_model_manifest_doc()],
        ) as mock_read,
        patch("app.custom_models.service.write_manifest_to_s3") as mock_write,
    ):
        result = await finalize_aim_profile_for_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=minio_client,
            namespace="kw-test-project",
            aim_model_name="llama-3-8b",
            image_ref="amdenterpriseai/aim-base:0.11",
            bucket="test-bucket",
        )

    assert result == patched_profile
    mock_wait.assert_awaited_once()
    mock_patch.assert_awaited_once()
    mock_read.assert_called_once()

    _, bucket_arg, key_arg, documents_arg = mock_write.call_args.args
    assert bucket_arg == "test-bucket"
    assert key_arg == "kw-test-project/custom-models/llama-3-8b/manifest.yaml"
    kinds = [doc["kind"] for doc in documents_arg]
    assert kinds == ["AIMModel", "AIMProfile"]
    profile_doc = documents_arg[1]
    assert profile_doc["apiVersion"] == "aim.eai.amd.com/v1alpha2"
    assert profile_doc["metadata"]["annotations"][AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION] == (
        "amdenterpriseai/aim-base:0.11"
    )


@pytest.mark.asyncio
async def test_finalize_profile_raises_precondition_when_profile_never_appears(
    mock_kube_client: AsyncMock,
) -> None:
    """When aim-engine doesn't emit the profile, the helper must raise a
    domain precondition error *before* touching S3 — that's the
    no-orphans contract."""
    minio_client = MagicMock(spec=MinioClient)

    with (
        patch(
            "app.custom_models.service.wait_for_aim_profile",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.custom_models.service.patch_aim_profile",
            new=AsyncMock(),
        ) as mock_patch,
        patch("app.custom_models.service.read_manifest_from_s3") as mock_read,
        patch("app.custom_models.service.write_manifest_to_s3") as mock_write,
    ):
        with pytest.raises(PreconditionNotMetException, match="did not emit"):
            await finalize_aim_profile_for_onboarded_model(
                kube_client=mock_kube_client,
                minio_client=minio_client,
                namespace="kw-test-project",
                aim_model_name="llama-3-8b",
            )

    mock_patch.assert_not_awaited()
    mock_read.assert_not_called()
    mock_write.assert_not_called()


@pytest.mark.asyncio
async def test_finalize_profile_raises_precondition_when_manifest_scaffold_missing(
    mock_kube_client: AsyncMock,
) -> None:
    """The AIMModel document is written by the sibling onboard step; if it's
    not in S3 when we try to append the profile, we'd silently lose the
    AIMModel half of the durable record — better to fail loud.

    Critically, the missing-scaffold precondition must be checked *before*
    we mutate the cluster: otherwise a missing scaffold would leave the
    profile annotated with no corresponding durable record, forcing the
    compensation path to also unpatch.
    """
    minio_client = MagicMock(spec=MinioClient)

    with (
        patch(
            "app.custom_models.service.wait_for_aim_profile",
            new=AsyncMock(return_value=_make_patched_profile()),
        ),
        patch(
            "app.custom_models.service.patch_aim_profile",
            new=AsyncMock(return_value=_make_patched_profile()),
        ) as mock_patch,
        patch("app.custom_models.service.read_manifest_from_s3", return_value=[]),
        patch("app.custom_models.service.write_manifest_to_s3") as mock_write,
    ):
        with pytest.raises(PreconditionNotMetException, match="missing or"):
            await finalize_aim_profile_for_onboarded_model(
                kube_client=mock_kube_client,
                minio_client=minio_client,
                namespace="kw-test-project",
                aim_model_name="llama-3-8b",
            )

    mock_patch.assert_not_awaited()
    mock_write.assert_not_called()


@pytest.mark.asyncio
async def test_finalize_profile_raises_precondition_when_aim_model_scaffold_missing_from_manifest(
    mock_kube_client: AsyncMock,
) -> None:
    """The manifest object can exist (non-empty) while still missing the
    AIMModel half — e.g. corrupted partial write from an older version,
    manual edits, or a previous run that wrote only the profile.
    Proceeding from here would leave the durable record with an
    AIMProfile orphaned from its scaffold, so we must abort
    *before* patching the cluster."""
    minio_client = MagicMock(spec=MinioClient)
    orphan_profile_doc = {
        "apiVersion": "aim.eai.amd.com/v1alpha2",
        "kind": "AIMProfile",
        "metadata": {"name": "llama-3-8b-default", "namespace": "kw-test-project"},
        "spec": {"aimId": "llama-3-8b"},
    }

    with (
        patch(
            "app.custom_models.service.wait_for_aim_profile",
            new=AsyncMock(return_value=_make_patched_profile()),
        ),
        patch(
            "app.custom_models.service.patch_aim_profile",
            new=AsyncMock(return_value=_make_patched_profile()),
        ) as mock_patch,
        patch(
            "app.custom_models.service.read_manifest_from_s3",
            return_value=[orphan_profile_doc],
        ),
        patch("app.custom_models.service.write_manifest_to_s3") as mock_write,
    ):
        with pytest.raises(PreconditionNotMetException, match="does not contain an AIMModel"):
            await finalize_aim_profile_for_onboarded_model(
                kube_client=mock_kube_client,
                minio_client=minio_client,
                namespace="kw-test-project",
                aim_model_name="llama-3-8b",
            )

    mock_patch.assert_not_awaited()
    mock_write.assert_not_called()


@pytest.mark.asyncio
async def test_finalize_profile_raises_precondition_when_aim_model_scaffold_has_wrong_name(
    mock_kube_client: AsyncMock,
) -> None:
    """An AIMModel document with the wrong name in a namespace-scoped
    manifest is a corruption signal — the S3 key is keyed by model
    name so the document inside should match. Refusing here keeps us
    from silently appending a profile that doesn't belong to the
    AIMModel the manifest claims to describe."""
    minio_client = MagicMock(spec=MinioClient)
    wrong_aim_model = {
        "apiVersion": "aim.eai.amd.com/v1alpha1",
        "kind": "AIMModel",
        "metadata": {"name": "different-model", "namespace": "kw-test-project"},
        "spec": {"aimId": "meta-llama/Different-Model"},
    }

    with (
        patch(
            "app.custom_models.service.wait_for_aim_profile",
            new=AsyncMock(return_value=_make_patched_profile()),
        ),
        patch(
            "app.custom_models.service.patch_aim_profile",
            new=AsyncMock(return_value=_make_patched_profile()),
        ) as mock_patch,
        patch(
            "app.custom_models.service.read_manifest_from_s3",
            return_value=[wrong_aim_model],
        ),
        patch("app.custom_models.service.write_manifest_to_s3") as mock_write,
    ):
        with pytest.raises(PreconditionNotMetException, match="does not contain an AIMModel"):
            await finalize_aim_profile_for_onboarded_model(
                kube_client=mock_kube_client,
                minio_client=minio_client,
                namespace="kw-test-project",
                aim_model_name="llama-3-8b",
            )

    mock_patch.assert_not_awaited()
    mock_write.assert_not_called()


@pytest.mark.asyncio
async def test_finalize_profile_raises_precondition_when_aim_model_scaffold_has_wrong_namespace(
    mock_kube_client: AsyncMock,
) -> None:
    """A namespace mismatch between the S3 key (which is namespace-scoped)
    and the AIMModel document's own ``metadata.namespace`` is a
    cross-namespace corruption signal and must abort."""
    minio_client = MagicMock(spec=MinioClient)
    cross_namespace_aim_model = {
        "apiVersion": "aim.eai.amd.com/v1alpha1",
        "kind": "AIMModel",
        "metadata": {"name": "llama-3-8b", "namespace": "other-project"},
        "spec": {"aimId": "meta-llama/Llama-3-8B"},
    }

    with (
        patch(
            "app.custom_models.service.wait_for_aim_profile",
            new=AsyncMock(return_value=_make_patched_profile()),
        ),
        patch(
            "app.custom_models.service.patch_aim_profile",
            new=AsyncMock(return_value=_make_patched_profile()),
        ) as mock_patch,
        patch(
            "app.custom_models.service.read_manifest_from_s3",
            return_value=[cross_namespace_aim_model],
        ),
        patch("app.custom_models.service.write_manifest_to_s3") as mock_write,
    ):
        with pytest.raises(PreconditionNotMetException, match="does not contain an AIMModel"):
            await finalize_aim_profile_for_onboarded_model(
                kube_client=mock_kube_client,
                minio_client=minio_client,
                namespace="kw-test-project",
                aim_model_name="llama-3-8b",
            )

    mock_patch.assert_not_awaited()
    mock_write.assert_not_called()


@pytest.mark.asyncio
async def test_finalize_profile_accepts_aim_model_scaffold_without_namespace_field(
    mock_kube_client: AsyncMock,
) -> None:
    """The S3 key already pins the namespace, so an AIMModel document
    that omits ``metadata.namespace`` is treated as implicitly belonging
    to the namespace under which the manifest is stored. Required so
    existing manifests from older versions (or ones written by callers
    that don't bother to set namespace on the in-cluster doc) don't
    trigger a false precondition failure."""
    minio_client = MagicMock(spec=MinioClient)
    namespaceless_aim_model = {
        "apiVersion": "aim.eai.amd.com/v1alpha1",
        "kind": "AIMModel",
        "metadata": {"name": "llama-3-8b"},
        "spec": {"aimId": "meta-llama/Llama-3-8B"},
    }
    patched = _make_patched_profile()

    with (
        patch(
            "app.custom_models.service.wait_for_aim_profile",
            new=AsyncMock(return_value=patched),
        ),
        patch(
            "app.custom_models.service.patch_aim_profile",
            new=AsyncMock(return_value=patched),
        ) as mock_patch,
        patch(
            "app.custom_models.service.read_manifest_from_s3",
            return_value=[namespaceless_aim_model],
        ),
        patch("app.custom_models.service.write_manifest_to_s3") as mock_write,
    ):
        await finalize_aim_profile_for_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=minio_client,
            namespace="kw-test-project",
            aim_model_name="llama-3-8b",
        )

    mock_patch.assert_awaited_once()
    mock_write.assert_called_once()


@pytest.mark.asyncio
async def test_finalize_profile_strips_server_populated_metadata_from_manifest(
    mock_kube_client: AsyncMock,
) -> None:
    """The durable record must be re-appliable into a freshly-installed
    cluster, so server-populated metadata fields — ``uid``,
    ``creationTimestamp``, ``ownerReferences`` — must not leak into the
    S3 manifest. ``uid`` is forbidden to set on create, and stale
    ``ownerReferences`` point at AIMModel uids that no longer exist
    post-reinstall."""
    minio_client = MagicMock(spec=MinioClient)
    patched_with_server_fields = AIMProfileResource.model_validate(
        {
            "metadata": {
                "name": "llama-3-8b-default",
                "namespace": "kw-test-project",
                "uid": "11111111-2222-3333-4444-555555555555",
                "creationTimestamp": "2026-05-25T16:00:00Z",
                "ownerReferences": [
                    {
                        "apiVersion": "aim.eai.amd.com/v1alpha1",
                        "kind": "AIMModel",
                        "name": "llama-3-8b",
                        "uid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    }
                ],
                "annotations": {AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION: "amdenterpriseai/aim-base:0.11"},
            },
            "spec": {"aimId": "llama-3-8b", "image": "amdenterpriseai/aim-base:0.11"},
            "status": {"ready": True},
        }
    )

    with (
        patch(
            "app.custom_models.service.wait_for_aim_profile",
            new=AsyncMock(return_value=patched_with_server_fields),
        ),
        patch(
            "app.custom_models.service.patch_aim_profile",
            new=AsyncMock(return_value=patched_with_server_fields),
        ),
        patch(
            "app.custom_models.service.read_manifest_from_s3",
            return_value=[_aim_model_manifest_doc()],
        ),
        patch("app.custom_models.service.write_manifest_to_s3") as mock_write,
    ):
        await finalize_aim_profile_for_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=minio_client,
            namespace="kw-test-project",
            aim_model_name="llama-3-8b",
        )

    documents = mock_write.call_args.args[3]
    profile_doc = next(d for d in documents if d["kind"] == "AIMProfile")
    metadata = profile_doc["metadata"]

    assert profile_doc["apiVersion"] == "aim.eai.amd.com/v1alpha2"
    assert "uid" not in metadata
    assert "creationTimestamp" not in metadata
    assert "ownerReferences" not in metadata
    assert "status" not in profile_doc
    # Desired-state fields survive — name/namespace/annotations are what
    # ``kubectl apply`` actually needs to recreate the profile.
    assert metadata["name"] == "llama-3-8b-default"
    assert metadata["namespace"] == "kw-test-project"
    assert metadata["annotations"][AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION] == "amdenterpriseai/aim-base:0.11"


@pytest.mark.asyncio
async def test_finalize_profile_is_idempotent_on_re_onboard(
    mock_kube_client: AsyncMock,
) -> None:
    """Re-running onboard for the same model updates the AIMProfile
    document in place and does not append a duplicate."""
    minio_client = MagicMock(spec=MinioClient)
    existing_profile_doc = {
        "apiVersion": "aim.eai.amd.com/v1alpha2",
        "kind": "AIMProfile",
        "metadata": {
            "name": "llama-3-8b-default",
            "namespace": "kw-test-project",
            "annotations": {AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION: "amdenterpriseai/aim-base:0.10"},
        },
        "spec": {"aimId": "llama-3-8b", "image": "amdenterpriseai/aim-base:0.10"},
    }
    repatched = _make_patched_profile(image_ref="amdenterpriseai/aim-base:0.11")

    with (
        patch(
            "app.custom_models.service.wait_for_aim_profile",
            new=AsyncMock(return_value=_make_patched_profile()),
        ),
        patch(
            "app.custom_models.service.patch_aim_profile",
            new=AsyncMock(return_value=repatched),
        ),
        patch(
            "app.custom_models.service.read_manifest_from_s3",
            return_value=[_aim_model_manifest_doc(), existing_profile_doc],
        ),
        patch("app.custom_models.service.write_manifest_to_s3") as mock_write,
    ):
        await finalize_aim_profile_for_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=minio_client,
            namespace="kw-test-project",
            aim_model_name="llama-3-8b",
            image_ref="amdenterpriseai/aim-base:0.11",
        )

    documents = mock_write.call_args.args[3]
    assert len(documents) == 2
    profile_docs = [d for d in documents if d["kind"] == "AIMProfile"]
    assert len(profile_docs) == 1
    assert profile_docs[0]["metadata"]["annotations"][AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION] == (
        "amdenterpriseai/aim-base:0.11"
    )


@pytest.mark.asyncio
async def test_finalize_profile_forwards_custom_profile_onto_patch_spec(
    mock_kube_client: AsyncMock,
) -> None:
    """A non-empty ``custom_profile`` from ``OnboardRequest`` must reach the
    AIMProfile patch as ``custom_profile_spec`` so user-supplied runtime
    parameters land on the live CR (and, via the post-patch mirror, the
    durable manifest)."""
    minio_client = MagicMock(spec=MinioClient)
    overrides = {
        "engine": "vllm",
        "engineArgs": {"max-model-len": 8192},
        "metric": "throughput",
    }
    patched = _make_patched_profile()

    with (
        patch(
            "app.custom_models.service.wait_for_aim_profile",
            new=AsyncMock(return_value=patched),
        ),
        patch(
            "app.custom_models.service.patch_aim_profile",
            new=AsyncMock(return_value=patched),
        ) as mock_patch,
        patch(
            "app.custom_models.service.read_manifest_from_s3",
            return_value=[_aim_model_manifest_doc()],
        ),
        patch("app.custom_models.service.write_manifest_to_s3"),
    ):
        await finalize_aim_profile_for_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=minio_client,
            namespace="kw-test-project",
            aim_model_name="llama-3-8b",
            custom_profile=overrides,
        )

    mock_patch.assert_awaited_once()
    assert mock_patch.await_args is not None
    forwarded = mock_patch.await_args.kwargs["custom_profile_spec"]
    assert forwarded == overrides


@pytest.mark.asyncio
async def test_finalize_profile_omits_custom_profile_when_not_supplied(
    mock_kube_client: AsyncMock,
) -> None:
    """Callers that don't supply ``custom_profile`` should pay no extra
    cost — the patch must run with ``custom_profile_spec=None`` so the
    gateway emits an annotation-only patch body."""
    minio_client = MagicMock(spec=MinioClient)
    patched = _make_patched_profile()

    with (
        patch(
            "app.custom_models.service.wait_for_aim_profile",
            new=AsyncMock(return_value=patched),
        ),
        patch(
            "app.custom_models.service.patch_aim_profile",
            new=AsyncMock(return_value=patched),
        ) as mock_patch,
        patch(
            "app.custom_models.service.read_manifest_from_s3",
            return_value=[_aim_model_manifest_doc()],
        ),
        patch("app.custom_models.service.write_manifest_to_s3"),
    ):
        await finalize_aim_profile_for_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=minio_client,
            namespace="kw-test-project",
            aim_model_name="llama-3-8b",
        )

    assert mock_patch.await_args is not None
    assert mock_patch.await_args.kwargs["custom_profile_spec"] is None


def test_profile_manifest_document_preserves_unmodeled_spec_fields() -> None:
    """Regression for the DR-correctness invariant: the typed
    ``AIMProfileSpec`` only declares the v1alpha2 fields the API
    references explicitly, but aim-engine populates additional
    desired-state fields (resources, runtime config, …). Without
    ``extra="allow"`` on the spec model those fields are silently
    dropped before the renderer ever sees them, and the durable
    manifest written to S3 becomes an incomplete copy of the live CR —
    a post-reinstall ``kubectl apply -f manifest.yaml`` would then
    recreate a stub profile incapable of running inference.

    Locks in both the schema-level invariant (extras survive
    ``model_validate``) and the renderer-level invariant (extras
    survive ``model_dump`` into the manifest doc).
    """
    profile = AIMProfileResource.model_validate(
        {
            "metadata": {
                "name": "llama-3-8b-default",
                "namespace": "kw-test-project",
                "annotations": {AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION: "amdenterpriseai/aim-base:0.11"},
            },
            "spec": {
                "aimId": "llama-3-8b",
                "image": "amdenterpriseai/aim-base:0.11",
                # Fields aim-engine populates but AIMProfileSpec does not
                # model — must round-trip via ``extra="allow"``.
                "resources": {"limits": {"nvidia.com/gpu": "1", "memory": "32Gi"}},
                "runtimeConfigName": "llama-default",
                "extraScheduling": {"nodeSelector": {"gpu": "mi300x"}},
            },
            "status": {},
        }
    )

    document = _profile_resource_to_manifest_document(profile)

    spec = document["spec"]
    assert spec["aimId"] == "llama-3-8b"
    assert spec["image"] == "amdenterpriseai/aim-base:0.11"
    assert spec["resources"] == {"limits": {"nvidia.com/gpu": "1", "memory": "32Gi"}}
    assert spec["runtimeConfigName"] == "llama-default"
    assert spec["extraScheduling"] == {"nodeSelector": {"gpu": "mi300x"}}
