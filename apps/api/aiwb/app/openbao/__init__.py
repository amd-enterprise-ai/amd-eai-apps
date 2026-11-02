# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""OpenBao KV client for API-key token storage."""

from fastapi import Request
from loguru import logger

from .client import OpenBaoClient, init_openbao_client


def get_openbao_client(request: Request) -> OpenBaoClient | None:
    """
    FastAPI dependency returning the OpenBao client from app state.

    The OpenBao/ESO store is the sole API-key path. Returns None when the store is disabled
    (``openBao.enabled: false`` renders no OPENBAO_ADDR/OPENBAO_TOKEN) or its initialization
    failed — in which case every API-key mutation raises an ExternalServiceError rather than
    silently skipping the store.
    """
    client = getattr(request.app.state, "openbao_client", None)
    if client is None:
        logger.debug("OpenBao client not available in app.state (initialization failed)")
    return client


__all__ = ["OpenBaoClient", "get_openbao_client", "init_openbao_client"]
