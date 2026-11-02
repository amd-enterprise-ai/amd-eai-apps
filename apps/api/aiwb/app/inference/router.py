# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""HTTP interface for the inference capability.

Endpoints are organised to mirror the inference capability shape:
a cluster-wide catalog of base models and a per-project surface
for managing inference deployments.

Path-keying choice
------------------
URLs use ``/v1/projects/{project}/inference/...`` per the convention
established by the fine-tuning capability. The ``ensure_access_to_project``
dependency maps the project identifier 1:1 to the underlying workbench
namespace, so the inference routes plug into the established auth flow
without leaking the internal namespace naming into the API surface.

This module is a thin facade over ``aims.service`` for the capability
surface (``models``, deployments, ``replicas``, metrics).
"""

from textwrap import dedent
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Query, status
from prometheus_api_client import PrometheusConnect
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.auth.security import get_user_email
from api_common.collections import PaginationMetadata, paginate_list
from api_common.database import get_session
from api_common.schemas import ListResponse, QueryParam

from ..aims.crds import AIMProfileResource
from ..aims.gateway import list_aim_service_replicas
from ..aims.schemas import AIMResponse
from ..aims.service import (
    deploy_aim,
    get_aim_by_resource_name,
    get_aim_cluster_profile,
    get_aim_service,
    list_aim_cluster_profiles,
    list_aims,
    undeploy_aim,
)
from ..common_responses import EXTERNAL_SERVICE_RESPONSES, PROJECT_ACCESS_RESPONSES
from ..dispatch.kube_client import KubernetesClient, get_kube_client
from ..metrics.client import get_prometheus_client
from ..metrics.enums import MetricName
from ..metrics.schemas import MetricsScalar, MetricsScalarWithRange, MetricsTimeRange, MetricsTimeseries
from ..metrics.service import get_metric_by_workload_id
from ..minio import MinioClient, get_minio_client_optional
from ..projects.security import ensure_access_to_project
from . import service as inference_service
from .schemas import (
    InferenceDeploymentResponse,
    InferenceDeploymentsList,
    InferenceDeployRequest,
    InferenceModelsList,
    InferencePatchRequest,
    InferenceProfilesList,
    InferenceReplicaResponse,
    ListInferenceDeploymentsQuery,
    ListInferenceModelsQuery,
    ListInferenceProfilesQuery,
)

router = APIRouter(tags=["Inference"])


@router.get(
    "/inference/models",
    response_model=InferenceModelsList,
    summary="List inference base models",
    description=dedent("""
        List the cluster's catalog of base models that can be deployed for
        inference as a paginated envelope (default page size 10, max 100).
        Use `?page=` and `?pageSize=` to navigate; the response includes a
        `pagination` object with `page`, `pageSize`, and `total` alongside `data`.

        Use the `statusFilter` query parameter (repeatable) to return only models
        with matching statuses, e.g. `?statusFilter=Ready&statusFilter=Failed`.

        Use `?acceleratorType=` to narrow the catalog to AIMs whose published
        hardware footprints include that accelerator family — useful for
        picking out EPYC-only or GPU-only models for the deploy picker. The
        parameter is repeatable to OR multiple values, e.g.
        `?acceleratorType=cpu&acceleratorType=gpu`. An AIM matches when any
        entry in its `status.discoveredProfiles.byHardware[]` list has a
        matching `acceleratorType`. Values are case-sensitive lowercase;
        AIMs with no published hardware are excluded when this filter is set.

        Pagination is applied after the filters, so `total` reflects only the
        matching models.
    """),
)
async def list_inference_models_endpoint(
    query: QueryParam[ListInferenceModelsQuery],
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> InferenceModelsList:
    aims = await list_aims(
        kube_client,
        statuses=query.status_filter,
        accelerator_type=query.accelerator_type,
    )
    paginated = paginate_list(aims, page=query.page, page_size=query.page_size)
    return InferenceModelsList(
        data=paginated.items,
        pagination=PaginationMetadata(
            page=paginated.page,
            page_size=paginated.page_size,
            total=paginated.total,
        ),
    )


@router.get(
    "/inference/models/{name}",
    response_model=AIMResponse,
    summary="Get an inference base model",
    description=dedent("""
        Get a single base model from the cluster catalog by its resource
        name (AIMClusterModel metadata.name).
    """),
    responses={
        404: {"description": "AIM cluster model not found."},
    },
)
async def get_inference_model_endpoint(
    name: str = Path(..., description="AIMClusterModel resource name"),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> AIMResponse:
    return await get_aim_by_resource_name(kube_client, name)


@router.get(
    "/inference/profiles",
    response_model=InferenceProfilesList,
    summary="List inference base model profiles",
    description=dedent("""
        List AIMClusterProfile resources as a paginated envelope (default
        page size 10, max 100). Use `?page=` and `?pageSize=` to navigate.

        Pass `?aimId=<canonical-id>` to narrow the result set. The query
        parameter is repeatable to batch several models into one round-trip
        (`?aimId=meta-llama/Llama-3&aimId=Cohere/cmd-a`). The `aimId`
        corresponds to the AIMClusterModel's `status.aimId` (e.g.
        `CohereLabs/command-a-reasoning-08-2025`) and matches each profile's
        `spec.aimId`. Callers should prefer the `aimId` they already have
        from the catalog response rather than indirecting through a
        resource name — the engine reconciles `status.aimId` asynchronously.

        Each profile captures a pre-validated serving configuration for the
        model: optimization metric (latency vs throughput), accelerator
        model and count, precision, and an availability flag that reflects
        whether the cluster currently has the hardware to run it.

        Returns 200 + empty `data` when no profiles match — no 404 is
        emitted for an unknown `aimId`.
    """),
)
async def list_inference_profiles_endpoint(
    query: QueryParam[ListInferenceProfilesQuery],
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> InferenceProfilesList:
    profiles = await list_aim_cluster_profiles(kube_client, aim_ids=query.aim_id)
    paginated = paginate_list(profiles, page=query.page, page_size=query.page_size)
    return InferenceProfilesList(
        data=paginated.items,
        pagination=PaginationMetadata(
            page=paginated.page,
            page_size=paginated.page_size,
            total=paginated.total,
        ),
    )


@router.get(
    "/inference/profiles/{name}",
    response_model=AIMProfileResource,
    summary="Get a single inference base model profile",
    description=dedent("""
        Fetch a single AIMClusterProfile by resource name. Designed for
        targeted lookups where the caller already knows the profile name
        (e.g. the AIM detail page joining
        `AIMService.status.resolvedProfile.name`) — avoids the aimId
        derivation hop required by the listing endpoint.
    """),
    responses={
        404: {"description": "AIMClusterProfile not found."},
    },
)
async def get_inference_profile_endpoint(
    name: str = Path(
        ...,
        description="AIMClusterProfile resource name (metadata.name).",
        pattern=r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$",
    ),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> AIMProfileResource:
    return await get_aim_cluster_profile(kube_client, name)


@router.post(
    "/projects/{project}/inference",
    response_model=InferenceDeploymentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Deploy a model for inference",
    description=dedent("""
        Deploy a model for inference in the given project.

        The `model` field accepts either an AIMClusterModel name
        (cluster-scoped) or an AIMModel name (project-scoped fine-tuned or
        custom-onboarded model). The API auto-detects which type it is.

        For a custom-onboarded model, `profileName` selects which of that
        model's profiles serves the deployment, using an identifier from its
        profile list (`default` selects the engine-provided profile). The
        server resolves it to the profile that identifier derives and pins it,
        so the deployment keeps serving that profile rather than re-resolving to
        a sibling. Omitting `profileName` deploys the Default. Fine-tuned models
        have no selectable profiles and continue to reject it.

        `adapters` attaches the project's LoRA adapters to the deployment by name.
        Each one must be an adapter in this project, must list the deployed model
        among the base models it can serve, and — for adapters uploaded here — must
        have finished uploading its weights. If any adapter fails a check the whole
        deploy is refused with a 400 naming each one and why, and nothing is created.

        `adapterMode` is immutable once the deployment exists, so it can only be
        chosen here. Omit it to take the platform default (`static`, serving exactly
        the adapters listed at deploy time).

        `maxLoraRank` reserves the highest LoRA rank a `dynamic` deployment can serve,
        since its adapters are not known at deploy time; it is refused on any other
        mode, as is spelling it as the `max-lora-rank` engine argument.

        A pinned profile must support serving adapters whenever the deployment will
        need that capability — either because `adapters` names some, or because
        `adapterMode` is `dynamic`, which asks for adapters to be attachable while the
        deployment runs and so is refused on an incapable profile even when no adapters
        are named. On the selector path no profile is pinned and the engine makes that
        call instead, after the deployment is created.

        Per-adapter progress appears on `status.adapters` of the deployment exactly
        as the engine reports it; the platform neither derives nor aggregates it.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        400: {
            "description": (
                "Model requires a Hugging Face token but none was provided; `profileName` is unknown to the "
                "model or names a profile that is not ready; `profileName` was supplied for a fine-tuned "
                "model; `imagePullSecrets`/`hfToken` were supplied for a project-scoped model; a "
                "requested adapter cannot be attached to this model or profile; or `adapterMode` "
                "is `dynamic` and the pinned profile cannot serve adapters."
            )
        },
        404: {"description": "Project or namespace not found, or referenced model resource not found."},
        422: {
            "description": (
                "Invalid scaling policy (e.g., missing one of minReplicas/maxReplicas/autoScaling, "
                "or maxReplicas < minReplicas), an invalid adapters list (more than 64 adapters, "
                "the same adapter listed twice, or a name no adapter artifact could have), or a "
                "`maxLoraRank` that is unsupported, set outside `dynamic` adapter mode, or spelled "
                "as the `max-lora-rank` engine argument."
            )
        },
    },
)
async def deploy_inference_endpoint(
    deploy_request: InferenceDeployRequest = Body(...),
    project: str = Depends(ensure_access_to_project),
    submitter: str = Depends(get_user_email),
    kube_client: KubernetesClient = Depends(get_kube_client),
    minio_client: MinioClient | None = Depends(get_minio_client_optional),
) -> InferenceDeploymentResponse:
    aim_response = await deploy_aim(
        kube_client=kube_client,
        deploy_request=deploy_request,
        namespace=project,
        submitter=submitter,
        minio_client=minio_client,
    )
    return InferenceDeploymentResponse.model_validate(aim_response, from_attributes=True)


@router.get(
    "/projects/{project}/inference",
    response_model=InferenceDeploymentsList,
    summary="List inference deployments",
    description=dedent("""
        List inference deployments in the project as a paginated envelope
        (default page size 10, max 100). Use `?page=` and `?pageSize=` to
        navigate; the response includes a `pagination` object with `page`,
        `pageSize`, and `total` alongside `data`.

        Use `?capability=chat` or `?capability=transcription` to narrow the
        list to deployments whose model advertises that capability via its
        catalog tags and whose serving stack is fully ready — for example,
        populating chat-target pickers or discovering speech-to-text
        (Whisper-style) endpoints. Use `?statusFilter=` to filter by
        deployment status (repeatable). Pagination is applied after capability
        and status filters, so `total` reflects the filtered set.

        Including `statusFilter=Deleted` also surfaces DB-persisted historical
        deployments (undeployed AIMServices), merged into the same paginated
        `data` list. Historical entries carry `statusValue: "Deleted"`, empty
        `endpoints`, and the original deployment's id, model and
        `creationTimestamp`; the live K8s engine never emits the `Deleted`
        status itself.

        Note: a `capability` filter requires the serving stack to be fully
        ready, so combining it with `statusFilter=Pending` (or other non-ready
        statuses) will typically return an empty list.
    """),
    responses={**PROJECT_ACCESS_RESPONSES},
)
async def list_inference_deployments_endpoint(
    query: QueryParam[ListInferenceDeploymentsQuery],
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
    session: AsyncSession = Depends(get_session),
) -> InferenceDeploymentsList:
    paginated = await inference_service.list_inference_deployments(
        kube_client=kube_client,
        project=project,
        capability=query.capability,
        status_filter=query.status_filter,
        session=session,
        page=query.page,
        page_size=query.page_size,
    )
    return InferenceDeploymentsList(
        data=[InferenceDeploymentResponse.model_validate(s, from_attributes=True) for s in paginated.items],
        pagination=PaginationMetadata(
            page=paginated.page,
            page_size=paginated.page_size,
            total=paginated.total,
        ),
    )


@router.get(
    "/projects/{project}/inference/{id}",
    response_model=InferenceDeploymentResponse,
    summary="Get an inference deployment",
    description=dedent("""
        Get a single inference deployment by ID.

        The response includes `endpoints.internal`, the in-cluster URL used
        by the AIWB UI's chat bypass for direct inference calls.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        **EXTERNAL_SERVICE_RESPONSES,
        404: {"description": "Project or namespace not found, or inference deployment not found in the project."},
    },
)
async def get_inference_deployment_endpoint(
    id: UUID = Path(description="The UUID of the inference deployment"),
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> InferenceDeploymentResponse:
    aim_response = await get_aim_service(kube_client, project, id)
    return InferenceDeploymentResponse.model_validate(aim_response, from_attributes=True)


@router.patch(
    "/projects/{project}/inference/{id}",
    response_model=InferenceDeploymentResponse,
    summary="Update an inference deployment",
    description=dedent("""
        Update an inference deployment without redeploying the model.

        Two changes are supported, either on its own or both together:

        - **Scaling policy.** All three fields (`minReplicas`, `maxReplicas`,
          `autoScaling`) must be provided together.
        - **Adapters.** `adapters` is the complete set the deployment should
          serve: adapters currently attached and not listed are detached, and
          `[]` detaches all of them. Omit the field to leave the adapter set
          alone.

        A request carrying both reaches Kubernetes as a single atomic update:
        either both changes are recorded or neither is.

        Changing adapters requires the deployment to have been created with
        `adapterMode: dynamic`, which is fixed at deploy time — a deployment
        created without it can never accept an adapter change. Each requested
        adapter passes the same checks as at deploy time: it must be an adapter
        in this project, must list the deployed model among the base models it
        can serve, and — for adapters uploaded here — must not be waiting on an
        unfinished upload. That last check only ever refuses on a definite "the
        weights are not there"; storage that cannot be reached leaves it unknown
        and the change proceeds. If any check fails, the request is refused with
        a 400 naming each one and why, and nothing is changed. A scaling-only
        request is not subject to `adapterMode` and works on any deployment.

        Accepting this request records the requested set on the deployment; it
        does not mean the adapters are serving traffic yet. `spec.adapters` is
        what was requested and `status.adapters[]` is what the engine reports,
        verbatim — the platform neither derives nor aggregates it. The `state`
        on each entry is that adapter's **disk-side** staging state: `Downloaded`
        means its weights are present, which is not a load confirmation and must
        not be read as one. `Loaded` is the authoritative signal that an adapter
        is available for inference wherever the engine reports it, but the engine
        deployed today reports disk-side states only, so the absence of `Loaded`
        is not evidence of failure. A detached adapter legitimately stays in
        `status.adapters` as `Deleting` until the unload completes. The engine
        picks up a change on its next poll, so allow up to one poll interval
        before the runtime reflects it.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        400: {
            "description": (
                "Neither adapters nor the scaling policy was supplied; the deployment's "
                "adapterMode is not `dynamic`; a requested adapter cannot be attached to this "
                "deployment; or Kubernetes rejected the change."
            )
        },
        404: {"description": "Project or namespace not found, or inference deployment not found in the project."},
        409: {"description": "The deployment changed concurrently; re-read it and retry."},
        422: {
            "description": (
                "Scaling fields are partially provided (e.g., autoScaling missing while min/max set), "
                "maxReplicas < minReplicas, or an invalid adapters list (more than 64 adapters, the "
                "same adapter listed twice, or a name no adapter artifact could have)."
            )
        },
        502: {
            "description": (
                "The cluster could not be reached, or refused the change for a reason it did not "
                "attribute to the request."
            )
        },
    },
)
async def update_inference_deployment_endpoint(
    id: UUID = Path(..., description="UUID of the inference deployment"),
    patch_request: InferencePatchRequest = Body(...),
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
    minio_client: MinioClient | None = Depends(get_minio_client_optional),
) -> InferenceDeploymentResponse:
    aim_response = await inference_service.update_inference_deployment(
        kube_client=kube_client,
        project=project,
        id=id,
        patch_request=patch_request,
        minio_client=minio_client,
    )
    return InferenceDeploymentResponse.model_validate(aim_response, from_attributes=True)


@router.delete(
    "/projects/{project}/inference/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Undeploy an inference deployment",
    description=dedent("""
        Undeploy an inference deployment by removing its AIMService from
        Kubernetes. Tears down associated cluster-auth groups when present.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        **EXTERNAL_SERVICE_RESPONSES,
        404: {"description": "Project or namespace not found, or inference deployment not found in the project."},
    },
)
async def undeploy_inference_endpoint(
    id: UUID = Path(..., description="UUID of the inference deployment to undeploy"),
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> None:
    await undeploy_aim(
        kube_client=kube_client,
        namespace=project,
        id=id,
    )


@router.get(
    "/projects/{project}/inference/{id}/metrics/{metric}",
    response_model=MetricsTimeseries | MetricsScalar | MetricsScalarWithRange,
    summary="Get an inference deployment metric",
    description=dedent("""
        Retrieve a single inference-scoped metric for a deployment from
        Prometheus, identified by deployment UUID. Optionally scope to a
        specific replica via `podName`.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        **EXTERNAL_SERVICE_RESPONSES,
        404: {"description": "Project or namespace not found, or inference deployment not found in the project."},
        422: {
            "description": (
                "Invalid metric name (not in the supported enum), "
                "or invalid time range (e.g., start >= end, or start older than the lookback window)."
            )
        },
    },
)
async def get_inference_metric_endpoint(
    id: UUID = Path(description="The UUID of the inference deployment"),
    metric: MetricName = Path(description="Metric name to retrieve"),
    time_range: MetricsTimeRange = Depends(),
    pod_name: str | None = Query(
        None,
        alias=to_camel("pod_name"),
        pattern=r"^[a-z0-9][a-z0-9\-\.]{0,252}$",
        description="Optional pod name to scope metrics to a single replica.",
    ),
    prometheus_client: PrometheusConnect = Depends(get_prometheus_client),
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> MetricsTimeseries | MetricsScalar | MetricsScalarWithRange:
    # Verify the deployment belongs to the authorized project before querying
    # Prometheus — Prometheus lookups key on workload_id alone, so without this
    # check a user with access to project A could fetch metrics for a deployment
    # UUID belonging to project B.
    await get_aim_service(kube_client, project, id)
    return await get_metric_by_workload_id(
        workload_id=str(id),
        metric=metric,
        start=time_range.start,
        end=time_range.end,
        prometheus_client=prometheus_client,
        kube_client=kube_client,
        namespace=project,
        pod_name=pod_name,
    )


@router.get(
    "/projects/{project}/inference/{id}/replicas",
    response_model=ListResponse[InferenceReplicaResponse],
    status_code=status.HTTP_200_OK,
    summary="List inference deployment replicas",
    description=dedent("""
        Return Kubernetes pod data for each replica of an inference deployment.
        The response is a fixed schema containing commonly needed pod fields
        (name, phase, IP, containers, resource limits, conditions).
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        **EXTERNAL_SERVICE_RESPONSES,
        404: {"description": "Project or namespace not found, or inference deployment not found in the project."},
    },
)
async def list_inference_replicas_endpoint(
    id: UUID = Path(description="The UUID of the inference deployment"),
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> ListResponse[InferenceReplicaResponse]:
    # Verify the deployment belongs to the authorized project before listing pods —
    # the pod label selector keys on workload_id alone, so without this check a user
    # with access to project A could fetch pod data for a deployment in project B.
    await get_aim_service(kube_client, project, id)
    replicas = await list_aim_service_replicas(kube_client, project, id)
    return ListResponse(data=[InferenceReplicaResponse.model_validate(r) for r in replicas])
