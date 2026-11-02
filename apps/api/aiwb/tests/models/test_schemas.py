# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    FinetunableModelResponse,
    FinetuneCreate,
    FinetuningHyperparameters,
    FineTuningOutput,
    LoraHyperparameters,
    LoraSettings,
    TrainingType,
)


def test_finetune_create_accepts_legacy_dataset_id() -> None:
    dataset_id = uuid4()

    request = FinetuneCreate(display_name="fine-tune", dataset_id=dataset_id)

    assert request.dataset_ids == [dataset_id]


def test_finetune_create_accepts_legacy_dataset_id_with_empty_dataset_ids() -> None:
    dataset_id = uuid4()

    request = FinetuneCreate(
        display_name="fine-tune",
        dataset_id=dataset_id,
        dataset_ids=[],
    )

    assert request.dataset_ids == [dataset_id]


def test_finetune_create_deduplicates_dataset_ids() -> None:
    dataset_id = uuid4()

    request = FinetuneCreate(
        display_name="fine-tune",
        dataset_ids=[dataset_id, dataset_id],
    )

    assert request.dataset_ids == [dataset_id]


def test_finetune_create_rejects_both_dataset_fields() -> None:
    with pytest.raises(ValidationError, match="not both"):
        FinetuneCreate(
            display_name="fine-tune",
            dataset_id=uuid4(),
            dataset_ids=[uuid4()],
        )


def test_finetune_create_requires_a_dataset() -> None:
    with pytest.raises(ValidationError, match="One or more datasetIds are required"):
        FinetuneCreate(display_name="fine-tune")


def test_finetune_create_accepts_at_most_ten_datasets() -> None:
    with pytest.raises(ValidationError):
        FinetuneCreate(display_name="fine-tune", dataset_ids=[uuid4() for _ in range(11)])


def test_finetune_create_rejects_an_unknown_field() -> None:
    """A misspelled field must be refused, not ignored.

    `outupt` accepted and dropped means the caller waits hours of GPU time for an adapter
    and is handed a merged model instead, with nothing in the response saying so.
    """
    with pytest.raises(ValidationError, match="outupt"):
        FinetuneCreate(
            display_name="fine-tune",
            dataset_ids=[uuid4()],
            outupt="adapter",  # type: ignore[call-arg]
        )


def test_finetune_create_defaults_output_to_model() -> None:
    request = FinetuneCreate(display_name="fine-tune", dataset_ids=[uuid4()])

    assert request.output is FineTuningOutput.MODEL


def test_finetune_create_accepts_an_optional_description() -> None:
    request = FinetuneCreate(
        display_name="fine-tune",
        description="Sentiment adapter for support tickets.",
        dataset_ids=[uuid4()],
    )

    assert request.description == "Sentiment adapter for support tickets."


def test_finetune_create_defaults_description_to_none() -> None:
    request = FinetuneCreate(display_name="fine-tune", dataset_ids=[uuid4()])

    assert request.description is None


def test_finetune_create_rejects_a_description_over_2048_characters() -> None:
    with pytest.raises(ValidationError, match="description"):
        FinetuneCreate(display_name="fine-tune", description="x" * 2049, dataset_ids=[uuid4()])


def test_finetune_create_rejects_an_output_outside_the_enum() -> None:
    with pytest.raises(ValidationError, match="output"):
        FinetuneCreate(
            display_name="fine-tune",
            dataset_ids=[uuid4()],
            output="checkpoint",  # type: ignore[arg-type]
        )


def test_lora_settings_rejects_an_unknown_field() -> None:
    """Same reasoning as FinetuneCreate: a dropped hyperparameter trains the wrong thing quietly."""
    with pytest.raises(ValidationError, match="droput"):
        LoraSettings(droput=0.1)  # type: ignore[call-arg]


@pytest.mark.parametrize("rank", [0, -1])
def test_lora_settings_rejects_a_non_positive_rank(rank: int) -> None:
    with pytest.raises(ValidationError, match="rank"):
        LoraSettings(rank=rank)


@pytest.mark.parametrize("alpha", [0, -1])
def test_lora_settings_rejects_a_non_positive_alpha(alpha: int) -> None:
    with pytest.raises(ValidationError, match="alpha"):
        LoraSettings(alpha=alpha)


@pytest.mark.parametrize("dropout", [1.0, 1.5, -0.1])
def test_lora_settings_rejects_a_dropout_outside_the_unit_interval(dropout: float) -> None:
    """Dropout is a probability, and 1.0 drops every unit — a run that learns nothing."""
    with pytest.raises(ValidationError, match="dropout"):
        LoraSettings(dropout=dropout)


def test_lora_settings_accepts_a_zero_dropout() -> None:
    """Zero is a legitimate request to disable dropout, distinct from leaving it to the recipe."""
    assert LoraSettings(dropout=0.0).dropout == 0.0


def test_lora_settings_default_to_leaving_every_value_to_the_recipe() -> None:
    settings = LoraSettings()

    assert settings.model_dump(exclude_none=True) == {}


def test_finetunable_model_defaults_training_type_to_full() -> None:
    """A recipe that declares nothing trains full-parameter, matching the chart default."""
    model = FinetunableModelResponse(
        canonical_name="acme/base",
        hyperparameters=FinetuningHyperparameters(batch_size=None, epochs=None, learning_rate=None, lora=None),
    )

    assert model.training_type is TrainingType.FULL


def test_finetune_create_leaves_every_hyperparameter_to_the_recipe() -> None:
    """A caller who names no hyperparameter trains with the base model recipe's own values.

    Nothing unset reaches the job, so the recipe's values layer is the one that wins. A
    platform-chosen default here would silently override every recipe with the same number.
    """
    request = FinetuneCreate(display_name="fine-tune", dataset_ids=[uuid4()])

    assert (request.batch_size, request.epochs, request.learning_rate) == (None, None, None)


@pytest.mark.parametrize("epochs", [0, -1])
def test_finetune_create_rejects_a_non_positive_epochs(epochs: int) -> None:
    """A supplied value is still validated; only an absent one is left to the recipe."""
    with pytest.raises(ValidationError, match="epochs"):
        FinetuneCreate(display_name="fine-tune", dataset_ids=[uuid4()], epochs=epochs)


@pytest.mark.parametrize("batch_size", [0, -1])
def test_finetune_create_rejects_a_non_positive_batch_size(batch_size: int) -> None:
    with pytest.raises(ValidationError, match="batch_size"):
        FinetuneCreate(display_name="fine-tune", dataset_ids=[uuid4()], batch_size=batch_size)


@pytest.mark.parametrize("learning_rate", [0.0, -1.0])
def test_finetune_create_rejects_a_non_positive_learning_rate(learning_rate: float) -> None:
    with pytest.raises(ValidationError, match="learning_rate"):
        FinetuneCreate(display_name="fine-tune", dataset_ids=[uuid4()], learning_rate=learning_rate)


def test_finetune_create_keeps_an_explicitly_null_hyperparameter_null() -> None:
    """Spelling a hyperparameter out as null asks for nothing, exactly as leaving it out does."""
    request = FinetuneCreate(
        display_name="fine-tune",
        dataset_ids=[uuid4()],
        batch_size=None,
        epochs=None,
        learning_rate=None,
    )

    assert (request.batch_size, request.epochs, request.learning_rate) == (None, None, None)


def test_echoing_an_advertised_null_back_matches_omitting_the_field() -> None:
    """Every shipped recipe advertises a null batch size, and both ways to submit that agree.

    A UI that round-trips the listing into its form can echo the advertised nulls back verbatim,
    or drop them, without the two requests training differently — a divergence a caller could
    only discover part-way into a multi-hour job.
    """
    advertised = FinetuningHyperparameters(batch_size=None, epochs=1, learning_rate=1.0, lora=None)
    assert advertised.batch_size is None

    omitting = FinetuneCreate(
        display_name="fine-tune",
        dataset_ids=[uuid4()],
        epochs=advertised.epochs,
        learning_rate=advertised.learning_rate,
    )
    echoing = FinetuneCreate(
        display_name="fine-tune",
        dataset_ids=[uuid4()],
        epochs=advertised.epochs,
        learning_rate=advertised.learning_rate,
        batch_size=advertised.batch_size,
    )

    assert omitting.batch_size is None
    assert echoing.batch_size is None


@pytest.mark.parametrize("rank", [0, -1])
def test_lora_hyperparameters_report_a_rank_a_submission_would_reject(rank: int) -> None:
    """Recipes are external data: describing one odd recipe beats failing the whole listing.

    `LoraSettings` rejects these ranks on submission; the listing schema must not, so constructing
    it has to succeed and carry the value through untouched.
    """
    described = LoraHyperparameters(rank=rank, alpha=None, dropout=None)

    assert described.rank == rank


@pytest.mark.parametrize("alpha", [0, -1])
def test_lora_hyperparameters_report_an_alpha_a_submission_would_reject(alpha: int) -> None:
    assert LoraHyperparameters(rank=None, alpha=alpha, dropout=None).alpha == alpha


@pytest.mark.parametrize("dropout", [1.0, 1.5, -0.1])
def test_lora_hyperparameters_report_a_dropout_a_submission_would_reject(dropout: float) -> None:
    assert LoraHyperparameters(rank=None, alpha=None, dropout=dropout).dropout == dropout


@pytest.mark.parametrize("omitted", ["rank", "alpha", "dropout"])
def test_lora_hyperparameters_require_every_field(omitted: str) -> None:
    """A LoRA recipe reports all three either way, so the schema must not offer an absent case."""
    supplied = {"rank": 64, "alpha": 16, "dropout": 0.05}
    del supplied[omitted]

    with pytest.raises(ValidationError, match=omitted):
        LoraHyperparameters(**supplied)  # type: ignore[arg-type]


def test_finetunable_model_requires_hyperparameters() -> None:
    """Every listed model advertises these, so the schema must not offer clients an absent case."""
    with pytest.raises(ValidationError, match="hyperparameters"):
        FinetunableModelResponse(canonical_name="acme/base")  # type: ignore[call-arg]


def test_finetunable_model_serializes_hyperparameters_as_camel_case() -> None:
    """The UI reads these straight off the wire and posts them back under the same names."""
    model = FinetunableModelResponse(
        canonical_name="acme/base",
        hyperparameters=FinetuningHyperparameters(
            batch_size=8, epochs=3, learning_rate=1.0, lora=LoraHyperparameters(rank=64, alpha=16, dropout=0.05)
        ),
    )

    payload = model.model_dump(by_alias=True)["hyperparameters"]

    assert payload["batchSize"] == 8
    assert payload["learningRate"] == 1.0
    assert payload["lora"]["rank"] == 64
    assert "batch_size" not in payload and "learning_rate" not in payload


def test_finetunable_model_hyperparameter_names_match_the_submission_fields() -> None:
    """A control pre-filled from `hyperparameters` posts back under the same key."""
    advertised = set(FinetuningHyperparameters.model_fields) - {"lora"}

    assert advertised <= set(FinetuneCreate.model_fields)
