# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from kubernetes_asyncio.client import ApiException

from api_common.exceptions import ConflictException, ExternalServiceError, NotFoundException, ValidationException
from app.secrets.constants import USE_CASE_LABEL
from app.storages.constants import STORAGE_CONFIGMAP_LABEL, STORAGE_TYPE_LABEL
from app.storages.enums import StorageType
from app.storages.schemas import ProjectStorageCreateRequest, S3StorageSpec
from app.storages.service import (
    _resolve_s3_secret_key_names,
    create_project_storage,
    generate_storage_name,
    list_project_storages,
)


def _request(access_key_name: str | None = None, secret_key_name: str | None = None) -> ProjectStorageCreateRequest:
    return ProjectStorageCreateRequest(
        display_name="Default S3 Storage",
        secret_name="s3-credentials",
        spec=S3StorageSpec(
            access_key_name=access_key_name,
            secret_key_name=secret_key_name,
        ),
    )


def test_resolve_s3_secret_key_names_uses_request_values_when_present() -> None:
    request = _request(access_key_name="accessKeyId", secret_key_name="secretAccessKey")
    secret_data = {"accessKeyId": "YWJj", "secretAccessKey": "eHl6"}

    access_key_name, secret_key_name = _resolve_s3_secret_key_names("s3-credentials", secret_data, request)

    assert access_key_name == "accessKeyId"
    assert secret_key_name == "secretAccessKey"


def test_resolve_s3_secret_key_names_autodetects_when_not_provided() -> None:
    request = _request()
    secret_data = {"AWS_ACCESS_KEY_ID": "YWJj", "AWS_SECRET_ACCESS_KEY": "eHl6"}

    access_key_name, secret_key_name = _resolve_s3_secret_key_names("s3-credentials", secret_data, request)

    assert access_key_name == "AWS_ACCESS_KEY_ID"
    assert secret_key_name == "AWS_SECRET_ACCESS_KEY"


def test_resolve_s3_secret_key_names_autodetects_storage_access_key_alias() -> None:
    request = _request()
    secret_data = {"storage-access-key": "YWJj", "storage-secret-key": "eHl6"}

    access_key_name, secret_key_name = _resolve_s3_secret_key_names("s3-credentials", secret_data, request)

    assert access_key_name == "storage-access-key"
    assert secret_key_name == "storage-secret-key"


def test_resolve_s3_secret_key_names_errors_when_alias_missing() -> None:
    request = _request(access_key_name=None, secret_key_name=None)
    secret_data = {"username": "YWJj", "password": "eHl6"}

    with pytest.raises(ValidationException, match="does not contain a detectable access key"):
        _resolve_s3_secret_key_names("s3-credentials", secret_data, request)


def test_resolve_s3_secret_key_names_autodetects_only_missing_value() -> None:
    request = _request(access_key_name="accessKeyId", secret_key_name=None)
    secret_data = {"accessKeyId": "YWJj", "AWS_SECRET_ACCESS_KEY": "eHl6"}

    access_key_name, secret_key_name = _resolve_s3_secret_key_names("s3-credentials", secret_data, request)

    assert access_key_name == "accessKeyId"
    assert secret_key_name == "AWS_SECRET_ACCESS_KEY"


def test_resolve_s3_secret_key_names_errors_when_explicit_key_missing() -> None:
    request = _request(access_key_name="not-present", secret_key_name="secretAccessKey")
    secret_data = {"secretAccessKey": "eHl6"}

    with pytest.raises(ValidationException, match="missing required key 'not-present'"):
        _resolve_s3_secret_key_names("s3-credentials", secret_data, request)


def test_resolve_s3_secret_key_names_errors_when_resolved_keys_are_identical() -> None:
    request = _request(access_key_name="sharedKey", secret_key_name="sharedKey")
    secret_data = {"sharedKey": "eHl6"}

    with pytest.raises(ValidationException, match="same field"):
        _resolve_s3_secret_key_names("s3-credentials", secret_data, request)


def test_generate_storage_name_is_deterministic_and_k8s_compatible() -> None:
    generated = generate_storage_name("Default S3 Storage")
    generated_again = generate_storage_name("Default S3 Storage")
    generated_different = generate_storage_name("Different Storage")

    assert generated.startswith("wb-storage-")
    assert len(generated) <= 63
    assert generated == generated_again
    assert generated != generated_different


def _config_map(
    *,
    name: str,
    display_name: str | None = None,
    storage_type: str = "S3",
    secret_name: str = "s3-credentials",
    bucket_url: str | None = None,
    region: str | None = None,
    access_key_name: str | None = None,
    secret_key_name: str | None = None,
) -> SimpleNamespace:
    data: dict[str, str] = {
        "type": storage_type,
        "secretName": secret_name,
    }
    if bucket_url:
        data["bucketUrl"] = bucket_url
    if region:
        data["region"] = region
    if access_key_name:
        data["accessKeyName"] = access_key_name
    if secret_key_name:
        data["secretKeyName"] = secret_key_name

    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            annotations=(
                {"aiwb.apps.eai.amd.com/storage-display-name": display_name} if display_name is not None else {}
            ),
            labels={
                STORAGE_CONFIGMAP_LABEL: "true",
                STORAGE_TYPE_LABEL: storage_type,
            },
            creation_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        data=data,
    )


@pytest.mark.asyncio
async def test_list_project_storages_returns_storages() -> None:
    kube_client = AsyncMock()
    kube_client.core_v1.list_namespaced_config_map = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                _config_map(
                    name="default-s3-storage",
                    bucket_url="https://s3.example.com/my-bucket",
                    region="us-east-1",
                    access_key_name="accessKeyId",
                    secret_key_name="secretAccessKey",
                ),
            ]
        )
    )

    result = await list_project_storages(kube_client, "test-namespace")

    assert len(result) == 1
    assert result[0].name == "default-s3-storage"
    assert result[0].display_name == "default-s3-storage"
    assert result[0].type == StorageType.S3
    assert result[0].spec.region == "us-east-1"
    kube_client.core_v1.list_namespaced_config_map.assert_awaited_once_with(
        namespace="test-namespace",
        label_selector=f"{STORAGE_CONFIGMAP_LABEL}=true",
    )


@pytest.mark.asyncio
async def test_list_project_storages_accepts_airm_style_uppercase_configmap_keys() -> None:
    kube_client = AsyncMock()
    kube_client.core_v1.list_namespaced_config_map = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                SimpleNamespace(
                    metadata=SimpleNamespace(
                        name="seaweed-storage-info-config-map",
                        annotations={},
                        labels={
                            STORAGE_CONFIGMAP_LABEL: "true",
                            STORAGE_TYPE_LABEL: "S3",
                        },
                        creation_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                    ),
                    data={
                        "SECRET_NAME": "minio-credentials",
                        "BUCKET_URL": "http://filer-s3.seaweedfs-instance.svc.cluster.local:80",
                        "ACCESS_KEY_NAME": "minio-access-key",
                        "SECRET_KEY_NAME": "minio-secret-key",
                    },
                ),
            ]
        )
    )

    result = await list_project_storages(kube_client, "workbench")

    assert len(result) == 1
    assert result[0].name == "seaweed-storage-info-config-map"
    assert result[0].secret_name == "minio-credentials"
    assert result[0].spec.bucket_url == "http://filer-s3.seaweedfs-instance.svc.cluster.local:80"
    assert result[0].spec.access_key_name == "minio-access-key"
    assert result[0].spec.secret_key_name == "minio-secret-key"
    assert result[0].type == StorageType.S3


@pytest.mark.asyncio
async def test_list_project_storages_sorts_by_normalized_display_name_then_name() -> None:
    kube_client = AsyncMock()
    kube_client.core_v1.list_namespaced_config_map = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                _config_map(name="wb-storage-z", display_name="zeta"),
                _config_map(name="wb-storage-b", display_name="  Alpha  "),
                _config_map(name="wb-storage-a", display_name="alpha"),
            ]
        )
    )

    result = await list_project_storages(kube_client, "test-namespace")

    assert [storage.name for storage in result] == [
        "wb-storage-a",
        "wb-storage-b",
        "wb-storage-z",
    ]
    assert [storage.display_name for storage in result] == [
        "alpha",
        "  Alpha  ",
        "zeta",
    ]


@pytest.mark.asyncio
async def test_list_project_storages_applies_type_filter() -> None:
    kube_client = AsyncMock()
    kube_client.core_v1.list_namespaced_config_map = AsyncMock(
        return_value=SimpleNamespace(items=[_config_map(name="default-s3-storage")])
    )

    _ = await list_project_storages(kube_client, "test-namespace", storage_type=StorageType.S3)

    kube_client.core_v1.list_namespaced_config_map.assert_awaited_once_with(
        namespace="test-namespace",
        label_selector=f"{STORAGE_CONFIGMAP_LABEL}=true,{STORAGE_TYPE_LABEL}=S3",
    )


@pytest.mark.asyncio
async def test_list_project_storages_wraps_api_errors() -> None:
    kube_client = AsyncMock()
    kube_client.core_v1.list_namespaced_config_map = AsyncMock(side_effect=ApiException(status=500, reason="boom"))

    with pytest.raises(ExternalServiceError, match="Failed to list storages"):
        await list_project_storages(kube_client, "test-namespace")


def _create_request(
    display_name: str = "Default S3 Storage",
    access_key_name: str | None = "accessKeyId",
    secret_key_name: str | None = "secretAccessKey",
) -> ProjectStorageCreateRequest:
    return ProjectStorageCreateRequest(
        display_name=display_name,
        secret_name="s3-credentials",
        spec=S3StorageSpec(
            bucket_url="https://s3.example.com/my-bucket",
            region="us-east-1",
            access_key_name=access_key_name,
            secret_key_name=secret_key_name,
        ),
    )


def _mock_secret(
    *,
    uid: str = "secret-uid-1234",
    name: str = "s3-credentials",
    labels: dict | None = None,
    data: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            uid=uid,
            labels=labels or {},
        ),
        data=data or {"accessKeyId": "YWJj", "secretAccessKey": "eHl6"},
    )


def _mock_created_config_map(name: str = "wb-storage-1234abcd") -> SimpleNamespace:
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            annotations={},
            creation_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        data={
            "type": "S3",
            "secretName": "s3-credentials",
            "accessKeyName": "accessKeyId",
            "secretKeyName": "secretAccessKey",
            "bucketUrl": "https://s3.example.com/my-bucket",
            "region": "us-east-1",
        },
    )


@pytest.mark.asyncio
async def test_create_project_storage_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.storages.service.generate_storage_name",
        lambda _display_name: "wb-storage-1234abcd",
    )
    kube_client = AsyncMock()
    kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_mock_secret())
    kube_client.core_v1.create_namespaced_config_map = AsyncMock(return_value=_mock_created_config_map())

    result = await create_project_storage(
        kube_client=kube_client,
        namespace="test-namespace",
        submitter="user@example.com",
        request=_create_request(),
    )

    assert result.name == "wb-storage-1234abcd"
    assert result.display_name == "Default S3 Storage"
    assert result.type == StorageType.S3
    assert result.project == "test-namespace"
    assert result.secret_name == "s3-credentials"
    assert result.spec.access_key_name == "accessKeyId"
    assert result.spec.secret_key_name == "secretAccessKey"
    assert result.spec.bucket_url == "https://s3.example.com/my-bucket"
    assert result.spec.region == "us-east-1"
    kube_client.core_v1.create_namespaced_config_map.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_project_storage_normalizes_display_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.storages.service.generate_storage_name",
        lambda _display_name: "wb-storage-1234abcd",
    )
    kube_client = AsyncMock()
    kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_mock_secret())
    kube_client.core_v1.create_namespaced_config_map = AsyncMock(return_value=_mock_created_config_map())

    result = await create_project_storage(
        kube_client=kube_client,
        namespace="test-namespace",
        submitter="user@example.com",
        request=_create_request(display_name="  Default S3 Storage  "),
    )

    assert result.display_name == "Default S3 Storage"
    _, call_kwargs = kube_client.core_v1.create_namespaced_config_map.await_args
    assert call_kwargs["body"].metadata.annotations["aiwb.apps.eai.amd.com/storage-display-name"] == (
        "Default S3 Storage"
    )
    assert call_kwargs["body"].data == {
        "TYPE": "S3",
        "SECRET_NAME": "s3-credentials",
        "ACCESS_KEY_NAME": "accessKeyId",
        "SECRET_KEY_NAME": "secretAccessKey",
        "BUCKET_URL": "https://s3.example.com/my-bucket",
        "REGION": "us-east-1",
    }


@pytest.mark.asyncio
async def test_create_project_storage_autodetects_key_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.storages.service.generate_storage_name",
        lambda _display_name: "wb-storage-1234abcd",
    )
    kube_client = AsyncMock()
    kube_client.core_v1.read_namespaced_secret = AsyncMock(
        return_value=_mock_secret(data={"AWS_ACCESS_KEY_ID": "YWJj", "AWS_SECRET_ACCESS_KEY": "eHl6"})
    )
    kube_client.core_v1.create_namespaced_config_map = AsyncMock(return_value=_mock_created_config_map())

    result = await create_project_storage(
        kube_client=kube_client,
        namespace="test-namespace",
        submitter="user@example.com",
        request=_create_request(access_key_name=None, secret_key_name=None),
    )

    assert result.spec.access_key_name == "AWS_ACCESS_KEY_ID"
    assert result.spec.secret_key_name == "AWS_SECRET_ACCESS_KEY"


@pytest.mark.asyncio
async def test_create_project_storage_raises_not_found_when_secret_missing() -> None:
    kube_client = AsyncMock()
    kube_client.core_v1.read_namespaced_secret = AsyncMock(side_effect=ApiException(status=404, reason="Not Found"))

    with pytest.raises(NotFoundException, match="s3-credentials"):
        await create_project_storage(
            kube_client=kube_client,
            namespace="test-namespace",
            submitter="user@example.com",
            request=_create_request(),
        )


@pytest.mark.asyncio
async def test_create_project_storage_wraps_secret_read_5xx() -> None:
    kube_client = AsyncMock()
    kube_client.core_v1.read_namespaced_secret = AsyncMock(side_effect=ApiException(status=500, reason="boom"))

    with pytest.raises(ExternalServiceError, match="Failed to read secret"):
        await create_project_storage(
            kube_client=kube_client,
            namespace="test-namespace",
            submitter="user@example.com",
            request=_create_request(),
        )


@pytest.mark.asyncio
async def test_create_project_storage_raises_validation_on_wrong_use_case() -> None:
    kube_client = AsyncMock()
    kube_client.core_v1.read_namespaced_secret = AsyncMock(
        return_value=_mock_secret(labels={USE_CASE_LABEL: "HuggingFace"})
    )

    with pytest.raises(ValidationException, match="use case"):
        await create_project_storage(
            kube_client=kube_client,
            namespace="test-namespace",
            submitter="user@example.com",
            request=_create_request(),
        )


@pytest.mark.asyncio
async def test_create_project_storage_raises_validation_on_undetectable_key() -> None:
    kube_client = AsyncMock()
    kube_client.core_v1.read_namespaced_secret = AsyncMock(
        return_value=_mock_secret(data={"username": "YWJj", "password": "eHl6"})
    )

    with pytest.raises(ValidationException, match="does not contain a detectable access key"):
        await create_project_storage(
            kube_client=kube_client,
            namespace="test-namespace",
            submitter="user@example.com",
            request=_create_request(access_key_name=None, secret_key_name=None),
        )


@pytest.mark.asyncio
async def test_create_project_storage_raises_conflict_on_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.storages.service.generate_storage_name",
        lambda _display_name: "wb-storage-1234abcd",
    )
    kube_client = AsyncMock()
    kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_mock_secret())
    kube_client.core_v1.create_namespaced_config_map = AsyncMock(
        side_effect=ApiException(status=409, reason="AlreadyExists")
    )

    with pytest.raises(ConflictException, match="display name 'Default S3 Storage' already exists"):
        await create_project_storage(
            kube_client=kube_client,
            namespace="test-namespace",
            submitter="user@example.com",
            request=_create_request(),
        )


@pytest.mark.asyncio
async def test_create_project_storage_wraps_configmap_create_5xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.storages.service.generate_storage_name",
        lambda _display_name: "wb-storage-1234abcd",
    )
    kube_client = AsyncMock()
    kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_mock_secret())
    kube_client.core_v1.create_namespaced_config_map = AsyncMock(
        side_effect=ApiException(status=500, reason="internal error")
    )

    with pytest.raises(ExternalServiceError, match="Failed to create storage"):
        await create_project_storage(
            kube_client=kube_client,
            namespace="test-namespace",
            submitter="user@example.com",
            request=_create_request(),
        )


@pytest.mark.asyncio
async def test_create_project_storage_rejects_duplicate_display_name() -> None:
    kube_client = AsyncMock()
    kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_mock_secret())
    kube_client.core_v1.list_namespaced_config_map = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                _config_map(
                    name="wb-storage-aaaa1111",
                    display_name="Default S3 Storage",
                ),
            ]
        )
    )

    with pytest.raises(ConflictException, match="display name 'Default S3 Storage' already exists"):
        await create_project_storage(
            kube_client=kube_client,
            namespace="test-namespace",
            submitter="user@example.com",
            request=_create_request(display_name="  Default S3 Storage  "),
        )


@pytest.mark.asyncio
async def test_create_project_storage_rejects_whitespace_only_display_name() -> None:
    kube_client = AsyncMock()
    kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=_mock_secret())

    with pytest.raises(ValidationException, match="non-whitespace character"):
        await create_project_storage(
            kube_client=kube_client,
            namespace="test-namespace",
            submitter="user@example.com",
            request=_create_request(display_name="   "),
        )
