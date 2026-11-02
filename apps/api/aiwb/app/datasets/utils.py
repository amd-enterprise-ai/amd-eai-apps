# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import os
import re
from collections.abc import Generator

from fastapi import UploadFile
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from api_common.exceptions import ValidationException
from api_common.slugs import slugify

from ..minio.client import MinioClient, handle_s3_operation
from ..minio.config import MINIO_BUCKET, MINIO_MAX_ATTEMPTS, MINIO_MAX_WAIT, MINIO_MIN_WAIT
from ..minio.exceptions import S3SyncError
from .config import (
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
)
from .models import Dataset


def get_object_key(dataset_id: str, namespace: str) -> str:
    """
    Generate the S3 object key for a dataset.

    Format: {namespace}/datasets/{dataset_id}.jsonl

    Uses the dataset UUID as the filename to decouple S3 paths from display names.
    This prevents path collisions when display names contain special characters or
    when two names would slugify to the same string.
    """
    slugified_project = slugify(namespace)
    return f"{slugified_project}/datasets/{dataset_id}.jsonl"


def derive_name_from_path(s3_key: str) -> str:
    """
    Derive a dataset name from an S3 key.
    - Extract the filename from the path
    - Remove common extensions
    - Convert hyphens to spaces for better readability
    """
    # Extract the filename (last part of the path)
    filename = os.path.basename(s3_key)

    # Remove common extensions
    name = re.sub(r"\.jsonl$|\.json$|\.csv$|\.txt$", "", filename)

    # Convert hyphens to spaces for better readability
    name = name.replace("-", " ").replace("_", " ")

    # Capitalize first letter of each word for better presentation
    name = " ".join(word.capitalize() for word in name.split())

    return name


def clean_s3_path(path: str) -> str:
    """
    Clean and validate an S3 path provided by the user.
    - Handle s3:// protocol prefixes
    - Extract just the key if a bucket is specified
    - Validate the bucket if present

    Returns the cleaned key without bucket name.
    """
    # Remove s3:// protocol if present
    if path.startswith("s3://"):
        path = path[5:]

    # Check if the path contains a bucket prefix that matches our expected bucket name
    # This prevents common directory names like "datasets" from being mistaken for bucket names
    parts = path.split("/", 1)
    if len(parts) == 2 and parts[0] == MINIO_BUCKET:
        bucket, key = parts
        return key

    # If no bucket specified, assume it's just the key
    return path


async def verify_s3_sync(client: MinioClient, bucket: str, object_key: str, content: bytes) -> bool:
    with handle_s3_operation("verifying upload", f"s3://{bucket}/{object_key}"):
        # Check if object exists - will raise S3Error if not found
        stat = await asyncio.to_thread(client.client.stat_object, bucket, object_key)

        # Compare sizes
        if stat.size != len(content):
            raise S3SyncError("Size mismatch between local and S3 files")

        return True


@retry(
    wait=wait_exponential(multiplier=1, min=MINIO_MIN_WAIT, max=MINIO_MAX_WAIT),
    stop=stop_after_attempt(MINIO_MAX_ATTEMPTS),
    reraise=True,
)
async def sync_dataset_to_s3(dataset: Dataset, file: UploadFile, client: MinioClient) -> str:
    """
    Upload a dataset file to S3 and return the full path
    """
    # The dataset.path already contains the full S3 key
    object_key = dataset.path
    dataset_path = os.path.join(MINIO_BUCKET, object_key)
    logger.info(f"Uploading dataset {dataset.id} to S3 as {dataset_path}")

    with handle_s3_operation("uploading dataset", f"s3://{MINIO_BUCKET}/{object_key}", dataset.id):
        # Upload file
        content = await file.read()
        client.upload_object(bucket_name=MINIO_BUCKET, object_name=object_key, data=content)

        # Verify upload - will raise S3Error or S3SyncError on failure
        await verify_s3_sync(client, MINIO_BUCKET, object_key, content)

    logger.info(f"Successfully uploaded and verified dataset {dataset.id} to S3")
    return dataset_path


def download_from_s3_stream(dataset: Dataset, client: MinioClient) -> Generator[bytes]:
    """
    Stream dataset from S3 in chunks without loading into memory.

    Args:
        dataset: Dataset model with path information
        client: MinioClient instance

    Yields:
        bytes: Chunks of the dataset file (8KB each)
    """
    object_key = dataset.path
    logger.info(f"Streaming dataset {dataset.id} from S3: {object_key}")

    with handle_s3_operation("streaming dataset", f"s3://{MINIO_BUCKET}/{object_key}", dataset.id):
        yield from client.stream_object(MINIO_BUCKET, object_key)

    logger.info(f"Successfully streamed dataset {dataset.id} from S3")


@retry(
    wait=wait_exponential(multiplier=1, min=MINIO_MIN_WAIT, max=MINIO_MAX_WAIT),
    stop=stop_after_attempt(MINIO_MAX_ATTEMPTS),
    reraise=True,
)
async def delete_from_s3(dataset: Dataset, client: MinioClient) -> None:
    """
    Deletes file with Minio
    """
    # dataset.path now only contains the key portion, bucket is known
    object_key = dataset.path

    with handle_s3_operation("deleting dataset", f"s3://{MINIO_BUCKET}/{object_key}", dataset.id):
        await asyncio.to_thread(client.delete_object, bucket_name=MINIO_BUCKET, object_name=object_key)
        logger.info(f"Successfully deleted dataset {dataset.id} from S3: {object_key}")


def validate_jsonl(file: UploadFile) -> None:
    if not file.filename.endswith(".jsonl"):
        raise ValidationException(message="Invalid file format. Only .jsonl files are allowed.")

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValidationException(message=f"File size exceeds {MAX_FILE_SIZE_MB}MB limit.")
