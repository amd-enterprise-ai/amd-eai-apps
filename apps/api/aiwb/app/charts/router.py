# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from textwrap import dedent
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.auth.security import ensure_platform_administrator, get_user_email
from api_common.database import get_session
from api_common.exceptions import NotFoundException, ValidationException
from api_common.schemas import ListResponse

from ..common_responses import PLATFORM_ADMINISTRATOR_RESPONSES
from ..workloads.enums import WorkloadType
from .repository import (
    create_chart,
    delete_chart,
    list_charts,
    update_chart,
)
from .schemas import ChartCreate, ChartListResponse, ChartResponse, ChartUpdate
from .service import get_chart

router = APIRouter(tags=["Charts"])


@router.post(
    "/charts",
    operation_id="create_chart",
    summary="Create a workload chart",
    description=dedent("""
        Register a new chart in the cluster-wide chart catalog.

        A chart is a Helm-like template surface that AIWB uses to render the
        Kubernetes manifests for a workload class (workspaces, inference
        scaffolding, fine-tuning jobs). Each chart bundles a signature
        (YAML schema describing user-facing inputs and defaults) plus the
        template files themselves, and is keyed by a unique `name` within a
        `type` (workspace / inference / fine-tuning).

        Charts are global (not project-scoped). Once created, projects can
        reference the chart when deploying workloads, optionally further
        customised by an overlay (see the Overlays API). Because every
        project deploys from the catalog, only a Platform Administrator can
        change it.
    """),
    status_code=status.HTTP_201_CREATED,
    response_model=ChartResponse,
    responses={
        **PLATFORM_ADMINISTRATOR_RESPONSES,
        400: {
            "description": (
                "Invalid YAML in the uploaded signature file, or a chart file path that is absolute "
                "or points outside the chart."
            )
        },
        409: {"description": "A chart with this name already exists."},
    },
)
async def create_chart_endpoint(
    _: None = Depends(ensure_platform_administrator),
    chart: ChartCreate = Form(),
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_user_email),
) -> ChartResponse:
    try:
        chart_obj = await create_chart(session, chart, user)
        return chart_obj
    except ValueError as e:
        raise ValidationException(str(e))


@router.put(
    "/charts/{chart_id}",
    operation_id="update_chart",
    summary="Update a workload chart",
    description=dedent("""
        Update an existing chart in place.

        Supports partial updates: only the fields supplied on the multipart
        form are modified; omitted metadata fields are left untouched.
        Providing `files` replaces the chart's file set wholesale (the old
        files are deleted before the new ones are written), so always
        re-submit the full template tree when uploading files. Providing
        `signature` replaces the signature YAML.

        Charts are global (not project-scoped); only a Platform
        Administrator can update them.
    """),
    status_code=status.HTTP_200_OK,
    response_model=ChartResponse,
    responses={
        **PLATFORM_ADMINISTRATOR_RESPONSES,
        400: {
            "description": (
                "Invalid YAML in the uploaded signature file, or a chart file path that is absolute "
                "or points outside the chart."
            )
        },
        404: {"description": "Chart not found."},
    },
)
async def update_chart_endpoint(
    chart_id: UUID,
    _: None = Depends(ensure_platform_administrator),
    chart_update: ChartUpdate = Form(),
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_user_email),
) -> ChartResponse:
    try:
        chart = await update_chart(session, chart_id, chart_update, user)
        return chart
    except ValueError as e:
        raise ValidationException(str(e))


@router.get(
    "/charts",
    response_model=ListResponse[ChartListResponse],
    status_code=status.HTTP_200_OK,
    summary="List workload charts",
    description=dedent("""
        List all charts in the cluster-wide catalog.

        Returns the lightweight `ChartListResponse` representation (no
        signature or file contents) — fetch a single chart by id to obtain
        its full body.

        Filter by workload class with `?type=` (one of `INFERENCE`,
        `FINE_TUNING`, `WORKSPACE`); omitted returns all types.
    """),
)
async def get_charts(
    session: AsyncSession = Depends(get_session),
    chart_type: WorkloadType | None = Query(default=None, alias="type"),
) -> ListResponse[ChartListResponse]:
    charts = await list_charts(session, chart_type)
    return ListResponse(data=charts)


@router.get(
    "/charts/{chart_id}",
    operation_id="get_chart",
    summary="Get a workload chart",
    description=dedent("""
        Retrieve a single chart by id, including the parsed signature and
        the full list of template files (path + content). Use this before
        rendering a deployment form for the chart, or for inspecting the
        templates the workload will be deployed from.
    """),
    response_model=ChartResponse,
    responses={
        404: {"description": "Chart not found."},
    },
)
async def get_chart_endpoint(
    chart_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ChartResponse:
    chart = await get_chart(session, chart_id=chart_id)
    return chart


@router.delete(
    "/charts/{chart_id}",
    operation_id="delete_chart",
    summary="Delete a workload chart",
    description=dedent("""
        Remove a chart from the catalog. The deletion cascades to the
        chart's stored template files but is not a soft-delete and cannot
        be undone.

        Overlays that reference the chart will be left dangling — delete
        or repoint them first to avoid orphans. Existing deployments
        rendered from the chart are not affected, since they hold their
        own rendered manifests.

        Charts are global (not project-scoped); only a Platform
        Administrator can delete them.
    """),
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **PLATFORM_ADMINISTRATOR_RESPONSES,
        404: {"description": "Chart not found."},
    },
)
async def delete_chart_endpoint(
    chart_id: UUID,
    _: None = Depends(ensure_platform_administrator),
    session: AsyncSession = Depends(get_session),
) -> None:
    deleted = await delete_chart(session, chart_id)
    if not deleted:
        raise NotFoundException("Chart not found")
