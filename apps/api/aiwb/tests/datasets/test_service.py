# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Datasets service tests."""

import io
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ConflictException, NotFoundException, UploadFailedException, ValidationException
from app.datasets.models import DatasetType
from app.datasets.repository import list_datasets, select_dataset
from app.datasets.service import (
    create_and_upload_dataset,
    delete_dataset,
    download_dataset_file,
    get_dataset_by_id,
    list_paginated_datasets,
)
from app.minio import MinioClient
from tests import factory


@pytest.mark.asyncio
async def test_create_and_upload_dataset_success(db_session: AsyncSession, test_namespace: str, test_user: str) -> None:
    """Test complete dataset creation and upload workflow."""
    file_content = b'{"text": "test"}\n{"text": "test2"}'
    upload_file = UploadFile(filename="test-upload.jsonl", file=io.BytesIO(file_content))

    name = "Test Upload"
    description = "Uploaded dataset"
    dataset_type = DatasetType.FINETUNING

    with (
        patch("app.datasets.service.validate_jsonl") as mock_validate,
        patch("app.datasets.service.sync_dataset_to_s3") as mock_sync,
    ):
        mock_client = AsyncMock(spec=MinioClient)

        result = await create_and_upload_dataset(
            db_session,
            name,
            description,
            dataset_type,
            upload_file,
            test_user,
            test_namespace,
            mock_client,
        )

    assert result.name == name
    assert result.description == description
    assert result.type == dataset_type
    assert result.namespace == test_namespace
    assert result.created_by == test_user

    mock_validate.assert_called_once_with(upload_file)
    mock_sync.assert_called_once_with(result, upload_file, mock_client)

    db_dataset = await select_dataset(db_session, result.id, test_namespace)
    assert db_dataset is not None


@pytest.mark.asyncio
async def test_create_and_upload_dataset_minio_failure(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Test dataset creation when Minio upload fails."""
    file_content = b'{"text": "test"}\n'
    upload_file = UploadFile(filename="test-upload.jsonl", file=io.BytesIO(file_content))

    with (
        patch("app.datasets.service.validate_jsonl") as mock_validate,
        patch("app.datasets.service.sync_dataset_to_s3") as mock_sync,
    ):
        mock_client = AsyncMock(spec=MinioClient)
        mock_sync.side_effect = UploadFailedException("Minio upload failed")

        with pytest.raises(UploadFailedException, match="Failed to upload dataset file to storage"):
            await create_and_upload_dataset(
                db_session,
                "Test Upload",
                "Failed upload",
                DatasetType.FINETUNING,
                upload_file,
                test_user,
                test_namespace,
                mock_client,
            )


@pytest.mark.asyncio
async def test_create_and_upload_dataset_duplicate_name(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Test that duplicate dataset names raise ConflictException."""
    # Create existing dataset
    await factory.create_dataset(
        db_session, name="Existing Dataset", path="existing-dataset.jsonl", namespace=test_namespace
    )

    file_content = b'{"text": "test"}\n'
    upload_file = UploadFile(filename="duplicate.jsonl", file=io.BytesIO(file_content))

    with patch("app.datasets.service.validate_jsonl"):
        mock_client = AsyncMock(spec=MinioClient)

        with pytest.raises(ConflictException, match="already exists"):
            await create_and_upload_dataset(
                db_session,
                "Existing Dataset",  # Duplicate name
                "Duplicate dataset",
                DatasetType.FINETUNING,
                upload_file,
                test_user,
                test_namespace,
                mock_client,
            )


@pytest.mark.asyncio
async def test_create_and_upload_dataset_validation_failure(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Test dataset creation when validation fails."""
    file_content = b"invalid json content"
    upload_file = UploadFile(filename="invalid.jsonl", file=io.BytesIO(file_content))

    with patch("app.datasets.service.validate_jsonl") as mock_validate:
        mock_validate.side_effect = ValidationException("Invalid JSONL format")
        mock_client = AsyncMock(spec=MinioClient)

        with pytest.raises(ValidationException):
            await create_and_upload_dataset(
                db_session,
                "Invalid Dataset",
                "Invalid upload",
                DatasetType.FINETUNING,
                upload_file,
                test_user,
                test_namespace,
                mock_client,
            )


@pytest.mark.asyncio
async def test_download_dataset_file_success(db_session: AsyncSession, test_namespace: str, test_user: str) -> None:
    """Test successful dataset file download using streaming."""
    dataset = await factory.create_dataset(
        db_session, name="Download Test Dataset", path="download-test.jsonl", namespace=test_namespace
    )

    mock_file_content = b'{"text": "dataset content"}\n'

    def mock_stream():
        yield mock_file_content

    with patch("app.datasets.service.download_from_s3_stream") as mock_download:
        mock_download.return_value = mock_stream()

        mock_client = AsyncMock(spec=MinioClient)
        mock_stat = MagicMock()
        mock_stat.size = len(mock_file_content)
        mock_client.stat_object.return_value = mock_stat

        response = await download_dataset_file(dataset.id, test_namespace, db_session, mock_client)

        assert response is not None
        assert response.media_type == "application/jsonl; charset=utf-8"
        assert "download-test.jsonl" in response.headers["Content-Disposition"]
        assert response.headers["Content-Length"] == str(len(mock_file_content))

        mock_download.assert_called_once_with(dataset, mock_client)
        mock_client.stat_object.assert_called_once()


@pytest.mark.asyncio
async def test_download_dataset_file_not_found(db_session: AsyncSession, test_namespace: str) -> None:
    """Test downloading non-existent dataset file."""
    non_existent_id = uuid4()

    mock_client = AsyncMock(spec=MinioClient)
    with pytest.raises(NotFoundException, match="Dataset.*not found"):
        await download_dataset_file(non_existent_id, test_namespace, db_session, mock_client)


@pytest.mark.asyncio
async def test_get_dataset_by_id_success(
    db_session: AsyncSession,
    test_namespace: str,
    test_user: str,
    mock_minio_client: MinioClient,
) -> None:
    """Test retrieving a dataset by ID."""
    dataset = await factory.create_dataset(
        db_session, name="Test Dataset", path="test-dataset.jsonl", namespace=test_namespace
    )

    result = await get_dataset_by_id(db_session, dataset.id, test_namespace, mock_minio_client)

    assert result.id == dataset.id
    assert result.name == dataset.name
    assert result.size_bytes == len(b'{"text": "test"}\n{"text": "test2"}')


@pytest.mark.asyncio
async def test_get_dataset_by_id_not_found(
    db_session: AsyncSession,
    test_namespace: str,
    mock_minio_client: MinioClient,
) -> None:
    """Test retrieving non-existent dataset raises NotFoundException."""
    non_existent_id = uuid4()

    with pytest.raises(NotFoundException, match="Dataset.*not found"):
        await get_dataset_by_id(db_session, non_existent_id, test_namespace, mock_minio_client)


@pytest.mark.asyncio
async def test_get_dataset_by_id_returns_unknown_size_when_storage_fails(
    db_session: AsyncSession,
    test_namespace: str,
    mock_minio_client: MinioClient,
) -> None:
    dataset = await factory.create_dataset(
        db_session,
        name="Test Dataset",
        path="test-dataset.jsonl",
        namespace=test_namespace,
    )
    mock_minio_client.stat_object.side_effect = RuntimeError("storage unavailable")

    result = await get_dataset_by_id(db_session, dataset.id, test_namespace, mock_minio_client)

    assert result.size_bytes is None


@pytest.mark.asyncio
async def test_delete_dataset_success(db_session: AsyncSession, test_namespace: str, test_user: str) -> None:
    """Test successful deletion of a single dataset."""
    dataset = await factory.create_dataset(
        db_session, name="Dataset 1", path="dataset-1.jsonl", namespace=test_namespace
    )

    with patch("app.datasets.service.delete_from_s3") as mock_delete_s3:
        mock_client = AsyncMock(spec=MinioClient)

        result = await delete_dataset(db_session, dataset.id, test_namespace, mock_client)

        assert result is None

        # Verify S3 deletion was called once for the dataset
        assert mock_delete_s3.call_count == 1

        # Verify dataset is deleted from database
        remaining = await list_datasets(db_session, test_namespace)
        assert len(remaining) == 0


@pytest.mark.asyncio
async def test_delete_dataset_not_found(db_session: AsyncSession, test_namespace: str) -> None:
    """Test deletion of non-existent dataset is idempotent (returns None, no error)."""
    non_existent_id = uuid4()

    with patch("app.datasets.service.delete_from_s3") as mock_delete_s3:
        mock_client = AsyncMock(spec=MinioClient)

        result = await delete_dataset(db_session, non_existent_id, test_namespace, mock_client)

        assert result is None
        # S3 deletion should NOT be attempted for non-existent dataset
        mock_delete_s3.assert_not_called()


@pytest.mark.asyncio
async def test_delete_dataset_s3_failure_continues(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Test that S3 deletion failure doesn't prevent database deletion."""
    dataset = await factory.create_dataset(
        db_session, name="Test Dataset", path="test-dataset.jsonl", namespace=test_namespace
    )

    with patch("app.datasets.service.delete_from_s3") as mock_delete_s3:
        mock_delete_s3.side_effect = Exception("S3 deletion failed")
        mock_client = AsyncMock(spec=MinioClient)

        # Deletion should still succeed (no exception raised)
        result = await delete_dataset(db_session, dataset.id, test_namespace, mock_client)

        assert result is None

        # Verify dataset is deleted from database even though S3 deletion failed
        remaining = await list_datasets(db_session, test_namespace)
        assert len(remaining) == 0


@pytest.mark.asyncio
async def test_delete_dataset_namespace_isolation(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Test that datasets can only be deleted from their own namespace."""
    other_namespace = "other-namespace"

    # Create dataset in test_namespace
    dataset = await factory.create_dataset(
        db_session, name="Test Dataset", path="test-dataset.jsonl", namespace=test_namespace
    )

    with patch("app.datasets.service.delete_from_s3") as mock_delete_s3:
        mock_client = AsyncMock(spec=MinioClient)

        # Try to delete from different namespace - idempotent no-op
        result = await delete_dataset(db_session, dataset.id, other_namespace, mock_client)

        assert result is None
        # S3 deletion should NOT be attempted when dataset is in a different namespace
        mock_delete_s3.assert_not_called()

    # Verify dataset still exists in original namespace
    found = await select_dataset(db_session, dataset.id, test_namespace)
    assert found is not None


# ============================================================================
# list_paginated_datasets
# ============================================================================


@pytest.mark.asyncio
async def test_list_paginated_datasets_empty(
    db_session: AsyncSession,
    test_namespace: str,
    mock_minio_client: MinioClient,
) -> None:
    """An empty namespace yields an empty page with total=0."""
    result = await list_paginated_datasets(
        session=db_session,
        namespace=test_namespace,
        type=None,
        name=None,
        page=1,
        page_size=10,
        minio_client=mock_minio_client,
    )

    assert result.items == []
    assert result.total == 0
    assert result.page == 1
    assert result.page_size == 10


@pytest.mark.asyncio
async def test_list_paginated_datasets_single_page(
    db_session: AsyncSession,
    test_namespace: str,
    mock_minio_client: MinioClient,
) -> None:
    """When the row count is below page_size, all rows are returned on page 1."""
    for i in range(3):
        await factory.create_dataset(db_session, name=f"Dataset {i}", path=f"ds-{i}.jsonl", namespace=test_namespace)

    result = await list_paginated_datasets(
        session=db_session,
        namespace=test_namespace,
        type=None,
        name=None,
        page=1,
        page_size=10,
        minio_client=mock_minio_client,
    )

    assert len(result.items) == 3
    assert result.total == 3
    assert result.page == 1


@pytest.mark.asyncio
async def test_list_paginated_datasets_exact_page_boundary(
    db_session: AsyncSession,
    test_namespace: str,
    mock_minio_client: MinioClient,
) -> None:
    """When the row count equals page_size, page 1 is full and page 2 is empty."""
    for i in range(5):
        await factory.create_dataset(db_session, name=f"Dataset {i}", path=f"ds-{i}.jsonl", namespace=test_namespace)

    first = await list_paginated_datasets(
        session=db_session,
        namespace=test_namespace,
        type=None,
        name=None,
        page=1,
        page_size=5,
        minio_client=mock_minio_client,
    )
    second = await list_paginated_datasets(
        session=db_session,
        namespace=test_namespace,
        type=None,
        name=None,
        page=2,
        page_size=5,
        minio_client=mock_minio_client,
    )

    assert len(first.items) == 5
    assert first.total == 5
    assert len(second.items) == 0
    assert second.total == 5


@pytest.mark.asyncio
async def test_list_paginated_datasets_multi_page_slicing(
    db_session: AsyncSession,
    test_namespace: str,
    mock_minio_client: MinioClient,
) -> None:
    """Pages slice the filtered list; total reflects the full set on every page."""
    for i in range(12):
        await factory.create_dataset(db_session, name=f"Dataset {i}", path=f"ds-{i}.jsonl", namespace=test_namespace)

    page_one = await list_paginated_datasets(
        session=db_session,
        namespace=test_namespace,
        type=None,
        name=None,
        page=1,
        page_size=5,
        minio_client=mock_minio_client,
    )
    page_two = await list_paginated_datasets(
        session=db_session,
        namespace=test_namespace,
        type=None,
        name=None,
        page=2,
        page_size=5,
        minio_client=mock_minio_client,
    )
    page_three = await list_paginated_datasets(
        session=db_session,
        namespace=test_namespace,
        type=None,
        name=None,
        page=3,
        page_size=5,
        minio_client=mock_minio_client,
    )

    assert len(page_one.items) == 5
    assert len(page_two.items) == 5
    assert len(page_three.items) == 2
    assert page_one.total == page_two.total == page_three.total == 12


@pytest.mark.asyncio
async def test_list_paginated_datasets_passes_filters_to_repository(
    db_session: AsyncSession,
    test_namespace: str,
    mock_minio_client: MinioClient,
) -> None:
    """`name`/`type` filters are forwarded to the repository unchanged."""
    with patch("app.datasets.service.repository.list_datasets", autospec=True) as mock_repo:
        mock_repo.return_value = []

        await list_paginated_datasets(
            session=db_session,
            namespace=test_namespace,
            type=DatasetType.FINETUNING,
            name="my-dataset",
            page=1,
            page_size=10,
            minio_client=mock_minio_client,
        )

    mock_repo.assert_called_once_with(
        session=db_session,
        namespace=test_namespace,
        type=DatasetType.FINETUNING,
        name="my-dataset",
    )


@pytest.mark.asyncio
async def test_list_paginated_datasets_returns_unknown_sizes_when_storage_fails(
    db_session: AsyncSession,
    test_namespace: str,
    mock_minio_client: MinioClient,
) -> None:
    await factory.create_dataset(
        db_session,
        name="Dataset",
        path=f"{test_namespace}/datasets/dataset.jsonl",
        namespace=test_namespace,
    )
    mock_minio_client.get_object_sizes.side_effect = RuntimeError("storage unavailable")

    result = await list_paginated_datasets(
        session=db_session,
        namespace=test_namespace,
        type=None,
        name=None,
        page=1,
        page_size=10,
        minio_client=mock_minio_client,
    )

    assert len(result.items) == 1
    assert result.items[0].size_bytes is None
