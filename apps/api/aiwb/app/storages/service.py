# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import hashlib

from kubernetes_asyncio.client import ApiException, V1ConfigMap, V1ObjectMeta, V1OwnerReference

from api_common.exceptions import ConflictException, ExternalServiceError, NotFoundException, ValidationException
from api_common.secrets import S3_REQUIRED_CREDENTIAL_KEYS, SecretUseCase

from ..config import SUBMITTER_ANNOTATION
from ..dispatch.kube_client import KubernetesClient
from ..secrets.constants import AIRM_USE_CASE_LABEL, USE_CASE_LABEL
from .constants import (
    STORAGE_CONFIGMAP_LABEL,
    STORAGE_DISPLAY_NAME_ANNOTATION,
    STORAGE_NAME_DISPLAY_HASH_LENGTH,
    STORAGE_NAME_MAX_LENGTH,
    STORAGE_NAME_NON_ALNUM_RE,
    STORAGE_NAME_PREFIX,
    STORAGE_TYPE_LABEL,
)
from .enums import StorageType
from .schemas import ProjectStorageCreateRequest, ProjectStorageResponse, S3StorageSpec


def _slugify_display_name_for_storage_name(display_name: str, max_length: int) -> str:
    slug = STORAGE_NAME_NON_ALNUM_RE.sub("-", display_name.strip().lower()).strip("-")
    if not slug:
        return ""
    return slug[:max_length].rstrip("-")


def generate_storage_name(display_name: str) -> str:
    """Generate a deterministic K8s-compatible storage ConfigMap name."""
    normalized = _normalize_display_name(display_name)
    hash_suffix = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:STORAGE_NAME_DISPLAY_HASH_LENGTH]
    slug_budget = STORAGE_NAME_MAX_LENGTH - len(STORAGE_NAME_PREFIX) - len(hash_suffix) - 1
    slug = _slugify_display_name_for_storage_name(normalized, slug_budget)
    if slug:
        return f"{STORAGE_NAME_PREFIX}{slug}-{hash_suffix}"
    return f"{STORAGE_NAME_PREFIX}{hash_suffix}"


def _validate_secret_use_case(
    secret_name: str,
    labels: dict[str, str],
    expected_use_case: SecretUseCase,
) -> None:
    """Allow unlabeled secrets; enforce a caller-provided use case when labeled."""
    raw_use_case = labels.get(USE_CASE_LABEL) or labels.get(AIRM_USE_CASE_LABEL)
    if not raw_use_case:
        return
    try:
        use_case = SecretUseCase(raw_use_case)
    except ValueError as e:
        raise ValidationException(
            f"Secret '{secret_name}' has unsupported use-case label '{raw_use_case}'. "
            f"Expected one of: {', '.join(uc.value for uc in SecretUseCase)}."
        ) from e
    if use_case != expected_use_case:
        raise ValidationException(
            f"Secret '{secret_name}' is labeled for use case '{raw_use_case}' "
            f"and cannot be used where '{expected_use_case.value}' is required."
        )


def _resolve_secret_key_name(
    *,
    secret_name: str,
    data: dict[str, str],
    provided_key_name: str | None,
    logical_name: str,
) -> str:
    """Resolve a secret key name from request or known aliases; raise when unresolved."""
    if provided_key_name:
        if provided_key_name not in data:
            raise ValidationException(f"Secret '{secret_name}' is missing required key '{provided_key_name}'.")
        return provided_key_name

    aliases = S3_REQUIRED_CREDENTIAL_KEYS[logical_name]
    match = next((alias for alias in aliases if alias in data), None)
    if match:
        return match

    display_aliases = ", ".join(aliases)
    raise ValidationException(
        f"Secret '{secret_name}' does not contain a detectable {logical_name}. "
        f"Provide key name explicitly or include one of: {display_aliases}."
    )


def _resolve_s3_secret_key_names(
    secret_name: str, data: dict[str, str], request: ProjectStorageCreateRequest
) -> tuple[str, str]:
    access_key_name = _resolve_secret_key_name(
        secret_name=secret_name,
        data=data,
        provided_key_name=request.spec.access_key_name,
        logical_name="access key",
    )
    secret_key_name = _resolve_secret_key_name(
        secret_name=secret_name,
        data=data,
        provided_key_name=request.spec.secret_key_name,
        logical_name="secret key",
    )
    if access_key_name == secret_key_name:
        raise ValidationException(
            f"Secret '{secret_name}' resolves access and secret key to the same field '{access_key_name}'. "
            "They must be distinct."
        )
    return access_key_name, secret_key_name


def _normalize_display_name(display_name: str) -> str:
    normalized = display_name.strip()
    if not normalized:
        raise ValidationException("Storage display name must contain at least one non-whitespace character.")
    return normalized


def _storage_sort_key(storage: ProjectStorageResponse) -> tuple[str, str]:
    normalized_display_name = storage.display_name.strip() or storage.name
    return normalized_display_name.casefold(), storage.name


def _first_present(data: dict[str, str], *keys: str) -> str | None:
    """Return the first present value among equivalent ConfigMap keys."""
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _to_project_storage_response(config_map: V1ConfigMap, namespace: str) -> ProjectStorageResponse | None:
    metadata = config_map.metadata
    data = config_map.data or {}
    labels = metadata.labels if metadata and metadata.labels else {}

    if not metadata or not metadata.name:
        return None

    raw_type = _first_present(data, "type", "TYPE") or labels.get(STORAGE_TYPE_LABEL)
    secret_name = _first_present(data, "secretName", "SECRET_NAME")
    if not raw_type or not secret_name:
        return None

    try:
        storage_type = StorageType(raw_type)
    except ValueError:
        return None

    display_name = (
        metadata.annotations.get(STORAGE_DISPLAY_NAME_ANNOTATION) if metadata and metadata.annotations else None
    ) or metadata.name

    return ProjectStorageResponse(
        name=metadata.name,
        display_name=display_name,
        project=namespace,
        type=storage_type,
        secret_name=secret_name,
        spec=S3StorageSpec(
            bucket_url=_first_present(data, "bucketUrl", "BUCKET_URL"),
            region=_first_present(data, "region", "REGION"),
            access_key_name=_first_present(data, "accessKeyName", "ACCESS_KEY_NAME"),
            secret_key_name=_first_present(data, "secretKeyName", "SECRET_KEY_NAME"),
        ),
        created_at=metadata.creation_timestamp,
    )


async def list_project_storages(
    kube_client: KubernetesClient,
    namespace: str,
    storage_type: StorageType | None = None,
) -> list[ProjectStorageResponse]:
    label_selector = f"{STORAGE_CONFIGMAP_LABEL}=true"
    if storage_type:
        label_selector = f"{label_selector},{STORAGE_TYPE_LABEL}={storage_type.value}"

    try:
        config_maps = await kube_client.core_v1.list_namespaced_config_map(
            namespace=namespace,
            label_selector=label_selector,
        )
    except ApiException as e:
        raise ExternalServiceError(f"Failed to list storages for project '{namespace}': {e.reason}") from e

    storages = [
        storage
        for config_map in (config_maps.items or [])
        if (storage := _to_project_storage_response(config_map, namespace)) is not None
    ]
    storages.sort(key=_storage_sort_key)
    return storages


async def create_project_storage(
    kube_client: KubernetesClient,
    namespace: str,
    submitter: str,
    request: ProjectStorageCreateRequest,
) -> ProjectStorageResponse:
    """Create a project-scoped storage config backed by an existing project secret."""
    if request.type != StorageType.S3:
        raise ValidationException("Only storage type 'S3' is currently supported.")

    try:
        secret = await kube_client.core_v1.read_namespaced_secret(name=request.secret_name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            raise NotFoundException(f"Secret '{request.secret_name}' not found in project '{namespace}'.") from e
        raise ExternalServiceError(f"Failed to read secret '{request.secret_name}': {e.reason}") from e

    secret_labels = secret.metadata.labels or {}
    secret_data = secret.data or {}
    _validate_secret_use_case(request.secret_name, secret_labels, SecretUseCase.S3)
    access_key_name, secret_key_name = _resolve_s3_secret_key_names(request.secret_name, secret_data, request)
    normalized_display_name = _normalize_display_name(request.display_name)

    existing_storages = await list_project_storages(kube_client=kube_client, namespace=namespace)
    for existing in existing_storages:
        if existing.display_name.strip() == normalized_display_name:
            raise ConflictException(
                f"A storage with display name '{normalized_display_name}' already exists in project '{namespace}'."
            )

    resolved_spec = S3StorageSpec.model_validate(
        request.spec.model_dump() | {"access_key_name": access_key_name, "secret_key_name": secret_key_name}
    )

    data = {
        "TYPE": request.type.value,
        "SECRET_NAME": request.secret_name,
        "ACCESS_KEY_NAME": access_key_name,
        "SECRET_KEY_NAME": secret_key_name,
    }
    if resolved_spec.bucket_url:
        data["BUCKET_URL"] = resolved_spec.bucket_url
    if resolved_spec.region:
        data["REGION"] = resolved_spec.region

    owner_references: list[V1OwnerReference] | None = None
    secret_uid = secret.metadata.uid if secret.metadata else None
    secret_name = secret.metadata.name if secret.metadata else None
    if secret_uid and secret_name:
        owner_references = [
            V1OwnerReference(
                api_version="v1",
                kind="Secret",
                name=secret_name,
                uid=secret_uid,
                controller=False,
                block_owner_deletion=False,
            )
        ]

    generated_name = generate_storage_name(normalized_display_name)
    config_map = V1ConfigMap(
        metadata=V1ObjectMeta(
            name=generated_name,
            namespace=namespace,
            labels={
                STORAGE_CONFIGMAP_LABEL: "true",
                STORAGE_TYPE_LABEL: request.type.value,
            },
            annotations={
                SUBMITTER_ANNOTATION: submitter,
                STORAGE_DISPLAY_NAME_ANNOTATION: normalized_display_name,
            },
            owner_references=owner_references,
        ),
        data=data,
    )

    try:
        created = await kube_client.core_v1.create_namespaced_config_map(namespace=namespace, body=config_map)
    except ApiException as e:
        if e.status == 409:
            raise ConflictException(
                f"A storage with display name '{normalized_display_name}' already exists in project '{namespace}'."
            ) from e
        raise ExternalServiceError(f"Failed to create storage '{normalized_display_name}': {e.reason}") from e

    return ProjectStorageResponse(
        name=created.metadata.name,
        display_name=normalized_display_name,
        project=namespace,
        type=request.type,
        secret_name=request.secret_name,
        spec=resolved_spec,
        created_at=created.metadata.creation_timestamp,
    )
