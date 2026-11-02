# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from unittest.mock import MagicMock, patch

import pytest

from api_common.exceptions import NotFoundException
from app.minio.client import MinioClient
from app.models.utils import delete_from_s3, delete_object_from_s3, get_finetuned_model_weights_path


def test_get_finetuned_model_weights_path_basic() -> None:
    """Test basic functionality of get_finetuned_model_weights_path."""
    result = get_finetuned_model_weights_path("meta-llama/Llama-3.1-8B", "my-finetune", "My Test Project")
    assert result == "my-test-project/finetuned-models/meta-llama/Llama-3.1-8B/my-finetune"


def test_get_finetuned_model_weights_path_with_special_characters() -> None:
    """Test get_finetuned_model_weights_path with special characters in project name."""
    result = get_finetuned_model_weights_path("test/model", "custom-finetune", "Test! @#$%^&*() Project")
    assert result == "test-project/finetuned-models/test/model/custom-finetune"


def test_get_finetuned_model_weights_path_with_already_slugified_name() -> None:
    """Test get_finetuned_model_weights_path with already slugified project name."""
    result = get_finetuned_model_weights_path("test/model", "custom-finetune", "test-project")
    assert result == "test-project/finetuned-models/test/model/custom-finetune"


# ============================================================================
# S3 Deletion Tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_from_s3_success() -> None:
    """Test delete_from_s3 successfully deletes model weights using an object prefix."""
    prefix = "test-namespace/models/test-model/weights.bin"
    mock_minio_client = MagicMock(spec=MinioClient)
    mock_minio_client.delete_objects = MagicMock(spec=[], return_value=None)

    with (
        patch("asyncio.to_thread", side_effect=lambda fn, **kwargs: fn(**kwargs)),
        patch("app.models.utils.MINIO_BUCKET", "test-bucket"),
    ):
        await delete_from_s3(prefix, mock_minio_client, "Test Model")

    mock_minio_client.delete_objects.assert_called_once()
    call_args = mock_minio_client.delete_objects.call_args
    assert call_args[1]["bucket_name"] == "test-bucket"
    assert call_args[1]["prefix"] == prefix


@pytest.mark.asyncio
async def test_delete_from_s3_handles_not_found_gracefully() -> None:
    """Test delete_from_s3 propagates NotFoundException from S3."""
    mock_minio_client = MagicMock(spec=MinioClient)
    mock_minio_client.delete_objects = MagicMock(spec=[], side_effect=NotFoundException("S3 object not found"))

    async def async_to_thread(fn, **kwargs):
        return fn(**kwargs)

    with patch("asyncio.to_thread", side_effect=async_to_thread):
        with pytest.raises(NotFoundException, match="S3 object not found"):
            await delete_from_s3("test-namespace/models/missing/weights.bin", mock_minio_client)


@pytest.mark.asyncio
async def test_delete_object_from_s3_success() -> None:
    """Test delete_object_from_s3 deletes one exact object key."""
    object_key = "test-namespace/finetuned-models/model-a/run-1/"
    mock_minio_client = MagicMock(spec=MinioClient)
    mock_minio_client.delete_object = MagicMock(spec=[], return_value=None)

    with (
        patch("asyncio.to_thread", side_effect=lambda fn, **kwargs: fn(**kwargs)) as mock_to_thread,
        patch("app.models.utils.MINIO_BUCKET", "test-bucket"),
    ):
        await delete_object_from_s3(object_key, mock_minio_client, "Test Model")

    mock_to_thread.assert_called_once_with(
        mock_minio_client.delete_object, bucket_name="test-bucket", object_name=object_key
    )
    mock_minio_client.delete_object.assert_called_once_with(bucket_name="test-bucket", object_name=object_key)
