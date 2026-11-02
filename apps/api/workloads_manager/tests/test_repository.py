# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for repository initialization and status reporting."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from rich.console import Console

from tests.conftest import COPYRIGHT_HEADER
from workloads_manager.core import repository

# Reads the pin directly rather than through initialize(), because the rest of that
# function needs a git remote that cannot be built inside a one-line -c program.
_READ_PIN_PROBE = (
    "import sys;"
    "from workloads_manager import config;"
    "from workloads_manager.core import repository;"
    "config.PACKAGE_DIR = sys.argv[1];"
    "print(repository._get_patched_version())"
)


def _write_patched_version(workloads: dict[str, str], content: str) -> Path:
    patched_version_file = Path(workloads["package_dir"]) / "PATCHED_VERSION"
    # Pinned so the suite exercises the same encoding regardless of the runner's locale.
    patched_version_file.write_text(content, encoding="utf-8")
    return patched_version_file


def test_initialize_checks_out_the_pinned_commit(workloads: dict[str, str]) -> None:
    """The pinned commit is checked out, not main's tip."""
    result = repository.initialize()

    assert result["success"] is True
    assert result["commit"] == workloads["pinned_commit"]
    assert result["commit"] != workloads["main_tip"]


def test_initialize_ignores_a_comment_written_after_the_pin(workloads: dict[str, str]) -> None:
    """Comments are ignored wherever they appear, not only in the leading header."""
    _write_patched_version(workloads, f"{COPYRIGHT_HEADER}\n{workloads['pinned_commit']}\n# a trailing note\n")

    result = repository.initialize()

    assert result["success"] is True
    assert result["commit"] == workloads["pinned_commit"]


def test_initialize_ignores_a_blank_line_written_after_the_pin(workloads: dict[str, str]) -> None:
    """Trailing blank lines do not shadow the pin."""
    _write_patched_version(workloads, f"{COPYRIGHT_HEADER}\n{workloads['pinned_commit']}\n\n\n")

    result = repository.initialize()

    assert result["success"] is True
    assert result["commit"] == workloads["pinned_commit"]


def test_initialize_ignores_an_indented_comment_written_after_the_pin(workloads: dict[str, str]) -> None:
    """A comment is a comment wherever it starts, not only at column zero."""
    _write_patched_version(workloads, f"{COPYRIGHT_HEADER}\n{workloads['pinned_commit']}\n  # an indented note\n")

    result = repository.initialize()

    assert result["success"] is True
    assert result["commit"] == workloads["pinned_commit"]


def test_initialize_tolerates_whitespace_around_the_pin(workloads: dict[str, str]) -> None:
    """A pin padded with whitespace is still a pin, not a malformed hash."""
    _write_patched_version(workloads, f"{COPYRIGHT_HEADER}\n   {workloads['pinned_commit']}   \n")

    result = repository.initialize()

    assert result["success"] is True
    assert result["commit"] == workloads["pinned_commit"]


def test_initialize_uses_the_last_pin_when_the_file_lists_several(workloads: dict[str, str]) -> None:
    """An appended pin supersedes the ones above it, so a stale line cannot win."""
    _write_patched_version(workloads, f"{COPYRIGHT_HEADER}\n{workloads['main_tip']}\n{workloads['pinned_commit']}\n")

    result = repository.initialize()

    assert result["success"] is True
    assert result["commit"] == workloads["pinned_commit"]
    assert result["commit"] != workloads["main_tip"]


def test_initialize_fails_when_pinned_commit_is_unreachable(workloads: dict[str, str]) -> None:
    """An unreachable pin fails loudly instead of silently using main."""
    unreachable = "0123456789abcdef0123456789abcdef01234567"
    _write_patched_version(workloads, f"{COPYRIGHT_HEADER}\n{unreachable}\n")

    result = repository.initialize()

    assert result["success"] is False
    assert unreachable in result["message"]
    # git's own error text also quotes the hash, so only the wrapper's own words
    # distinguish "we refused to fall back" from "the raw error leaked out".
    assert "could not be checked out" in result["message"]


def test_initialize_does_not_report_a_commit_on_failure(workloads: dict[str, str]) -> None:
    """A failed initialization must not hand callers a plausible but wrong commit."""
    _write_patched_version(workloads, f"{COPYRIGHT_HEADER}\n0123456789abcdef0123456789abcdef01234567\n")

    result = repository.initialize()

    assert result["success"] is False
    assert "commit" not in result


def test_initialize_fails_when_patched_version_file_is_missing(workloads: dict[str, str]) -> None:
    """A missing pin file is an error, not a licence to use main."""
    (Path(workloads["package_dir"]) / "PATCHED_VERSION").unlink()

    result = repository.initialize()

    assert result["success"] is False
    # FileNotFoundError already quotes the path, so assert the wrapper's own words:
    # without them the test passes even with the read guard deleted entirely.
    assert "Could not read PATCHED_VERSION file" in result["message"]


def test_initialize_fails_when_patched_version_file_is_empty(workloads: dict[str, str]) -> None:
    """An empty pin file reports what is wrong rather than an indexing error."""
    _write_patched_version(workloads, "")

    result = repository.initialize()

    assert result["success"] is False
    assert "contains no commit hash" in result["message"]
    assert "list index out of range" not in result["message"]


def test_initialize_fails_when_patched_version_has_only_comments(workloads: dict[str, str]) -> None:
    """A pin file left with only its copyright header is an error."""
    _write_patched_version(workloads, COPYRIGHT_HEADER)

    result = repository.initialize()

    assert result["success"] is False
    assert "PATCHED_VERSION" in result["message"]
    assert "contains no commit hash" in result["message"]


def test_initialize_fails_when_patched_version_is_whitespace_only(workloads: dict[str, str]) -> None:
    """Blank lines do not count as a pin."""
    _write_patched_version(workloads, "   \n\n")

    result = repository.initialize()

    assert result["success"] is False
    assert "PATCHED_VERSION" in result["message"]
    assert "contains no commit hash" in result["message"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
def test_initialize_fails_when_patched_version_is_unreadable(workloads: dict[str, str]) -> None:
    """An unreadable pin file names the path it could not read."""
    patched_version_file = _write_patched_version(workloads, f"{COPYRIGHT_HEADER}\n{workloads['pinned_commit']}\n")
    patched_version_file.chmod(0o000)

    try:
        result = repository.initialize()
    finally:
        patched_version_file.chmod(0o644)

    assert result["success"] is False
    assert str(patched_version_file) in result["message"]
    # PermissionError already quotes the path; only the wrapper's own words prove
    # the read guard ran rather than the raw error reaching the generic handler.
    assert "Could not read PATCHED_VERSION file" in result["message"]


def test_initialize_fails_when_patched_version_is_not_utf8(workloads: dict[str, str]) -> None:
    """A corrupted pin file is a pin error, not an unhandled decode error."""
    patched_version_file = Path(workloads["package_dir"]) / "PATCHED_VERSION"
    patched_version_file.write_bytes(b"# header\n\xff\xfe\xfd\n")

    result = repository.initialize()

    assert result["success"] is False
    assert "Could not read PATCHED_VERSION file" in result["message"]


def test_patched_version_is_read_as_utf8_regardless_of_the_locale(tmp_path: Path) -> None:
    """A valid pin file must read the same everywhere, not only where the locale is UTF-8."""
    pin = "0123456789abcdef0123456789abcdef01234567"
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    # The copyright header carries a non-ASCII character, so a read that falls back
    # to an ASCII locale rejects a pin file that is perfectly valid.
    (package_dir / "PATCHED_VERSION").write_text(f"{COPYRIGHT_HEADER}\n{pin}\n", encoding="utf-8")

    # Only a subprocess can observe this: the interpreter resolves its default text
    # encoding once at startup, so the ambient locale cannot be changed from inside
    # a running test, and in a UTF-8 environment an unpinned read passes either way.
    env = {
        **os.environ,
        "LC_ALL": "C",
        "LANG": "C",
        # Left unset, CPython coerces the C locale to C.UTF-8 and enables UTF-8 mode,
        # which would restore the very default this test exists to remove.
        "PYTHONCOERCECLOCALE": "0",
        "PYTHONUTF8": "0",
    }
    probe = subprocess.run(
        [sys.executable, "-c", _READ_PIN_PROBE, str(package_dir)],
        capture_output=True,
        text=True,
        env=env,
    )

    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == pin


@pytest.mark.parametrize(
    "pin",
    [
        "not-a-commit-hash",
        # Too short to identify one commit: git would resolve it to whatever it
        # happens to abbreviate today, which is the silently-wrong-tree failure
        # this pin exists to prevent.
        "abc12",
        # Opens with hash-like characters, so a pattern that matched a prefix
        # rather than the whole line would accept it and hand git a bad ref.
        "1234567-not-a-hash",
    ],
)
def test_initialize_fails_when_patched_version_is_not_a_hash(workloads: dict[str, str], pin: str) -> None:
    """A pin that is not a commit hash is reported with the offending value."""
    _write_patched_version(workloads, f"{COPYRIGHT_HEADER}\n{pin}\n")

    result = repository.initialize()

    assert result["success"] is False
    assert pin in result["message"]
    # Distinguishes the pin-format diagnostic from git's opaque pathspec failure.
    assert "not a commit hash" in result["message"]


def test_status_reports_an_invalid_pin_without_losing_git_status(workloads: dict[str, str]) -> None:
    """A broken pin file degrades the version line only, not the whole git status."""
    assert repository.initialize()["success"] is True
    _write_patched_version(workloads, COPYRIGHT_HEADER)

    status = repository.get_repo_status()

    assert "error" not in status
    assert "branch" in status
    assert status["commit"].startswith(workloads["pinned_commit"][:8])
    # The path alone appears in every pin error, so name the specific diagnostic.
    assert "contains no commit hash" in status["commit"]


def test_status_reports_a_corrupted_pin_without_losing_git_status(workloads: dict[str, str]) -> None:
    """A pin file that is not even decodable still degrades only the version line."""
    assert repository.initialize()["success"] is True
    (Path(workloads["package_dir"]) / "PATCHED_VERSION").write_bytes(b"# header\n\xff\xfe\xfd\n")

    status = repository.get_repo_status()

    assert "error" not in status
    assert status["commit"].startswith(workloads["pinned_commit"][:8])
    assert "Could not read PATCHED_VERSION file" in status["commit"]


def test_status_survives_rich_markup_in_the_pin_file(workloads: dict[str, str]) -> None:
    """The status line quotes the pin file, so its contents must not be able to break rendering."""
    _write_patched_version(workloads, f"{COPYRIGHT_HEADER}\n{workloads['pinned_commit']}\n")
    assert repository.initialize()["success"] is True
    _write_patched_version(workloads, f"{COPYRIGHT_HEADER}\nnot-a-hash[/][bold red]\n")

    status = repository.get_repo_status()

    console = Console(width=200)
    with console.capture() as rendered:
        console.print(f"  Commit: {status['commit']}")

    # The pin file's contents survive verbatim, so the tags it contains were never
    # treated as markup: they can neither restyle the line nor vanish from a
    # diagnostic whose whole job is to quote what the file actually says.
    assert "not-a-hash[/][bold red]" in rendered.get()
    # ...while the status line's own markup is still markup. Escaping the whole
    # line instead of just the message would satisfy the assertion above and
    # silently turn the highlighting into literal text.
    assert "[bold yellow]" not in rendered.get()


def test_status_reports_a_matching_pin(workloads: dict[str, str]) -> None:
    """The common case: the checked-out commit is the pinned one."""
    assert repository.initialize()["success"] is True

    status = repository.get_repo_status()

    assert "matches latest patched version" in status["commit"]
    assert "does not match" not in status["commit"]


def test_status_reports_a_pin_that_moved_ahead_of_the_checkout(workloads: dict[str, str]) -> None:
    """A pin bumped since the last init is reported as a mismatch, naming the new pin."""
    assert repository.initialize()["success"] is True
    _write_patched_version(workloads, f"{COPYRIGHT_HEADER}\n{workloads['main_tip']}\n")

    status = repository.get_repo_status()

    assert "does not match latest patched version" in status["commit"]
    assert workloads["main_tip"][:8] in status["commit"]
