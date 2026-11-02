# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Static regression tests for the AIWB models Robot resource."""

import re
from pathlib import Path

RESOURCE_PATH = Path(__file__).parent / "resources" / "aiwb_models.resource"


def _keyword_rows(source: str, name: str) -> list[list[str]]:
    lines = source.splitlines()
    start = lines.index(name) + 1
    rows = []
    for line in lines[start:]:
        if line and not line[0].isspace():
            break
        cells = re.split(r"\s{2,}", line.strip())
        if cells != [""]:
            rows.append(cells)
    return rows


def test_finetuning_readiness_waits_share_completion_timeout():
    source = RESOURCE_PATH.read_text()

    timeout = re.search(
        r"^\$\{FINETUNING_COMPLETION_TIMEOUT\}\s{2,}(.+)$",
        source,
        flags=re.MULTILINE,
    )
    assert timeout is not None
    assert timeout.group(1) == "15 min"

    workload_rows = _keyword_rows(
        source,
        'Finetuning workload should reach status "${target_status}"',
    )
    assert ["VAR", "${timeout}", "${FINETUNING_COMPLETION_TIMEOUT}"] in workload_rows

    model_rows = _keyword_rows(
        source,
        'Finetuned model onboarding status should be "${target_status}"',
    )
    assert [
        "Wait Until Keyword Succeeds",
        "${FINETUNING_COMPLETION_TIMEOUT}",
        "10 sec",
    ] in model_rows


def test_finetuned_readiness_polls_the_resolved_model_directly_once_cached():
    """Once TEST_FINETUNING_RESOURCE_NAME is known, a retry must poll that one model directly
    (Get model) rather than re-scanning the full namespace model list (Get models) again."""
    source = RESOURCE_PATH.read_text()
    rows = _keyword_rows(source, "Finetuned model status should be")

    assert [
        "${resource_name}=",
        "Get Variable Value",
        "${TEST_FINETUNING_RESOURCE_NAME}",
        "${None}",
    ] in rows
    assert [
        "${response}=",
        "Get model",
        "${resource_name}",
        "namespace=${namespace}",
        "expected_status=200",
    ] in rows


def test_finetuned_readiness_caches_resolved_resource_name():
    """Until the resource name is first known, the fallback list scan must resolve and cache it
    so every following poll can take the targeted path checked above."""
    source = RESOURCE_PATH.read_text()
    rows = _keyword_rows(source, "Finetuned model status should be")

    assert [
        "${resolved_name}=",
        "Get From Dictionary",
        "${model}[metadata]",
        "name",
    ] in rows
    assert [
        "VAR",
        "${TEST_FINETUNING_RESOURCE_NAME}",
        "${resolved_name}",
        "scope=TEST",
    ] in rows
    assert [
        "VAR",
        "${_CACHED_FINETUNING_RESOURCE_NAME}",
        "${resolved_name}",
        "scope=SUITE",
    ] in rows


def test_finetuning_base_fixture_reuses_the_suite_shared_workload_instead_of_a_stand_in():
    """A base model for a "continue fine-tuning" run must be the suite's own, already
    genuinely-completed workload — not a fabricated checkpoint or a cluster model picked by
    some other identifier. Reusing the shared workload is what guarantees the base carries a
    real, trainer-produced aimId and weights that actually match the recipe used to build it."""
    source = RESOURCE_PATH.read_text()
    rows = _keyword_rows(source, "A completed fine-tuned model usable as a finetuning base exists")

    # Must drive the run to completion through the same shared, idempotent workload every other
    # GPU scenario in the suite uses — not stand up a separate, disposable one of its own.
    assert ["A finetuning workload exists"] in rows
    assert ['Finetuning workload should reach status "Complete"'] in rows

    assert [
        "VAR",
        "${TEST_BASE_MODEL_WORKLOAD_ID}",
        "${TEST_FINETUNING_WORKLOAD_ID}",
        "scope=TEST",
    ] in rows

    # aimId must come from the engine's own reconciled status on that same resource, not from a
    # value copied over from an unrelated cluster model.
    assert [
        "${aim_id}=",
        "Wait Until Keyword Succeeds",
        "2 min",
        "5 sec",
    ] in rows
    assert [
        "...",
        "Resolve Fine-Tuned Model aimId",
        "${resource_name}",
        "${namespace}",
    ] in rows
    assert [
        "VAR",
        "${TEST_MODEL_AIM_ID}",
        "${aim_id}",
        "scope=TEST",
    ] in rows


def test_finetuning_base_fixture_re_resolves_resource_name_after_complete_instead_of_copying_a_stale_name():
    """Regression for a real bug: "A finetuning workload exists" resolves the AIMModel CR name
    lazily and can leave it ${None} on a cold cache (a workload still Running when first seen).
    Waiting for the workload to reach "Complete" only polls workload status, not the AIMModel —
    it does not repair that ${None}. This asserts the fixture re-resolves the CR name from the
    workload id (bounded wait, since the CR appears only once the engine has created it) and
    copies identity from THAT freshly-resolved value — not from whatever
    TEST_FINETUNING_RESOURCE_NAME held before the resolve, which a cold cache could still be
    ${None}. Ordering is checked, not just that the right keywords appear somewhere in the body."""
    source = RESOURCE_PATH.read_text()
    rows = _keyword_rows(source, "A completed fine-tuned model usable as a finetuning base exists")

    def index_of(row):
        return rows.index(row)

    complete_wait_idx = index_of(['Finetuning workload should reach status "Complete"'])
    resolve_call_idx = index_of(
        [
            "${resource_name}=",
            "Wait Until Keyword Succeeds",
            "2 min",
            "5 sec",
        ]
    )
    resolve_continuation_idx = index_of(
        ["...", "Get finetuned model resource name from workload", "${TEST_FINETUNING_WORKLOAD_ID}"]
    )
    cache_update_idx = index_of(["VAR", "${TEST_FINETUNING_RESOURCE_NAME}", "${resource_name}", "scope=TEST"])
    suite_cache_update_idx = index_of(["VAR", "${_CACHED_FINETUNING_RESOURCE_NAME}", "${resource_name}", "scope=SUITE"])
    model_name_copy_idx = index_of(["VAR", "${TEST_MODEL_NAME}", "${resource_name}", "scope=TEST"])

    # The re-resolve must happen after Complete is reached (the CR is only guaranteed to exist
    # then) and its result must land in the caches strictly before identity is copied from it —
    # a copy from the stale, possibly-${None} TEST_FINETUNING_RESOURCE_NAME would reproduce the bug.
    assert complete_wait_idx < resolve_call_idx < resolve_continuation_idx
    assert resolve_continuation_idx < cache_update_idx < model_name_copy_idx
    assert resolve_continuation_idx < suite_cache_update_idx < model_name_copy_idx

    # Never copy the pre-resolve, possibly-stale variable directly into the base model's identity.
    assert ["VAR", "${TEST_MODEL_NAME}", "${TEST_FINETUNING_RESOURCE_NAME}", "scope=TEST"] not in rows


def test_finetune_from_existing_model_clears_the_base_models_cached_resource_name():
    """Starting a run FROM an existing fine-tuned model must drop the cached resource name.

    The base fixture leaves TEST_FINETUNING_RESOURCE_NAME pointing at the base model. The new
    run gets a fresh workload id, but its own AIMModel CR is engine-assigned and does not exist
    yet. If the cached name survived, the targeted poll in "Finetuned model status should be"
    would query the BASE model - already Complete - and report success immediately, so the
    scenario would pass without the new run having progressed at all. Clearing it forces the
    next poll back onto the workload-id label, which resolves the new run's own CR.
    """
    source = RESOURCE_PATH.read_text()
    rows = _keyword_rows(source, "A finetune request from an existing model is sent")

    workload_pin = rows.index(["VAR", "${TEST_FINETUNING_WORKLOAD_ID}", "${workload_id}", "scope=TEST"])
    cache_clear = rows.index(["VAR", "${TEST_FINETUNING_RESOURCE_NAME}", "${None}", "scope=TEST"])

    # Clearing must follow the new workload id, so the pair is always updated together.
    assert workload_pin < cache_clear

    # The base model's name must never be left in place as this run's resource name.
    assert ["VAR", "${TEST_FINETUNING_RESOURCE_NAME}", "${resource_name}", "scope=TEST"] not in rows


def test_finetuning_from_existing_model_scenario_proves_real_training_not_just_pod_admission():
    """The continuation scenario must assert the new job reaches "Complete", not merely
    "Running" — admission only proves the pod was scheduled, not that the base model's weights
    were actually loaded and trained against."""
    robot_path = Path(__file__).parent / "finetuning.robot"
    lines = robot_path.read_text().splitlines()

    start = lines.index("Finetuned model can be used as base model for a new finetuning run") + 1
    body_lines = []
    for line in lines[start:]:
        if line and not line[0].isspace():
            break
        body_lines.append(line)
    test_body = "\n".join(body_lines)

    assert 'Finetuning workload should reach status "Complete"' in test_body
    assert 'Finetuning workload should reach status "Running"' not in test_body
