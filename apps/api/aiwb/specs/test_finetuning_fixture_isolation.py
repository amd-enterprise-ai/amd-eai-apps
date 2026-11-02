# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Guards ownership of the shared fine-tuning workload fixture.

The suite shares one expensive GPU run through an in-process cache and a durable display
name for restart-safe reuse. Discovery must match that marker: adopting another test's
workload can select incompatible inputs and leave every dependent scenario without an
AIMModel.
"""

from __future__ import annotations

import pathlib

RESOURCE = pathlib.Path(__file__).resolve().parent / "resources" / "aiwb_models.resource"
MODELS_API_RESOURCE = pathlib.Path(__file__).resolve().parent / "resources" / "api" / "models.resource"


def _keyword_block(text: str, name: str) -> str:
    """Return one Robot keyword body, excluding the next top-level keyword."""
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.rstrip() == name), None)
    assert start is not None, f"keyword {name!r} not found"
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def test_shared_finetuning_fixture_uses_owned_cache_and_discovery() -> None:
    """The expensive fixture must reuse only work carrying its durable marker."""
    text = RESOURCE.read_text(encoding="utf-8")
    fixture = _keyword_block(text, "A finetuning workload exists")
    reusability = _keyword_block(text, "Owned finetuning workload is reusable")
    discovery = _keyword_block(text, "Find owned finetuning workload in namespace")
    model_lookup = _keyword_block(text, "Get finetuned model resource name from workload")
    request = _keyword_block(text, "A finetune request is sent")

    assert "${_CACHED_FINETUNING_WORKLOAD_ID}" in fixture
    assert "Owned finetuning workload is reusable" in fixture
    assert "Clear cached finetuning workload" in fixture
    assert "Find owned finetuning workload in namespace" in fixture
    assert "Finetune dataset exists" in fixture
    assert "A finetune request is sent" in fixture

    assert "Get AIWB workload" in reusability
    assert "${response.status_code} != 200    RETURN    ${False}    ${None}" in reusability
    assert '$workload["displayName"] != $fixture_name' in reusability
    assert "Get finetuned model resource name from workload" in reusability
    assert '$status not in ["Pending", "Starting", "Running", "Complete"]' in reusability
    assert '$status in ["Pending", "Starting", "Running"]' in reusability

    assert "${fixture_name}=    Test Name    ${FINETUNING_FIXTURE_SUFFIX}" in discovery
    assert '$workload["displayName"] != $fixture_name' in discovery
    assert "Owned finetuning workload is reusable" in discovery
    assert "WHILE    $True" in discovery
    assert "page=${page}    page_size=100" in discovery
    assert "${page} * ${page_size} >= ${total}" in discovery
    assert "${page}=    Evaluate    ${page} + 1" in discovery

    assert "WHILE    $True" in model_lookup
    assert "page=${page}    page_size=100" in model_lookup
    assert "airm.silogen.ai/workload-id" in model_lookup
    assert "${model}[metadata]    name" in model_lookup
    assert "${page} * ${page_size} >= ${total}" in model_lookup
    assert "${page}=    Evaluate    ${page} + 1" in model_lookup

    models_api_text = MODELS_API_RESOURCE.read_text(encoding="utf-8")
    get_models = _keyword_block(models_api_text, "Get models")
    assert "${page}=${None}" in get_models
    assert "${page_size}=${None}" in get_models
    assert "page=${page}" in get_models
    assert "pageSize=${page_size}" in get_models

    assert "${model_name}=    Test Name    ${FINETUNING_FIXTURE_SUFFIX}" in request
    assert "Find finetuning workload in namespace\n" not in text
