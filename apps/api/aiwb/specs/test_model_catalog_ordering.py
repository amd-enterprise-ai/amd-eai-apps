# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for deployable AIM catalog ordering and model-level deduplication."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "libraries"))

from ModelCatalog import (  # noqa: E402
    get_second_smallest_deployable_aim,
    get_smallest_adapter_capable_aim,
    get_smallest_deployable_aim,
)


def _aim(resource_name, aim_id):
    return {"metadata": {"name": resource_name}, "status": {"status": "Ready", "aimId": aim_id}}


def _profile(aim_id, gpus, name=""):
    return {
        # A pin-able profile must be nameable; the catalog skips unnamed profiles.
        "metadata": {"name": name or f"{aim_id.replace('/', '-')}-{gpus}gpu"},
        "spec": {"aimId": aim_id, "acceleratorCount": gpus, "manualSelectionOnly": False},
        "status": {"status": "Ready", "matchingNodes": 1},
    }


def _adapter_profile(aim_id, name, gpus):
    return {
        "metadata": {"name": name},
        "spec": {"aimId": aim_id, "acceleratorCount": gpus, "features": ["adapters"]},
        "status": {"status": "Ready", "matchingNodes": 1},
    }


def test_newest_published_version_wins_a_tie():
    """Versions of one model tie on GPU and parameter count; the newest must win.

    String order would pick ``0-10-0`` (because ``1`` < ``9``), an old release that
    nothing else on the cluster deploys.
    """
    aim_id = "openai/gpt-oss-20b"
    aims = [
        _aim("amdenterpriseai-aim-openai-gpt-oss-20b-0-10-0-059b5d", aim_id),
        _aim("amdenterpriseai-aim-openai-gpt-oss-20b-0-9-0-601f10", aim_id),
        _aim("amdenterpriseai-aim-openai-gpt-oss-20b-0-11-1-83d542", aim_id),
        _aim("amdenterpriseai-aim-openai-gpt-oss-20b-0-11-0-51bf41", aim_id),
    ]

    selected = get_smallest_deployable_aim(aims, [_profile(aim_id, gpus=1)])

    assert selected == "amdenterpriseai-aim-openai-gpt-oss-20b-0-11-1-83d542"


def test_gpu_count_still_outranks_version():
    """Version only breaks ties — a smaller footprint always wins first."""
    small, big = "openai/gpt-oss-20b", "qwen/qwen3-20b"
    aims = [
        _aim("amdenterpriseai-aim-openai-gpt-oss-20b-0-9-0-601f10", small),
        _aim("amdenterpriseai-aim-qwen-qwen3-20b-0-13-0-31bb0f", big),
    ]
    profiles = [_profile(small, gpus=1), _profile(big, gpus=4)]

    selected = get_smallest_deployable_aim(aims, profiles)

    assert selected == "amdenterpriseai-aim-openai-gpt-oss-20b-0-9-0-601f10"


def test_first_and_second_pick_stay_distinct_across_models():
    """The dual-AIM setup needs two *different* models, so the two selectors must agree.

    Both read one shared order. Ranking separately is what let them disagree and hand
    the same model to both slots, failing the dual-AIM ``Should Not Be Equal``.
    """
    aims = [
        _aim("aaa-20b-0-9-0-abc111", "x/aaa-20b"),
        _aim("bbb-20b-2-0-0-abc222", "x/bbb-20b"),
        _aim("ccc-20b-1-0-0-abc333", "x/ccc-20b"),
    ]
    profiles = [_profile(aim_id, gpus=1) for aim_id in ("x/aaa-20b", "x/bbb-20b", "x/ccc-20b")]

    first = get_smallest_deployable_aim(aims, profiles)
    second = get_second_smallest_deployable_aim(aims, profiles)

    assert first == "aaa-20b-0-9-0-abc111"
    assert second == "bbb-20b-2-0-0-abc222"
    assert first != second


def test_release_of_one_model_does_not_reshuffle_other_models():
    """Version ranks releases of one model — it must not order different models.

    Release numbers of different models are not comparable, so letting one influence
    cross-model order means publishing a new release of an unrelated model silently
    changes which models the dual-AIM scenario deploys.
    """
    profiles = [_profile(aim_id, gpus=1) for aim_id in ("x/aaa-20b", "x/bbb-20b", "x/ccc-20b")]

    def picks(ccc_version):
        aims = [
            _aim("aaa-20b-1-0-0-abc111", "x/aaa-20b"),
            _aim("bbb-20b-1-0-0-abc222", "x/bbb-20b"),
            _aim(f"ccc-20b-{ccc_version}-abc333", "x/ccc-20b"),
        ]
        return get_smallest_deployable_aim(aims, profiles), get_second_smallest_deployable_aim(aims, profiles)

    assert picks("3-0-0") == picks("1-0-0") == ("aaa-20b-1-0-0-abc111", "bbb-20b-1-0-0-abc222")


def test_second_pick_is_a_different_model_not_an_older_release():
    """A model's older releases are removed before selecting the second model."""
    aim_id_a, aim_id_b = "x/aaa-20b", "x/bbb-20b"
    aims = [
        _aim("aaa-20b-0-9-0-abc111", aim_id_a),
        _aim("aaa-20b-1-2-0-abc444", aim_id_a),
        _aim("bbb-20b-0-1-0-abc222", aim_id_b),
    ]
    profiles = [_profile(aim_id_a, gpus=1), _profile(aim_id_b, gpus=1)]

    assert get_smallest_deployable_aim(aims, profiles) == "aaa-20b-1-2-0-abc444"
    assert get_second_smallest_deployable_aim(aims, profiles) == "bbb-20b-0-1-0-abc222"


def test_adapter_pick_is_not_reshuffled_by_another_models_release():
    """The adapter selector shares the two-scope rule: version never orders models."""
    profiles = [
        _adapter_profile("x/aaa-20b", "p-aaa", gpus=1),
        _adapter_profile("x/ccc-20b", "p-ccc", gpus=1),
    ]

    def pick(ccc_version):
        aims = [
            _aim("aaa-20b-1-0-0-abc111", "x/aaa-20b"),
            _aim(f"ccc-20b-{ccc_version}-abc333", "x/ccc-20b"),
        ]
        return get_smallest_adapter_capable_aim(aims, profiles)

    assert pick("3-0-0") == pick("1-0-0") == ("aaa-20b-1-0-0-abc111", "p-aaa")


def test_adapter_pick_uses_the_newest_release_of_the_chosen_model():
    """Within one model the newest release still represents it."""
    aim_id = "x/aaa-20b"
    aims = [
        _aim("aaa-20b-0-9-0-abc111", aim_id),
        _aim("aaa-20b-1-2-0-abc444", aim_id),
    ]

    selected, profile_name = get_smallest_adapter_capable_aim(aims, [_adapter_profile(aim_id, "p-aaa", gpus=1)])

    assert (selected, profile_name) == ("aaa-20b-1-2-0-abc444", "p-aaa")


def test_second_smallest_reports_too_few_distinct_models():
    """Several releases of one model still count as one dual-AIM candidate."""
    aim_id = "x/aaa-20b"
    aims = [
        _aim("aaa-20b-0-9-0-abc111", aim_id),
        _aim("aaa-20b-1-2-0-abc444", aim_id),
    ]

    with pytest.raises(ValueError, match="at least two"):
        get_second_smallest_deployable_aim(aims, [_profile(aim_id, gpus=1)])


def test_unversioned_names_sort_last_but_remain_selectable():
    """A name with no parseable version must not outrank a real release — or vanish."""
    aim_id = "openai/gpt-oss-20b"
    versioned = "amdenterpriseai-aim-openai-gpt-oss-20b-0-9-0-601f10"
    unversioned = "amdenterpriseai-aim-openai-gpt-oss-20b-preview"
    profiles = [_profile(aim_id, gpus=1)]

    assert get_smallest_deployable_aim([_aim(unversioned, aim_id), _aim(versioned, aim_id)], profiles) == versioned
    assert get_smallest_deployable_aim([_aim(unversioned, aim_id)], profiles) == unversioned
