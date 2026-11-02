# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT


from typing import Any, get_args

from pydantic import Field, computed_field, field_validator, model_validator

from api_common.schemas import BaseModel

from ..artifacts.schemas import ArtifactName
from .constants import AIM_SERVING_READY_CONDITIONS, MAX_LORA_RANK_ENGINE_ARG, LoraRank
from .crds import AIMModelResource, AIMServiceResource, HTTPRouteResource
from .enums import AdapterMode, AIMModelStatus, OptimizationMetric
from .utils import extract_endpoints, is_condition_true

# Mirrors the AIMService CRD's own maxItems on spec.adapters. Bounded here so an oversized list is a
# field-level 422 rather than an opaque admission failure, and so one request cannot fan out into an
# unbounded number of per-adapter compatibility reads at deploy time.
_MAX_ADAPTERS = 64

# Spelled into the engine-arg refusal so a caller moving the value across also learns which
# ranks it may hold, instead of paying a second 422 to find out.
_SUPPORTED_LORA_RANKS = ", ".join(str(rank) for rank in get_args(LoraRank))


class AdaptersMixin(BaseModel):
    """The adapter set a request declares, shared by deploy and patch so the bound is stated once."""

    adapters: list[ArtifactName] | None = Field(
        None,
        max_length=_MAX_ADAPTERS,
        description=(
            "Names of adapter artifacts in this project to serve alongside the base model, "
            "written to spec.adapters as AIMArtifact references. Entries must be unique, and the "
            "list is the complete set the deployment should serve. Per-adapter progress is "
            "reported on status.adapters of the deployment."
        ),
        examples=[["my-lora-adapter"]],
    )

    @model_validator(mode="after")
    def _adapters_are_unique(self) -> "AdaptersMixin":
        # spec.adapters is an atomic list, so unlike a set-typed field the API server accepts a
        # repeat and the engine would attach the same artifact twice. Named here, where the
        # response can point at the offending value.
        adapters = self.adapters or []
        duplicates = sorted({name for name in adapters if adapters.count(name) > 1})
        if duplicates:
            raise ValueError(f"adapters entries must be unique, repeated: {', '.join(duplicates)}")
        return self


class ScalingPolicyMixin(BaseModel):
    """Mixin for scaling policy fields.

    For autoscaling, all three fields (minReplicas, maxReplicas, autoScaling) must be
    provided together. For fixed replicas, use only the 'replicas' field instead.

    NOTE: aim-engine enables KEDA when minReplicas/maxReplicas are set, so these fields
    should only be used with a valid autoScaling configuration containing KEDA metrics.
    """

    min_replicas: int | None = Field(
        None,
        ge=1,
        description="Minimum number of replicas for autoscaling. Requires autoScaling config.",
        examples=[1],
    )
    max_replicas: int | None = Field(
        None,
        ge=1,
        description="Maximum number of replicas for autoscaling. Requires autoScaling config.",
        examples=[5],
    )
    auto_scaling: dict[str, Any] | None = Field(
        None,
        description=(
            "KEDA autoscaling configuration with custom metrics. Required when using minReplicas/maxReplicas. "
            "Example: {'metrics': [{'type': 'PodMetric', 'podmetric': {'metric': {...}, 'target': {...}}}]}"
        ),
    )

    @model_validator(mode="after")
    def validate_scaling_policy(self) -> "ScalingPolicyMixin":
        """Validate that autoscaling fields are provided together."""
        fields = [self.min_replicas, self.max_replicas, self.auto_scaling]
        fields_set = sum(1 for f in fields if f is not None)

        # All three must be provided together or none at all
        # This prevents accidentally enabling KEDA without valid triggers in aim-engine
        if fields_set > 0 and fields_set < 3:
            raise ValueError(
                "Autoscaling requires all three fields: minReplicas, maxReplicas, and autoScaling. "
                "For fixed replicas, use only the 'replicas' field instead."
            )

        # Validate max_replicas >= min_replicas
        if self.min_replicas is not None and self.max_replicas is not None:
            if self.max_replicas < self.min_replicas:
                raise ValueError(f"maxReplicas ({self.max_replicas}) must be >= minReplicas ({self.min_replicas})")

        # autoScaling must not be empty (would cause KEDA errors)
        if self.auto_scaling is not None and self.auto_scaling == {}:
            raise ValueError("autoScaling cannot be empty - provide valid KEDA metrics configuration")

        return self


class ListAimsQuery(BaseModel):
    status_filter: list[AIMModelStatus] | None = Field(default=None, description="Filter by status(es)")


class AIMResponse(AIMModelResource):
    """AIMResponse API response schema.

    Pure pass-through of the ``AIMModelResource`` CRD shape, which backs both
    cluster-scoped ``AIMClusterModel`` and namespace-scoped ``AIMModel``
    resources. AIWB performs no enrichment or formatting on the response —
    consumers read accelerator metadata directly from
    ``status.discoveredProfiles.byHardware[]`` on the resource, mirroring what
    the aim-engine controller publishes.
    """


class AIMDeployRequest(ScalingPolicyMixin, AdaptersMixin):
    """Schema for deploying an AIM with optional scaling policy configuration.

    The `model` field can reference either a cluster-scoped AIMClusterModel or a
    namespace-scoped AIMModel (fine-tuned). The API auto-detects which type it is.
    """

    model: str = Field(
        ...,
        description=(
            "Model resource name. Either an AIMClusterModel name (e.g., 'meta-llama-3-8b') "
            "or a namespace-scoped AIMModel name (fine-tuned model UUID). "
            "The API auto-detects which type it is."
        ),
        examples=["meta-llama-3-8b", "7f3b6c8e-2a1d-4b9f-9c12-1a2b3c4d5e6f"],
    )
    replicas: int = Field(
        1,
        description="Number of replicas for this service.",
        examples=[1, 3],
    )
    image_pull_secrets: list[str] | None = Field(
        None,
        description=(
            "Names of the secrets for pulling AIM container images. "
            "Honored only on cluster-scoped AIMClusterModel deployments; "
            "rejected with 400 when sent for custom-onboarded/fine-tuned models."
        ),
        examples=[["registry-credentials"]],
    )
    hf_token: str | None = Field(
        None,
        description=(
            "Hugging Face token for accessing private models (if required). "
            "Honored only on cluster-scoped AIMClusterModel deployments; "
            "rejected with 400 when sent for custom-onboarded/fine-tuned models."
        ),
        examples=["hf_xxxxxxxxxxxx"],
    )
    metric: OptimizationMetric | None = Field(
        None,
        description=(
            "Profile-selector field written to spec.profile.selector.metric "
            "(latency or throughput). Ignored when profileName is set."
        ),
    )
    precision: str | None = Field(
        None,
        description=(
            "Profile-selector field written to spec.profile.selector.precision "
            "(e.g. fp8, fp16). Ignored when profileName is set."
        ),
        examples=["fp8", "fp16"],
    )
    gpu_model: str | None = Field(
        None,
        description=(
            "Profile-selector field written to spec.profile.selector.acceleratorModel "
            "(e.g. MI300X). Ignored when profileName is set."
        ),
        examples=["MI300X"],
    )
    gpu_count: int | None = Field(
        None,
        ge=1,
        description=(
            "Number of GPUs per replica. Not a profile selector — "
            "the selector picks profiles by hardware model. When set, written to "
            "``spec.profileOverrides.acceleratorCount`` as a per-service override "
            "on top of the resolved profile."
        ),
        examples=[1, 8],
    )
    engine_args: dict[str, Any] | None = Field(
        None,
        description="Engine launch arguments (e.g. vLLM flags). Forwarded to AIMService.spec.profileOverrides.engineArgs.",
        examples=[{"max-model-len": 8192}],
    )
    engine_env: list[dict[str, Any]] | None = Field(
        None,
        description=(
            "Engine-process environment variables as name/value entries. "
            "Converted to AIMService.spec.profileOverrides.engineEnv."
        ),
        examples=[[{"name": "VLLM_LOGGING_LEVEL", "value": "DEBUG"}]],
    )
    container_env: list[dict[str, Any]] | None = Field(
        None,
        description="Container env entries (K8s EnvVar shape). Forwarded to AIMService.spec.profileOverrides.containerEnv.",
    )
    profile_name: str | None = Field(
        None,
        description=(
            "Which profile to deploy. Resolution depends on the model: for a cluster-scoped model "
            "this is a literal AIMClusterProfile name, while for a custom-onboarded model it is an "
            "identifier from that model's profile list (a profile name, or `default` for the "
            "engine-provided one) which the server resolves to the profile it derives. Custom model "
            "clients therefore never handle engine-generated profile names. When unset, a custom "
            "model deploys its Default and a cluster-scoped model lets the engine resolve by aimId. "
            "Rejected with 400 for fine-tuned models, which have no selectable profiles, and when "
            "the identifier is unknown to the model or its profile is not ready."
        ),
        examples=["high-speed"],
    )
    display_name: str | None = Field(
        None,
        description="User-visible display name for this AIM deployment. Stored as a K8s annotation; any characters are allowed.",
    )
    adapter_mode: AdapterMode | None = Field(
        None,
        description=(
            "How the deployment admits adapters, written to spec.adapterMode. 'static' serves "
            "exactly the adapters listed at deploy time; 'dynamic' allows adapters to be attached "
            "and detached while it runs. Immutable once deployed — a deployment created without "
            "it keeps the cluster default ('static') for its whole life."
        ),
        examples=["dynamic"],
    )
    max_lora_rank: LoraRank | None = Field(
        None,
        description=(
            "Highest LoRA rank the deployment can serve, written to spec.adapterRuntime.maxRank. "
            "Requires adapterMode 'dynamic', where adapters are not known at deploy time and the "
            "ceiling must be reserved up front; under any other mode the deploy is refused, since "
            "a static deployment derives its ceiling from the adapters it declares."
        ),
        examples=[16],
    )

    @field_validator("max_lora_rank", mode="before")
    @classmethod
    def _max_lora_rank_is_an_integer(cls, value: Any) -> Any:
        # Literal[1, ...] matches True by equality and coerces 32.0 to 32, so either would
        # silently deploy at a rank the caller never spelled out.
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError("must be an integer")
        return value

    # Runs before the dynamic-only check so a request that violates both is told about the
    # unsupported spelling first, which is the more actionable of the two.
    @model_validator(mode="after")
    def _max_lora_rank_engine_arg_is_rejected(self) -> "AIMDeployRequest":
        if self.engine_args and MAX_LORA_RANK_ENGINE_ARG in self.engine_args:
            raise ValueError(
                f"engineArgs['{MAX_LORA_RANK_ENGINE_ARG}'] is not accepted; use the maxLoraRank "
                f"field instead, which takes one of {_SUPPORTED_LORA_RANKS} under adapterMode "
                f"'dynamic'"
            )
        return self

    @model_validator(mode="after")
    def _max_lora_rank_is_a_dynamic_only_field(self) -> "AIMDeployRequest":
        if self.max_lora_rank is not None and self.adapter_mode != AdapterMode.DYNAMIC:
            raise ValueError(
                "maxLoraRank requires adapterMode 'dynamic'; a static deployment takes its rank "
                "ceiling from the adapters it declares"
            )
        return self


class AIMServicePatchRequest(ScalingPolicyMixin, AdaptersMixin):
    """Request schema for patching an AIMService.

    All fields are optional. Include only the fields you want to update. For scaling policy, all
    three fields (minReplicas, maxReplicas, autoScaling) must be provided together. ``adapters`` and
    the scaling policy may be changed in the same request; both are written as one atomic update.
    """


class AIMServiceResponse(AIMServiceResource):
    """AIMService API response schema.

    Inherits all fields from AIMServiceResource (metadata, spec, status).
    This is the live K8s CRD data with namespace already in metadata.
    """

    httproute: HTTPRouteResource | None = Field(None, exclude=True)
    inference_service_name: str | None = Field(None, exclude=True)

    @computed_field
    def status_value(self) -> str:
        return self.status.status.value

    @computed_field
    def endpoints(self) -> dict[str, str]:
        # Endpoints require both routing and inference service to be ready.
        # We check both conditions because endpoints represent inference service URLs
        # and should only be shown when the full stack is functional.
        if not all(is_condition_true(self.status.conditions, c) for c in AIM_SERVING_READY_CONDITIONS):
            return {}
        return extract_endpoints(self, httproute=self.httproute, inference_service_name=self.inference_service_name)
