# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Request/response schemas for the inference capability API.

These schemas are deliberately thin wrappers around the existing AIM schemas
to keep the wire contract aligned with the underlying live data model
(v1alpha2 AIMService). Reusing them avoids duplicate validation and keeps
the client-facing surface consistent regardless of which path is called.
"""

from typing import Annotated, Any

from pydantic import Field

from api_common.collections import BasePaginationList, PaginationConditions
from api_common.schemas import BaseModel

from ..aims.crds import AIMProfileResource
from ..aims.enums import AcceleratorType, AIMModelStatus, AIMServiceStatus
from ..aims.schemas import AIMDeployRequest, AIMResponse, AIMServicePatchRequest, AIMServiceResponse
from .enums import InferenceCapability


class InferenceDeployRequest(AIMDeployRequest):
    """Deploy a model through the inference capability.

    Currently identical to ``AIMDeployRequest``; kept as a subclass so the
    inference contract can evolve independently (e.g. adding chart-based
    deployments) without breaking the legacy AIM route.
    """


class InferencePatchRequest(AIMServicePatchRequest):
    """Patch an inference deployment: its adapter set, its scaling policy, or both."""


class InferenceDeploymentResponse(AIMServiceResponse):
    """Inference deployment response.

    Inherits every field of ``AIMServiceResponse`` — including the computed
    ``endpoints`` map. ``endpoints.internal`` is the in-cluster URL the AIWB
    UI uses for direct-to-AIM chat.
    """


class InferenceDeploymentsList(BasePaginationList):
    """Paginated list of inference deployments."""

    data: list[InferenceDeploymentResponse]


class InferenceModelsList(BasePaginationList):
    """Paginated list of inference base models (cluster catalog)."""

    data: list[AIMResponse]


class InferenceProfilesList(BasePaginationList):
    """Paginated list of AIMClusterProfile / AIMProfile resources."""

    data: list[AIMProfileResource]


class ListInferenceProfilesQuery(PaginationConditions):
    """Query parameters for listing inference profiles.

    ``aim_id`` is repeatable; pass once to filter by a single aimId, or
    multiple times to batch several into one round-trip
    (``?aimId=a&aimId=b&aimId=c``). When omitted, the full profile catalog
    is returned (paginated).
    """

    page: int = Field(default=1, ge=1)
    # Bound page_size so a single client cannot fetch arbitrarily large pages.
    page_size: int = Field(default=10, ge=1, le=100)
    # Cap fan-out: each aim_id triggers one parallel k8s list call in the gateway.
    aim_id: list[Annotated[str, Field(min_length=1)]] | None = Field(
        default=None,
        max_length=50,
        description=(
            "Filter by canonical model architecture identifier "
            "(matches profile `spec.aimId`). Repeatable to OR multiple "
            "values, e.g. `?aimId=meta-llama/Llama-3&aimId=Cohere/cmd-a`. "
            "Max 50 values per request."
        ),
        examples=[["meta-llama/Llama-3.1-8B-Instruct"]],
    )


class ListInferenceModelsQuery(PaginationConditions):
    """Query parameters for listing inference base models."""

    page: int = Field(default=1, ge=1)
    # Bound page_size so a single client cannot fetch arbitrarily large pages.
    page_size: int = Field(default=10, ge=1, le=100)
    status_filter: list[AIMModelStatus] | None = Field(
        default=None,
        description="Filter base models by status (repeatable), e.g. `?statusFilter=Ready&statusFilter=Failed`.",
        examples=[["Ready", "Failed"]],
    )
    accelerator_type: list[AcceleratorType] | None = Field(
        default=None,
        description=(
            "Filter base models by accelerator family. Repeat to OR multiple values, "
            "e.g. `?acceleratorType=cpu&acceleratorType=gpu`. Case-sensitive lowercase "
            "values: `cpu` or `gpu`. Models with no published hardware are excluded "
            "when this filter is set."
        ),
        examples=[["cpu"], ["cpu", "gpu"]],
    )


class ListInferenceDeploymentsQuery(PaginationConditions):
    """Query parameters for listing inference deployments.

    The ``capability`` filter narrows the result set to deployments matching
    a specific capability (e.g. ``chat``). When omitted, all deployments are
    returned; ``status_filter`` further restricts the list by AIMService
    status. Pagination applies after capability and status filters.
    """

    page: int = Field(default=1, ge=1, examples=[1])
    # Bound page_size so a single client cannot fetch arbitrarily large pages.
    page_size: int = Field(default=10, ge=1, le=100, examples=[10])
    capability: InferenceCapability | None = Field(
        default=None,
        description=(
            "Filter deployments by capability, derived from the model's catalog "
            "tags. `chat` returns chat-completion deployments; `transcription` "
            "returns speech-to-text (Whisper-style) catalog deployments. "
            "Custom-onboarded (namespace) models are currently classified as "
            "chat only. Only fully-ready deployments are returned."
        ),
        examples=["chat", "transcription"],
    )
    status_filter: list[AIMServiceStatus] | None = Field(
        default=None,
        description="Optional filter by deployment status (repeatable).",
        examples=[["Running", "Failed"]],
    )


# ---------------------------------------------------------------------------
# Replica response schemas
# ---------------------------------------------------------------------------
# These models mirror the subset of Kubernetes pod fields useful for showing
# replica status. Field names follow camelCase via alias_generator, with one
# explicit override: podIP (Kubernetes uses uppercase "IP", not "Ip").
# ---------------------------------------------------------------------------


class ReplicaContainerStatus(BaseModel):
    ready: bool | None = Field(None, examples=[True])
    restart_count: int | None = Field(None, examples=[0])
    state: dict[str, Any] | None = Field(None, examples=[{"running": {"startedAt": "2026-01-15T10:00:00Z"}}])


class ReplicaCondition(BaseModel):
    type: str | None = Field(None, examples=["Ready"])
    status: str | None = Field(None, examples=["True"])
    reason: str | None = Field(None, examples=["ContainersReady"])
    message: str | None = Field(None, examples=["All containers are ready"])


class ReplicaStatus(BaseModel):
    phase: str | None = Field(None, examples=["Running"])
    # sanitize_for_serialization produces "podIP" (K8s JSON format); the serialization alias
    # uses "podIp" (standard camelCase) so the API response is consistent with other fields.
    pod_ip: str | None = Field(None, alias="podIP", serialization_alias="podIp", examples=["10.244.1.42"])
    container_statuses: list[ReplicaContainerStatus] | None = None
    conditions: list[ReplicaCondition] | None = None


class ReplicaResources(BaseModel):
    limits: dict[str, str] | None = Field(None, examples=[{"cpu": "4", "memory": "16Gi", "amd.com/gpu": "1"}])


class ReplicaContainer(BaseModel):
    resources: ReplicaResources | None = None


class ReplicaSpec(BaseModel):
    node_name: str | None = Field(None, examples=["mi300x-worker-01"])
    containers: list[ReplicaContainer] | None = None


class ReplicaMetadata(BaseModel):
    name: str = Field(..., examples=["acme-summarizer-aim-7f3b6c8e-0"])
    creation_timestamp: str | None = Field(None, examples=["2026-01-15T10:00:00Z"])


class InferenceReplicaResponse(BaseModel):
    """Kubernetes pod data for a single inference deployment replica."""

    metadata: ReplicaMetadata
    status: ReplicaStatus | None = None
    spec: ReplicaSpec | None = None
