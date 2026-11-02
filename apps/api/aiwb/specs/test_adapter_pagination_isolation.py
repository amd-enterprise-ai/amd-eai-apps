# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Static guards for adapter pagination scenario independence."""

import re
from pathlib import Path

SPECS_DIR = Path(__file__).resolve().parent
ADAPTERS_SUITE = SPECS_DIR / "adapters.robot"
ADAPTERS_RESOURCE = SPECS_DIR / "resources" / "aiwb_adapters.resource"


def _block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.rstrip() == name), None)
    assert start is not None, f"{name!r} not found"
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def test_adapter_pagination_uses_only_scenario_owned_artifacts() -> None:
    suite = ADAPTERS_SUITE.read_text(encoding="utf-8")
    scenario = _block(suite, "Adapter list is returned page by page")

    assert "Given a fresh project with user access exists" in scenario
    assert "Given a ready project with user access exists" not in scenario

    resource = ADAPTERS_RESOURCE.read_text(encoding="utf-8")
    fixture = _block(resource, "Multiple adapter artifacts exist in the project")

    assert "List Artifacts" not in fixture


def test_adapter_pagination_fixture_creates_more_than_one_adapter() -> None:
    resource = ADAPTERS_RESOURCE.read_text(encoding="utf-8")
    fixture = _block(resource, "Multiple adapter artifacts exist in the project")

    assert "Apply Multiple AIMArtifact CRs" in fixture

    default_count = re.search(r"\$\{count\}=(\d+)", fixture)
    assert default_count is not None, "expected a default value for ${count}"
    assert int(default_count.group(1)) > 1
