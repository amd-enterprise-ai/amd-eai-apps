# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import yaml
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.database import get_session
from workloads_manager.core.workloads import get_registerable_workloads
from workloads_manager.models import OverlayData

from ..overlays.repository import delete_overlays_absent_from_chart, list_overlays
from ..overlays.schemas import OverlayUpdate
from ..overlays.service import create_overlay, update_overlay
from .repository import create_chart, select_chart, update_chart
from .schemas import ChartCreate, ChartUpdate

session_ctx = asynccontextmanager(get_session)

# Marks rows this registration pass owns, so pruning never removes API-authored overlays.
REGISTRATION_CREATOR = "system"


async def register_workloads() -> None:
    """Register workloads in the system."""
    registerable_workloads = get_registerable_workloads()

    if len(registerable_workloads) == 0:
        logger.error("No workloads found to register. This usually means the workloads directory is missing or empty.")
        logger.error(
            "Please run 'uv run wm init' manually in the workloads_manager package directory to initialize the workloads repository."
        )
        raise ValueError("No workloads found to register.")

    logger.info(f"Registering {len(registerable_workloads)} workloads.")
    created = 0
    updated = 0
    async with session_ctx() as session:
        try:
            for workload in registerable_workloads:
                # Register workload to create or update charts
                form_data: dict[str, str | list | dict | None] = {"name": workload.chart_name, "type": workload.type}
                metadata = workload.get_metadata_for_api()
                api_files = workload.get_chart_upload_data()

                form_data.update(metadata)
                form_data.update(normalize_api_files(api_files))
                chart = await select_chart(session, chart_name=workload.chart_name)
                if chart:
                    updated += 1
                    schema = ChartUpdate(**form_data)
                    chart = await update_chart(
                        session, chart_id=chart.id, update_schema=schema, creator=REGISTRATION_CREATOR
                    )
                else:
                    created += 1
                    schema = ChartCreate(**form_data)
                    chart = await create_chart(session, chart_schema=schema, creator=REGISTRATION_CREATOR)

                registered_ids = [
                    await register_overlay(session, chart_id=chart.id, file_path=file_path)
                    for file_path, _rel_path_str in workload.get_overlay_files()
                ]
                # Finding no recipe files is ambiguous: the chart may ship none, or the overlay
                # directories may never have been read (ALLOWED_CHART_PATHS carrying no
                # `overrides/` entry, a missing chart checkout). Both look identical here, and
                # pruning on the second reading deletes the chart's entire registered catalog.
                if not registered_ids:
                    continue
                pruned_ids = await delete_overlays_absent_from_chart(
                    session, chart_id=chart.id, keep_ids=registered_ids, creator=REGISTRATION_CREATOR
                )
                if pruned_ids:
                    logger.info(f"Pruned {len(pruned_ids)} overlays no longer shipped by '{workload.chart_name}'.")
            logger.info(f"Registration complete: {created} created, {updated} updated")
        except Exception as e:
            await session.rollback()
            logger.exception("Registration failed")
            raise e


async def register_overlay(session: AsyncSession, chart_id: UUID, file_path: Path) -> UUID:
    """Create or refresh the overlay row backing a single recipe file, returning its ID."""
    raw_data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    canonical_name = OverlayData(**raw_data).canonical_name if raw_data and isinstance(raw_data, dict) else None

    # list_overlays returns every overlay for the chart when canonical_name is None, so filter
    # explicitly: a generic file must never adopt an unrelated canonical-named overlay's row.
    existing_overlays = [
        overlay
        for overlay in await list_overlays(session=session, chart_id=chart_id, canonical_name=canonical_name)
        if overlay.canonical_name == canonical_name
    ]
    overlay_schema: dict = {"chart_id": chart_id}
    if raw_data:
        overlay_schema["overlay"] = raw_data

    if existing_overlays:
        overlay = await update_overlay(
            session=session,
            overlay_id=existing_overlays[0].id,
            overlay_update=OverlayUpdate(**overlay_schema, updated_by=REGISTRATION_CREATOR),
        )
    else:
        if not raw_data:
            raise ValueError("Overlay data is required for creating an overlay.")
        overlay = await create_overlay(
            session=session,
            chart_id=chart_id,
            overlay_data=raw_data,
            canonical_name=canonical_name,
            creator=REGISTRATION_CREATOR,
        )
    return overlay.id


def normalize_api_files(files: dict) -> dict[str, str]:
    """Normalize files for API upload."""
    signature = files.get("signature")
    if isinstance(signature, list) and signature:
        signature = signature[0]
    return {"files": files["files"], "signature": signature}
