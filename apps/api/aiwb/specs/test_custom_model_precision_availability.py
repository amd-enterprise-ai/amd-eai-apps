# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Static coverage for the custom-model precision-selection scenario.

A single-precision base template is a valid configuration, not a defect, so the scenario
must run against whatever precisions the template emits and only skip when the template
emits none at all.

Read through Robot's parser via :mod:`robot_guards`, so a keyword name appearing in a
comment or in ``[Documentation]`` is not a call and cannot satisfy any assertion here.
"""

from pathlib import Path

import robot_guards

SPECS_DIR = Path(__file__).resolve().parent
SUITE = SPECS_DIR / "custom_models.robot"
RESOURCE = SPECS_DIR / "resources" / "aiwb_custom_models.resource"

SCENARIO = "Deploying a custom model pins the profile matching the onboarded precision"
CALLER = "The base template offers at least one precision"
CALLEE = "The base template's offered precisions"


def test_scenario_requires_only_one_precision() -> None:
    """The scenario must require a precision, never a second one.

    Both needles are normalised and carry no BDD prefix, because neither is part of what
    Robot resolves: it compares keyword names ignoring case, spaces and underscores, and
    strips a leading Given/When/Then/And/But first. So reinstating the cardinality gate as
    ``And The Base Template Offers More Than One Precision`` is still caught, while
    re-prefixing the required step is a pure rename and must not be reported as a
    regression.

    Called keywords, not source rows: ``Log    ...at least one precision`` names the step
    in an *argument* while calling something else, and must not stand in for it.
    """
    called = robot_guards.called_names(robot_guards.test_case(SUITE, SCENARIO))

    required = robot_guards.normalize("the base template offers at least one precision")
    assert any(required in name for name in called), called

    forbidden = robot_guards.normalize("the base template offers more than one precision")
    gates = [name for name in called if forbidden in name]
    assert not gates, f"the scenario must not require a second precision: {gates}"


# Every statement that runs once ``${precisions}`` can exist, across BOTH keywords that
# handle it. Pinning the shape closes the surface a "more than one precision" gate could
# sit on without enumerating the ways to write such a gate -- enumeration is what fails
# here, because ``Should Be True    ${count} > 1`` aborts the keyword with no Skip, Fail
# or RETURN anywhere in it, and the set of other ways to reject a one-item list is open.
#
# Both keywords, because a gate is not visible from either one alone:
#
#   In the caller, a gate after END fails the test outright; one inside the TRY body is
#   caught by the EXCEPT and re-emerges as the sanctioned Skip.
#   In the callee, a gate raises inside the polled keyword, so the caller's Wait Until
#   Keyword Succeeds retries it to the full timeout and the EXCEPT turns it into that
#   same Skip -- a single-precision template is skipped rather than exercised, and the
#   log reads as the legitimate "template offers no precision" path.
#
# Both are pinned whole rather than from the TRY. Anchoring on "where ${precisions} is
# first bound" describes today's body, not a property of the keyword: a gate inserted
# ahead of the TRY can bind the precisions itself -- calling the callee directly and
# testing its length -- and an anchored pin never looks there.
#
# The pin is structural, not textual: control-flow markers are their own rows, arguments
# continued across lines stay part of their statement, and documentation contributes
# nothing -- so narrative can be rewritten freely without a re-pin.
_CALLER_BODY = (
    ("KEYWORD", "Get Project Namespace", (), ("${namespace}=",)),
    ("TRY",),
    (
        "KEYWORD",
        "Wait Until Keyword Succeeds",
        ("2 min", "5 sec", "The base template's offered precisions", "${namespace}"),
        ("${precisions}=",),
    ),
    ("EXCEPT", (), "${error}"),
    ("KEYWORD", "Log", ("Base template still offers no precision after waiting: ${error}", "INFO"), ()),
    ("KEYWORD", "No Base Role AIMProfile Should Declare A Precision", ("${namespace}",), ()),
    (
        "KEYWORD",
        "Skip",
        ("Base template offers no precision; cannot exercise deploy precision selection",),
        (),
    ),
    ("END",),
    ("VAR", "@{TEST_OFFERED_PRECISIONS}", ("@{precisions}",), "TEST"),
    (
        "KEYWORD",
        "Largest Accelerator Count For Precisions",
        ("${precisions}", "${namespace}"),
        ("${required_gpus}=",),
    ),
    ("VAR", "${TEST_REQUIRED_GPU_COUNT}", ("${required_gpus}",), "TEST"),
)

_CALLEE_BODY = (
    ("ARGUMENTS", ("${namespace}",)),
    ("KEYWORD", "Get Runtime Profile Options", ("${namespace}", "expected_status=200"), ("${response}=",)),
    (
        "KEYWORD",
        "Get From Dictionary",
        ("${response.json()}", "precisions", "default=@{EMPTY}"),
        ("${precisions}=",),
    ),
    (
        "KEYWORD",
        "Should Not Be Empty",
        ("${precisions}", "msg=The base model has not emitted a precision-bearing profile yet"),
        (),
    ),
    ("RETURN", ("${precisions}",)),
)

_REPIN = (
    "this keyword must reach the deploy path for any non-empty set of precisions; re-read "
    "it and re-pin only if the change is not a cardinality gate"
)


def test_fixture_does_not_require_a_second_precision() -> None:
    """One precision is a valid template, so nothing may bail out before the test runs.

    An added statement is not automatically wrong -- but on these two keywords it has to
    be read, because this is where a regression would put the gate back. Anything that
    changes either shape fails here and has to be re-pinned deliberately.
    """
    caller = robot_guards.shape(robot_guards.keyword(RESOURCE, CALLER))
    assert caller == _CALLER_BODY, f"{_REPIN}: {caller}"

    callee = robot_guards.shape(robot_guards.keyword(RESOURCE, CALLEE))
    assert callee == _CALLEE_BODY, f"{_REPIN}: {callee}"


def test_an_empty_read_is_retried_before_it_is_believed() -> None:
    """The endpoint is fail-open, so one empty answer is not evidence of no precision.

    It reports no precisions when its own base-profile read fails, and also while a
    freshly created project has not emitted profiles yet. Accepting the first empty read
    would retire this test's coverage on a transient outage, silently and as a pass.
    """
    waits = [
        call
        for call in robot_guards.calls(robot_guards.keyword(RESOURCE, CALLER))
        if call.keyword == "Wait Until Keyword Succeeds"
    ]
    assert waits, "an empty read must be polled, not accepted"

    # The retried keyword is an argument of the wait, so the two are only evidence
    # together: a wait retrying something else leaves the read itself unpolled.
    assert any(CALLEE in call.args for call in waits), (
        f"the polled keyword must be the precision read itself, found: {[call.args for call in waits]}"
    )

    helper = robot_guards.calls(robot_guards.keyword(RESOURCE, CALLEE))
    assert any(call.keyword == "Should Not Be Empty" and "${precisions}" in call.args for call in helper), (
        "the polled helper must fail on empty, or the wait returns immediately"
    )


def test_the_skip_is_cross_checked_against_kubernetes_first() -> None:
    """Skipping is only honest once Kubernetes agrees no base profile declares a precision.

    Both statements live in the EXCEPT branch, and the cross-check has to come first: a
    Skip reached before it would retire the coverage on the endpoint's word alone, which
    is the failure mode the polling above cannot catch on its own.
    """
    guarded = robot_guards.try_blocks(robot_guards.keyword(RESOURCE, CALLER))
    assert guarded, "the wait must be guarded"

    # Read the EXCEPT branch from the tree rather than slicing a flattened shape to the
    # next END: the first END after the branch marker is only the branch boundary while
    # the branch contains no nested block of its own, so a later IF or FOR inside it would
    # silently truncate the slice and hide whatever came after.
    handler = robot_guards.branch(guarded[0], "EXCEPT")
    assert handler is not None, "the wait must have an EXCEPT handler"
    branch = [call.keyword for call in robot_guards.calls(handler)]

    cross_check = next((index for index, name in enumerate(branch) if name.startswith("No Base Role AIMProfile")), None)
    skip = next((index for index, name in enumerate(branch) if name == "Skip"), None)
    assert cross_check is not None, "the skip must be cross-checked against Kubernetes"
    assert skip is not None, "a template genuinely offering no precision must skip, not fail"
    assert cross_check < skip, "the cross-check must run before the Skip, not after it"
