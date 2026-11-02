# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Pydantic schemas for custom model preview, onboard, and profile reads."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, ConfigDict, Field, model_validator

from api_common.schemas import BaseModel

from ..aims.crds import AIMModelResource, AIMProfileResource, ProfileSelector
from ..secrets.constants import SECRET_NAME_MAX_LENGTH, SECRET_NAME_MIN_LENGTH, SECRET_NAME_PATTERN
from .enums import CustomModelImportType, OnboardPhase


class SourceSecretRequest(BaseModel):
    """Shared source-secret fields and validation helpers for custom-model APIs."""

    hf_token_secret_name: str | None = Field(
        None,
        description=(
            "K8s secret name in the namespace containing an HF token under the "
            "'token' key. Valid only when sourceType is 'huggingFace'."
        ),
        min_length=SECRET_NAME_MIN_LENGTH,
        max_length=SECRET_NAME_MAX_LENGTH,
        pattern=SECRET_NAME_PATTERN,
        examples=["hf-token"],
    )
    s3_storage_name: str | None = Field(
        None,
        description=(
            "Project storage configuration name in the namespace for S3 access credentials. "
            "Required when sourceType is 's3'."
        ),
        min_length=SECRET_NAME_MIN_LENGTH,
        max_length=SECRET_NAME_MAX_LENGTH,
        pattern=SECRET_NAME_PATTERN,
        examples=["default-s3-storage"],
    )

    @staticmethod
    def _validate_source_secret_compatibility(
        source_type: CustomModelImportType,
        hf_token_secret_name: str | None,
        s3_storage_name: str | None,
    ) -> None:
        """Validate source-specific secret constraints."""
        if source_type == CustomModelImportType.S3:
            if not s3_storage_name:
                raise ValueError("s3StorageName is required when sourceType is 's3'.")
            if hf_token_secret_name:
                raise ValueError("hfTokenSecretName is only supported when sourceType is 'huggingFace'.")
            return
        if s3_storage_name:
            raise ValueError("s3StorageName is only supported when sourceType is 's3'.")


class PreviewRequest(SourceSecretRequest):
    """Request body for the model source preview endpoint."""

    source_type: CustomModelImportType = Field(
        default=CustomModelImportType.HUGGING_FACE,
        description=(
            "Source family for preview validation. "
            "'huggingFace' keeps the current Hub preview path; "
            "'s3' enables S3 credential and layout validation."
        ),
        examples=[CustomModelImportType.HUGGING_FACE, CustomModelImportType.S3],
    )
    source: str = Field(
        ...,
        description=(
            "Source location to preview. For 'huggingFace', pass an HF repo id "
            "or URL; a revision may be embedded in the URL "
            "(e.g. /tree/<rev> or /blob/<rev>/...). For 's3', pass an "
            "s3://bucket/prefix URI."
        ),
        examples=[
            "meta-llama/Llama-3.1-8B-Instruct",
            "https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct",
            "s3://my-bucket/path/to/model",
        ],
    )

    @model_validator(mode="after")
    def _validate_source_specific_secret_fields(self) -> "PreviewRequest":
        """Enforce source-type/secret compatibility at the request boundary."""
        self._validate_source_secret_compatibility(
            self.source_type,
            self.hf_token_secret_name,
            self.s3_storage_name,
        )
        return self


class OnboardRequest(SourceSecretRequest):
    """Request body for the custom model onboard endpoint.

    Carries the Hub-validated fields returned by preview (possibly edited by
    the user) plus the container image selected in the UI. The server
    re-fetches Hub on every onboard and rejects the request if the supplied
    sha does not match what Hub currently resolves `(repoId, revision)` to,
    so stale or forged Hub fields fail at the API boundary rather than
    landing on the persisted CR.
    """

    source_type: CustomModelImportType = Field(
        default=CustomModelImportType.HUGGING_FACE,
        description=(
            "Source family for onboarding. 'huggingFace' keeps the current Hub "
            "re-verify + import path; 's3' uses S3-backed onboarding."
        ),
        examples=[CustomModelImportType.HUGGING_FACE, CustomModelImportType.S3],
    )
    repo_id: str = Field(..., min_length=1, description="Canonical repo id from preview.")
    revision: str = Field(..., min_length=1, description="Resolved revision label or SHA from preview.")
    sha: str = Field(..., min_length=1, description="Pinned commit SHA from preview.")
    display_name: str = Field(
        ...,
        min_length=1,
        description=(
            "Display title for the model; may differ from preview suggestion. "
            "Non-empty so the sanitized DISPLAY_NAME_LABEL is non-empty: an empty "
            "label value yields a `display-name=` selector that matches every "
            "AIMModel missing the label, corrupting conflict detection."
        ),
    )
    description: str = Field(default="", description="Catalog description from preview; may be empty.")
    tags: list[str] = Field(default_factory=list, description="HuggingFace Hub tags from preview.")
    image: str = Field(
        ...,
        min_length=1,
        description="Container image reference chosen by the user for the onboarded model.",
    )
    custom_profile: dict[str, Any] | None = Field(
        None,
        description=(
            "Optional opaque profile overrides written verbatim to "
            "`AIMModel.spec.profiles.overrides`. aim-engine consumes this block at "
            "admission and bakes the values (engine, engineArgs, engineEnv, "
            "containerEnv, metric, precision, accelerator settings, etc.) into each "
            "emitted AIMProfile.spec. `engineEnv` is supplied as `[{name, value}]` "
            "entries (env var names are UPPER_SNAKE_CASE, so they ride as values to "
            "stay outside the camelCase contract); its entry shape is validated and "
            "collapsed to a `map[string]string` server-side. Other fields pass through "
            "verbatim — the API does not validate their shape, and aim-engine rejects "
            "unknown keys at admission. If `customProfile.image` "
            "is supplied it must agree with the top-level `image` field, otherwise "
            "the two image references would disagree once the profile is emitted."
        ),
    )

    @model_validator(mode="after")
    def _reject_conflicting_image_refs(self) -> "OnboardRequest":
        """Reject disagreeing image refs so the deployment image stays unambiguous (422 from FastAPI)."""
        if not self.custom_profile:
            return self
        profile_image = self.custom_profile.get("image")
        if profile_image is None:
            return self
        if profile_image == "":
            raise ValueError(
                "customProfile.image must not be an empty string. "
                "Either omit customProfile.image so the top-level image is used, "
                "or set it to the same non-empty image reference."
            )
        if profile_image == self.image:
            return self
        raise ValueError(
            f"customProfile.image '{profile_image}' conflicts with the top-level "
            f"image '{self.image}'. Either omit customProfile.image so the top-level "
            "image is used, or set them to the same reference."
        )

    @model_validator(mode="after")
    def _validate_source_specific_secret_fields(self) -> "OnboardRequest":
        """Enforce source-type/secret compatibility at the request boundary."""
        self._validate_source_secret_compatibility(
            self.source_type,
            self.hf_token_secret_name,
            self.s3_storage_name,
        )
        return self


class CustomModelOnboardStatus(BaseModel):
    """Composed lifecycle status for a custom (BYOM) model.

    Aggregates three independent Kubernetes resources into a single object
    so clients never need to perform their own multi-resource joins:

    * ``state`` — derived lifecycle state spanning the full arc from import
      to deployment (see ``OnboardPhase``).
    * ``status`` — raw AIMModel.status.status string from the controller.
    * ``templateReady`` — whether at least one AIMProfile has been emitted
      by aim-engine for this model. Necessary but not sufficient for
      deployability: profiles derive from the base image, so this can be True
      while the weight import is still Importing or has Failed. Gate deploy on
      ``state == Ready``, not on this flag.
    * ``artifact_phase`` / ``artifact_last_error`` — weight-import signal,
      read from the workbench-owned import annotations on the CR. Null until
      an import has recorded a state.

    ``state`` composition rule:
    * ``Ready``     — AIMModel is Ready *and* templateReady is True.
    * ``Failed``    — AIMModel status indicates failure, or the import Failed.
    * ``Importing`` — an import is recorded and not yet terminal (state not Ready/Failed).
    * ``Pending``   — none of the above; the CR exists and the engine has not yet reacted.

    Display metadata (title, tags, description) is stored in
    ``metadata.annotations`` on the parent ``CustomModelResponse`` rather than
    in a dedicated sub-object, so UI parsers must read annotations directly.
    """

    state: OnboardPhase = Field(
        OnboardPhase.PENDING,
        description="Derived lifecycle state spanning import → ready → deployed.",
    )
    status: str = Field("", description="Raw AIMModel.status.status string from the controller.")
    template_ready: bool = Field(
        False,
        description="True when at least one AIMProfile has been emitted by aim-engine for this model.",
    )
    artifact_phase: str | None = Field(
        None,
        description=(
            "Weight-import phase, read from the workbench-owned import annotations on the CR. "
            "Null until an import has recorded a state."
        ),
    )
    artifact_last_error: str | None = Field(None, description="Last import error; null when no error.")


class CustomModelResponse(AIMModelResource):
    """Custom (BYOM) model onboarded via the preview endpoint.

    Extends AIMModelResource (namespace-scoped v1alpha2) so the spec reflects
    the actual CR shape — including spec.profiles, modelSources, and image —
    rather than the cluster-scoped AIMClusterModelResource projection that only
    carries spec.image.  Extra fields carry custom-model-specific data that has
    no equivalent in the base CR shape.
    """

    # lifecycle phase that aggregates AIMModel, AIMProfile, and AIMArtifact.
    phase: CustomModelOnboardStatus = Field(
        default_factory=lambda: CustomModelOnboardStatus(state=OnboardPhase.PENDING)
    )
    profiles: list["CustomProfileResponse"] = Field(
        default_factory=list,
        description=(
            "Every profile row for the model (Default plus named), composed exactly like the "
            "dedicated profile endpoints: Default first, then by display name. Empty until the "
            "model has emitted a profile set. Each row's nested `profile` is the effective "
            "AIMProfile deploy would pin."
        ),
    )


class WeightFile(BaseModel):
    """A single candidate weight file from the Hub repository."""

    path: str = Field(
        ...,
        description="Relative path from the repo root (rfilename from Hub siblings).",
        examples=["model-00001-of-00004.safetensors"],
    )
    size_bytes: int | None = Field(
        None,
        description="File size in bytes; None when Hub did not report it.",
        examples=[4831838208],
    )
    role: str | None = Field(
        None,
        description="Coarse role classification: primary, shard, or config.",
        examples=["primary", "shard", "config"],
    )


class PreviewResponse(BaseModel):
    """Response body for the model source preview endpoint.

    Contains Hub metadata and candidate weight files for UI selection.
    Preview is read-only; persist the model via POST .../models/onboard.
    """

    source_type: CustomModelImportType = Field(
        default=CustomModelImportType.HUGGING_FACE,
        description="Source family used for preview validation.",
        examples=[CustomModelImportType.HUGGING_FACE, CustomModelImportType.S3],
    )
    repo_id: str = Field(
        ...,
        description="Canonical repo id after normalization.",
        examples=["meta-llama/Llama-3.1-8B-Instruct"],
    )
    revision: str = Field(
        ...,
        description=(
            "Resolved revision label or SHA for import. Equal to the revision "
            "label extracted from the source URL (branch, tag, or SHA) when one "
            "was provided; otherwise equal to the SHA of the Hub's default branch."
        ),
        examples=["main"],
    )
    sha: str = Field(
        ...,
        description="Resolved commit SHA from Hub; use this to pin the import.",
        examples=["8ab3a4c1b2d4e5f6789012345678901234567890"],
    )
    display_name: str = Field(
        ...,
        description="Suggested display title derived from Hub card data or repo name.",
        examples=["Llama 3.1 8B Instruct"],
    )
    description: str = Field(
        ...,
        description="Catalog description from Hub card data; may be empty.",
    )
    tags: list[str] = Field(
        ...,
        description="Hub and card tags associated with the model.",
        examples=[["text-generation", "llama", "meta"]],
    )
    pipeline_tag: str | None = Field(
        None,
        description="Hub pipeline tag (e.g. text-generation).",
        examples=["text-generation"],
    )
    gated: bool = Field(
        ...,
        description="True when the Hub model requires license acceptance to download.",
    )
    hf_token_recommended: bool = Field(
        ...,
        description="True when an HF token is required or strongly recommended.",
    )
    weight_files: list[WeightFile] = Field(
        ...,
        description=(
            "All candidate files from the Hub repo. Entries with role 'primary' "
            "or 'shard' are selectable weight blobs; entries with role 'config' "
            "(tokenizer files, README, config.json, etc.) are included for "
            "context and should not be presented as selectable weights."
        ),
    )
    layout_hint: str | None = Field(
        None,
        description=(
            "Coarse layout hint: 'safetensors', 'gguf', 'mixed' when both "
            "formats are present, or null when no recognised weight files "
            "were found."
        ),
        examples=["safetensors"],
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Non-blocking validation warnings for the source contents. "
            "Preview may still succeed when warnings are present."
        ),
    )


class CustomModelPatchRequest(BaseModel):
    """Partial update body for a custom-onboarded model.

    All fields are optional; supply only the fields to change. At least one
    field must be present — enforced in the service layer after
    ``model_dump(exclude_unset=True)``.

    Two groups of edits are supported and may be combined in one request:

    * **Display metadata** (``display_name`` / ``description`` / ``tags``) —
      written to the AIMModel annotations.
    * **Runtime profile** (``image`` / ``custom_profile``) — rewrites
      ``AIMModel.spec.profiles.overrides`` and repatches the live AIMProfile so
      the change takes effect without waiting for a controller reconcile.

    Runtime-profile edits use JSON merge-patch semantics on the overrides block,
    so the client must send the *complete* desired profile: a present key is
    set, a key sent as ``null`` is deleted (reset to the aim-engine default),
    and an omitted key is left unchanged. A profile edit requires the model to
    already have a derived AIMProfile (i.e. be past import); the service rejects
    it otherwise.
    """

    display_name: str | None = Field(
        None,
        min_length=1,
        description="Updated display title for the model card and detail surfaces.",
    )
    description: str | None = Field(
        None,
        description="Updated catalog description; pass an empty string to clear.",
    )
    tags: list[str] | None = Field(
        None,
        description="Replacement tag list; pass an empty list to clear all tags.",
    )
    image: str | None = Field(
        None,
        min_length=1,
        description=(
            "Updated runtime container image reference. Supplying this — alone or "
            "alongside customProfile — triggers a runtime-profile edit: the "
            "AIMModel overrides image and the live AIMProfile deployment-image-ref "
            "annotation are repointed. Requires a derived AIMProfile to exist."
        ),
    )
    custom_profile: dict[str, Any] | None = Field(
        None,
        description=(
            "Complete runtime profile overrides written verbatim to "
            "`AIMModel.spec.profiles.overrides` and merged onto the live "
            "`AIMProfile.spec`. Merge-patch semantics apply: send every field to "
            "keep, send `null` to reset a field to the aim-engine default. The API "
            "does not validate field shape — aim-engine rejects unknown keys at "
            "admission. If `customProfile.image` is supplied it must agree with the "
            "top-level `image`, otherwise the two image references would disagree "
            "once the profile is re-emitted."
        ),
    )

    @model_validator(mode="after")
    def _reject_conflicting_image_refs(self) -> "CustomModelPatchRequest":
        """Reject disagreeing image refs so the deployment image stays unambiguous (422 from FastAPI)."""
        if not self.custom_profile:
            return self
        profile_image = self.custom_profile.get("image")
        if profile_image is None:
            return self
        if profile_image == "":
            raise ValueError(
                "customProfile.image must not be an empty string. "
                "Either omit customProfile.image so the top-level image is used, "
                "or set it to the same non-empty image reference."
            )
        if self.image is not None and profile_image != self.image:
            raise ValueError(
                f"customProfile.image '{profile_image}' conflicts with the top-level "
                f"image '{self.image}'. Either omit customProfile.image so the top-level "
                "image is used, or set them to the same reference."
            )
        return self


class CustomModelPatchResponse(BaseModel):
    """Post-patch display metadata for a custom-onboarded AIMModel."""

    name: str = Field(..., description="AIMModel CR resource name in the namespace.")
    display_name: str = Field(..., description="Current display title.")
    description: str = Field(default="", description="Current catalog description.")
    tags: list[str] = Field(default_factory=list, description="Current tag list.")


class RuntimeProfileCombination(BaseModel):
    """One four-axis tuple a base-role AIMProfile actually emits.

    The distinct per-axis lists on ``RuntimeProfileOptions`` say which values
    exist but not which coexist; a profile create/update must resolve its four
    narrowing axes to exactly one base profile, so a form that offers any
    cartesian product of the distinct lists can build a tuple the base never
    emits (rejected with 400). This carries the emitted tuples so the client can
    constrain its selectors to combinations that are actually reachable.
    """

    accelerator_model: str = Field(
        ...,
        description="Accelerator model the base profile targets (e.g. 'MI300X').",
    )
    accelerator_count: int = Field(
        ...,
        description="Accelerator (GPU) count for this combination.",
    )
    precision: str = Field(
        ...,
        description="Precision the base template emits for this combination (e.g. 'fp8').",
    )
    metric: str = Field(
        ...,
        description="Optimization metric for this combination (e.g. 'latency', 'throughput').",
    )


class RuntimeProfileOptions(BaseModel):
    """Runtime options a custom model will support, derived from the namespace's base-image profiles.

    A BYOM model inherits its runtime matrix from the base-image model's
    base-role AIMProfiles, so these distinct values are what the onboard wizard
    should offer (and preset) — the onboard-time analogue of the deploy wizard's
    Ready-profile selectors. Empty lists mean the base model has not emitted
    profiles yet; the client should fall back to its static defaults.

    The distinct per-axis lists are kept for presetting and for the empty-matrix
    fallback, but they cannot express which axis values coexist. ``combinations``
    carries the emitted four-axis tuples so the client can narrow each selector to
    values still reachable from the current selection, rather than offering a
    cartesian product the base never emits (which a create/update would reject).
    """

    accelerator_models: list[str] = Field(
        default_factory=list,
        description="Distinct acceleratorModel values (e.g. 'MI300X') aim-engine resolves against.",
    )
    precisions: list[str] = Field(
        default_factory=list,
        description="Distinct precisions the base template emits (e.g. 'fp16'); precision is base-determined, not freely chosen.",
    )
    accelerator_counts: list[int] = Field(
        default_factory=list,
        description="Distinct accelerator (GPU) counts per profile, ascending (e.g. [1, 2, 4, 8]).",
    )
    optimization_classes: list[str] = Field(
        default_factory=list,
        description="Distinct optimization tiers (AIMProfile.spec.type, e.g. 'general', 'optimized').",
    )
    metrics: list[str] = Field(
        default_factory=list,
        description="Distinct optimization metrics the base template emits (e.g. 'latency', 'throughput').",
    )
    combinations: list[RuntimeProfileCombination] = Field(
        default_factory=list,
        description=(
            "Emitted four-axis tuples (acceleratorModel, acceleratorCount, precision, metric). "
            "Only these combinations resolve to a single base profile; the client narrows its "
            "selectors to combinations reachable from the current selection. Empty when the base "
            "model has not emitted profiles yet."
        ),
    )
    profiles_available: bool = Field(
        default=False,
        description=(
            "Whether the base model has emitted any runtime profiles yet. Distinguishes an empty "
            "`combinations` that means 'not ready — fall back to defaults' (false) from one that "
            "means 'profiles exist but none resolves to a single base profile' (true), where the "
            "client must offer no runtime choices and block the save rather than fall back."
        ),
    )


class BaseImageRuntimeProfileOptions(BaseModel):
    """Runtime options for one selected base image (repository + tag).

    Unlike :class:`RuntimeProfileOptions` (namespace-wide unions), this payload
    is scoped to a specific base image's discovered hardware matrix so the UI
    can drive type/model/count/precision selectors from a coherent per-image
    option set.
    """

    image_repository: str = Field(..., description="Base image repository (without tag).")
    image_tag: str = Field(..., description="Base image tag.")
    accelerator_types: list[str] = Field(
        default_factory=list,
        description="Distinct accelerator families discovered for this base image (e.g. ['gpu']).",
    )
    accelerator_models: list[str] = Field(
        default_factory=list,
        description="Distinct acceleratorModel values discovered for this base image.",
    )
    accelerator_counts_by_model: dict[str, list[int]] = Field(
        default_factory=dict,
        description="Per-acceleratorModel supported count options discovered for this base image.",
    )
    precisions_by_model: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Per-acceleratorModel precisions discovered for this base image.",
    )
    metrics_by_model: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Per-acceleratorModel optimization metrics discovered for this base image.",
    )
    optimization_classes_by_model: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Per-acceleratorModel optimization classes (AIMProfile type) when available.",
    )
    combinations: list[RuntimeProfileCombination] = Field(
        default_factory=list,
        description=(
            "Emitted four-axis tuples (acceleratorModel, acceleratorCount, precision, metric) for this "
            "base image, read from the discovered-profile matrix. The per-model lists above say which "
            "values exist but not which coexist; only these combinations resolve to a single base profile, "
            "so the client narrows its count/precision/metric selectors to combinations reachable from the "
            "current selection instead of offering a cartesian product the base never emits."
        ),
    )
    profiles_available: bool = Field(
        default=False,
        description=(
            "Whether the selected base image has discovered any runtime profiles. Distinguishes an empty "
            "`combinations` that means 'not ready — fall back to defaults' (false) from one that means "
            "'profiles exist but none resolves to a single base profile' (true), where the client must "
            "offer no runtime choices and block the save rather than fall back."
        ),
    )


# Narrowing-axis keys the server composes from the typed request fields. They are
# rejected inside ``customProfile`` (both spellings) so a client cannot restate an
# axis there and have it silently overwritten by the top-level field.
_NARROWING_AXIS_KEYS = frozenset(
    {
        "acceleratorModel",
        "accelerator_model",
        "acceleratorCount",
        "accelerator_count",
        "precision",
        "metric",
    }
)


def _validate_custom_profile_display_name(value: str) -> str:
    """Reject blank names and the reserved engine-owned Default label."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("displayName must not be blank.")
    if stripped.casefold() == "default":
        raise ValueError("displayName 'Default' is reserved for the engine-owned profile set.")
    return value


CustomProfileDisplayName = Annotated[str, AfterValidator(_validate_custom_profile_display_name)]


class CustomProfileCreateRequest(BaseModel):
    """Request body for creating a named profile on an already-onboarded custom model.

    Unlike ``OnboardRequest.customProfile`` (a pure opaque passthrough), the four
    narrowing axes are typed first-class fields. The server composes *both* the
    AIMProfileSet's ``spec.selector`` (which base profile the set narrows to) and
    its ``spec.overrides`` from them, so the accelerator count cannot be stated
    twice and drift apart from ``tensor-parallel-size`` — the divergence found on
    live custom models where one opaque overrides block was stamped across all
    derived profiles. Everything else stays opaque under ``customProfile`` with
    the existing merge-patch contract (aim-engine rejects unknown keys at
    admission).

    Weights and model identity are copied from the parent AIMModel server-side,
    so the created profile is self-contained and deployable on its own without
    perturbing the AIMModel, its Default, or any sibling profile.
    """

    display_name: CustomProfileDisplayName = Field(
        ...,
        min_length=1,
        description=(
            "Human-facing label for the profile. Must be unique among the model's "
            "profiles; the reserved name 'Default' is rejected (that row is the "
            "engine-owned set, classified by provenance on read)."
        ),
        examples=["High speed fun"],
    )
    accelerator_model: str = Field(
        ...,
        min_length=1,
        description="Accelerator model the profile targets (e.g. 'MI300X'); one of the values from runtime-profile-options.",
        examples=["MI300X"],
    )
    accelerator_count: int = Field(
        ...,
        gt=0,
        description=(
            "Accelerator (GPU) count. Composed into both the selector and the overrides "
            "so it cannot disagree with the derived profile's tensor-parallel-size."
        ),
        examples=[8],
    )
    precision: str = Field(
        ...,
        min_length=1,
        description="Precision the base template emits (e.g. 'fp8'); precision is base-determined.",
        examples=["fp8"],
    )
    metric: str = Field(
        ...,
        min_length=1,
        description="Optimization metric (e.g. 'latency', 'throughput'); one of the values from runtime-profile-options.",
        examples=["latency"],
    )
    image: str = Field(
        ...,
        min_length=1,
        description="Container image reference for the profile's runtime.",
        examples=["amdenterpriseai/aim-base:0.11"],
    )
    custom_profile: dict[str, Any] | None = Field(
        None,
        description=(
            "Optional opaque profile overrides (engineArgs, engineEnv, containerEnv, etc.) "
            "written verbatim to the AIMProfileSet overrides. The four narrowing axes above "
            "are composed by the server and must not be restated here — doing so is rejected "
            "with a 422. `engineEnv` is supplied as `[{name, value}]` entries and collapsed to "
            "a map server-side. If `customProfile.image` is supplied it must agree with the "
            "top-level `image`."
        ),
    )

    @model_validator(mode="after")
    def _reject_conflicting_image_refs(self) -> "CustomProfileCreateRequest":
        """Reject disagreeing image refs so the deployment image stays unambiguous (422 from FastAPI)."""
        if not self.custom_profile:
            return self
        profile_image = self.custom_profile.get("image")
        if profile_image is None:
            return self
        if profile_image == "":
            raise ValueError(
                "customProfile.image must not be an empty string. "
                "Either omit customProfile.image so the top-level image is used, "
                "or set it to the same non-empty image reference."
            )
        if profile_image == self.image:
            return self
        raise ValueError(
            f"customProfile.image '{profile_image}' conflicts with the top-level "
            f"image '{self.image}'. Either omit customProfile.image so the top-level "
            "image is used, or set them to the same reference."
        )

    @model_validator(mode="after")
    def _reject_narrowing_axes_in_custom_profile(self) -> "CustomProfileCreateRequest":
        """Reject restating a narrowing axis under customProfile so an invalid payload can't silently succeed.

        The server composes the four axes into the set's selector and overrides from
        the typed top-level fields, overwriting anything with the same key in
        customProfile. Rejecting them here makes that clash a clear 422 rather than a
        silent overwrite.
        """
        if not self.custom_profile:
            return self
        restated = sorted(key for key in self.custom_profile if key in _NARROWING_AXIS_KEYS)
        if restated:
            raise ValueError(
                f"customProfile must not restate the narrowing axes {restated}; set acceleratorModel, "
                "acceleratorCount, precision, and metric as top-level fields instead."
            )
        return self


class CustomProfileStatus(BaseModel):
    """Readiness of a custom-model profile row, derived from its effective AIMProfile.

    An AIMProfileSet carries no status of its own, so ``state`` is taken from the
    effective AIMProfile the row summarises (the one deploy would pin). Empty when
    the model has not emitted a profile yet.
    """

    state: str = Field("", description="Effective AIMProfile readiness (e.g. 'Ready'); empty when none is emitted yet.")
    message: str = Field(
        "", description="Human-readable detail for non-ready states; empty when there is nothing to add."
    )


class ProfileInUseRef(BaseModel):
    """A deployment that currently pins a profile, so the UI can disable edit/delete per row."""

    service_id: str | None = Field(
        None,
        description="Workload id of the referencing AIMService, when it carries one.",
    )
    display_name: str = Field(
        ..., description="Display name of the referencing deployment (falls back to its resource name)."
    )


class CustomProfileConfiguration(BaseModel):
    """User-authored profile overrides returned through the public API.

    The typed fields below are the *allowlist*: only these are surfaced from an
    AIMProfileSet's overrides. ``extra="ignore"`` drops everything else —
    server-composed identity/model-source/selector-axis fields and any future
    engine-authored keys — so the response fails closed rather than leaking
    whatever the engine happens to stamp into ``spec.overrides``. This must stay
    in sync with the create/update request field set so an
    authored profile round-trips losslessly through the edit drawer.
    """

    model_config = ConfigDict(extra="ignore")

    image: str | None = None
    engine: str | None = None
    # Authored as an opaque customProfile knob rather than a narrowing axis:
    # aim-engine resolves the base profile by accelerator *model*, so this only
    # ever reaches spec.overrides. It is surfaced because the drawer offers it as
    # an editable field and would otherwise lose the user's choice on reopen.
    accelerator_type: str | None = None
    engine_args: dict[str, Any] | None = None
    engine_env: list[dict[str, Any]] | dict[str, str] | None = None
    container_env: list[dict[str, Any]] | None = None


class CustomProfileResponse(BaseModel):
    """A single profile row for a custom model: the Default or a named profile.

    One row per AIMProfileSet. ``profile`` embeds the effective AIMProfile (the
    one deploy would pin) so the existing profile-summary UI renders unchanged;
    ``selector`` and ``customProfile`` carry the authored intent the edit drawer
    hydrates from. ``name`` is the reserved literal ``default`` for the Default
    row; ``resourceName`` always carries the real AIMProfileSet resource name.
    """

    name: str = Field(
        ..., description="AIMProfileSet resource name, or the reserved literal 'default' for the Default."
    )
    display_name: str = Field(..., description="Human-facing label ('Default' for the Default row).")
    is_default: bool = Field(
        ..., description="True for the engine-owned Default set, classified by provenance on read."
    )
    resource_name: str = Field(
        ..., description="Real AIMProfileSet resource name (metadata.name), stable for deploy pins and debugging."
    )
    created_at: datetime | None = Field(None, description="AIMProfileSet creation timestamp.")
    created_by: str | None = Field(
        None, description="Submitter of an AIWB-authored set; absent for the engine-owned Default."
    )
    status: CustomProfileStatus = Field(default_factory=CustomProfileStatus)
    in_use_by: list[ProfileInUseRef] = Field(
        default_factory=list,
        description="Deployments currently pinning this profile; empty when none reference it.",
    )
    selector: ProfileSelector = Field(
        default_factory=ProfileSelector,
        description="Authored filter narrowing which base profile the set derives from.",
    )
    custom_profile: CustomProfileConfiguration = Field(
        default_factory=CustomProfileConfiguration,
        description=(
            "User-authored overrides (image, engineArgs, etc.) overlaid onto the derived profile. "
            "Server-composed identity, model sources, and selector axes are excluded."
        ),
    )
    profile: AIMProfileResource | None = Field(
        None,
        description="Effective derived AIMProfile (the one deploy would pin); null when none has been emitted yet.",
    )


class CustomProfilePatchRequest(BaseModel):
    """Partial update body for a named custom-model profile.

    Every field mirrors ``CustomProfileCreateRequest`` but is optional; supply
    only the fields to change. The service rejects an empty body (no field set)
    with a 400 after ``model_dump(exclude_unset=True)``, matching the model
    PATCH contract. Two groups of edits are supported and may be combined:

    * **Rename** — ``display_name`` rewrites the profile's display-name
      annotation. Kubernetes object names are immutable, so a rename never
      changes the AIMProfileSet resource name. The reserved name 'Default' and a
      blank name are rejected (422) via the shared display-name validator.
    * **Configuration** — the four narrowing axes plus ``image`` / ``custom_profile``
      rewrite the set's ``spec.selector`` and ``spec.overrides`` together so the
      accelerator count cannot drift apart from the derived profile's
      tensor-parallel-size.

    ``custom_profile`` is the typed, closed ``CustomProfileConfiguration`` (not a
    free-form dict) so read and write share one field set and an authored profile
    round-trips losslessly through the edit drawer. Merge-patch semantics apply
    to its map fields (``engineArgs`` / ``engineEnv``): a present key is set, a
    key sent as ``null`` resets to the aim-engine default, and an omitted key is
    left unchanged.
    """

    display_name: CustomProfileDisplayName | None = Field(
        None,
        min_length=1,
        description=(
            "Updated human-facing label. Must be unique among the model's profiles; "
            "the reserved name 'Default' is rejected."
        ),
        examples=["High speed fun v2"],
    )
    accelerator_model: str | None = Field(
        None,
        min_length=1,
        description="Accelerator model the profile targets (e.g. 'MI300X'); one of the values from runtime-profile-options.",
        examples=["MI300X"],
    )
    accelerator_count: int | None = Field(
        None,
        gt=0,
        description="Accelerator (GPU) count, composed into both the selector and the overrides so they cannot disagree.",
        examples=[8],
    )
    precision: str | None = Field(
        None,
        min_length=1,
        description="Precision the base template emits (e.g. 'fp8'); precision is base-determined.",
        examples=["fp8"],
    )
    metric: str | None = Field(
        None,
        min_length=1,
        description="Optimization metric (e.g. 'latency', 'throughput'); one of the values from runtime-profile-options.",
        examples=["latency"],
    )
    image: str | None = Field(
        None,
        min_length=1,
        description="Container image reference for the profile's runtime.",
        examples=["amdenterpriseai/aim-base:0.11"],
    )
    custom_profile: CustomProfileConfiguration | None = Field(
        None,
        description=(
            "Complete runtime overrides (engineArgs, engineEnv, containerEnv, etc.) merged onto the "
            "profile. Typed as the closed CustomProfileConfiguration so it round-trips with the read "
            "path. If `customProfile.image` is supplied it must agree with the top-level `image`."
        ),
    )

    @model_validator(mode="after")
    def _reject_conflicting_image_refs(self) -> "CustomProfilePatchRequest":
        """Reject disagreeing image refs so the deployment image stays unambiguous (422 from FastAPI)."""
        if self.custom_profile is None:
            return self
        profile_image = self.custom_profile.image
        if profile_image is None:
            return self
        if profile_image == "":
            raise ValueError(
                "customProfile.image must not be an empty string. "
                "Either omit customProfile.image so the top-level image is used, "
                "or set it to the same non-empty image reference."
            )
        if self.image is not None and profile_image != self.image:
            raise ValueError(
                f"customProfile.image '{profile_image}' conflicts with the top-level "
                f"image '{self.image}'. Either omit customProfile.image so the top-level "
                "image is used, or set them to the same reference."
            )
        return self


# CustomModelResponse.profiles forward-references CustomProfileResponse, which is
# defined later in this module; rebuild once both are in scope.
CustomModelResponse.model_rebuild()
