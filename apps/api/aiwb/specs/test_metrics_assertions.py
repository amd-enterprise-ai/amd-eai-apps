# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the inference-metric response assertion (scraped-value detection)."""

import sys
from pathlib import Path

import pytest

# Add libraries to path so MetricsAssertions is importable
sys.path.insert(0, str(Path(__file__).parent / "libraries"))

from MetricsAssertions import metric_response_should_carry_a_scraped_value


def _timeseries(*values: float | None) -> dict:
    return {"data": [{"metadata": {"label": "requests"}, "values": [{"value": v} for v in values]}]}


def test_scalar_value_passes():
    metric_response_should_carry_a_scraped_value({"data": 42.0})


def test_scalar_zero_passes():
    metric_response_should_carry_a_scraped_value({"data": 0})


def test_timeseries_with_a_value_passes():
    metric_response_should_carry_a_scraped_value(_timeseries(None, 3.0, None))


def test_timeseries_with_zero_value_passes():
    # A scraped 0 is a real datapoint and must count.
    metric_response_should_carry_a_scraped_value(_timeseries(None, 0.0))


def test_all_null_timeseries_fails():
    # The regression: the collector scraped nothing, so every datapoint is null.
    with pytest.raises(AssertionError, match="no non-null datapoint"):
        metric_response_should_carry_a_scraped_value(_timeseries(None, None, None))


def test_empty_timeseries_fails():
    with pytest.raises(AssertionError, match="empty"):
        metric_response_should_carry_a_scraped_value({"data": []})


def test_missing_data_field_fails():
    with pytest.raises(AssertionError, match="no 'data' field"):
        metric_response_should_carry_a_scraped_value({"range": {}})
