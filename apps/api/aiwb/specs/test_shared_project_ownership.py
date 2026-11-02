# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Static coverage for AIWB shared-project ownership and MLflow isolation.

Shared fixed-name projects must be adopted (run-scoped cleanup), never tracked as if this
test created them (per-test cleanup) — a per-test teardown deleting a shared project other
tests still use is the regression this guards against. The MLflow uniqueness scenario must
use a fresh project, not a fixed name, so a leftover from an earlier run cannot make its
first create fail.

Read through Robot's parser via :mod:`robot_guards`, so a keyword named in a comment or in
``[Documentation]`` is not a call and cannot satisfy — or falsely trip — any assertion here.
"""

from pathlib import Path

import robot_guards

SPECS_DIR = Path(__file__).resolve().parent
WORKSPACES_SUITE = SPECS_DIR / "workspaces.robot"
CATALOG_RESOURCE = SPECS_DIR / "resources" / "aim_catalog.resource"

MLFLOW_SCENARIO = "Only one MLflow workspace per project"
CATALOG_TEARDOWN = "Cleanup AIM catalog testing"


def test_mlflow_uniqueness_scenario_uses_a_fresh_project() -> None:
    """Any fixed project name reintroduces the collision, not just the original one.

    A leftover project from an earlier run makes the first create in this scenario fail,
    so the name has to be generated. Naming the historical value alone would let the
    scenario regress to a different hard-coded name and still pass.

    Both needles are normalised and carry no BDD prefix -- Robot strips a leading
    Given/When/Then/And/But before resolving a keyword and ignores case, spaces and
    underscores, so ``And A Fresh Project With User Access Exists`` is the same call: a
    pure re-prefix must not report a still-correct scenario as unproven, and a reused
    project reached under any prefix must still be caught.
    """
    called = robot_guards.called_names(robot_guards.test_case(WORKSPACES_SUITE, MLFLOW_SCENARIO))

    fresh = robot_guards.normalize("a fresh project with user access exists")
    assert any(fresh in name for name in called), f"the scenario must create its own project: {called}"

    # Any invocation of the reusable-project step, not just one carrying a quoted literal.
    # A variable argument pins a name just as firmly as a literal does and reads nothing
    # like one, so the keyword is what gets rejected rather than the spelling of its argument.
    reusable = robot_guards.normalize("a ready project")
    reused = [name for name in called if reusable in name]
    assert not reused, f"the scenario must create its own project, not reuse a named one: {reused}"


def test_aim_catalog_child_teardown_does_not_drain_adopted_projects() -> None:
    """The drain belongs to the directory suite teardown, never to a child suite.

    ``Clean Up Adopted Projects`` removes every project tracked for the whole run, so a
    child suite calling it deletes shared projects its siblings are still using. The
    directory ``__init__.robot`` owns that call. A standalone ``aim_catalog.robot`` run
    does not reach that teardown at all, which is why this suite cleans up its own
    adopted project through ``Clean Up Catalog Project`` instead of the global drain.
    """
    teardown = robot_guards.keyword(CATALOG_RESOURCE, CATALOG_TEARDOWN)

    # Substring over the normalised name, not equality: a call folded into Run Keywords
    # passes the drain as an argument rather than invoking it directly, and that is still
    # a drain. Normalised the way Robot resolves names, so Clean_Up_Adopted_Projects is
    # the same call.
    drain = robot_guards.normalize("Clean Up Adopted Projects")
    drains = [
        call.keyword
        for call in robot_guards.calls(teardown)
        if drain in robot_guards.normalize(call.keyword)
        or any(drain in robot_guards.normalize(argument) for argument in call.args)
    ]
    assert not drains, f"the child suite must not drain run-scoped projects: {drains}"
