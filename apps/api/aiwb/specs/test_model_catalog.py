# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for profile-aware AIM catalog selection."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "libraries"))

from ModelCatalog import (
    get_deployable_aim_gpu_count,
    get_deployable_aim_profile,
    get_model_resource_quota,
    get_second_smallest_deployable_aim_with_gpu_count,
    get_second_smallest_deployable_aim_with_profile,
    get_smallest_adapter_capable_aim,
    get_smallest_adapter_capable_aim_with_gpu_count,
    get_smallest_aim_for_runtime_profile_overrides,
    get_smallest_deployable_aim_with_gpu_count,
    get_smallest_deployable_aim_with_profile,
    get_smallest_finetunable_model_with_gpu_count,
)


def _aim(aim_id: str, resource_name: str) -> dict:
    return {
        "metadata": {"name": resource_name},
        "status": {"aimId": aim_id, "status": "Ready"},
    }


def _profile(
    aim_id: str,
    gpu_count: int,
    *,
    manual: bool = False,
    features: list[str] | None = None,
    name: str = "profile",
) -> dict:
    return {
        "metadata": {"name": name},
        "spec": {
            "acceleratorCount": gpu_count,
            "aimId": aim_id,
            "features": features or [],
            "manualSelectionOnly": manual,
        },
        "status": {"matchingNodes": 1, "status": "Ready"},
    }


def _runtime_aim(aim_id: str, resource_name: str, image: str | None = None) -> dict:
    return {
        "metadata": {"name": resource_name},
        "spec": {"image": image or f"registry.example.com/{aim_id.lower().replace('/', '-')}:latest"},
        "status": {"aimId": aim_id, "status": "Ready"},
    }


def _runtime_profile(
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


def _keyword_block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.rstrip() == name)
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def test_runtime_override_fixture_uses_selector_compatible_model() -> None:
    specs_dir = Path(__file__).resolve().parent
    robot_text = (specs_dir / "aims.robot").read_text()
    resource_text = (specs_dir / "resources" / "aiwb_aims.resource").read_text()

    assert robot_text.count("And an AIM compatible with runtime profile overrides exists") == 2

    selector_block = _keyword_block(resource_text, "An AIM compatible with runtime profile overrides exists")
    assert "No Ready AIMs available in system" in selector_block
    payload_block = _keyword_block(resource_text, "Valid AIM deploy data with runtime profile overrides is prepared")
    assertion_block = _keyword_block(
        resource_text,
        "AIMService CR should have runtime profile overrides in kubernetes",
    )
    for block in (selector_block, payload_block, assertion_block):
        assert "MI300X" in block
        assert "fp4" in block
    assert "${2}" in selector_block
    assert "gpuCount=${2}" in payload_block
    assert "max-model-len=${8192}" in payload_block
    assert "name=VLLM_LOGGING_LEVEL" in payload_block
    assert "value=DEBUG" in payload_block


def test_runtime_override_selection_uses_model_with_matching_profile() -> None:
    aims = [
        _runtime_aim("acme/Model-7B", "smallest-incompatible"),
        _runtime_aim("acme/Model-20B", "compatible-model"),
    ]
    profiles = [
        _runtime_profile("acme/Model-7B", precision="fp16"),
        _runtime_profile("acme/Model-20B"),
    ]

    selected = get_smallest_aim_for_runtime_profile_overrides(aims, profiles, "MI300X", 2, "fp4")

    assert selected == "compatible-model"


def test_runtime_override_selection_keeps_profile_on_matching_image_version() -> None:
    aims = [
        _runtime_aim("acme/Model-20B", "older-model", "registry.example.com/model:1.0"),
        _runtime_aim("acme/Model-20B", "profile-owner", "registry.example.com/model:2.0"),
    ]
    profiles = [_runtime_profile("acme/Model-20B", image="registry.example.com/model:2.0")]

    selected = get_smallest_aim_for_runtime_profile_overrides(aims, profiles, "MI300X", 2, "fp4")

    assert selected == "profile-owner"


def test_runtime_override_selection_accepts_profile_without_optional_image() -> None:
    profile = _runtime_profile("acme/Model-20B")
    profile["spec"].pop("image")

    selected = get_smallest_aim_for_runtime_profile_overrides(
        [_runtime_aim("acme/Model-20B", "compatible-model")],
        [profile],
        "MI300X",
        2,
        "fp4",
    )

    assert selected == "compatible-model"


@pytest.mark.parametrize(
    "profile",
    [
        _runtime_profile("Qwen/Qwen3-32B", status="Pending"),
        _runtime_profile("Qwen/Qwen3-32B", matching_nodes=0),
        _runtime_profile("Qwen/Qwen3-32B", manual_selection_only=True),
    ],
    ids=["not-ready", "no-matching-node", "manual-only"],
)
def test_runtime_override_selection_rejects_unavailable_profiles(profile: dict) -> None:
    with pytest.raises(ValueError, match="No open, Ready AIM has a Ready, auto-selectable profile"):
        get_smallest_aim_for_runtime_profile_overrides(
            [_runtime_aim("Qwen/Qwen3-32B", "unavailable-model")],
            [profile],
            "MI300X",
            2,
            "fp4",
        )


def test_smallest_deployable_aim_returns_its_exact_profile_and_gpu_count():
    aims = [_aim("example/Model-8B", "model-8b"), _aim("example/Model-3B", "model-3b")]
    profiles = [
        _profile("example/Model-8B", 2, name="model-8b-2gpu"),
        _profile("example/Model-3B", 1, name="model-3b-1gpu"),
    ]

    assert get_smallest_deployable_aim_with_profile(aims, profiles) == (
        "model-3b",
        "model-3b-1gpu",
        1,
    )
    assert get_smallest_deployable_aim_with_gpu_count(aims, profiles) == ("model-3b", 1)


@pytest.mark.parametrize("gpu_count", [2, 4, 8])
def test_smallest_deployable_aim_supports_catalog_gpu_requirements(gpu_count):
    aims = [_aim("example/Model-3B", "model-3b")]
    profiles = [_profile("example/Model-3B", gpu_count)]

    assert get_smallest_deployable_aim_with_gpu_count(aims, profiles) == ("model-3b", gpu_count)


def test_smallest_deployable_aim_pins_the_profile_behind_its_gpu_requirement():
    aims = [_aim("example/Model-3B", "model-3b")]
    profiles = [
        _profile("example/Model-3B", 4, name="optimized-4gpu"),
        _profile("example/Model-3B", 2, name="general-2gpu"),
        _profile("example/Model-3B", 1, manual=True, name="manual-1gpu"),
    ]

    assert get_smallest_deployable_aim_with_profile(aims, profiles) == (
        "model-3b",
        "general-2gpu",
        2,
    )


def test_deployable_aim_profile_resolves_an_explicit_selection():
    aims = [_aim("example/Model-8B", "model-8b"), _aim("example/Model-3B", "model-3b")]
    profiles = [
        _profile("example/Model-8B", 4, name="model-8b-4gpu"),
        _profile("example/Model-3B", 1, name="model-3b-1gpu"),
    ]

    assert get_deployable_aim_profile(aims, profiles, "model-8b") == ("model-8b-4gpu", 4)
    assert get_deployable_aim_gpu_count(aims, profiles, "model-8b") == 4


def test_second_smallest_deployable_aim_returns_its_profile_gpu_count():
    aims = [_aim("example/Model-8B", "model-8b"), _aim("example/Model-3B", "model-3b")]
    profiles = [
        _profile("example/Model-8B", 4, name="model-8b-4gpu"),
        _profile("example/Model-3B", 1, name="model-3b-1gpu"),
    ]

    assert get_second_smallest_deployable_aim_with_profile(aims, profiles) == (
        "model-8b",
        "model-8b-4gpu",
        4,
    )
    assert get_second_smallest_deployable_aim_with_gpu_count(aims, profiles) == ("model-8b", 4)


def test_smallest_adapter_capable_aim_returns_pinned_profile_gpu_count():
    aims = [_aim("example/Model-8B", "model-8b"), _aim("example/Model-3B", "model-3b")]
    profiles = [
        _profile("example/Model-8B", 4, features=["adapters"], name="adapter-4gpu"),
        _profile("example/Model-3B", 2, manual=True, features=["adapters"], name="adapter-2gpu"),
    ]

    assert get_smallest_adapter_capable_aim_with_gpu_count(aims, profiles) == ("model-3b", "adapter-2gpu", 2)
    assert get_smallest_adapter_capable_aim(aims, profiles) == ("model-3b", "adapter-2gpu")


def test_smallest_finetunable_model_returns_its_recipe_gpu_count():
    models = [
        {"canonicalName": "example/Model-8B", "gpuCount": 4},
        {"canonicalName": "example/Model-3B", "gpuCount": 1},
    ]

    assert get_smallest_finetunable_model_with_gpu_count(models) == ("example/Model-3B", 1)


def test_smallest_finetunable_model_keeps_open_model_preference():
    models = [
        {"canonicalName": "meta-llama/Llama-3.2-1B", "gpuCount": 1},
        {"canonicalName": "example/Model-8B", "gpuCount": 4},
    ]

    assert get_smallest_finetunable_model_with_gpu_count(models) == ("example/Model-8B", 4)


@pytest.mark.parametrize(
    ("gpu_count", "expected"),
    [
        ("1", (1, 4_000, 32 * 1024**3)),
        (4, (4, 16_000, 128 * 1024**3)),
        (8, (8, 32_000, 256 * 1024**3)),
    ],
)
def test_model_resource_quota_scales_with_gpu_count(gpu_count, expected):
    assert get_model_resource_quota(gpu_count) == expected


@pytest.mark.parametrize("gpu_count", [0, -1, 1.5, True, "invalid"])
def test_model_resource_quota_rejects_invalid_gpu_count(gpu_count):
    with pytest.raises(ValueError, match="positive integer"):
        get_model_resource_quota(gpu_count)
