# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import math
from collections import defaultdict
from datetime import datetime
from uuid import UUID

from fastapi import Request
from loguru import logger
from prometheus_api_client import PrometheusConnect
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.collections import FilterCondition, PaginationConditions, PaginationMetadata, SortCondition

from ..projects.models import Project
from ..projects.models import Project as ProjectModel
from ..projects.repository import get_projects
from ..projects.utils import map_to_project_response
from ..quotas.repository import get_quotas
from ..utilities.prometheus_instrumentation import ALLOCATED_GPU_VRAM_METRIC_LABEL, ALLOCATED_GPUS_METRIC_LABEL
from ..workloads.enums import WorkloadStatus
from ..workloads.repository import (
    get_average_pending_time_for_workloads_in_project_created_between,
    get_workload_counts_with_status_by_project_id,
    get_workloads_by_ids_in_cluster,
    get_workloads_in_cluster,
    get_workloads_with_running_time_in_project,
)
from .config import PROMETHEUS_URL
from .constants import (
    ALLOCATED_GPU_VRAM_SERIES_LABEL,
    ALLOCATED_GPUS_SERIES_LABEL,
    CLUSTER_NAME_METRIC_LABEL,
    GPU_AVERAGE_PACKAGE_POWER_METRIC,
    GPU_CLOCK_METRIC,
    GPU_CLOCK_TYPE_LABEL,
    GPU_CLOCK_TYPE_SYSTEM_REGEX,
    GPU_GFX_ACTIVITY_METRIC,
    GPU_ID_METRIC_LABEL,
    GPU_JUNCTION_TEMPERATURE_METRIC,
    GPU_MEMORY_TEMPERATURE_METRIC,
    GPU_PACKAGE_POWER_METRIC,
    GPU_TOTAL_VRAM_METRIC,
    GPU_USED_VRAM_METRIC,
    GPU_UUID_METRIC_LABEL,
    HOSTNAME_METRIC_LABEL,
    UTILIZED_GPU_VRAM_SERIES_LABEL,
    UTILIZED_GPUS_SERIES_LABEL,
    WORKLOAD_ID_METRIC_LABEL,
    PCIe_BANDWIDTH_METRIC,
    PCIe_MAX_SPEED_METRIC,
    PCIe_SPEED_METRIC,
)
from .constants import CLUSTER_NAME_METRIC_LABEL as CLUSTER_NAME
from .constants import PROJECT_ID_METRIC_LABEL as PROJECT_ID
from .constants import WORKLOAD_ID_METRIC_LABEL as WORKLOAD_ID
from .enums import WorkloadDeviceMetricKind
from .schemas import (
    CurrentUtilization,
    Datapoint,
    DateRange,
    DeviceMetricTimeseries,
    GpuDeviceSingleMetricResponse,
    GpuDeviceWithSingleMetric,
    MetricsScalarWithRange,
    MetricsTimeRange,
    MetricsTimeseries,
    NodeGpuDevicesResponse,
    NodeWorkloadsWithMetrics,
    NodeWorkloadWithMetrics,
    UtilizationByProject,
    WorkloadGpuDevice,
    WorkloadsWithMetrics,
    WorkloadWithMetrics,
)
from .utils import (
    a_custom_query,
    a_custom_query_range,
    build_node_device_query,
    build_node_instant_query,
    build_node_vram_utilization_instant_query,
    build_workload_device_query,
    construct_timeseries_query_with_fallback_for_default_series,
    convert_prometheus_string_to_float,
    get_aggregation_lookback_for_metrics,
    get_step_for_range_query,
    is_valid_metric_value,
    map_metrics_timeseries,
    map_results_to_node_gpu_devices,
    map_timeseries_split_by_project,
    parse_device_range_timeseries,
)


def init_prometheus_client() -> PrometheusConnect:
    """Initialize Prometheus client. This will be called at application startup."""
    if not PROMETHEUS_URL:
        raise ValueError("PROMETHEUS_URL environment variable must be set")
    client = PrometheusConnect(url=PROMETHEUS_URL, disable_ssl=True)
    logger.info("Connected to Prometheus server at {}", PROMETHEUS_URL)
    return client


def get_prometheus_client(request: Request) -> PrometheusConnect:
    """FastAPI dependency to get the initialized PrometheusConnect client from app.state."""
    if not hasattr(request.app.state, "prometheus_client") or request.app.state.prometheus_client is None:
        logger.error("Prometheus client not initialized in app.state.")
        raise RuntimeError("Prometheus client not available.")
    return request.app.state.prometheus_client


async def get_gpu_memory_utilization_timeseries(
    session: AsyncSession,
    start: datetime,
    end: datetime,
    prometheus_client: PrometheusConnect,
    step: int | None = None,
) -> MetricsTimeseries:
    """
    Returns a timeseries of GPU memory utilization, grouped by Project.

    This corresponds to (GPU Used VRAM (grouped by project) / GPU Total VRAM) or (0 / GPU Total VRAM).
    The second part of the query ensures that if there is data available for GPU Total VRAM, we receive 0 utilization
    but if it doesn't have values, we receive NaN. This is to account for cases where there was a network error and we
    don't have values to display.
    """
    projects = await get_projects(session)

    query_step = step if step else get_step_for_range_query(start, end)

    numerator = f"""
sum by({PROJECT_ID}) (
    gpu_used_vram
) * 100
"""
    denominator = """
scalar(
    sum(
        max by (gpu_uuid, hostname) (
            gpu_total_vram
        )
    )
)
"""

    query = construct_timeseries_query_with_fallback_for_default_series(numerator, denominator)

    results = await a_custom_query_range(
        client=prometheus_client, query=query, start_time=start, end_time=end, step=str(query_step)
    )
    return map_timeseries_split_by_project(
        results=results,
        projects=projects,
        start=start,
        end=end,
        step=query_step,
        series_label=UTILIZED_GPU_VRAM_SERIES_LABEL,
    )


async def get_gpu_device_utilization_timeseries(
    session: AsyncSession,
    start: datetime,
    end: datetime,
    prometheus_client: PrometheusConnect,
    step: int | None = None,
) -> MetricsTimeseries:
    """
    Returns a timeseries of GPU device utilization, grouped by Project.

    This corresponds to (Number of unique GPUs used (grouped by project) / Total number of GPUs) or (0 / Total number of GPUs).
    The second part of the query ensures that if there is data available for Total number of GPUs, we receive 0 utilization
    but if it doesn't have values, we receive NaN. This is to account for cases where there was a network error and we
    don't have values to display.
    """
    projects = await get_projects(session)

    query_step = step if step else get_step_for_range_query(start, end)

    numerator = f"""
count by ({PROJECT_ID}) (
        {GPU_GFX_ACTIVITY_METRIC}
) * 100
"""
    denominator = """
scalar(
    count(
        count by (gpu_uuid, hostname) (
            gpu_total_vram
        )
    )
)
"""

    query = construct_timeseries_query_with_fallback_for_default_series(numerator, denominator)
    results = await a_custom_query_range(
        client=prometheus_client, query=query, start_time=start, end_time=end, step=str(query_step)
    )
    return map_timeseries_split_by_project(
        results=results,
        projects=projects,
        start=start,
        end=end,
        step=query_step,
        series_label=UTILIZED_GPUS_SERIES_LABEL,
    )


async def get_gpu_device_utilization_timeseries_for_cluster(
    session: AsyncSession,
    start: datetime,
    end: datetime,
    cluster_name: str,
    prometheus_client: PrometheusConnect,
    step: int | None = None,
) -> MetricsTimeseries:
    """
    Returns a timeseries of GPU device utilization for the given cluster, grouped by Project.

    This corresponds to (Number of unique GPUs used (grouped by project) / Total number of GPUs) or (0 / Total number of GPUs).
    The second part of the query ensures that if there is data available for Total number of GPUs, we receive 0 utilization
    but if it doesn't have values, we receive NaN. This is to account for cases where there was a network error and we
    don't have values to display.
    """
    projects = await get_projects(session)
    query_step = step if step else get_step_for_range_query(start, end)

    numerator = f"""
count by ({PROJECT_ID}) (
    {GPU_GFX_ACTIVITY_METRIC}{{{CLUSTER_NAME}="{cluster_name}"}}
) * 100
"""
    denominator = f"""
scalar(
    count(
        count by (gpu_uuid, hostname) (
            gpu_total_vram{{{CLUSTER_NAME}="{cluster_name}"}}
        )
    )
)
"""

    query = construct_timeseries_query_with_fallback_for_default_series(numerator, denominator)
    results = await a_custom_query_range(
        client=prometheus_client, query=query, start_time=start, end_time=end, step=str(query_step)
    )
    return map_timeseries_split_by_project(
        results=results,
        projects=projects,
        start=start,
        end=end,
        step=query_step,
        series_label=UTILIZED_GPUS_SERIES_LABEL,
    )


async def get_current_utilization(session: AsyncSession, prometheus_client: PrometheusConnect) -> CurrentUtilization:
    """
    Returns a snapshot of GPU device utilization for the given cluster, grouped by Project, along with some workload stats.
    """
    workload_counts_by_project, quotas, projects = await asyncio.gather(
        get_workload_counts_with_status_by_project_id(session, [WorkloadStatus.RUNNING, WorkloadStatus.PENDING]),
        get_quotas(session),
        get_projects(session),
    )

    allocated_gpu_counts_by_project: dict[UUID, int] = defaultdict(int)
    for quota in quotas:
        allocated_gpu_counts_by_project[quota.project_id] += quota.gpu_count

    utilization_by_project_id = await __get_utilized_gpu_count_by_project(
        prometheus_client=prometheus_client,
    )
    total_running_workloads_count = sum(
        count for (_, status), count in workload_counts_by_project.items() if status == WorkloadStatus.RUNNING
    )
    total_pending_workloads_count = sum(
        count for (_, status), count in workload_counts_by_project.items() if status == WorkloadStatus.PENDING
    )

    return CurrentUtilization(
        total_utilized_gpus_count=sum([utilization_by_project_id.get(str(project.id), 0) for project in projects]),
        total_running_workloads_count=total_running_workloads_count,
        total_pending_workloads_count=total_pending_workloads_count,
        utilization_by_project=[
            UtilizationByProject(
                project=map_to_project_response(project),
                allocated_gpus_count=allocated_gpu_counts_by_project.get(project.id, 0),
                utilized_gpus_count=utilization_by_project_id.get(str(project.id), 0),
                running_workloads_count=workload_counts_by_project.get((project.id, WorkloadStatus.RUNNING), 0),
                pending_workloads_count=workload_counts_by_project.get((project.id, WorkloadStatus.PENDING), 0),
            )
            for project in projects
        ],
    )


async def __get_utilized_gpu_count_by_project(prometheus_client: PrometheusConnect) -> dict[str, int]:
    # Query the most recent GPU utilization snapshot per project
    results = await a_custom_query(
        client=prometheus_client,
        query=f"""
count by ({PROJECT_ID}) (
    {GPU_GFX_ACTIVITY_METRIC}
)
""",
    )
    project_gpu_counts: dict[str, int] = {}
    for result in results:
        project_id = result["metric"].get(PROJECT_ID, None)
        value = int(result["value"][1])
        project_gpu_counts[project_id] = value
    return project_gpu_counts


async def get_gpu_device_utilization_timeseries_for_project(
    start: datetime, end: datetime, project: ProjectModel, prometheus_client: PrometheusConnect, step: int | None = None
) -> MetricsTimeseries:
    """
    Returns two timeseries of GPU device utilization for the given project:
    Count of utilized GPUs vs count of allocated GPUs.

    For count of utilized GPUs, the data is "or-ed" with a fallback to 0 * a guaranteed-available metric,
    (max(gpu_total_vram)), that is always expected to exist - Absence of this metric implies error collecting data,
    and will result in null value for that datapoint. This is needed because gpu_gfx_activity{project_id="..."}
    only exists when the GPU is being utilized by a workload of the project, else it returns a null.

    gpu_total_vram was chosen instead of allocated_gpus since the source of gpu_total_vram (GPU metrics exporter)
    is the same as that of gpu_gfx_activity
    """
    query_step = step if step else get_step_for_range_query(start, end)
    utilized_gpus = f"""
count(
    {GPU_GFX_ACTIVITY_METRIC}{{{PROJECT_ID}="{project.id}"}}
)
OR (0 * max(gpu_total_vram{{{CLUSTER_NAME}="{project.cluster.name}"}}))
"""
    allocated_gpus = f"""
max(
    {ALLOCATED_GPUS_METRIC_LABEL}{{{PROJECT_ID}="{project.id}"}}
)
"""
    utilized_gpus_res, allocated_gpus_res = await asyncio.gather(
        a_custom_query_range(
            client=prometheus_client, query=utilized_gpus, start_time=start, end_time=end, step=str(query_step)
        ),
        a_custom_query_range(
            client=prometheus_client, query=allocated_gpus, start_time=start, end_time=end, step=str(query_step)
        ),
    )
    utilized_gpus_timeseries = map_metrics_timeseries(
        results=utilized_gpus_res,
        project=project,
        start=start,
        end=end,
        step=query_step,
        series_label=UTILIZED_GPUS_SERIES_LABEL,
    )
    allocated_gpus_timeseries = map_metrics_timeseries(
        results=allocated_gpus_res,
        project=project,
        start=start,
        end=end,
        step=query_step,
        series_label=ALLOCATED_GPUS_SERIES_LABEL,
    )

    return MetricsTimeseries(
        data=utilized_gpus_timeseries.data + allocated_gpus_timeseries.data, range=utilized_gpus_timeseries.range
    )


async def get_gpu_memory_utilization_timeseries_for_project(
    start: datetime, end: datetime, project: ProjectModel, prometheus_client: PrometheusConnect, step: int | None = None
) -> MetricsTimeseries:
    """
    Returns two timeseries of GPU memory utilization for the given project:
    Utilized GPU VRAM vs (count of allocated GPUs * VRAM per GPU)

    For utilized GPU VRAM, the data is "or-ed" with a fallback to 0 * a guaranteed-available metric,
    (max(gpu_total_vram)), that is always expected to exist. Absence of this metric implies error collecting data,
    and will result in null value for that datapoint. This is needed because gpu_used_vram{project_id="..."}
    only exists when the GPU is being utilized by a workload of the project, else it returns a null.

    gpu_total_vram was chosen instead of allocated_gpus since the source of gpu_total_vram (GPU metrics exporter)
    is the same as that of gpu_used_vram

    """
    query_step = step if step else get_step_for_range_query(start, end)
    utilized_vram = f"""
sum(
    gpu_used_vram{{{PROJECT_ID}="{project.id}"}}
)
OR (0 * max(gpu_total_vram{{{CLUSTER_NAME}="{project.cluster.name}"}}))
"""
    allocated_vram = f"""
max(
    {ALLOCATED_GPU_VRAM_METRIC_LABEL}{{{PROJECT_ID}="{project.id}"}}
)
"""
    utilized_vram_res, allocated_vram_res = await asyncio.gather(
        a_custom_query_range(
            client=prometheus_client, query=utilized_vram, start_time=start, end_time=end, step=str(query_step)
        ),
        a_custom_query_range(
            client=prometheus_client, query=allocated_vram, start_time=start, end_time=end, step=str(query_step)
        ),
    )
    utilized_vram_timeseries = map_metrics_timeseries(
        results=utilized_vram_res,
        project=project,
        start=start,
        end=end,
        step=query_step,
        series_label=UTILIZED_GPU_VRAM_SERIES_LABEL,
    )
    allocated_vram_timeseries = map_metrics_timeseries(
        results=allocated_vram_res,
        project=project,
        start=start,
        end=end,
        step=query_step,
        series_label=ALLOCATED_GPU_VRAM_SERIES_LABEL,
    )

    return MetricsTimeseries(
        data=utilized_vram_timeseries.data + allocated_vram_timeseries.data, range=utilized_vram_timeseries.range
    )


async def _get_gpu_device_utilization_by_workload_id_with_filter(
    prometheus_client: PrometheusConnect, prometheus_filter: str
) -> dict[str, int]:
    """
    Helper function to get GPU device utilization by workload ID with a custom Prometheus filter.
    Returns a snapshot of the count of utilized GPUs for each workload matching the filter.
    """
    results = await a_custom_query(
        client=prometheus_client,
        query=f"""
count by ({WORKLOAD_ID}) (
  {GPU_GFX_ACTIVITY_METRIC}{{{prometheus_filter}}}
)
""",
    )
    workload_gpu_counts: dict[str, int] = {}
    for result in results:
        workload_id = result["metric"].get(WORKLOAD_ID, None)
        value = int(result["value"][1])
        workload_gpu_counts[workload_id] = value
    return workload_gpu_counts


async def _get_gpu_memory_utilization_by_workload_id_with_filter(
    prometheus_client: PrometheusConnect, prometheus_filter: str
) -> dict[str, float]:
    """
    Helper function to get GPU memory utilization by workload ID with a custom Prometheus filter.
    Returns a snapshot of the current utilized VRAM for each workload matching the filter.
    """
    results = await a_custom_query(
        client=prometheus_client,
        query=f"""
sum by ({WORKLOAD_ID}) (
  gpu_used_vram{{{prometheus_filter}}}
)
""",
    )
    workload_vram_usage: dict[str, float] = {}
    for result in results:
        workload_id = result["metric"].get(WORKLOAD_ID, None)
        value = convert_prometheus_string_to_float(result["value"][1])
        workload_vram_usage[workload_id] = value
    return workload_vram_usage


async def get_gpu_and_node_counts_for_workload(
    workload_id: UUID, prometheus_client: PrometheusConnect
) -> tuple[int, int]:
    """
    Returns (gpu_devices_in_use, nodes_in_use) for a single workload
    """
    wid_filter = f'{WORKLOAD_ID}="{workload_id}"'

    gpu_results, node_results = await asyncio.gather(
        a_custom_query(
            client=prometheus_client,
            query=f"count({GPU_GFX_ACTIVITY_METRIC}{{{wid_filter}}})",
        ),
        a_custom_query(
            client=prometheus_client,
            query=f"count(count by ({HOSTNAME_METRIC_LABEL}) ({GPU_GFX_ACTIVITY_METRIC}{{{wid_filter}}}))",
        ),
    )

    gpu_count = int(gpu_results[0]["value"][1]) if gpu_results else 0
    node_count = int(node_results[0]["value"][1]) if node_results else 0
    return gpu_count, node_count


async def get_node_names_for_workload(workload_id: UUID, prometheus_client: PrometheusConnect) -> list[str]:
    """
    Returns the list of node hostnames (Prometheus label 'hostname') that have
    GPU activity for the given workload at the current time
    """
    wid_filter = f'{WORKLOAD_ID}="{workload_id}"'
    results = await a_custom_query(
        client=prometheus_client,
        query=f"{GPU_GFX_ACTIVITY_METRIC}{{{wid_filter}}}",
    )
    names: list[str] = []
    seen: set[str] = set()
    for item in results:
        name = item.get("metric", {}).get(HOSTNAME_METRIC_LABEL)
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


async def get_gpu_device_utilization_for_project_by_workload_id(
    project_id: UUID, prometheus_client: PrometheusConnect
) -> dict[str, int]:
    """
    Returns a snapshot of the count of utilized GPUs for each workload in the given project.
    """
    return await _get_gpu_device_utilization_by_workload_id_with_filter(
        prometheus_client, f'{PROJECT_ID}="{project_id}"'
    )


async def get_gpu_memory_utilization_for_project_by_workload_id(
    project_id: UUID, prometheus_client: PrometheusConnect
) -> dict[str, float]:
    """
    Returns a snapshot of the average utilized VRAM for each workload in the given project.
    """
    return await _get_gpu_memory_utilization_by_workload_id_with_filter(
        prometheus_client, f'{PROJECT_ID}="{project_id}"'
    )


async def get_gpu_device_utilization_for_cluster_by_workload_id(
    cluster_name: str, prometheus_client: PrometheusConnect
) -> dict[str, int]:
    """
    Returns a snapshot of the count of utilized GPUs for each workload in the given cluster.
    """
    return await _get_gpu_device_utilization_by_workload_id_with_filter(
        prometheus_client, f'{CLUSTER_NAME}="{cluster_name}"'
    )


async def get_gpu_memory_utilization_for_cluster_by_workload_id(
    cluster_name: str, prometheus_client: PrometheusConnect
) -> dict[str, float]:
    """
    Returns a snapshot of the average utilized VRAM for each workload in the given cluster.
    """
    return await _get_gpu_memory_utilization_by_workload_id_with_filter(
        prometheus_client, f'{CLUSTER_NAME}="{cluster_name}"'
    )


async def get_workloads_metrics_by_project(
    session: AsyncSession,
    project: Project,
    prometheus_client: PrometheusConnect,
    pagination_params: PaginationConditions,
    sort_params: list[SortCondition],
    filter_params: list[FilterCondition],
) -> WorkloadsWithMetrics:
    """
    Returns a snapshot of workloads with their corresponding metrics for the given project.

    This includes the:
    - GPUs currently allocated to the workload
    - VRAM currently utilized by the workload
    - Aggregated run time of the workload in seconds (Elapsed run time + (now - last status change if current status = RUNNING)
    """
    [workloads_with_running_time, count], workload_gpu_counts, workload_vram_usage = await asyncio.gather(
        get_workloads_with_running_time_in_project(session, project.id, pagination_params, sort_params, filter_params),
        get_gpu_device_utilization_for_project_by_workload_id(project.id, prometheus_client),
        get_gpu_memory_utilization_for_project_by_workload_id(project.id, prometheus_client),
    )
    workload_metrics = []
    for workload, running_time in workloads_with_running_time:
        workload_dict = {
            **workload.__dict__,
            "gpu_count": workload_gpu_counts.get(str(workload.id), 0),
            "vram": workload_vram_usage.get(str(workload.id), 0),
            "run_time": int(running_time),
        }
        workload_metrics.append(WorkloadWithMetrics.model_validate(workload_dict))

    return WorkloadsWithMetrics(
        data=workload_metrics,
        pagination=PaginationMetadata(
            page=pagination_params.page,
            page_size=pagination_params.page_size,
            total=count,
        ),
    )


async def get_workloads_metrics_by_cluster(
    session: AsyncSession,
    cluster_id: UUID,
    cluster_name: str,
    prometheus_client: PrometheusConnect,
    pagination_params: PaginationConditions,
    sort_params: list[SortCondition],
    filter_params: list[FilterCondition],
) -> WorkloadsWithMetrics:
    """
    Returns a snapshot of workloads with their corresponding metrics for the given cluster.

    This includes the:
    - GPUs currently allocated to the workload
    - VRAM currently utilized by the workload
    """
    [workloads, count], workload_gpu_counts, workload_vram_usage = await asyncio.gather(
        get_workloads_in_cluster(session, cluster_id, pagination_params, sort_params, filter_params),
        get_gpu_device_utilization_for_cluster_by_workload_id(cluster_name, prometheus_client),
        get_gpu_memory_utilization_for_cluster_by_workload_id(cluster_name, prometheus_client),
    )
    workload_metrics = []
    for workload in workloads:
        workload_dict = {
            **workload.__dict__,
            "gpu_count": workload_gpu_counts.get(str(workload.id), 0),
            "vram": workload_vram_usage.get(str(workload.id), 0),
        }
        workload_metrics.append(WorkloadWithMetrics.model_validate(workload_dict))

    return WorkloadsWithMetrics(
        data=workload_metrics,
        pagination=PaginationMetadata(
            page=pagination_params.page,
            page_size=pagination_params.page_size,
            total=count,
        ),
    )


async def get_average_wait_time_for_project(
    session: AsyncSession, start: datetime, end: datetime, project: ProjectModel
) -> MetricsScalarWithRange:
    """
    Returns the average wait time for workloads in the given project that were created between the start and end dates.
    Average wait time corresponds to avg(Elapsed pending time + (now - last status change if current status = PENDING))

    """
    average_wait_time = await get_average_pending_time_for_workloads_in_project_created_between(
        session, project.id, start, end
    )

    return MetricsScalarWithRange(
        data=average_wait_time or 0,
        range=DateRange(start=start, end=end),
    )


async def get_avg_gpu_idle_time_for_project(
    start: datetime, end: datetime, project: ProjectModel, prometheus_client: PrometheusConnect, step: int | None = None
) -> MetricsScalarWithRange:
    """
    Returns the average GPU idle time for the given project within the specified date range.

    The idle time is calculated as:
    sum((Average allocated GPUs - Average utilized GPUs) * step / Average allocated GPU)

    For each datapoint, it computes the average allocated GPUs and average utilized GPUs over a lookback period,
    This is then multiplied by the step size to get the idle time in seconds, for that time range.
    These are then summed up, to get the total idle time for the range.
    """
    query_step = step if step else get_step_for_range_query(start, end)
    lookback = get_aggregation_lookback_for_metrics(query_step)

    idle_time_query = f"""
(
    avg_over_time(
        avg(
            {ALLOCATED_GPUS_METRIC_LABEL}{{{PROJECT_ID}="{project.id}"}}
        )
        [{lookback}:]
    ) -
    on() avg_over_time(
        count(
            {GPU_GFX_ACTIVITY_METRIC}{{{PROJECT_ID}="{project.id}"}}
        )
        [{lookback}:]
    )
) * {query_step}
/
on() avg_over_time(
        avg(
            {ALLOCATED_GPUS_METRIC_LABEL}{{{PROJECT_ID}="{project.id}"}}
        )
        [{lookback}:]
)
"""
    results = await a_custom_query_range(
        client=prometheus_client, query=idle_time_query, start_time=start, end_time=end, step=str(query_step)
    )

    idle_time = sum([float(v[1]) for v in results[0]["values"] if is_valid_metric_value(v[1])] if results else []) or 0

    return MetricsScalarWithRange(
        data=max(idle_time, 0),
        range=DateRange(start=start, end=end),
    )


async def _get_gpu_device_single_metric_for_workload(
    workload_id: UUID,
    prometheus_client: PrometheusConnect,
    start: datetime,
    end: datetime,
    metric_kind: WorkloadDeviceMetricKind,
    step: int | None = None,
) -> GpuDeviceSingleMetricResponse:
    """
    Returns per-GPU device timeseries for a single metric (vram_utilization, gpu_utilization, or power_usage).
    """
    wid = str(workload_id)
    query_step = step if step else get_step_for_range_query(start, end)
    lookback = get_aggregation_lookback_for_metrics(query_step)
    group_by = "gpu_id, gpu_uuid, hostname"
    wid_filter = f'{WORKLOAD_ID_METRIC_LABEL}="{workload_id}"'

    if metric_kind == WorkloadDeviceMetricKind.VRAM_UTILIZATION:
        query = f"""
avg by ({group_by}) (avg_over_time(gpu_used_vram{{{wid_filter}}}[{lookback}]))
/ on({group_by})
avg by ({group_by}) (gpu_total_vram{{{wid_filter}}})
* 100
"""
        series_label = "vramUtilizationPct"
    elif metric_kind == WorkloadDeviceMetricKind.GPU_UTILIZATION:
        query = build_workload_device_query(wid, GPU_GFX_ACTIVITY_METRIC, "avg", use_lookback=True, lookback=lookback)
        series_label = "gpuActivityPct"
    elif metric_kind == WorkloadDeviceMetricKind.POWER_USAGE:
        package_power = build_workload_device_query(
            wid, GPU_PACKAGE_POWER_METRIC, "max", use_lookback=True, lookback=lookback
        )
        avg_package_power = build_workload_device_query(
            wid, GPU_AVERAGE_PACKAGE_POWER_METRIC, "max", use_lookback=True, lookback=lookback
        )
        query = f"{package_power} or {avg_package_power}"
        series_label = "powerWatts"
    else:
        raise ValueError(f"Unknown metric_kind: {metric_kind}")

    result = await a_custom_query_range(
        client=prometheus_client,
        query=query,
        start_time=start,
        end_time=end,
        step=str(query_step),
    )
    by_device = parse_device_range_timeseries(result, start, end, query_step)
    gpu_devices = [
        GpuDeviceWithSingleMetric(
            gpu_uuid=gpu_uuid,
            gpu_id=gpu_id,
            hostname=hostname,
            metric=DeviceMetricTimeseries(series_label=series_label, values=values),
        )
        for (gpu_uuid, hostname, gpu_id), values in sorted(by_device.items())
    ]
    return GpuDeviceSingleMetricResponse(
        gpu_devices=gpu_devices,
        range=MetricsTimeRange(start=start, end=end),
    )


async def get_gpu_device_vram_utilization_for_workload(
    workload_id: UUID,
    prometheus_client: PrometheusConnect,
    start: datetime,
    end: datetime,
    step: int | None = None,
) -> GpuDeviceSingleMetricResponse:
    """Returns per-GPU VRAM utilization percentage timeseries for the given workload."""
    return await _get_gpu_device_single_metric_for_workload(
        workload_id, prometheus_client, start, end, metric_kind=WorkloadDeviceMetricKind.VRAM_UTILIZATION, step=step
    )


async def get_gpu_device_gpu_utilization_for_workload(
    workload_id: UUID,
    prometheus_client: PrometheusConnect,
    start: datetime,
    end: datetime,
    step: int | None = None,
) -> GpuDeviceSingleMetricResponse:
    """Returns per-GPU core activity (gpu_gfx_activity %) timeseries for the given workload."""
    return await _get_gpu_device_single_metric_for_workload(
        workload_id, prometheus_client, start, end, metric_kind=WorkloadDeviceMetricKind.GPU_UTILIZATION, step=step
    )


async def get_gpu_device_power_usage_for_workload(
    workload_id: UUID,
    prometheus_client: PrometheusConnect,
    start: datetime,
    end: datetime,
    step: int | None = None,
) -> GpuDeviceSingleMetricResponse:
    """Returns per-GPU power draw (watts) timeseries for the given workload."""
    return await _get_gpu_device_single_metric_for_workload(
        workload_id, prometheus_client, start, end, metric_kind=WorkloadDeviceMetricKind.POWER_USAGE, step=step
    )


async def _get_node_gpu_single_metric(
    prometheus_client: PrometheusConnect,
    start: datetime,
    end: datetime,
    query: str,
    series_label: str,
    step: float,
) -> GpuDeviceSingleMetricResponse:
    result = await a_custom_query_range(
        client=prometheus_client,
        query=query,
        start_time=start,
        end_time=end,
        step=str(step),
    )
    by_device = parse_device_range_timeseries(result, start, end, step)
    gpu_devices = [
        GpuDeviceWithSingleMetric(
            gpu_uuid=gpu_uuid,
            gpu_id=gpu_id,
            hostname=hostname,
            metric=DeviceMetricTimeseries(series_label=series_label, values=values),
        )
        for (gpu_uuid, hostname, gpu_id), values in sorted(by_device.items())
    ]
    return GpuDeviceSingleMetricResponse(
        gpu_devices=gpu_devices,
        range=MetricsTimeRange(start=start, end=end),
    )


async def get_node_gpu_utilization(
    node_name: str,
    cluster_name: str,
    prometheus_client: PrometheusConnect,
    start: datetime,
    end: datetime,
    step: int | None = None,
) -> GpuDeviceSingleMetricResponse:
    """Returns per-GPU core activity (gpu_gfx_activity %) timeseries for the given cluster node."""
    query_step = step if step else get_step_for_range_query(start, end)
    lookback = get_aggregation_lookback_for_metrics(query_step)

    query = build_node_device_query(node_name, cluster_name, GPU_GFX_ACTIVITY_METRIC, "avg", lookback)
    return await _get_node_gpu_single_metric(prometheus_client, start, end, query, "gpuActivityPct", query_step)


async def get_node_gpu_vram_utilization(
    node_name: str,
    cluster_name: str,
    prometheus_client: PrometheusConnect,
    start: datetime,
    end: datetime,
    step: int | None = None,
) -> GpuDeviceSingleMetricResponse:
    """Returns per-GPU VRAM utilization (%) timeseries for the given cluster node."""
    query_step = step if step else get_step_for_range_query(start, end)
    lookback = get_aggregation_lookback_for_metrics(query_step)
    node_filter = f'{HOSTNAME_METRIC_LABEL}="{node_name}", {CLUSTER_NAME_METRIC_LABEL}="{cluster_name}"'
    group_by = f"{GPU_ID_METRIC_LABEL}, {GPU_UUID_METRIC_LABEL}, {HOSTNAME_METRIC_LABEL}"
    query = f"""
avg by ({group_by}) (avg_over_time({GPU_USED_VRAM_METRIC}{{{node_filter}}}[{lookback}]))
/ on({group_by})
avg by ({group_by}) ({GPU_TOTAL_VRAM_METRIC}{{{node_filter}}})
* 100
"""
    return await _get_node_gpu_single_metric(prometheus_client, start, end, query, "vramUtilizationPct", query_step)


async def get_node_gpu_clock_speed(
    node_name: str,
    cluster_name: str,
    prometheus_client: PrometheusConnect,
    start: datetime,
    end: datetime,
    step: int | None = None,
) -> GpuDeviceSingleMetricResponse:
    """Returns per-GPU system clock speed (MHz) timeseries for the given cluster node."""
    query_step = step if step else get_step_for_range_query(start, end)
    lookback = get_aggregation_lookback_for_metrics(query_step)
    query = build_node_device_query(
        node_name,
        cluster_name,
        GPU_CLOCK_METRIC,
        "avg",
        lookback,
        extra_regex_filters={GPU_CLOCK_TYPE_LABEL: GPU_CLOCK_TYPE_SYSTEM_REGEX},
    )
    return await _get_node_gpu_single_metric(prometheus_client, start, end, query, "clockSpeedMhz", query_step)


async def get_node_power_usage(
    node_name: str,
    cluster_name: str,
    prometheus_client: PrometheusConnect,
    start: datetime,
    end: datetime,
    step: int | None = None,
) -> GpuDeviceSingleMetricResponse:
    """Returns per-GPU power draw (watts) timeseries for the given cluster node."""
    query_step = step if step else get_step_for_range_query(start, end)
    lookback = get_aggregation_lookback_for_metrics(query_step)

    package_power = build_node_device_query(node_name, cluster_name, GPU_PACKAGE_POWER_METRIC, "max", lookback)
    avg_package_power = build_node_device_query(
        node_name, cluster_name, GPU_AVERAGE_PACKAGE_POWER_METRIC, "max", lookback
    )
    query = f"{package_power} or {avg_package_power}"

    result = await a_custom_query_range(
        client=prometheus_client,
        query=query,
        start_time=start,
        end_time=end,
        step=str(query_step),
    )
    by_device = parse_device_range_timeseries(result, start, end, query_step)
    gpu_devices = [
        GpuDeviceWithSingleMetric(
            gpu_uuid=gpu_uuid,
            gpu_id=gpu_id,
            hostname=hostname,
            metric=DeviceMetricTimeseries(series_label="powerWatts", values=values),
        )
        for (gpu_uuid, hostname, gpu_id), values in sorted(by_device.items())
    ]
    return GpuDeviceSingleMetricResponse(
        gpu_devices=gpu_devices,
        range=MetricsTimeRange(start=start, end=end),
    )


async def get_node_gpu_junction_temperature(
    node_name: str,
    cluster_name: str,
    prometheus_client: PrometheusConnect,
    start: datetime,
    end: datetime,
    step: int | None = None,
) -> GpuDeviceSingleMetricResponse:
    """Returns per-GPU junction temperature (Celsius) timeseries for the given cluster node."""
    query_step = step if step else get_step_for_range_query(start, end)
    lookback = get_aggregation_lookback_for_metrics(query_step)

    query = build_node_device_query(node_name, cluster_name, GPU_JUNCTION_TEMPERATURE_METRIC, "max", lookback)
    return await _get_node_gpu_single_metric(
        prometheus_client, start, end, query, "junctionTemperatureCelsius", query_step
    )


async def get_node_gpu_memory_temperature(
    node_name: str,
    cluster_name: str,
    prometheus_client: PrometheusConnect,
    start: datetime,
    end: datetime,
    step: int | None = None,
) -> GpuDeviceSingleMetricResponse:
    """Returns per-GPU memory temperature (Celsius) timeseries for the given cluster node."""
    query_step = step if step else get_step_for_range_query(start, end)
    lookback = get_aggregation_lookback_for_metrics(query_step)

    query = build_node_device_query(node_name, cluster_name, GPU_MEMORY_TEMPERATURE_METRIC, "max", lookback)
    return await _get_node_gpu_single_metric(
        prometheus_client, start, end, query, "memoryTemperatureCelsius", query_step
    )


async def get_pcie_bandwidth_timeseries_for_node(
    cluster_name: str,
    node_hostname: str,
    start: datetime,
    end: datetime,
    prometheus_client: PrometheusConnect,
    step: int | None = None,
) -> GpuDeviceSingleMetricResponse:
    """
    Returns per-GPU PCIe bandwidth timeseries for a specific node in a cluster.
    Filters by cluster name and node hostname; uses the exporter's pcie_bandwidth metric.
    """
    query_step = step if step else get_step_for_range_query(start, end)
    lookback = get_aggregation_lookback_for_metrics(query_step)
    group_by = "gpu_id, gpu_uuid, hostname"
    node_filter = f'{CLUSTER_NAME}="{cluster_name}", {HOSTNAME_METRIC_LABEL}="{node_hostname}"'
    query = f"avg by ({group_by}) (avg_over_time({PCIe_BANDWIDTH_METRIC}{{{node_filter}}}[{lookback}]))"

    result = await a_custom_query_range(
        client=prometheus_client,
        query=query,
        start_time=start,
        end_time=end,
        step=str(query_step),
    )
    by_device = parse_device_range_timeseries(result, start, end, query_step)
    gpu_devices = [
        GpuDeviceWithSingleMetric(
            gpu_uuid=gpu_uuid,
            gpu_id=gpu_id,
            hostname=hostname,
            metric=DeviceMetricTimeseries(series_label="pcieBandwidth", values=values),
        )
        for (gpu_uuid, hostname, gpu_id), values in sorted(by_device.items())
    ]
    return GpuDeviceSingleMetricResponse(
        gpu_devices=gpu_devices,
        range=MetricsTimeRange(start=start, end=end),
    )


async def get_pcie_efficiency_timeseries_for_node(
    cluster_name: str,
    node_hostname: str,
    start: datetime,
    end: datetime,
    prometheus_client: PrometheusConnect,
    step: int | None = None,
) -> GpuDeviceSingleMetricResponse:
    """
    Returns per-GPU PCIe efficiency (speed / max_speed as percentage) timeseries for a specific node.
    Uses a single PromQL range query that computes the ratio in Prometheus, avoiding timestamp-matching in Python.
    """
    query_step = step if step else get_step_for_range_query(start, end)
    lookback = get_aggregation_lookback_for_metrics(query_step)
    group_by = "gpu_id, gpu_uuid, hostname"
    node_filter = f'{CLUSTER_NAME}="{cluster_name}", {HOSTNAME_METRIC_LABEL}="{node_hostname}"'
    # Ratio in PromQL: (speed / max_speed) * 100 per device; division by zero yields NaN (dropped in parse).
    speed_avg = f"avg by ({group_by}) (avg_over_time({PCIe_SPEED_METRIC}{{{node_filter}}}[{lookback}]))"
    max_speed_avg = f"avg by ({group_by}) (avg_over_time({PCIe_MAX_SPEED_METRIC}{{{node_filter}}}[{lookback}]))"
    query = f"({speed_avg} / {max_speed_avg}) * 100"

    result = await a_custom_query_range(
        client=prometheus_client,
        query=query,
        start_time=start,
        end_time=end,
        step=str(query_step),
    )
    by_device = parse_device_range_timeseries(result, start, end, query_step)
    gpu_devices = []
    for (gpu_uuid, hostname, gpu_id), points in sorted(by_device.items()):
        values = []
        for dp in points:
            val = dp.value
            if val is None or not is_valid_metric_value(val):
                continue
            v = float(val)
            v = 0.0 if not math.isfinite(v) else round(v, 2)
            values.append(Datapoint(timestamp=dp.timestamp, value=v))
        gpu_devices.append(
            GpuDeviceWithSingleMetric(
                gpu_uuid=gpu_uuid,
                gpu_id=gpu_id,
                hostname=hostname,
                metric=DeviceMetricTimeseries(series_label="pcieEfficiency", values=values),
            )
        )
    return GpuDeviceSingleMetricResponse(
        gpu_devices=gpu_devices,
        range=MetricsTimeRange(start=start, end=end),
    )


async def get_node_gpu_devices_with_metrics(
    node_name: str,
    cluster_name: str,
    gpu_product_name: str | None,
    prometheus_client: PrometheusConnect,
) -> NodeGpuDevicesResponse:
    """Returns the latest snapshot metrics for each GPU device on the given cluster node."""
    package_power = build_node_instant_query(node_name, cluster_name, GPU_PACKAGE_POWER_METRIC)
    avg_package_power = build_node_instant_query(node_name, cluster_name, GPU_AVERAGE_PACKAGE_POWER_METRIC)
    power_query = f"{package_power} or {avg_package_power}"
    temp_results, power_results, vram_util_results = await asyncio.gather(
        a_custom_query(
            client=prometheus_client,
            query=build_node_instant_query(node_name, cluster_name, GPU_JUNCTION_TEMPERATURE_METRIC),
        ),
        a_custom_query(
            client=prometheus_client,
            query=power_query,
        ),
        a_custom_query(
            client=prometheus_client,
            query=build_node_vram_utilization_instant_query(node_name, cluster_name),
        ),
    )

    gpu_devices = map_results_to_node_gpu_devices(
        temp_results=temp_results,
        power_results=power_results,
        vram_util_results=vram_util_results,
        gpu_product_name=gpu_product_name,
    )

    return NodeGpuDevicesResponse(gpu_devices=gpu_devices)


async def get_workloads_on_node_with_gpu_devices(
    node_name: str,
    cluster_name: str,
    prometheus_client: PrometheusConnect,
) -> dict[str, list[WorkloadGpuDevice]]:
    """
    Single query to get all workloads with GPU activity in the cluster, then filters
    to workloads present on the specified node. Returns the workload IDs on the node
    and a mapping of workload_id -> all GPU devices across the cluster for those workloads.
    """
    results = await a_custom_query(
        client=prometheus_client,
        query=f'{GPU_GFX_ACTIVITY_METRIC}{{{CLUSTER_NAME}="{cluster_name}"}}',
    )

    devices_by_workload: dict[str, list[WorkloadGpuDevice]] = defaultdict(list)
    seen: dict[str, set[tuple[str, str]]] = defaultdict(set)
    workloads_on_node: set[str] = set()

    for item in results:
        metric = item.get("metric", {})
        wid = metric.get(WORKLOAD_ID)
        hostname = metric.get(HOSTNAME_METRIC_LABEL, "")
        gpu_id = metric.get(GPU_ID_METRIC_LABEL, "")
        if not wid:
            continue

        if hostname == node_name:
            workloads_on_node.add(wid)

        if (hostname, gpu_id) not in seen[wid]:
            seen[wid].add((hostname, gpu_id))
            devices_by_workload[wid].append(WorkloadGpuDevice(gpu_id=gpu_id, hostname=hostname))

    return {wid: devices_by_workload[wid] for wid in workloads_on_node}


async def get_workloads_metrics_by_node(
    session: AsyncSession,
    cluster_id: UUID,
    cluster_name: str,
    node_name: str,
    prometheus_client: PrometheusConnect,
) -> NodeWorkloadsWithMetrics:
    """
    Returns workloads that have GPU activity on the specified node, enriched with
    GPU device details and VRAM usage across the entire cluster.
    """
    gpu_devices_by_workload = await get_workloads_on_node_with_gpu_devices(node_name, cluster_name, prometheus_client)
    if len(gpu_devices_by_workload) == 0:
        return NodeWorkloadsWithMetrics(data=[])

    workload_uuids = [UUID(wid) for wid in gpu_devices_by_workload.keys()]

    workloads, workload_vram_usage = await asyncio.gather(
        get_workloads_by_ids_in_cluster(session, workload_uuids, cluster_id),
        _get_gpu_memory_utilization_by_workload_id_with_filter(prometheus_client, f'{CLUSTER_NAME}="{cluster_name}"'),
    )

    workload_metrics = []
    for workload in workloads:
        wid_str = str(workload.id)
        devices = gpu_devices_by_workload.get(wid_str, [])
        workload_dict = {
            **workload.__dict__,
            "gpu_count": len(devices),
            "vram": workload_vram_usage.get(wid_str, 0),
            "gpu_devices": devices,
        }
        workload_metrics.append(NodeWorkloadWithMetrics.model_validate(workload_dict))

    return NodeWorkloadsWithMetrics(data=workload_metrics)
