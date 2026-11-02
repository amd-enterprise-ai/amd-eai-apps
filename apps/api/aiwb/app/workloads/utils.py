# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import time
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

import yaml
from kubernetes.client import ApiException, V1DeploymentStatus, V1JobStatus
from loguru import logger

from ..config import CLUSTER_HOST, SUBMITTER_ANNOTATION
from ..dispatch.kube_client import KubernetesClient, get_dynamic_client
from ..dispatch.utils import sanitize_label_value
from .constants import (
    CHART_ID_LABEL,
    DATASET_ID_LABEL,
    DEPLOYMENT_COND_AVAILABLE,
    DEPLOYMENT_COND_PROGRESSING,
    DEPLOYMENT_COND_REPLICA_FAILURE,
    DEPLOYMENT_REASON_DEADLINE_EXCEEDED,
    DEPLOYMENT_RESOURCE,
    DISPLAY_NAME_ANNOTATION,
    JOB_COND_COMPLETE,
    JOB_COND_FAILED,
    JOB_COND_FAILURE_TARGET,
    JOB_COND_SUSPENDED,
    JOB_RESOURCE,
    WORKLOAD_ID_LABEL,
    WORKLOAD_TYPE_LABEL,
)
from .enums import WorkloadStatus
from .models import Workload

if TYPE_CHECKING:
    # Imported under TYPE_CHECKING to avoid circular import with schemas.py at runtime.
    from .schemas import WorkloadResourceType


def get_resource_type(manifest: str) -> "WorkloadResourceType":
    """Extract the WorkloadResourceType from an AIWB workload manifest.

    AIWB chart-based workloads always contain either a Deployment or a Job as the
    primary resource — the Helm chart guarantees this.

    Raises:
        ValueError: If the manifest is empty, malformed, or lacks a Deployment/Job.
    """
    # Local import to avoid circular dependency with schemas.py at runtime.
    from .schemas import WorkloadResourceType  # noqa: PLC0415

    try:
        for doc in yaml.safe_load_all(manifest):
            if not doc or not isinstance(doc, dict):
                continue
            kind = doc.get("kind")
            if kind in {DEPLOYMENT_RESOURCE, JOB_RESOURCE}:
                return WorkloadResourceType(kind)
    except yaml.YAMLError as e:
        raise ValueError(f"Malformed manifest YAML: {e}") from e
    raise ValueError("Manifest has no Deployment or Job")


def derive_deployment_status(status: V1DeploymentStatus | None) -> WorkloadStatus:
    """Derive a WorkloadStatus from a V1DeploymentStatus.

    Checks conditions first (failure, available, deadline exceeded),
    then falls back to replica counts.
    """
    if status is None:
        return WorkloadStatus.PENDING

    conditions = {c.type: c for c in (status.conditions or [])}

    replica_failure = conditions.get(DEPLOYMENT_COND_REPLICA_FAILURE)
    if replica_failure and replica_failure.status == "True":
        return WorkloadStatus.FAILED

    available = conditions.get(DEPLOYMENT_COND_AVAILABLE)
    if available and available.status == "True":
        return WorkloadStatus.RUNNING

    progressing = conditions.get(DEPLOYMENT_COND_PROGRESSING)
    if progressing:
        if getattr(progressing, "reason", None) == DEPLOYMENT_REASON_DEADLINE_EXCEEDED:
            return WorkloadStatus.FAILED
        if progressing.status == "True":
            return WorkloadStatus.PENDING

    if status.ready_replicas and status.ready_replicas > 0:
        return WorkloadStatus.RUNNING

    return WorkloadStatus.PENDING


def derive_job_status(status: V1JobStatus | None) -> WorkloadStatus:
    """Derive a WorkloadStatus from a V1JobStatus.

    Checks conditions first (failed, complete, suspended),
    then falls back to pod counters (active, ready, succeeded, failed).
    Active pods that aren't ready are treated as Pending.
    """
    if status is None:
        return WorkloadStatus.PENDING

    conditions = {c.type: c.status for c in (status.conditions or [])}

    if conditions.get(JOB_COND_FAILED) == "True":
        return WorkloadStatus.FAILED
    if conditions.get(JOB_COND_FAILURE_TARGET) == "True":
        return WorkloadStatus.FAILED
    if conditions.get(JOB_COND_COMPLETE) == "True":
        return WorkloadStatus.COMPLETE
    if conditions.get(JOB_COND_SUSPENDED) == "True":
        return WorkloadStatus.PENDING

    if status.active and status.active > 0:
        if status.ready and status.ready > 0:
            return WorkloadStatus.RUNNING
        return WorkloadStatus.PENDING
    if status.succeeded and status.succeeded > 0:
        return WorkloadStatus.COMPLETE
    if status.failed and status.failed > 0:
        return WorkloadStatus.FAILED

    return WorkloadStatus.PENDING


async def apply_manifest(
    kube_client: KubernetesClient,
    manifest: str,
    workload: Workload,
    namespace: str,
    submitter: str,
    extra_labels: dict[str, str] | None = None,
    extra_annotations: dict[str, str] | None = None,
) -> None:
    """Apply Kubernetes manifest with workload metadata injection.

    This function:
    - Parses the YAML manifest
    - Injects namespace, workload labels, and submitter annotation into each resource
    - Applies resources using Kubernetes Python client (create or update)

    Args:
        kube_client: KubernetesClient instance for Kubernetes operations
        manifest: YAML manifest string to apply (can contain multiple documents)
        workload: The workload instance containing metadata to inject
        namespace: Kubernetes namespace
        submitter: User identifier (e.g. email) who submitted the workload
        extra_labels: Additional labels to inject into primary workload resources (Job/Deployment)
        extra_annotations: Additional annotations to inject into primary workload resources

    Raises:
        RuntimeError: If applying manifest fails
    """
    dyn_client = await asyncio.to_thread(get_dynamic_client)
    documents = list(yaml.safe_load_all(manifest))

    for doc in documents:
        if not doc or not isinstance(doc, dict):
            continue

        api_version = doc.get("apiVersion")
        kind = doc.get("kind")

        if not api_version or not kind:
            continue

        # Ensure metadata exists
        if "metadata" not in doc:
            doc["metadata"] = {}

        # Inject namespace
        doc["metadata"]["namespace"] = namespace

        # Inject workload labels for tracking and auto-discovery
        if "labels" not in doc["metadata"]:
            doc["metadata"]["labels"] = {}

        labels = doc["metadata"]["labels"]

        # All resources get workload-id for tracking
        labels[WORKLOAD_ID_LABEL] = str(workload.id)

        # Only primary workload resources get full metadata for auto-discovery.
        if kind in {DEPLOYMENT_RESOURCE, JOB_RESOURCE}:
            labels[CHART_ID_LABEL] = str(workload.chart_id)
            labels[WORKLOAD_TYPE_LABEL] = sanitize_label_value(str(workload.type))
            if workload.dataset_id:
                labels[DATASET_ID_LABEL] = str(workload.dataset_id)
            if extra_labels:
                for key, value in extra_labels.items():
                    labels[key] = sanitize_label_value(value)

        # Inject submitter annotation
        if "annotations" not in doc["metadata"]:
            doc["metadata"]["annotations"] = {}
        doc["metadata"]["annotations"][SUBMITTER_ANNOTATION] = submitter
        if kind in {DEPLOYMENT_RESOURCE, JOB_RESOURCE}:
            doc["metadata"]["annotations"][DISPLAY_NAME_ANNOTATION] = workload.display_name
            if extra_annotations:
                doc["metadata"]["annotations"].update(extra_annotations)

        name = doc["metadata"].get("name", "unknown")
        logger.debug(f"Applying {kind}/{name} with workload-id {workload.id}")

        try:
            api_resource = dyn_client.resources.get(api_version=api_version, kind=kind)
            api_resource.create(body=doc, namespace=namespace if api_resource.namespaced else None)
            logger.debug(f"Created {kind}/{name}")
        except ApiException as e:
            if e.status == 409:
                # Resource already exists - log and continue (idempotent behavior)
                logger.debug(f"{kind}/{name} already exists, skipping")
            else:
                error_msg = f"Failed to create {kind}/{name}: {e.body if hasattr(e, 'body') else str(e)}"
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e


def generate_workload_name(workload: Workload) -> str:
    """
    Generate a unique name for a managed workload.

    mw-{chart_name}-{timestamp}-{uuid_prefix} (max 53 chars)
    """
    uuid_prefix = str(workload.id)[:4]
    timestamp = str(int(time.time()))[:10]
    prefix = workload.chart.name.replace(" ", "-").replace("_", "-")[:33]
    return f"wb-{prefix}-{timestamp}-{uuid_prefix}"[:53]


def generate_display_name(workload: Workload) -> str:
    """
    Generate a display name for a managed workload.

    Callers that know a human-readable handle (e.g. the FT flow uses the
    finetuning job name) should set ``workload.display_name`` explicitly
    before creation; this fallback only runs when no display name was
    provided.
    """
    uuid_prefix = str(workload.id)[:8]
    return f"{workload.chart.name}-{uuid_prefix}"  # caller must pass a DB-attached Workload so chart is loaded


def get_workload_internal_url(workload_name: str, namespace: str) -> str:
    """Get the full internal URL for a workload.

    Returns the complete URL with http:// protocol for accessing the workload internally.

    Args:
        workload_name: Name of the workload resource
        namespace: Kubernetes namespace

    Returns:
        Full internal URL with protocol (e.g., http://workload-name.namespace.svc.cluster.local)
    """
    return f"http://{workload_name}.{namespace}.svc.cluster.local"


def get_workload_host_from_HTTPRoute_manifest(*, manifest: str, cluster_host: str = CLUSTER_HOST) -> str | None:
    """Extract the external URL from an HTTPRoute manifest, or None if undeterminable.

    The host is taken from the route's own ``spec.hostnames`` when present, so the
    advertised URL always matches the host the route is actually served on
    (workspaces land on ``workspaces.<domain>`` once pinned by ``apply_manifest``;
    anything on ``workloads.<domain>`` — e.g. inference — keeps that host). A pinned
    hostname only replaces the host portion of ``cluster_host``; its scheme and port
    are preserved so non-default ports (e.g. local ``http://localhost:8080``) survive.
    Routes that declare no hostnames fall back to ``cluster_host`` verbatim.
    """
    try:
        docs = list(yaml.safe_load_all(manifest))
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse manifest YAML: {e}")
        return None

    for doc in docs:
        if not doc or not isinstance(doc, dict):
            continue

        if doc.get("kind") != "HTTPRoute":
            continue

        # Prefer the route's own pinned hostname; fall back to the configured host.
        # Swap only the host of cluster_host, keeping its scheme and port so a pinned
        # hostname stays reachable on non-default ports (e.g. local http://localhost:8080).
        hostnames = doc.get("spec", {}).get("hostnames") or []
        if hostnames:
            parsed = urlparse(cluster_host)
            scheme = parsed.scheme or "https"
            netloc = f"{hostnames[0]}:{parsed.port}" if parsed.port else hostnames[0]
            base_url = f"{scheme}://{netloc}"
        else:
            base_url = cluster_host
        if not base_url:
            logger.warning("No route hostname and cluster host is not set - external URL unavailable")
            return None

        for rule in doc.get("spec", {}).get("rules", []):
            for match in rule.get("matches", []):
                path = match.get("path", {})

                if path.get("type") == "PathPrefix":
                    path_value = path.get("value")
                    if path_value:
                        return urljoin(base_url, path_value)

    logger.warning("Could not determine external URL from HTTPRoute manifest: no PathPrefix found")
    return None


def sanitize_user_id(email: str) -> str:
    """
    Sanitize user email to be used as Kubernetes resource name components.
    Replaces @, ., _, and + with dashes to ensure valid DNS-compatible names.
    """
    return email.lower().replace("@", "-").replace(".", "-").replace("_", "-").replace("+", "-")
