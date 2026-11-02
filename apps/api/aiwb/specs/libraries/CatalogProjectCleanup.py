# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Scoped adopted-project tracking-list logic for AIWB E2E teardowns.

``Clean Up Adopted Projects`` (airm_projects.resource) drains the ENTIRE
run-scoped ``ADOPTED_PROJECT_IDS`` list — correct at its one intended call site
(the parent directory's Suite Teardown, which owns every adopted project by the
time it runs) but wrong for a child suite that is also run standalone: draining
the whole list there would delete sibling suites' still-shared projects too, if
this suite ever ran nested mid-directory instead.

This keeps the list-scoping decision in one small, directly testable function so
"only remove the one id this suite owns, never anyone else's" is a property a
unit test can actually prove, rather than something only visible by reading
Robot source text (which a stray comment can satisfy without the real keyword
call existing at all).
"""

from robot.api.deco import keyword


@keyword
def remove_adopted_project_id(adopted_ids: list, project_id: str) -> list:
    """Returns ``adopted_ids`` with ``project_id`` removed and nothing else.

    "One project", not "one list entry": EVERY occurrence of ``project_id`` is
    dropped. The project is deleted once, so a second entry for it could only
    ever be a stale pointer to something already gone.
    ``Track Adopted Project For Suite Cleanup`` dedupes on insert, so a repeat
    should not arise in the first place; dropping all of them is simply the safe
    direction if one ever does.

    Every other id — regardless of how many times it repeats or where it sits —
    is preserved in its original order. Does not mutate the input list.
    """
    return [pid for pid in adopted_ids if pid != project_id]


@keyword
def scoped_cleanup_result(adopted_ids: list, project_id: str, deletion_confirmed: bool) -> list:
    """Returns the ``ADOPTED_PROJECT_IDS`` state ``Clean Up Catalog Project`` should set.

    Deliberately does NOT rely on the calling Robot keyword stopping execution
    after a failed delete/wait: Robot Framework's "continue on failure" mode is
    automatically on inside every teardown, at every keyword-call depth, so a
    failed keyword does not by itself prevent later statements in the same
    teardown from running — including a statement placed right after a failing
    call but still inside the same ``TRY`` body, which also still runs. Overriding
    that with continue/stop-on-failure tags on a teardown keyword is itself
    unreliable, so the control flow must not depend on it. The caller always calls
    this function;
    ``deletion_confirmed`` is what decides the outcome, and that flag must come
    from a single atomic call whose own PASS/FAIL becomes the boolean directly
    (``Run Keyword And Return Status`` around the wait), never from a follow-up
    statement after the wait, so a failed wait leaves it ``False`` and this
    function preserves tracking.
    """
    if not deletion_confirmed:
        # Register it if it is not already there, rather than only preserving an
        # existing entry. A setup that aborts after creating the project but before
        # adoption tracking leaves it untracked, and the per-suite delete is then the
        # last reference to it - so returning the list unchanged would drop a project
        # that is still alive. Adding it lets a directory-level teardown retry the
        # delete, which is what the caller's warning already promises.
        if project_id in adopted_ids:
            return list(adopted_ids)
        return [*adopted_ids, project_id]
    return remove_adopted_project_id(adopted_ids, project_id)
