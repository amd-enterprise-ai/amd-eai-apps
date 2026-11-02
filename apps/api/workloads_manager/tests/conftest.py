# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Shared pytest fixtures for all tests."""

import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import git
import pytest
import yaml

from workloads_manager import config

COPYRIGHT_HEADER = "# Copyright © Advanced Micro Devices, Inc., or its affiliates.\n#\n# SPDX-License-Identifier: MIT\n"


def _commit(repo: git.Repo, filename: str, message: str) -> str:
    """Add a file and commit it, returning the new commit hash."""
    file_path = Path(repo.working_dir) / filename
    file_path.write_text(f"{message}\n")
    repo.index.add([filename])
    return repo.index.commit(message).hexsha


@pytest.fixture
def workloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set up a throwaway remote repository with a pinned commit behind main's tip.

    Returns the pinned commit and main's tip so tests can assert which one was
    checked out. The pin is the first of two commits, so a fallback to main is
    always observable.
    """
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    remote = git.Repo.init(remote_dir, initial_branch="main")
    remote.config_writer().set_value("user", "name", "Test User").release()
    remote.config_writer().set_value("user", "email", "test@example.com").release()

    pinned_commit = _commit(remote, "first.txt", "first")
    main_tip = _commit(remote, "second.txt", "second")

    package_dir = tmp_path / "package"
    package_dir.mkdir()
    (package_dir / "PATCHED_VERSION").write_text(f"{COPYRIGHT_HEADER}\n{pinned_commit}\n", encoding="utf-8")

    monkeypatch.setattr(config, "WORKLOADS_REPO", str(remote_dir))
    monkeypatch.setattr(config, "WORKLOADS_DIR", str(tmp_path / "ai-workloads"))
    monkeypatch.setattr(config, "PACKAGE_DIR", package_dir)
    monkeypatch.setattr(config, "MAIN_BRANCH", "main")

    return {"pinned_commit": pinned_commit, "main_tip": main_tip, "package_dir": str(package_dir)}


@pytest.fixture
def temp_yaml_file(tmp_path: Path) -> Iterator[Callable[[dict[str, object]], Path]]:
    """Create a temporary YAML file."""

    def _create_temp_yaml(content_dict: dict[str, object]) -> Path:
        with tempfile.NamedTemporaryFile(dir=tmp_path, mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(content_dict, f)
            temp_file = Path(f.name)
            return temp_file

    yield _create_temp_yaml
