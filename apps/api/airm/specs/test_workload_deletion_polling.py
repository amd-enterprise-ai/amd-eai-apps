# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Guards the out-of-band workload-deletion assertion against a reconciliation race."""

from __future__ import annotations

import pathlib

RESOURCE = pathlib.Path(__file__).resolve().parent / "resources" / "airm_workloads.resource"


def _keyword_block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = lines.index(name)
    end = next((i for i in range(start + 1, len(lines)) if lines[i] and not lines[i][0].isspace()), len(lines))
    return "\n".join(lines[start:end])


def test_workload_deletion_status_is_polled() -> None:
    """AIRM observes helm/kubectl deletion asynchronously, so one immediate GET is a race."""
    block = _keyword_block(RESOURCE.read_text(), "Workload should report a deletion status via API")

    assert "Wait Until Keyword Succeeds    2 min    5 sec" in block
    assert "Workload status should be Deleting or Deleted via API" in block
    assert "Get workload" not in block, "the public keyword must poll through the one-attempt helper"


def test_deletion_poll_attempt_accepts_only_soft_delete_states() -> None:
    block = _keyword_block(RESOURCE.read_text(), "Workload status should be Deleting or Deleted via API")

    assert "Get workload    ${TEST_WORKLOAD_ID}    expected_status=200" in block
    assert "Should Match Regexp    ${status}    ^(Deleting|Deleted)$" in block
