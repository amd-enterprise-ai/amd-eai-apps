# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Chart lookups and assertions the chart E2E scenarios rely on to tell stored charts from refused ones."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent / "libraries"))

from ChartCatalog import ChartCatalog  # noqa: E402

CATALOG = {"data": [{"name": "first", "id": "id-1"}, {"name": "second", "id": "id-2"}]}


def response(status_code: int, body: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(status_code=status_code, json=lambda: body)


@pytest.mark.parametrize("status_code", [200, 201])
def test_accepted_upload_reports_the_stored_chart_id(status_code: int) -> None:
    assert ChartCatalog().created_chart_id(response(status_code, {"id": "chart-1"})) == "chart-1"


@pytest.mark.parametrize("status_code", [400, 409, 422, 500])
def test_refused_upload_reports_no_chart_without_reading_the_body(status_code: int) -> None:
    def unreadable() -> dict:
        raise AssertionError("an error body has no chart id and must not be read")

    refused = SimpleNamespace(status_code=status_code, json=unreadable)
    assert ChartCatalog().created_chart_id(refused) is None


def test_find_chart_id_matches_by_name() -> None:
    assert ChartCatalog().find_chart_id(CATALOG, "second") == "id-2"


@pytest.mark.parametrize("catalog", [CATALOG, {"data": []}])
def test_find_chart_id_returns_none_for_an_unknown_name(catalog: dict) -> None:
    assert ChartCatalog().find_chart_id(catalog, "missing") is None


def test_catalog_without_the_chart_passes() -> None:
    ChartCatalog().catalog_should_not_contain_chart(CATALOG, "missing")


def test_catalog_holding_the_chart_fails_naming_it() -> None:
    with pytest.raises(AssertionError, match="'first' is in the catalog"):
        ChartCatalog().catalog_should_not_contain_chart(CATALOG, "first")


def test_chart_with_the_file_passes() -> None:
    chart = {"files": [{"path": "Chart.yaml"}, {"path": "templates/deployment.yaml"}]}
    ChartCatalog().chart_should_contain_file(chart, "templates/deployment.yaml")


@pytest.mark.parametrize("chart", [{"files": [{"path": "deployment.yaml"}]}, {"files": []}, {}])
def test_chart_without_the_file_fails_listing_what_it_has(chart: dict) -> None:
    with pytest.raises(AssertionError, match="no file at 'templates/deployment.yaml'"):
        ChartCatalog().chart_should_contain_file(chart, "templates/deployment.yaml")
