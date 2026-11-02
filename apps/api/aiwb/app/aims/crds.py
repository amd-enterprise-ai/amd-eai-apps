# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Pydantic models for AIMService CRD responses from Kubernetes.

These models are intentionally minimal and lenient:
- Only include fields we actually access in the code
- All fields optional with sensible defaults
- Parsing won't fail if K8s adds/removes fields
- Uses BaseModel with alias_generator=to_camel for K8s camelCase fields
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, computed_field, model_validator

from api_common.schemas import BaseModel

from ..dispatch.crds import K8sMetadata
from ..workloads.constants import WORKLOAD_ID_LABEL
from .constants import LoraRank
from .enums import AdapterMode, AdapterState, AIMVersionPolicy, ResolutionScope
from .enums import AIMArtifactStatus as AIMArtifactStatusEnum
from .enums import AIMModelStatus as AIMModelStatusEnum
from .enums import AIMServiceStatus as AIMServiceStatusEnum


class AIMModelMetadata(BaseModel):
    canonical_name: str | None = None
    description_full: str | None = None
    hf_token_required: bool | None = None
    source: str | None = None
    tags: list[str] = Field(default_factory=list)
    title: str | None = None
    variants: list[str] = Field(default_factory=list)


class OciMetadata(BaseModel):
    created: str | None = None
    description: str | None = None
    licenses: str | None = None
    revision: str | None = None
    source: str | None = None
    title: str | None = None
    vendor: str | None = None
    version: str | None = None


class AIMImageMetadata(BaseModel):
    model: AIMModelMetadata = Field(default_factory=AIMModelMetadata)
    oci: OciMetadata = Field(default_factory=OciMetadata)
    original_labels: dict[str, str] = Field(default_factory=dict)


class AIMModelDiscoveryConfig(BaseModel):
    """Discovery configuration for AIMModel.

    Mirrors `AIMModelDiscoveryConfig` in aim-engine. Controls which metadata
    aim-engine extracts from the source image and whether per-profile CRs are
    auto-created.
    """

    extract_metadata: bool | None = None
    create_service_templates: bool | None = None


class ProfileHardwareGroupEntry(BaseModel):
    """A single (metric, precision) pair under a hardware group.

    Kept loose as ``str | None`` — these are aim-engine enum values that AIWB
    only forwards, not switches on, so widening the engine's enum surface
    here would couple AIWB to changes it doesn't otherwise care about.
    """

    metric: str | None = None
    precision: str | None = None


class ProfileHardwareGroup(BaseModel):
    """One accelerator footprint that an AIM can run on.

    Groups by ``(acceleratorType, acceleratorModel, acceleratorCount)`` so
    catalog consumers can describe an AIM's headline hardware without listing
    AIMProfile CRs themselves. ``supported`` reflects whether the cluster
    actually has nodes that satisfy this footprint.
    """

    # Loose ``str | None`` rather than narrowed to AIWB's AcceleratorType
    # enum: the engine owns the vocabulary (currently cpu/gpu, plus any
    # future family it adds) and AIWB only forwards the value, so we
    # accept whatever the engine emits verbatim.
    accelerator_type: str | None = None
    accelerator_model: str | None = None
    accelerator_count: int | None = None
    supported: bool = False
    profiles: list[ProfileHardwareGroupEntry] = Field(default_factory=list)


class DiscoveredProfileCounts(BaseModel):
    """Per-AIM accelerator/profile discovery breakdown.

    aim-engine publishes this on ``AIMModel.status`` so consumers can render
    accelerator metadata directly from the model resource instead of joining
    against AIMProfile lists. The ``byHardware`` array is sorted by
    ``(acceleratorType, acceleratorModel, acceleratorCount)`` and has no
    ``primary`` flag — representative selection is the consumer's choice.
    """

    total: int | None = None
    supported: int | None = None
    unsupported: int | None = None
    by_hardware: list[ProfileHardwareGroup] = Field(default_factory=list)


class AIMProfileSpec(BaseModel):
    """Spec for AIMProfile (namespace- or cluster-scoped).

    Mirrors `AIMProfileSpecCommon` in aim-engine. Only the fields AIWB
    actually consumes are typed; less-used fields stay loose to preserve
    forward compatibility with aim-engine-side additions.

    ``extra="allow"`` is required for DR-correctness: aim-engine populates
    additional spec fields the API does not model, and those must survive a
    ``model_validate`` → ``model_dump`` round-trip when the profile is mirrored
    to the durable S3 manifest. Pydantic v2 stores extras in
    ``__pydantic_extra__`` and re-emits them under their original (camelCase)
    keys, which is what Kubernetes expects on apply.
    """

    model_config = ConfigDict(extra="allow")

    aim_id: str = ""
    model_id: str | None = None
    # Engine-assigned identity of the base profile a derived profile was copied from.
    profile_id: str | None = None
    engine: str | None = None
    metric: str | None = None
    precision: str | None = None
    # Optimization hierarchy: optimized > general > preview > unoptimized.
    type: str | None = None
    primary: bool | None = None
    accelerator_model: str | None = None
    # `gpu` or `cpu`. Drives resource derivation strategy in aim-engine.
    accelerator_type: str | None = None
    accelerator_count: int | None = None
    image: str | None = None
    # engineArgs is a free-form JSON object (CLI args for the inference engine).
    engine_args: dict[str, Any] | None = None
    # engineEnv is a map[string]string of env vars for the inference engine subprocess.
    engine_env: dict[str, str] | None = None
    container_env: list[dict[str, Any]] | None = None
    model_sources: list[dict[str, Any]] | None = None
    image_pull_secrets: list[dict[str, Any]] | None = None
    # Capabilities the profile's runtime supports, as an unordered set. `adapters`
    # is the signal that the profile can serve LoRA adapters; the engine owns the
    # vocabulary, so unknown entries pass through as plain strings.
    features: list[str] = Field(default_factory=list)


class AIMProfileStatus(BaseModel):
    """Status for AIMProfile (namespace- or cluster-scoped)."""

    status: str | None = None
    version: str | None = None
    matching_nodes: int | None = None
    # Human-readable summary like "1 x MI300X" or "CPU".
    hardware_summary: str | None = None
    resources: dict[str, Any] | None = None
    resolved_node_affinity: dict[str, Any] | None = None
    conditions: list[dict[str, Any]] | None = None


class AIMProfileResource(BaseModel):
    """AIMProfile CRD resource (namespace- or cluster-scoped).

    Cluster-scoped resources (kind `AIMClusterProfile`) have an empty
    `metadata.namespace`; namespace-scoped resources (kind `AIMProfile`)
    always carry it. The shape is otherwise identical, matching aim-engine's
    Go types where one `AIMProfileSpec`/`AIMProfileStatus` backs both CRDs.
    """

    metadata: K8sMetadata
    spec: AIMProfileSpec = Field(default_factory=AIMProfileSpec)
    status: AIMProfileStatus = Field(default_factory=AIMProfileStatus)


class AIMModelSourceEnvVar(BaseModel):
    """A single environment variable applied to a model source.

    ``name`` is the variable name (e.g. ``HF_TOKEN``, ``AWS_ENDPOINT_URL``); the
    value is supplied inline or from a secret reference. Additional keys such as
    ``value`` and ``valueFrom`` are preserved as-is so a read-modify-write of the
    resource does not drop credential configuration authored elsewhere.
    """

    model_config = ConfigDict(extra="allow")

    name: str | None = None


class AIMModelSource(BaseModel):
    """Source for model weights in an AIMModel or AIMClusterModel.

    ``env`` carries per-source credential overrides (e.g. HF_TOKEN) in the
    v1alpha2 ``spec.profiles.overrides.modelSources[]`` shape. Left as ``None``
    (rather than an empty list) so it is omitted on dump when unused — the CRD
    treats absent and empty differently for some sources.
    """

    model_id: str = ""
    source_uri: str = ""
    # Tying each source to a precision lets aim-engine custom-weight onboarding
    # match sources to compatible profiles.
    precision: str | None = None
    env: list[AIMModelSourceEnvVar] | None = None


class AIMModelCustom(BaseModel):
    """Custom model settings (fine-tuned / custom-weight models)."""

    version_policy: AIMVersionPolicy | None = None
    hardware: list[dict[str, Any]] | None = None
    type: str | None = None


class ProfileSelectorModelRef(BaseModel):
    """Reference to the source AIMModel a derivation pulls profiles from.

    ``scope`` is ``Namespace`` or ``Cluster`` (or ``Auto``); for BYOM onboard it
    pins the derivation to a namespace-scoped base-image AIMModel.
    """

    name: str = ""
    scope: str | None = None


class ProfileSelector(BaseModel):
    """Filter half of ``derivedFrom`` — narrows which source profiles match.

    ``extra="allow"`` keeps optional aim-engine filter axes we do not model
    (e.g. ``acceleratorModel``, ``precision``) round-trippable. For BYOM onboard
    only ``role`` + ``model_ref`` are set; per CEL, identity fields (aimId /
    modelId) are forbidden when ``role=base``.
    """

    model_config = ConfigDict(extra="allow")

    role: str | None = None
    model_ref: ProfileSelectorModelRef | None = None


class AIMModelProfilesDerivedFrom(BaseModel):
    """Source half of the derivation — which existing profiles to copy from.

    Only ``selector`` is modeled; the alternate ``sourceRef`` (discovery-cache
    source) is not used by the onboard flow.
    """

    selector: ProfileSelector = Field(default_factory=ProfileSelector)


class ProfileOverrides(BaseModel):
    """Stamp half of the derivation — identity, image, and weights overlaid
    onto the derived profile. For ``role=base`` derivations CEL requires
    ``aim_id`` and ``model_id`` (base profiles carry no identity of their own);
    ``image`` overrides the runtime container image and ``model_sources`` supply
    the BYO weights (with per-source ``env``). Opaque onboard ``customProfile``
    keys (engine, precision, etc.) pass through via ``extra="allow"``."""

    model_config = ConfigDict(extra="allow")

    aim_id: str | None = None
    model_id: str | None = None
    image: str | None = None
    model_sources: list[AIMModelSource] = Field(default_factory=list)


class AIMModelProfilesSpec(BaseModel):
    """v1alpha2 ``spec.profiles`` block driving profile derivation.

    ``version_policy`` / ``version`` sit here (not under ``derived_from``) to
    mirror the CRD. CEL: ``version`` is required when ``version_policy`` is
    ``pinned`` and forbidden when it is ``latest``/``all`` — the onboard builder
    uses ``all`` and leaves ``version`` unset.
    """

    derived_from: AIMModelProfilesDerivedFrom = Field(default_factory=AIMModelProfilesDerivedFrom)
    version_policy: str | None = None
    version: str | None = None
    overrides: ProfileOverrides = Field(default_factory=ProfileOverrides)


class AIMProfileSetSpec(BaseModel):
    """Spec for a namespace-scoped AIMProfileSet.

    Unlike ``AIMModel.spec.profiles`` (which nests the filter under
    ``derivedFrom.selector``), the AIMProfileSet CRD carries ``selector`` at the
    top level. ``extra="allow"`` (plus the nested selector/overrides) keeps
    engine-authored fields — ``image``, ``imagePullSecrets``, ``sourceRef``,
    ``serviceAccountName`` — round-trippable through ``model_validate`` →
    ``model_dump`` on patch.
    """

    model_config = ConfigDict(extra="allow")

    selector: ProfileSelector = Field(default_factory=ProfileSelector)
    overrides: ProfileOverrides = Field(default_factory=ProfileOverrides)
    version_policy: str | None = None
    version: str | None = None


class AIMProfileSetResource(BaseModel):
    """AIMProfileSet CRD resource (namespace-scoped)."""

    metadata: K8sMetadata
    spec: AIMProfileSetSpec = Field(default_factory=AIMProfileSetSpec)


class AIMModelSpec(BaseModel):
    """Spec shared by AIMModel and AIMClusterModel (namespace- or cluster-scoped).

    aim-engine reuses one Go ``AIMModelSpec`` for both cluster- and namespace-
    scoped CRDs; AIWB mirrors that. Namespace-only fields (``model_sources``,
    ``custom``, ``env``) are simply unused on cluster-scoped resources.

    Carries both the legacy v1alpha1 flat fields (``image``, ``model_sources``,
    ``env``) used by fine-tuning/official flows and the v1alpha2 ``profiles``
    derivation block used by custom-model onboard. CEL enforces image XOR
    profiles, so a single object only ever populates one shape.

    Note these two shapes are NOT made exclusive by ``model_dump`` alone:
    ``image``/``model_sources``/``env`` default to ``""``/``[]``/``[]`` (not
    ``None``), so dumping an instance with ``exclude_none=True`` would still emit
    empty legacy fields alongside ``profiles`` and trip the CEL rule. Callers
    that build a v1alpha2 manifest must therefore emit a profiles-only spec
    explicitly — the custom-model onboard builder composes ``{"profiles": ...}``
    from the ``AIMModelProfilesSpec`` dump rather than serializing a full
    ``AIMModelSpec``. This model is still used unchanged for *reading back*
    either shape (where the populated fields are exactly what the server
    returned).
    """

    aim_id: str | None = None
    image: str = ""
    image_metadata: AIMImageMetadata | None = None
    model_sources: list[AIMModelSource] = Field(default_factory=list)
    custom: AIMModelCustom | None = None
    env: list[dict[str, Any]] = Field(default_factory=list)
    # Discovery controls (see AIMModelDiscoveryConfig). Optional — aim-engine
    # supplies defaults when omitted.
    discovery: AIMModelDiscoveryConfig | None = None
    profiles: AIMModelProfilesSpec | None = None


class AIMCondition(BaseModel):
    """A single ``metav1.Condition`` entry, shared across AIM CRD status blocks."""

    last_transition_time: str | None = None
    message: str = ""
    observed_generation: int | None = None
    reason: str = ""
    status: str = ""
    type: str = ""


class AIMModelStatusFields(BaseModel):
    """Status for AIMModel (namespace- or cluster-scoped).

    aim-engine reuses one Go `AIMModelStatus` for both scopes; AIWB does the
    same.
    """

    status: AIMModelStatusEnum = AIMModelStatusEnum.NOT_AVAILABLE
    conditions: list[AIMCondition] = Field(default_factory=list)
    image_metadata: AIMImageMetadata = Field(default_factory=AIMImageMetadata)
    source_type: str | None = None
    # Resolved model architecture identifier. Populated by the v1alpha2
    # controller from spec.aimId (custom path) or discovered metadata
    # (image-discovery path). Read this instead of spec.aim_id when the
    # consumer needs the resolved value rather than the user's input.
    aim_id: str | None = None
    # Hardware-grouped discovery breakdown — the catalog reads accelerator
    # metadata from here because AIMModel.spec is accelerator-agnostic. None
    # on clusters running an engine that doesn't emit this field yet; the
    # catalog then surfaces null accelerator fields rather than dropping the
    # AIM.
    discovered_profiles: DiscoveredProfileCounts | None = None
    # Count summary emitted by aim-engine for managed profile classes (e.g.
    # base/deployable). Kept as a loose map because the engine may add keys.
    managed_profiles: dict[str, int] | None = None


class AIMModelResource(BaseModel):
    """AIMModel CRD resource (namespace- or cluster-scoped).

    Cluster-scoped resources (kind `AIMClusterModel`) have an empty
    `metadata.namespace`; namespace-scoped resources (kind `AIMModel`) always
    carry it. The shape is otherwise identical, matching aim-engine's Go
    types where one `AIMModelSpec`/`AIMModelStatus` backs both CRDs.
    """

    metadata: K8sMetadata
    spec: AIMModelSpec = Field(default_factory=AIMModelSpec)
    status: AIMModelStatusFields = Field(default_factory=AIMModelStatusFields)


class ResolvedRef(BaseModel):
    """Reference aim-engine resolved to a concrete resource.

    Mirrors aim-engine's ``AIMResolvedReference``: ``resolved_model`` and
    ``resolved_profile`` on AIMService, ``resolved_parent`` on AIMArtifact.

    ``kind`` and ``uid`` are populated by AIMArtifact but not AIMService.
    """

    model_config = ConfigDict(extra="allow")

    name: str | None = Field(None, description="Resolved resource name")
    namespace: str | None = Field(None, description="Namespace when namespace-scoped")
    # A scope the engine adds later must not fail validation for the whole resource; known values
    # still resolve to the enum, anything else passes through as the raw string.
    scope: Annotated[ResolutionScope | str, Field(union_mode="left_to_right")] | None = Field(
        None, description="Scope the reference resolved at"
    )
    kind: str | None = Field(None, description="Kind of the resolved reference, when known")
    uid: str | None = Field(None, description="Unique identifier of the resolved reference, when known")


class AIMArtifactSpec(BaseModel):
    """Spec for a namespace-scoped AIMArtifact CR."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    source_uri: str | None = None
    model_id: str | None = None
    # Canonical model ids an adapter may attach to. Nothing resolves them, so it is owned by nothing
    # and outlives every base it names. Immutable once set.
    compatible_with: list[str] | None = None
    rank: int | None = None
    # Credentials for reading source_uri. None rather than [] so it is omitted on dump when unused.
    env: list[AIMModelSourceEnvVar] | None = None


class AIMArtifactDownloadStatus(BaseModel):
    """Progress of aim-engine's fetch of the artifact's source.

    Reported per attempt while the download is retried, so ``attempt`` and ``total_attempts`` move
    independently of the artifact's own status. Fields aim-engine may add later pass through
    unvalidated rather than being dropped.
    """

    model_config = ConfigDict(extra="allow")

    attempt: int | None = None
    total_attempts: int | None = None
    message: str | None = None
    protocol: str | None = None
    protocol_sequence: str | None = None


class AIMArtifactStatusFields(BaseModel):
    """Status of a namespace-scoped AIMArtifact CR.

    The controller reports sizing and progress detail (``allocatedSize``, ``progress``,
    ``persistentVolumeClaim`` and similar) that is passed through unmodelled rather than dropped.
    """

    model_config = ConfigDict(extra="allow")

    # A status the engine adds later must not fail validation for the whole artifact; known values
    # still resolve to the enum, anything else passes through as the raw string.
    status: Annotated[AIMArtifactStatusEnum | str, Field(union_mode="left_to_right")] | None = None
    conditions: list[AIMCondition] = Field(default_factory=list)
    download: AIMArtifactDownloadStatus | None = None
    parent_model_id: str | None = None
    adapter_path: str | None = None
    resolved_parent: ResolvedRef | None = None


class AIMArtifactResource(BaseModel):
    """Namespace-scoped AIMArtifact CRD resource."""

    metadata: K8sMetadata
    spec: AIMArtifactSpec = Field(default_factory=AIMArtifactSpec)
    status: AIMArtifactStatusFields = Field(default_factory=AIMArtifactStatusFields)


class HTTPRoutePathMatch(BaseModel):
    """HTTPRoute path match configuration."""

    type: str | None = Field(None, description="Path match type (e.g., 'PathPrefix')")
    value: str | None = Field(None, description="Path value to match")


class HTTPRouteMatch(BaseModel):
    """HTTPRoute match configuration."""

    path: HTTPRoutePathMatch | None = Field(None, description="Path match configuration")


class HTTPRouteBackendRef(BaseModel):
    """HTTPRoute backend reference."""

    kind: str | None = Field(None, description="Backend resource kind (e.g., 'Service')")
    name: str | None = Field(None, description="Backend resource name")
    port: int | None = Field(None, description="Backend port")


class HTTPRouteRule(BaseModel):
    """HTTPRoute rule configuration."""

    matches: list[HTTPRouteMatch] = Field(default_factory=list, description="Request match conditions")
    backend_refs: list[HTTPRouteBackendRef] = Field(default_factory=list, description="Backend references")


class HTTPRouteSpec(BaseModel):
    """HTTPRoute spec configuration."""

    rules: list[HTTPRouteRule] = Field(default_factory=list, description="Route rules")


class HTTPRouteResource(BaseModel):
    """HTTPRoute CRD resource from Gateway API."""

    metadata: K8sMetadata
    spec: HTTPRouteSpec = Field(default_factory=HTTPRouteSpec)


class CachingConfig(BaseModel):
    """AIMService caching configuration.

    Replaces the deprecated boolean `cacheModel` field. `mode` controls how
    model weights are cached across replicas; `Shared` is the v1alpha2 default
    and matches prior `cacheModel: true` behavior.

    `env` carries env vars injected only into the model-download Job, not the
    inference container. Use this for credentials (e.g. HF_TOKEN) that the
    download step needs but should not be visible to the running model server.
    """

    mode: str = "Shared"
    env: list[dict[str, Any]] = Field(default_factory=list)


class AIMServiceProfileConfig(BaseModel):
    """Profile resolution config for AIMService.

    Mirrors `AIMServiceProfileConfig` in aim-engine. Exactly one
    of `name` (direct reference) or `selector` (criteria-based lookup) should
    be set; if both are omitted aim-engine auto-resolves the profile from
    `spec.model`.

    The `selector` payload is kept as a loose dict so AIWB can pass the FE's
    chosen criteria through unchanged. Recognized keys are `metric`,
    `precision`, `acceleratorModel`, and `type` (optimization tier) —
    aim-engine ranks matches by `type` (optimized > general > preview >
    unoptimized), `primary` flag, then version.

    ``extra="allow"`` mirrors the rationale on ``AIMProfileSpec``: aim-engine
    may introduce additional selector keys or future resolution modes that
    AIWB does not (yet) model, and those must survive a ``model_validate`` →
    ``model_dump`` round-trip so AIWB never silently drops engine-authored
    fields when reading and re-applying an AIMService. Pydantic v2 stores
    extras in ``__pydantic_extra__`` and re-emits them under their original
    (camelCase) keys, which is what Kubernetes expects on apply.
    """

    model_config = ConfigDict(extra="allow")

    name: str | None = None
    selector: dict[str, Any] | None = None


class AIMServiceModelRef(BaseModel):
    """Reference to the AIM an AIMService deploys (``spec.model``).

    ``name`` identifies the target AIM. It may be empty for services created by
    direct image reference; in that case it is populated from the resolved model
    (``status.resolvedModel.name``) once the model has been resolved.
    """

    model_config = ConfigDict(extra="allow")

    name: str | None = None


class AIMServiceAdapterRef(BaseModel):
    """One adapter attached to an AIMService (``spec.adapters[]``).

    ``kind`` + ``name`` reference an AIMArtifact in the service's own namespace,
    and are the only shape aim-engine acts on today. ``source_uri``,
    ``model_id`` and ``rank`` are reserved by the CRD for an inline-adapter form
    the engine does not read yet; CEL couples them (``model_id`` required
    alongside ``source_uri``, ``rank`` permitted only with it), so they are set
    together or left out entirely.
    """

    model_config = ConfigDict(extra="allow")

    kind: Literal["AIMArtifact"] = "AIMArtifact"
    name: str
    source_uri: str | None = None
    model_id: str | None = None
    rank: int | None = None


class AdapterRuntime(BaseModel):
    """spec.adapterRuntime: the LoRA rank ceiling enforced for dynamic-mode adapters.

    Rejected by the CRD when the service is `static` (static services infer their ceiling
    from declared AIMArtifact ranks instead). Unset falls back to namespace/cluster
    RuntimeConfig defaults, then a controller built-in default.
    """

    max_rank: LoraRank | None = None


class AIMServiceSpec(BaseModel):
    model: AIMServiceModelRef = Field(default_factory=AIMServiceModelRef)
    replicas: int = Field(1, description="The current replicas count")
    routing: dict[str, Any] = Field(default_factory=dict)
    caching: CachingConfig = Field(default_factory=CachingConfig)
    runtime_config_name: str | None = None
    # Profile resolution: name (direct), selector (criteria), or omitted
    # entirely (aim-engine auto-resolves from spec.model).
    profile: AIMServiceProfileConfig | None = Field(default=None)
    # Per-service overrides on the resolved profile (engineArgs, containerEnv,
    # acceleratorModel, acceleratorCount, etc.). Materializes as a service-owned
    # namespace AIMProfile copy on the aim-engine side. AIWB currently authors
    # `acceleratorCount` here when the deploy request supplies `gpu_count`; other
    # override knobs have no UI yet.
    profile_overrides: dict[str, Any] | None = Field(default=None)
    # Scaling policy fields
    min_replicas: int | None = Field(None, description="Minimum replicas for autoscaling")
    max_replicas: int | None = Field(None, description="Maximum replicas for autoscaling")
    auto_scaling: dict[str, Any] | None = Field(None, description="Advanced autoscaling config")
    env: list[dict[str, Any]] = Field(default_factory=list)
    image_pull_secrets: list[dict[str, Any]] = Field(default_factory=list)
    # LoRA adapters served alongside the base model. None rather than [] so it is
    # omitted on dump when unused: under the default `static` mode aim-engine
    # mounts the adapter disk only for a service that declares adapters, and an
    # explicit empty array is a claim on the field a read-modify-write would carry
    # over any adapters set elsewhere.
    adapters: list[AIMServiceAdapterRef] | None = None
    # Omitted means "let the CRD default (static) apply". Immutable after
    # creation, so a service created without it can never switch to dynamic.
    adapter_mode: AdapterMode | None = None
    adapter_runtime: AdapterRuntime | None = None


class AIMServiceRuntime(BaseModel):
    """Runtime scaling status from AIMService CRD status.runtime."""

    current_replicas: int | None = None
    desired_replicas: int | None = None
    min_replicas: int | None = None
    max_replicas: int | None = None
    replicas: str | None = None


class AIMServiceAdapterStatus(BaseModel):
    """What aim-engine reports about one attached adapter (``status.adapters[]``).

    Passed through verbatim — AIWB neither aggregates these entries nor derives a
    readiness verdict from them, so the engine stays the only authority on what an
    adapter is doing and a state it adds later reaches consumers unchanged.
    ``name`` is the only field it always sets; the rest appear as the adapter
    progresses.
    """

    model_config = ConfigDict(extra="allow")

    name: str
    # A state the engine adds later must not fail validation for the whole AIMService — that would
    # drop the deployment from the list, and make the get 404 as though it had been deleted. Known
    # values still resolve to the enum, so they stay documented and comparable; anything else
    # passes through as the raw string.
    state: Annotated[AdapterState | str, Field(union_mode="left_to_right")] | None = None
    adapter_path: str | None = None
    model_id: str | None = None
    last_error: str | None = None
    last_observed: datetime | None = None
    # Reported as "loaded/total" (e.g. "3/3"). Reserved: the engine does not
    # populate it yet.
    loaded_replicas: str | None = None


class AIMServiceStatusFields(BaseModel):
    status: AIMServiceStatusEnum = AIMServiceStatusEnum.PENDING
    routing: dict[str, Any] = Field(default_factory=dict)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    observed_generation: int | None = None
    runtime: AIMServiceRuntime = Field(default_factory=AIMServiceRuntime)
    resolved_model: ResolvedRef | None = None
    resolved_profile: ResolvedRef | None = None
    adapters: list[AIMServiceAdapterStatus] | None = None


class AIMServiceResource(BaseModel):
    metadata: K8sMetadata
    spec: AIMServiceSpec = Field(default_factory=AIMServiceSpec)  # type: ignore
    status: AIMServiceStatusFields = Field(default_factory=AIMServiceStatusFields)  # type: ignore
    httproute: HTTPRouteResource | None = Field(None, repr=False, exclude=True)
    inference_service_name: str | None = Field(None, repr=False, exclude=True)

    @computed_field
    def id(self) -> str | None:
        return self.metadata.labels.get(WORKLOAD_ID_LABEL)

    # TODO: drop once aim-engine removes v1alpha1. Backfilling
    # `spec.model.name` is only needed for legacy v1alpha1 deploy-by-image
    # services where the user set `spec.model.image` (no name) and the
    # template reconciler resolved the AIMClusterModel and wrote its
    # resource name to `status.resolvedModel.name`. v1alpha2 always sets
    # `spec.model.name` at create time, so post-v1alpha1 this validator
    # becomes a no-op and can be deleted.
    #
    # Unlike the (reverted) annotation validator, this normalisation fills
    # a user-supplied input field (spec.model.name) that the engine never
    # authors — there is no engine-side write to mask, and PATCH paths that
    # carry spec.model are already overwriting user intent on apply.
    @model_validator(mode="after")
    def _backfill_model_name(self) -> "AIMServiceResource":
        if not self.spec.model.name:
            resolved = self.status.resolved_model
            if resolved and resolved.name:
                self.spec.model.name = resolved.name
        return self
