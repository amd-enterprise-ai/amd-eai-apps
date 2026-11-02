#!/usr/bin/env python3

# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Validate the vendored ai-workloads Helm charts after `wm init` has applied patches.

`git apply --3way` can report a failure while still writing conflict markers into the
working tree, and a chart carrying those markers is unparseable YAML that will only
surface at deploy time. This checks the patched tree directly so CI rejects it before
the image is built.
"""

import sys
from pathlib import Path

import yaml

CONFLICT_MARKERS = ("<<<<<<<", ">>>>>>>")


def _default_workloads_dir() -> Path:
    """Locate the vendored workloads checkout relative to this script."""
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "apps/api/workloads_manager/workloads_manager/data/ai-workloads"


def _find_conflict_markers(helm_files: list[Path]) -> list[str]:
    problems = []
    for path in helm_files:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Binary chart assets cannot carry textual conflict markers.
            continue
        except OSError as exc:
            problems.append(f"{path}: could not be read: {exc}")
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            if line.startswith(CONFLICT_MARKERS):
                problems.append(f"{path}:{line_number}: git conflict marker left by a failed patch")
    return problems


def _find_unparseable_yaml(workloads_dir: Path) -> tuple[list[str], int]:
    """Parse the chart files that must be valid YAML, for two different reasons.

    Helm templates are excluded on purpose: they carry Go templating and are not valid
    YAML on their own. Files under ``overrides/`` are ``yaml.safe_load``-ed at chart
    registration time, where a parse error is caught and replaced by a name guessed from
    the filename — so a patch that garbles one without leaving a conflict marker never
    surfaces at all, it just registers the wrong thing. ``values.yaml`` and ``Chart.yaml``
    are stored as raw text and never parsed by this app; they must still be valid YAML
    because Helm parses them at deploy time.
    """
    problems = []
    parsed_count = 0
    for pattern in (
        "workloads/*/helm/values.yaml",
        "workloads/*/helm/Chart.yaml",
        "workloads/*/helm/overrides/**/*.yaml",
        "workloads/*/helm/overrides/**/*.yml",
    ):
        for path in sorted(workloads_dir.glob(pattern)):
            parsed_count += 1
            try:
                yaml.safe_load(path.read_text(encoding="utf-8"))
            except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
                problems.append(f"{path}: unparseable YAML after patching: {exc}")
    return problems, parsed_count


def main() -> int:
    workloads_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_workloads_dir()

    if not workloads_dir.is_dir():
        print(f"❌ Workloads directory not found: {workloads_dir}", file=sys.stderr)
        return 1

    helm_files = [p for p in workloads_dir.glob("workloads/*/helm/**/*") if p.is_file()]
    if not helm_files:
        print(f"❌ No Helm chart files found under {workloads_dir}/workloads/*/helm", file=sys.stderr)
        return 1

    yaml_problems, yaml_parsed_count = _find_unparseable_yaml(workloads_dir)
    problems = _find_conflict_markers(helm_files) + yaml_problems

    if problems:
        print("❌ Patched workload charts are broken:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"✅ Patched workload charts are intact ({len(helm_files)} files checked, "
        f"{yaml_parsed_count} parsed as YAML)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
