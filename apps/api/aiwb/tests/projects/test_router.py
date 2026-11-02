# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for projects router endpoints using FastAPI TestClient with dependency overrides."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from api_common.auth.security import get_user_groups
from api_common.exceptions import NotFoundException
from app import app  # type: ignore[attr-defined]
from app.projects.crds import Namespace
from tests.dependency_overrides import BASE_OVERRIDES, override_dependencies
from tests.factory import make_aim_cluster_profile


@override_dependencies(
    {
        **BASE_OVERRIDES,
        get_user_groups: lambda: ["namespace-1", "namespace-2"],
    }
)
@patch("app.projects.router.get_accessible_namespaces", autospec=True)
def test_list_projects(mock_get_namespaces: AsyncMock) -> None:
    """Test GET /projects returns list of accessible projects."""
    mock_namespace1 = MagicMock(spec=Namespace)
    mock_namespace1.name = "namespace-1"
    mock_namespace2 = MagicMock(spec=Namespace)
    mock_namespace2.name = "namespace-2"
    mock_get_namespaces.return_value = [mock_namespace2, mock_namespace1]

    with TestClient(app) as client:
        response = client.get("/v1/projects")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["data"] == [
        {"id": "namespace-1", "name": "namespace-1"},
        {"id": "namespace-2", "name": "namespace-2"},
    ]
    mock_get_namespaces.assert_called_once()


@override_dependencies(
    {
        **BASE_OVERRIDES,
        get_user_groups: lambda: ["namespace-1", "namespace-2"],
    }
)
@patch("app.projects.router.get_accessible_namespaces", autospec=True)
def test_list_projects_empty(mock_get_namespaces: AsyncMock) -> None:
    """Test GET /projects returns empty list when no projects are accessible."""
    mock_get_namespaces.return_value = []

    with TestClient(app) as client:
        response = client.get("/v1/projects")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "data" in data
    assert len(data["data"]) == 0
    mock_get_namespaces.assert_called_once()


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.list_aim_profiles", autospec=True)
def test_list_project_profiles_filters_by_aim_id(mock_list: AsyncMock) -> None:
    """GET /v1/projects/{project}/profiles?aimId=... narrows the result to one model."""
    mock_list.return_value = []

    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/profiles",
            params={"aimId": "org/my-aim"},
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["data"] == []
    assert body["pagination"]["total"] == 0
    mock_list.assert_called_once()
    call_kwargs = mock_list.call_args.kwargs
    assert call_kwargs["namespace"] == "test-namespace"
    assert call_kwargs["aim_ids"] == ["org/my-aim"]


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.list_aim_profiles", autospec=True)
def test_list_project_profiles_batches_multiple_aim_ids(mock_list: AsyncMock) -> None:
    """Repeating ?aimId=... batches namespace profiles for several models in one call."""
    mock_list.return_value = []

    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/profiles",
            params=[("aimId", "org/a"), ("aimId", "org/b")],
        )

    assert response.status_code == status.HTTP_200_OK
    call_kwargs = mock_list.call_args.kwargs
    assert call_kwargs["aim_ids"] == ["org/a", "org/b"]


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.list_aim_profiles", autospec=True)
def test_list_project_profiles_rejects_empty_aim_id(mock_list: AsyncMock) -> None:
    """Empty ?aimId= is rejected with 422 by the schema's per-item min_length=1."""
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/profiles",
            params={"aimId": ""},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    mock_list.assert_not_called()


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.list_aim_profiles", autospec=True)
def test_list_project_profiles_no_filter_returns_all_paginated(mock_list: AsyncMock) -> None:
    """Without aimId the full namespace catalog is returned (paginated)."""
    mock_list.return_value = []

    with TestClient(app) as client:
        response = client.get("/v1/projects/test-namespace/profiles")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["data"] == []
    assert body["pagination"] == {"page": 1, "pageSize": 10, "total": 0}
    call_kwargs = mock_list.call_args.kwargs
    assert call_kwargs["aim_ids"] is None


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.get_aim_profile", autospec=True)
def test_get_project_profile_by_name(mock_get: AsyncMock) -> None:
    """GET /v1/projects/{project}/profiles/{name} returns the single matching profile."""
    profile = make_aim_cluster_profile(name="profile-x", aim_id="org/ft-aim")
    mock_get.return_value = profile

    with TestClient(app) as client:
        response = client.get("/v1/projects/test-namespace/profiles/profile-x")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["metadata"]["name"] == "profile-x"
    call_args = mock_get.call_args.args
    assert call_args[1] == "test-namespace"
    assert call_args[2] == "profile-x"


@override_dependencies(BASE_OVERRIDES)
@patch("app.projects.router.get_aim_profile", autospec=True)
def test_get_project_profile_by_name_404(mock_get: AsyncMock) -> None:
    """Unknown profile name returns 404."""
    mock_get.side_effect = NotFoundException("AIMProfile 'missing' not found in namespace 'test-namespace'")
    with TestClient(app) as client:
        response = client.get("/v1/projects/test-namespace/profiles/missing")

    assert response.status_code == status.HTTP_404_NOT_FOUND
