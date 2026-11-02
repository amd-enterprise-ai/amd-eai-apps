# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for planned fine-tuning output assertions."""

import pytest
from FineTuningOutput import TRAINING_OUTPUT_ANNOTATION, workload_planned_output_should_be


@pytest.mark.parametrize("workload", [{}, {"annotations": None}, {"annotations": {}}])
def test_missing_null_or_empty_annotations_mean_full_output(workload: dict) -> None:
    """Legacy and full-training workload shapes share the full-output default."""
    workload_planned_output_should_be(workload, "full")


def test_explicit_lora_output_is_accepted() -> None:
    """An adapter-producing workload must report the explicit LoRA classification."""
    workload = {"annotations": {TRAINING_OUTPUT_ANNOTATION: "lora"}}

    workload_planned_output_should_be(workload, "lora")


def test_missing_annotations_do_not_pass_as_lora() -> None:
    """The compatibility default must not weaken the adapter-versus-model assertion."""
    with pytest.raises(AssertionError, match="should be 'lora', got 'full'"):
        workload_planned_output_should_be({}, "lora")


def test_explicit_merged_output_is_accepted() -> None:
    """A LoRA run that produces a model keeps its merged classification."""
    workload = {"annotations": {TRAINING_OUTPUT_ANNOTATION: "merged"}}

    workload_planned_output_should_be(workload, "merged")
