# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Gateway for accessing workload resources from Kubernetes."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import yaml
from kubernetes.client import ApiException, V1DeleteOptions
from loguru import logger

from ..config import SUBMITTER_ANNOTATION
from ..dispatch.kube_client import get_dynamic_client, get_kube_client
from ..dispatch.utils import parse_uuid
from .constants import (
    CANONICAL_NAME_LABEL,
    CHART_ID_LABEL,
    DATASET_ID_LABEL,
    DEPLOYMENT_RESOURCE,
    DISPLAY_NAME_ANNOTATION,
    JOB_RESOURCE,
    WORKLOAD_ID_LABEL,
    WORKLOAD_RESOURCES,
    WORKLOAD_TYPE_LABEL,
)
from .enums import WorkloadStatus, WorkloadType
from .models import Workload
from .utils import derive_deployment_status, derive_job_status


def _fetch_httproute_manifest(workload_id: UUID, namespace: str) -> str:
    """Fetch the HTTPRoute for a workload from Kubernetes and return it as a YAML string.

    Uses the sync dynamic client (HTTPRoute is a CRD not covered by the typed async client).
    Returns an empty string if no HTTPRoute is found or the client is unavailable.
    """
    try:
        dynamic_client = get_dynamic_client()
    except RuntimeError:
        return ""

    label_selector = f"{WORKLOAD_ID_LABEL}={workload_id}"
    try:
        httproute_resource = dynamic_client.resources.get(api_version="gateway.networking.k8s.io/v1", kind="HTTPRoute")
        result = httproute_resource.get(namespace=namespace, label_selector=label_selector)
        items = result.items if result.items else []
        if not items:
            return ""
        return yaml.dump(items[0].to_dict())
    except Exception:
        logger.exception(f"Error reading HTTPRoute for workload {workload_id}")
        return ""


async def get_workload_from_k8s(
    workload_id: UUID,
    namespace: str,
) -> Workload | None:
    """Get a workload by querying Kubernetes resources with the workload-id label.

    Checks Deployments first (for inference/workspace workloads), then Jobs
    (for training workloads). Returns a transient Workload built from K8s labels
    and live status, without touching the database.

    Returns None if no matching resource is found in the cluster.
    """
    try:
        kube_client = get_kube_client()
    except RuntimeError:
        return None  # K8s client not available

    label_selector = f"{WORKLOAD_ID_LABEL}={workload_id}"

    try:
        deployments = await kube_client.apps_v1.list_namespaced_deployment(
            namespace=namespace,
            label_selector=label_selector,
        )
        if deployments.items:
            item = deployments.items[0]
            status = derive_deployment_status(item.status)
            manifest = await asyncio.to_thread(_fetch_httproute_manifest, workload_id, namespace)
            return _workload_from_k8s_resource(item, status, namespace, manifest)
    except Exception:
        logger.exception(f"Error reading deployment for workload {workload_id}")

    try:
        jobs = await kube_client.batch_v1.list_namespaced_job(
            namespace=namespace,
            label_selector=label_selector,
        )
        if jobs.items:
            item = jobs.items[0]
            status = derive_job_status(item.status)
            manifest = await asyncio.to_thread(_fetch_httproute_manifest, workload_id, namespace)
            return _workload_from_k8s_resource(item, status, namespace, manifest)
    except Exception:
        logger.exception(f"Error reading job for workload {workload_id}")

    return None


async def get_finetuning_workloads_annotations(
    namespace: str,
    workload_ids: list[UUID],
) -> dict[UUID, dict[str, str]]:
    """Return Kubernetes annotations indexed by fine-tuning workload ID."""
    workload_ids = list(dict.fromkeys(workload_ids))
    if not workload_ids:
        return {}

    try:
        kube_client = get_kube_client()
    except RuntimeError:
        return {}

    workload_id_selector = ",".join(str(workload_id) for workload_id in workload_ids)
    try:
        jobs = await kube_client.batch_v1.list_namespaced_job(
            namespace=namespace,
            label_selector=(
                f"{WORKLOAD_TYPE_LABEL}={WorkloadType.FINE_TUNING.value},"
                f"{WORKLOAD_ID_LABEL} in ({workload_id_selector})"
            ),
        )
    except Exception:
        logger.exception(f"Error reading fine-tuning workload annotations in namespace {namespace}")
        return {}

    annotations_by_workload: dict[UUID, dict[str, str]] = {}
    for job in jobs.items:
        labels = job.metadata.labels or {}
        workload_id = parse_uuid(labels.get(WORKLOAD_ID_LABEL))
        if workload_id is not None:
            annotations_by_workload[workload_id] = job.metadata.annotations or {}
    return annotations_by_workload


def _workload_from_k8s_resource(resource: Any, status: WorkloadStatus, namespace: str, manifest: str = "") -> Workload:
    """Construct a transient Workload from a Kubernetes resource object.

    Reads workload metadata from resource labels and annotations, which are
    stamped at deploy time by apply_manifest. The returned object is not
    persisted to or managed by any database session.

    Note on ``workload_type`` fallback: when ``WORKLOAD_TYPE_LABEL`` is absent,
    the resource is assumed to be ``FINE_TUNING``. This is a historical
    compatibility default — every K8s resource produced by AIWB stamps the
    label, but older workloads (which were only ever fine-tuning jobs)
    may lack it. Type-scoped endpoints that gate on ``workload.type`` are
    therefore weaker than they appear for label-less legacy resources.

    TODO: drop the FINE_TUNING fallback once all legacy workloads
    have been backfilled with the label, so missing-label resources surface
    as a real error rather than being silently classified.
    """
    labels = resource.metadata.labels or {}
    annotations = resource.metadata.annotations or {}

    workload_id = labels.get(WORKLOAD_ID_LABEL)
    chart_id = labels.get(CHART_ID_LABEL)
    dataset_id = labels.get(DATASET_ID_LABEL)
    display_name = annotations.get(DISPLAY_NAME_ANNOTATION, "")
    workload_type = labels.get(WORKLOAD_TYPE_LABEL, WorkloadType.FINE_TUNING)
    submitter = annotations.get(SUBMITTER_ANNOTATION, "")

    created_at = resource.metadata.creation_timestamp or datetime.now(UTC)

    workload = Workload(
        id=parse_uuid(workload_id),
        name=resource.metadata.name,
        display_name=display_name,
        namespace=namespace,
        type=workload_type,
        status=status,
        chart_id=parse_uuid(chart_id),
        dataset_id=parse_uuid(dataset_id),
        created_by=submitter,
        updated_by=submitter,
        created_at=created_at,
        updated_at=created_at,
        manifest=manifest,
    )
    workload.annotations = annotations
    return workload


async def get_workload_canonical_name(workload_id: UUID, namespace: str) -> str | None:
    """Read the canonical-name label from the workload's primary K8s resource.

    Looks up the Deployment (inference/workspace) or Job (training) tagged with
    the workload-id label and returns the ``CANONICAL_NAME_LABEL`` value.

    Returns None if the K8s client is unavailable, no primary resource is
    found, or the label is not set.
    """
    try:
        kube_client = get_kube_client()
    except RuntimeError:
        return None

    label_selector = f"{WORKLOAD_ID_LABEL}={workload_id}"

    for resource_kind, list_fn in (
        (DEPLOYMENT_RESOURCE, kube_client.apps_v1.list_namespaced_deployment),
        (JOB_RESOURCE, kube_client.batch_v1.list_namespaced_job),
    ):
        try:
            result = await list_fn(namespace=namespace, label_selector=label_selector)
        except Exception:
            logger.exception(f"Error reading {resource_kind} for workload {workload_id}")
            continue

        if result.items:
            labels = result.items[0].metadata.labels or {}
            return labels.get(CANONICAL_NAME_LABEL)

    return None


async def delete_workload_resources(
    namespace: str,
    workload_id: str,
) -> None:
    """Delete all Kubernetes resources with the workload-id label.

    Deletes Deployments, Jobs, and any supporting resources (ConfigMaps, Services, HTTPRoutes)
    created by AIWB workload manifests.

    Raises:
        RuntimeError: If any resource deletion fails (excluding 404 not found)
    """
    label_selector = f"{WORKLOAD_ID_LABEL}={workload_id}"

    dynamic_client = await asyncio.to_thread(get_dynamic_client)

    for resource in WORKLOAD_RESOURCES:
        try:
            # Background propagation cascades to dependents (e.g., Kueue Workload owned by Job)
            await asyncio.to_thread(
                dynamic_client.resources.get(api_version=resource.api_version, kind=resource.kind).delete,
                namespace=namespace,
                label_selector=label_selector,
                body=V1DeleteOptions(propagation_policy="Background"),
            )
            logger.debug(f"Deleted {resource.plural} with label {label_selector} from namespace {namespace}")
        except ApiException as e:
            if e.status == 404:
                logger.debug(f"No {resource.plural} found with label {label_selector}")
            else:
                logger.error(f"Failed to delete {resource.plural}: {e}")
                raise RuntimeError(
                    f"Failed to delete Kubernetes resources for workload {workload_id}. Please try again. Error: {e}"
                ) from e

    logger.info(f"Deleted all resources for workload {workload_id} in namespace {namespace}")
