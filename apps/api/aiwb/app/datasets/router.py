# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from textwrap import dedent
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api_common.auth.security import get_user_email
from api_common.collections import PaginationMetadata
from api_common.database import get_session
from api_common.schemas import QueryParam

from ..common_responses import PROJECT_ACCESS_RESPONSES
from ..minio import MinioClient, get_minio_client
from ..projects.security import ensure_access_to_project
from .config import MAX_FILE_SIZE_MB
from .models import DatasetType
from .schemas import DatasetResponse, DatasetsList, ListDatasetsQuery
from .service import (
    create_and_upload_dataset,
    delete_dataset,
    download_dataset_file,
    get_dataset_by_id,
    list_paginated_datasets,
)

router = APIRouter(tags=["Datasets"])


@router.post(
    "/projects/{project}/datasets",
    response_model=DatasetResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload a dataset to a project",
    description=dedent(f"""
        Upload a JSONL dataset into the project's storage.

        The request is `multipart/form-data`: send the file in `jsonl` and
        the metadata (`name`, `description`, `type`) as form fields. The
        file must be valid JSONL (one JSON object per line). Maximum file
        size is {MAX_FILE_SIZE_MB} MB; larger files are rejected at the
        storage backend.

        The dataset is persisted to S3 under a project-scoped object key
        and a matching DB record is created in a single atomic operation
        — either both succeed or both are rolled back.

        Requires project access. The dataset is owned by the project and
        is not visible from other projects.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        400: {"description": "File is not valid JSONL or violates schema."},
        409: {"description": "A dataset with this name already exists in the project."},
        500: {"description": "S3 upload failed (storage backend error or oversized file)."},
    },
)
async def upload_dataset(
    name: str = Form(
        ...,
        description="The name for the dataset (unique within the project).",
        examples=["imdb-sentiment-v1"],
    ),
    description: str | None = Form(
        default=None,
        description="Optional free-form description of the dataset's contents.",
        examples=["IMDB reviews labelled positive/negative; 25k train / 25k test"],
    ),
    type: DatasetType = Form(
        ...,
        description="The type of the dataset.",
        examples=["Fine-tuning"],
    ),
    jsonl: UploadFile = File(..., description="The JSONL file to upload"),
    author: str = Depends(get_user_email),
    session: AsyncSession = Depends(get_session),
    minio_client: MinioClient = Depends(get_minio_client),
    project: str = Depends(ensure_access_to_project),
) -> DatasetResponse:
    dataset = await create_and_upload_dataset(
        session=session,
        name=name,
        description=description,
        type=type,
        file=jsonl,
        author=author,
        namespace=project,
        minio_client=minio_client,
    )
    return DatasetResponse.model_validate(dataset).model_copy(update={"size_bytes": jsonl.size})


@router.get(
    "/projects/{project}/datasets",
    response_model=DatasetsList,
    status_code=status.HTTP_200_OK,
    summary="List datasets in a project",
    description=dedent("""
        List datasets that have been uploaded into the project as a paginated
        envelope (default page size 10, max 100). Use `?page=` and `?pageSize=`
        to navigate; the response includes a `pagination` object with `page`,
        `pageSize`, and `total` alongside `data`.

        Use `?type=` to filter by dataset kind (exact match) and `?name=`
        to filter by name (exact match). The two filters compose. Pagination
        is applied after filtering, so `total` reflects the filtered set.

        Requires project access.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
    },
)
async def get_datasets(
    query: QueryParam[ListDatasetsQuery],
    session: AsyncSession = Depends(get_session),
    minio_client: MinioClient = Depends(get_minio_client),
    project: str = Depends(ensure_access_to_project),
) -> DatasetsList:
    paginated = await list_paginated_datasets(
        session=session,
        namespace=project,
        type=query.type,
        name=query.name,
        page=query.page,
        page_size=query.page_size,
        minio_client=minio_client,
    )
    return DatasetsList(
        data=paginated.items,
        pagination=PaginationMetadata(
            page=paginated.page,
            page_size=paginated.page_size,
            total=paginated.total,
        ),
    )


@router.get(
    "/projects/{project}/datasets/{dataset_id}",
    response_model=DatasetResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a dataset in a project",
    description=dedent("""
        Get metadata for a single dataset by id (name, description, type,
        S3 path, and file size in bytes). The file size is null when object
        storage metadata is unavailable. Does not return the dataset contents
        — use the download endpoint to fetch the JSONL bytes.

        Requires project access.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        404: {"description": "Project or namespace not found, or dataset not found in the project."},
    },
)
async def get_dataset(
    dataset_id: UUID,
    session: AsyncSession = Depends(get_session),
    minio_client: MinioClient = Depends(get_minio_client),
    project: str = Depends(ensure_access_to_project),
) -> DatasetResponse:
    return await get_dataset_by_id(session, dataset_id, project, minio_client)


@router.get(
    "/projects/{project}/datasets/{dataset_id}/download",
    status_code=status.HTTP_200_OK,
    summary="Download a dataset file",
    description=dedent("""
        Stream the dataset's JSONL contents back from S3 as an
        `application/jsonl` attachment. The response is streamed (not
        loaded into memory), so it is safe for datasets larger than the
        API server's heap.

        Requires project access.
    """),
    response_description="Streaming JSONL bytes; safe for files larger than memory.",
    responses={
        **PROJECT_ACCESS_RESPONSES,
        404: {"description": "Project or namespace not found, or dataset not found, or has no uploaded content."},
    },
)
async def download_dataset(
    dataset_id: UUID,
    session: AsyncSession = Depends(get_session),
    minio_client: MinioClient = Depends(get_minio_client),
    project: str = Depends(ensure_access_to_project),
) -> StreamingResponse:
    return await download_dataset_file(dataset_id, project, session, minio_client)


@router.delete(
    "/projects/{project}/datasets/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a dataset from a project",
    description=dedent("""
        Permanently delete a dataset from the project.

        Cascades: removes both the DB record and the backing S3 object.
        The DB delete is the authoritative step; if the subsequent S3
        delete fails the dataset still disappears from the API and the
        orphaned object is logged for out-of-band cleanup. Calling delete
        on a missing dataset is a no-op (idempotent).

        Requires project access.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
    },
)
async def delete_dataset_endpoint(
    dataset_id: UUID,
    session: AsyncSession = Depends(get_session),
    minio_client: MinioClient = Depends(get_minio_client),
    project: str = Depends(ensure_access_to_project),
) -> None:
    await delete_dataset(session, dataset_id, project, minio_client)
