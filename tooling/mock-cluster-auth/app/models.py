# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from typing import Any

from pydantic import BaseModel


class CreateApiKeyRequest(BaseModel):
    """Request model for creating an API key."""

    ttl: str = "0"
    num_uses: int = 0
    meta: dict[str, Any] | None = None
    period: str = ""
    renewable: bool = True
    explicit_max_ttl: str = ""


class RevokeApiKeyRequest(BaseModel):
    """Request model for revoking an API key."""

    key_id: str


class RenewApiKeyRequest(BaseModel):
    """Request model for renewing an API key."""

    key_id: str
    increment: str | None = None


class LookupApiKeyRequest(BaseModel):
    """Request model for looking up an API key."""

    key_id: str


class CreateGroupRequest(BaseModel):
    """Request model for creating a group."""

    name: str | None = None
    id: str | None = None


class BindApiKeyRequest(BaseModel):
    """Request model for binding an API key to a group."""

    key_id: str
    group_id: str


class UnbindApiKeyRequest(BaseModel):
    """Request model for unbinding an API key from a group."""

    key_id: str
    group_id: str
