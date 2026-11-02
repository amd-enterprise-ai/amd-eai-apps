# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import base64
import json
from uuid import uuid4

from kubernetes_asyncio.client import ApiException
from loguru import logger

from api_common.exceptions import ConflictException, NotFoundException, ValidationException
from api_common.secrets import S3_REQUIRED_CREDENTIAL_KEYS, SecretUseCase, find_missing_s3_credential_types

from ..dispatch.kube_client import KubernetesClient
from .constants import DISPLAY_NAME_ANNOTATION
from .gateway import (
    create_kubernetes_secret,
    delete_kubernetes_secret,
    get_kubernetes_secret,
    list_kubernetes_secrets,
)
from .schemas import SecretCreate, SecretResponse


def generate_secret_name() -> str:
    """Generate a unique K8s-compatible name for a secret.

    Returns a name in the format 'wb-secret-{8-char-hex}' (18 chars total).
    The generated name is returned in API responses as metadata.name; display_name holds the human-readable name.
    """
    return f"wb-secret-{uuid4().hex[:8]}"


async def list_secrets_for_namespace(
    kube_client: KubernetesClient,
    namespace: str,
    use_case: SecretUseCase | None = None,
) -> list[SecretResponse]:
    """
    List all Kubernetes Secrets in a namespace.

    Returns:
        List of secrets
    """
    secrets_crds = await list_kubernetes_secrets(kube_client=kube_client, namespace=namespace)
    secrets = [SecretResponse.model_validate(crd.model_dump()) for crd in secrets_crds]

    # Filter by use case if specified
    if use_case:
        secrets = [s for s in secrets if s.use_case == use_case]

    logger.debug(f"Found {len(secrets)} secrets in namespace {namespace}")
    return secrets


async def get_secret_details(
    kube_client: KubernetesClient,
    namespace: str,
    secret_name: str,
) -> SecretResponse:
    """
    Get detailed information about a specific secret.

    Returns:
        Detailed secret information

    Raises:
        NotFoundException: If the secret doesn't exist
    """
    secret_crd = await get_kubernetes_secret(kube_client=kube_client, namespace=namespace, name=secret_name)

    if not secret_crd:
        raise NotFoundException(f"Secret '{secret_name}' not found in namespace '{namespace}'")

    return SecretResponse.model_validate(secret_crd.model_dump())


async def create_secret(
    kube_client: KubernetesClient,
    namespace: str,
    secret_in: SecretCreate,
    submitter: str | None = None,
) -> SecretResponse:
    """
    Create a new Kubernetes Secret.

    Returns:
        Created secret

    Raises:
        ConflictException: If a secret with the same name already exists
        ValidationException: If image pull secret value is not valid JSON, or an S3 secret is
            missing required credential keys
    """
    if secret_in.use_case == SecretUseCase.IMAGE_PULL_SECRET:
        dockerconfig_b64 = secret_in.data.get(".dockerconfigjson")
        if dockerconfig_b64:
            try:
                payload = base64.b64decode(dockerconfig_b64, validate=True)
                json.loads(payload.decode("utf-8"))
            except (ValueError, json.JSONDecodeError) as e:
                raise ValidationException(
                    message='Image pull secret value must be valid Docker config JSON (e.g. {"auths":{"<registry>":{"username":"...","password":"...","auth":"..."}}}). Paste the JSON content, not YAML or other formats.',
                    detail=str(e),
                ) from e

    if secret_in.use_case == SecretUseCase.S3:
        missing = find_missing_s3_credential_types(secret_in.data.keys())
        if missing:
            details = "; ".join(
                f"{name} (one of: {', '.join(alias for alias in S3_REQUIRED_CREDENTIAL_KEYS[name] if '_' not in alias)})"
                for name in missing
            )
            raise ValidationException(message=f"S3 secret is missing required credential key(s): {details}.")

    existing_secrets = await list_kubernetes_secrets(kube_client=kube_client, namespace=namespace)
    for existing in existing_secrets:
        existing_display_name = existing.metadata.annotations.get(DISPLAY_NAME_ANNOTATION) or existing.metadata.name
        if existing_display_name == secret_in.display_name:
            raise ConflictException(
                f"A secret with display name '{secret_in.display_name}' already exists in namespace '{namespace}'"
            )

    _max_retries = 3
    for attempt in range(_max_retries):
        secret_name = generate_secret_name()
        try:
            secret_crd = await create_kubernetes_secret(
                kube_client=kube_client,
                namespace=namespace,
                name=secret_name,
                display_name=secret_in.display_name,
                data=secret_in.data,
                use_case=secret_in.use_case,
                submitter=submitter,
            )
            logger.info(f"Created secret '{secret_in.display_name}' ({secret_name}) in namespace '{namespace}'")
            return SecretResponse.model_validate(secret_crd.model_dump())
        except ApiException as e:
            if e.status == 409 and attempt < _max_retries - 1:
                logger.warning(f"Generated name '{secret_name}' already exists, retrying...")
                continue
            if e.status == 409:
                raise ConflictException(
                    f"Generated K8s name '{secret_name}' already exists in namespace '{namespace}' after {_max_retries} attempts"
                )
            raise

    raise ConflictException(f"Failed to create secret in namespace '{namespace}' after {_max_retries} attempts")


async def delete_secret(
    kube_client: KubernetesClient,
    namespace: str,
    secret_name: str,
) -> None:
    """
    Delete a Kubernetes Secret.

    Raises:
        NotFoundException: If the secret doesn't exist
        ConflictException: If the secret has an ownerReference
    """
    # First, get the secret to check if it has owner references
    secret_crd = await get_kubernetes_secret(kube_client=kube_client, namespace=namespace, name=secret_name)

    if not secret_crd:
        raise NotFoundException(f"Secret '{secret_name}' not found in namespace '{namespace}'")

    # Check if secret has owner references
    if secret_crd.metadata.owner_references:
        raise ConflictException(
            f"Cannot delete secret '{secret_name}' as it is managed by another resource. "
            f"Secrets with ownerReferences must be deleted by their owner."
        )

    try:
        await delete_kubernetes_secret(
            kube_client=kube_client,
            namespace=namespace,
            name=secret_name,
        )
        logger.info(f"Deleted secret '{secret_name}' from namespace '{namespace}'")
    except ApiException as e:
        if e.status == 404:
            raise NotFoundException(f"Secret '{secret_name}' not found in namespace '{namespace}'")
        raise
