# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import copy
from typing import Any

import pytest

from app.models.hyperparameters import (
    BATCH_SIZE_PATH,
    EPOCHS_PATH,
    LEARNING_RATE_PATH,
    LORA_PEFT_KEYS,
    merge_helm_values,
    resolve_hyperparameters,
)
from app.models.schemas import LoraHyperparameters, TrainingType

# Mirrors overrides/dev-center/signature.yaml, the chart-wide layer every recipe merges over.
# `total_train_batch_size` is declared with no value, which is why no shipped recipe advertises a
# batch size: a submission that names none leaves the key unset rather than resolving it here.
CHART_SIGNATURE: dict[str, Any] = {
    "kaiwo": {"enabled": False},
    "runTensorboard": False,
    "checkpointsRemote": None,
    "basemodel": None,
    "finetuning_config": {
        "data_conf": {"training_data": {"datasets": [{"path": None}]}},
        "batchsize_conf": {"total_train_batch_size": None},
        "overrides": {"lr_multiplier": 1.0},
        "training_args": {"num_train_epochs": 1},
    },
}

# Mirrors the peft_kwargs block of overrides/models/Qwen_Qwen3-32B.yaml, including the float
# spelling of lora_alpha and the target_modules list the platform must never choose itself.
REAL_PEFT_KWARGS: dict[str, Any] = {
    "r": 64,
    "lora_alpha": 16.0,
    "lora_dropout": 0.05,
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
}


# Every field is required, so the recipe-declares-nothing case has to be spelled out.
ALL_NULL_LORA = LoraHyperparameters(rank=None, alpha=None, dropout=None)


_UNSET = object()


def make_recipe(
    *,
    training_type: str | None = None,
    peft_conf: Any = None,
    training_args: dict[str, Any] | None = None,
    batchsize_conf: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
    finetuning_config: Any = _UNSET,
) -> dict[str, Any]:
    """Build a recipe overlay shaped like overrides/models/*.yaml.

    `training_type` omitted leaves `metadata.trainingType` undeclared, the shape two of the six
    shipped recipes have. `finetuning_config` replaces the whole block, for malformed-recipe cases.
    """
    metadata: dict[str, Any] = {"hfTokenRequired": False, "compatibleAccelerators": ["74a1"]}
    if training_type is not None:
        metadata["trainingType"] = training_type

    if finetuning_config is _UNSET:
        finetuning_config = {
            "method": "sft",
            "training_args": {"learning_rate": 0.000005, "seed": 42, **(training_args or {})},
            "batchsize_conf": {"max_per_device_train_batch_size": 1, **(batchsize_conf or {})},
        }
        if overrides is not None:
            finetuning_config["overrides"] = overrides
        if peft_conf is not None:
            finetuning_config["peft_conf"] = peft_conf

    return {
        "metadata": metadata,
        "model": "acme/base-model",
        "finetuningGpus": 1,
        "finetuning_config": finetuning_config,
        "aimManifest": {"modelId": "acme/base-model", "aimId": "acme/base-model"},
    }


def lora_peft_conf(**kwargs: Any) -> dict[str, Any]:
    return {"peft_type": "LORA", "task_type": "CAUSAL_LM", "peft_kwargs": {**REAL_PEFT_KWARGS, **kwargs}}


# ============================================================================
# Merge semantics
# ============================================================================


def test_merge_helm_values_merges_maps_key_by_key() -> None:
    merged = merge_helm_values([{"a": {"x": 1, "y": 2}}, {"a": {"y": 3, "z": 4}}])

    assert merged == {"a": {"x": 1, "y": 3, "z": 4}}


def test_merge_helm_values_applies_layers_lowest_precedence_first() -> None:
    merged = merge_helm_values([{"n": 1}, {"n": 2}, {"n": 3}])

    assert merged == {"n": 3}


def test_merge_helm_values_replaces_lists_wholesale() -> None:
    """A recipe that names two target_modules means two, not the chart's four plus its own."""
    merged = merge_helm_values([{"targets": ["a", "b", "c"]}, {"targets": ["x"]}])

    assert merged == {"targets": ["x"]}


def test_merge_helm_values_replaces_a_map_with_a_scalar() -> None:
    merged = merge_helm_values([{"peft_conf": {"peft_kwargs": {"r": 64}}}, {"peft_conf": "NO_PEFT"}])

    assert merged == {"peft_conf": "NO_PEFT"}


def test_merge_helm_values_lets_an_explicit_null_clear_a_lower_layer() -> None:
    """A recipe that deliberately blanks a chart default must not have it revived by the merge.

    Reporting the chart's value there would advertise a default the job never trains with.
    """
    merged = merge_helm_values(
        [
            {"finetuning_config": {"overrides": {"lr_multiplier": 1.0}}},
            {"finetuning_config": {"overrides": {"lr_multiplier": None}}},
        ]
    )

    assert merged["finetuning_config"]["overrides"]["lr_multiplier"] is None
    assert resolve_hyperparameters(merged).learning_rate is None


def test_merge_helm_values_keeps_a_lower_layer_key_the_higher_layer_omits() -> None:
    merged = merge_helm_values([{"a": {"x": 1}}, {"a": {"y": 2}}])

    assert merged == {"a": {"x": 1, "y": 2}}


def test_merge_helm_values_leaves_its_layers_untouched() -> None:
    base = {"finetuning_config": {"training_args": {"num_train_epochs": 1}}}
    layer = {"finetuning_config": {"training_args": {"num_train_epochs": 9}}}
    base_before, layer_before = copy.deepcopy(base), copy.deepcopy(layer)

    merge_helm_values([base, layer])

    assert base == base_before
    assert layer == layer_before


def test_merge_helm_values_does_not_carry_one_merge_into_the_next_over_a_shared_base() -> None:
    """The listing merges every recipe over the same chart signature object, one after another."""
    signature = copy.deepcopy(CHART_SIGNATURE)
    loud = make_recipe(
        training_type=TrainingType.LORA.value, peft_conf=lora_peft_conf(), training_args={"num_train_epochs": 7}
    )

    merge_helm_values([signature, loud])
    quiet = merge_helm_values([signature, make_recipe()])

    assert quiet["finetuning_config"]["training_args"]["num_train_epochs"] == 1
    assert "peft_conf" not in quiet["finetuning_config"]


# ============================================================================
# Reading a recipe
# ============================================================================


def test_resolve_reads_the_values_a_lora_recipe_declares() -> None:
    values = merge_helm_values(
        [
            CHART_SIGNATURE,
            make_recipe(
                training_type=TrainingType.LORA.value,
                peft_conf=lora_peft_conf(),
                training_args={"num_train_epochs": 3},
                overrides={"lr_multiplier": 0.5},
            ),
        ]
    )

    resolved = resolve_hyperparameters(values)

    assert resolved.epochs == 3
    assert resolved.learning_rate == 0.5
    assert resolved.lora == LoraHyperparameters(rank=64, alpha=16, dropout=0.05)


def test_resolve_reports_a_null_batch_size_for_the_shipped_chart_layering() -> None:
    """Every shipped recipe leaves the signature's blank `total_train_batch_size` blank.

    Pinned because it is what sends a caller who leaves the field alone past the recipe to the
    chart's own batch size: neither the submission nor the recipe names one.
    """
    resolved = resolve_hyperparameters(merge_helm_values([CHART_SIGNATURE, make_recipe()]))

    assert resolved.batch_size is None


def test_resolve_falls_back_to_the_chart_signature_for_values_a_recipe_omits() -> None:
    resolved = resolve_hyperparameters(merge_helm_values([CHART_SIGNATURE, make_recipe()]))

    assert resolved.epochs == 1
    assert resolved.learning_rate == 1.0


def test_resolve_reads_a_batch_size_a_recipe_does_set() -> None:
    values = merge_helm_values([CHART_SIGNATURE, make_recipe(batchsize_conf={"total_train_batch_size": 8})])

    assert resolve_hyperparameters(values).batch_size == 8


def test_resolve_reports_nothing_for_an_empty_values_document() -> None:
    resolved = resolve_hyperparameters({})

    assert resolved.model_dump(exclude_none=True) == {}


# ============================================================================
# LoRA gating on metadata.trainingType
# ============================================================================


def test_resolve_reports_no_lora_when_the_recipe_omits_a_training_type() -> None:
    """Two of the six shipped recipes declare nothing, which means full-parameter training.

    Advertising LoRA controls there would offer knobs job submission refuses outright.
    """
    values = merge_helm_values([CHART_SIGNATURE, make_recipe(peft_conf={"peft_type": "NO_PEFT"})])

    assert resolve_hyperparameters(values).lora is None


def test_resolve_reports_no_lora_for_a_full_recipe() -> None:
    values = merge_helm_values(
        [CHART_SIGNATURE, make_recipe(training_type=TrainingType.FULL.value, peft_conf=lora_peft_conf())]
    )

    assert resolve_hyperparameters(values).lora is None


def test_resolve_reports_lora_when_the_recipe_declares_lora() -> None:
    values = merge_helm_values(
        [CHART_SIGNATURE, make_recipe(training_type=TrainingType.LORA.value, peft_conf=lora_peft_conf())]
    )

    assert resolve_hyperparameters(values).lora is not None


def test_resolve_reports_an_all_null_lora_block_for_a_lora_recipe_without_peft_kwargs() -> None:
    """The block still appears: the recipe trains LoRA, so the controls apply even unset."""
    values = merge_helm_values([CHART_SIGNATURE, make_recipe(training_type=TrainingType.LORA.value)])

    assert resolve_hyperparameters(values).lora == ALL_NULL_LORA


# ============================================================================
# Numeric handling
# ============================================================================


def test_resolve_reads_an_integral_float_as_an_integer() -> None:
    """Recipes spell integral values as floats — most shipped LoRA recipes write `16.0`, one a plain `16`."""
    values = make_recipe(training_type=TrainingType.LORA.value, peft_conf=lora_peft_conf(lora_alpha=16.0))

    alpha = resolve_hyperparameters(values).lora.alpha  # type: ignore[union-attr]
    assert alpha == 16
    assert isinstance(alpha, int)


@pytest.mark.parametrize(
    "alpha",
    [16.5, True, False, "16", None, [16], {"value": 16}, float("nan"), float("inf"), -float("inf")],
    ids=["fractional", "true", "false", "string", "null", "list", "map", "nan", "inf", "-inf"],
)
def test_resolve_reports_an_unreadable_integer_as_null(alpha: Any) -> None:
    """Truncating 16.5 or reading `True` as 1 would advertise a default the recipe never uses."""
    values = make_recipe(training_type=TrainingType.LORA.value, peft_conf=lora_peft_conf(lora_alpha=alpha))

    assert resolve_hyperparameters(values).lora.alpha is None  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "dropout",
    [True, False, "0.05", None, [0.05], float("nan"), float("inf")],
    ids=["true", "false", "string", "null", "list", "nan", "inf"],
)
def test_resolve_reports_an_unreadable_float_as_null(dropout: Any) -> None:
    values = make_recipe(training_type=TrainingType.LORA.value, peft_conf=lora_peft_conf(lora_dropout=dropout))

    assert resolve_hyperparameters(values).lora.dropout is None  # type: ignore[union-attr]


def test_resolve_reports_an_integer_too_large_for_a_float_as_null() -> None:
    """A recipe carrying an absurd number must cost only its own field, not the whole listing."""
    too_large = 10**400

    resolved = resolve_hyperparameters(
        make_recipe(
            training_type=TrainingType.LORA.value,
            peft_conf=lora_peft_conf(lora_dropout=too_large),
            overrides={"lr_multiplier": too_large},
        )
    )

    assert resolved.learning_rate is None
    assert resolved.lora.dropout is None  # type: ignore[union-attr]


def test_resolve_keeps_a_zero_dropout() -> None:
    """Zero disables dropout and is a real declaration — swallowing it as falsy hides the recipe's choice."""
    values = make_recipe(training_type=TrainingType.LORA.value, peft_conf=lora_peft_conf(lora_dropout=0.0))

    assert resolve_hyperparameters(values).lora.dropout == 0.0  # type: ignore[union-attr]


def test_resolve_reads_an_integer_dropout_as_a_float() -> None:
    values = make_recipe(training_type=TrainingType.LORA.value, peft_conf=lora_peft_conf(lora_dropout=0))

    dropout = resolve_hyperparameters(values).lora.dropout  # type: ignore[union-attr]
    assert dropout == 0.0
    assert isinstance(dropout, float)


def test_resolve_reports_a_zero_epoch_count_rather_than_nothing() -> None:
    values = merge_helm_values([CHART_SIGNATURE, make_recipe(training_args={"num_train_epochs": 0})])

    assert resolve_hyperparameters(values).epochs == 0


# ============================================================================
# Malformed recipes
# ============================================================================


@pytest.mark.parametrize("rank", [0, -8], ids=["zero", "negative"])
def test_resolve_passes_through_a_rank_a_submission_would_reject(rank: int) -> None:
    """Reporting what the recipe says beats failing the whole listing over one odd recipe.

    `LoraHyperparameters` deliberately carries none of `LoraSettings`' range constraints for this.
    """
    values = make_recipe(training_type=TrainingType.LORA.value, peft_conf=lora_peft_conf(r=rank))

    assert resolve_hyperparameters(values).lora.rank == rank  # type: ignore[union-attr]


@pytest.mark.parametrize("dropout", [1.0, -0.1], ids=["one", "negative"])
def test_resolve_passes_through_a_dropout_a_submission_would_reject(dropout: float) -> None:
    values = make_recipe(training_type=TrainingType.LORA.value, peft_conf=lora_peft_conf(lora_dropout=dropout))

    assert resolve_hyperparameters(values).lora.dropout == dropout  # type: ignore[union-attr]


def test_resolve_reports_the_readable_lora_fields_when_a_sibling_is_malformed() -> None:
    """One unreadable field must cost that field only, not the rest of the recipe's LoRA block."""
    values = make_recipe(training_type=TrainingType.LORA.value, peft_conf=lora_peft_conf(lora_alpha="sixteen"))

    assert resolve_hyperparameters(values).lora == LoraHyperparameters(rank=64, alpha=None, dropout=0.05)


@pytest.mark.parametrize(
    "peft_conf",
    ["NO_PEFT", 7, ["LORA"], {"peft_kwargs": "none"}, {"peft_kwargs": None}],
    ids=["string", "int", "list", "scalar-kwargs", "null-kwargs"],
)
def test_resolve_reports_an_all_null_lora_block_when_peft_conf_is_not_a_mapping(peft_conf: Any) -> None:
    values = make_recipe(training_type=TrainingType.LORA.value, peft_conf=peft_conf)

    assert resolve_hyperparameters(values).lora == ALL_NULL_LORA


@pytest.mark.parametrize("finetuning_config", ["sft", 7, ["sft"], None], ids=["string", "int", "list", "null"])
def test_resolve_reports_nothing_when_finetuning_config_is_not_a_mapping(finetuning_config: Any) -> None:
    """A malformed recipe must describe itself as unknown, not break the listing for every model."""
    values = make_recipe(training_type=TrainingType.LORA.value, finetuning_config=finetuning_config)

    resolved = resolve_hyperparameters(values)

    assert (resolved.batch_size, resolved.epochs, resolved.learning_rate) == (None, None, None)
    assert resolved.lora == ALL_NULL_LORA


@pytest.mark.parametrize("metadata", ["lora", 7, ["lora"], None], ids=["string", "int", "list", "null"])
def test_resolve_reports_no_lora_when_metadata_is_not_a_mapping(metadata: Any) -> None:
    values = {**make_recipe(peft_conf=lora_peft_conf()), "metadata": metadata}

    assert resolve_hyperparameters(values).lora is None


def test_resolve_reports_a_scalar_training_args_block_as_null_epochs() -> None:
    values = make_recipe(training_args={})
    values["finetuning_config"]["training_args"] = "defaults"

    assert resolve_hyperparameters(values).epochs is None


# ============================================================================
# Alignment with what job submission writes
# ============================================================================


def test_the_resolver_reads_back_every_hyperparameter_job_submission_writes() -> None:
    """The listing must read each value back from the same path submission writes it to.

    Both sides now import these paths, so a rename cannot desynchronise them; what this still
    catches is the resolver reading a path it hardcoded instead of the shared one.
    """
    paths = {"batch_size": BATCH_SIZE_PATH, "epochs": EPOCHS_PATH, "learning_rate": LEARNING_RATE_PATH}
    sentinels: dict[str, Any] = {"batch_size": 8, "epochs": 3, "learning_rate": 2.5}

    values: dict[str, Any] = {"finetuning_config": {}}
    for field, (section, key) in paths.items():
        values["finetuning_config"].setdefault(section, {})[key] = sentinels[field]

    resolved = resolve_hyperparameters(values)

    for field, submitted in sentinels.items():
        assert getattr(resolved, field) == submitted, (
            f"{field} is submitted to {'.'.join(paths[field])} but the listing does not read it back from there"
        )


def test_the_lora_settings_a_caller_may_send_are_the_ones_the_listing_describes() -> None:
    """Adding an accepted LoRA setting without advertising it leaves a control with no default."""
    assert set(LORA_PEFT_KEYS) == set(LoraHyperparameters.model_fields)
