# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Registration functionality."""

from pathlib import Path

import httpx
import yaml
from loguru import logger

from .. import config
from ..core.workloads import get_workloads
from ..models import (
    FileProcessingResult,
    OverlayData,
    ProcessingStats,
    ProcessingStatus,
    WorkloadRegistrationResult,
)
from .api import check_api_server, make_api_request
from .utils import temp_file_with_content

# The creator AIWB records on the overlays it registers itself at startup.
SERVICE_REGISTRATION_CREATOR = "system"


def register_workload(workload_name: str, api_url: httpx.URL) -> WorkloadRegistrationResult:
    """Register a workload template to the service."""
    workload = next((w for w in get_workloads() if w.dir_name == workload_name), None)

    if not workload:
        logger.error(f"Workload {workload_name} not found")
        return WorkloadRegistrationResult(success=False, error=f"Workload {workload_name} not found")

    if not workload.is_registerable:
        logger.error(f"Workload {workload_name} is not registerable (missing metadata)")
        return WorkloadRegistrationResult(
            success=False, error=f"Workload {workload_name} is not registerable (missing metadata)"
        )

    if not config.TOKEN:
        logger.error("TOKEN environment variable not set")
        return WorkloadRegistrationResult(success=False, error="TOKEN environment variable not set")

    if not check_api_server(api_url):
        logger.error(f"Cannot register workload: API server at {api_url} is not accessible")
        return WorkloadRegistrationResult(
            success=False, error=f"Cannot register workload: API server at {api_url} is not accessible"
        )

    logger.info(f"Processing chart: {workload.chart_name}")
    chart_id = upload_chart(workload.path, api_url)

    if not chart_id:
        logger.error("Failed to upload chart. Please check API server accessibility.")
        return WorkloadRegistrationResult(
            success=False,
            error="Failed to upload chart. Please check API server accessibility.",
            chart_name=workload.chart_name,
        )

    processed_files: list[FileProcessingResult] = []
    stats = ProcessingStats()

    # Process overlay files using workload method
    overlay_files = workload.get_overlay_files()
    for file_path, rel_path_str in overlay_files:
        status, file_id = process_single_overlay(file_path, rel_path_str, api_url, chart_id)
        result = FileProcessingResult(path=rel_path_str, status=ProcessingStatus(status), id=file_id)
        processed_files.append(result)
        stats.increment(ProcessingStatus(status))

    # A failed upload leaves this run's set of recipes incomplete, and pruning against it would
    # delete recipes that still ship.
    if processed_files and all(result.status == ProcessingStatus.SUCCESS for result in processed_files):
        prune_overlays_absent_from_workload(chart_id, {result.id for result in processed_files}, api_url)

    # Process all other files for reporting (chart files + skipped files)
    processed_paths = {result.path for result in processed_files}

    for file_path, rel_path_str in workload._iter_files():
        if rel_path_str in processed_paths:
            continue  # Already processed as overlay

        if workload._is_allowed_file(rel_path_str):
            # This is a chart file (not overlay)
            result = FileProcessingResult(path=rel_path_str, status=ProcessingStatus.SUCCESS, id="Part of chart")
        else:
            # This file is not allowed/skipped
            result = FileProcessingResult(path=rel_path_str, status=ProcessingStatus.SKIPPED, id="")

        processed_files.append(result)
        stats.increment(result.status)

    return WorkloadRegistrationResult(
        success=True,
        chart_id=chart_id,
        chart_name=workload.chart_name,
        files=processed_files,
        stats=stats,
    )


def upload_chart(workload_path: Path, api_url: httpx.URL) -> str | None:
    """Upload or update a chart to the service and return the chart ID."""
    workload = next((w for w in get_workloads() if w.dir_name == workload_path.name), None)
    if not workload:
        logger.error(f"Workload {workload_path.name} not found")
        return None

    if not workload.chart_path.exists():
        logger.error(f"Chart directory not found at {workload.chart_path}")
        return None

    api_files = workload.get_chart_upload_data()
    if not api_files:
        return None

    # Build form data with basic fields and metadata
    form_data: dict[str, str | list | dict | None] = {"name": workload.chart_name, "type": workload.type}

    # Add metadata fields if available
    metadata = workload.get_metadata_for_api()
    form_data.update(metadata)

    existing_chart_id = get_chart_id(workload.chart_name, api_url)  # type: ignore
    if existing_chart_id:
        endpoint = f"charts/{existing_chart_id}"
        method = "PUT"
        logger.info(
            f"Updating chart: {workload.chart_name} (ID: {existing_chart_id}) with {len(api_files['files'])} chart files + signature"
        )
    else:
        endpoint = "charts"
        method = "POST"
        logger.info(f"Creating chart: {workload.chart_name} with {len(api_files['files'])} chart files + signature")

    success, response_data = make_api_request(method, endpoint, api_url, data=form_data, files=api_files)

    if not success:
        error_msg = response_data.get("error", "Unknown error")
        if "detail" in response_data:
            error_msg = response_data["detail"]
        logger.error(f"Failed to upload chart: {error_msg}")
        return None

    # For updates, return the existing chart_id; for creates, extract from response
    if existing_chart_id:
        logger.info(f"Successfully updated chart with ID: {existing_chart_id}")
        return existing_chart_id
    else:
        new_chart_id = response_data.get("id")
        if not new_chart_id:
            if "detail" in response_data:
                logger.error(f"API error details: {response_data['detail']}")
            logger.error("Chart creation response did not contain an ID")
            logger.debug(f"Full response: {response_data}")
            return None

        logger.info(f"Successfully created chart with ID: {new_chart_id}")
        return new_chart_id


def get_chart_id(chart_name: str, api_url: httpx.URL) -> str | None:
    """Get the ID of a chart by name."""
    success, response = make_api_request("GET", "charts", api_url)

    if not success:
        logger.debug(f"Failed to get chart ID for {chart_name}: {response.get('error', 'Unknown error')}")
        return None

    # The API returns a ListResponse with a "data" key containing a list of charts
    charts: list = []
    if isinstance(response, dict):
        if "data" in response:
            charts = response["data"]
        elif "id" in response:
            # Single chart object returned directly
            if response.get("name") == chart_name:
                chart_id = response.get("id")
                logger.debug(f"Found existing chart: {chart_name} (ID: {chart_id})")
                return chart_id
    elif isinstance(response, list):
        charts = response

    for chart in charts:
        if isinstance(chart, dict) and chart.get("name") == chart_name:
            chart_id = chart.get("id")
            if chart_id:
                logger.debug(f"Found existing chart: {chart_name} (ID: {chart_id})")
                return chart_id

    logger.debug(f"No existing chart found for: {chart_name}")
    return None


def list_chart_overlays(chart_id: str, api_url: httpx.URL) -> list[dict] | None:
    """Return the overlays registered on the chart, or None when they could not be listed."""
    success, response = make_api_request("GET", f"overlays?chartId={chart_id}", api_url)
    if not success:
        logger.debug(f"Failed to get overlays: {response.get('error', 'Unknown error')}")
        return None
    return [
        overlay
        for overlay in (
            response.get("data", []) if isinstance(response, dict) else response if isinstance(response, list) else []
        )
        if isinstance(overlay, dict)
    ]


def prune_overlays_absent_from_workload(chart_id: str, keep_ids: set[str], api_url: httpx.URL) -> list[str]:
    """Delete the chart's file-backed overlays this registration did not register, returning their IDs.

    A recipe file renamed or removed in the workload otherwise leaves its row behind, still offered
    as a recipe. Only overlays registered from a file qualify: one authored through the API has no
    source path and is its author's to manage. Overlays AIWB registered itself are left to its own
    startup registration, which prunes them against the chart it ships.
    """
    overlays = list_chart_overlays(chart_id, api_url)
    if overlays is None:
        logger.warning("Could not list the chart's overlays; skipping removal of overlays it no longer ships.")
        return []

    pruned_ids: list[str] = []
    for overlay in overlays:
        overlay_id = overlay.get("id")
        if (
            overlay_id is None
            or overlay_id in keep_ids
            or overlay.get("sourcePath") is None
            or overlay.get("createdBy") == SERVICE_REGISTRATION_CREATOR
        ):
            continue
        success, response = make_api_request("DELETE", f"overlays/{overlay_id}", api_url)
        if success:
            logger.info(f"Removed overlay {overlay_id} for {overlay['sourcePath']}, which the workload no longer ships")
            pruned_ids.append(overlay_id)
        else:
            logger.error(f"Failed to remove overlay {overlay_id}: {response.get('error', 'Unknown error')}")
    return pruned_ids


def get_overlay_id(chart_id: str, source_path: str, canonical_name: str | None, api_url: httpx.URL) -> str | None:
    """Get the ID of the overlay registered from `source_path` on the chart.

    Several recipe files may declare the same model, so the file path is the overlay's identity.
    An overlay AIWB registered before overlays recorded their file has no source path; one declaring
    the same canonical name is adopted instead, so re-registering does not duplicate it. An overlay
    without a source path that anyone else created may be a user's API-authored override, so it is
    never adopted and the recipe gets a row of its own.
    """
    overlays = list_chart_overlays(chart_id, api_url)
    if overlays is None:
        return None
    for overlay in overlays:
        if overlay.get("sourcePath") == source_path:
            return overlay.get("id")
    for overlay in overlays:
        if (
            overlay.get("sourcePath") is None
            and overlay.get("createdBy") == SERVICE_REGISTRATION_CREATOR
            and overlay.get("canonicalName") == canonical_name
        ):
            return overlay.get("id")
    return None


def _get_canonical_name(rel_path_str: str, content: str, stem: str) -> str | None:
    """Return the canonical name for an overlay file, or None for non-model overlays."""
    if not rel_path_str.startswith("overrides/models/"):
        return None

    fallback = stem.replace("_", "/").replace(":", "/")
    try:
        raw_data = yaml.safe_load(content)
        if raw_data and isinstance(raw_data, dict):
            return OverlayData(**raw_data).canonical_name or fallback
    except Exception as e:
        logger.warning(f"Could not parse YAML from {stem}: {e}")
    return fallback


def process_single_overlay(overlay_file: Path, rel_path_str: str, api_url: httpx.URL, chart_id: str) -> tuple[str, str]:
    """Process a single overlay file and return (status, file_id)."""
    try:
        content = overlay_file.read_text(encoding="utf-8")
        canonical_name = _get_canonical_name(rel_path_str, content, overlay_file.stem)

        # Upload overlay directly
        with temp_file_with_content(content, suffix=".yaml") as temp_path:
            if not temp_path:
                logger.error(f"Failed to create temporary file for overlay: {overlay_file.name}")
                return (ProcessingStatus.FAILED, "Error creating temp file")

            source_path = Path(rel_path_str).as_posix()
            data = {"chartId": chart_id, "sourcePath": source_path}
            if canonical_name:
                data["canonicalName"] = canonical_name

            files = {"overlayFile": [Path(temp_path)]}

            existing_id = get_overlay_id(chart_id, source_path, canonical_name, api_url)
            endpoint = f"overlays/{existing_id}" if existing_id else "overlays"
            method = "PUT" if existing_id else "POST"

            success, response = make_api_request(method, endpoint, api_url, data=data, files=files)

            if success and "id" in response:
                overlay_id = existing_id or response["id"]
                action = "updated" if existing_id else "created"
                target = f"model {canonical_name}" if canonical_name else f"file {overlay_file.name}"
                logger.info(f"Successfully {action} overlay for {target} with ID: {overlay_id}")
                return (ProcessingStatus.SUCCESS, overlay_id)
            else:
                error_msg = response.get("error", "Unknown error")
                logger.error(f"Failed to upload overlay: {error_msg}")
                return (ProcessingStatus.FAILED, "")

    except Exception as e:
        logger.error(f"Error processing overlay {overlay_file}: {e}")
        return (ProcessingStatus.FAILED, "Error processing file")
