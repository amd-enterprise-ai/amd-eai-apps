# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import uuid
from typing import Any

import yaml
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import NotFoundException, ValidationException
from api_common.models import set_updated_fields

from .models import Overlay
from .repository import delete_overlay, get_overlay, insert_overlay
from .schemas import OverlayUpdate


async def create_overlay(
    session: AsyncSession,
    chart_id: uuid.UUID,
    overlay_data: dict[str, Any],
    canonical_name: str | None = None,
    display_name: str | None = None,
    creator: str | None = None,
    source_path: str | None = None,
) -> Overlay:
    overlay = await insert_overlay(
        session=session,
        chart_id=chart_id,
        overlay_data=overlay_data,
        canonical_name=canonical_name,
        display_name=display_name,
        creator=creator,
        source_path=source_path,
    )
    return overlay


async def update_overlay(
    session: AsyncSession,
    overlay_id: uuid.UUID,
    overlay_update: OverlayUpdate,
) -> Overlay:
    """Update an existing overlay."""
    overlay = await get_overlay(session, overlay_id)
    if not overlay:
        raise NotFoundException(f"Overlay with ID {overlay_id} not found")
    overlay_data = overlay_update.model_dump(exclude_unset=True)
    # Update the overlay data
    for key, value in overlay_data.items():
        setattr(overlay, key, value)

    set_updated_fields(overlay, overlay_update.updated_by)

    session.add(overlay)
    await session.flush()
    return overlay


async def parse_overlay_file(file: UploadFile) -> dict[str, Any]:
    """Parse a YAML file into a dictionary."""
    if not file.filename.endswith((".yml", ".yaml")):
        raise ValidationException("Invalid file format. Only YAML files are accepted.")

    try:
        contents = await file.read()
        return yaml.safe_load(contents)
    except yaml.YAMLError as e:
        raise ValidationException(f"Invalid YAML format: {str(e)}")
    finally:
        await file.close()


async def get_overlay_by_id(session: AsyncSession, overlay_id: uuid.UUID) -> Overlay:
    """Get an overlay by ID, raising NotFoundException if not found."""
    overlay = await get_overlay(session, overlay_id)
    if not overlay:
        raise NotFoundException(f"Overlay with ID {overlay_id} not found")
    return overlay


async def delete_overlay_by_id_service(session: AsyncSession, overlay_id: uuid.UUID) -> None:
    """Delete an overlay, raising NotFoundException if not found."""
    deleted = await delete_overlay(session, overlay_id)
    if not deleted:
        raise NotFoundException(f"Overlay with ID {overlay_id} not found")
