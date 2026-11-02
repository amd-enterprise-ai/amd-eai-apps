#!/usr/bin/env python3
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
"""Go module discovery shared by the two OSS compliance generators.

The SBOM and the third-party notices have to describe the same set of modules. Held in one place
rather than copied into both generators, because two copies that drift produce exactly the defect
these generators exist to avoid: one legal disclosure listing a service the other one omits.

Importable with a plain `import _oss_shared` from either generator regardless of the working
directory, because Python puts the directory of the script being run at the front of sys.path.
"""

import os
import subprocess
from pathlib import Path, PurePosixPath

# A go.mod under either of these is not part of any build the Go toolchain performs, so it is not a
# module this repository ships.
GO_EXCLUDED_DIRS = frozenset({"vendor", "testdata"})

# Variables through which the environment can name a repository. Git honours them ahead of the
# working directory, so any query meant to be about a particular tree has to unset them first.
GIT_LOCATION_ENV = frozenset({"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"})


def git_env() -> dict[str, str]:
    """The ambient environment with any repository location removed from it."""
    return {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_ENV}


def discover_go_subprojects(repo_root: Path) -> list[Path]:
    """Every tracked Go module directory, sorted.

    Discovered rather than listed because a service whose dependencies are missing from the
    disclosures is a licensing defect that nothing else in the pipeline notices. Enumerated through
    git rather than a filesystem walk so an untracked scratch checkout sitting in the tree can never
    contribute dependencies to a legal disclosure.

    GIT_DIR and friends are dropped because they outrank `cwd`: inherited from a git hook or a
    wrapper script, they would silently point the query at a different repository than the one
    being described.
    """
    result = subprocess.run(
        ["git", "ls-files", "--", "*/go.mod", "go.mod"],
        cwd=repo_root, env=git_env(), capture_output=True, text=True, check=True,
    )
    return sorted(
        repo_root / parent
        for line in result.stdout.splitlines()
        if GO_EXCLUDED_DIRS.isdisjoint((parent := PurePosixPath(line).parent).parts)
    )
