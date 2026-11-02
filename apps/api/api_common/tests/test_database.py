# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import api_common.database as db_module


async def test_session_scope_reraises_original_error_when_rollback_and_close_fail(monkeypatch):
    session = AsyncMock(spec=AsyncSession)
    session.rollback.side_effect = RuntimeError("connection already broken")
    session.close.side_effect = RuntimeError("connection already broken")
    monkeypatch.setattr(db_module, "session_maker", lambda: session)

    original_error = ValueError("something went wrong in the caller")

    with pytest.raises(ValueError, match="something went wrong in the caller"):
        async with db_module.session_scope() as scoped_session:
            assert scoped_session is session
            raise original_error

    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()


async def test_session_scope_logs_when_rollback_fails(monkeypatch):
    session = AsyncMock(spec=AsyncSession)
    session.rollback.side_effect = RuntimeError("connection already broken")
    monkeypatch.setattr(db_module, "session_maker", lambda: session)

    logged = []
    monkeypatch.setattr(db_module.logger, "exception", lambda msg, *a, **kw: logged.append(msg))

    with pytest.raises(ValueError):
        async with db_module.session_scope():
            raise ValueError("original failure")

    assert logged == ["Failed to roll back database session"]
