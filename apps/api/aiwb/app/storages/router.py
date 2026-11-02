# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from textwrap import dedent

from fastapi import APIRouter, Body, Depends, status

from api_common.auth.security import get_user_email
from api_common.schemas import ListResponse, QueryParam

from ..common_responses import PROJECT_ACCESS_RESPONSES
from ..dispatch.kube_client import KubernetesClient, get_kube_client
from ..projects.security import ensure_access_to_project
from .schemas import (
    ProjectStorageCreateRequest,
    ProjectStorageListQuery,
    ProjectStorageResponse,
)
from .service import create_project_storage as create_storage
from .service import list_project_storages as list_storages

router = APIRouter(tags=["Storages"])


@router.get(
    "/projects/{project}/storages",
    response_model=ListResponse[ProjectStorageResponse],
    status_code=status.HTTP_200_OK,
    summary="List storage configurations",
    description=dedent("""
        List project-scoped storage configurations created in this project.

        Returns storage metadata persisted as AIWB-managed ConfigMaps.
        Use `?type=` to filter by storage type (exact match), for example
        `?type=S3`.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        502: {"description": "Upstream Kubernetes API failure while listing ConfigMaps."},
    },
)
async def list_storage_endpoint(
    query: QueryParam[ProjectStorageListQuery],
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> ListResponse[ProjectStorageResponse]:
    storages = await list_storages(
        kube_client=kube_client,
        namespace=project,
        storage_type=query.type,
    )
    return ListResponse(data=storages)


@router.post(
    "/projects/{project}/storages",
    response_model=ProjectStorageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a storage configuration",
    description=dedent("""
        Create a project-scoped S3 storage configuration backed by an existing
        S3 secret in the project.

        The request `displayName` is user-visible only; AIWB generates the
        Kubernetes ConfigMap resource name automatically.

        The provided secret must exist in the same project and, when labeled
        with a use-case, must be labeled as `S3`. The secret must also contain
        the configured access and secret key fields. The storage is persisted as
        a namespaced ConfigMap that can be referenced by project-local flows.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        400: {"description": "Secret use-case or required key validation failed."},
        404: {"description": "Referenced secret not found in the project."},
        409: {"description": "A storage with this display name already exists in the project."},
        502: {"description": "Upstream Kubernetes API failure while reading secret or creating ConfigMap."},
    },
)
async def create_storage_endpoint(
    body: ProjectStorageCreateRequest = Body(...),
    project: str = Depends(ensure_access_to_project),
    kube_client: KubernetesClient = Depends(get_kube_client),
    submitter: str = Depends(get_user_email),
) -> ProjectStorageResponse:
    return await create_storage(
        kube_client=kube_client,
        namespace=project,
        submitter=submitter,
        request=body,
    )
