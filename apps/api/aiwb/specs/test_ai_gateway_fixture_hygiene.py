# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Protect the multi-AIM gateway fixture from propagation-poll regressions."""

from __future__ import annotations

import pathlib
import re

SPECS_DIR = pathlib.Path(__file__).resolve().parent
AI_GATEWAY_RESOURCE = SPECS_DIR / "resources" / "aiwb_ai_gateway.resource"
MODELS_RESOURCE = SPECS_DIR / "resources" / "api" / "models.resource"


def _keyword_block(text: str, name: str) -> str:
    """Return the body of a Robot keyword."""
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.rstrip() == name), None)
    assert start is not None, f"keyword {name!r} not found"

    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def test_model_list_timeout_is_configurable_without_changing_its_default():
    """Propagation polls need short attempts while other callers keep the established timeout."""
    block = _keyword_block(MODELS_RESOURCE.read_text(), "List models from external endpoint")

    assert "${timeout}=180" in block
    assert re.search(r"expected_status=200\s+timeout=\$\{timeout\}", block)


def test_api_key_propagation_is_awaited_before_each_model_list():
    """A model list must not run until the bound key is accepted by the gateway."""
    text = AI_GATEWAY_RESOURCE.read_text()
    keyword_names = (
        "A valid API key authorized for this model exists",
        "A second model with its own key is available",
        "The same AIM model is deployed in a second project",
    )

    for name in keyword_names:
        # Robot resolves keyword names case-insensitively; matching the same way keeps a
        # re-cased call from silently reading as "absent" and passing the ordering check.
        block = _keyword_block(text, name).casefold()
        wait = block.find("api key binding should take effect")
        assert wait != -1, f"{name!r} must wait for the binding to propagate before using the key"
        listing = block.find("list models from external endpoint")
        assert listing == -1 or wait < listing, (
            f"{name!r} must await propagation before it lists models with the bound key"
        )


def test_cross_model_fixture_documentation_has_no_ticket_reference():
    """Fixture rationale must describe stable behavior instead of a historical ticket."""
    block = _keyword_block(AI_GATEWAY_RESOURCE.read_text(), "Another model is available on the gateway")

    assert re.search(r"\bEAI-\d+\b", block, flags=re.IGNORECASE) is None
