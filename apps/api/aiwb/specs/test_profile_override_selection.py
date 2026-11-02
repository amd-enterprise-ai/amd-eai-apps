# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for runtime-profile-aware AIM selection."""

import sys
from pathlib import Path

import pytest

SPECS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SPECS_DIR / "libraries"))

from ModelCatalog import get_smallest_aim_for_runtime_profile_overrides  # noqa: E402


def _aim(aim_id: str, resource_name: str, image: str | None = None) -> dict:
    return {
        "metadata": {"name": resource_name},
        "spec": {"image": image or f"registry.example.com/{aim_id.lower().replace('/', '-')}:latest"},
        "status": {"aimId": aim_id, "status": "Ready"},
    }


def _profile(
    aim_id: str,
    *,
    image: str | None = None,
    precision: str = "fp4",
    status: str = "Ready",
    matching_nodes: int = 1,
    manual_selection_only: bool = False,
) -> dict:
    return {
        "spec": {
            "aimId": aim_id,
            "image": image or f"registry.example.com/{aim_id.lower().replace('/', '-')}:latest",
            "acceleratorModel": "MI300X",
            "acceleratorCount": 2,
            "precision": precision,
            "manualSelectionOnly": manual_selection_only,
        },
        "status": {"status": status, "matchingNodes": matching_nodes},
    }


def _block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.rstrip() == name)
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def test_runtime_override_fixture_uses_selector_compatible_model() -> None:
    suite = (SPECS_DIR / "aims.robot").read_text()
    resource = (SPECS_DIR / "resources" / "aiwb_aims.resource").read_text()

    assert suite.count("And an AIM compatible with runtime profile overrides exists") == 2
    selector = _block(resource, "An AIM compatible with runtime profile overrides exists")
    payload = _block(resource, "Valid AIM deploy data with runtime profile overrides is prepared")
    assertion = _block(resource, "AIMService CR should have runtime profile overrides in kubernetes")
    for block in (selector, payload, assertion):
        assert "MI300X" in block
        assert "fp4" in block
    assert "${2}" in selector
    assert "gpuCount=${2}" in payload


def test_runtime_override_selection_uses_matching_profile() -> None:
    aims = [_aim("acme/Model-7B", "incompatible"), _aim("acme/Model-20B", "compatible")]
    profiles = [_profile("acme/Model-7B", precision="fp16"), _profile("acme/Model-20B")]

    assert get_smallest_aim_for_runtime_profile_overrides(aims, profiles, "MI300X", 2, "fp4") == "compatible"


def test_runtime_override_selection_matches_profile_image_version() -> None:
    aims = [
        _aim("acme/Model-20B", "old", "registry.example.com/model:1.0"),
        _aim("acme/Model-20B", "current", "registry.example.com/model:2.0"),
    ]
    profiles = [_profile("acme/Model-20B", image="registry.example.com/model:2.0")]

    assert get_smallest_aim_for_runtime_profile_overrides(aims, profiles, "MI300X", 2, "fp4") == "current"


def test_runtime_override_selection_accepts_profile_without_optional_image() -> None:
    profile = _profile("acme/Model-20B")
    profile["spec"].pop("image")

    assert (
        get_smallest_aim_for_runtime_profile_overrides(
            [_aim("acme/Model-20B", "compatible")], [profile], "MI300X", 2, "fp4"
        )
        == "compatible"
    )


@pytest.mark.parametrize(
    "profile",
    [
        _profile("Qwen/Qwen3-32B", status="Pending"),
        _profile("Qwen/Qwen3-32B", matching_nodes=0),
        _profile("Qwen/Qwen3-32B", manual_selection_only=True),
    ],
    ids=["not-ready", "no-matching-node", "manual-only"],
)
def test_runtime_override_selection_rejects_unavailable_profiles(profile: dict) -> None:
    with pytest.raises(ValueError, match="No open, Ready AIM has a Ready, auto-selectable profile"):
        get_smallest_aim_for_runtime_profile_overrides(
            [_aim("Qwen/Qwen3-32B", "unavailable")], [profile], "MI300X", 2, "fp4"
        )
