# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Robot Framework library for asserting on inference metric responses."""

from robot.api.deco import keyword


def _timeseries_has_scraped_value(data: list) -> bool:
    """True if any nested datapoint in a MetricsTimeseries carries a non-null value.

    A MetricsTimeseries always serializes a non-empty ``data`` wrapper (one entry per
    series, each with a ``values`` list), and missing datapoints are filled with
    ``value: null``. So a non-empty wrapper does not prove anything was scraped — only a
    non-null nested value does. A numeric ``0`` counts as scraped.
    """
    for series in data:
        for point in series.get("values", []):
            if point.get("value") is not None:
                return True
    return False


@keyword("Metric Response Should Carry A Scraped Value")
def metric_response_should_carry_a_scraped_value(body: dict) -> None:
    """Assert the metric response proves the collector scraped a value.

    Handles the three response shapes the inference metric endpoint returns:
      - MetricsScalar / MetricsScalarWithRange: ``data`` is a number (``0`` counts).
      - MetricsTimeseries: ``data`` is a list of series; at least one nested datapoint
        value must be non-null (numeric ``0`` counts). An all-null timeseries means the
        collector never scraped the deployment — the regression this test guards — and fails.
    """
    if not isinstance(body, dict) or "data" not in body:
        raise AssertionError(f"Metric response has no 'data' field; got: {body}")
    data = body["data"]
    # bool is an int subclass, but a metric value is never a bool; guard anyway.
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        return
    if isinstance(data, list):
        if not data:
            raise AssertionError(f"Metric timeseries 'data' is empty; got: {body}")
        if not _timeseries_has_scraped_value(data):
            raise AssertionError(
                f"Metric timeseries carries no non-null datapoint — the collector scraped "
                f"nothing for this deployment; got: {body}"
            )
        return
    raise AssertionError(f"Unexpected metric 'data' shape {type(data).__name__}; got: {body}")
