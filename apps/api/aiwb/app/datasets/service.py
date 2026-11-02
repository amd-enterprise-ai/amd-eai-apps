# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
from uuid import UUID, uuid4

from fastapi import UploadFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api_common.collections import PaginatedResult, paginate_list
from api_common.exceptions import (
    ConflictException,
    NotFoundException,
    UploadFailedException,
    ValidationException,
)
from api_common.slugs import slugify

from ..minio.config import MINIO_BUCKET
from . import repository
from .models import Dataset, DatasetType
from .schemas import DatasetResponse
from .utils import (
    MinioClient,
    delete_from_s3,
    download_from_s3_stream,
    get_object_key,
    sync_dataset_to_s3,
    validate_jsonl,
)


async def create_and_upload_dataset(
    session: AsyncSession,
    name: str,
    description: str | None,
    type: DatasetType,
    file: UploadFile,
    author: str,
    namespace: str,
    minio_client: MinioClient,
) -> Dataset:
    """
    Create a new dataset with user-provided name and upload its content.
    The path will be generated based on the name and project name using a slug format.

    This function implements a two-phase process:
    1. Create a database record with a generated path
    2. Upload the file to S3 at that path

    If either step fails, the entire transaction is rolled back by the API layer.

    Raises:
        ValidationException: If validation fails
        ConflictException: If a dataset with the same name exists
        UploadFailedException: If there are issues with S3 upload
    """
    try:
        # Validate the file first to avoid unnecessary database operations if validation fails
        validate_jsonl(file)
    except Exception as e:
        # Handle validation errors
        logger.error(f"Validation error for dataset {name}: {e}")
        raise ValidationException(
            message="Failed to validate dataset file, please ensure it is a valid JSONL file with the correct format.",
            detail=str(e),
        )

    dataset_db = None

    try:
        # Generate a new UUID for the dataset
        dataset_id = uuid4()

        # Generate the S3 object key using the dataset UUID so display names can contain
        # any characters without risking S3 path collisions from slugify normalisation.
        object_key = get_object_key(str(dataset_id), namespace)

        # Create the dataset record with the generated path
        dataset_db = await repository.insert_dataset(
            session,
            id=dataset_id,
            name=name,
            creator=author,
            description=description,
            namespace=namespace,
            type=type,
            path=object_key,
        )

        # Ensure the dataset record is created
        await session.flush()

        # Upload the file to S3
        try:
            await file.seek(0)
            await sync_dataset_to_s3(dataset_db, file, minio_client)

        except Exception as e:
            logger.error(f"Failed to upload dataset file for {name} (ID: {dataset_db.id}): {e}")
            raise UploadFailedException(
                message="Failed to upload dataset file to storage",
                detail=str(e),
            )

        return dataset_db

    except (ValidationException, NotFoundException, ConflictException, UploadFailedException):
        # Re-raise known domain exceptions as is without wrapping them
        raise

    except Exception as e:
        # For any other unexpected exceptions
        logger.error(f"Failed to insert dataset record for {name}: {e}")
        raise UploadFailedException(
            message="Failed to create dataset record in database.",
            detail=str(e),
        )


async def download_dataset_file(
    dataset_id: UUID, namespace: str, session: AsyncSession, minio_client: MinioClient
) -> StreamingResponse:
    """
    Stream a dataset file from S3 storage without loading into memory.

    This uses streaming to prevent:
    - Memory exhaustion on large files
    - Event loop blocking in frontend proxies
    - Gateway timeouts on slow downloads

    Raises:
        NotFoundException: If the dataset is not found or has no content
    """
    dataset = await repository.select_dataset(session, dataset_id, namespace)
    if not dataset:
        raise NotFoundException(message=f"Dataset {dataset_id} not found")

    # Check if the dataset has content uploaded (i.e., a path is set)
    if not dataset.path:
        raise NotFoundException(message=f"Dataset {dataset_id} has no content to download.")

    object_key = dataset.path
    file_name = object_key.split("/")[-1]

    # stat_object is a blocking call; run it in a thread to get Content-Length before streaming.
    stat = await asyncio.to_thread(minio_client.stat_object, MINIO_BUCKET, object_key)

    return StreamingResponse(
        download_from_s3_stream(dataset, minio_client),
        media_type="application/jsonl; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Content-Length": str(stat.size),
        },
    )


def _dataset_response(dataset: Dataset, size_bytes: int | None) -> DatasetResponse:
    return DatasetResponse.model_validate(dataset).model_copy(update={"size_bytes": size_bytes})


async def get_dataset_by_id(
    session: AsyncSession,
    dataset_id: UUID,
    namespace: str,
    minio_client: MinioClient,
) -> DatasetResponse:
    """Get a dataset by ID, raising NotFoundException if not found."""
    dataset = await repository.select_dataset(session, dataset_id, namespace)
    if not dataset:
        raise NotFoundException(f"Dataset with ID {dataset_id} not found")
    try:
        stat = await asyncio.to_thread(minio_client.stat_object, MINIO_BUCKET, dataset.path)
        size_bytes = stat.size
    except Exception as e:
        logger.warning(f"Failed to read size for dataset {dataset_id}: {e}")
        size_bytes = None
    return _dataset_response(dataset, size_bytes)


async def list_paginated_datasets(
    session: AsyncSession,
    namespace: str,
    type: DatasetType | None,
    name: str | None,
    page: int,
    page_size: int,
    minio_client: MinioClient,
) -> PaginatedResult[DatasetResponse]:
    datasets = await repository.list_datasets(
        session=session,
        namespace=namespace,
        type=type,
        name=name,
    )
    sizes: dict[str, int] = {}
    if datasets:
        prefix = f"{slugify(namespace)}/datasets/"
        try:
            sizes = await asyncio.to_thread(minio_client.get_object_sizes, MINIO_BUCKET, prefix)
        except Exception as e:
            logger.warning(f"Failed to read dataset sizes for namespace {namespace}: {e}")

    responses = [_dataset_response(dataset, sizes.get(dataset.path)) for dataset in datasets]

    # Paginate after filtering so `total` reflects the filtered set.
    return paginate_list(responses, page=page, page_size=page_size)


async def delete_dataset(session: AsyncSession, dataset_id: UUID, namespace: str, minio_client: MinioClient) -> None:
    """Delete a single dataset from database and S3 storage. Idempotent."""
    dataset = await repository.select_dataset(session, dataset_id, namespace)
    if dataset is None:
        return
    await repository.delete_dataset_by_id(session, dataset_id, namespace)
    try:
        await delete_from_s3(dataset, minio_client)
    except Exception as e:
        logger.warning(f"S3 deletion failed for dataset {dataset_id}: {e}")
