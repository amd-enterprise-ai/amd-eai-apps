# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for Overlays router endpoints using FastAPI TestClient."""

from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from api_common.auth.security import auth_token_claimset
from api_common.exceptions import NotFoundException
from app import app  # type: ignore[attr-defined]
from app.overlays.models import SOURCE_PATH_MAX_LENGTH
from app.overlays.schemas import OverlayResponse
from tests.dependency_overrides import (
    PLATFORM_ADMIN_OVERRIDES,
    SESSION_OVERRIDES,
    TEAM_MEMBER_OVERRIDES,
    override_dependencies,
    runtime_dependency_overrides,
)


@pytest.fixture
def overlay_id() -> UUID:
    return uuid4()


@pytest.fixture
def chart_id() -> UUID:
    return uuid4()


@pytest.fixture
def overlay_response(chart_id: UUID) -> OverlayResponse:
    return OverlayResponse(
        id=uuid4(),
        canonical_name="test-overlay",
        chart_id=chart_id,
        overlay={"key": "value"},
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
        created_by="test-user",
        updated_by="test-user",
    )


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.overlays.router.parse_overlay_file", autospec=True)
@patch("app.overlays.router.create_overlay", autospec=True)
def test_create_overlay(
    mock_service_create_overlay: MagicMock,
    mock_helper_parse_overlay: MagicMock,
    overlay_response: OverlayResponse,
    chart_id: UUID,
) -> None:
    """Test creating an overlay."""
    canonical_name = "test-mock-overlay"
    overlay_data = {"key": "value", "name": canonical_name}

    mock_helper_parse_overlay.return_value = overlay_data
    mock_service_create_overlay.return_value = overlay_response

    with TestClient(app) as client:
        response = client.post(
            "/v1/overlays",
            data={
                "chartId": str(chart_id),
                "canonicalName": canonical_name,
            },
            files={
                "overlayFile": ("test.yaml", BytesIO(b"key: value"), "application/x-yaml"),
            },
        )

    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert response_data["canonicalName"] == overlay_response.canonical_name
    assert response_data["chartId"] == str(overlay_response.chart_id)
    assert response_data["overlay"] == overlay_response.overlay

    mock_helper_parse_overlay.assert_awaited_once()
    mock_service_create_overlay.assert_awaited_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.overlays.router.parse_overlay_file", autospec=True)
@patch("app.overlays.router.create_overlay", side_effect=ValueError("Chart not found"), autospec=True)
def test_create_overlay_non_existent_chart(
    mock_service_create_overlay: MagicMock, mock_helper_parse_overlay: MagicMock, chart_id: UUID
) -> None:
    """Test creating overlay with non-existent chart."""
    canonical_name = "test-mock-nonexistent-chart"
    overlay_data = {"key": "value", "name": canonical_name}

    mock_helper_parse_overlay.return_value = overlay_data

    with TestClient(app) as client:
        response = client.post(
            "/v1/overlays",
            data={
                "chartId": str(chart_id),
                "canonicalName": canonical_name,
            },
            files={
                "overlayFile": ("test.yaml", BytesIO(b"key: value"), "application/x-yaml"),
            },
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Chart not found" in response.json()["detail"]

    mock_helper_parse_overlay.assert_awaited_once()
    mock_service_create_overlay.assert_awaited_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.overlays.router.parse_overlay_file", autospec=True)
@patch("app.overlays.router.create_overlay", side_effect=ValueError("Duplicate canonical name"), autospec=True)
def test_create_overlay_duplicate(
    mock_service_create_overlay: MagicMock, mock_helper_parse_overlay: MagicMock, chart_id: UUID
) -> None:
    """Test creating duplicate overlay."""
    canonical_name = "test-mock-duplicate"
    overlay_data = {"key": "value", "name": canonical_name}

    mock_helper_parse_overlay.return_value = overlay_data

    with TestClient(app) as client:
        response = client.post(
            "/v1/overlays",
            data={
                "chartId": str(chart_id),
                "canonicalName": canonical_name,
            },
            files={
                "overlayFile": ("test.yaml", BytesIO(b"key: value"), "application/x-yaml"),
            },
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Duplicate canonical name" in response.json()["detail"]

    mock_helper_parse_overlay.assert_awaited_once()
    mock_service_create_overlay.assert_awaited_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.overlays.router.parse_overlay_file", side_effect=ValueError("Invalid YAML"), autospec=True)
def test_create_overlay_invalid_yaml(mock_helper_parse_overlay: MagicMock, chart_id: UUID) -> None:
    """Test creating overlay with invalid YAML."""
    canonical_name = "test-mock-invalid-yaml"

    with TestClient(app) as client:
        response = client.post(
            "/v1/overlays",
            data={
                "chartId": str(chart_id),
                "canonicalName": canonical_name,
            },
            files={
                "overlayFile": ("test.yaml", BytesIO(b"invalid: yaml: content"), "application/x-yaml"),
            },
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid YAML" in response.json()["detail"]

    mock_helper_parse_overlay.assert_awaited_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.overlays.router.parse_overlay_file", autospec=True)
@patch("app.overlays.router.update_overlay", autospec=True)
def test_update_overlay_with_file(
    mock_service_update_overlay: MagicMock,
    mock_helper_parse_overlay: MagicMock,
    overlay_response: OverlayResponse,
    chart_id: UUID,
) -> None:
    """Test updating an overlay with a new file."""
    canonical_name = "test-mock-overlay"
    overlay_data = {"key": "value", "name": canonical_name}

    mock_helper_parse_overlay.return_value = overlay_data
    mock_service_update_overlay.return_value = overlay_response

    with TestClient(app) as client:
        response = client.put(
            f"/v1/overlays/{overlay_response.id}",
            data={
                "chartId": str(chart_id),
                "canonicalName": canonical_name,
            },
            files={
                "overlayFile": ("test.yaml", BytesIO(b"key: value"), "application/x-yaml"),
            },
        )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data["canonicalName"] == overlay_response.canonical_name
    assert response_data["chartId"] == str(overlay_response.chart_id)
    assert response_data["overlay"] == overlay_response.overlay

    mock_helper_parse_overlay.assert_awaited_once()
    mock_service_update_overlay.assert_awaited_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.overlays.router.update_overlay", autospec=True)
def test_update_overlay_without_file(
    mock_update_overlay: MagicMock, overlay_response: OverlayResponse, chart_id: UUID
) -> None:
    """Test updating overlay without providing a new file."""
    canonical_name = "test-no-file"
    mock_update_overlay.return_value = overlay_response

    with TestClient(app) as client:
        response = client.put(
            f"/v1/overlays/{overlay_response.id}",
            data={
                "chartId": str(chart_id),
                "canonicalName": canonical_name,
            },
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["canonicalName"] == overlay_response.canonical_name
    assert data["chartId"] == str(overlay_response.chart_id)

    mock_update_overlay.assert_awaited_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.overlays.router.update_overlay", autospec=True)
def test_update_overlay_without_chart_id_does_not_null_it(
    mock_update_overlay: MagicMock, overlay_response: OverlayResponse
) -> None:
    """Test that updating overlay without chart_id does not set chart_id to None."""
    canonical_name = "updated-canonical-name"
    mock_update_overlay.return_value = overlay_response

    with TestClient(app) as client:
        response = client.put(
            f"/v1/overlays/{overlay_response.id}",
            data={
                "canonicalName": canonical_name,
            },
        )

    assert response.status_code == status.HTTP_200_OK

    call_kwargs = mock_update_overlay.call_args
    overlay_update = call_kwargs.kwargs["overlay_update"]
    unset_fields = overlay_update.model_dump(exclude_unset=True)
    assert "chart_id" not in unset_fields, "chart_id should not be set when not provided in the request"
    assert "canonical_name" in unset_fields
    assert unset_fields["canonical_name"] == canonical_name


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.overlays.router.parse_overlay_file", autospec=True)
@patch("app.overlays.router.create_overlay", autospec=True)
def test_create_overlay_rejects_source_path_longer_than_column(
    mock_service_create_overlay: MagicMock, mock_helper_parse_overlay: MagicMock, chart_id: UUID
) -> None:
    """A source path the database column cannot hold is rejected before anything is stored."""
    with TestClient(app) as client:
        response = client.post(
            "/v1/overlays",
            data={"chartId": str(chart_id), "sourcePath": "a" * (SOURCE_PATH_MAX_LENGTH + 1)},
            files={"overlayFile": ("test.yaml", BytesIO(b"key: value"), "application/x-yaml")},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert [error["loc"][-1] for error in response.json()["detail"]] == ["sourcePath"]
    mock_service_create_overlay.assert_not_awaited()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.overlays.router.update_overlay", autospec=True)
def test_update_overlay_rejects_source_path_longer_than_column(
    mock_update_overlay: MagicMock, overlay_response: OverlayResponse
) -> None:
    """A source path the database column cannot hold is rejected before anything is stored."""
    with TestClient(app) as client:
        response = client.put(
            f"/v1/overlays/{overlay_response.id}",
            data={"sourcePath": "a" * (SOURCE_PATH_MAX_LENGTH + 1)},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert [error["loc"][-1] for error in response.json()["detail"]] == ["sourcePath"]
    mock_update_overlay.assert_not_awaited()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.overlays.router.update_overlay", autospec=True)
def test_update_overlay_empty_request(mock_update_overlay: MagicMock, overlay_response: OverlayResponse) -> None:
    """Test updating overlay with no data returns validation error."""
    with TestClient(app) as client:
        resp = client.put(f"/v1/overlays/{overlay_response.id}")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    response_data = resp.json()
    assert "detail" in response_data
    assert (
        "Either 'overlayFile' or 'chartId' or 'canonicalName' or 'displayName' or 'sourcePath' must be provided"
        in response_data["detail"]
    )


@override_dependencies(SESSION_OVERRIDES)
@patch("app.overlays.router.get_overlay_by_id", autospec=True)
def test_get_overlay(mock_service_get_overlay_by_id: MagicMock, overlay_response: OverlayResponse) -> None:
    """Test getting an overlay by ID."""
    mock_service_get_overlay_by_id.return_value = overlay_response

    with TestClient(app) as client:
        response = client.get(f"/v1/overlays/{overlay_response.id}")

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data["id"] == str(overlay_response.id)
    assert response_data["canonicalName"] == overlay_response.canonical_name
    assert response_data["chartId"] == str(overlay_response.chart_id)
    assert response_data["overlay"] == overlay_response.overlay
    assert response_data["createdBy"] == overlay_response.created_by

    mock_service_get_overlay_by_id.assert_awaited_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.overlays.router.get_overlay_by_id", autospec=True)
def test_get_overlay_not_found(mock_service_get_overlay_by_id: MagicMock, overlay_id: UUID) -> None:
    """Test getting a non-existent overlay returns 404."""
    mock_service_get_overlay_by_id.side_effect = NotFoundException("Overlay not found")

    with TestClient(app) as client:
        response = client.get(f"/v1/overlays/{overlay_id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Overlay not found" in response.json()["detail"]

    mock_service_get_overlay_by_id.assert_awaited_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.overlays.router.delete_overlay_by_id_service", autospec=True)
def test_delete_overlay(mock_service_delete_overlay: MagicMock, overlay_id: UUID) -> None:
    """Test deleting an overlay."""
    mock_service_delete_overlay.return_value = None

    with TestClient(app) as client:
        response = client.delete(f"/v1/overlays/{overlay_id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_service_delete_overlay.assert_awaited_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.overlays.router.delete_overlay_by_id_service", autospec=True)
def test_delete_overlay_not_found(mock_service_delete_overlay: MagicMock, overlay_id: UUID) -> None:
    """Test deleting a non-existent overlay returns 404."""
    mock_service_delete_overlay.side_effect = NotFoundException("Overlay not found")

    with TestClient(app) as client:
        response = client.delete(f"/v1/overlays/{overlay_id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Overlay not found" in response.json()["detail"]

    mock_service_delete_overlay.assert_awaited_once()


@pytest.mark.parametrize(
    ("method", "path", "service_function"),
    [
        ("POST", "/v1/overlays", "create_overlay"),
        ("PUT", "/v1/overlays/00000000-0000-0000-0000-000000000001", "update_overlay"),
        ("DELETE", "/v1/overlays/00000000-0000-0000-0000-000000000001", "delete_overlay_by_id_service"),
    ],
    ids=["create", "update", "delete"],
)
@override_dependencies(TEAM_MEMBER_OVERRIDES)
def test_overlay_mutations_require_platform_administrator(method: str, path: str, service_function: str) -> None:
    """Overlays apply to every project's deployments, so a project member without the admin role must not change them."""
    with patch(f"app.overlays.router.{service_function}", autospec=True) as mock_service:
        with TestClient(app) as client:
            response = client.request(
                method,
                path,
                data={"chartId": str(uuid4())},
                files={"overlayFile": ("overlay.yaml", BytesIO(b"key: value"), "application/x-yaml")},
            )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Missing required role: Platform Administrator"
    mock_service.assert_not_called()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.overlays.router.delete_overlay_by_id_service", autospec=True)
def test_platform_administrator_token_can_delete_overlay(mock_service_delete_overlay: MagicMock) -> None:
    """The real role check accepts a token whose realm roles hold Platform Administrator."""
    admin_claims = {"email": "admin@example.com", "realm_access": {"roles": ["Platform Administrator"]}}
    with runtime_dependency_overrides({auth_token_claimset: lambda: admin_claims}), TestClient(app) as client:
        response = client.delete(f"/v1/overlays/{uuid4()}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_service_delete_overlay.assert_awaited_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.overlays.router.list_overlays", autospec=True)
def test_list_overlays(mock_list_overlays: MagicMock, overlay_response: OverlayResponse) -> None:
    """Test listing overlays."""
    mock_list_overlays.return_value = [overlay_response]

    with TestClient(app) as client:
        response = client.get("/v1/overlays")

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert "data" in response_data
    assert len(response_data["data"]) == 1
    assert response_data["data"][0]["id"] == str(overlay_response.id)

    mock_list_overlays.assert_awaited_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.overlays.router.list_overlays", autospec=True)
def test_list_overlays_with_chart_filter(mock_list_overlays: MagicMock, chart_id: UUID) -> None:
    """Test listing overlays with chart_id filter."""
    mock_list_overlays.return_value = []

    with TestClient(app) as client:
        response = client.get(f"/v1/overlays?chartId={chart_id}")

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert "data" in response_data
    assert len(response_data["data"]) == 0

    mock_list_overlays.assert_awaited_once()
