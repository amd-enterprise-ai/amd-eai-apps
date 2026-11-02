# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for holding a started fine-tuning run to the settings its base model reports."""

import pytest
from ModelCatalog import trained_settings_should_match_reported_settings, training_configuration_of_run

RECIPE_CONFIG = """
training_args:
  num_train_epochs: 3
overrides:
  lr_multiplier: 0.5
batchsize_conf:
  total_train_batch_size: 16
"""


def _published(**data: str) -> list:
    return [{"data": dict(data)}]


def test_a_run_training_at_the_reported_settings_is_accepted() -> None:
    reported = {"epochs": 3, "learningRate": 0.5, "batchSize": 16}

    trained_settings_should_match_reported_settings(RECIPE_CONFIG, reported)


def test_a_run_overriding_a_reported_setting_is_caught() -> None:
    """The regression this guards: a platform default landing on top of the recipe's own value."""
    reported = {"epochs": 3, "learningRate": 0.5}
    trained_at_platform_defaults = "training_args:\n  num_train_epochs: 1\noverrides:\n  lr_multiplier: 0.5\n"

    with pytest.raises(AssertionError, match="reports epochs 3"):
        trained_settings_should_match_reported_settings(trained_at_platform_defaults, reported)


def test_a_setting_the_recipe_never_stated_is_not_checked() -> None:
    """A blank reported setting is nothing to hold the run to, so the chart's own value stands."""
    reported = {"epochs": 3, "learningRate": 0.5, "batchSize": None}

    trained_settings_should_match_reported_settings(RECIPE_CONFIG, reported)


def test_a_base_model_reporting_nothing_leaves_the_run_unchecked() -> None:
    """Silence must fail loudly rather than pass as a run that honoured everything."""
    with pytest.raises(AssertionError, match="reports none of its training settings"):
        trained_settings_should_match_reported_settings(RECIPE_CONFIG, {})


def test_an_integral_setting_written_as_a_float_still_matches() -> None:
    """Charts commonly spell integral values as floats, and 3.0 epochs is still three epochs."""
    trained_settings_should_match_reported_settings("training_args:\n  num_train_epochs: 3.0\n", {"epochs": 3})


def test_a_missing_section_is_reported_rather_than_passed_over() -> None:
    with pytest.raises(AssertionError, match="trains with None"):
        trained_settings_should_match_reported_settings("training_args:\n  seed: 42\n", {"epochs": 3})


def test_the_training_configuration_is_read_from_what_the_run_published() -> None:
    published = _published(**{"accelerate_config.yaml": "num_machines: 1", "finetuning_config.yaml": RECIPE_CONFIG})

    assert training_configuration_of_run(published) == RECIPE_CONFIG


@pytest.mark.parametrize(
    "published",
    [
        [],
        [{}],
        [{"data": None}],
        [{"data": {"accelerate_config.yaml": "num_machines: 1"}}],
        _published(**{"finetuning_config.yaml": "  "}),
    ],
)
def test_a_run_that_has_published_nothing_yet_keeps_the_caller_waiting(published: list) -> None:
    """Polling has to keep waiting rather than assert against a configuration that is not there."""
    with pytest.raises(AssertionError, match="published no finetuning_config.yaml"):
        training_configuration_of_run(published)
