# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Patches management functionality."""

import os
import subprocess
from pathlib import Path
from typing import Any

from .. import config


def get_available_patches() -> list[str]:
    """Get list of available patch names (without .patch extension)."""
    patches_dir = Path(config.PATCHES_DIR)

    if not patches_dir.exists():
        return []

    return [patch_file.stem for patch_file in patches_dir.glob("*.patch") if patch_file.is_file()]


def apply_patches() -> list[dict[str, Any]]:
    """Apply all available patches and return detailed results."""
    patches_dir = Path(config.PATCHES_DIR)
    workloads_dir = Path(config.WORKLOADS_DIR)
    available_patches = get_available_patches()

    if not available_patches:
        return []

    results = []
    for patch_name in available_patches:
        patch_file = patches_dir / f"{patch_name}.patch"

        if not workloads_dir.exists() or not patch_file.exists():
            results.append({"name": patch_name, "success": False, "message": "Missing directory or patch file"})
            continue

        try:
            # The patches are relative to the workloads directory, so we apply them there
            command = ["git", "apply", "--3way", "--ignore-whitespace", "-p1", str(patch_file)]
            process = subprocess.run(
                command,
                cwd=str(workloads_dir),
                capture_output=True,
                text=True,
            )

            success = process.returncode == 0
            message = (
                process.stdout if success else f"{' '.join(command)}:\n{process.stderr}" or "Patch failed to apply"
            )

            results.append(
                {
                    "name": patch_name,
                    "success": success,
                    "message": message or ("Patch applied successfully" if success else "Patch failed to apply"),
                }
            )

        except Exception as e:
            results.append({"name": patch_name, "success": False, "message": f"Error: {str(e)}"})

    return results


def create_patch(workload_name: str) -> dict[str, Any]:
    """Create a patch for a workload's changes."""
    patches_dir = Path(config.PATCHES_DIR)
    workloads_dir = Path(config.WORKLOADS_DIR)
    workload_path = f"workloads/{workload_name}"
    patch_file = patches_dir / f"{workload_name}.patch"

    # Create patches directory if it doesn't exist
    patches_dir.mkdir(parents=True, exist_ok=True)

    destination_opened = False

    try:
        # Get all tracked changes
        tracked_changes = subprocess.run(
            ["git", "diff", config.MAIN_BRANCH, workload_path],
            cwd=str(workloads_dir),
            capture_output=True,
            text=True,
        ).stdout

        # Get list of untracked files
        untracked_files = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", workload_path],
            cwd=str(workloads_dir),
            capture_output=True,
            text=True,
        ).stdout.splitlines()

        # Write the patch file
        with open(patch_file, "w") as f:
            destination_opened = True

            # Write tracked changes
            f.write(tracked_changes)

            # Process untracked files
            for file_path in untracked_files:
                if not file_path.strip():
                    continue

                full_path = os.path.join(workloads_dir, file_path)
                if not os.path.isfile(full_path):
                    continue

                try:
                    with open(full_path) as content_file:
                        content = content_file.read()

                    # Write patch header for this file
                    lines = content.splitlines()
                    f.write(f"diff --git a/{file_path} b/{file_path}\n")
                    f.write("new file mode 100644\n")
                    f.write("--- /dev/null\n")
                    f.write(f"+++ b/{file_path}\n")
                    f.write(f"@@ -0,0 +1,{len(lines)} @@\n")

                    # Write file content with + prefix
                    for line in lines:
                        f.write(f"+{line}\n")
                except UnicodeDecodeError:
                    # Skip binary files
                    pass

        # Check if the patch file has content
        if os.path.getsize(patch_file) == 0:
            # A failed run must not leave a file behind: README instructs committing
            # patches with a `*.patch` glob, which would sweep up an unusable artifact.
            patch_file.unlink(missing_ok=True)
            return {"name": workload_name, "success": False, "error": "No changes to create patch"}

        return {"name": workload_name, "success": True, "patch_file": str(patch_file)}
    except Exception as e:
        # A partially written patch is worse than none: it is non-empty, so it passes
        # every size heuristic downstream while being a corrupt, unappliable diff. Only
        # discard what this run truncated, though - a git call raising before the
        # destination was opened leaves an earlier, still-valid patch untouched.
        if destination_opened:
            patch_file.unlink(missing_ok=True)
        return {"name": workload_name, "success": False, "error": f"Error creating patch: {str(e)}"}
