# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Reads chart identity and contents out of AIWB chart API responses."""

from typing import Any

ACCEPTED_STATUSES = (200, 201)


class ChartCatalog:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def created_chart_id(self, response: Any) -> str | None:
        """ID of the chart an upload stored, or None when the API refused it.

        Callers register a returned ID for cleanup, so an upload a test expected to be
        rejected never leaks a chart when the API wrongly accepts it.
        """
        if response.status_code not in ACCEPTED_STATUSES:
            return None
        return response.json()["id"]

    def find_chart_id(self, chart_list: dict, chart_name: str) -> str | None:
        """ID of the chart with this name in a chart list response, or None if absent."""
        return next((chart["id"] for chart in chart_list["data"] if chart.get("name") == chart_name), None)

    def catalog_should_contain_chart(self, chart_list: dict, chart_name: str) -> None:
        if self.find_chart_id(chart_list, chart_name) is None:
            raise AssertionError(f"Chart '{chart_name}' is not in the catalog but should be")

    def catalog_should_not_contain_chart(self, chart_list: dict, chart_name: str) -> None:
        chart_id = self.find_chart_id(chart_list, chart_name)
        if chart_id is not None:
            raise AssertionError(f"Chart '{chart_name}' is in the catalog (id {chart_id}) but should not be")

    def chart_should_contain_file(self, chart: dict, path: str) -> None:
        paths = [file["path"] for file in chart.get("files", [])]
        if path not in paths:
            raise AssertionError(f"Chart has no file at '{path}'; it has {paths}")
