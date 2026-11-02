# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Assertions for planned fine-tuning output in workload API responses."""

from typing import Any

from robot.api.deco import keyword

TRAINING_OUTPUT_ANNOTATION = "aiwb.apps.eai.amd.com/training-output"
_FULL_OUTPUT = "full"


def _planned_output(workload: dict[str, Any]) -> str:
    """Return the explicit output annotation or the full-training default."""
    annotations = workload.get("annotations") or {}
    return annotations.get(TRAINING_OUTPUT_ANNOTATION) or _FULL_OUTPUT


@keyword("Workload Planned Output Should Be")
def workload_planned_output_should_be(workload: dict[str, Any], expected_output: str) -> None:
    """Assert the planned output reported for one workload response."""
    actual_output = _planned_output(workload)
    if actual_output != expected_output:
        raise AssertionError(
            f"Fine-tuning workload planned output should be {expected_output!r}, got {actual_output!r}"
        )
