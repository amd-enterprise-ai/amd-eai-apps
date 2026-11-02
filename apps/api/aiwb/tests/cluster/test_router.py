# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for cluster catalog router endpoints."""

from unittest.mock import AsyncMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from app import app  # type: ignore[attr-defined]
from app.cluster.schemas import ClusterAccelerator
from tests.dependency_overrides import BASE_OVERRIDES, override_dependencies


@override_dependencies(BASE_OVERRIDES)
def test_list_aim_images_returns_catalog() -> None:
    with TestClient(app) as client:
        response = client.get("/v1/cluster/aim-images")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert "data" in body
    assert isinstance(body["data"], list)
    assert body["data"][0]["familyId"] == "automatic"
    assert body["data"][0]["repository"] is None
    family_ids = {item["familyId"] for item in body["data"]}
    assert family_ids == {"automatic", "aim-base"}
    first_family = body["data"][1]
    assert first_family["familyId"] == "aim-base"
    assert "displayName" in first_family
    assert "tags" in first_family
    assert "deviceId" not in first_family


@override_dependencies(BASE_OVERRIDES)
@patch("app.cluster.router.get_cluster_accelerators", new_callable=AsyncMock)
def test_list_cluster_accelerators_returns_data(mock_get_accelerators: AsyncMock) -> None:
    mock_get_accelerators.return_value = [
        ClusterAccelerator(
            accelerator_type="gpu",
            device_id="74a1",
            accelerator_vendor="amd",
            product_name="AMD Instinct MI300X",
            allocatable_count=8,
            accelerator_model="MI300X",
        )
    ]
    with TestClient(app) as client:
        response = client.get("/v1/cluster/accelerators")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body == {
        "data": [
            {
                "acceleratorType": "gpu",
                "deviceId": "74a1",
                "acceleratorVendor": "amd",
                "productName": "AMD Instinct MI300X",
                "allocatableCount": 8,
                "acceleratorModel": "MI300X",
            }
        ]
    }


@override_dependencies(BASE_OVERRIDES)
@patch("app.cluster.router.get_cluster_accelerators", new_callable=AsyncMock)
def test_list_cluster_accelerators_empty_list(mock_get_accelerators: AsyncMock) -> None:
    mock_get_accelerators.return_value = []
    with TestClient(app) as client:
        response = client.get("/v1/cluster/accelerators")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"data": []}


@override_dependencies(BASE_OVERRIDES)
@patch("app.cluster.router.get_cluster_accelerators", new_callable=AsyncMock)
def test_list_cluster_accelerators_propagates_service_error(mock_get_accelerators: AsyncMock) -> None:
    mock_get_accelerators.side_effect = RuntimeError("kube unavailable")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/v1/cluster/accelerators")
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
