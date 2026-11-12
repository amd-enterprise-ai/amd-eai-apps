# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from textwrap import dedent
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from api_common.auth.security import ensure_platform_administrator, get_user_email
from api_common.database import get_session
from api_common.exceptions import ValidationException
from api_common.schemas import ListResponse, QueryParam

from ..common_responses import PLATFORM_ADMINISTRATOR_RESPONSES
from .models import SOURCE_PATH_MAX_LENGTH
from .repository import list_overlays
from .schemas import OverlayListQuery, OverlayResponse, OverlayUpdate
from .service import create_overlay, delete_overlay_by_id_service, get_overlay_by_id, parse_overlay_file, update_overlay

router = APIRouter(tags=["Overlays"])


@router.post(
    "/overlays",
    response_model=OverlayResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a chart overlay",
    description=dedent("""
        Attach a YAML overlay to an existing chart.

        An overlay layers chart-specific or model-specific value overrides
        on top of a chart's signature defaults, so the same chart can be
        reused for different models or runtime profiles without forking
        the template. An overlay registered from a chart file is keyed by
        `(chartId, sourcePath)`, so a chart can ship one recipe per GPU
        family for the same model. Without `sourcePath` it is keyed by
        `(chartId, canonicalName)`; omitting `canonicalName` as well creates
        a generic fallback that matches any model.

        Overlays are global (not project-scoped) and apply to every project's
        deployments, so only a Platform Administrator can create them.
    """),
    responses={
        **PLATFORM_ADMINISTRATOR_RESPONSES,
        400: {"description": "Invalid YAML overlay file or non-YAML file extension."},
        404: {"description": "Referenced chart not found."},
        409: {"description": "An overlay with these parameters already exists for the chart."},
    },
)
async def create_overlay_endpoint(
    _: None = Depends(ensure_platform_administrator),
    chart_id: UUID = Form(alias=to_camel("chart_id"), description="The ID of an existing Chart."),
    overlay_file: UploadFile = File(
        alias=to_camel("overlay_file"), description="YAML file containing the model overlay"
    ),
    canonical_name: str | None = Form(
        None,
        alias=to_camel("canonical_name"),
        description="Optional canonical name to associate the overlay with a model type, for example 'meta-llama/Llama-3.1-8B'.",
        examples=["meta-llama/Llama-3.1-8B"],
    ),
    display_name: str | None = Form(
        None,
        alias=to_camel("display_name"),
        description="Optional user-visible display name for this overlay.",
    ),
    source_path: str | None = Form(
        None,
        alias=to_camel("source_path"),
        max_length=SOURCE_PATH_MAX_LENGTH,
        description="Optional path of the chart file this overlay is registered from, relative to the chart.",
        examples=["overrides/models/meta-llama_Llama-3.1-8B.yaml"],
    ),
    session: Session = Depends(get_session),
    creator: str = Depends(get_user_email),
) -> OverlayResponse:
    overlay_data = await parse_overlay_file(overlay_file)
    overlay = await create_overlay(
        session=session,
        chart_id=chart_id,
        overlay_data=overlay_data,
        canonical_name=canonical_name,
        display_name=display_name,
        creator=creator,
        source_path=source_path,
    )
    return overlay


@router.put(
    "/overlays/{overlay_id}",
    response_model=OverlayResponse,
    summary="Update a chart overlay",
    description=dedent("""
        Update an existing overlay in place.

        Supports partial updates: at least one of `overlayFile`, `chartId`,
        `canonicalName`, `displayName` or `sourcePath` must be supplied —
        submitting an empty form returns 400. Providing `overlayFile`
        replaces the parsed overlay body wholesale; `chartId` repoints the
        overlay at a different chart; `canonicalName` changes the model the
        overlay matches; `sourcePath` records the chart file it is
        registered from.

        Overlays are global (not project-scoped); only a Platform
        Administrator can update them.
    """),
    responses={
        **PLATFORM_ADMINISTRATOR_RESPONSES,
        400: {"description": "Invalid YAML overlay file, or no updatable fields provided."},
        404: {"description": "Overlay not found, or referenced chart not found."},
    },
)
async def update_overlay_endpoint(
    overlay_id: UUID,
    _: None = Depends(ensure_platform_administrator),
    chart_id: UUID = Form(None, alias=to_camel("chart_id"), description="The ID of an existing Chart."),
    overlay_file: UploadFile | None = File(
        None, alias=to_camel("overlay_file"), description="YAML file containing the model overlay"
    ),
    canonical_name: str | None = Form(
        None,
        alias=to_camel("canonical_name"),
        description="Optional canonical name to associate the overlay with a model type, for example 'meta-llama/Llama-3.1-8B'.",
        examples=["meta-llama/Llama-3.1-8B"],
    ),
    display_name: str | None = Form(
        None,
        alias=to_camel("display_name"),
        description="Optional user-visible display name for this overlay.",
    ),
    source_path: str | None = Form(
        None,
        alias=to_camel("source_path"),
        max_length=SOURCE_PATH_MAX_LENGTH,
        description="Optional path of the chart file this overlay is registered from, relative to the chart.",
        examples=["overrides/models/meta-llama_Llama-3.1-8B.yaml"],
    ),
    session: Session = Depends(get_session),
    updater: str = Depends(get_user_email),
) -> OverlayResponse:
    overlay_data = None
    if overlay_file:
        overlay_data = await parse_overlay_file(overlay_file)
    if not overlay_data and not chart_id and not canonical_name and display_name is None and not source_path:
        raise ValidationException(
            "Either 'overlayFile' or 'chartId' or 'canonicalName' or 'displayName' or 'sourcePath' must be provided"
        )

    update_kwargs: dict[str, Any] = {"updated_by": updater}
    if chart_id is not None:
        update_kwargs["chart_id"] = chart_id
    if overlay_data is not None:
        update_kwargs["overlay"] = overlay_data
    if canonical_name is not None:
        update_kwargs["canonical_name"] = canonical_name
    if display_name is not None:
        update_kwargs["display_name"] = display_name
    if source_path is not None:
        update_kwargs["source_path"] = source_path
    overlay_update = OverlayUpdate(**update_kwargs)

    overlay = await update_overlay(
        session=session,
        overlay_id=overlay_id,
        overlay_update=overlay_update,
    )
    return overlay


@router.get(
    "/overlays",
    response_model=ListResponse[OverlayResponse],
    summary="List chart overlays",
    description=dedent("""
        List all overlays in the cluster-wide catalog.

        Filter with `?chartId=` to scope to a single chart, and/or with
        `?canonicalName=` to scope to overlays matching a specific model.
        With no filters, all overlays are returned.
    """),
)
async def list_overlays_endpoint(
    query: QueryParam[OverlayListQuery],
    session: Session = Depends(get_session),
) -> ListResponse[OverlayResponse]:
    """
    List all model overlays.
    """
    items = await list_overlays(
        session=session,
        chart_id=query.chart_id,
        canonical_name=query.canonical_name,
    )
    return ListResponse(data=items)


@router.get(
    "/overlays/{overlay_id}",
    response_model=OverlayResponse,
    summary="Get a chart overlay",
    description=dedent("""
        Retrieve a single overlay by id, including its parsed YAML body and
        the chart it is attached to.
    """),
    responses={
        404: {"description": "Overlay not found."},
    },
)
async def get_overlay_endpoint(
    overlay_id: UUID,
    session: Session = Depends(get_session),
) -> OverlayResponse:
    overlay = await get_overlay_by_id(session, overlay_id)
    return overlay


@router.delete(
    "/overlays/{overlay_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chart overlay",
    description=dedent("""
        Permanently remove an overlay from the catalog. Hard delete; the
        referenced chart is left untouched. Future deployments that would
        have matched this overlay fall back to chart defaults (or to a
        generic overlay if one exists for the chart).

        Overlays are global (not project-scoped); only a Platform
        Administrator can delete them.
    """),
    responses={
        **PLATFORM_ADMINISTRATOR_RESPONSES,
        404: {"description": "Overlay not found."},
    },
)
async def delete_overlay_endpoint(
    overlay_id: UUID,
    _: None = Depends(ensure_platform_administrator),
    session: Session = Depends(get_session),
) -> None:
    await delete_overlay_by_id_service(session, overlay_id)
