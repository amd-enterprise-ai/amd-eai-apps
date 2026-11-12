# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from typing import Any
from uuid import UUID

from pydantic import Field

from api_common.schemas import BaseEntityPublic, BaseModel

from .models import SOURCE_PATH_MAX_LENGTH


class OverlayListQuery(BaseModel):
    chart_id: UUID | None = Field(
        default=None,
        description="Optionally filter by chart ID",
        examples=["b0c1d2e3-4567-89ab-cdef-0123456789ab"],
    )
    canonical_name: str | None = Field(
        default=None,
        description="Optionally filter by overlays compatible to models with a specific canonical name. This also includes overlays with no canonical name specified.",
        examples=["meta-llama/Llama-3.1-8B"],
    )


class OverlayResponse(BaseEntityPublic):
    display_name: str | None = Field(
        default=None,
        description="Optional user-visible display name for this overlay.",
    )
    canonical_name: str | None = Field(
        description="Optional canonical name for a model which this overlay is compatible with. Used to identify overlays for models of the same origin.",
        examples=["meta-llama/Llama-3.1-8B"],
    )
    source_path: str | None = Field(
        default=None,
        description=(
            "Path of the chart file this overlay was registered from, relative to the chart. Identifies a "
            "chart-shipped recipe, so one model can have a recipe per GPU family. Null for overlays created "
            "through the API."
        ),
        examples=["overrides/models/meta-llama_Llama-3.1-8B.yaml"],
    )
    chart_id: UUID = Field(
        description="ID of the chart this overlay is attached to.",
        examples=["b0c1d2e3-4567-89ab-cdef-0123456789ab"],
    )
    overlay: dict[str, Any] = Field(
        description="Parsed overlay body merged into the chart's values at render time.",
        examples=[{"resources": {"limits": {"amd.com/gpu": 1}}, "env": [{"name": "HF_HOME", "value": "/cache"}]}],
    )


class OverlayUpdate(BaseModel):
    """Request schema for updating an overlay."""

    display_name: str | None = Field(
        None,
        description="Optional user-visible display name for this overlay.",
    )
    chart_id: UUID | None = Field(
        None,
        description="The ID of the chart this overlay is associated with.",
        examples=["b0c1d2e3-4567-89ab-cdef-0123456789ab"],
    )
    overlay: dict[str, Any] | None = Field(
        None,
        description="The overlay data in YAML format.",
        examples=[{"resources": {"limits": {"amd.com/gpu": 1}}}],
    )
    canonical_name: str | None = Field(
        None,
        description="Optional canonical name to associate the overlay with a model type, for example 'meta-llama/Llama-3.1-8B'.",
        examples=["meta-llama/Llama-3.1-8B"],
    )
    source_path: str | None = Field(
        None,
        max_length=SOURCE_PATH_MAX_LENGTH,
        description="Path of the chart file this overlay is registered from, relative to the chart.",
        examples=["overrides/models/meta-llama_Llama-3.1-8B.yaml"],
    )
    updated_by: str = Field(
        description="Email of the user who updated the overlay.",
        examples=["alice@acme.example"],
    )
