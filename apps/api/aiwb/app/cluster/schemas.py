# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Cluster resource schemas for AIWB API."""

from pydantic import Field

from api_common.schemas import BaseModel

from .enums import ClusterAcceleratorType


class AvailableResources(BaseModel):
    """Available cluster resources."""

    cpu_milli_cores: int = Field(
        ...,
        description="Available CPU in milli-cores (1 core = 1000 milli-cores)",
        examples=[64000],
    )
    memory_bytes: int = Field(
        ...,
        description="Available memory in bytes",
        examples=[549755813888],
    )
    ephemeral_storage_bytes: int = Field(
        ...,
        description="Available ephemeral storage in bytes",
        examples=[10995116277760],
    )
    gpu_count: int = Field(
        ...,
        description="Total number of GPUs available",
        examples=[8],
    )


class ClusterResourcesData(BaseModel):
    """Cluster resources data."""

    available_resources: AvailableResources = Field(
        ...,
        description="Available cluster resources",
    )
    total_node_count: int = Field(
        ...,
        description="Total number of nodes in the cluster",
        examples=[4],
    )


class ClusterResourcesResponse(BaseModel):
    """Response model for cluster resources endpoint."""

    data: ClusterResourcesData = Field(
        ...,
        description="Cluster resources data",
    )


class AimImageFamily(BaseModel):
    """A supported aim-engine container image family for runtime profile selection."""

    family_id: str = Field(
        ...,
        description="Stable catalog key for the image family (e.g. 'automatic', 'aim-base'), not a UUID.",
        examples=["automatic", "aim-base"],
    )
    display_name: str = Field(
        ...,
        description="Human-readable label for UI dropdowns.",
        examples=["Automatic", "aim-base"],
    )
    repository: str | None = Field(
        None,
        description="Container repository without tag. Null for the Automatic entry.",
        examples=["amdenterpriseai/aim-base"],
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Available image tags/versions for this family.",
        examples=[["0.11"], []],
    )


class ResourceQuotas(BaseModel):
    """Per-resource quota values from the project's Kueue ClusterQueue."""

    gpu_count: int | None = Field(
        None, description="GPU quota (nominalQuota for amd.com/gpu or nvidia.com/gpu).", examples=[4]
    )
    cpu_milli_cores: int | None = Field(None, description="CPU quota in milli-cores.", examples=[8000])
    memory_bytes: int | None = Field(None, description="Memory quota in bytes.", examples=[17179869184])
    ephemeral_storage_bytes: int | None = Field(None, description="Ephemeral storage quota in bytes.", examples=[0])


class ProjectQuotaResponse(BaseModel):
    """Response model for the project resource quota endpoint."""

    is_quota_managed: bool = Field(
        ...,
        description="True when the project has a Kueue LocalQueue and ClusterQueue managing its resource quotas.",
    )
    quotas: ResourceQuotas = Field(
        ...,
        description="Per-resource quota values. Fields are None when the resource is not configured in the ClusterQueue.",
    )


class ClusterAccelerator(BaseModel):
    """An accelerator product available on the cluster."""

    device_id: str = Field(
        ...,
        description="Accelerator identifier (GPU device type ID, or model label fallback when unavailable).",
        examples=["74a1", "MI300X", "EPYC_ZEN5"],
    )
    product_name: str = Field(
        ...,
        description="Display name from node labels. May be empty when labels do not provide a product name.",
        examples=["AMD Instinct MI300X", "AMD EPYC ZEN5"],
    )
    allocatable_count: int = Field(
        ...,
        ge=0,
        description="Total allocatable units for this accelerator model aggregated across ready nodes.",
        examples=[8, 760],
    )
    accelerator_model: str | None = Field(
        default=None,
        description=(
            "Canonical acceleratorModel from aim-engine node feature labels "
            "(feature.node.kubernetes.io/aim-accelerator.*), when present."
        ),
        examples=["MI300X", "R9700"],
    )
    accelerator_type: ClusterAcceleratorType = Field(
        ...,
        description="Accelerator family type inferred from model labels.",
        examples=["gpu", "cpu", "apu", "unknown"],
    )
    accelerator_vendor: str = Field(
        ...,
        description="Lowercase accelerator vendor from aim-engine node labels when available.",
        examples=["amd", "nvidia", ""],
    )
