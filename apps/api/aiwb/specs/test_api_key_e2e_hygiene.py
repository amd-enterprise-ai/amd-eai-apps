# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Regression guards for API-key gateway timing and bare denial responses."""

from __future__ import annotations

import pathlib
import re

SPECS_DIR = pathlib.Path(__file__).resolve().parent
RESOURCES_DIR = SPECS_DIR / "resources"
AIMS_API_KEYS = RESOURCES_DIR / "aims" / "api_keys.resource"
GENERIC_API_KEYS = RESOURCES_DIR / "api_keys.resource"
MODELS_API = RESOURCES_DIR / "api" / "models.resource"
DENIAL_GUARDS = {
    "Error message should indicate missing api key": re.compile(r"IF\s+\$\{status\}\s+in\s+\[401, 403\]"),
    "Response error message should indicate authentication failure": re.compile(
        r"IF\s+\$\{status\}\s+in\s+\[401, 403, 404\]"
    ),
}
PROPAGATION_WAIT = re.compile(
    r"Wait [Uu]ntil [Kk]eyword [Ss]ucceeds\s+2 min\s+5 sec\s*\n"
    r"\s*\.\.\.\s+External endpoint should accept the api key"
)


def _keyword_block(text: str, name: str) -> str:
    """Return a Robot keyword body through the next top-level keyword."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.rstrip() == name), None)
    assert start is not None, f"keyword {name!r} not found"
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def test_bare_gateway_denials_are_accepted_before_json_parsing():
    """Bare auth denials must be handled before an optional JSON body is parsed."""
    cases = (
        (GENERIC_API_KEYS, "Error message should indicate missing api key"),
        (AIMS_API_KEYS, "Response error message should indicate authentication failure"),
    )
    for path, keyword in cases:
        block = _keyword_block(path.read_text(), keyword)
        guard = DENIAL_GUARDS[keyword].search(block)
        assert guard, f"{keyword} must accept its bare gateway denial statuses"
        assert guard.start() < block.index("${TEST_RESPONSE.json()}"), (
            f"{keyword} must check denial status before parsing an optional JSON body"
        )


def test_missing_key_does_not_accept_an_ambiguous_404():
    """A route-level 404 must not pass the no-credential authentication assertion."""
    block = _keyword_block(GENERIC_API_KEYS.read_text(), "Error message should indicate missing api key")
    assert "[401, 403, 404]" not in block


def test_gateway_propagation_helper_is_bounded_per_attempt():
    """The two-minute retry must use an HTTP timeout shorter than its outer bound."""
    aims_text = AIMS_API_KEYS.read_text()
    block = _keyword_block(aims_text, "Api key binding should take effect")
    assert PROPAGATION_WAIT.search(block)
    attempt = _keyword_block(aims_text, "External endpoint should accept the api key")
    assert "timeout=4" in attempt
    models_api = _keyword_block(MODELS_API.read_text(), "Get models response from external endpoint")
    assert "${timeout}=180" in models_api
    assert "timeout=${timeout}" in models_api


def test_shared_valid_key_request_waits_before_gateway_use():
    """All API-key scenarios inherit propagation waiting through their use keyword."""
    text = AIMS_API_KEYS.read_text()
    request = _keyword_block(text, "Request is made to AIMS model with valid api key")
    assert "Api key binding should take effect" in request
    assert request.index("Api key binding should take effect") < request.index(
        "Send chat completion request to external endpoint"
    )
    access = _keyword_block(text, "AIMS model access works with api key")
    assert "Request is made to AIMS model with valid api key" in access


def test_revoked_key_denial_path_skips_the_acceptance_wait():
    """A revoked key must be sent directly so the rejection poll can observe denial."""
    text = AIMS_API_KEYS.read_text()
    block = _keyword_block(text, "Revoked api key request should be denied")
    # Case-insensitive for the same reason as the scenario guard above: a negative
    # assertion on an exact spelling passes silently when the casing differs.
    assert "api key binding should take effect" not in block.casefold()
    assert "request is made to aims model with valid api key" not in block.casefold()
    assert "Send chat completion request to external endpoint" in block


def test_api_key_scenario_keeps_propagation_mechanics_out_of_bdd_steps():
    """Behavioral scenarios delegate gateway convergence to business keywords."""
    # Robot resolves keyword names case-insensitively, so the guard has to match the
    # same way — otherwise the canonical "Api key binding should take effect" casing
    # is exactly the spelling that slips past it.
    scenario = (SPECS_DIR / "api_keys.robot").read_text().casefold()
    assert "api key binding should take effect" not in scenario


def test_all_direct_bind_then_use_resource_paths_wait_for_propagation():
    """Every direct resource-level bind consumer must wait before gateway traffic."""
    cases = {
        AIMS_API_KEYS: (
            "An AIM model is running with api key",
            "An api key authorized only for model A is created",
        ),
        RESOURCES_DIR / "aiwb_ai_gateway.resource": (
            "A valid API key authorized for this model exists",
            "A second model with its own key is available",
            "The same AIM model is deployed in a second project",
        ),
        RESOURCES_DIR / "aiwb_aims.resource": (
            "AIM workload should be accessible externally",
            "An API key exists and is assigned to AIM",
        ),
        RESOURCES_DIR / "aim_catalog.resource": ("Test Template: Run AIM Inference",),
        RESOURCES_DIR / "aiwb_custom_models.resource": (
            "Chat completion against deployed custom model should succeed",
        ),
    }
    for path, keywords in cases.items():
        text = path.read_text()
        for keyword in keywords:
            block = _keyword_block(text, keyword)
            assert "Api key binding should take effect" in block, (
                f"{path.name}: {keyword} must wait for gateway propagation"
            )
