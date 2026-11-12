# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for Charts router endpoints using FastAPI TestClient."""

from unittest.mock import ANY, MagicMock, patch
from uuid import uuid4

import pytest
import yaml
from fastapi import status
from fastapi.testclient import TestClient

from api_common.auth.security import auth_token_claimset
from api_common.exceptions import ConflictException, NotFoundException
from app import app  # type: ignore[attr-defined]
from app.charts.models import Chart
from app.charts.schemas import ChartFile as ChartFileSchema
from app.charts.schemas import ChartListResponse, ChartResponse
from app.workloads.enums import WorkloadType
from tests.dependency_overrides import (
    PLATFORM_ADMIN_OVERRIDES,
    SESSION_OVERRIDES,
    TEAM_MEMBER_OVERRIDES,
    override_dependencies,
    runtime_dependency_overrides,
)


@pytest.fixture
def chart_id():
    return uuid4()


@pytest.fixture
def chart_response():
    return ChartResponse(
        id=uuid4(),
        name="Test Chart",
        slug="test-chart-slug",
        display_name="Test Chart Display Name",
        type=WorkloadType.INFERENCE,
        signature={"key": "value"},
        usage_scope="user",
        created_at="2023-01-01T00:00:00Z",
        updated_at="2023-01-01T00:00:00Z",
        created_by="test@example.com",
        updated_by="test@example.com",
        files=[],
    )


@override_dependencies(SESSION_OVERRIDES)
@patch("app.charts.router.list_charts", autospec=True)
def test_list_charts(mock_repo_list_charts: MagicMock, sample_chart: Chart) -> None:
    """Test list charts endpoint returns 200."""
    expected_response = ChartListResponse.model_validate(sample_chart)
    mock_repo_list_charts.return_value = [expected_response]

    with TestClient(app) as client:
        response = client.get("/v1/charts")
        response_data = response.json()

    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response_data, dict)
    assert "data" in response_data
    assert len(response_data["data"]) == 1
    assert response_data["data"][0]["id"] == str(expected_response.id)
    assert response_data["data"][0]["name"] == expected_response.name
    mock_repo_list_charts.assert_called_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.charts.router.list_charts", autospec=True)
def test_list_charts_with_type_filter(mock_repo_list_charts: MagicMock, sample_chart: Chart) -> None:
    """Test list charts with type filter returns 200."""
    expected_response = ChartListResponse.model_validate(sample_chart)
    mock_repo_list_charts.return_value = [expected_response]

    with TestClient(app) as client:
        response = client.get("/v1/charts", params={"type": WorkloadType.INFERENCE.value})
        response_data = response.json()

    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response_data, dict)
    assert "data" in response_data
    assert len(response_data["data"]) == 1
    mock_repo_list_charts.assert_called_once_with(ANY, WorkloadType.INFERENCE)


@override_dependencies(SESSION_OVERRIDES)
@patch("app.charts.router.list_charts", autospec=True)
def test_list_charts_without_type_filter_forwards_none(mock_repo_list_charts: MagicMock, sample_chart: Chart) -> None:
    """Test list charts without type filter passes None."""
    expected_response = ChartListResponse.model_validate(sample_chart)
    mock_repo_list_charts.return_value = [expected_response]

    with TestClient(app) as client:
        response = client.get("/v1/charts")

    assert response.status_code == status.HTTP_200_OK
    mock_repo_list_charts.assert_called_once_with(ANY, None)


@override_dependencies(SESSION_OVERRIDES)
def test_list_charts_with_invalid_type_returns_422() -> None:
    """Test list charts with invalid type returns 422."""
    with TestClient(app) as client:
        response = client.get("/v1/charts", params={"type": "INVALID_TYPE"})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.charts.router.create_chart", autospec=True)
def test_create_chart_success(mock_repo_create_chart: MagicMock, chart_response: ChartResponse) -> None:
    """Test create chart endpoint returns 201."""
    mock_repo_create_chart.return_value = chart_response

    test_files = [ChartFileSchema(path="file1.yaml", content="content1")]
    with TestClient(app) as client:
        response = client.post(
            "/v1/charts",
            data={"name": chart_response.name, "type": chart_response.type.value},
            files=[
                ("signature", ("values.yaml", yaml.dump(chart_response.signature), "text/yaml")),
                *[("files", (f.path, f.content, "text/plain")) for f in test_files],
            ],
        )

    assert response.status_code == status.HTTP_201_CREATED
    response_json = response.json()
    assert response_json["id"] == str(chart_response.id)
    assert response_json["name"] == chart_response.name
    assert response_json["type"] == chart_response.type.value
    mock_repo_create_chart.assert_called_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.charts.router.update_chart", autospec=True)
def test_update_chart_success(mock_update_chart: MagicMock, chart_response: ChartResponse) -> None:
    """Test update chart endpoint returns 200."""
    mock_update_chart.return_value = chart_response

    with TestClient(app) as client:
        response = client.put(
            f"/v1/charts/{chart_response.id}",
            data={"name": chart_response.name, "type": chart_response.type.value},
            files=[
                ("signature", ("values.yaml", yaml.dump(chart_response.signature), "text/yaml")),
                ("files", ("file1.yaml", "file content", "text/plain")),
            ],
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == str(chart_response.id)
    assert data["name"] == chart_response.name
    mock_update_chart.assert_called_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.charts.router.update_chart", autospec=True)
def test_update_chart_conflict(mock_update_chart: MagicMock, chart_response: ChartResponse) -> None:
    """Test update chart with conflict returns 409."""
    mock_update_chart.side_effect = ConflictException("Chart with the same name already exists")

    with TestClient(app) as client:
        response = client.put(
            f"/v1/charts/{chart_response.id}",
            data={"name": chart_response.name, "type": chart_response.type.value},
            files=[
                ("signature", ("values.yaml", yaml.dump(chart_response.signature), "text/yaml")),
            ],
        )

    assert response.status_code == status.HTTP_409_CONFLICT
    mock_update_chart.assert_called_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch(
    "app.charts.router.create_chart",
    autospec=True,
    side_effect=ConflictException("Chart with the same name already exists"),
)
def test_create_chart_duplicate_name(mock_repo_create_chart: MagicMock) -> None:
    """Test create chart with duplicate name returns 409."""
    test_files = [ChartFileSchema(path="env.txt", content="ENV=production")]
    with TestClient(app) as client:
        response = client.post(
            "/v1/charts",
            data={"name": "duplicate-chart", "type": WorkloadType.FINE_TUNING.value},
            files=[
                ("signature", ("values.yaml", yaml.dump({"key": "value"}), "text/yaml")),
                *[("files", (f.path, f.content, "text/plain")) for f in test_files],
            ],
        )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "already exists" in response.json()["detail"]
    mock_repo_create_chart.assert_called_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.charts.router.create_chart", autospec=True, side_effect=ValueError("Invalid input"))
def test_create_chart_invalid_values(mock_repo_create_chart: MagicMock) -> None:
    """Test create chart with invalid values returns 400."""
    test_files = [ChartFileSchema(path="env.txt", content="ENV=production")]
    with TestClient(app) as client:
        response = client.post(
            "/v1/charts",
            data={"name": "invalid-chart", "type": WorkloadType.FINE_TUNING.value},
            files=[
                ("signature", ("values.yaml", yaml.dump({"key": "value"}), "text/yaml")),
                *[("files", (f.path, f.content, "text/plain")) for f in test_files],
            ],
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid input" in response.json()["detail"]
    mock_repo_create_chart.assert_called_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.charts.router.delete_chart", autospec=True, return_value=False)
def test_delete_chart_not_found(mock_repo_delete_chart: MagicMock) -> None:
    """Test delete chart not found returns 404."""
    non_existent_chart_id = uuid4()
    with TestClient(app) as client:
        response = client.delete(f"/v1/charts/{non_existent_chart_id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Chart not found" in response.json()["detail"]
    mock_repo_delete_chart.assert_called_once()


@override_dependencies(PLATFORM_ADMIN_OVERRIDES)
@patch("app.charts.router.delete_chart", autospec=True)
def test_delete_chart_success(mock_repo_delete_chart: MagicMock, sample_chart: Chart) -> None:
    """Test delete chart success returns 204."""
    mock_repo_delete_chart.return_value = True

    with TestClient(app) as client:
        response = client.delete(f"/v1/charts/{sample_chart.id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_repo_delete_chart.assert_called_once()


@pytest.mark.parametrize(
    ("method", "path", "repository_function"),
    [
        ("POST", "/v1/charts", "create_chart"),
        ("PUT", "/v1/charts/00000000-0000-0000-0000-000000000001", "update_chart"),
        ("DELETE", "/v1/charts/00000000-0000-0000-0000-000000000001", "delete_chart"),
    ],
    ids=["create", "update", "delete"],
)
@override_dependencies(TEAM_MEMBER_OVERRIDES)
def test_chart_mutations_require_platform_administrator(method: str, path: str, repository_function: str) -> None:
    """Charts are cluster-wide, so a project member without the admin role must not change them."""
    with patch(f"app.charts.router.{repository_function}", autospec=True) as mock_repository:
        with TestClient(app) as client:
            response = client.request(
                method,
                path,
                data={"name": "chart", "type": WorkloadType.INFERENCE.value},
                files=[("signature", ("values.yaml", yaml.dump({"key": "value"}), "text/yaml"))],
            )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Missing required role: Platform Administrator"
    mock_repository.assert_not_called()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.charts.router.delete_chart", autospec=True, return_value=True)
def test_platform_administrator_token_can_delete_chart(mock_repo_delete_chart: MagicMock) -> None:
    """The real role check accepts a token whose realm roles hold Platform Administrator."""
    admin_claims = {"email": "admin@example.com", "realm_access": {"roles": ["Platform Administrator"]}}
    with runtime_dependency_overrides({auth_token_claimset: lambda: admin_claims}):
        with TestClient(app) as client:
            response = client.delete(f"/v1/charts/{uuid4()}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_repo_delete_chart.assert_called_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.charts.router.get_chart", autospec=True)
def test_get_chart_success(mock_get_chart: MagicMock, chart_response: ChartResponse) -> None:
    """Test get chart success returns 200."""
    mock_get_chart.return_value = chart_response

    with TestClient(app) as client:
        response = client.get(f"/v1/charts/{chart_response.id}")

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    assert response_json["id"] == str(chart_response.id)
    assert response_json["name"] == chart_response.name
    assert response_json["type"] == chart_response.type.value
    mock_get_chart.assert_called()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.charts.router.get_chart", autospec=True)
def test_get_chart_not_found(mock_get_chart: MagicMock) -> None:
    """Test get chart not found returns 404."""
    non_existent_chart_id = uuid4()
    mock_get_chart.side_effect = NotFoundException(f"Chart with ID {non_existent_chart_id} not found")

    with TestClient(app) as client:
        response = client.get(f"/v1/charts/{non_existent_chart_id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert f"Chart with ID {non_existent_chart_id} not found" in response.json()["detail"]
    mock_get_chart.assert_called()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.charts.router.list_charts", autospec=True)
def test_list_charts_workspace_usage_scope(
    mock_repo_list_charts: MagicMock, workspace_charts: tuple[Chart, Chart]
) -> None:
    """Test that workspace charts return correct usage_scope values."""
    vscode_chart, mlflow_chart = workspace_charts

    vscode_response = ChartListResponse.model_validate(vscode_chart)
    mlflow_response = ChartListResponse.model_validate(mlflow_chart)

    mock_repo_list_charts.return_value = [vscode_response, mlflow_response]

    with TestClient(app) as client:
        response = client.get("/v1/charts")
        response_data = response.json()

    assert response.status_code == status.HTTP_200_OK
    assert "data" in response_data
    assert len(response_data["data"]) == 2

    vscode_data = next(chart for chart in response_data["data"] if chart["name"] == "dev-workspace-vscode")
    mlflow_data = next(chart for chart in response_data["data"] if chart["name"] == "dev-tracking-mlflow")

    # Verify usage_scope values match the expected mapping
    assert vscode_data["usageScope"] == "user"
    assert mlflow_data["usageScope"] == "namespace"

    mock_repo_list_charts.assert_called_once()
