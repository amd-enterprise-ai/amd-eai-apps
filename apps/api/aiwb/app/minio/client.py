# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import datetime
import io
from collections.abc import Generator
from contextlib import contextmanager

import urllib3
from loguru import logger
from minio import Minio
from minio.datatypes import Object
from minio.deleteobjects import DeleteObject
from minio.error import S3Error
from tenacity import retry, stop_after_attempt, wait_exponential

from api_common.exceptions import (
    BaseApiException,
    ExternalServiceError,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)

from .config import (
    MINIO_ACCESS_KEY,
    MINIO_MAX_ATTEMPTS,
    MINIO_MAX_WAIT,
    MINIO_MIN_WAIT,
    MINIO_SECRET_KEY,
    MINIO_URL,
)
from .exceptions import S3SyncError

_IN_CLUSTER_HOST_SUFFIXES = (".svc", ".svc.cluster.local")

# Single-label hostnames are otherwise read as Kubernetes service names. Loopback is the one that
# genuinely resolves for the caller, since it means the caller shares the host.
_LOOPBACK_HOSTNAMES = frozenset({"localhost"})


def strip_url_scheme(url: str) -> str:
    """Return the URL without its http:// or https:// prefix."""
    return url.removeprefix("https://").removeprefix("http://")


def is_in_cluster_host(url: str) -> bool:
    """Whether the URL names a Kubernetes service that only resolves inside the cluster.

    Deliberately narrow: private (RFC1918) addresses and ``localhost`` classify as external. Both
    mean "not on the public Internet", which is a different question from "not reachable by the
    caller" — on-prem and air-gapped installs reach object storage on exactly such an address, and
    treating those as unusable would break the very installs this classification protects.
    """
    hostname = strip_url_scheme(url).split("/")[0].split(":")[0].casefold().rstrip(".")
    if hostname in _LOOPBACK_HOSTNAMES:
        return False
    return hostname.endswith(_IN_CLUSTER_HOST_SUFFIXES) or "." not in hostname


class MinioClient:
    def __init__(
        self,
        host: str = None,
        access_key: str = None,
        secret_key: str = None,
        region: str | None = None,
    ):
        self.host = host or MINIO_URL
        self.access_key = access_key or MINIO_ACCESS_KEY
        self.secret_key = secret_key or MINIO_SECRET_KEY
        self.region = region
        self.client = self.create_client()

    def create_client(self):
        credentials = {
            "MINIO_URL": self.host,
            "MINIO_ACCESS_KEY": self.access_key,
            "MINIO_SECRET_KEY": self.secret_key,
        }

        missing_credentials = [key for key, value in credentials.items() if not value]
        if missing_credentials:
            raise ValueError(f"MinIO configuration environment variables are not set: {', '.join(missing_credentials)}")

        minio_host = strip_url_scheme(credentials["MINIO_URL"])

        # Determine if we should use HTTPS based on original URL
        use_https = not credentials["MINIO_URL"].startswith("http://")

        if use_https:
            urllib3.disable_warnings()

        return Minio(
            minio_host,
            access_key=credentials["MINIO_ACCESS_KEY"],
            secret_key=credentials["MINIO_SECRET_KEY"],
            secure=use_https,
            cert_check=False,
            region=self.region,
        )

    def upload_object(self, bucket_name: str, object_name: str, data: bytes) -> None:
        buffer = io.BytesIO(data)
        self.client.put_object(bucket_name, object_name, buffer, length=len(data))
        buffer.close()

    def upload_file(self, bucket_name: str, object_name: str, file_path: str) -> None:
        """Upload a file from disk, streaming it in parts.

        Unlike ``upload_object`` (which buffers the whole blob in memory),
        ``fput_object`` streams from the file handle and switches to a multipart
        upload automatically, so peak memory stays bounded regardless of file
        size. Used by the weight-import pipeline for multi-GB model shards.
        """
        self.client.fput_object(bucket_name, object_name, file_path)

    def download_object(self, bucket_name: str, object_name: str) -> bytes:
        return self.client.get_object(bucket_name, object_name).read()

    def stream_object(self, bucket_name: str, object_name: str, chunk_size: int = 8192) -> Generator[bytes]:
        """
        Stream an object from S3 in chunks without loading entire file into memory.

        Args:
            bucket_name: Name of the S3 bucket
            object_name: Object key/path in the bucket
            chunk_size: Size of chunks to read (default 8KB)

        Yields:
            bytes: Chunks of the object data
        """

        # Retry only the initial connection — once streaming starts we cannot retry mid-stream.
        @retry(
            wait=wait_exponential(multiplier=1, min=MINIO_MIN_WAIT, max=MINIO_MAX_WAIT),
            stop=stop_after_attempt(MINIO_MAX_ATTEMPTS),
            reraise=True,
        )
        def connect():
            return self.client.get_object(bucket_name, object_name)

        response = connect()
        try:
            yield from response.stream(chunk_size)
        finally:
            response.close()
            response.release_conn()

    def stat_object(self, bucket_name: str, object_name: str) -> Object:
        """Return metadata for an object without downloading it."""
        return self.client.stat_object(bucket_name, object_name)

    def get_object_sizes(self, bucket_name: str, prefix: str) -> dict[str, int]:
        """Return object sizes under a prefix without downloading content."""
        return {
            obj.object_name: obj.size
            for obj in self.client.list_objects(bucket_name, prefix=prefix, recursive=True)
            if obj.object_name is not None and obj.size is not None
        }

    def list_top_level_prefixes(self, bucket_name: str) -> list[str]:
        """Return the bucket's immediate child prefixes — one per project storage tree.

        Non-recursive, so the cost is proportional to the number of projects rather than to the
        number of objects they hold.
        """
        return [
            obj.object_name
            for obj in self.client.list_objects(bucket_name, recursive=False)
            if obj.is_dir and obj.object_name is not None
        ]

    def get_object_details(self, bucket_name: str, prefix: str) -> list[Object]:
        """Return objects under a prefix with their metadata intact.

        `get_object_sizes` covers the common case of wanting sizes alone; this keeps the whole
        record for callers that also need timestamps.
        """
        return [obj for obj in self.client.list_objects(bucket_name, prefix=prefix, recursive=True) if not obj.is_dir]

    def delete_object_keys(self, bucket_name: str, object_names: list[str]) -> None:
        """Delete exactly the named objects, and nothing else under their prefix.

        `delete_objects` re-lists the prefix and removes whatever it finds then, which is what a
        caller discarding a whole tree wants. Reclamation instead removes only the objects it
        listed and judged, so anything written after that judgement outlives it rather than being
        swept up on the strength of a verdict reached before it existed.
        """
        if not object_names:
            return

        errors = list(self.client.remove_objects(bucket_name, [DeleteObject(name) for name in object_names]))
        if errors:
            detail = ", ".join(f"Error deleting {error.name}: {error.message}" for error in errors)
            logger.error(f"Errors occurred while deleting objects: {detail}")
            raise ExternalServiceError(message="Failed to delete some objects", detail=detail)

    def delete_object(self, bucket_name: str, object_name: str) -> None:
        """Delete an object from the specified bucket."""
        self.client.remove_object(bucket_name, object_name)
        logger.info(f"Successfully deleted object {object_name} from bucket {bucket_name}")

    def generate_presigned_upload_url(
        self,
        bucket: str,
        object_name: str,
        expires: datetime.timedelta,
        request_date: datetime.datetime | None = None,
    ) -> str:
        """Return a presigned PUT URL for the given object.

        A signature's life runs from the timestamp stamped inside it, which defaults to whatever the
        signing client reads off its own clock at this call. Pass ``request_date`` to fix that
        timestamp so a batch of URLs shares one true deadline rather than each expiring a moment
        after the last. An aware datetime is converted to UTC; a naive one is read as UTC already.
        """
        # presigned_put_object exposes no request_date, so the general signer is called directly.
        return self.client.get_presigned_url("PUT", bucket, object_name, expires, request_date=request_date)

    def generate_presigned_download_url(
        self,
        bucket: str,
        object_name: str,
        expires: datetime.timedelta,
        request_date: datetime.datetime | None = None,
    ) -> str:
        """Return a presigned GET URL for the given object.

        See ``generate_presigned_upload_url`` for what fixing ``request_date`` buys.
        """
        return self.client.presigned_get_object(bucket, object_name, expires=expires, request_date=request_date)

    def is_externally_addressable(self) -> bool:
        """Whether URLs signed by this client can be resolved by a caller outside the cluster.

        False when the endpoint is an in-cluster service name. SigV4 covers the Host header, so a
        URL signed against such a host cannot be rewritten afterwards — before signing is the only
        moment the mismatch is still actionable.
        """
        return not is_in_cluster_host(self.host)

    def delete_objects(self, bucket_name: str, prefix: str) -> None:
        """Delete all objects in prefix from the specified bucket."""
        objects = list(self.client.list_objects(bucket_name, prefix, recursive=True))

        if not objects:
            logger.info(f"No objects found with prefix {prefix} in bucket {bucket_name}")
            return

        delete_objects = [DeleteObject(obj.object_name) for obj in objects]
        # Materialize the lazy generator so `if errors` reflects real failures,
        # not the always-truthy generator object.
        errors = list(self.client.remove_objects(bucket_name, delete_objects))
        if errors:
            error_messages = [f"Error deleting {error.name}: {error.message}" for error in errors]
            error_message = ", ".join(error_messages)
            logger.error(f"Errors occurred while deleting objects: {error_message}")
            raise ExternalServiceError(message="Failed to delete some objects", detail=error_message)
        logger.info(
            f"Successfully deleted {len(delete_objects)} objects with prefix {prefix} from bucket {bucket_name}"
        )


def map_s3_error_to_domain_exception(s3_error: S3Error, context: str) -> BaseApiException:
    """
    Map S3Error to appropriate domain exception based on error code.
    """
    error_code = s3_error.code

    if error_code in ["NoSuchKey", "NoSuchBucket"]:
        return NotFoundException(message=f"File not found in storage: {context}", detail=str(s3_error))
    elif error_code in ["AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"]:
        return ForbiddenException(message=f"Access denied to storage: {context}", detail=str(s3_error))
    elif error_code in ["InvalidRequest", "MalformedXML", "InvalidArgument"]:
        return ValidationException(message=f"Invalid storage request: {context}", detail=str(s3_error))
    else:
        # For InternalError, SlowDown, ServiceUnavailable, etc.
        return ExternalServiceError(message=f"Storage service error: {context}", detail=str(s3_error))


@contextmanager
def handle_s3_operation(operation: str, context: str, resource_id: str | None = None) -> Generator[None]:
    """
    Context manager for consistent S3 error handling and logging.

    Raises:
        NotFoundException: For NoSuchKey, NoSuchBucket errors (404)
        ForbiddenException: For AccessDenied errors (403)
        ValidationException: For InvalidRequest, MalformedXML errors (400)
        ExternalServiceError: For S3 service errors or S3SyncError (502)
    """
    try:
        yield
    except S3Error as e:
        resource_info = f" {resource_id}" if resource_id else ""
        logger.error(f"S3 error {operation}{resource_info}: {e}")
        raise map_s3_error_to_domain_exception(e, context)
    except S3SyncError as e:
        resource_info = f" {resource_id}" if resource_id else ""
        logger.error(f"S3 sync error {operation}{resource_info}: {e}")
        raise ExternalServiceError(message=f"Failed to verify {operation}: {context}", detail=str(e))
