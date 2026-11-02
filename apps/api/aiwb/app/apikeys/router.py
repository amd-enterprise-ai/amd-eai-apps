# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from textwrap import dedent
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, status
from prometheus_api_client import PrometheusConnect
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.auth.security import get_user_email
from api_common.collections import PaginationMetadata
from api_common.database import get_session
from api_common.schemas import QueryParam

from ..common_responses import PROJECT_ACCESS_RESPONSES
from ..dispatch.kube_client import KubernetesClient, get_kube_client
from ..metrics.client import get_prometheus_client
from ..metrics.schemas import MetricsTimeRange
from ..openbao import get_openbao_client
from ..openbao.client import OpenBaoClient
from ..projects.security import ensure_access_to_project
from .schemas import (
    ApiKeyCreate,
    ApiKeyDetails,
    ApiKeyMetricsResponse,
    ApiKeysList,
    ApiKeyUpdate,
    ApiKeyWithFullKey,
    ListApiKeysQuery,
)
from .service import (
    create_api_key_in_store,
    delete_api_key_from_store,
    get_api_key_details_from_store,
    get_api_key_usage_metrics,
    list_api_keys_for_namespace,
    update_api_key_bindings_in_store,
)

router = APIRouter(tags=["API Keys"])


@router.get(
    "/projects/{project}/api-keys",
    operation_id="get_api_keys",
    summary="List API keys for a project",
    description=dedent("""
        List the API keys that belong to a project as a paginated envelope
        (default page size 10, max 100). Use `?page=` and `?pageSize=` to
        navigate; the response includes a `pagination` object with `page`,
        `pageSize`, and `total` alongside `data`.

        Each entry includes a truncated form of the key suitable for display
        (the full secret value is only ever returned once at creation). Use
        `GET /projects/{project}/api-keys/{apiKeyId}` to fetch the metadata
        and bound models for a single key.
    """),
    status_code=status.HTTP_200_OK,
    response_model=ApiKeysList,
    responses={**PROJECT_ACCESS_RESPONSES},
)
async def get_api_keys(
    query: QueryParam[ListApiKeysQuery],
    project: str = Depends(ensure_access_to_project),
    session: AsyncSession = Depends(get_session),
) -> ApiKeysList:
    paginated = await list_api_keys_for_namespace(session, project, page=query.page, page_size=query.page_size)
    return ApiKeysList(
        data=paginated.items,
        pagination=PaginationMetadata(
            page=paginated.page,
            page_size=paginated.page_size,
            total=paginated.total,
        ),
    )


@router.post(
    "/projects/{project}/api-keys",
    operation_id="create_api_key",
    summary="Create an API key",
    description=dedent("""
        Create a new API key for the project.

        The response includes the full secret value in `fullKey`; this is
        the only opportunity to read it. Once the response is consumed only
        the truncated key, metadata, and group bindings are retrievable.
        Persist the secret on the client side at this point.

        The token is written to the OpenBao store and AIWB never sees it
        again. Optional `aimIds` bind the new key to specific deployed models
        (an entry in each model's per-backend Secret), so the key only works
        against those models. `ttl` sets a native expiry (e.g. `"30d"`,
        `"0"`/omitted = never); OpenBao drops the token when it lapses.
    """),
    status_code=status.HTTP_200_OK,
    response_model=ApiKeyWithFullKey,
    response_description="Created key with the full secret value; persist it now — only the metadata is retrievable later.",
    responses={
        **PROJECT_ACCESS_RESPONSES,
        409: {"description": "An API key with this name already exists in the project."},
        502: {"description": "The API-key store (OpenBao) was unavailable while creating the key."},
    },
)
async def create_api_key(
    api_key_in: ApiKeyCreate = Body(description="API key creation data"),
    project: str = Depends(ensure_access_to_project),
    user: str = Depends(get_user_email),
    session: AsyncSession = Depends(get_session),
    kube_client: KubernetesClient = Depends(get_kube_client),
    openbao_client: OpenBaoClient | None = Depends(get_openbao_client),
) -> ApiKeyWithFullKey:
    return await create_api_key_in_store(session, kube_client, project, api_key_in, user, openbao_client)


@router.get(
    "/projects/{project}/api-keys/{api_key_id}",
    operation_id="get_api_key_details",
    summary="Get API key details",
    description=dedent("""
        Get the metadata for one API key in the project.

        The response merges the DB record (name, namespace, truncated key,
        `expiresAt`) with the models the key is bound to (`groups` — the
        workload-ids whose per-backend Secret carries the key). Use this in
        place of the list endpoint when you need the bindings or expiry. The
        full secret value is never returned here.
    """),
    status_code=status.HTTP_200_OK,
    response_model=ApiKeyDetails,
    responses={
        **PROJECT_ACCESS_RESPONSES,
        404: {"description": "Project or namespace not found, or API key not found in the project."},
    },
)
async def get_api_key_details(
    api_key_id: UUID = Path(description="The ID of the API key"),
    project: str = Depends(ensure_access_to_project),
    session: AsyncSession = Depends(get_session),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> ApiKeyDetails:
    return await get_api_key_details_from_store(session, kube_client, project, api_key_id)


@router.patch(
    "/projects/{project}/api-keys/{api_key_id}",
    operation_id="update_api_key_bindings",
    summary="Update API key AIM deployment bindings",
    description=dedent("""
        Update the API key's bindings, replacing the set of AIM deployments
        it is permitted to call.

        `aimIds` is treated as the complete desired set: models present in
        the request are bound (the key is added to each model's per-backend
        Secret) and models previously bound but absent are unbound, with a
        minimal diff so unchanged bindings are left untouched. To revoke all
        bindings, send an empty list.
    """),
    status_code=status.HTTP_200_OK,
    response_model=ApiKeyDetails,
    responses={
        **PROJECT_ACCESS_RESPONSES,
        404: {"description": "Project or namespace not found, or API key not found in the project."},
    },
)
async def update_api_key_bindings(
    api_key_id: UUID = Path(description="The ID of the API key to update"),
    api_key_update: ApiKeyUpdate = Body(description="API key update data"),
    project: str = Depends(ensure_access_to_project),
    session: AsyncSession = Depends(get_session),
    kube_client: KubernetesClient = Depends(get_kube_client),
    openbao_client: OpenBaoClient | None = Depends(get_openbao_client),
) -> ApiKeyDetails:
    return await update_api_key_bindings_in_store(
        session, kube_client, project, api_key_id, api_key_update, openbao_client=openbao_client
    )


@router.delete(
    "/projects/{project}/api-keys/{api_key_id}",
    operation_id="delete_api_key",
    summary="Delete an API key",
    description=dedent("""
        Permanently delete an API key.

        The key is removed from every model's per-backend Secret, deleted
        from the OpenBao store, and its DB record is removed. Existing
        clients holding the secret will receive 401 from inference
        endpoints on the next request. The operation cannot be undone.
    """),
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **PROJECT_ACCESS_RESPONSES,
        404: {"description": "Project or namespace not found, or API key not found."},
    },
)
async def delete_api_key(
    api_key_id: UUID = Path(description="The ID of the API key to delete"),
    project: str = Depends(ensure_access_to_project),
    session: AsyncSession = Depends(get_session),
    kube_client: KubernetesClient = Depends(get_kube_client),
    openbao_client: OpenBaoClient | None = Depends(get_openbao_client),
) -> None:
    await delete_api_key_from_store(
        session, project, api_key_id, kube_client=kube_client, openbao_client=openbao_client
    )


@router.get(
    "/projects/{project}/api-keys/{api_key_id}/metrics",
    operation_id="get_api_key_metrics",
    summary="Get usage metrics for an API key",
    description=dedent("""
        Get aggregated usage metrics for an API key over a time range.

        Returns token consumption and request counts broken down by AIM service and time bucket.
        Sourced from AI Gateway ext-proc metrics via Prometheus.
    """),
    status_code=status.HTTP_200_OK,
    response_model=ApiKeyMetricsResponse,
    responses={**PROJECT_ACCESS_RESPONSES},
)
async def get_api_key_metrics_endpoint(
    api_key_id: UUID = Path(description="The ID of the API key"),
    time_range: MetricsTimeRange = Depends(),
    project: str = Depends(ensure_access_to_project),
    session: AsyncSession = Depends(get_session),
    prometheus_client: PrometheusConnect = Depends(get_prometheus_client),
) -> ApiKeyMetricsResponse:
    return await get_api_key_usage_metrics(
        session=session,
        namespace=project,
        api_key_id=api_key_id,
        start=time_range.start,
        end=time_range.end,
        prometheus_client=prometheus_client,
    )
