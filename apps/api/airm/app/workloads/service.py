# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from loguru import logger
from prometheus_api_client import PrometheusConnect
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ConflictException

from ..clusters.models import Cluster
from ..clusters.repository import get_cluster_by_id
from ..messaging.sender import MessageSender
from ..metrics.service import get_gpu_and_node_counts_for_workload
from ..projects.models import Project
from .constants import WORKLOAD_STATS_STATUSES
from .enums import WorkloadComponentKind, WorkloadStatus, WorkloadType
from .messaging import (
    AutoDiscoveredWorkloadComponentMessage,
    DeleteWorkloadMessage,
    WorkloadComponentStatusMessage,
    WorkloadMessage,
    WorkloadStatusMessage,
)
from .models import Workload
from .repository import create_workload as create_workload_in_db
from .repository import create_workload_component as create_workload_component_in_db
from .repository import create_workload_components as create_workload_components_in_db
from .repository import (
    get_workload_by_id_in_cluster,
    get_workload_component_by_id,
    get_workload_components_by_workload_id,
    get_workload_time_in_status,
    get_workload_time_summary_by_workload_id_and_status,
    get_workloads_in_clusters_with_status_count,
    get_workloads_with_status_count,
    get_workloads_with_status_in_cluster_count,
    get_workloads_with_status_in_project_count,
    increment_total_elapsed_seconds,
    insert_workload_time_summary,
)
from .repository import get_workloads_accessible_to_user as get_workloads_accessible_to_user_from_db
from .repository import get_workloads_by_project as get_workloads_by_project_in_db
from .repository import update_workload_component_status as update_workload_component_status_in_db
from .repository import update_workload_display_name as update_workload_display_name_in_db
from .repository import update_workload_status as update_workload_status_in_db
from .schemas import (
    WorkloadComponent,
    WorkloadComponentIn,
    WorkloadMetricsDetailsResponse,
    WorkloadResponse,
    Workloads,
    WorkloadsStats,
    WorkloadStatusCount,
    WorkloadStatusStats,
    WorkloadWithComponents,
)
from .utils import (
    extract_workload_components_from_manifest,
    get_workload_component_for_status_update,
    inject_workload_metadata_to_manifest,
    resolve_workload_status,
)

# These mirror Kubernetes' own generated-name scheme (apimachinery `rand.SafeEncodeString` /
# `rand.String`): the alphabet is k8s `alphanums` = "bcdfghjklmnpqrstvwxz2456789" (vowels, the
# consonant y, and the digits 0/1/3 dropped), a ReplicaSet appends a 1-10 char pod-template-hash,
# and a Pod appends a 5-char suffix. These are internal conventions with no compatibility
# guarantee, so reconstructing them here is best-effort and fail-closed.
_REPLICA_SET_NAME_SUFFIX = re.compile(r"^[bcdfghjklmnpqrstvwxz2456789]{1,10}$")
_POD_NAME_SUFFIX = re.compile(r"^[bcdfghjklmnpqrstvwxz2456789]{5}$")
# Owner kind -> the descendant kinds whose apiserver-generated names begin with the owner's.
# Deployment owns ReplicaSets (and, transitively, their Pods); ReplicaSet, Job and DaemonSet
# own Pods directly. StatefulSet is deliberately excluded: its pods use deterministic
# ordinal names (`<sts>-<n>`), so they can't be mistaken for their owner in the first place.
_OWNER_DESCENDANT_KINDS = {
    WorkloadComponentKind.DEPLOYMENT: frozenset(
        {WorkloadComponentKind.REPLICA_SET.value, WorkloadComponentKind.POD.value}
    ),
    WorkloadComponentKind.REPLICA_SET: frozenset({WorkloadComponentKind.POD.value}),
    WorkloadComponentKind.JOB: frozenset({WorkloadComponentKind.POD.value}),
    WorkloadComponentKind.DAEMON_SET: frozenset({WorkloadComponentKind.POD.value}),
}


def _looks_like_generated_descendant(owner_kind: WorkloadComponentKind, descendant_suffix: str) -> bool:
    """Whether descendant_suffix is the Kubernetes-generated tail of owner_kind's child.

    A ReplicaSet appends a pod-template-hash (1-10 chars) and its Pod appends a further 5-char
    suffix, so a Deployment's descendant is either `<hash>` or `<hash>-<pod>`. ReplicaSet-, Job-
    and DaemonSet-owned Pods add a single 5-char suffix. Pods never own a rename, so a Pod-kind
    owner is not reachable here.
    """
    if owner_kind == WorkloadComponentKind.DEPLOYMENT:
        replica_set_suffix, separator, pod_suffix = descendant_suffix.rpartition("-")
        return bool(
            _REPLICA_SET_NAME_SUFFIX.fullmatch(descendant_suffix)
            or (
                separator
                and _REPLICA_SET_NAME_SUFFIX.fullmatch(replica_set_suffix)
                and _POD_NAME_SUFFIX.fullmatch(pod_suffix)
            )
        )
    # ReplicaSet, Job and DaemonSet own Pods directly: a single apiserver 5-char suffix.
    return bool(_POD_NAME_SUFFIX.fullmatch(descendant_suffix))


async def extract_components_and_submit_workload(
    session: AsyncSession,
    workload: Workload,
    project: Project,
    manifest: list[dict],
    creator: str,
    token: str,
    message_sender: MessageSender,
) -> None:
    components_with_manifests = extract_workload_components_from_manifest(manifest, workload.id)
    # Separate the list into components and manifests lists
    components, manifests = zip(*components_with_manifests)

    # Save the components
    db_components = await create_workload_components_in_db(
        session=session,
        components=list(components),
        creator=creator,
    )

    # Match up the db components with the manifests based on the indexes in the lists
    db_components_with_manifests = list(zip(db_components, manifests))

    workload_manifest = inject_workload_metadata_to_manifest(workload.id, project, db_components_with_manifests)

    message = WorkloadMessage(
        message_type="workload", manifest=workload_manifest, user_token=token, workload_id=workload.id
    )
    await message_sender.enqueue(project.cluster_id, message)


async def create_and_submit_workload(
    session: AsyncSession,
    project: Project,
    manifest: list[dict],
    creator: str,
    token: str,
    workload_type: WorkloadType,
    display_name: str,
    message_sender: MessageSender,
) -> WorkloadResponse:
    workload = await create_workload_in_db(
        session=session,
        cluster_id=project.cluster_id,
        project_id=project.id,
        status=WorkloadStatus.PENDING,
        creator=creator,
        workload_type=workload_type,
        display_name=display_name,
    )
    await extract_components_and_submit_workload(session, workload, project, manifest, creator, token, message_sender)
    return WorkloadResponse.model_validate(workload)


async def submit_delete_workload(
    session: AsyncSession, workload: Workload, user: str, message_sender: MessageSender
) -> None:
    if workload.status == WorkloadStatus.DELETING:
        raise ConflictException("Workload is already marked for deletion")
    elif workload.status == WorkloadStatus.DELETED:
        raise ConflictException("Workload has already been deleted")

    if workload.updated_at > workload.last_status_transition_at:
        duration_in_status = workload.updated_at - workload.last_status_transition_at
    else:
        duration_in_status = datetime.now(UTC) - workload.updated_at

    await increment_workload_time_summary(session, workload.id, workload.status, duration_in_status)
    await update_workload_status_in_db(session, workload, WorkloadStatus.DELETING, datetime.now(UTC), user)

    message = DeleteWorkloadMessage(message_type="delete_workload", workload_id=workload.id)
    await message_sender.enqueue(workload.cluster_id, message)


async def get_workload_with_components(session: AsyncSession, workload: Workload) -> WorkloadWithComponents:
    components = await get_workload_components_by_workload_id(session, workload.id)
    return WorkloadWithComponents.model_validate(
        WorkloadResponse.model_validate(workload).model_copy(
            update={"components": [WorkloadComponent.model_validate(c) for c in components]}
        )
    )


async def get_workload_details(
    session: AsyncSession,
    workload: Workload,
    prometheus_client: PrometheusConnect,
) -> WorkloadMetricsDetailsResponse:
    """
    Builds the workload details response by combining DB data (cluster,
    time summaries) with Prometheus-derived counts.
    """
    gpu_devices_in_use, nodes_in_use = await get_gpu_and_node_counts_for_workload(workload.id, prometheus_client)

    cluster, queue_time, running_time = await asyncio.gather(
        get_cluster_by_id(session, workload.cluster_id),
        get_workload_time_in_status(session, workload.id, WorkloadStatus.PENDING),
        get_workload_time_in_status(session, workload.id, WorkloadStatus.RUNNING),
    )

    return WorkloadMetricsDetailsResponse(
        name=workload.display_name,
        workload_id=workload.id,
        created_by=workload.created_by,
        cluster_name=cluster.name if cluster else None,
        cluster_id=workload.cluster_id,
        nodes_in_use=nodes_in_use,
        gpu_devices_in_use=gpu_devices_in_use,
        created_at=workload.created_at,
        updated_at=workload.updated_at,
        queue_time=queue_time,
        running_time=running_time,
    )


async def get_status_stats_for_workloads_in_cluster(session: AsyncSession, cluster: Cluster) -> WorkloadStatusStats:
    """
    Returns detailed workload statistics for the given cluster, including counts for all workload statuses.
    This is similar to get_stats_for_workloads_in_project but for cluster-level stats.
    """
    workloads_counts = await get_workloads_with_status_in_cluster_count(
        session,
        cluster.id,
        WORKLOAD_STATS_STATUSES,
    )

    status_counts = [WorkloadStatusCount(status=status, count=count) for status, count in workloads_counts.items()]

    return WorkloadStatusStats(
        name=cluster.name, total_workloads=sum(workloads_counts.values()), status_counts=status_counts
    )


async def get_stats_for_workloads_in_accessible_clusters(
    session: AsyncSession, accessible_clusters: list[Cluster]
) -> WorkloadsStats:
    workloads_counts = await get_workloads_in_clusters_with_status_count(
        session,
        accessible_clusters,
        [WorkloadStatus.RUNNING, WorkloadStatus.PENDING],
    )
    return WorkloadsStats(
        running_workloads_count=workloads_counts.get(WorkloadStatus.RUNNING, 0),
        pending_workloads_count=workloads_counts.get(WorkloadStatus.PENDING, 0),
    )


async def get_stats_for_workloads(session: AsyncSession) -> WorkloadsStats:
    workloads_counts = await get_workloads_with_status_count(session, [WorkloadStatus.RUNNING, WorkloadStatus.PENDING])
    return WorkloadsStats(
        running_workloads_count=workloads_counts.get(WorkloadStatus.RUNNING, 0),
        pending_workloads_count=workloads_counts.get(WorkloadStatus.PENDING, 0),
    )


async def update_workload_status(
    session: AsyncSession, cluster: Cluster, workload_status: WorkloadStatusMessage
) -> None:
    workload = await get_workload_by_id_in_cluster(session, workload_status.workload_id, cluster.id)

    if workload is None:
        logger.warning(f"Workload {workload_status.workload_id} not found in cluster {cluster.id}")
        return

    if workload.updated_at < workload_status.updated_at:
        await increment_workload_time_summary(
            session, workload.id, workload.status, workload_status.updated_at - workload.updated_at
        )
        await update_workload_status_in_db(
            session, workload, workload_status.status, workload_status.updated_at, "system"
        )


async def get_workloads_by_project(session: AsyncSession, project_id: UUID) -> Workloads:
    db_workloads = await get_workloads_by_project_in_db(session, project_id)
    return Workloads(data=[WorkloadResponse.model_validate(workload) for workload in db_workloads])


async def get_workloads_accessible_to_user(session: AsyncSession, accessible_projects: list[Project]) -> Workloads:
    db_workloads = await get_workloads_accessible_to_user_from_db(session, accessible_projects)
    return Workloads(data=[WorkloadResponse.model_validate(workload) for workload in db_workloads])


async def update_workload_component_status(
    session: AsyncSession, cluster: Cluster, message: WorkloadComponentStatusMessage
) -> None:
    workload = await get_workload_by_id_in_cluster(session, message.workload_id, cluster.id)

    if workload is None:
        logger.error(f"Workload {message.workload_id} not found in cluster {cluster.id}")
        return

    components = await get_workload_components_by_workload_id(session, message.workload_id)

    if not components:
        logger.error(f"No components found for workload {message.workload_id}")
        return

    component = get_workload_component_for_status_update(components, message)

    if not component:
        logger.warning(
            f"Workload component {message.id} not found in workload {workload.id}. Maybe a child created from a component."
        )
        return

    if component.updated_at >= message.updated_at:
        logger.debug(f"Received outdated status for workload component {message.id}, ignoring.")
        return

    await update_workload_component_status_in_db(
        session, component, message.status, message.status_reason, message.updated_at, "system"
    )

    new_workload_status = resolve_workload_status(workload.status, components)

    if workload.status != new_workload_status:
        await increment_workload_time_summary(
            session, workload.id, workload.status, message.updated_at - workload.last_status_transition_at
        )
        await update_workload_status_in_db(session, workload, new_workload_status, message.updated_at, "system")


async def register_auto_discovered_workload_component(
    session: AsyncSession, cluster: Cluster, message: AutoDiscoveredWorkloadComponentMessage
) -> None:
    workload = await get_workload_by_id_in_cluster(session, message.workload_id, cluster.id)
    submitter = message.submitter or "system"
    if not workload:
        logger.info("Workload has been auto discovered, creating entry in database")

        workload = await create_workload_in_db(
            session=session,
            cluster_id=cluster.id,
            project_id=message.project_id,
            status=WorkloadStatus.PENDING,
            creator=submitter,
            workload_type=message.workload_type,
            display_name=message.name,
            workload_id=message.workload_id,
        )
    elif (
        workload.display_name
        and workload.display_name != message.name
        and message.kind in _OWNER_DESCENDANT_KINDS
        and workload.display_name.startswith(f"{message.name}-")
    ):
        # Discovery messages for an owner and its hash-suffixed children can arrive in any
        # order. Rename to the shorter owner name only when the current name is a generated
        # child suffix AND a child component actually carries that name, so submitter-chosen
        # names that merely share a prefix are left unchanged.
        descendant_suffix = workload.display_name.removeprefix(f"{message.name}-")
        if _looks_like_generated_descendant(message.kind, descendant_suffix):
            components = await get_workload_components_by_workload_id(session, workload.id)
            # Require a real descendant component carrying this name before renaming, so a
            # submitter-chosen name that merely shares the prefix is never rewritten.
            # For an auto-discovered owner->child chain the agent propagates one shared
            # component_id into each pod template, so the chain collapses to a single component
            # row (a manifest-submitted workload has one row per resource, but those arrive under
            # the owner name and never reach this branch). In a Pod->ReplicaSet->Deployment race
            # that single row is the Pod, and after the Pod->ReplicaSet rename the stored
            # display_name is the ReplicaSet name while the row still holds the grandchild Pod
            # name; the second clause recognises that Pod as the display_name's descendant.
            # Without it, Pod-first three-level discovery would stop one level short.
            has_descendant_lineage = any(
                component.kind in _OWNER_DESCENDANT_KINDS[message.kind]
                and (
                    component.name == workload.display_name
                    or (
                        component.kind == WorkloadComponentKind.POD
                        and component.name.startswith(f"{workload.display_name}-")
                        and _POD_NAME_SUFFIX.fullmatch(component.name.removeprefix(f"{workload.display_name}-"))
                    )
                )
                for component in components
            )
            if has_descendant_lineage:
                logger.info(
                    f"Renaming auto-discovered workload {workload.id} from {workload.display_name} "
                    f"to its owning {message.kind} {message.name}"
                )
                await update_workload_display_name_in_db(session, workload, message.name, "system")

    component = await get_workload_component_by_id(session, message.component_id, workload.id)
    if not component:
        logger.info("Workload component has been auto discovered, creating entry in database")
        component = WorkloadComponentIn(
            name=message.name,
            kind=message.kind,
            api_version=message.api_version,
            workload_id=workload.id,
            id=message.component_id,
        )
        await create_workload_component_in_db(session=session, component=component, creator=submitter)


async def increment_workload_time_summary(
    session: AsyncSession, workload_id: UUID, status: WorkloadStatus, duration_in_status: timedelta
) -> None:
    duration_in_status_seconds = duration_in_status.total_seconds()
    workload_time_summary = await get_workload_time_summary_by_workload_id_and_status(session, workload_id, status)
    if workload_time_summary:
        await increment_total_elapsed_seconds(
            session, workload_time_summary=workload_time_summary, increment_seconds=duration_in_status_seconds
        )
    else:
        await insert_workload_time_summary(
            session, workload_id=workload_id, status=status, total_elapsed_seconds=duration_in_status_seconds
        )


async def get_stats_for_workloads_in_project(session: AsyncSession, project: Project) -> WorkloadStatusStats:
    workloads_counts = await get_workloads_with_status_in_project_count(
        session,
        project.id,
        WORKLOAD_STATS_STATUSES,
    )

    status_counts = [WorkloadStatusCount(status=status, count=count) for status, count in workloads_counts.items()]

    return WorkloadStatusStats(
        name=project.name, total_workloads=sum(workloads_counts.values()), status_counts=status_counts
    )
