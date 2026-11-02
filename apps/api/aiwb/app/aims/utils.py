# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT


import hashlib
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, NamedTuple
from urllib.parse import urljoin
from uuid import uuid4

from loguru import logger

from api_common.exceptions import InconsistentStateException, ValidationException

from ..config import CLUSTER_HOST, EAI_APPS_METADATA_PREFIX, SUBMITTER_ANNOTATION
from ..dispatch.crds import K8sMetadata
from ..workloads.constants import CANONICAL_NAME_LABEL, DISPLAY_NAME_ANNOTATION, MODEL_NAME_LABEL
from ..workloads.enums import WorkloadType
from .config import AIM_CLUSTER_RUNTIME_CONFIG_NAME, AIM_GATEWAY_NAME, AIM_GATEWAY_NAMESPACE
from .constants import (
    AIM_PROFILE_SET_RESOURCE,
    AIM_PROFILE_SOURCE_MODEL_LABEL,
    FINE_TUNED_LABEL,
    NAMESPACE_AIM_MODEL_LABEL,
    PROFILE_ORIGIN_LABEL,
    RECONCILER_PIPELINE_ANNOTATION,
    RECONCILER_PIPELINE_PROFILE,
)
from .crds import (
    AIMModelResource,
    AIMProfileResource,
    AIMProfileSetResource,
    AIMServiceResource,
    AIMServiceSpec,
    HTTPRouteResource,
)
from .enums import AIMModelStatus

if TYPE_CHECKING:
    from .schemas import AIMDeployRequest


def is_condition_true(conditions: list[dict[str, Any]], condition_type: str) -> bool:
    """Check if a specific condition type is True.

    Args:
        conditions: List of condition dicts from AIMService status
        condition_type: Condition type to check (e.g., "InferenceServiceReady")

    Returns:
        True if condition exists and status is "True", False otherwise
    """
    for condition in conditions:
        if condition.get("type") == condition_type:
            return condition.get("status") == "True"
    return False


def is_default_profile_set(profile_set: AIMProfileSetResource) -> bool:
    """A set is the Default iff it lacks AIWB's origin label."""
    return PROFILE_ORIGIN_LABEL not in (profile_set.metadata.labels or {})


def classify_default_profile_set(profile_sets: list[AIMProfileSetResource]) -> AIMProfileSetResource:
    """Return the single Default set, raising if not exactly one is present."""
    defaults = [profile_set for profile_set in profile_sets if is_default_profile_set(profile_set)]
    if len(defaults) != 1:
        raise InconsistentStateException(f"Expected exactly one Default AIMProfileSet, found {len(defaults)}")
    return defaults[0]


def owning_profile_set_name(profile: AIMProfileResource) -> str | None:
    """Return the name of the AIMProfileSet that owns ``profile``, or None.

    aim-engine owns every custom-model AIMProfile via an ``AIMProfileSet``
    owner reference, which is the durable link between a derived profile and
    the set it belongs to (the model.name label alone ties a profile to the
    model, not to a specific set).
    """
    for ref in profile.metadata.owner_references or []:
        if ref.get("kind") == AIM_PROFILE_SET_RESOURCE:
            return ref.get("name")
    return None


def profiles_derived_from_set(profiles: list[AIMProfileResource], set_name: str) -> list[AIMProfileResource]:
    """The subset of ``profiles`` owned by the AIMProfileSet named ``set_name``, in list order."""
    return [profile for profile in profiles if owning_profile_set_name(profile) == set_name]


def profiles_without_owning_set(profiles: list[AIMProfileResource]) -> list[AIMProfileResource]:
    """The subset of ``profiles`` no AIMProfileSet owns, in list order.

    These are the profiles aim-engine emitted before sets owned them; a model
    that has never been reconciled by a set-aware engine has only these.
    """
    return [profile for profile in profiles if owning_profile_set_name(profile) is None]


class ServedWeights(NamedTuple):
    """The identities naming the weights a deployment runs, as its resolved profile states them.

    ``model_id`` names the specific weights; ``aim_id`` names the group every variant built from
    them shares. Both are optional because a profile predating either field states neither, and
    ``ServedWeights(None, None)`` is a settled negative — the deployment can serve no adapter —
    rather than an absence, which callers signal with ``None`` instead of an instance.
    """

    model_id: str | None
    aim_id: str | None


def adapter_serves(
    compatible_with: Iterable[str],
    served: ServedWeights,
    *,
    adapter_name: str,
    namespace: str,
) -> bool:
    """Whether an adapter declares the weights a deployment runs, on either identity.

    ``modelId`` is the identity that actually decides this: an adapter is trained against one set
    of weights, and a profile serves one set. ``aimId`` is coarser — every quantised variant of a
    model shares it — so matching on it can admit an adapter the running variant cannot load.

    It is accepted anyway because nothing on the platform writes a modelId into ``compatibleWith``
    yet; every producer writes an aimId, AIWB's own fine-tuning output included, and on the
    families where the two differ a modelId-only rule would reject every adapter the platform
    itself made. Accepting both keeps the precise identity authoritative wherever it is present
    while the old one is still the only thing being written.

    An aimId-only match is logged so the size of the remaining old-axis population stays
    measurable. The aimId arm can be deleted once that count reaches zero — that is, once adapter
    producers record the profile's modelId in ``compatibleWith`` and existing adapters have been
    re-declared against it — after which this becomes the exact rule the name suggests.
    """
    declared = set(compatible_with)
    if served.model_id and served.model_id in declared:
        return True
    if served.aim_id and served.aim_id in declared:
        logger.info(
            "Adapter {} in {} matched model group '{}' rather than the weights '{}' the deployment "
            "serves; compatibleWith={}",
            adapter_name,
            namespace,
            served.aim_id,
            served.model_id or "unknown",
            sorted(declared),
        )
        return True
    return False


def agreed_adapter_weights(declarations: Iterable[Iterable[str]], published_model_ids: Iterable[str]) -> str | None:
    """The one set of weights every requested adapter names and the model publishes, or None.

    ``compatibleWith`` mixes the two identities ``adapter_serves`` matches on, and which of the two
    a given string is cannot be read off the string. Classifying it in isolation gets that wrong in
    both directions: on an unquantised base the group id is also the ``modelId`` of the profile
    serving those weights, so treating that string as a mere family name discards exactly the
    declaration a migrated producer writes; and an adapter naming several variants is counted as
    disagreement even when the model serves only one of them.

    So the question is answered from the side that knows. Keeping only what the model's own
    profiles publish lets a string equal to the group id survive when a profile genuinely serves it,
    and narrows a multi-entry declaration to the variants this model can run.

    Several survivors are several workable answers rather than an impasse: each one is weights every
    requested adapter declared and this deployment can actually resolve, so any of them loads the
    adapters. Abstaining there does not leave the deploy merely unconstrained — a declaration that
    names no group id has nothing else for ``adapter_serves`` to match on, so no pin is a refusal of
    an adapter the model demonstrably serves. One is therefore chosen, by sorted order, so the same
    request pins the same weights every time rather than following the listing's arrival order.

    None only when nothing survives: that is the old-axis population with nothing more precise to
    say than the group, or weights this deployment cannot resolve, and both leave selector
    resolution exactly as unconstrained as it is without adapters. ``published_model_ids`` is what
    keeps that honest — the caller passes the weights eligible for *this* deploy, not every weights
    id sharing the group.
    """
    declared = [frozenset(entry) for entry in declarations]
    if not declared:
        return None
    agreed = frozenset.intersection(*declared) & frozenset(published_model_ids)
    return min(agreed) if agreed else None


def deploy_selector_criteria(deploy_request: "AIMDeployRequest") -> dict[str, str]:
    """The profile-selector criteria the request itself carries, under the engine's own key names.

    One definition serves two readers: the selector written to the CR, and the set of profiles
    aim-engine could resolve against that selector. Deriving them separately is what let the gate
    admit adapters on weights no candidate of this deploy publishes.
    """
    criteria: dict[str, str] = {}
    if deploy_request.metric:
        criteria["metric"] = str(deploy_request.metric)
    if deploy_request.precision:
        criteria["precision"] = deploy_request.precision
    if deploy_request.gpu_model is not None:
        criteria["acceleratorModel"] = deploy_request.gpu_model
    return criteria


def _profile_axis(profile: AIMProfileResource, axis: str) -> str | None:
    """Read the profile field a selector key names, or None when the profile states none."""
    spec = profile.spec
    return {"metric": spec.metric, "precision": spec.precision, "acceleratorModel": spec.accelerator_model}.get(axis)


def profiles_eligible_for_deploy(
    profiles: Iterable[AIMProfileResource],
    *,
    model_name: str,
    criteria: dict[str, str],
) -> list[AIMProfileResource]:
    """The profiles aim-engine could still resolve for this deploy, out of the model group's own.

    A group id spans every quantised variant and every version of a model, so the group's profiles
    are a far wider pool than one deploy can land on. aim-engine's selector match is conjunctive and
    its candidate listing is scoped to the model a profile records as its source, so a profile is
    only a real candidate when it belongs to the model version being deployed *and* agrees with
    every criterion the request carries. Anything the request left open stays open, matching the
    selector it writes.

    Provenance is read from the label aim-engine itself stamps and selects on, so a profile the
    engine attributed to a sibling version is excluded on the strength of what the engine wrote
    rather than on a key it never sets — reading a key the engine does not stamp leaves every
    profile unlabelled, which silently retains the whole group.

    A profile carrying no provenance label is still kept: an unstamped profile is a gap in that
    provenance rather than evidence of belonging to a sibling — the same reason an empty catalog is
    not read as a mismatch. Comparison is case-insensitive, as ``select_custom_deploy_profile``
    already treats precision, so a catalog writing ``FP8`` where the request says ``fp8`` does not
    read as a different profile.
    """
    eligible = []
    for profile in profiles:
        labelled_model = (profile.metadata.labels or {}).get(AIM_PROFILE_SOURCE_MODEL_LABEL)
        if labelled_model and labelled_model != model_name:
            continue
        if any((_profile_axis(profile, axis) or "").lower() != value.lower() for axis, value in criteria.items()):
            continue
        eligible.append(profile)
    return eligible


# Optimization tiers (best first) and metric preference used to pick one profile
# deterministically among several that share the onboarded precision.
_PROFILE_TYPE_RANK = {"optimized": 0, "general": 1, "preview": 2, "unoptimized": 3}
_PROFILE_METRIC_RANK = {"latency": 0, "throughput": 1}
# Sort key for a profile whose type/metric is unrecognized: rank it after every
# known value so unknowns are only ever chosen as a last resort.
_PROFILE_RANK_UNKNOWN = 99


def select_custom_deploy_profile(
    profiles: list[AIMProfileResource], preferred_precision: str
) -> AIMProfileResource | None:
    """Return the Ready AIMProfile matching the onboarded precision, or None.

    A custom model emits one profile per (precision, metric) pair, so pinning an
    arbitrary one loses the user's onboarded precision. Prefer a Ready profile
    whose ``spec.precision`` matches ``preferred_precision``; ties break by
    optimization tier, the engine's ``primary`` flag, metric (latency first),
    then name, matching aim-engine's documented ranking. Returns None when no Ready
    profile carries that precision, so the caller can fall back.
    """
    matching = [
        p
        for p in profiles
        if (p.spec.precision or "").lower() == preferred_precision.lower()
        and p.status
        and str(p.status.status) == AIMModelStatus.READY
    ]
    if not matching:
        return None

    def _rank(profile: AIMProfileResource) -> tuple[int, int, int, str]:
        spec = profile.spec
        return (
            _PROFILE_TYPE_RANK.get((spec.type or "").lower(), _PROFILE_RANK_UNKNOWN),
            0 if spec.primary else 1,
            _PROFILE_METRIC_RANK.get((spec.metric or "").lower(), _PROFILE_RANK_UNKNOWN),
            profile.metadata.name or "",
        )

    return min(matching, key=_rank)


def effective_profile_for_set(
    derived_profiles: list[AIMProfileResource],
    preferred_precision: str | None,
) -> AIMProfileResource | None:
    """Pick the profile a deploy pins for a set, so row summaries agree with deploy.

    A narrowed set derives exactly one profile, so the choice is unambiguous. An
    unnarrowed Default derives several: prefer the Ready profile matching the
    precision the model was onboarded at, and fall back to the first derived
    profile when the model carries no precision annotation or has no Ready profile
    at that precision — the same profile deploy pinned before this selection existed.
    """
    if not derived_profiles:
        return None
    if preferred_precision:
        selected = select_custom_deploy_profile(derived_profiles, preferred_precision)
        if selected is not None:
            return selected
    return derived_profiles[0]


def generate_aim_service_name(aim_id: str | None = None) -> str:
    """
    Generate a unique name for an AIM service.

    Args:
        aim_id: Optional UUID string. If not provided, generates a new UUID internally.

    Returns:
        Service name in format "wb-aim-{hash}" (15 chars total)

    Note:
        - Uses "wb-aim-" prefix + 8-char hash (15 chars total)
        - Prefix ensures name starts with letter (KServe requirement)
        - This allows namespace names up to 63 - 15 - 10 ("-predictor") - 1 = 37 chars
    """
    uuid_str = str(aim_id) if aim_id else str(uuid4())
    hash_digest = hashlib.sha256(uuid_str.encode()).hexdigest()
    return f"wb-aim-{hash_digest[:8]}"


def get_aim_service_internal_url(
    httproute: HTTPRouteResource,
    namespace: str,
) -> str:
    """
    Extract the internal URL for an AIMService from HTTPRoute backend.

    Args:
        httproute: HTTPRoute resource from Kubernetes API
        namespace: Namespace of the AIMService

    Returns:
        Internal service URL

    Raises:
        ValidationException: If HTTPRoute has no rules or no Service backend reference
    """

    if not httproute.spec.rules:
        raise ValidationException("HTTPRoute has no rules")

    # Find first Service backend reference
    service_backend = next(
        (ref for rule in httproute.spec.rules for ref in rule.backend_refs if ref.kind == "Service" and ref.name),
        None,
    )
    if not service_backend:
        raise ValidationException("No Service backend reference found in HTTPRoute")

    port_suffix = f":{service_backend.port}" if service_backend.port not in (None, 80) else ""
    return f"http://{service_backend.name}.{namespace}.svc.cluster.local{port_suffix}"


def get_aim_service_external_url(
    httproute: HTTPRouteResource,
    cluster_host: str = CLUSTER_HOST,
) -> str:
    """
    Extract the external URL for an AIMService from HTTPRoute path.

    Args:
        httproute: HTTPRoute resource from Kubernetes API
        cluster_host: Base URL of the cluster (should include http:// or https://)

    Returns:
        External URL

    Raises:
        ValidationException: If cluster host not configured, no rules, or no PathPrefix found
    """

    if not cluster_host:
        raise ValidationException("Cluster host is not set - external URLs not available")

    if not httproute.spec.rules:
        raise ValidationException("HTTPRoute has no rules")

    # Find first PathPrefix match
    path_match = next(
        (
            match.path.value
            for rule in httproute.spec.rules
            for match in rule.matches
            if match.path and match.path.type == "PathPrefix" and match.path.value
        ),
        None,
    )
    if not path_match:
        raise ValidationException("No PathPrefix match found in HTTPRoute")

    base_url = cluster_host if cluster_host.startswith(("http://", "https://")) else f"https://{cluster_host}"
    return urljoin(base_url, path_match)


def extract_endpoints(
    aim_service: AIMServiceResource,
    httproute: HTTPRouteResource | None = None,
    cluster_host: str = CLUSTER_HOST,
    inference_service_name: str | None = None,
) -> dict[str, str]:
    """
    Extract internal and external endpoints for an AIMService.

    When an HTTPRoute is present, the internal URL uses its backend ref (which
    may include a custom port) and the external URL is derived from its path
    prefix. Otherwise, the internal URL is derived from the KServe predictor
    service name ({isvc-name}-predictor.{namespace}.svc.cluster.local).

    Args:
        aim_service: The AIMService CRD resource
        httproute: HTTPRoute resource from Kubernetes API (optional)
        cluster_host: Base URL of the cluster (should include http:// or https://)
        inference_service_name: Name of the KServe InferenceService owned by this
            AIMService (fetched via ownerReferences). Used to derive the predictor
            service URL when HTTPRoute is not available.

    Returns:
        Dictionary with "internal" and optionally "external" URLs
    """
    namespace = aim_service.metadata.namespace or ""
    name = aim_service.metadata.name

    endpoints: dict[str, str] = {}

    if httproute:
        try:
            endpoints["internal"] = get_aim_service_internal_url(httproute, namespace)
        except Exception as e:
            logger.warning(f"Could not determine internal URL from HTTPRoute for {name}: {e}")

        try:
            endpoints["external"] = get_aim_service_external_url(httproute, cluster_host)
        except Exception as e:
            logger.warning(f"Could not determine external URL for {name}: {e}")

    if "internal" not in endpoints and inference_service_name:
        endpoints["internal"] = f"http://{inference_service_name}-predictor.{namespace}.svc.cluster.local"

    if "internal" not in endpoints:
        logger.warning(
            f"Could not determine internal URL for AIMService {name}: no HTTPRoute or InferenceService found"
        )

    return endpoints


def _build_aim_service_profile(
    deploy_request: "AIMDeployRequest",
    pinned_model_id: str | None = None,
    pinned_aim_id: str | None = None,
) -> dict[str, Any]:
    """Build spec.profile (direct name or selector) from deploy-time criteria.

    Always injects minimumType=any so aim-engine considers all profile tiers
    (optimized, preview, unoptimized) rather than enforcing the default optimized
    floor. Without this, deployments on clusters that only have unoptimized or
    preview profiles fail with ProfileNotFound even when matching candidates exist.

    ``pinned_model_id`` is the weights the requested adapters were built for. aim-engine resolves a
    selector after the CR is written, and an unconstrained one can land on a sibling variant of the
    same model — another quantisation, say — that those adapters cannot load. The request is
    accepted and the failure arrives minutes later as a service that never starts. Naming the
    weights leaves the engine no such profile to choose.

    ``pinned_aim_id`` travels with it rather than standing in for it: the engine's candidate listing
    is indexed on the group identity and falls back to listing every profile in scope without it.
    Both are needed for the narrowing to be free, so a weights identity with no group identity
    beside it pins nothing -- the caller-supplied criteria are left exactly as they are today.
    """
    if deploy_request.profile_name:
        return {"name": deploy_request.profile_name}

    selector: dict[str, Any] = {"minimumType": "any", **deploy_selector_criteria(deploy_request)}
    if pinned_model_id and pinned_aim_id:
        selector["modelId"] = pinned_model_id
        selector["aimId"] = pinned_aim_id
    return {"selector": selector}


def env_entries_to_map(entries: list[dict[str, Any]]) -> dict[str, str]:
    """Convert K8s-style env var entries to the engineEnv map shape."""
    result: dict[str, str] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValidationException(f"engineEnv[{index}] must be an object with name and value")
        if "name" not in entry:
            raise ValidationException(f"engineEnv[{index}] is missing required field 'name'")
        if "value" not in entry:
            raise ValidationException(f"engineEnv[{index}] is missing required field 'value'")

        name = entry["name"]
        value = entry["value"]
        if not isinstance(name, str) or not name:
            raise ValidationException(f"engineEnv[{index}].name must be a non-empty string")
        if value is None:
            raise ValidationException(f"engineEnv[{index}].value must be a string")
        if not isinstance(value, str):
            raise ValidationException(f"engineEnv[{index}].value must be a string")
        if name in result:
            raise ValidationException(f"engineEnv[{index}].name duplicates earlier entry '{name}'")

        result[name] = value
    return result


def _build_aim_service_profile_overrides(deploy_request: "AIMDeployRequest") -> dict[str, Any]:
    """Build spec.profileOverrides patches applied on top of the resolved profile."""
    overrides: dict[str, Any] = {}
    if deploy_request.gpu_count is not None:
        overrides["acceleratorCount"] = deploy_request.gpu_count
    if deploy_request.engine_args:
        overrides["engineArgs"] = deploy_request.engine_args
    if deploy_request.engine_env:
        overrides["engineEnv"] = env_entries_to_map(deploy_request.engine_env)
    if deploy_request.container_env:
        overrides["containerEnv"] = deploy_request.container_env
    return overrides


def _apply_deploy_profile_fields(
    spec_dict: dict[str, Any],
    deploy_request: "AIMDeployRequest",
    pinned_model_id: str | None = None,
    pinned_aim_id: str | None = None,
) -> None:
    """Populate spec.profile and spec.profileOverrides from the deploy request."""
    spec_dict["profile"] = _build_aim_service_profile(deploy_request, pinned_model_id, pinned_aim_id)
    profile_overrides = _build_aim_service_profile_overrides(deploy_request)
    if profile_overrides:
        spec_dict["profile_overrides"] = profile_overrides


def _apply_deploy_adapter_fields(spec_dict: dict[str, Any], deploy_request: "AIMDeployRequest") -> None:
    """Populate the adapter fields from the deploy request.

    An empty adapters list is treated as no request at all, exactly like omitting the field. Writing
    `spec.adapters: []` would not be the neutral record it looks like: under the default `static`
    mode aim-engine mounts the adapter disk for any service that declares adapters, so persisting an
    empty declaration hands the caller a mount they never asked for.

    adapterMode is likewise left unwritten unless chosen, because it is immutable once set — leaving
    it out keeps the CRD default in force rather than permanently pinning the service to a mode the
    user never picked.

    adapterRuntime is a sibling of profileOverrides, so the rank ceiling is written independently
    of engine and container overrides on the profile.
    """
    if deploy_request.adapters:
        spec_dict["adapters"] = [{"kind": "AIMArtifact", "name": name} for name in deploy_request.adapters]
    if deploy_request.adapter_mode is not None:
        spec_dict["adapter_mode"] = deploy_request.adapter_mode
    if deploy_request.max_lora_rank is not None:
        spec_dict["adapter_runtime"] = {"max_rank": deploy_request.max_lora_rank}


def generate_fine_tuned_aim_service_manifest(
    model_name: str,
    deploy_request: "AIMDeployRequest",
    namespace: str,
    service_name: str,
    api_version: str,
    submitter: str,
    display_name: str,
    canonical_name: str,
) -> dict:
    """Backward-compatible wrapper for fine-tuned namespace deployments."""
    return generate_namespace_aim_service_manifest(
        model_name=model_name,
        deploy_request=deploy_request,
        namespace=namespace,
        service_name=service_name,
        api_version=api_version,
        submitter=submitter,
        display_name=display_name,
        canonical_name=canonical_name,
        is_fine_tuned=True,
    )


def generate_namespace_aim_service_manifest(
    model_name: str,
    deploy_request: "AIMDeployRequest",
    namespace: str,
    service_name: str,
    api_version: str,
    submitter: str,
    display_name: str,
    canonical_name: str,
    is_fine_tuned: bool = True,
    resolved_profile_name: str | None = None,
    deploy_display_name: str | None = None,
    pinned_model_id: str | None = None,
    pinned_aim_id: str | None = None,
) -> dict:
    """Generate AIMService manifest for a namespace AIMModel deployment.

    Sibling of generate_aim_service_manifest; takes a namespace-scoped AIMModel
    name (`model_name`) instead of an AIMModelResource. Stamps
    NAMESPACE_AIM_MODEL_LABEL so chattable detection skips the cluster-catalog
    lookup. For backward compatibility, fine-tuned deployments also keep
    FINE_TUNED_LABEL.

    ``display_name`` is the onboarded model's identity (kept on MODEL_NAME_LABEL).
    ``deploy_display_name`` is the optional user-entered deploy name; when present
    it wins for the user-visible DISPLAY_NAME_ANNOTATION, otherwise it falls back
    to the model identity.

    ``pinned_model_id``/``pinned_aim_id`` narrow selector resolution to the weights the requested
    adapters were built for; the caller resolves them, as this builds no state of its own.
    """
    routing_config: dict[str, Any] = {
        "enabled": True,
        "gatewayRef": {
            "name": AIM_GATEWAY_NAME,
            "namespace": AIM_GATEWAY_NAMESPACE,
        },
    }

    spec_dict: dict[str, Any] = {
        "model": {"name": model_name},
        "replicas": deploy_request.replicas,
        "runtime_config_name": AIM_CLUSTER_RUNTIME_CONFIG_NAME,
        "caching": {"mode": "Shared"},
        "routing": routing_config,
    }

    # When a ready namespace AIMProfile exists (custom onboarding or fine-tuned
    # emission), pin it by name so aim-engine uses model/profile settings instead
    # of selector resolution. Deploy-time selectors and profileOverrides on the
    # request are ignored in that case. Without a pinned profile, the deploy
    # request may supply selectors/overrides or omit spec.profile for auto-resolve.
    if resolved_profile_name:
        spec_dict["profile"] = {"name": resolved_profile_name}
    else:
        _apply_deploy_profile_fields(spec_dict, deploy_request, pinned_model_id, pinned_aim_id)

    _apply_deploy_adapter_fields(spec_dict, deploy_request)

    if deploy_request.min_replicas is not None:
        spec_dict["min_replicas"] = deploy_request.min_replicas
        spec_dict["max_replicas"] = deploy_request.max_replicas
        spec_dict["auto_scaling"] = deploy_request.auto_scaling

    # A whitespace-only deploy name is not a real name; fall back to model identity.
    effective_display_name = (deploy_display_name or "").strip() or display_name

    resource = AIMServiceResource(
        metadata=K8sMetadata(
            name=service_name,
            namespace=namespace,
            annotations={
                SUBMITTER_ANNOTATION: submitter,
                # TODO: drop once aim-engine removes v1alpha1 and the
                # profile pipeline becomes the default dispatch.
                RECONCILER_PIPELINE_ANNOTATION: RECONCILER_PIPELINE_PROFILE,
                CANONICAL_NAME_LABEL: canonical_name,
                MODEL_NAME_LABEL: display_name,
                **({DISPLAY_NAME_ANNOTATION: effective_display_name} if effective_display_name else {}),
            },
            labels={
                f"{EAI_APPS_METADATA_PREFIX}/workload-type": WorkloadType.INFERENCE,
                # Marks this service as deployed from a namespace AIMModel so
                # chattable detection does not require an AIMClusterModel catalog lookup.
                NAMESPACE_AIM_MODEL_LABEL: "true",
                **({FINE_TUNED_LABEL: "true"} if is_fine_tuned else {}),
            },
        ),
        spec=AIMServiceSpec.model_validate(spec_dict),
    )

    manifest = resource.model_dump(
        by_alias=True,
        exclude_none=True,
        exclude={"status", "httproute", "inference_service_name", "id"},
    )
    manifest["apiVersion"] = api_version
    manifest["kind"] = "AIMService"
    return manifest


def generate_aim_service_manifest(
    aim: AIMModelResource,
    deploy_request: "AIMDeployRequest",
    namespace: str,
    service_name: str,
    api_version: str,
    submitter: str,
    display_name: str | None = None,
    pinned_model_id: str | None = None,
    pinned_aim_id: str | None = None,
) -> dict:
    """Generate AIMService CRD manifest for deploying an AIM using Pydantic models.

    ``pinned_model_id``/``pinned_aim_id`` narrow selector resolution to the weights the requested
    adapters were built for; the caller resolves them, as this builds no state of its own.

    Args:
        aim: AIMClusterModel resource
        deploy_request: The deployment request with model identifier
        namespace: Target namespace
        service_name: The K8s resource name for the AIMService
        api_version: K8s API version
        submitter: User submitting the service
        display_name: Optional user-visible display name stored as annotation
    """
    # Build spec using dict for complex fields that aren't fully modeled
    routing_config: dict[str, Any] = {
        "enabled": True,
        "gatewayRef": {
            "name": AIM_GATEWAY_NAME,
            "namespace": AIM_GATEWAY_NAMESPACE,
        },
    }

    spec_dict: dict[str, Any] = {
        "model": {"name": aim.metadata.name},
        "replicas": deploy_request.replicas,
        "runtime_config_name": AIM_CLUSTER_RUNTIME_CONFIG_NAME,
        "caching": {"mode": "Shared"},
        "routing": routing_config,
    }

    _apply_deploy_profile_fields(spec_dict, deploy_request, pinned_model_id, pinned_aim_id)
    _apply_deploy_adapter_fields(spec_dict, deploy_request)

    # Add scaling policy if provided (validation handled by pydantic schema)
    if deploy_request.min_replicas is not None:
        spec_dict["min_replicas"] = deploy_request.min_replicas
        spec_dict["max_replicas"] = deploy_request.max_replicas
        spec_dict["auto_scaling"] = deploy_request.auto_scaling

    if deploy_request.image_pull_secrets:
        spec_dict["imagePullSecrets"] = [{"name": secret_name} for secret_name in deploy_request.image_pull_secrets]

    if deploy_request.hf_token:
        spec_dict["caching"]["env"] = [
            {
                "name": "HF_TOKEN",
                "valueFrom": {"secretKeyRef": {"name": deploy_request.hf_token, "key": "token"}},
            }
        ]

    resource = AIMServiceResource(
        metadata=K8sMetadata(
            name=service_name,
            namespace=namespace,
            annotations={
                SUBMITTER_ANNOTATION: submitter,
                # TODO: drop once aim-engine removes v1alpha1 and the
                # profile pipeline becomes the default dispatch.
                RECONCILER_PIPELINE_ANNOTATION: RECONCILER_PIPELINE_PROFILE,
                **({DISPLAY_NAME_ANNOTATION: display_name} if display_name else {}),
            },
            labels={
                f"{EAI_APPS_METADATA_PREFIX}/workload-type": WorkloadType.INFERENCE,
            },
        ),
        spec=AIMServiceSpec.model_validate(spec_dict),
    )

    # Convert to dict with camelCase for K8s API
    # Exclude status and computed fields (e.g., id) which aren't part of the CRD
    manifest = resource.model_dump(
        by_alias=True,
        exclude_none=True,
        exclude={"status", "httproute", "inference_service_name", "id"},
    )
    manifest["apiVersion"] = api_version
    manifest["kind"] = "AIMService"

    return manifest
