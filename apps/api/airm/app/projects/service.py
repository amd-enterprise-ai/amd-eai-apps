# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from keycloak import KeycloakAdmin
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ConflictException, NotFoundException, UnhealthyException, ValidationException

from ..clusters.models import Cluster
from ..clusters.schemas import ClusterResponse, ClusterStatus, ClusterWithResources
from ..clusters.service import get_cluster_with_resources
from ..messaging.sender import MessageSender
from ..namespaces.enums import NamespaceStatus
from ..namespaces.models import Namespace
from ..namespaces.repository import (
    get_namespace_by_name_and_cluster,
    get_namespace_by_project_and_cluster,
)
from ..namespaces.service import (
    create_namespace_for_project,
    delete_namespace_in_cluster,
    find_namespace_sharing_storage_prefix,
    send_project_namespace_manifest_update,
)
from ..quotas.enums import QuotaStatus
from ..quotas.models import Quota
from ..quotas.schemas import QuotaResponse
from ..quotas.service import (
    create_project_quota,
    delete_project_quota,
    update_project_quota,
)
from ..secrets.enums import SecretScope
from ..secrets.models import OrganizationScopedSecret
from ..secrets.repository import get_secrets_for_project
from ..secrets.service import recalculate_organization_secret_status
from ..storages.repository import get_storages_for_project
from ..storages.service import recalculate_storage_status
from ..users.repository import get_users_by_ids, get_users_by_keycloak_ids
from ..users.utils import (
    is_keycloak_user_active,
    is_keycloak_user_inactive,
    merge_invited_user_details,
    merge_user_details,
)
from ..utilities.enums import GPUVendor
from ..utilities.keycloak_admin import (
    assign_users_to_group,
    create_group,
    delete_group,
    get_group_members,
    get_users_in_role,
    unassign_users_from_group,
)
from ..utilities.security import (
    Roles,
)
from .constants import MAX_PROJECTS_PER_CLUSTER, PLACEHOLDER_KEYCLOAK_GROUP_ID
from .enums import ProjectStatus
from .models import Project
from .repository import create_project as create_project_in_db
from .repository import (
    delete_project,
    get_active_project_count_per_cluster,
    get_project_by_name,
    get_projects,
    get_projects_in_clusters,
    update_keycloak_group_id,
    update_project_status,
)
from .repository import get_project_by_id as get_project_by_id_from_db
from .repository import get_projects_in_cluster as get_projects_in_cluster_from_db
from .repository import update_project as update_project_in_db
from .schemas import (
    ProjectCreate,
    ProjectEdit,
    Projects,
    ProjectsWithResourceAllocation,
    ProjectWithUsers,
)
from .utils import (
    build_projects_with_allocations,
    ensure_project_safe_to_delete,
    extract_gpu_preemption_config,
    has_gpu_preemption_changed,
    map_to_project_response,
    map_to_project_with_cluster_and_quota,
    resolve_project_status,
)


async def get_submittable_projects(accessible_projects: list[Project]) -> Projects:
    """
    Convert accessible projects to submittable projects schema.
    Projects are now passed in from Keycloak group membership.
    """
    projects_list = []
    for project in accessible_projects:
        projects_list.append(map_to_project_with_cluster_and_quota(project))

    return Projects(data=projects_list)


async def get_projects_in_cluster(session: AsyncSession, cluster: ClusterResponse) -> Projects:
    projects = await get_projects_in_cluster_from_db(session, cluster.id)
    return Projects(data=[map_to_project_with_cluster_and_quota(project) for project in projects])


async def __fetch_cluster_resources(
    session: AsyncSession, unique_clusters: dict[UUID, Cluster]
) -> dict[UUID, ClusterWithResources]:
    """Fetch cluster resources in parallel for the given clusters."""
    cluster_resources_tasks = [get_cluster_with_resources(session, cluster) for cluster in unique_clusters.values()]
    cluster_resources_results = await asyncio.gather(*cluster_resources_tasks)

    return {
        cluster_id: resource_result
        for cluster_id, resource_result in zip(unique_clusters.keys(), cluster_resources_results)
    }


async def get_projects_with_resource_allocation(session: AsyncSession) -> ProjectsWithResourceAllocation:
    """
    Get all projects with resource allocation information.
    """
    projects = await get_projects(session)

    unique_clusters = {project.cluster.id: project.cluster for project in projects}
    clusters_with_resources = await __fetch_cluster_resources(session, unique_clusters)

    return build_projects_with_allocations(projects, clusters_with_resources)


async def get_projects_with_resource_allocation_in_clusters(
    session: AsyncSession, clusters: list[Cluster]
) -> ProjectsWithResourceAllocation:
    """
    Get projects with resource allocations, in the clusters specified.
    """
    unique_clusters = {cluster.id: cluster for cluster in clusters}
    projects = await get_projects_in_clusters(session, list(unique_clusters.keys()))
    clusters_with_resources = await __fetch_cluster_resources(session, unique_clusters)

    return build_projects_with_allocations(projects, clusters_with_resources)


async def get_projects_in_cluster_with_resource_allocation(
    session: AsyncSession, cluster: Cluster
) -> ProjectsWithResourceAllocation:
    """
    Get projects in a specific cluster with resource allocation information.
    """
    projects = await get_projects_in_cluster_from_db(session, cluster.id)
    cluster_with_resources = await get_cluster_with_resources(session, cluster)

    return build_projects_with_allocations(projects, {cluster.id: cluster_with_resources})


async def get_project_with_users(kc_admin: KeycloakAdmin, session: AsyncSession, project: Project) -> ProjectWithUsers:
    """
    Get a project with users but without expensive user count calculations.
    Uses Keycloak group membership for user information.
    """
    group_members, platform_admin_users = await asyncio.gather(
        get_group_members(kc_admin, project.keycloak_group_id),
        get_users_in_role(kc_admin=kc_admin, role=Roles.PLATFORM_ADMINISTRATOR),
    )
    platform_admins = {pa["id"] for pa in platform_admin_users}

    group_member_ids = [member["id"] for member in group_members]
    users_in_project = await get_users_by_keycloak_ids(session, group_member_ids)

    # Separate active and invited users
    active_keycloak_users_by_id = {}
    invited_keycloak_users_by_id = {}

    for user in group_members:
        if is_keycloak_user_active(user):
            active_keycloak_users_by_id[user["id"]] = user
        elif is_keycloak_user_inactive(user):
            invited_keycloak_users_by_id[user["id"]] = user

    active_users_in_project = [
        user for user in users_in_project if str(user.keycloak_user_id) in active_keycloak_users_by_id
    ]
    invited_users_in_project = [
        user for user in users_in_project if str(user.keycloak_user_id) in invited_keycloak_users_by_id
    ]

    return ProjectWithUsers(
        **map_to_project_response(project).model_dump(),
        quota=QuotaResponse.model_validate(project.quota),
        cluster=ClusterResponse.model_validate(project.cluster),
        users=[
            merge_user_details(active_keycloak_users_by_id[str(user.keycloak_user_id)], user, platform_admins)
            for user in active_users_in_project
        ],
        invited_users=[
            merge_invited_user_details(invited_user, platform_admins) for invited_user in invited_users_in_project
        ],
    )


async def create_project(
    kc_admin: KeycloakAdmin,
    session: AsyncSession,
    message_sender: MessageSender,
    cluster: Cluster,
    project: ProjectCreate,
    creator: str,
) -> Project:
    if ClusterResponse.model_validate(cluster).status is not ClusterStatus.HEALTHY:
        raise UnhealthyException("Project cannot be created for an unhealthy cluster.")

    if await get_project_by_name(session, project_name=project.name):
        raise ConflictException(f"Project with name {project.name} already exists.")

    # Subsumed by the prefix check below — an identical name necessarily shares a prefix — and kept
    # for the message, which names the collision the caller can actually see. Removing it would
    # answer "that name is taken" with an explanation about storage prefixes.
    existing_namespace = await get_namespace_by_name_and_cluster(session, cluster.id, project.name)
    if existing_namespace:
        raise ConflictException(f"A namespace '{project.name}' already exists in cluster '{cluster.name}'. ")

    # AIWB derives every object-storage prefix from the slug of the namespace and checks nothing
    # about namespace naming itself, so this call and the slug-stability rule on ProjectCreate.name
    # are together the only thing keeping two projects out of one storage tree.
    colliding_namespace = await find_namespace_sharing_storage_prefix(session, cluster.id, project.name)
    if colliding_namespace:
        raise ConflictException(
            f"A namespace '{colliding_namespace.name}' already exists in cluster '{cluster.name}' and would share "
            f"object storage with '{project.name}'. Choose a name that does not collide with it."
        )

    project_count = await get_active_project_count_per_cluster(session, cluster.id)
    if project_count >= MAX_PROJECTS_PER_CLUSTER - 1:
        raise ValidationException(f"Maximum of {MAX_PROJECTS_PER_CLUSTER - 1} projects per cluster exceeded.")

    project_db = await create_project_in_db(session, project, creator, keycloak_group_id=PLACEHOLDER_KEYCLOAK_GROUP_ID)
    await create_project_quota(session, project_db, cluster, project.quota, creator, message_sender)
    await create_namespace_for_project(session, project_db, cluster.id, creator, message_sender)

    keycloak_group_id = await create_group(kc_admin, project.name)
    await update_keycloak_group_id(session, project_db, keycloak_group_id, creator)
    return project_db


async def update_project(
    session: AsyncSession, message_sender: MessageSender, project: Project, project_edit: ProjectEdit, updater: str
) -> Project:
    if project.status == ProjectStatus.DELETING:
        raise ConflictException("Project is currently marked for deletion")

    old_preemption = extract_gpu_preemption_config(project)
    await update_project_in_db(session, project, project_edit, updater)
    await update_project_quota(session, project, project.cluster, project_edit.quota, updater, message_sender)
    await refresh_project_status_after_edit(session, project, updater)
    if has_gpu_preemption_changed(old_preemption, project_edit.gpu_preemption):
        await send_project_namespace_manifest_update(project, project_edit.gpu_preemption, message_sender)
    return project


async def add_users_to_project_and_keycloak_group(
    kc_admin: KeycloakAdmin, session: AsyncSession, project: Project, user_ids: list[UUID]
) -> None:
    users = await get_users_by_ids(session, user_ids)

    if len(users) != len(user_ids):
        raise NotFoundException("Some users not found.")

    keycloak_user_ids = [user.keycloak_user_id for user in users]
    await assign_users_to_group(kc_admin=kc_admin, user_ids=keycloak_user_ids, group_id=project.keycloak_group_id)


async def remove_user_from_project_and_keycloak_group(
    kc_admin: KeycloakAdmin, session: AsyncSession, project: Project, user_id: UUID
) -> None:
    users = await get_users_by_ids(session=session, user_ids=[user_id])
    keycloak_user_ids = [user.keycloak_user_id for user in users]
    await unassign_users_from_group(kc_admin=kc_admin, user_ids=keycloak_user_ids, group_id=project.keycloak_group_id)


async def get_project_by_id(session: AsyncSession, project_id: UUID) -> Project:
    project = await get_project_by_id_from_db(session, project_id)
    if not project:
        raise NotFoundException(f"Project with ID {project_id} not found")
    return project


async def submit_delete_project(
    session: AsyncSession, project: Project, user: str, gpu_vendor: GPUVendor | None, message_sender: MessageSender
) -> None:
    ensure_project_safe_to_delete(project)
    await delete_project_quota(session, project.quota, project.cluster, gpu_vendor, user, message_sender)
    await delete_namespace_in_cluster(session, project, user, message_sender)
    await update_project_status(session, project, ProjectStatus.DELETING, "Project is being deleted", user)


async def delete_project_with_cleanup(session: AsyncSession, project: Project) -> None:
    """
    Delete a project and recalculate status for affected secrets and storages.
    """
    # Before deleting the project, find all organization-scoped secrets and storages assigned to it
    # so we can recalculate their status after the cascade deletion
    affected_secrets = await get_secrets_for_project(session, project.id, scope=SecretScope.ORGANIZATION)
    affected_storages = await get_storages_for_project(session, project.id)

    # Delete the project (this will cascade-delete OrganizationSecretAssignment and ProjectStorage entries)
    await delete_project(session, project)

    # Recalculate status for each affected secret and storage
    now = datetime.now(UTC)

    for secret in affected_secrets:
        if isinstance(secret, OrganizationScopedSecret):
            await recalculate_organization_secret_status(session, secret, now)

    for storage in affected_storages:
        await recalculate_storage_status(session, storage, now)


async def delete_project_if_components_deleted(
    kc_admin: KeycloakAdmin, session: AsyncSession, project: Project, quota: Quota, namespace: Namespace
) -> bool:
    """Delete project if all components are deleted. Returns True if project was deleted.

    Exception Handling:
        Keycloak deletion failures are logged but do not block database cleanup. This ensures
        eventual consistency - orphaned Keycloak groups can be identified and cleaned separately.
        Database exceptions propagate to router layer for transaction handling.
    """

    if (
        project.status == ProjectStatus.DELETING
        and quota.status == QuotaStatus.DELETED
        and namespace.status == NamespaceStatus.DELETED
    ):
        # External service cleanup - not covered by database transactions
        # If Keycloak deletion fails, we proceed with database cleanup to maintain consistency
        try:
            await delete_group(kc_admin, project.keycloak_group_id)
        except Exception as e:
            # Log the error but proceed with database cleanup
            # Orphaned Keycloak groups can be cleaned up via separate reconciliation process
            logger.warning(f"Failed to delete Keycloak group {project.keycloak_group_id} for project {project.id}: {e}")

        await delete_project_with_cleanup(session, project)
        return True
    return False


async def refresh_project_status_after_edit(session: AsyncSession, project: Project, updater: str) -> None:
    """Bring project status back in line with its components after the project was edited.

    Without this a project failed by its quota keeps both the FAILED status and the failure text
    built from the old quota reason, even though the re-requested quota is PENDING and carries no
    reason: the cluster-driven path is what normally recomputes status, and an edit never reaches
    it. The deletion-aware variant is deliberately not reused here — an edit is not a deletion, and
    it needs a Keycloak client this path has no reason to hold.

    The status is derived, but the edit that caused it was not: `updater` is the human who made it,
    and stamping "system" here the way the cluster-driven path does would overwrite the audit
    attribution the edit just recorded.

    A project with no namespace is left untouched rather than failed; an edit should not be the
    thing that condemns a project whose namespace has not been recorded yet. This diverges on
    purpose from update_project_status_from_components, which fails the project in that case: the
    cluster-driven path is reacting to evidence about the cluster, an edit is not. Unreachable
    today, since every project gets a namespace at creation.
    """
    namespace = await get_namespace_by_project_and_cluster(session, project.id, project.cluster_id)
    if not namespace:
        return

    project_status, status_reason = resolve_project_status(namespace, project.quota, project)
    await update_project_status(session, project, project_status, status_reason, updater)


async def update_project_status_from_components(
    kc_admin: KeycloakAdmin, session: AsyncSession, project: Project
) -> None:
    """Update project status based on component (namespace and quota) states.

    Exception Handling:
        Database exceptions propagate to router layer for transaction handling.
        Keycloak failures are handled by delete_project_if_components_deleted with compensation logic.
    """

    namespace = await get_namespace_by_project_and_cluster(session, project.id, project.cluster_id)

    if not namespace:
        await update_project_status(session, project, ProjectStatus.FAILED, "Namespace not found", "system")
        return

    await session.refresh(project, ["quota"])

    if not project.quota:
        await update_project_status(session, project, ProjectStatus.FAILED, "Quota not found", "system")
        return

    deleted = await delete_project_if_components_deleted(kc_admin, session, project, project.quota, namespace)
    if deleted:
        return

    project_status, status_reason = resolve_project_status(namespace, project.quota, project)

    await update_project_status(session, project, project_status, status_reason, "system")
