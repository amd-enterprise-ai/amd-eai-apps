# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Static regression tests for the AIWB projects Robot resource."""

from pathlib import Path

from robot.api import get_model

RESOURCE_PATH = Path(__file__).parent / "resources" / "aiwb_projects.resource"


def test_finetuned_aim_service_match_uses_quoted_dictionary_key():
    source = RESOURCE_PATH.read_text()
    model = get_model(RESOURCE_PATH)

    assert not model.errors
    assert 'IF    $entry["id"] == $TEST_AIM_ID' in source
    assert "IF    $entry[id] == $TEST_AIM_ID" not in source
