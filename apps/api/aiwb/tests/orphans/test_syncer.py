# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import start_pollers  # type: ignore[attr-defined]
from app.minio.client import MinioClient
from app.orphans.config import CLEANUP_INTERVAL_SECONDS
from app.orphans.syncer import reclaim_orphaned_data


def session_holding_the_lock(acquired: bool = True) -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = acquired
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_the_app_switch_gates_reclamation_registration(enabled: bool) -> None:
    register = MagicMock()

    with (
        patch("app.CLEANUP_ENABLED", enabled),
        patch("app.poller.register_syncer", register),
        patch("app.poller.start_poller", AsyncMock()),
    ):
        await start_pollers()

    registered_syncers = {call.args[0] for call in register.call_args_list}
    assert (reclaim_orphaned_data in registered_syncers) is enabled
    if enabled:
        reclaim_call = next(call for call in register.call_args_list if call.args[0] is reclaim_orphaned_data)
        assert reclaim_call.kwargs["interval_seconds"] == CLEANUP_INTERVAL_SECONDS


@pytest.mark.asyncio
async def test_enabled_reclaims_orphaned_data() -> None:
    session = session_holding_the_lock()

    with (
        patch("app.orphans.syncer._minio_client", MagicMock(spec=MinioClient)),
        patch("app.orphans.syncer._openbao_client", MagicMock()),
        patch("app.orphans.syncer.get_namespaces", AsyncMock(return_value=[MagicMock()])),
        patch("app.orphans.syncer.reclaim", AsyncMock()) as reclaim,
    ):
        await reclaim_orphaned_data(session, MagicMock())

    assert len(reclaim.await_args_list[0].args) == 5
    assert "pg_try_advisory_xact_lock" in str(session.scalar.await_args.args[0])


@pytest.mark.asyncio
async def test_a_replica_that_cannot_take_the_lock_does_no_work() -> None:
    session = session_holding_the_lock(acquired=False)

    with (
        patch("app.orphans.syncer._minio_client", MagicMock(spec=MinioClient)),
        patch("app.orphans.syncer._openbao_client", MagicMock()),
        patch("app.orphans.syncer.get_namespaces", AsyncMock()) as get_namespaces,
        patch("app.orphans.syncer.reclaim", AsyncMock()) as reclaim,
    ):
        await reclaim_orphaned_data(session, MagicMock())

    reclaim.assert_not_called()
    session.execute.assert_not_awaited()
    get_namespaces.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_lock_is_released_even_when_reclamation_fails() -> None:
    """The transaction-level lock is rolled back when reclamation fails."""
    session = session_holding_the_lock()

    with (
        patch("app.orphans.syncer._minio_client", MagicMock(spec=MinioClient)),
        patch("app.orphans.syncer._openbao_client", MagicMock()),
        patch("app.orphans.syncer.get_namespaces", AsyncMock(return_value=[MagicMock()])),
        patch("app.orphans.syncer.reclaim", AsyncMock(side_effect=RuntimeError("storage down"))),
        pytest.raises(RuntimeError),
    ):
        await reclaim_orphaned_data(session, MagicMock())

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_without_credential_store_nothing_is_attempted() -> None:
    session = session_holding_the_lock()

    with (
        patch("app.orphans.syncer._minio_client", MagicMock(spec=MinioClient)),
        patch("app.orphans.syncer._openbao_client", None),
        patch("app.orphans.syncer.reclaim", AsyncMock()) as reclaim,
    ):
        await reclaim_orphaned_data(session, MagicMock())

    reclaim.assert_not_called()
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_without_visible_namespaces_nothing_is_attempted() -> None:
    session = session_holding_the_lock()

    with (
        patch("app.orphans.syncer._minio_client", MagicMock(spec=MinioClient)),
        patch("app.orphans.syncer._openbao_client", MagicMock()),
        patch("app.orphans.syncer.get_namespaces", AsyncMock(return_value=[])),
        patch("app.orphans.syncer.reclaim", AsyncMock()) as reclaim,
    ):
        await reclaim_orphaned_data(session, MagicMock())

    reclaim.assert_not_called()
    session.scalar.assert_awaited_once()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_without_object_storage_nothing_is_attempted() -> None:
    """Half a pass would read as "nothing else to reclaim", which is the dangerous half."""
    session = session_holding_the_lock()

    with (
        patch("app.orphans.syncer._minio_client", None),
    ):
        await reclaim_orphaned_data(session, MagicMock())

    session.scalar.assert_not_awaited()
