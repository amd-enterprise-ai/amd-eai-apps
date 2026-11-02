# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.charts.registration import REGISTRATION_CREATOR, normalize_api_files, register_workloads


def make_session_scope_cm(session: AsyncMock | None = None) -> tuple[AsyncMock, AsyncMock]:
    """Build an async context manager that yields an AsyncSession-like object."""
    if session is None:
        session = AsyncMock(name="AsyncSession", spec=AsyncSession)
    cm = AsyncMock(name="session_scope_cm", spec=["__aenter__", "__aexit__"])
    # Make __aenter__ async by wrapping the return value
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm, session


def make_workload(
    *,
    chart_name: str,
    chart_type: str = "INFERENCE",
    metadata: dict | None = None,
    chart_upload_data: dict | None = None,
    overlay_files: list[tuple[Path, str]] | None = None,
) -> MagicMock:
    """
    Build a MagicMock workload with the minimal API used by register_workloads.
    - get_overlay_files returns a list of (Path, rel_path_str)
    """
    wl = MagicMock(
        name="WorkloadMock",
        spec=["chart_name", "type", "get_metadata_for_api", "get_chart_upload_data", "get_overlay_files"],
    )
    wl.chart_name = chart_name
    wl.type = chart_type
    wl.get_metadata_for_api.return_value = metadata or {}
    wl.get_chart_upload_data.return_value = chart_upload_data or {
        "signature": ["sig/path.yaml"],  # list to exercise normalize_api_files
        "files": ["a", "b"],
    }
    wl.get_overlay_files.return_value = overlay_files or []
    return wl


def write_overlay(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


@pytest.mark.asyncio
@patch("app.charts.registration.delete_overlays_absent_from_chart", autospec=True)
@patch("app.charts.registration.update_overlay", autospec=True)
@patch("app.charts.registration.create_overlay", autospec=True)
@patch("app.charts.registration.list_overlays", autospec=True)
@patch("app.charts.registration.update_chart", autospec=True)
@patch("app.charts.registration.create_chart", autospec=True)
@patch("app.charts.registration.select_chart", autospec=True)
@patch("app.charts.registration.get_registerable_workloads", autospec=True)
@patch("app.charts.registration.session_ctx", autospec=True)
async def test_updates_existing_chart_and_overlay(
    session_scope_mock: MagicMock,
    mock_get_registerable_workloads: AsyncMock,
    mock_select_chart: AsyncMock,
    mock_create_chart: AsyncMock,
    mock_update_chart: AsyncMock,
    mock_list_overlays: AsyncMock,
    mock_create_overlay: AsyncMock,
    mock_update_overlay: AsyncMock,
    mock_prune_overlays: AsyncMock,
    tmp_path: Path,
    db_session: AsyncSession,
) -> None:
    cm, _session = make_session_scope_cm(db_session)
    session_scope_mock.return_value = cm
    mock_prune_overlays.return_value = []

    chart_id = uuid4()
    overlay_id = uuid4()

    # Overlay YAML includes model field; code will use it for canonical_name
    overlay_path = write_overlay(tmp_path, "valid_overlay.yaml", "model: foo/bar\nx: 1\n")
    wl = make_workload(chart_name="Existing Chart", overlay_files=[(overlay_path, "overlays/valid_overlay.yaml")])

    mock_get_registerable_workloads.return_value = [wl]
    mock_select_chart.return_value = SimpleNamespace(id=chart_id)
    mock_update_chart.return_value = SimpleNamespace(id=chart_id)
    mock_list_overlays.return_value = [SimpleNamespace(id=overlay_id, canonical_name="foo/bar")]

    await register_workloads()

    mock_create_chart.assert_not_awaited()
    mock_update_chart.assert_awaited_once()
    mock_create_overlay.assert_not_awaited()
    mock_update_overlay.assert_awaited_once()

    assert mock_update_overlay.await_args is not None
    args, kwargs = mock_update_overlay.await_args
    assert args == ()
    assert kwargs["overlay_id"] == overlay_id
    ov = kwargs["overlay_update"]
    assert str(ov.chart_id) == str(chart_id)
    assert ov.updated_by == "system"


@pytest.mark.asyncio
@patch("app.charts.registration.delete_overlays_absent_from_chart", autospec=True)
@patch("app.charts.registration.update_overlay", autospec=True)
@patch("app.charts.registration.create_overlay", autospec=True)
@patch("app.charts.registration.list_overlays", autospec=True)
@patch("app.charts.registration.update_chart", autospec=True)
@patch("app.charts.registration.create_chart", autospec=True)
@patch("app.charts.registration.select_chart", autospec=True)
@patch("app.charts.registration.get_registerable_workloads", autospec=True)
@patch("app.charts.registration.session_ctx", autospec=True)
async def test_updates_existing_chart_creates_overlay_when_missing(
    session_scope_mock: MagicMock,
    mock_get_registerable_workloads: AsyncMock,
    mock_select_chart: AsyncMock,
    mock_create_chart: AsyncMock,
    mock_update_chart: AsyncMock,
    mock_list_overlays: AsyncMock,
    mock_create_overlay: AsyncMock,
    mock_update_overlay: AsyncMock,
    mock_prune_overlays: AsyncMock,
    tmp_path: Path,
    db_session: AsyncSession,
) -> None:
    cm, _session = make_session_scope_cm(db_session)
    session_scope_mock.return_value = cm
    mock_prune_overlays.return_value = []

    chart_id = uuid4()

    overlay_dict = {"model": "new/overlay", "a": 1}
    overlay_path = write_overlay(tmp_path, "new_overlay.yaml", yaml.safe_dump(overlay_dict))
    wl = make_workload(chart_name="Existing Chart", overlay_files=[(overlay_path, "overlays/new_overlay.yaml")])

    mock_get_registerable_workloads.return_value = [wl]
    mock_select_chart.return_value = SimpleNamespace(id=chart_id)
    mock_update_chart.return_value = SimpleNamespace(id=chart_id)
    mock_list_overlays.return_value = []

    await register_workloads()

    mock_create_chart.assert_not_awaited()
    mock_update_chart.assert_awaited_once()
    mock_update_overlay.assert_not_awaited()
    mock_create_overlay.assert_awaited_once()

    mock_create_overlay.assert_awaited_once_with(
        session=ANY, chart_id=chart_id, overlay_data=overlay_dict, canonical_name="new/overlay", creator="system"
    )


@pytest.mark.asyncio
@patch("app.charts.registration.delete_overlays_absent_from_chart", autospec=True)
@patch("app.charts.registration.update_overlay", autospec=True)
@patch("app.charts.registration.create_overlay", autospec=True)
@patch("app.charts.registration.list_overlays", autospec=True)
@patch("app.charts.registration.update_chart", autospec=True)
@patch("app.charts.registration.create_chart", autospec=True)
@patch("app.charts.registration.select_chart", autospec=True)
@patch("app.charts.registration.get_registerable_workloads", autospec=True)
@patch("app.charts.registration.session_ctx", autospec=True)
async def test_generic_overlay_does_not_adopt_unrelated_canonical_overlay(
    session_scope_mock: MagicMock,
    mock_get_registerable_workloads: AsyncMock,
    mock_select_chart: AsyncMock,
    mock_create_chart: AsyncMock,
    mock_update_chart: AsyncMock,
    mock_list_overlays: AsyncMock,
    mock_create_overlay: AsyncMock,
    mock_update_overlay: AsyncMock,
    mock_prune_overlays: AsyncMock,
    tmp_path: Path,
    db_session: AsyncSession,
) -> None:
    """A generic file (no `model:` field) must not adopt a stale canonical-named overlay's row.

    list_overlays(canonical_name=None) returns every overlay for the chart, so registering a
    generic file alongside an existing model-specific overlay must not pick that unrelated row
    as "the existing overlay" for the generic file.
    """
    cm, _session = make_session_scope_cm(db_session)
    session_scope_mock.return_value = cm
    mock_prune_overlays.return_value = []

    chart_id = uuid4()
    stale_canonical_id = uuid4()
    new_generic_id = uuid4()

    overlay_path = write_overlay(tmp_path, "generic.yaml", "a: 1\n")
    wl = make_workload(chart_name="Existing Chart", overlay_files=[(overlay_path, "overlays/generic.yaml")])

    mock_get_registerable_workloads.return_value = [wl]
    mock_select_chart.return_value = SimpleNamespace(id=chart_id)
    mock_update_chart.return_value = SimpleNamespace(id=chart_id)
    mock_list_overlays.return_value = [SimpleNamespace(id=stale_canonical_id, canonical_name="stale/model")]
    mock_create_overlay.return_value = SimpleNamespace(id=new_generic_id)

    await register_workloads()

    mock_update_overlay.assert_not_awaited()
    mock_create_overlay.assert_awaited_once_with(
        session=ANY, chart_id=chart_id, overlay_data={"a": 1}, canonical_name=None, creator="system"
    )
    mock_prune_overlays.assert_awaited_once_with(
        ANY, chart_id=chart_id, keep_ids=[new_generic_id], creator=REGISTRATION_CREATOR
    )


@pytest.mark.asyncio
@patch("app.charts.registration.delete_overlays_absent_from_chart", autospec=True)
@patch("app.charts.registration.update_overlay", autospec=True)
@patch("app.charts.registration.create_overlay", autospec=True)
@patch("app.charts.registration.list_overlays", autospec=True)
@patch("app.charts.registration.update_chart", autospec=True)
@patch("app.charts.registration.create_chart", autospec=True)
@patch("app.charts.registration.select_chart", autospec=True)
@patch("app.charts.registration.get_registerable_workloads", autospec=True)
@patch("app.charts.registration.session_ctx", autospec=True)
async def test_updates_chart_only_when_no_overlay_files(
    session_scope_mock: MagicMock,
    mock_get_registerable_workloads: AsyncMock,
    mock_select_chart: AsyncMock,
    mock_create_chart: AsyncMock,
    mock_update_chart: AsyncMock,
    mock_list_overlays: AsyncMock,
    mock_create_overlay: AsyncMock,
    mock_update_overlay: AsyncMock,
    mock_prune_overlays: AsyncMock,
    db_session: AsyncSession,
) -> None:
    cm, _session = make_session_scope_cm(db_session)
    session_scope_mock.return_value = cm
    mock_prune_overlays.return_value = []

    chart_id = uuid4()
    wl = make_workload(chart_name="Existing Chart", overlay_files=[])

    mock_get_registerable_workloads.return_value = [wl]
    mock_select_chart.return_value = SimpleNamespace(id=chart_id)
    mock_update_chart.return_value = SimpleNamespace(id=chart_id)

    await register_workloads()

    mock_create_chart.assert_not_awaited()
    mock_update_chart.assert_awaited_once()
    mock_create_overlay.assert_not_awaited()
    mock_update_overlay.assert_not_awaited()
    mock_list_overlays.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.charts.registration.delete_overlays_absent_from_chart", autospec=True)
@patch("app.charts.registration.update_overlay", autospec=True)
@patch("app.charts.registration.create_overlay", autospec=True)
@patch("app.charts.registration.list_overlays", autospec=True)
@patch("app.charts.registration.update_chart", autospec=True)
@patch("app.charts.registration.create_chart", autospec=True)
@patch("app.charts.registration.select_chart", autospec=True)
@patch("app.charts.registration.get_registerable_workloads", autospec=True)
@patch("app.charts.registration.session_ctx", autospec=True)
async def test_creates_new_chart_and_overlay(
    session_scope_mock: MagicMock,
    mock_get_registerable_workloads: AsyncMock,
    mock_select_chart: AsyncMock,
    mock_create_chart: AsyncMock,
    mock_update_chart: AsyncMock,
    mock_list_overlays: AsyncMock,
    mock_create_overlay: AsyncMock,
    mock_update_overlay: AsyncMock,
    mock_prune_overlays: AsyncMock,
    tmp_path: Path,
) -> None:
    cm, _session = make_session_scope_cm()
    session_scope_mock.return_value = cm
    mock_prune_overlays.return_value = []

    new_chart_id = uuid4()
    overlay_dict = {"model": "brand/new", "z": 9}
    overlay_path = write_overlay(tmp_path, "brand_new.yaml", yaml.safe_dump(overlay_dict))
    wl = make_workload(chart_name="Brand New", overlay_files=[(overlay_path, "overlays/brand_new.yaml")])

    mock_get_registerable_workloads.return_value = [wl]
    mock_select_chart.return_value = None
    mock_create_chart.return_value = SimpleNamespace(id=new_chart_id)
    mock_list_overlays.return_value = []

    await register_workloads()

    mock_create_chart.assert_awaited_once()
    mock_update_chart.assert_not_awaited()
    mock_update_overlay.assert_not_awaited()
    mock_create_overlay.assert_awaited_once()

    mock_create_overlay.assert_awaited_once_with(
        session=ANY, chart_id=new_chart_id, overlay_data=overlay_dict, canonical_name="brand/new", creator="system"
    )


@pytest.mark.asyncio
@patch("app.charts.registration.delete_overlays_absent_from_chart", autospec=True)
@patch("app.charts.registration.update_overlay", autospec=True)
@patch("app.charts.registration.create_overlay", autospec=True)
@patch("app.charts.registration.list_overlays", autospec=True)
@patch("app.charts.registration.update_chart", autospec=True)
@patch("app.charts.registration.create_chart", autospec=True)
@patch("app.charts.registration.select_chart", autospec=True)
@patch("app.charts.registration.get_registerable_workloads", autospec=True)
@patch("app.charts.registration.session_ctx", autospec=True)
async def test_invalid_overlay_yaml_raises_value_error_when_overlay_missing(
    session_scope_mock: MagicMock,
    mock_get_registerable_workloads: AsyncMock,
    mock_select_chart: AsyncMock,
    mock_create_chart: AsyncMock,
    mock_update_chart: AsyncMock,
    mock_list_overlays: AsyncMock,
    mock_create_overlay: AsyncMock,
    mock_update_overlay: AsyncMock,
    mock_prune_overlays: AsyncMock,
    tmp_path: Path,
) -> None:
    cm, _session = make_session_scope_cm()
    session_scope_mock.return_value = cm
    mock_prune_overlays.return_value = []

    chart_id = uuid4()
    overlay_path = write_overlay(tmp_path, "bad.yaml", "not: valid: [")

    wl = make_workload(chart_name="Existing Chart", overlay_files=[(overlay_path, "overlays/bad.yaml")])

    mock_get_registerable_workloads.return_value = [wl]
    mock_select_chart.return_value = SimpleNamespace(id=chart_id)
    mock_update_chart.return_value = SimpleNamespace(id=chart_id)
    mock_list_overlays.return_value = []  # go down the "create" path

    with patch("app.charts.registration.yaml.safe_load", return_value=None):
        with pytest.raises(ValueError, match="Overlay data is required for creating an overlay."):
            await register_workloads()

    mock_update_chart.assert_awaited_once()
    mock_create_overlay.assert_not_awaited()
    mock_update_overlay.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.charts.registration.delete_overlays_absent_from_chart", autospec=True)
@patch("app.charts.registration.update_overlay", autospec=True)
@patch("app.charts.registration.create_overlay", autospec=True)
@patch("app.charts.registration.list_overlays", autospec=True)
@patch("app.charts.registration.update_chart", autospec=True)
@patch("app.charts.registration.create_chart", autospec=True)
@patch("app.charts.registration.select_chart", autospec=True)
@patch("app.charts.registration.get_registerable_workloads", autospec=True)
@patch("app.charts.registration.session_ctx", autospec=True)
async def test_prunes_overlays_the_chart_no_longer_ships(
    session_scope_mock: MagicMock,
    mock_get_registerable_workloads: AsyncMock,
    mock_select_chart: AsyncMock,
    mock_create_chart: AsyncMock,
    mock_update_chart: AsyncMock,
    mock_list_overlays: AsyncMock,
    mock_create_overlay: AsyncMock,
    mock_update_overlay: AsyncMock,
    mock_prune_overlays: AsyncMock,
    tmp_path: Path,
    db_session: AsyncSession,
) -> None:
    cm, _session = make_session_scope_cm(db_session)
    session_scope_mock.return_value = cm

    chart_id = uuid4()
    shipped_id = uuid4()
    stale_id = uuid4()

    overlay_path = write_overlay(tmp_path, "shipped.yaml", "model: still/shipped\n")
    wl = make_workload(chart_name="Existing Chart", overlay_files=[(overlay_path, "overlays/shipped.yaml")])

    mock_get_registerable_workloads.return_value = [wl]
    mock_select_chart.return_value = SimpleNamespace(id=chart_id)
    mock_update_chart.return_value = SimpleNamespace(id=chart_id)
    mock_list_overlays.return_value = [SimpleNamespace(id=shipped_id, canonical_name="still/shipped")]
    mock_update_overlay.return_value = SimpleNamespace(id=shipped_id)
    mock_prune_overlays.return_value = [stale_id]

    await register_workloads()

    mock_prune_overlays.assert_awaited_once_with(
        ANY, chart_id=chart_id, keep_ids=[shipped_id], creator=REGISTRATION_CREATOR
    )


@pytest.mark.asyncio
@patch("app.charts.registration.delete_overlays_absent_from_chart", autospec=True)
@patch("app.charts.registration.update_overlay", autospec=True)
@patch("app.charts.registration.create_overlay", autospec=True)
@patch("app.charts.registration.list_overlays", autospec=True)
@patch("app.charts.registration.update_chart", autospec=True)
@patch("app.charts.registration.create_chart", autospec=True)
@patch("app.charts.registration.select_chart", autospec=True)
@patch("app.charts.registration.get_registerable_workloads", autospec=True)
@patch("app.charts.registration.session_ctx", autospec=True)
async def test_skips_pruning_when_no_recipe_files_are_discovered(
    session_scope_mock: MagicMock,
    mock_get_registerable_workloads: AsyncMock,
    mock_select_chart: AsyncMock,
    mock_create_chart: AsyncMock,
    mock_update_chart: AsyncMock,
    mock_list_overlays: AsyncMock,
    mock_create_overlay: AsyncMock,
    mock_update_overlay: AsyncMock,
    mock_prune_overlays: AsyncMock,
    db_session: AsyncSession,
) -> None:
    """A chart yielding no recipe files is left untouched rather than emptied.

    Discovering nothing is indistinguishable from never having looked: a misconfigured
    ALLOWED_CHART_PATHS or an incomplete checkout produces the same empty list as a chart that
    genuinely dropped its recipes. Pruning on that reading wipes the whole registered catalog.
    """
    cm, _session = make_session_scope_cm(db_session)
    session_scope_mock.return_value = cm

    chart_id = uuid4()
    wl = make_workload(chart_name="Existing Chart", overlay_files=[])

    mock_get_registerable_workloads.return_value = [wl]
    mock_select_chart.return_value = SimpleNamespace(id=chart_id)
    mock_update_chart.return_value = SimpleNamespace(id=chart_id)

    await register_workloads()

    mock_prune_overlays.assert_not_awaited()


# Tests for normalize_api_files function


def test_normalize_api_files_with_list_signature() -> None:
    """Test normalize_api_files extracts first item from signature list."""
    files = {"signature": ["sig1.yaml", "sig2.yaml"], "files": ["file1.yaml", "file2.yaml"]}

    result = normalize_api_files(files)

    assert result == {"files": ["file1.yaml", "file2.yaml"], "signature": "sig1.yaml"}  # First item from list


def test_normalize_api_files_with_string_signature() -> None:
    """Test normalize_api_files preserves string signature unchanged."""
    files = {"signature": "single_sig.yaml", "files": ["file1.yaml", "file2.yaml"]}

    result = normalize_api_files(files)

    assert result == {"files": ["file1.yaml", "file2.yaml"], "signature": "single_sig.yaml"}  # Unchanged


def test_normalize_api_files_with_empty_list_signature() -> None:
    """Test normalize_api_files handles empty signature list safely."""
    files = {"signature": [], "files": ["file1.yaml"]}

    result = normalize_api_files(files)

    assert result == {"files": ["file1.yaml"], "signature": []}  # Empty list unchanged
