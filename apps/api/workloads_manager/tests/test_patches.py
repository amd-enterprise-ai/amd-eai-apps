# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for patch creation, patch application, and the CLI exit behaviour that depends on them."""

import builtins
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest
from click.testing import CliRunner

from workloads_manager import config
from workloads_manager.cli import cli
from workloads_manager.core import patches
from workloads_manager.models.workload import WorkloadRegistrationResult

BASE_VALUES = "\n".join(f"key{i}: value{i}" for i in range(1, 11)) + "\n"


def _git(repo: Path, *args: str) -> str:
    """Run a git command in ``repo`` and return stdout, failing the test on error."""
    # Ignore the developer's own git config: settings such as commit.gpgsign or
    # core.autocrlf otherwise leak in and break these fixtures on some machines.
    isolated_env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    result = subprocess.run(
        ["git", "-c", "user.email=dev@example.com", "-c", "user.name=Test User", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=isolated_env,
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout


@pytest.fixture
def workloads_repo(tmp_path: Path) -> Path:
    """A git repository standing in for the vendored ai-workloads checkout."""
    repo = tmp_path / "ai-workloads"
    (repo / "workloads" / "demo" / "helm").mkdir(parents=True)
    (repo / "workloads" / "demo" / "helm" / "values.yaml").write_text(BASE_VALUES)
    _git(repo.parent, "init", "--quiet", str(repo))
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "Initial workloads")
    return repo


@pytest.fixture
def patches_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "patches"
    directory.mkdir()
    return directory


@pytest.fixture(autouse=True)
def configured_dirs(monkeypatch: pytest.MonkeyPatch, workloads_repo: Path, patches_dir: Path) -> None:
    """Point the patch machinery at the temporary repository and patch directory."""
    monkeypatch.setattr(config, "WORKLOADS_DIR", str(workloads_repo))
    monkeypatch.setattr(config, "PATCHES_DIR", str(patches_dir))


def _write_patch_from_working_tree(repo: Path, patches_dir: Path, name: str) -> Path:
    """Capture the current uncommitted changes as a patch, then restore the tree."""
    patch_file = patches_dir / f"{name}.patch"
    patch_file.write_text(_git(repo, "diff"))
    _git(repo, "checkout", "--", ".")
    return patch_file


@pytest.fixture
def values_file(workloads_repo: Path) -> Path:
    return workloads_repo / "workloads" / "demo" / "helm" / "values.yaml"


def test_patch_applying_cleanly_succeeds(workloads_repo: Path, patches_dir: Path, values_file: Path) -> None:
    values_file.write_text(BASE_VALUES.replace("value5", "patched"))
    _write_patch_from_working_tree(workloads_repo, patches_dir, "demo")

    results = patches.apply_patches()

    assert len(results) == 1
    assert results[0]["success"] is True
    assert results[0]["name"] == "demo"
    assert "patched" in values_file.read_text()


def test_conflicting_patch_fails_and_leaves_conflict_markers(
    workloads_repo: Path, patches_dir: Path, values_file: Path
) -> None:
    """A failed three-way merge still writes conflict markers into the chart.

    The markers are pinned deliberately: a non-zero result does not mean the tree was
    left untouched, so the caller must treat a failure as "this tree is unshippable"
    rather than "nothing happened".
    """
    values_file.write_text(BASE_VALUES.replace("value5", "from-patch"))
    _write_patch_from_working_tree(workloads_repo, patches_dir, "demo")

    # Upstream changes the same line, so the three-way merge cannot reconcile them.
    values_file.write_text(BASE_VALUES.replace("value5", "from-upstream"))
    _git(workloads_repo, "commit", "--quiet", "-am", "Upstream change")

    results = patches.apply_patches()

    assert len(results) == 1
    assert results[0]["success"] is False
    assert "<<<<<<<" in values_file.read_text()


def test_patch_without_three_way_fallback_fails(patches_dir: Path, values_file: Path) -> None:
    """A patch git cannot even attempt to merge is reported as a failure."""
    (patches_dir / "broken.patch").write_text(
        "--- a/workloads/demo/helm/values.yaml\n"
        "+++ b/workloads/demo/helm/values.yaml\n"
        "@@ -1,2 +1,2 @@\n"
        "-nonexistent: context\n"
        "+replacement: line\n"
        " trailing: context\n"
    )

    results = patches.apply_patches()

    assert len(results) == 1
    assert results[0]["success"] is False
    assert values_file.read_text() == BASE_VALUES


def test_missing_workloads_directory_is_reported(monkeypatch: pytest.MonkeyPatch, patches_dir: Path) -> None:
    (patches_dir / "demo.patch").write_text("")
    monkeypatch.setattr(config, "WORKLOADS_DIR", str(patches_dir / "does-not-exist"))

    results = patches.apply_patches()

    assert results == [{"name": "demo", "success": False, "message": "Missing directory or patch file"}]


def test_no_patches_available_returns_empty_list() -> None:
    assert patches.apply_patches() == []


def test_init_exits_non_zero_when_a_patch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "workloads_manager.core.repository.initialize",
        lambda force: {"success": True, "commit": "0123456789abcdef"},
    )
    monkeypatch.setattr(
        "workloads_manager.core.patches.apply_patches",
        lambda: [
            {"name": "ok", "success": True, "message": "Patch applied successfully"},
            {"name": "broken", "success": False, "message": "Patch failed to apply"},
        ],
    )

    result = CliRunner().invoke(cli, ["init"])

    assert result.exit_code == 1
    assert "broken" in result.output


def test_init_exits_zero_when_all_patches_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "workloads_manager.core.repository.initialize",
        lambda force: {"success": True, "commit": "0123456789abcdef"},
    )
    monkeypatch.setattr(
        "workloads_manager.core.patches.apply_patches",
        lambda: [{"name": "ok", "success": True, "message": "Patch applied successfully"}],
    )

    result = CliRunner().invoke(cli, ["init"])

    assert result.exit_code == 0


def test_register_exits_non_zero_when_a_patch_fails_during_auto_clone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "workloads_manager.core.repository.check_directories",
        lambda: {"workloads_repo_exists": False, "patches_dir_exists": True},
    )
    monkeypatch.setattr(
        "workloads_manager.core.repository.initialize",
        lambda force: {"success": True, "commit": "0123456789abcdef"},
    )
    monkeypatch.setattr(
        "workloads_manager.core.patches.apply_patches",
        lambda: [
            {"name": "ok", "success": True, "message": "Patch applied successfully"},
            {"name": "broken", "success": False, "message": "Patch failed to apply"},
        ],
    )
    # Sentinel: reaching workload discovery means the patch failure did not stop the
    # command. Without it the test passes either way, because an unrelated exit(1)
    # further down ("no registerable workloads") produces the same exit code.
    monkeypatch.setattr(
        "workloads_manager.cli.get_registerable_workloads",
        lambda: pytest.fail("registration must not proceed after a failed patch"),
    )

    result = CliRunner().invoke(cli, ["register", "all", "--yes"])

    assert result.exit_code == 1
    assert "broken" in result.output


def test_register_exits_non_zero_when_the_auto_clone_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "workloads_manager.core.repository.check_directories",
        lambda: {"workloads_repo_exists": False, "patches_dir_exists": True},
    )
    monkeypatch.setattr(
        "workloads_manager.core.repository.initialize",
        lambda force: {"success": False, "message": "Failed to clone repository"},
    )
    monkeypatch.setattr(
        "workloads_manager.core.patches.apply_patches",
        lambda: pytest.fail("patches must not be applied on top of a failed clone"),
    )

    result = CliRunner().invoke(cli, ["register", "all", "--yes"])

    assert result.exit_code == 1
    assert "Failed to clone repository" in result.output


@pytest.mark.parametrize(
    ("registration_succeeds", "expected_exit_code"),
    [(True, 0), (False, 1)],
)
def test_register_all_exit_code_reflects_whether_every_workload_registered(
    monkeypatch: pytest.MonkeyPatch, registration_succeeds: bool, expected_exit_code: int
) -> None:
    """A partial rollout must not look like a finished one to an automated caller."""
    monkeypatch.setattr(
        "workloads_manager.core.repository.check_directories",
        lambda: {"workloads_repo_exists": True, "patches_dir_exists": True},
    )
    monkeypatch.setattr(
        "workloads_manager.cli.get_registerable_workloads",
        lambda: [SimpleNamespace(dir_name="demo", type="workload", chart_name="demo-chart")],
    )
    monkeypatch.setattr(
        "workloads_manager.core.registration.register_workload",
        lambda name, url: WorkloadRegistrationResult(
            success=registration_succeeds, error=None if registration_succeeds else "Upload rejected"
        ),
    )

    result = CliRunner().invoke(cli, ["register", "all", "--yes"])

    assert result.exit_code == expected_exit_code


def _git_output(*outputs: str) -> Any:
    """Return a subprocess.run stub yielding the given stdout values in order."""
    remaining = list(outputs)

    def _run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=remaining.pop(0), stderr="")

    return _run


def test_create_patch_leaves_no_file_when_there_are_no_changes(patches_dir: Path) -> None:
    """An empty diff must not leave a zero-byte patch behind."""
    with mock.patch("workloads_manager.core.patches.subprocess.run", side_effect=_git_output("", "")):
        result = patches.create_patch("test-workload")

    assert not result["success"]
    assert result["error"] == "No changes to create patch"
    assert list(patches_dir.glob("*.patch")) == []


def test_create_patch_leaves_no_file_when_writing_fails(patches_dir: Path, workloads_repo: Path) -> None:
    """A write failure must not leave a truncated patch behind.

    A partially written patch is non-empty, so nothing downstream can tell it apart
    from a valid one - it has to be removed at the point of failure.
    """
    real_open = builtins.open
    patch_file = patches_dir / "test-workload.patch"
    (workloads_repo / "new.txt").write_text("added\n")
    writes = 0

    def _open_failing_after_first_write(file: Any, *args: Any, **kwargs: Any) -> Any:
        handle = real_open(file, *args, **kwargs)
        if Path(file) != patch_file:
            return handle

        original_write = handle.write

        def _write(data: str) -> int:
            nonlocal writes
            writes += 1
            if writes > 1:
                raise OSError("disk full")
            return original_write(data)

        handle.write = _write  # type: ignore[method-assign]
        return handle

    with (
        mock.patch(
            "workloads_manager.core.patches.subprocess.run",
            side_effect=_git_output("diff --git a/workloads/test-workload/x b/workloads/test-workload/x\n", "new.txt"),
        ),
        mock.patch("builtins.open", side_effect=_open_failing_after_first_write),
    ):
        result = patches.create_patch("test-workload")

    # Guards the premise of this test: the failure has to land after an earlier write
    # already put bytes on disk, otherwise it exercises the empty-diff branch instead.
    assert writes > 1

    assert not result["success"]
    assert "disk full" in result["error"]
    assert list(patches_dir.glob("*.patch")) == []


def test_create_patch_keeps_existing_patch_when_git_fails(patches_dir: Path) -> None:
    """A failure before the destination is opened must not discard a valid patch.

    The patch path is known before any work starts, so cleanup that ignores whether
    this run actually wrote anything would delete a previously created patch.
    """
    existing = patches_dir / "test-workload.patch"
    existing.write_text("diff --git a/x b/x\n")

    with mock.patch("workloads_manager.core.patches.subprocess.run", side_effect=OSError("git missing")):
        result = patches.create_patch("test-workload")

    assert not result["success"]
    assert "git missing" in result["error"]
    assert existing.exists()
    assert existing.read_text() == "diff --git a/x b/x\n"
