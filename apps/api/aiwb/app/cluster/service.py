# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Cluster resources service for AIWB API."""

import re

from loguru import logger

from ..aims.gateway import list_aim_cluster_models
from ..config import STANDALONE_MODE
from ..custom_models.constants import (
    DEFAULT_AIM_DEPLOYMENT_IMAGE_REF,
    EPYC_AIM_DEPLOYMENT_IMAGE_REF,
    RADEON_AIM_DEPLOYMENT_IMAGE_REF,
)
from ..dispatch.kube_client import KubernetesClient
from ..projects.crds import Namespace
from .constants import (
    AIM_ACCELERATOR_LABEL_PREFIX,
    AMD_GPU_DEVICE_ID_LABEL,
    AMD_GPU_DEVICE_ID_LABEL_BETA,
    AMD_GPU_PRODUCT_NAME_LABEL,
    AMD_GPU_PRODUCT_NAME_LABEL_BETA,
    AMD_GPU_RESOURCE,
    KUEUE_API_GROUP,
    KUEUE_API_VERSION,
    KUEUE_CLUSTER_QUEUE_PLURAL,
    KUEUE_LOCAL_QUEUE_PLURAL,
    NVIDIA_GPU_RESOURCE,
)
from .enums import ClusterAcceleratorType
from .schemas import (
    AimImageFamily,
    AvailableResources,
    ClusterAccelerator,
    ClusterResourcesData,
    ClusterResourcesResponse,
    ProjectQuotaResponse,
    ResourceQuotas,
)
from .utils import (
    is_node_ready,
    node_aim_accelerator_model_counts,
    parse_container_image_repository_and_tag,
)


def parse_cpu_value(cpu_str: str) -> int:
    """Parse Kubernetes CPU value to milli-cores.

    Examples:
        - "1" -> 1000 milli-cores
        - "500m" -> 500 milli-cores
        - "2.5" -> 2500 milli-cores
    """
    if not cpu_str:
        return 0

    cpu_str = cpu_str.strip()
    if cpu_str.endswith("m"):
        # Already in milli-cores
        return int(cpu_str[:-1])
    else:
        # In cores, convert to milli-cores
        return int(float(cpu_str) * 1000)


def parse_memory_value(memory_str: str) -> int:
    """Parse Kubernetes memory value to bytes.

    Supports units: Ki, Mi, Gi, Ti, K, M, G, T, and plain bytes.
    """
    if not memory_str:
        return 0

    memory_str = memory_str.strip()

    # Handle binary units (Ki, Mi, Gi, Ti)
    if memory_str.endswith("Ki"):
        return int(memory_str[:-2]) * 1024
    elif memory_str.endswith("Mi"):
        return int(memory_str[:-2]) * 1024 * 1024
    elif memory_str.endswith("Gi"):
        return int(memory_str[:-2]) * 1024 * 1024 * 1024
    elif memory_str.endswith("Ti"):
        return int(memory_str[:-2]) * 1024 * 1024 * 1024 * 1024

    # Handle decimal units (K, M, G, T)
    elif memory_str.endswith("K"):
        return int(float(memory_str[:-1]) * 1000)
    elif memory_str.endswith("M"):
        return int(float(memory_str[:-1]) * 1000 * 1000)
    elif memory_str.endswith("G"):
        return int(float(memory_str[:-1]) * 1000 * 1000 * 1000)
    elif memory_str.endswith("T"):
        return int(float(memory_str[:-1]) * 1000 * 1000 * 1000 * 1000)

    # Plain bytes
    else:
        return int(memory_str)


def get_gpu_count_from_node(node: dict) -> int:
    """Extract GPU count from a Kubernetes node.

    Looks for nvidia.com/gpu or amd.com/gpu in allocatable resources.
    """
    allocatable = node.get("status", {}).get("allocatable", {})

    # Check for NVIDIA GPUs
    nvidia_gpus = allocatable.get("nvidia.com/gpu", "0")
    if nvidia_gpus and nvidia_gpus != "0":
        return int(nvidia_gpus)

    # Check for AMD GPUs
    amd_gpus = allocatable.get(AMD_GPU_RESOURCE, "0")
    if amd_gpus and amd_gpus != "0":
        return int(amd_gpus)

    return 0


async def get_cluster_resources(kube_client: KubernetesClient) -> ClusterResourcesResponse:
    """Get available cluster resources by querying Kubernetes API.

    Queries all nodes in the cluster and aggregates their allocatable resources.
    Only counts resources from ready nodes.

    Args:
        kube_client: Kubernetes client instance

    Returns:
        ClusterResourcesResponse with aggregated cluster resources
    """
    try:
        # List all nodes in the cluster
        nodes_response = await kube_client.core_v1.list_node()
        nodes = nodes_response.items if hasattr(nodes_response, "items") else []

        total_cpu_milli_cores = 0
        total_memory_bytes = 0
        total_storage_bytes = 0
        total_gpu_count = 0
        ready_node_count = 0

        for node in nodes:
            if not is_node_ready(node):
                continue

            ready_node_count += 1

            # Get allocatable resources
            if hasattr(node, "status") and node.status and hasattr(node.status, "allocatable"):
                allocatable = node.status.allocatable

                # Parse CPU
                if hasattr(allocatable, "get"):
                    cpu_str = allocatable.get("cpu", "0")
                    memory_str = allocatable.get("memory", "0")
                    storage_str = allocatable.get("ephemeral-storage", "0")
                else:
                    # Handle dict-like object
                    cpu_str = getattr(allocatable, "cpu", "0")
                    memory_str = getattr(allocatable, "memory", "0")
                    storage_str = getattr(allocatable, "ephemeral_storage", "0")

                total_cpu_milli_cores += parse_cpu_value(cpu_str)
                total_memory_bytes += parse_memory_value(memory_str)
                total_storage_bytes += parse_memory_value(storage_str)

                # Count GPUs
                # Convert node object to dict for GPU parsing
                node_dict = node.to_dict() if hasattr(node, "to_dict") else {}
                total_gpu_count += get_gpu_count_from_node(node_dict)

        logger.info(
            f"Cluster resources: {ready_node_count} ready nodes, "
            f"{total_cpu_milli_cores}m CPU, "
            f"{total_memory_bytes} bytes memory, "
            f"{total_gpu_count} GPUs"
        )

        return ClusterResourcesResponse(
            data=ClusterResourcesData(
                available_resources=AvailableResources(
                    cpu_milli_cores=total_cpu_milli_cores,
                    memory_bytes=total_memory_bytes,
                    ephemeral_storage_bytes=total_storage_bytes,
                    gpu_count=total_gpu_count,
                ),
                total_node_count=ready_node_count,
            )
        )

    except Exception:
        logger.exception("Failed to get cluster resources")
        raise


async def _get_cluster_queue_for_namespace(namespace: str, kube_client: KubernetesClient) -> dict | None:
    """Resolve the Kueue ClusterQueue for a namespace via its LocalQueue.

    Returns the ClusterQueue dict, or None if no LocalQueue exists, the
    ClusterQueue is not found, or the Kueue API is unavailable (404).
    Any other error is propagated.
    """
    try:
        local_queues = await kube_client.custom_objects.list_namespaced_custom_object(
            group=KUEUE_API_GROUP,
            version=KUEUE_API_VERSION,
            namespace=namespace,
            plural=KUEUE_LOCAL_QUEUE_PLURAL,
        )
    except Exception as e:
        if hasattr(e, "status") and e.status == 404:
            return None
        logger.exception(f"Failed to list LocalQueues in namespace {namespace}: {e}")
        raise

    items = local_queues.get("items", [])
    if not items:
        return None

    cluster_queue_name = items[0].get("spec", {}).get("clusterQueue")
    if not cluster_queue_name:
        return None

    try:
        return await kube_client.custom_objects.get_cluster_custom_object(
            group=KUEUE_API_GROUP,
            version=KUEUE_API_VERSION,
            plural=KUEUE_CLUSTER_QUEUE_PLURAL,
            name=cluster_queue_name,
        )
    except Exception as e:
        if hasattr(e, "status") and e.status == 404:
            return None
        logger.exception(f"Failed to get ClusterQueue/{cluster_queue_name}: {e}")
        raise


async def get_project_gpu_quota_from_kueue(namespace: str, kube_client: KubernetesClient) -> int | None:
    """Read a project's GPU quota from its Kueue ClusterQueue.

    Returns None if no LocalQueue exists, the ClusterQueue cannot be found,
    or no GPU resource is configured. Any unexpected error is propagated.
    """
    cluster_queue = await _get_cluster_queue_for_namespace(namespace, kube_client)
    if cluster_queue is None:
        return None

    for resource_group in cluster_queue.get("spec", {}).get("resourceGroups", []):
        for flavor in resource_group.get("flavors", []):
            for resource in flavor.get("resources", []):
                if resource.get("name") in (AMD_GPU_RESOURCE, NVIDIA_GPU_RESOURCE):
                    try:
                        return int(resource["nominalQuota"])
                    except (KeyError, TypeError, ValueError):
                        return None

    return None


_KUEUE_CPU_RESOURCE = "cpu"
_KUEUE_MEMORY_RESOURCE = "memory"
_KUEUE_EPHEMERAL_STORAGE_RESOURCE = "ephemeral-storage"


async def get_project_quota_state(namespace: str, kube_client: KubernetesClient) -> ProjectQuotaResponse:
    """Return the Kueue quota state for a project namespace.

    Reads all resource quotas from the ClusterQueue associated with the
    namespace's LocalQueue. Returns is_quota_managed=False with null quotas
    when no Kueue queue exists for the namespace.
    """
    cluster_queue = await _get_cluster_queue_for_namespace(namespace, kube_client)
    if cluster_queue is None:
        return ProjectQuotaResponse(is_quota_managed=False, quotas=ResourceQuotas())

    quotas = ResourceQuotas()
    for resource_group in cluster_queue.get("spec", {}).get("resourceGroups", []):
        for flavor in resource_group.get("flavors", []):
            for resource in flavor.get("resources", []):
                name = resource.get("name")
                nominal_quota = resource.get("nominalQuota")
                if nominal_quota is None:
                    continue
                try:
                    # GPU quotas are plain integers; CPU/memory/ephemeral-storage are
                    # Kubernetes Quantity strings (e.g. "500m", "16Gi") and need unit parsing.
                    if name in (AMD_GPU_RESOURCE, NVIDIA_GPU_RESOURCE):
                        quotas.gpu_count = int(nominal_quota)
                    elif name == _KUEUE_CPU_RESOURCE:
                        quotas.cpu_milli_cores = parse_cpu_value(str(nominal_quota))
                    elif name == _KUEUE_MEMORY_RESOURCE:
                        quotas.memory_bytes = parse_memory_value(str(nominal_quota))
                    elif name == _KUEUE_EPHEMERAL_STORAGE_RESOURCE:
                        quotas.ephemeral_storage_bytes = parse_memory_value(str(nominal_quota))
                except (TypeError, ValueError):
                    continue

    return ProjectQuotaResponse(is_quota_managed=True, quotas=quotas)


async def get_project_gpu_allocation_ceiling(namespace: Namespace, kube_client: KubernetesClient) -> int | None:
    """Resolve the GPU ceiling to display alongside a project's usage.

    Standalone AIWB has no quota system, so the ceiling is the cluster's total
    GPU capacity. Joint AIRM deployments use the project's assigned quota.
    """
    # The ceiling is a best-effort decoration on top of usage data; a cluster or
    # Kueue read failure must not fail the whole metrics response.
    try:
        if not STANDALONE_MODE:
            quota = await get_project_gpu_quota_from_kueue(namespace.name, kube_client)
            if quota:
                return quota
        resources = await get_cluster_resources(kube_client)
        return resources.data.available_resources.gpu_count
    except Exception:
        logger.exception("Failed to read GPU allocation ceiling")
        return None


async def get_project_cpu_allocation_ceiling(namespace: Namespace, kube_client: KubernetesClient) -> float | None:
    """Resolve the CPU ceiling (cores) to display alongside a project's usage.

    Mirrors get_project_gpu_allocation_ceiling: the project's Kueue quota when managed,
    otherwise the cluster's total CPU capacity. Best-effort — a read failure omits the
    ceiling rather than failing the metrics response.
    """
    try:
        if not STANDALONE_MODE:
            quota = await get_project_quota_state(namespace.name, kube_client)
            if quota.is_quota_managed and quota.quotas.cpu_milli_cores is not None:
                return quota.quotas.cpu_milli_cores / 1000
        resources = await get_cluster_resources(kube_client)
        return resources.data.available_resources.cpu_milli_cores / 1000
    except Exception:
        logger.exception("Failed to read CPU allocation ceiling")
        return None


async def get_project_memory_allocation_ceiling(namespace: Namespace, kube_client: KubernetesClient) -> float | None:
    """Resolve the system-memory ceiling (bytes) to display alongside a project's usage.

    Mirrors get_project_gpu_allocation_ceiling: the project's Kueue quota when managed,
    otherwise the cluster's total memory capacity. Best-effort.
    """
    try:
        if not STANDALONE_MODE:
            quota = await get_project_quota_state(namespace.name, kube_client)
            if quota.is_quota_managed and quota.quotas.memory_bytes is not None:
                return float(quota.quotas.memory_bytes)
        resources = await get_cluster_resources(kube_client)
        return float(resources.data.available_resources.memory_bytes)
    except Exception:
        logger.exception("Failed to read memory allocation ceiling")
        return None


async def get_cluster_gpu_device_info(kube_client: KubernetesClient) -> dict[str, str]:
    """Get AMD GPU device IDs and display names from ready cluster nodes.

    Returns a dict mapping device_id → display_name. Display name is read from
    the amd.com/gpu.product-name node label (underscores replaced with spaces).
    Falls back to the raw device ID when the label is absent.
    """
    try:
        nodes_response = await kube_client.core_v1.list_node()
        nodes = nodes_response.items if hasattr(nodes_response, "items") else []

        device_info: dict[str, str] = {}
        for node in nodes:
            if not is_node_ready(node):
                continue

            if hasattr(node, "metadata") and node.metadata:
                labels = node.metadata.labels or {}
                device_id = labels.get(AMD_GPU_DEVICE_ID_LABEL) or labels.get(AMD_GPU_DEVICE_ID_LABEL_BETA)
                if device_id:
                    product_name = labels.get(AMD_GPU_PRODUCT_NAME_LABEL) or labels.get(AMD_GPU_PRODUCT_NAME_LABEL_BETA)
                    device_info[device_id] = product_name.replace("_", " ") if product_name else device_id

        return device_info

    except Exception:
        logger.exception("Failed to get cluster GPU device info")
        raise


async def get_cluster_accelerators(kube_client: KubernetesClient) -> list[ClusterAccelerator]:
    """List all accelerator models found on ready nodes via aim-engine labels."""
    try:
        nodes_response = await kube_client.core_v1.list_node()
        nodes = nodes_response.items if hasattr(nodes_response, "items") else []

        # Keyed by (resource_type, device_id, vendor) to avoid collisions between families and vendors.
        aggregates: dict[tuple[ClusterAcceleratorType, str, str], tuple[str, int, str]] = {}
        generic_cpu_counts_by_vendor: dict[str, int] = {}
        discovered_cpu_models_by_vendor: dict[str, set[str]] = {}

        for node in nodes:
            if not is_node_ready(node):
                continue
            _process_ready_node_accelerators(
                node=node,
                aggregates=aggregates,
                generic_cpu_counts_by_vendor=generic_cpu_counts_by_vendor,
                discovered_cpu_models_by_vendor=discovered_cpu_models_by_vendor,
            )

        _apply_generic_cpu_fallbacks(
            aggregates=aggregates,
            generic_cpu_counts_by_vendor=generic_cpu_counts_by_vendor,
            discovered_cpu_models_by_vendor=discovered_cpu_models_by_vendor,
        )

        return [
            ClusterAccelerator(
                accelerator_type=resource_type,
                device_id=device_id,
                accelerator_vendor=vendor,
                product_name=product_name,
                allocatable_count=count,
                accelerator_model=accelerator_model,
            )
            for (resource_type, device_id, vendor), (product_name, count, accelerator_model) in sorted(
                aggregates.items(), key=lambda item: item[0]
            )
        ]

    except Exception:
        logger.exception("Failed to get cluster accelerators")
        raise


async def get_cluster_gpu_device_ids(kube_client: KubernetesClient) -> set[str]:
    """Get AMD GPU device type IDs present in the cluster.
    Returns a set of hex device type IDs (e.g. {"74a1", "74a9"}).
    """
    try:
        nodes_response = await kube_client.core_v1.list_node()
        nodes = nodes_response.items if hasattr(nodes_response, "items") else []

        device_ids: set[str] = set()
        for node in nodes:
            if not is_node_ready(node):
                continue

            if hasattr(node, "metadata") and node.metadata:
                labels = node.metadata.labels or {}
                device_id = labels.get(AMD_GPU_DEVICE_ID_LABEL) or labels.get(AMD_GPU_DEVICE_ID_LABEL_BETA)
                if device_id:
                    device_ids.add(device_id)

        return device_ids

    except Exception:
        logger.exception("Failed to get cluster GPU device IDs")
        raise


async def get_aim_image_families(kube_client: KubernetesClient) -> list[AimImageFamily]:
    """Return runtime-profile image families.

    Preferred source: base-only AIMClusterModels identified by
    status.managedProfiles where ``base > 0`` and all other profile types are
    zero. Fallback to accelerator-derived base image refs only when cluster
    model discovery fails.
    """
    try:
        discovered_images = await _list_supported_base_cluster_model_images(kube_client)
        return _build_aim_image_families_from_image_refs(discovered_images)
    except Exception as exc:
        logger.warning(
            f"Failed to list supported base cluster model images; falling back to accelerator discovery: {exc}"
        )
        image_refs = await get_cluster_base_image_refs(kube_client)
        return _build_aim_image_families_from_image_refs(image_refs)


def _is_base_only_managed_profiles(managed_profiles: object) -> bool:
    """Return True when managedProfiles indicates only base profiles."""
    if not isinstance(managed_profiles, dict):
        return False

    base_count = managed_profiles.get("base")
    if not isinstance(base_count, int) or base_count <= 0:
        return False

    # ready/total/notAvailable are aggregate counters, not profile types.
    aggregate_keys = {"base", "ready", "total", "notAvailable"}
    for profile_type, count in managed_profiles.items():
        if profile_type in aggregate_keys:
            continue
        if isinstance(count, int) and count > 0:
            return False
    return True


def is_supported_base_cluster_model(item: object) -> bool:
    """Return True for a hardware-validated, base-only AIMClusterModel."""
    if not isinstance(item, dict):
        return False
    status = item.get("status")
    if not isinstance(status, dict):
        return False
    if not _is_base_only_managed_profiles(status.get("managedProfiles")):
        return False
    discovered = status.get("discoveredProfiles")
    if not isinstance(discovered, dict):
        return False
    supported = discovered.get("supported")
    return isinstance(supported, int) and supported > 0


async def _list_supported_base_cluster_model_images(kube_client: KubernetesClient) -> list[str]:
    """Return unique image refs from supported base-only AIMClusterModels.

    Base-only is signaled by status.managedProfiles.base > 0 and all other
    profile-type counts equal to zero. Candidate base models must also have
    status.discoveredProfiles.supported > 0 (hardware-validated).
    """
    images: set[str] = set()
    for item in await list_aim_cluster_models(kube_client, raise_on_error=True):
        if not is_supported_base_cluster_model(item):
            continue
        spec = item.get("spec") if isinstance(item, dict) else None
        image_ref = spec.get("image") if isinstance(spec, dict) else None
        if not isinstance(image_ref, str):
            continue

        normalized = image_ref.strip()
        if normalized:
            images.add(normalized)
    return sorted(images)


def _build_aim_image_families_from_image_refs(image_refs: list[str]) -> list[AimImageFamily]:
    """Build deterministic families grouped by image repository."""
    tags_by_family: dict[str, set[str]] = {}
    repository_by_family: dict[str, str] = {}

    for image_ref in image_refs:
        try:
            repository, tag = parse_container_image_repository_and_tag(image_ref)
        except ValueError:
            logger.warning(f"Skipping invalid AIM image ref from discovery: {image_ref!r}")
            continue

        family_id = repository.rsplit("/", 1)[-1]
        repository_by_family[family_id] = repository
        tags_by_family.setdefault(family_id, set()).add(tag)

    families: list[AimImageFamily] = [
        AimImageFamily(
            family_id="automatic",
            display_name="Automatic",
            repository=None,
            tags=[],
        )
    ]
    for family_id in sorted(tags_by_family):
        families.append(
            AimImageFamily(
                family_id=family_id,
                display_name=family_id,
                repository=repository_by_family[family_id],
                tags=_sort_image_tags_desc(tags_by_family[family_id]),
            )
        )
    return families


def _sort_image_tags_desc(tags: set[str]) -> list[str]:
    """Sort tags newest-first, preferring semantic versions over plain text."""
    return sorted(tags, key=_image_tag_sort_key, reverse=True)


def _image_tag_sort_key(tag: str) -> tuple[int, tuple[int, ...], int, str]:
    """Build a sort key for image tags.

    1) Semantic-like tags (e.g. 0.13.1, v1.2) come before non-version strings.
    2) Higher numeric versions sort first.
    3) Stable releases sort above pre-release variants of the same base version.
    4) Remaining ties use lexicographic order.
    """
    normalized = tag.strip()
    if not normalized:
        return (0, tuple(), 0, normalized)

    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)(.*)", normalized)
    if not match:
        return (0, tuple(), 0, normalized)

    version_core = tuple(int(part) for part in match.group(1).split("."))
    suffix = match.group(2).strip()
    is_stable = 1 if suffix == "" else 0
    return (1, version_core, is_stable, normalized)


def _resolve_cluster_base_image_ref(accelerators: list[ClusterAccelerator]) -> list[str]:
    """Resolve candidate base image refs from detected accelerator families."""
    has_radeon_gpu = False
    has_other_gpu = False
    has_epyc_cpu = False

    for entry in accelerators:
        model = (entry.accelerator_model or "").strip()
        if entry.accelerator_type == ClusterAcceleratorType.GPU:
            normalized_model = model.upper()
            vendor = (entry.accelerator_vendor or "").strip().lower()
            is_radeon_gpu = (
                normalized_model.startswith(("R", "W"))
                and not normalized_model.startswith("RTX")
                and vendor != "nvidia"
            )
            if is_radeon_gpu:
                has_radeon_gpu = True
            else:
                has_other_gpu = True
        elif entry.accelerator_type == ClusterAcceleratorType.CPU and model.startswith("EPYC_"):
            has_epyc_cpu = True

    image_refs: list[str] = []
    if has_other_gpu:
        image_refs.append(DEFAULT_AIM_DEPLOYMENT_IMAGE_REF)
    if has_radeon_gpu:
        image_refs.append(RADEON_AIM_DEPLOYMENT_IMAGE_REF)
    if has_epyc_cpu:
        image_refs.append(EPYC_AIM_DEPLOYMENT_IMAGE_REF)
    if not image_refs:
        image_refs.append(DEFAULT_AIM_DEPLOYMENT_IMAGE_REF)
    return image_refs


async def get_cluster_base_image_refs(kube_client: KubernetesClient) -> list[str]:
    """Return candidate base image refs for the accelerators detected in the cluster."""
    try:
        accelerators = await get_cluster_accelerators(kube_client)
    except Exception as exc:
        logger.warning(f"Failed to read cluster accelerators for image discovery; using default image ref: {exc}")
        accelerators = []
    return _resolve_cluster_base_image_ref(accelerators)


def _accelerator_resource_type(accelerator_model: str) -> ClusterAcceleratorType:
    """Infer accelerator resource type from accelerator model naming."""
    if accelerator_model == "CPU":
        return ClusterAcceleratorType.CPU
    if accelerator_model.startswith("EPYC_"):
        return ClusterAcceleratorType.CPU
    if accelerator_model.startswith("APU_"):
        return ClusterAcceleratorType.APU
    if accelerator_model.startswith(("MI", "R", "W")):
        return ClusterAcceleratorType.GPU
    return ClusterAcceleratorType.UNKNOWN


def _is_gpu_labeled_node(labels: dict[str, str], allocatable: dict[str, str]) -> bool:
    """Return True when node labels/resources indicate GPU capacity."""
    if labels.get(f"{AIM_ACCELERATOR_LABEL_PREFIX}GPU"):
        return True
    if allocatable.get(AMD_GPU_RESOURCE, "0") not in {"", "0"}:
        return True
    if allocatable.get(NVIDIA_GPU_RESOURCE, "0") not in {"", "0"}:
        return True
    return False


def _aim_vendor_by_resource_type(labels: dict[str, str]) -> dict[ClusterAcceleratorType, str]:
    """Extract preferred vendor by accelerator type from aim vendor labels."""
    preferred: dict[ClusterAcceleratorType, tuple[str, int]] = {}
    for key, value in labels.items():
        if not key.startswith(f"{AIM_ACCELERATOR_LABEL_PREFIX}vendor."):
            continue
        suffix = key[len(f"{AIM_ACCELERATOR_LABEL_PREFIX}vendor.") :]
        parts = suffix.split(".")
        if len(parts) < 2:
            continue
        family, vendor = parts[0], parts[1]
        if family == "CPU":
            resource_type = ClusterAcceleratorType.CPU
        elif family == "GPU":
            resource_type = ClusterAcceleratorType.GPU
        elif family == "APU":
            resource_type = ClusterAcceleratorType.APU
        else:
            resource_type = ClusterAcceleratorType.UNKNOWN
        normalized_vendor = vendor.strip().lower()
        if not normalized_vendor:
            continue
        try:
            score = int(value)
        except (TypeError, ValueError):
            score = 0
        current = preferred.get(resource_type)
        if current is None or score > current[1]:
            preferred[resource_type] = (normalized_vendor, score)
    return {resource_type: vendor for resource_type, (vendor, _score) in preferred.items()}


def _upsert_accelerator_aggregate(
    aggregates: dict[tuple[ClusterAcceleratorType, str, str], tuple[str, int, str]],
    resource_type: ClusterAcceleratorType,
    device_id: str,
    vendor: str,
    product_name: str,
    allocatable_count: int,
    accelerator_model: str,
) -> None:
    """Insert or merge an accelerator aggregate row."""
    key = (resource_type, device_id, vendor)
    if key in aggregates:
        existing_name, existing_count, existing_model = aggregates[key]
        name = existing_name or product_name
        aggregates[key] = (name, existing_count + allocatable_count, existing_model or accelerator_model)
    else:
        aggregates[key] = (product_name, allocatable_count, accelerator_model)


def _add_generic_cpu_count_for_vendor(
    generic_cpu_counts_by_vendor: dict[str, int],
    cpu_family_count: str | None,
    cpu_vendor: str,
) -> None:
    """Track generic CPU counts from family labels for later model folding."""
    if not cpu_family_count:
        return
    try:
        generic_cpu_counts_by_vendor[cpu_vendor] = generic_cpu_counts_by_vendor.get(cpu_vendor, 0) + int(
            cpu_family_count
        )
    except (TypeError, ValueError):
        return


def _apply_generic_cpu_fallbacks(
    aggregates: dict[tuple[ClusterAcceleratorType, str, str], tuple[str, int, str]],
    generic_cpu_counts_by_vendor: dict[str, int],
    discovered_cpu_models_by_vendor: dict[str, set[str]],
) -> None:
    """Fold generic CPU counts into a concrete model when unambiguous."""
    for cpu_vendor, generic_count in generic_cpu_counts_by_vendor.items():
        candidate_models = discovered_cpu_models_by_vendor.get(cpu_vendor, set())
        if len(candidate_models) == 1:
            cpu_model = next(iter(candidate_models))
            _upsert_accelerator_aggregate(
                aggregates=aggregates,
                resource_type=ClusterAcceleratorType.CPU,
                device_id=cpu_model,
                vendor=cpu_vendor,
                product_name="",
                allocatable_count=generic_count,
                accelerator_model=cpu_model,
            )
            continue

        _upsert_accelerator_aggregate(
            aggregates=aggregates,
            resource_type=ClusterAcceleratorType.CPU,
            device_id="CPU",
            vendor=cpu_vendor,
            product_name="",
            allocatable_count=generic_count,
            accelerator_model="CPU",
        )


def _node_labels_and_allocatable(node: object) -> tuple[dict[str, str], dict[str, str]]:
    """Return node labels and allocatable maps with safe defaults."""
    labels = node.metadata.labels if hasattr(node, "metadata") and node.metadata else {}
    allocatable = node.status.allocatable if hasattr(node, "status") and node.status else {}
    return labels, allocatable


def _gpu_identity_from_labels(labels: dict[str, str]) -> tuple[str | None, str | None]:
    """Return (gpu_device_id, gpu_product_name) from known AMD GPU labels."""
    gpu_device_id = labels.get(AMD_GPU_DEVICE_ID_LABEL) or labels.get(AMD_GPU_DEVICE_ID_LABEL_BETA)
    gpu_product_label = labels.get(AMD_GPU_PRODUCT_NAME_LABEL) or labels.get(AMD_GPU_PRODUCT_NAME_LABEL_BETA)
    gpu_product_name = gpu_product_label.replace("_", " ") if gpu_product_label else None
    return gpu_device_id, gpu_product_name


def _resolve_accelerator_entry_fields(
    accelerator_model: str,
    is_gpu_node: bool,
    vendors_by_type: dict[ClusterAcceleratorType, str],
    gpu_device_id: str | None,
    gpu_product_name: str | None,
) -> tuple[ClusterAcceleratorType, str, str, str]:
    """Resolve output fields for one accelerator model count entry."""
    resource_type = _accelerator_resource_type(accelerator_model)
    if resource_type == ClusterAcceleratorType.UNKNOWN and is_gpu_node:
        resource_type = ClusterAcceleratorType.GPU
    vendor = vendors_by_type.get(resource_type, "")
    if resource_type == ClusterAcceleratorType.GPU:
        return resource_type, vendor, gpu_device_id or accelerator_model, gpu_product_name or ""
    return resource_type, vendor, accelerator_model, ""


def _process_ready_node_accelerators(
    node: object,
    aggregates: dict[tuple[ClusterAcceleratorType, str, str], tuple[str, int, str]],
    generic_cpu_counts_by_vendor: dict[str, int],
    discovered_cpu_models_by_vendor: dict[str, set[str]],
) -> None:
    """Extract accelerator counts from one ready node and merge into aggregates."""
    model_counts = node_aim_accelerator_model_counts(node)
    labels, allocatable = _node_labels_and_allocatable(node)
    vendors_by_type = _aim_vendor_by_resource_type(labels)
    if not model_counts:
        _add_generic_cpu_count_for_vendor(
            generic_cpu_counts_by_vendor=generic_cpu_counts_by_vendor,
            cpu_family_count=labels.get(f"{AIM_ACCELERATOR_LABEL_PREFIX}CPU"),
            cpu_vendor=vendors_by_type.get(ClusterAcceleratorType.CPU, ""),
        )
        return

    gpu_device_id, gpu_product_name = _gpu_identity_from_labels(labels)
    is_gpu_node = _is_gpu_labeled_node(labels, allocatable)

    has_specific_cpu_model = any(
        _accelerator_resource_type(model) == ClusterAcceleratorType.CPU for model in model_counts
    )
    if not has_specific_cpu_model:
        _add_generic_cpu_count_for_vendor(
            generic_cpu_counts_by_vendor=generic_cpu_counts_by_vendor,
            cpu_family_count=labels.get(f"{AIM_ACCELERATOR_LABEL_PREFIX}CPU"),
            cpu_vendor=vendors_by_type.get(ClusterAcceleratorType.CPU, ""),
        )

    for accelerator_model, allocatable_count in model_counts.items():
        resource_type, vendor, device_id, product_name = _resolve_accelerator_entry_fields(
            accelerator_model=accelerator_model,
            is_gpu_node=is_gpu_node,
            vendors_by_type=vendors_by_type,
            gpu_device_id=gpu_device_id,
            gpu_product_name=gpu_product_name,
        )
        if resource_type == ClusterAcceleratorType.CPU and accelerator_model != "CPU":
            discovered_cpu_models_by_vendor.setdefault(vendor, set()).add(accelerator_model)
        _upsert_accelerator_aggregate(
            aggregates=aggregates,
            resource_type=resource_type,
            device_id=device_id,
            vendor=vendor,
            product_name=product_name,
            allocatable_count=allocatable_count,
            accelerator_model=accelerator_model,
        )
