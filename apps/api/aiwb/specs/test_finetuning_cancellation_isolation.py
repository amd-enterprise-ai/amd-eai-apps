# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Guards cancellation from destroying the shared fine-tuning fixture.

The suite shares one expensive GPU fine-tuning run. A scenario that cancels its job must
own a disposable one: cancelling the shared fixture leaves it Deleted, and every later
scenario then pays for a second full run. Two independent properties keep that separated,
and this module pins both because either one alone silently degrades to the old behaviour.

  - the destructive scenario must request the disposable job, not the shared fixture;
  - cancellation must not clear the shared cache, or an intact fixture is discarded even
    though the job just cancelled was never the fixture.

Ownership itself is enforced by an allowlist rather than by naming: discovery adopts a
workload only when its display name matches the fixture marker exactly (see
test_finetuning_fixture_isolation.py). The cancellation prefix is therefore a naming
convention, and is deliberately not a selection key -- a denylist would have to enumerate
every disposable prefix, and a scenario that forgot one would become adoptable again.
"""

from __future__ import annotations

import pathlib
import re

SPECS_DIR = pathlib.Path(__file__).resolve().parent
RESOURCE = SPECS_DIR / "resources" / "aiwb_models.resource"
SUITE = SPECS_DIR / "finetuning.robot"


def _cells(line: str) -> list[str]:
    """Split one Robot line into its cells. Robot separates cells by 2+ spaces."""
    return [cell.strip() for cell in re.split(r"\s{2,}", line.strip()) if cell.strip()]


def _block(text: str, name: str) -> str:
    """Return one Robot keyword or test-case body, excluding the next top-level block."""
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.rstrip() == name), None)
    assert start is not None, f"block {name!r} not found"
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    extracted = "\n".join(body)
    assert extracted.strip(), f"block {name!r} is empty"
    return extracted


def test_cancellation_scenario_uses_a_disposable_job_not_the_shared_fixture() -> None:
    """The destructive scenario must not be handed the shared fixture."""
    scenario = _block(SUITE.read_text(encoding="utf-8"), "Cancel a running finetuning job")

    assert "an in-progress fine-tuning job exists" in scenario
    assert "a finetuning workload exists" not in scenario
    assert "the finetuning job is cancelled" in scenario

    # The job is the scenario's own, and it is a GPU workload. If the cancel request or the
    # status poll fails, nothing else stops it: suite teardown only deletes the project at the
    # very end, so without a test teardown it keeps running through every later GPU test.
    assert "The current fine-tuning job is torn down" in scenario


def test_cancellation_scenario_sizes_quota_for_its_own_job() -> None:
    """Owning a second job means paying for it: the project must be sized for two.

    The shared fixture may still be alive when this scenario starts its own job, so the
    default sizing -- one recipe's worth of GPU -- leaves the new job Pending against the
    project quota and the Running wait times out. That only shows up on a cluster that
    actually enforces quota, so nothing here fails without this guard.
    """
    scenario = _block(SUITE.read_text(encoding="utf-8"), "Cancel a running finetuning job")

    quota_cells = next(
        (
            _cells(line)
            for line in scenario.splitlines()
            if _cells(line)[:1] == ["And the project has fine-tuning quota available"]
        ),
        None,
    )
    assert quota_cells is not None, "the scenario must request fine-tuning quota"
    assert "concurrent_workloads=2" in quota_cells, f"quota must cover two jobs, got {quota_cells!r}"

    # The argument has to reach the sizing call. A keyword that accepts it and then sizes
    # off the bare recipe count would satisfy the assertion above and change nothing.
    quota = _block(RESOURCE.read_text(encoding="utf-8"), "The project has fine-tuning quota available")
    assert "${concurrent_workloads}" in quota, "the argument must be declared and used"
    assert "${TEST_FINETUNING_GPU_COUNT} * ${concurrent_workloads}" in quota, (
        "quota must scale the recipe GPU count by the requested concurrency"
    )


def test_in_progress_job_is_self_owned_and_never_cached() -> None:
    """The job must be independently created, proven Running, tracked, and kept out of the cache."""
    job = _block(RESOURCE.read_text(encoding="utf-8"), "An in-progress fine-tuning job exists")

    assert "Finetune dataset exists" in job
    assert "Finetune model" in job
    assert "${FINETUNING_CANCELLATION_PREFIX}-${random_suffix}" in job
    assert "${TEST_FINETUNING_WORKLOAD_ID}" in job
    assert "Track workload for cleanup" in job
    # Submission is asynchronous: without this wait the scenario cancels a Pending job
    # and stops covering the in-progress case its name promises. Assert Running as a cell on
    # the Wait line rather than as a free substring, so a wait retargeted at Complete cannot
    # pass on the word appearing elsewhere in the block.
    wait_cells = next(
        (_cells(line) for line in job.splitlines() if _cells(line)[:1] == ["Wait For Resource Status"]),
        None,
    )
    assert wait_cells is not None, "the job must wait for a status before returning"
    assert "Running" in wait_cells, f"wait must target Running, got {wait_cells!r}"
    # Caching it would make the next scenario adopt a job that is about to be destroyed.
    assert "_CACHED_FINETUNING" not in job


def test_cancellation_does_not_clear_the_shared_cache() -> None:
    """Clearing the cache here would discard an intact fixture the cancellation never touched.

    This is the half that is easy to lose: the scenario can be repointed at its own job
    while cancellation still nukes the cache, which reintroduces the redundant GPU run
    with no visible change to the scenario.

    Both routes to the cache are pinned. Naming the variables alone is not enough: the
    resource already exposes "Clear cached finetuning workload", so a regression could
    discard the fixture through that helper without any cache variable appearing here.
    The two stems also differ -- _CACHED_FINETUNING is not a substring of
    _CACHED_FINETUNED_MODEL_ID -- so the broad check does not cover the latter, and both
    have to be named.
    """
    cancellation = _block(RESOURCE.read_text(encoding="utf-8"), "The finetuning job is cancelled")

    assert "Cancel finetuning job" in cancellation
    assert "Clear cached finetuning workload" not in cancellation
    assert "_CACHED_FINETUNING" not in cancellation
    assert "_CACHED_FINETUNED_MODEL_ID" not in cancellation


def test_cancellation_prefix_is_a_name_not_a_selection_key() -> None:
    """The prefix must never become a denylist: ownership is an exact-match allowlist.

    Discovery and reusability must both key off the fixture marker. If either started
    consulting the cancellation prefix, a scenario that forgot the prefix would become
    adoptable, which is precisely the failure mode the allowlist rules out.
    """
    text = RESOURCE.read_text(encoding="utf-8")
    discovery = _block(text, "Find owned finetuning workload in namespace")
    reusability = _block(text, "Owned finetuning workload is reusable")

    # The job keyword interpolates this variable, so a declaration carrying no real value does
    # not fail outright -- it silently produces a display name that is just the random suffix.
    # Three ways to write that, all of which a naive pattern accepts: no value at all (\s would
    # match the newline and take the NEXT variable name as the value), a trailing comment only,
    # or an explicit empty sentinel. Read the declaration as cells and check the first one.
    declaration = next(
        (_cells(line) for line in text.splitlines() if _cells(line)[:1] == ["${FINETUNING_CANCELLATION_PREFIX}"]),
        None,
    )
    assert declaration is not None, "FINETUNING_CANCELLATION_PREFIX is not declared"
    assert len(declaration) > 1, f"FINETUNING_CANCELLATION_PREFIX has no value: {declaration!r}"
    value = declaration[1]
    assert not value.startswith("#"), f"FINETUNING_CANCELLATION_PREFIX value is a comment: {value!r}"
    assert value not in ("${EMPTY}", "${None}"), f"FINETUNING_CANCELLATION_PREFIX is empty: {value!r}"

    assert "${FINETUNING_FIXTURE_SUFFIX}" in discovery
    assert "${FINETUNING_FIXTURE_SUFFIX}" in reusability
    assert "FINETUNING_CANCELLATION_PREFIX" not in discovery
    assert "FINETUNING_CANCELLATION_PREFIX" not in reusability
