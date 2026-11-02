# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from enum import StrEnum
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from api_common.schemas import BaseModel


class TrainingType(StrEnum):
    """How a fine-tuning recipe trains, fixed by the base model's recipe rather than the caller."""

    LORA = "lora"
    FULL = "full"


class FineTuningOutput(StrEnum):
    """What a completed fine-tuning job registers in the project."""

    MODEL = "model"
    ADAPTER = "adapter"


class LoraSettings(BaseModel):
    """LoRA hyperparameters layered over the recipe's own values.

    Only supplied fields are sent onward, so anything left unset keeps the value the
    recipe already uses. Unknown fields are rejected rather than ignored: a misspelled
    hyperparameter that trains something other than what was asked, yet still reports
    success, is the worst outcome for a multi-hour GPU job.
    """

    model_config = ConfigDict(extra="forbid")

    rank: int | None = Field(
        default=None,
        ge=1,
        description=(
            "LoRA rank. Defaults to the base model recipe's value, which is commonly 64. "
            "aim-engine advertises a maximum servable adapter rank of 32 per serving pod, so a "
            "higher rank trains successfully but may not be servable."
        ),
        examples=[16, 32, 64],
    )
    alpha: int | None = Field(
        default=None,
        ge=1,
        description="LoRA alpha scaling factor. Defaults to the base model recipe's value.",
        examples=[16, 32],
    )
    dropout: float | None = Field(
        default=None,
        ge=0.0,
        lt=1.0,
        description="LoRA dropout probability. Defaults to the base model recipe's value.",
        examples=[0.05, 0.1],
    )


# Carries none of LoraSettings' range constraints on purpose: those validate what a caller may ask
# for, while this reports what a recipe already says. Recipes are external data, so rejecting an
# out-of-range value here would fail the whole listing instead of describing one odd recipe.
class LoraHyperparameters(BaseModel):
    """The LoRA values a recipe declares.

    No field has a default: the server always sends all three, and a default would drop the field
    from the OpenAPI `required` list, generating an optional property in clients for a field that
    is never absent. A value the recipe does not set is sent as null, not omitted.
    """

    rank: int | None = Field(..., description="LoRA rank, or null if the recipe does not set one.", examples=[64])
    alpha: int | None = Field(
        ..., description="LoRA alpha scaling factor, or null if the recipe does not set one.", examples=[16]
    )
    dropout: float | None = Field(
        ..., description="LoRA dropout probability, or null if the recipe does not set one.", examples=[0.05]
    )


# Values that cannot be read as a finite number are reported as null rather than guessed at: a
# wrong default silently trains the wrong job for hours.
class FinetuningHyperparameters(BaseModel):
    """The values a recipe trains with unless overridden.

    Each field mirrors the same-named field of a fine-tuning job submission. Omitting a field from a
    submission trains with the recipe's own value, and only an explicitly supplied value overrides
    it — the same contract `lora` keeps. A value the recipe does not set is reported as null, and
    submitting without it leaves the chart's own default in charge.

    No field has a default: the server always sends all four, and a default would drop the field
    from the OpenAPI `required` list, generating an optional property in clients for a field that
    is never absent.
    """

    batch_size: int | None = Field(
        ...,
        description="Total training batch size across all GPUs, or null when the recipe does not set one.",
        examples=[2, 8],
    )
    epochs: int | None = Field(
        ..., description="Number of training epochs, or null when the recipe does not set one.", examples=[1, 3]
    )
    learning_rate: float | None = Field(
        ...,
        description="Learning rate multiplier, not an absolute learning rate. It scales the recipe's "
        "own learning rate, so 1.0 means train at the recipe's rate. Matches the `learningRate` field "
        "of a job submission.",
        examples=[1.0, 1.41421],
    )
    lora: LoraHyperparameters | None = Field(
        ...,
        description="LoRA defaults, or null for a recipe that trains full-parameter and therefore "
        "has no LoRA settings to offer.",
    )


class FinetunableModelResponse(BaseModel):
    canonical_name: str = Field(
        description="The canonical name of the finetunable model.", examples=["meta-llama/Llama-3.1-8B"]
    )
    gpu_count: int | None = Field(
        None,
        description="Number of GPUs required for finetuning, or null if unspecified.",
        examples=[1, 2, 4, 8],
    )
    compatible_accelerators: list[str] = Field(
        default_factory=list,
        description="AMD GPU device IDs this recipe is compatible with.",
        examples=[["0x74a1"]],
    )
    compatible_accelerator_names: list[str] = Field(
        default_factory=list,
        description="Display names for the compatible AMD GPUs, resolved from cluster node labels.",
        examples=[["AMD Instinct MI300X"]],
    )
    hf_token_required: bool = Field(
        True,
        description="Whether this base model is gated on Hugging Face and requires a token to download. "
        "Read from the recipe overlay's `metadata.hfTokenRequired` field. Defaults to true when the "
        "overlay omits it or declares a non-boolean, so a model whose gating cannot be determined is "
        "offered as gated rather than silently presented as open.",
        examples=[True, False],
    )
    training_type: TrainingType = Field(
        default=TrainingType.FULL,
        description="How this base model trains. Only `lora` recipes can produce an adapter; a `full` "
        "recipe trains every weight and has no adapter to keep. A recipe that declares nothing is "
        "reported as `full`, matching the fine-tuning chart default.",
    )
    # No default: the server always sends this, and a default would drop the field from the
    # OpenAPI `required` list, generating an optional property in clients for a field that is
    # never absent.
    hyperparameters: FinetuningHyperparameters = Field(
        description="The hyperparameters this recipe trains with unless overridden.",
    )


class FinetuneJobResponse(BaseModel):
    """Response returned when a finetuning job is submitted.

    Represents the pending job, not yet an AIMModel CR (which is created upon completion).
    """

    workload_id: UUID = Field(
        description="AIWB workload ID to track the job.",
        examples=["7f3b6c8e-2a1d-4b9f-9c12-1a2b3c4d5e6f"],
    )
    display_name: str = Field(
        description="Name of the finetuned model to be produced.",
        examples=["imdb-classifier-v3"],
    )
    base_model: str = Field(
        description="Canonical name of the base model being finetuned.",
        examples=["meta-llama/Llama-3.1-8B"],
    )
    namespace: str = Field(
        description="Namespace where the job runs.",
        examples=["acme-summarizer"],
    )
    status: str = Field(default="Pending", description="Initial job status.", examples=["Pending"])


class FinetuneCreate(BaseModel):
    """Input shape for submitting a fine-tuning job.

    Unknown fields are rejected for the same reason they are inside ``lora``: a misspelled key
    is silently dropped, and the job then trains for hours and reports success having ignored
    what was asked for. ``outupt`` would otherwise produce a merged model with no complaint.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(
        min_length=1,
        description="The user-visible name for the finetuning job and the resulting finetuned model. Any characters are allowed.",
        examples=["imdb-classifier-v3"],
    )
    description: str | None = Field(
        default=None,
        max_length=2048,
        description="Optional human-readable description stored with the produced model or adapter.",
        examples=["IMDB sentiment classifier, 3 epochs"],
    )
    dataset_id: UUID | None = Field(
        default=None,
        deprecated="Use datasetIds instead; a fine-tuning job can use multiple datasets.",
        description="Deprecated UUID. Use datasetIds instead; it accepts one or more datasets.",
        examples=["7f3b6c8e-2a1d-4b9f-9c12-1a2b3c4d5e6f"],
    )
    # Guardrail against unbounded client input, not a training-pipeline limit:
    # each ID widens the availability query, the snapshot, and the job manifest.
    dataset_ids: list[UUID] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "The IDs of the datasets to use for fine-tuning. At least one dataset is required "
            "and at most 10 may be given. Mutually exclusive with the deprecated datasetId."
        ),
        examples=[
            [
                "7f3b6c8e-2a1d-4b9f-9c12-1a2b3c4d5e6f",
                "b739c5f8-c5f8-4423-b1af-c3ea2fbf6904",
            ]
        ],
    )
    epochs: int | None = Field(
        description="The number of epochs to train the model for. Defaults to the base model recipe's value.",
        default=None,
        ge=1,
        examples=[1, 3, 10],
    )
    learning_rate: float | None = Field(
        description="Learning rate multiplier, not an absolute learning rate. It scales the recipe's own "
        "learning rate, so 1.0 means train at the recipe's rate. Defaults to the base model recipe's value.",
        default=None,
        gt=0,
        examples=[1.0, 0.5],
    )
    batch_size: int | None = Field(
        description="Total training batch size across all GPUs. Defaults to the base model recipe's value.",
        default=None,
        ge=1,
        examples=[2, 4, 8],
    )
    hf_token_secret_name: str | None = Field(
        description="Optional HuggingFace token secret name for downloading private models",
        default=None,
        examples=["hf-token"],
    )
    output: FineTuningOutput = Field(
        default=FineTuningOutput.MODEL,
        description="What the completed job registers in the project. `model` produces a fine-tuned "
        "model, as it does today. `adapter` keeps the trained LoRA adapter instead, and is accepted "
        "only for base models whose training type is `lora`.",
    )
    lora: LoraSettings | None = Field(
        default=None,
        description="LoRA hyperparameter overrides. Independent of `output` — these apply to any LoRA "
        "run, including one that merges into a model. Rejected for base models that train full-parameter.",
    )

    @model_validator(mode="after")
    def reconcile_dataset_ids(self) -> "FinetuneCreate":
        if self.dataset_id and self.dataset_ids:
            raise ValueError("Provide either datasetId or datasetIds, not both")
        if self.dataset_ids:
            self.dataset_ids = list(dict.fromkeys(self.dataset_ids))
        elif self.dataset_id:
            self.dataset_ids = [self.dataset_id]
        else:
            raise ValueError("One or more datasetIds are required")
        return self
