# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from collections.abc import Collection
from typing import Any
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ConflictException, NotFoundException

from .models import Overlay


async def insert_overlay(
    session: AsyncSession,
    chart_id: UUID,
    overlay_data: dict[str, Any],
    canonical_name: str | None = None,
    display_name: str | None = None,
    creator: str | None = None,
    source_path: str | None = None,
) -> Overlay:
    """
    Insert a new overlay record into the database.

    Raises:
        NotFoundException: If the chart_id references a non-existent chart
        ConflictException: If the chart already has an overlay from the same source file, or, for an
            overlay without one, an overlay for the same canonical name
    """
    overlay = Overlay(
        canonical_name=canonical_name,
        source_path=source_path,
        display_name=display_name,
        chart_id=chart_id,
        overlay=overlay_data,
        created_by=creator,
        updated_by=creator,
    )
    session.add(overlay)
    try:
        await session.flush()
        await session.refresh(overlay)
        return overlay
    except IntegrityError as e:
        error_message = str(e)
        if "ForeignKeyViolationError" in error_message and 'is not present in table "charts"' in error_message:
            raise NotFoundException(f"Chart with ID {chart_id} not found")
        elif source_path is not None:
            raise ConflictException(
                f"Overlay with chart ID '{chart_id}' and source path '{source_path}' already exists."
            )
        else:
            raise ConflictException(
                f"Overlay with chart ID '{chart_id}' and canonical name '{canonical_name}' already exists."
            )


async def list_overlays(
    session: AsyncSession,
    chart_id: UUID | None = None,
    canonical_name: str | None = None,
    include_generic: bool = False,
) -> list[Overlay]:
    query = select(Overlay)
    if chart_id is not None:
        query = query.where(Overlay.chart_id == chart_id)

    if canonical_name is not None:
        if include_generic:
            query = query.where(or_(Overlay.canonical_name == canonical_name, Overlay.canonical_name.is_(None)))
        else:
            query = query.where(Overlay.canonical_name == canonical_name)
    result = await session.execute(query)
    return result.scalars().unique().all()


async def delete_overlays_absent_from_chart(
    session: AsyncSession,
    chart_id: UUID,
    keep_ids: Collection[UUID],
    creator: str,
) -> list[UUID]:
    """Delete a chart's registered overlays that the chart no longer ships.

    Overlay rows are a cache of the recipe files a chart carries. Without pruning, a recipe that is
    renamed, relocated, or dropped upstream keeps being served from whatever content it held when it
    was last registered.

    Scoped to `creator` so overlays added through the API are never touched, and to rows that can be
    traced back to a file — by the source path they were registered from, or by the model they
    declare. A row with neither predates source tracking and cannot be matched to any file, so its
    absence from `keep_ids` proves nothing.
    """
    query = delete(Overlay).where(
        Overlay.chart_id == chart_id,
        Overlay.created_by == creator,
        or_(Overlay.source_path.is_not(None), Overlay.canonical_name.is_not(None)),
    )
    if keep_ids:
        query = query.where(Overlay.id.not_in(keep_ids))
    result = await session.execute(query.returning(Overlay.id), execution_options={"synchronize_session": False})
    deleted_ids = [row[0] for row in result.fetchall()]
    await session.flush()
    return deleted_ids


async def get_overlay(
    session: AsyncSession,
    overlay_id: UUID,
) -> Overlay | None:
    query = select(Overlay).where(Overlay.id == overlay_id)
    result = await session.execute(query)
    return result.unique().scalar_one_or_none()


async def delete_overlay(
    session: AsyncSession,
    overlay_id: UUID,
) -> bool:
    """Delete an overlay. Returns True if deleted, False if not found."""
    query = select(Overlay).where(Overlay.id == overlay_id)
    result = await session.execute(query)
    overlay = result.scalars().first()

    if overlay:
        await session.delete(overlay)
        await session.flush()
        return True
    else:
        return False
