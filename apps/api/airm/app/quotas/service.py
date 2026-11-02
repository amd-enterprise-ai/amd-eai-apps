# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from keycloak import KeycloakAdmin
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ValidationException

from ..clusters.models import Cluster
from ..clusters.service import get_cluster_with_resources
from ..messaging.sender import MessageSender
from ..projects.models import Project
from ..projects.repository import get_projects_in_cluster
from ..utilities.enums import GPUVendor
from .constants import DEFAULT_CATCH_ALL_QUOTA_NAME, QUOTA_FAILURE_REASON_UNSPECIFIED
from .enums import QuotaStatus
from .messaging import ClusterQuotaAllocation, ClusterQuotasFailureMessage, ClusterQuotasStatusMessage
from .models import Quota
from .repository import create_quota as create_quota_in_db
from .repository import update_quota, update_quota_status
from .schemas import QuotaBase, QuotaCreate, QuotaResponse, QuotaUpdate
from .utils import (
    calculate_dynamic_catch_all_quota_allocation,
    does_quota_match_allocation,
    format_quotas_allocation_message,
    have_quota_resources_changed,
    is_within_provisioning_grace,
    quota_failure_message_mismatch,
    quota_failure_message_missing,
    validate_quota_against_available_cluster_resources,
)


async def send_quotas_allocation_to_cluster_queue(
    session: AsyncSession,
    cluster: Cluster,
    gpu_vendor: GPUVendor | None,
    message_sender: MessageSender,
) -> None:
    projects_for_cluster = await get_projects_in_cluster(session, cluster.id)

    quotas_allocations = [
        ClusterQuotaAllocation(
            quota_name=project.name,
            cpu_milli_cores=project.quota.cpu_milli_cores,
            memory_bytes=project.quota.memory_bytes,
            ephemeral_storage_bytes=project.quota.ephemeral_storage_bytes,
            gpu_count=project.quota.gpu_count,
            namespaces=[project.name],
        )
        for project in projects_for_cluster
        if project.quota and project.quota.status not in [QuotaStatus.DELETING, QuotaStatus.DELETED]
    ]

    dynamic_catch_all_quota = await calculate_dynamic_catch_all_quota_allocation(session, cluster)
    quotas_allocations.append(dynamic_catch_all_quota)

    message = format_quotas_allocation_message(quotas_allocations, gpu_vendor)
    await message_sender.enqueue(cluster.id, message)


async def create_project_quota(
    session: AsyncSession,
    project: Project,
    cluster: Cluster,
    quota_data: QuotaBase,
    user: str,
    message_sender: MessageSender,
) -> Quota:
    quota_create = QuotaCreate(**quota_data.model_dump(), cluster_id=cluster.id, project_id=project.id)

    cluster_with_resources = await get_cluster_with_resources(session, cluster)
    validation_errors = validate_quota_against_available_cluster_resources(cluster_with_resources, quota_create)

    if validation_errors:
        raise ValidationException(f"Quota exceeds available cluster resources: {', '.join(validation_errors)}")

    gpu_vendor = cluster_with_resources.gpu_info.vendor if cluster_with_resources.gpu_info else None
    quota = await create_quota_in_db(session, project.id, cluster.id, quota_create, QuotaStatus.PENDING, user)

    await send_quotas_allocation_to_cluster_queue(session, cluster, gpu_vendor, message_sender)
    return quota


async def update_project_quota(
    session: AsyncSession,
    project: Project,
    cluster: Cluster,
    quota_edit: QuotaUpdate,
    user: str,
    message_sender: MessageSender,
) -> QuotaResponse:
    current_quota = project.quota

    resources_changed = have_quota_resources_changed(current_quota, quota_edit)

    # If resources have changed, set status to PENDING and send message to cluster
    # Otherwise, set status directly to READY and skip sending message
    if resources_changed:
        cluster_with_resources = await get_cluster_with_resources(session, cluster)
        validation_errors = validate_quota_against_available_cluster_resources(
            cluster_with_resources, quota_edit, current_quota
        )

        if validation_errors:
            raise ValidationException(f"Quota exceeds available cluster resources: {', '.join(validation_errors)}")

        gpu_vendor = cluster_with_resources.gpu_info.vendor if cluster_with_resources.gpu_info else None
        db_quota = await update_quota(session, current_quota, quota_edit, QuotaStatus.PENDING, None, user)
        await send_quotas_allocation_to_cluster_queue(session, cluster, gpu_vendor, message_sender)
    else:
        # No resource changes, directly set to READY and skip cluster message
        db_quota = await update_quota(session, current_quota, quota_edit, QuotaStatus.READY, None, user)
        logger.info(
            f"No resource changes detected for quota {current_quota.id}. Setting status to READY and skipping cluster message."
        )

    return QuotaResponse.model_validate(db_quota)


async def update_cluster_quotas_from_allocations(
    kc_admin: KeycloakAdmin, session: AsyncSession, cluster: Cluster, message: ClusterQuotasStatusMessage
) -> None:
    from ..projects.service import update_project_status_from_components  # noqa: PLC0415

    projects = await get_projects_in_cluster(session, cluster.id)
    # Only consider quotas that were last updated before the message was received.
    quotas_by_project_name: dict[str, Quota] = {
        project.name: project.quota
        for project in projects
        if project.quota and project.quota.updated_at <= message.updated_at
    }

    quotas_to_delete = []
    for quota_allocation in message.quota_allocations:
        if quota_allocation.quota_name == DEFAULT_CATCH_ALL_QUOTA_NAME:
            continue

        quota = quotas_by_project_name.pop(quota_allocation.quota_name, None)
        if quota is None:
            logger.warning(
                f"Quota with name {quota_allocation.quota_name} not found for cluster {cluster.id}. Skipping quota."
            )
            continue
        if quota.status in [QuotaStatus.DELETING, QuotaStatus.DELETED]:
            continue

        if does_quota_match_allocation(quota, quota_allocation):
            # A quota that is already READY but still carries a reason recovered before reasons
            # were cleared on recovery, so repair it here: without this the matching branch never
            # runs again for it and the stale reason stays in the project's status text forever.
            if quota.status != QuotaStatus.READY or quota.status_reason is not None:
                await update_quota_status(session, quota, QuotaStatus.READY, None, "system", message.updated_at)

                await update_project_status_from_components(kc_admin, session, quota.project)
        elif is_within_provisioning_grace(quota, message.updated_at):
            logger.debug(
                f"Quota {quota.id} still carries its previous allocation in the snapshot but is within "
                "its provisioning grace period; leaving it PENDING."
            )
        else:
            await update_quota_status(
                session,
                quota,
                QuotaStatus.FAILED,
                quota_failure_message_mismatch(quota_allocation),
                "system",
                message.updated_at,
            )

            await update_project_status_from_components(kc_admin, session, quota.project)

    for quota in quotas_by_project_name.values():
        if is_within_provisioning_grace(quota, message.updated_at):
            logger.debug(
                f"Quota {quota.id} is absent from the snapshot but still within its provisioning "
                "grace period; leaving it PENDING."
            )
            continue
        if quota.status not in [QuotaStatus.DELETING, QuotaStatus.DELETED]:
            quota_update = QuotaUpdate(
                cpu_milli_cores=0,
                ephemeral_storage_bytes=0,
                memory_bytes=0,
                gpu_count=0,
            )
            await update_quota(
                session,
                quota,
                quota_update,
                QuotaStatus.FAILED,
                # The reason describes what the snapshot just showed, not what the quota happened
                # to be failing for before: a quota that disappears from the cluster has been
                # removed, whatever it was failing for earlier.
                quota_failure_message_missing(quota),
                "system",
                message.updated_at,
            )

            await update_project_status_from_components(kc_admin, session, quota.project)
            logger.warning("Quota has been removed from the cluster.")
        else:
            quotas_to_delete.append(quota)
    for quota in quotas_to_delete:
        await update_quota_status(session, quota, QuotaStatus.DELETED, "Quota marked as deleted", "system")
        await update_project_status_from_components(kc_admin, session, quota.project)


async def delete_project_quota(
    session: AsyncSession,
    quota: Quota,
    cluster: Cluster,
    gpu_vendor: GPUVendor | None,
    updater: str,
    message_sender: MessageSender,
) -> None:
    await update_quota_status(session, quota, QuotaStatus.DELETING, None, updater)
    await send_quotas_allocation_to_cluster_queue(session, cluster, gpu_vendor, message_sender)


async def update_pending_quotas_to_failed(
    kc_admin: KeycloakAdmin, session: AsyncSession, cluster: Cluster, message: ClusterQuotasFailureMessage
) -> None:
    from ..projects.service import update_project_status_from_components  # noqa: PLC0415

    projects = await get_projects_in_cluster(session, cluster.id)

    for project in projects:
        if (
            not project.quota
            or project.quota.status != QuotaStatus.PENDING.value
            or project.quota.updated_at >= message.updated_at
        ):
            continue

        await update_quota_status(
            session=session,
            quota=project.quota,
            status=QuotaStatus.FAILED,
            # The cluster may report a failure without a reason; a failed quota still needs one.
            status_reason=message.reason or QUOTA_FAILURE_REASON_UNSPECIFIED,
            updater="system",
            updated_at=message.updated_at,
        )
        await update_project_status_from_components(kc_admin, session, project)
        logger.info(f"Quota {project.name} with PENDING status has been marked as FAILED.")
