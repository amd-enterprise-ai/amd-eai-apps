# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Direct coverage for the shared Robot-source reading in :mod:`robot_guards`.

Three guards now depend on this module, so a silent narrowing here weakens all of them at
once and in the direction that reads as a pass: a statement the walk fails to reach is a
statement no assertion can object to. The consumers exercise it against real fixtures,
which cannot reach the shapes those fixtures happen not to contain -- nested branches,
FOR/WHILE bodies, a keyword that does not exist. Those are covered here, on synthetic
sources, so the coverage does not depend on what the suites look like today.
"""

from pathlib import Path

import pytest
import robot_guards


def _resource(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "sample.resource"
    path.write_text(f"*** Keywords ***\n{body}")
    return path


def test_calls_reaches_every_branch_of_nested_control_flow(tmp_path: Path) -> None:
    """A step moved into a branch is still called, so the walk has to follow branches.

    A reader that only saw the top level would report a step relocated into an ELSE, an
    EXCEPT or a loop body as deleted -- and, worse in this direction, would not see a gate
    hidden in one.
    """
    path = _resource(
        tmp_path,
        "Sample\n"
        "    Top Level\n"
        "    IF    ${a}\n"
        "        In If\n"
        "    ELSE IF    ${b}\n"
        "        In Else If\n"
        "    ELSE\n"
        "        In Else\n"
        "    END\n"
        "    TRY\n"
        "        In Try\n"
        "    EXCEPT    boom\n"
        "        In Except\n"
        "    ELSE\n"
        "        In Try Else\n"
        "    FINALLY\n"
        "        In Finally\n"
        "    END\n"
        "    FOR    ${i}    IN    @{xs}\n"
        "        In For\n"
        "    END\n"
        "    WHILE    ${c}\n"
        "        In While\n"
        "    END\n"
        "    GROUP    labelled\n"
        "        In Group\n"
        "    END\n",
    )

    called = [call.keyword for call in robot_guards.calls(robot_guards.keyword(path, "Sample"))]
    assert called == [
        "Top Level",
        "In If",
        "In Else If",
        "In Else",
        "In Try",
        "In Except",
        "In Try Else",
        "In Finally",
        "In For",
        "In While",
        "In Group",
    ]


def test_a_fixture_invokes_a_keyword_and_must_be_seen_as_one(tmp_path: Path) -> None:
    """``[Setup]`` and ``[Teardown]`` call keywords, and Robot models them separately.

    A reader that only knew ``KeywordCall`` would not see them, which fails in the
    expensive direction: an assertion that some keyword is *not* called would pass while
    the call sat in a fixture the walk never reached.
    """
    path = _resource(
        tmp_path,
        "Sample\n    [Setup]    In Setup\n    Body Step\n    [Teardown]    In Teardown    arg\n",
    )

    calls = robot_guards.calls(robot_guards.keyword(path, "Sample"))
    assert [call.keyword for call in calls] == ["In Setup", "Body Step", "In Teardown"]
    assert calls[-1].args == ("arg",)


def test_shape_records_fixtures_groups_and_what_a_loop_iterates(tmp_path: Path) -> None:
    """A pin must move when any of these move, or it is not pinning them.

    A statement relocated into ``[Teardown]`` or a ``GROUP``, or a loop pointed at a
    different iterable, each changes what the keyword does.
    """
    path = _resource(
        tmp_path,
        "Sample\n"
        "    [Setup]    Prepare\n"
        "    GROUP    labelled\n"
        "        Inside\n"
        "    END\n"
        "    FOR    ${i}    IN    @{xs}\n"
        "        Looped\n"
        "    END\n"
        "    [Teardown]    Finish\n",
    )

    assert robot_guards.shape(robot_guards.keyword(path, "Sample")) == (
        ("SETUP", "Prepare", ()),
        ("GROUP", "labelled"),
        ("KEYWORD", "Inside", (), ()),
        ("END",),
        ("FOR", ("${i}",), "IN", ("@{xs}",)),
        ("KEYWORD", "Looped", (), ()),
        ("END",),
        ("TEARDOWN", "Finish", ()),
    )


def test_no_statement_is_dropped_from_a_pin_just_because_it_is_unrecognised(tmp_path: Path) -> None:
    """A pin that silently skips statement kinds is not pinning the body, only part of it.

    ``BREAK`` and ``CONTINUE`` change control flow, and ``[Timeout]``/``[Tags]`` change how
    the keyword runs -- a one-second timeout added to a keyword that polls for two minutes
    breaks it outright. None of them is a ``KeywordCall``, so an if/elif chain over known
    types drops them, and a dropped statement cannot fail a comparison: it is simply not
    there. The walk therefore represents every statement it does not narrate.
    """
    path = _resource(
        tmp_path,
        "Sample\n"
        "    [Timeout]    5s\n"
        "    [Tags]    slow\n"
        "    FOR    ${i}    IN    @{xs}\n"
        "        IF    ${c}\n"
        "            CONTINUE\n"
        "        END\n"
        "        BREAK\n"
        "    END\n",
    )

    assert robot_guards.shape(robot_guards.keyword(path, "Sample")) == (
        ("TIMEOUT", ("5s",)),
        ("TAGS", ("slow",)),
        ("FOR", ("${i}",), "IN", ("@{xs}",)),
        ("IF", "${c}"),
        ("CONTINUE", ()),
        ("END",),
        ("BREAK", ()),
        ("END",),
    )


def test_narrative_is_still_the_only_thing_a_pin_ignores(tmp_path: Path) -> None:
    """Documentation and comments must remain free to rewrite, or every edit re-pins."""
    path = _resource(
        tmp_path,
        "Sample\n    [Documentation]    Narrative.\n    ...    More narrative.\n    # A comment\n    Step\n",
    )

    assert robot_guards.shape(robot_guards.keyword(path, "Sample")) == (("KEYWORD", "Step", (), ()),)


def test_a_template_runs_a_keyword_and_counts_as_calling_it(tmp_path: Path) -> None:
    """``[Template]`` names the keyword each data row invokes, so the walk must see it."""
    path = tmp_path / "templated.robot"
    path.write_text("*** Test Cases ***\nCase\n    [Template]    Templated Step\n    one\n    two\n")

    called = [call.keyword for call in robot_guards.calls(robot_guards.test_case(path, "Case"))]
    assert "Templated Step" in called


def test_a_branch_is_read_from_the_tree_not_by_scanning_for_the_next_end(tmp_path: Path) -> None:
    """Nested control flow inside a branch must not truncate it.

    Slicing a flattened shape to the first ``END`` after the branch marker works only
    while the branch stays flat; an inner IF closes first and everything after it
    disappears, taking any later statement out of view.
    """
    path = _resource(
        tmp_path,
        "Sample\n"
        "    TRY\n"
        "        Risky\n"
        "    EXCEPT    AS    ${err}\n"
        "        First\n"
        "        IF    ${c}\n"
        "            Nested\n"
        "        END\n"
        "        Last\n"
        "    END\n",
    )

    handler = robot_guards.branch(robot_guards.try_blocks(robot_guards.keyword(path, "Sample"))[0], "EXCEPT")
    assert handler is not None
    assert [call.keyword for call in robot_guards.calls(handler)] == ["First", "Nested", "Last"]


def test_a_comment_is_never_read_as_a_call(tmp_path: Path) -> None:
    """The vacuity the guards exist to prevent, asserted at the source of the reading.

    A keyword name left behind in a comment or in documentation must not be able to
    satisfy an assertion that the keyword is still called.
    """
    path = _resource(
        tmp_path,
        "Sample\n"
        "    [Documentation]    Calls Deleted Step and then Another Deleted Step.\n"
        "    # Deleted Step\n"
        "    Real Step    # Deleted Step\n",
    )

    called = [call.keyword for call in robot_guards.calls(robot_guards.keyword(path, "Sample"))]
    assert called == ["Real Step"]


def test_shape_ignores_narrative_but_keeps_structure(tmp_path: Path) -> None:
    """Documentation must not be pinnable; control flow and continuations must be.

    An argument continued with ``...`` belongs to its statement rather than forming a row
    of its own -- the shape a line-based reading would have split.
    """
    path = _resource(
        tmp_path,
        "Sample\n"
        "    [Documentation]    Narrative that must not appear in the shape.\n"
        "    ...    across two lines.\n"
        "    ${x}=    Produce    one\n"
        "    ...    two\n"
        "    TRY\n"
        "        Risky\n"
        "    EXCEPT    AS    ${err}\n"
        "        Handle    ${err}\n"
        "    END\n"
        "    RETURN    ${x}\n",
    )

    assert robot_guards.shape(robot_guards.keyword(path, "Sample")) == (
        ("KEYWORD", "Produce", ("one", "two"), ("${x}=",)),
        ("TRY",),
        ("KEYWORD", "Risky", (), ()),
        ("EXCEPT", (), "${err}"),
        ("KEYWORD", "Handle", ("${err}",), ()),
        ("END",),
        ("RETURN", ("${x}",)),
    )


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("A Ready Project", "areadyproject"),
        ("Given a ready project", "areadyproject"),
        ("WHEN A Ready Project", "areadyproject"),
        ("Then    a   ready   project", "areadyproject"),
        ("And_A_Ready_Project", "areadyproject"),
        ("But a ready project", "areadyproject"),
        # Only the leading prefix is a prefix. A second BDD word is part of the name, so
        # stripping repeatedly would collapse two different keywords onto one.
        ("Given given a ready project", "givenareadyproject"),
        # A word merely starting with a prefix is not prefixed.
        ("Andover project", "andoverproject"),
    ],
)
def test_normalize_matches_how_robot_compares_keyword_names(written: str, expected: str) -> None:
    """Robot ignores case, spaces and underscores and strips one leading BDD prefix.

    Pinning any of those would report a pure rename as a regression, and -- the direction
    that matters -- would let a forbidden step return under a different spelling.
    """
    assert robot_guards.normalize(written) == expected


def test_a_missing_block_fails_by_name(tmp_path: Path) -> None:
    """A renamed or deleted block must be reported, never treated as an empty body.

    An empty body satisfies every negative assertion, so silently returning one would turn
    the deletion of a guarded keyword into a passing test.
    """
    path = _resource(tmp_path, "Sample\n    Step\n")

    with pytest.raises(AssertionError, match="Absent Keyword"):
        robot_guards.keyword(path, "Absent Keyword")

    with pytest.raises(AssertionError, match="Absent Case"):
        robot_guards.test_case(path, "Absent Case")
