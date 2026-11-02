# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Every suite importing aim_catalog.resource must be able to resolve the variables it reads.

A resource whose keywords read ${TEST_MODE} but that does not default it works only for suites
that happen to declare it themselves. A second importing suite then fails at run time with
"Variable '${TEST_MODE}' not found", in suite setup, before any assertion runs. Neither a parse
nor a Robot dry-run catches this: both resolve keyword names, not variable values. These
scenarios are GPU-tagged, so the failure is invisible on the default pipeline and only surfaces
on the nightly GPU run.
"""

import re
from pathlib import Path

SPECS = Path(__file__).resolve().parent
RESOURCE = SPECS / "resources" / "aim_catalog.resource"
SEARCH = [
    SPECS,
    SPECS / "libraries",
    SPECS.parents[2] / "testing",
    SPECS.parents[2] / "testing" / "libraries",
    SPECS.parents[1] / "airm" / "specs",
]
# Robot built-ins and case-variant artifacts of the ALL-CAPS heuristic below.
_BUILTIN = {
    "EMPTY",
    "SPACE",
    "TEMPDIR",
    "CURDIR",
    "EXECDIR",
    "OUTPUT_DIR",
    "OUTPUT_FILE",
    "LOG_LEVEL",
    "TEST_NAME",
    "SUITE_NAME",
    "TRUE",
    "FALSE",
    "NONE",
}


def _find(name: str, base: Path) -> Path | None:
    for candidate in [base.parent / name] + [d / name for d in SEARCH]:
        if candidate.exists():
            return candidate.resolve()
    return None


def _walk(path: Path, seen: set[Path], defined: set[str], texts: list[str]) -> None:
    path = path.resolve()
    if path in seen:
        return
    seen.add(path)
    text = path.read_text()
    texts.append(text)
    in_vars = False
    for line in text.splitlines():
        if line.startswith("*** Variables ***"):
            in_vars = True
            continue
        if in_vars and line.startswith("*** "):
            in_vars = False
        if in_vars:
            match = re.match(r"^[\$@&]\{([^}]+)\}", line)
            if match:
                defined.add(match.group(1).split(":")[0].strip())
    for match in re.finditer(r"^Resource\s+(\S+)", text, re.MULTILINE):
        resolved = _find(match.group(1), path)
        if resolved:
            _walk(resolved, seen, defined, texts)


def _unresolvable(suite: Path) -> set[str]:
    defined: set[str] = set()
    seen: set[Path] = set()
    texts: list[str] = []
    _walk(suite, seen, defined, texts)
    referenced: set[str] = set()
    assigned: set[str] = set()
    for text in texts:
        referenced |= set(re.findall(r"\$\{([A-Z][A-Z0-9_]{3,})\}", text))
        assigned |= set(re.findall(r"VAR\s+\$\{([A-Z][A-Z0-9_]+)\}", text))
        assigned |= set(re.findall(r"Set (?:Test|Suite|Global) Variable\s+\$\{([A-Z][A-Z0-9_]+)\}", text))
    return {v for v in referenced if v not in defined and v not in _BUILTIN and v not in assigned}


def _importing_suites() -> list[Path]:
    return sorted(
        path
        for path in SPECS.glob("*.robot")
        if re.search(r"^Resource\s+resources/aim_catalog\.resource", path.read_text(), re.MULTILINE)
    )


def test_catalog_config_variables_are_defaulted_in_the_shared_resource():
    """The resource must default every catalog knob its own keywords read."""
    text = RESOURCE.read_text()
    body = text.split("*** Keywords ***", 1)[1]
    table = text.split("*** Variables ***", 1)[1].split("*** ", 1)[0]
    declared = set(re.findall(r"^[\$@&]\{([^}:]+)", table, re.MULTILINE))

    for name in ("TEST_MODE", "MAX_GPU_COUNT", "AIM_DEPLOY_TIMEOUT", "AIM_CATALOG_MODEL"):
        if f"${{{name}}}" in body:
            assert name in declared, (
                f"aim_catalog.resource reads ${{{name}}} but does not default it; any importing "
                "suite that does not redeclare it fails at run time in suite setup"
            )


def test_every_suite_importing_the_catalog_resource_can_resolve_its_variables():
    """No importing suite may reference a catalog variable nothing in its import graph defines."""
    suites = _importing_suites()
    assert suites, "expected at least one suite importing resources/aim_catalog.resource"

    # The dynamically generated catalog suite is the reference: it has always worked, so any
    # name unresolvable there too is an artifact of this heuristic, not a real defect.
    reference = _unresolvable(SPECS / "aim_catalog.robot")
    for suite in suites:
        extra = _unresolvable(suite) - reference
        assert not extra, (
            f"{suite.name} cannot resolve {sorted(extra)}; aim_catalog.robot can. "
            "Default them in resources/aim_catalog.resource rather than per suite."
        )
