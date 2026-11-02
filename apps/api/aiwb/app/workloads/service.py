# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Workload service for creation, deletion, and management."""

import asyncio
from collections import Counter
from uuid import UUID

from loguru import logger
from prometheus_api_client import PrometheusConnect
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.collections import PaginationMetadata, SortCondition, SortDirection, paginate_list, sort_list
from api_common.exceptions import NotFoundException

from ..aims import gateway as aims_gateway
from ..aims.enums import AIMServiceStatus
from ..aims.repository import get_aim_service_by_id
from ..aims.service import list_aim_services
from ..config import SUBMITTER_ANNOTATION
from ..dispatch.kube_client import KubernetesClient
from ..metrics.service import get_gpu_utilization_by_workload_in_namespace, get_gpu_vram_by_workload_in_namespace
from ..projects.crds import Namespace
from ..projects.utils import AIM_TO_WORKLOAD_STATUS
from .constants import ACTIVE_WORKLOAD_STATUSES, DISPLAY_NAME_ANNOTATION
from .enums import WorkloadStatus, WorkloadType
from .gateway import delete_workload_resources
from .models import Workload
from .repository import (
    get_existing_dataset_ids,
    get_workload_by_id,
    get_workload_dataset_refs,
    get_workloads,
    update_workload_status,
)
from .schemas import (
    WorkloadDatasetResponse,
    WorkloadMetrics,
    WorkloadMetricsListPaginated,
    WorkloadResourceType,
    WorkloadStatsCounts,
    WorkloadStatusCount,
)
from .utils import get_resource_type


async def resolve_workload_datasets(
    session: AsyncSession,
    workload_id: UUID,
) -> list[WorkloadDatasetResponse]:
    """Resolve a workload's dataset snapshots against datasets that still exist."""
    # K8s-sourced workload objects do not contain the persisted dataset snapshots.
    refs = await get_workload_dataset_refs(session, workload_id)
    available_ids = await get_existing_dataset_ids(session, [ref["id"] for ref in refs])
    return _dataset_responses(refs, available_ids)


async def resolve_workloads_datasets(
    session: AsyncSession,
    workloads: list[Workload],
) -> dict[UUID, list[WorkloadDatasetResponse]]:
    """Resolve dataset snapshots for a workload page in one availability query."""
    refs_by_workload = {workload.id: workload.dataset_refs or [] for workload in workloads}
    dataset_ids = list(dict.fromkeys(ref["id"] for refs in refs_by_workload.values() for ref in refs))
    available_ids = await get_existing_dataset_ids(session, dataset_ids)
    return {workload_id: _dataset_responses(refs, available_ids) for workload_id, refs in refs_by_workload.items()}


def _dataset_responses(
    refs: list[dict[str, str]],
    available_ids: set[str],
) -> list[WorkloadDatasetResponse]:
    return [
        WorkloadDatasetResponse(
            id=ref["id"],
            name=ref["name"],
            available=ref["id"] in available_ids,
        )
        for ref in refs
    ]


async def ensure_workload_or_aim_service_exists(
    session: AsyncSession,
    kube_client: KubernetesClient,
    project: str,
    workload_id: UUID,
) -> None:
    """Guard the logs/metrics endpoints against unknown ids without false negatives.

    ``get_workload_by_id`` only resolves a backing Deployment/Job (via the
    propagated workload-id label) or a legacy DB row. An AIMService that is
    still starting has neither yet, so falling back to the live AIMService CR
    keeps the access/existence guarantee while letting logs/metrics return an
    empty "nothing yet" state instead of a 404 during the startup window.
    """
    workload = await get_workload_by_id(session=session, workload_id=workload_id, namespace=project)
    if workload is not None:
        return
    aim_service = await aims_gateway.get_aim_service_by_id(kube_client, project, workload_id)
    if aim_service is not None:
        return
    raise NotFoundException(f"Workload {workload_id} not found")


async def delete_workload_components(
    namespace: str,
    workload_id: UUID,
    session: AsyncSession,
    workload: Workload | None = None,
) -> None:
    """Delete all Kubernetes components associated with a workload.

    Callers that have already loaded the workload (e.g. for a type guard) can
    pass it in to avoid a second lookup.

    Raises:
        RuntimeError: If Kubernetes resource deletion fails. Database changes are rolled back.
    """
    logger.info(f"Deleting workload {workload_id}")

    if workload is None:
        workload = await get_workload_by_id(session, workload_id)
    if not workload:
        logger.warning(f"Workload {workload_id} not found in database")
        return

    await update_workload_status(session, workload.id, WorkloadStatus.DELETING, workload.updated_by)
    await delete_workload_resources(namespace, str(workload.id))
    await update_workload_status(session, workload.id, WorkloadStatus.DELETED, workload.updated_by)
    logger.info(f"Workload {workload.id} marked as DELETED")


async def _process_aim_services_to_metrics(
    aim_services_k8s: list,
    session: AsyncSession,
    namespace_name: str,
    gpu_counts: dict[str, int],
    vram_usage: dict[str, float],
) -> list[WorkloadMetrics]:
    """Process AIM services from Kubernetes into WorkloadMetrics.

    Args:
        aim_services_k8s: List of AIM services from Kubernetes
        session: Database session for fetching AIM service metadata
        namespace_name: Name of the namespace
        gpu_counts: GPU count by workload ID
        vram_usage: VRAM usage by workload ID

    Returns:
        List of WorkloadMetrics for AIM services
    """
    metrics: list[WorkloadMetrics] = []

    for aim_service in aim_services_k8s:
        aim_service_id = aim_service.id
        if not aim_service_id:
            continue

        try:
            aim_service_uuid = UUID(aim_service_id)
        except (ValueError, TypeError):
            continue

        annotations = aim_service.metadata.annotations or {}
        created_at = aim_service.metadata.creation_timestamp
        created_by = annotations.get(SUBMITTER_ANNOTATION)

        # Fall back to the DB row only when K8s metadata is incomplete; for fine-tuned
        # AIMs (no DB row) the CR carries both fields, so most calls skip the DB hit.
        if created_at is None or created_by is None:
            aim_service_db = await get_aim_service_by_id(session, aim_service_uuid, namespace_name)
            if aim_service_db is not None:
                if created_at is None:
                    created_at = aim_service_db.created_at
                if created_by is None:
                    created_by = aim_service_db.created_by

        status = AIM_TO_WORKLOAD_STATUS.get(aim_service.status.status, WorkloadStatus.UNKNOWN)

        gpu_count = gpu_counts.get(aim_service_id)
        vram = vram_usage.get(aim_service_id)

        # The manifest generators write the human-facing name to the display-name
        # annotation. Before reconciliation that annotation may be absent, so fall
        # back to the resolved model name (set on status once the engine reconciles)
        # and finally to the K8s resource name.
        resolved_model = aim_service.status.resolved_model
        display_name = (
            annotations.get(DISPLAY_NAME_ANNOTATION)
            or (resolved_model.name if resolved_model else None)
            or aim_service.metadata.name
        )

        metrics.append(
            WorkloadMetrics(
                id=aim_service_uuid,
                name=aim_service.metadata.name,
                display_name=display_name,
                type=WorkloadType.INFERENCE,
                status=status,
                resource_type=WorkloadResourceType.AIM_SERVICE,
                gpu_count=gpu_count,
                vram=vram,
                created_at=created_at,
                created_by=created_by,
            )
        )

    return metrics


async def _process_workloads_to_metrics(
    workloads_db: list,
    gpu_counts: dict[str, int],
    vram_usage: dict[str, float],
) -> list[WorkloadMetrics]:
    """Process workloads from database into WorkloadMetrics.

    Args:
        workloads_db: List of workloads from database
        gpu_counts: GPU count by workload ID
        vram_usage: VRAM usage by workload ID

    Returns:
        List of WorkloadMetrics for workloads
    """
    metrics: list[WorkloadMetrics] = []

    for workload in workloads_db:
        workload_id = str(workload.id)
        gpu_count = gpu_counts.get(workload_id)
        vram = vram_usage.get(workload_id)

        try:
            resource_type = get_resource_type(workload.manifest)
        except ValueError:
            resource_type = (
                WorkloadResourceType.JOB
                if workload.type == WorkloadType.FINE_TUNING
                else WorkloadResourceType.DEPLOYMENT
            )
            logger.warning(
                f"Workload {workload_id}: could not parse manifest, falling back to {resource_type} from type"
            )

        metrics.append(
            WorkloadMetrics(
                id=workload.id,
                name=workload.name,
                display_name=workload.display_name,
                type=workload.type,
                status=workload.status,
                resource_type=resource_type,
                gpu_count=gpu_count,
                vram=vram,
                created_at=workload.created_at,
                created_by=workload.created_by,
            )
        )

    return metrics


async def get_workload_metrics_paginated(
    kube_client: KubernetesClient,
    session: AsyncSession,
    namespace: Namespace,
    prometheus_client: PrometheusConnect,
    page: int = 1,
    page_size: int = 10,
    workload_types: list[WorkloadType] | None = None,
    status_filter: list[WorkloadStatus] | None = None,
    sort: list[SortCondition] | None = None,
) -> WorkloadMetricsListPaginated:
    """Get paginated metrics for all resources in a project.

    Combines AIM services and workloads with their metrics.

    Args:
        kube_client: Kubernetes client for AIM service queries
        session: Database session for workload queries
        namespace: Namespace to search in
        prometheus_client: Prometheus client for GPU/VRAM metrics
        page: Page number (1-indexed)
        page_size: Number of items per page
        workload_types: Optional filter by workload type(s)
        status_filter: Optional filter by workload status(es)
        sort: Optional list of sort conditions (field + direction)
    """
    # Convert user's WorkloadStatus filter to corresponding AIMServiceStatus values.
    # None means "no filter requested"; an empty list means the user's filter mapped to
    # zero AIM statuses (e.g. COMPLETE, DELETING — workload-only).
    aim_status_filter: list[AIMServiceStatus] | None
    if status_filter is None:
        aim_status_filter = None
    else:
        aim_status_filter = [aim for aim, ws in AIM_TO_WORKLOAD_STATUS.items() if ws in status_filter]
    workload_status_filter = status_filter if status_filter is not None else ACTIVE_WORKLOAD_STATUSES

    async def _list_aim_services_or_empty() -> list:
        # list_aim_services() treats a falsy status_filter as "no filter" and returns all
        # services, so short-circuit when the user's filter mapped to no AIM statuses.
        if aim_status_filter == []:
            return []
        return await list_aim_services(kube_client, namespace.name, status_filter=aim_status_filter)

    # Fetch all data in parallel
    aim_services_k8s, workloads_db, gpu_counts, vram_usage = await asyncio.gather(
        _list_aim_services_or_empty(),
        get_workloads(
            session, namespace=namespace.name, workload_types=workload_types, status_filter=workload_status_filter
        ),
        get_gpu_utilization_by_workload_in_namespace(namespace, prometheus_client),
        get_gpu_vram_by_workload_in_namespace(namespace, prometheus_client),
    )

    aim_metrics, workload_metrics = await asyncio.gather(
        _process_aim_services_to_metrics(aim_services_k8s, session, namespace.name, gpu_counts, vram_usage),
        _process_workloads_to_metrics(workloads_db, gpu_counts, vram_usage),
    )

    metrics = aim_metrics + workload_metrics

    if sort and len(sort) > 1:
        logger.warning("Multiple sort conditions provided, only the first will be applied")
    sort_by = sort[0].field if sort else None
    sort_order = sort[0].direction if sort else SortDirection.desc
    metrics = sort_list(metrics, sort_by=sort_by, sort_order=sort_order)

    paginated = paginate_list(metrics, page=page, page_size=page_size)

    return WorkloadMetricsListPaginated(
        data=paginated.items,
        pagination=PaginationMetadata(
            page=paginated.page,
            page_size=paginated.page_size,
            total=paginated.total,
        ),
    )


async def get_workload_stats_counts(
    kube_client: KubernetesClient,
    session: AsyncSession,
    namespace: Namespace,
) -> WorkloadStatsCounts:
    """Get statistics counts for all resources in a project.

    Returns aggregated counts of resources (AIM services + workloads) grouped by status.
    This is a lightweight endpoint that only returns counts (no GPU/VRAM metrics).
    """
    # Fetch AIM services and workloads in parallel
    aim_services_k8s, workloads_db = await asyncio.gather(
        list_aim_services(kube_client, namespace.name, status_filter=list(AIM_TO_WORKLOAD_STATUS.keys())),
        get_workloads(session, namespace=namespace.name, status_filter=ACTIVE_WORKLOAD_STATUSES),
    )

    status_counter = Counter[WorkloadStatus]()

    # Count AIM service statuses
    for aim_service in aim_services_k8s:
        if not aim_service.id:
            continue
        status = AIM_TO_WORKLOAD_STATUS.get(aim_service.status.status, WorkloadStatus.UNKNOWN)
        status_counter[status] += 1

    # Count workload statuses (DELETED already filtered at repository)
    for workload in workloads_db:
        status_counter[workload.status] += 1

    # Create status counts list
    status_counts = [
        WorkloadStatusCount(status=status, count=count) for status, count in sorted(status_counter.items())
    ]

    return WorkloadStatsCounts(
        project=namespace.name,
        total=sum(status_counter.values()),
        status_counts=status_counts,
    )
