# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.models import set_updated_fields

from .enums import NamespaceStatus
from .models import Namespace


async def create_namespace(session: AsyncSession, namespace: Namespace) -> Namespace:
    session.add(namespace)
    await session.flush()
    return namespace


async def update_namespace_status(
    session: AsyncSession,
    namespace: Namespace,
    status: NamespaceStatus,
    status_reason: str | None,
    updater: str,
    updated_at: datetime | None = None,
) -> Namespace:
    namespace.status = status
    namespace.status_reason = status_reason
    set_updated_fields(namespace, updater, updated_at)
    await session.flush()
    return namespace


async def get_namespace_by_project_and_cluster(
    session: AsyncSession, project_id: UUID, cluster_id: UUID
) -> Namespace | None:
    result = await session.execute(
        select(Namespace).where(Namespace.project_id == project_id, Namespace.cluster_id == cluster_id)
    )
    return result.scalars().first()


async def delete_namespace(session: AsyncSession, namespace: Namespace) -> None:
    await session.delete(namespace)
    await session.flush()


async def get_namespaces_in_cluster(session: AsyncSession, cluster_id: UUID) -> list[Namespace]:
    result = await session.execute(select(Namespace).where(Namespace.cluster_id == cluster_id))
    return list(result.scalars().all())


async def get_namespace_by_name_and_cluster(
    session: AsyncSession, cluster_id: UUID, namespace_name: str
) -> Namespace | None:
    result = await session.execute(
        select(Namespace).where(Namespace.cluster_id == cluster_id, Namespace.name == namespace_name)
    )
    return result.scalars().first()
