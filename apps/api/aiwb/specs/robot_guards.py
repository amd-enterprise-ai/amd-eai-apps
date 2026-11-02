# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Shared Robot-source reading for the static guard tests in this directory.

The guards assert structural facts about Robot suites -- that a step is still called, that
a keyword body has not grown a gate -- and every one of them needs the same three things:
find a named block, walk the statements it actually executes, and compare a keyword name
the way Robot compares it.

Read through Robot's own parser rather than over the source text. A statement is a
``KeywordCall`` node or it is not one, so a ``#`` comment that merely mentions a keyword
name can never satisfy an assertion meant to prove that keyword is still called -- the
vacuity these guards exist to prevent is closed by construction instead of by a
hand-written comment stripper. The same applies to the shapes a text scanner has to
special-case one at a time: tab versus two-space cells, a lowercase setting, a
``[Documentation]`` continuation, and an argument continued across lines with ``...``,
which the parser merges back into the single statement it always was.

This module exists so the three guards share one reading of Robot source instead of
carrying near-identical copies. The copies had already drifted once.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

from robot.api import get_model, get_resource_model
from robot.parsing.model.blocks import Block, For, Group, If, Keyword, TestCase, Try, While
from robot.parsing.model.statements import (
    Arguments,
    Comment,
    Documentation,
    EmptyLine,
    KeywordCall,
    Return,
    Setup,
    Teardown,
    Template,
    Var,
)


class Call(NamedTuple):
    """A keyword invocation, however the source spells it.

    ``[Setup]`` and ``[Teardown]`` invoke a keyword just as a plain row does, but Robot
    models them as their own statement types carrying ``name`` rather than ``keyword``.
    Reporting them in one shape keeps the distinction out of every caller -- and a caller
    that only knew about ``KeywordCall`` would not see a step moved into a fixture at all,
    which is the silent direction: an assertion that a keyword is *not* called would pass
    because the walk never looked there.
    """

    keyword: str
    args: tuple[str, ...]


# Blocks whose body is executed and therefore has to be walked. GROUP is RF 7.2+ and is
# purely a labelled wrapper, so a step inside one is still a step the keyword runs.
_NESTED = (If, Try, For, While, Group)

# The only statements that carry no behaviour. Everything else a keyword body can hold --
# BREAK, CONTINUE, [Timeout], [Tags], [Template] -- changes what the keyword does, so the
# readers below represent it rather than skipping it. Skipping by omission is how a pin
# stops pinning: the statement is simply not there to compare.
_NARRATIVE = (Documentation, Comment, EmptyLine)

# Robot strips one of these from the front of a keyword name before resolving it, so
# ``Given a ready project`` and ``a ready project`` are the same call. A guard that pinned
# the prefix would report a pure re-prefix as a regression and miss a step reintroduced
# under a different one.
_BDD_PREFIXES = ("given ", "when ", "then ", "and ", "but ")


def _model(path: Path) -> Any:
    """Robot's parse of a suite or resource file, picking the right reader for the kind."""
    read = get_resource_model if path.suffix == ".resource" else get_model
    return read(str(path))


def _blocks(path: Path, block_type: type) -> Iterator[Any]:
    for section in _model(path).sections:
        for node in getattr(section, "body", []):
            if isinstance(node, block_type):
                yield node


def keyword(path: Path, name: str) -> Keyword:
    """The named keyword block. Missing fails by name, so a rename reports which one.

    Named rather than searched by content: an absent block must never let a negative
    assertion pass against an empty body.
    """
    for block in _blocks(path, Keyword):
        if block.name == name:
            return block
    raise AssertionError(f"no Robot keyword named {name!r} in {path.name}")


def test_case(path: Path, name: str) -> TestCase:
    """The named test case, failing by name for the same reason as :func:`keyword`."""
    for block in _blocks(path, TestCase):
        if block.name == name:
            return block
    raise AssertionError(f"no Robot test case named {name!r} in {path.name}")


def calls(block: Any) -> list[Call]:
    """Every keyword the block invokes, wherever the invocation is written.

    Branches, loops and GROUP bodies are walked because a step can be moved into one
    without changing what the block does, and ``[Setup]``/``[Teardown]`` are included
    because they invoke a keyword too. A reader that missed any of these would report a
    relocated step as deleted -- and, in the direction that actually costs coverage, would
    let a forbidden call hide somewhere the walk never reaches and still report a pass.
    """
    found: list[Call] = []

    def collect(body: Any) -> None:
        for item in body:
            if isinstance(item, KeywordCall):
                found.append(Call(item.keyword, tuple(item.args)))
            elif isinstance(item, (Setup, Teardown)):
                if item.name:
                    found.append(Call(item.name, tuple(item.args)))
            elif isinstance(item, Template):
                # A templated test runs this keyword once per data row, so it is called.
                if item.value:
                    found.append(Call(item.value, ()))
            elif isinstance(item, _NESTED):
                collect(item.body)
                for attribute in ("orelse", "next"):
                    branch = getattr(item, attribute, None)
                    while branch is not None:
                        collect(branch.body)
                        branch = getattr(branch, attribute, None)
            elif isinstance(item, Block):
                # An unrecognised block has a body this walk would not enter, so every
                # call inside it would read as absent. Fail rather than under-report.
                raise AssertionError(
                    f"robot_guards.calls does not know how to walk {type(item).__name__}; "
                    f"teach it that block before relying on this result"
                )

    collect(block.body)
    return found


def try_blocks(block: Any) -> list[Try]:
    """Every TRY block in the body, at any nesting depth.

    Exposed so a guard can read a specific branch from the tree rather than by scanning a
    flattened shape for the next ``END`` -- a scan that silently takes an inner block's
    ``END`` as the boundary the moment the branch grows any nested control flow.
    """
    found: list[Try] = []

    def collect(body: Any) -> None:
        for item in body:
            if isinstance(item, Try):
                found.append(item)
            if isinstance(item, _NESTED):
                collect(item.body)
                for attribute in ("orelse", "next"):
                    branch = getattr(item, attribute, None)
                    while branch is not None:
                        collect(branch.body)
                        branch = getattr(branch, attribute, None)

    collect(block.body)
    return found


def branch(try_block: Try, branch_type: str) -> Try | None:
    """The named branch of a TRY block (``EXCEPT``, ``ELSE``, ``FINALLY``), or ``None``."""
    current = try_block.next
    while current is not None:
        if current.type == branch_type:
            return current
        current = current.next
    return None


def called_names(block: Any) -> list[str]:
    """Normalised names of the keywords the block calls, ready for comparison."""
    return [normalize(call.keyword) for call in calls(block)]


def normalize(name: str) -> str:
    """A keyword name reduced the way Robot compares them.

    Case, spaces and underscores are insignificant to Robot, and a leading BDD prefix is
    stripped before resolution, so all of those must be insignificant here too.
    """
    collapsed = " ".join(str(name).replace("_", " ").split()).lower()
    for prefix in _BDD_PREFIXES:
        if collapsed.startswith(prefix):
            collapsed = collapsed[len(prefix) :]
            break
    return collapsed.replace(" ", "")


def shape(block: Any) -> tuple[tuple[Any, ...], ...]:
    """The block's executable structure as comparable rows, for pinning a whole body.

    Structure rather than text: control-flow markers are their own rows, so a statement
    inserted before a ``TRY`` is as visible as one inside it, and an argument continued
    across lines stays part of the statement it belongs to instead of becoming a row of
    its own. Documentation, comments and blank lines contribute nothing, so narrative can
    be rewritten freely without re-pinning.
    """
    rows: list[tuple[Any, ...]] = []

    def emit(body: Any) -> None:
        for item in body:
            if isinstance(item, KeywordCall):
                rows.append(("KEYWORD", item.keyword, tuple(item.args), tuple(item.assign)))
            elif isinstance(item, (Setup, Teardown)):
                # A fixture invokes a keyword, so it is part of the shape. Omitting it
                # would let a statement be moved into [Teardown] without changing the pin.
                rows.append((item.type, item.name, tuple(item.args)))
            elif isinstance(item, Var):
                rows.append(("VAR", item.name, tuple(item.value), item.scope))
            elif isinstance(item, Return):
                rows.append(("RETURN", tuple(item.values)))
            elif isinstance(item, Arguments):
                rows.append(("ARGUMENTS", tuple(item.values)))
            elif isinstance(item, Try):
                rows.append(("TRY",))
                emit(item.body)
                branch = item.next
                while branch is not None:
                    rows.append((branch.type, tuple(branch.patterns or ()), branch.assign))
                    emit(branch.body)
                    branch = branch.next
                rows.append(("END",))
            elif isinstance(item, If):
                rows.append(("IF", item.condition))
                emit(item.body)
                branch = item.orelse
                while branch is not None:
                    rows.append((branch.type, branch.condition))
                    emit(branch.body)
                    branch = branch.orelse
                rows.append(("END",))
            elif isinstance(item, For):
                # What it iterates is part of the shape: a loop whose iterable changed
                # would otherwise leave a bare marker and slip past an exact pin.
                rows.append(("FOR", tuple(item.assign), item.flavor, tuple(item.values)))
                emit(item.body)
                rows.append(("END",))
            elif isinstance(item, While):
                rows.append(("WHILE", item.condition))
                emit(item.body)
                rows.append(("END",))
            elif isinstance(item, Group):
                rows.append(("GROUP", item.name))
                emit(item.body)
                rows.append(("END",))
            elif isinstance(item, _NARRATIVE):
                continue
            elif isinstance(item, Block):
                raise AssertionError(
                    f"robot_guards.shape does not know how to walk {type(item).__name__}; "
                    f"teach it that block before relying on this pin"
                )
            else:
                # Any other statement -- BREAK, CONTINUE, [Timeout], [Tags], [Template] --
                # still changes the keyword, so it gets a row from its own tokens rather
                # than being dropped. Representing it generically keeps the pin total: an
                # unhandled statement becomes visible in the diff instead of invisible.
                rows.append(
                    (item.type or type(item).__name__.upper(), tuple(token.value for token in item.data_tokens[1:]))
                )

    emit(block.body)
    return tuple(rows)
