# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Business logic for the inference capability.

The router is intentionally thin and delegates here for the operations
that carry inference-specific orchestration:

- ``list_inference_deployments`` dispatches between the chattable and
  general listing paths based on capability, applying status filters on
  the Python side when the chat path is taken (the chattable gateway does
  not accept a status filter today). When the caller asks for
  ``statusFilter=Deleted``, this function additionally merges in
  DB-persisted historical records (the live K8s catalog never returns
  ``Deleted``; that status is API-only).
- ``update_inference_deployment`` decides which spec mutations a PATCH
  asks for and dispatches to ``aims.service``, refusing only an empty
  body. It raises ``ValidationException`` so the FastAPI exception handler
  maps it to a 400 — keeping HTTP concerns out of the service layer.

Pass-through router calls (deploy/get/undeploy/metric/catalog) continue to
hit ``aims.service`` directly — wrapping them here would add dead
indirection without adding value.
"""

from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api_common.collections import PaginatedResult, paginate_list
from api_common.exceptions import ValidationException

from ..aims import repository as aims_repository
from ..aims import service as aims_service
from ..aims.enums import AIMServiceStatus
from ..aims.models import AIMService as AIMServiceRow
from ..aims.schemas import AIMServiceResponse
from ..config import SUBMITTER_ANNOTATION
from ..dispatch.crds import K8sMetadata
from ..dispatch.kube_client import KubernetesClient
from ..minio import MinioClient
from ..workloads.constants import WORKLOAD_ID_LABEL
from .enums import InferenceCapability
from .schemas import InferencePatchRequest


def _historical_row_to_response(row: AIMServiceRow) -> AIMServiceResponse:
    """Shape a DB-persisted historical AIMService row as an ``AIMServiceResponse``.

    Historical rows describe deployments that have been undeployed (or otherwise
    removed from the cluster). Only the columns persisted in PostgreSQL are
    available — there's no live K8s ``status`` block, no routing, no conditions.
    We populate the minimum the UI needs (id via workload-id label, model name,
    status, namespace, creation timestamp) so the response sits cleanly in the
    same ``AIMServiceResponse[]`` list as live deployments. Computed fields like
    ``endpoints`` naturally return ``{}`` because no chattable conditions are
    True, so the UI history panel can rely on ``statusValue == "Deleted"`` to
    branch its rendering without a separate response shape.

    The submitter annotation mirrors what live K8s resources carry, so the UI
    detail page can render "Created by" for deleted entries without a separate
    code path. ``created_by`` may be NULL on legacy rows; we omit the annotation
    rather than emitting a misleading empty string.

    Note: ``metadata.name`` is set to the deployment UUID (the original K8s
    resource name is not persisted in the DB row).
    """
    annotations: dict[str, str] = {}
    if row.created_by:
        annotations[SUBMITTER_ANNOTATION] = row.created_by
    return AIMServiceResponse.model_validate(
        {
            "metadata": K8sMetadata(
                name=str(row.id),
                namespace=row.namespace,
                labels={WORKLOAD_ID_LABEL: str(row.id)},
                annotations=annotations,
                creation_timestamp=row.created_at,
            ),
            "spec": {"model": {"name": row.model}, "replicas": 0},
            "status": {"status": AIMServiceStatus(row.status)},
        }
    )


async def list_inference_deployments(
    kube_client: KubernetesClient,
    project: str,
    capability: InferenceCapability | None,
    status_filter: list[AIMServiceStatus] | None,
    session: AsyncSession,
    page: int = 1,
    page_size: int = 10,
) -> PaginatedResult[AIMServiceResponse]:
    # When the caller asks for AIMServiceStatus.DELETED, the live K8s catalog
    # cannot satisfy it (DELETED is an API-only status, never set by the engine);
    # we fold in the DB history rows so a single list endpoint surfaces both
    # live and undeployed services. This powers the UI's historical-services
    # panel on the AIM detail page without resurrecting the old
    # /aims/services/history route.
    include_history = status_filter is not None and AIMServiceStatus.DELETED in status_filter
    # K8s never returns DELETED, so passing it through the live filter wastes a
    # call. If DELETED is the *only* filter value, skip the K8s lookup entirely.
    live_status_filter: list[AIMServiceStatus] | None = (
        [s for s in status_filter if s is not AIMServiceStatus.DELETED] if status_filter else None
    )

    if status_filter and not live_status_filter:
        # Filter is ["Deleted"] alone — nothing live can match, even with a capability filter.
        live_services = []
    elif capability is InferenceCapability.CHAT:
        live_services = await aims_service.list_chattable_aim_services(kube_client, project)
        if live_status_filter:
            live_services = [s for s in live_services if s.status.status in live_status_filter]
    elif capability is InferenceCapability.TRANSCRIPTION:
        live_services = await aims_service.list_transcribable_aim_services(kube_client, project)
        if live_status_filter:
            live_services = [s for s in live_services if s.status.status in live_status_filter]
    else:
        live_services = await aims_service.list_aim_services(kube_client, project, status_filter=live_status_filter)

    historical_services: list[AIMServiceResponse] = []
    if include_history:
        historical_rows = await aims_repository.list_aim_services_history(
            session, namespace=project, status=AIMServiceStatus.DELETED
        )
        historical_services = [_historical_row_to_response(row) for row in historical_rows]

    services = live_services + historical_services
    # Paginate after filtering so `total` reflects the filtered view, not the
    # raw K8s response.
    return paginate_list(services, page=page, page_size=page_size)


async def update_inference_deployment(
    kube_client: KubernetesClient,
    project: str,
    id: UUID,
    patch_request: InferencePatchRequest,
    minio_client: MinioClient | None = None,
) -> AIMServiceResponse:
    # ScalingPolicyMixin's validator has already rejected a partial trio, so autoScaling being set
    # is the same thing as the scaling policy having been asked for.
    if patch_request.auto_scaling is None and patch_request.adapters is None:
        raise ValidationException(
            "Nothing to update: supply adapters, or all scaling fields (minReplicas, maxReplicas, autoScaling)."
        )
    scaling = None
    if patch_request.auto_scaling is not None:
        # cast() narrows the types without runtime overhead, and survives `python -O` (unlike
        # `assert`); the model validators have already established each value is set.
        scaling = aims_service.ScalingPolicy(
            min_replicas=cast(int, patch_request.min_replicas),
            max_replicas=cast(int, patch_request.max_replicas),
            auto_scaling=patch_request.auto_scaling,
        )
    return await aims_service.update_aim_service_spec(
        kube_client=kube_client,
        namespace=project,
        id=id,
        adapters=patch_request.adapters,
        scaling=scaling,
        minio_client=minio_client,
    )
