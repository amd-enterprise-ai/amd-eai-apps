# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Unit tests for the adapter weight-readiness probe shared by the artifact and deploy paths."""

from unittest.mock import MagicMock

import pytest
from minio.error import S3Error

from app.artifacts.readiness import OBJECT_MISSING_CODE, split_s3_uri, stat_readiness
from app.artifacts.schemas import REQUIRED_PEFT_FILENAMES, ReadinessState
from app.minio import MinioClient

_LOCATION = ("test-bucket", "test-namespace/adapters/my-adapter/")


def _s3_error(code: str) -> S3Error:
    """Build the S3Error minio-py would raise for the given error code."""
    return S3Error(
        code=code,
        message=code,
        resource="/bucket/object",
        request_id="request123",
        host_id="host123",
        response=MagicMock(status=404 if code == OBJECT_MISSING_CODE else 503),
    )


@pytest.fixture
def minio_client() -> MagicMock:
    client = MagicMock(spec=MinioClient)
    client.stat_object.return_value = MagicMock()
    return client


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        pytest.param("s3://bucket/ns/adapters/a/", ("bucket", "ns/adapters/a/"), id="trailing-slash-kept"),
        pytest.param("s3://bucket/ns/adapters/a", ("bucket", "ns/adapters/a/"), id="trailing-slash-added"),
        pytest.param("s3://bucket", ("bucket", ""), id="bucket-root"),
        pytest.param("hf://org/some-adapter", None, id="not-object-storage"),
        pytest.param("s3:///ns/adapters/a/", None, id="no-bucket"),
        pytest.param("", None, id="empty"),
        pytest.param(None, None, id="absent"),
    ],
)
def test_split_s3_uri(uri: str | None, expected: tuple[str, str] | None) -> None:
    """A URI this probe cannot read simply yields no location, never an error."""
    assert split_s3_uri(uri) == expected


async def test_readiness_is_ready_when_every_required_file_is_present(minio_client: MagicMock) -> None:
    assert await stat_readiness(minio_client, _LOCATION) is ReadinessState.READY

    bucket, prefix = _LOCATION
    stated = {call.args for call in minio_client.stat_object.call_args_list}
    assert stated == {(bucket, f"{prefix}{name}") for name in REQUIRED_PEFT_FILENAMES}


async def test_readiness_is_not_ready_when_a_required_file_is_missing(minio_client: MagicMock) -> None:
    minio_client.stat_object.side_effect = _s3_error(OBJECT_MISSING_CODE)

    assert await stat_readiness(minio_client, _LOCATION) is ReadinessState.NOT_READY


async def test_a_confirmed_missing_file_outweighs_a_transient_failure(minio_client: MagicMock) -> None:
    """One file confirmed absent settles the verdict even when another file could not be checked."""
    minio_client.stat_object.side_effect = [_s3_error("SlowDown"), _s3_error(OBJECT_MISSING_CODE)]

    assert await stat_readiness(minio_client, _LOCATION) is ReadinessState.NOT_READY


@pytest.mark.parametrize(
    "failure",
    [pytest.param(_s3_error("AccessDenied"), id="refused"), pytest.param(ConnectionError("unreachable"), id="down")],
)
async def test_readiness_is_unknown_when_storage_cannot_answer(minio_client: MagicMock, failure: Exception) -> None:
    """A check that could not run is never reported as weights being absent."""
    minio_client.stat_object.side_effect = failure

    assert await stat_readiness(minio_client, _LOCATION) is ReadinessState.UNKNOWN


@pytest.mark.parametrize(
    ("client", "location"),
    [pytest.param(None, _LOCATION, id="storage-unconfigured"), pytest.param(MagicMock(), None, id="unreadable-uri")],
)
async def test_readiness_is_unknown_without_something_to_check(
    client: MinioClient | None, location: tuple[str, str] | None
) -> None:
    assert await stat_readiness(client, location) is ReadinessState.UNKNOWN
