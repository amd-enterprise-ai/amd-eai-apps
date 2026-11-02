# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Repository management functionality."""

import re
import shutil
from pathlib import Path
from typing import Any

import git
from loguru import logger
from rich.markup import escape

from .. import config

_COMMIT_HASH_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")


class WorkloadsPinError(Exception):
    """The pinned ai-workloads commit could not be determined or checked out."""


def _reset_repo_to_clean_state(repo: git.Repo) -> None:
    """Reset repository to clean state by removing all local changes."""
    repo.git.reset("--hard")
    repo.git.clean("-fdx")


def _get_patched_version() -> str:
    """Get the target commit hash from the PATCHED_VERSION file.

    There is deliberately no fallback: any real ref used as a default is
    indistinguishable from a valid pin, so downstream patching and image builds
    would silently run against the wrong tree.
    """
    patched_version_file = Path(config.PACKAGE_DIR) / "PATCHED_VERSION"
    try:
        # The encoding is pinned rather than taken from the locale so that whether a
        # pin file decodes at all does not depend on the environment the CLI runs in.
        content = patched_version_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        # UnicodeDecodeError is a ValueError, not an OSError, so it needs naming
        # explicitly or a corrupted pin file escapes this function unwrapped and
        # collapses the whole of get_repo_status() instead of one status line.
        raise WorkloadsPinError(f"Could not read PATCHED_VERSION file {patched_version_file}: {e}") from e

    hashes = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
    if not hashes:
        raise WorkloadsPinError(f"PATCHED_VERSION file {patched_version_file} contains no commit hash")

    commit = hashes[-1]
    if not _COMMIT_HASH_PATTERN.match(commit):
        raise WorkloadsPinError(f"PATCHED_VERSION file {patched_version_file} contains '{commit}', not a commit hash")
    return commit


def initialize(force: bool = False) -> dict[str, Any]:
    """Ensure the repository exists and is checked out at the pinned commit.

    The repository is cloned if it is missing and reset if it already exists, then
    moved to the commit recorded in PATCHED_VERSION. A pin that cannot be read,
    parsed or checked out reports success=False rather than settling for another
    commit, because the vendored patches are only meaningful against the pin.
    """
    workloads_dir = Path(config.WORKLOADS_DIR)

    try:
        workloads_dir.parent.mkdir(parents=True, exist_ok=True)

        if force and workloads_dir.exists():
            shutil.rmtree(workloads_dir)

        if not workloads_dir.exists():
            repo = git.Repo.clone_from(config.WORKLOADS_REPO, workloads_dir, branch=config.MAIN_BRANCH)
        else:
            repo = git.Repo(workloads_dir)
            _reset_repo_to_clean_state(repo)

        checkout_commit = _get_patched_version()
        try:
            logger.info(f"Checking out commit {checkout_commit}")
            repo.git.checkout(checkout_commit)
        except git.GitCommandError as e:
            raise WorkloadsPinError(f"Pinned workloads commit {checkout_commit} could not be checked out") from e

        return {
            "success": True,
            "message": "Repository initialized",
            "commit": repo.head.commit.hexsha,
            "commit_message": repo.head.commit.message.strip(),
        }

    except Exception as e:
        return {"success": False, "message": f"Failed to initialize repository: {str(e)}"}


def update_repo() -> dict[str, Any]:
    """Update the repository by pulling latest changes.

    This function pulls the latest changes from the remote repository
    and returns information about the updates.
    """
    workloads_dir = Path(config.WORKLOADS_DIR)

    if not workloads_dir.exists():
        return {"success": False, "message": f"Repository not found at {workloads_dir}. Run 'wm init' first."}

    try:
        repo = git.Repo(workloads_dir)
        # Store current commit before pull
        old_commit = repo.head.commit.hexsha
        old_commit_message = repo.head.commit.message.strip()

        # Pull latest changes
        if repo.is_dirty(untracked_files=True):
            _reset_repo_to_clean_state(repo)
        repo.git.checkout(config.MAIN_BRANCH)
        repo.git.pull("origin", config.MAIN_BRANCH)

        # Get new commit info
        new_commit = repo.head.commit.hexsha
        new_commit_message = repo.head.commit.message.strip()
        updated = old_commit != new_commit
        patched_version_file = Path(config.PACKAGE_DIR) / "PATCHED_VERSION"
        if patched_version_file.exists():
            # Keep copyright header if it exists
            lines = patched_version_file.read_text(encoding="utf-8").splitlines()
            copyright_header = "\n".join(line for line in lines if line.startswith("#"))
            if copyright_header:
                patched_version_file.write_text(f"{copyright_header}\n\n{new_commit}\n", encoding="utf-8")
            else:
                patched_version_file.write_text(new_commit + "\n", encoding="utf-8")
        else:
            patched_version_file.write_text(new_commit + "\n", encoding="utf-8")
        logger.info(f"Updated PATCHED_VERSION to {new_commit}")

        # Get commit log if updated
        if updated:
            # Get the log of commits between old and new
            log_output = repo.git.log(f"{old_commit}..{new_commit}", "--pretty=format:%h %s", "--no-merges")
            commit_log = log_output if log_output else ""
            message = f"Repository updated successfully. PATCHED_VERSION updated to {new_commit}"
        else:
            message = "Repository already up to date"
            commit_log = ""

        return {
            "success": True,
            "message": message,
            "old_commit": old_commit,
            "old_commit_message": old_commit_message,
            "commit": new_commit,
            "commit_message": new_commit_message,
            "updated": updated,
            "commit_log": commit_log,
        }

    except Exception as e:
        return {"success": False, "message": f"Failed to update repository: {str(e)}", "updated": False}


def check_directories() -> dict[str, Any]:
    """Check if the workloads and patches directories exist."""
    workloads_dir = Path(config.WORKLOADS_DIR)
    patches_dir = Path(config.PATCHES_DIR)

    return {
        "workloads_repo_exists": workloads_dir.exists(),
        "patches_dir_exists": patches_dir.exists(),
    }


def get_repo_status() -> dict[str, Any]:
    """Get the current status of the repository.

    Returns:
        Dict with status information including branch, commit, and commit message.
        If there's an error, returns a dict with an 'error' key.
    """
    workloads_dir = Path(config.WORKLOADS_DIR)

    try:
        if not workloads_dir.exists() or not (workloads_dir / ".git").exists():
            return {"error": "Repository not initialized"}

        repo = git.Repo(workloads_dir)

        # Check if we're in detached HEAD state
        try:
            branch_name = repo.active_branch.name
            is_detached = False
        except TypeError:
            # We're in detached HEAD state
            branch_name = None
            is_detached = True

        current_commit = repo.head.commit.hexsha
        try:
            patched_version = _get_patched_version()
        except WorkloadsPinError as e:
            # The message quotes PATCHED_VERSION's contents, so it must be escaped:
            # an unescaped "[/]" in that file makes rich raise MarkupError when the
            # caller prints this line, losing the status output entirely.
            version_status = f" [bold yellow]- {escape(str(e))}[/]"
        else:
            if current_commit != patched_version:
                version_status = f" [bold yellow]- does not match latest patched version {patched_version[:8]}. Update PATCHED_VERSION file[/]"
            else:
                version_status = " [bold green]- matches latest patched version[/bold green]"

        return {
            "branch": branch_name,
            "commit": current_commit[:8] + version_status,
            "commit_message": repo.head.commit.message.strip(),
            "is_dirty": repo.is_dirty(),
            "untracked_files": repo.untracked_files,
            "is_detached": is_detached,
        }

    except Exception as e:
        logger.error(f"Error getting repository status: {e}")
        return {"error": str(e)}
