# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from uuid import UUID

from keycloak import KeycloakAdmin
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import NotFoundException
from api_common.slugs import slugify

from ..clusters.models import Cluster
from ..messaging.sender import MessageSender
from ..projects.models import Project
from ..projects.repository import get_project_by_id
from ..projects.schemas import GpuPreemptionConfig
from ..projects.utils import extract_gpu_preemption_config, has_gpu_preemption_changed
from .messaging import (
    NamespaceDeletedMessage,
    NamespaceStatus,
    ProjectNamespaceCreateMessage,
    ProjectNamespaceDeleteMessage,
    ProjectNamespaceStatusMessage,
    ProjectNamespaceUpdateMessage,
    UnmanagedNamespaceMessage,
)
from .models import Namespace
from .repository import (
    create_namespace,
    delete_namespace,
    get_namespace_by_name_and_cluster,
    get_namespace_by_project_and_cluster,
    get_namespaces_in_cluster,
    update_namespace_status,
)
from .utils import _build_namespace_manifest, namespace_failure_message_preemption_mismatch


async def find_namespace_sharing_storage_prefix(session: AsyncSession, cluster_id: UUID, name: str) -> Namespace | None:
    """The namespace in the cluster, if any, whose object-storage prefix `name` would also address.

    Object storage is keyed by the slug of the namespace name, and slugging is lossy, so a name
    is not confined to its own prefix just because it is unique. New names are required to be
    slug-stable, which keeps them from colliding with each other — but rows predating that rule
    are not, and a slug-stable new name can still land on a legacy one (`data-science` on an
    existing `data--science`). This is what catches that case.

    Slugging cannot be expressed in SQL, so the comparison happens over the cluster's namespaces
    in Python, and no stored slug column exists for a unique index to back the check the way
    `ix_namespaces_name_cluster` backs the raw-name check. The read therefore sits outside the
    write with nothing to catch a loser — but not with another project create: two accepted names
    are both slug-stable, and slug-stable names cannot slug alike. The only writer that can insert
    a colliding row is `record_unmanaged_namespace`, which records namespaces the cluster agent
    reports and is deliberately not validated, because a name already live in Kubernetes cannot be
    refused. The namespace it records carries no `project-id` label on the cluster, and that label
    is the single thing AIWB admits a caller on, so a pair created through that window is inert
    rather than a cross-tenant read.

    Namespaces are matched whatever their status, including ones a deleted project left behind.
    Deleting a project does not delete the objects written under its prefix, so handing the prefix
    to a differently-named project would hand it those objects — which is the same exposure this
    is here to prevent.
    """
    namespaces = await get_namespaces_in_cluster(session, cluster_id)
    slug = slugify(name)
    return next((namespace for namespace in namespaces if slugify(namespace.name) == slug), None)


async def create_namespace_for_project(
    session: AsyncSession, project: Project, cluster_id: UUID, user: str, message_sender: MessageSender
) -> Namespace:
    namespace = Namespace(
        project_id=project.id,
        name=project.name,
        cluster_id=cluster_id,
        status=NamespaceStatus.PENDING,
        status_reason="creating",
        created_by=user,
        updated_by=user,
    )
    await create_namespace(session, namespace)

    gpu_preemption = extract_gpu_preemption_config(project)
    manifest = _build_namespace_manifest(namespace.name, namespace.project_id, gpu_preemption)
    message = ProjectNamespaceCreateMessage(message_type="project_namespace_create", namespace_manifest=manifest)
    await message_sender.enqueue(project.cluster_id, message)

    return namespace


async def send_project_namespace_manifest_update(
    project: Project, gpu_preemption: GpuPreemptionConfig, message_sender: MessageSender
) -> None:
    manifest = _build_namespace_manifest(project.name, project.id, gpu_preemption)
    message = ProjectNamespaceUpdateMessage(message_type="project_namespace_update", namespace_manifest=manifest)
    await message_sender.enqueue(project.cluster_id, message)


async def update_project_namespace_status(
    kc_admin: KeycloakAdmin,
    session: AsyncSession,
    cluster: Cluster,
    message: ProjectNamespaceStatusMessage,
) -> None:
    namespace = await get_namespace_by_project_and_cluster(session, message.project_id, cluster.id)
    if not namespace:
        raise NotFoundException(f"Namespace for project {message.project_id} not found in cluster {cluster.id}.")

    project = await get_project_by_id(session, namespace.project_id)
    if not project:
        raise NotFoundException(f"Project {namespace.project_id} not found.")

    db_config = extract_gpu_preemption_config(project)
    if message.gpu_preemption is not None and has_gpu_preemption_changed(db_config, message.gpu_preemption):
        await __update_project_namespace_status(
            kc_admin,
            session,
            namespace,
            project,
            NamespaceStatus.FAILED,
            namespace_failure_message_preemption_mismatch(message.gpu_preemption),
        )
        logger.warning(f"Namespace {project.name} preemption config diverged from DB; marked as failed.")
    else:
        await __update_project_namespace_status(
            kc_admin, session, namespace, project, message.status, message.status_reason
        )


async def __update_project_namespace_status(
    kc_admin: KeycloakAdmin,
    session: AsyncSession,
    namespace: Namespace,
    project: Project,
    status: NamespaceStatus,
    status_reason: str | None,
) -> None:
    from ..projects.service import update_project_status_from_components  # noqa: PLC0415

    await update_namespace_status(session, namespace, status, status_reason, "system")
    await update_project_status_from_components(kc_admin, session, project)
    logger.info(f"Updated namespace {project.name} status to {status}.")


async def delete_namespace_in_cluster(
    session: AsyncSession, project: Project, updater: str, message_sender: MessageSender
) -> None:
    namespace = await get_namespace_by_project_and_cluster(session, project.id, project.cluster_id)
    if not namespace:
        raise NotFoundException(f"Namespace for project {project.id} not found in cluster {project.cluster_id}.")

    await update_namespace_status(
        session, namespace, NamespaceStatus.TERMINATING, "Namespace is being deleted", updater
    )
    message = ProjectNamespaceDeleteMessage(
        message_type="project_namespace_delete",
        name=project.name,
        project_id=project.id,
    )
    await message_sender.enqueue(project.cluster_id, message)


async def record_unmanaged_namespace(
    session: AsyncSession, cluster: Cluster, message: UnmanagedNamespaceMessage
) -> None:
    namespace = await get_namespace_by_name_and_cluster(session, cluster.id, message.namespace_name)
    if namespace and namespace.project_id is None:
        await update_namespace_status(
            session,
            namespace,
            message.namespace_status,
            f"Unmanaged namespace status: {message.namespace_status.value}",
            updater="system",
        )
        logger.info(f"Updated unmanaged namespace '{message.namespace_name}' in cluster {cluster.name}")
    elif not namespace:
        namespace = Namespace(
            name=message.namespace_name,
            cluster_id=cluster.id,
            status=message.namespace_status,
            status_reason=f"Unmanaged namespace status: {message.namespace_status.value}",
            project_id=None,
            created_by="system",
            updated_by="system",
        )
        await create_namespace(session, namespace)
        logger.info(f"Created unmanaged namespace '{message.namespace_name}' in cluster {cluster.name}")


async def handle_namespace_deleted(
    kc_admin: KeycloakAdmin, session: AsyncSession, cluster: Cluster, message: NamespaceDeletedMessage
) -> None:
    namespace = await get_namespace_by_name_and_cluster(session, cluster.id, message.namespace_name)

    if not namespace:
        raise NotFoundException(f"Namespace {message.namespace_name} not found in cluster {cluster.id}.")

    if namespace.project_id is not None:
        project = await get_project_by_id(session, namespace.project_id)
        if not project:
            raise NotFoundException(f"Project {namespace.project_id} not found.")
        await __update_project_namespace_status(
            kc_admin, session, namespace, project, NamespaceStatus.DELETED, "Namespace deleted"
        )
    else:
        await delete_namespace(session, namespace)
        logger.info(f"Deleted unmanaged namespace '{message.namespace_name}' from database")
