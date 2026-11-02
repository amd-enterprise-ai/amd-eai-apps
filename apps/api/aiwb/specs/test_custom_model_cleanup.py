# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Contract tests for deterministic custom-model deployment teardown."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from robot.api import get_model
from robot.parsing.model.blocks import If, Keyword
from robot.parsing.model.statements import KeywordCall, Var

RESOURCE = Path(__file__).parent / "resources" / "aiwb_custom_models.resource"


def _keyword(name: str) -> Keyword:
    model = get_model(RESOURCE)
    for section in model.sections:
        for node in section.body:
            if isinstance(node, Keyword) and node.name == name:
                return node
    raise AssertionError(f"Keyword {name!r} not found")


def _calls(keyword: Keyword) -> list[KeywordCall]:
    calls: list[KeywordCall] = []

    def collect(body: Iterable[Any]) -> None:
        for child in body:
            if isinstance(child, KeywordCall):
                calls.append(child)
            elif isinstance(child, If):
                branch = child
                while branch is not None:
                    collect(branch.body)
                    branch = branch.orelse

    collect(keyword.body)
    return calls


def _var_assignments(keyword: Keyword) -> list[Var]:
    """Collect VAR assignments, which are their own statement type rather than keyword calls."""
    found: list[Var] = []

    def collect(body: Iterable[Any]) -> None:
        for child in body:
            if isinstance(child, Var):
                found.append(child)
            elif isinstance(child, If):
                branch = child
                while branch is not None:
                    collect(branch.body)
                    branch = branch.orelse

    collect(keyword.body)
    return found


def test_custom_model_cleanup_waits_for_deleted_workload() -> None:
    """A model-deploying test cannot return while its AIM workload still owns pods."""
    calls = _calls(_keyword("Remove custom model deployment if present"))
    names = [call.keyword for call in calls]

    undeploy = names.index("Undeploy AIM")
    deleted = names.index("Wait for AIM workload to reach state")
    deployment_gone = names.index("Wait Until Keyword Succeeds")

    assert undeploy < deleted < deployment_gone
    assert calls[deleted].args == ("Deleted", "timeout=120", "interval=5")
    assert calls[deployment_gone].args == (
        "2 min",
        "5 sec",
        "Verify AIM deployment gone",
        "${service_name}",
        "${namespace}",
    )


def test_cleanup_verifies_kubernetes_after_explicit_undeploy() -> None:
    """The lifecycle path captures a K8s name before API deletion and reuses it in teardown."""
    remove_vars = _var_assignments(_keyword("Custom model deployment is removed"))
    cleanup_calls = _calls(_keyword("Remove custom model deployment if present"))

    # Matched on the assignment itself, not on a keyword name: this repository mandates the
    # RF 5 VAR form, which the parser models as its own statement type rather than a call.
    assert any(var.name == "${TEST_AIM_SERVICE_NAME}" for var in remove_vars)
    assert any(
        call.keyword == "Get Variable Value" and "${TEST_AIM_SERVICE_NAME}" in call.args for call in cleanup_calls
    )
    assert any(
        call.keyword == "Wait Until Keyword Succeeds" and "Verify AIM deployment gone" in call.args
        for call in cleanup_calls
    )


def test_legacy_cleanup_name_delegates_to_the_waiting_cleanup() -> None:
    """All custom-model test teardowns share the deterministic cleanup path."""
    calls = _calls(_keyword("Undeploy the custom model AIM service if present"))

    assert [call.keyword for call in calls] == ["Remove custom model deployment if present"]
