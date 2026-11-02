# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..charts.models import Chart
from ..datasets.models import Dataset
from .enums import WorkloadStatus, WorkloadType
from .gateway import get_workload_from_k8s
from .models import Workload
from .utils import generate_display_name, generate_workload_name


async def create_workload(
    session: AsyncSession,
    display_name: str,
    workload_type: WorkloadType,
    chart_id: UUID,
    namespace: str,
    submitter: str,
    status: WorkloadStatus,
    dataset_id: UUID | None = None,
    dataset_refs: list[dict[str, str]] | None = None,
) -> Workload:
    """
    Create a new workload in the database.

    Args:
        session: Database session
        display_name: Human-readable display name (empty string to auto-generate)
        workload_type: Type of workload (WORKSPACE, INFERENCE, TRAINING, etc.)
        chart_id: ID of the chart used to create this workload
        namespace: Kubernetes namespace where workload is deployed
        submitter: Email of the user creating the workload
        status: Initial status of the workload
        dataset_id: Optional ID of the dataset associated with this workload
        dataset_refs: Deletion-proof dataset identifiers and names

    Returns:
        Created Workload instance with auto-generated name
    """
    workload = Workload(
        name="",  # Will be generated after flush
        display_name=display_name,
        type=workload_type,
        status=status,
        chart_id=chart_id,
        namespace=namespace,
        created_by=submitter,
        updated_by=submitter,
        dataset_id=dataset_id,
        dataset_refs=dataset_refs or [],
    )
    session.add(workload)
    await session.flush()

    # Auto-generate name based on workload ID
    workload.name = generate_workload_name(workload)
    if not workload.display_name:
        workload.display_name = generate_display_name(workload)

    return workload


async def get_workload_dataset_refs(
    session: AsyncSession,
    workload_id: UUID,
) -> list[dict[str, str]]:
    """Get the persisted dataset snapshots for a workload."""
    return await session.scalar(select(Workload.dataset_refs).where(Workload.id == workload_id)) or []


async def get_existing_dataset_ids(
    session: AsyncSession,
    dataset_ids: list[str],
) -> set[str]:
    """Get the IDs that still identify existing datasets."""
    if not dataset_ids:
        return set()
    result = await session.scalars(select(Dataset.id).where(Dataset.id.in_(dataset_ids)))
    return {str(dataset_id) for dataset_id in result}


async def get_workload_by_id(
    session: AsyncSession,
    workload_id: UUID,
    namespace: str | None = None,
) -> Workload | None:
    """Get a workload by ID, checking Kubernetes first then falling back to the database.

    When a namespace is provided, the live K8s cluster is queried first (Deployments,
    then Jobs). This is the preferred path as the codebase moves away from storing
    workload state in the database.

    Falls back to the database when:
    - No namespace is supplied
    - The workload is not found in the cluster (e.g. it was deleted from K8s but the
      DB record still exists, or it pre-dates the K8s-first approach)
    """
    if namespace is not None:
        workload = await get_workload_from_k8s(workload_id, namespace)
        if workload is not None:
            if workload.chart_id:
                result = await session.execute(select(Chart).where(Chart.id == workload.chart_id))
                workload.chart = result.unique().scalar_one_or_none()
            return workload

    query = select(Workload).where(Workload.id == workload_id)

    if namespace is not None:
        query = query.where(Workload.namespace == namespace)

    result = await session.execute(query)
    return result.scalars().first()


async def get_workloads(
    session: AsyncSession,
    namespace: str | None = None,
    workload_types: list[WorkloadType] | None = None,
    status_filter: list[WorkloadStatus] | None = None,
    chart_name: str | None = None,
) -> list[Workload]:
    """
    Get all workloads, optionally filtered by namespace, type, status, and chart.

    Args:
        session: Database session
        namespace: Filter by namespace
        workload_types: Filter by workload type(s)
        status_filter: Include only these statuses
        chart_name: Filter by chart name

    Returns:
        List of matching workloads
    """

    query = select(Workload)
    if namespace is not None:
        query = query.where(Workload.namespace == namespace)
    if workload_types:
        query = query.where(Workload.type.in_(workload_types))
    if status_filter:
        query = query.where(Workload.status.in_(status_filter))
    if chart_name:
        query = query.join(Chart).where(Chart.name == chart_name)
    # Stable order so pagination (in-memory today, SQL LIMIT/OFFSET tomorrow
    # alike) is deterministic; without it the same row can appear
    # on multiple pages or be skipped as a client navigates.
    query = query.order_by(Workload.created_at.desc(), Workload.id.desc())

    result = await session.execute(query)
    return result.unique().scalars().all()


async def update_workload_status(
    session: AsyncSession, workload_id: UUID, status: WorkloadStatus, updated_by: str
) -> Workload | None:
    """
    Update the status of a workload.

    Args:
        session: Database session
        workload_id: ID of the workload to update
        status: New status
        updated_by: Email of user updating the status

    Returns:
        Updated workload or None if not found
    """
    workload = await get_workload_by_id(session, workload_id)
    if workload:
        workload.status = status
        workload.updated_by = updated_by
        await session.flush()
    return workload


async def delete_workload(session: AsyncSession, workload_id: UUID) -> bool:
    """
    Delete a workload from the database.

    Args:
        session: Database session
        workload_id: ID of the workload to delete

    Returns:
        True if deleted, False if not found
    """
    result = await session.execute(select(Workload).where(Workload.id == workload_id))
    workload = result.unique().scalar_one_or_none()
    if workload:
        await session.delete(workload)
        return True
    return False
