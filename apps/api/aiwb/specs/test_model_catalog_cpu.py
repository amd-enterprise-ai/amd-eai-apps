# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for ModelCatalog pure selection logic (smallest-deployable and CPU-servable)."""

import sys
from pathlib import Path

import pytest

# Add libraries to path so ModelCatalog is importable
sys.path.insert(0, str(Path(__file__).parent / "libraries"))

from ModelCatalog import get_smallest_cpu_servable_aim, get_smallest_deployable_aim

# -- Builders --


def _aim(aim_id: str, resource_name: str, status: str = "Ready") -> dict:
    return {"metadata": {"name": resource_name}, "status": {"aimId": aim_id, "status": status}}


def _profile(
    aim_id: str,
    accelerator_type: str = "gpu",
    accelerator_count: int = 1,
    *,
    name: str = "",
    status: str = "Ready",
    matching_nodes: int = 1,
    manual_only: bool = False,
    accelerator_model: str = "EPYC_ZEN4",
) -> dict:
    return {
        "metadata": {"name": name or f"{aim_id}-{accelerator_type}-profile"},
        "spec": {
            "aimId": aim_id,
            "acceleratorType": accelerator_type,
            "acceleratorCount": accelerator_count,
            "acceleratorModel": accelerator_model,
            "manualSelectionOnly": manual_only,
        },
        "status": {"status": status, "matchingNodes": matching_nodes},
    }


# -- get_smallest_deployable_aim --


def test_deployable_picks_fewest_accelerators_then_params():
    aims = [_aim("org/Big-70B", "big"), _aim("org/Small-3B", "small")]
    profiles = [
        _profile("org/Big-70B", accelerator_count=8),
        _profile("org/Small-3B", accelerator_count=1),
    ]
    assert get_smallest_deployable_aim(aims, profiles) == "small"


def test_deployable_excludes_approval_gated_families():
    aims = [_aim("meta-llama/Llama-8B", "llama")]
    profiles = [_profile("meta-llama/Llama-8B", accelerator_count=1)]
    with pytest.raises(ValueError, match="non-approval-gated families"):
        get_smallest_deployable_aim(aims, profiles)


def test_deployable_ignores_manual_only_profiles():
    aims = [_aim("org/Model-3B", "m3")]
    profiles = [_profile("org/Model-3B", accelerator_count=1, manual_only=True)]
    with pytest.raises(ValueError, match="No auto-selectable deployable profiles"):
        get_smallest_deployable_aim(aims, profiles)


def test_deployable_prefers_open_model_when_smaller_gated_model_exists():
    aims = [_aim("meta-llama/Llama-1B", "gated"), _aim("org/Open-3B", "open")]
    profiles = [
        _profile("meta-llama/Llama-1B", accelerator_count=1),
        _profile("org/Open-3B", accelerator_count=2),
    ]
    assert get_smallest_deployable_aim(aims, profiles) == "open"


# -- get_smallest_cpu_servable_aim --


def test_cpu_servable_prefers_cpu_profile_over_gpu_and_returns_profile():
    aims = [_aim("org/Gpu-3B", "gpu-aim"), _aim("org/Cpu-3B", "cpu-aim")]
    profiles = [
        _profile("org/Gpu-3B", accelerator_type="gpu", accelerator_count=1),
        _profile("org/Cpu-3B", accelerator_type="cpu", accelerator_count=0, name="cpu-3b-profile"),
    ]
    assert get_smallest_cpu_servable_aim(aims, profiles) == ("cpu-aim", "cpu-3b-profile", "EPYC_ZEN4")


def test_cpu_servable_accepts_zero_accelerator_count():
    aims = [_aim("org/Cpu-3B", "cpu-aim")]
    profiles = [_profile("org/Cpu-3B", accelerator_type="cpu", accelerator_count=0)]
    name, _profile_name, _accelerator_model = get_smallest_cpu_servable_aim(aims, profiles)
    assert name == "cpu-aim"


def test_cpu_servable_pins_manual_only_profile():
    # manualSelectionOnly CPU profiles are eligible because the caller pins the profileName.
    aims = [_aim("meta-llama/Llama-8B", "llama")]
    profiles = [
        _profile("meta-llama/Llama-8B", accelerator_type="cpu", accelerator_count=1, manual_only=True, name="llama-cpu")
    ]
    assert get_smallest_cpu_servable_aim(aims, profiles, allow_gated=True) == ("llama", "llama-cpu", "EPYC_ZEN4")


def test_cpu_servable_excludes_gated_by_default():
    aims = [_aim("meta-llama/Llama-8B", "llama")]
    profiles = [_profile("meta-llama/Llama-8B", accelerator_type="cpu", accelerator_count=0)]
    with pytest.raises(ValueError, match="non-approval-gated families"):
        get_smallest_cpu_servable_aim(aims, profiles)


def test_cpu_servable_includes_gated_when_allowed():
    aims = [_aim("meta-llama/Llama-8B", "llama")]
    profiles = [_profile("meta-llama/Llama-8B", accelerator_type="cpu", accelerator_count=0)]
    name, _profile_name, _accelerator_model = get_smallest_cpu_servable_aim(aims, profiles, allow_gated=True)
    assert name == "llama"


def test_cpu_servable_raises_when_only_gpu_profiles():
    aims = [_aim("org/Gpu-3B", "gpu-aim")]
    profiles = [_profile("org/Gpu-3B", accelerator_type="gpu", accelerator_count=1)]
    with pytest.raises(ValueError, match="No collector-supported EPYC profile"):
        get_smallest_cpu_servable_aim(aims, profiles)


def test_cpu_servable_rejects_generic_cpu_profile():
    aims = [_aim("org/Cpu-3B", "cpu-aim")]
    profiles = [
        _profile(
            "org/Cpu-3B",
            accelerator_type="cpu",
            accelerator_count=0,
            accelerator_model="CPU",
        )
    ]
    with pytest.raises(ValueError, match="No collector-supported EPYC profile"):
        get_smallest_cpu_servable_aim(aims, profiles)


def test_cpu_servable_prefers_supported_epyc_over_smaller_generic_cpu():
    aims = [_aim("org/Generic-1B", "generic"), _aim("org/Epyc-3B", "epyc")]
    profiles = [
        _profile("org/Generic-1B", accelerator_type="cpu", accelerator_count=0, accelerator_model="CPU"),
        _profile(
            "org/Epyc-3B",
            accelerator_type="cpu",
            accelerator_count=188,
            accelerator_model="EPYC_ZEN4",
            name="epyc-profile",
        ),
    ]
    assert get_smallest_cpu_servable_aim(aims, profiles) == ("epyc", "epyc-profile", "EPYC_ZEN4")


def test_cpu_servable_rejects_unsupported_epyc_model():
    aims = [_aim("org/Future-Epyc-1B", "future")]
    profiles = [
        _profile(
            "org/Future-Epyc-1B",
            accelerator_type="cpu",
            accelerator_count=1,
            accelerator_model="EPYC_FUTURE",
        )
    ]
    with pytest.raises(ValueError, match="No collector-supported EPYC profile"):
        get_smallest_cpu_servable_aim(aims, profiles)


def test_cpu_servable_ignores_unschedulable_and_non_ready_cpu_profiles():
    aims = [_aim("org/NoNode-3B", "nonode"), _aim("org/Pending-3B", "pending")]
    profiles = [
        _profile("org/NoNode-3B", accelerator_type="cpu", accelerator_count=0, matching_nodes=0),
        _profile("org/Pending-3B", accelerator_type="cpu", accelerator_count=0, status="Pending"),
    ]
    with pytest.raises(ValueError, match="No collector-supported EPYC profile"):
        get_smallest_cpu_servable_aim(aims, profiles)


def test_cpu_servable_raises_when_model_not_ready_despite_cpu_profile():
    # A CPU profile exists and is schedulable, but its AIM is not Ready -> no candidate.
    aims = [_aim("org/Cpu-3B", "cpu-aim", status="Pending")]
    profiles = [_profile("org/Cpu-3B", accelerator_type="cpu", accelerator_count=0)]
    with pytest.raises(ValueError, match="No AIM with a CPU profile found"):
        get_smallest_cpu_servable_aim(aims, profiles)


def test_cpu_servable_returns_accelerator_model():
    aims = [_aim("meta-llama/Llama-3.1-8B-Instruct", "llama8b")]
    profiles = [
        _profile(
            "meta-llama/Llama-3.1-8B-Instruct",
            accelerator_type="cpu",
            accelerator_count=188,
            name="epyc-profile",
            accelerator_model="EPYC_9965",
        )
    ]
    assert get_smallest_cpu_servable_aim(aims, profiles, allow_gated=True) == (
        "llama8b",
        "epyc-profile",
        "EPYC_9965",
    )


def test_cpu_servable_picks_smallest_model_before_fewest_cpu_cores():
    aims = [_aim("org/Large-70B", "large"), _aim("org/Small-1B", "small")]
    profiles = [
        _profile("org/Large-70B", accelerator_type="cpu", accelerator_count=96, name="large-epyc"),
        _profile("org/Small-1B", accelerator_type="cpu", accelerator_count=188, name="small-epyc"),
    ]
    assert get_smallest_cpu_servable_aim(aims, profiles) == (
        "small",
        "small-epyc",
        "EPYC_ZEN4",
    )


def test_cpu_servable_picks_smallest_by_params_when_counts_tie():
    # Mirrors a target EPYC environment, where CPU profiles share one accelerator count.
    aims = [_aim("meta-llama/Llama-3.1-8B-Instruct", "llama8b"), _aim("google/gemma-4-E4B-it", "gemma4b")]
    profiles = [
        _profile("meta-llama/Llama-3.1-8B-Instruct", accelerator_type="cpu", accelerator_count=188),
        _profile("google/gemma-4-E4B-it", accelerator_type="cpu", accelerator_count=188, name="gemma-cpu"),
    ]
    assert get_smallest_cpu_servable_aim(aims, profiles, allow_gated=True) == (
        "gemma4b",
        "gemma-cpu",
        "EPYC_ZEN4",
    )
