# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from pydantic import Field

from api_common.collections import BasePaginationList, PaginationConditions
from api_common.schemas import BaseEntityPublic

from .models import DatasetType


class DatasetResponse(BaseEntityPublic):
    """Response model for dataset operations"""

    name: str = Field(
        description="The name of the dataset (unique within the project).",
        examples=["imdb-sentiment-v1"],
    )
    description: str = Field(
        description="Free-form description of the dataset's contents.",
        examples=["IMDB reviews labelled positive/negative"],
    )
    path: str = Field(
        description="S3 object key under which the dataset bytes are stored.",
        examples=["acme-summarizer/imdb-sentiment-v1.jsonl"],
    )
    type: DatasetType = Field(
        description="The type of the dataset.",
        examples=["Fine-tuning"],
    )
    size_bytes: int | None = Field(
        default=None,
        description="Size of the dataset file in bytes, read from object storage.",
    )


class DatasetsList(BasePaginationList):
    """Paginated list of datasets."""

    data: list[DatasetResponse]


class ListDatasetsQuery(PaginationConditions):
    """Query parameters for listing datasets."""

    page: int = Field(default=1, ge=1)
    # Bound page_size so a single client cannot fetch arbitrarily large pages.
    page_size: int = Field(default=10, ge=1, le=100)
    type: DatasetType | None = Field(
        default=None,
        description="Filter datasets by type (exact match).",
    )
    name: str | None = Field(
        default=None,
        description="Filter datasets by name (exact match).",
    )
