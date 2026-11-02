# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from api_common.exceptions import ConflictException

from .models import Dataset, DatasetType


async def insert_dataset(
    session: AsyncSession,
    name: str,
    creator: str,
    description: str | None,
    namespace: str,
    type: DatasetType,
    path: str,
    id: UUID = None,
) -> Dataset:
    """
    Insert a new dataset record into the database.

    Raises:
        ConflictException: If a dataset with the same path or name already exists in the namespace
    """
    dataset = Dataset(
        id=id,
        name=name,
        created_by=creator,
        updated_by=creator,
        path=path,
        description=description or "",
        namespace=namespace,
        type=type,
    )
    session.add(dataset)
    try:
        await session.flush()
        await session.refresh(dataset)
        return dataset
    except IntegrityError as e:
        error_message = str(e)
        if "datasets_path_key" in error_message:
            raise ConflictException(
                message=f"A dataset with path {path} already exists",
            )
        elif "datasets_name_namespace_key" in error_message:
            raise ConflictException(
                message=f"A dataset with name '{name}' already exists",
            )
        raise e


async def select_dataset(
    session: AsyncSession,
    dataset_id: UUID,
    namespace: str,
) -> Dataset | None:
    """
    Retrieve a dataset by ID within a specific namespace.

    Returns:
        Dataset object if found, None otherwise
    """
    query = select(Dataset).where(Dataset.id == dataset_id, Dataset.namespace == namespace)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def list_datasets(
    session: AsyncSession,
    namespace: str,
    selected_datasets_ids: list[UUID] | None = None,
    type: DatasetType | None = None,
    name: str | None = None,
) -> list[Dataset]:
    """
    List datasets in a project with optional filtering.

    Returns:
        List of Dataset objects matching the criteria
    """
    query = select(Dataset).where(Dataset.namespace == namespace)
    if selected_datasets_ids:
        query = query.where(Dataset.id.in_(selected_datasets_ids))
    if type:
        query = query.where(Dataset.type == type)
    if name:
        query = query.where(Dataset.name == name)
    query = query.order_by(Dataset.created_at.desc())
    result = await session.execute(query)
    return result.scalars().all()


async def get_all_datasets(session: AsyncSession) -> list[Dataset]:
    """
    Get every dataset across all namespaces.

    Unscoped on purpose: callers auditing datasets against the namespaces that still exist have to
    see the ones whose namespace does not, which a per-namespace query cannot reach.
    """
    result = await session.execute(select(Dataset).order_by(Dataset.namespace, Dataset.created_at))
    return list(result.scalars().all())


async def delete_dataset_by_id(session: AsyncSession, dataset_id: UUID, namespace: str) -> bool:
    """
    Delete a single dataset by ID within a namespace.

    Note:
        Only deletes from database - S3 cleanup must be handled separately by the service layer.
    """
    dataset = await select_dataset(session, dataset_id, namespace)

    if not dataset:
        return False

    await session.delete(dataset)
    await session.flush()
    return True
