#!/usr/bin/env python3
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
"""Generate THIRD-PARTY-NOTICES.md for AMD AI Workbench.

Collects license metadata from all Python virtual environments (via pip-licenses)
and the Node.js workspace (via license-checker), then writes a human-readable
attribution document at the repo root.

Usage:
    python3 scripts/generate-notices.py
    # or from any directory:
    python3 /path/to/core/scripts/generate-notices.py
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from _oss_shared import discover_go_subprojects


def _version_tuple(v: str) -> tuple[int, ...]:
    """Convert a version string to a comparable tuple of ints, ignoring leading 'v'."""
    v = v.lstrip("v")
    parts = re.split(r"[.\-]", v)
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            break
    return tuple(result) or (0,)

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

FIRST_PARTY_PYTHON = {
    "aiwb-api", "airm-api", "api-common", "api_common",
    "workloads-manager", "workloads_manager", "aiwb_api", "airm_api",
}

FIRST_PARTY_NODE = {
    "amdenterpriseai-ui", "aiwb-ui", "airm-ui",
    "@amdenterpriseai/assets", "@amdenterpriseai/components",
    "@amdenterpriseai/hooks", "@amdenterpriseai/layouts",
    "@amdenterpriseai/types", "@amdenterpriseai/utils",
    "@amdenterpriseai/tailwind-config",
}

FIRST_PARTY_GO_PREFIXES = ("github.com/silogen",)

MANUAL_COMPONENTS: list[dict] = []

OUTPUT_FILE = REPO_ROOT / "THIRD-PARTY-NOTICES.md"

# Maps verbose license names returned by pip-licenses / license-checker to SPDX identifiers.
LICENSE_SPDX: dict[str, str] = {
    "Apache Software License": "Apache-2.0",
    "Apache Software License; BSD License": "Apache-2.0 AND BSD-3-Clause",
    "Apache Software License; MIT License": "Apache-2.0 AND MIT",
    "Apache License 2.0": "Apache-2.0",
    "Apache License, Version 2.0": "Apache-2.0",
    "Apache 2.0": "Apache-2.0",
    "Apache-2": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
    "BSD-3-Clause License": "BSD-3-Clause",
    "BSD 3-Clause": "BSD-3-Clause",
    "BSD 2-Clause": "BSD-2-Clause",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0-or-later",
    "GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "ISC License (ISCL)": "ISC",
    "MIT License": "MIT",
    "MIT*": "MIT",
    "MIT-CMU": "MIT",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
    "Python Software Foundation License; MIT License": "PSF-2.0 AND MIT",
    "Public Domain": "Unlicense",
    "The Unlicense (Unlicense)": "Unlicense",
    "CC0 1.0 Universal (CC0 1.0) Public Domain Dedication": "CC0-1.0",
    "Historical Permission Notice and Disclaimer (HPND)": "HPND",
    "(MIT OR CC0-1.0)": "MIT OR CC0-1.0",
}

_EMAIL_RE = re.compile(r"\s*<[^>]+>")


def normalize_license(raw: str) -> str:
    raw = raw.strip()
    # pip-licenses sometimes puts the full license text in the License field.
    # Detect by newlines or a leading copyright notice and classify by content.
    if "\n" in raw or raw.lower().startswith("copyright"):
        low = raw.lower()
        if "apache" in low:
            return "Apache-2.0"
        if "lgpl" in low or "lesser general public" in low:
            return "LGPL-3.0-or-later"
        if "mozilla" in low:
            return "MPL-2.0"
        # Check BSD before MIT — BSD templates contain "redistribution"
        if "redistribution" in low or "bsd" in low:
            # BSD-3 has the non-endorsement clause; BSD-2 does not
            has_third = "neither the name" in low or "endorse or promote" in low
            return "BSD-3-Clause" if has_third else "BSD-2-Clause"
        if "mit license" in low or "permission is hereby granted" in low:
            return "MIT"
        return "Unknown"
    # Split composite strings (e.g. "BSD License; Public Domain") and normalize each part.
    if ";" in raw or ("," in raw and not raw.startswith("(")):
        sep = ";" if ";" in raw else ","
        parts = [LICENSE_SPDX.get(p.strip(), p.strip()) for p in raw.split(sep) if p.strip()]
        return " AND ".join(dict.fromkeys(parts))
    return LICENSE_SPDX.get(raw, raw)


def normalize_python_copyright(author: str) -> str:
    """Return a clean author name, or 'See project repository' when unknown."""
    author = author.strip().strip(",")
    if not author or author.upper() in {"UNKNOWN", "NONE", ""}:
        return "See project repository"
    # Strip encoded email headers (=?utf-8?...?=)
    author = re.sub(r"=\?[^?]+\?[bBqQ]\?[^?]+\?=", "", author).strip()
    # Strip angle-bracket emails
    author = _EMAIL_RE.sub("", author).strip().strip(",").strip()
    # Strip surrounding quotes
    author = author.strip('"').strip("'").strip()
    # Strip leading single-character word artifacts from package metadata (e.g. "x The platformdirs developers")
    author = re.sub(r"^[a-zA-Z]\s+", "", author).strip()
    if not author:
        return "See project repository"
    return author


_COPYRIGHT_STMT_RE = re.compile(
    # A copyright statement either:
    #   (a) has the (c) / © symbol:  "Copyright (c) Sindre Sorhus"
    #   (b) has a year:              "Copyright 2013 Foo Inc."
    # The Apache-2.0 body clause ("copyright notice that is included in or
    # attached to the work") has neither, so this rejects it.
    r"(?i)^copyright\s*(\(c\)|©|\d{4})",
)


def copyright_from_license_file(license_file: str) -> str:
    """Extract the first copyright holder from a package's LICENSE file."""
    try:
        text = Path(license_file).read_text(errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            # Require "Copyright <symbol?> <year>" — filters out Apache license body
            # clauses like "copyright notice that is included in or attached to the work".
            if not _COPYRIGHT_STMT_RE.match(stripped):
                continue
            holder = re.sub(r"(?i)^copyright\s*(\(c\)|©)?\s*(\d{4}[\d\s,\-–x]+)?\s*", "", stripped).strip()
            holder = holder.rstrip(",").strip()
            if holder:
                return holder
    except OSError:
        pass
    return "See project repository"

INTRO = """\
<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Third-Party Notices

This software incorporates code or materials from third parties. AMD makes certain \
open-source software available via written request (identify product name, component \
name, version number) to Advanced Micro Devices, Inc., Attn: Software Legal Team, \
7171 Southwest Pkwy, Austin, TX, 78735. AMD may charge you a reasonable fee for \
providing the source code.

---
"""


def collect_python(project_dir: Path) -> list[dict]:
    print(f"  Collecting Python licenses from {project_dir.relative_to(REPO_ROOT)} ...", flush=True)
    result = subprocess.run(
        ["uv", "run", "--with", "pip-licenses",
         "pip-licenses", "--format=json", "--with-authors", "--with-urls", "--with-license-file"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(f"pip-licenses failed in {project_dir.name}:\n{result.stderr[-500:]}")
    return json.loads(result.stdout)


def collect_node(workspace: Path) -> dict[str, dict]:
    print(f"  Collecting Node.js licenses from {workspace.relative_to(REPO_ROOT)} ...", flush=True)
    result = subprocess.run(
        ["npx", "license-checker@25.0.1", "--json"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        sys.exit(f"license-checker failed:\n{result.stderr[-500:]}")
    return json.loads(result.stdout)


def merge_python(all_results: list[list[dict]]) -> dict[str, dict]:
    """Deduplicate across subprojects, keeping highest version seen."""
    merged: dict[str, dict] = {}
    for entries in all_results:
        for entry in entries:
            name = entry.get("Name", "")
            if not name or name.lower().replace("-", "_") in {
                p.replace("-", "_") for p in FIRST_PARTY_PYTHON
            }:
                continue
            existing = merged.get(name)
            if existing is None or _version_tuple(entry.get("Version", "")) > _version_tuple(existing.get("Version", "")):
                merged[name] = entry
    return merged


def format_python_section(packages: dict[str, dict]) -> str:
    lines = ["## Python Dependencies\n"]
    for name in sorted(packages, key=str.lower):
        p = packages[name]
        version = p.get("Version", "")
        license_ = normalize_license(p.get("License", "Unknown"))
        copyright_ = normalize_python_copyright(p.get("Author", ""))
        if copyright_ == "See project repository" and (lf := p.get("LicenseFile", "")):
            copyright_ = copyright_from_license_file(lf)
        lines.append(f"### {name} {version}\n")
        lines.append(f"**License:** {license_}")
        lines.append(f"**Copyright:** {copyright_}\n")
    return "\n".join(lines)


def _copyright_from_package_json(pkg_path: str) -> str:
    """Extract a copyright holder from a package's package.json."""
    try:
        d = json.loads(Path(pkg_path).read_text())

        # author field: string or {name, email, url}
        author = d.get("author") or {}
        if isinstance(author, str) and author:
            name = _EMAIL_RE.sub("", author).split("(")[0].strip().strip('"')
            if name:
                return name
        elif isinstance(author, dict) and author.get("name"):
            return author["name"]

        # contributors / maintainers: [{name, email, organization}] or ["name <email>"]
        for field in ("contributors", "maintainers"):
            entries = d.get(field) or []
            if not isinstance(entries, list):
                continue
            for entry in entries[:1]:
                if isinstance(entry, dict):
                    org = entry.get("organization") or entry.get("name") or ""
                    name = _EMAIL_RE.sub("", org).strip()
                    if name:
                        return name
                elif isinstance(entry, str):
                    name = _EMAIL_RE.sub("", entry).split("(")[0].strip()
                    if name:
                        return name

        # Infer from well-known repository owners
        repo = d.get("repository") or {}
        url = repo.get("url", "") if isinstance(repo, dict) else str(repo)
        REPO_OWNERS = {
            "github.com/vercel/": "Vercel, Inc.",
            "github.com/facebook/": "Meta Platforms, Inc. and affiliates",
            "github.com/koajs/": "TJ Holowaychuk",
            "koajs/": "TJ Holowaychuk",  # shorthand "koajs/compose" form
            "github.com/mathjax/": "MathJax Consortium",
            "github.com/nicolo-ribaudo/": "Nicolo Ribaudo",
        }
        for pattern, owner in REPO_OWNERS.items():
            if pattern in url:
                return owner

    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return "See project repository"


def _node_copyright(meta: dict) -> str:
    """Resolve copyright for a Node.js package, trying multiple sources."""
    publisher = meta.get("publisher", "").strip()
    if publisher:
        return publisher

    if license_file := meta.get("licenseFile", ""):
        holder = copyright_from_license_file(license_file)
        if holder != "See project repository":
            return holder
        # Also try package.json in the same directory
        pkg_json = str(Path(license_file).parent / "package.json")
        holder = _copyright_from_package_json(pkg_json)
        if holder != "See project repository":
            return holder

    if path := meta.get("path", ""):
        holder = _copyright_from_package_json(str(Path(path) / "package.json"))
        if holder != "See project repository":
            return holder

    return "See project repository"


def format_node_section(raw: dict[str, dict]) -> tuple[str, int]:
    lines = ["## Node.js Dependencies\n"]
    seen: dict[str, dict] = {}
    for key, meta in raw.items():
        if meta.get("private"):
            continue
        at = key.rfind("@") if not key.startswith("@") else key.rfind("@", 1)
        name = key[:at] if at > 0 else key
        version = key[at + 1:] if at > 0 else ""
        if name in FIRST_PARTY_NODE:
            continue
        existing = seen.get(name)
        if existing is None or _version_tuple(version) > _version_tuple(existing.get("_version", "")):
            seen[name] = {**meta, "_version": version}

    for name in sorted(seen, key=str.lower):
        meta = seen[name]
        version = meta.get("_version", "")
        license_ = normalize_license(meta.get("licenses", "Unknown"))
        copyright_ = _node_copyright(meta)
        lines.append(f"### {name} {version}\n")
        lines.append(f"**License:** {license_}")
        lines.append(f"**Copyright:** {copyright_}\n")
    return "\n".join(lines), len(seen)


def _go_module_dirs(project_dir: Path) -> dict[str, Path]:
    """Return a map of module path → local directory from the module cache."""
    result = subprocess.run(
        ["go", "mod", "download", "-json"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    module_dirs: dict[str, Path] = {}
    decoder = json.JSONDecoder()
    data = result.stdout
    while data:
        data = data.lstrip()
        if not data:
            break
        try:
            obj, idx = decoder.raw_decode(data)
            path = obj.get("Path", "")
            dir_ = obj.get("Dir", "")
            if path and dir_:
                module_dirs[path] = Path(dir_)
            data = data[idx:]
        except json.JSONDecodeError:
            break
    return module_dirs


_GO_SOURCE_COPYRIGHT_RE = re.compile(
    r"(?:^//\s*|^/\*\s*|^\s*)Copyright\s+(?:\(c\)|©)?\s*(?:\d{4}[\d,\s\-–]*)?\s*(.+?)(?:\.|,|\n|\*/|$)",
    re.IGNORECASE | re.MULTILINE,
)


def _copyright_from_go_sources(module_dir: Path) -> str:
    """Extract copyright from Go source file block comments (/* Copyright ... */)."""
    for go_file in sorted(module_dir.rglob("*.go")):
        try:
            text = go_file.read_text(errors="replace")
        except OSError:
            continue
        # Only scan the first 30 lines — copyright headers are at the top.
        snippet = "\n".join(text.splitlines()[:30])
        m = _GO_SOURCE_COPYRIGHT_RE.search(snippet)
        if m:
            holder = m.group(1).strip().rstrip(".,")
            # Strip trailing parenthetical URLs (may be unclosed if regex stopped mid-URL):
            # "sigu-399 ( https://github.com/..." → "sigu-399"
            holder = re.sub(r"\s*\(\s*https?://.*$", "", holder).strip().rstrip(".,")
            if holder and len(holder) > 2:
                return holder
    return "See project repository"


def _go_copyright(package_name: str, module_dirs: dict[str, Path]) -> str:
    """Resolve copyright for a Go package by reading its LICENSE/NOTICE file from the module cache."""
    # Find the longest module prefix that matches the package name.
    match = max(
        (m for m in module_dirs if package_name == m or package_name.startswith(m + "/")),
        key=len,
        default=None,
    )
    if match is None:
        return "See project repository"
    module_dir = module_dirs[match]
    if not module_dir.exists():
        return "See project repository"
    # Check LICENSE first, then NOTICE — Apache projects often only have copyright in NOTICE.
    for pattern in (r"(?i)^(UN)?LICEN(S|C)E", r"(?i)^NOTICE"):
        for candidate in module_dir.iterdir():
            if re.match(pattern, candidate.name) and candidate.is_file():
                holder = copyright_from_license_file(str(candidate))
                if holder != "See project repository":
                    return holder
    # Last resort: scan Go source file headers (Apache projects embed copyright there).
    return _copyright_from_go_sources(module_dir)


def collect_go(project_dir: Path) -> list[dict]:
    print(f"  Collecting Go licenses from {project_dir.relative_to(REPO_ROOT)} ...", flush=True)
    try:
        # Ignore stdlib and first-party packages — go-licenses can't resolve stdlib module info.
        stdlib = subprocess.run(["go", "list", "std"], cwd=project_dir, capture_output=True, text=True)
        ignore_parts = list(stdlib.stdout.split()) if stdlib.returncode == 0 else []
        ignore_parts += list(FIRST_PARTY_GO_PREFIXES)
        ignore = ",".join(ignore_parts)

        cmd = ["go-licenses", "report", "--ignore", ignore, "./..."]
        result = subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True)
    except FileNotFoundError:
        sys.exit("go-licenses not found. Install Go and run: go install github.com/google/go-licenses@latest")
    if result.returncode != 0:
        sys.exit(f"go-licenses failed in {project_dir.name}:\n{result.stderr[-300:]}")

    module_dirs = _go_module_dirs(project_dir)

    entries = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 3:
            continue
        name, _url, license_ = parts[0], parts[1], parts[2]
        copyright_ = _go_copyright(name, module_dirs)
        entries.append({"Name": name, "License": normalize_license(license_), "Copyright": copyright_})
    return entries


def merge_go(all_results: list[list[dict]]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for entries in all_results:
        for entry in entries:
            name = entry["Name"]
            if name not in merged:
                merged[name] = entry
    return merged


def format_go_section(packages: dict[str, dict]) -> str:
    lines = ["## Go Dependencies\n"]
    for name in sorted(packages, key=str.lower):
        p = packages[name]
        license_ = p.get("License", "Unknown")
        copyright_ = p.get("Copyright", "See project repository")
        lines.append(f"### {name}\n")
        lines.append(f"**License:** {license_}")
        lines.append(f"**Copyright:** {copyright_}\n")
    return "\n".join(lines)


def format_manual_section() -> str:
    lines = ["## Vendored Components\n"]
    for comp in MANUAL_COMPONENTS:
        lines.append(f"### {comp['name']} {comp['version']}\n")
        lines.append(f"**License:** {comp['license']}")
        lines.append(f"**Copyright:** {comp['copyright']}")
        lines.append(f"**Source:** {comp['url']}\n")
    return "\n".join(lines)


def main() -> None:
    print("Collecting Python licenses ...")
    py_raw = [collect_python(d) for d in PYTHON_SUBPROJECTS]
    py_packages = merge_python(py_raw)

    print("Collecting Node.js licenses ...")
    node_raw = collect_node(NODE_WORKSPACE)

    print("Collecting Go licenses ...")
    # An empty result would otherwise sail through: the Go section would render with no entries and
    # the script would exit 0, publishing a disclosure that is quietly missing every Go dependency.
    go_projects = discover_go_subprojects(REPO_ROOT)
    if not go_projects:
        sys.exit("No tracked Go modules found — refusing to write notices without them.")
    go_raw = [collect_go(d) for d in go_projects]
    go_packages = merge_go(go_raw)

    print("Writing THIRD-PARTY-NOTICES.md ...")
    node_section, node_count = format_node_section(node_raw)
    sections = [
        INTRO,
        format_python_section(py_packages),
        "\n---\n",
        node_section,
        "\n---\n",
        format_go_section(go_packages),
    ]
    if MANUAL_COMPONENTS:
        sections += ["\n---\n", format_manual_section()]
    OUTPUT_FILE.write_text("\n".join(sections) + "\n")

    print(
        f"Done — {len(py_packages)} Python packages, "
        f"{node_count} Node.js packages, "
        f"{len(go_packages)} Go packages → {OUTPUT_FILE.relative_to(REPO_ROOT)}"
    )


if __name__ == "__main__":
    main()
