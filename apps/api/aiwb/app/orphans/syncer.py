# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Runs reclamation on the poller's schedule, at its own much slower interval."""

from fastapi import FastAPI
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..dispatch.kube_client import KubernetesClient
from ..minio.client import MinioClient
from ..openbao.client import OpenBaoClient
from ..projects.gateway import get_namespaces
from .config import CLEANUP_LOCK_KEY
from .reap import reclaim

# Set at startup. The poller hands syncers a session and a kube client; object storage and the
# credential store are reached through neither, and are the same process-wide clients the request
# path already uses.
_minio_client: MinioClient | None = None
_openbao_client: OpenBaoClient | None = None


def bind_clients(app_state: FastAPI) -> None:
    global _minio_client, _openbao_client
    _minio_client = app_state.minio_client
    _openbao_client = app_state.openbao_client


async def reclaim_orphaned_data(session: AsyncSession, kube_client: KubernetesClient) -> None:
    """Find and reclaim data whose project is gone.

    Only registered when reclamation is switched on, so reaching here means an operator has already
    chosen to act.
    """
    if _minio_client is None:
        logger.warning("Object storage is unavailable; skipping the search for abandoned data")
        return

    if _openbao_client is None:
        logger.error("OpenBao is unavailable; refusing to reclaim abandoned data")
        return

    # Correctness does not rest on this: timestamp checks guard each deletion, so a lost lock costs
    # wasted effort rather than a wrong outcome. It is here because the poller runs in every
    # replica, and a bucket-wide scan is not work to do twice over.
    acquired = await session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": CLEANUP_LOCK_KEY})
    if not acquired:
        logger.debug("Another replica is already reclaiming abandoned data")
        return

    live_namespaces = await get_namespaces(kube_client)
    if not live_namespaces:
        logger.error("No namespaces are visible; refusing to treat the estate as abandoned")
        await session.rollback()
        return

    try:
        await reclaim(session, kube_client, _minio_client, _openbao_client, live_namespaces)
    finally:
        # Transaction-level locks release on commit or rollback, keeping lock ownership tied to
        # the transaction rather than to whichever pooled connection the session uses next.
        await session.rollback()
