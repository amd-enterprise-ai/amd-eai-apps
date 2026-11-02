# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT


import asyncio
import base64
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from kubernetes_asyncio.client import ApiException
from loguru import logger
from minio.error import S3Error
from pydantic import ValidationError

from api_common.exceptions import (
    ConflictException,
    ExternalServiceError,
    ForbiddenException,
    InconsistentStateException,
    NotFoundException,
    PreconditionNotMetException,
    ValidationException,
)
from api_common.secrets import SecretUseCase
from api_common.slugs import slugify

from ..aims import gateway as aims_gateway
from ..aims.constants import (
    AIM_API_GROUP,
    AIM_API_VERSION,
    AIM_PROFILE_SET_RESOURCE,
    PROFILE_ORIGIN_AIWB,
    PROFILE_ORIGIN_LABEL,
)
from ..aims.constants import AIM_MODEL_LABEL as AIM_MODEL_LABEL_KEY
from ..aims.crds import (
    AIMModelProfilesDerivedFrom,
    AIMModelProfilesSpec,
    AIMModelResource,
    AIMModelSource,
    AIMModelSourceEnvVar,
    AIMProfileResource,
    AIMProfileSetResource,
    AIMServiceResource,
    ProfileOverrides,
    ProfileSelector,
    ProfileSelectorModelRef,
)
from ..aims.utils import (
    classify_default_profile_set,
    effective_profile_for_set,
    env_entries_to_map,
    is_default_profile_set,
    owning_profile_set_name,
    profiles_derived_from_set,
)
from ..cluster.service import get_cluster_base_image_refs, is_supported_base_cluster_model
from ..cluster.utils import parse_container_image_repository_and_tag
from ..config import SUBMITTER_ANNOTATION
from ..dispatch.crds import K8sMetadata
from ..dispatch.kube_client import KubernetesClient
from ..dispatch.utils import sanitize_label_value
from ..minio.client import MinioClient, map_s3_error_to_domain_exception
from ..minio.config import MINIO_BUCKET, MINIO_URL
from ..models.utils import (
    delete_from_s3,
    get_custom_model_manifest_path,
    get_custom_model_root_path,
    get_custom_model_weights_path,
)
from ..secrets.constants import AIRM_USE_CASE_LABEL, USE_CASE_LABEL
from ..storages.constants import STORAGE_CONFIGMAP_LABEL, STORAGE_TYPE_LABEL
from ..storages.enums import StorageType
from ..workloads.constants import (
    CANONICAL_NAME_LABEL,
    DISPLAY_NAME_ANNOTATION,
    MODEL_NAME_LABEL,
    MODEL_SOURCE_TYPE_LABEL,
)
from ..workloads.enums import ModelSourceType
from .asr import (
    ASR_IDENTITY_AXES,
    apply_asr_preset,
    is_asr_source,
    is_audio_capable_base_image,
)
from .constants import (
    AIM_BASE_MODEL_NAME,
    AIM_BASE_MODEL_SCOPE,
    AIM_PROFILE_POLL_INTERVAL_SECONDS,
    AIM_PROFILE_WAIT_TIMEOUT_SECONDS,
    CANONICAL_REPO_ID_ANNOTATION,
    COMPONENT_ID_ANNOTATION,
    DEFAULT_AIM_DEPLOYMENT_IMAGE_REF,
    DEFAULT_PROFILE_ALIAS,
    HF_MAX_RESPONSE_BYTES,
    HF_REQUEST_TIMEOUT,
    IMPORT_ERROR_ANNOTATION,
    IMPORT_STATE_ANNOTATION,
    MODEL_CARD_FILENAME,
    MODEL_DISPLAY_NAME_ANNOTATION,
    MODEL_PRECISION_ANNOTATION,
    PROFILE_DISPLAY_NAME_ANNOTATION,
    REVISION_ANNOTATION,
    S3_EXPECTED_LAYOUT_FILES,
    S3_EXPECTED_TOKENIZER_FILES,
    SOURCE_DESCRIPTION_ANNOTATION,
    SOURCE_METADATA_MAX_BYTES,
    SOURCE_SHA_ANNOTATION,
    SOURCE_TAGS_ANNOTATION,
    SOURCE_URI_ANNOTATION,
)
from .enums import CustomModelImportType
from .gateway import (
    list_aim_profiles,
    list_base_role_profiles,
    patch_aim_profile,
    wait_for_aim_profile,
)
from .manifest import (
    ManifestDocument,
    delete_manifest_from_s3,
    manifest_write_lock,
    read_manifest_from_s3,
    remove_manifest_documents,
    upsert_manifest_documents,
    write_manifest_to_s3,
)
from .schemas import (
    BaseImageRuntimeProfileOptions,
    CustomModelOnboardStatus,
    CustomModelPatchRequest,
    CustomModelPatchResponse,
    CustomModelResponse,
    CustomProfileConfiguration,
    CustomProfileCreateRequest,
    CustomProfilePatchRequest,
    CustomProfileResponse,
    CustomProfileStatus,
    OnboardRequest,
    PreviewRequest,
    PreviewResponse,
    ProfileInUseRef,
    RuntimeProfileCombination,
    RuntimeProfileOptions,
)
from .tag_discovery import (
    DiscoveredMetadata,
    card_metadata_from_frontmatter,
    parse_card_frontmatter,
    resolve_discovered_tags,
)
from .utils import (
    build_copy_onboard_request,
    build_description,
    build_display_metadata_patch,
    build_display_name,
    classify_siblings,
    display_metadata_response_from_model,
    extract_onboard_repo_id,
    extract_overrides_image,
    get_layout_hint,
    hub_request_args,
    next_copy_display_name,
    normalize_hf_source,
    raise_for_hub_status,
    resolve_custom_model_display_name,
    resolve_onboard_phase,
    validate_hf_repo_id,
)

# The AIMProfile CRD kind name carried on the wire. The Pydantic resource
# model strips ``kind`` and ``apiVersion`` during validation, so the manifest
# emitter has to re-add them — without these the document is not reapplyable
# with ``kubectl apply -f manifest.yaml``.
_AIM_PROFILE_KIND = "AIMProfile"
_AIM_MODEL_KIND = "AIMModel"
# All AIM CRDs share one group/version; kubectl apply routes each manifest
# document to its own CRD.
_AIM_API_VERSION_FULL = f"{AIM_API_GROUP}/{AIM_API_VERSION}"

# Trim a slugified display name so the AIMModel CR name stays well within the
# K8s DNS-subdomain 253-char limit even after appending the 8-char id suffix.
_RESOURCE_NAME_SLUG_MAX_LENGTH = 200


def _manifest_contains_aim_model(
    documents: list[ManifestDocument],
    namespace: str,
    aim_model_name: str,
) -> bool:
    """Return True iff ``documents`` carries an AIMModel scaffold matching
    the namespace and name being onboarded.

    The S3 key is already namespace-scoped, but a manifest carrying an
    AIMModel doc with a different ``metadata.namespace`` or
    ``metadata.name`` is a corruption signal — checking both fields
    catches a manifest that was hand-edited or partially written by an
    older version, where the overall blob exists but the AIMModel half
    is missing or wrong.
    """
    for doc in documents:
        if doc.get("kind") != _AIM_MODEL_KIND:
            continue
        metadata = doc.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if metadata.get("name") != aim_model_name:
            continue
        doc_namespace = metadata.get("namespace")
        if doc_namespace is None or doc_namespace == namespace:
            return True
    return False


async def _get_hf_token(kube_client: KubernetesClient, namespace: str, secret_name: str) -> str:
    try:
        secret = await kube_client.core_v1.read_namespaced_secret(name=secret_name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            raise NotFoundException(f"Secret '{secret_name}' not found in namespace '{namespace}'") from e
        logger.error(f"Failed to read secret '{secret_name}' in namespace '{namespace}': {e}")
        raise ExternalServiceError(f"Failed to read secret '{secret_name}': {e.reason}") from e

    data = secret.data or {}
    if "token" not in data:
        raise ValidationException(
            message=f"Secret '{secret_name}' does not contain a 'token' key. "
            "Ensure the secret was created with a 'token' key holding the HF access token."
        )

    try:
        token = base64.b64decode(data["token"], validate=True).decode("utf-8").strip()
    except Exception as e:
        raise ValidationException(
            message=f"Secret '{secret_name}' has an invalid 'token' value: {type(e).__name__}"
        ) from e
    if not token:
        raise ValidationException(
            message=f"Secret '{secret_name}' contains an empty 'token' value. "
            "The 'token' key must hold a non-empty Hugging Face access token."
        )
    return token


async def _get_hub_response(repo_id: str, url: str, params: dict, headers: dict) -> tuple[int, bytes]:
    try:
        async with httpx.AsyncClient(timeout=HF_REQUEST_TIMEOUT) as client:
            async with client.stream("GET", url, params=params, headers=headers) as response:
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > HF_MAX_RESPONSE_BYTES:
                        raise ExternalServiceError(
                            f"Hugging Face Hub response for '{repo_id}' exceeded {HF_MAX_RESPONSE_BYTES} bytes."
                        )
                    chunks.append(chunk)
                return response.status_code, b"".join(chunks)
    except httpx.TimeoutException as e:
        raise ExternalServiceError(f"Timed out contacting Hugging Face Hub for '{repo_id}'") from e
    except httpx.RequestError as e:
        raise ExternalServiceError(
            f"Network error contacting Hugging Face Hub for '{repo_id}': {type(e).__name__}"
        ) from e


async def _fetch_hub_model(repo_id: str, revision: str | None, token: str | None) -> dict:
    logger.debug(f"Fetching Hub metadata for {repo_id}@{revision or '<default-branch>'}")
    url, params, headers = hub_request_args(repo_id, revision, token)
    status_code, body = await _get_hub_response(repo_id, url, params, headers)
    raise_for_hub_status(status_code, repo_id, revision, token, body)
    try:
        payload = json.loads(body)
    except ValueError as e:
        raise ExternalServiceError(f"Hugging Face Hub returned an unparseable response for '{repo_id}'.") from e
    if not isinstance(payload, dict):
        raise ExternalServiceError(f"Hugging Face Hub returned an invalid response shape for '{repo_id}'.")
    siblings = payload.get("siblings")
    if siblings is not None and not isinstance(siblings, list):
        raise ExternalServiceError(f"Hugging Face Hub returned an invalid 'siblings' field for '{repo_id}'.")
    return payload


def _build_aim_base_model_manifest(*, namespace: str, image_ref: str, model_name: str = AIM_BASE_MODEL_NAME) -> dict:
    """Compose the namespace-scoped base-image AIMModel that emits derivable profiles."""
    metadata = K8sMetadata(name=model_name, namespace=namespace)
    return {
        "apiVersion": _AIM_API_VERSION_FULL,
        "kind": _AIM_MODEL_KIND,
        "metadata": metadata.model_dump(by_alias=True, exclude_none=True),
        "spec": {"image": image_ref},
    }


# Kubernetes metadata.name is a DNS subdomain of labels no longer than 63 characters.
_K8S_RESOURCE_NAME_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_K8S_RESOURCE_NAME_MAX_LENGTH = 253


def _base_model_name_from_image_ref(image_ref: str, *, fallback: bool = True) -> str:
    """Resolve the base-model name from a selected base image ref.

    Use the repository tail directly as ``derivedFrom.modelRef.name``.
    Invalid or empty refs fall back to the legacy default (``aim-base``)
    only when ``fallback`` is true — explicit user selections must not.
    """
    try:
        repository, _ = parse_container_image_repository_and_tag(image_ref)
    except ValueError:
        if fallback:
            return AIM_BASE_MODEL_NAME
        raise ValidationException(f"Image '{image_ref}' does not identify a supported runtime family.") from None
    model_name = repository.rsplit("/", 1)[-1].strip()
    if not model_name:
        if fallback:
            return AIM_BASE_MODEL_NAME
        raise ValidationException(f"Image '{image_ref}' does not identify a supported runtime family.")
    return model_name


def _require_valid_base_model_name(model_name: str, image_ref: str) -> None:
    """Reject image families that cannot be stored as a Kubernetes resource name."""
    labels = model_name.split(".")
    if (
        len(model_name) <= _K8S_RESOURCE_NAME_MAX_LENGTH
        and labels
        and all(_K8S_RESOURCE_NAME_LABEL_RE.fullmatch(label) for label in labels)
    ):
        return
    raise ValidationException(f"Image '{image_ref}' does not identify a supported runtime family.")


def _image_refs_match(left: str, right: str) -> bool:
    try:
        left_repo, left_tag = parse_container_image_repository_and_tag(left)
        right_repo, right_tag = parse_container_image_repository_and_tag(right)
    except ValueError:
        return left.strip() == right.strip()
    return _normalize_repository_for_match(left_repo) == _normalize_repository_for_match(right_repo) and (
        left_tag == right_tag
    )


async def _resolve_cluster_scoped_base_model_name(kube_client: KubernetesClient, image_ref: str) -> str:
    """Return the AIMClusterModel name whose ``spec.image`` matches ``image_ref``."""
    try:
        parse_container_image_repository_and_tag(image_ref)
    except ValueError:
        raise ValidationException(f"Image '{image_ref}' does not identify a supported runtime family.") from None

    matches: list[str] = []
    for item in await aims_gateway.list_aim_cluster_models(kube_client, raise_on_error=True):
        if not is_supported_base_cluster_model(item):
            continue
        spec = item.get("spec") if isinstance(item, dict) else None
        current_image = (spec or {}).get("image") if isinstance(spec, dict) else None
        if not isinstance(current_image, str) or not current_image.strip():
            continue
        if not _image_refs_match(current_image, image_ref):
            continue
        name = ((item.get("metadata") or {}).get("name") if isinstance(item, dict) else None) or ""
        if isinstance(name, str) and name.strip():
            matches.append(name.strip())
    if not matches:
        raise NotFoundException(f"No AIMClusterModel found for base image '{image_ref}'.")
    return sorted(matches)[0]


def _selected_base_image_conflict(namespace: str, model_name: str, current_image_ref: str, image_ref: str) -> None:
    raise ConflictException(
        f"Base model '{model_name}' in project '{namespace}' already uses image "
        f"'{current_image_ref}', which conflicts with requested image '{image_ref}'. "
        "Keep the existing runtime tag, or onboard in a project that does not already "
        "provision this family. To change only this model's container image without "
        "repointing the shared family, update the model instead of re-onboarding."
    )


async def ensure_namespace_aim_base_model(
    kube_client: KubernetesClient,
    namespace: str,
    image_ref: str | None = None,
    model_name: str | None = None,
) -> str:
    """Idempotently provision the base-image AIMModel BYOM ``derivedFrom`` needs.

    When ``image_ref`` is not supplied, the base image is resolved from the
    cluster's detected accelerators rather than a static default.

    When the configured base-model scope is not ``Namespace``, this still
    derives the family from a selected ``image_ref`` by matching an existing
    cluster-scoped AIMClusterModel (without creating or patching a namespaced
    AIMModel).
    """
    image_ref_was_selected = image_ref is not None
    if image_ref is None:
        if AIM_BASE_MODEL_SCOPE != "Namespace":
            return AIM_BASE_MODEL_NAME
        image_refs = await get_cluster_base_image_refs(kube_client)
        image_ref = (
            DEFAULT_AIM_DEPLOYMENT_IMAGE_REF if DEFAULT_AIM_DEPLOYMENT_IMAGE_REF in image_refs else image_refs[0]
        )
    if AIM_BASE_MODEL_SCOPE != "Namespace":
        return await _resolve_cluster_scoped_base_model_name(kube_client, image_ref)

    if model_name is None:
        model_name = _base_model_name_from_image_ref(image_ref, fallback=not image_ref_was_selected)
    _require_valid_base_model_name(model_name, image_ref)

    existing = await aims_gateway.get_aim_model(kube_client, namespace, model_name)
    if existing is not None:
        current_image_ref = (existing.spec.image or "").strip()
        if not _image_refs_match(current_image_ref, image_ref):
            if image_ref_was_selected:
                _selected_base_image_conflict(namespace, model_name, current_image_ref, image_ref)
            await aims_gateway.patch_aim_model(
                kube_client,
                namespace,
                model_name,
                {"spec": {"image": image_ref}},
            )
            logger.info(
                f"Re-pointed base-image AIMModel {model_name} in namespace {namespace} "
                f"from {current_image_ref!r} to {image_ref!r}"
            )
        return model_name

    manifest = _build_aim_base_model_manifest(namespace=namespace, image_ref=image_ref, model_name=model_name)
    try:
        await aims_gateway.create_aim_model(kube_client, namespace, manifest)
        logger.info(f"Provisioned base-image AIMModel {model_name} in namespace {namespace}")
    except ConflictException:
        raced = await aims_gateway.get_aim_model(kube_client, namespace, model_name)
        if raced is None:
            raise
        current_image_ref = (raced.spec.image or "").strip()
        if image_ref_was_selected and not _image_refs_match(current_image_ref, image_ref):
            _selected_base_image_conflict(namespace, model_name, current_image_ref, image_ref)
        logger.debug(f"Base-image AIMModel {model_name} already exists in namespace {namespace} after create race")
    return model_name


# Keys in spec.profiles.overrides that the onboard/edit flow owns and stamps
# itself — model identity, runtime image, and BYO weights. Any same-named key
# in a client-supplied customProfile is dropped before these authoritative
# values are written, so the opaque pass-through cannot spoof the model
# identity or repoint the weights. Both snake_case and camelCase spellings are
# stripped because customProfile is opaque and may arrive in either casing.
_OVERRIDES_RESERVED_KEYS = (
    "aim_id",
    "aimId",
    "model_id",
    "modelId",
    "image",
    "model_sources",
    "modelSources",
)


def _normalize_engine_env(custom_profile: dict[str, Any] | None) -> dict[str, Any] | None:
    """If ``engineEnv`` is a list of ``{name, value}`` entries, rewrite it as a string map."""
    if not custom_profile or not isinstance(custom_profile.get("engineEnv"), list):
        return custom_profile
    normalized = dict(custom_profile)
    normalized["engineEnv"] = env_entries_to_map(normalized["engineEnv"])
    return normalized


def build_overrides_payload(
    *,
    custom_profile: dict[str, Any] | None,
    repo_id: str,
    image: str,
    model_sources: list[dict[str, Any]],
    identity_id: str | None = None,
) -> dict[str, Any]:
    """Compose a ``spec.profiles.overrides`` payload from opaque customProfile fields plus the authoritative identity, image, and weights.

    Client ``customProfile`` keys pass through verbatim (aim-engine validates
    shape at admission); the reserved identity/image/weights keys are always
    stamped by the server in their camelCase CRD spelling so the result is
    applyable both through ``ProfileOverrides.model_validate`` (onboard) and as
    a raw JSON merge-patch body (edit). ``null`` values inside ``customProfile``
    are preserved so a merge-patch edit can delete (reset) an overridden field.
    """
    custom_profile = _normalize_engine_env(custom_profile)
    payload: dict[str, Any] = dict(custom_profile) if custom_profile else {}
    for reserved_key in _OVERRIDES_RESERVED_KEYS:
        payload.pop(reserved_key, None)
    model_source_identity = ""
    if model_sources:
        source_model_id = model_sources[0].get("modelId")
        if isinstance(source_model_id, str):
            model_source_identity = source_model_id
    # Keep identity stable for edit/patch flows: if caller does not provide an
    # explicit identity_id, prefer the existing modelSources[*].modelId (the
    # live CR identity) over repo_id/canonical source.
    effective_identity_id = identity_id or model_source_identity or repo_id
    payload.update(
        {
            "aimId": effective_identity_id,
            "modelId": effective_identity_id,
            "image": image,
            "modelSources": model_sources,
        }
    )
    return payload


def _runtime_override_fields(custom_profile: dict[str, Any] | None) -> dict[str, Any]:
    """Return only the opaque runtime knobs from a customProfile, dropping the server-owned identity/image/weights keys.

    The live AIMProfile derives identity, image, and weights from the AIMModel,
    so an edit must merge only the runtime tuning fields (engine, engineArgs,
    precision, etc.) onto ``AIMProfile.spec`` — never the reserved keys, which
    would clobber aim-engine-derived values. ``null`` values are preserved so a
    merge-patch can reset a field.
    """
    if not custom_profile:
        return {}
    normalized = _normalize_engine_env(custom_profile) or {}
    return {key: value for key, value in normalized.items() if key not in _OVERRIDES_RESERVED_KEYS}


# Runtime knobs persisted as maps under ``spec.profiles.overrides``. A JSON
# merge-patch deletes a map key only when the patch sets it to ``null``, so an
# edit that drops one key of several must carry an explicit ``null`` tombstone
# for it (see _tombstone_removed_map_keys).
_MERGE_PATCH_MAP_FIELDS = ("engineArgs", "engineEnv")


def _existing_overrides_map(model: AIMModelResource) -> dict[str, Any]:
    """Return the live ``spec.profiles.overrides`` as a camelCase dict, or ``{}``."""
    profiles = model.spec.profiles
    if profiles is None or profiles.overrides is None:
        return {}
    return profiles.overrides.model_dump(by_alias=True, exclude_none=True)


def _tombstone_removed_map_keys(
    custom_profile: dict[str, Any] | None,
    existing_overrides: dict[str, Any],
) -> dict[str, Any] | None:
    """Add explicit ``null`` entries for runtime-map keys the edit dropped.

    RFC 7396 merge-patch removes a map key only when the patch sets it to
    ``null``; a key merely absent from the patch is left intact. So removing one
    of several ``engineArgs``/``engineEnv`` pairs in the edit form must send the
    surviving keys *plus* a ``null`` tombstone for each dropped key, or the
    deletion silently fails to persist. A whole-field reset (incoming ``null``)
    and a never-set field need no tombstones.
    """
    if not custom_profile:
        return custom_profile
    normalized = _normalize_engine_env(custom_profile) or {}
    result = dict(normalized)
    for field in _MERGE_PATCH_MAP_FIELDS:
        new_value = result.get(field)
        existing_value = existing_overrides.get(field)
        if not isinstance(new_value, dict) or not isinstance(existing_value, dict):
            continue
        removed_keys = existing_value.keys() - new_value.keys()
        if removed_keys:
            result[field] = {**new_value, **dict.fromkeys(removed_keys, None)}
    return result


def _build_custom_aim_model_manifest(
    *,
    namespace: str,
    resource_name: str,
    source: OnboardRequest,
    source_uri: str,
    submitter: str,
    component_id: str,
    base_model_name: str = AIM_BASE_MODEL_NAME,
    model_source_env: list[AIMModelSourceEnvVar] | None = None,
) -> dict:
    """Build a profiles-only v1alpha2 AIMModel manifest with image-family base derivation and stamped repo/image/weights/customProfile overrides."""
    display_label_value = sanitize_label_value(source.display_name)
    canonical_label_value = sanitize_label_value(source.repo_id)

    labels: dict[str, str] = {
        MODEL_NAME_LABEL: display_label_value,
        CANONICAL_NAME_LABEL: canonical_label_value,
        MODEL_SOURCE_TYPE_LABEL: ModelSourceType.CUSTOM,
    }

    annotations: dict[str, str] = {
        SUBMITTER_ANNOTATION: submitter,
        DISPLAY_NAME_ANNOTATION: source.display_name,
        MODEL_DISPLAY_NAME_ANNOTATION: source.display_name,
        CANONICAL_REPO_ID_ANNOTATION: source.repo_id,
        COMPONENT_ID_ANNOTATION: component_id,
        SOURCE_URI_ANNOTATION: source_uri,
        REVISION_ANNOTATION: source.revision,
        SOURCE_SHA_ANNOTATION: source.sha,
        SOURCE_DESCRIPTION_ANNOTATION: source.description,
        SOURCE_TAGS_ANNOTATION: json.dumps(source.tags),
    }

    # Precision is pruned from overrides; store it.
    precision = (source.custom_profile or {}).get("precision")
    if precision:
        annotations[MODEL_PRECISION_ANNOTATION] = str(precision)

    # AIMModel CRD validates modelSources[*].modelId as owner/model. For S3
    # imports we keep the true external location in sourceUri and write a
    # synthetic, CRD-valid identifier in modelId.
    source_model_id = source.repo_id
    if source.source_type == CustomModelImportType.S3:
        source_model_id = f"s3/{resource_name}"
    weights_source = AIMModelSource(model_id=source_model_id, source_uri=source_uri)
    if model_source_env is not None:
        weights_source.env = model_source_env
    else:
        # Hugging Face sources load directly from hf://; only wire HF_TOKEN when
        # a token secret was selected. Public models omit env entirely.
        weights_source.env = []
        if source.hf_token_secret_name:
            weights_source.env.append(
                AIMModelSourceEnvVar.model_validate(
                    {
                        "name": "HF_TOKEN",
                        "valueFrom": {"secretKeyRef": {"name": source.hf_token_secret_name, "key": "token"}},
                    }
                )
            )
        if not weights_source.env:
            weights_source.env = None
    overrides_payload = build_overrides_payload(
        custom_profile=source.custom_profile,
        repo_id=source.repo_id,
        image=source.image,
        model_sources=[weights_source.model_dump(by_alias=True, exclude_none=True)],
        identity_id=source_model_id,
    )

    profiles = AIMModelProfilesSpec(
        derived_from=AIMModelProfilesDerivedFrom(
            selector=ProfileSelector(
                role="base",
                model_ref=ProfileSelectorModelRef(name=base_model_name, scope=AIM_BASE_MODEL_SCOPE),
            ),
        ),
        version_policy="all",
        overrides=ProfileOverrides.model_validate(overrides_payload),
    )

    metadata = K8sMetadata(
        name=resource_name,
        namespace=namespace,
        labels=labels,
        annotations=annotations,
    )

    return {
        "apiVersion": _AIM_API_VERSION_FULL,
        "kind": _AIM_MODEL_KIND,
        "metadata": metadata.model_dump(by_alias=True, exclude_none=True),
        "spec": {"profiles": profiles.model_dump(by_alias=True, exclude_none=True)},
    }


async def _sync_manifest_to_s3(minio_client: MinioClient, object_key: str, aim_model_manifest: dict) -> None:
    """Upsert the AIMModel doc into the namespace S3 manifest under lock, preserving any existing AIMProfile document."""
    async with manifest_write_lock(MINIO_BUCKET, object_key):
        await _upsert_manifest_to_s3_unlocked(minio_client, object_key, aim_model_manifest)


async def _upsert_manifest_to_s3_unlocked(minio_client: MinioClient, object_key: str, aim_model_manifest: dict) -> None:
    """Read → upsert a single AIMModel doc → write, without acquiring the lock.

    Thin wrapper over :func:`_upsert_manifest_documents_to_s3_unlocked` for the
    common single-document case (onboard sync, metadata-only edit).
    """
    await _upsert_manifest_documents_to_s3_unlocked(minio_client, object_key, [aim_model_manifest])


async def _upsert_manifest_documents_to_s3_unlocked(
    minio_client: MinioClient, object_key: str, documents: list[dict]
) -> None:
    """Read → upsert one or more documents → write the manifest object *without* acquiring the lock.

    Callers that must include a cluster mutation inside the same critical
    section (so the durable mirror cannot invert relative to the
    authoritative CR) hold ``manifest_write_lock`` themselves and invoke
    this directly — ``manifest_write_lock`` is a non-reentrant
    ``asyncio.Lock``, so re-entering via :func:`_sync_manifest_to_s3`
    would deadlock.

    Documents are matched on ``(kind, name)`` by
    :func:`upsert_manifest_documents`, so passing both the AIMModel and its
    AIMProfile in one call refreshes both in a single read-modify-write —
    used by the runtime-profile edit path, which mutates both CRs under one
    lock.
    """
    existing = await read_manifest_from_s3(minio_client, MINIO_BUCKET, object_key)
    merged = upsert_manifest_documents(existing=existing, new_documents=documents)
    await write_manifest_to_s3(minio_client, MINIO_BUCKET, object_key, merged)


def _custom_model_weights_uri(namespace: str, resource_name: str) -> str:
    """Compose the s3:// URI inference loads weights from for a BYOM AIMModel."""
    return f"s3://{MINIO_BUCKET}/{get_custom_model_weights_path(namespace, resource_name)}"


def _normalize_s3_source(source: str) -> tuple[str, str, str]:
    """Return normalized source URI, bucket, and prefix from an S3 URI.

    Requires an explicit prefix so preview validates one model tree and never
    scans an entire bucket.
    """
    normalized = source.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme.lower() != "s3" or not parsed.netloc:
        raise ValidationException(message=f"Invalid S3 source '{source}'. Expected format: s3://bucket/prefix")
    prefix = parsed.path.strip("/")
    if not prefix:
        raise ValidationException(
            message=(f"Invalid S3 source '{source}'. Expected format: s3://bucket/prefix (prefix is required).")
        )
    return normalized, parsed.netloc, prefix


def _decode_secret_data_value(secret_name: str, key_name: str, encoded_value: str) -> str:
    """Decode one base64-encoded Kubernetes secret value."""
    try:
        decoded = base64.b64decode(encoded_value, validate=True).decode("utf-8").strip()
    except Exception as e:
        raise ValidationException(
            message=f"Secret '{secret_name}' has an invalid '{key_name}' value: {type(e).__name__}"
        ) from e
    if not decoded:
        raise ValidationException(
            message=(
                f"Secret '{secret_name}' contains an empty '{key_name}' value. "
                "The key must hold a non-empty credential value."
            )
        )
    return decoded


def _validate_secret_use_case(
    secret_name: str,
    labels: dict[str, str],
    expected_use_case: SecretUseCase,
    context: str,
) -> None:
    """Reject secrets labeled for a different use case when label metadata is present."""
    use_case_label = labels.get(USE_CASE_LABEL) or labels.get(AIRM_USE_CASE_LABEL)
    if not use_case_label:
        return
    try:
        use_case = SecretUseCase(use_case_label)
    except ValueError as e:
        raise ValidationException(
            f"Secret '{secret_name}' has an unrecognized use-case label value '{use_case_label}'. "
            f"Expected one of: {', '.join(uc.value for uc in SecretUseCase)}."
        ) from e
    if use_case != expected_use_case:
        raise ForbiddenException(
            f"Secret '{secret_name}' is labeled for use case '{use_case_label}' and cannot be used for "
            f"{context}. Use a secret labeled '{expected_use_case.value}'."
        )


def _validate_s3_secret_use_case(secret_name: str, labels: dict[str, str], context: str) -> None:
    """Validate optional secret use-case label compatibility for S3 operations."""
    _validate_secret_use_case(
        secret_name=secret_name,
        labels=labels,
        expected_use_case=SecretUseCase.S3,
        context=context,
    )


async def _read_namespaced_secret_for_s3_preview(
    kube_client: KubernetesClient,
    namespace: str,
    secret_name: str,
) -> Any:
    """Fetch the S3 credential secret used by preview and map Kubernetes API failures."""
    try:
        return await kube_client.core_v1.read_namespaced_secret(name=secret_name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            raise NotFoundException(f"Secret '{secret_name}' not found in namespace '{namespace}'") from e
        logger.error(f"Failed to read secret '{secret_name}' in namespace '{namespace}': {e}")
        raise ExternalServiceError(f"Failed to read secret '{secret_name}': {e.reason}") from e


async def _build_s3_onboard_source_env(
    kube_client: KubernetesClient,
    namespace: str,
    storage_name: str,
) -> list[AIMModelSourceEnvVar]:
    """Build model-source env bindings from S3 storage config and credentials secret."""
    secret_name, bucket_url, storage_region, access_key_name, secret_key_name = await _resolve_s3_storage_config(
        kube_client=kube_client,
        namespace=namespace,
        storage_name=storage_name,
    )
    secret = await _read_namespaced_secret_for_s3_preview(kube_client, namespace, secret_name)

    labels = secret.metadata.labels or {}
    _validate_s3_secret_use_case(secret_name, labels, context="S3 onboarding")

    data = secret.data or {}
    if access_key_name not in data:
        raise ValidationException(
            message=(
                f"Secret '{secret_name}' is missing required access key field '{access_key_name}' "
                f"configured by storage '{storage_name}'."
            )
        )
    if secret_key_name not in data:
        raise ValidationException(
            message=(
                f"Secret '{secret_name}' is missing required secret key field '{secret_key_name}' "
                f"configured by storage '{storage_name}'."
            )
        )
    access_key_field = access_key_name
    secret_key_field = secret_key_name
    endpoint = _endpoint_from_bucket_url(storage_name, bucket_url) if bucket_url else None

    env = [
        AIMModelSourceEnvVar.model_validate(
            {
                "name": "AWS_ACCESS_KEY_ID",
                "valueFrom": {"secretKeyRef": {"name": secret_name, "key": access_key_field}},
            }
        ),
        AIMModelSourceEnvVar.model_validate(
            {
                "name": "AWS_SECRET_ACCESS_KEY",
                "valueFrom": {"secretKeyRef": {"name": secret_name, "key": secret_key_field}},
            }
        ),
    ]
    resolved_endpoint = endpoint or MINIO_URL
    env.append(AIMModelSourceEnvVar.model_validate({"name": "AWS_ENDPOINT_URL", "value": resolved_endpoint}))
    region = storage_region
    if region:
        env.append(AIMModelSourceEnvVar.model_validate({"name": "AWS_DEFAULT_REGION", "value": region}))
    return env


def _build_s3_preview_client_from_secret(
    secret_name: str,
    secret: Any,
    storage_name: str,
    access_key_name: str,
    secret_key_name: str,
    storage_bucket_url: str | None,
    storage_region: str | None,
) -> MinioClient:
    """Build a Minio client from S3 storage config and secret credentials."""
    labels = secret.metadata.labels or {}
    _validate_s3_secret_use_case(secret_name, labels, context="S3 preview")

    data = secret.data or {}
    if access_key_name not in data:
        raise ValidationException(
            message=(
                f"Secret '{secret_name}' is missing required access key field '{access_key_name}' "
                f"configured by storage '{storage_name}'."
            )
        )
    if secret_key_name not in data:
        raise ValidationException(
            message=(
                f"Secret '{secret_name}' is missing required secret key field '{secret_key_name}' "
                f"configured by storage '{storage_name}'."
            )
        )
    access_key_field = access_key_name
    secret_key_field = secret_key_name
    access_key = _decode_secret_data_value(
        secret_name=secret_name,
        key_name=access_key_field,
        encoded_value=data[access_key_field],
    )
    secret_key = _decode_secret_data_value(
        secret_name=secret_name,
        key_name=secret_key_field,
        encoded_value=data[secret_key_field],
    )

    resolved_endpoint = _endpoint_from_bucket_url(storage_name, storage_bucket_url) if storage_bucket_url else MINIO_URL
    region = storage_region
    return MinioClient(
        host=resolved_endpoint,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
    )


async def _list_s3_preview_objects(
    minio_client: MinioClient,
    bucket: str,
    list_prefix: str,
    normalized: str,
    secret_name: str,
) -> list[Any]:
    """List objects under an S3 prefix and map provider errors to API-level failures."""
    try:
        return await asyncio.to_thread(
            lambda: list(minio_client.client.list_objects(bucket, prefix=list_prefix, recursive=True))
        )
    except S3Error as e:
        raise map_s3_error_to_domain_exception(
            e,
            context=f"s3 preview source '{normalized}' with secret '{secret_name}'",
        ) from e
    except Exception as e:
        raise ExternalServiceError(f"Failed to query S3 source '{normalized}': {type(e).__name__}") from e


def _build_s3_preview_siblings(
    listed_objects: list[Any],
    list_prefix: str,
    normalized: str,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Convert listed objects into sibling metadata and normalized relative paths."""
    siblings: list[dict[str, Any]] = []
    object_paths: list[str] = []
    has_prefix_marker_object = False

    for obj in listed_objects:
        object_name = getattr(obj, "object_name", "") or ""
        if not object_name.startswith(list_prefix):
            continue
        if object_name.rstrip("/") == list_prefix.rstrip("/"):
            has_prefix_marker_object = True
        relative_path = object_name[len(list_prefix) :].strip("/")
        if not relative_path:
            continue
        object_paths.append(relative_path)
        siblings.append({"rfilename": relative_path, "size": getattr(obj, "size", None)})

    if not siblings:
        if has_prefix_marker_object:
            raise ValidationException(
                message=(f"S3 source '{normalized}' is empty. No files found at the provided bucket/prefix.")
            )
        raise ValidationException(
            message=(f"S3 source '{normalized}' does not exist. Check the bucket and folder path.")
        )

    return siblings, {path.lower() for path in object_paths}


def _build_s3_preview_warnings(normalized: str, lower_paths: set[str]) -> list[str]:
    """Return non-blocking warnings describing missing or unusual S3 model layout files."""
    warnings: list[str] = []
    # Accept either source-root layout (config.json at root) or a nested
    # weights/ subtree (weights/config.json). This avoids false warnings when a
    # caller previews a previously onboarded model root directory.
    validation_paths = _expand_s3_validation_paths(lower_paths)

    missing_layout_files = [name for name in S3_EXPECTED_LAYOUT_FILES if name not in validation_paths]
    if missing_layout_files:
        missing = ", ".join(missing_layout_files)
        warnings.append(f"S3 source '{normalized}' is missing recommended file(s): {missing}.")

    if not any(tokenizer_file in validation_paths for tokenizer_file in S3_EXPECTED_TOKENIZER_FILES):
        tokenizer_candidates = " or ".join(S3_EXPECTED_TOKENIZER_FILES)
        warnings.append(f"S3 source '{normalized}' should include {tokenizer_candidates}.")

    safetensor_paths = [path for path in validation_paths if path.endswith(".safetensors")]
    if not safetensor_paths:
        warnings.append(f"S3 source '{normalized}' should include at least one '*.safetensors' weight file.")
    if len(safetensor_paths) > 1 and not any(path.endswith(".safetensors.index.json") for path in validation_paths):
        warnings.append(
            f"S3 source '{normalized}' has multiple safetensor shards but is missing a '*.safetensors.index.json' file."
        )

    return warnings


def _expand_s3_validation_paths(lower_paths: set[str]) -> set[str]:
    """Return layout-check paths including optional weights/ root normalization."""
    expanded = set(lower_paths)
    expanded.update(
        path[len("weights/") :] for path in lower_paths if path.startswith("weights/") and path != "weights/"
    )
    return expanded


def _locate_s3_model_card(listed_objects: list[Any], list_prefix: str) -> str | None:
    """Return the top-level model card's object key when present."""
    for obj in listed_objects:
        object_name = getattr(obj, "object_name", "") or ""
        if not object_name.startswith(list_prefix):
            continue
        relative_path = object_name[len(list_prefix) :].strip("/").lower()
        if relative_path == MODEL_CARD_FILENAME:
            return object_name
    return None


async def _read_s3_metadata_object(minio_client: MinioClient, bucket: str, object_name: str) -> str | None:
    """Read up to ``SOURCE_METADATA_MAX_BYTES`` of a metadata object as text, or None.

    Returns None for every failure mode — missing object, denied read, binary
    content, provider error — because tag discovery is best-effort display
    metadata and must not block preview. Failures are logged without the
    exception message because S3 errors can echo caller-supplied connection
    details.
    """

    def _read() -> bytes:
        response = None
        try:
            response = minio_client.client.get_object(bucket, object_name)
            return response.read(SOURCE_METADATA_MAX_BYTES)
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    try:
        payload = await asyncio.to_thread(_read)
    except Exception as e:
        logger.debug(f"Skipping unreadable S3 metadata during tag discovery: {type(e).__name__}")
        return None

    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        logger.debug("Skipping non-text S3 metadata during tag discovery")
        return None


async def _fetch_provenance_hub_data(repo_id: str) -> dict[str, Any] | None:
    """Fetch Hub metadata for a base model named by a source's provenance, or None.

    ``repo_id`` has already been constrained to bare ``owner/model`` form, and the
    request URL is composed from the fixed Hub API base, so this cannot be
    steered at another host. No token is attached: the provenance value comes
    from a user-controlled bucket, so presenting namespace credentials to the
    repo it names would let an uploader harvest them. That limits resolution to
    public base models, which is the intended reach.
    """
    try:
        return await _fetch_hub_model(repo_id, None, None)
    except Exception as e:
        logger.debug(f"Could not resolve base model '{repo_id}' on Hugging Face Hub: {type(e).__name__}")
        return None


async def _discover_s3_tags(
    minio_client: MinioClient,
    bucket: str,
    listed_objects: list[Any],
    list_prefix: str,
) -> DiscoveredMetadata:
    """Discover catalog tags for an S3 source from its model card and provenance.

    An object-store prefix carries no catalog metadata of its own, so tags are
    reconstructed from what the uploader left behind. Every step is best-effort;
    the worst outcome is an empty tag list rather than an error.
    """
    card_object = _locate_s3_model_card(listed_objects, list_prefix)
    raw_card = await _read_s3_metadata_object(minio_client, bucket, card_object) if card_object else None
    card = card_metadata_from_frontmatter(parse_card_frontmatter(raw_card)) if raw_card else DiscoveredMetadata()
    hub_data = await _fetch_provenance_hub_data(card.base_model) if card.base_model else None

    return resolve_discovered_tags(card=card, hub_data=hub_data)


async def _build_s3_preview_response(
    kube_client: KubernetesClient,
    namespace: str,
    source: str,
    storage_name: str,
) -> PreviewResponse:
    """Validate an S3 source + storage config and build preview metadata."""
    normalized, bucket, prefix = _normalize_s3_source(source)
    list_prefix = prefix + "/"

    secret_name, bucket_url, region, access_key_name, secret_key_name = await _resolve_s3_storage_config(
        kube_client=kube_client,
        namespace=namespace,
        storage_name=storage_name,
    )
    secret = await _read_namespaced_secret_for_s3_preview(kube_client, namespace, secret_name)
    minio_client = _build_s3_preview_client_from_secret(
        secret_name=secret_name,
        secret=secret,
        storage_name=storage_name,
        access_key_name=access_key_name,
        secret_key_name=secret_key_name,
        storage_bucket_url=bucket_url,
        storage_region=region,
    )
    listed_objects = await _list_s3_preview_objects(minio_client, bucket, list_prefix, normalized, secret_name)
    siblings, lower_paths = _build_s3_preview_siblings(listed_objects, list_prefix, normalized)
    warnings = _build_s3_preview_warnings(normalized, lower_paths)

    for warning_message in warnings:
        logger.warning(warning_message)

    display_name = prefix.rsplit("/", 1)[-1] if prefix else bucket
    if not display_name:
        display_name = "custom-model"
    all_weight_files = classify_siblings(siblings)
    weight_files = [wf for wf in all_weight_files if wf.role != "config"]
    config_files = [wf for wf in all_weight_files if wf.role == "config"]
    inferred_layout_hint = get_layout_hint(weight_files)

    discovered = await _discover_s3_tags(minio_client, bucket, listed_objects, list_prefix)

    # S3 previews do not resolve a git revision/SHA; these sentinel values keep
    # the PreviewResponse contract shape stable across source families.
    return PreviewResponse(
        source_type=CustomModelImportType.S3,
        repo_id=normalized,
        revision="s3",
        sha="s3",
        display_name=display_name,
        description="",
        tags=discovered.tags,
        pipeline_tag=discovered.pipeline_tag,
        gated=False,
        hf_token_recommended=False,
        weight_files=weight_files + config_files,
        layout_hint=inferred_layout_hint,
        warnings=warnings,
    )


async def _verify_request_matches_hub(request: OnboardRequest, token: str | None) -> None:
    """Re-fetch Hub and reject onboard when repo_id, revision, or sha no longer match preview."""
    hub_data = await _fetch_hub_model(request.repo_id, request.revision, token)
    hub_sha = hub_data.get("sha")
    if not hub_sha:
        raise ExternalServiceError(f"Hugging Face Hub did not return a SHA for '{request.repo_id}'.")
    if hub_sha != request.sha:
        raise ValidationException(
            message=(
                f"Submitted sha '{request.sha}' does not match the current Hub sha "
                f"'{hub_sha}' for '{request.repo_id}' at revision '{request.revision}'. "
                "Re-preview the model to refresh the pin."
            )
        )


def _read_import_signal(
    cr: AIMModelResource,
) -> tuple[str | None, str | None]:
    """Return ``(phase, last_error)`` from the CR's import annotations, if present.

    Nothing in this codebase writes ``IMPORT_STATE_ANNOTATION``, so this currently always
    returns ``(None, None)``.
    """
    annotations = cr.metadata.annotations or {}
    import_state = annotations.get(IMPORT_STATE_ANNOTATION)
    if import_state:
        return import_state, annotations.get(IMPORT_ERROR_ANNOTATION) or None
    return None, None


def _compose_onboard_status(
    cr: AIMModelResource,
    profile: AIMProfileResource | None,
) -> CustomModelOnboardStatus:
    """Derive the composed onboard status from the contributing signals.

    ``profile_ready`` signals that the model has at least one deployable
    AIMProfile emitted by aim-engine.  For spec.profiles derivation models
    (the current onboard contract) aim-engine does not stamp the legacy
    ``deployment-image-ref`` annotation — profile existence alongside
    AIMModel Ready is the correct readiness signal.

    Import phase/last-error come from ``_read_import_signal``.
    """
    aim_model_status = str(cr.status.status) if (cr.status and cr.status.status) else ""

    # For derived profiles (spec.profiles) aim-engine never stamps the legacy
    # deployment-image-ref annotation — profile existence is sufficient.
    profile_ready = profile is not None

    artifact_phase, artifact_last_error = _read_import_signal(cr)

    return CustomModelOnboardStatus(
        state=resolve_onboard_phase(aim_model_status, profile_ready, artifact_phase),
        status=aim_model_status,
        template_ready=profile_ready,
        artifact_phase=artifact_phase,
        artifact_last_error=artifact_last_error,
    )


def _to_custom_model_response(
    cr: AIMModelResource,
    profiles: list[CustomProfileResponse],
) -> CustomModelResponse:
    """Convert an AIMModel CR into a CustomModelResponse with composed status.

    ``profiles`` are the composed rows (Default first, matching the dedicated
    profile endpoints). The composed ``phase`` derives readiness from the Default
    row's effective AIMProfile, so a model whose only emitted profile is a named
    (non-Default) one is not reported ready. The weight-import signal is read from
    the CR's own annotations inside ``_compose_onboard_status``.
    """
    default_profile = next((row.profile for row in profiles if row.is_default), None)
    composed_status = _compose_onboard_status(cr, default_profile)

    return CustomModelResponse(
        metadata=cr.metadata,
        spec=cr.spec,
        status=cr.status,
        profiles=profiles,
        phase=composed_status,
    )


async def _create_new_custom_model_from_onboard_request(
    *,
    kube_client: KubernetesClient,
    minio_client: MinioClient,
    namespace: str,
    submitter: str,
    request: OnboardRequest,
    name_suffix: str | None,
    source_uri: str | None = None,
    base_model_name: str = AIM_BASE_MODEL_NAME,
    model_source_env: list[AIMModelSourceEnvVar] | None = None,
) -> str:
    """Create a new custom AIMModel from an onboarding payload and sync manifest."""
    slug = slugify(request.display_name)[:_RESOURCE_NAME_SLUG_MAX_LENGTH] or "custom-model"
    name_parts = [slug]
    if name_suffix:
        name_parts.append(name_suffix)
    name_parts.append(uuid4().hex[:8])
    resource_name = "-".join(name_parts)

    manifest = _build_custom_aim_model_manifest(
        namespace=namespace,
        resource_name=resource_name,
        source=request,
        source_uri=source_uri or _custom_model_weights_uri(namespace, resource_name),
        submitter=submitter,
        component_id=str(uuid4()),
        base_model_name=base_model_name,
        model_source_env=model_source_env,
    )

    await aims_gateway.create_aim_model(kube_client, namespace, manifest)
    object_key = get_custom_model_manifest_path(namespace, resource_name)
    try:
        await _sync_manifest_to_s3(minio_client, object_key, manifest)
    except Exception as s3_error:
        # S3 is a hard precondition for finalize_aim_profile_for_onboarded_model, so
        # a CR without its manifest would cause finalization to fail. Roll back the
        # CR so the caller can retry cleanly from a known-good state.
        logger.warning(
            f"Created AIMModel {resource_name} in {namespace} but S3 manifest sync failed; "
            f"rolling back CR so the operation is safe to retry. Error: {s3_error}"
        )
        try:
            await aims_gateway.delete_aim_model(kube_client, namespace, resource_name)
        except Exception as rollback_error:
            logger.warning(
                f"Failed to roll back AIMModel {resource_name} after S3 sync failure; "
                f"the CR exists without an S3 manifest and will need manual cleanup. "
                f"Error: {rollback_error}"
            )
        raise

    return resource_name


async def list_custom_models(
    kube_client: KubernetesClient,
    namespace: str,
) -> list[CustomModelResponse]:
    """Return all custom AIMModel CRs in the namespace with composed status.

    Custom models are identified by the ``MODEL_SOURCE_TYPE_LABEL=custom``
    label, which is stamped unconditionally during onboarding and used as a
    server-side label selector so the API server filters results before they
    reach the service layer.

    Profiles, profile sets, and services are bulk-fetched (namespace-wide list
    calls) and grouped in memory, so each model's profile rows compose from O(1)
    lookups with no per-model (N+1) Kubernetes calls.
    """
    custom_crs, all_profiles, all_profile_sets, all_services = await asyncio.gather(
        aims_gateway.list_aim_models(
            kube_client, namespace, label_selector=f"{MODEL_SOURCE_TYPE_LABEL}={ModelSourceType.CUSTOM}"
        ),
        list_aim_profiles(kube_client, namespace),
        aims_gateway.list_aim_profile_sets_for_model(kube_client, namespace),
        aims_gateway.list_aim_services_for_model(kube_client, namespace),
    )

    profiles_by_model: dict[str, list[AIMProfileResource]] = defaultdict(list)
    for profile in all_profiles:
        model = (profile.metadata.labels or {}).get(AIM_MODEL_LABEL_KEY)
        if model:
            profiles_by_model[model].append(profile)

    profile_sets_by_model: dict[str, list[AIMProfileSetResource]] = defaultdict(list)
    for profile_set in all_profile_sets:
        model = (profile_set.metadata.labels or {}).get(AIM_MODEL_LABEL_KEY)
        if model:
            profile_sets_by_model[model].append(profile_set)

    services_by_model: dict[str, list[AIMServiceResource]] = defaultdict(list)
    for service in all_services:
        model = service.spec.model.name if service.spec.model else None
        if model:
            services_by_model[model].append(service)

    return [
        _to_custom_model_response(
            cr,
            profiles=_profiles_for_model(
                cr,
                profile_sets_by_model.get(cr.metadata.name, []),
                profiles_by_model.get(cr.metadata.name, []),
                services_by_model.get(cr.metadata.name, []),
                raise_on_inconsistent=False,
            ),
        )
        for cr in custom_crs
    ]


async def get_custom_model(
    kube_client: KubernetesClient,
    namespace: str,
    model_name: str,
) -> CustomModelResponse:
    """Return the full detail for a single onboarded custom model.

    Loads the model CR plus everything its profile rows compose from (sets,
    profiles, services) via the shared profile context, then composes the same
    Default-first profile rows the dedicated profile endpoints return.

    Raises:
        NotFoundException: when no AIMModel with ``model_name`` exists in
            ``namespace``, or the CR exists but is not a custom model
            (missing REVISION_ANNOTATION).
        InconsistentStateException: when the model's Default AIMProfileSet
            cannot be uniquely classified (matching ``list_custom_model_profiles``).
    """
    cr, profile_sets, all_profiles, services = await _load_custom_model_profile_context(
        kube_client, namespace, model_name
    )
    profiles = _profiles_for_model(cr, profile_sets, all_profiles, services, raise_on_inconsistent=True)
    return _to_custom_model_response(cr, profiles=profiles)


def _in_use_refs_for_profiles(
    derived_profiles: list[AIMProfileResource],
    services_by_profile_name: dict[str, list[AIMServiceResource]],
) -> list[ProfileInUseRef]:
    """Deployments pinning any of a set's derived profiles, deduped by service name."""
    refs: list[ProfileInUseRef] = []
    seen: set[str] = set()
    for profile in derived_profiles:
        for service in services_by_profile_name.get(profile.metadata.name, []):
            if service.metadata.name in seen:
                continue
            seen.add(service.metadata.name)
            refs.append(
                ProfileInUseRef(
                    service_id=service.id,
                    display_name=(service.metadata.annotations or {}).get(DISPLAY_NAME_ANNOTATION)
                    or service.metadata.name,
                )
            )
    refs.sort(key=lambda ref: ref.display_name.lower())
    return refs


def _custom_profile_configuration(profile_set: AIMProfileSetResource) -> CustomProfileConfiguration:
    """Return only user-authored profile overrides from an AIMProfileSet.

    ``CustomProfileConfiguration`` is an allowlist (``extra="ignore"``): only its
    typed fields are surfaced, so server-composed identity/model-source/selector
    fields and any future engine-authored keys are dropped rather than leaked.
    modelSources in particular can carry internal storage paths and
    secret-reference names, so failing closed here is a security property, not a
    convenience.
    """
    overrides = profile_set.spec.overrides.model_dump(by_alias=True, exclude_none=True, exclude_defaults=True)
    return CustomProfileConfiguration.model_validate(overrides)


def _custom_profile_status(profile: AIMProfileResource | None) -> CustomProfileStatus:
    """Derive row status and a useful failure message from the effective profile."""
    if profile is None:
        return CustomProfileStatus()

    state = str(profile.status.status or "")
    if state == "Ready":
        return CustomProfileStatus(state=state)

    conditions = profile.status.conditions or []
    ready = next((condition for condition in conditions if condition.get("type") == "Ready"), None)
    message = str(ready.get("message") or "") if ready else ""
    return CustomProfileStatus(state=state, message=message)


def _to_custom_profile_response(
    profile_set: AIMProfileSetResource,
    *,
    is_default: bool,
    effective_profile: AIMProfileResource | None,
    in_use_by: list[ProfileInUseRef],
) -> CustomProfileResponse:
    """Map an AIMProfileSet to a single profile row, embedding its effective profile."""
    annotations = profile_set.metadata.annotations or {}
    display_name = (
        "Default" if is_default else (annotations.get(PROFILE_DISPLAY_NAME_ANNOTATION) or profile_set.metadata.name)
    )
    return CustomProfileResponse(
        name=DEFAULT_PROFILE_ALIAS if is_default else profile_set.metadata.name,
        display_name=display_name,
        is_default=is_default,
        resource_name=profile_set.metadata.name,
        created_at=profile_set.metadata.creation_timestamp,
        created_by=annotations.get(SUBMITTER_ANNOTATION),
        status=_custom_profile_status(effective_profile),
        in_use_by=in_use_by,
        selector=profile_set.spec.selector,
        custom_profile=_custom_profile_configuration(profile_set),
        profile=effective_profile,
    )


async def _load_custom_model_profile_context(
    kube_client: KubernetesClient,
    namespace: str,
    model_name: str,
) -> tuple[AIMModelResource, list[AIMProfileSetResource], list[AIMProfileResource], list[AIMServiceResource]]:
    """Fetch the model CR and everything the profile rows are composed from.

    Raises:
        NotFoundException: when ``model_name`` is not a custom model in
            ``namespace`` (so a model in another project reads as not-found
            rather than leaking another project's data).
        ExternalServiceError: when a Kubernetes read fails for a reason other
            than 404 (surfaced as 502 to match the OpenAPI contract).
    """
    try:
        cr = await aims_gateway.get_aim_model(kube_client, namespace, model_name)
    except ApiException as e:
        raise ExternalServiceError(f"Failed to read AIMModel '{model_name}': {e.reason}") from e
    if cr is None or (cr.metadata.annotations or {}).get(REVISION_ANNOTATION) is None:
        raise NotFoundException(f"Custom model '{model_name}' not found in project '{namespace}'.")

    try:
        profile_sets, all_profiles, services = await asyncio.gather(
            aims_gateway.list_aim_profile_sets_for_model(kube_client, namespace, model_name),
            list_aim_profiles(kube_client, namespace, model_name=model_name, strict=True),
            aims_gateway.list_aim_services_for_model(kube_client, namespace, model_name),
        )
    except ApiException as e:
        raise ExternalServiceError(
            f"Failed to read profiles for custom model '{model_name}' in project '{namespace}': {e.reason}"
        ) from e
    return cr, profile_sets, all_profiles, services


def _build_custom_profile_responses(
    cr: AIMModelResource,
    profile_sets: list[AIMProfileSetResource],
    all_profiles: list[AIMProfileResource],
    services: list[AIMServiceResource],
    default_set: AIMProfileSetResource,
) -> list[CustomProfileResponse]:
    """Compose profile rows, Default first, from the model's sets/profiles/services."""
    preferred_precision = (cr.metadata.annotations or {}).get(MODEL_PRECISION_ANNOTATION)

    profiles_by_set: dict[str, list[AIMProfileResource]] = defaultdict(list)
    for profile in all_profiles:
        owner = owning_profile_set_name(profile)
        if owner:
            profiles_by_set[owner].append(profile)

    services_by_profile_name: dict[str, list[AIMServiceResource]] = defaultdict(list)
    for service in services:
        pinned = service.spec.profile.name if service.spec.profile else None
        if pinned:
            services_by_profile_name[pinned].append(service)

    responses: list[CustomProfileResponse] = []
    for profile_set in profile_sets:
        is_default = profile_set.metadata.name == default_set.metadata.name
        derived = profiles_by_set.get(profile_set.metadata.name, [])
        responses.append(
            _to_custom_profile_response(
                profile_set,
                is_default=is_default,
                effective_profile=effective_profile_for_set(derived, preferred_precision),
                in_use_by=_in_use_refs_for_profiles(derived, services_by_profile_name),
            )
        )

    # Deterministic ordering: Default first, then by display name, then resource name.
    responses.sort(key=lambda r: (not r.is_default, r.display_name.lower(), r.resource_name))
    return responses


def _profiles_for_model(
    cr: AIMModelResource,
    profile_sets: list[AIMProfileSetResource],
    all_profiles: list[AIMProfileResource],
    services: list[AIMServiceResource],
    *,
    raise_on_inconsistent: bool,
) -> list[CustomProfileResponse]:
    """Compose a model's profile rows, tolerating onboarding and inconsistent states.

    Shared by the model list and detail endpoints so both surface the same rows as
    the dedicated profile endpoints. A model still onboarding (no sets yet) returns
    ``[]`` — calling ``classify_default_profile_set`` on it would 500 on the missing
    Default. When the Default cannot be uniquely classified, ``raise_on_inconsistent``
    selects the endpoint's contract: detail re-raises (500, matching
    ``list_custom_model_profiles``); the list logs and returns ``[]`` so one bad CR
    cannot fail the whole grid.
    """
    if not profile_sets:
        return []
    try:
        default_set = classify_default_profile_set(profile_sets)
    except InconsistentStateException:
        if raise_on_inconsistent:
            raise
        logger.warning(
            f"Custom model '{cr.metadata.name}' in '{cr.metadata.namespace}' has no unique Default "
            "AIMProfileSet; omitting its profiles from the model-list response."
        )
        return []
    return _build_custom_profile_responses(cr, profile_sets, all_profiles, services, default_set)


async def list_custom_model_profiles(
    kube_client: KubernetesClient,
    namespace: str,
    model_name: str,
) -> list[CustomProfileResponse]:
    """Return every profile (Default plus named) for a custom model, Default first.

    Lists AIMProfileSets so an unnarrowed Default renders as one row rather than
    its six derived profiles. Default-ness is classified by provenance on read,
    so models imported before this release list correctly with no backfill.

    Heal-on-read (intentional write on GET): named AIWB-authored sets snapshot
    identity at create, and ``spec.aimId`` on the derived AIMProfile is immutable,
    so aim-engine cannot itself reconcile a set whose parent model identity later
    drifted (an engine-side fix would remove the need for this). Until
    then this read restamps every drifted AIWB set and deletes stale, unpinned
    derived profiles so the engine recreates them. Auth already gates reads and
    writes identically, so this grants no new capability. The engine-owned
    Default is never touched.
    """
    cr, profile_sets, all_profiles, services = await _load_custom_model_profile_context(
        kube_client, namespace, model_name
    )
    profile_sets = await _restamp_aiwb_profile_set_identities(
        kube_client,
        namespace,
        cr,
        profile_sets,
        all_profiles,
        services,
    )
    default_set = classify_default_profile_set(profile_sets)
    # Eventually consistent by design: any derived profile just deleted by the
    # restamp is still present in all_profiles, so it renders one more time (as
    # Not ready) until the engine recreates it and a later read reflects it.
    # Do not refetch to "fix" this — it would add a round-trip to every read.
    return _build_custom_profile_responses(cr, profile_sets, all_profiles, services, default_set)


async def get_custom_model_profile(
    kube_client: KubernetesClient,
    namespace: str,
    model_name: str,
    profile: str,
) -> CustomProfileResponse:
    """Return a single profile by AIMProfileSet name, or the reserved literal ``default``.

    Heal-on-read is scoped to the requested set only: unlike the list endpoint
    (which heals every AIWB set), a single-profile GET must not patch or delete
    unrelated siblings. See ``list_custom_model_profiles`` for the rationale and
    the eventual-consistency note (a just-deleted derived profile renders once
    more until the engine recreates it).

    Raises:
        NotFoundException: when the model is not a custom model in ``namespace``,
            or no set with that identifier belongs to it (so a profile from
            another model or project reads as not-found).
    """
    cr, profile_sets, all_profiles, services = await _load_custom_model_profile_context(
        kube_client, namespace, model_name
    )
    default_set = classify_default_profile_set(profile_sets)

    if profile == DEFAULT_PROFILE_ALIAS:
        target: AIMProfileSetResource = default_set
    else:
        match = next((s for s in profile_sets if s.metadata.name == profile), None)
        if match is None:
            raise NotFoundException(
                f"Profile '{profile}' not found for custom model '{model_name}' in project '{namespace}'."
            )
        target = match

    target = (await _restamp_aiwb_profile_set_identities(kube_client, namespace, cr, [target], all_profiles, services))[
        0
    ]

    return _build_custom_profile_responses(cr, [target], all_profiles, services, default_set)[0]


# Upper bound on the readable display-name slug in an AIMProfileSet resource name.
# The set name is also capped as a whole (see _PROFILE_SET_NAME_MAX_LENGTH); this
# only keeps the slug from crowding out the model prefix on short model names.
_PROFILE_SET_SLUG_MAX_LENGTH = 40
_RESOURCE_NAME_HASH_LENGTH = 8

# aim-engine stamps the AIMProfileSet's full name into a label VALUE on every
# derived AIMProfile (e.g. metadata.labels["aim.eai.amd.com/profile-set..."]),
# and Kubernetes caps label values at 63 characters. A set name that the API
# server accepts as a k8s object name (limit 253) is therefore still rejected at
# reconcile time once the engine copies it into that label: the set stays
# Progressing with no derived AIMProfile, so the profile row renders blank in the
# UI. The label limit is the binding constraint on the set name, so cap there.
_K8S_LABEL_VALUE_MAX_LENGTH = 63
_PROFILE_SET_NAME_MAX_LENGTH = _K8S_LABEL_VALUE_MAX_LENGTH

# The <model>-<slug>-<hash> resource name joins its three parts with two hyphens,
# and the slug must contribute at least one character.
_RESOURCE_NAME_SEPARATOR_COUNT = 2
_MIN_PROFILE_SLUG_LENGTH = 1


# Typed narrowing axes composed into BOTH the AIMProfileSet selector and its
# overrides. Composing from one source per axis is what stops the accelerator
# count from disagreeing with the derived profile's tensor-parallel-size.
def _narrowing_axes(request: CustomProfileCreateRequest) -> dict[str, Any]:
    return {
        "acceleratorModel": request.accelerator_model,
        "acceleratorCount": request.accelerator_count,
        "precision": request.precision,
        "metric": request.metric,
    }


def _narrowing_axes_from_profile(profile: AIMProfileResource) -> dict[str, Any]:
    """Read the four narrowing axes off an AIMProfile."""
    spec = profile.spec
    return {
        "acceleratorModel": spec.accelerator_model,
        "acceleratorCount": spec.accelerator_count,
        "precision": spec.precision,
        "metric": spec.metric,
    }


_NARROWING_AXIS_KEYS = ("acceleratorModel", "acceleratorCount", "precision", "metric")


def _submitted_narrowing_axes(custom_profile: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return narrowing axes explicitly submitted by a Default edit, or None when it did not edit them."""
    if not custom_profile:
        return None
    submitted = {key: custom_profile[key] for key in _NARROWING_AXIS_KEYS if key in custom_profile}
    return submitted or None


def _selector_carries_axes(selector: ProfileSelector | None, axes: dict[str, Any]) -> bool:
    """True when ``selector`` already pins every axis to ``axes`` — the idempotency guard for a re-run."""
    if selector is None:
        return False
    current = selector.model_dump(by_alias=True, exclude_none=True)
    return all(current.get(key) == value for key, value in axes.items())


def _matching_base_profiles(base_profiles: list[AIMProfileResource], axes: dict[str, Any]) -> list[AIMProfileResource]:
    """Base-role profiles whose accelerator/precision/metric/count tuple equals ``axes``."""
    return [
        profile
        for profile in base_profiles
        if (profile.spec.accelerator_model or "") == axes["acceleratorModel"]
        and (profile.spec.precision or "") == axes["precision"]
        and (profile.spec.metric or "") == axes["metric"]
        and profile.spec.accelerator_count == axes["acceleratorCount"]
    ]


def _resolve_narrowing_base_profile(
    submitted_axes: dict[str, Any],
    base_profiles: list[AIMProfileResource],
) -> AIMProfileResource | None:
    """Resolve the submitted configuration to the one base-role profile it selects, or None."""
    if any(value in (None, "") for value in submitted_axes.values()):
        return None

    matches = [
        profile
        for profile in base_profiles
        if all(_narrowing_axes_from_profile(profile)[key] == value for key, value in submitted_axes.items())
    ]
    return matches[0] if len(matches) == 1 else None


def _derived_profiles_for_base(
    derived: list[AIMProfileResource],
    base: AIMProfileResource,
    axes: dict[str, Any],
) -> list[AIMProfileResource]:
    """Default-derived profiles that came from ``base``.

    Onboard overrides can collapse several derived profiles onto the same axes,
    so the axes alone no longer tell them apart; the engine's ``profileId`` still
    names the base profile each one was derived from. A base profile that carries
    an id with no matching derived profile yields no match (narrowing is skipped)
    rather than falling back to axes, which could pick the wrong profile.
    """
    base_id = base.spec.profile_id
    if not base_id:
        return _matching_base_profiles(derived, axes)
    return [profile for profile in derived if profile.spec.profile_id == base_id]


# Slug the engine reserves for its own auto-created Default set
# (<model>-profiles-<hash>). An AIWB set must never reproduce that pattern, so a
# display name that slugs to this value is nudged to the singular form.
_ENGINE_DEFAULT_SET_SLUG = "profiles"


def _profile_resource_slug(display_name: str) -> str:
    """Convert free-text profile names to an ASCII DNS-subdomain component.

    Case-folds before ASCII-folding so the slug is derived from the same
    normalized key as the deterministic digest (``strip().casefold()``). This
    matters for Unicode case pairs the uniqueness check treats as equal — e.g.
    ``"Straße"``/``"STRASSE"`` both fold to ``strasse`` — so every equal pair
    resolves to one ``metadata.name`` and the atomic 409 backstop cannot be
    bypassed by a slug that differs while the digest matches.
    """
    normalized = display_name.strip().casefold()
    ascii_name = unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")


def _profile_set_name_digest(model_name: str, display_name: str) -> str:
    """Deterministic short digest over the model and case-normalized display name.

    Using it as the resource-name suffix makes two creates of the same
    ``(model, case-insensitive name)`` resolve to the same ``metadata.name``, so
    the Kubernetes API server rejects the second with a 409 — an atomic backstop
    for the read-then-create window in the display-name uniqueness check. The
    full model name is hashed (not just the visible prefix) so a truncated prefix
    on an over-long model name cannot alias a different model.

    This atomic key is create-only: because the resource name is immutable, it
    reserves the *creation-time* name, not the current one. TODO: rename
    frees a display name without freeing this key, so re-creating the old name
    would collide here and read as a false duplicate — rename must reserve the
    normalized current name in a separate movable claim rather than reuse this.
    """
    normalized = f"{model_name}\x00{display_name.strip().casefold()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:_RESOURCE_NAME_HASH_LENGTH]


def _custom_profile_set_resource_name(model_name: str, display_name: str) -> str:
    """Compose a deterministic, DNS-safe AIMProfileSet name of the form ``<model>-<slug>-<hash>``.

    Prefixing the model resource name keeps AIWB-authored sets visually distinct
    from the engine's auto-created Default set (``<model>-profiles-<hash>``) in
    ``kubectl`` output and logs. The hash is derived from the model and the
    normalized display name rather than randomly, so a duplicate create collides
    on ``metadata.name`` and uniqueness is enforced atomically by the API server.
    The full model name is retained when it fits; an over-long one (an onboarded
    model's slug alone may be 200 chars) is truncated from the front so its
    terminal unique suffix (e.g. ``-import-<hash>``) is preserved, and the slug is
    shortened so the whole set name stays within the engine-safe cap that leaves
    aim-engine headroom to name the derived AIMProfiles.
    """
    digest = _profile_set_name_digest(model_name, display_name)

    # Reserve the digest, two separators, and at least one slug character. When
    # the model name cannot fit, drop its readable head rather than the terminal
    # unique suffix, which is what disambiguates otherwise-similar model names.
    max_prefix_length = (
        _PROFILE_SET_NAME_MAX_LENGTH - len(digest) - _RESOURCE_NAME_SEPARATOR_COUNT - _MIN_PROFILE_SLUG_LENGTH
    )
    if len(model_name) <= max_prefix_length:
        prefix = model_name
    else:
        prefix = model_name[len(model_name) - max_prefix_length :].lstrip("-.")

    slug_max_length = min(
        _PROFILE_SET_SLUG_MAX_LENGTH,
        _PROFILE_SET_NAME_MAX_LENGTH - len(prefix) - len(digest) - _RESOURCE_NAME_SEPARATOR_COUNT,
    )
    slug = _profile_resource_slug(display_name)[:slug_max_length].rstrip("-")
    if not slug:
        slug = "profile"[:slug_max_length] or "p"
    if slug == _ENGINE_DEFAULT_SET_SLUG:
        slug = "profile"
    return f"{prefix}-{slug}-{digest}"


def _assert_single_base_profile(base_profiles: list[AIMProfileResource], axes: dict[str, Any]) -> None:
    """Validate ``axes`` select exactly one base-role profile, else raise ValidationException.

    Shared by profile create and update: the four narrowing axes must pin a single
    base profile so the set derives one profile whose selector and overrides cannot
    disagree. Zero or multiple matches means the tuple is not one the base emits — a
    client error, reported with the emitted tuples so the caller can correct it.
    """
    matches = _matching_base_profiles(base_profiles, axes)
    if len(matches) == 1:
        return
    available = sorted(
        f"{p.spec.accelerator_model}/{p.spec.accelerator_count}x/{p.spec.precision}/{p.spec.metric}"
        for p in base_profiles
    )
    raise ValidationException(
        message=(
            f"The narrowing axes (acceleratorModel={axes['acceleratorModel']}, "
            f"acceleratorCount={axes['acceleratorCount']}, precision={axes['precision']}, "
            f"metric={axes['metric']}) resolve to {len(matches)} base profiles; exactly one is required. "
            f"Available base profiles (acceleratorModel/count/precision/metric): {available or '[none]'}."
        )
    )


def _resolve_single_base_profile(
    base_profiles: list[AIMProfileResource],
    request: CustomProfileCreateRequest,
) -> None:
    """Validate the four typed axes select exactly one base-role profile, else raise ValidationException.

    The axes must pin a single base profile so the created set derives one profile
    whose selector and overrides cannot disagree. Zero or multiple matches means the
    axes are under- or mis-specified — a client error, not an upstream failure.
    """
    _assert_single_base_profile(base_profiles, _narrowing_axes(request))


def _assert_unique_profile_display_name(
    profile_sets: list[AIMProfileSetResource],
    display_name: str,
    *,
    namespace: str,
    model_name: str,
    exclude_resource_name: str | None = None,
) -> None:
    """Reject a display name already used by another profile on the same model (case-insensitive).

    Names are compared stripped and case-folded so casing/whitespace variants of
    the same name collide. ``exclude_resource_name`` skips one set so a rename can
    re-assert uniqueness without conflicting with the set being renamed. The
    engine-owned Default carries no display-name annotation, so it never matches.
    """
    requested = display_name.strip().casefold()
    for existing_set in profile_sets:
        if exclude_resource_name is not None and existing_set.metadata.name == exclude_resource_name:
            continue
        existing_name = (existing_set.metadata.annotations or {}).get(PROFILE_DISPLAY_NAME_ANNOTATION)
        if existing_name and existing_name.strip().casefold() == requested:
            raise ConflictException(
                f"A profile named '{display_name}' already exists for custom model "
                f"'{model_name}' in project '{namespace}'."
            )


def _require_base_derivation(model: AIMModelResource, namespace: str) -> None:
    """Reject a model whose derivation cannot be narrowed into a new AIMProfileSet.

    A new set copies the model's base derivation — ``role`` plus the base-image
    ``modelRef`` — and narrows it with the request's axes. Without that pair the
    selector would carry only the axes and match base profiles the model never
    derived from, so the request is refused here rather than admitted over-broad
    or bounced back as an opaque upstream rejection.
    """
    profiles = model.spec.profiles
    selector = profiles.derived_from.selector if profiles else None
    model_ref_name = selector.model_ref.name if selector and selector.model_ref else ""
    if selector is None or not selector.role or not model_ref_name:
        raise ValidationException(
            message=(
                f"Custom model '{model.metadata.name}' in project '{namespace}' cannot take new profiles: "
                "its profile derivation is missing a role or a source model reference. Re-onboard the "
                "model to restore the derivation before adding profiles."
            )
        )


def _build_custom_profile_set_manifest(
    *,
    namespace: str,
    resource_name: str,
    model: AIMModelResource,
    request: CustomProfileCreateRequest,
    submitter: str,
) -> dict:
    """Compose an AIWB-authored AIMProfileSet that mirrors the model's derivation, narrowed to one base profile.

    The selector reuses the model's base derivation (role + base-image modelRef)
    and adds the typed axes; the overrides copy the model's identity and weights
    (so the profile is self-contained) and stamp the same typed axes plus the
    opaque customProfile. A non-controller ownerReference to the AIMModel makes the
    set cascade on model delete; the engine's Default holds the single permitted
    controller owner on its own set.
    """
    profiles = model.spec.profiles
    selector = profiles.derived_from.selector.model_dump(by_alias=True, exclude_none=True) if profiles else {}
    selector.update(_narrowing_axes(request))

    overrides_payload = build_overrides_payload(
        custom_profile=request.custom_profile,
        repo_id=extract_onboard_repo_id(model),
        image=request.image,
        model_sources=_existing_model_source_dicts_for_profile_patch(model),
    )
    overrides_payload.update(_narrowing_axes(request))

    spec: dict[str, Any] = {"selector": selector, "overrides": overrides_payload}
    if profiles and profiles.version_policy:
        spec["versionPolicy"] = profiles.version_policy

    owner_references: list[dict[str, Any]] = []
    if model.metadata.uid:
        owner_references.append(
            {
                "apiVersion": _AIM_API_VERSION_FULL,
                "kind": _AIM_MODEL_KIND,
                "name": model.metadata.name,
                "uid": model.metadata.uid,
                "controller": False,
                "blockOwnerDeletion": False,
            }
        )

    metadata = K8sMetadata(
        name=resource_name,
        namespace=namespace,
        labels={AIM_MODEL_LABEL_KEY: model.metadata.name, PROFILE_ORIGIN_LABEL: PROFILE_ORIGIN_AIWB},
        annotations={PROFILE_DISPLAY_NAME_ANNOTATION: request.display_name, SUBMITTER_ANNOTATION: submitter},
        owner_references=owner_references,
    )
    return {
        "apiVersion": _AIM_API_VERSION_FULL,
        "kind": AIM_PROFILE_SET_RESOURCE,
        "metadata": metadata.model_dump(by_alias=True, exclude_none=True),
        "spec": spec,
    }


async def create_custom_model_profile(
    kube_client: KubernetesClient,
    namespace: str,
    model_name: str,
    submitter: str,
    request: CustomProfileCreateRequest,
) -> CustomProfileResponse:
    """Create a named profile (AIMProfileSet) on an already-onboarded custom model.

    Writes an AIWB-authored AIMProfileSet whose selector is narrowed by the four
    typed axes to a single base profile, and whose overrides copy the model's
    weights and identity so the profile is self-contained and deployable on its
    own. The parent AIMModel, its Default, and any sibling profiles are untouched.

    The response is the same ``CustomProfileResponse`` shape the read endpoints
    return. The new set has no derived AIMProfile yet (aim-engine reconciles
    asynchronously), so its effective ``profile`` is null until one is emitted.

    A missing/non-custom model reads as not-found; a duplicate display name conflicts
    (case-insensitively, and atomically via the deterministic resource name so a
    concurrent create cannot slip a duplicate through); a model without derivable
    profiles or narrowing axes that do not resolve to exactly one base profile are
    rejected as invalid; upstream Kubernetes failures surface as external-service errors.
    """
    cr, profile_sets, all_profiles, services = await _load_custom_model_profile_context(
        kube_client, namespace, model_name
    )

    _assert_unique_profile_display_name(profile_sets, request.display_name, namespace=namespace, model_name=model_name)

    _require_base_derivation(cr, namespace)

    # strict=True so a real Kubernetes failure surfaces as a 502 rather than an
    # empty list that _resolve_single_base_profile would misread as a 400
    # ("zero base profiles"), which the endpoint's contract documents as 502.
    base_profiles = await list_base_role_profiles(kube_client, namespace, strict=True)
    _resolve_single_base_profile(base_profiles, request)

    # Classify the Default before mutating the cluster: an inconsistent model
    # (0 or >1 Default set) must fail with 500 here, not after create_aim_profile_set
    # has already applied a set that would then be orphaned by the error.
    default_set = classify_default_profile_set(profile_sets)

    manifest = _build_custom_profile_set_manifest(
        namespace=namespace,
        resource_name=_custom_profile_set_resource_name(cr.metadata.name, request.display_name),
        model=cr,
        request=request,
        submitter=submitter,
    )
    try:
        created = await aims_gateway.create_aim_profile_set(kube_client, namespace, manifest)
    except ConflictException as exc:
        # The pre-check and the create are not one atomic step: a concurrent
        # request for the same case-normalized name reserved the deterministic
        # resource name first, so the API server rejected this one with a 409.
        raise ConflictException(
            f"A profile named '{request.display_name}' already exists for custom model "
            f"'{model_name}' in project '{namespace}'."
        ) from exc

    return _build_custom_profile_responses(cr, [created], all_profiles, services, default_set)[0]


# Edits to the engine-owned Default land through the model-settings PATCH, not
# this per-profile route, so the caller is pointed there when they target it.
_DEFAULT_EDIT_HINT = (
    "The Default profile cannot be edited here; change it through the model settings "
    "(PATCH /v1/projects/{project}/models/{model_name})."
)


def _selector_axes(selector: ProfileSelector) -> dict[str, Any]:
    """Read the four narrowing axes off an AIMProfileSet selector (they ride as ``extra`` fields)."""
    dumped = selector.model_dump(by_alias=True, exclude_none=True)
    return {key: dumped.get(key) for key in _NARROWING_AXIS_KEYS}


def _effective_narrowing_axes(target: AIMProfileSetResource, request: CustomProfilePatchRequest) -> dict[str, Any]:
    """Overlay the request's supplied axes onto the set's current selector axes.

    A configuration change rewrites selector and overrides together from one
    axis set, so an unedited axis is carried over from the set rather than
    dropped — otherwise a partial edit (e.g. image only) would empty the axes.
    """
    current = _selector_axes(target.spec.selector)
    return {
        "acceleratorModel": request.accelerator_model or current["acceleratorModel"],
        "acceleratorCount": request.accelerator_count or current["acceleratorCount"],
        "precision": request.precision or current["precision"],
        "metric": request.metric or current["metric"],
    }


def _assert_profile_set_not_in_use(
    target: AIMProfileSetResource,
    derived_profiles: list[AIMProfileResource],
    services: list[AIMServiceResource],
) -> None:
    """Refuse an edit while any deployment pins one of the set's derived profiles.

    Blocking any modification while a workload references the profile is the
    agreed simplification: rather than reason about a live deployment when the
    profile beneath it changes, the operation is refused (nothing is written)
    and the response names the blocking deployments, mirroring the model-delete
    guard. Matches AIMServices on ``spec.profile.name``.
    """
    derived_names = {profile.metadata.name for profile in derived_profiles if profile.metadata.name}
    blocking = _services_pinning_profiles(services, derived_names)
    if not blocking:
        return
    display_name = (target.metadata.annotations or {}).get(PROFILE_DISPLAY_NAME_ANNOTATION) or target.metadata.name
    blocking_services = [
        ProfileInUseRef(
            service_id=service.id,
            display_name=(service.metadata.annotations or {}).get(DISPLAY_NAME_ANNOTATION) or service.metadata.name,
        ).model_dump(by_alias=True)
        for service in blocking
    ]
    raise ConflictException(
        f"Profile '{display_name}' is in use by {len(blocking)} deployment(s) and cannot be modified or deleted.",
        detail={"blockingServices": blocking_services},
    )


async def _assert_profile_set_not_in_use_before_write(
    kube_client: KubernetesClient,
    namespace: str,
    model_name: str,
    target: AIMProfileSetResource,
) -> None:
    """Re-read derived profiles and deployments, then refuse if the set is pinned.

    Must run inside ``manifest_write_lock`` immediately before the cluster write
    (patch or delete) so a deployment created after the endpoint's initial check
    cannot pin the profile in the local check-to-write window. Kubernetes cannot
    atomically read AIMServices and mutate an AIMProfileSet, but keeping both
    inside this lock minimizes that window — the same rationale as
    ``patch_onboarded_model``'s Default-narrowing guard.
    """
    try:
        all_profiles, services = await asyncio.gather(
            list_aim_profiles(kube_client, namespace, model_name=model_name, strict=True),
            aims_gateway.list_aim_services_for_model(kube_client, namespace, model_name),
        )
    except ApiException as e:
        raise ExternalServiceError(
            f"Failed to read deployments for custom model '{model_name}' in project '{namespace}': {e.reason}"
        ) from e
    derived_profiles = profiles_derived_from_set(all_profiles, target.metadata.name)
    _assert_profile_set_not_in_use(target, derived_profiles, services)


async def _compose_profile_config_patch(
    kube_client: KubernetesClient,
    namespace: str,
    model: AIMModelResource,
    target: AIMProfileSetResource,
    request: CustomProfilePatchRequest,
) -> dict[str, Any]:
    """Compose the AIMProfileSet ``spec`` patch for a configuration edit.

    Rebuilds selector and overrides from one axis set so the accelerator count
    cannot drift apart from the derived profile's tensor-parallel-size. The axes
    must still resolve to exactly one base profile (else 400); weights and
    identity are carried verbatim from the parent model so the profile stays
    self-contained. Opaque overrides use merge-patch semantics: an omitted key is
    left unchanged, and a dropped ``engineArgs``/``engineEnv`` map key is
    tombstoned so it is actually deleted.
    """
    _require_base_derivation(model, namespace)
    effective_axes = _effective_narrowing_axes(target, request)

    base_profiles = await list_base_role_profiles(kube_client, namespace, strict=True)
    _assert_single_base_profile(base_profiles, effective_axes)

    effective_image = request.image or target.spec.overrides.image or extract_overrides_image(model)
    if not effective_image:
        raise ValidationException(
            message=(
                "Cannot edit the profile configuration without a container image: none was supplied "
                "and the profile has no existing image override."
            )
        )

    submitted_custom_profile: dict[str, Any] | None = None
    if request.custom_profile is not None:
        submitted_custom_profile = request.custom_profile.model_dump(by_alias=True, exclude_unset=True)
        existing_overrides = target.spec.overrides.model_dump(by_alias=True, exclude_none=True)
        submitted_custom_profile = _tombstone_removed_map_keys(submitted_custom_profile, existing_overrides)

    profiles = model.spec.profiles
    selector = profiles.derived_from.selector.model_dump(by_alias=True, exclude_none=True) if profiles else {}
    selector.update(effective_axes)

    overrides_payload = build_overrides_payload(
        custom_profile=submitted_custom_profile,
        repo_id=extract_onboard_repo_id(model),
        image=effective_image,
        model_sources=_existing_model_source_dicts_for_profile_patch(model),
    )
    overrides_payload.update(effective_axes)
    return {"selector": selector, "overrides": overrides_payload}


async def update_custom_model_profile(
    kube_client: KubernetesClient,
    minio_client: MinioClient,
    namespace: str,
    model_name: str,
    profile: str,
    request: CustomProfilePatchRequest,
) -> CustomProfileResponse:
    """Update a named custom-model profile's display name, configuration, or both.

    A rename rewrites only the display-name annotation — Kubernetes object names
    are immutable, so the AIMProfileSet resource name is untouched. A
    configuration change rebuilds ``spec.selector`` and ``spec.overrides``
    together (see :func:`_compose_profile_config_patch`). Both may be combined in
    one merge-patch, and the S3 mirror is refreshed under the manifest write lock
    so the durable record never inverts relative to the authoritative CR.

    The edit is refused (nothing written) while any deployment pins the profile,
    with a 409 naming the blocking deployments. The deployment check is
    re-evaluated inside ``manifest_write_lock`` immediately before the cluster
    patch so a workload cannot pin the profile in the local check-to-write gap.
    The engine-owned Default is not editable here — the reserved ``default`` alias
    and the classified Default set are both refused with a 422 pointing at the
    model-settings route.

    Raises:
        ValidationException: empty request body, an attempt to edit the Default,
            or axes that do not resolve to exactly one base profile.
        NotFoundException: the model is not a custom model in ``namespace``, or no
            set with that resource name belongs to it.
        ConflictException: a deployment references the profile, or the new display
            name is already used by a sibling profile.
    """
    if profile == DEFAULT_PROFILE_ALIAS:
        raise ValidationException(message=_DEFAULT_EDIT_HINT)

    updates = request.model_dump(exclude_unset=True)
    if not updates:
        raise ValidationException(
            message=(
                "At least one of displayName, acceleratorModel, acceleratorCount, precision, metric, image, "
                "or customProfile must be provided."
            )
        )

    cr, profile_sets, all_profiles, services = await _load_custom_model_profile_context(
        kube_client, namespace, model_name
    )
    default_set = classify_default_profile_set(profile_sets)

    target = next((s for s in profile_sets if s.metadata.name == profile), None)
    if target is None:
        raise NotFoundException(
            f"Profile '{profile}' not found for custom model '{model_name}' in project '{namespace}'."
        )
    if target.metadata.name == default_set.metadata.name:
        raise ValidationException(message=_DEFAULT_EDIT_HINT)

    rename = "display_name" in updates
    config_fields = ("accelerator_model", "accelerator_count", "precision", "metric", "image", "custom_profile")
    config_edit = any(key in updates for key in config_fields)

    patch_body: dict[str, Any] = {}
    if rename:
        new_display_name = request.display_name
        if new_display_name is None:
            raise ValidationException(message="displayName must be provided.")
        _assert_unique_profile_display_name(
            profile_sets,
            new_display_name,
            namespace=namespace,
            model_name=model_name,
            exclude_resource_name=target.metadata.name,
        )
        patch_body.setdefault("metadata", {}).setdefault("annotations", {})[PROFILE_DISPLAY_NAME_ANNOTATION] = (
            new_display_name
        )
    if config_edit:
        patch_body["spec"] = await _compose_profile_config_patch(kube_client, namespace, cr, target, request)

    object_key = get_custom_model_manifest_path(namespace, model_name)
    async with manifest_write_lock(MINIO_BUCKET, object_key):
        await _assert_profile_set_not_in_use_before_write(kube_client, namespace, model_name, target)
        patched = await aims_gateway.patch_aim_profile_set(kube_client, namespace, target.metadata.name, patch_body)
        try:
            await _upsert_manifest_documents_to_s3_unlocked(
                minio_client, object_key, [_profile_set_to_manifest_document(patched)]
            )
        except Exception as s3_error:
            logger.warning(
                f"Patched AIMProfileSet {target.metadata.name} in {namespace} but S3 mirror sync failed; "
                f"the CR is authoritative and a subsequent patch will re-sync. Error: {s3_error}"
            )

    logger.info(
        f"Updated custom-model profile {target.metadata.name} in namespace {namespace} "
        f"(rename={rename}, config={config_edit})"
    )
    return _build_custom_profile_responses(cr, [patched], all_profiles, services, default_set)[0]


class DefaultProfileImmutableError(ValidationException):
    """A delete targeted the engine-owned Default profile set.

    The delete route catches this and answers 422 rather than the 400 a plain
    ``ValidationException`` yields, because the Default is reconciled from the
    AIMModel and removed only when the model is deleted — an unprocessable
    request rather than a malformed one. Subclassing ``ValidationException``
    keeps the shared 400 handler as the fallback: no registered handler maps to
    422, so deriving straight from ``BaseApiException`` would turn an uncaught
    raise into a 500. Raised for both spellings of the Default: the literal
    ``default`` alias and the engine set addressed by its own resource name.
    """


async def delete_custom_model_profile(
    kube_client: KubernetesClient,
    minio_client: MinioClient,
    namespace: str,
    model_name: str,
    profile: str,
) -> None:
    """Delete a named profile (AIMProfileSet) from an onboarded custom model.

    Removes the AIWB-authored AIMProfileSet; aim-engine garbage-collects the
    AIMProfile derived from it via the set's owner reference. Sibling profiles
    and the model itself are untouched.

    The engine-owned Default cannot be deleted — the AIMModel controller
    reconciles it from ``spec.profiles`` so a delete would either be recreated
    or strip the model of its derivation. This is refused whether the caller
    addresses the Default by the literal ``default`` or by the engine set's own
    resource name, so a client that read ``resourceName`` off the list response
    cannot route around the guard.

    Deletion is refused while a live AIMService pins one of the set's derived
    profiles, so a running workload never loses the profile it deployed. The
    deployment check is re-evaluated inside ``manifest_write_lock`` immediately
    before the cluster delete so a workload cannot pin the profile in the local
    check-to-write gap, mirroring :func:`update_custom_model_profile`.

    An already-deleted profile reads as not-found rather than succeeding
    silently, matching the model-delete convention.

    After the cluster delete, the derived profile's mirror document is dropped
    from the durable S3 manifest. The cluster delete is authoritative: an S3
    failure is logged rather than failing the request, matching
    :func:`delete_onboarded_model`.
    """
    if profile == DEFAULT_PROFILE_ALIAS:
        raise DefaultProfileImmutableError(
            message=(
                f"The Default profile of custom model '{model_name}' cannot be deleted; "
                "it is reconciled from the model and is removed only when the model is deleted."
            )
        )

    _cr, profile_sets, all_profiles, services = await _load_custom_model_profile_context(
        kube_client, namespace, model_name
    )

    target = next((s for s in profile_sets if s.metadata.name == profile), None)
    if target is None:
        raise NotFoundException(
            f"Profile '{profile}' not found for custom model '{model_name}' in project '{namespace}'."
        )

    if is_default_profile_set(target):
        raise DefaultProfileImmutableError(
            message=(
                f"The Default profile of custom model '{model_name}' cannot be deleted; "
                "it is reconciled from the model and is removed only when the model is deleted."
            )
        )

    derived = profiles_derived_from_set(all_profiles, target.metadata.name)
    derived_names = {p.metadata.name for p in derived if p.metadata.name}
    _assert_profile_set_not_in_use(target, derived, services)

    object_key = get_custom_model_manifest_path(namespace, model_name)
    async with manifest_write_lock(MINIO_BUCKET, object_key):
        await _assert_profile_set_not_in_use_before_write(kube_client, namespace, model_name, target)
        await aims_gateway.delete_aim_profile_set(kube_client, namespace, target.metadata.name)

        if derived_names:
            identities = {("AIMProfile", name) for name in derived_names}
            try:
                existing = await read_manifest_from_s3(minio_client, MINIO_BUCKET, object_key)
                remaining = remove_manifest_documents(existing, identities)
                if len(remaining) != len(existing):
                    if remaining:
                        await write_manifest_to_s3(minio_client, MINIO_BUCKET, object_key, remaining)
                    else:
                        # The AIMModel scaffold normally survives and keeps the
                        # manifest non-empty, but a blob hand-edited or partially
                        # written by an older version can hold nothing but the
                        # dropped profile. An empty manifest cannot be
                        # serialized, so removing the object is the only way to
                        # clear the stale document.
                        await delete_manifest_from_s3(minio_client, MINIO_BUCKET, object_key)
            except Exception as s3_error:
                logger.warning(
                    f"Deleted AIMProfileSet {target.metadata.name} for {model_name} in {namespace} but S3 mirror "
                    f"refresh failed; the CRs are authoritative and a subsequent write will re-sync. Error: {s3_error}"
                )
                return

    logger.info(f"Deleted custom profile {target.metadata.name} for model {model_name} in namespace {namespace}")


async def get_base_runtime_profile_options(
    kube_client: KubernetesClient,
    namespace: str,
) -> RuntimeProfileOptions:
    """Return the runtime options a custom model will support in this namespace.

    Derived from the base-image model's base-role AIMProfiles: a BYOM model
    inherits exactly that runtime matrix, so onboarding should offer (and
    preset) these accelerator/precision/count/optimization values rather than a
    free-form precision the AIMModel CRD silently prunes. Returns empty lists
    when the base model has not emitted profiles yet, so the client can fall
    back to static defaults.
    """
    profiles = await list_base_role_profiles(kube_client, namespace)

    accelerator_models: set[str] = set()
    precisions: set[str] = set()
    accelerator_counts: set[int] = set()
    optimization_classes: set[str] = set()
    metrics: set[str] = set()
    # Count base profiles per four-axis tuple so we can drop any tuple that more
    # than one base profile matches: create/update require the axes to resolve to
    # exactly one base profile (``_assert_single_base_profile``), so advertising an
    # ambiguous tuple (e.g. two profiles differing only by optimization ``type``)
    # would let the form submit a combination the API then rejects with a 400.
    combination_counts: Counter[tuple[str, int, str, str]] = Counter()
    for profile in profiles:
        spec = profile.spec
        if spec.accelerator_model:
            accelerator_models.add(spec.accelerator_model)
        if spec.precision:
            precisions.add(spec.precision)
        if spec.accelerator_count is not None and spec.accelerator_count > 0:
            accelerator_counts.add(spec.accelerator_count)
        if spec.type:
            optimization_classes.add(spec.type)
        if spec.metric:
            metrics.add(spec.metric)
        # A combination needs all four narrowing axes; a profile missing any of
        # them can never be resolved by create/update, so it is not offered.
        if (
            spec.accelerator_model
            and spec.precision
            and spec.metric
            and spec.accelerator_count
            and (spec.accelerator_count > 0)
        ):
            combination_counts[(spec.accelerator_model, spec.accelerator_count, spec.precision, spec.metric)] += 1

    sorted_combinations = [
        RuntimeProfileCombination(accelerator_model=model, accelerator_count=count, precision=precision, metric=metric)
        for (model, count, precision, metric), cardinality in sorted(combination_counts.items())
        if cardinality == 1
    ]
    return RuntimeProfileOptions(
        accelerator_models=sorted(accelerator_models),
        precisions=sorted(precisions),
        accelerator_counts=sorted(accelerator_counts),
        optimization_classes=sorted(optimization_classes),
        metrics=sorted(metrics),
        combinations=sorted_combinations,
        # The base has emitted profiles even when none resolves to a single tuple
        # (all ambiguous or incomplete); the client uses this to block the save
        # instead of falling back to the per-axis lists.
        profiles_available=bool(profiles),
    )


async def copy_custom_model(
    kube_client: KubernetesClient,
    minio_client: MinioClient,
    namespace: str,
    source_model_name: str,
    submitter: str,
) -> None:
    """Copy an onboarded custom model into a new model in the same project."""
    source = await aims_gateway.get_aim_model(kube_client, namespace, source_model_name)
    source_labels = (source.metadata.labels if source is not None else None) or {}
    is_custom_model = source_labels.get(MODEL_SOURCE_TYPE_LABEL) == ModelSourceType.CUSTOM
    source_annotations = (source.metadata.annotations if source is not None else None) or {}
    has_onboard_stamps = (
        source_annotations.get(REVISION_ANNOTATION) is not None
        and source_annotations.get(SOURCE_SHA_ANNOTATION) is not None
    )
    if source is None or not is_custom_model or not has_onboard_stamps:
        raise NotFoundException(f"Custom model '{source_model_name}' not found in project '{namespace}'.")

    custom_crs = await aims_gateway.list_aim_models(
        kube_client,
        namespace,
        label_selector=f"{MODEL_SOURCE_TYPE_LABEL}={ModelSourceType.CUSTOM}",
    )
    source_display_name = resolve_custom_model_display_name(source)
    existing_display_names = {resolve_custom_model_display_name(cr) for cr in custom_crs}
    copy_display_name = next_copy_display_name(source_display_name, existing_display_names)
    copy_request = build_copy_onboard_request(source, copy_display_name)
    source_uri = (source.metadata.annotations or {}).get(SOURCE_URI_ANNOTATION)
    base_model_name = await ensure_namespace_aim_base_model(
        kube_client,
        namespace,
        image_ref=copy_request.image,
    )
    await _create_new_custom_model_from_onboard_request(
        kube_client=kube_client,
        minio_client=minio_client,
        namespace=namespace,
        submitter=submitter,
        request=copy_request,
        name_suffix=None,
        source_uri=source_uri,
        base_model_name=base_model_name,
    )


async def _resolve_asr_axis_defaults(
    kube_client: KubernetesClient, namespace: str, base_model_name: str
) -> dict[str, Any]:
    """Identity-axis values the audio base model's profiles unanimously agree on.

    Only an axis whose base profiles all carry the same value is safe to stamp;
    an axis with several candidates has no single right answer at onboard time,
    and leaving it unset lets each derived copy keep its source profile's value.

    Scoped to ``base_model_name`` because a namespace holds one base model per
    image family: an earlier chat onboard leaves ``aim-base`` behind, so reading
    every base-role profile would stamp the chat image's precision — and through
    it the vLLM dtype — onto a speech model derived from the audio image.
    """
    # strict=True so a real Kubernetes failure surfaces as a 502 rather than an
    # empty list, which is indistinguishable from "this namespace legitimately
    # has no base profiles yet" and would silently drop the dtype this resolves.
    profiles = await list_base_role_profiles(kube_client, namespace, model_name=base_model_name, strict=True)
    defaults: dict[str, Any] = {}
    for axis in ASR_IDENTITY_AXES:
        values = {value for value in (getattr(profile.spec, axis, None) for profile in profiles) if value}
        if len(values) == 1:
            defaults[axis] = values.pop()
    return defaults


def _assert_asr_runtime_supported(request: OnboardRequest) -> None:
    """Reject a speech model whose selected base image cannot serve audio.

    Such a model would deploy and report healthy, then fail every transcription
    call because the image lacks the runtime vLLM decodes audio with. Both
    inputs are on the request, so this runs at the service boundary — before the
    Hub re-verify and before any base model is provisioned — and a rejected
    request leaves nothing behind.
    """
    if not is_asr_source(request.tags):
        return
    if is_audio_capable_base_image(request.image):
        return
    try:
        parse_container_image_repository_and_tag(request.image)
    except ValueError:
        # A reference we cannot parse is not an audio problem, and blaming the
        # audio runtime would send the user looking for a different image when
        # the one they picked is malformed. Leave it to the runtime-family
        # validation downstream, which names the actual fault.
        return
    raise ValidationException(
        f"'{request.repo_id}' is a speech-to-text model and needs a runtime image that includes "
        f"the audio runtime, which '{request.image}' does not. Select an audio-capable runtime "
        "image and onboard again."
    )


async def _apply_asr_onboard_preset(
    kube_client: KubernetesClient,
    namespace: str,
    request: OnboardRequest,
    base_model_name: str,
) -> OnboardRequest:
    """Stamp the speech-to-text runtime preset onto an ASR onboard request.

    Non-speech sources pass through untouched. The base image is known to be
    audio-capable by now: ``_assert_asr_runtime_supported`` rejects the
    alternative at the service boundary.
    """
    if not is_asr_source(request.tags):
        return request

    axis_defaults = await _resolve_asr_axis_defaults(kube_client, namespace, base_model_name)
    custom_profile = apply_asr_preset(request.custom_profile, axis_defaults)
    logger.info(
        f"Onboarding '{request.repo_id}' as speech-to-text on image {request.image}; "
        f"stamped identity axes {axis_defaults} and ASR engine args."
    )
    return request.model_copy(update={"custom_profile": custom_profile})


async def onboard_custom_model_source(
    kube_client: KubernetesClient,
    minio_client: MinioClient,
    namespace: str,
    submitter: str,
    request: OnboardRequest,
) -> None:
    """Upsert the AIMModel CR + S3 manifest for a previewed source.

    Conflict key is (sanitized display name, canonical repo id) within the
    namespace. For HuggingFace sources the canonical repo id is the HF repo
    path; for S3 sources it is the full ``s3://bucket/prefix`` URI entered by
    the user (stored in ``CANONICAL_REPO_ID_ANNOTATION`` on the CR).
    A same-name request pointing at a different source raises ConflictException
    so the FE prompts for a new name. Re-submitting the same form, including the
    same runtime image, is idempotent. A different tag of a family already
    provisioned in the project raises ConflictException instead of repointing
    the shared base-model CR.

    Ordering: the AIMModel CR is the source of truth; the S3 manifest is a DR
    mirror. We write k8s first, then S3. On the **create** path, an S3 failure
    rolls back the CR so the next call retries from a clean slate. On the
    **patch** path the CR is preserved as the authority; the next call re-syncs
    the mirror.

    Once the CR and manifest are in place, HuggingFace sources keep an
    ``hf://owner/model`` sourceUri and optional ``HF_TOKEN`` env on the
    model source so aim-engine downloads directly. S3 sources keep their external
    sourceUri and provide access credentials so runtime can fetch directly.
    """
    # Speech models need an audio-capable runtime. The check reads only the
    # request, so it runs before the Hub call and before any CR is provisioned:
    # a rejected onboard must not leave a base model behind.
    _assert_asr_runtime_supported(request)

    is_hf_source = request.source_type == CustomModelImportType.HUGGING_FACE
    token: str | None = None
    source_uri: str | None = None
    model_source_env: list[AIMModelSourceEnvVar] | None = None

    if is_hf_source:
        validate_hf_repo_id(request.repo_id)
        source_uri = f"hf://{request.repo_id}"

        # Resolve the HF token once: it authorizes both the Hub re-verify below and
        # the eventual model-source env wiring.
        token = (
            await _get_hf_token(kube_client, namespace, request.hf_token_secret_name)
            if request.hf_token_secret_name
            else None
        )

        await _verify_request_matches_hub(request, token)
    else:
        # Re-run the same S3 hard-validation path used by preview and proceed
        # even if warnings were emitted.
        if not request.s3_storage_name:
            raise ValidationException("s3StorageName is required when sourceType is 's3'.")
        await _build_s3_preview_response(
            kube_client=kube_client,
            namespace=namespace,
            source=request.repo_id,
            storage_name=request.s3_storage_name,
        )
        source_uri = request.repo_id
        model_source_env = await _build_s3_onboard_source_env(
            kube_client=kube_client,
            namespace=namespace,
            storage_name=request.s3_storage_name,
        )
    display_label_value = sanitize_label_value(request.display_name)

    selector = f"{MODEL_NAME_LABEL}={display_label_value},{MODEL_SOURCE_TYPE_LABEL}={ModelSourceType.CUSTOM}"
    existing = await aims_gateway.find_aim_model_by_label(kube_client, namespace, selector)

    if existing is not None:
        existing_repo_id = extract_onboard_repo_id(existing)
        if existing_repo_id != request.repo_id:
            raise ConflictException(
                f"A custom model named '{request.display_name}' already exists in namespace '{namespace}' with a different source."
            )

    base_model_name = await ensure_namespace_aim_base_model(
        kube_client,
        namespace,
        image_ref=request.image,
    )

    # Runs after the base model exists so any base profiles aim-engine has
    # already emitted for it are visible. Both the create and re-onboard
    # branches below build their manifest from `request`.
    request = await _apply_asr_onboard_preset(kube_client, namespace, request, base_model_name)

    if existing is not None:
        resource_name = existing.metadata.name
        existing_annotations = existing.metadata.annotations or {}
        component_id = existing_annotations.get(COMPONENT_ID_ANNOTATION) or str(uuid4())
        manifest = _build_custom_aim_model_manifest(
            namespace=namespace,
            resource_name=resource_name,
            source=request,
            source_uri=source_uri or _custom_model_weights_uri(namespace, resource_name),
            submitter=submitter,
            component_id=component_id,
            base_model_name=base_model_name,
            model_source_env=model_source_env,
        )
        patch_body = {
            "metadata": {
                "labels": manifest["metadata"].get("labels", {}),
                "annotations": manifest["metadata"].get("annotations", {}),
            },
            "spec": manifest["spec"],
        }
        await aims_gateway.patch_aim_model(kube_client, namespace, resource_name, patch_body)
        object_key = get_custom_model_manifest_path(namespace, resource_name)
        try:
            await _sync_manifest_to_s3(minio_client, object_key, manifest)
        except Exception as s3_error:
            logger.warning(
                f"Patched AIMModel {resource_name} in {namespace} but S3 mirror sync failed; "
                f"the CR is authoritative and a retry may re-sync the manifest. Error: {s3_error}"
            )
            raise
        logger.info(f"Patched existing custom AIMModel {resource_name} in namespace {namespace}")
        return

    resource_name = await _create_new_custom_model_from_onboard_request(
        kube_client=kube_client,
        minio_client=minio_client,
        namespace=namespace,
        submitter=submitter,
        request=request,
        name_suffix="import",
        source_uri=source_uri,
        base_model_name=base_model_name,
        model_source_env=model_source_env,
    )

    logger.info(f"Created custom AIMModel {resource_name} in namespace {namespace}")


async def delete_onboarded_model(
    kube_client: KubernetesClient,
    minio_client: MinioClient,
    namespace: str,
    name: str,
) -> None:
    """Delete an onboarded custom model: the AIMModel CR and its S3 object tree.

    Safety guard: if any AIMService in the namespace references this AIMModel,
    the deletion is refused with a ConflictException naming the blocking
    services so the caller can tear those deployments down first.

    Responsibility boundary: AIWB owns only the AIMModel CR and the
    namespace-scoped S3 tree rooted at this model path. For newly onboarded
    Hugging Face models, that tree is expected to contain the onboarding
    manifest (not staged weights). Legacy onboarded models may still have
    imported weight objects under the same prefix, so cleanup still sweeps the
    full tree. The derived AIMProfileSet / AIMProfile are owner-referenced by
    the AIMModel and garbage-collected by aim-engine via Kubernetes owner
    references — AIWB never deletes them.
    Profile caches and artifacts are tied to AIMService lifecycle and
    aim-engine's reuse semantics, so they are not touched here either.

    Ordering: delete the CR first (the live intent), then sweep the S3 tree.
    An S3 failure after a successful CR delete is logged as a recoverable
    warning and does not fail the request — the live record is already gone
    and orphaned objects can be reclaimed out-of-band.

    Raises:
        NotFoundException: when no AIMModel named ``name`` exists in
            ``namespace``, or the CR exists but is not a custom onboarded model.
        ConflictException: when one or more AIMServices still reference the model.
        ExternalServiceError: when a Kubernetes API call fails for any reason
            other than a 404 (surfaced as 502 to match the OpenAPI contract).
    """
    try:
        cr = await aims_gateway.get_aim_model(kube_client, namespace, name)
    except ApiException as e:
        logger.error(f"Failed to read AIMModel {name} in namespace {namespace}: {e}")
        raise ExternalServiceError(f"Failed to read AIMModel '{name}': {e.reason}") from e
    if cr is None or (cr.metadata.annotations or {}).get(REVISION_ANNOTATION) is None:
        raise NotFoundException(f"Custom model '{name}' not found in project '{namespace}'.")

    try:
        blocking = await aims_gateway.list_aim_services_for_model(kube_client, namespace, name)
    except ApiException as e:
        logger.error(f"Failed to list AIMServices referencing {name} in namespace {namespace}: {e}")
        raise ExternalServiceError(f"Failed to check active deployments for '{name}': {e.reason}") from e
    if blocking:
        blocking_names = ", ".join(sorted(service.metadata.name for service in blocking))
        raise ConflictException(
            f"Custom model '{name}' cannot be deleted while {len(blocking)} AIMService(s) "
            f"reference it: {blocking_names}. Delete those deployments first."
        )

    try:
        await aims_gateway.delete_aim_model(kube_client, namespace, name)
    except ApiException as e:
        logger.error(f"Failed to delete AIMModel {name} in namespace {namespace}: {e}")
        raise ExternalServiceError(f"Failed to delete AIMModel '{name}': {e.reason}") from e

    root_prefix = get_custom_model_root_path(namespace, name)
    try:
        await delete_from_s3(root_prefix, minio_client, name)
    except Exception as s3_error:
        logger.warning(
            f"Deleted AIMModel {name} in {namespace} but S3 cleanup at '{root_prefix}' failed; "
            f"the live record is gone and the orphaned objects can be reclaimed out-of-band. "
            f"Error: {s3_error}"
        )
        return

    logger.info(f"Deleted custom AIMModel {name} and S3 tree '{root_prefix}' in namespace {namespace}")


async def preview_model_source(
    kube_client: KubernetesClient,
    namespace: str,
    request: PreviewRequest,
) -> PreviewResponse:
    if request.source_type == CustomModelImportType.S3:
        if not request.s3_storage_name:
            raise ValidationException("s3StorageName is required when sourceType is 's3'.")
        return await _build_s3_preview_response(
            kube_client=kube_client,
            namespace=namespace,
            source=request.source,
            storage_name=request.s3_storage_name,
        )

    repo_id, source_revision = normalize_hf_source(request.source)

    token: str | None = None
    if request.hf_token_secret_name:
        token = await _get_hf_token(kube_client, namespace, request.hf_token_secret_name)

    hub_data = await _fetch_hub_model(repo_id, source_revision, token)

    if hub_data.get("gated") and not token:
        raise ForbiddenException(
            f"Model '{repo_id}' is a gated repository. "
            "Provide a Hugging Face token via 'hfTokenSecretName' to access it."
        )

    siblings: list[dict] = hub_data.get("siblings") or []
    all_weight_files = classify_siblings(siblings)
    weight_files = [wf for wf in all_weight_files if wf.role != "config"]
    config_files = [wf for wf in all_weight_files if wf.role == "config"]

    gated_value = hub_data.get("gated", False)
    gated = bool(gated_value)
    hf_token_recommended = gated or bool(hub_data.get("private", False))

    sha = hub_data.get("sha")
    if not sha:
        logger.error(
            "Hub returned 200 without a SHA for {} (revision={}). Response keys: {}",
            repo_id,
            source_revision,
            sorted(hub_data.keys()),
        )
        raise ExternalServiceError(f"Hugging Face Hub did not return a SHA for '{repo_id}'.")

    resolved_revision = source_revision or sha
    display_name = build_display_name(hub_data, repo_id)
    description = build_description(hub_data)
    canonical_repo_id = hub_data.get("id") or repo_id
    return PreviewResponse(
        source_type=CustomModelImportType.HUGGING_FACE,
        repo_id=canonical_repo_id,
        revision=resolved_revision,
        sha=sha,
        display_name=display_name,
        description=description,
        tags=hub_data.get("tags") or [],
        pipeline_tag=hub_data.get("pipeline_tag"),
        gated=gated,
        hf_token_recommended=hf_token_recommended,
        weight_files=weight_files + config_files,
        layout_hint=get_layout_hint(weight_files),
    )


def _profile_resource_to_manifest_document(profile: AIMProfileResource) -> ManifestDocument:
    """Render an AIMProfile as a re-applicable manifest doc, stripping server-owned status and metadata fields."""

    document = profile.model_dump(
        by_alias=True,
        exclude_none=True,
        exclude={
            "status": True,
            "metadata": {"uid", "creation_timestamp", "owner_references"},
        },
    )
    return {
        "apiVersion": _AIM_API_VERSION_FULL,
        "kind": _AIM_PROFILE_KIND,
        **document,
    }


def _profile_set_to_manifest_document(profile_set: AIMProfileSetResource) -> ManifestDocument:
    """Render an AIMProfileSet as a re-applicable manifest doc, stripping server-owned metadata fields.

    Mirrors :func:`_profile_resource_to_manifest_document` but emits the
    AIMProfileSet kind. Used by the profile-edit path to refresh the set document
    in the durable S3 manifest after a CR patch; the AIMProfileSet has no status,
    so only the server-stamped ``metadata`` fields are dropped.
    """
    document = profile_set.model_dump(
        by_alias=True,
        exclude_none=True,
        exclude={"metadata": {"uid", "creation_timestamp", "owner_references"}},
    )
    return {
        "apiVersion": _AIM_API_VERSION_FULL,
        "kind": AIM_PROFILE_SET_RESOURCE,
        **document,
    }


def _model_resource_to_manifest_document(model: AIMModelResource) -> ManifestDocument:
    """Render a live AIMModel CR as a clean, reapplyable manifest document.

    Mirrors :func:`_profile_resource_to_manifest_document` but emits the
    AIMModel kind/apiVersion. Used by the display-metadata patch path to
    refresh the AIMModel document in the durable S3 manifest after a CR
    mutation; the same server-stamped fields (``status``, ``metadata.uid`` /
    ``creationTimestamp`` / ``ownerReferences``) are stripped so the record
    stays reapplyable into a freshly-installed cluster.

    A v1alpha2 custom AIMModel is profiles-shaped, but ``AIMModelSpec`` defaults
    the legacy ``image``/``modelSources``/``env`` fields to ``""``/``[]``/``[]``
    (not ``None``), so ``exclude_none`` alone would emit them alongside
    ``profiles`` and trip the CEL ``image XOR profiles`` rule on re-apply. Drop
    the empty legacy fields when the profiles shape is present so the durable
    record stays applyable — mirroring how the onboard builder emits a
    profiles-only spec.
    """
    document = model.model_dump(
        by_alias=True,
        exclude_none=True,
        exclude={
            "status": True,
            "metadata": {"uid", "creation_timestamp", "owner_references"},
        },
    )
    spec = document.get("spec")
    if isinstance(spec, dict) and spec.get("profiles"):
        for legacy_field in ("image", "modelSources", "env"):
            if not spec.get(legacy_field):
                spec.pop(legacy_field, None)
    return {
        "apiVersion": _AIM_API_VERSION_FULL,
        "kind": _AIM_MODEL_KIND,
        **document,
    }


async def _assert_display_name_available_for_patch(
    kube_client: KubernetesClient,
    namespace: str,
    display_name: str,
    resource_name: str,
) -> None:
    display_label_value = sanitize_label_value(display_name)
    selector = f"{MODEL_NAME_LABEL}={display_label_value},{MODEL_SOURCE_TYPE_LABEL}={ModelSourceType.CUSTOM}"
    try:
        existing = await aims_gateway.find_aim_model_by_label(kube_client, namespace, selector)
    except ApiException as e:
        logger.error(f"Failed to look up AIMModels in namespace {namespace} for display-name check: {e}")
        raise ExternalServiceError(f"Failed to verify display-name availability: {e.reason}") from e
    if existing is not None and existing.metadata.name != resource_name:
        raise ConflictException(f"A custom model named '{display_name}' already exists in namespace '{namespace}'.")


def _resolve_profile_image(request: CustomModelPatchRequest, model: AIMModelResource) -> str:
    """Resolve the deployment image for a runtime-profile edit.

    Prefer the explicit top-level ``image``, then ``customProfile.image`` (the
    request validator has already confirmed the two agree), then the image
    already recorded on the model's overrides. Guarantees a non-empty ref so the
    AIMProfile ``deployment-image-ref`` patch is well-formed.
    """
    if request.image:
        return request.image
    if request.custom_profile and request.custom_profile.get("image"):
        return request.custom_profile["image"]
    existing = extract_overrides_image(model)
    if existing:
        return existing
    raise ValidationException(
        message=(
            "Cannot edit the runtime profile without a container image: none was supplied "
            "and the model has no existing image override."
        )
    )


def _existing_model_source_dicts_for_profile_patch(model: AIMModelResource) -> list[dict[str, Any]]:
    """Return weights ``modelSources`` as camelCase dicts for a runtime-profile PATCH.

    BYO weights and identity must be carried verbatim from the live CR. If the
    AIMModel is not v1alpha2 profiles-shaped (no ``spec.profiles``) or overrides
    lack sources, returning an empty list would merge-patch empty ``modelSources``
    and corrupt the model — fail fast instead.
    """
    profiles = model.spec.profiles
    if profiles is None:
        raise ValidationException(
            message=(
                "Cannot edit the runtime profile: this AIMModel has no `spec.profiles` block "
                "(expected v1alpha2 profile derivation). Runtime edits are only supported for "
                "custom models onboarded through the current flow."
            )
        )
    overrides = profiles.overrides
    if not overrides.model_sources:
        raise ValidationException(
            message=(
                "Cannot edit the runtime profile: `spec.profiles.overrides.modelSources` "
                "is missing or empty, so weights cannot be preserved. Repair or re-onboard "
                "the model before editing its runtime settings."
            )
        )
    return [source.model_dump(by_alias=True, exclude_none=True) for source in overrides.model_sources]


def _identity_overrides_from_profile_overrides(overrides: ProfileOverrides | None) -> dict[str, Any] | None:
    """Return ``aimId``/``modelId``/``modelSources`` as a merge-patch fragment, or None when identity cannot be read."""
    if not isinstance(overrides, ProfileOverrides) or not overrides.model_sources:
        return None
    model_sources = [source.model_dump(by_alias=True, exclude_none=True) for source in overrides.model_sources]
    # aimId and modelId each fall back to the other, so if either is set both are.
    aim_id = overrides.aim_id or overrides.model_id
    model_id = overrides.model_id or overrides.aim_id
    if not aim_id:
        first = model_sources[0].get("modelId")
        if not isinstance(first, str) or not first:
            return None
        aim_id = first
        model_id = first
    return {"aimId": aim_id, "modelId": model_id, "modelSources": model_sources}


def _model_identity_overrides(model: AIMModelResource) -> dict[str, Any] | None:
    """Return the AIMModel identity named AIMProfileSets must match, or None when the model is not profiles-shaped."""
    profiles = model.spec.profiles
    if profiles is None:
        return None
    return _identity_overrides_from_profile_overrides(profiles.overrides)


def _profiles_referenced_by_services(services: list[AIMServiceResource]) -> set[str]:
    """Names of AIMProfiles any live AIMService uses, whether pinned or engine-resolved.

    A deployment can bind a profile directly (``spec.profile.name``) or leave the
    engine to resolve one via selector/auto-resolution, in which case the concrete
    profile lands in ``status.resolvedProfile``. Both must count as in-use so the
    stale-profile cleanup never deletes a profile a running deployment depends on.
    """
    referenced: set[str] = set()
    for service in services:
        if service.spec.profile and service.spec.profile.name:
            referenced.add(service.spec.profile.name)
        resolved = service.status.resolved_profile
        if resolved and resolved.name:
            referenced.add(resolved.name)
    return referenced


async def _recreate_stale_derived_profiles(
    kube_client: KubernetesClient,
    namespace: str,
    profile_set_name: str,
    target_aim_id: str,
    derived_profiles: list[AIMProfileResource],
    in_use_profile_names: set[str],
) -> None:
    """Delete derived AIMProfiles still carrying the old immutable ``spec.aimId`` so the engine recreates them.

    ``spec.aimId`` is immutable, so aligning the set cannot update an existing
    derived profile — it must be recreated. Skips any profile a live AIMService
    uses (it keeps serving and heals on a later read after undeploy). Deletes are
    independent, so they run concurrently; each failure is logged and left for a
    later read rather than failing the caller.
    """

    async def _maybe_delete(derived_profile: AIMProfileResource) -> None:
        profile_name = derived_profile.metadata.name
        current_aim_id = derived_profile.spec.aim_id
        if not profile_name or not current_aim_id or current_aim_id == target_aim_id:
            return
        if profile_name in in_use_profile_names:
            logger.info(
                f"Keeping stale AIMProfile {profile_name} in {namespace} because a deployment still uses it; "
                "it will be recreated after undeploy and a subsequent profiles read"
            )
            return
        try:
            await aims_gateway.delete_aim_profile(kube_client, namespace, profile_name)
        except (ExternalServiceError, ApiException) as e:
            logger.warning(
                f"Failed to delete stale AIMProfile {profile_name} in {namespace} after restamping "
                f"AIMProfileSet {profile_set_name}: {e}"
            )

    await asyncio.gather(*(_maybe_delete(derived_profile) for derived_profile in derived_profiles))


async def _restamp_aiwb_profile_set_identities(
    kube_client: KubernetesClient,
    namespace: str,
    model: AIMModelResource,
    profile_sets: list[AIMProfileSetResource],
    all_profiles: list[AIMProfileResource],
    services: list[AIMServiceResource],
) -> list[AIMProfileSetResource]:
    """Merge-patch named AIMProfileSets whose identity no longer matches the AIMModel.

    Named sets snapshot ``aimId``/``modelId``/``modelSources`` at create so each
    profile is self-contained. The engine-owned Default tracks the AIMModel and
    must not be patched here. Identity can also change outside this API, so
    list/get restamp drifted siblings rather than waiting for a model edit.

    Best-effort per set: an upstream failure or unparseable patch response leaves
    that row as-is so the list still returns. Only identity fields are merged;
    runtime knobs on the set are kept.

    A derived AIMProfile whose immutable ``spec.aimId`` still carries the old
    identity must be recreated after the set is aligned. Such a profile is
    deleted only when no AIMService uses it; an in-use profile is left running
    and a later profiles read retries after undeploy. Sets are independent, so
    they are aligned concurrently.
    """
    identity = _model_identity_overrides(model)
    if identity is None:
        return profile_sets

    in_use_profile_names = _profiles_referenced_by_services(services)
    target_aim_id = identity["aimId"]

    async def _align(profile_set: AIMProfileSetResource) -> AIMProfileSetResource:
        labels = profile_set.metadata.labels or {}
        if labels.get(PROFILE_ORIGIN_LABEL) != PROFILE_ORIGIN_AIWB:
            return profile_set
        aligned_set = profile_set
        if _identity_overrides_from_profile_overrides(profile_set.spec.overrides) != identity:
            try:
                aligned_set = await aims_gateway.patch_aim_profile_set(
                    kube_client,
                    namespace,
                    profile_set.metadata.name,
                    {"spec": {"overrides": identity}},
                )
            except (ExternalServiceError, ValidationError, ApiException) as e:
                logger.warning(
                    f"Failed to restamp identity on AIMProfileSet {profile_set.metadata.name} "
                    f"in {namespace} to match AIMModel {model.metadata.name}: {e}"
                )
                return profile_set
            logger.info(
                f"Restamped identity on AIMProfileSet {profile_set.metadata.name} in {namespace} "
                f"to match AIMModel {model.metadata.name}"
            )

        await _recreate_stale_derived_profiles(
            kube_client,
            namespace,
            profile_set.metadata.name,
            target_aim_id,
            profiles_derived_from_set(all_profiles, profile_set.metadata.name),
            in_use_profile_names,
        )
        return aligned_set

    return list(await asyncio.gather(*(_align(profile_set) for profile_set in profile_sets)))


async def _restamp_named_profile_sets_best_effort(
    kube_client: KubernetesClient,
    namespace: str,
    model: AIMModelResource,
) -> None:
    """List and restamp named AIMProfileSet identities; never fail the caller.

    A model edit succeeds even when this fan-out cannot run: a later read of the
    profiles list restamps the same drifted sets, so the heal is not lost.
    """
    if _model_identity_overrides(model) is None:
        return
    try:
        profile_sets, all_profiles, services = await asyncio.gather(
            aims_gateway.list_aim_profile_sets_for_model(kube_client, namespace, model.metadata.name),
            list_aim_profiles(kube_client, namespace, model_name=model.metadata.name, strict=True),
            aims_gateway.list_aim_services_for_model(kube_client, namespace, model.metadata.name),
        )
        await _restamp_aiwb_profile_set_identities(
            kube_client,
            namespace,
            model,
            profile_sets,
            all_profiles,
            services,
        )
    except (ExternalServiceError, ValidationError, ApiException) as e:
        # list_aim_services_for_model re-raises non-404 ApiException as-is, so it
        # must be caught here too — the model PATCH already committed and this
        # fan-out is best-effort, retried on the next profiles read.
        logger.warning(
            f"Failed to restamp named AIMProfileSet identities for {model.metadata.name} "
            f"in {namespace}; named profiles may stay Not ready until the next list. Error: {e}"
        )


def _compose_narrowed_default_patch(
    model: AIMModelResource,
    target_axes: dict[str, Any],
) -> dict[str, Any] | None:
    """Return a ``spec.profiles`` fragment narrowing the Default to the submitted target, or None to skip.

    Pins the engine-owned Default derivation to the configuration the user
    submitted, so the set stops fanning out. Composes the same axes
    into both the selector and the overrides from one source, so the accelerator
    count cannot drift from the derived profile's tensor-parallel-size.

    Returns None (leaving the Default broad but functional, never emptied) when
    the model has no narrowable derivation or the selector is already narrowed
    to the target (an idempotent re-run).
    """
    profiles = model.spec.profiles
    selector = profiles.derived_from.selector if profiles else None
    model_ref_name = selector.model_ref.name if selector and selector.model_ref else ""
    if selector is None or not selector.role or not model_ref_name:
        return None

    if _selector_carries_axes(selector, target_axes):
        return None

    narrowed_selector = selector.model_dump(by_alias=True, exclude_none=True)
    narrowed_selector.update(target_axes)
    return {"derivedFrom": {"selector": narrowed_selector}, "overrides": dict(target_axes)}


@dataclass(frozen=True)
class _DefaultNarrowing:
    profiles_patch: dict[str, Any]
    target_profile: AIMProfileResource


def _services_pinning_profiles(services: list[AIMServiceResource], profile_names: set[str]) -> list[AIMServiceResource]:
    """AIMServices whose pinned ``spec.profile.name`` is one of ``profile_names``.

    Resolves the deployment's pinned profile — not the overlay the engine mints
    from it — so the reverse lookup keys on what the user deployed.
    """
    return [service for service in services if service.spec.profile and service.spec.profile.name in profile_names]


async def _resolve_default_narrowing_patch(
    kube_client: KubernetesClient,
    namespace: str,
    model_name: str,
    model: AIMModelResource,
    custom_profile: dict[str, Any] | None,
) -> _DefaultNarrowing | None:
    """Resolve the submitted Default configuration and compose its narrowing patch, or None to skip.

    Best-effort resolution: narrowing rides along on a Default edit as otherwise
    invisible cleanup, so any inability to identify a single Default set, its
    derived profiles, or one base profile matching the submitted axes leaves the
    Default unnarrowed. An unnarrowed Default is fully functional, so skipping
    never breaks the user's edit.

    Not best-effort once narrowing *would* apply: rewriting the selector makes
    the engine re-derive and prune every profile the narrowed set no longer
    selects. If a live AIMService pins one of those pruned profiles, that workload
    would break, so the edit is refused (nothing is written) with a conflict
    naming the blocking deployments.
    """
    submitted_axes = _submitted_narrowing_axes(custom_profile)
    if submitted_axes is None:
        return None

    try:
        profile_sets = await aims_gateway.list_aim_profile_sets_for_model(kube_client, namespace, model_name)
        default_set = classify_default_profile_set(profile_sets)
    except (ExternalServiceError, InconsistentStateException) as e:
        logger.debug(f"Skipping Default narrowing for {model_name} in {namespace}: no unique Default set ({e}).")
        return None

    all_profiles, base_profiles = await asyncio.gather(
        list_aim_profiles(kube_client, namespace, model_name=model_name),
        list_base_role_profiles(kube_client, namespace),
    )
    default_derived = profiles_derived_from_set(all_profiles, default_set.metadata.name)
    base_profile = _resolve_narrowing_base_profile(submitted_axes, base_profiles)
    if base_profile is None:
        return None
    target_axes = _narrowing_axes_from_profile(base_profile)

    target_profiles = _derived_profiles_for_base(default_derived, base_profile, target_axes)
    if len(target_profiles) != 1:
        return None
    target_profile = target_profiles[0]

    fragment = _compose_narrowed_default_patch(model, target_axes)
    if fragment is None:
        return None

    # Narrowing would prune the Default's other derived profiles. Confirm no live
    # deployment pins a profile owned by the Default set before rewriting the
    # selector; a K8s read failure here skips narrowing (leaves the Default broad
    # and functional) rather than narrowing without knowing it is safe.
    try:
        services = await aims_gateway.list_aim_services_for_model(kube_client, namespace, model_name)
    except ApiException as e:
        logger.warning(
            f"Skipping Default narrowing for {model_name} in {namespace}: deployment check failed ({e.reason})."
        )
        return None

    pruned_profile_names = {
        profile.metadata.name
        for profile in default_derived
        if profile.metadata.name and profile.metadata.name != target_profile.metadata.name
    }
    blocking = _services_pinning_profiles(services, pruned_profile_names)
    if blocking:
        blocking_services = [
            ProfileInUseRef(
                service_id=service.id,
                display_name=(service.metadata.annotations or {}).get(DISPLAY_NAME_ANNOTATION) or service.metadata.name,
            ).model_dump(by_alias=True)
            for service in blocking
        ]
        raise ConflictException(
            f"Profile 'Default' is in use by {len(blocking)} deployment(s) and cannot be modified or deleted.",
            detail={"blockingServices": blocking_services},
        )

    return _DefaultNarrowing(
        profiles_patch=fragment,
        target_profile=target_profile,
    )


async def _default_effective_profile(
    kube_client: KubernetesClient,
    namespace: str,
    model_name: str,
    model: AIMModelResource,
) -> AIMProfileResource | None:
    """Return the effective AIMProfile of the model's Default set (the one deploy pins).

    Used as the runtime-profile patch target when the edit does not itself narrow the
    Default. Patching the Default's effective profile keeps the write aligned with the
    profile deploy would select, instead of an arbitrary first-item AIMProfile off a
    label list. Returns ``None`` when the model has no unique Default set or no derived
    profile yet, so the caller raises the not-ready conflict rather than patching the
    wrong profile. A Kubernetes read failure propagates as ``ExternalServiceError`` (502).
    """
    try:
        profile_sets = await aims_gateway.list_aim_profile_sets_for_model(kube_client, namespace, model_name)
        default_set = classify_default_profile_set(profile_sets)
    except InconsistentStateException as e:
        logger.debug(f"No unique Default set for {model_name} in {namespace}; cannot resolve effective profile ({e}).")
        return None

    all_profiles = await list_aim_profiles(kube_client, namespace, model_name=model_name, strict=True)
    default_derived = profiles_derived_from_set(all_profiles, default_set.metadata.name)
    preferred_precision = (model.metadata.annotations or {}).get(MODEL_PRECISION_ANNOTATION)
    return effective_profile_for_set(default_derived, preferred_precision)


async def patch_onboarded_model(
    kube_client: KubernetesClient,
    minio_client: MinioClient,
    namespace: str,
    name: str,
    request: CustomModelPatchRequest,
) -> CustomModelPatchResponse:
    """Apply a partial update to a custom-onboarded model: display metadata and/or runtime profile.

    Display fields (display name, description, tags) patch the AIMModel
    annotations and labels. Runtime-profile fields (image, customProfile)
    rewrite ``spec.profiles.overrides`` and repatch the live AIMProfile
    (``deployment-image-ref`` annotation plus the runtime spec knobs) so the
    change takes effect without waiting for a controller reconcile. When both
    groups are present the AIMModel mutation is a single merge-patch and the S3
    mirror is refreshed in one read-modify-write, all under the manifest write
    lock, so the durable mirror never inverts relative to the authoritative CRs.

    Editing the Default (a runtime-profile edit) is also the moment its
    derivation is narrowed to the submitted runtime configuration, so an
    already-imported model stops fanning out without inferring a surprise
    target. That narrowing is refused when a live deployment pins a profile the
    narrowed set would prune (see ``_resolve_default_narrowing_patch``).

    After the AIMModel write, AIWB-authored sibling AIMProfileSets are restamped
    onto the live model identity so named profiles cannot stay Not ready when
    identity/weights drifted (including edits that only change display metadata).

    Raises:
        ValidationException: empty request (no recognised field supplied); or a
            runtime-profile edit on an AIMModel without v1alpha2
            ``spec.profiles.overrides.modelSources`` (weights cannot be preserved).
        NotFoundException: model missing, or not a custom-onboarded model.
        ConflictException: requested display name already taken; a runtime-profile
            edit was requested before aim-engine emitted the AIMProfile; or the
            edit would narrow the Default and prune a profile a deployment pins.
    """
    updates = request.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        raise ValidationException(
            message="At least one of displayName, description, tags, image, or customProfile must be provided."
        )

    metadata_updates = {key: value for key, value in updates.items() if key in ("display_name", "description", "tags")}
    profile_edit = "image" in updates or "custom_profile" in updates

    try:
        model = await aims_gateway.get_aim_model(kube_client, namespace, name)
    except ApiException as e:
        logger.error(f"Failed to read AIMModel {name} in namespace {namespace}: {e}")
        raise ExternalServiceError(f"Failed to read AIMModel '{name}': {e.reason}") from e
    if model is None:
        raise NotFoundException(f"Custom onboarded model '{name}' not found in namespace '{namespace}'")
    if (model.metadata.labels or {}).get(MODEL_SOURCE_TYPE_LABEL) != ModelSourceType.CUSTOM:
        raise NotFoundException(f"Custom onboarded model '{name}' not found in namespace '{namespace}'")

    if "display_name" in metadata_updates:
        await _assert_display_name_available_for_patch(kube_client, namespace, metadata_updates["display_name"], name)

    # Compose the AIMModel merge-patch: display metadata and/or the rewritten
    # profile overrides, in one body so both halves land atomically on the CR.
    patch_body: dict[str, Any] = {}
    if metadata_updates:
        patch_body.update(build_display_metadata_patch(metadata_updates))

    effective_image = ""
    profile_spec_patch: dict[str, Any] = {}
    narrowing: _DefaultNarrowing | None = None
    if profile_edit:
        effective_image = _resolve_profile_image(request, model)
        # Tombstone keys the edit dropped so merge-patch actually deletes them
        # from the live engineArgs/engineEnv maps instead of silently keeping them.
        custom_profile = _tombstone_removed_map_keys(request.custom_profile, _existing_overrides_map(model))
        overrides_payload = build_overrides_payload(
            custom_profile=custom_profile,
            repo_id=extract_onboard_repo_id(model),
            image=effective_image,
            model_sources=_existing_model_source_dicts_for_profile_patch(model),
        )
        profiles_patch: dict[str, Any] = {"overrides": overrides_payload}
        patch_body.setdefault("spec", {})["profiles"] = profiles_patch
        profile_spec_patch = _runtime_override_fields(custom_profile)

        # Precision remains an annotation because the CRD prunes it from overrides.
        resulting_precision = (model.metadata.annotations or {}).get(MODEL_PRECISION_ANNOTATION)
        if request.custom_profile is not None and "precision" in request.custom_profile:
            edited_precision = request.custom_profile["precision"]
            resulting_precision = str(edited_precision) if edited_precision else None
            annotations = patch_body.setdefault("metadata", {}).setdefault("annotations", {})
            annotations[MODEL_PRECISION_ANNOTATION] = resulting_precision

    object_key = get_custom_model_manifest_path(namespace, name)

    async with manifest_write_lock(MINIO_BUCKET, object_key):
        if profile_edit:
            # Perform the deployment check as close as possible to the AIMModel
            # patch. Kubernetes cannot atomically read AIMServices and patch an
            # AIMModel, but keeping both inside this lock minimizes the local
            # check-to-write window.
            narrowing = await _resolve_default_narrowing_patch(
                kube_client,
                namespace,
                name,
                model,
                custom_profile,
            )
            if narrowing is not None:
                profiles_patch["derivedFrom"] = narrowing.profiles_patch["derivedFrom"]
                profiles_patch["overrides"].update(narrowing.profiles_patch["overrides"])

        # Resolve the live AIMProfile before mutating anything so a runtime-profile
        # edit on a not-yet-ready model fails (409) without a partial write.
        profile: AIMProfileResource | None = None
        if profile_edit:
            profile = narrowing.target_profile if narrowing is not None else None
            if profile is None:
                profile = await _default_effective_profile(kube_client, namespace, name, model)
            if profile is None:
                raise ConflictException(
                    f"Runtime profile for custom model '{name}' in project '{namespace}' is not ready yet; "
                    "wait for the model to finish importing before editing its runtime profile."
                )

        patched = await aims_gateway.patch_aim_model(kube_client, namespace, name, patch_body)
        documents = [_model_resource_to_manifest_document(patched)]

        if profile is not None:
            patched_profile = await patch_aim_profile(
                kube_client=kube_client,
                namespace=namespace,
                profile_name=profile.metadata.name,
                image_ref=effective_image,
                custom_profile_spec=profile_spec_patch or None,
            )
            documents.append(_profile_resource_to_manifest_document(patched_profile))

        try:
            await _upsert_manifest_documents_to_s3_unlocked(minio_client, object_key, documents)
        except Exception as s3_error:
            logger.warning(
                f"Patched custom AIMModel {name} in {namespace} but S3 mirror sync failed; "
                f"the CRs are authoritative and a subsequent patch will re-sync. Error: {s3_error}"
            )

    logger.info(
        f"Updated custom AIMModel {name} in namespace {namespace} "
        f"(metadata={bool(metadata_updates)}, profile={profile_edit})"
    )
    await _restamp_named_profile_sets_best_effort(kube_client, namespace, patched)
    return display_metadata_response_from_model(patched)


async def finalize_aim_profile_for_onboarded_model(
    kube_client: KubernetesClient,
    minio_client: MinioClient,
    namespace: str,
    aim_model_name: str,
    image_ref: str = DEFAULT_AIM_DEPLOYMENT_IMAGE_REF,
    custom_profile: dict[str, Any] | None = None,
    bucket: str = MINIO_BUCKET,
    timeout_seconds: float = AIM_PROFILE_WAIT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = AIM_PROFILE_POLL_INTERVAL_SECONDS,
) -> AIMProfileResource:
    """Wait for aim-engine AIMProfile, patch deployment-image-ref and customProfile, mirror AIMModel+AIMProfile to S3. Precondition failures leave cluster untouched."""
    profile = await wait_for_aim_profile(
        kube_client=kube_client,
        namespace=namespace,
        model_name=aim_model_name,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    if profile is None:
        raise PreconditionNotMetException(
            message=(
                f"aim-engine did not emit an AIMProfile for AIMModel "
                f"'{aim_model_name}' in namespace '{namespace}' within "
                f"{timeout_seconds:g}s; cannot complete onboard."
            )
        )

    manifest_key = get_custom_model_manifest_path(namespace, aim_model_name)
    # Hold the lock across read, patch, and write so concurrent re-onboards cannot drop the AIMProfile or publish a stale AIMModel.
    async with manifest_write_lock(bucket, manifest_key):
        existing_documents = await read_manifest_from_s3(minio_client, bucket, manifest_key)
        # Abort before patching when the S3 scaffold is missing or lacks the AIMModel doc, so we never append an orphaned AIMProfile.
        if not existing_documents:
            raise PreconditionNotMetException(
                message=(
                    f"Onboarded-model manifest at '{manifest_key}' is missing or "
                    "empty; the AIMModel document must be written before the "
                    "AIMProfile document can be appended."
                )
            )
        if not _manifest_contains_aim_model(existing_documents, namespace, aim_model_name):
            raise PreconditionNotMetException(
                message=(
                    f"Onboarded-model manifest at '{manifest_key}' does not contain "
                    f"an AIMModel document for '{aim_model_name}' in namespace "
                    f"'{namespace}'; refusing to write an AIMProfile document that "
                    "would be orphaned from its AIMModel scaffold."
                )
            )

        patched_profile = await patch_aim_profile(
            kube_client=kube_client,
            namespace=namespace,
            profile_name=profile.metadata.name,
            image_ref=image_ref,
            custom_profile_spec=custom_profile,
        )

        merged = upsert_manifest_documents(
            existing=existing_documents,
            new_documents=[_profile_resource_to_manifest_document(patched_profile)],
        )
        await write_manifest_to_s3(minio_client, bucket, manifest_key, merged)

    logger.info(
        "Onboarded-model manifest updated at {}/{} with AIMProfile {}",
        bucket,
        manifest_key,
        patched_profile.metadata.name,
    )
    return patched_profile


def _blank_to_none(value: str | None) -> str | None:
    """Normalize empty or whitespace-only strings to None."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _endpoint_from_bucket_url(storage_name: str, bucket_url: str) -> str:
    """Extract endpoint origin from a storage bucket URL."""
    parsed = urlsplit(bucket_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValidationException(
            message=(
                f"Storage '{storage_name}' has invalid BUCKET_URL '{bucket_url}'. "
                "Expected a full URL like 'https://s3.example.com/my-bucket'."
            )
        )
    return f"{parsed.scheme}://{parsed.netloc}"


def _normalize_repository_for_match(repo: str) -> str:
    normalized = repo.strip().lower()
    if normalized.startswith("docker.io/"):
        normalized = normalized[len("docker.io/") :]
    if normalized.startswith("library/"):
        normalized = normalized[len("library/") :]
    return normalized


def _cleaned_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def _collect_discovered_profile_matrix(
    by_hardware: Any,
    accelerator_types: set[str],
    accelerator_models: set[str],
    counts_by_model: defaultdict[str, set[int]],
    precisions_by_model: defaultdict[str, set[str]],
    metrics_by_model: defaultdict[str, set[str]],
    optimization_classes_by_model: defaultdict[str, set[str]],
    emitted_tuples: set[tuple[str, int, str, str]],
    ambiguous_tuples: set[tuple[str, int, str, str]],
) -> None:
    """Fold one AIMClusterModel's discovered matrix into the accumulating sets.

    Ambiguity is judged *within a single model*: a tuple two of this model's
    profiles both emit (differing only by optimization type) is ambiguous and
    withheld. Across models the same tuple may recur because Kubernetes does not
    enforce image-reference uniqueness — that duplication is not ambiguity, so
    the within-model count is used rather than a global one, and identical tuples
    from separate models are deduplicated through ``emitted_tuples``.
    """
    if not isinstance(by_hardware, list):
        return

    within_model_counts: Counter[tuple[str, int, str, str]] = Counter()
    for entry in by_hardware:
        if not isinstance(entry, dict):
            continue

        accelerator_type = _cleaned_string(entry.get("acceleratorType"))
        if accelerator_type:
            accelerator_types.add(accelerator_type)

        model_key = _cleaned_string(entry.get("acceleratorModel"))
        if not model_key:
            continue

        accelerator_models.add(model_key)
        raw_count = entry.get("acceleratorCount")
        valid_count = raw_count if isinstance(raw_count, int) and raw_count > 0 else None
        if valid_count is not None:
            counts_by_model[model_key].add(valid_count)

        profiles = entry.get("profiles")
        if not isinstance(profiles, list):
            continue
        for profile in profiles:
            if not isinstance(profile, dict):
                continue

            precision = _cleaned_string(profile.get("precision"))
            if precision:
                precisions_by_model[model_key].add(precision)

            metric = _cleaned_string(profile.get("metric"))
            if metric:
                metrics_by_model[model_key].add(metric)

            optimization_class = _cleaned_string(profile.get("type"))
            if optimization_class:
                optimization_classes_by_model[model_key].add(optimization_class)

            # A combination is one hardware entry's (model, count) paired with a
            # coexisting (precision, metric); this is the coexistence the flat
            # per-model lists cannot express. All four axes must be present, since
            # a create/update resolves exactly this tuple against the base.
            if valid_count is not None and precision and metric:
                within_model_counts[(model_key, valid_count, precision, metric)] += 1

    for combination, count in within_model_counts.items():
        emitted_tuples.add(combination)
        if count > 1:
            ambiguous_tuples.add(combination)


async def _resolve_s3_storage_config(
    kube_client: KubernetesClient,
    namespace: str,
    storage_name: str,
) -> tuple[str, str | None, str | None, str, str]:
    """Resolve S3 storage config values from the project storage ConfigMap."""
    try:
        storage_config = await kube_client.core_v1.read_namespaced_config_map(name=storage_name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            raise NotFoundException(f"Storage '{storage_name}' not found in namespace '{namespace}'") from e
        logger.error(f"Failed to read storage '{storage_name}' in namespace '{namespace}': {e}")
        raise ExternalServiceError(f"Failed to read storage '{storage_name}': {e.reason}") from e

    labels = storage_config.metadata.labels or {}
    if labels.get(STORAGE_CONFIGMAP_LABEL) != "true":
        raise ValidationException(
            message=(
                f"Storage '{storage_name}' is not a valid AIWB storage configuration. "
                "Create the storage via the AIWB storages API first."
            )
        )

    data = storage_config.data or {}
    raw_type = _blank_to_none(data.get("TYPE")) or _blank_to_none(labels.get(STORAGE_TYPE_LABEL))
    if raw_type != StorageType.S3.value:
        raise ValidationException(
            message=(f"Storage '{storage_name}' has type '{raw_type or 'unknown'}'. Expected '{StorageType.S3.value}'.")
        )

    secret_name = _blank_to_none(data.get("SECRET_NAME"))
    if not secret_name:
        raise ValidationException(
            message=(
                f"Storage '{storage_name}' is missing 'SECRET_NAME'. "
                "Recreate the storage configuration with a backing secret."
            )
        )

    access_key_name = _blank_to_none(data.get("ACCESS_KEY_NAME"))
    if not access_key_name:
        raise ValidationException(
            message=(
                f"Storage '{storage_name}' is missing 'ACCESS_KEY_NAME'. "
                "Recreate the storage configuration with explicit secret key mappings."
            )
        )

    secret_key_name = _blank_to_none(data.get("SECRET_KEY_NAME"))
    if not secret_key_name:
        raise ValidationException(
            message=(
                f"Storage '{storage_name}' is missing 'SECRET_KEY_NAME'. "
                "Recreate the storage configuration with explicit secret key mappings."
            )
        )

    return (
        secret_name,
        _blank_to_none(data.get("BUCKET_URL")),
        _blank_to_none(data.get("REGION")),
        access_key_name,
        secret_key_name,
    )


async def get_base_image_runtime_profile_options(
    kube_client: KubernetesClient,
    image_repository: str,
    image_tag: str,
) -> BaseImageRuntimeProfileOptions:
    """Return runtime options discovered for one selected base image.

    Reads the AIMClusterModel ``status.discoveredProfiles.byHardware`` matrix
    for the matching ``spec.image`` reference and projects it into per-model
    selector options (accelerator types/models/counts, precisions, metrics).
    """
    repository = image_repository.strip()
    tag = image_tag.strip()
    if not repository or not tag:
        raise ValidationException("Both imageRepository and imageTag are required.")

    repository_match_key = _normalize_repository_for_match(repository)

    accelerator_types: set[str] = set()
    accelerator_models: set[str] = set()
    counts_by_model: defaultdict[str, set[int]] = defaultdict(set)
    precisions_by_model: defaultdict[str, set[str]] = defaultdict(set)
    metrics_by_model: defaultdict[str, set[str]] = defaultdict(set)
    optimization_classes_by_model: defaultdict[str, set[str]] = defaultdict(set)
    # A tuple is resolvable unless a single model emits it more than once (two
    # profiles differing only by optimization type): a create/update must resolve
    # the axes to exactly one base profile, so such a tuple would be offered by the
    # form yet rejected by the API with a 400. Ambiguity is per-model; identical
    # tuples across duplicate cluster models are deduplicated, not treated as
    # ambiguous.
    emitted_tuples: set[tuple[str, int, str, str]] = set()
    ambiguous_tuples: set[tuple[str, int, str, str]] = set()
    has_matching_model = False

    cluster_models = await aims_gateway.list_aim_cluster_models(kube_client)
    for model in cluster_models:
        spec = model.get("spec") if isinstance(model, dict) else None
        image_ref = (spec or {}).get("image")
        if not isinstance(image_ref, str) or not image_ref.strip():
            continue
        try:
            repo, model_tag = parse_container_image_repository_and_tag(image_ref)
        except ValueError:
            continue
        if _normalize_repository_for_match(repo) != repository_match_key or model_tag != tag:
            continue

        has_matching_model = True
        by_hardware = (
            ((model.get("status") or {}).get("discoveredProfiles") or {}).get("byHardware")
            if isinstance(model, dict)
            else None
        )
        _collect_discovered_profile_matrix(
            by_hardware=by_hardware,
            accelerator_types=accelerator_types,
            accelerator_models=accelerator_models,
            counts_by_model=counts_by_model,
            precisions_by_model=precisions_by_model,
            metrics_by_model=metrics_by_model,
            optimization_classes_by_model=optimization_classes_by_model,
            emitted_tuples=emitted_tuples,
            ambiguous_tuples=ambiguous_tuples,
        )

    if not has_matching_model:
        raise NotFoundException(f"No AIMClusterModel found for base image '{repository}:{tag}'.")

    return BaseImageRuntimeProfileOptions(
        image_repository=repository,
        image_tag=tag,
        accelerator_types=sorted(accelerator_types),
        accelerator_models=sorted(accelerator_models),
        accelerator_counts_by_model={k: sorted(v) for k, v in sorted(counts_by_model.items())},
        precisions_by_model={k: sorted(v) for k, v in sorted(precisions_by_model.items())},
        metrics_by_model={k: sorted(v) for k, v in sorted(metrics_by_model.items())},
        optimization_classes_by_model={k: sorted(v) for k, v in sorted(optimization_classes_by_model.items())},
        combinations=[
            RuntimeProfileCombination(
                accelerator_model=model, accelerator_count=count, precision=precision, metric=metric
            )
            for (model, count, precision, metric) in sorted(emitted_tuples - ambiguous_tuples)
        ],
        # Reflect whether an actual discovered *profile* was seen, not just a
        # hardware group: a ``byHardware`` entry with ``profiles: []`` records an
        # accelerator model but no profile, so it must read as not-ready (client
        # falls back) rather than blocking. Any profile with content populates at
        # least one of these per-model maps.
        profiles_available=bool(precisions_by_model or metrics_by_model or optimization_classes_by_model),
    )
