# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import datetime

from pydantic import Field

from api_common.schemas import BaseModel

from ..secrets.constants import SECRET_NAME_MAX_LENGTH, SECRET_NAME_MIN_LENGTH, SECRET_NAME_PATTERN
from .enums import StorageType


class S3StorageSpec(BaseModel):
    bucket_url: str | None = Field(
        None,
        min_length=1,
        description="Optional S3 or S3-compatible bucket URL used for model source reads.",
        examples=["https://s3.example.com/my-bucket"],
    )
    region: str | None = Field(
        None,
        min_length=1,
        description="Optional S3 region (for example `us-east-1`) used by compatible clients.",
        examples=["us-east-1"],
    )
    access_key_name: str | None = Field(
        None,
        min_length=1,
        description="Optional secret data key name containing access key ID.",
        examples=["accessKeyId"],
    )
    secret_key_name: str | None = Field(
        None,
        min_length=1,
        description="Optional secret data key name containing secret access key.",
        examples=["secretAccessKey"],
    )


class ProjectStorageCreateRequest(BaseModel):
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=253,
        description=(
            "User-visible name for the storage configuration. Any characters are allowed; "
            "the Kubernetes resource name is auto-generated."
        ),
        examples=["Default team bucket"],
    )
    type: StorageType = Field(default=StorageType.S3, description="Storage type.")
    secret_name: str = Field(
        ...,
        min_length=SECRET_NAME_MIN_LENGTH,
        max_length=SECRET_NAME_MAX_LENGTH,
        pattern=SECRET_NAME_PATTERN,
        description="Project secret name holding S3 credentials.",
        examples=["s3-credentials"],
    )
    spec: S3StorageSpec = Field(..., description="S3 storage configuration.")


class ProjectStorageResponse(BaseModel):
    name: str = Field(..., description="Storage configuration resource name.")
    display_name: str = Field(..., description="User-visible name for the storage configuration.")
    project: str = Field(..., description="Project (namespace) the storage belongs to.")
    type: StorageType = Field(..., description="Storage type.")
    secret_name: str = Field(..., description="Secret name backing this storage configuration.")
    spec: S3StorageSpec = Field(..., description="S3 storage specification.")
    created_at: datetime | None = Field(None, description="Creation timestamp from Kubernetes metadata.")


class ProjectStorageListQuery(BaseModel):
    type: StorageType | None = Field(
        default=None,
        description="Optional storage-type filter (exact match).",
    )
