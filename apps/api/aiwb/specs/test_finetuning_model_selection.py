# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Regression tests for fine-tuning model selection in the Robot keyword layer."""

import sys
from pathlib import Path

import pytest

SPECS_DIR = Path(__file__).resolve().parent
MODELS_RESOURCE = SPECS_DIR / "resources" / "aiwb_models.resource"
sys.path.insert(0, str(SPECS_DIR / "libraries"))

from ModelCatalog import get_finetunable_model_training_type  # noqa: E402


def _keyword_block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.rstrip() == name), None)
    assert start is not None, f"keyword {name!r} not found"
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def test_training_type_lookup_treats_canonical_name_as_data():
    models = [
        {"canonicalName": "example/small-model", "trainingType": "full"},
        {"canonicalName": 'example/model-with-"quotes"', "trainingType": "lora"},
    ]

    training_type = get_finetunable_model_training_type(models, 'example/model-with-"quotes"')

    assert training_type == "lora"


def test_training_type_lookup_rejects_unknown_canonical_name():
    with pytest.raises(ValueError, match="not found in the finetunable catalog"):
        get_finetunable_model_training_type([], "example/missing-model")


def test_training_type_lookup_rejects_model_without_training_type():
    models = [{"canonicalName": "example/model-without-training-type"}]

    with pytest.raises(ValueError, match="missing trainingType"):
        get_finetunable_model_training_type(models, "example/model-without-training-type")


def test_robot_keyword_delegates_training_type_lookup_to_python():
    keyword = _keyword_block(MODELS_RESOURCE.read_text(), "Get smallest finetunable catalog model")

    assert "Get Finetunable Model Training Type    ${models}    ${canonical_name}" in keyword
    assert "next(" not in keyword
