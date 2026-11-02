# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for workloads router endpoints using FastAPI TestClient with dependency overrides."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from prometheus_api_client import PrometheusConnect

from api_common.collections import PaginationMetadata
from api_common.schemas import PaginationMetadataResponse
from app import app  # type: ignore[attr-defined]
from app.logs.schemas import LogEntry, LogLevel, LogType, WorkloadLogsResponse
from app.metrics.client import get_prometheus_client
from app.metrics.enums import MetricName, NamespaceMetricName
from app.metrics.schemas import (
    Datapoint,
    DatapointMetadataBase,
    DatapointsWithMetadata,
    DateRange,
    MetricsScalar,
    MetricsScalarWithRange,
    MetricsTimeseries,
    TimeseriesRange,
)
from app.projects.security import ensure_access_to_project, get_project_namespace
from app.workloads.constants import DESCRIPTION_ANNOTATION, TRAINING_OUTPUT_ANNOTATION
from app.workloads.enums import TrainingOutput, WorkloadStatus, WorkloadType
from app.workloads.schemas import WorkloadDatasetResponse, WorkloadMetricsListPaginated
from tests import factory
from tests.dependency_overrides import (
    PROMETHEUS_OVERRIDES,
    SESSION_OVERRIDES,
    override_dependencies,
    runtime_dependency_overrides,
)
from tests.factory import make_namespace_crd, make_workload_metrics, make_workload_stats_counts


@pytest.fixture(autouse=True)
def mock_finetuning_workloads_annotations() -> Iterator[AsyncMock]:
    with patch(
        "app.workloads.router.get_finetuning_workloads_annotations",
        new_callable=AsyncMock,
        return_value={},
    ) as mock:
        yield mock


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.get_workloads")
def test_list_workloads(mock_get_workloads: AsyncMock) -> None:
    """Test GET /v1/projects/{project}/workloads returns 200."""
    mock_get_workloads.return_value = []

    with TestClient(app) as client:
        response = client.get("/v1/projects/test-project/workloads")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert "data" in body
    assert body["pagination"]["total"] == 0
    mock_get_workloads.assert_called_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.get_workloads")
def test_list_workloads_with_filters(mock_get_workloads: AsyncMock) -> None:
    """Test GET /v1/projects/{project}/workloads with type and status filters."""
    mock_get_workloads.return_value = []

    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-project/workloads",
            params={
                "workloadType": "INFERENCE",
                # WorkloadStatus values are title-cased (see app/workloads/enums.py)
                "statusFilter": "Running",
            },
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert "data" in body
    assert body["pagination"]["total"] == 0
    mock_get_workloads.assert_called_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.resolve_workloads_datasets")
@patch("app.workloads.router.get_workloads")
def test_list_workloads_returns_paginated_envelope(
    mock_get_workloads: AsyncMock,
    mock_resolve_datasets: AsyncMock,
) -> None:
    """GET /v1/projects/{project}/workloads returns the nested pagination envelope."""
    workload = factory.make_workload_mock(
        workload_id=uuid4(),
        name="wl-1",
        display_name="WL 1",
        namespace="test-project",
        workload_type=WorkloadType.WORKSPACE,
        status=WorkloadStatus.RUNNING,
    )
    workload.chart = None
    workload.chart_name = None
    dataset_id = uuid4()
    mock_get_workloads.return_value = [workload]
    mock_resolve_datasets.return_value = {
        workload.id: [WorkloadDatasetResponse(id=dataset_id, name="Training dataset", available=True)]
    }

    with TestClient(app) as client:
        response = client.get("/v1/projects/test-project/workloads")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["datasets"] == [{"id": str(dataset_id), "name": "Training dataset", "available": True}]
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pageSize"] == 10
    assert body["pagination"]["total"] == 1
    # Nested pagination envelope must not leak loose top-level keys.
    assert "total" not in body
    assert "page" not in body
    assert "pageSize" not in body
    assert "totalPages" not in body
    assert "totalPages" not in body["pagination"]


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.resolve_workloads_datasets")
@patch("app.workloads.router.get_workloads")
def test_list_workloads_includes_finetuning_annotations(
    mock_get_workloads: AsyncMock,
    mock_resolve_datasets: AsyncMock,
    mock_finetuning_workloads_annotations: AsyncMock,
) -> None:
    workload = factory.make_workload_mock(
        workload_id=uuid4(),
        name="fine-tuning-job",
        display_name="Fine-tuning job",
        namespace="test-project",
        workload_type=WorkloadType.FINE_TUNING,
        status=WorkloadStatus.RUNNING,
    )
    workload.chart = None
    workload.chart_name = None
    mock_get_workloads.return_value = [workload]
    mock_resolve_datasets.return_value = {workload.id: []}
    annotations = {
        TRAINING_OUTPUT_ANNOTATION: TrainingOutput.LORA.value,
        "example.com/owner": "team-a",
    }
    mock_finetuning_workloads_annotations.return_value = {workload.id: annotations}

    with TestClient(app) as client:
        response = client.get("/v1/projects/test-project/workloads")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"][0]["annotations"] == {
        TRAINING_OUTPUT_ANNOTATION: TrainingOutput.LORA.value,
        "example.com/owner": "team-a",
    }
    mock_finetuning_workloads_annotations.assert_awaited_once_with("test-namespace", [workload.id])


def _make_workload_mock(workload_type: WorkloadType = WorkloadType.WORKSPACE) -> MagicMock:
    workload = factory.make_workload_mock(
        workload_id=uuid4(),
        name="wl",
        display_name="WL",
        namespace="test-project",
        workload_type=workload_type,
        status=WorkloadStatus.RUNNING,
    )
    workload.chart = None
    workload.chart_name = None
    return workload


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.get_workloads")
def test_list_workloads_paginates_results(mock_get_workloads: AsyncMock) -> None:
    """Page slicing covers the right rows and pagination metadata is consistent."""
    mock_get_workloads.return_value = [_make_workload_mock() for _ in range(15)]

    with TestClient(app) as client:
        first = client.get("/v1/projects/test-project/workloads")
        second = client.get(
            "/v1/projects/test-project/workloads",
            params={"page": 2, "pageSize": 10},
        )

    assert first.status_code == status.HTTP_200_OK
    first_body = first.json()
    assert len(first_body["data"]) == 10
    assert first_body["pagination"]["page"] == 1
    assert first_body["pagination"]["pageSize"] == 10
    assert first_body["pagination"]["total"] == 15

    assert second.status_code == status.HTTP_200_OK
    second_body = second.json()
    assert len(second_body["data"]) == 5
    assert second_body["pagination"]["page"] == 2
    assert second_body["pagination"]["total"] == 15


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.get_workloads")
def test_list_workloads_uses_default_page_size_of_10(mock_get_workloads: AsyncMock) -> None:
    """Without query params, the endpoint returns 10 items on page 1."""
    mock_get_workloads.return_value = [_make_workload_mock() for _ in range(25)]

    with TestClient(app) as client:
        response = client.get("/v1/projects/test-project/workloads")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 10
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pageSize"] == 10
    assert body["pagination"]["total"] == 25


@override_dependencies(SESSION_OVERRIDES)
def test_list_workloads_rejects_invalid_page_size() -> None:
    """`pageSize` must be in [1, 100]; values outside the bound are 422."""
    with TestClient(app) as client:
        too_small = client.get(
            "/v1/projects/test-project/workloads",
            params={"pageSize": 0},
        )
        too_large = client.get(
            "/v1/projects/test-project/workloads",
            params={"pageSize": 101},
        )

    assert too_small.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert too_large.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.get_workloads")
def test_list_workloads_pagination_composes_with_filters(mock_get_workloads: AsyncMock) -> None:
    """Pagination slices the filtered set; `total` reflects the filtered count."""
    mock_get_workloads.return_value = [_make_workload_mock(WorkloadType.WORKSPACE) for _ in range(12)]

    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-project/workloads",
            params={"workloadType": "WORKSPACE", "page": 2, "pageSize": 5},
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 5
    assert body["pagination"]["page"] == 2
    assert body["pagination"]["pageSize"] == 5
    assert body["pagination"]["total"] == 12
    # Filter was forwarded to the repository call.
    call_kwargs = mock_get_workloads.call_args.kwargs
    assert call_kwargs["workload_types"] == [WorkloadType.WORKSPACE]


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.get_workload_by_id")
def test_get_workload_not_found(mock_get: AsyncMock) -> None:
    """Test GET /v1/projects/{project}/workloads/{id} returns 404 when not found."""
    workload_id = uuid4()
    mock_get.return_value = None

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-project/workloads/{workload_id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# Removed-endpoint Tests (capability-specific replacements now serve these)
# =============================================================================


@override_dependencies(SESSION_OVERRIDES)
def test_chat_endpoint_returns_404() -> None:
    """POST /workloads/{id}/chat is gone; UI calls AIM internal URL directly."""
    workload_id = uuid4()

    with TestClient(app) as client:
        response = client.post(
            f"/v1/projects/test-project/workloads/{workload_id}/chat",
            json={"messages": []},
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(SESSION_OVERRIDES)
def test_chattable_filter_is_removed() -> None:
    """GET /workloads/chattable is gone; use /v1/projects/{p}/inference?capability=chat instead.

    With the dedicated /chattable route removed, the path now collides with
    /workloads/{workload_id} and "chattable" fails UUID validation (422).
    """
    with TestClient(app) as client:
        response = client.get("/v1/projects/test-project/workloads/chattable")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(SESSION_OVERRIDES)
def test_delete_workload_is_removed() -> None:
    """DELETE /workloads/{id} is gone; capability-specific deletes (inference/fine-tuning/workspaces) replace it.

    Only GET remains on this path, so DELETE yields 405 Method Not Allowed.
    """
    workload_id = uuid4()

    with TestClient(app) as client:
        response = client.delete(f"/v1/projects/test-project/workloads/{workload_id}")

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# =============================================================================
# Metrics Endpoint Tests
# =============================================================================


@override_dependencies(PROMETHEUS_OVERRIDES)
@patch("app.workloads.router.get_metric_by_workload_id")
@patch("app.workloads.service.get_workload_by_id")
def test_get_workload_metrics_success(mock_get_workload: AsyncMock, mock_get_metric: AsyncMock) -> None:
    """Test successful metrics retrieval with Prometheus client."""
    workload_id = uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    start_time = now - timedelta(hours=1)
    end_time = now

    # Mock workload exists
    mock_workload = MagicMock()
    mock_workload.id = workload_id
    mock_get_workload.return_value = mock_workload

    # Mock metrics response with timeseries data
    mock_metric_response = MetricsTimeseries(
        data=[
            DatapointsWithMetadata(
                metadata=DatapointMetadataBase(label="gpu-0"),
                values=[
                    Datapoint(value=50.0, timestamp=start_time),
                    Datapoint(value=75.0, timestamp=end_time),
                ],
            )
        ],
        range=TimeseriesRange(
            start=start_time,
            end=end_time,
            interval_seconds=3600,
            timestamps=[start_time, end_time],
        ),
    )
    mock_get_metric.return_value = mock_metric_response

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/metrics/gpu_device_utilization",
            params={
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
        )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert "data" in response_data
    assert "range" in response_data
    # Check timestamps are present (format may vary: +00:00 vs Z)
    assert "start" in response_data["range"]
    assert "end" in response_data["range"]

    # Verify get_workload_by_id was called correctly
    mock_get_workload.assert_called_once()
    call_kwargs = mock_get_workload.call_args.kwargs
    assert call_kwargs["workload_id"] == workload_id
    # Project value comes from the ensure_access_to_project override in PROMETHEUS_OVERRIDES
    assert call_kwargs["namespace"] == "test-namespace"

    # Verify get_metric_by_workload_id was called correctly
    mock_get_metric.assert_called_once()
    call_kwargs = mock_get_metric.call_args.kwargs
    assert call_kwargs["workload_id"] == str(workload_id)
    assert call_kwargs["metric"] == MetricName.GPU_DEVICE_UTILIZATION
    assert call_kwargs["start"] == start_time
    assert call_kwargs["end"] == end_time
    assert "prometheus_client" in call_kwargs


@override_dependencies(PROMETHEUS_OVERRIDES)
@patch("app.workloads.router.get_metric_by_workload_id")
@patch("app.workloads.service.get_workload_by_id")
def test_get_workload_metrics_scalar_response(mock_get_workload: AsyncMock, mock_get_metric: AsyncMock) -> None:
    """Test metrics endpoint returns scalar value."""
    workload_id = uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    start_time = now - timedelta(hours=1)
    end_time = now

    # Mock workload exists
    mock_workload = MagicMock()
    mock_workload.id = workload_id
    mock_get_workload.return_value = mock_workload

    # Mock metrics response with scalar data
    mock_metric_response = MetricsScalar(data=1000.0)
    mock_get_metric.return_value = mock_metric_response

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/metrics/total_tokens",
            params={
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
        )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert "data" in response_data
    assert response_data["data"] == 1000.0
    assert "range" not in response_data  # Scalar doesn't have range

    # Verify the metric parameter was passed correctly
    mock_get_metric.assert_called_once()
    call_kwargs = mock_get_metric.call_args.kwargs
    assert call_kwargs["metric"] == MetricName.TOTAL_TOKENS


@override_dependencies(PROMETHEUS_OVERRIDES)
@patch("app.workloads.router.get_metric_by_workload_id")
@patch("app.workloads.service.get_workload_by_id")
def test_get_workload_metrics_with_time_range(mock_get_workload: AsyncMock, mock_get_metric: AsyncMock) -> None:
    """Test metrics with start/end time parameters."""
    workload_id = uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    start_time = now - timedelta(days=1)
    end_time = now

    # Mock workload exists
    mock_workload = MagicMock()
    mock_workload.id = workload_id
    mock_get_workload.return_value = mock_workload

    # Mock metrics response with scalar and range
    mock_metric_response = MetricsScalarWithRange(
        data=50.5,
        range=DateRange(start=start_time, end=end_time),
    )
    mock_get_metric.return_value = mock_metric_response

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/metrics/requests",
            params={
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
        )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert "data" in response_data
    assert "range" in response_data
    assert response_data["data"] == 50.5

    # Verify time parameters were forwarded correctly
    mock_get_metric.assert_called_once()
    call_kwargs = mock_get_metric.call_args.kwargs
    assert call_kwargs["start"] == start_time
    assert call_kwargs["end"] == end_time


@override_dependencies(PROMETHEUS_OVERRIDES)
@patch("app.workloads.service.aims_gateway.get_aim_service_by_id")
@patch("app.workloads.service.get_workload_by_id")
def test_get_workload_metrics_workload_not_found(mock_get_workload: AsyncMock, mock_get_aim_service: AsyncMock) -> None:
    """Test 404 when neither a workload nor a live AIMService exists for the id."""
    workload_id = uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    start_time = now - timedelta(hours=1)
    end_time = now

    # Neither a backing workload nor a live AIMService exists
    mock_get_workload.return_value = None
    mock_get_aim_service.return_value = None

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/metrics/gpu_device_utilization",
            params={
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()

    # Verify both existence checks were attempted
    mock_get_workload.assert_called_once()
    mock_get_aim_service.assert_called_once()


@override_dependencies(PROMETHEUS_OVERRIDES)
@patch("app.workloads.router.get_metric_by_workload_id")
@patch("app.workloads.service.aims_gateway.get_aim_service_by_id")
@patch("app.workloads.service.get_workload_by_id")
def test_get_workload_metrics_starting_aim_service(
    mock_get_workload: AsyncMock, mock_get_aim_service: AsyncMock, mock_get_metric: AsyncMock
) -> None:
    """A still-starting AIMService (no backing Deployment yet) yields 200, not 404."""
    workload_id = uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    start_time = now - timedelta(hours=1)
    end_time = now

    mock_get_workload.return_value = None
    mock_get_aim_service.return_value = MagicMock(id=workload_id)
    mock_get_metric.return_value = MetricsTimeseries(
        data=[],
        range=TimeseriesRange(
            start=start_time,
            end=end_time,
            interval_seconds=3600,
            timestamps=[],
        ),
    )

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/metrics/gpu_device_utilization",
            params={
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
        )

    assert response.status_code == status.HTTP_200_OK
    mock_get_aim_service.assert_called_once()
    mock_get_metric.assert_called_once()


@override_dependencies(PROMETHEUS_OVERRIDES)
def test_get_workload_metrics_invalid_metric_name() -> None:
    """Test invalid metric name handling."""
    workload_id = uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    start_time = now - timedelta(hours=1)
    end_time = now

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/metrics/invalid_metric_name",
            params={
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
        )

    # FastAPI should return 422 for invalid enum value
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(PROMETHEUS_OVERRIDES)
@patch("app.workloads.router.get_metric_by_workload_id")
@patch("app.workloads.service.get_workload_by_id")
def test_get_workload_metrics_prometheus_error(mock_get_workload: AsyncMock, mock_get_metric: AsyncMock) -> None:
    """Test Prometheus client error handling."""
    workload_id = uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    start_time = now - timedelta(hours=1)
    end_time = now

    # Mock workload exists
    mock_workload = MagicMock()
    mock_workload.id = workload_id
    mock_get_workload.return_value = mock_workload

    # Mock Prometheus error
    mock_get_metric.side_effect = Exception("Prometheus connection error")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/metrics/gpu_device_utilization",
            params={
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
        )

    # Should return 500 for internal errors
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # Verify both functions were called
    mock_get_workload.assert_called_once()
    mock_get_metric.assert_called_once()


# =============================================================================
# Success Case Tests
# =============================================================================


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.resolve_workload_datasets")
@patch("app.workloads.router.get_workload_by_id")
def test_get_workload_success(mock_get: AsyncMock, mock_resolve_datasets: AsyncMock) -> None:
    """Test GET /v1/projects/{project}/workloads/{id} returns 200 with workload data."""

    workload_id = uuid4()

    # Create a mock workload using centralized factory
    mock_workload = factory.make_workload_mock(
        workload_id=workload_id,
        name="test-workload",
        display_name="Test Workload",
        namespace="test-project",
        workload_type=WorkloadType.FINE_TUNING,
        status=WorkloadStatus.RUNNING,
    )
    # Add additional attributes not in factory defaults
    mock_workload.chart = None
    mock_workload.chart_name = None
    mock_workload.annotations = {TRAINING_OUTPUT_ANNOTATION: TrainingOutput.MERGED.value}

    mock_get.return_value = mock_workload
    dataset_id = uuid4()
    mock_resolve_datasets.return_value = [
        WorkloadDatasetResponse(id=dataset_id, name="Deleted dataset", available=False)
    ]

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-project/workloads/{workload_id}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == str(workload_id)
    assert data["name"] == "test-workload"
    assert data["displayName"] == "Test Workload"
    assert data["type"] == "FINE_TUNING"
    assert data["status"] == "Running"
    assert data["annotations"] == {TRAINING_OUTPUT_ANNOTATION: TrainingOutput.MERGED.value}
    assert data["datasets"] == [{"id": str(dataset_id), "name": "Deleted dataset", "available": False}]
    mock_get.assert_called_once()
    mock_resolve_datasets.assert_awaited_once_with(ANY, workload_id)


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.resolve_workload_datasets")
@patch("app.workloads.router.get_workload_by_id")
def test_get_workload_surfaces_description(mock_get: AsyncMock, mock_resolve_datasets: AsyncMock) -> None:
    """The description supplied at creation is surfaced from the workload's annotation."""
    workload_id = uuid4()
    mock_workload = factory.make_workload_mock(
        workload_id=workload_id,
        name="test-workload",
        display_name="Test Workload",
        namespace="test-project",
        workload_type=WorkloadType.FINE_TUNING,
        status=WorkloadStatus.RUNNING,
    )
    mock_workload.chart = None
    mock_workload.chart_name = None
    mock_workload.annotations = {DESCRIPTION_ANNOTATION: "A helpful description"}

    mock_get.return_value = mock_workload
    mock_resolve_datasets.return_value = []

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-project/workloads/{workload_id}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["description"] == "A helpful description"


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.resolve_workload_datasets")
@patch("app.workloads.router.get_workload_by_id")
def test_get_workload_description_null_when_absent(mock_get: AsyncMock, mock_resolve_datasets: AsyncMock) -> None:
    """With no description annotation the response reports description as null, not an empty string."""
    workload_id = uuid4()
    mock_workload = factory.make_workload_mock(
        workload_id=workload_id,
        name="test-workload",
        display_name="Test Workload",
        namespace="test-project",
        workload_type=WorkloadType.FINE_TUNING,
        status=WorkloadStatus.RUNNING,
    )
    mock_workload.chart = None
    mock_workload.chart_name = None
    mock_workload.annotations = {}

    mock_get.return_value = mock_workload
    mock_resolve_datasets.return_value = []

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-project/workloads/{workload_id}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["description"] is None


@override_dependencies(
    {
        **SESSION_OVERRIDES,
        ensure_access_to_project: lambda: "authorized-project",
    }
)
@patch("app.workloads.router.get_workloads")
def test_list_workloads_authorization(mock_get_workloads: AsyncMock) -> None:
    """Test GET /v1/projects/{project}/workloads succeeds for authorized project."""
    mock_get_workloads.return_value = []

    with TestClient(app) as client:
        response = client.get("/v1/projects/authorized-project/workloads")

    assert response.status_code == status.HTTP_200_OK
    assert "data" in response.json()
    mock_get_workloads.assert_called_once()
    # Verify called with the authorized project (mapped 1:1 to namespace)
    call_kwargs = mock_get_workloads.call_args.kwargs
    assert call_kwargs["namespace"] == "authorized-project"


@override_dependencies(SESSION_OVERRIDES)
def test_endpoint_invalid_uuid_format() -> None:
    """Test endpoints reject malformed UUIDs with 422 error."""
    invalid_uuid = "not-a-valid-uuid"

    with TestClient(app) as client:
        # Test GET workload endpoint
        response = client.get(f"/v1/projects/test-project/workloads/{invalid_uuid}")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "detail" in response.json()


# =============================================================================
# Section 4.1: Authorization Tests
# =============================================================================


def test_get_workload_unauthorized() -> None:
    """Test GET /workloads/{id} with unauthorized project returns 403."""

    def mock_unauthorized_access():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to project 'unauthorized-project'",
        )

    workload_id = uuid4()

    with runtime_dependency_overrides(
        {
            **SESSION_OVERRIDES,
            ensure_access_to_project: mock_unauthorized_access,
        }
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(f"/v1/projects/unauthorized-project/workloads/{workload_id}")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "access" in response.json()["detail"].lower()


def test_get_workload_metrics_unauthorized() -> None:
    """Test GET /workloads/{id}/metrics/{metric} with unauthorized project returns 403."""

    def mock_unauthorized_access():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to project 'unauthorized-project'",
        )

    workload_id = uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    start_time = now - timedelta(hours=1)
    end_time = now

    with runtime_dependency_overrides(
        {
            **PROMETHEUS_OVERRIDES,
            ensure_access_to_project: mock_unauthorized_access,
        }
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                f"/v1/projects/unauthorized-project/workloads/{workload_id}/metrics/gpu_device_utilization",
                params={
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                },
            )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "access" in response.json()["detail"].lower()


def test_get_workload_logs_unauthorized() -> None:
    """Test GET /workloads/{id}/logs with unauthorized project returns 403."""

    def mock_unauthorized_access():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to project 'unauthorized-project'",
        )

    workload_id = uuid4()

    with runtime_dependency_overrides(
        {
            **SESSION_OVERRIDES,
            ensure_access_to_project: mock_unauthorized_access,
        }
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                f"/v1/projects/unauthorized-project/workloads/{workload_id}/logs",
                params={"start": "2025-01-01T00:00:00Z", "end": "2025-01-01T23:59:59Z"},
            )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "access" in response.json()["detail"].lower()


def test_stream_workload_logs_unauthorized() -> None:
    """Test GET /workloads/{id}/logs/stream with unauthorized project returns 403."""

    def mock_unauthorized_access():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to project 'unauthorized-project'",
        )

    workload_id = uuid4()

    with runtime_dependency_overrides(
        {
            **SESSION_OVERRIDES,
            ensure_access_to_project: mock_unauthorized_access,
        }
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(f"/v1/projects/unauthorized-project/workloads/{workload_id}/logs/stream")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "access" in response.json()["detail"].lower()


# =============================================================================
# Section 4.2: Input Validation Tests
# =============================================================================


@override_dependencies(SESSION_OVERRIDES)
def test_list_workloads_invalid_status_filter() -> None:
    """Test status_filter with invalid enum value returns 422."""
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-project/workloads",
            params={
                "statusFilter": "INVALID_STATUS",
            },
        )

    # FastAPI should return 422 for invalid enum value
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "detail" in response.json()


@override_dependencies(PROMETHEUS_OVERRIDES)
def test_metrics_invalid_datetime_format() -> None:
    """Test start/end with malformed datetime returns 422."""
    workload_id = uuid4()

    with TestClient(app) as client:
        # Test invalid start datetime
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/metrics/gpu_device_utilization",
            params={
                "start": "not-a-valid-datetime",
                "end": datetime.now(UTC).isoformat(),
            },
        )

    # FastAPI should return 422 for validation errors
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "detail" in response.json()

    with TestClient(app) as client:
        # Test invalid end datetime
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/metrics/gpu_device_utilization",
            params={
                "start": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                "end": "invalid-datetime-format",
            },
        )

    # FastAPI should return 422 for validation errors
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "detail" in response.json()


# =============================================================================
# GET /workloads/{id}/logs Tests
# =============================================================================


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.get_logs_by_workload_id")
@patch("app.workloads.service.get_workload_by_id")
def test_get_workload_logs_success(mock_get_workload: AsyncMock, mock_get_logs: AsyncMock) -> None:
    """Test successful log retrieval."""
    workload_id = uuid4()
    mock_workload = MagicMock(id=workload_id)
    mock_get_workload.return_value = mock_workload

    # Mock log response
    log_entry = LogEntry(
        timestamp=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC), level=LogLevel.INFO, message="Test log message"
    )
    mock_get_logs.return_value = WorkloadLogsResponse(
        data=[log_entry], pagination=PaginationMetadataResponse(has_more=False, page_token=None, total_returned=1)
    )

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/logs",
            params={"start": "2025-01-01T00:00:00Z", "end": "2025-01-01T23:59:59Z"},
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "data" in data
    assert "pagination" in data
    assert len(data["data"]) == 1
    assert data["data"][0]["level"] == "info"
    assert data["data"][0]["message"] == "Test log message"
    mock_get_workload.assert_called_once()
    mock_get_logs.assert_called_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.get_logs_by_workload_id")
@patch("app.workloads.service.get_workload_by_id")
def test_get_workload_logs_with_filters(mock_get_workload: AsyncMock, mock_get_logs: AsyncMock) -> None:
    """Test with level, log_type, and limit filters."""
    workload_id = uuid4()
    mock_workload = MagicMock(id=workload_id)
    mock_get_workload.return_value = mock_workload

    mock_get_logs.return_value = WorkloadLogsResponse(
        data=[], pagination=PaginationMetadataResponse(has_more=False, page_token=None, total_returned=0)
    )

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/logs",
            params={
                "start": "2025-01-01T00:00:00Z",
                "end": "2025-01-01T23:59:59Z",
                "level": "error",
                "logType": "event",
                "limit": 500,
            },
        )

    assert response.status_code == status.HTTP_200_OK
    mock_get_logs.assert_called_once()

    # Verify the filters were passed correctly
    call_kwargs = mock_get_logs.call_args.kwargs
    assert call_kwargs["level_filter"] == LogLevel.ERROR
    assert call_kwargs["log_type"] == LogType.EVENT
    assert call_kwargs["limit"] == 500


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.get_logs_by_workload_id")
@patch("app.workloads.service.get_workload_by_id")
def test_get_workload_logs_with_pagination(mock_get_workload: AsyncMock, mock_get_logs: AsyncMock) -> None:
    """Test with start_time parameter (page_token)."""
    workload_id = uuid4()
    mock_workload = MagicMock(id=workload_id)
    mock_get_workload.return_value = mock_workload

    next_page_token = "2025-01-01T12:00:00Z"
    mock_get_logs.return_value = WorkloadLogsResponse(
        data=[], pagination=PaginationMetadataResponse(has_more=True, page_token=next_page_token, total_returned=0)
    )

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/logs",
            params={
                "start": "2025-01-01T00:00:00Z",
                "end": "2025-01-01T23:59:59Z",
                "pageToken": "2025-01-01T11:00:00Z",
            },
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["pagination"]["hasMore"] is True
    assert data["pagination"]["pageToken"] == next_page_token
    mock_get_logs.assert_called_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.service.aims_gateway.get_aim_service_by_id")
@patch("app.workloads.service.get_workload_by_id")
def test_get_workload_logs_workload_not_found(mock_get_workload: AsyncMock, mock_get_aim_service: AsyncMock) -> None:
    """Test 404 when neither a workload nor a live AIMService exists for the id."""
    workload_id = uuid4()
    mock_get_workload.return_value = None
    mock_get_aim_service.return_value = None

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/logs",
            params={"start": "2025-01-01T00:00:00Z", "end": "2025-01-01T23:59:59Z"},
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.get_logs_by_workload_id")
@patch("app.workloads.service.aims_gateway.get_aim_service_by_id")
@patch("app.workloads.service.get_workload_by_id")
def test_get_workload_logs_starting_aim_service(
    mock_get_workload: AsyncMock, mock_get_aim_service: AsyncMock, mock_get_logs: AsyncMock
) -> None:
    """A still-starting AIMService (no backing Deployment yet) yields 200 with an empty state, not 404."""
    workload_id = uuid4()
    mock_get_workload.return_value = None
    mock_get_aim_service.return_value = MagicMock(id=workload_id)

    mock_get_logs.return_value = WorkloadLogsResponse(
        data=[], pagination=PaginationMetadataResponse(has_more=False, page_token=None, total_returned=0)
    )

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/logs",
            params={"start": "2025-01-01T00:00:00Z", "end": "2025-01-01T23:59:59Z"},
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["data"] == []
    mock_get_aim_service.assert_called_once()
    mock_get_logs.assert_called_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.get_logs_by_workload_id")
@patch("app.workloads.service.get_workload_by_id")
def test_get_workload_logs_loki_error(mock_get_workload: AsyncMock, mock_get_logs: AsyncMock) -> None:
    """Test Loki client error handling."""
    workload_id = uuid4()
    mock_workload = MagicMock(id=workload_id)
    mock_get_workload.return_value = mock_workload

    # Mock Loki error - service returns empty response on errors
    mock_get_logs.return_value = WorkloadLogsResponse(
        data=[], pagination=PaginationMetadataResponse(has_more=False, page_token=None, total_returned=0)
    )

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/logs",
            params={"start": "2025-01-01T00:00:00Z", "end": "2025-01-01T23:59:59Z"},
        )

    # Service handles errors gracefully and returns empty results
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["data"]) == 0


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.get_logs_by_workload_id")
@patch("app.workloads.service.get_workload_by_id")
def test_get_workload_logs_empty_results(mock_get_workload: AsyncMock, mock_get_logs: AsyncMock) -> None:
    """Test empty log results."""
    workload_id = uuid4()
    mock_workload = MagicMock(id=workload_id)
    mock_get_workload.return_value = mock_workload

    mock_get_logs.return_value = WorkloadLogsResponse(
        data=[], pagination=PaginationMetadataResponse(has_more=False, page_token=None, total_returned=0)
    )

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/logs",
            params={"start": "2025-01-01T00:00:00Z", "end": "2025-01-01T23:59:59Z"},
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["data"]) == 0
    assert data["pagination"]["totalReturned"] == 0
    assert data["pagination"]["hasMore"] is False


# =============================================================================
# GET /workloads/{id}/logs/stream Tests
# =============================================================================


async def mock_log_stream_generator():
    """Mock async generator for log streaming."""
    log_entry = LogEntry(
        timestamp=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC), level=LogLevel.INFO, message="Streaming log"
    )
    yield log_entry.model_dump_json()


async def mock_sse_stream_generator():
    """Mock SSE formatted stream."""
    log_entry = LogEntry(
        timestamp=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC), level=LogLevel.INFO, message="Streaming log"
    )
    yield f"data: {log_entry.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.stream_workload_logs_sse")
@patch("app.workloads.service.get_workload_by_id")
def test_stream_workload_logs_success(mock_get_workload: AsyncMock, mock_stream: AsyncMock) -> None:
    """Test SSE streaming with proper headers."""
    workload_id = uuid4()
    mock_workload = MagicMock(id=workload_id)
    mock_get_workload.return_value = mock_workload

    mock_stream.return_value = mock_sse_stream_generator()

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/logs/stream",
            params={"startTime": "2025-01-01T00:00:00Z"},
        )

    assert response.status_code == status.HTTP_200_OK

    # Verify SSE headers
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["connection"] == "keep-alive"

    # Verify content contains SSE formatted data
    content = response.text
    assert "data: " in content

    mock_get_workload.assert_called_once()
    mock_stream.assert_called_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.stream_workload_logs_sse")
@patch("app.workloads.service.get_workload_by_id")
def test_stream_workload_logs_with_filters(mock_get_workload: AsyncMock, mock_stream: AsyncMock) -> None:
    """Test with level and log_type filters."""
    workload_id = uuid4()
    mock_workload = MagicMock(id=workload_id)
    mock_get_workload.return_value = mock_workload

    mock_stream.return_value = mock_sse_stream_generator()

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/logs/stream",
            params={"level": "warning", "logType": "event"},
        )

    assert response.status_code == status.HTTP_200_OK
    mock_stream.assert_called_once()

    # Verify filters were passed
    call_kwargs = mock_stream.call_args.kwargs
    assert call_kwargs["level_filter"] == LogLevel.WARNING
    assert call_kwargs["log_type"] == LogType.EVENT


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.stream_workload_logs_sse")
@patch("app.workloads.service.get_workload_by_id")
def test_stream_workload_logs_with_delay(mock_get_workload: AsyncMock, mock_stream: AsyncMock) -> None:
    """Test custom delay parameter."""
    workload_id = uuid4()
    mock_workload = MagicMock(id=workload_id)
    mock_get_workload.return_value = mock_workload

    mock_stream.return_value = mock_sse_stream_generator()

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-project/workloads/{workload_id}/logs/stream", params={"delay": 5})

    assert response.status_code == status.HTTP_200_OK
    mock_stream.assert_called_once()

    # Verify delay was passed
    call_kwargs = mock_stream.call_args.kwargs
    assert call_kwargs["delay_seconds"] == 5


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.service.get_workload_by_id")
def test_stream_workload_logs_delay_validation(mock_get_workload: AsyncMock) -> None:
    """Test delay boundary validation (1-30 range)."""
    workload_id = uuid4()
    mock_workload = MagicMock(id=workload_id)
    mock_get_workload.return_value = mock_workload

    with TestClient(app) as client:
        # Test delay too low
        response = client.get(f"/v1/projects/test-project/workloads/{workload_id}/logs/stream", params={"delay": 0})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Test delay too high
        response = client.get(f"/v1/projects/test-project/workloads/{workload_id}/logs/stream", params={"delay": 31})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Verify get_workload was never called for invalid requests
        mock_get_workload.assert_not_called()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.service.aims_gateway.get_aim_service_by_id")
@patch("app.workloads.service.get_workload_by_id")
def test_stream_workload_logs_workload_not_found(mock_get_workload: AsyncMock, mock_get_aim_service: AsyncMock) -> None:
    """Test 404 when neither a workload nor a live AIMService exists for the id."""
    workload_id = uuid4()
    mock_get_workload.return_value = None
    mock_get_aim_service.return_value = None

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-project/workloads/{workload_id}/logs/stream")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.stream_workload_logs_sse")
@patch("app.workloads.service.aims_gateway.get_aim_service_by_id")
@patch("app.workloads.service.get_workload_by_id")
def test_stream_workload_logs_starting_aim_service(
    mock_get_workload: AsyncMock, mock_get_aim_service: AsyncMock, mock_stream: AsyncMock
) -> None:
    """A still-starting AIMService (no backing Deployment yet) streams 200, not 404."""
    workload_id = uuid4()
    mock_get_workload.return_value = None
    mock_get_aim_service.return_value = MagicMock(id=workload_id)
    mock_stream.return_value = mock_sse_stream_generator()

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-project/workloads/{workload_id}/logs/stream")

    assert response.status_code == status.HTTP_200_OK
    mock_get_aim_service.assert_called_once()
    mock_stream.assert_called_once()


async def mock_sse_error_stream():
    """Mock SSE stream with error event."""
    yield 'data: {"error": "Loki connection failed"}\n\n'


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.router.stream_workload_logs_sse")
@patch("app.workloads.service.get_workload_by_id")
def test_stream_workload_logs_loki_error(mock_get_workload: AsyncMock, mock_stream: AsyncMock) -> None:
    """Test error JSON event when Loki fails."""
    workload_id = uuid4()
    mock_workload = MagicMock(id=workload_id)
    mock_get_workload.return_value = mock_workload

    mock_stream.return_value = mock_sse_error_stream()

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-project/workloads/{workload_id}/logs/stream")

    assert response.status_code == status.HTTP_200_OK
    content = response.text
    assert "error" in content
    assert "Loki connection failed" in content


@override_dependencies(SESSION_OVERRIDES)
@patch("app.workloads.service.get_workload_by_id")
def test_stream_workload_logs_invalid_start_time(mock_get_workload: AsyncMock) -> None:
    """Test malformed start_time handling."""
    workload_id = uuid4()
    mock_workload = MagicMock(id=workload_id)
    mock_get_workload.return_value = mock_workload

    with TestClient(app) as client:
        # Invalid ISO format
        response = client.get(
            f"/v1/projects/test-project/workloads/{workload_id}/logs/stream",
            params={"startTime": "invalid-date"},
        )

    # FastAPI returns 422 for validation errors
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ============================================================================
# Tests for project-level workload stats and metrics endpoints
# (migrated from old /v1/namespaces/{namespace}/{stats,metrics,metrics/{metric}}
# to /v1/projects/{project}/workloads/{stats,metrics,metrics/{metric}})
# ============================================================================


def test_get_project_workload_stats() -> None:
    """Test GET /v1/projects/{project}/workloads/stats returns resource counts."""

    mock_namespace = make_namespace_crd(
        name="test-namespace",
        labels={"project-id": "test-project"},
    )
    mock_stats = make_workload_stats_counts(project="test-namespace")

    with (
        runtime_dependency_overrides(
            {
                **SESSION_OVERRIDES,
                get_project_namespace: lambda: mock_namespace,
            }
        ),
        patch("app.workloads.router.get_workload_stats_counts", autospec=True) as mock_get_stats,
    ):
        mock_get_stats.return_value = mock_stats

        with TestClient(app) as client:
            response = client.get("/v1/projects/test-namespace/workloads/stats")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["project"] == "test-namespace"
    assert data["total"] == 5
    assert len(data["statusCounts"]) == 2
    mock_get_stats.assert_called_once()


def test_get_project_workload_metrics() -> None:
    """Test GET /v1/projects/{project}/workloads/metrics returns paginated metrics."""

    mock_namespace = make_namespace_crd(
        name="test-namespace",
        labels={"project-id": "test-project"},
    )
    mock_metric = make_workload_metrics(
        name="test-workload",
        display_name="Test Workload",
        status=WorkloadStatus.RUNNING,
    )
    mock_response = WorkloadMetricsListPaginated(
        data=[mock_metric],
        pagination=PaginationMetadata(page=1, page_size=10, total=1),
    )

    with (
        runtime_dependency_overrides(
            {
                **SESSION_OVERRIDES,
                get_project_namespace: lambda: mock_namespace,
            }
        ),
        patch("app.workloads.router.get_workload_metrics_paginated", autospec=True) as mock_get_metrics,
    ):
        mock_get_metrics.return_value = mock_response

        with TestClient(app) as client:
            response = client.get("/v1/projects/test-namespace/workloads/metrics")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "data" in data
    assert len(data["data"]) == 1
    assert data["data"][0]["name"] == "test-workload"
    assert data["pagination"]["total"] == 1
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["pageSize"] == 10
    # Nested pagination envelope must not leak loose top-level keys.
    assert "total" not in data
    assert "page" not in data
    assert "pageSize" not in data
    assert "totalPages" not in data
    assert "totalPages" not in data["pagination"]
    mock_get_metrics.assert_called_once()


def test_get_project_workload_metrics_with_pagination() -> None:
    """Test GET /v1/projects/{project}/workloads/metrics with pagination parameters."""

    mock_namespace = make_namespace_crd(
        name="test-namespace",
        labels={"project-id": "test-project"},
    )
    mock_response = WorkloadMetricsListPaginated(
        data=[],
        pagination=PaginationMetadata(page=2, page_size=50, total=0),
    )

    with (
        runtime_dependency_overrides(
            {
                **SESSION_OVERRIDES,
                get_project_namespace: lambda: mock_namespace,
            }
        ),
        patch("app.workloads.router.get_workload_metrics_paginated", autospec=True) as mock_get_metrics,
    ):
        mock_get_metrics.return_value = mock_response

        with TestClient(app) as client:
            response = client.get(
                "/v1/projects/test-namespace/workloads/metrics",
                params={"page": 2, "pageSize": 50},
            )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["pagination"]["page"] == 2
    assert data["pagination"]["pageSize"] == 50
    assert data["pagination"]["total"] == 0
    # Nested pagination envelope must not leak loose top-level keys.
    assert "total" not in data
    assert "page" not in data
    assert "pageSize" not in data
    assert "totalPages" not in data
    assert "totalPages" not in data["pagination"]
    mock_get_metrics.assert_called_once()
    call_kwargs = mock_get_metrics.call_args.kwargs
    assert call_kwargs["page"] == 2
    assert call_kwargs["page_size"] == 50


def test_get_project_workload_metrics_invalid_pagination() -> None:
    """Test GET /v1/projects/{project}/workloads/metrics with invalid pagination parameters."""

    mock_namespace = make_namespace_crd(
        name="test-namespace",
        labels={"project-id": "test-project"},
    )

    with runtime_dependency_overrides(
        {
            **SESSION_OVERRIDES,
            get_project_namespace: lambda: mock_namespace,
        }
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/v1/projects/test-namespace/workloads/metrics",
                params={"page": 0},
            )
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

            response = client.get(
                "/v1/projects/test-namespace/workloads/metrics",
                params={"pageSize": 0},
            )
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_get_project_metric() -> None:
    """Test GET /v1/projects/{project}/workloads/metrics/{metric} returns timeseries data."""

    mock_namespace = make_namespace_crd(
        name="test-namespace",
        labels={"project-id": "test-project"},
    )
    now = datetime.now(UTC).replace(microsecond=0)
    start_time = now - timedelta(hours=1)
    end_time = now

    mock_response = MetricsTimeseries(
        data=[
            DatapointsWithMetadata(
                metadata=DatapointMetadataBase(label="gpu-0"),
                values=[
                    Datapoint(value=50.0, timestamp=start_time),
                    Datapoint(value=75.0, timestamp=end_time),
                ],
            )
        ],
        range=TimeseriesRange(
            start=start_time,
            end=end_time,
            interval_seconds=3600,
            timestamps=[start_time, end_time],
        ),
    )

    with (
        runtime_dependency_overrides(
            {
                **SESSION_OVERRIDES,
                get_project_namespace: lambda: mock_namespace,
                get_prometheus_client: lambda: MagicMock(spec=PrometheusConnect),
            }
        ),
        patch("app.workloads.router.get_metric_by_namespace", autospec=True) as mock_get_metric,
    ):
        mock_get_metric.return_value = mock_response

        with TestClient(app) as client:
            response = client.get(
                "/v1/projects/test-namespace/workloads/metrics/gpu_device_utilization",
                params={
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                },
            )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "data" in data
    assert "range" in data
    mock_get_metric.assert_called_once()
    call_kwargs = mock_get_metric.call_args.kwargs
    assert call_kwargs["metric"] == NamespaceMetricName.GPU_DEVICE_UTILIZATION


def test_get_project_workload_stats_unauthorized() -> None:
    """Test GET /v1/projects/{project}/workloads/stats returns 403 for unauthorized access."""

    def mock_unauthorized_access():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to namespace 'unauthorized-namespace'",
        )

    with runtime_dependency_overrides(
        {
            **SESSION_OVERRIDES,
            get_project_namespace: mock_unauthorized_access,
        }
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/v1/projects/unauthorized-namespace/workloads/stats")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "access" in response.json()["detail"].lower()


def test_get_project_workload_metrics_unauthorized() -> None:
    """Test GET /v1/projects/{project}/workloads/metrics returns 403 for unauthorized access."""

    def mock_unauthorized_access():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to namespace 'unauthorized-namespace'",
        )

    with runtime_dependency_overrides(
        {
            **SESSION_OVERRIDES,
            get_project_namespace: mock_unauthorized_access,
        }
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/v1/projects/unauthorized-namespace/workloads/metrics")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "access" in response.json()["detail"].lower()
