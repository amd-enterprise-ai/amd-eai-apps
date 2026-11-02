# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from uuid import UUID

from pydantic import Field

from api_common.collections import BasePaginationList, PaginationConditions

from ..aims.crds import AIMModelResource
from ..models.schemas import FinetuneCreate


class FineTuningJobRequest(FinetuneCreate):
    """Input shape for POST /v1/projects/{project}/fine-tuning/jobs.

    Extends FinetuneCreate by hoisting the base model identifier into the request
    body — the legacy endpoint passed it as a URL path parameter, but the project-
    scoped URL convention keeps job identity in the body.
    """

    base_model: UUID | str = Field(
        description=(
            "Identifier of the base model to fine-tune. Either an AIMModel UUID "
            "(for fine-tuning an existing fine-tuned model) or a HuggingFace "
            "canonical name (e.g., 'meta-llama/Llama-3.1-8B')."
        ),
        examples=["meta-llama/Llama-3.1-8B"],
    )


class FineTuningModelsList(BasePaginationList):
    """Paginated list of fine-tuned models in a project."""

    data: list[AIMModelResource]


class ListFineTuningModelsQuery(PaginationConditions):
    """Query parameters for listing fine-tuned models in a project."""

    page: int = Field(default=1, ge=1)
    # Bound page_size so a single client cannot fetch arbitrarily large pages.
    page_size: int = Field(default=10, ge=1, le=100)
