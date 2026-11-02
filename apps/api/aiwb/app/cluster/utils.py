# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Pure helpers for cluster catalog operations (Kubernetes nodes and container image refs)."""

from kubernetes_asyncio.client import V1Node

from .constants import (
    AIM_ACCELERATOR_EXCLUDED_SUFFIX_PREFIXES,
    AIM_ACCELERATOR_LABEL_PREFIX,
    AMD_GPU_DEVICE_ID_LABEL,
    AMD_GPU_DEVICE_ID_LABEL_BETA,
    AMD_GPU_PRODUCT_NAME_LABEL,
    AMD_GPU_PRODUCT_NAME_LABEL_BETA,
    AMD_GPU_RESOURCE,
)


def repository_without_tag(name: str) -> str:
    """Remove an optional ``:tag`` suffix from the name portion of a digest-pinned ref."""
    slash_index = name.rfind("/")
    if slash_index == -1:
        if name.count(":") == 1:
            repository, _, _tag = name.rpartition(":")
            return repository
        return name

    prefix = name[:slash_index]
    path = name[slash_index + 1 :]
    if ":" not in path:
        return name
    path, _, _tag = path.rpartition(":")
    return f"{prefix}/{path}"


def parse_container_image_repository_and_tag(image_ref: str) -> tuple[str, str]:
    """Split a container image reference into repository and tag or digest.

    Supports tagged refs (``repo:tag``, including registries with ports) and
    digest refs (``repo@sha256:...`` or ``repo:tag@sha256:...``). Raises ``ValueError`` when the ref cannot
    be parsed — callers must not silently substitute a different default.
    """
    image_ref = image_ref.strip()
    if not image_ref:
        msg = "image reference must not be empty"
        raise ValueError(msg)

    if "@" in image_ref:
        repository, separator, digest = image_ref.partition("@")
        algorithm, _, encoded = digest.partition(":")
        if not repository or not separator or not algorithm or not encoded:
            msg = f"invalid digest image reference: {image_ref!r}"
            raise ValueError(msg)
        return repository_without_tag(repository), digest

    repository, separator, tag = image_ref.rpartition(":")
    if not separator or not repository or not tag or "/" in tag:
        msg = f"invalid tagged image reference: {image_ref!r}"
        raise ValueError(msg)
    return repository, tag


def is_node_ready(node: V1Node) -> bool:
    """Return True if the node has a Ready=True condition."""
    if not (hasattr(node, "status") and node.status and hasattr(node.status, "conditions")):
        return False
    for condition in node.status.conditions or []:
        if condition.type == "Ready" and condition.status == "True":
            return True
    return False


def node_device_id_and_product_name(node: V1Node) -> tuple[str, str] | None:
    """Return (device_id, product_name) when the node carries an AMD GPU device-id label."""
    if not (hasattr(node, "metadata") and node.metadata):
        return None
    labels = node.metadata.labels or {}
    device_id = labels.get(AMD_GPU_DEVICE_ID_LABEL) or labels.get(AMD_GPU_DEVICE_ID_LABEL_BETA)
    if not device_id:
        return None
    product_name = labels.get(AMD_GPU_PRODUCT_NAME_LABEL) or labels.get(AMD_GPU_PRODUCT_NAME_LABEL_BETA)
    display = product_name.replace("_", " ") if product_name else device_id
    return device_id, display


def preferred_accelerator_product_name(device_id: str, *candidates: str) -> str:
    """Pick the best display name when aggregating nodes that share a device id."""
    for candidate in candidates:
        if candidate != device_id:
            return candidate
    return device_id


def get_amd_gpu_allocatable_from_node(node: dict) -> int:
    """Return allocatable ``amd.com/gpu`` units on the node (0 when absent)."""
    allocatable = node.get("status", {}).get("allocatable", {})
    amd_gpus = allocatable.get(AMD_GPU_RESOURCE, "0")
    if not amd_gpus or amd_gpus == "0":
        return 0
    return int(amd_gpus)


def node_aim_gpu_accelerator_model(node: V1Node) -> str | None:
    """Resolve the canonical GPU ``acceleratorModel`` from aim-engine node labels."""
    if not (hasattr(node, "metadata") and node.metadata):
        return None
    candidates: list[str] = []
    for key in node.metadata.labels or {}:
        if not key.startswith(AIM_ACCELERATOR_LABEL_PREFIX):
            continue
        suffix = key[len(AIM_ACCELERATOR_LABEL_PREFIX) :]
        if not suffix or suffix.startswith(AIM_ACCELERATOR_EXCLUDED_SUFFIX_PREFIXES):
            continue
        candidates.append(suffix)
    return candidates[0] if candidates else None


def node_aim_accelerator_model_counts(node: V1Node) -> dict[str, int]:
    """Return per-model accelerator counts from aim-engine node labels."""
    if not (hasattr(node, "metadata") and node.metadata):
        return {}
    model_counts: dict[str, int] = {}
    for key, value in (node.metadata.labels or {}).items():
        if not key.startswith(AIM_ACCELERATOR_LABEL_PREFIX):
            continue
        suffix = key[len(AIM_ACCELERATOR_LABEL_PREFIX) :]
        if not suffix or suffix in {"CPU", "GPU", "APU"} or suffix.startswith(("partitioning-scheme.", "vendor.")):
            continue
        try:
            model_counts[suffix] = model_counts.get(suffix, 0) + int(value)
        except (TypeError, ValueError):
            continue
    return model_counts
