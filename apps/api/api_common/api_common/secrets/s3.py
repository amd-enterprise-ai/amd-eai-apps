# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from collections.abc import Iterable

# Accepted key aliases for S3 credential material in a Kubernetes Secret's data map.
# S3 secrets are authored by different tools (AWS CLI, MinIO, custom scripts), so a
# credential can arrive under any of these spellings. Keyed by logical credential name.
S3_REQUIRED_CREDENTIAL_KEYS: dict[str, tuple[str, ...]] = {
    "access key": (
        "AWS_ACCESS_KEY_ID",
        "awsAccessKeyId",
        "aws_access_key_id",
        "AWS_ACCESS_KEY",
        "accessKeyId",
        "access_key_id",
        "S3_ACCESS_KEY_ID",
        "S3_ACCESS_KEY",
        "s3_access_key_id",
        "s3_access_key",
        "MINIO_ACCESS_KEY",
        "minio_access_key",
        "MINIO_ROOT_USER",
        "ACCESS_KEY",
        "access_key",
        "minio-access-key",
        "storage-access-key",
    ),
    "secret key": (
        "AWS_SECRET_ACCESS_KEY",
        "awsSecretAccessKey",
        "aws_secret_access_key",
        "AWS_SECRET_KEY",
        "secretAccessKey",
        "secret_access_key",
        "S3_SECRET_ACCESS_KEY",
        "S3_SECRET_KEY",
        "s3_secret_access_key",
        "s3_secret_key",
        "MINIO_SECRET_KEY",
        "minio_secret_key",
        "MINIO_ROOT_PASSWORD",
        "SECRET_KEY",
        "secret_key",
        "minio-secret-key",
        "storage-secret-key",
    ),
}

# Optional endpoint override aliases; absence implies the platform default endpoint.
S3_ENDPOINT_KEYS: tuple[str, ...] = (
    "AWS_ENDPOINT_URL",
    "awsEndpointUrl",
    "aws_endpoint_url",
    "S3_ENDPOINT_URL",
    "S3_ENDPOINT",
    "s3_endpoint_url",
    "s3_endpoint",
    "MINIO_ENDPOINT",
    "minio_endpoint",
    "endpoint",
)


def find_missing_s3_credential_types(data_keys: Iterable[str]) -> list[str]:
    """Return the logical credential names (e.g. "access key") not covered by any provided data key."""
    present = set(data_keys)
    return [
        logical_name
        for logical_name, aliases in S3_REQUIRED_CREDENTIAL_KEYS.items()
        if not any(alias in present for alias in aliases)
    ]
