# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Service layer for AIMs - handles business logic for AIM deployment and management."""

import asyncio
import json
from typing import Any, NamedTuple
from uuid import UUID

from kubernetes_asyncio.client import ApiException
from loguru import logger

from api_common.exceptions import (
    ConflictException,
    ExternalServiceError,
    InconsistentStateException,
    NotFoundException,
    ValidationException,
)

from ..artifacts.readiness import gather_readiness, split_s3_uri
from ..artifacts.schemas import ReadinessState
from ..artifacts.service import MANAGED_BY_LABEL, PLATFORM_MANAGED_BY_VALUES, is_platform_managed
from ..custom_models.constants import (
    DEFAULT_PROFILE_ALIAS,
    IMPORT_ERROR_ANNOTATION,
    IMPORT_STATE_ANNOTATION,
    MODEL_PRECISION_ANNOTATION,
)
from ..custom_models.enums import OnboardPhase
from ..custom_models.gateway import find_aim_profile_for_model

# Aliased: this module already defines a `list_aim_profiles` (aimId-filtered);
# the custom-models gateway variant filters by the model.name label, which is
# the reliable key for a custom model's derived profiles.
from ..custom_models.gateway import list_aim_profiles as list_custom_model_profiles
from ..dispatch.kube_client import KubernetesClient
from ..inference.enums import InferenceCapability
from ..minio import MinioClient
from ..secrets.service import get_secret_details
from ..workloads.constants import DISPLAY_NAME_ANNOTATION, MODEL_NAME_LABEL, MODEL_SOURCE_TYPE_LABEL
from ..workloads.enums import ModelSourceType
from .constants import ADAPTER_PROFILE_FEATURE, AIM_MODEL_LABEL
from .crds import (
    AIMArtifactResource,
    AIMModelResource,
    AIMProfileResource,
    AIMProfileSetResource,
    AIMServiceResource,
)
from .enums import AcceleratorType, AdapterMode, AIMModelStatus, AIMServiceStatus
from .gateway import create_aim_service as create_aim_service_in_k8s
from .gateway import create_namespace_aim_service as create_namespace_aim_service_in_k8s
from .gateway import delete_aim_service as delete_aim_service_from_k8s
from .gateway import (
    get_aim_artifact,
    get_aim_by_name,
    get_aim_cluster_model_strict,
    get_aim_profile_any_scope,
    list_aim_profile_sets_for_model,
    resolve_recorded_profile,
)
from .gateway import get_aim_cluster_profile_by_name as get_aim_cluster_profile_from_k8s
from .gateway import get_aim_model as get_aim_model_from_k8s
from .gateway import get_aim_profile_by_name as get_aim_profile_from_k8s
from .gateway import get_aim_service_by_id as get_aim_service_from_k8s
from .gateway import list_aim_cluster_profiles_by_aim_ids as get_aim_cluster_profiles_from_k8s
from .gateway import list_aim_profiles_by_aim_ids as get_aim_profiles_from_k8s
from .gateway import list_aim_services as get_aim_services_from_k8s
from .gateway import list_aims as get_aims_from_k8s
from .gateway import patch_aim_service_spec as patch_aim_service_spec_in_k8s
from .schemas import (
    AIMDeployRequest,
    AIMResponse,
    AIMServiceResponse,
)
from .utils import (
    ServedWeights,
    adapter_serves,
    agreed_adapter_weights,
    classify_default_profile_set,
    deploy_selector_criteria,
    effective_profile_for_set,
    generate_aim_service_name,
    profiles_derived_from_set,
    profiles_eligible_for_deploy,
    profiles_without_owning_set,
)

# AIMDeployRequest fields no namespace AIMModel deployment accepts: both are only
# honored for cluster-scoped AIMClusterModel deployments. Namespace models
# materialize weights into object storage ahead of time and drive profile
# resolution through the AIMModel CR, so neither caller-supplied images nor HF
# credentials are needed at deploy time. Selector criteria and profileOverrides may
# still be sent on the request but are ignored when a ready namespace AIMProfile is
# pinned onto the manifest.
_NAMESPACE_MODEL_DISALLOWED_FIELDS = (
    "image_pull_secrets",
    "hf_token",
)


def _is_base_only_cluster_model(aim: AIMResponse) -> bool:
    """Return True when an AIMClusterModel is base-only."""
    managed_profiles = aim.status.managed_profiles
    if isinstance(managed_profiles, dict):
        base_count = managed_profiles.get("base")
        if isinstance(base_count, int) and base_count > 0:
            aggregate_keys = {"base", "ready", "total", "notAvailable", "not_available"}
            is_base_only = True
            for profile_type, count in managed_profiles.items():
                if profile_type in aggregate_keys:
                    continue
                if isinstance(count, int) and count > 0:
                    is_base_only = False
                    break
            if is_base_only:
                return True

    # Unsupported base images can still surface as AIMClusterModels with no
    # resolved AIM identifier. Treat "Base" catalog titles without aimId/canonical
    # metadata as base-image entries and exclude them from inference catalog.
    model_metadata = aim.status.image_metadata.model
    title = (model_metadata.title or "").strip().lower()
    if "base" not in title:
        return False
    return aim.status.aim_id is None and model_metadata.canonical_name is None


def _wire_field_names(*field_names: str) -> str:
    """Deploy request fields under the names clients send them by, for an error message."""
    return ", ".join(AIMDeployRequest.model_fields[name].alias or name for name in field_names)


async def list_aims(
    kube_client: KubernetesClient,
    statuses: list[AIMModelStatus] | None = None,
    accelerator_type: list[AcceleratorType] | None = None,
) -> list[AIMResponse]:
    """List all AIMs from Kubernetes.

    When ``accelerator_type`` is set, an AIM matches when any entry of its
    ``status.discoveredProfiles.byHardware[]`` has an accelerator family in
    the requested set. AIMs whose engine has not yet published a hardware
    breakdown (``discoveredProfiles`` is ``None`` or has an empty
    ``byHardware``) are excluded when the filter is set — consistent with
    the prior single-value behavior of dropping AIMs without accelerator
    metadata. The engine's ``accelerator_type`` is a raw string; the filter
    matches by comparing against the enum's ``.value``.
    """
    aims_crds = await get_aims_from_k8s(kube_client, statuses)
    aims = [AIMResponse.model_validate(crd.model_dump()) for crd in aims_crds]
    aims = [aim for aim in aims if not _is_base_only_cluster_model(aim)]
    if accelerator_type:
        requested = {at.value for at in accelerator_type}
        aims = [
            aim
            for aim in aims
            if aim.status.discovered_profiles is not None
            and any(h.accelerator_type in requested for h in aim.status.discovered_profiles.by_hardware)
        ]
    return aims


async def get_aim_by_resource_name(
    kube_client: KubernetesClient,
    resource_name: str,
) -> AIMResponse:
    """Get a specific AIM from Kubernetes by resource name.

    Args:
        kube_client: Kubernetes client
        resource_name: The Kubernetes resource name of the AIMClusterModel

    Returns:
        AIMResponse containing the AIMClusterModel data

    Raises:
        NotFoundException: If AIMClusterModel not found
    """
    aim_crd = await get_aim_by_name(kube_client, resource_name)
    if not aim_crd:
        raise NotFoundException(f"AIM with resource name '{resource_name}' not found")

    return AIMResponse.model_validate(aim_crd.model_dump())


async def deploy_aim(
    kube_client: KubernetesClient,
    deploy_request: AIMDeployRequest,
    namespace: str,
    submitter: str,
    minio_client: MinioClient | None = None,
) -> AIMServiceResponse:
    """Deploy an AIM by creating an AIMService CRD in Kubernetes.

    Auto-detects the model type: tries AIMClusterModel (cluster-scoped) first,
    then falls back to AIMModel (namespace-scoped fine-tuned model).

    ``minio_client`` is only used to check that a requested adapter's weights have
    finished uploading; without it that one check is skipped and the deploy proceeds.
    """
    aim_service_name = generate_aim_service_name()

    # Try cluster-scoped AIMClusterModel first
    aim_cluster_model = await get_aim_by_name(kube_client, deploy_request.model)
    if aim_cluster_model:
        if aim_cluster_model.status.image_metadata.model.hf_token_required:
            if not deploy_request.hf_token:
                raise ValidationException("This model requires a Hugging Face token but none was provided")
            await get_secret_details(kube_client, namespace, deploy_request.hf_token)

        pinned_model_id = await _validate_deploy_adapters(
            kube_client=kube_client,
            minio_client=minio_client,
            namespace=namespace,
            deploy_request=deploy_request,
            base_model=aim_cluster_model,
        )

        created = await create_aim_service_in_k8s(
            kube_client=kube_client,
            namespace=namespace,
            aim=aim_cluster_model,
            deploy_request=deploy_request,
            submitter=submitter,
            service_name=aim_service_name,
            display_name=deploy_request.display_name,
            pinned_model_id=pinned_model_id,
            pinned_aim_id=aim_cluster_model.status.aim_id,
        )
        logger.info(f"Created AIMService {aim_service_name} in namespace {namespace}")
        return AIMServiceResponse.model_validate(created, from_attributes=True)

    # Fall back to namespace-scoped AIMModel (fine-tuned/custom-onboarded)
    aim_model = await get_aim_model_from_k8s(kube_client, namespace, deploy_request.model)
    if aim_model:
        is_custom_model = _is_custom_onboarded_model(aim_model)
        supplied = [name for name in _NAMESPACE_MODEL_DISALLOWED_FIELDS if getattr(deploy_request, name) is not None]
        if supplied:
            raise ValidationException(
                f"Namespace model deployments do not accept {_wire_field_names(*supplied)}; "
                "remove and retry. Weights and images are resolved from the model itself."
            )
        if not is_custom_model and deploy_request.profile_name is not None:
            raise ValidationException(
                f"Model '{deploy_request.model}' has no selectable profiles, so "
                f"{_wire_field_names('profile_name')} is not accepted; remove it and retry. "
                "aim-engine derives the profile for a fine-tuned model."
            )

        resolved_profile = await _resolve_namespace_deploy_profile(
            kube_client=kube_client,
            namespace=namespace,
            model_name=deploy_request.model,
            aim_model=aim_model,
            is_custom_model=is_custom_model,
            profile_selection=deploy_request.profile_name,
        )
        resolved_profile_name = resolved_profile.metadata.name if resolved_profile else None

        pinned_model_id = await _validate_deploy_adapters(
            kube_client=kube_client,
            minio_client=minio_client,
            namespace=namespace,
            deploy_request=deploy_request,
            base_model=aim_model,
            pinned_profile=resolved_profile,
        )

        created = await create_namespace_aim_service_in_k8s(
            kube_client=kube_client,
            namespace=namespace,
            model_name=deploy_request.model,
            deploy_request=deploy_request,
            submitter=submitter,
            service_name=aim_service_name,
            display_name=_extract_namespace_model_display_name(aim_model),
            canonical_name=_extract_namespace_model_canonical_name(aim_model),
            is_fine_tuned=not is_custom_model,
            resolved_profile_name=resolved_profile_name,
            deploy_display_name=deploy_request.display_name,
            pinned_model_id=pinned_model_id,
            pinned_aim_id=aim_model.status.aim_id,
        )
        logger.info(
            f"Created AIMService {aim_service_name} for namespace model {deploy_request.model} in namespace {namespace}"
        )
        return AIMServiceResponse.model_validate(created, from_attributes=True)

    raise NotFoundException(
        f"Model '{deploy_request.model}' not found as AIMClusterModel or AIMModel in namespace '{namespace}'"
    )


async def undeploy_aim(
    kube_client: KubernetesClient,
    id: UUID,
    namespace: str,
) -> None:
    """Undeploy an AIM by deleting its AIMService CRD from Kubernetes using service id.

    Args:
        kube_client: Kubernetes client
        id: AIM service ID
        namespace: Target namespace
    """
    try:
        service = await get_aim_service_from_k8s(kube_client, namespace, id)
        if not service:
            raise NotFoundException(f"AIM service {id} not found in Kubernetes (may be deleted)")

        service_name = await delete_aim_service_from_k8s(kube_client, namespace, id)
        logger.info(f"Deleted AIMService {service_name} (id: {id}) from namespace {namespace}")
    except ValueError as e:
        raise NotFoundException(str(e))


async def list_aim_services(
    kube_client: KubernetesClient,
    namespace: str,
    status_filter: list[AIMServiceStatus] | None = None,
) -> list[AIMServiceResponse]:
    """List all AIMServices from Kubernetes.

    Returns the raw service status. Consumers that need the resolved
    AIMProfile/AIMClusterProfile spec must fetch the profile catalog from
    the profile endpoints and join client-side by ``status.resolvedProfile.name``.
    """
    services_crds = await get_aim_services_from_k8s(kube_client, namespace, status_filter=status_filter)
    return [AIMServiceResponse.model_validate(crd, from_attributes=True) for crd in services_crds]


async def get_aim_service(
    kube_client: KubernetesClient,
    namespace: str,
    id: UUID,
) -> AIMServiceResponse:
    """Get a single AIMService by ID."""
    service = await get_aim_service_from_k8s(kube_client, namespace, id)
    if not service:
        raise NotFoundException(f"AIM service {id} not found in Kubernetes (may be deleted)")
    return AIMServiceResponse.model_validate(service, from_attributes=True)


async def list_aim_services_by_capability(
    kube_client: KubernetesClient,
    namespace: str,
    capability: InferenceCapability,
) -> list[AIMServiceResponse]:
    """List all ready AIM services whose model exposes the given capability."""
    services_crds = await get_aim_services_from_k8s(kube_client, namespace, capability=capability)
    return [AIMServiceResponse.model_validate(crd, from_attributes=True) for crd in services_crds]


async def list_chattable_aim_services(
    kube_client: KubernetesClient,
    namespace: str,
) -> list[AIMServiceResponse]:
    """List all AIM services with ready conditions that support chat."""
    return await list_aim_services_by_capability(kube_client, namespace, InferenceCapability.CHAT)


async def list_transcribable_aim_services(
    kube_client: KubernetesClient,
    namespace: str,
) -> list[AIMServiceResponse]:
    """List all AIM services with ready conditions that support transcription."""
    return await list_aim_services_by_capability(kube_client, namespace, InferenceCapability.TRANSCRIPTION)


async def list_aim_cluster_profiles(
    kube_client: KubernetesClient,
    aim_ids: list[str] | None = None,
) -> list[AIMProfileResource]:
    """List AIMClusterProfile resources, optionally filtered by ``spec.aimId``.

    Returns an empty list when no profiles match. Callers that need to
    distinguish "no profiles" from "model unknown" should do so via the
    model endpoints — this listing does not validate the existence of any
    AIMClusterModel.
    """
    return await get_aim_cluster_profiles_from_k8s(kube_client, aim_ids=aim_ids)


async def get_aim_cluster_profile(
    kube_client: KubernetesClient,
    name: str,
) -> AIMProfileResource:
    """Fetch a single AIMClusterProfile by resource name.

    Used by callers that already know the exact profile name (e.g. from
    ``AIMService.status.resolvedProfile.name``) and want a targeted lookup
    instead of the aimId-keyed batched list.

    Raises:
        NotFoundException: When no AIMClusterProfile with that name exists.
    """
    profile = await get_aim_cluster_profile_from_k8s(kube_client, name)
    if profile is None:
        raise NotFoundException(f"AIMClusterProfile '{name}' not found")
    return profile


def _k8s_rejection_detail(exc: ApiException) -> str:
    """The API server's own message, which is where a CEL rule states why it refused the write."""
    try:
        parsed = json.loads(exc.body or "{}")
    except (TypeError, ValueError):
        parsed = None
    message = parsed.get("message") if isinstance(parsed, dict) else None
    return str(message or exc.reason)


class ScalingPolicy(NamedTuple):
    """The scaling trio as one value, because the CRD only accepts it as one."""

    min_replicas: int
    max_replicas: int
    auto_scaling: dict[str, Any]


async def update_aim_service_spec(
    kube_client: KubernetesClient,
    namespace: str,
    id: UUID,
    adapters: list[str] | None = None,
    scaling: ScalingPolicy | None = None,
    minio_client: MinioClient | None = None,
) -> AIMServiceResponse:
    """Change the adapters a running deployment serves, its scaling policy, or both.

    ``None`` means "leave this alone"; every supplied field travels in one merge patch, which the
    API server applies whole or not at all — so there is no order to choose between the changes and
    no half-applied outcome.

    ``adapters`` is otherwise the complete desired set. An empty list detaches everything, and
    clears ``spec.adapters`` rather than writing ``[]``: the CRD reads an explicit empty array as a
    claim on the field, while an absent one is what a deployment that never carried adapters looks
    like. The adapterMode gate and the per-adapter checks apply only when adapters are supplied —
    scaling a deployment that was never opted into dynamic adapters stays allowed.

    ``minio_client`` is only used to check that a requested adapter's weights have finished
    uploading; without it that one check is skipped and the change proceeds.
    """
    if adapters is None and scaling is None:
        raise ValidationException("Nothing to update: supply adapters, a scaling policy, or both.")

    service = await get_aim_service_from_k8s(kube_client, namespace, id)
    if service is None:
        raise NotFoundException(f"AIM service {id} not found in namespace '{namespace}'")

    spec_patch: dict[str, Any] = {}

    if adapters is not None:
        if service.spec.adapter_mode is not AdapterMode.DYNAMIC:
            raise ValidationException(
                "This deployment does not admit adapter changes: its adapterMode is "
                f"'{service.spec.adapter_mode or AdapterMode.STATIC}', which is fixed at deploy time. "
                "Redeploy the model with adapterMode 'dynamic' to change adapters while it runs."
            )

        if adapters:
            base_model = await _resolve_service_base_model(kube_client, namespace, service)
            profile = await _running_service_profile(kube_client, namespace, service)
            # Only the failures matter here: the profile a running deployment serves is already
            # fixed, so there is no selector left for the adapters' weights to narrow.
            failures = (
                await _adapter_attachment_failures(
                    kube_client=kube_client,
                    minio_client=minio_client,
                    namespace=namespace,
                    adapter_names=adapters,
                    model_ref_name=service.spec.model.name or "",
                    base_model=base_model,
                    expected_model_id=profile.spec.model_id if profile else None,
                )
            ).failures
            # Asked here as well as at deploy time, unlike the narrowing constraints a running
            # deployment is entitled to revisit: a runtime that cannot host adapters at all can
            # serve none of them, so there is no legitimate change being refused. Leaving it
            # unasked let a PATCH attach an adapter that the artifacts listing — reading this same
            # profile — had already reported as not servable.
            if (capability_failure := _adapter_capability_failure(profile)) is not None:
                failures.append(capability_failure)
            if failures:
                raise ValidationException("Cannot attach the requested adapters: " + "; ".join(failures))

        refs = [{"kind": "AIMArtifact", "name": name} for name in adapters]
        spec_patch["adapters"] = refs or None

    if scaling is not None:
        # ``replicas`` is deliberately left as-is; KEDA decides which of the two takes priority.
        spec_patch |= {
            "minReplicas": scaling.min_replicas,
            "maxReplicas": scaling.max_replicas,
            "autoScaling": scaling.auto_scaling,
        }

    try:
        patched = await patch_aim_service_spec_in_k8s(kube_client, namespace, service.metadata.name, spec_patch)
    except ApiException as e:
        detail = _k8s_rejection_detail(e)
        if e.status in (400, 422):
            raise ValidationException(f"Kubernetes rejected the change: {detail}")
        if e.status == 409:
            raise ConflictException(f"The deployment changed while the update was in flight: {detail}")
        raise ExternalServiceError(f"Failed to update AIM service '{id}': {detail}")
    except Exception as e:
        raise ExternalServiceError(f"Failed to update AIM service '{id}': {e}") from e

    logger.info(f"Updated AIMService {patched.metadata.name} in {namespace}, spec fields: {sorted(spec_patch)}")
    return AIMServiceResponse.model_validate(patched.model_dump())


def _adapter_capability_failure(profile: AIMProfileResource | None) -> str | None:
    """Why this profile's runtime cannot host adapters at all, or None when nothing says it cannot.

    One expression serves the deploy gate and the attach gate, because two spellings of the same
    field are how the two come to disagree about the same profile — which is exactly the state the
    ``servable`` flag is supposed to be able to promise against.

    An unresolved profile refuses nothing: nothing has been read that could say the runtime lacks
    the feature, and refusing on absent evidence would block attachments that work.
    """
    if profile is None or ADAPTER_PROFILE_FEATURE in profile.spec.features:
        return None
    return f"profile '{profile.metadata.name}' cannot serve adapters"


async def _running_service_profile(
    kube_client: KubernetesClient,
    namespace: str,
    service: AIMServiceResource,
) -> AIMProfileResource | None:
    """The profile a running deployment resolved, which is what decides the adapters it can load.

    aim-engine records the profile it picked in ``status.resolvedProfile``, and that profile is the
    only place both the running weights (``spec.modelId``) and the runtime's adapter capability are
    named. The whole profile is returned rather than just the weights so both questions are
    answered from one read: asked separately they are two reads that can land on different objects.
    This is deliberately the same read the artifacts listing performs to report ``servable``, so the
    flag a client is offered and the gate its change is judged by cannot answer from different
    profiles.

    None means the deployment has named no profile this code can read, which narrows nothing and
    refuses nothing: a profile not recorded yet and one that no longer resolves are
    indistinguishable here, and the check then rests on the model's group identity alone. A profile
    that could not be *read* is neither of those — it propagates, because widening the gate on an
    unreachable cluster would accept an attachment on the coarse identity that the precise one would
    have refused, and because the listing this shares its read with answers the same failure by
    failing too.
    """
    return await resolve_recorded_profile(kube_client, namespace, service.status.resolved_profile)


async def _resolve_service_base_model(
    kube_client: KubernetesClient,
    namespace: str,
    service: AIMServiceResource,
) -> AIMModelResource:
    """The model a running service serves, looked up cluster-scope first like a deploy does."""
    model_name = service.spec.model.name
    if model_name:
        # get_aim_by_name swallows every non-404 failure and returns None, which would collapse a
        # transient or forbidden cluster read into the same "model not found" path as a clean 404 —
        # so a cluster fault here must not fall through to the InconsistentStateException below.
        base_model = await get_aim_cluster_model_strict(kube_client, model_name)
        if base_model is None:
            try:
                base_model = await get_aim_model_from_k8s(kube_client, namespace, model_name)
            except ApiException as e:
                raise ExternalServiceError(f"Failed to look up AIM model '{model_name}': {e.reason}") from e
        if base_model is not None:
            return base_model
    raise InconsistentStateException(
        f"The model this deployment serves ('{model_name or 'unknown'}') is no longer available, so adapter "
        "compatibility cannot be checked"
    )


async def list_aim_profiles(
    kube_client: KubernetesClient,
    namespace: str,
    aim_ids: list[str] | None = None,
) -> list[AIMProfileResource]:
    """List namespace-scoped AIMProfile resources, optionally filtered by ``spec.aimId``.

    Returns an empty list when no profiles match. Like the cluster-scoped
    variant, this listing does not validate that any AIMModel CR exists in
    the namespace.
    """
    return await get_aim_profiles_from_k8s(kube_client, namespace, aim_ids=aim_ids)


async def get_aim_profile(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
) -> AIMProfileResource:
    """Fetch a single namespace-scoped AIMProfile by resource name.

    Targeted lookup variant of ``list_aim_profiles`` — used when the caller
    already knows the exact profile name (e.g. fine-tuned model detail page
    joining ``AIMService.status.resolvedProfile.name``).

    Raises:
        NotFoundException: When no AIMProfile with that name exists in the
            namespace.
    """
    profile = await get_aim_profile_from_k8s(kube_client, namespace, name)
    if profile is None:
        raise NotFoundException(f"AIMProfile '{name}' not found in namespace '{namespace}'")
    return profile


def _is_custom_onboarded_model(aim_model: Any) -> bool:
    labels = aim_model.metadata.labels or {}
    return labels.get(MODEL_SOURCE_TYPE_LABEL) == ModelSourceType.CUSTOM


def _extract_namespace_model_display_name(aim_model: Any) -> str:
    annotations = aim_model.metadata.annotations or {}
    labels = aim_model.metadata.labels or {}
    return annotations.get(DISPLAY_NAME_ANNOTATION) or labels.get(MODEL_NAME_LABEL, "")


def _extract_namespace_model_canonical_name(aim_model: Any) -> str:
    model_sources = aim_model.spec.model_sources or []
    if model_sources:
        return model_sources[0].model_id
    profiles = aim_model.spec.profiles
    overrides = profiles.overrides if profiles else None
    if overrides and overrides.model_id:
        return overrides.model_id
    if overrides and overrides.model_sources:
        return overrides.model_sources[0].model_id
    return ""


def _available_profile_identifiers(
    profile_sets: list[AIMProfileSetResource],
    default_set: AIMProfileSetResource | None,
) -> str:
    """Selectable profile identifiers for a rejection message, in the form clients send."""
    default_name = default_set.metadata.name if default_set else None
    identifiers = sorted(
        DEFAULT_PROFILE_ALIAS if s.metadata.name == default_name else s.metadata.name for s in profile_sets
    )
    return ", ".join(f"'{identifier}'" for identifier in identifiers) if identifiers else "none"


def _unresolved_profile_reason(
    model_name: str,
    model_profiles: list[AIMProfileResource],
    target: AIMProfileSetResource | None,
    default_set: AIMProfileSetResource | None,
) -> str:
    """Explain why a selection resolved to no AIMProfile, distinguishing the three causes.

    Profiles that exist but belong to other sets point at different troubleshooting
    than an engine that has emitted none, so one shared message misdirects readers.
    """
    if not model_profiles:
        return (
            "aim-engine has emitted no AIMProfile for this model. "
            f"Expected an AIMProfile labeled {AIM_MODEL_LABEL}={model_name}. "
            "If the AIMModel is Ready, check aim-engine reconciliation for that model."
        )
    if target is None:
        return (
            "its Default profile cannot be identified, because the model does not have exactly one "
            "engine-owned AIMProfileSet. Check aim-engine reconciliation for that model."
        )
    selected = DEFAULT_PROFILE_ALIAS if target is default_set else target.metadata.name
    return (
        f"profile '{selected}' has no AIMProfile derived from it yet. The model's other profiles "
        "cannot stand in for it; check aim-engine reconciliation for that profile."
    )


async def _resolve_custom_profile_selection(
    kube_client: KubernetesClient,
    namespace: str,
    model_name: str,
    aim_model: Any,
    selection: str | None,
) -> AIMProfileResource:
    """Resolve a profile selection on a custom model to the AIMProfile to pin.

    ``selection`` is an AIMProfileSet name or the literal ``default`` — the
    identifiers the profiles list returns — and ``None`` means no choice was made
    and takes the Default. Both reads are namespace-scoped and strict, so another
    project's set reads as an unknown selection, and a partial list raises rather
    than resolving to a profile the caller did not choose.
    """
    profile_sets, model_profiles = await asyncio.gather(
        list_aim_profile_sets_for_model(kube_client, namespace, model_name, strict=True),
        list_custom_model_profiles(kube_client, namespace, model_name=model_name, strict=True),
    )
    try:
        default_set: AIMProfileSetResource | None = classify_default_profile_set(profile_sets)
    except InconsistentStateException as e:
        logger.warning("Cannot identify the Default profile set for {} in {}: {}", model_name, namespace, e)
        default_set = None

    wants_default = selection is None or selection == DEFAULT_PROFILE_ALIAS
    if wants_default:
        target = default_set
    else:
        target = next((s for s in profile_sets if s.metadata.name == selection), None)
        if target is None:
            raise ValidationException(
                f"Profile '{selection}' does not exist on model '{model_name}' in project '{namespace}'. "
                f"Available profiles: {_available_profile_identifiers(profile_sets, default_set)}."
            )

    derived = profiles_derived_from_set(model_profiles, target.metadata.name) if target else []
    if not derived and wants_default:
        # No sets, or profiles predating being owned by one: fall back to the
        # profiles no set owns, which is what deploy read before sets existed.
        # Every profile would reach into an authored set the user never selected.
        derived = profiles_without_owning_set(model_profiles)

    preferred_precision = (aim_model.metadata.annotations or {}).get(MODEL_PRECISION_ANNOTATION)
    profile = effective_profile_for_set(derived, preferred_precision)
    if profile is None:
        raise ValidationException(
            f"Custom model '{model_name}' is not deployable yet: "
            f"{_unresolved_profile_reason(model_name, model_profiles, target, default_set)}"
        )
    return profile


async def _resolve_namespace_deploy_profile(
    kube_client: KubernetesClient,
    namespace: str,
    model_name: str,
    aim_model: Any,
    *,
    is_custom_model: bool,
    profile_selection: str | None = None,
) -> AIMProfileResource | None:
    """Resolve the namespace AIMProfile to pin on an AIMService manifest.

    Custom models require a Ready AIMModel and always pin a profile, resolved from
    ``profile_selection`` (an AIMProfileSet name or ``default``; ``None`` takes the
    Default), and a failed read raises because no other profile is a correct
    substitute. Other namespace models pin the profile aim-engine emitted when it
    is Ready and otherwise return ``None``, leaving the engine to resolve one;
    ``profile_selection`` never reaches them, as the caller rejects it first.
    """
    if not is_custom_model:
        try:
            profile = await find_aim_profile_for_model(kube_client, namespace, model_name)
        except ApiException:
            logger.warning(
                "Namespace AIMProfile lookup failed for model {} in {}; continuing without pinned profile",
                model_name,
                namespace,
            )
            return None
        if profile is not None and str(profile.status.status or "") == AIMModelStatus.READY:
            return profile
        return None

    annotations = aim_model.metadata.annotations or {}
    import_state = annotations.get(IMPORT_STATE_ANNOTATION)
    if import_state == OnboardPhase.FAILED:
        import_error = annotations.get(IMPORT_ERROR_ANNOTATION)
        reason = f": {import_error}" if import_error else "."
        raise ValidationException(
            f"Custom model '{model_name}' is not deployable: weight import failed{reason} Re-import the model before deploying."
        )
    if import_state and import_state not in (OnboardPhase.READY, OnboardPhase.FAILED):
        raise ValidationException(
            f"Custom model '{model_name}' is not deployable yet: weight import is still in progress."
        )

    model_status = str(aim_model.status.status) if (aim_model.status and aim_model.status.status) else ""
    if model_status != AIMModelStatus.READY:
        raise ValidationException(
            f"Custom model '{model_name}' is not deployable yet: AIMModel status is '{model_status or 'Unknown'}', expected 'Ready'."
        )
    profile = await _resolve_custom_profile_selection(kube_client, namespace, model_name, aim_model, profile_selection)
    profile_status = str(profile.status.status or "")
    if profile_status != AIMModelStatus.READY:
        raise ValidationException(
            f"Custom model '{model_name}' is not deployable yet: AIMProfile '{profile.metadata.name}' status is "
            f"'{profile_status or 'Unknown'}', expected 'Ready'."
        )
    return profile


async def _resolve_named_profile(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
) -> AIMProfileResource | None:
    """The profile a pinned ``spec.profile.name`` refers to: the project's own copy, else cluster-wide."""
    return await get_aim_profile_any_scope(kube_client, namespace, name)


async def _validate_deploy_adapters(
    kube_client: KubernetesClient,
    minio_client: MinioClient | None,
    namespace: str,
    deploy_request: AIMDeployRequest,
    base_model: AIMModelResource,
    pinned_profile: AIMProfileResource | None = None,
) -> str | None:
    """Refuse a deploy whose requested adapters cannot be attached to this model and profile.

    ``pinned_profile`` is for callers that already resolved the profile they will pin — the
    namespace path pins one it derives from the AIMModel rather than from the request. Callers
    without one leave it unset and the pinned ``profile_name`` on the request is resolved here.

    Returns the weights the accepted adapters agree on and this model publishes, for the caller to
    narrow selector resolution with, or None when that is not exactly one — see
    ``agreed_adapter_weights``.
    """
    names = deploy_request.adapters or []
    # A deploy that neither names adapters nor asks to change them later has nothing to check, and
    # returning here keeps the common case from resolving a profile it has no question about.
    if not names and deploy_request.adapter_mode is not AdapterMode.DYNAMIC:
        return None

    # Only a pinned profile can be checked: on the selector path aim-engine resolves the profile
    # after the CR is written, so a check here could pass on a profile it never picks. That path is
    # left to the engine's own ConfigValid rejection.
    profile = pinned_profile
    if profile is None and deploy_request.profile_name:
        profile = await _resolve_named_profile(kube_client, namespace, deploy_request.profile_name)

    # A deploy that pins a profile writes its name and no selector at all, so the request's criteria
    # constrain nothing and must not narrow what the model is read as publishing. The pin is not
    # always the caller's doing: the namespace path derives one from the AIMModel, and the manifest
    # ignores the criteria just the same, so judging against them could refuse a deploy over an
    # option the resulting service will never carry.
    pinned = profile is not None or deploy_request.profile_name is not None

    checks = await _adapter_attachment_failures(
        kube_client=kube_client,
        minio_client=minio_client,
        namespace=namespace,
        adapter_names=names,
        model_ref_name=deploy_request.model,
        base_model=base_model,
        expected_model_id=profile.spec.model_id if profile else None,
        selector_criteria=None if pinned else deploy_selector_criteria(deploy_request),
    )
    failures = checks.failures
    # Asked here rather than in the shared checks because it turns on the capability the request
    # asks for rather than on the adapters it happens to name: a deployment opened to adapter
    # changes needs the feature whether or not it starts with any, and adapterMode cannot be
    # relaxed afterwards.
    if (capability_failure := _adapter_capability_failure(profile)) is not None:
        failures.append(capability_failure)

    if failures:
        subject = "the requested adapters" if names else f"{_wire_field_names('adapter_mode')} '{AdapterMode.DYNAMIC}'"
        raise ValidationException(f"Cannot deploy with {subject}: " + "; ".join(failures))

    return checks.pinnable_model_id


class AdapterChecks(NamedTuple):
    """The verdict on a set of requested adapters: why they were refused, and what they pin.

    ``pinnable_model_id`` is only set when nothing was refused, so a caller cannot narrow a deploy
    on the strength of adapters it is about to reject.
    """

    failures: list[str]
    pinnable_model_id: str | None


async def _published_adapter_weights(
    kube_client: KubernetesClient,
    namespace: str,
    aim_id: str,
    model_name: str,
    criteria: dict[str, str],
) -> set[str]:
    """Every ``modelId`` this deploy's own candidate profiles offer as a home for adapters.

    Only the model can say which weights it publishes, and an adapter's ``compatibleWith`` is
    evidence about the adapter alone. Asking the model is what separates an adapter built for these
    weights from one built for another model's, which judging the adapters against an identity they
    supplied cannot do.

    The whole set is read rather than one membership question, because a declaration cannot be
    classified before this is known: the group id is also a profile's ``modelId`` on an unquantised
    base, and a declaration naming several variants only narrows against what is actually served.

    Ready profiles only, and only those whose runtime hosts adapters: a profile that failed to
    reconcile advertises weights the model cannot serve, and one lacking the adapter feature cannot
    host an adapter at all, so either would steer a deploy onto weights no adapter can land on.

    An empty set is not evidence of a mismatch. A model publishing no such profile has said nothing
    about what it serves, and the caller stays on the group identity rather than refusing; refusing
    on absent evidence would block deploys that work.

    Both scopes are read because the same model group is published cluster-wide and copied into
    projects, and either copy's profiles are weights this deploy can land on.

    The group is only how the profiles are fetched, never the boundary of the answer: the listing is
    keyed on ``aimId``, which every quantised variant and every version of the model shares, while
    this deploy can only resolve a candidate of the requested version that satisfies the criteria it
    carries. ``profiles_eligible_for_deploy`` applies that boundary, so the weights confirmed here
    are weights the selector this same request writes can actually reach — a pin drawn from the
    wider pool produced a conjunction of ``modelId`` and ``precision`` no profile satisfies, and the
    service never resolved.
    """
    cluster_profiles, namespace_profiles = await asyncio.gather(
        list_aim_cluster_profiles(kube_client, aim_ids=[aim_id]),
        list_aim_profiles(kube_client, namespace, aim_ids=[aim_id]),
    )
    candidates = profiles_eligible_for_deploy(
        (*cluster_profiles, *namespace_profiles), model_name=model_name, criteria=criteria
    )
    return {
        profile.spec.model_id
        for profile in candidates
        if profile.status.status == "Ready" and profile.spec.model_id and _adapter_capability_failure(profile) is None
    }


async def _adapter_attachment_failures(
    kube_client: KubernetesClient,
    minio_client: MinioClient | None,
    namespace: str,
    adapter_names: list[str],
    model_ref_name: str,
    base_model: AIMModelResource,
    expected_model_id: str | None = None,
    selector_criteria: dict[str, str] | None = None,
) -> AdapterChecks:
    """Every reason the named adapters cannot be attached to this model, in the order found.

    Failures are returned rather than raised so a caller can add its own before reporting them, and
    so every adapter is checked before anything is refused: a caller attaching several learns about
    all the problems at once instead of one per retry.

    ``expected_model_id`` is the weights the request already fixes, which only a known profile
    states. It is unset on the selector path, where aim-engine resolves the profile after the CR is
    written; there the weights stand in for it, drawn from what the adapters declare and what the
    model publishes together — see ``_published_adapter_weights``. That is what lets an adapter
    naming only a modelId be judged against a weights identity rather than against the group alone,
    without letting the adapters decide for themselves which weights they are judged against.

    ``selector_criteria`` are the profile-selector criteria that same request will write, which
    bound which of the model's profiles it could ever resolve. They are only meaningful on the
    selector path, so a caller with a resolved profile passes none.

    Storage readiness only ever refuses on a definite "the weights are not there". Unreachable or
    unconfigured storage leaves readiness unknown and the caller proceeds — the signal exists to
    tell users an upload is unfinished, and turning it into a gate would make attaching an adapter
    depend on object storage being up.
    """
    names = list(dict.fromkeys(adapter_names))
    if not names:
        return AdapterChecks(failures=[], pinnable_model_id=None)

    artifacts = await asyncio.gather(*(get_aim_artifact(kube_client, namespace, name) for name in names))

    # An adapter declares the base models it can serve as canonical model ids; the resolved value on
    # the model side is status.aimId, not the image metadata's canonicalName, which is null for
    # namespaced and imported models.
    base_aim_id = base_model.status.aim_id
    # Adapters with nothing to declare are left out so one unusable adapter does not blank the
    # identity the rest are judged against, which would misreport them as incompatible.
    declarations = [
        artifact.spec.compatible_with for artifact in artifacts if artifact and artifact.spec.compatible_with
    ]
    # Derived before the gate rather than after it, because on the selector path this identity both
    # admits the adapters and narrows the selector the deploy is written with. One value serves both
    # so the gate cannot admit one set of weights while the CR pins another.
    #
    # The declarations are resolved against what the model publishes rather than classified on their
    # own, because a ``compatibleWith`` entry carries no mark saying which identity it is: read in
    # isolation, a real weights id that happens to equal the group id looks like a family name, and
    # a multi-entry declaration looks like disagreement. Neither survives contact with the catalog.
    # The catalog is read as this deploy would resolve it — the requested model version, under the
    # criteria the request carries — because weights only a sibling version or another precision
    # publishes are weights this service can never run, and admitting an adapter on them pins a
    # selector no profile satisfies.
    #
    # The catalog is read only where its answer could be used: a pinned profile already states the
    # weights, and a request whose adapters declare nothing has nothing to resolve, so neither pays
    # for a listing. A deploy with no adapters at all returned above, before any of this.
    confirmed_model_id = (
        agreed_adapter_weights(
            declarations,
            await _published_adapter_weights(
                kube_client, namespace, base_aim_id, model_ref_name, selector_criteria or {}
            ),
        )
        if expected_model_id is None and declarations and base_aim_id
        else None
    )
    served = ServedWeights(model_id=expected_model_id or confirmed_model_id, aim_id=base_aim_id)
    failures: list[str] = []
    attachable: list[tuple[str, AIMArtifactResource]] = []
    for name, artifact in zip(names, artifacts, strict=True):
        if artifact is None or not is_platform_managed(artifact):
            failures.append(f"'{name}' is not an adapter in this project")
            continue
        compatible_with = artifact.spec.compatible_with or []
        if not compatible_with:
            failures.append(
                f"'{name}' does not declare which base models it can serve, so it cannot be attached to any "
                "deployment; re-create the adapter with that declaration"
            )
            continue
        # Checked after the adapter's own declaration so a permanently broken adapter is still named
        # here rather than hidden behind a model that may resolve on its own. With neither identity
        # known there is nothing to match against, so report the model as unresolved rather than
        # blaming every adapter for not listing it.
        if not served.model_id and not served.aim_id:
            failures.append(
                f"'{name}' cannot be checked because model '{model_ref_name}' has not resolved its "
                "identity yet; retry once the model reports it"
            )
            continue
        if not adapter_serves(compatible_with, served, adapter_name=name, namespace=namespace):
            # Both sides are logged because a resolution bug on either one is indistinguishable from
            # a user attaching the wrong adapter.
            logger.info(
                "Adapter {} in {} rejected for model {}: compatibleWith={}, requested modelId={}, base status.aimId={}",
                name,
                namespace,
                model_ref_name,
                compatible_with,
                served.model_id,
                served.aim_id,
            )
            failures.append(f"'{name}' does not list model '{model_ref_name}' among the models it can serve")
            continue
        attachable.append((name, artifact))

    # Readiness only applies to platform-hosted storage (uploaded via AIWB or produced by
    # fine-tuning) — AIWB can stat those weights directly. An externally sourced adapter's
    # sourceUri points somewhere AIWB has no reader for, so it is fetched and validated by
    # aim-engine instead.
    readiness_targets = [
        (name, location)
        for name, artifact in attachable
        if artifact.metadata.labels.get(MANAGED_BY_LABEL) in PLATFORM_MANAGED_BY_VALUES
        and (location := split_s3_uri(artifact.spec.source_uri)) is not None
    ]
    if minio_client is not None and readiness_targets:
        states = await gather_readiness(minio_client, (location for _, location in readiness_targets))
        failures.extend(
            f"'{name}' has no uploaded weights yet"
            for (name, _), state in zip(readiness_targets, states, strict=True)
            if state is ReadinessState.NOT_READY
        )

    # The identity the adapters were admitted on is the identity the deploy is pinned to; they are
    # the same value rather than two expressions that have to be kept agreeing. Withheld whenever
    # anything was refused, so a deploy that never happens cannot be narrowed by adapters the caller
    # is about to reject.
    return AdapterChecks(failures=failures, pinnable_model_id=None if failures else confirmed_model_id)
