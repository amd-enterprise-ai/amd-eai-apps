# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Tests for the MinioClient class and related functionality.
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from minio import Minio
from minio.datatypes import Object
from minio.deleteobjects import DeleteError, DeleteObject
from minio.error import S3Error

from api_common.exceptions import ExternalServiceError
from app.minio import MinioClient, get_minio_client, get_minio_external_client


def test_init_with_custom_values():
    """Test initialization with custom provided values."""
    client = MinioClient(host="custom_host", access_key="custom_access", secret_key="custom_secret")
    assert client.host == "custom_host"
    assert client.access_key == "custom_access"
    assert client.secret_key == "custom_secret"


def test_create_client_with_http_url():
    """Test client creation with HTTP URL."""
    with patch("app.minio.client.Minio") as mock_minio:
        client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
        # Check that Minio was called with secure=False
        mock_minio.assert_called_once()
        args, kwargs = mock_minio.call_args
        assert kwargs.get("secure") is False


def test_create_client_with_https_url():
    """Test client creation with HTTPS URL."""
    with patch("app.minio.client.Minio") as mock_minio:
        client = MinioClient(host="https://localhost:9000", access_key="access_key", secret_key="secret_key")
        # Check that Minio was called with secure=True
        mock_minio.assert_called_once()
        args, kwargs = mock_minio.call_args
        assert kwargs.get("secure") is True


def test_missing_host():
    """Test client creation with missing host."""
    with patch.object(
        MinioClient,
        "create_client",
        side_effect=ValueError("MinIO configuration environment variables are not set: MINIO_URL"),
    ):
        with pytest.raises(ValueError) as exc_info:
            MinioClient(host="", access_key="access_key", secret_key="secret_key")
        assert "MinIO configuration environment variables are not set" in str(exc_info.value)


def test_missing_access_key():
    """Test client creation with missing access key."""
    with patch.object(
        MinioClient,
        "create_client",
        side_effect=ValueError("MinIO configuration environment variables are not set: MINIO_ACCESS_KEY"),
    ):
        with pytest.raises(ValueError) as exc_info:
            MinioClient(host="host", access_key="", secret_key="secret_key")
        assert "MinIO configuration environment variables are not set" in str(exc_info.value)


def test_missing_secret_key():
    """Test client creation with missing secret key."""
    with patch.object(
        MinioClient,
        "create_client",
        side_effect=ValueError("MinIO configuration environment variables are not set: MINIO_SECRET_KEY"),
    ):
        with pytest.raises(ValueError) as exc_info:
            MinioClient(host="host", access_key="access_key", secret_key="")
        assert "MinIO configuration environment variables are not set" in str(exc_info.value)


def test_upload_object():
    """Test uploading an object to MinIO."""
    client = MagicMock(spec=Minio)
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client

    data = b"test data"
    minio_client.upload_object("bucket", "object", data)

    client.put_object.assert_called_once()
    args, kwargs = client.put_object.call_args
    assert args[0] == "bucket"
    assert args[1] == "object"
    assert kwargs["length"] == len(data)


def test_download_object():
    """Test downloading an object from MinIO."""
    client = MagicMock(spec=Minio)
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client

    mock_response = MagicMock()
    mock_response.read.return_value = b"test data"
    client.get_object.return_value = mock_response

    result = minio_client.download_object("bucket", "object")

    client.get_object.assert_called_once_with("bucket", "object")
    assert result == b"test data"


def test_stream_object():
    """Test streaming an object from MinIO in chunks."""
    client = MagicMock(spec=Minio)
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client

    mock_response = MagicMock()
    test_chunks = [b"chunk1", b"chunk2", b"chunk3"]
    mock_response.stream.return_value = iter(test_chunks)
    client.get_object.return_value = mock_response

    result = list(minio_client.stream_object("bucket", "object", chunk_size=8192))

    client.get_object.assert_called_once_with("bucket", "object")
    mock_response.stream.assert_called_once_with(8192)
    mock_response.close.assert_called_once()
    mock_response.release_conn.assert_called_once()
    assert result == test_chunks


def test_stream_object_custom_chunk_size():
    """Test streaming with custom chunk size."""
    client = MagicMock(spec=Minio)
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client

    mock_response = MagicMock()
    test_chunks = [b"data"]
    mock_response.stream.return_value = iter(test_chunks)
    client.get_object.return_value = mock_response

    list(minio_client.stream_object("bucket", "object", chunk_size=65536))

    mock_response.stream.assert_called_once_with(65536)


def test_stream_object_cleanup_on_error():
    """Test that stream_object cleans up resources even on error."""
    client = MagicMock(spec=Minio)
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client

    mock_response = MagicMock()

    def failing_stream(chunk_size):
        yield b"chunk1"
        raise RuntimeError("Streaming error")

    mock_response.stream.return_value = failing_stream(8192)
    client.get_object.return_value = mock_response

    with pytest.raises(RuntimeError, match="Streaming error"):
        list(minio_client.stream_object("bucket", "object"))

    # Verify cleanup happened despite error
    mock_response.close.assert_called_once()
    mock_response.release_conn.assert_called_once()


def test_delete_object():
    """Test deleting an object from MinIO."""
    client = MagicMock(spec=Minio)
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client
    minio_client.delete_object("bucket", "object")
    client.remove_object.assert_called_once_with("bucket", "object")


def test_delete_objects():
    """Test deleting multiple objects from MinIO."""
    client = MagicMock(spec=Minio)
    object_names = ["prefix/1/2", "prefix/3"]
    objects = [Object("bucket", name) for name in object_names]
    delete_objects = [DeleteObject(name) for name in object_names]
    client.list_objects.return_value = objects
    # remove_objects returns a lazy generator (not a list); a successful delete
    # yields nothing. Mirror that here so the test exercises the real return type.
    client.remove_objects.return_value = iter([])
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client
    minio_client.delete_objects("bucket", "prefix")
    client.list_objects.assert_called_once_with("bucket", "prefix", recursive=True)
    client.remove_objects.assert_called_once()
    # Check that the correct objects were passed to remove_objects
    assert client.remove_objects.call_count == 1
    assert client.remove_objects.call_args[0][0] == "bucket"
    assert set(obj.name for obj in client.remove_objects.call_args[0][1]) == set(obj.name for obj in delete_objects)


def test_delete_objects_raises_on_real_errors():
    """A genuine DeleteError yielded by remove_objects must surface as ExternalServiceError."""
    client = MagicMock(spec=Minio)
    objects = [Object("bucket", "prefix/1")]
    client.list_objects.return_value = objects
    client.remove_objects.return_value = iter(
        [DeleteError(code="AccessDenied", message="denied", name="prefix/1", version_id=None)]
    )
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client
    with pytest.raises(ExternalServiceError):
        minio_client.delete_objects("bucket", "prefix")


def test_get_minio_client_returns_client():
    """Test that get_minio_client returns the client from app.state."""
    mock_client = MagicMock(spec=MinioClient)
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.minio_client = mock_client

    client = get_minio_client(mock_request)
    assert client is mock_client


def test_get_minio_client_missing_client():
    """Storage that was never configured is reported as the same upstream failure as storage that
    refuses or cannot be reached, so routes answer with their documented 502 rather than a 500."""
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.minio_client = None

    with pytest.raises(ExternalServiceError) as exc_info:
        get_minio_client(mock_request)
    assert "Object storage is not available" in str(exc_info.value)


def test_get_minio_client_no_attribute():
    """Test that get_minio_client raises an exception when minio_client attribute doesn't exist."""
    mock_request = MagicMock(spec=Request)
    # Remove the minio_client attribute
    if hasattr(mock_request.app.state, "minio_client"):
        delattr(mock_request.app.state, "minio_client")

    with pytest.raises(ExternalServiceError) as exc_info:
        get_minio_client(mock_request)
    assert "Object storage is not available" in str(exc_info.value)


def test_get_minio_external_client_missing_client():
    """The presigning client reports its absence the same way, so a route resolving both fails
    identically whichever one is missing."""
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.minio_external_client = None

    with pytest.raises(ExternalServiceError) as exc_info:
        get_minio_external_client(mock_request)
    assert "Object storage is not available" in str(exc_info.value)


def test_stream_object_retries_on_transient_connection_error():
    """Test that stream_object retries get_object on transient S3 errors."""
    client = MagicMock(spec=Minio)
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client

    mock_response = MagicMock()
    mock_response.stream.return_value = iter([b"data"])

    transient_error = S3Error("ServiceUnavailable", "Service unavailable", "resource", "request_id", "host_id", "url")
    client.get_object.side_effect = [transient_error, mock_response]

    with (
        patch("app.minio.client.MINIO_MIN_WAIT", 0),
        patch("app.minio.client.MINIO_MAX_WAIT", 0),
        patch("app.minio.client.MINIO_MAX_ATTEMPTS", 3),
    ):
        result = list(minio_client.stream_object("bucket", "object"))

    assert client.get_object.call_count == 2
    assert result == [b"data"]


def test_stream_object_raises_after_max_retries():
    """Test that stream_object raises after exhausting all retry attempts."""
    client = MagicMock(spec=Minio)
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client

    transient_error = S3Error("ServiceUnavailable", "Service unavailable", "resource", "request_id", "host_id", "url")
    client.get_object.side_effect = transient_error

    with (
        patch("app.minio.client.MINIO_MIN_WAIT", 0),
        patch("app.minio.client.MINIO_MAX_WAIT", 0),
        patch("app.minio.client.MINIO_MAX_ATTEMPTS", 2),
    ):
        with pytest.raises(S3Error):
            list(minio_client.stream_object("bucket", "object"))

    assert client.get_object.call_count == 2


def test_stat_object():
    """Test stat_object delegates to the underlying minio client."""
    client = MagicMock(spec=Minio)
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client

    mock_stat = MagicMock()
    mock_stat.size = 1024
    client.stat_object.return_value = mock_stat

    result = minio_client.stat_object("bucket", "object")

    client.stat_object.assert_called_once_with("bucket", "object")
    assert result.size == 1024


def test_get_object_sizes():
    """Object listing exposes authoritative sizes by object name."""
    client = MagicMock(spec=Minio)
    first = Object("bucket", "prefix/first.jsonl", size=128)
    second = Object("bucket", "prefix/second.jsonl", size=256)
    client.list_objects.return_value = iter([first, second])
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client

    result = minio_client.get_object_sizes("bucket", "prefix/")

    assert result == {
        "prefix/first.jsonl": 128,
        "prefix/second.jsonl": 256,
    }
    client.list_objects.assert_called_once_with("bucket", prefix="prefix/", recursive=True)


def test_generate_presigned_download_url():
    """Test generate_presigned_download_url delegates to the underlying minio client."""
    client = MagicMock(spec=Minio)
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client
    client.presigned_get_object.return_value = "https://storage.example.com/presigned"

    expires = datetime.timedelta(minutes=15)
    result = minio_client.generate_presigned_download_url("bucket", "object", expires)

    client.presigned_get_object.assert_called_once_with("bucket", "object", expires=expires, request_date=None)
    assert result == "https://storage.example.com/presigned"


def test_presigned_urls_carry_the_signing_instant_they_are_given():
    """A signature's life runs from a timestamp inside it, so a caller minting a batch must be able
    to fix that timestamp — otherwise every URL takes its own reading and the batch has no single
    deadline. Uploads route around presigned_put_object, which exposes no such parameter."""
    client = MagicMock(spec=Minio)
    minio_client = MinioClient(host="http://localhost:9000", access_key="access_key", secret_key="secret_key")
    minio_client.client = client

    expires = datetime.timedelta(minutes=15)
    signed_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)

    minio_client.generate_presigned_upload_url("bucket", "object", expires, request_date=signed_at)
    minio_client.generate_presigned_download_url("bucket", "object", expires, request_date=signed_at)

    client.get_presigned_url.assert_called_once_with("PUT", "bucket", "object", expires, request_date=signed_at)
    client.presigned_get_object.assert_called_once_with("bucket", "object", expires=expires, request_date=signed_at)


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
