# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Tests for API keys router endpoints.

Uses TestClient with dependency overrides for consistent HTTP-level testing.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, patch
from uuid import uuid4

from fastapi import status
from fastapi.testclient import TestClient

from api_common.collections import PaginatedResult
from api_common.exceptions import NotFoundException
from app import app  # type: ignore[attr-defined]
from app.apikeys.schemas import (
    ApiKeyDetails,
    ApiKeyMetricsResponse,
    ApiKeyMetricsStats,
    ApiKeyRequestsTimeseries,
    ApiKeyResponse,
    ApiKeyTokensTimeseries,
    ApiKeyWithFullKey,
)
from tests.dependency_overrides import APIKEY_OVERRIDES, PROMETHEUS_OVERRIDES, override_dependencies


def _make_api_key_response(display_name: str = "Production Key") -> ApiKeyResponse:
    return ApiKeyResponse(
        id=uuid4(),
        display_name=display_name,
        truncated_key="amd_aim_api_key_••••••••1234",
        namespace="test-project",
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        created_by="test@example.com",
        updated_by="test@example.com",
    )


@override_dependencies(APIKEY_OVERRIDES)
def test_get_api_keys_success() -> None:
    """Test listing API keys for a project returns the nested paginated envelope."""
    expected_keys = [_make_api_key_response()]

    with patch("app.apikeys.router.list_api_keys_for_namespace") as mock_service:
        mock_service.return_value = PaginatedResult(items=expected_keys, total=1, page=1, page_size=10, total_pages=1)
        with TestClient(app) as client:
            response = client.get("/v1/projects/test-project/api-keys")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["data"][0]["displayName"] == "Production Key"
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pageSize"] == 10
    assert body["pagination"]["total"] == 1
    # Nested pagination envelope must not leak loose top-level keys.
    assert "page" not in body
    assert "pageSize" not in body
    assert "total" not in body
    assert "totalPages" not in body
    assert "totalPages" not in body["pagination"]


@override_dependencies(APIKEY_OVERRIDES)
def test_get_api_keys_paginates_results() -> None:
    """`?page=2&pageSize=10` is forwarded to the service and reflected in the envelope."""
    page_two_keys = [_make_api_key_response(display_name=f"Key {i}") for i in range(5)]

    with patch("app.apikeys.router.list_api_keys_for_namespace") as mock_service:
        mock_service.return_value = PaginatedResult(items=page_two_keys, total=15, page=2, page_size=10, total_pages=2)
        with TestClient(app) as client:
            response = client.get(
                "/v1/projects/test-project/api-keys",
                params={"page": 2, "pageSize": 10},
            )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 5
    assert body["pagination"]["page"] == 2
    assert body["pagination"]["pageSize"] == 10
    assert body["pagination"]["total"] == 15
    mock_service.assert_called_once_with(ANY, "test-namespace", page=2, page_size=10)


@override_dependencies(APIKEY_OVERRIDES)
def test_get_api_keys_uses_default_page_size_of_10() -> None:
    """Without query params, the endpoint defaults to page=1 and pageSize=10."""
    with patch("app.apikeys.router.list_api_keys_for_namespace") as mock_service:
        mock_service.return_value = PaginatedResult(items=[], total=0, page=1, page_size=10, total_pages=1)
        with TestClient(app) as client:
            response = client.get("/v1/projects/test-project/api-keys")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pageSize"] == 10
    mock_service.assert_called_once_with(ANY, "test-namespace", page=1, page_size=10)


@override_dependencies(APIKEY_OVERRIDES)
def test_get_api_keys_rejects_invalid_page_size() -> None:
    """`pageSize` must be in [1, 100]; values outside the bound are 422."""
    with TestClient(app) as client:
        too_small = client.get(
            "/v1/projects/test-project/api-keys",
            params={"pageSize": 0},
        )
        too_large = client.get(
            "/v1/projects/test-project/api-keys",
            params={"pageSize": 101},
        )

    assert too_small.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert too_large.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(APIKEY_OVERRIDES)
def test_create_api_key_success() -> None:
    """Test creating a new API key."""
    expected_response = ApiKeyWithFullKey(
        id=uuid4(),
        display_name="New Key",
        truncated_key="amd_aim_api_key_••••••••5678",
        namespace="test-project",
        expires_at=None,
        ttl="24h",
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        created_by="test@example.com",
        updated_by="test@example.com",
        full_key="amd_aim_api_key_hvs.7a3f9b2e1d4c8a6f5e9b2d1c3a7f5678",
    )

    with patch("app.apikeys.router.create_api_key_in_store") as mock_service:
        mock_service.return_value = expected_response
        with TestClient(app) as client:
            response = client.post(
                "/v1/projects/test-project/api-keys",
                json={"displayName": "New Key", "ttl": "24h", "aimIds": []},
            )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["displayName"] == "New Key"


@override_dependencies(APIKEY_OVERRIDES)
def test_get_api_key_details_success() -> None:
    """Test getting detailed API key information."""
    api_key_id = uuid4()
    expected_details = ApiKeyDetails(
        id=api_key_id,
        display_name="Detailed Key",
        truncated_key="amd_aim_api_key_••••••••9999",
        namespace="test-project",
        expires_at=None,
        ttl=None,
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        created_by="test@example.com",
        updated_by="test@example.com",
        groups=["group-1", "group-2"],
    )

    with patch("app.apikeys.router.get_api_key_details_from_store") as mock_service:
        mock_service.return_value = expected_details
        with TestClient(app) as client:
            response = client.get(f"/v1/projects/test-project/api-keys/{api_key_id}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["displayName"] == "Detailed Key"


@override_dependencies(APIKEY_OVERRIDES)
def test_delete_api_key_success() -> None:
    """Test deleting an API key."""
    with patch("app.apikeys.router.delete_api_key_from_store") as mock_service:
        mock_service.return_value = None
        with TestClient(app) as client:
            response = client.delete(f"/v1/projects/test-project/api-keys/{uuid4()}")

    assert response.status_code == status.HTTP_204_NO_CONTENT


@override_dependencies(APIKEY_OVERRIDES)
def test_update_api_key_bindings_success() -> None:
    """Test updating API key AIM deployment bindings."""
    api_key_id = uuid4()
    mock_updated_key = ApiKeyDetails(
        id=api_key_id,
        display_name="Updated Key",
        truncated_key="amd_aim_api_key_••••••••abcd",
        namespace="test-project",
        ttl=None,
        expires_at=None,
        groups=["aim-group-1", "aim-group-2"],
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T01:00:00Z",
        created_by="user@example.com",
        updated_by="user@example.com",
    )

    with patch("app.apikeys.router.update_api_key_bindings_in_store") as mock_service:
        mock_service.return_value = mock_updated_key
        with TestClient(app) as client:
            response = client.patch(
                f"/v1/projects/test-project/api-keys/{api_key_id}",
                json={"aimIds": [str(uuid4()), str(uuid4())]},
            )

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["groups"]) == 2


# ── Metrics endpoint ──────────────────────────────────────────────────────────


def _make_metrics_response() -> ApiKeyMetricsResponse:
    empty_ts: list = []
    return ApiKeyMetricsResponse(
        stats=ApiKeyMetricsStats(
            total_requests=1000,
            successful_requests=980,
            failed_requests=20,
            total_tokens=250000,
            linked_deployments=2,
        ),
        services=["aim-service-a", "aim-service-b"],
        requests_over_time=ApiKeyRequestsTimeseries(total=empty_ts, successful=empty_ts, failed=empty_ts),
        tokens_over_time=ApiKeyTokensTimeseries(total=empty_ts, input=empty_ts, output=empty_ts),
    )


@override_dependencies(PROMETHEUS_OVERRIDES)
def test_get_api_key_metrics_success() -> None:
    """Metrics endpoint returns 200 with camelCase fields matching the response schema."""
    api_key_id = uuid4()

    with patch("app.apikeys.router.get_api_key_usage_metrics") as mock_service:
        mock_service.return_value = _make_metrics_response()
        with TestClient(app) as client:
            response = client.get(
                f"/v1/projects/test-namespace/api-keys/{api_key_id}/metrics",
                params={
                    "start": (datetime.now(UTC) - timedelta(hours=24)).isoformat(),
                    "end": datetime.now(UTC).isoformat(),
                },
            )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["stats"]["totalRequests"] == 1000
    assert body["stats"]["successfulRequests"] == 980
    assert body["stats"]["failedRequests"] == 20
    assert body["stats"]["totalTokens"] == 250000
    assert body["stats"]["linkedDeployments"] == 2
    assert body["services"] == ["aim-service-a", "aim-service-b"]
    assert "requestsOverTime" in body
    assert "tokensOverTime" in body
    # Verify camelCase — snake_case keys must not appear at the top level.
    assert "requests_over_time" not in body
    assert "tokens_over_time" not in body


@override_dependencies(PROMETHEUS_OVERRIDES)
def test_get_api_key_metrics_not_found() -> None:
    """Metrics endpoint returns 404 when the API key does not exist in the project."""
    with patch("app.apikeys.router.get_api_key_usage_metrics") as mock_service:
        mock_service.side_effect = NotFoundException("API key not found")
        with TestClient(app) as client:
            response = client.get(
                f"/v1/projects/test-namespace/api-keys/{uuid4()}/metrics",
                params={
                    "start": (datetime.now(UTC) - timedelta(hours=24)).isoformat(),
                    "end": datetime.now(UTC).isoformat(),
                },
            )

    assert response.status_code == status.HTTP_404_NOT_FOUND
