# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the OpenBao KV client (API-key token vault)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.openbao.client import OpenBaoClient


def _resp(status: int = 200, payload: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value=payload or {})
    return r


def _client() -> OpenBaoClient:
    c = OpenBaoClient("http://openbao:8200", "roottoken", kv_mount="secrets", path_prefix="apikeys")
    c.client = MagicMock()
    c.client.post = AsyncMock(return_value=_resp())
    c.client.get = AsyncMock(return_value=_resp(404))
    c.client.delete = AsyncMock(return_value=_resp(204))
    return c


@pytest.mark.asyncio
async def test_put_token_sets_ttl_then_writes_data() -> None:
    c = _client()
    await c.put_token("kid", "tokval", "ns", "token-ns-k", ttl="24h")

    calls = c.client.post.await_args_list
    assert len(calls) == 2
    # 1) native expiry on the metadata path
    assert calls[0].args[0] == "/secrets/metadata/apikeys/kid"
    assert calls[0].kwargs["json"] == {"delete_version_after": "24h"}
    # 2) the token on the data path
    assert calls[1].args[0] == "/secrets/data/apikeys/kid"
    assert calls[1].kwargs["json"]["data"]["token"] == "tokval"
    assert calls[1].kwargs["json"]["data"]["client_id"] == "token-ns-k"


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl", [None, "", "0", "0s"])
async def test_put_token_never_expires_skips_metadata(ttl: str | None) -> None:
    c = _client()
    await c.put_token("kid", "tokval", "ns", "cid", ttl=ttl)

    calls = c.client.post.await_args_list
    assert len(calls) == 1  # only the data write, no delete_version_after
    assert calls[0].args[0] == "/secrets/data/apikeys/kid"


@pytest.mark.asyncio
async def test_get_token_returns_value() -> None:
    c = _client()
    c.client.get = AsyncMock(return_value=_resp(200, {"data": {"data": {"token": "v"}}}))
    assert await c.get_token("kid") == "v"


@pytest.mark.asyncio
async def test_get_token_missing_returns_none() -> None:
    c = _client()
    c.client.get = AsyncMock(return_value=_resp(404))
    assert await c.get_token("kid") is None


@pytest.mark.asyncio
async def test_delete_token_tolerates_404() -> None:
    c = _client()
    c.client.delete = AsyncMock(return_value=_resp(404))
    await c.delete_token("kid")  # must not raise
    c.client.delete.assert_awaited_once_with("/secrets/metadata/apikeys/kid")
