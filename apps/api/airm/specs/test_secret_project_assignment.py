# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Guards additive organization-secret assignment in shared E2E setup.

The shared setup must add the current project to a secret's assignment set and
never replace that set: the organization-scoped endpoint drops every project
omitted from the PUT, so under the concurrent-run model a full replace here
strips the secret from another run's project.

Asserts over the parsed Robot model rather than the source text. A substring
check cannot express this rule: Robot matches keyword names ignoring case,
spaces and underscores, so ``Assign Secret To Projects`` is the same keyword as
``assign_secret_to_projects`` and a literal search for one spelling misses the
others. Normalizing the parsed call names the way Robot itself compares them is
what makes the guard bind on the keyword rather than on how it was typed.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterable
from typing import Any

import pytest
from robot.api import get_resource_model
from robot.parsing.model.blocks import For, If, Keyword, Try
from robot.parsing.model.statements import KeywordCall

_SPECS = pathlib.Path(__file__).resolve().parent

# Every shared-setup site that assigns an organization secret to the current project. Both
# use the additive endpoint for the same reason, so both need the same guard: covering only
# one leaves the rule enforced on paper while the other can quietly switch to a full
# replace. The MinIO one runs in universal project setup, so it is the more heavily used.
_GUARDED = (
    ("airm_secrets.resource", 'Secret "${secret_name}" is assigned to project'),
    ("airm_projects.resource", "MinIO credentials are available in the current project"),
)

_ADDITIVE = "assignsecrettoproject"
_DESTRUCTIVE = "assignsecrettoprojects"


def _normalize(name: str) -> str:
    """Collapses a keyword name the way Robot compares them: no case, space or underscore."""
    return name.replace(" ", "").replace("_", "").lower()


def _keyword_calls(resource_name: str, keyword_name: str) -> list[KeywordCall]:
    """Returns every keyword call in the named keyword, including nested bodies."""
    model = get_resource_model(_SPECS / "resources" / resource_name)
    target = None
    for section in model.sections:
        for node in section.body:
            if isinstance(node, Keyword) and node.name == keyword_name:
                target = node
    assert target is not None, f"{keyword_name} not found in {resource_name}"

    return _collect_calls(target.body)


def _collect_calls(body: Iterable[Any]) -> list[KeywordCall]:
    """Every KeywordCall in a keyword body, descending into FOR, IF and TRY blocks.

    Robot links IF chains through .orelse but TRY chains through .next, so a walk
    following only .orelse stops at the TRY body and never sees EXCEPT, ELSE or
    FINALLY - which is where a full-replace call would hide from this guard.
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


@pytest.mark.parametrize(("resource_name", "keyword_name"), _GUARDED)
def test_keyword_assigns_the_project_additively(resource_name: str, keyword_name: str) -> None:
    """The additive, project-scoped assignment call is present."""
    names = [_normalize(call.keyword or "") for call in _keyword_calls(resource_name, keyword_name)]
    assert names.count(_ADDITIVE) == 1


@pytest.mark.parametrize(("resource_name", "keyword_name"), _GUARDED)
def test_keyword_never_replaces_the_whole_assignment_set(resource_name: str, keyword_name: str) -> None:
    """No full-replace assignment, however it is spelled.

    Catches the additive-plus-destructive shape too: keeping the additive call and
    appending a full replace still violates the rule, so this asserts on the absence
    of the destructive keyword rather than on the presence of the additive one.
    """
    names = [_normalize(call.keyword or "") for call in _keyword_calls(resource_name, keyword_name)]
    assert _DESTRUCTIVE not in names


@pytest.mark.parametrize(("resource_name", "keyword_name"), _GUARDED)
def test_keyword_does_not_hand_roll_a_full_replace_request(resource_name: str, keyword_name: str) -> None:
    """No full replace issued directly, bypassing the keyword check above.

    ``projectIds`` is the request field of the destructive endpoint
    (``PUT /secrets/{id}/assign``, api/secrets.resource). A hand-rolled
    ``Safe Put Request`` carrying that payload revokes every project omitted from
    it, exactly like the keyword, while calling no keyword named "assign secret to
    projects" - so the name check alone would not see it.

    Note ``projectSecrets`` is a RESPONSE field only, so guarding that string here
    would forbid something a request can never contain.
    """
    for call in _keyword_calls(resource_name, keyword_name):
        for arg in call.args:
            assert "projectIds" not in arg, f"hand-rolled full-replace payload in: {call.keyword}"
        if _normalize(call.keyword or "") == _normalize("Safe Put Request"):
            assert not any("/assign" in arg for arg in call.args), "direct PUT to the assign endpoint"
