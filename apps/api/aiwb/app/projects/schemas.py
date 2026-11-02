# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from pydantic import Field

from api_common.schemas import BaseModel


class ProjectResponse(BaseModel):
    """Project identifier and display name."""

    id: str
    name: str


class RuntimeProfileOptionsByImageQuery(BaseModel):
    """Required query parameters for base-image runtime-option lookup."""

    image_repository: str = Field(
        ...,
        min_length=1,
        description="Base image repository (without tag), e.g. 'amdenterpriseai/aim-base'.",
        examples=["amdenterpriseai/aim-base"],
    )
    image_tag: str = Field(
        ...,
        min_length=1,
        description="Base image tag, e.g. '0.13.1'.",
        examples=["0.13.1"],
    )
