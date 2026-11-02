# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger

from .models import (
    BindApiKeyRequest,
    CreateApiKeyRequest,
    CreateGroupRequest,
    LookupApiKeyRequest,
    RenewApiKeyRequest,
    RevokeApiKeyRequest,
    UnbindApiKeyRequest,
)
from .service import ClusterAuthService

router = APIRouter()

# Global service instance (in-memory storage)
_service = ClusterAuthService()


def get_admin_token(x_admin_token: str | None = Header(None, alias="X-Admin-Token")) -> str:
    """
    Dependency to extract and validate admin token from X-Admin-Token header.

    Args:
        x_admin_token: Admin token from header

    Returns:
        Admin token string

    Raises:
        HTTPException: If token is missing or invalid
    """
    expected_token = os.getenv("ADMIN_TOKEN", "mock-admin-token")

    if not x_admin_token:
        logger.warning("Missing X-Admin-Token header")
        raise HTTPException(status_code=401, detail="Missing X-Admin-Token header")

    if x_admin_token != expected_token:
        logger.warning("Invalid admin token provided")
        raise HTTPException(status_code=403, detail="Invalid admin token")

    return x_admin_token


@router.post("/apikey/create")
async def create_api_key(
    request: CreateApiKeyRequest,
    _: str = Depends(get_admin_token),
) -> dict:
    """
    Create a new API key with associated entity.

    Returns:
        dict with api_key, key_id, and other metadata
    """
    try:
        return await _service.create_api_key(
            ttl=request.ttl,
            num_uses=request.num_uses,
            meta=request.meta,
            period=request.period,
            renewable=request.renewable,
            explicit_max_ttl=request.explicit_max_ttl,
        )
    except Exception as e:
        logger.exception(f"Error creating API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apikey/revoke")
async def revoke_api_key(
    request: RevokeApiKeyRequest,
    _: str = Depends(get_admin_token),
) -> dict:
    """
    Revoke an API key.

    Returns:
        Empty dict on success
    """
    try:
        await _service.revoke_api_key(request.key_id)
        return {}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Error revoking API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apikey/renew")
async def renew_api_key(
    request: RenewApiKeyRequest,
    _: str = Depends(get_admin_token),
) -> dict:
    """
    Renew an API key's lease.

    Returns:
        dict with lease_duration
    """
    try:
        return await _service.renew_api_key(request.key_id, request.increment)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Error renewing API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apikey/lookup")
async def lookup_api_key(
    request: LookupApiKeyRequest,
    _: str = Depends(get_admin_token),
) -> dict:
    """
    Get API key metadata.

    Returns:
        dict with key metadata including groups
    """
    try:
        return await _service.lookup_api_key(request.key_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Error looking up API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apikey/group")
async def create_group(
    request: CreateGroupRequest,
    _: str = Depends(get_admin_token),
) -> dict:
    """
    Create a new group.

    Returns:
        dict with id and name
    """
    try:
        return await _service.create_group(name=request.name, group_id=request.id)
    except Exception as e:
        logger.exception(f"Error creating group: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/apikey/group")
async def delete_group(
    id: str,
    _: str = Depends(get_admin_token),
) -> dict:
    """
    Delete a group.

    Args:
        id: Group ID to delete

    Returns:
        Empty dict on success
    """
    try:
        await _service.delete_group(id)
        return {}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Error deleting group: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apikey/bind")
async def bind_api_key(
    request: BindApiKeyRequest,
    _: str = Depends(get_admin_token),
) -> dict:
    """
    Bind an API key to a group.

    Returns:
        dict with updated groups list
    """
    try:
        return await _service.bind_api_key_to_group(request.key_id, request.group_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Error binding API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apikey/unbind")
async def unbind_api_key(
    request: UnbindApiKeyRequest,
    _: str = Depends(get_admin_token),
) -> dict:
    """
    Unbind an API key from a group.

    Returns:
        dict with updated groups list
    """
    try:
        return await _service.unbind_api_key_from_group(request.key_id, request.group_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Error unbinding API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check() -> dict:
    """
    Health check endpoint.

    Returns:
        dict with status
    """
    return {"status": "healthy"}
