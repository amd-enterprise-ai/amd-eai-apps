# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from prometheus_api_client import PrometheusConnect
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.collections import PaginationConditions
from app.clusters.models import Cluster
from app.metrics.constants import (
    PROJECT_ID_METRIC_LABEL,
)
from app.metrics.schemas import (
    Datapoint,
    DatapointsWithMetadata,
    DateRange,
    GpuDeviceSingleMetricResponse,
    MetricsScalarWithRange,
    MetricsTimeRange,
    MetricsTimeseries,
    ProjectDatapointMetadata,
    TimeseriesRange,
    WorkloadGpuDevice,
    WorkloadsWithMetrics,
)
from app.metrics.service import (
    __get_utilized_gpu_count_by_project,
    get_average_wait_time_for_project,
    get_avg_gpu_idle_time_for_project,
    get_current_utilization,
    get_gpu_and_node_counts_for_workload,
    get_gpu_device_gpu_utilization_for_workload,
    get_gpu_device_power_usage_for_workload,
    get_gpu_device_utilization_for_cluster_by_workload_id,
    get_gpu_device_utilization_for_project_by_workload_id,
    get_gpu_device_utilization_timeseries,
    get_gpu_device_utilization_timeseries_for_cluster,
    get_gpu_device_utilization_timeseries_for_project,
    get_gpu_device_vram_utilization_for_workload,
    get_gpu_memory_utilization_for_cluster_by_workload_id,
    get_gpu_memory_utilization_for_project_by_workload_id,
    get_gpu_memory_utilization_timeseries,
    get_gpu_memory_utilization_timeseries_for_project,
    get_node_gpu_devices_with_metrics,
    get_node_gpu_junction_temperature,
    get_node_gpu_memory_temperature,
    get_node_gpu_utilization,
    get_node_gpu_vram_utilization,
    get_node_names_for_workload,
    get_node_power_usage,
    get_pcie_bandwidth_timeseries_for_node,
    get_pcie_efficiency_timeseries_for_node,
    get_workloads_metrics_by_cluster,
    get_workloads_metrics_by_node,
    get_workloads_metrics_by_project,
    get_workloads_on_node_with_gpu_devices,
)
from app.projects.enums import ProjectStatus
from app.projects.models import Project
from app.projects.utils import map_to_project_response
from app.quotas.models import Quota
from app.workloads.enums import WorkloadStatus
from app.workloads.models import Workload


@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch(
    "app.metrics.service.get_projects",
    return_value=[
        Project(
            id=UUID("a24c9e53-5532-419e-8dec-cf8b29d63812"),
            name="Group1",
            description="Test Group 1",
            status=ProjectStatus.READY,
            gpu_preemption_enabled=False,
            created_at=datetime(2023, 1, 1, tzinfo=UTC),
            updated_at=datetime(2023, 1, 1, tzinfo=UTC),
            created_by="test@example.com",
            updated_by="test@example.com",
        ),
        Project(
            id=UUID("3d8e02e4-caf3-48ff-8342-63cb5db19792"),
            name="Group2",
            description="Test Group 2",
            status=ProjectStatus.READY,
            gpu_preemption_enabled=False,
            created_at=datetime(2023, 1, 1, tzinfo=UTC),
            updated_at=datetime(2023, 1, 1, tzinfo=UTC),
            created_by="test@example.com",
            updated_by="test@example.com",
        ),
    ],
)
@patch("app.metrics.service.a_custom_query_range", return_value=AsyncMock())
@patch("app.metrics.service.map_timeseries_split_by_project", return_value=AsyncMock())
async def test_get_gpu_memory_utilization_timeseries(
    mock_map_timeseries: AsyncMock,
    mock_query: AsyncMock,
    mock_get_projects: MagicMock,
    mock_get_step: MagicMock,
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    await get_gpu_memory_utilization_timeseries(
        session=AsyncMock(spec=AsyncSession),
        start=datetime(2023, 1, 1),
        end=datetime(2023, 1, 2),
        prometheus_client=prometheus_client_mock,
    )

    assert mock_query.call_count == 1
    assert (
        mock_query.call_args[1]["query"]
        == """
(
sum by(project_id) (
    gpu_used_vram
) * 100
 /
scalar(
    sum(
        max by (gpu_uuid, hostname) (
            gpu_total_vram
        )
    )
)
)
or
(vector(0) /
scalar(
    sum(
        max by (gpu_uuid, hostname) (
            gpu_total_vram
        )
    )
)
)
"""
    )


@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch(
    "app.metrics.service.get_projects",
    return_value=[
        Project(
            id=UUID("a24c9e53-5532-419e-8dec-cf8b29d63812"),
            name="Group1",
            description="Test Group 1",
            status=ProjectStatus.READY,
            gpu_preemption_enabled=False,
            created_at=datetime(2023, 1, 1, tzinfo=UTC),
            updated_at=datetime(2023, 1, 1, tzinfo=UTC),
            created_by="test@example.com",
            updated_by="test@example.com",
        ),
        Project(
            id=UUID("3d8e02e4-caf3-48ff-8342-63cb5db19792"),
            name="Group2",
            description="Test Group 2",
            status=ProjectStatus.READY,
            gpu_preemption_enabled=False,
            created_at=datetime(2023, 1, 1, tzinfo=UTC),
            updated_at=datetime(2023, 1, 1, tzinfo=UTC),
            created_by="test@example.com",
            updated_by="test@example.com",
        ),
    ],
)
@patch("app.metrics.service.a_custom_query_range", return_value=AsyncMock())
@patch("app.metrics.service.map_timeseries_split_by_project", return_value=AsyncMock())
async def test_get_gpu_device_utilization_timeseries(
    mock_map_timeseries: AsyncMock,
    mock_query: AsyncMock,
    mock_get_projects: MagicMock,
    mock_get_step: MagicMock,
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    await get_gpu_device_utilization_timeseries(
        session=AsyncMock(spec=AsyncSession),
        start=datetime(2023, 1, 1),
        end=datetime(2023, 1, 2),
        prometheus_client=prometheus_client_mock,
    )

    assert mock_query.call_count == 1
    assert (
        mock_query.call_args[1]["query"]
        == """
(
count by (project_id) (
        gpu_gfx_activity
) * 100
 /
scalar(
    count(
        count by (gpu_uuid, hostname) (
            gpu_total_vram
        )
    )
)
)
or
(vector(0) /
scalar(
    count(
        count by (gpu_uuid, hostname) (
            gpu_total_vram
        )
    )
)
)
"""
    )


@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch(
    "app.metrics.service.get_projects",
    return_value=[
        Project(
            id=UUID("a24c9e53-5532-419e-8dec-cf8b29d63812"),
            name="Group1",
            description="Test Group 1",
            status=ProjectStatus.READY,
            gpu_preemption_enabled=False,
            created_at=datetime(2023, 1, 1, tzinfo=UTC),
            updated_at=datetime(2023, 1, 1, tzinfo=UTC),
            created_by="test@example.com",
            updated_by="test@example.com",
        ),
        Project(
            id=UUID("3d8e02e4-caf3-48ff-8342-63cb5db19792"),
            name="Group2",
            description="Test Group 2",
            status=ProjectStatus.READY,
            gpu_preemption_enabled=False,
            created_at=datetime(2023, 1, 1, tzinfo=UTC),
            updated_at=datetime(2023, 1, 1, tzinfo=UTC),
            created_by="test@example.com",
            updated_by="test@example.com",
        ),
    ],
)
@patch("app.metrics.service.a_custom_query_range", return_value=AsyncMock())
@patch("app.metrics.service.map_timeseries_split_by_project", return_value=AsyncMock())
async def test_get_gpu_device_utilization_timeseries_for_cluster(
    mock_map_timeseries: AsyncMock,
    mock_query: AsyncMock,
    mock_get_projects: MagicMock,
    mock_get_step: MagicMock,
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    await get_gpu_device_utilization_timeseries_for_cluster(
        session=AsyncMock(spec=AsyncSession),
        start=datetime(2023, 1, 1),
        end=datetime(2023, 1, 2),
        cluster_name="CLUSTER1",
        prometheus_client=prometheus_client_mock,
    )

    assert mock_query.call_count == 1
    assert (
        mock_query.call_args[1]["query"]
        == """
(
count by (project_id) (
    gpu_gfx_activity{kube_cluster_name="CLUSTER1"}
) * 100
 /
scalar(
    count(
        count by (gpu_uuid, hostname) (
            gpu_total_vram{kube_cluster_name="CLUSTER1"}
        )
    )
)
)
or
(vector(0) /
scalar(
    count(
        count by (gpu_uuid, hostname) (
            gpu_total_vram{kube_cluster_name="CLUSTER1"}
        )
    )
)
)
"""
    )


@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
@patch(
    "app.metrics.service.get_workload_counts_with_status_by_project_id",
    return_value={
        (UUID("a24c9e53-5532-419e-8dec-cf8b29d63812"), WorkloadStatus.RUNNING): 5,
        (UUID("3d8e02e4-caf3-48ff-8342-63cb5db19792"), WorkloadStatus.RUNNING): 3,
        (UUID("a24c9e53-5532-419e-8dec-cf8b29d63812"), WorkloadStatus.PENDING): 1,
        (UUID("3d8e02e4-caf3-48ff-8342-63cb5db19792"), WorkloadStatus.PENDING): 0,
    },
)
@patch(
    "app.metrics.service.get_quotas",
    return_value=[
        Quota(
            cluster_id="f33bf805-2a5f-4f01-8e3b-339fd8c9e092",
            gpu_count=8,
            cpu_milli_cores=1000,
            memory_bytes=1000,
            ephemeral_storage_bytes=1000,
            status="pending",
            project_id=UUID("a24c9e53-5532-419e-8dec-cf8b29d63812"),
            project=Project(
                id=UUID("a24c9e53-5532-419e-8dec-cf8b29d63812"),
                name="Test Project",
                description="Test Description",
                status=ProjectStatus.READY,
                gpu_preemption_enabled=False,
                cluster_id="f33bf805-2a5f-4f01-8e3b-339fd8c9e092",
                created_at=datetime(2023, 1, 1, tzinfo=UTC),
                updated_at=datetime(2023, 1, 1, tzinfo=UTC),
                created_by="test@example.com",
                updated_by="test@example.com",
            ),
        ),
        Quota(
            cluster_id="f33bf805-2a5f-4f01-8e3b-339fd8c9e092",
            gpu_count=0,
            cpu_milli_cores=500,
            memory_bytes=1000,
            ephemeral_storage_bytes=1000,
            status="deleting",
            project_id=UUID("a24c9e53-5532-419e-8dec-cf8b29d63812"),
            project=Project(
                id=UUID("a24c9e53-5532-419e-8dec-cf8b29d63812"),
                name="Test Project",
                description="Test Description",
                status=ProjectStatus.READY,
                gpu_preemption_enabled=False,
                cluster_id="f33bf805-2a5f-4f01-8e3b-339fd8c9e092",
                created_at=datetime(2023, 1, 1, tzinfo=UTC),
                updated_at=datetime(2023, 1, 1, tzinfo=UTC),
                created_by="test@example.com",
                updated_by="test@example.com",
            ),
        ),
        Quota(
            cluster_id="f33bf805-2a5f-4f01-8e3b-339fd8c9e092",
            gpu_count=1,
            cpu_milli_cores=500,
            memory_bytes=1000,
            ephemeral_storage_bytes=1000,
            status="deleting",
            project_id=UUID("3d8e02e4-caf3-48ff-8342-63cb5db19792"),
            project=Project(
                id=UUID("3d8e02e4-caf3-48ff-8342-63cb5db19792"),
                name="Test Project",
                description="Test Description",
                status=ProjectStatus.READY,
                gpu_preemption_enabled=False,
                cluster_id="f33bf805-2a5f-4f01-8e3b-339fd8c9e092",
                created_at=datetime(2023, 1, 1, tzinfo=UTC),
                updated_at=datetime(2023, 1, 1, tzinfo=UTC),
                created_by="test@example.com",
                updated_by="test@example.com",
            ),
        ),
    ],
)
@patch(
    "app.metrics.service.get_projects",
    return_value=[
        Project(
            id=UUID("a24c9e53-5532-419e-8dec-cf8b29d63812"),
            name="group1",
            description="Test Group 1",
            status=ProjectStatus.READY,
            gpu_preemption_enabled=False,
            cluster_id="f33bf805-2a5f-4f01-8e3b-339fd8c9e092",
            created_at=datetime(2023, 1, 1, tzinfo=UTC),
            updated_at=datetime(2023, 1, 1, tzinfo=UTC),
            created_by="test@example.com",
            updated_by="test@example.com",
        ),
        Project(
            id=UUID("3d8e02e4-caf3-48ff-8342-63cb5db19792"),
            name="group2",
            description="Test Group 2",
            status=ProjectStatus.READY,
            gpu_preemption_enabled=False,
            cluster_id="f33bf805-2a5f-4f01-8e3b-339fd8c9e092",
            created_at=datetime(2023, 1, 1, tzinfo=UTC),
            updated_at=datetime(2023, 1, 1, tzinfo=UTC),
            created_by="test@example.com",
            updated_by="test@example.com",
        ),
    ],
)
@patch(
    "app.metrics.service.__get_utilized_gpu_count_by_project",
    return_value={"a24c9e53-5532-419e-8dec-cf8b29d63812": 5, "3d8e02e4-caf3-48ff-8342-63cb5db19792": 3, None: 2},
)
async def test_get_current_utilization(
    mock_get_utilized_gpu_count: AsyncMock,
    mock_get_projects: AsyncMock,
    mock_get_quotas: AsyncMock,
    mock_get_workload_counts: AsyncMock,
    mock_get_lookback: MagicMock,
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    utilization = await get_current_utilization(
        session=AsyncMock(spec=AsyncSession),
        prometheus_client=prometheus_client_mock,
    )

    assert utilization.total_utilized_gpus_count == 8
    assert utilization.total_running_workloads_count == 8
    assert utilization.total_pending_workloads_count == 1
    assert len(utilization.utilization_by_project) == 2
    assert utilization.utilization_by_project[0].project.id == UUID("a24c9e53-5532-419e-8dec-cf8b29d63812")
    assert utilization.utilization_by_project[0].allocated_gpus_count == 8
    assert utilization.utilization_by_project[0].utilized_gpus_count == 5
    assert utilization.utilization_by_project[0].pending_workloads_count == 1
    assert utilization.utilization_by_project[0].running_workloads_count == 5

    assert utilization.utilization_by_project[1].project.id == UUID("3d8e02e4-caf3-48ff-8342-63cb5db19792")
    assert utilization.utilization_by_project[1].allocated_gpus_count == 1
    assert utilization.utilization_by_project[1].utilized_gpus_count == 3
    assert utilization.utilization_by_project[1].pending_workloads_count == 0
    assert utilization.utilization_by_project[1].running_workloads_count == 3


@patch(
    "app.metrics.service.a_custom_query",
    return_value=[
        {
            "metric": {
                PROJECT_ID_METRIC_LABEL: "123",
            },
            "value": [1672531199, "1"],
        },
        {
            "metric": {
                PROJECT_ID_METRIC_LABEL: "345",
            },
            "value": [1672531199, "2"],
        },
        {"metric": {}, "value": [1672531199, "5"]},
    ],
)
async def test__get_utilized_gpu_count_by_project(mock_query: AsyncMock) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    results = await __get_utilized_gpu_count_by_project(prometheus_client=prometheus_client_mock)
    assert results == {"123": 1, "345": 2, None: 5}
    assert mock_query.call_count == 1
    assert (
        mock_query.call_args[1]["query"]
        == """
count by (project_id) (
    gpu_gfx_activity
)
"""
    )


@pytest.mark.asyncio
async def test_get_metrics_for_workloads_in_project() -> None:
    mock_session = AsyncMock(spec=AsyncSession)
    project = Project(
        id=uuid4(),
        name="Test Project",
        status=ProjectStatus.READY,
        gpu_preemption_enabled=False,
        cluster_id="b4884301-b87c-4e4a-89bc-e60f458f176d",
        created_at=datetime(2023, 1, 1, tzinfo=UTC),
        updated_at=datetime(2023, 1, 1, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
    )

    workload = Workload(
        id=uuid4(),
        project_id=project.id,
        cluster_id=uuid4(),
        status=WorkloadStatus.RUNNING,
        created_by="tester",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        updated_by="tester",
    )
    gpus = {}
    vram = {}
    gpus[str(workload.id)] = 1
    vram[str(workload.id)] = 1024

    pagination_params = PaginationConditions(page=1, page_size=10)
    sort_params: list[str] = []
    filter_params: list[str] = []

    with (
        patch("app.metrics.service.get_workloads_with_running_time_in_project", return_value=([(workload, 300)], 1)),
        patch("app.metrics.service.get_gpu_device_utilization_for_project_by_workload_id", return_value=gpus),
        patch("app.metrics.service.get_gpu_memory_utilization_for_project_by_workload_id", return_value=vram),
    ):
        prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
        result = await get_workloads_metrics_by_project(
            mock_session,
            project=project,
            prometheus_client=prometheus_client_mock,
            pagination_params=pagination_params,
            sort_params=sort_params,
            filter_params=filter_params,
        )

    assert isinstance(result, WorkloadsWithMetrics)
    assert result.pagination.page == 1
    assert result.pagination.page_size == 10
    assert result.pagination.total == 1
    assert len(result.data) == 1
    workload_result = result.data[0]
    assert workload_result.gpu_count == 1
    assert workload_result.vram == 1024
    assert workload_result.run_time == 300
    assert workload_result.status == WorkloadStatus.RUNNING
    assert workload_result.created_by == "tester"


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query", autospec=True)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_gpu_device_utilization_for_project_by_workload_id(
    mock_lookback: MagicMock, mock_query: AsyncMock
) -> None:
    project_id = uuid4()
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    mock_query.return_value = [
        {"metric": {"workload_id": "w1"}, "value": [1672531199, "2"]},
        {"metric": {"workload_id": "w2"}, "value": [1672531199, "4"]},
        {"metric": {}, "value": [1672531199, "1"]},
    ]

    result = await get_gpu_device_utilization_for_project_by_workload_id(
        project_id, prometheus_client=prometheus_client_mock
    )
    assert result == {"w1": 2, "w2": 4, None: 1}
    assert mock_query.call_count == 1
    assert (
        "count by (workload_id)" in mock_query.call_args[1]["query"]
        and f'gpu_gfx_activity{{project_id="{project_id}"}}' in mock_query.call_args[1]["query"]
    )


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query", autospec=True)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_gpu_memory_utilization_for_project_by_workload_id(
    mock_lookback: MagicMock, mock_query: AsyncMock
) -> None:
    project_id = uuid4()
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    mock_query.return_value = [
        {"metric": {"workload_id": "w1"}, "value": [1672531199, "1024"]},
        {"metric": {"workload_id": "w2"}, "value": [1672531199, "2048"]},
        {"metric": {}, "value": [1672531199, "512"]},
    ]

    result = await get_gpu_memory_utilization_for_project_by_workload_id(
        project_id, prometheus_client=prometheus_client_mock
    )
    assert result == {"w1": 1024, "w2": 2048, None: 512}
    assert mock_query.call_count == 1
    assert (
        "sum by (workload_id)" in mock_query.call_args[1]["query"]
        and f'gpu_used_vram{{project_id="{project_id}"}}' in mock_query.call_args[1]["query"]
    )


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", return_value=AsyncMock())
@patch("app.metrics.service.map_metrics_timeseries", autospec=True)
async def test_get_gpu_device_utilization_timeseries_for_project(
    mock_map_timeseries: MagicMock, mock_custom_query: AsyncMock
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    start = datetime.now(UTC)
    end = start + timedelta(minutes=10)
    project = Project(
        id=uuid4(),
        name="test-project",
        description="Test description",
        cluster_id="b4884301-b87c-4e4a-89bc-e60f458f176d",
        created_at=datetime(2023, 1, 1, tzinfo=UTC),
        updated_at=datetime(2023, 1, 1, tzinfo=UTC),
        created_by="test@example.com",
        status=ProjectStatus.READY,
        gpu_preemption_enabled=False,
        updated_by="test@example.com",
        cluster=Cluster(id="b4884301-b87c-4e4a-89bc-e60f458f176d", name="Test Cluster"),
    )

    utilized_gpus_mock = [{"metric": {}, "values": [(start.timestamp(), "5"), (end.timestamp(), "10")]}]
    allocated_gpus_mock = [{"metric": {}, "values": [(start.timestamp(), "15"), (end.timestamp(), "20")]}]
    mock_custom_query.side_effect = [utilized_gpus_mock, allocated_gpus_mock]

    mock_map_timeseries.side_effect = [
        MetricsTimeseries(
            data=[
                DatapointsWithMetadata(
                    metadata=ProjectDatapointMetadata(label="utilizedGpus", project=map_to_project_response(project)),
                    values=[Datapoint(value=5.0, timestamp=start), Datapoint(value=10.0, timestamp=end)],
                )
            ],
            range=TimeseriesRange(start=start, end=end, interval_seconds=300, timestamps=[start, end]),
        ),
        MetricsTimeseries(
            data=[
                DatapointsWithMetadata(
                    metadata=ProjectDatapointMetadata(label="allocatedGpus", project=map_to_project_response(project)),
                    values=[Datapoint(value=8.0, timestamp=start), Datapoint(value=10.0, timestamp=end)],
                )
            ],
            range=TimeseriesRange(start=start, end=end, interval_seconds=300, timestamps=[start, end]),
        ),
    ]

    result = await get_gpu_device_utilization_timeseries_for_project(
        start, end, project, prometheus_client=prometheus_client_mock
    )

    assert len(result.data) == 2
    assert result.data[0].values[0].value == 5.0
    assert result.data[1].values[0].value == 8.0

    assert mock_custom_query.call_count == 2

    assert (
        mock_custom_query.call_args_list[0][1]["query"]
        == f"""
count(
    gpu_gfx_activity{{project_id="{project.id}"}}
)
OR (0 * max(gpu_total_vram{{kube_cluster_name="Test Cluster"}}))
"""
    )
    assert (
        mock_custom_query.call_args_list[1][1]["query"]
        == f"""
max(
    allocated_gpus{{project_id="{project.id}"}}
)
"""
    )


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", return_value=AsyncMock())
@patch("app.metrics.service.map_metrics_timeseries", autospec=True)
async def test_get_gpu_memory_utilization_timeseries_for_project(
    mock_map_timeseries: MagicMock, mock_custom_query: AsyncMock
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    start = datetime.now(UTC)
    end = start + timedelta(minutes=10)
    project = Project(
        id=uuid4(),
        name="test-project",
        description="Test description",
        status=ProjectStatus.READY,
        gpu_preemption_enabled=False,
        cluster_id="b4884301-b87c-4e4a-89bc-e60f458f176d",
        created_at=datetime(2023, 1, 1, tzinfo=UTC),
        updated_at=datetime(2023, 1, 1, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
        cluster=Cluster(id="b4884301-b87c-4e4a-89bc-e60f458f176d", name="Test Cluster"),
    )

    utilized_gpus_mock = [{"metric": {}, "values": [(start.timestamp(), "5"), (end.timestamp(), "10")]}]
    allocated_gpus_mock = [{"metric": {}, "values": [(start.timestamp(), "15"), (end.timestamp(), "20")]}]
    mock_custom_query.side_effect = [utilized_gpus_mock, allocated_gpus_mock]

    mock_map_timeseries.side_effect = [
        MetricsTimeseries(
            data=[
                DatapointsWithMetadata(
                    metadata=ProjectDatapointMetadata(
                        label="utilizedGpuVram", project=map_to_project_response(project)
                    ),
                    values=[Datapoint(value=5.0, timestamp=start), Datapoint(value=10.0, timestamp=end)],
                )
            ],
            range=TimeseriesRange(start=start, end=end, interval_seconds=300, timestamps=[start, end]),
        ),
        MetricsTimeseries(
            data=[
                DatapointsWithMetadata(
                    metadata=ProjectDatapointMetadata(
                        label="allocatedGpuVram", project=map_to_project_response(project)
                    ),
                    values=[Datapoint(value=8.0, timestamp=start), Datapoint(value=10.0, timestamp=end)],
                )
            ],
            range=TimeseriesRange(start=start, end=end, interval_seconds=300, timestamps=[start, end]),
        ),
    ]

    result = await get_gpu_memory_utilization_timeseries_for_project(
        start, end, project, prometheus_client=prometheus_client_mock
    )

    assert len(result.data) == 2
    assert result.data[0].values[0].value == 5.0
    assert result.data[1].values[0].value == 8.0

    assert mock_custom_query.call_count == 2

    assert (
        mock_custom_query.call_args_list[0][1]["query"]
        == f"""
sum(
    gpu_used_vram{{project_id="{project.id}"}}
)
OR (0 * max(gpu_total_vram{{kube_cluster_name="Test Cluster"}}))
"""
    )
    assert (
        mock_custom_query.call_args_list[1][1]["query"]
        == f"""
max(
    allocated_gpu_vram{{project_id="{project.id}"}}
)
"""
    )


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", return_value=AsyncMock())
async def test_get_avg_gpu_idle_time_for_project(mock_custom_query: AsyncMock) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    start = datetime.now(UTC)
    end = start + timedelta(minutes=10)
    project = Project(
        id=uuid4(),
        name="Test Project",
        description="Test description",
        status=ProjectStatus.READY,
        gpu_preemption_enabled=False,
        created_at=datetime(2023, 1, 1, tzinfo=UTC),
        updated_at=datetime(2023, 1, 1, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
    )

    average_idle_time_mock = [
        {
            "metric": {},
            "values": [
                (start.timestamp(), "5"),
                ((start + timedelta(minutes=1)).timestamp(), "6"),
                ((start + timedelta(minutes=2)).timestamp(), "NaN"),
                ((start + timedelta(minutes=3)).timestamp(), "Inf"),
                ((start + timedelta(minutes=4)).timestamp(), "-Inf"),
                (end.timestamp(), "10"),
            ],
        }
    ]
    mock_custom_query.return_value = average_idle_time_mock

    result = await get_avg_gpu_idle_time_for_project(start, end, project, prometheus_client=prometheus_client_mock)

    assert result.data == 21.0

    assert mock_custom_query.call_count == 1

    assert (
        mock_custom_query.call_args_list[0][1]["query"]
        == f"""
(
    avg_over_time(
        avg(
            allocated_gpus{{project_id="{project.id}"}}
        )
        [1m:]
    ) -
    on() avg_over_time(
        count(
            gpu_gfx_activity{{project_id="{project.id}"}}
        )
        [1m:]
    )
) * 60.0
/
on() avg_over_time(
        avg(
            allocated_gpus{{project_id="{project.id}"}}
        )
        [1m:]
)
"""
    )


@pytest.mark.asyncio
@patch("app.metrics.service.get_average_pending_time_for_workloads_in_project_created_between", autospec=True)
async def test_get_average_pending_time_for_workloads_in_project_created_between_returns_valid_average(
    mock_get_avg: AsyncMock,
) -> None:
    mock_get_avg.return_value = 123.45

    project = Project(
        id=uuid4(),
        status=ProjectStatus.READY,
        gpu_preemption_enabled=False,
        created_at=datetime(2023, 1, 1, tzinfo=UTC),
        updated_at=datetime(2023, 1, 1, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
    )
    start = datetime.now(UTC) - timedelta(days=1)
    end = datetime.now(UTC)

    session = AsyncMock(spec=AsyncSession)

    result = await get_average_wait_time_for_project(session, start, end, project)

    assert isinstance(result, MetricsScalarWithRange)
    assert result.data == 123.45
    assert result.range == DateRange(start=start, end=end)


@pytest.mark.asyncio
@patch("app.metrics.service.get_average_pending_time_for_workloads_in_project_created_between", autospec=True)
async def test_get_average_pending_time_for_workloads_in_project_created_between_returns_zero_if_none(
    mock_get_avg: AsyncMock,
) -> None:
    mock_get_avg.return_value = None

    project = Project(
        id=uuid4(),
        status=ProjectStatus.READY,
        gpu_preemption_enabled=False,
        created_at=datetime(2023, 1, 1, tzinfo=UTC),
        updated_at=datetime(2023, 1, 1, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
    )
    start = datetime.now(UTC) - timedelta(days=1)
    end = datetime.now(UTC)

    session = AsyncMock(spec=AsyncSession)

    result = await get_average_wait_time_for_project(session, start, end, project)

    assert result.data == 0
    assert result.range == DateRange(start=start, end=end)


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query", autospec=True)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_gpu_device_utilization_for_cluster_by_workload_id(mock_lookback, mock_query):
    cluster_name = "test-cluster"
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    mock_query.return_value = [
        {"metric": {"workload_id": "w1"}, "value": [1672531199, "2"]},
        {"metric": {"workload_id": "w2"}, "value": [1672531199, "4"]},
        {"metric": {}, "value": [1672531199, "1"]},
    ]

    result = await get_gpu_device_utilization_for_cluster_by_workload_id(
        cluster_name, prometheus_client=prometheus_client_mock
    )
    assert result == {"w1": 2, "w2": 4, None: 1}
    assert mock_query.call_count == 1
    assert (
        "count by (workload_id)" in mock_query.call_args[1]["query"]
        and f'gpu_gfx_activity{{kube_cluster_name="{cluster_name}"}}' in mock_query.call_args[1]["query"]
    )


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query", autospec=True)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_gpu_memory_utilization_for_cluster_by_workload_id(mock_lookback, mock_query):
    cluster_name = "test-cluster"
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    mock_query.return_value = [
        {"metric": {"workload_id": "w1"}, "value": [1672531199, "1024"]},
        {"metric": {"workload_id": "w2"}, "value": [1672531199, "2048"]},
        {"metric": {}, "value": [1672531199, "512"]},
    ]

    result = await get_gpu_memory_utilization_for_cluster_by_workload_id(
        cluster_name, prometheus_client=prometheus_client_mock
    )
    assert result == {"w1": 1024, "w2": 2048, None: 512}
    assert mock_query.call_count == 1
    assert (
        "sum by (workload_id)" in mock_query.call_args[1]["query"]
        and f'gpu_used_vram{{kube_cluster_name="{cluster_name}"}}' in mock_query.call_args[1]["query"]
    )


@pytest.mark.asyncio
async def test_get_metrics_for_workloads_in_cluster():
    mock_session = AsyncMock(spec=AsyncSession)
    cluster_id = uuid4()
    cluster_name = "test-cluster"

    workload = Workload(
        id=uuid4(),
        project_id=uuid4(),
        cluster_id=cluster_id,
        status=WorkloadStatus.RUNNING,
        created_by="tester",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        updated_by="tester",
    )
    gpus = {}
    vram = {}
    gpus[str(workload.id)] = 2
    vram[str(workload.id)] = 2048

    pagination_params = PaginationConditions(page=1, page_size=10)
    sort_params = []
    filter_params = []

    with (
        patch("app.metrics.service.get_workloads_in_cluster", return_value=([workload], 1)),
        patch("app.metrics.service.get_gpu_device_utilization_for_cluster_by_workload_id", return_value=gpus),
        patch("app.metrics.service.get_gpu_memory_utilization_for_cluster_by_workload_id", return_value=vram),
    ):
        prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
        result = await get_workloads_metrics_by_cluster(
            mock_session,
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            prometheus_client=prometheus_client_mock,
            pagination_params=pagination_params,
            sort_params=sort_params,
            filter_params=filter_params,
        )

    assert isinstance(result, WorkloadsWithMetrics)
    assert result.pagination.page == 1
    assert result.pagination.page_size == 10
    assert result.pagination.total == 1
    assert len(result.data) == 1
    workload_result = result.data[0]
    assert workload_result.gpu_count == 2
    assert workload_result.vram == 2048
    assert workload_result.status == WorkloadStatus.RUNNING
    assert workload_result.created_by == "tester"


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query", autospec=True)
async def test_get_gpu_and_node_counts_for_workload(mock_query: AsyncMock) -> None:
    workload_id = uuid4()
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)

    mock_query.side_effect = [
        [{"metric": {}, "value": [1672531199, "4"]}],
        [{"metric": {}, "value": [1672531199, "2"]}],
    ]

    gpu_count, node_count = await get_gpu_and_node_counts_for_workload(workload_id, prometheus_client_mock)

    assert gpu_count == 4
    assert node_count == 2
    assert mock_query.call_count == 2

    gpu_query = mock_query.call_args_list[0][1]["query"]
    node_query = mock_query.call_args_list[1][1]["query"]
    assert f'workload_id="{workload_id}"' in gpu_query
    assert "count(gpu_gfx_activity" in gpu_query
    assert "count by (hostname)" in node_query


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query", autospec=True)
async def test_get_gpu_and_node_counts_for_workload_empty(mock_query: AsyncMock) -> None:
    workload_id = uuid4()
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)

    mock_query.side_effect = [[], []]

    gpu_count, node_count = await get_gpu_and_node_counts_for_workload(workload_id, prometheus_client_mock)

    assert gpu_count == 0
    assert node_count == 0


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query", autospec=True)
async def test_get_node_names_for_workload(mock_query: AsyncMock) -> None:
    workload_id = uuid4()
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    mock_query.return_value = [
        {"metric": {"hostname": "node-1"}, "value": [1672531199, "1"]},
        {"metric": {"hostname": "node-2"}, "value": [1672531199, "1"]},
    ]

    names = await get_node_names_for_workload(workload_id, prometheus_client_mock)

    assert names == ["node-1", "node-2"]
    mock_query.assert_called_once()
    assert "gpu_gfx_activity" in mock_query.call_args[1]["query"]
    assert f'workload_id="{workload_id}"' in mock_query.call_args[1]["query"]


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query", autospec=True)
async def test_get_node_names_for_workload_empty(mock_query: AsyncMock) -> None:
    workload_id = uuid4()
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    mock_query.return_value = []

    names = await get_node_names_for_workload(workload_id, prometheus_client_mock)

    assert names == []


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_gpu_device_vram_utilization_for_workload(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    workload_id = uuid4()
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=2)).replace(microsecond=0)
    end = (now - timedelta(hours=1)).replace(microsecond=0)

    mock_query_range.return_value = [{"metric": {"gpu_uuid": "gpu-1"}, "values": []}]
    device_key = ("gpu-1", "node-1", "0")
    mock_parse.return_value = {device_key: [Datapoint(timestamp=start, value=65.0)]}

    result = await get_gpu_device_vram_utilization_for_workload(
        workload_id, prometheus_client_mock, start=start, end=end
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 1
    assert result.gpu_devices[0].gpu_uuid == "gpu-1"
    assert result.gpu_devices[0].metric.series_label == "vramUtilizationPct"
    assert result.gpu_devices[0].metric.values[0].value == 65.0
    assert isinstance(result.range, MetricsTimeRange)
    assert result.range.start == start
    assert result.range.end == end

    vram_query = mock_query_range.call_args[1]["query"]
    assert "gpu_used_vram" in vram_query
    assert "gpu_total_vram" in vram_query
    assert "* 100" in vram_query
    # avg by prevents double-counting per-process series that would inflate values above 100%
    assert "avg by" in vram_query
    assert "sum by" not in vram_query


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_gpu_device_gpu_utilization_for_workload(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    workload_id = uuid4()
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=2)).replace(microsecond=0)
    end = (now - timedelta(hours=1)).replace(microsecond=0)

    mock_query_range.return_value = [{"metric": {"gpu_uuid": "gpu-1"}, "values": []}]
    device_key = ("gpu-1", "node-1", "0")
    mock_parse.return_value = {device_key: [Datapoint(timestamp=start, value=42.5)]}

    result = await get_gpu_device_gpu_utilization_for_workload(
        workload_id, prometheus_client_mock, start=start, end=end
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 1
    assert result.gpu_devices[0].metric.series_label == "gpuActivityPct"
    assert result.gpu_devices[0].metric.values[0].value == 42.5

    query = mock_query_range.call_args[1]["query"]
    assert "gpu_gfx_activity" in query


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_gpu_device_power_usage_for_workload(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    workload_id = uuid4()
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=2)).replace(microsecond=0)
    end = (now - timedelta(hours=1)).replace(microsecond=0)

    mock_query_range.return_value = [{"metric": {"gpu_uuid": "gpu-1"}, "values": []}]
    device_key = ("gpu-1", "node-1", "0")
    mock_parse.return_value = {device_key: [Datapoint(timestamp=start, value=120.0)]}

    result = await get_gpu_device_power_usage_for_workload(workload_id, prometheus_client_mock, start=start, end=end)

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 1
    assert result.gpu_devices[0].metric.series_label == "powerWatts"
    assert result.gpu_devices[0].metric.values[0].value == 120.0

    query = mock_query_range.call_args[1]["query"]
    assert "gpu_package_power" in query
    assert "gpu_average_package_power" in query
    assert re.search(r"\bor\b", query)


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_gpu_device_single_metric_empty_result(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    workload_id = uuid4()
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=2)).replace(microsecond=0)
    end = (now - timedelta(hours=1)).replace(microsecond=0)

    mock_query_range.return_value = []
    mock_parse.return_value = {}

    result = await get_gpu_device_vram_utilization_for_workload(
        workload_id, prometheus_client_mock, start=start, end=end
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 0
    assert isinstance(result.range, MetricsTimeRange)
    assert result.range.start == start
    assert result.range.end == end


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_gpu_device_single_metric_multiple_devices(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    workload_id = uuid4()
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=2)).replace(microsecond=0)
    end = (now - timedelta(hours=1)).replace(microsecond=0)

    mock_query_range.return_value = []
    key_a = ("gpu-aaa", "node-1", "0")
    key_b = ("gpu-bbb", "node-1", "1")
    dp = Datapoint(timestamp=start, value=10.0)
    mock_parse.return_value = {key_a: [dp], key_b: [dp]}

    result = await get_gpu_device_gpu_utilization_for_workload(
        workload_id, prometheus_client_mock, start=start, end=end
    )

    assert len(result.gpu_devices) == 2
    uuids = {d.gpu_uuid for d in result.gpu_devices}
    assert uuids == {"gpu-aaa", "gpu-bbb"}


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_gpu_utilization(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=2)).replace(microsecond=0)
    end = (now - timedelta(hours=1)).replace(microsecond=0)

    mock_query_range.return_value = [{"metric": {"gpu_uuid": "gpu-1"}, "values": []}]
    device_key = ("gpu-1", "node-1", "0")
    mock_parse.return_value = {device_key: [Datapoint(timestamp=start, value=75.0)]}

    result = await get_node_gpu_utilization(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 1
    assert result.gpu_devices[0].gpu_uuid == "gpu-1"
    assert result.gpu_devices[0].metric.series_label == "gpuActivityPct"
    assert result.gpu_devices[0].metric.values[0].value == 75.0
    assert result.range.start == start
    assert result.range.end == end

    query = mock_query_range.call_args[1]["query"]
    assert "gpu_gfx_activity" in query
    assert 'hostname="worker-1"' in query
    assert 'kube_cluster_name="my-cluster"' in query


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_gpu_utilization_empty(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=2)).replace(microsecond=0)
    end = (now - timedelta(hours=1)).replace(microsecond=0)

    mock_query_range.return_value = []
    mock_parse.return_value = {}

    result = await get_node_gpu_utilization(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 0
    assert result.range.start == start
    assert result.range.end == end


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_gpu_utilization_with_step(
    mock_lookback: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    """When step is provided, it is used directly as the query interval in seconds."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = []
    device_key = ("gpu-1", "node-1", "0")
    mock_parse.return_value = {device_key: [Datapoint(timestamp=start, value=50.0)]}

    result = await get_node_gpu_utilization(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
        step=300,
    )

    assert mock_query_range.call_args[1]["step"] == "300"
    assert len(result.gpu_devices) == 1


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="1h")
async def test_get_node_gpu_utilization_with_step_3600(
    mock_lookback: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    """24h range with step=3600 uses 1h interval between datapoints."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(days=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = []
    mock_parse.return_value = {}

    await get_node_gpu_utilization(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
        step=3600,
    )

    assert mock_query_range.call_args[1]["step"] == "3600"


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_gpu_utilization_without_step_uses_auto_step(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    """When step is not provided, the step falls back to get_step_for_range_query."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = []
    mock_parse.return_value = {}

    await get_node_gpu_utilization(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
    )

    mock_step.assert_called_once_with(start, end)
    assert mock_query_range.call_args[1]["step"] == "300"


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_gpu_vram_utilization(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = [{"metric": {"gpu_uuid": "gpu-1"}, "values": []}]
    device_key = ("gpu-1", "node-1", "0")
    mock_parse.return_value = {device_key: [Datapoint(timestamp=start, value=62.5)]}

    result = await get_node_gpu_vram_utilization(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 1
    assert result.gpu_devices[0].gpu_uuid == "gpu-1"
    assert result.gpu_devices[0].metric.series_label == "vramUtilizationPct"
    assert result.gpu_devices[0].metric.values[0].value == 62.5
    assert result.range.start == start
    assert result.range.end == end

    query = mock_query_range.call_args[1]["query"]
    assert "gpu_used_vram" in query
    assert "gpu_total_vram" in query
    assert "* 100" in query
    assert 'hostname="worker-1"' in query
    assert 'kube_cluster_name="my-cluster"' in query
    # avg by prevents double-counting per-process series that would inflate values above 100%
    assert "avg by" in query
    assert "sum by" not in query


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_gpu_vram_utilization_empty(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = []
    mock_parse.return_value = {}

    result = await get_node_gpu_vram_utilization(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 0
    assert result.range.start == start
    assert result.range.end == end


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_gpu_vram_utilization_with_step(
    mock_lookback: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    """When step is provided, it is used directly as the query step interval."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = []
    mock_parse.return_value = {}

    await get_node_gpu_vram_utilization(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
        step=360,
    )

    assert mock_query_range.call_args[1]["step"] == "360"


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query", autospec=True)
async def test_get_node_gpu_devices_with_metrics(mock_query: AsyncMock) -> None:
    """Returns per-GPU snapshot metrics with correct values and Prometheus-computed VRAM utilization."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    timestamp = datetime.now(UTC).timestamp()

    def make_result(gpu_id: str, gpu_uuid: str, value: str) -> dict:
        return {"metric": {"gpu_id": gpu_id, "gpu_uuid": gpu_uuid}, "value": [timestamp, value]}

    mock_query.side_effect = [
        [make_result("0", "uuid-aaa", "63.5"), make_result("1", "uuid-bbb", "42.0")],
        [make_result("0", "uuid-aaa", "19.5"), make_result("1", "uuid-bbb", "15.0")],
        [make_result("0", "uuid-aaa", "25.0"), make_result("1", "uuid-bbb", "12.5")],
    ]

    result = await get_node_gpu_devices_with_metrics(
        node_name="worker-1",
        cluster_name="my-cluster",
        gpu_product_name="Instinct MI300",
        prometheus_client=prometheus_client_mock,
    )

    assert len(result.gpu_devices) == 2

    gpu0 = result.gpu_devices[0]
    assert gpu0.gpu_uuid == "uuid-aaa"
    assert gpu0.gpu_id == "0"
    assert gpu0.product_name == "Instinct MI300"
    assert gpu0.temperature == 63.5
    assert gpu0.power_consumption == 19.5
    assert gpu0.vram_utilization == pytest.approx(25.0)
    assert gpu0.last_updated is not None

    gpu1 = result.gpu_devices[1]
    assert gpu1.gpu_uuid == "uuid-bbb"
    assert gpu1.gpu_id == "1"
    assert gpu1.temperature == 42.0
    assert gpu1.power_consumption == 15.0
    assert gpu1.vram_utilization == pytest.approx(12.5)

    assert mock_query.call_count == 3
    queries = [call[1]["query"] for call in mock_query.call_args_list]
    assert any("gpu_junction_temperature" in q for q in queries)
    assert any(
        "gpu_package_power" in q and "gpu_average_package_power" in q and re.search(r"\bor\b", q) for q in queries
    )
    assert any("gpu_used_vram" in q and "gpu_total_vram" in q for q in queries)
    for q in queries:
        assert 'hostname="worker-1"' in q
        assert 'kube_cluster_name="my-cluster"' in q


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query", autospec=True)
async def test_get_node_gpu_devices_with_metrics_empty(mock_query: AsyncMock) -> None:
    """Returns empty list when Prometheus has no GPU data for the node."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    mock_query.return_value = []

    result = await get_node_gpu_devices_with_metrics(
        node_name="worker-1",
        cluster_name="my-cluster",
        gpu_product_name="Instinct MI300",
        prometheus_client=prometheus_client_mock,
    )

    assert len(result.gpu_devices) == 0
    assert mock_query.call_count == 3


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query", autospec=True)
async def test_get_node_gpu_devices_with_metrics_partial(mock_query: AsyncMock) -> None:
    """GPU devices with only some metrics still report available values."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    timestamp = datetime.now(UTC).timestamp()

    mock_query.side_effect = [
        [{"metric": {"gpu_id": "0", "gpu_uuid": "uuid-aaa"}, "value": [timestamp, "55.0"]}],
        [],
        [],
    ]

    result = await get_node_gpu_devices_with_metrics(
        node_name="worker-1",
        cluster_name="my-cluster",
        gpu_product_name=None,
        prometheus_client=prometheus_client_mock,
    )

    assert len(result.gpu_devices) == 1
    gpu0 = result.gpu_devices[0]
    assert gpu0.gpu_uuid == "uuid-aaa"
    assert gpu0.gpu_id == "0"
    assert gpu0.product_name is None
    assert gpu0.temperature == 55.0
    assert gpu0.power_consumption is None
    assert gpu0.vram_utilization is None


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query", autospec=True)
async def test_get_node_gpu_devices_with_metrics_nan_excluded(mock_query: AsyncMock) -> None:
    """NaN values from Prometheus are excluded, leaving the metric as None."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    timestamp = datetime.now(UTC).timestamp()

    mock_query.side_effect = [
        [{"metric": {"gpu_id": "0", "gpu_uuid": "uuid-aaa"}, "value": [timestamp, "NaN"]}],
        [{"metric": {"gpu_id": "0", "gpu_uuid": "uuid-aaa"}, "value": [timestamp, "10.0"]}],
        [],
    ]

    result = await get_node_gpu_devices_with_metrics(
        node_name="worker-1",
        cluster_name="my-cluster",
        gpu_product_name="MI300",
        prometheus_client=prometheus_client_mock,
    )

    assert len(result.gpu_devices) == 1
    gpu0 = result.gpu_devices[0]
    assert gpu0.temperature is None
    assert gpu0.power_consumption == 10.0


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query")
async def test_get_workloads_on_node_with_gpu_devices_returns_filtered_workloads(
    mock_query: AsyncMock,
) -> None:
    mock_query.return_value = [
        {"metric": {"workload_id": "wid-aaa", "hostname": "worker-1", "gpu_id": "0"}, "value": [1234, "50"]},
        {"metric": {"workload_id": "wid-aaa", "hostname": "worker-1", "gpu_id": "1"}, "value": [1234, "55"]},
        {"metric": {"workload_id": "wid-aaa", "hostname": "worker-2", "gpu_id": "0"}, "value": [1234, "60"]},
        {"metric": {"workload_id": "wid-bbb", "hostname": "worker-1", "gpu_id": "0"}, "value": [1234, "70"]},
        {"metric": {"workload_id": "wid-ccc", "hostname": "worker-2", "gpu_id": "0"}, "value": [1234, "80"]},
    ]
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)

    devices = await get_workloads_on_node_with_gpu_devices("worker-1", "my-cluster", prometheus_client_mock)

    assert set(devices.keys()) == {"wid-aaa", "wid-bbb"}
    assert "wid-ccc" not in devices
    assert len(devices["wid-aaa"]) == 3
    assert len(devices["wid-bbb"]) == 1
    hostnames = {d.hostname for d in devices["wid-aaa"]}
    assert hostnames == {"worker-1", "worker-2"}
    mock_query.assert_called_once()
    assert 'kube_cluster_name="my-cluster"' in mock_query.call_args[1]["query"]


@patch("app.metrics.service.a_custom_query")
async def test_get_workloads_on_node_with_gpu_devices_empty(
    mock_query: AsyncMock,
) -> None:
    mock_query.return_value = []
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)

    devices = await get_workloads_on_node_with_gpu_devices("idle-worker", "my-cluster", prometheus_client_mock)

    assert devices == {}


@patch("app.metrics.service.a_custom_query")
async def test_get_workloads_on_node_with_gpu_devices_deduplicates(
    mock_query: AsyncMock,
) -> None:
    mock_query.return_value = [
        {"metric": {"workload_id": "wid-aaa", "hostname": "worker-1", "gpu_id": "0"}, "value": [1234, "50"]},
        {"metric": {"workload_id": "wid-aaa", "hostname": "worker-1", "gpu_id": "0"}, "value": [1235, "51"]},
    ]
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)

    devices = await get_workloads_on_node_with_gpu_devices("worker-1", "my-cluster", prometheus_client_mock)

    assert len(devices["wid-aaa"]) == 1


@patch("app.metrics.service._get_gpu_memory_utilization_by_workload_id_with_filter")
@patch("app.metrics.service.get_workloads_by_ids_in_cluster")
@patch("app.metrics.service.get_workloads_on_node_with_gpu_devices")
async def test_get_workloads_metrics_by_node(
    mock_get_node_devices: AsyncMock,
    mock_get_workloads: AsyncMock,
    mock_get_vram: AsyncMock,
) -> None:
    workload_id = uuid4()
    cluster_id = uuid4()
    project_id = uuid4()

    mock_get_node_devices.return_value = {
        str(workload_id): [
            WorkloadGpuDevice(gpu_id="0", hostname="worker-1"),
            WorkloadGpuDevice(gpu_id="1", hostname="worker-1"),
        ]
    }

    mock_workload = MagicMock(spec=Workload)
    mock_workload.id = workload_id
    mock_workload.project_id = project_id
    mock_workload.cluster_id = cluster_id
    mock_workload.status = WorkloadStatus.RUNNING.value
    mock_workload.display_name = "test-workload"
    mock_workload.type = "INFERENCE"
    mock_workload.created_at = datetime(2023, 6, 1, tzinfo=UTC)
    mock_workload.created_by = "user@test.com"
    mock_workload.updated_at = datetime(2023, 6, 1, tzinfo=UTC)
    mock_workload.updated_by = "user@test.com"
    mock_workload.__dict__ = {
        "id": workload_id,
        "project_id": project_id,
        "cluster_id": cluster_id,
        "status": WorkloadStatus.RUNNING.value,
        "display_name": "test-workload",
        "type": "INFERENCE",
        "created_at": datetime(2023, 6, 1, tzinfo=UTC),
        "created_by": "user@test.com",
        "updated_at": datetime(2023, 6, 1, tzinfo=UTC),
        "updated_by": "user@test.com",
    }

    mock_get_workloads.return_value = [mock_workload]
    mock_get_vram.return_value = {str(workload_id): 8192.0}

    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    session_mock = AsyncMock(spec=AsyncSession)

    result = await get_workloads_metrics_by_node(
        session=session_mock,
        cluster_id=cluster_id,
        cluster_name="my-cluster",
        node_name="worker-1",
        prometheus_client=prometheus_client_mock,
    )

    assert len(result.data) == 1
    assert result.data[0].display_name == "test-workload"
    assert result.data[0].gpu_count == 2
    assert result.data[0].vram == 8192.0
    assert len(result.data[0].gpu_devices) == 2


@patch("app.metrics.service.get_workloads_on_node_with_gpu_devices")
async def test_get_workloads_metrics_by_node_no_workloads(
    mock_get_node_devices: AsyncMock,
) -> None:
    mock_get_node_devices.return_value = {}
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    session_mock = AsyncMock(spec=AsyncSession)

    result = await get_workloads_metrics_by_node(
        session=session_mock,
        cluster_id=uuid4(),
        cluster_name="my-cluster",
        node_name="idle-worker",
        prometheus_client=prometheus_client_mock,
    )

    assert result.data == []


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_power_usage_queries_both_power_metrics(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    """AMD exporters emit gpu_package_power (MI3xx) XOR gpu_average_package_power (MI2xx);
    the PromQL `or` returns whichever the exporter has without per-family dispatch."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = [{"metric": {"gpu_uuid": "gpu-1"}, "values": []}]
    device_key = ("gpu-1", "worker-1", "0")
    mock_parse.return_value = {device_key: [Datapoint(timestamp=start, value=195.0)]}

    result = await get_node_power_usage(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 1
    assert result.gpu_devices[0].metric.series_label == "powerWatts"
    assert result.gpu_devices[0].metric.values[0].value == 195.0

    query = mock_query_range.call_args[1]["query"]
    assert "gpu_package_power" in query
    assert "gpu_average_package_power" in query
    assert re.search(r"\bor\b", query)
    assert 'hostname="worker-1"' in query
    assert 'kube_cluster_name="my-cluster"' in query


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_gpu_junction_temperature(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = [{"metric": {"gpu_uuid": "gpu-1"}, "values": []}]
    device_key = ("gpu-1", "node-1", "0")
    mock_parse.return_value = {device_key: [Datapoint(timestamp=start, value=72.5)]}

    result = await get_node_gpu_junction_temperature(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 1
    assert result.gpu_devices[0].gpu_uuid == "gpu-1"
    assert result.gpu_devices[0].metric.series_label == "junctionTemperatureCelsius"
    assert result.gpu_devices[0].metric.values[0].value == 72.5
    assert result.range.start == start
    assert result.range.end == end

    query = mock_query_range.call_args[1]["query"]
    assert "gpu_junction_temperature" in query
    assert 'hostname="worker-1"' in query
    assert 'kube_cluster_name="my-cluster"' in query


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_gpu_junction_temperature_empty(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = []
    mock_parse.return_value = {}

    result = await get_node_gpu_junction_temperature(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 0
    assert result.range.start == start
    assert result.range.end == end


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_pcie_bandwidth_timeseries_for_node_success(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    """Returns per-GPU PCIe bandwidth timeseries with correct query and response shape."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)
    t1 = start
    t2 = start + timedelta(seconds=300)

    mock_query_range.return_value = [{"metric": {"gpu_uuid": "gpu-1"}, "values": []}]
    device_key = ("gpu-1", "worker-1", "0")
    mock_parse.return_value = {
        device_key: [
            Datapoint(timestamp=t1, value=1.5),
            Datapoint(timestamp=t2, value=2.0),
        ]
    }

    result = await get_pcie_bandwidth_timeseries_for_node(
        cluster_name="my-cluster",
        node_hostname="worker-1",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 1
    assert result.gpu_devices[0].gpu_uuid == "gpu-1"
    assert result.gpu_devices[0].gpu_id == "0"
    assert result.gpu_devices[0].hostname == "worker-1"
    assert result.gpu_devices[0].metric.series_label == "pcieBandwidth"
    assert [v.value for v in result.gpu_devices[0].metric.values] == [1.5, 2.0]
    assert result.range.start == start
    assert result.range.end == end

    mock_query_range.assert_awaited_once()
    call_kw = mock_query_range.call_args[1]
    assert call_kw["start_time"] == start
    assert call_kw["end_time"] == end
    assert call_kw["step"] == "300"
    query = call_kw["query"]
    assert "pcie_bandwidth" in query
    assert 'kube_cluster_name="my-cluster"' in query
    assert 'hostname="worker-1"' in query
    assert "avg by" in query
    assert "5m" in query


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_pcie_bandwidth_timeseries_for_node_empty(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    """When Prometheus returns no series, response has no GPU devices."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = []
    mock_parse.return_value = {}

    result = await get_pcie_bandwidth_timeseries_for_node(
        cluster_name="my-cluster",
        node_hostname="worker-1",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 0
    assert result.range.start == start
    assert result.range.end == end


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_pcie_bandwidth_timeseries_for_node_with_step(
    mock_lookback: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    """When step is provided, it is used as the query step interval."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = []
    device_key = ("gpu-1", "worker-1", "0")
    mock_parse.return_value = {device_key: [Datapoint(timestamp=start, value=1.0)]}

    result = await get_pcie_bandwidth_timeseries_for_node(
        cluster_name="my-cluster",
        node_hostname="worker-1",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
        step=600,
    )

    assert mock_query_range.call_args[1]["step"] == "600"
    assert len(result.gpu_devices) == 1


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_pcie_efficiency_timeseries_for_node_filters_invalid_datapoints(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    """Invalid values (None, nan, inf) are omitted; only valid finite values appear in the series."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    t1 = start
    t2 = start + timedelta(seconds=300)
    t3 = start + timedelta(seconds=600)
    t4 = start + timedelta(seconds=900)

    mock_query_range.return_value = [{"metric": {"gpu_uuid": "gpu-1"}, "values": []}]
    device_key = ("gpu-1", "node-1", "0")
    mock_parse.return_value = {
        device_key: [
            Datapoint(timestamp=t1, value=None),
            Datapoint(timestamp=t2, value=float("nan")),
            Datapoint(timestamp=t3, value=float("inf")),
            Datapoint(timestamp=t4, value=85.25),
        ]
    }

    result = await get_pcie_efficiency_timeseries_for_node(
        cluster_name="my-cluster",
        node_hostname="worker-1",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=now.replace(microsecond=0),
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 1
    values = result.gpu_devices[0].metric.values
    assert len(values) == 1
    assert values[0].value == 85.25
    assert values[0].timestamp == t4


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_gpu_junction_temperature_with_step(
    mock_lookback: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    """When step is provided, it is used directly as the query step interval."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = []
    device_key = ("gpu-1", "node-1", "0")
    mock_parse.return_value = {device_key: [Datapoint(timestamp=start, value=65.0)]}

    result = await get_node_gpu_junction_temperature(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
        step=600,
    )

    assert mock_query_range.call_args[1]["step"] == "600"
    assert len(result.gpu_devices) == 1


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_step_for_range_query", return_value=300)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_gpu_memory_temperature(
    mock_lookback: MagicMock,
    mock_step: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = [{"metric": {"gpu_uuid": "gpu-1"}, "values": []}]
    device_key = ("gpu-1", "node-1", "0")

    mock_parse.return_value = {device_key: [Datapoint(timestamp=start, value=68.0)]}

    mock_parse.return_value = {device_key: [Datapoint(timestamp=start, value=68.0)]}

    result = await get_node_gpu_memory_temperature(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
        step=600,
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 1
    assert result.gpu_devices[0].gpu_uuid == "gpu-1"
    assert result.gpu_devices[0].metric.series_label == "memoryTemperatureCelsius"
    assert result.gpu_devices[0].metric.values[0].value == 68.0
    assert result.range.start == start
    assert result.range.end == end

    query = mock_query_range.call_args[1]["query"]
    assert "gpu_memory_temperature" in query
    assert 'hostname="worker-1"' in query
    assert 'kube_cluster_name="my-cluster"' in query
    assert "max by" in query
    assert "sum by" not in query


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_gpu_memory_temperature_empty(
    mock_lookback: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = []
    mock_parse.return_value = {}

    result = await get_node_gpu_memory_temperature(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
    )

    assert isinstance(result, GpuDeviceSingleMetricResponse)
    assert len(result.gpu_devices) == 0
    assert result.range.start == start
    assert result.range.end == end


@pytest.mark.asyncio
@patch("app.metrics.service.a_custom_query_range", autospec=True)
@patch("app.metrics.service.parse_device_range_timeseries", autospec=True)
@patch("app.metrics.service.get_aggregation_lookback_for_metrics", return_value="5m")
async def test_get_node_gpu_memory_temperature_with_step(
    mock_lookback: MagicMock,
    mock_parse: MagicMock,
    mock_query_range: AsyncMock,
) -> None:
    """When step is provided, it is used directly as the query step interval."""
    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).replace(microsecond=0)
    end = now.replace(microsecond=0)

    mock_query_range.return_value = []
    device_key = ("gpu-1", "node-1", "0")
    mock_parse.return_value = {device_key: [Datapoint(timestamp=start, value=68.0)]}

    result = await get_node_gpu_memory_temperature(
        node_name="worker-1",
        cluster_name="my-cluster",
        prometheus_client=prometheus_client_mock,
        start=start,
        end=end,
        step=600,
    )
    assert mock_query_range.call_args[1]["step"] == "600"
    assert len(result.gpu_devices) == 1
