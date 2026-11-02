# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from fastapi import Request
from loguru import logger

from api_common.exceptions import ExternalServiceError

from .client import MinioClient
from .config import MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_URL


def init_minio_client(host: str | None = None) -> MinioClient | None:
    """Initialize a Minio client. This will be called at application startup.

    Defaults to the in-cluster endpoint. Pass MINIO_EXTERNAL_URL to build the client that signs
    URLs for callers outside the cluster; credentials and bucket are shared either way.
    Returns None if initialization fails.
    """
    endpoint = host or MINIO_URL
    try:
        if not MINIO_ACCESS_KEY or not endpoint or not MINIO_SECRET_KEY:
            logger.warning("Minio not fully configured. Minio features will be unavailable.")
            return None

        client = MinioClient(
            host=endpoint,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
        )

        logger.info(f"Connected to Minio server at {endpoint}")
        return client
    except Exception as e:
        logger.warning(f"Failed to initialize Minio client: {e}")
        return None


# Absent storage is the same class of failure as storage that refuses or cannot be reached, so the
# strict dependencies below report it with the exception the rest of the storage path already uses.
_STORAGE_UNAVAILABLE = (
    "Object storage is not available. It may not be configured for this deployment, or its client "
    "failed to initialize at startup."
)


def get_minio_client(request: Request) -> MinioClient:
    """FastAPI dependency to get the initialized Minio client from app.state."""
    if not hasattr(request.app.state, "minio_client") or request.app.state.minio_client is None:
        logger.error("Minio client not initialized in app.state. Check Minio configuration.")
        raise ExternalServiceError(_STORAGE_UNAVAILABLE)
    return request.app.state.minio_client


def get_minio_client_optional(request: Request) -> MinioClient | None:
    """FastAPI dependency to get the initialized Minio client, or None if unavailable.

    Unlike ``get_minio_client``, this never raises. For routes where a Minio-backed signal is
    best-effort (e.g. a display-only readiness check) rather than required for the request to
    succeed, raising here would fail the whole request instead of the degraded response the
    route already knows how to produce.
    """
    return getattr(request.app.state, "minio_client", None)


def get_minio_external_client(request: Request) -> MinioClient:
    """FastAPI dependency to get the presigning Minio client from app.state."""
    if not hasattr(request.app.state, "minio_external_client") or request.app.state.minio_external_client is None:
        logger.error("External Minio client not initialized in app.state. Check Minio configuration.")
        raise ExternalServiceError(_STORAGE_UNAVAILABLE)
    return request.app.state.minio_external_client
