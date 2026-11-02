# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from textwrap import dedent
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.auth.security import get_user_email
from api_common.collections import PaginationMetadata
from api_common.database import get_session
from api_common.exceptions import NotFoundException
from api_common.schemas import ListResponse, QueryParam

from ..aims.crds import AIMModelResource
from ..common_responses import EXTERNAL_SERVICE_RESPONSES, PROJECT_ACCESS_RESPONSES
from ..dispatch.kube_client import KubernetesClient, get_kube_client
from ..minio import MinioClient, get_minio_client
from ..models.schemas import FinetunableModelResponse, FinetuneJobResponse
from ..models.service import delete_model, get_finetunable_models, run_finetune_model_workload
from ..projects.security import ensure_access_to_project
from .schemas import FineTuningJobRequest, FineTuningModelsList, ListFineTuningModelsQuery
from .service import delete_fine_tuning_job, get_fine_tuning_model, list_fine_tuning_models

router = APIRouter(tags=["Fine-tuning"])


@router.get(
    "/fine-tuning/models",
    response_model=ListResponse[FinetunableModelResponse],
    status_code=status.HTTP_200_OK,
    summary="List finetunable base models",
    description=dedent("""
        List base models that can be fine-tuned on the cluster's current GPU
        hardware.

        Only models with at least one matching recipe are returned. A recipe is
        considered matching when its required accelerator family is present on
        at least one schedulable node in the cluster, so the result set is
        gated by the GPUs actually installed (e.g., a cluster with only
        MI300X nodes will not see MI250-only recipes). Each entry reports the
        canonical model name, the recipe's GPU count, and the AMD device IDs
        and display names of the compatible accelerators.
    """),
)
async def list_finetunable_models_endpoint(
    session: AsyncSession = Depends(get_session),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> ListResponse[FinetunableModelResponse]:
    models = await get_finetunable_models(session, kube_client)
    return ListResponse(data=models)


@router.get(
    "/fine-tuning/models/{name:path}",
    response_model=FinetunableModelResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a finetunable base model by canonical name",
    description=dedent("""
        Look up a single finetunable base model by its canonical name
        (e.g., `meta-llama/Llama-3.1-8B`).

        The `name` segment is declared as a path parameter with
        `{name:path}` so canonical names containing forward slashes
        (the standard HuggingFace `org/model` convention) match without
        URL-encoding the separator. The returned entry mirrors what
        `GET /fine-tuning/models` would emit for that model, including
        the compatible GPU set.
    """),
    responses={404: {"description": "Finetunable model not found, or not compatible with the cluster's GPUs."}},
)
async def get_finetunable_model_endpoint(
    name: str = Path(..., description="Canonical name of the finetunable base model"),
    session: AsyncSession = Depends(get_session),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> FinetunableModelResponse:
    models = await get_finetunable_models(session, kube_client)
    for model in models:
        if model.canonical_name == name:
            return model
    raise NotFoundException(f"Finetunable model {name} not found")


@router.get(
    "/projects/{project}/fine-tuning/models",
    response_model=FineTuningModelsList,
    status_code=status.HTTP_200_OK,
    summary="List fine-tuned models in a project",
    description=dedent("""
        List AIMModel resources in a project that were produced by fine-tuning
        jobs as a paginated envelope (default page size 10, max 100). Use
        `?page=` and `?pageSize=` to navigate; the response includes a
        `pagination` object with `page`, `pageSize`, and `total` alongside
        `data`.

        Excludes onboarded custom models (those go through
        `/projects/{project}/models/preview`) — only models whose AIMModel CR
        records a fine-tuning provenance are returned. The fine-tuning label
        filter is applied before pagination so `total` reflects only
        fine-tuned models, not the raw AIMModel count.
    """),
    responses={**PROJECT_ACCESS_RESPONSES},
)
async def list_project_fine_tuned_models(
    query: QueryParam[ListFineTuningModelsQuery],
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> FineTuningModelsList:
    paginated = await list_fine_tuning_models(
        kube_client=kube_client,
        namespace=project,
        page=query.page,
        page_size=query.page_size,
    )
    return FineTuningModelsList(
        data=paginated.items,
        pagination=PaginationMetadata(
            page=paginated.page,
            page_size=paginated.page_size,
            total=paginated.total,
        ),
    )


@router.get(
    "/projects/{project}/fine-tuning/models/{model_id:path}",
    response_model=AIMModelResource,
    status_code=status.HTTP_200_OK,
    summary="Get a fine-tuned model",
    description=dedent("""
        Get a single fine-tuned model in a project.

        The `model_id` may be either the AIMModel resource name or the UUID of
        the workload that produced it; the API resolves both forms to the same
        underlying AIMModel CR. The segment is declared as `{model_id:path}`
        so resource names containing forward slashes match without
        URL-encoding the separator.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        404: {"description": "Project or namespace not found, or fine-tuned model not found in the project."},
    },
)
async def get_project_fine_tuned_model(
    model_id: str = Path(..., description="AIMModel CR resource name or workload UUID"),
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> AIMModelResource:
    return await get_fine_tuning_model(kube_client, project, model_id)


@router.delete(
    "/projects/{project}/fine-tuning/models/{model_id:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a fine-tuned model",
    description=dedent("""
        Delete a fine-tuned model from the project.

        Cascading semantics: the AIMModel CR is removed from Kubernetes and
        the model weights are deleted from S3 in the same operation. If
        active inference deployments reference the model, the request is
        rejected with 409; pass `force=true` to delete anyway (the
        downstream deployments will fail to reload on restart). The call is
        idempotent for an already-deleted model — a second DELETE returns
        404.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        **EXTERNAL_SERVICE_RESPONSES,
        404: {"description": "Project or namespace not found, or fine-tuned model not found in the project."},
        409: {"description": "Active deployments reference the model; pass force=true to override."},
    },
)
async def delete_project_fine_tuned_model(
    model_id: str = Path(..., description="AIMModel CR resource name or workload UUID"),
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
    minio_client: MinioClient = Depends(get_minio_client),
    session: AsyncSession = Depends(get_session),
    force: bool = Query(False, description="Delete even if active deployments exist"),
) -> None:
    # Type-scoped: 404 when the resource exists but isn't a fine-tuning model.
    await get_fine_tuning_model(kube_client, project, model_id)
    await delete_model(kube_client, model_id, project, minio_client=minio_client, force=force, session=session)


@router.post(
    "/projects/{project}/fine-tuning/jobs",
    response_model=FinetuneJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a fine-tuning job",
    description=dedent("""
        Start a fine-tuning job in the project.

        The `baseModel` field accepts either a HuggingFace canonical name
        (e.g., `meta-llama/Llama-3.1-8B`) or an existing AIMModel UUID to
        continue training from a previous fine-tune. Each entry in `datasetIds`
        must reference a dataset already uploaded into the same project —
        datasets from other projects are not visible. The deprecated
        `datasetId` field remains accepted for single-dataset clients.

        The job is submitted asynchronously; the response carries the new
        `workloadId`. The job then transitions Pending → Running →
        Completed/Failed and on success produces an AIMModel CR that becomes
        visible via `GET /projects/{project}/fine-tuning/models`.
    """),
    response_description="Job submitted; poll workloadId for progress.",
    responses={
        **PROJECT_ACCESS_RESPONSES,
        400: {"description": "Base model has no weights URI (not fully onboarded)."},
        404: {
            "description": "Project or namespace not found, or base model not found, or dataset not found in the project."
        },
        422: {"description": "Invalid hyperparameters or job name (pattern / range constraints)."},
    },
)
async def create_fine_tuning_job(
    request: FineTuningJobRequest = Body(...),
    project: str = Depends(ensure_access_to_project),
    submitter: str = Depends(get_user_email),
    session: AsyncSession = Depends(get_session),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> FinetuneJobResponse:
    return await run_finetune_model_workload(
        session=session,
        kube_client=kube_client,
        model_id=request.base_model,
        finetuning_data=request,
        namespace=project,
        submitter=submitter,
    )


@router.delete(
    "/projects/{project}/fine-tuning/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a fine-tuning job",
    description=dedent("""
        Cancel an in-progress fine-tuning job in the project.

        Cascading semantics: the underlying Kubernetes job and its supporting
        components (PyTorchJob, configmaps, secrets) are torn down, but the
        workload row is retained for history and audit so the cancelled run
        remains visible in `/projects/{project}/workloads`. The call is
        idempotent: repeating it on an already-cancelled job returns 204 and
        re-attempts the K8s teardown (missing resources are treated as
        already-deleted).
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        404: {"description": "Project or namespace not found, or fine-tuning job not found in the project."},
    },
)
async def cancel_fine_tuning_job(
    job_id: UUID = Path(..., description="Workload UUID of the fine-tuning job"),
    project: str = Depends(ensure_access_to_project),
    session: AsyncSession = Depends(get_session),
) -> None:
    await delete_fine_tuning_job(session=session, namespace=project, workload_id=job_id)
