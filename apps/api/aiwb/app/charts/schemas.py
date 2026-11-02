# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import File, UploadFile
from pydantic import ConfigDict, Field, field_validator

from api_common.schemas import BaseEntityPublic, BaseModel

from ..workloads.enums import WorkloadType
from ..workspaces.enums import WorkspaceUsageScope


async def _parse_signature_file(signature: UploadFile | Path) -> dict:
    """Parse signature YAML file."""
    try:
        if isinstance(signature, Path):
            with open(signature, encoding="utf-8") as f:
                signature_content = f.read()
        else:
            signature_content = (await signature.read()).decode()
        parsed = yaml.safe_load(signature_content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in signature file: {e}")
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ValueError(f"Signature file must contain a YAML mapping, got {type(parsed).__name__}")
    return parsed


async def _parse_chart_files(files: list[UploadFile | Path]) -> list[dict]:
    """Parse chart files into dict objects."""
    files_data = []
    for file in files:
        if isinstance(file, Path):
            with open(file, encoding="utf-8") as f:
                content = f.read()
            file_name = file.name
            path_parts = file.parts
            if "helm" in path_parts:
                helm_idx = path_parts.index("helm")
                if helm_idx + 1 < len(path_parts):
                    # Get relative path from helm directory
                    rel_parts = path_parts[helm_idx + 1 :]
                    file_name = "/".join(rel_parts)
        else:
            content = (await file.read()).decode()
            file_name = file.filename
        files_data.append({"path": file_name, "content": content})
    return files_data


class ChartRequiredResources(BaseModel):
    """Default resource hints surfaced when deploying a chart.

    Extra keys from legacy chart metadata are tolerated so that charts
    stored before this schema was introduced don't fail validation.
    """

    model_config = ConfigDict(extra="allow")

    gpu_count: int | None = None
    gpu_memory: int | None = None
    cpu_core_count: int | None = None
    system_memory: int | None = None


class ChartSignature(BaseModel):
    """Parsed chart signature. Free-form YAML (stored as JSONB); only `image`
    is consumed by the UI, so type that and tolerate any additional keys."""

    model_config = ConfigDict(extra="allow")

    image: str | None = Field(
        default=None,
        description="Container image the chart renders workloads with.",
        examples=["registry.example.com/charts/jupyterlab:latest"],
    )


class ChartFile(BaseModel):
    path: str = Field(
        description="Relative path of the template file within the chart.",
        examples=["templates/deployment.yaml"],
    )
    content: str = Field(
        description="Raw text contents of the file (YAML / Helm template).",
        examples=["apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: {{ .Release.Name }}\n"],
    )


class ChartMetadata(BaseModel):
    """Chart metadata fields."""

    display_name: str | None = Field(
        default=None,
        description="Human-readable name shown in the AIWB UI.",
        examples=["JupyterLab Workspace"],
    )
    slug: str | None = Field(
        default=None,
        description="URL-safe identifier for the chart.",
        examples=["jupyterlab"],
    )
    description: str | None = Field(
        default=None,
        description="Short single-line summary of what the chart deploys.",
        examples=["Interactive Jupyter notebook environment with GPU support"],
    )
    long_description: str | None = Field(
        default=None,
        description="Extended Markdown description rendered on the chart's detail page.",
        examples=[
            "# JupyterLab\n\nLaunches a JupyterLab pod with optional GPU attachment, persistent home volume, and pre-installed PyTorch."
        ],
    )
    category: str | None = Field(
        default=None,
        description="Catalog grouping used by the UI (e.g. 'workspace', 'inference', 'fine-tuning').",
        examples=["workspace"],
    )
    tags: list[str] | None = Field(
        default=None,
        description="Free-form tags for filtering and search.",
        examples=[["jupyter", "notebook", "python"]],
    )
    featured_image: str | None = Field(
        default=None,
        description="URL of an icon/illustration shown in the catalog tile.",
        examples=["https://assets.example.com/charts/jupyterlab.png"],
    )
    required_resources: ChartRequiredResources | None = Field(
        default=None,
        description="Default resource hints surfaced to the user when deploying.",
        examples=[{"gpuCount": 1, "gpuMemory": 32, "cpuCoreCount": 4, "systemMemory": 64}],
    )
    external_url: str | None = Field(
        default=None,
        description="Optional link to upstream documentation or the project homepage.",
        examples=["https://jupyter.org"],
    )

    @field_validator("required_resources", mode="before")
    @classmethod
    def parse_required_resources(cls, v: Any) -> Any:
        """Parse required_resources from FastAPI multipart form data."""
        # Handle direct JSON string from form data
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        # FastAPI can also send as list containing JSON string
        elif isinstance(v, list) and len(v) == 1 and isinstance(v[0], str):
            try:
                return json.loads(v[0])
            except json.JSONDecodeError:
                return None
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v):
        """Parse tags from FastAPI multipart form data."""
        # Handle direct JSON string from form data
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                raise ValueError("Tags must be a valid JSON list or a list of strings.")
        return v


class ChartBase(ChartMetadata):
    """Base chart schema with core fields and metadata."""

    name: str = Field(
        min_length=3,
        max_length=64,
        description="Unique chart identifier within the cluster (slug-style).",
        examples=["jupyterlab"],
    )
    type: WorkloadType = Field(
        description="Workload class the chart can be used to render.",
        examples=["WORKSPACE"],
    )


class ChartCreate(ChartBase):
    """API schema for creating charts."""

    signature: UploadFile | Path = File(...)
    files: list[UploadFile | Path] | None = File(None)

    async def to_data(self) -> dict:
        """Convert schema to dict with parsed file data for database storage."""
        data = self.model_dump(exclude={"signature", "files"})
        data["signature"] = await _parse_signature_file(self.signature)
        data["files"] = await _parse_chart_files(self.files) if self.files else []
        return data


class ChartUpdate(ChartMetadata):
    """API schema for updating charts."""

    name: str | None = Field(None, min_length=3, max_length=64)
    type: WorkloadType | None = None
    signature: UploadFile | Path | None = File(None)
    files: list[UploadFile | Path] | None = File(None)

    async def to_data(self) -> dict:
        """Convert schema to dict with parsed file data for database storage."""
        data = self.model_dump(exclude={"signature", "files"}, exclude_none=True)
        if self.signature:
            data["signature"] = await _parse_signature_file(self.signature)
        if self.files is not None:
            data["files"] = await _parse_chart_files(self.files)
        return data


class ChartResponse(BaseEntityPublic, ChartBase):
    """Response schema for charts."""

    signature: ChartSignature
    files: list[ChartFile] = []
    usage_scope: WorkspaceUsageScope


class ChartListResponse(BaseEntityPublic, ChartBase):
    """Lightweight response for listing charts."""

    usage_scope: WorkspaceUsageScope
