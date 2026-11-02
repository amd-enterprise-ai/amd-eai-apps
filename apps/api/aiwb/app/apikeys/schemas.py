# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from pydantic import AwareDatetime, Field

from api_common.collections import BasePaginationList, PaginationConditions
from api_common.schemas import BaseEntityPublic, BaseModel


class ApiKeyCreate(BaseModel):
    """Schema for creating a new API key"""

    display_name: str = Field(
        description="User-friendly name for the API key",
        examples=["llama-3-prod-key"],
    )
    ttl: str = Field(
        default="0",
        description="Time to live (e.g., '1h', '24h', '30d', '0' for never)",
        examples=["24h", "30d", "0"],
    )
    aim_ids: list[str] = Field(
        default_factory=list,
        description="List of AIM IDs to bind this API key to (use AIM service IDs from workloads)",
        examples=[["7f3b6c8e-2a1d-4b9f-9c12-1a2b3c4d5e6f"]],
    )


class ApiKeyResponse(BaseEntityPublic):
    """Schema for API key response in list view (without ttl/expires_at/renewable/num_uses)"""

    display_name: str = Field(
        description="User-friendly name for the API key",
        examples=["llama-3-prod-key"],
    )
    truncated_key: str = Field(
        description="Truncated API key for display (e.g., 'amd_aim_api_key_••••••••1234')",
        examples=["amd_aim_api_key_••••••••a1b2"],
    )
    namespace: str = Field(
        description="The namespace this key belongs to",
        examples=["acme-summarizer"],
    )


class ApiKeysList(BasePaginationList):
    """Paginated list of API keys."""

    data: list[ApiKeyResponse]


class ListApiKeysQuery(PaginationConditions):
    """Query parameters for listing API keys."""

    page: int = Field(default=1, ge=1)
    # Bound page_size so a single client cannot fetch arbitrarily large pages.
    page_size: int = Field(default=10, ge=1, le=100)


class ApiKeyWithFullKey(ApiKeyResponse):
    """
    Schema for API key response that includes the full key.
    This is only returned once during creation.
    """

    ttl: str | None = Field(
        default=None,
        description="Time to live requested at creation ('0'/None = never)",
        examples=["86400"],
    )
    expires_at: AwareDatetime | None = Field(
        default=None,
        description="Expiration timestamp (None = never)",
        examples=["2026-06-28T12:00:00Z"],
    )
    full_key: str = Field(
        description="The complete API key with prefix (only shown once during creation)",
        examples=["amd_aim_api_key_hvs.CAESIJlWWvb3r..."],
    )


class ApiKeyDetails(ApiKeyResponse):
    """
    Schema for detailed API key information.
    Includes expiry and the set of models (workload-ids) the key is bound to.
    """

    ttl: str | None = Field(
        default=None,
        description="Time to live ('0'/None = never)",
        examples=["86400"],
    )
    expires_at: AwareDatetime | None = Field(
        default=None,
        description="Expiration timestamp (None = never)",
        examples=["2026-06-28T12:00:00Z"],
    )
    groups: list[str] = Field(
        default_factory=list,
        description="Workload-ids of the models this key is bound to (its per-backend Secret membership)",
        examples=[["7f3b6c8e-2a1d-4b9f-9c12-1a2b3c4d5e6f"]],
    )


class ApiKeyUpdate(BaseModel):
    """Schema for updating an API key's AIM bindings"""

    aim_ids: list[str] = Field(
        description="List of AIM IDs to bind this API key to (replaces existing bindings)",
        examples=[["7f3b6c8e-2a1d-4b9f-9c12-1a2b3c4d5e6f", "9a8b7c6d-5e4f-3a2b-1c0d-987654321abc"]],
    )


# ── API key metrics ──────────────────────────────────────────────────────────

# Each datapoint is a time bucket with per-service values keyed by aim_service_id.
# Wide format: { date: ISO string, <aim_service_id>: float, ... }
# This mirrors the frontend ApiKeyMetricsDataPoint type.
ApiKeyMetricsDataPoint = dict[str, float | str]


class ApiKeyMetricsStats(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_tokens: int
    linked_deployments: int


class ApiKeyRequestsTimeseries(BaseModel):
    total: list[ApiKeyMetricsDataPoint]
    successful: list[ApiKeyMetricsDataPoint]
    failed: list[ApiKeyMetricsDataPoint]


class ApiKeyTokensTimeseries(BaseModel):
    total: list[ApiKeyMetricsDataPoint]
    input: list[ApiKeyMetricsDataPoint]
    output: list[ApiKeyMetricsDataPoint]


class ApiKeyMetricsResponse(BaseModel):
    stats: ApiKeyMetricsStats
    services: list[str]
    requests_over_time: ApiKeyRequestsTimeseries
    tokens_over_time: ApiKeyTokensTimeseries
