# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import os

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from api_common.exceptions import ValidationException
from api_common.slugs import slugify

from ..minio import MinioClient
from ..minio.client import handle_s3_operation
from ..minio.config import MINIO_BUCKET, MINIO_MAX_ATTEMPTS, MINIO_MAX_WAIT, MINIO_MIN_WAIT


class InvalidPathError(ValidationException):
    """Exception raised when a path doesn't follow project scoping conventions"""

    pass


def get_finetuned_model_weights_path(base_canonical_name: str, finetuning_name: str, project_name: str) -> str:
    slugified_project = slugify(project_name)
    return os.path.join(slugified_project, "finetuned-models", base_canonical_name, finetuning_name)


def get_custom_model_manifest_path(namespace: str, resource_name: str) -> str:
    """S3 key for the YAML manifest of a custom (BYOM) AIMModel.

    Format: {slugified_namespace}/custom-models/{resource_name}/manifest.yaml.
    The resource_name is the AIMModel CR's `metadata.name`, which is the only
    stable, deterministic identifier we need: it never changes, it's unique
    within the namespace, and the CR itself is the link between the cluster
    record and the manifest in object storage.
    """
    return os.path.join(slugify(namespace), "custom-models", resource_name, "manifest.yaml")


def get_custom_model_root_path(namespace: str, resource_name: str) -> str:
    """S3 key prefix for the entire object-storage tree of a custom (BYOM) AIMModel.

    Format: {slugified_namespace}/custom-models/{resource_name}/.
    This is the common parent of both the ``manifest.yaml`` mirror and the
    ``weights/`` tree, so a single recursive delete under this prefix reclaims
    all workbench-owned object storage for the model. aim-engine downloads
    *from* the weights URI into a PVC and never writes here, so this tree is
    the workbench's to clean up.
    """
    return os.path.join(slugify(namespace), "custom-models", resource_name) + "/"


def get_adapter_artifacts_root(namespace: str) -> str:
    """S3 key prefix holding every adapter artifact the platform allocates for a project.

    Format: {slugified_namespace}/adapters/
    One level below it is one adapter, which is what makes a single listing under this root
    enough to discover adapters whose weights exist without a CR backing them.
    """
    return os.path.join(slugify(namespace), "adapters") + "/"


def get_adapter_artifact_prefix(namespace: str, resource_name: str) -> str:
    """S3 key prefix for a LoRA adapter artifact.

    Format: {slugified_namespace}/adapters/{resource_name}/
    """
    return f"{get_adapter_artifacts_root(namespace)}{resource_name}/"


def get_custom_model_weights_path(namespace: str, resource_name: str) -> str:
    """S3 key prefix where weights for a custom (BYOM) AIMModel are imported.

    Format: {slugified_namespace}/custom-models/{resource_name}/weights/.
    This is the object-storage tree that inference loads from (shards, config,
    tokenizer). A sibling ticket performs the actual Hub-to-S3 weight import;
    this PR only writes the prefix into AIMModel.spec.modelSources[0].sourceUri
    so the manifest is fully formed from day one.
    """
    return os.path.join(slugify(namespace), "custom-models", resource_name, "weights") + "/"


@retry(
    wait=wait_exponential(multiplier=1, min=MINIO_MIN_WAIT, max=MINIO_MAX_WAIT),
    stop=stop_after_attempt(MINIO_MAX_ATTEMPTS),
    reraise=True,
)
async def delete_from_s3(
    prefix: str, client: MinioClient, model_name: str = "", operation: str = "deleting model weights"
) -> None:
    with handle_s3_operation(operation, f"s3://{MINIO_BUCKET}/{prefix}", model_name):
        await asyncio.to_thread(client.delete_objects, bucket_name=MINIO_BUCKET, prefix=prefix)
        logger.info(f"Finished {operation} from S3: {prefix}")


@retry(
    wait=wait_exponential(multiplier=1, min=MINIO_MIN_WAIT, max=MINIO_MAX_WAIT),
    stop=stop_after_attempt(MINIO_MAX_ATTEMPTS),
    reraise=True,
)
async def delete_object_from_s3(
    object_key: str, client: MinioClient, model_name: str = "", operation: str = "deleting model folder marker"
) -> None:
    with handle_s3_operation(operation, f"s3://{MINIO_BUCKET}/{object_key}", model_name):
        await asyncio.to_thread(client.delete_object, bucket_name=MINIO_BUCKET, object_name=object_key)
        logger.info(f"Finished {operation} from S3: {object_key}")
