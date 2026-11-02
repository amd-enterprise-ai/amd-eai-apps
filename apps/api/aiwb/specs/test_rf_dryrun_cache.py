# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for tooling/rf_dryrun_cache.py — the --dryrun keyword-resolution cache.

The cache must never change what a dry-run reports. Because a dry-run is a
*validation gate*, that includes the runs it is supposed to REJECT: these tests
therefore cover failing fixtures (unknown keyword, wrong argument count) as well
as passing ones, and assert the plain and cached runs agree in both directions.

Each test builds a throwaway Robot project under tmp_path (never under specs/, so
the real dry-run cannot discover it) and runs it in a subprocess, with and without
the listener. A probe listener asserts the cache was actually populated, so a
silent fallback to uncached — e.g. the version/internals guard rejecting a future
RF — cannot masquerade as "cache verified" by making both sides trivially equal.
"""

import importlib.util
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
TOOLING = REPO_ROOT / "tooling"

# tooling/ is not an importable package from here, so load the module by path.
# Importing it is inert — it only defines the listener hooks; nothing is patched
# until start_suite observes a dry-run.
_SPEC = importlib.util.spec_from_file_location("rf_dryrun_cache", TOOLING / "rf_dryrun_cache.py")
assert _SPEC is not None and _SPEC.loader is not None
rf_dryrun_cache = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rf_dryrun_cache)

# resource_a and resource_b each define "Shared Step" with a different arg count.
# A keyword defined in each file calls "Shared Step" with the arg count matching
# its own file's definition; RF's same-file prioritisation makes each resolve
# locally. A resolution cache keyed by name alone would break one of them.
RESOURCE_A = """\
*** Keywords ***
Shared Step
    [Arguments]    ${only_one}
    Log    ${only_one}

Call Shared From A
    Shared Step    one
"""

RESOURCE_B = """\
*** Keywords ***
Shared Step
    [Arguments]    ${first}    ${second}
    Log    ${first} ${second}

Call Shared From B
    Shared Step    one    two
"""

RESOURCE_C = """\
*** Keywords ***
Keyword From C
    Log    from c
"""

LIBRARY_D = """\
def keyword_from_d():
    pass
"""

PASSING_SUITE = """\
*** Settings ***
Resource    resource_a.resource
Resource    resource_b.resource

*** Test Cases ***
Resolves Shared Step In Caller A Context
    Call Shared From A

Resolves Shared Step In Caller B Context
    Call Shared From B

Uses An Unambiguous Keyword Many Times
    Log    hello
    Log    hello
    Log    hello
"""

# A dry-run must still REJECT these. Memoizing a validation gate is exactly the
# risk this change carries, so the rejections are asserted to be identical too.
FAILING_SUITE = """\
*** Settings ***
Resource    resource_a.resource

*** Test Cases ***
Unknown Keyword Is Rejected
    This Keyword Does Not Exist Anywhere

Wrong Argument Count Is Rejected
    Call Shared From A
    Shared Step    one    two    three

Valid Test Still Passes
    Call Shared From A
"""

# "Keyword From C" is looked up BEFORE resource_c is imported (so a 0-match result
# is cached), then again after. If the import did not invalidate the cache, the
# second lookup would serve the stale "not found" and fail.
INVALIDATION_SUITE = """\
*** Test Cases ***
Lookup Before Import Fails
    Keyword From C

Lookup After Import Succeeds
    Import Resource    ${CURDIR}/resource_c.resource
    Keyword From C
"""

LIBRARY_INVALIDATION_SUITE = """\
*** Test Cases ***
Lookup Before Import Fails
    Keyword From D

Lookup After Import Succeeds
    Import Library    library_d.py
    Keyword From D
"""

# Runs after rf_dryrun_cache and records how many entries the root store's cache
# actually accumulated, so the tests can prove the cache was live.
PROBE_LISTENER = """\
from pathlib import Path

from robot.running.context import EXECUTION_CONTEXTS

ROBOT_LISTENER_API_VERSION = 3
_MARKER = Path(__file__).with_name("cache_probe.txt")


def end_test(data, result):
    store = EXECUTION_CONTEXTS.current.namespace._kw_store
    entries = len(getattr(store, "_dryrun_res_scan", {}) or {})
    previous = int(_MARKER.read_text()) if _MARKER.exists() else 0
    _MARKER.write_text(str(max(previous, entries)))
"""


@dataclass
class RobotResult:
    returncode: int
    statuses: dict[str, str]
    stdout: str
    stderr: str


def _write_resources(root: Path) -> None:
    (root / "resource_a.resource").write_text(RESOURCE_A)
    (root / "resource_b.resource").write_text(RESOURCE_B)
    (root / "resource_c.resource").write_text(RESOURCE_C)
    (root / "library_d.py").write_text(LIBRARY_D)
    (root / "probe_listener.py").write_text(PROBE_LISTENER)


def _run(
    root: Path,
    suite: str,
    *,
    dryrun: bool,
    cache: bool,
    expect_rc: int | None = None,
) -> RobotResult:
    """Run one robot subprocess and return its per-test statuses.

    ``expect_rc`` asserts robot's exit code when the fixture's outcome is known;
    pass ``None`` to accept any code. Robot reports failing tests with a non-zero
    code, so the failing fixtures need this rather than a blanket ``== 0``.
    """
    tag = f"{suite}_{'dry' if dryrun else 'real'}_{'cache' if cache else 'plain'}"
    output = root / f"out_{tag}.xml"
    cmd = [
        sys.executable,
        "-m",
        "robot",
        "--output",
        str(output),
        "--log",
        "NONE",
        "--report",
        "NONE",
    ]
    if dryrun:
        cmd.append("--dryrun")
    cmd += ["--pythonpath", str(root)]
    if cache:
        # The probe must load after the cache listener so it observes the patch.
        cmd += [
            "--pythonpath",
            str(TOOLING),
            "--listener",
            "rf_dryrun_cache",
            "--listener",
            "probe_listener",
        ]
    cmd += [str(root / f"{suite}.robot")]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    # A robot that never ran (bad listener, import error) yields a missing or
    # partial XML; surface its output instead of a confusing parse error.
    assert output.exists(), (
        f"robot produced no output (rc={proc.returncode})\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    if expect_rc is not None:
        assert proc.returncode == expect_rc, (
            f"robot exited {proc.returncode}, expected {expect_rc}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    # The listener swallows install failures and continues uncached. If that
    # happened, an identity assertion would hold trivially and prove nothing.
    if cache:
        assert "rf_dryrun_cache: not installed" not in proc.stderr, (
            f"cache silently fell back to uncached:\n{proc.stderr}"
        )
    tree = ET.parse(output)
    statuses: dict[str, str] = {}
    for test in tree.iter("test"):
        name = test.get("name")
        status = test.find("status")
        assert name is not None and status is not None
        statuses[name] = status.get("status", "")
    return RobotResult(proc.returncode, statuses, proc.stdout, proc.stderr)


def _cache_entries(root: Path) -> int:
    marker = root / "cache_probe.txt"
    return int(marker.read_text()) if marker.exists() else 0


def test_dryrun_outcome_identical_with_and_without_cache(tmp_path):
    _write_resources(tmp_path)
    (tmp_path / "passing.robot").write_text(PASSING_SUITE)
    plain = _run(tmp_path, "passing", dryrun=True, cache=False, expect_rc=0)
    cached = _run(tmp_path, "passing", dryrun=True, cache=True, expect_rc=0)
    assert plain.statuses == cached.statuses
    # The ambiguous keyword must resolve in each caller's own context.
    assert cached.statuses == {
        "Resolves Shared Step In Caller A Context": "PASS",
        "Resolves Shared Step In Caller B Context": "PASS",
        "Uses An Unambiguous Keyword Many Times": "PASS",
    }
    # Prove the cache was actually exercised, not silently skipped.
    assert _cache_entries(tmp_path) > 0


def test_dryrun_still_rejects_invalid_keywords_with_cache(tmp_path):
    # A dry-run is a validation gate: caching must not let a bad suite pass.
    _write_resources(tmp_path)
    (tmp_path / "failing.robot").write_text(FAILING_SUITE)
    plain = _run(tmp_path, "failing", dryrun=True, cache=False)
    cached = _run(tmp_path, "failing", dryrun=True, cache=True)
    assert plain.statuses == cached.statuses
    assert plain.returncode == cached.returncode
    assert cached.returncode != 0
    assert cached.statuses == {
        "Unknown Keyword Is Rejected": "FAIL",
        "Wrong Argument Count Is Rejected": "FAIL",
        "Valid Test Still Passes": "PASS",
    }
    # Self-validating in isolation: without this, the test would still pass if the
    # cache had never installed and both runs were plain.
    assert _cache_entries(tmp_path) > 0


def test_import_invalidates_cached_lookup(tmp_path):
    # A name cached as "not found" must not survive an import that defines it.
    _write_resources(tmp_path)
    (tmp_path / "invalidation.robot").write_text(INVALIDATION_SUITE)
    plain = _run(tmp_path, "invalidation", dryrun=True, cache=False)
    cached = _run(tmp_path, "invalidation", dryrun=True, cache=True)
    assert plain.statuses == cached.statuses
    assert cached.statuses == {
        "Lookup Before Import Fails": "FAIL",
        "Lookup After Import Succeeds": "PASS",
    }
    # Self-validating in isolation: an uninstalled cache has nothing to invalidate.
    assert _cache_entries(tmp_path) > 0


def test_library_import_invalidates_cached_lookup(tmp_path):
    # A name cached as "not found" must not survive a library import that defines it.
    _write_resources(tmp_path)
    (tmp_path / "library_invalidation.robot").write_text(LIBRARY_INVALIDATION_SUITE)
    plain = _run(tmp_path, "library_invalidation", dryrun=True, cache=False)
    cached = _run(tmp_path, "library_invalidation", dryrun=True, cache=True)
    assert plain.statuses == cached.statuses
    assert cached.statuses == {
        "Lookup Before Import Fails": "FAIL",
        "Lookup After Import Succeeds": "PASS",
    }
    assert _cache_entries(tmp_path) > 0


def test_real_run_unaffected_by_listener(tmp_path):
    # The listener must self-gate to dry-run: a real (non-dryrun) execution with
    # the listener loaded must behave exactly as without it, and never patch.
    _write_resources(tmp_path)
    (tmp_path / "passing.robot").write_text(PASSING_SUITE)
    plain = _run(tmp_path, "passing", dryrun=False, cache=False, expect_rc=0)
    cached = _run(tmp_path, "passing", dryrun=False, cache=True, expect_rc=0)
    assert plain.statuses == cached.statuses
    assert set(cached.statuses.values()) == {"PASS"}
    # No cache is installed outside a dry-run, so the probe must see nothing.
    assert _cache_entries(tmp_path) == 0


@pytest.mark.parametrize(
    ("version", "supported"),
    [
        ("7.4.1", True),
        ("7.4", True),
        ("7.4.1.1", True),
        # Only the diffed versions are supported; an unverified release must fall
        # back to uncached rather than be assumed compatible.
        ("7.5.0", False),
        ("8.0.0", False),
        ("7.3.2", False),
        ("not-a-version", False),
        # Pre-release and dev builds are not released versions, so they are
        # unsupported consistently -- whether or not their numeric prefix parses.
        ("7.4.0rc1", False),
        ("7.4rc1", False),
        ("7.4.1.dev0", False),
        ("8.0.0rc1", False),
    ],
)
def test_version_guard_rejects_unsupported_robot(version, supported, monkeypatch):
    # The patched bodies mirror RF's resolution pipeline, so a release outside the
    # verified range must fail safe to uncached rather than silently diverge.
    monkeypatch.setattr(rf_dryrun_cache, "_RF_VERSION", version)
    assert rf_dryrun_cache._rf_version_supported() is supported
