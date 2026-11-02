# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ConflictException
from api_common.models import set_updated_fields

from .enums import QuotaStatus
from .models import Quota
from .schemas import QuotaCreate, QuotaUpdate


async def get_quotas_for_cluster(session: AsyncSession, cluster_id: UUID) -> list[Quota]:
    return await get_quotas_for_clusters(session, [cluster_id])


async def get_quotas_for_clusters(session: AsyncSession, cluster_ids: list[UUID]) -> list[Quota]:
    result = await session.execute(select(Quota).where(Quota.cluster_id.in_(cluster_ids)))
    return result.scalars().all()


async def get_quotas(session: AsyncSession) -> list[Quota]:
    result = await session.execute(select(Quota))
    return result.scalars().all()


async def create_quota(
    session: AsyncSession, project_id: UUID, cluster_id: UUID, quota: QuotaCreate, status: str, creator: str
) -> Quota:
    quota = Quota(
        cluster_id=cluster_id,
        project_id=project_id,
        cpu_milli_cores=quota.cpu_milli_cores,
        memory_bytes=quota.memory_bytes,
        ephemeral_storage_bytes=quota.ephemeral_storage_bytes,
        gpu_count=quota.gpu_count,
        status=status,
        created_by=creator,
        updated_by=creator,
    )
    session.add(quota)
    try:
        await session.flush()
        return quota
    except IntegrityError as e:
        error_message = str(e)
        if "quotas_project_id_key" in error_message:
            raise ConflictException("A quota already exists for this project")
        raise e


async def update_quota_status(
    session: AsyncSession,
    quota: Quota,
    status: QuotaStatus,
    status_reason: str | None,
    updater: str,
    updated_at: datetime | None = None,
) -> Quota:
    # status_reason is authoritative: None clears it. A quota that recovers must stop
    # reporting the failure it recovered from, since project status text is built from
    # whatever reason is stored regardless of the status it accompanies.
    quota.status = status
    quota.status_reason = status_reason
    set_updated_fields(quota, updater, updated_at)
    await session.flush()
    return quota


async def update_quota(
    session: AsyncSession,
    quota: Quota,
    edits: QuotaUpdate,
    status: QuotaStatus,
    status_reason: str | None,
    updater: str,
    updated_at: datetime | None = None,
) -> Quota:
    for key, value in edits.model_dump().items():
        setattr(quota, key, value)
    return await update_quota_status(session, quota, status, status_reason, updater, updated_at)
