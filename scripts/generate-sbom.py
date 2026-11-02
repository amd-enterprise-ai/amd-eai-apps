#!/usr/bin/env python3
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
"""Generate a merged CycloneDX SBOM for AMD AI Workbench.

Runs cdxgen against each Python subproject, the Node.js UI workspace and every
tracked Go module, then merges all components into a single sbom.json at the repo root.

Usage:
    python3 scripts/generate-sbom.py
    # or from any directory:
    python3 /path/to/core/scripts/generate-sbom.py
"""

import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from _oss_shared import discover_go_subprojects, git_env

REPO_ROOT = Path(__file__).parent.parent.resolve()

# Enumerated rather than discovered, unlike the Go modules. `git ls-files '*/pyproject.toml'` finds
# twice this many projects, but the other four are Robot Framework spec environments and test
# tooling — none of them ship, so none of their dependencies belong in a legal disclosure. This
# list is therefore a curated shipped-set and has to be extended by hand when a new shipped Python
# service lands.
PYTHON_SUBPROJECTS = [
    REPO_ROOT / "apps/api/aiwb",
    REPO_ROOT / "apps/api/airm",
    REPO_ROOT / "apps/api/api_common",
    REPO_ROOT / "apps/api/workloads_manager",
]

NODE_WORKSPACE = REPO_ROOT / "apps/ui"

# Packages that are part of this repo — exclude from the SBOM.
FIRST_PARTY = {
    "aiwb-api", "airm-api", "api-common", "api_common",
    "workloads-manager", "workloads_manager", "aiwb_api", "airm_api",
    "amdenterpriseai-ui", "aiwb-ui", "airm-ui",
    "@amdenterpriseai/assets", "@amdenterpriseai/components",
    "@amdenterpriseai/hooks", "@amdenterpriseai/layouts",
    "@amdenterpriseai/types", "@amdenterpriseai/utils",
    "@amdenterpriseai/tailwind-config",
}

FIRST_PARTY_PREFIXES = ("github.com/silogen",)

MANUAL_COMPONENTS: list[dict] = []

SPEC_VERSION = "1.7"
OUTPUT_FILE = REPO_ROOT / "sbom.json"


CDXGEN_VERSION = "12.4.1"


def require_cdxgen() -> str:
    path = shutil.which("cdxgen") or shutil.which("npx")
    if path is None:
        sys.exit("cdxgen (or npx) not found. Install Node.js and run: pnpm add -g @cyclonedx/cdxgen")
    return path


def run_cdxgen(cdxgen: str, project_dir: Path, project_type: str, tmp_out: Path) -> dict:
    cmd = (
        [cdxgen, f"@cyclonedx/cdxgen@{CDXGEN_VERSION}"] if Path(cdxgen).stem in {"npx", "npx.cmd"} else [cdxgen]
    ) + [
        "--type", project_type,
        "--output", str(tmp_out),
        "--spec-version", SPEC_VERSION,
        "--no-recurse",
        "--fail-on-error",
    ]
    print(f"  Running cdxgen ({project_type}) in {project_dir.relative_to(REPO_ROOT)} ...", flush=True)
    result = subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(
            f"cdxgen failed for {project_dir.relative_to(REPO_ROOT)} "
            f"(exit {result.returncode}):\n{result.stderr[-500:]}"
        )
    if not tmp_out.exists():
        sys.exit(f"cdxgen produced no output for {project_dir.relative_to(REPO_ROOT)}")
    return json.loads(tmp_out.read_text())


def collect_components(sbom: dict, seen_purls: set[str]) -> list[dict]:
    collected = []
    for comp in sbom.get("components", []):
        name = comp.get("name", "")
        purl = comp.get("purl", "")
        if name in FIRST_PARTY:
            continue
        if any(name.startswith(p) for p in FIRST_PARTY_PREFIXES):
            continue
        dedup_key = purl if purl else f"{name}@{comp.get('version', '')}"
        if dedup_key in seen_purls:
            continue
        seen_purls.add(dedup_key)
        collected.append(comp)
    return collected


def merge(sboms: list[dict]) -> dict:
    seen_purls: set[str] = set()
    all_components: list[dict] = []

    for sbom in sboms:
        all_components.extend(collect_components(sbom, seen_purls))

    for comp in MANUAL_COMPONENTS:
        purl = str(comp.get("purl", comp["name"]))
        if purl not in seen_purls:
            seen_purls.add(purl)
            all_components.append(comp)

    all_components.sort(key=lambda c: c.get("name", "").lower())

    # Derive a deterministic UUID from the component list so the serialNumber
    # is stable across regenerations with identical dependencies.
    components_digest = hashlib.sha256(
        json.dumps(all_components, sort_keys=True).encode()
    ).digest()
    serial_uuid = uuid.UUID(bytes=components_digest[:16], version=5)

    # Use the last git commit date so the timestamp is reproducible in CI.
    git_date = subprocess.run(
        ["git", "log", "-1", "--format=%cI"],
        cwd=REPO_ROOT, env=git_env(), capture_output=True, text=True,
    )
    timestamp = git_date.stdout.strip() or datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{serial_uuid}",
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "tools": [{"vendor": "OWASP", "name": "cdxgen"}],
            "component": {
                "type": "application",
                "name": "AMD AI Workbench",
                "version": "0.1.0",
                "copyright": "Copyright (c) 2025 Advanced Micro Devices, Inc.",
                "licenses": [{"license": {"id": "MIT"}}],
            },
        },
        "components": all_components,
    }


def main() -> None:
    cdxgen = require_cdxgen()
    sboms: list[dict] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        print("Generating Python SBOMs ...")
        for i, project_dir in enumerate(PYTHON_SUBPROJECTS):
            out = tmp_path / f"python-{i}.json"
            sbom = run_cdxgen(cdxgen, project_dir, "python", out)
            if sbom:
                sboms.append(sbom)

        print("Generating Node.js SBOM ...")
        out = tmp_path / "nodejs.json"
        sbom = run_cdxgen(cdxgen, NODE_WORKSPACE, "npm", out)
        if sbom:
            sboms.append(sbom)

        print("Generating Go SBOMs ...")
        # The `if not sboms` check below is already satisfied by the Python and Node results, so an
        # empty Go set would otherwise produce an SBOM that is quietly missing every Go component.
        go_projects = discover_go_subprojects(REPO_ROOT)
        if not go_projects:
            sys.exit("No tracked Go modules found — refusing to write an SBOM without them.")
        for i, project_dir in enumerate(go_projects):
            out = tmp_path / f"go-{i}.json"
            sbom = run_cdxgen(cdxgen, project_dir, "go", out)
            if sbom:
                sboms.append(sbom)

    if not sboms:
        sys.exit("No SBOMs generated — aborting.")

    print("Merging ...")
    merged = merge(sboms)
    OUTPUT_FILE.write_text(json.dumps(merged, indent=2) + "\n")

    print(f"Written {len(merged['components'])} components → {OUTPUT_FILE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
