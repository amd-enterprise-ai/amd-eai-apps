# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the scoped adopted-project cleanup logic used by the standalone
AIM catalog suite teardown.

Clean Up Adopted Projects (airm_projects.resource) drains the entire run-scoped
ADOPTED_PROJECT_IDS list — correct only at its intended call site (the parent
directory's Suite Teardown). aim_catalog.robot is documented and run in CI as a
standalone suite, so it must clean up only the one project it itself adopted,
never anyone else's still-tracked project. These tests exercise the exact
function the Robot keyword calls (remove_adopted_project_id), not a parsed
source-text approximation of it.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_SPECS = pathlib.Path(__file__).resolve().parent
_LIBRARY = _SPECS / "libraries" / "CatalogProjectCleanup.py"
_SPEC = importlib.util.spec_from_file_location("CatalogProjectCleanup", _LIBRARY)
assert _SPEC is not None and _SPEC.loader is not None
catalog_project_cleanup = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("CatalogProjectCleanup", catalog_project_cleanup)
_SPEC.loader.exec_module(catalog_project_cleanup)

remove_adopted_project_id = catalog_project_cleanup.remove_adopted_project_id
scoped_cleanup_result = catalog_project_cleanup.scoped_cleanup_result


def test_removes_only_the_targeted_project() -> None:
    remaining = remove_adopted_project_id(["proj-a", "proj-b", "proj-c"], "proj-b")
    assert remaining == ["proj-a", "proj-c"]


def test_preserves_every_unrelated_project_untouched() -> None:
    others = ["proj-a", "proj-c", "proj-d"]
    remaining = remove_adopted_project_id(["proj-a", "target", "proj-c", "proj-d"], "target")
    assert remaining == others


def test_removes_every_occurrence_of_the_target() -> None:
    """A repeated target id is dropped completely, not once.

    The project is deleted a single time, so a surviving second entry would be a
    stale pointer to something already gone, and the run-scoped teardown would
    later try to delete it again. Track Adopted Project For Suite Cleanup dedupes on insert so this
    should not arise; the behaviour is pinned here because the function name alone
    could be read as "remove one entry".
    """
    remaining = remove_adopted_project_id(["proj-a", "dupe", "proj-c", "dupe"], "dupe")
    assert remaining == ["proj-a", "proj-c"]


def test_target_not_present_leaves_list_unchanged() -> None:
    remaining = remove_adopted_project_id(["proj-a", "proj-c"], "not-tracked")
    assert remaining == ["proj-a", "proj-c"]


def test_empty_list_stays_empty() -> None:
    assert remove_adopted_project_id([], "proj-b") == []


def test_does_not_mutate_the_input_list() -> None:
    """Returning a new list is what lets the caller decide whether to keep the change.

    Clean Up Catalog Project calls this unconditionally, on the failed paths too, so
    mutating the caller's list in place would drop tracking for a project whose
    deletion was never confirmed - even though the caller then discards the return
    value.
    """
    original = ["proj-a", "proj-b", "proj-c"]
    remove_adopted_project_id(original, "proj-b")
    assert original == ["proj-a", "proj-b", "proj-c"]


def test_scoped_cleanup_preserves_tracking_when_deletion_not_confirmed() -> None:
    """Clean Up Catalog Project calls this unconditionally, regardless of whether the
    delete/wait succeeded — Robot's teardown continue-on-failure mode means the calling
    keyword's later statements always run. The safety property must therefore live here,
    not in whether Robot code after a failure executes: a False confirmation must leave
    the project's own id in the list, exactly as if the call had never happened."""
    adopted = ["proj-a", "catalog-project", "proj-c"]
    result = scoped_cleanup_result(adopted, "catalog-project", False)
    assert result == adopted


def test_scoped_cleanup_removes_only_the_confirmed_project() -> None:
    adopted = ["proj-a", "catalog-project", "proj-c"]
    result = scoped_cleanup_result(adopted, "catalog-project", True)
    assert result == ["proj-a", "proj-c"]


def test_scoped_cleanup_does_not_mutate_input_when_unconfirmed() -> None:
    original = ["proj-a", "catalog-project"]
    scoped_cleanup_result(original, "catalog-project", False)
    assert original == ["proj-a", "catalog-project"]


def test_scoped_cleanup_registers_an_untracked_project_when_unconfirmed() -> None:
    """An unconfirmed deletion adds the project if nothing was tracking it yet.

    Setup can abort after creating the project but before anything adopts it, and the
    per-suite delete is then the last reference to a project that is still alive.
    Preserving the list unchanged would drop it; adding it lets a directory-level
    teardown retry the delete, which is what the caller's warning promises.
    """
    assert scoped_cleanup_result([], "catalog-project", False) == ["catalog-project"]
    assert scoped_cleanup_result(["proj-a"], "catalog-project", False) == ["proj-a", "catalog-project"]


def test_scoped_cleanup_does_not_duplicate_an_already_tracked_project() -> None:
    """Registering is idempotent, so a repeated teardown cannot stack duplicates."""
    assert scoped_cleanup_result(["proj-a", "catalog-project"], "catalog-project", False) == [
        "proj-a",
        "catalog-project",
    ]


def test_scoped_cleanup_on_an_empty_list_confirmed_stays_empty() -> None:
    """A confirmed deletion never registers anything - there is nothing left to track."""
    assert scoped_cleanup_result([], "catalog-project", True) == []
