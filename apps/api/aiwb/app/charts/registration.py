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

from ..overlays.models import Overlay
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

                overlay_files = workload.get_overlay_files()
                chart_overlays = list(await list_overlays(session=session, chart_id=chart.id)) if overlay_files else []
                registered_ids = [
                    await register_overlay(
                        session,
                        chart_id=chart.id,
                        file_path=file_path,
                        source_path=Path(rel_path_str).as_posix(),
                        chart_overlays=chart_overlays,
                    )
                    for file_path, rel_path_str in overlay_files
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


async def register_overlay(
    session: AsyncSession, chart_id: UUID, file_path: Path, source_path: str, chart_overlays: list[Overlay]
) -> UUID:
    """Create or refresh the overlay row backing a single recipe file, returning its ID.

    `source_path` is the file's path relative to the chart; it is the row's identity, since several
    files may declare the same model. `chart_overlays` is the chart's overlays, loaded once per
    chart and kept current here as rows are written, so each file need not reload them.
    """
    raw_data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    # An emptied file must not refresh its row: the row would keep the old model-specific body while
    # losing its canonical name, turning it into a generic overlay merged into every model's launch.
    if not raw_data or not isinstance(raw_data, dict):
        raise ValueError(f"Overlay data is required for recipe file '{source_path}'.")
    canonical_name = OverlayData(**raw_data).canonical_name

    existing = next((overlay for overlay in chart_overlays if overlay.source_path == source_path), None)
    if existing is None:
        # Rows registered before overlays recorded their file carry no source path. The first file
        # declaring the same model adopts one, so the upgrade neither duplicates a recipe nor leaves
        # a stale copy that pruning cannot trace. Only rows this registration created qualify: a
        # generic file must never adopt an unrelated canonical-named row, nor any row an API user
        # authored.
        existing = next(
            (
                overlay
                for overlay in chart_overlays
                if overlay.source_path is None
                and overlay.created_by == REGISTRATION_CREATOR
                and overlay.canonical_name == canonical_name
            ),
            None,
        )

    if existing is not None:
        overlay = await update_overlay(
            session=session,
            overlay_id=existing.id,
            overlay_update=OverlayUpdate(
                chart_id=chart_id,
                canonical_name=canonical_name,
                source_path=source_path,
                overlay=raw_data,
                updated_by=REGISTRATION_CREATOR,
            ),
        )
        chart_overlays.remove(existing)
    else:
        overlay = await create_overlay(
            session=session,
            chart_id=chart_id,
            overlay_data=raw_data,
            canonical_name=canonical_name,
            creator=REGISTRATION_CREATOR,
            source_path=source_path,
        )
    chart_overlays.append(overlay)
    return overlay.id


def normalize_api_files(files: dict) -> dict[str, str]:
    """Normalize files for API upload."""
    signature = files.get("signature")
    if isinstance(signature, list) and signature:
        signature = signature[0]
    return {"files": files["files"], "signature": signature}
