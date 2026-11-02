# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from fastapi import status
from fastapi.testclient import TestClient
from tests.dependency_overrides import BASE_OVERRIDES, override_dependencies

from api_common.exceptions import ConflictException, NotFoundException, ValidationException
from app import app  # type: ignore[attr-defined]
from app.storages.enums import StorageType
from app.storages.schemas import ProjectStorageResponse, S3StorageSpec

_PROJECT = "test-namespace"
_URL = f"/v1/projects/{_PROJECT}/storages"


def _payload(name: str = "default-s3-storage") -> dict:
    return {
        "displayName": name,
        "type": "S3",
        "secretName": "s3-credentials",
        "spec": {
            "bucketUrl": "https://s3.example.com/my-bucket",
            "accessKeyName": "accessKeyId",
            "secretKeyName": "secretAccessKey",
            "region": "us-east-1",
        },
    }


def _payload_without_key_names(name: str = "default-s3-storage") -> dict:
    return {
        "displayName": name,
        "type": "S3",
        "secretName": "s3-credentials",
        "spec": {
            "bucketUrl": "https://s3.example.com/my-bucket",
            "region": "us-east-1",
        },
    }


def _response() -> ProjectStorageResponse:
    return ProjectStorageResponse(
        name="default-s3-storage",
        display_name="Default S3 Storage",
        project=_PROJECT,
        type=StorageType.S3,
        secret_name="s3-credentials",
        spec=S3StorageSpec(
            bucket_url="https://s3.example.com/my-bucket",
            access_key_name="accessKeyId",
            secret_key_name="secretAccessKey",
            region="us-east-1",
        ),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@override_dependencies(BASE_OVERRIDES)
@patch("app.storages.router.list_storages", new_callable=AsyncMock)
def test_list_storages_returns_200(mock_list_storages: AsyncMock) -> None:
    mock_list_storages.return_value = [_response()]
    with TestClient(app) as client:
        response = client.get(_URL)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["name"] == "default-s3-storage"
    assert body["data"][0]["displayName"] == "Default S3 Storage"


@override_dependencies(BASE_OVERRIDES)
@patch("app.storages.router.list_storages", new_callable=AsyncMock)
def test_list_storages_with_type_filter_returns_200(mock_list_storages: AsyncMock) -> None:
    mock_list_storages.return_value = [_response()]
    with TestClient(app) as client:
        response = client.get(f"{_URL}?type=S3")

    assert response.status_code == status.HTTP_200_OK
    mock_list_storages.assert_awaited_once()
    await_args = mock_list_storages.await_args
    assert await_args is not None
    call_kwargs = await_args.kwargs
    assert call_kwargs["namespace"] == _PROJECT
    assert call_kwargs["storage_type"] == StorageType.S3


@override_dependencies(BASE_OVERRIDES)
@patch("app.storages.router.create_storage", new_callable=AsyncMock)
def test_create_storage_returns_201(mock_create: AsyncMock) -> None:
    mock_create.return_value = _response()
    with TestClient(app) as client:
        response = client.post(_URL, json=_payload())

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["name"] == "default-s3-storage"
    assert body["displayName"] == "Default S3 Storage"
    assert body["project"] == _PROJECT
    assert body["type"] == "S3"
    assert body["secretName"] == "s3-credentials"
    assert body["spec"]["region"] == "us-east-1"


@override_dependencies(BASE_OVERRIDES)
@patch("app.storages.router.create_storage", new_callable=AsyncMock)
def test_create_storage_accepts_single_character_display_name(mock_create: AsyncMock) -> None:
    mock_create.return_value = _response()
    with TestClient(app) as client:
        response = client.post(_URL, json=_payload("a"))

    assert response.status_code == status.HTTP_201_CREATED


@override_dependencies(BASE_OVERRIDES)
@patch("app.storages.router.create_storage", new_callable=AsyncMock)
def test_create_storage_without_key_names_returns_201(mock_create: AsyncMock) -> None:
    mock_create.return_value = _response()
    with TestClient(app) as client:
        response = client.post(_URL, json=_payload_without_key_names())

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["spec"]["accessKeyName"] == "accessKeyId"
    assert body["spec"]["secretKeyName"] == "secretAccessKey"


@override_dependencies(BASE_OVERRIDES)
@patch("app.storages.router.create_storage", new_callable=AsyncMock, side_effect=ConflictException("exists"))
def test_create_storage_returns_409_on_name_conflict(mock_create: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.post(_URL, json=_payload())
    assert response.status_code == status.HTTP_409_CONFLICT


@override_dependencies(BASE_OVERRIDES)
@patch("app.storages.router.create_storage", new_callable=AsyncMock, side_effect=ValidationException("bad secret"))
def test_create_storage_returns_400_on_validation_error(mock_create: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.post(_URL, json=_payload())
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@override_dependencies(BASE_OVERRIDES)
@patch("app.storages.router.create_storage", new_callable=AsyncMock, side_effect=NotFoundException("missing secret"))
def test_create_storage_returns_404_when_secret_missing(mock_create: AsyncMock) -> None:
    with TestClient(app) as client:
        response = client.post(_URL, json=_payload())
    assert response.status_code == status.HTTP_404_NOT_FOUND
