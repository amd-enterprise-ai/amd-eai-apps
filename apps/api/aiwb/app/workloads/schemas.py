# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, Field, computed_field, model_validator

from api_common.collections import BasePaginationList, PaginationConditions, SortDirection
from api_common.schemas import BaseEntityPublic, BaseModel

from ..aims.constants import AIM_SERVICE_RESOURCE
from ..logs.schemas import LogLevel, LogType
from ..workspaces.enums import WORKSPACE_URL_SUFFIX_MAPPING
from .constants import DEPLOYMENT_RESOURCE, DESCRIPTION_ANNOTATION, JOB_RESOURCE
from .enums import WorkloadStatus, WorkloadType
from .utils import get_workload_host_from_HTTPRoute_manifest, get_workload_internal_url


class DisplayNameQuery(BaseModel):
    display_name: str | None = Field(
        default=None,
        description="User-friendly display name for the workload",
        examples=["Llama 3 Production"],
    )


class WorkloadListQuery(PaginationConditions):
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    # Bound page_size so a single client cannot fetch arbitrarily large pages.
    page_size: int = Field(default=10, ge=1, le=100, description="Number of items per page")
    workload_type: list[WorkloadType] = Field(default_factory=list, description="Filter by workload type(s)")
    status_filter: list[WorkloadStatus] = Field(default_factory=list, description="Filter by workload status(es)")


class WorkloadStreamQuery(BaseModel):
    start_time: datetime | None = Field(default=None, description="Start time for streaming (ISO format)")
    level: LogLevel | None = Field(default=None, description="Filter logs at this level and above")
    log_type: LogType = Field(default=LogType.WORKLOAD, description="Type of logs: 'workload' or 'event'")
    delay: int = Field(
        default=1,
        ge=1,
        le=30,
        description="Delay between polls (1-30 seconds)",
        examples=[5],
    )


class WorkloadDatasetResponse(BaseModel):
    id: UUID
    name: str
    available: bool


class WorkloadResponse(BaseEntityPublic):
    """Base workload schema."""

    name: str = Field(..., examples=["llama-3-8b-prod"])
    display_name: str = Field(..., examples=["Llama 3 Production"])
    type: WorkloadType
    annotations: dict[str, str] = Field(
        default_factory=dict,
        description="Annotations from the workload's Kubernetes resource.",
    )
    status: WorkloadStatus
    namespace: str = Field(..., examples=["acme-summarizer"])
    chart_id: UUID | None = None
    dataset_id: UUID | None = Field(
        default=None,
        deprecated="Use datasets instead; a fine-tuning job can use multiple datasets.",
        description=(
            "First dataset used by the job, or null if that dataset was deleted. "
            "Use datasets for the deletion-proof record."
        ),
    )
    datasets: list[WorkloadDatasetResponse] = Field(
        default_factory=list,
        description="Datasets used by the job, including snapshots of datasets that were later deleted.",
    )
    manifest: str = Field(default="", exclude=True)
    chart_name: str | None = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def extract_chart_name(cls, data: Any) -> Any:
        if hasattr(data, "chart") and data.chart:
            data.__dict__["chart_name"] = data.chart.name
        return data

    @computed_field
    def description(self) -> str | None:
        """Human-readable description supplied at creation, sourced from the workload's annotation."""
        return self.annotations.get(DESCRIPTION_ANNOTATION) or None

    @computed_field
    def endpoints(self) -> dict[str, str]:
        # Skip computation for deleted workloads
        if self.status not in [WorkloadStatus.PENDING, WorkloadStatus.RUNNING]:
            return {}

        internal = get_workload_internal_url(self.name, self.namespace)
        external = get_workload_host_from_HTTPRoute_manifest(manifest=self.manifest)

        suffix = WORKSPACE_URL_SUFFIX_MAPPING.get(self.chart_name or "", "")
        if suffix:
            internal += suffix
            if external:
                external += suffix

        endpoints = {"internal": internal}
        if external:
            endpoints["external"] = external
        return endpoints


class WorkloadsList(BasePaginationList):
    """Paginated list of workloads."""

    data: list[WorkloadResponse]


class WorkloadMetricsQuery(PaginationConditions):
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    # Bound page_size so a single client cannot fetch arbitrarily large pages.
    page_size: int = Field(default=10, ge=1, le=100, description="Number of items per page")
    workload_type: list[WorkloadType] | None = Field(default=None, description="Filter by workload type(s)")
    status_filter: list[WorkloadStatus] | None = Field(default=None, description="Filter by workload status(es)")
    sort_by: str | None = Field(
        default=None,
        description="Field to sort by (e.g., 'createdAt', 'name', 'status')",
        examples=["createdAt", "name", "status"],
    )
    sort_order: SortDirection = Field(default=SortDirection.desc, description="Sort order: 'asc' or 'desc'")


class WorkloadResourceType(StrEnum):
    """Resource types for workloads and AIM services."""

    DEPLOYMENT = DEPLOYMENT_RESOURCE
    JOB = JOB_RESOURCE
    AIM_SERVICE = AIM_SERVICE_RESOURCE


class WorkloadMetrics(BaseModel):
    """Metrics for a single resource (AIM service or workload)."""

    id: UUID = Field(
        ...,
        description="The unique ID of the resource",
        examples=["7f3b6c8e-2a1d-4b9f-9c12-1a2b3c4d5e6f"],
    )
    name: str = Field(..., description="The name of the resource", examples=["llama-3-8b-prod"])
    display_name: str | None = Field(
        None,
        description="The display name of the resource",
        examples=["Llama 3 Production"],
    )
    type: WorkloadType = Field(..., description="The type of the resource (INFERENCE, FINE_TUNING, WORKSPACE)")
    status: WorkloadStatus = Field(..., description="The current status of the resource")
    resource_type: WorkloadResourceType = Field(..., description="The resource type (Deployment, Job, AIMService)")
    gpu_count: int | None = Field(
        None,
        description="The number of GPUs allocated to the resource",
        examples=[8],
    )
    vram: float | None = Field(
        None,
        description="The amount of VRAM used by the resource in bytes",
        examples=[68719476736.0],
    )
    created_at: AwareDatetime | None = Field(None, description="The timestamp of when the resource was created")
    created_by: str | None = Field(
        None,
        description="The user who created the resource",
        examples=["user@example.com"],
    )


class WorkloadMetricsListPaginated(BasePaginationList):
    """Response model for paginated workload metrics.

    Contains metrics for resources in a project as the nested pagination
    envelope (``data`` plus a sibling ``pagination`` block).
    """

    data: list[WorkloadMetrics] = Field(..., description="List of resources with their metrics")


class WorkloadStatusCount(BaseModel):
    """Count of resources for a specific status."""

    status: WorkloadStatus = Field(..., description="The resource status")
    count: int = Field(..., description="The number of resources in this status", examples=[3])


class WorkloadStatsCounts(BaseModel):
    """Response model for workload statistics counts.

    Contains aggregated counts of resources (AIM services + workloads) grouped by status.
    This is a lightweight response without computing metrics.
    """

    project: str = Field(..., description="The project name", examples=["acme-summarizer"])
    total: int = Field(
        ...,
        description="The total number of resources (AIM services + workloads)",
        examples=[12],
    )
    status_counts: list[WorkloadStatusCount] = Field(..., description="The total count of resources grouped by status")
