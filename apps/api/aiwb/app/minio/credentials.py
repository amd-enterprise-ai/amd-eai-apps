# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Shared MinIO credential wiring for resources that read an S3 source."""

from kubernetes_asyncio.client import ApiException
from loguru import logger

from api_common.exceptions import ExternalServiceError, ValidationException

from ..aims.crds import AIMModelSourceEnvVar
from ..dispatch.kube_client import KubernetesClient
from .config import (
    MINIO_CREDENTIALS_ACCESS_KEY_KEY,
    MINIO_CREDENTIALS_SECRET_KEY_KEY,
    MINIO_CREDENTIALS_SECRET_NAME,
    MINIO_URL,
)


def minio_credentials_env() -> list[AIMModelSourceEnvVar]:
    """Environment aim-engine needs to read an S3 source while reconciling a resource.

    The endpoint is the in-cluster one: these are consumed by jobs running next to the storage, not
    by clients uploading to it, which are handed presigned URLs signed for the external endpoint.
    """
    return [
        AIMModelSourceEnvVar.model_validate(
            {
                "name": "AWS_ACCESS_KEY_ID",
                "valueFrom": {
                    "secretKeyRef": {"name": MINIO_CREDENTIALS_SECRET_NAME, "key": MINIO_CREDENTIALS_ACCESS_KEY_KEY}
                },
            }
        ),
        AIMModelSourceEnvVar.model_validate(
            {
                "name": "AWS_SECRET_ACCESS_KEY",
                "valueFrom": {
                    "secretKeyRef": {"name": MINIO_CREDENTIALS_SECRET_NAME, "key": MINIO_CREDENTIALS_SECRET_KEY_KEY}
                },
            }
        ),
        AIMModelSourceEnvVar.model_validate({"name": "AWS_ENDPOINT_URL", "value": MINIO_URL}),
    ]


async def verify_minio_credentials_secret(kube_client: KubernetesClient, namespace: str) -> None:
    """Raise ValidationException (400) when the MinIO credentials secret is absent.

    Resources that reference an S3 source name this secret rather than carrying credentials inline,
    so aim-engine's reconciliation jobs cannot authenticate without it. The check is per request
    because the secret is provisioned per project namespace and can lag behind namespace creation.
    Failing here gives the caller an actionable error instead of a resource that is accepted and
    then silently never reconciles.
    """
    try:
        await kube_client.core_v1.read_namespaced_secret(name=MINIO_CREDENTIALS_SECRET_NAME, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            raise ValidationException(
                f"Secret '{MINIO_CREDENTIALS_SECRET_NAME}' not found in namespace '{namespace}'. "
                "This secret must be provisioned before S3-backed resources can be created. "
                "Contact your platform administrator to ensure MinIO credentials are configured for this namespace."
            ) from e
        logger.error(f"Failed to read MinIO credentials secret in namespace '{namespace}': {e}")
        raise ExternalServiceError(
            f"Failed to verify MinIO credentials secret in namespace '{namespace}': {e.reason}"
        ) from e
