# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Contract tests for deterministic AIM catalog teardown."""

import io
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest
from robot.api import get_model
from robot.parsing.model.blocks import For, If, Keyword, Try
from robot.parsing.model.statements import KeywordCall, SuiteTeardown

RESOURCE = Path(__file__).parent / "resources" / "aim_catalog.resource"

# Both suites adopt the same catalog project through "Setup AIM catalog testing", so both
# must tear it down through the wrapper that undeploys tracked AIMs first and then removes
# only this suite's adopted project.
CATALOG_SUITES = ("aim_catalog.robot", "aim_catalog_cleanup.robot")


def _keyword(name: str) -> Keyword:
    model = get_model(RESOURCE)
    for section in model.sections:
        for node in section.body:
            if isinstance(node, Keyword) and node.name == name:
                return node
    raise AssertionError(f"{name} keyword not found")


def _cleanup_keyword() -> Keyword:
    # The per-service undeploy/wait/verify loop lives in "Undeploy all tracked AIM
    # catalog services", factored out of "Cleanup AIM catalog testing" so E2E tests
    # can drive it directly before project (and namespace) deletion. "Cleanup AIM
    # catalog testing" itself is now a thin wrapper: that keyword plus project cleanup.
    return _keyword("Undeploy all tracked AIM catalog services")


def _collect_calls(body: Iterable[Any]) -> list[KeywordCall]:
    """Every KeywordCall in a keyword body, descending into FOR, IF and TRY blocks.

    THE one walker in this module. Every guard below routes through it, and so does
    its own regression test - a test carrying a private copy of this walk would keep
    passing after the walk the guards actually use regressed.

    The non-obvious part: Robot links IF chains through .orelse but TRY chains
    through .next, so following only .orelse stops at the TRY body and never sees
    EXCEPT, ELSE or FINALLY - exactly where a forbidden call would hide.
    """
    calls: list[KeywordCall] = []
    for child in body:
        if isinstance(child, KeywordCall):
            calls.append(child)
        elif isinstance(child, (For, If, Try)):
            branch: Any = child
            while branch is not None:
                calls.extend(_collect_calls(branch.body))
                branch = getattr(branch, "orelse", None) or getattr(branch, "next", None)
    return calls


def _cleanup_calls() -> list[KeywordCall]:
    return _collect_calls(_cleanup_keyword().body)


def test_cleanup_waits_for_each_tracked_aim_to_release_its_pod() -> None:
    """Every tracked deployment is undeployed and confirmed absent from Kubernetes."""
    calls = _cleanup_calls()
    names = [call.keyword for call in calls]

    undeploy = names.index("Undeploy AIM")
    deleted = names.index("Wait for catalog AIM workload to reach state")
    deployment_gone = names.index("Wait Until Keyword Succeeds")

    assert undeploy < deleted < deployment_gone
    assert calls[deleted].args == (
        "Deleted",
        "timeout=120",
        "interval=5",
        "workload_id=${service_id}",
    )
    assert calls[deployment_gone].args == (
        "2 min",
        "5 sec",
        "Verify AIM deployment gone",
        "${service_name}",
        "${namespace}",
    )


def test_cleanup_undeploys_aims_before_deleting_the_project() -> None:
    """The AIM-only cleanup must run while the project (and its namespace) still exists.

    "Cleanup AIM catalog testing" is a thin wrapper: it delegates to "Undeploy all
    tracked AIM catalog services" first, then deletes test projects. Reversing that
    order would make the Kubernetes-level absence assertion run against an already
    deleted namespace, which fails kubectl rather than proving anything.
    """
    wrapper = _keyword("Cleanup AIM catalog testing")
    names = [call.keyword for call in wrapper.body if isinstance(call, KeywordCall)]

    undeploy_all = names.index("Undeploy all tracked AIM catalog services")
    projects = names.index("Clean Up All Created Projects With Wait")

    assert undeploy_all < projects


def test_cleanup_verifies_kubernetes_after_api_resource_is_already_gone() -> None:
    """An API 404 cannot skip the predictor Deployment deletion check."""
    calls = _cleanup_calls()
    names = [call.keyword for call in calls]

    service = names.index("Get AIM Service")
    deployment_gone = names.index("Wait Until Keyword Succeeds")

    assert service < deployment_gone
    assert any(call.keyword == "Get From Dictionary" and "${DEPLOYED_AIM_NAMES}" in call.args for call in calls)


def test_cleanup_does_not_hide_incomplete_deletion() -> None:
    """A failed undeploy or wait must fail teardown instead of leaving GPU pods behind."""
    cleanup = _cleanup_keyword()

    assert not any(isinstance(node, Try) for node in cleanup.body)
    assert any(
        call.keyword == "Should Be True"
        and any("Unexpected status ${response.status_code}" in arg for arg in call.args)
        for call in _cleanup_calls()
    )


# --- Scoped catalog-project teardown wiring ---
# CatalogProjectCleanup.py holds the list-scoping decision so it can be unit-tested, but the
# unit tests only prove the pure functions. Everything that makes them matter lives in Robot
# source: that the teardown calls the keyword at all, that the keyword routes through the
# scoped helper rather than draining the whole list, and that the confirmation flag comes
# from the atomic wait. `robot --dryrun` accepts every mutation of those, and dryrun is all
# that touches this resource on pull_request, so the property has to be asserted here.


def _normalize(name: str) -> str:
    """Collapses a keyword name the way Robot compares them: no case, space or underscore."""
    return name.replace(" ", "").replace("_", "").lower()


def _catalog_project_cleanup_calls() -> list[KeywordCall]:
    return _collect_calls(_keyword("Clean Up Catalog Project").body)


def test_the_walker_reaches_calls_inside_a_try_except() -> None:
    """A forbidden call hidden in an EXCEPT branch is still collected.

    Robot's If chains link through .orelse but Try chains link through .next, so a
    walker that follows only .orelse stops at the TRY body and never sees EXCEPT,
    ELSE or FINALLY. Clean Up Catalog Project is built around a TRY/EXCEPT, so a
    forbidden call placed in its EXCEPT branch would go uncollected, and the guards
    above would pass while the property they name is violated. Exercised on a
    synthetic keyword so the regression stays pinned even if the real keyword stops
    using TRY.
    """
    source = """
*** Keywords ***
Probe
    TRY
        Log    body
    EXCEPT    AS    ${err}
        Clean Up Adopted Projects
    ELSE
        Log    else-branch
    FINALLY
        Log    finally-branch
    END
"""
    model = get_model(io.StringIO(source))
    probe = next(node for section in model.sections for node in section.body if isinstance(node, Keyword))

    # Deliberately the SAME _collect_calls the guards above use. Reimplementing the
    # walk here would make this test pass while that one regressed.
    collected = [call.keyword for call in _collect_calls(probe.body)]

    assert "Clean Up Adopted Projects" in collected, "walker must descend into EXCEPT"
    assert collected.count("Log") == 3, f"walker must reach every TRY branch, saw {collected}"


@pytest.mark.parametrize("suite_name", CATALOG_SUITES)
def test_catalog_suite_binds_its_teardown_to_the_full_cleanup_wrapper(suite_name: str) -> None:
    """Each catalog suite's Suite Teardown setting names the full cleanup wrapper.

    The other tests here inspect the wrapper's BODY. None of them read the setting
    that binds a suite to it, so pointing a suite straight at
    "Clean Up All Created Projects With Wait" reintroduces the leak - the adopted
    project is never removed, and tracked AIMs are never undeployed before the
    namespace goes - while every body-level assertion still passes.
    """
    model = get_model(Path(__file__).parent / suite_name)
    teardowns = [
        statement
        for section in model.sections
        for statement in getattr(section, "body", [])
        if isinstance(statement, SuiteTeardown)
    ]

    assert len(teardowns) == 1, f"{suite_name} must declare exactly one Suite Teardown"
    assert _normalize(teardowns[0].name) == _normalize("Cleanup AIM catalog testing")


def test_teardown_cleans_up_the_catalog_project_after_created_projects() -> None:
    """The suite teardown actually invokes the scoped catalog-project cleanup.

    Without this, deleting the call leaves every other test green while a standalone
    catalog run silently leaks its adopted project - the whole point of the keyword.
    """
    wrapper = _keyword("Cleanup AIM catalog testing")
    names = [_normalize(call.keyword) for call in wrapper.body if isinstance(call, KeywordCall)]

    created = names.index(_normalize("Clean Up All Created Projects With Wait"))
    catalog = names.index(_normalize("Clean Up Catalog Project"))

    assert created < catalog


def test_catalog_project_cleanup_scopes_the_tracking_list() -> None:
    """Tracking is updated through the scoped helper, never by draining the whole list.

    Draining ADOPTED_PROJECT_IDS wholesale is the exact bug this keyword exists to
    prevent: it would delete sibling suites' still-shared projects.
    """
    calls = _catalog_project_cleanup_calls()
    scoped = [call for call in calls if _normalize(call.keyword) == _normalize("Scoped Cleanup Result")]

    assert len(scoped) == 1, "Clean Up Catalog Project must route tracking through Scoped Cleanup Result"

    # Routing through the scoped helper is not enough on its own: adding the run-scoped
    # drain ALONGSIDE it still empties the whole list, so the scoped call becomes
    # decoration and sibling suites lose their still-shared projects.
    assert not any(_normalize(call.keyword) == _normalize("Clean Up Adopted Projects") for call in calls), (
        "Clean Up Catalog Project must not drain the run-scoped adopted list"
    )

    # The delete has to target this suite's own project. Pointed anywhere else it
    # would delete someone else's while still satisfying every check above.
    deletes = [call for call in calls if _normalize(call.keyword) == _normalize("Delete project")]
    assert len(deletes) == 1, "Clean Up Catalog Project must delete exactly one project"
    assert "${catalog_project_id}" in deletes[0].args

    # The scoped helper only preserves tracking if it is actually told whether the
    # deletion was confirmed; dropping that argument silently re-enables the drop.
    assert "${deletion_confirmed}" in scoped[0].args

    assigned = scoped[0].assign[0].rstrip("= ")
    globals_set = [
        call
        for call in calls
        if _normalize(call.keyword) == _normalize("Set Global Variable")
        and "${ADOPTED_PROJECT_IDS}" in call.args
        and assigned in call.args
    ]
    assert globals_set, "the scoped result must be what lands back in ADOPTED_PROJECT_IDS"


def test_setup_clears_a_stale_catalog_project_before_creating_its_own() -> None:
    """Setup removes any project of this name, and waits, before creating one.

    This is what makes per-suite deletion in the teardown safe. Both catalog suites
    resolve the same "aim-catalog" name, so if setup ever reused an existing project
    instead of replacing it, two suites in one directory run would share it and the
    first teardown would delete it under the second. They do not share today because
    setup destroys any pre-existing project of that name first, so each suite only
    ever deletes a project it created. Remove that sweep and the teardown contract
    silently changes.
    """
    collected = _collect_calls(_keyword("Setup AIM catalog testing").body)
    names = [_normalize(call.keyword) for call in collected]

    delete_at = names.index(_normalize("Delete project"))
    wait_at = names.index(_normalize("Wait Until Project Deleted"))
    create_at = next(i for i, call in enumerate(collected) if "with user access exists" in (call.keyword or ""))

    assert delete_at < wait_at < create_at, "setup must clear and wait out a stale project before creating one"


def test_teardown_targets_the_suite_scoped_catalog_project() -> None:
    """The teardown resolves its target from the suite-scoped snapshot.

    Suite setup captures ${CATALOG_PROJECT_ID} at suite scope precisely so the
    teardown does not depend on Set Test Variable's suite-setup scoping rule, which
    reads as a bug even though it works.

    The fallback to ${TEST_PROJECT_ID} is required, not redundant: the snapshot is
    taken on the line AFTER "A ready project ... exists" returns, so a setup failure
    inside that keyword - once the project is created and tracked, while waiting for
    readiness or granting access - leaves the snapshot unset while the project exists.
    A standalone run has no directory teardown to drain the tracking list, so without
    the fallback that project leaks.
    """
    setup_calls = [
        statement
        for statement in _keyword("Setup AIM catalog testing").body
        if type(statement).__name__ == "Var" and "${CATALOG_PROJECT_ID}" in getattr(statement, "name", "")
    ]
    assert len(setup_calls) == 1, "Setup AIM catalog testing must snapshot CATALOG_PROJECT_ID"
    assert "SUITE" in str(getattr(setup_calls[0], "scope", "")).upper()

    lookups = [
        str(getattr(call, "args", ()))
        for call in _catalog_project_cleanup_calls()
        if call.keyword == "Get Variable Value"
    ]
    joined = "\n".join(lookups)
    assert "${CATALOG_PROJECT_ID}" in joined
    assert "${TEST_PROJECT_ID}" in joined, "teardown must fall back when setup failed before the snapshot"

    catalog_at = next(i for i, text in enumerate(lookups) if "${CATALOG_PROJECT_ID}" in text)
    fallback_at = next(i for i, text in enumerate(lookups) if "${TEST_PROJECT_ID}" in text)
    assert catalog_at < fallback_at, "the suite-scoped snapshot must be preferred over the fallback"

    # Both names must be ESCAPED. Get Variable Value documents the unescaped spelling as
    # working only when the variable already exists, which neither of these can assume -
    # the fallback exists precisely for the run where the snapshot is missing.
    for text in lookups:
        assert "\\${" in text, f"optional lookup must pass an escaped variable name: {text}"


def test_deletion_confirmation_comes_from_the_atomic_wait() -> None:
    """${deletion_confirmed} is the wait's own PASS/FAIL, not a later assignment.

    Robot turns continue-on-failure on inside every teardown, so a statement placed
    after a failing wait still runs. Assigning the flag as a follow-up statement would
    therefore report success for a wait that failed, and tracking would be dropped for
    a project that still exists.
    """
    producers = [
        call for call in _catalog_project_cleanup_calls() if any("${deletion_confirmed}" in a for a in call.assign)
    ]

    assert len(producers) == 1, "${deletion_confirmed} must be assigned exactly once"
    assert _normalize(producers[0].keyword) == _normalize("Run Keyword And Return Status")
    assert _normalize("Wait Until Project Deleted") in [_normalize(a) for a in producers[0].args]
