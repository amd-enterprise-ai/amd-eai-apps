# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Utility functions for dispatch operations."""

from uuid import UUID

from kubernetes_asyncio import client
from loguru import logger

from .kube_client import get_kube_client


async def get_resource_version(group: str, plural: str) -> str | None:
    """Get the version of a Kubernetes resource (core or CRD).

    Handles both core API resources (e.g., services, configmaps) and custom resources.
    For core API resources (empty group), returns "v1" directly without querying.

    Args:
        group: The API group of the resource. Empty string "" for core API resources.
        plural: The plural name of the resource (e.g., "services", "aimclustermodels")

    Returns:
        The version string if found, None otherwise.
        - "v1" for core API resources (group=="")
        - Storage version for CRDs, falls back to first served version
    """
    # Core API resources don't need version lookup
    if group == "":
        return "v1"

    try:
        kube_client = get_kube_client()
        crd_name = f"{plural}.{group}"
        crd_obj = await kube_client.api_extensions.read_custom_resource_definition(crd_name)

        # Prefer storage version
        for ver in crd_obj.spec.versions:
            if ver.storage:
                return ver.name

        # Fallback to first served version
        for ver in crd_obj.spec.versions:
            if ver.served:
                return ver.name

        return None
    except client.ApiException as e:
        if e.status == 404:
            logger.debug(f"CRD {plural}.{group} not found")
        else:
            logger.exception(f"Error checking CRD {plural}.{group}")
        return None


def parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def sanitize_label_value(value: str, max_length: int = 63) -> str:
    """
    Sanitize a string to be a valid Kubernetes label value.

    Kubernetes label values must:
    - Be empty or consist of alphanumeric characters, '-', '_' or '.'
    - Start and end with an alphanumeric character
    - Be at most 63 characters

    Args:
        value: The string to sanitize
        max_length: Maximum length for the label value (default 63 for Kubernetes)

    Returns:
        Sanitized string that conforms to Kubernetes label value requirements
    """
    if not value:
        return ""

    # Replace spaces, special characters with hyphens
    sanitized_chars = []
    for char in value:
        if char.isalnum() or char in ("-", "_", "."):
            sanitized_chars.append(char)
        elif char in (" ", "/"):
            sanitized_chars.append("-")
        # Skip other special characters

    sanitized = "".join(sanitized_chars)
    # Remove leading/trailing hyphens and non-alphanumeric characters
    sanitized = sanitized.strip("-_.")

    # Ensure it starts and ends with alphanumeric
    while sanitized and not sanitized[0].isalnum():
        sanitized = sanitized[1:]
    while sanitized and not sanitized[-1].isalnum():
        sanitized = sanitized[:-1]

    # Truncate to max length
    sanitized = sanitized[:max_length]

    # Truncation can cut on a separator, invalidating the final character.
    # Re-apply edge cleanup so start/end remain alphanumeric.
    while sanitized and not sanitized[0].isalnum():
        sanitized = sanitized[1:]
    while sanitized and not sanitized[-1].isalnum():
        sanitized = sanitized[:-1]

    return sanitized or "unknown"
