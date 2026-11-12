# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for deciding which base models the fine-tuning catalog must offer, and for its token gating."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "libraries"))

from ModelCatalog import (
    assert_finetunable_models_report_hf_token_gating,
    assert_finetuning_catalog_offers,
    get_base_model_supported_gpus,
    get_recipes_the_cluster_should_offer,
    node_running_fine_tuning_job,
    node_should_have_a_supported_gpu,
)

_UNSET = object()


def _recipe(canonical_name: str, accelerators: object = _UNSET, aim_id: str | None = None) -> dict:
    metadata = {} if accelerators is _UNSET else {"compatibleAccelerators": accelerators}
    return {
        "canonicalName": canonical_name,
        "overlay": {"aimManifest": {"aimId": aim_id or canonical_name}, "metadata": metadata},
    }


def _profile(aim_id: str, status: str = "Ready") -> dict:
    return {"spec": {"aimId": aim_id}, "status": {"status": status}}


def _gpu(device_id: str) -> dict:
    return {"acceleratorType": "gpu", "deviceId": device_id}


@pytest.mark.parametrize(
    ("node_device_id", "recipe_device_id"),
    [("75a8", "0x75a8"), ("75a8", "0X75A8"), ("0x75a8", "75a8"), ("74a1", "74a1"), ("7448", 7448)],
)
def test_recipe_is_expected_however_either_side_writes_the_gpu_id(
    node_device_id: str, recipe_device_id: object
) -> None:
    expected = get_recipes_the_cluster_should_offer(
        [_recipe("example/Model-8B", [recipe_device_id])], [_profile("example/Model-8B")], [_gpu(node_device_id)]
    )

    assert expected == ["example/Model-8B"]


def test_recipe_declaring_no_gpus_is_expected_on_any_hardware() -> None:
    expected = get_recipes_the_cluster_should_offer(
        [_recipe("example/Model-8B")], [_profile("example/Model-8B")], [_gpu("74a1")]
    )

    assert expected == ["example/Model-8B"]


@pytest.mark.parametrize("node_device_id", ["74a1", "75a8"])
def test_model_with_a_recipe_per_gpu_family_is_expected_on_either_family(node_device_id: str) -> None:
    recipes = [_recipe("example/Model-32B", ["74a1"]), _recipe("example/Model-32B", ["0x75a8"])]

    expected = get_recipes_the_cluster_should_offer(recipes, [_profile("example/Model-32B")], [_gpu(node_device_id)])

    assert expected == ["example/Model-32B"]


def test_api_overlay_does_not_stand_in_for_a_model_with_recipe_files() -> None:
    recipe_file = {**_recipe("example/Model-32B", ["74a1"]), "sourcePath": "overrides/models/Model-32B.yaml"}
    api_overlay = _recipe("example/Model-32B", ["75a8"])

    expected = get_recipes_the_cluster_should_offer(
        [recipe_file, api_overlay], [_profile("example/Model-32B")], [_gpu("75a8")]
    )

    assert expected == []


def test_api_overlay_is_expected_for_a_model_without_recipe_files() -> None:
    expected = get_recipes_the_cluster_should_offer(
        [_recipe("example/Model-32B", ["75a8"])], [_profile("example/Model-32B")], [_gpu("75a8")]
    )

    assert expected == ["example/Model-32B"]


@pytest.mark.parametrize(
    ("recipe", "profiles", "accelerators"),
    [
        pytest.param(_recipe("example/A-1B", ["0x75a8"]), [_profile("example/A-1B")], [_gpu("74a1")], id="other-gpu"),
        pytest.param(_recipe("example/A-1B", []), [_profile("example/A-1B")], [_gpu("74a1")], id="declares-none"),
        pytest.param(
            _recipe("example/A-1B", ["74a1"]),
            [_profile("example/A-1B", status="NotAvailable")],
            [_gpu("74a1")],
            id="profile-not-ready",
        ),
        pytest.param(_recipe("example/A-1B", ["74a1"]), [], [_gpu("74a1")], id="no-profile"),
        pytest.param({"canonicalName": None, "overlay": {}}, [], [_gpu("74a1")], id="generic-overlay"),
    ],
)
def test_recipe_is_not_expected_when_the_cluster_cannot_offer_it(
    recipe: dict, profiles: list, accelerators: list
) -> None:
    assert get_recipes_the_cluster_should_offer([recipe], profiles, accelerators) == []


def _node(labels: dict) -> dict:
    return {"metadata": {"name": "gpu-node", "labels": labels}}


@pytest.mark.parametrize(
    "labels",
    [{"amd.com/gpu.device-id": "75a8"}, {"beta.amd.com/gpu.device-id": "75a8"}],
)
def test_job_on_a_node_with_a_supported_gpu_passes(labels: dict) -> None:
    node_should_have_a_supported_gpu(_node(labels), ["0x75a8"])


def test_job_on_another_gpu_family_names_the_node() -> None:
    with pytest.raises(AssertionError, match="gpu-node"):
        node_should_have_a_supported_gpu(_node({"amd.com/gpu.device-id": "74a1"}), ["0x75a8"])


def test_job_on_a_node_without_gpu_labels_fails() -> None:
    with pytest.raises(AssertionError, match="unknown"):
        node_should_have_a_supported_gpu(_node({}), ["0x75a8"])


def test_base_model_supported_gpus_are_read_as_strings() -> None:
    models = [{"canonicalName": "example/A-1B", "compatibleAccelerators": [7448, "0x75a8"]}]

    assert get_base_model_supported_gpus(models, "example/A-1B") == ["7448", "0x75a8"]


def test_unscheduled_job_keeps_the_caller_waiting() -> None:
    with pytest.raises(AssertionError, match="no pod placed"):
        node_running_fine_tuning_job([{"spec": {}}])


def test_catalog_offering_every_expected_model_passes() -> None:
    models = [{"canonicalName": "example/A-1B"}, {"canonicalName": "example/B-1B"}]

    assert_finetuning_catalog_offers(models, ["example/A-1B"])


def test_catalog_missing_an_expected_model_names_it() -> None:
    with pytest.raises(AssertionError, match=r"\['example/B-1B'\]"):
        assert_finetuning_catalog_offers([{"canonicalName": "example/A-1B"}], ["example/A-1B", "example/B-1B"])


def test_open_gemma_4_model_passes_token_gating() -> None:
    assert_finetunable_models_report_hf_token_gating(
        [{"canonicalName": "google/gemma-4-31b-it", "hfTokenRequired": False}]
    )


def test_earlier_gemma_reported_as_open_still_fails_token_gating() -> None:
    with pytest.raises(AssertionError, match="gated family"):
        assert_finetunable_models_report_hf_token_gating(
            [{"canonicalName": "google/gemma-3-27b-it", "hfTokenRequired": False}]
        )
