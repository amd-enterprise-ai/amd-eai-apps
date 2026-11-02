# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""AIMService syncer for polling framework."""

import asyncio
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import SUBMITTER_ANNOTATION
from ..dispatch.kube_client import KubernetesClient
from ..projects.gateway import get_namespaces
from ..workloads.constants import WORKLOAD_ID_LABEL
from .enums import AIMServiceStatus
from .gateway import get_aim_by_name, list_aim_services
from .repository import create_aim_service, list_aim_services_history, update_aim_service_status


async def sync_aim_services(session: AsyncSession, kube_client: KubernetesClient) -> None:
    """Sync AIMServices between K8s and DB.

    This syncer performs the following tasks:
    1. Lists all DB objects (using repository functions with models)
    2. Lists all K8s objects (using gateway functions with CRDs)
    3. Updates status of existing objects in DB
    4. Creates new objects in DB that exist in K8s but not in DB
    5. Marks objects as deleted that exist in DB but not in K8s
    """

    # 1. List all DB objects
    db_aim_services = await list_aim_services_history(session=session)
    # Filter to only non-terminal statuses for status updates
    active_db_services = [
        service
        for service in db_aim_services
        if service.status not in [AIMServiceStatus.DELETED, AIMServiceStatus.FAILED]
    ]
    # Map active services by ID for status updates
    db_services_by_id = {service.id: service for service in active_db_services}
    # Map ALL services by ID to prevent duplicate creation
    all_db_services_by_id = {service.id: service for service in db_aim_services}

    # 2. List all K8s objects
    # Get all accessible namespaces (workbench namespaces with project-id label)
    # In standalone mode, this returns only the default namespace
    accessible_namespaces = await get_namespaces(kube_client)
    service_lists = await asyncio.gather(*(list_aim_services(kube_client, ns.name) for ns in accessible_namespaces))
    k8s_aim_services = [svc for sublist in service_lists for svc in sublist]

    # Map by id from labels
    # Only process services that have been labeled by Kyverno/AIRM
    k8s_services_by_id = {}
    for k8s_aim_service in k8s_aim_services:
        id_str = k8s_aim_service.metadata.labels.get(WORKLOAD_ID_LABEL)
        if not id_str:
            # Skip services without workload-id (not yet labeled by Kyverno/AIRM)
            logger.debug(
                f"Skipping AIMService {k8s_aim_service.metadata.namespace}/{k8s_aim_service.metadata.name} - "
                f"no workload-id label (not yet processed by Kyverno/AIRM)"
            )
            continue

        try:
            service_id = UUID(id_str)
            k8s_services_by_id[service_id] = k8s_aim_service
        except ValueError:
            logger.warning(
                f"Invalid workload-id UUID in K8s service "
                f"{k8s_aim_service.metadata.namespace}/{k8s_aim_service.metadata.name}: {id_str}"
            )

    logger.debug(
        f"AIMService sync: {len(db_aim_services)} total in DB "
        f"({len(active_db_services)} active), {len(k8s_services_by_id)} in K8s"
    )

    # 3. Update status of existing objects in DB
    for service_id, k8s_aim_service in k8s_services_by_id.items():
        db_aim_service = db_services_by_id.get(service_id)
        if db_aim_service:
            k8s_status = k8s_aim_service.status.status
            if db_aim_service.status != k8s_status:
                logger.info(f"Updating service {service_id} status: {db_aim_service.status} -> {k8s_status}")
                await update_aim_service_status(session, db_aim_service, k8s_status, updater="system")

    # 4. Create new objects in DB (exist in K8s but not in DB)
    for service_id, service in k8s_services_by_id.items():
        if service_id not in all_db_services_by_id:
            # Validate required fields
            if not service.metadata.namespace:
                logger.debug(f"Skipping AIMService {service.metadata.name} - missing namespace")
                continue

            model_name = service.spec.model.name
            if not model_name:
                logger.debug(f"Skipping AIMService {service.metadata.name} - missing model name")
                continue

            try:
                aim_crd = await get_aim_by_name(kube_client, model_name)
                if not aim_crd:
                    logger.debug(f"Skipping AIMService {service.metadata.name} - AIM {model_name} not found")
                    continue

                # The optimization metric lives in
                # spec.profile.selector.metric (v1alpha2), not the legacy
                # spec.overrides.metric (v1alpha1). When the profile is
                # auto-resolved or chosen by name there's no metric to record.
                profile = service.spec.profile
                selector_metric = profile.selector.get("metric") if profile and profile.selector else None

                await create_aim_service(
                    session=session,
                    namespace=service.metadata.namespace,
                    model=model_name,
                    status=service.status.status,
                    metric=selector_metric,
                    submitter=service.metadata.annotations.get(SUBMITTER_ANNOTATION, "system"),
                    id=service_id,
                )
                logger.info(f"Created new AIMService {service.metadata.namespace}/{service.metadata.name}")
            except Exception as e:
                logger.error(f"Failed to create AIMService {service.metadata.name}: {e}")

    # 5. Mark objects as deleted (exist in DB but not in K8s)
    for service_id, db_aim_service in db_services_by_id.items():
        if service_id not in k8s_services_by_id:
            logger.info(
                f"Service {service_id} (namespace: {db_aim_service.namespace}) not found in K8s - marking as Deleted"
            )
            await update_aim_service_status(session, db_aim_service, AIMServiceStatus.DELETED, updater="system")

    await session.commit()
