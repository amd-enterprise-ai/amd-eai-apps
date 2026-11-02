# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Regression coverage for the dual-AIM fixture's combined GPU quota sizing.

AIM-B's own auto-selected profile can need more GPUs than AIM-A's, so the fixture
must size project quota to their SUM before deploying AIM-B, not assume a fixed
GPU count covers both. Without this, a second model that needs more GPUs than the
project's original allowance silently exceeds quota and the deploy hangs waiting
to schedule instead of failing fast.

Sizing the quota to a GPU count alone is not enough: aim-engine is free to resolve
ANY eligible auto-selectable profile for an aimId at deploy time when the deploy
payload omits profileName, including one needing more GPUs than the one a caller
costed quota for. So the fixture must also pin the EXACT profile name it costed
into the deploy payload's profileName field -- both for AIM-A (pinned at initial
selection) and AIM-B (pinned right before its own deploy).
"""

import sys
from pathlib import Path

import pytest

SPECS_DIR = Path(__file__).resolve().parent
AIWB_AIMS_RESOURCE = SPECS_DIR / "resources" / "aiwb_aims.resource"
API_KEYS_AIMS_RESOURCE = SPECS_DIR / "resources" / "aims" / "api_keys.resource"

sys.path.insert(0, str(SPECS_DIR / "libraries"))

from ModelCatalog import (  # noqa: E402
    OVERRIDE_FALLBACK_GPU_COUNT,
    get_deployable_aim_gpu_count,
    get_deployable_aim_profile,
    get_deployable_aim_profile_or_none,
    get_model_resource_quota,
    get_profile_gpu_count,
    get_second_smallest_deployable_aim_with_gpu_count,
    get_second_smallest_deployable_aim_with_profile,
    get_smallest_deployable_aim_with_profile,
)


def _block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.rstrip() == name)
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def _aim(resource_name: str, aim_id: str) -> dict:
    return {"metadata": {"name": resource_name}, "status": {"status": "Ready", "aimId": aim_id}}


def _profile(aim_id: str, gpus: int, name: str) -> dict:
    return {
        "metadata": {"name": name},
        "spec": {"aimId": aim_id, "acceleratorCount": gpus, "manualSelectionOnly": False},
        "status": {"status": "Ready", "matchingNodes": 1},
    }


def test_dual_aim_fixture_sums_both_selected_models_before_second_deploy() -> None:
    """AIM-B's deploy must be preceded by a quota sized to AIM-A + AIM-B, not a fixed guess."""
    resource = API_KEYS_AIMS_RESOURCE.read_text()
    selection = _block(resource, "Second smallest deployable AIM resource name, profile and GPU count")
    deploy = _block(resource, "A second AIM model is running")

    assert "Get Second Smallest Deployable Aim With Profile" in selection

    # Quota sizing goes through the shared `Set project quota for model GPU count` wrapper,
    # which resolves the CPU/memory footprint via Get Model Resource Quota before applying it.
    assert "Set project quota for model GPU count" in deploy
    assert "int($saved_gpu_count) + int($aim_b_gpu_count)" in deploy
    assert deploy.index("Set project quota for model GPU count") < deploy.index("AIM is deployed and running"), (
        "project quota must be sized before AIM-B is deployed, not after"
    )


def test_dual_aim_fixture_pins_aim_b_profile_before_deploy() -> None:
    """AIM-B's exact selected profile name -- not just its GPU count -- must be pinned into
    TEST_AIM_PROFILE_NAME before deploy, so aim-engine cannot resolve a different, larger
    eligible profile for the same aimId at deploy time."""
    resource = API_KEYS_AIMS_RESOURCE.read_text()
    deploy = _block(resource, "A second AIM model is running")

    pin_profile = deploy.index("${TEST_AIM_PROFILE_NAME}    ${aim_b_profile_name}    scope=TEST")
    pin_gpu_count = deploy.index("${TEST_AIM_GPU_COUNT}    ${aim_b_gpu_count}    scope=TEST")
    deploy_call = deploy.index("AIM is deployed and running")

    assert pin_profile < deploy_call
    assert pin_gpu_count < deploy_call


def test_dual_aim_fixture_restores_aim_a_selection_state_after_aim_b_deploy() -> None:
    """AIM-A's name/id/host/profile/GPU-count must all be restored once AIM-B's own state is
    captured -- a stale AIM-B profile pin left in place would corrupt any later deploy that
    reuses TEST_AIM_PROFILE_NAME for AIM-A."""
    resource = API_KEYS_AIMS_RESOURCE.read_text()
    deploy = _block(resource, "A second AIM model is running")

    capture_b = deploy.index("${TEST_AIM_B_EXTERNAL_HOST}")
    restore_name = deploy.index("${TEST_AIM_NAME}    ${saved_aim_name}")
    restore_id = deploy.index("${TEST_AIM_ID}    ${saved_aim_id}")
    restore_host = deploy.index("${TEST_AIM_EXTERNAL_HOST}    ${saved_ext_host}")
    restore_profile = deploy.index("${TEST_AIM_PROFILE_NAME}    ${saved_profile_name}")
    restore_gpu_count = deploy.index("${TEST_AIM_GPU_COUNT}    ${saved_gpu_count}")

    assert capture_b < restore_name
    assert capture_b < restore_id
    assert capture_b < restore_host
    assert capture_b < restore_profile
    assert capture_b < restore_gpu_count


def test_deploy_payload_pins_profile_name_when_test_aim_profile_name_is_set() -> None:
    """The shared deploy-payload builder must carry TEST_AIM_PROFILE_NAME into profileName,
    since every default AIM deploy in the suite builds its payload through this keyword."""
    resource = AIWB_AIMS_RESOURCE.read_text()
    prepare = _block(resource, "Valid AIM deploy data is prepared")

    assert "Get Variable Value" in prepare
    assert "${TEST_AIM_PROFILE_NAME}" in prepare
    assert "profileName=${profile_name}" in prepare
    assert prepare.index("profileName=${profile_name}") < prepare.index("hfToken=${hf_secret}")


def test_an_aim_exists_in_system_pins_profile_and_gpu_count_on_fresh_selection() -> None:
    """A fresh automatic selection must pin both TEST_AIM_PROFILE_NAME and TEST_AIM_GPU_COUNT."""
    resource = AIWB_AIMS_RESOURCE.read_text()
    keyword = _block(resource, "An AIM exists in system")

    assert "Smallest deployable AIM resource name, profile and GPU count" in keyword
    assert "VAR    ${TEST_AIM_PROFILE_NAME}" in keyword
    assert "VAR    ${TEST_AIM_GPU_COUNT}" in keyword


def test_an_aim_exists_in_system_backfill_reads_the_running_services_resolved_profile() -> None:
    """The backfill path for an already-selected (but not-yet-repinned) AIM must cost the
    RUNNING service's actual status.resolvedProfile, not a fresh catalog-minimum lookup --
    catalog profile availability/ranking can drift over a suite, so re-deriving "the current
    smallest eligible profile" can under-cost a service that is already running a larger one."""
    resource = AIWB_AIMS_RESOURCE.read_text()
    keyword = _block(resource, "An AIM exists in system")

    find_existing = keyword.index("Find Existing AIM Service")
    read_resolved = keyword.index("$existing_status.get('resolvedProfile')")
    resolved_branch = keyword.index("IF    $resolved_profile is not None")
    profile_gpu_count = keyword.index("Get Profile Gpu Count")
    catalog_fallback = keyword.index("Get Deployable Aim Profile Or None")

    assert find_existing < read_resolved < resolved_branch < profile_gpu_count
    # The catalog-minimum lookup must only be reached when no resolvedProfile was found
    # (no service yet), never used to override an already-running service's real profile.
    assert resolved_branch < catalog_fallback


def test_an_aim_exists_in_system_backfill_tolerates_an_unplaceable_override() -> None:
    """AIM_RESOURCE_OVERRIDE is documented to work on clusters where catalog profile
    provisioning is incomplete, so the pre-deploy backfill path must not raise when the
    pinned AIM has no auto-selectable profile -- it must leave the pin unset instead, so the
    deploy payload falls back to omitting profileName."""
    resource = AIWB_AIMS_RESOURCE.read_text()
    keyword = _block(resource, "An AIM exists in system")

    or_none_call = keyword.index("Get Deployable Aim Profile Or None")
    guard = keyword.index("IF    $profile_name is not None")
    pin = keyword.index("VAR    ${TEST_AIM_PROFILE_NAME}    ${profile_name}    scope=TEST")

    assert or_none_call < guard < pin, (
        "pinning must be gated on the lookup actually returning a profile, not unconditional"
    )


def test_an_aim_exists_in_system_backfill_pins_gpu_count_even_when_no_profile_is_placeable() -> None:
    """The GPU-count pin from the catalog-incomplete-override fallback must NOT be gated behind
    the same "$profile_name is not None" guard as the profile-name pin -- Get Deployable Aim
    Profile Or None always returns a concrete gpu_count now (never ${None}), and that value must
    reach TEST_AIM_GPU_COUNT even on the branch where no profile can be pinned, or the dual-AIM
    fixture's later `int($saved_gpu_count) + int($aim_b_gpu_count)` raises on int(None)."""
    resource = AIWB_AIMS_RESOURCE.read_text()
    keyword = _block(resource, "An AIM exists in system")

    or_none_call = keyword.index("Get Deployable Aim Profile Or None")
    gpu_count_pin = keyword.index("VAR    ${TEST_AIM_GPU_COUNT}    ${gpu_count}    scope=TEST")
    guard_end = keyword.index("END", keyword.index("IF    $profile_name is not None"))

    assert or_none_call < gpu_count_pin
    # The GPU-count pin must sit AFTER the profile-name-only IF block closes, i.e. outside it.
    assert guard_end < gpu_count_pin


def test_second_smallest_gpu_count_selector_can_exceed_the_first_models_need() -> None:
    """AIM-B is picked purely by size ranking, so it is not capped at AIM-A's GPU count."""
    aim_a_id, aim_b_id = "example/model-a-1b", "example/model-b-70b"
    aims = [_aim("model-a-1b-0-1-0-abc111", aim_a_id), _aim("model-b-70b-0-1-0-abc222", aim_b_id)]
    profiles = [
        _profile(aim_a_id, gpus=1, name="model-a-1gpu"),
        _profile(aim_b_id, gpus=2, name="model-b-2gpu"),
    ]

    resource_name, gpu_count = get_second_smallest_deployable_aim_with_gpu_count(aims, profiles)

    assert resource_name == "model-b-70b-0-1-0-abc222"
    assert gpu_count == 2


def test_deployable_aim_gpu_count_resolves_an_already_selected_model() -> None:
    """AIM-A's GPU need is looked up fresh from the catalog, not assumed to be 1."""
    aim_a_id = "example/model-a-8b"
    aims = [_aim("model-a-8b-0-1-0-abc111", aim_a_id)]
    profiles = [_profile(aim_a_id, gpus=3, name="model-a-3gpu")]

    assert get_deployable_aim_gpu_count(aims, profiles, "model-a-8b-0-1-0-abc111") == 3


def test_deployable_aim_gpu_count_rejects_an_unknown_resource_name() -> None:
    aim_id = "example/model-a-8b"
    aims = [_aim("model-a-8b-0-1-0-abc111", aim_id)]
    profiles = [_profile(aim_id, gpus=1, name="model-a-1gpu")]

    with pytest.raises(ValueError, match="not found in catalog"):
        get_deployable_aim_gpu_count(aims, profiles, "does-not-exist")


def test_dual_aim_quota_cannot_silently_exceed_a_fixed_two_gpu_allowance() -> None:
    """Regression guard: a combined need above the old fixed 2-GPU quota must be sized up,
    not silently truncated back down to 2."""
    aim_a_id, aim_b_id = "example/model-a-1b", "example/model-b-70b"
    aims = [_aim("model-a-1b-0-1-0-abc111", aim_a_id), _aim("model-b-70b-0-1-0-abc222", aim_b_id)]
    # AIM-A needs 1 GPU, AIM-B (second-smallest) needs 2 -- combined need (3) exceeds the
    # project's old fixed two-GPU quota.
    profiles = [
        _profile(aim_a_id, gpus=1, name="model-a-1gpu"),
        _profile(aim_b_id, gpus=2, name="model-b-2gpu"),
    ]

    aim_a_gpu_count = get_deployable_aim_gpu_count(aims, profiles, "model-a-1b-0-1-0-abc111")
    _, aim_b_gpu_count = get_second_smallest_deployable_aim_with_gpu_count(aims, profiles)
    combined_gpu_count = aim_a_gpu_count + aim_b_gpu_count

    assert combined_gpu_count == 3
    assert combined_gpu_count > 2, "this regression only guards a combined need above the old fixed quota"

    gpu_count, cpu_milli_cores, memory_bytes = get_model_resource_quota(combined_gpu_count)
    assert gpu_count == 3
    assert cpu_milli_cores == 12_000
    assert memory_bytes == 103_079_215_104


def test_deployable_aim_profile_selects_the_smaller_of_multiple_eligible_profiles() -> None:
    """When an aimId publishes more than one auto-selectable profile, the smallest is
    selected and its EXACT profile name -- not merely a matching GPU count -- is returned,
    so it can be pinned into the deploy payload."""
    aim_id = "example/model-a-8b"
    aims = [_aim("model-a-8b-0-1-0-abc111", aim_id)]
    profiles = [
        _profile(aim_id, gpus=1, name="model-a-8b-1gpu"),
        _profile(aim_id, gpus=3, name="model-a-8b-3gpu"),
    ]

    profile_name, gpu_count = get_deployable_aim_profile(aims, profiles, "model-a-8b-0-1-0-abc111")

    assert profile_name == "model-a-8b-1gpu"
    assert gpu_count == 1


def test_smallest_deployable_aim_with_profile_ignores_a_larger_eligible_sibling_profile() -> None:
    """`Get Smallest Deployable Aim With Profile` must return the smallest model's smallest
    eligible profile, not be confused by a larger sibling profile also being eligible for the
    same aimId."""
    aim_id = "example/model-a-8b"
    aims = [_aim("model-a-8b-0-1-0-abc111", aim_id)]
    profiles = [
        _profile(aim_id, gpus=1, name="model-a-8b-1gpu"),
        _profile(aim_id, gpus=4, name="model-a-8b-4gpu"),
    ]

    resource_name, profile_name, gpu_count = get_smallest_deployable_aim_with_profile(aims, profiles)

    assert resource_name == "model-a-8b-0-1-0-abc111"
    assert profile_name == "model-a-8b-1gpu"
    assert gpu_count == 1


def test_second_smallest_with_profile_pins_the_exact_profile_not_just_a_matching_count() -> None:
    """AIM-B's aimId has two eligible profiles (2 GPU and 4 GPU). The selector must return
    the smaller one's EXACT profile name -- proving that pinning by name, not by GPU count
    alone, is what prevents aim-engine from substituting the larger eligible profile."""
    aim_a_id, aim_b_id = "example/model-a-1b", "example/model-b-70b"
    aims = [_aim("model-a-1b-0-1-0-abc111", aim_a_id), _aim("model-b-70b-0-1-0-abc222", aim_b_id)]
    profiles = [
        _profile(aim_a_id, gpus=1, name="model-a-1gpu"),
        _profile(aim_b_id, gpus=2, name="model-b-2gpu"),
        _profile(aim_b_id, gpus=4, name="model-b-4gpu"),
    ]

    resource_name, profile_name, gpu_count = get_second_smallest_deployable_aim_with_profile(aims, profiles)

    assert resource_name == "model-b-70b-0-1-0-abc222"
    assert profile_name == "model-b-2gpu"
    assert gpu_count == 2


def test_combined_quota_is_sized_to_the_pinned_profile_not_an_unrelated_larger_eligible_one() -> None:
    """The combined quota must reflect the sum of the EXACT profiles pinned for deploy
    (1 + 2 = 3 GPUs), not a total that assumes a larger, also-eligible profile for AIM-B
    could be substituted (1 + 4 = 5) -- proving quota sizing and the profile actually pinned
    into the deploy payload share one source of truth."""
    aim_a_id, aim_b_id = "example/model-a-1b", "example/model-b-70b"
    aims = [_aim("model-a-1b-0-1-0-abc111", aim_a_id), _aim("model-b-70b-0-1-0-abc222", aim_b_id)]
    profiles = [
        _profile(aim_a_id, gpus=1, name="model-a-1gpu"),
        # AIM-B's aimId has two eligible profiles; only the smaller one may drive the quota.
        _profile(aim_b_id, gpus=2, name="model-b-2gpu"),
        _profile(aim_b_id, gpus=4, name="model-b-4gpu"),
    ]

    aim_a_profile_name, aim_a_gpu_count = get_deployable_aim_profile(aims, profiles, "model-a-1b-0-1-0-abc111")
    _, aim_b_profile_name, aim_b_gpu_count = get_second_smallest_deployable_aim_with_profile(aims, profiles)
    combined_gpu_count = aim_a_gpu_count + aim_b_gpu_count

    assert aim_a_profile_name == "model-a-1gpu"
    assert aim_b_profile_name == "model-b-2gpu"
    assert combined_gpu_count == 3, "quota must size to the profile actually pinned (2 GPUs)"
    assert combined_gpu_count != 5, "must not silently size to the larger, unpinned eligible profile (4 GPUs)"

    gpu_count, cpu_milli_cores, memory_bytes = get_model_resource_quota(combined_gpu_count)
    assert gpu_count == 3
    assert cpu_milli_cores == 12_000
    assert memory_bytes == 103_079_215_104


def test_model_resource_quota_scales_linearly_with_gpu_count() -> None:
    assert get_model_resource_quota(2) == (2, 8_000, 68_719_476_736)
    assert get_model_resource_quota(3) == (3, 12_000, 103_079_215_104)


def test_model_resource_quota_rejects_non_positive_gpu_counts() -> None:
    for bad in (0, -1):
        with pytest.raises(ValueError, match="positive integer"):
            get_model_resource_quota(bad)


def test_profile_gpu_count_reads_the_named_profile_not_the_catalog_minimum() -> None:
    """An already-running AIM's resolvedProfile may not be the aimId's current catalog
    minimum (e.g. catalog ranking changed since it was deployed). Get Profile Gpu Count must
    return the count of the EXACT named profile, proving it does not fall back to
    re-deriving "the smallest eligible profile for this aimId" ranking logic."""
    aim_id = "example/model-a-8b"
    profiles = [
        _profile(aim_id, gpus=1, name="model-a-8b-1gpu"),
        _profile(aim_id, gpus=4, name="model-a-8b-4gpu"),
    ]

    assert get_profile_gpu_count(profiles, "model-a-8b-4gpu") == 4
    assert get_profile_gpu_count(profiles, "model-a-8b-1gpu") == 1


def test_profile_gpu_count_rejects_an_unknown_profile_name() -> None:
    profiles = [_profile("example/model-a-8b", gpus=1, name="model-a-8b-1gpu")]

    with pytest.raises(ValueError, match="not found in catalog"):
        get_profile_gpu_count(profiles, "does-not-exist")


def test_deployable_aim_profile_or_none_returns_a_concrete_gpu_count_for_an_unplaceable_override() -> None:
    """AIM_RESOURCE_OVERRIDE is documented to work even when the pinned AIM has no
    auto-selectable profile in the catalog (incomplete profile provisioning). The or_none
    variant must return profile_name=None for that specific condition instead of raising, but
    gpu_count must still be a real number -- never None -- so a caller summing it into a
    combined-quota calculation (the dual-AIM fixture) does not crash on int(None). Here the
    aimId has one non-auto-selectable (manualSelectionOnly) profile, so its own
    acceleratorCount is used rather than the no-profile-at-all fallback constant."""
    aim_id = "example/model-a-8b"
    aims = [_aim("model-a-8b-0-1-0-abc111", aim_id)]
    # Not auto-selectable (manualSelectionOnly), but still real profile data for this aimId.
    profiles = [
        {
            "metadata": {"name": "model-a-8b-manual-only"},
            "spec": {"aimId": aim_id, "acceleratorCount": 5, "manualSelectionOnly": True},
            "status": {"status": "Ready", "matchingNodes": 1},
        }
    ]

    profile_name, gpu_count = get_deployable_aim_profile_or_none(aims, profiles, "model-a-8b-0-1-0-abc111")

    assert profile_name is None
    assert gpu_count == 5


def test_deployable_aim_profile_or_none_falls_back_to_a_constant_when_no_profile_data_exists() -> None:
    """When the aimId has no profile data of any kind (not even a non-auto-selectable one),
    fall back to OVERRIDE_FALLBACK_GPU_COUNT rather than returning None -- so the combined
    quota still gets a real, if conservative, number instead of crashing on int(None)."""
    aim_id = "example/model-a-8b"
    aims = [_aim("model-a-8b-0-1-0-abc111", aim_id)]
    other_aim_profiles_only = [_profile("example/some-other-model", gpus=1, name="other-model-1gpu")]

    profile_name, gpu_count = get_deployable_aim_profile_or_none(
        aims, other_aim_profiles_only, "model-a-8b-0-1-0-abc111"
    )

    assert profile_name is None
    assert gpu_count == OVERRIDE_FALLBACK_GPU_COUNT


def test_dual_aim_quota_flow_survives_an_unplaceable_aim_a_override() -> None:
    """End-to-end regression through the real consumer flow (not just the helper's own return
    value): when AIM-A is a catalog-incomplete AIM_RESOURCE_OVERRIDE with no auto-selectable
    profile, `get_deployable_aim_profile_or_none`'s gpu_count must be usable directly by the
    same int($saved_gpu_count) + int($aim_b_gpu_count) arithmetic the dual-AIM fixture
    (aims/api_keys.resource, "A second AIM model is running") performs, and the resulting
    combined quota must still be sizeable via get_model_resource_quota -- proving the fix all
    the way through the quota flow a catalog-incomplete override actually hits, not merely that
    the helper returns two values."""
    aim_a_id, aim_b_id, aim_c_id = "example/model-a-override", "example/model-b-70b", "example/model-c-8b"
    aims = [
        # AIM-A: the AIM_RESOURCE_OVERRIDE pin. It is not part of the auto-deployable candidate
        # pool at all (no profile of its own), same as a real catalog-incomplete override --
        # AIM-B is picked from the OTHER Ready AIMs' ranking, independent of AIM-A.
        _aim("model-a-override-0-1-0-abc111", aim_a_id),
        _aim("model-c-8b-0-1-0-abc333", aim_c_id),
        _aim("model-b-70b-0-1-0-abc222", aim_b_id),
    ]
    # AIM-A's aimId has NO auto-selectable profile at all (catalog-incomplete provisioning) --
    # exactly the condition AIM_RESOURCE_OVERRIDE is documented to tolerate. AIM-C and AIM-B
    # are the two real auto-deployable candidates AIM-B's selector ranks between.
    profiles = [
        _profile(aim_c_id, gpus=1, name="model-c-1gpu"),
        _profile(aim_b_id, gpus=2, name="model-b-2gpu"),
    ]

    aim_a_profile_name, aim_a_gpu_count = get_deployable_aim_profile_or_none(
        aims, profiles, "model-a-override-0-1-0-abc111"
    )
    assert aim_a_profile_name is None
    assert aim_a_gpu_count == OVERRIDE_FALLBACK_GPU_COUNT

    aim_b_resource_name, aim_b_gpu_count = get_second_smallest_deployable_aim_with_gpu_count(aims, profiles)
    assert aim_b_resource_name == "model-b-70b-0-1-0-abc222"

    # This is the exact expression `A second AIM model is running` evaluates against
    # $saved_gpu_count / $aim_b_gpu_count; it must not raise TypeError on int(None).
    combined_gpu_count = int(aim_a_gpu_count) + int(aim_b_gpu_count)
    assert combined_gpu_count == OVERRIDE_FALLBACK_GPU_COUNT + 2

    gpu_count, cpu_milli_cores, memory_bytes = get_model_resource_quota(combined_gpu_count)
    assert gpu_count == combined_gpu_count
    assert cpu_milli_cores == combined_gpu_count * 4_000
    assert memory_bytes == combined_gpu_count * 32 * 1024**3


def test_deployable_aim_profile_or_none_still_rejects_an_unknown_resource_name() -> None:
    """A resource_name absent from the catalog entirely is a genuine caller/test bug, not the
    documented incomplete-provisioning condition -- it must still raise."""
    aim_id = "example/model-a-8b"
    aims = [_aim("model-a-8b-0-1-0-abc111", aim_id)]
    profiles = [_profile(aim_id, gpus=1, name="model-a-8b-1gpu")]

    with pytest.raises(ValueError, match="not found in catalog"):
        get_deployable_aim_profile_or_none(aims, profiles, "does-not-exist")
