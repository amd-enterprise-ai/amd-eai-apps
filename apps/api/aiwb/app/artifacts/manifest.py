# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Generic adapter manifest stored beside the raw PEFT files in S3.

The AIMArtifact CR is the authority for an onboarded adapter; this manifest is a
small, controller-independent mirror written next to the weights so the adapter
can be recovered (or migrated to a future schema) from object storage alone. The
fine-tuning engine writes the same file for adapters it produces, so the reader
must tolerate manifests it did not author.

Deliberately flat and minimal: the manifest's own S3 location defines the adapter
prefix, so the path is never stored in the body.
"""

import asyncio

import yaml
from loguru import logger
from minio.error import S3Error
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from api_common.exceptions import ExternalServiceError, ForbiddenException, NotFoundException, ValidationException
from api_common.schemas import BaseModel

from ..minio import MinioClient
from ..minio.client import map_s3_error_to_domain_exception
from ..minio.config import MINIO_MAX_ATTEMPTS, MINIO_MAX_WAIT, MINIO_MIN_WAIT

ADAPTER_MANIFEST_FILENAME = "adapter-manifest.yaml"

_OBJECT_MISSING_CODE = "NoSuchKey"


class AdapterManifest(BaseModel):
    """Recovery mirror of an adapter's identity, serialized as flat YAML.

    ``modelId`` is the adapter's own HF-style id, ``compatibleWith`` the canonical base-model ids
    it declares itself compatible with, optional so a manifest predating the field still parses.
    ``displayName`` and ``description`` mirror the CR's annotations of the same name so the
    human-facing label and blurb survive a rebuild from object storage.
    """

    model_id: str
    compatible_with: list[str] | None = None
    rank: int | None = None
    display_name: str | None = None
    description: str | None = None


async def read_adapter_manifest(
    minio_client: MinioClient,
    bucket: str,
    key: str,
) -> AdapterManifest | None:
    """Read and parse an adapter manifest from S3, returning ``None`` if absent.

    A genuine not-found is the common case (adapters onboarded before this file
    existed, or raw prefixes) and returns ``None`` so the caller can fall back to
    writing one. Other S3 errors flow through ``map_s3_error_to_domain_exception``;
    malformed YAML or a body that fails validation surfaces as ``ExternalServiceError``
    to flag storage corruption distinctly from a missing file.
    """
    try:
        content = await asyncio.to_thread(minio_client.download_object, bucket, key)
    except S3Error as e:
        if e.code == _OBJECT_MISSING_CODE:
            return None
        logger.error(f"Failed to read adapter manifest at {bucket}/{key}: {e}")
        raise map_s3_error_to_domain_exception(e, f"adapter manifest at {bucket}/{key}") from e

    try:
        loaded = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ExternalServiceError(f"Adapter manifest at {bucket}/{key} is not valid YAML: {e}") from e
    if not isinstance(loaded, dict):
        raise ExternalServiceError(
            f"Adapter manifest at {bucket}/{key} must be a YAML mapping, got {type(loaded).__name__}"
        )
    try:
        return AdapterManifest.model_validate(loaded)
    except ValueError as e:
        raise ExternalServiceError(f"Adapter manifest at {bucket}/{key} is malformed: {e}") from e


@retry(
    # Only transient storage failures are worth retrying. A mapped domain exception (auth, not-found,
    # bad request) is deterministic — retrying it just burns the full backoff budget before failing.
    retry=retry_if_not_exception_type((ForbiddenException, NotFoundException, ValidationException)),
    wait=wait_exponential(multiplier=1, min=MINIO_MIN_WAIT, max=MINIO_MAX_WAIT),
    stop=stop_after_attempt(MINIO_MAX_ATTEMPTS),
    reraise=True,
)
async def write_adapter_manifest(
    minio_client: MinioClient,
    bucket: str,
    key: str,
    manifest: AdapterManifest,
) -> None:
    """Serialize ``manifest`` to flat YAML and upload it to S3.

    ``sort_keys=False`` keeps the field order stable for humans reading the file
    in a bucket browser. The blocking minio-py call is dispatched through a thread.
    """
    payload = yaml.safe_dump(
        manifest.model_dump(by_alias=True, exclude_none=True),
        sort_keys=False,
        default_flow_style=False,
    ).encode("utf-8")
    try:
        await asyncio.to_thread(minio_client.upload_object, bucket_name=bucket, object_name=key, data=payload)
    except S3Error as e:
        logger.error(f"Failed to write adapter manifest at {bucket}/{key}: {e}")
        raise map_s3_error_to_domain_exception(e, f"adapter manifest at {bucket}/{key}") from e
