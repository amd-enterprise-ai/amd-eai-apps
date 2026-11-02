# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""`--exclude needs-aim-images` can only drop a suite it fully tags.

Custom Models and adapter serving cannot pass on a cluster that publishes no AIM image
catalog: Custom Models discovers a base-image family in its suite setup, and adapter serving
selects a Ready model out of the catalog. On the default CPU runner those are structural
failures, not defects, so CI excludes the `needs-aim-images` tag there. RF prunes a suite at
build time only when *every* selected test is excluded, so one test escaping the tag turns the
exclusion into a no-op and the suite fails structurally again.

These guards keep the tagging honest as the suites grow. Both suites carry the tag as a suite
default, so the risk is not a forgotten tag but an unjustified `-needs-aim-images` opt-out: the
handful of tests that keep running on a catalog-free cluster must genuinely stand on their own.
"""

import re
from pathlib import Path

from robot.running import ResourceFile

# Aliased so pytest does not try to collect the RF class as a test.
from robot.running import TestCase as RobotTestCase
from robot.running import TestSuite as RobotTestSuite

TAG = "needs-aim-images"
SPECS = Path(__file__).parent

# Where a resource import is looked up when it does not resolve beside the importing file,
# mirroring the pythonpath entries arguments.txt gives Robot.
RESOURCE_ROOTS = (SPECS, SPECS / "../../airm/specs", SPECS / "../../../../testing")

# Keywords that resolve a model out of the cluster AIM catalog. Checked against the whole
# expanded call tree below, not just the step a test names.
CATALOG_FIXTURES = (
    "an aim exists in system",
    "the project has gpu quota available",
    "the project has adapter-serving quota available",
    "an aim whose serving hardware cannot carry adapters exists in system",
)

# The adapter-serving scenarios that keep running where no catalog is published: one names a
# deployment that was never created, the other applies its deployment straight as a spec-only
# service. Neither reaches the catalog.
ADAPTER_SERVING_OPT_OUTS = {
    "Removing an adapter once no deployment uses it succeeds",
    "Changing the adapters of a deployment that does not exist is refused",
}

# Every step the opted-out scenarios are allowed to take, each read and confirmed to reach no
# catalog: the project fixtures touch AIRM only, the adapter fixtures work on an artifact the
# test uploads, and the blocking deployment is applied as a spec-only AIMService pinning a
# profile that never resolves. Listing what is permitted rather than what is forbidden is what
# makes this hold for keywords added later -- a composite fixture that selects a model behind
# two layers of indirection is not on this list, so it fails here rather than being read as
# catalog-free. The price is that a genuinely catalog-free step added to these scenarios must
# be read and added; that is the same judgement as opting a scenario out in the first place.
CATALOG_FREE_STEPS = {
    "a ready project with user access exists",
    "a fine-tuning adapter artifact exists in the project",
    "an aim deployment attaching the adapter artifact exists in the project",
    "the deployment using the adapter is removed",
    "the adapter artifact is deleted",
    "the adapter artifact removal should be accepted",
    "the adapter artifact should no longer appear in the project list",
    "the user attempts to change the adapters of a deployment that does not exist",
    "the deployment should not be found",
}

BDD_PREFIXES = ("given ", "when ", "then ", "and ", "but ")

# Body items that invoke a keyword, and body items that cannot reach one. Everything else --
# an unrecognised construct, or a future Robot node type -- fails the walk closed rather than
# being stepped over. `Var` carries a name too, but it assigns a variable rather than calling
# anything, so reading it as a call would look up a keyword that does not exist and clear it.
CALL_NODES = frozenset({"Keyword"})
VARIABLE_MARKER = "${"

# BuiltIns that take a keyword name as an argument, and where that name sits. Robot's polling
# idiom runs through `Wait Until Keyword Succeeds`, so a catalog fixture is as likely to be
# reached from an argument as from a step -- an argument the walk would otherwise never read.
# A variable in the naming position resolves at runtime to anything at all, so it fails closed;
# variables elsewhere in the arguments are ordinary data (timeouts, resource names) and do not.
KEYWORD_RUNNERS = {
    "run keyword": 0,
    "run keyword and continue on failure": 0,
    "run keyword and ignore error": 0,
    "run keyword and return status": 0,
    "run keyword and warn on failure": 0,
    "run keyword and expect error": 1,
    "run keyword if": 1,
    "run keyword unless": 1,
    "repeat keyword": 1,
    "wait until keyword succeeds": 2,
    # Shared helpers that take a GET keyword by name. Listing them is what lets the walk read
    # the literal each caller actually passes, rather than stopping at the variable they
    # forward it through.
    "wait for resource deletion": 0,
    "resource should not exist": 0,
}

# Dispatch through a variable is unknowable statically, so it fails closed -- except at a site
# where the variable is a parameter whose incoming values are already followed at every call
# site, via the entries above. Exempting the forwarding hop then loses no coverage: a caller
# passing a catalog fixture is caught where it passes it. Keyed by the keyword holding the call
# and the variable it runs, so a dynamic site anywhere else still fails rather than inheriting
# this. Anything that is merely believed safe does not belong here -- only what is covered
# elsewhere.
REVIEWED_DYNAMIC_DISPATCH = {
    ("resource should not exist", "${get_keyword}"),
}
INERT_NODES = frozenset({"Var", "Return", "Break", "Continue", "Comment", "Error"})


def _suite(name: str) -> RobotTestSuite:
    return RobotTestSuite.from_file_system(SPECS / name)


def _resolve_import(name: str, importer: Path) -> Path | None:
    for candidate in (importer / name, *(root / name for root in RESOURCE_ROOTS)):
        if candidate.exists():
            return candidate
    return None


def _keyword_index(suite_name: str) -> dict[str, object]:
    """Every user keyword a suite can reach, by lowercase name.

    Resource imports resolve beside the importing file before the pythonpath roots, which is
    the order Robot itself uses; getting that wrong silently yields an empty index and lets
    the reachability check below pass by finding nothing, so an unresolvable import raises.
    """
    index: dict[str, object] = {}
    loaded: set[Path] = set()

    def load(path: Path) -> None:
        path = path.resolve()
        if path in loaded:
            return
        loaded.add(path)
        resource = ResourceFile.from_file_system(path)
        for keyword in resource.keywords:
            index.setdefault(keyword.name.lower(), keyword)
        for item in resource.imports:
            if item.type == "RESOURCE":
                _load_import(item.name, path.parent)

    def _load_import(name: str, importer: Path) -> None:
        target = _resolve_import(name, importer)
        if target is None:
            raise AssertionError(f"cannot resolve resource import {name!r} from {importer}")
        load(target)

    for item in _suite(suite_name).resource.imports:
        if item.type == "RESOURCE":
            _load_import(item.name, SPECS)
    return index


def _catalog_path(step: str, index: dict[str, object], seen: tuple[str, ...] = ()) -> list[str]:
    """The chain of keyword calls from `step` down to a catalog fixture, empty if there is none.

    Only user keywords can be followed. A name that resolves to a Python library keyword is
    read as clean, because the alternative -- failing closed on every `Log` and `Should Be
    Equal` underneath these fixtures -- is a guard nobody can keep green. That gap is covered
    by review instead: the steps an opt-out may take are an allowlist, not merely whatever this
    walk returns nothing for. Pinning the library frontier as well was considered and rejected;
    it would fail for contributors editing shared keywords for unrelated reasons, and a guard
    that cries wolf gets deleted.
    """
    name = _strip_prefix(step)
    if any(fixture in name for fixture in CATALOG_FIXTURES):
        return [name]
    if name in seen:
        return []
    keyword = index.get(name)
    if keyword is None:
        # An unresolved name is normally a Python library keyword, read as clean above. One
        # kind cannot be: a name still carrying a variable resolves at runtime to whatever the
        # variable holds, which may be a catalog fixture. Embedded-argument keywords also carry
        # a variable in their name, but those match a real definition and were followed above.
        if VARIABLE_MARKER in name:
            return [f"<dynamic keyword name {name!r}>"]
        return []
    found = _walk_body(keyword.body, index, (*seen, name))  # type: ignore[attr-defined]
    return [name, *found] if found else []


def _run_argument_path(called: str, args: object, index: dict[str, object], seen: tuple[str, ...]) -> list[str]:
    """Follow the keyword a keyword-running BuiltIn was asked to run, if this is one."""
    position = KEYWORD_RUNNERS.get(_strip_prefix(called))
    if position is None:
        return []
    arguments = list(args)  # type: ignore[call-overload]
    if position >= len(arguments):
        return []
    target = str(arguments[position])
    if VARIABLE_MARKER in target:
        owner = seen[-1] if seen else ""
        if (owner, target) in REVIEWED_DYNAMIC_DISPATCH:
            return []
        return [f"<{called} running a variable keyword name {target!r} in {owner!r}>"]
    found = _catalog_path(target, index, seen)
    return [f"{called} -> {target}", *found[1:]] if found else []


def _walk_body(items: object, index: dict[str, object], seen: tuple[str, ...]) -> list[str]:
    """Follow every keyword call in a body, including the ones nested inside control flow.

    IF, FOR, TRY and WHILE hold their calls in their own bodies rather than exposing them as
    steps, so reading names off the top level alone skips whole branches -- the guard passing
    because it never looked. Anything this does not know how to walk fails closed: an opt-out
    is called catalog-dependent unless the walk actually cleared it. A false positive costs one
    excluded test; a false negative puts the structural failures back on the gate as green.
    """
    for item in items:  # type: ignore[attr-defined]
        kind = type(item).__name__
        if kind in INERT_NODES:
            continue
        if kind in CALL_NODES:
            called = getattr(item, "name", None)
            if not called:
                return [f"<{kind} with no resolvable name>"]
            found = _run_argument_path(called, getattr(item, "args", ()), index, seen)
            if found:
                return found
            found = _catalog_path(called, index, seen)
            if found:
                return found
            continue
        nested = getattr(item, "body", None)
        if nested is None:
            return [f"<unwalkable {kind}>"]
        found = _walk_body(nested, index, seen)
        if found:
            return found
    return []


def _tags(test: RobotTestCase) -> list[str]:
    return [str(tag) for tag in test.tags]


def _step_names(test: RobotTestCase) -> list[str]:
    # Setup and teardown hang off their own attributes and are not part of `body`, so iterating
    # `body` alone would miss a catalog model resolved from [Setup]. An absent setup/teardown is
    # a placeholder Keyword whose name is None, which the name check below discards. The BDD
    # prefix is stripped so re-ordering a step between Given and And is not read as a new one.
    names = []
    for item in (test.setup, *test.body, test.teardown):
        name = getattr(item, "name", None)
        if name:
            names.append(_strip_prefix(name))
    return names


def _strip_prefix(name: str) -> str:
    name = name.lower()
    for prefix in BDD_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def test_custom_models_suite_is_fully_tagged():
    """Its suite setup discovers a base-image family, so no test in it can run without one."""
    suite = _suite("custom_models.robot")

    assert suite.tests, "custom_models.robot must ship at least one test"
    untagged = [t.name for t in suite.tests if TAG not in _tags(t)]
    assert not untagged, f"custom_models tests missing {TAG!r}: {untagged}"


def test_both_suites_carry_the_tag_as_a_suite_default():
    """Tagging every test one by one satisfies the checks above and still leaves the next test
    added untagged -- back to one escapee turning the exclusion into a no-op. The default is
    what makes the dependency inherited, so assert the setting itself, not only its effect."""
    for name in ("custom_models.robot", "adapter_serving.robot"):
        settings = (SPECS / name).read_text()
        declared = re.search(rf"^Test Tags\b.*\b{re.escape(TAG)}\b", settings, re.MULTILINE)
        assert declared, f"{name} must set {TAG!r} as a suite default via Test Tags"


def test_adapter_serving_opt_outs_are_catalog_free():
    """A test opted out of the suite default keeps running on a catalog-free cluster, so it
    must not reach the catalog — otherwise the opt-out puts back the structural failure.

    Judged against the reviewed allowlist rather than a list of known catalog fixtures: a
    keyword can reach the catalog through any depth of indirection, and no name check on the
    step alone can see that. Unrecognised means unproven here, not proven safe.
    """
    suite = _suite("adapter_serving.robot")

    unreviewed = {
        step
        for test in suite.tests
        if TAG not in _tags(test)
        for step in _step_names(test)
        if step not in CATALOG_FREE_STEPS
    }
    assert not unreviewed, (
        f"tests opted out of {TAG!r} take steps not reviewed as catalog-free: {sorted(unreviewed)}. "
        f"Confirm each reaches no AIM catalog and add it to CATALOG_FREE_STEPS, or drop the opt-out."
    )


def test_opt_out_steps_do_not_reach_the_catalog_through_other_keywords():
    """The allowlist is read once; the keywords behind it keep changing. A composite that
    starts resolving a catalog model puts the structural failure back into a scenario the CPU
    gate still selects, without any of its step names changing."""
    suite = _suite("adapter_serving.robot")
    index = _keyword_index("adapter_serving.robot")

    reaching = {
        step: " -> ".join(path)
        for test in suite.tests
        if TAG not in _tags(test)
        for step in _step_names(test)
        if (path := _catalog_path(step, index))
    }
    assert not reaching, f"steps taken by a {TAG!r} opt-out now reach the AIM catalog: {reaching}"


def test_an_unrecognised_construct_is_treated_as_catalog_dependent():
    """The walk is only worth having if its unknowns land on the safe side. A construct it
    cannot follow -- a Robot node type added later, a dynamically named call -- must read as
    reaching the catalog, so the opt-out fails review rather than passing unexamined."""

    class Mystery:
        """Stands in for a body item the walk has no rule for."""

    class UnnamedCall:
        name = None

    UnnamedCall.__name__ = "Keyword"

    assert _walk_body([Mystery()], {}, ()), "an unknown construct must fail closed"
    assert _walk_body([UnnamedCall()], {}, ()), "a call with no resolvable name must fail closed"


def test_a_dynamically_named_call_is_treated_as_catalog_dependent():
    """A call named by a variable resolves to whatever that variable holds -- possibly a
    catalog fixture -- and no static walk can tell. It must not read as a library keyword.

    An embedded-argument keyword carries a variable in its name too but matches a real
    definition, so the distinction is resolvability, not the presence of a variable: treating
    every `${` as dynamic would fail the project fixture these opt-outs legitimately use.
    """
    index = _keyword_index("adapter_serving.robot")

    assert _catalog_path("${keyword}", index), "a dynamically named call must fail closed"
    assert not _catalog_path('Project "${project_name}" exists in system', index), (
        "an embedded-argument keyword resolves to a definition and must still be followed"
    )


def test_catalog_fixtures_and_opt_out_steps_all_resolve():
    """Anti-vacuity for the walk above: it can only report a catalog path for names it can
    actually follow, so a renamed fixture or step would retire the check in silence."""
    index = _keyword_index("adapter_serving.robot")

    missing_fixtures = [name for name in CATALOG_FIXTURES if name not in index]
    assert not missing_fixtures, f"CATALOG_FIXTURES names no longer defined: {missing_fixtures}"

    missing_steps = [name for name in CATALOG_FREE_STEPS if name not in index]
    assert not missing_steps, f"CATALOG_FREE_STEPS names no longer defined: {missing_steps}"


def test_reviewed_dynamic_dispatch_sites_still_exist():
    """An exemption that outlives its call site is a hole waiting for a name to be reused."""
    index = _keyword_index("adapter_serving.robot")

    for owner, variable in REVIEWED_DYNAMIC_DISPATCH:
        keyword = index.get(owner)
        assert keyword is not None, f"exempted keyword {owner!r} no longer exists"
        runs_it = any(
            variable in [str(argument) for argument in getattr(item, "args", ())]
            for item in keyword.body  # type: ignore[attr-defined]
        )
        assert runs_it, f"{owner!r} no longer dispatches on {variable!r}; drop the exemption"


def test_catalog_free_steps_are_all_still_taken():
    """Anti-rot: a renamed or removed step would sit in the allowlist forever, widening what a
    future opt-out may silently take. Keep the list to steps the opt-outs actually use."""
    suite = _suite("adapter_serving.robot")

    taken = {step for test in suite.tests if TAG not in _tags(test) for step in _step_names(test)}
    assert CATALOG_FREE_STEPS <= taken, (
        f"CATALOG_FREE_STEPS lists steps no opt-out takes: {sorted(CATALOG_FREE_STEPS - taken)}"
    )


def test_adapter_serving_opt_outs_are_exactly_the_declared_ones():
    """Which scenarios still run on a catalog-free cluster is what an operator reads this
    exclusion by, so the set is written down rather than counted off the file. Widening it is a
    deliberate act: adding an opt-out here is the same decision as adding one in the suite."""
    suite = _suite("adapter_serving.robot")

    opted_out = {t.name for t in suite.tests if TAG not in _tags(t)}
    assert opted_out == ADAPTER_SERVING_OPT_OUTS, (
        f"adapter_serving opt-outs changed: unexpected {sorted(opted_out - ADAPTER_SERVING_OPT_OUTS)}, "
        f"missing {sorted(ADAPTER_SERVING_OPT_OUTS - opted_out)}"
    )
