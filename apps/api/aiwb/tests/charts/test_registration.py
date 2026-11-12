# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from collections.abc import Iterator
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


def registered_row(
    canonical_name: str | None,
    source_path: str | None,
    created_by: str = REGISTRATION_CREATOR,
) -> SimpleNamespace:
    """A stored overlay row as list_overlays returns it."""
    return SimpleNamespace(id=uuid4(), canonical_name=canonical_name, source_path=source_path, created_by=created_by)


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

    # Overlay YAML includes model field; code will use it for canonical_name
    overlay_path = write_overlay(tmp_path, "valid_overlay.yaml", "model: foo/bar\nx: 1\n")
    wl = make_workload(chart_name="Existing Chart", overlay_files=[(overlay_path, "overlays/valid_overlay.yaml")])
    existing = registered_row("foo/bar", "overlays/valid_overlay.yaml")

    mock_get_registerable_workloads.return_value = [wl]
    mock_select_chart.return_value = SimpleNamespace(id=chart_id)
    mock_update_chart.return_value = SimpleNamespace(id=chart_id)
    mock_list_overlays.return_value = [existing]

    await register_workloads()

    mock_create_chart.assert_not_awaited()
    mock_update_chart.assert_awaited_once()
    mock_create_overlay.assert_not_awaited()
    mock_update_overlay.assert_awaited_once()

    assert mock_update_overlay.await_args is not None
    args, kwargs = mock_update_overlay.await_args
    assert args == ()
    assert kwargs["overlay_id"] == existing.id
    ov = kwargs["overlay_update"]
    assert str(ov.chart_id) == str(chart_id)
    assert ov.canonical_name == "foo/bar"
    assert ov.source_path == "overlays/valid_overlay.yaml"
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
        session=ANY,
        chart_id=chart_id,
        overlay_data=overlay_dict,
        canonical_name="new/overlay",
        creator="system",
        source_path="overlays/new_overlay.yaml",
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

    Registering a generic file alongside a model-specific overlay that predates source tracking
    must not pick that unrelated row as "the existing overlay" for the generic file.
    """
    cm, _session = make_session_scope_cm(db_session)
    session_scope_mock.return_value = cm
    mock_prune_overlays.return_value = []

    chart_id = uuid4()
    new_generic_id = uuid4()

    overlay_path = write_overlay(tmp_path, "generic.yaml", "a: 1\n")
    wl = make_workload(chart_name="Existing Chart", overlay_files=[(overlay_path, "overlays/generic.yaml")])

    mock_get_registerable_workloads.return_value = [wl]
    mock_select_chart.return_value = SimpleNamespace(id=chart_id)
    mock_update_chart.return_value = SimpleNamespace(id=chart_id)
    mock_list_overlays.return_value = [registered_row("stale/model", None)]
    mock_create_overlay.return_value = SimpleNamespace(id=new_generic_id)

    await register_workloads()

    mock_update_overlay.assert_not_awaited()
    mock_create_overlay.assert_awaited_once_with(
        session=ANY,
        chart_id=chart_id,
        overlay_data={"a": 1},
        canonical_name=None,
        creator="system",
        source_path="overlays/generic.yaml",
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
        session=ANY,
        chart_id=new_chart_id,
        overlay_data=overlay_dict,
        canonical_name="brand/new",
        creator="system",
        source_path="overlays/brand_new.yaml",
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
        with pytest.raises(ValueError, match="Overlay data is required for recipe file 'overlays/bad.yaml'"):
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
    stale_id = uuid4()

    overlay_path = write_overlay(tmp_path, "shipped.yaml", "model: still/shipped\n")
    wl = make_workload(chart_name="Existing Chart", overlay_files=[(overlay_path, "overlays/shipped.yaml")])
    shipped = registered_row("still/shipped", "overlays/shipped.yaml")

    mock_get_registerable_workloads.return_value = [wl]
    mock_select_chart.return_value = SimpleNamespace(id=chart_id)
    mock_update_chart.return_value = SimpleNamespace(id=chart_id)
    mock_list_overlays.return_value = [shipped]
    mock_update_overlay.return_value = SimpleNamespace(id=shipped.id)
    mock_prune_overlays.return_value = [stale_id]

    await register_workloads()

    mock_prune_overlays.assert_awaited_once_with(
        ANY, chart_id=chart_id, keep_ids=[shipped.id], creator=REGISTRATION_CREATOR
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


@pytest.fixture
def registration(db_session: AsyncSession) -> Iterator[SimpleNamespace]:
    """Patch register_workloads' collaborators around an existing chart, exposing the mocks by name."""
    cm, _session = make_session_scope_cm(db_session)
    chart_id = uuid4()
    with (
        patch("app.charts.registration.session_ctx", return_value=cm),
        patch("app.charts.registration.get_registerable_workloads") as get_workloads,
        patch("app.charts.registration.select_chart", return_value=SimpleNamespace(id=chart_id)),
        patch("app.charts.registration.update_chart", return_value=SimpleNamespace(id=chart_id)),
        patch("app.charts.registration.list_overlays") as list_overlays,
        patch("app.charts.registration.create_overlay") as create_overlay,
        patch("app.charts.registration.update_overlay") as update_overlay,
        patch("app.charts.registration.delete_overlays_absent_from_chart", return_value=[]),
    ):
        create_overlay.side_effect = lambda **kwargs: registered_row(kwargs["canonical_name"], kwargs["source_path"])
        update_overlay.side_effect = lambda **kwargs: SimpleNamespace(
            id=kwargs["overlay_id"],
            canonical_name=kwargs["overlay_update"].canonical_name,
            source_path=kwargs["overlay_update"].source_path,
            created_by=REGISTRATION_CREATOR,
        )
        yield SimpleNamespace(
            chart_id=chart_id,
            get_workloads=get_workloads,
            list_overlays=list_overlays,
            create_overlay=create_overlay,
            update_overlay=update_overlay,
        )


@pytest.mark.asyncio
async def test_registers_each_recipe_for_one_model_separately(registration: SimpleNamespace, tmp_path: Path) -> None:
    """Two recipes declaring the same model, one per GPU family, each keep a row of their own."""
    general = write_overlay(tmp_path, "general.yaml", "model: org/model\nfinetuningGpus: 8\n")
    mi350p = write_overlay(tmp_path, "mi350p.yaml", "model: org/model\nfinetuningGpus: 1\n")
    registration.get_workloads.return_value = [
        make_workload(
            chart_name="Existing Chart",
            overlay_files=[(general, "overrides/models/general.yaml"), (mi350p, "overrides/models/mi350p.yaml")],
        )
    ]
    general_row = registered_row("org/model", "overrides/models/general.yaml")
    registration.list_overlays.return_value = [general_row]

    await register_workloads()

    registration.update_overlay.assert_awaited_once()
    assert registration.update_overlay.await_args.kwargs["overlay_id"] == general_row.id
    assert registration.update_overlay.await_args.kwargs["overlay_update"].overlay == {
        "model": "org/model",
        "finetuningGpus": 8,
    }
    registration.create_overlay.assert_awaited_once_with(
        session=ANY,
        chart_id=registration.chart_id,
        overlay_data={"model": "org/model", "finetuningGpus": 1},
        canonical_name="org/model",
        creator=REGISTRATION_CREATOR,
        source_path="overrides/models/mi350p.yaml",
    )


@pytest.mark.asyncio
async def test_adopts_a_row_registered_before_source_tracking(registration: SimpleNamespace, tmp_path: Path) -> None:
    """A row stored without a source path is claimed by the file declaring its model, not duplicated."""
    recipe = write_overlay(tmp_path, "recipe.yaml", "model: org/model\n")
    registration.get_workloads.return_value = [
        make_workload(chart_name="Existing Chart", overlay_files=[(recipe, "overrides/models/recipe.yaml")])
    ]
    legacy_row = registered_row("org/model", None)
    registration.list_overlays.return_value = [legacy_row]

    await register_workloads()

    registration.create_overlay.assert_not_awaited()
    kwargs = registration.update_overlay.await_args.kwargs
    assert kwargs["overlay_id"] == legacy_row.id
    assert kwargs["overlay_update"].source_path == "overrides/models/recipe.yaml"


@pytest.mark.asyncio
async def test_a_legacy_row_is_adopted_by_only_one_recipe(registration: SimpleNamespace, tmp_path: Path) -> None:
    """When several files declare the legacy row's model, the first claims it and the rest get rows of their own."""
    first = write_overlay(tmp_path, "first.yaml", "model: org/model\n")
    second = write_overlay(tmp_path, "second.yaml", "model: org/model\n")
    registration.get_workloads.return_value = [
        make_workload(
            chart_name="Existing Chart",
            overlay_files=[(first, "overrides/models/first.yaml"), (second, "overrides/models/second.yaml")],
        )
    ]
    legacy_row = registered_row("org/model", None)
    registration.list_overlays.return_value = [legacy_row]

    await register_workloads()

    registration.list_overlays.assert_awaited_once()
    assert registration.update_overlay.await_args.kwargs["overlay_id"] == legacy_row.id
    registration.create_overlay.assert_awaited_once()
    assert registration.create_overlay.await_args.kwargs["source_path"] == "overrides/models/second.yaml"


@pytest.mark.asyncio
async def test_never_adopts_an_overlay_authored_through_the_api(registration: SimpleNamespace, tmp_path: Path) -> None:
    """An API user's overlay for the same model is theirs: registration creates its own row beside it."""
    recipe = write_overlay(tmp_path, "recipe.yaml", "model: org/model\n")
    registration.get_workloads.return_value = [
        make_workload(chart_name="Existing Chart", overlay_files=[(recipe, "overrides/models/recipe.yaml")])
    ]
    registration.list_overlays.return_value = [registered_row("org/model", None, created_by="user@example.com")]

    await register_workloads()

    registration.update_overlay.assert_not_awaited()
    registration.create_overlay.assert_awaited_once()
    assert registration.create_overlay.await_args.kwargs["source_path"] == "overrides/models/recipe.yaml"


@pytest.mark.asyncio
async def test_an_emptied_recipe_does_not_turn_its_row_generic(registration: SimpleNamespace, tmp_path: Path) -> None:
    """Emptying a registered recipe fails registration instead of leaving its old body behind without a model."""
    recipe = write_overlay(tmp_path, "recipe.yaml", "")
    registration.get_workloads.return_value = [
        make_workload(chart_name="Existing Chart", overlay_files=[(recipe, "overrides/models/recipe.yaml")])
    ]
    registration.list_overlays.return_value = [registered_row("org/model", "overrides/models/recipe.yaml")]

    with pytest.raises(ValueError, match="Overlay data is required for recipe file 'overrides/models/recipe.yaml'"):
        await register_workloads()

    registration.update_overlay.assert_not_awaited()
    registration.create_overlay.assert_not_awaited()


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
