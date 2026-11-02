# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import datetime

from prometheus_client.core import GaugeMetricFamily
from sqlalchemy.ext.asyncio import AsyncSession

from ..clusters.constants import DEFAULT_PRIORITY_CLASSES
from ..clusters.models import Cluster, ClusterNode
from ..clusters.schemas import ClusterWithResources
from ..clusters.service import get_cluster_with_resources
from ..projects.models import Project
from ..utilities.enums import GPUVendor
from .constants import DEFAULT_CATCH_ALL_QUOTA_NAME, PENDING_QUOTA_PROVISIONING_GRACE
from .enums import QuotaStatus
from .messaging import ClusterQuotaAllocation, ClusterQuotasAllocationMessage
from .models import Quota
from .schemas import QuotaCreate, QuotaUpdate


def format_quotas_allocation_message(
    quota_allocations: list[ClusterQuotaAllocation], gpu_vendor: GPUVendor | None
) -> ClusterQuotasAllocationMessage:
    """
    Format quota allocations into a ClusterQuotasAllocationMessage.

    Args:
        quota_allocations: List of quota allocations for the cluster
        gpu_vendor: GPU vendor type for the cluster

    Returns:
        ClusterQuotasAllocationMessage ready to be sent
    """
    return ClusterQuotasAllocationMessage(
        message_type="cluster_quotas_allocation",
        gpu_vendor=gpu_vendor,
        quota_allocations=quota_allocations,
        priority_classes=DEFAULT_PRIORITY_CLASSES,
    )


def validate_quota_against_available_cluster_resources(
    cluster_resources: ClusterWithResources, quota: QuotaCreate | QuotaUpdate, prev_quota: Quota | None = None
) -> list[str]:
    """Validates that the requested quota doesn't exceed available cluster resources"""
    allocated_resources = cluster_resources.allocated_resources

    allocated_cpu = allocated_resources.cpu_milli_cores
    allocated_memory = allocated_resources.memory_bytes
    allocated_storage = allocated_resources.ephemeral_storage_bytes
    allocated_gpu = allocated_resources.gpu_count

    if prev_quota:
        # Subtract the old values from allocated totals
        allocated_cpu -= prev_quota.cpu_milli_cores
        allocated_memory -= prev_quota.memory_bytes
        allocated_storage -= prev_quota.ephemeral_storage_bytes
        allocated_gpu -= prev_quota.gpu_count

    new_total_cpu = allocated_cpu + quota.cpu_milli_cores
    new_total_memory = allocated_memory + quota.memory_bytes
    new_total_storage = allocated_storage + quota.ephemeral_storage_bytes
    new_total_gpu = allocated_gpu + quota.gpu_count

    validation_errors = []

    if new_total_cpu > cluster_resources.available_resources.cpu_milli_cores:
        validation_errors.append("CPU")

    if new_total_memory > cluster_resources.available_resources.memory_bytes:
        validation_errors.append("memory")

    if new_total_storage > cluster_resources.available_resources.ephemeral_storage_bytes:
        validation_errors.append("storage")

    if new_total_gpu > cluster_resources.available_resources.gpu_count:
        validation_errors.append("GPU")
    return validation_errors


def does_quota_match_allocation(quota: Quota, quota_allocation: ClusterQuotaAllocation) -> bool:
    quota_field = quota.__dict__
    return all(v == quota_field.get(k) for k, v in quota_allocation.model_dump().items() if k in quota_field)


def is_within_provisioning_grace(quota: Quota, message_updated_at: datetime) -> bool:
    """Whether the cluster is still expected to be applying this quota.

    A PENDING quota has been accepted by the API but not yet confirmed by the cluster, so a
    snapshot taken during that window describes the state before the change: the quota is
    either absent (its ClusterQueue does not exist yet) or still carries its previous
    allocation. Neither means the quota is broken. Once the grace expires a quota the cluster
    never applied does fail, so a ClusterQueue that never materializes is not hidden forever.

    The window is measured across two hosts and therefore assumes their clocks are
    synchronized: message_updated_at is stamped by the cluster agent, while quota.updated_at is
    stamped by this API on create and update (cluster-driven transitions restamp it with the
    agent's own timestamp). An agent running more than the grace ahead of the API collapses the
    window and fails quotas early; one running behind widens it. Clusters and the API are
    expected to share an NTP source, so this is an operational invariant rather than something
    the comparison can recover from on its own.
    """
    return (
        quota.status == QuotaStatus.PENDING
        and (message_updated_at - quota.updated_at) < PENDING_QUOTA_PROVISIONING_GRACE
    )


def quota_failure_message_mismatch(quota_allocation: ClusterQuotaAllocation) -> str:
    return f"""Quota on cluster does not match configured value.
Quota on cluster:
{__format_quotas_for_message(quota_allocation.cpu_milli_cores, quota_allocation.memory_bytes, quota_allocation.ephemeral_storage_bytes, quota_allocation.gpu_count)}"""


def quota_failure_message_missing(quota: Quota) -> str:
    return f"""Quota was removed from the cluster.
Previously configured quota:
{__format_quotas_for_message(quota.cpu_milli_cores, quota.memory_bytes, quota.ephemeral_storage_bytes, quota.gpu_count)}"""


def __format_quotas_for_message(
    cpu_milli_cores: int, memory_bytes: int, ephemeral_storage_bytes: int, gpu_count: int
) -> str:
    return f"""- CPU: {round(cpu_milli_cores / 1000, 2)}
- Memory: {round(memory_bytes / (1024**3), 2)} GB
- Ephemeral Storage: {round(ephemeral_storage_bytes / (1024**3), 2)} GB
- GPU Count: {gpu_count}"""


async def calculate_dynamic_catch_all_quota_allocation(
    session: AsyncSession, cluster: Cluster
) -> ClusterQuotaAllocation:
    cluster_resources = await get_cluster_with_resources(session, cluster)

    remaining_cpu = max(
        0,
        cluster_resources.available_resources.cpu_milli_cores - cluster_resources.allocated_resources.cpu_milli_cores,
    )
    remaining_memory = max(
        0, cluster_resources.available_resources.memory_bytes - cluster_resources.allocated_resources.memory_bytes
    )
    remaining_storage = max(
        0,
        cluster_resources.available_resources.ephemeral_storage_bytes
        - cluster_resources.allocated_resources.ephemeral_storage_bytes,
    )
    remaining_gpu = max(
        0, cluster_resources.available_resources.gpu_count - cluster_resources.allocated_resources.gpu_count
    )

    return ClusterQuotaAllocation(
        cpu_milli_cores=remaining_cpu,
        gpu_count=remaining_gpu,
        memory_bytes=remaining_memory,
        ephemeral_storage_bytes=remaining_storage,
        quota_name=DEFAULT_CATCH_ALL_QUOTA_NAME,
        namespaces=[],
    )


def have_quota_resources_changed(quota: Quota, edits: QuotaUpdate) -> bool:
    return any(getattr(quota, key) != value for key, value in edits.model_dump().items())


def set_allocated_gpus_metric_samples(
    allocated_gpus_metric: GaugeMetricFamily, projects: list[Project]
) -> GaugeMetricFamily:
    allocated_gpus_metric.samples.clear()
    for project in projects:
        allocated_gpus_metric.add_metric(
            [
                str(project.id),
                str(project.cluster_id),
                project.cluster.name,
            ],
            project.quota.gpu_count,
        )
    return allocated_gpus_metric


def set_allocated_vram_metric_samples(
    allocated_gpu_vram_metric: GaugeMetricFamily,
    projects: list[Project],
    cluster_nodes: list[ClusterNode],
) -> GaugeMetricFamily:
    allocated_gpu_vram_metric.samples.clear()
    cluster_id_to_gpu_node = {node.cluster_id: node for node in cluster_nodes if node.gpu_vendor is not None}
    for project in projects:
        gpu_node = cluster_id_to_gpu_node.get(project.cluster_id, None)
        allocated_gpu_vram_metric.add_metric(
            [
                str(project.id),
                str(project.cluster_id),
                project.cluster.name,
            ],
            (project.quota.gpu_count * gpu_node.gpu_vram_bytes_per_device if gpu_node else 0)
            / (1024**2),  # Convert bytes to MB,
        )
    return allocated_gpu_vram_metric
