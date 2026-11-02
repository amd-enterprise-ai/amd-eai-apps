# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Gateway for accessing AIMClusterModel resources from Kubernetes."""

import asyncio
from typing import Any
from uuid import UUID

from kubernetes_asyncio.client import ApiException
from loguru import logger
from pydantic import ValidationError

from api_common.exceptions import ConflictException, ExternalServiceError

from ..dispatch.kube_client import KubernetesClient
from ..dispatch.utils import get_resource_version
from ..inference.enums import InferenceCapability
from ..workloads.constants import WORKLOAD_ID_LABEL
from .constants import (
    AIM_API_GROUP,
    AIM_API_VERSION,
    AIM_ARTIFACT_PLURAL,
    AIM_CLUSTER_MODEL_PLURAL,
    AIM_CLUSTER_PROFILE_PLURAL,
    AIM_COND_HTTP_ROUTE_READY,
    AIM_LEGACY_API_VERSION,
    AIM_MODEL_LABEL,
    AIM_MODEL_PLURAL,
    AIM_PROFILE_PLURAL,
    AIM_PROFILE_SET_PLURAL,
    AIM_SERVICE_PLURAL,
    AIM_SERVICE_RESOURCE,
    AIM_SERVING_READY_CONDITIONS,
    CHAT_TAG_VALUE,
    FINE_TUNED_LABEL,
    HTTP_ROUTE_API_GROUP,
    HTTP_ROUTE_PLURAL,
    KSERVE_API_GROUP,
    KSERVE_INFERENCE_SERVICE_PLURAL,
    NAMESPACE_AIM_MODEL_LABEL,
    TRANSCRIPTION_TAG_VALUES,
)
from .crds import (
    AIMArtifactResource,
    AIMModelResource,
    AIMProfileResource,
    AIMProfileSetResource,
    AIMServiceAdapterRef,
    AIMServiceResource,
    HTTPRouteResource,
    ResolvedRef,
)
from .enums import AIMModelStatus, ResolutionScope
from .enums import AIMServiceStatus as AIMServiceStatusEnum
from .schemas import AIMDeployRequest
from .utils import (
    generate_aim_service_manifest,
    generate_namespace_aim_service_manifest,
    is_condition_true,
)


async def list_aims(
    kube_client: KubernetesClient,
    statuses: list[AIMModelStatus] | None = None,
) -> list[AIMModelResource]:
    """Get all AIMClusterModels from Kubernetes."""
    try:
        result = await kube_client.custom_objects.list_cluster_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            plural=AIM_CLUSTER_MODEL_PLURAL,
        )

        aims = []
        for item in result.get("items", []):
            aim = AIMModelResource.model_validate(item)
            aims.append(aim)

        logger.debug(f"Found {len(aims)} AIMClusterModels in cluster")

        # Filter by status if provided
        if statuses:
            aims = [aim for aim in aims if aim.status.status in statuses]

        return aims

    except Exception as e:
        logger.exception(f"Failed to list AIMClusterModels: {e}")
        return []


async def list_aim_cluster_models(
    kube_client: KubernetesClient,
    *,
    raise_on_error: bool = False,
) -> list[dict[str, Any]]:
    """List raw AIMClusterModel resources from Kubernetes."""
    try:
        result = await kube_client.custom_objects.list_cluster_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            plural=AIM_CLUSTER_MODEL_PLURAL,
        )
        if not isinstance(result, dict):
            logger.warning("AIMClusterModel list response is not a dict")
            return []
        items = result.get("items", [])
        if not isinstance(items, list):
            logger.warning("AIMClusterModel list response has non-list 'items'")
            return []
        return [item for item in items if isinstance(item, dict)]
    except Exception as e:
        logger.exception(f"Failed to list AIMClusterModels: {e}")
        if raise_on_error:
            raise
        return []


async def get_aim_by_name(kube_client: KubernetesClient, resource_name: str) -> AIMModelResource | None:
    """Get a specific AIMClusterModel from Kubernetes by resource name."""
    try:
        result = await kube_client.custom_objects.get_cluster_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            plural=AIM_CLUSTER_MODEL_PLURAL,
            name=resource_name,
        )

        return AIMModelResource.model_validate(result)

    except Exception as e:
        if hasattr(e, "status") and e.status == 404:
            logger.debug(f"AIMClusterModel {resource_name} not found")
            return None
        logger.exception(f"Failed to get AIMClusterModel {resource_name}: {e}")
        return None


async def get_aim_cluster_model_strict(kube_client: KubernetesClient, resource_name: str) -> AIMModelResource | None:
    """Get a specific AIMClusterModel by resource name. Returns None only on a definite 404.

    Unlike ``get_aim_by_name``, a non-404 failure (unreachable cluster, forbidden, etc.) raises
    ``ExternalServiceError`` instead of resolving to None — for callers that must not mistake a
    transient cluster fault for "no such model".
    """
    try:
        result = await kube_client.custom_objects.get_cluster_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            plural=AIM_CLUSTER_MODEL_PLURAL,
            name=resource_name,
        )
        return AIMModelResource.model_validate(result)
    except ApiException as e:
        if e.status == 404:
            return None
        logger.error(f"Failed to get AIMClusterModel {resource_name}: {e}")
        raise ExternalServiceError(f"Failed to get AIMClusterModel '{resource_name}': {e.reason}") from e


def _model_tags_match_capability(tags: list[str], capability: InferenceCapability) -> bool:
    """Return True when a catalog model's tags advertise the given capability."""
    if capability is InferenceCapability.CHAT:
        return CHAT_TAG_VALUE in tags
    if capability is InferenceCapability.TRANSCRIPTION:
        return any(tag in TRANSCRIPTION_TAG_VALUES for tag in tags)
    return False


def aim_service_has_capability(
    aim_service: AIMServiceResource,
    aims_by_name: dict[str, AIMModelResource],
    capability: InferenceCapability,
) -> bool:
    """Check whether a ready AIM service exposes the given inference capability.

    A service qualifies when:
    1. InferenceServiceReady condition is True (endpoint is reachable), and
    2. HTTPRouteReady condition is True (routing is configured), and
    3. its associated AIMClusterModel advertises the capability via its image
       metadata tags.

    Namespace AIMModel services (custom-onboarded / fine-tuned) have no
    cluster-scoped AIMClusterModel, so their capability cannot be read from the
    catalog. Today they are treated as chat by label; classifying them from
    their own source tags is handled separately.

    Note: We check conditions rather than status.status because a service
    can be in Degraded status while still having a functional inference endpoint.
    """
    conditions = aim_service.status.conditions
    if not all(is_condition_true(conditions, c) for c in AIM_SERVING_READY_CONDITIONS):
        return False

    # Namespace AIMModel services (fine-tuned/custom-onboarded) have no associated
    # AIMClusterModel, so we cannot read a catalog tag. They are still classified
    # as chat by label; classifying them from their own source tags (so a custom
    # speech-to-text model is also surfaced as transcription-capable) is deferred.
    if NAMESPACE_AIM_MODEL_LABEL in aim_service.metadata.labels or FINE_TUNED_LABEL in aim_service.metadata.labels:
        return capability is InferenceCapability.CHAT

    aim_name = aim_service.spec.model.name
    if not aim_name:
        return False

    aim_crd = aims_by_name.get(aim_name)
    if not aim_crd:
        logger.debug(f"AIM {aim_name} not found for service {aim_service.metadata.name}")
        return False

    return _model_tags_match_capability(aim_crd.status.image_metadata.model.tags, capability)


async def list_aim_services(
    kube_client: KubernetesClient,
    namespace: str,
    capability: InferenceCapability | None = None,
    status_filter: list[AIMServiceStatusEnum] | None = None,
) -> list[AIMServiceResource]:
    """List AIMService resources in a namespace.

    When ``capability`` is set, only serving-ready services whose catalog model
    advertises that capability are returned; ``status_filter`` further narrows the
    results to the given statuses.
    """
    try:
        result = await kube_client.custom_objects.list_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_SERVICE_PLURAL,
        )

        httproutes, isvc_names, aims_by_name = await asyncio.gather(
            _get_httproutes_for_aim_services(kube_client, namespace),
            _get_isvc_names(kube_client, namespace),
            _get_aims_by_name(kube_client) if capability is not None else asyncio.sleep(0, result={}),
        )

        aim_services = []
        for item in result.get("items", []):
            try:
                aim_service = AIMServiceResource.model_validate(item)

                # Filter by status inclusions
                if status_filter and aim_service.status.status not in status_filter:
                    continue

                # Apply capability filter
                if capability is not None and not aim_service_has_capability(aim_service, aims_by_name, capability):
                    continue

                if is_condition_true(aim_service.status.conditions, AIM_COND_HTTP_ROUTE_READY):
                    aim_service.httproute = httproutes.get(aim_service.metadata.name)
                    aim_service.inference_service_name = isvc_names.get(aim_service.metadata.name)
                aim_services.append(aim_service)
            except Exception as e:
                logger.error(f"Failed to parse AIMService: {e}")
                continue

        return aim_services

    except Exception as e:
        logger.exception(f"Failed to list AIMServices: {e}")
        return []


async def get_aim_service_by_id(
    kube_client: KubernetesClient,
    namespace: str,
    id: UUID,
) -> AIMServiceResource | None:
    """Get an AIMService by id label.

    Returns None only when no resource carries the label. A resource that exists but fails to
    parse raises instead of returning None — that would read as "not found" and let callers
    report a live, broken deployment as though it had been deleted.
    """
    label_selector = f"{WORKLOAD_ID_LABEL}={str(id)}"
    try:
        result = await kube_client.custom_objects.list_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_SERVICE_PLURAL,
            label_selector=label_selector,
        )
    except ApiException as e:
        logger.error(f"Failed to get AIMService by id {str(id)}: {e}")
        raise ExternalServiceError(f"Failed to get AIMService by id '{id}': {e.reason}") from e

    items = result.get("items", [])
    if not items:
        return None

    try:
        aim_service = AIMServiceResource.model_validate(items[0])
    except Exception as e:
        logger.error(f"Failed to parse AIMService by id {str(id)}: {e}")
        raise ExternalServiceError(f"Failed to parse AIMService for id '{id}': {e}") from e

    if is_condition_true(aim_service.status.conditions, AIM_COND_HTTP_ROUTE_READY):
        httproutes = await _get_httproutes_for_aim_services(kube_client, namespace)
        isvc_names = await _get_isvc_names(kube_client, namespace)
        aim_service.httproute = httproutes.get(aim_service.metadata.name)
        aim_service.inference_service_name = isvc_names.get(aim_service.metadata.name)
    return aim_service


async def create_aim_service(
    kube_client: KubernetesClient,
    namespace: str,
    aim: AIMModelResource,
    deploy_request: AIMDeployRequest,
    submitter: str,
    service_name: str,
    display_name: str | None = None,
    pinned_model_id: str | None = None,
    pinned_aim_id: str | None = None,
) -> AIMServiceResource:
    """Create an AIMService in Kubernetes.

    ``pinned_model_id``/``pinned_aim_id`` are the weights the requested adapters were built for,
    resolved by the caller and passed through to the profile selector.

    Args:
        aim: AIMClusterModel resource if found, None if deploying by image reference that doesn't exist yet
        service_name: The K8s resource name for the AIMService
        display_name: Optional user-visible display name stored as annotation
    """
    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=deploy_request,
        namespace=namespace,
        service_name=service_name,
        api_version=f"{AIM_API_GROUP}/{AIM_API_VERSION}",
        submitter=submitter,
        display_name=display_name,
        pinned_model_id=pinned_model_id,
        pinned_aim_id=pinned_aim_id,
    )

    created = await kube_client.custom_objects.create_namespaced_custom_object(
        group=AIM_API_GROUP,
        version=AIM_API_VERSION,
        namespace=namespace,
        plural=AIM_SERVICE_PLURAL,
        body=manifest,
    )

    return AIMServiceResource.model_validate(created)


async def create_namespace_aim_service(
    kube_client: KubernetesClient,
    namespace: str,
    model_name: str,
    deploy_request: AIMDeployRequest,
    submitter: str,
    service_name: str,
    display_name: str,
    canonical_name: str,
    is_fine_tuned: bool = True,
    resolved_profile_name: str | None = None,
    deploy_display_name: str | None = None,
    pinned_model_id: str | None = None,
    pinned_aim_id: str | None = None,
) -> AIMServiceResource:
    """Create an AIMService for a namespace-scoped AIMModel.

    ``display_name`` carries the onboarded model's identity (used for
    MODEL_NAME_LABEL/canonical display). ``deploy_display_name`` is the optional
    user-entered name from the deploy request; when present it takes precedence
    for the user-visible display-name annotation.

    ``pinned_model_id``/``pinned_aim_id`` are the weights the requested adapters were built for,
    resolved by the caller and passed through to the profile selector.
    """
    manifest = generate_namespace_aim_service_manifest(
        model_name=model_name,
        deploy_request=deploy_request,
        namespace=namespace,
        service_name=service_name,
        api_version=f"{AIM_API_GROUP}/{AIM_API_VERSION}",
        submitter=submitter,
        display_name=display_name,
        canonical_name=canonical_name,
        is_fine_tuned=is_fine_tuned,
        resolved_profile_name=resolved_profile_name,
        deploy_display_name=deploy_display_name,
        pinned_model_id=pinned_model_id,
        pinned_aim_id=pinned_aim_id,
    )

    created = await kube_client.custom_objects.create_namespaced_custom_object(
        group=AIM_API_GROUP,
        version=AIM_API_VERSION,
        namespace=namespace,
        plural=AIM_SERVICE_PLURAL,
        body=manifest,
    )
    return AIMServiceResource.model_validate(created)


async def create_fine_tuned_aim_service(
    kube_client: KubernetesClient,
    namespace: str,
    model_name: str,
    deploy_request: AIMDeployRequest,
    submitter: str,
    service_name: str,
    display_name: str,
    canonical_name: str,
) -> AIMServiceResource:
    """Wrapper for namespace-scoped AIMModel fine-tuned deployments."""
    return await create_namespace_aim_service(
        kube_client=kube_client,
        namespace=namespace,
        model_name=model_name,
        deploy_request=deploy_request,
        submitter=submitter,
        service_name=service_name,
        display_name=display_name,
        canonical_name=canonical_name,
        is_fine_tuned=True,
    )


async def delete_aim_service(
    kube_client: KubernetesClient,
    namespace: str,
    id: UUID,
) -> str:
    """Delete an AIMService from Kubernetes by id."""
    service = await get_aim_service_by_id(kube_client, namespace, id)
    if not service:
        raise ValueError(f"No AIMService found with id '{id}' in namespace '{namespace}'")

    # Delete the service
    await kube_client.custom_objects.delete_namespaced_custom_object(
        group=AIM_API_GROUP,
        version=AIM_API_VERSION,
        namespace=namespace,
        plural=AIM_SERVICE_PLURAL,
        name=service.metadata.name,
    )

    return service.metadata.name


async def list_aim_cluster_profiles_by_aim_ids(
    kube_client: KubernetesClient,
    aim_ids: list[str] | None = None,
) -> list[AIMProfileResource]:
    """List AIMClusterProfile resources, optionally filtered by spec.aimId.

    aim-engine declares ``spec.aimId`` in the CRD's ``selectableFields``, so
    multi-id filtering fans out to N parallel API-server calls (field
    selectors are equality-only). ``aim_ids`` is deduped before fan-out.
    """
    selectors: list[str | None] = [f"spec.aimId={aim_id}" for aim_id in dict.fromkeys(aim_ids)] if aim_ids else [None]

    async def fetch(field_selector: str | None) -> list[dict[str, Any]]:
        list_kwargs: dict[str, Any] = {
            "group": AIM_API_GROUP,
            "version": AIM_API_VERSION,
            "plural": AIM_CLUSTER_PROFILE_PLURAL,
        }
        if field_selector is not None:
            list_kwargs["field_selector"] = field_selector
        try:
            result = await kube_client.custom_objects.list_cluster_custom_object(**list_kwargs)
        except ApiException as e:
            logger.error(f"Failed to list AIMClusterProfiles: {e}")
            raise ExternalServiceError(f"Failed to list AIMClusterProfiles: {e.reason}") from e
        return result.get("items", [])

    item_lists = await asyncio.gather(*(fetch(fs) for fs in selectors))

    profiles: list[AIMProfileResource] = []
    for items in item_lists:
        for item in items:
            try:
                profiles.append(AIMProfileResource.model_validate(item))
            except Exception as e:
                logger.error(f"Failed to parse AIMClusterProfile: {e}")

    logger.debug(f"Found {len(profiles)} AIMClusterProfiles for aimIds {aim_ids or 'all'}")
    return profiles


async def get_aim_cluster_profile_by_name(
    kube_client: KubernetesClient,
    name: str,
) -> AIMProfileResource | None:
    """Fetch a single AIMClusterProfile by resource name.

    Direct K8s GET — ``metadata.name`` is always selectable, so no list /
    Python-side filter is needed. Returns ``None`` when the CR does not exist
    so callers can map to a 404 at the router boundary.
    """
    try:
        result = await kube_client.custom_objects.get_cluster_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            plural=AIM_CLUSTER_PROFILE_PLURAL,
            name=name,
        )
    except ApiException as e:
        if e.status == 404:
            return None
        logger.error(f"Failed to get AIMClusterProfile {name}: {e}")
        raise ExternalServiceError(f"Failed to get AIMClusterProfile '{name}': {e.reason}") from e
    return AIMProfileResource.model_validate(result)


async def patch_aim_service_spec(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
    spec_patch: dict[str, Any],
) -> AIMServiceResource:
    """Merge-patch ``spec`` on the named AIMService.

    ``ApiException`` is re-raised untouched: the API server's rejection of a spec mutation carries
    the CEL rule that explains it, and only the caller knows which of its own gates that maps to.
    """
    logger.info(f"Patching AIMService {name} spec fields: {sorted(spec_patch)}")

    try:
        patched = await kube_client.custom_objects.patch_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_SERVICE_PLURAL,
            name=name,
            body={"spec": spec_patch},
            _content_type="application/merge-patch+json",
        )
    except ApiException:
        logger.exception(f"Failed to patch AIMService {name} in namespace {namespace}")
        raise

    return AIMServiceResource.model_validate(patched)


async def list_aim_service_replicas(
    kube_client: KubernetesClient,
    namespace: str,
    id: UUID,
) -> list[dict]:
    """Return raw pod dicts for all pods belonging to an AIM service, sorted by name.

    Pods are fetched from Kubernetes and serialized to camelCase dicts via the K8s
    API client. Schema mapping is left to the router layer.
    """
    label_selector = f"{WORKLOAD_ID_LABEL}={str(id)}"
    try:
        result = await kube_client.core_v1.list_namespaced_pod(
            namespace=namespace,
            label_selector=label_selector,
        )
        replicas = []
        for pod in result.items:
            if not pod.metadata or not pod.metadata.name:
                continue
            pod_dict: dict = kube_client._api_client.sanitize_for_serialization(pod)
            replicas.append(pod_dict)

        return sorted(replicas, key=lambda r: r["metadata"]["name"])
    except Exception as e:
        logger.exception(f"Failed to list pods for AIM service {id}: {e}")
        return []


async def list_aim_models(
    kube_client: KubernetesClient,
    namespace: str,
    label_selector: str | None = None,
) -> list[AIMModelResource]:
    """List namespace-scoped AIMModel resources from Kubernetes.

    AIMModel CRs are created by the fine-tuning engine when a job completes successfully.
    """
    try:
        result = await kube_client.custom_objects.list_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_MODEL_PLURAL,
            label_selector=label_selector,
        )

        models = []
        for item in result.get("items", []):
            try:
                model = AIMModelResource.model_validate(item)
                models.append(model)
            except Exception as e:
                logger.error(f"Failed to parse AIMModel: {e}")
                continue

        logger.debug(f"Found {len(models)} AIMModels in namespace {namespace}")
        return models

    except Exception as e:
        logger.exception(f"Failed to list AIMModels in namespace {namespace}: {e}")
        return []


async def _get_aims_by_name(
    kube_client: KubernetesClient,
) -> dict[str, AIMModelResource]:
    """Get all AIMClusterModels, indexed by name.

    Single API call to avoid N+1 queries when checking chattable services.
    """
    aims = await list_aims(kube_client)
    return {aim.metadata.name: aim for aim in aims}


async def _get_httproutes_for_aim_services(
    kube_client: KubernetesClient,
    namespace: str,
) -> dict[str, HTTPRouteResource]:
    """Get all HTTPRoutes in a namespace, indexed by their owning AIMService name.

    Single API call to avoid N+1 queries when listing multiple AIMServices.
    """
    version = await get_resource_version(HTTP_ROUTE_API_GROUP, HTTP_ROUTE_PLURAL)
    if not version:
        return {}

    try:
        result = await kube_client.custom_objects.list_namespaced_custom_object(
            group=HTTP_ROUTE_API_GROUP,
            version=version,
            namespace=namespace,
            plural=HTTP_ROUTE_PLURAL,
        )

        routes: dict[str, HTTPRouteResource] = {}
        for item in result.get("items", []):
            for owner_ref in item.get("metadata", {}).get("ownerReferences", []):
                if (
                    owner_ref.get("kind") == AIM_SERVICE_RESOURCE
                    and owner_ref.get("controller") is True
                    and owner_ref.get("name")
                ):
                    routes[owner_ref["name"]] = HTTPRouteResource.model_validate(item)
                    break
        return routes

    except Exception as e:
        logger.exception(f"Failed to list HTTPRoutes in namespace {namespace}: {e}")
        return {}


async def _get_isvc_names(
    kube_client: KubernetesClient,
    namespace: str,
) -> dict[str, str]:
    """Map AIMService names to their InferenceService names via ownerReferences."""
    version = await get_resource_version(KSERVE_API_GROUP, KSERVE_INFERENCE_SERVICE_PLURAL)
    if not version:
        return {}

    try:
        result = await kube_client.custom_objects.list_namespaced_custom_object(
            group=KSERVE_API_GROUP, version=version, namespace=namespace, plural=KSERVE_INFERENCE_SERVICE_PLURAL
        )
        mapping: dict[str, str] = {}
        for item in result.get("items", []):
            isvc_name = item.get("metadata", {}).get("name")
            if not isvc_name:
                continue
            for owner in item.get("metadata", {}).get("ownerReferences", []):
                owner_name = owner.get("name")
                if owner_name and owner.get("kind") == AIM_SERVICE_RESOURCE and owner.get("controller"):
                    mapping[owner_name] = isvc_name
                    break
        return mapping
    except Exception as e:
        logger.warning(f"Failed to list InferenceServices in namespace {namespace}: {e}")
        return {}


async def get_aim_model(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
) -> AIMModelResource | None:
    """Get a namespace-scoped AIMModel by name."""
    try:
        result = await kube_client.custom_objects.get_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_MODEL_PLURAL,
            name=name,
        )
        return AIMModelResource.model_validate(result)
    except ApiException as e:
        if e.status == 404:
            return None
        raise


async def find_aim_model_by_label(
    kube_client: KubernetesClient,
    namespace: str,
    label_selector: str,
) -> AIMModelResource | None:
    """Find a namespace-scoped AIMModel matching a label selector. Returns the first match or None."""
    result = await kube_client.custom_objects.list_namespaced_custom_object(
        group=AIM_API_GROUP,
        version=AIM_API_VERSION,
        namespace=namespace,
        plural=AIM_MODEL_PLURAL,
        label_selector=label_selector,
    )
    items = result.get("items", [])
    if not items:
        return None
    return AIMModelResource.model_validate(items[0])


async def list_aim_services_for_model(
    kube_client: KubernetesClient,
    namespace: str,
    resource_name: str | None = None,
) -> list[AIMServiceResource]:
    """List AIMService CRs in a namespace, optionally filtered to one AIMModel.

    When ``resource_name`` is given, only services referencing that model are returned;
    with ``resource_name=None`` the list is namespace-wide, which callers use to compose
    profile ``inUseBy`` refs without N+1 lookups. This is a thin list: it validates the CRs
    but skips the HTTPRoute/InferenceService joins that ``list_aim_services`` performs.

    Parse-failure handling depends on the mode. When filtering to a specific model, a
    matching service that fails to parse raises: this backs the delete-safety check, where
    one fewer blocker than actually exists could let an in-use model be deleted. In the
    namespace-wide mode it only composes display-time ``inUseBy`` refs, so a single malformed
    (possibly unrelated) CR is logged and skipped rather than 502-ing the whole models grid.
    The ApiException contract (404 empty, other statuses re-raised as-is) is unchanged: at
    least one caller deliberately treats a lookup failure here as "skip this optimization".
    """
    try:
        result = await kube_client.custom_objects.list_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_SERVICE_PLURAL,
        )
    except ApiException as e:
        if e.status == 404:
            return []
        raise

    matches: list[AIMServiceResource] = []
    for item in result.get("items", []):
        if resource_name is not None and item.get("spec", {}).get("model", {}).get("name") != resource_name:
            continue
        try:
            matches.append(AIMServiceResource.model_validate(item))
        except Exception as e:
            if resource_name is None:
                svc_name = item.get("metadata", {}).get("name", "<unknown>")
                logger.warning(
                    f"Skipping unparseable AIMService '{svc_name}' in namespace '{namespace}' during "
                    f"namespace-wide list; its inUseBy refs will be omitted from the models grid: {e}"
                )
                continue
            logger.error(f"Failed to parse AIMService referencing model {resource_name}: {e}")
            raise ExternalServiceError(
                f"Failed to parse AIMService referencing model '{resource_name}' in namespace '{namespace}': {e}"
            ) from e
    return matches


async def delete_aim_model(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
) -> None:
    """Delete a namespace-scoped AIMModel CR. No-ops if the resource is missing."""
    try:
        await kube_client.custom_objects.delete_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_MODEL_PLURAL,
            name=name,
        )
        logger.info(f"Deleted AIMModel {name} from namespace {namespace}")
    except ApiException as e:
        if e.status == 404:
            return
        raise


async def create_aim_model(
    kube_client: KubernetesClient,
    namespace: str,
    manifest: dict,
) -> AIMModelResource:
    """Create a namespace-scoped AIMModel CR from a fully composed manifest.

    Sibling of create_aim_service; the manifest is composed by the caller because
    AIMModel covers more onboarding shapes than a single helper would. Translates
    409 from the API server into ConflictException so the FE sees a stable signal
    when a CR with the same name already exists.
    """
    try:
        created = await kube_client.custom_objects.create_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_MODEL_PLURAL,
            body=manifest,
        )
    except ApiException as e:
        if e.status == 409:
            raise ConflictException(
                f"AIMModel '{manifest.get('metadata', {}).get('name')}' already exists in namespace '{namespace}'"
            ) from e
        raise

    return AIMModelResource.model_validate(created)


async def create_aim_artifact(
    kube_client: KubernetesClient,
    namespace: str,
    manifest: dict,
) -> AIMArtifactResource:
    """Create a namespace-scoped AIMArtifact CR from a fully composed manifest.

    Translates 409 from the API server into ConflictException so callers see a
    stable signal when a CR with the same name already exists.
    """
    try:
        created = await kube_client.custom_objects.create_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_LEGACY_API_VERSION,
            namespace=namespace,
            plural=AIM_ARTIFACT_PLURAL,
            body=manifest,
        )
    except ApiException as e:
        if e.status == 409:
            raise ConflictException(
                f"AIMArtifact '{manifest.get('metadata', {}).get('name')}' already exists in namespace '{namespace}'"
            ) from e
        logger.error(f"Failed to create AIMArtifact in namespace {namespace}: {e}")
        raise ExternalServiceError(f"Failed to create AIMArtifact in namespace '{namespace}': {e.reason}") from e

    return AIMArtifactResource.model_validate(created)


async def get_aim_artifact(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
) -> AIMArtifactResource | None:
    """Get a namespace-scoped AIMArtifact by name. Returns None if it does not exist.

    Non-404 failures wrap as ``ExternalServiceError`` so every leg of an artifact request reports an
    unreachable cluster with the same status as its neighbours here, rather than passing the raw
    Kubernetes status through for this one call.
    """
    try:
        result = await kube_client.custom_objects.get_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_LEGACY_API_VERSION,
            namespace=namespace,
            plural=AIM_ARTIFACT_PLURAL,
            name=name,
        )
        return AIMArtifactResource.model_validate(result)
    except ApiException as e:
        if e.status == 404:
            return None
        logger.error(f"Failed to get AIMArtifact {name} in namespace {namespace}: {e}")
        raise ExternalServiceError(f"Failed to get AIMArtifact '{name}': {e.reason}") from e


async def patch_aim_model(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
    patch_body: dict,
) -> AIMModelResource:
    """Patch a namespace-scoped AIMModel CR using merge-patch semantics.

    Non-domain K8s failures wrap as ``ExternalServiceError`` (502). Status
    passthrough via the global ApiException handler is a follow-up — the
    FastAPI app currently only registers ``kubernetes.client.exceptions.ApiException``
    (the sync class), so re-raising the async client's ``kubernetes_asyncio.client.ApiException``
    would fall through to the generic handler and surface as an opaque 500
    rather than the upstream K8s status/body.
    """
    try:
        patched = await kube_client.custom_objects.patch_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_MODEL_PLURAL,
            name=name,
            body=patch_body,
            _content_type="application/merge-patch+json",
        )
    except ApiException as e:
        logger.error(f"Failed to patch AIMModel {name} in namespace {namespace}: {e}")
        raise ExternalServiceError(f"Failed to patch AIMModel '{name}': {e.reason}") from e

    return AIMModelResource.model_validate(patched)


def _is_service_owned_profile(item: dict[str, Any]) -> bool:
    """True if the profile carries an AIMService ownerReference (engine overlay).

    The engine materializes ``spec.profileOverrides`` as a
    namespace-scoped AIMProfile copy owned by the originating AIMService.
    These are deployment-internal artifacts; they should not appear in the
    user-facing profile catalog. We distinguish them by the controller
    ownerReference rather than a label so we don't depend on the engine
    setting one.
    """
    for owner_ref in item.get("metadata", {}).get("ownerReferences", []):
        if owner_ref.get("kind") == AIM_SERVICE_RESOURCE:
            return True
    return False


async def list_aim_profiles_by_aim_ids(
    kube_client: KubernetesClient,
    namespace: str,
    aim_ids: list[str] | None = None,
) -> list[AIMProfileResource]:
    """List namespace-scoped AIMProfile resources, optionally filtered by spec.aimId.

    Same field-selector mechanic as the cluster-scoped variant. The
    AIMService-owned overlay exclusion stays client-side — ownerReferences
    are not a selectable field.
    """
    selectors: list[str | None] = [f"spec.aimId={aim_id}" for aim_id in dict.fromkeys(aim_ids)] if aim_ids else [None]

    async def fetch(field_selector: str | None) -> list[dict[str, Any]]:
        list_kwargs: dict[str, Any] = {
            "group": AIM_API_GROUP,
            "version": AIM_API_VERSION,
            "namespace": namespace,
            "plural": AIM_PROFILE_PLURAL,
        }
        if field_selector is not None:
            list_kwargs["field_selector"] = field_selector
        try:
            result = await kube_client.custom_objects.list_namespaced_custom_object(**list_kwargs)
        except ApiException as e:
            logger.error(f"Failed to list AIMProfiles in namespace {namespace}: {e}")
            raise ExternalServiceError(f"Failed to list AIMProfiles in namespace '{namespace}': {e.reason}") from e
        return result.get("items", [])

    item_lists = await asyncio.gather(*(fetch(fs) for fs in selectors))

    profiles: list[AIMProfileResource] = []
    for items in item_lists:
        for item in items:
            if _is_service_owned_profile(item):
                continue
            try:
                profiles.append(AIMProfileResource.model_validate(item))
            except Exception as e:
                logger.error(f"Failed to parse AIMProfile: {e}")

    logger.debug(f"Found {len(profiles)} AIMProfiles for aimIds {aim_ids or 'all'} in {namespace}")
    return profiles


async def get_aim_profile_by_name(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
) -> AIMProfileResource | None:
    """Fetch a single namespace-scoped AIMProfile by resource name.

    Direct K8s GET — ``metadata.name`` is always selectable, so no list /
    Python-side filter is needed. Returns ``None`` when the CR does not exist
    so callers can map to a 404 at the router boundary.
    """
    try:
        result = await kube_client.custom_objects.get_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_PROFILE_PLURAL,
            name=name,
        )
    except ApiException as e:
        if e.status == 404:
            return None
        logger.error(f"Failed to get AIMProfile {name} in namespace {namespace}: {e}")
        raise ExternalServiceError(f"Failed to get AIMProfile '{name}' in namespace '{namespace}': {e.reason}") from e
    return AIMProfileResource.model_validate(result)


async def get_aim_profile_any_scope(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
) -> AIMProfileResource | None:
    """The profile a bare profile name refers to: the project's own copy, else cluster-wide.

    Returns None when neither scope has it. aim-engine owns profile resolution, so a name AIWB
    cannot place is left for it to reject rather than being second-guessed here.
    """
    namespaced, cluster = await asyncio.gather(
        get_aim_profile_by_name(kube_client, namespace, name),
        get_aim_cluster_profile_by_name(kube_client, name),
    )
    return namespaced or cluster


async def resolve_recorded_profile(
    kube_client: KubernetesClient,
    namespace: str,
    resolved: ResolvedRef | None,
) -> AIMProfileResource | None:
    """The profile ``status.resolvedProfile`` points at, read at the scope the reference states.

    A profile name is unique only within a scope, so one name can belong to both a project-scoped
    profile and a cluster-wide one serving different weights. aim-engine chose between them when it
    deployed the service and said which in the reference, so honouring that is the difference
    between reading the weights the deployment runs and reading a namesake's.

    A reference naming no scope AIWB can act on falls back to the bare-name lookup: ``Merged`` and
    ``Unknown`` identify no single object to read, and an engine newer than this code can state a
    scope that means nothing here.
    """
    if not resolved or not resolved.name:
        return None
    if resolved.scope == ResolutionScope.CLUSTER:
        return await get_aim_cluster_profile_by_name(kube_client, resolved.name)
    if resolved.scope == ResolutionScope.NAMESPACE:
        return await get_aim_profile_by_name(kube_client, resolved.namespace or namespace, resolved.name)
    return await get_aim_profile_any_scope(kube_client, namespace, resolved.name)


async def _list_aim_artifact_items(
    kube_client: KubernetesClient,
    namespace: str,
    label_selector: str | None = None,
) -> list[Any]:
    """Raw AIMArtifact list items, exactly as the API server returned them.

    A 404 means the CRD is absent (older cluster) and degrades to an empty list; any other API
    failure raises so the caller never mistakes an unreachable cluster for "no artifacts".
    """
    selector = {"label_selector": label_selector} if label_selector is not None else {}
    try:
        result = await kube_client.custom_objects.list_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_LEGACY_API_VERSION,
            namespace=namespace,
            plural=AIM_ARTIFACT_PLURAL,
            **selector,
        )
    except ApiException as e:
        if e.status == 404:
            logger.debug(f"AIMArtifact CRD not found in namespace {namespace}; treating as empty")
            return []
        logger.error(f"Failed to list AIMArtifacts in namespace {namespace}: {e}")
        raise ExternalServiceError(f"Failed to list AIMArtifacts in namespace '{namespace}': {e.reason}") from e
    return list(result.get("items", []))


async def list_aim_artifacts_by_label_selector(
    kube_client: KubernetesClient,
    namespace: str,
    label_selector: str | None = None,
) -> list[AIMArtifactResource]:
    """List AIMArtifacts in a namespace, optionally narrowed by a Kubernetes label selector.

    Which labels constitute a collection is the caller's policy, not this layer's; ``None`` selects
    every artifact, whoever authored it.

    Parsing is lenient: an artifact of an unexpected shape is logged and dropped rather than failing
    the whole listing. Callers deciding whether something is *safe* must not read the result that
    way — an absent artifact here means "unreadable" as often as it means "not there" — and should
    use ``list_aim_artifact_source_uris`` instead.
    """
    artifacts: list[AIMArtifactResource] = []
    for item in await _list_aim_artifact_items(kube_client, namespace, label_selector):
        try:
            artifacts.append(AIMArtifactResource.model_validate(item))
        except Exception as e:
            logger.error(f"Failed to parse AIMArtifact: {e}")
    return artifacts


async def list_aim_artifact_source_uris(
    kube_client: KubernetesClient,
    namespace: str,
) -> dict[str, str]:
    """Every AIMArtifact in the namespace mapped to the ``spec.sourceUri`` it records.

    Backs the storage-reclamation safety check, which asks whether anything else still points at a
    prefix about to be swept. Reads the raw items rather than the validated resources because a
    model-validation failure on an unrelated field would silently drop an artifact, and a dropped
    artifact reads as "does not claim this prefix" — deleting files it still owns. Only the two
    values the check needs are read, so nothing about the rest of the resource can suppress a claim.

    Artifacts with no readable name or string ``sourceUri`` are omitted: they name no location, so
    there is nothing they could be claiming.
    """
    source_uris: dict[str, str] = {}
    for item in await _list_aim_artifact_items(kube_client, namespace):
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata")
        spec = item.get("spec")
        name = metadata.get("name") if isinstance(metadata, dict) else None
        source_uri = spec.get("sourceUri") if isinstance(spec, dict) else None
        if isinstance(name, str) and isinstance(source_uri, str):
            source_uris[name] = source_uri
    return source_uris


async def delete_aim_artifact(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
) -> bool:
    """Delete a namespace-scoped AIMArtifact by name.

    Returns False when the artifact is already gone (404), so the caller can distinguish a
    just-accepted deletion from a no-op on the wire (202 vs 204). Any other API failure raises.
    """
    try:
        await kube_client.custom_objects.delete_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_LEGACY_API_VERSION,
            namespace=namespace,
            plural=AIM_ARTIFACT_PLURAL,
            name=name,
        )
    except ApiException as e:
        if e.status == 404:
            return False
        logger.error(f"Failed to delete AIMArtifact {name} in namespace {namespace}: {e}")
        raise ExternalServiceError(f"Failed to delete AIMArtifact '{name}': {e.reason}") from e
    return True


def _service_spec_references_artifact(spec: dict[str, Any], artifact_name: str) -> bool:
    """True if an AIMService spec attaches the named adapter artifact via ``spec.adapters[].name``.

    Backs the artifact-deletion-safety check: an artifact still referenced here is serving live
    adapter weights, so deleting it breaks that deployment on its next reload.

    Entries are validated one at a time so a single malformed neighbour cannot make every artifact
    in the namespace undeletable, and one that fails validation still has its raw ``name`` read: a
    reference AIWB cannot parse is a reference all the same, and reading past it would let live
    weights be deleted.
    """
    adapters = spec.get("adapters")
    if not isinstance(adapters, list):
        return False
    for entry in adapters:
        try:
            if AIMServiceAdapterRef.model_validate(entry).name == artifact_name:
                return True
        except ValidationError as e:
            logger.warning(f"Unparseable AIMService spec.adapters entry, falling back to raw name match: {e}")
            if isinstance(entry, dict) and entry.get("name") == artifact_name:
                return True
    return False


async def list_aim_services_referencing_artifact(
    kube_client: KubernetesClient,
    namespace: str,
    artifact_name: str,
) -> list[str]:
    """Names of AIMServices that attach the given adapter artifact.

    Whether a service references an artifact is a computed predicate over ``spec.adapters[].name``
    that K8s cannot express as a selector, so it is evaluated client-side over the raw list. Any API
    failure raises rather than returning [] — an empty result must mean "no references", never "we
    could not check", so an unreachable cluster can never let an in-use adapter be deleted.
    """
    try:
        result = await kube_client.custom_objects.list_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_SERVICE_PLURAL,
        )
    except ApiException as e:
        logger.error(f"Failed to list AIMServices in namespace {namespace}: {e}")
        raise ExternalServiceError(f"Failed to list AIMServices in namespace '{namespace}': {e.reason}") from e

    referencing: list[str] = []
    for item in result.get("items", []):
        spec = item.get("spec")
        if not isinstance(spec, dict) or not _service_spec_references_artifact(spec, artifact_name):
            continue
        name = item.get("metadata", {}).get("name")
        if name:
            referencing.append(name)
    return referencing


async def list_aim_profile_sets_for_model(
    kube_client: KubernetesClient,
    namespace: str,
    model_name: str | None = None,
    *,
    strict: bool = False,
) -> list[AIMProfileSetResource]:
    """List AIMProfileSets, optionally filtered on the model.name label.

    Always namespace-scoped: the K8s namespace guarantees a project only ever
    sees its own sets, even when another project has a model of the same name.
    Pass ``model_name=None`` to list every set in the namespace (used by the
    model-list endpoint to group sets per model in memory without N+1 calls).

    A Kubernetes read failure always raises. ``strict`` additionally raises when
    an individual set fails to parse, rather than dropping it from the list.
    Callers that resolve a decision from the set list want this: a vanished set
    reads as one the model does not have, which turns an upstream problem into a
    confident wrong answer.
    """
    label_selector = f"{AIM_MODEL_LABEL}={model_name}" if model_name else None
    try:
        result = await kube_client.custom_objects.list_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_PROFILE_SET_PLURAL,
            label_selector=label_selector,
        )
    except ApiException as e:
        logger.error(f"Failed to list AIMProfileSets in namespace {namespace}: {e}")
        raise ExternalServiceError(f"Failed to list AIMProfileSets in namespace '{namespace}': {e.reason}") from e

    profile_sets: list[AIMProfileSetResource] = []
    for item in result.get("items", []):
        try:
            profile_sets.append(AIMProfileSetResource.model_validate(item))
        except Exception as e:
            logger.error(f"Failed to parse AIMProfileSet: {e}")
            if strict:
                raise ExternalServiceError(f"Failed to parse AIMProfileSet in namespace '{namespace}': {e}") from e

    logger.debug(f"Found {len(profile_sets)} AIMProfileSets for model {model_name or 'all'} in {namespace}")
    return profile_sets


async def get_aim_profile_set_by_name(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
) -> AIMProfileSetResource | None:
    """Fetch a single namespace-scoped AIMProfileSet by name; None on 404."""
    try:
        result = await kube_client.custom_objects.get_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_PROFILE_SET_PLURAL,
            name=name,
        )
    except ApiException as e:
        if e.status == 404:
            return None
        logger.error(f"Failed to get AIMProfileSet {name} in namespace {namespace}: {e}")
        raise ExternalServiceError(
            f"Failed to get AIMProfileSet '{name}' in namespace '{namespace}': {e.reason}"
        ) from e
    return AIMProfileSetResource.model_validate(result)


async def create_aim_profile_set(
    kube_client: KubernetesClient,
    namespace: str,
    manifest: dict,
) -> AIMProfileSetResource:
    """Create a namespace-scoped AIMProfileSet from a composed manifest.

    AIWB-authored sets should carry a non-controller owner reference to the
    AIMModel so they cascade on model delete; the engine's auto-set already
    holds the single permitted controller:true owner on its own resource.
    """
    try:
        created = await kube_client.custom_objects.create_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_PROFILE_SET_PLURAL,
            body=manifest,
        )
    except ApiException as e:
        if e.status == 409:
            raise ConflictException(
                f"AIMProfileSet '{manifest.get('metadata', {}).get('name')}' already exists in namespace '{namespace}'"
            ) from e
        logger.error(f"Failed to create AIMProfileSet in namespace {namespace}: {e}")
        raise ExternalServiceError(f"Failed to create AIMProfileSet in namespace '{namespace}': {e.reason}") from e
    return AIMProfileSetResource.model_validate(created)


async def patch_aim_profile_set(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
    patch_body: dict,
) -> AIMProfileSetResource:
    """Patch a namespace-scoped AIMProfileSet using merge-patch semantics."""
    try:
        patched = await kube_client.custom_objects.patch_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_PROFILE_SET_PLURAL,
            name=name,
            body=patch_body,
            _content_type="application/merge-patch+json",
        )
    except ApiException as e:
        logger.error(f"Failed to patch AIMProfileSet {name} in namespace {namespace}: {e}")
        raise ExternalServiceError(
            f"Failed to patch AIMProfileSet '{name}' in namespace '{namespace}': {e.reason}"
        ) from e
    return AIMProfileSetResource.model_validate(patched)


async def delete_aim_profile(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
) -> None:
    """Delete a namespace-scoped AIMProfile. No-ops if it is already absent."""
    try:
        await kube_client.custom_objects.delete_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_PROFILE_PLURAL,
            name=name,
        )
        logger.info(f"Deleted AIMProfile {name} from namespace {namespace}")
    except ApiException as e:
        if e.status == 404:
            return
        logger.error(f"Failed to delete AIMProfile {name} in namespace {namespace}: {e}")
        raise ExternalServiceError(
            f"Failed to delete AIMProfile '{name}' in namespace '{namespace}': {e.reason}"
        ) from e


async def delete_aim_profile_set(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
) -> None:
    """Delete a namespace-scoped AIMProfileSet. No-ops if the resource is missing."""
    try:
        await kube_client.custom_objects.delete_namespaced_custom_object(
            group=AIM_API_GROUP,
            version=AIM_API_VERSION,
            namespace=namespace,
            plural=AIM_PROFILE_SET_PLURAL,
            name=name,
        )
        logger.info(f"Deleted AIMProfileSet {name} from namespace {namespace}")
    except ApiException as e:
        if e.status == 404:
            return
        logger.error(f"Failed to delete AIMProfileSet {name} in namespace {namespace}: {e}")
        raise ExternalServiceError(
            f"Failed to delete AIMProfileSet '{name}' in namespace '{namespace}': {e.reason}"
        ) from e
