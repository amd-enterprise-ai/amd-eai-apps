# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import UTC, datetime, timedelta

from pydantic import AwareDatetime, Field, model_validator

from api_common.collections import BasePaginationList
from api_common.schemas import BaseModel

from ..projects.schemas import ProjectResponse
from ..workloads.schemas import WorkloadResponse
from .constants import MAX_DAYS_FOR_TIMESERIES


class MetricsTimeRange(BaseModel):
    """Validated start/end time range for metrics queries."""

    start: AwareDatetime = Field(description="Start time. ISO 8601 with timezone (e.g. UTC: ...Z or +00:00).")
    end: AwareDatetime = Field(description="End time. ISO 8601 with timezone (e.g. UTC: ...Z or +00:00).")
    step: int | None = Field(
        None,
        ge=1,
        description="Interval in seconds between returned datapoints. If not provided, a suitable interval is determined automatically from the time range.",
    )

    @model_validator(mode="after")
    def validate_range(self) -> "MetricsTimeRange":
        # Prometheus works on second precision — truncate sub-second component
        self.start = self.start.replace(microsecond=0)
        self.end = self.end.replace(microsecond=0)

        now = datetime.now(UTC)
        if self.start >= self.end:
            raise ValueError("start time must be before end time")
        if self.start < now - timedelta(days=MAX_DAYS_FOR_TIMESERIES):
            raise ValueError(f"start time must be within the last {MAX_DAYS_FOR_TIMESERIES} days")
        if self.end > now + timedelta(minutes=1):
            raise ValueError("end time must not be in the future")
        return self


class DatapointMetadataBase(BaseModel):
    label: str = Field(
        description="The label for the series that the datapoint belongs to.", min_length=1, max_length=64
    )


class ProjectDatapointMetadata(DatapointMetadataBase):
    project: ProjectResponse = Field(description="The project the datapoint corresponds to")


class DeviceDatapointMetadata(DatapointMetadataBase):
    gpu_uuid: str = Field(description="The unique identifier of the GPU device.")
    hostname: str = Field(description="The hostname of the node the GPU is on.")


class Datapoint(BaseModel):
    value: float | None = Field(None, description="The value of the datapoint.")
    timestamp: AwareDatetime = Field(description="The timestamp of the datapoint.")


class DatapointsWithMetadata(BaseModel):
    metadata: DatapointMetadataBase | ProjectDatapointMetadata | DeviceDatapointMetadata = Field(
        description="Metadata for the datapoints."
    )
    values: list[Datapoint] = Field(description="The list of datapoints corresponding to the metadata.")


class TimeseriesRange(BaseModel):
    start: AwareDatetime = Field(description="The start of the timeseries range.")
    end: AwareDatetime = Field(description="The end of the timeseries range.")
    interval_seconds: int = Field(description="The interval in seconds for the timeseries data.")
    timestamps: list[AwareDatetime] = Field(description="The keys for the datapoints in the timeseries.")


class MetricsTimeseries(BaseModel):
    data: list[DatapointsWithMetadata] = Field(description="The metrics timeseries data points.")
    range: TimeseriesRange = Field(description="The range of the timeseries.")


class UtilizationByProject(BaseModel):
    project: ProjectResponse = Field(description="The project the utilization corresponds to.")
    allocated_gpus_count: int = Field(description="The number of GPUs allocated to the project.")
    utilized_gpus_count: int = Field(description="The number of GPUs currently being utilized by the project.")
    running_workloads_count: int = Field(description="The number of running workloads for the project.")
    pending_workloads_count: int = Field(description="The number of pending workloads for the project.")


class CurrentUtilization(BaseModel):
    timestamp: AwareDatetime = Field(datetime.now(tz=UTC), description="The timestamp of the current utilization data.")
    utilization_by_project: list[UtilizationByProject] = Field(
        description="The GPU utilization by project.",
    )
    total_utilized_gpus_count: int = Field(description="The number of GPUs currently in use.")
    total_running_workloads_count: int = Field(description="The number of running workloads.")
    total_pending_workloads_count: int = Field(description="The number of pending workloads.")


class WorkloadWithMetrics(WorkloadResponse):
    gpu_count: int = Field(description="The number of GPUs allocated to the workload", default=None)
    vram: float = Field(description="The amount of VRAM used by the workload", default=None)
    run_time: int = Field(description="The total run time of the workload in seconds", default=None)
    created_at: AwareDatetime | None = Field(description="The timestamp of when the workload was created", default=None)
    created_by: str = Field(description="The user who created the workload", default=None)


class WorkloadsWithMetrics(BasePaginationList):
    data: list[WorkloadWithMetrics]


class WorkloadGpuDevice(BaseModel):
    """A single GPU device assignment for a workload."""

    gpu_id: str = Field(description="The GPU device index identifier (e.g. '0', '1').")
    hostname: str = Field(description="The hostname of the node the GPU device is on.")


class NodeWorkloadWithMetrics(WorkloadResponse):
    """Workload with metrics and GPU device details, used for node-scoped workload listings."""

    gpu_count: int = Field(description="The number of GPU devices the workload is using.", default=0)
    vram: float = Field(description="The amount of VRAM used by the workload in megabytes.", default=0)
    gpu_devices: list[WorkloadGpuDevice] = Field(
        description="All GPU devices the workload runs on across the cluster.", default_factory=list
    )
    created_at: AwareDatetime | None = Field(
        description="The timestamp of when the workload was created.", default=None
    )
    created_by: str = Field(description="The user who created the workload.", default=None)


class NodeWorkloadsWithMetrics(BaseModel):
    """Response for workloads running on a specific node."""

    data: list[NodeWorkloadWithMetrics] = Field(description="Workloads with GPU activity on the node.")


class DateRange(BaseModel):
    start: AwareDatetime = Field(..., description="Start of the requested time range.")
    end: AwareDatetime = Field(..., description="End of the requested time range.")


class MetricsScalar(BaseModel):
    """
    Represents a scalar metric value at a single point in time.
    Used for point-in-time metrics.
    """

    data: float = Field(..., description="The scalar metric value.")


class MetricsScalarWithRange(MetricsScalar):
    """
    Represents a scalar metric value aggregated over a time range.
    Used for metrics computed over a specified range.
    """

    range: DateRange = Field(..., description="The range for which the scalar metric was computed.")


class DeviceMetricTimeseries(BaseModel):
    series_label: str = Field(description="Label identifying this metric series.")
    values: list[Datapoint] = Field(description="Timeseries datapoints.", default_factory=list)


class GpuDeviceWithSingleMetric(BaseModel):
    """Per-GPU device with a single timeseries metric (for dedicated metric endpoints)."""

    gpu_uuid: str = Field(..., description="The unique identifier of the GPU device.")
    gpu_id: str = Field(..., description="The GPU device index identifier.")
    hostname: str = Field(..., description="The hostname of the node the GPU is on.")
    metric: DeviceMetricTimeseries = Field(description="The timeseries for this metric.")


class GpuDeviceSingleMetricResponse(BaseModel):
    """Response for a single GPU device metric (VRAM utilization, GPU utilization, or power usage)."""

    gpu_devices: list[GpuDeviceWithSingleMetric] = Field(
        description="Per-GPU device timeseries for this metric.", default_factory=list
    )
    range: MetricsTimeRange = Field(..., description="The requested time range.")


class NodeGpuDevice(BaseModel):
    """Snapshot of a single GPU device on a cluster node with its latest metric values."""

    gpu_uuid: str = Field(..., description="The unique identifier of the GPU device.")
    gpu_id: str = Field(..., description="The GPU device index identifier.")
    product_name: str | None = Field(None, description="The GPU product name (e.g. Instinct MI300).")
    temperature: float | None = Field(None, description="Junction temperature in Celsius.")
    power_consumption: float | None = Field(None, description="Power draw in Watts.")
    vram_utilization: float | None = Field(None, description="VRAM utilization percentage (0-100).")
    last_updated: AwareDatetime | None = Field(None, description="Timestamp of the most recent metric datapoint.")


class NodeGpuDevicesResponse(BaseModel):
    """Response containing the latest GPU device metrics for a cluster node."""

    gpu_devices: list[NodeGpuDevice] = Field(description="Per-GPU device snapshot metrics.", default_factory=list)
