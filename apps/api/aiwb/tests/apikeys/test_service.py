# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for API key service layer."""

import math
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ConflictException, ExternalServiceError, NotFoundException
from app.apikeys import service
from app.apikeys.repository import get_api_key_by_id, get_api_keys_for_namespace
from app.apikeys.schemas import ApiKeyCreate, ApiKeyUpdate
from tests import factory


@pytest.mark.asyncio
async def test_truncate_api_key() -> None:
    """Test API key truncation preserves prefix and shows last 4 chars."""
    full_key = "amd_aim_api_key_hvs.abc123def456"
    truncated = service.truncate_api_key(full_key)

    assert truncated.startswith("amd_aim_api_key_")
    assert truncated.endswith("f456")  # Last 4 chars of the token part
    assert "••••••••" in truncated


@pytest.mark.asyncio
async def test_truncate_api_key_invalid_prefix() -> None:
    """Test truncation fails for keys without proper prefix."""
    with pytest.raises(ValueError, match="must start with"):
        service.truncate_api_key("invalid_key_123")


@pytest.mark.asyncio
async def test_generate_api_key_has_correct_prefix() -> None:
    """generate_api_key returns a token with the expected prefix."""
    key = service.generate_api_key()
    assert key.startswith("amd_aim_api_key_")
    # prefix + urlsafe b64 token
    assert len(key) > len("amd_aim_api_key_")


@pytest.mark.asyncio
async def test_expires_at_from_ttl_never() -> None:
    """TTL of '0', '0s', '' or None maps to None (never expires)."""
    assert service._expires_at_from_ttl("0") is None
    assert service._expires_at_from_ttl("0s") is None
    assert service._expires_at_from_ttl("") is None
    assert service._expires_at_from_ttl(None) is None


@pytest.mark.asyncio
async def test_expires_at_from_ttl_hours() -> None:
    """'24h' yields a datetime approximately 24 h from now."""
    before = datetime.now(UTC)
    result = service._expires_at_from_ttl("24h")
    assert result is not None
    assert result > before
    # Allow ±5 s of clock drift in the test
    delta = (result - before).total_seconds()
    assert math.isclose(delta, 86400, abs_tol=5)


@pytest.mark.asyncio
async def test_expires_at_from_ttl_compound() -> None:
    """Compound durations like '1h30m' are summed; a partial/garbage TTL is treated as never."""
    before = datetime.now(UTC)
    result = service._expires_at_from_ttl("1h30m")
    assert result is not None
    delta = (result - before).total_seconds()
    assert math.isclose(delta, 5400, abs_tol=5)  # 1h30m == 5400s

    # Bare seconds still parse.
    assert service._expires_at_from_ttl("86400") is not None

    # A partial/unparseable TTL is treated as non-expiring rather than silently under-counted.
    assert service._expires_at_from_ttl("1h30x") is None


# ── create ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_api_key_writes_openbao_and_es_store(
    db_session: AsyncSession,
    test_namespace: str,
    test_user: str,
    mock_kube_client: AsyncMock,
    mock_openbao_client: AsyncMock,
) -> None:
    """create stores the token in OpenBao and creates the key's ExternalSecret bound to each AIM."""
    aim_ids = [str(uuid4()), str(uuid4())]
    api_key_in = ApiKeyCreate(display_name="Store Key", ttl="24h", aim_ids=aim_ids)

    with patch.object(service.es_store, "create_key_secret", AsyncMock()) as create:
        result = await service.create_api_key_in_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_in=api_key_in,
            user=test_user,
            openbao_client=mock_openbao_client,
        )

    # OpenBao must have received the token and the requested TTL.
    mock_openbao_client.put_token.assert_awaited_once()
    call_kwargs = mock_openbao_client.put_token.await_args.kwargs
    assert call_kwargs["ttl"] == "24h"

    # One ExternalSecret is created for the key: arg[4] is the display_name, arg[5] the bound set.
    create.assert_awaited_once()
    assert create.await_args is not None
    assert create.await_args.args[4] == "Store Key"
    assert create.await_args.args[5] == {aim_ids[0], aim_ids[1]}

    # Full key is present in the response (only returned once).
    assert result.full_key.startswith("amd_aim_api_key_")
    assert result.display_name == "Store Key"
    assert result.namespace == test_namespace
    assert result.created_by == test_user

    # Expiry is persisted in the DB row.
    db_record = await get_api_key_by_id(db_session, result.id, test_namespace)
    assert db_record is not None
    assert db_record.display_name == "Store Key"
    assert db_record.expires_at is not None  # ttl="24h" -> not-None


@pytest.mark.asyncio
async def test_create_api_key_rejects_client_id_collision(
    db_session: AsyncSession,
    test_namespace: str,
    test_user: str,
    mock_kube_client: AsyncMock,
    mock_openbao_client: AsyncMock,
) -> None:
    """Two display names that normalize to the same client_id are rejected on the second create."""
    # "My Key" and "my-key" both sanitize to token-<ns>-my-key.
    first = ApiKeyCreate(display_name="My Key", ttl="0", aim_ids=[])
    await service.create_api_key_in_store(
        session=db_session,
        kube_client=mock_kube_client,
        namespace=test_namespace,
        api_key_in=first,
        user=test_user,
        openbao_client=mock_openbao_client,
    )

    collide = ApiKeyCreate(display_name="my-key", ttl="0", aim_ids=[])
    with pytest.raises(ConflictException, match="normalizes to the same identifier"):
        await service.create_api_key_in_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_in=collide,
            user=test_user,
            openbao_client=mock_openbao_client,
        )


@pytest.mark.asyncio
async def test_create_api_key_no_openbao_client_raises(
    db_session: AsyncSession,
    test_namespace: str,
    test_user: str,
    mock_kube_client: AsyncMock,
) -> None:
    """create raises ExternalServiceError when openbao_client is None."""
    api_key_in = ApiKeyCreate(display_name="Bad Key", ttl="0")

    with pytest.raises(ExternalServiceError, match="OpenBao store is not configured"):
        await service.create_api_key_in_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_in=api_key_in,
            user=test_user,
            openbao_client=None,
        )


@pytest.mark.asyncio
async def test_create_api_key_no_expiry_for_zero_ttl(
    db_session: AsyncSession,
    test_namespace: str,
    test_user: str,
    mock_kube_client: AsyncMock,
    mock_openbao_client: AsyncMock,
) -> None:
    """TTL of '0' leaves expires_at as None and ttl in the response as None."""
    api_key_in = ApiKeyCreate(display_name="Immortal Key", ttl="0")

    result = await service.create_api_key_in_store(
        session=db_session,
        kube_client=mock_kube_client,
        namespace=test_namespace,
        api_key_in=api_key_in,
        user=test_user,
        openbao_client=mock_openbao_client,
    )

    assert result.expires_at is None
    assert result.ttl is None  # service sets ttl=None when there's no expiry

    db_record = await get_api_key_by_id(db_session, result.id, test_namespace)
    assert db_record is not None
    assert db_record.expires_at is None


@pytest.mark.asyncio
async def test_create_api_key_no_aim_ids(
    db_session: AsyncSession,
    test_namespace: str,
    test_user: str,
    mock_kube_client: AsyncMock,
    mock_openbao_client: AsyncMock,
) -> None:
    """create with no aim_ids still creates the key's ExternalSecret, bound to nothing."""
    api_key_in = ApiKeyCreate(display_name="Unbound Key", ttl="0", aim_ids=[])

    with patch.object(service.es_store, "create_key_secret", AsyncMock()) as create:
        result = await service.create_api_key_in_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_in=api_key_in,
            user=test_user,
            openbao_client=mock_openbao_client,
        )

    mock_openbao_client.put_token.assert_awaited_once()
    create.assert_awaited_once()
    assert create.await_args is not None
    assert create.await_args.args[4] == "Unbound Key"
    assert create.await_args.args[5] == set()
    assert result.display_name == "Unbound Key"


@pytest.mark.asyncio
async def test_create_api_key_rolls_back_on_store_failure(
    db_session: AsyncSession,
    test_namespace: str,
    test_user: str,
    mock_kube_client: AsyncMock,
    mock_openbao_client: AsyncMock,
) -> None:
    """If the OpenBao write fails the DB row is deleted and the exception propagates."""
    mock_openbao_client.put_token.side_effect = Exception("OpenBao unavailable")

    api_key_in = ApiKeyCreate(display_name="Rollback Key", ttl="24h")

    with (
        patch.object(service.es_store, "delete_key_secret", AsyncMock()),
        pytest.raises(Exception, match="OpenBao unavailable"),
    ):
        await service.create_api_key_in_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_in=api_key_in,
            user=test_user,
            openbao_client=mock_openbao_client,
        )

    # The DB must not retain the row.
    remaining = await get_api_keys_for_namespace(db_session, test_namespace)
    assert not any(k.display_name == "Rollback Key" for k in remaining)


@pytest.mark.asyncio
async def test_create_api_key_rolls_back_on_es_store_failure(
    db_session: AsyncSession,
    test_namespace: str,
    test_user: str,
    mock_kube_client: AsyncMock,
    mock_openbao_client: AsyncMock,
) -> None:
    """If an ExternalSecret write fails, the DB row is deleted and cleanup is attempted."""
    aim_id = str(uuid4())
    api_key_in = ApiKeyCreate(display_name="ES Rollback Key", ttl="24h", aim_ids=[aim_id])

    with (
        patch.object(service.es_store, "create_key_secret", AsyncMock(side_effect=Exception("K8s write failed"))),
        patch.object(service.es_store, "delete_key_secret", AsyncMock()) as rm,
        pytest.raises(Exception, match="K8s write failed"),
    ):
        await service.create_api_key_in_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_in=api_key_in,
            user=test_user,
            openbao_client=mock_openbao_client,
        )

    # Best-effort cleanup must have been called.
    rm.assert_awaited_once()
    mock_openbao_client.delete_token.assert_awaited_once()


# ── list ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_api_keys_for_namespace(
    db_session: AsyncSession,
    test_namespace: str,
) -> None:
    """Test listing API keys for a namespace returns a paginated result."""
    # Create test keys
    await factory.create_api_key(db_session, display_name="Key 1", namespace=test_namespace)
    await factory.create_api_key(db_session, display_name="Key 2", namespace=test_namespace)

    # Create key in different namespace (should not be returned)
    await factory.create_api_key(db_session, display_name="Other Key", namespace="other-namespace")

    result = await service.list_api_keys_for_namespace(
        session=db_session,
        namespace=test_namespace,
    )

    assert result.total == 2
    assert result.page == 1
    assert result.page_size == 10
    assert len(result.items) == 2
    assert {r.display_name for r in result.items} == {"Key 1", "Key 2"}
    assert all(r.namespace == test_namespace for r in result.items)


@pytest.mark.asyncio
async def test_list_api_keys_uses_default_page_args(
    db_session: AsyncSession,
    test_namespace: str,
) -> None:
    """Calling the service without page args defaults to page=1, page_size=10."""
    await factory.create_api_key(db_session, display_name="Solo Key", namespace=test_namespace)

    result = await service.list_api_keys_for_namespace(
        session=db_session,
        namespace=test_namespace,
    )

    assert result.page == 1
    assert result.page_size == 10
    assert result.total == 1


@pytest.mark.asyncio
async def test_list_api_keys_paginates(
    db_session: AsyncSession,
    test_namespace: str,
) -> None:
    """Page slicing covers the right rows and total reflects the full set."""
    for i in range(15):
        await factory.create_api_key(db_session, display_name=f"Key {i:02d}", namespace=test_namespace)

    result = await service.list_api_keys_for_namespace(
        session=db_session,
        namespace=test_namespace,
        page=2,
        page_size=10,
    )

    assert result.total == 15
    assert result.page == 2
    assert result.page_size == 10
    assert len(result.items) == 5


# ── get details ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_api_key_details_from_store(
    db_session: AsyncSession,
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """get_api_key_details reads expiry from DB and groups from es_store."""
    api_key = await factory.create_api_key(
        db_session,
        display_name="Test Key",
        namespace=test_namespace,
    )

    workload_ids = ["wl-abc", "wl-def"]
    with patch.object(service.es_store, "list_workload_ids_for_key", AsyncMock(return_value=workload_ids)) as lst:
        result = await service.get_api_key_details_from_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_id=api_key.id,
        )

    lst.assert_awaited_once()
    assert result.id == api_key.id
    assert result.display_name == "Test Key"
    assert result.groups == workload_ids
    # cluster-auth fields are gone.
    assert not hasattr(result, "renewable")
    assert not hasattr(result, "num_uses")
    assert not hasattr(result, "entity_id")
    assert not hasattr(result, "meta")


@pytest.mark.asyncio
async def test_get_api_key_details_not_found(
    db_session: AsyncSession,
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Getting details for a non-existent API key raises NotFoundException."""
    random_id = uuid4()

    with pytest.raises(NotFoundException, match="not found"):
        await service.get_api_key_details_from_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_id=random_id,
        )


@pytest.mark.asyncio
async def test_get_api_key_details_returns_expires_at_from_db(
    db_session: AsyncSession,
    test_namespace: str,
    mock_kube_client: AsyncMock,
    mock_openbao_client: AsyncMock,
) -> None:
    """expires_at in the details response comes from the DB row, not cluster-auth."""
    api_key_in = ApiKeyCreate(display_name="Expiring Key", ttl="1h")

    with patch.object(service.es_store, "create_key_secret", AsyncMock()):
        created = await service.create_api_key_in_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_in=api_key_in,
            user="user@example.com",
            openbao_client=mock_openbao_client,
        )

    with patch.object(service.es_store, "list_workload_ids_for_key", AsyncMock(return_value=[])):
        details = await service.get_api_key_details_from_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_id=created.id,
        )

    assert details.expires_at is not None


# ── delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_api_key_from_store(
    db_session: AsyncSession,
    test_namespace: str,
    mock_kube_client: AsyncMock,
    mock_openbao_client: AsyncMock,
) -> None:
    """delete removes the key from all backends, OpenBao, and the DB."""
    api_key = await factory.create_api_key(
        db_session,
        display_name="Key to Delete",
        namespace=test_namespace,
    )

    with patch.object(service.es_store, "delete_key_secret", AsyncMock()) as rm:
        await service.delete_api_key_from_store(
            session=db_session,
            namespace=test_namespace,
            api_key_id=api_key.id,
            kube_client=mock_kube_client,
            openbao_client=mock_openbao_client,
        )

    # ESO backends must be cleaned up.
    rm.assert_awaited_once()
    # OpenBao token must be deleted.
    mock_openbao_client.delete_token.assert_awaited_once_with(str(api_key.id))
    # DB row must be gone.
    deleted_key = await get_api_key_by_id(db_session, api_key.id, test_namespace)
    assert deleted_key is None


@pytest.mark.asyncio
async def test_delete_api_key_without_openbao_client(
    db_session: AsyncSession,
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """delete is refused while the store is disabled, and nothing is torn down."""
    api_key = await factory.create_api_key(
        db_session,
        display_name="No-OpenBao Delete Key",
        namespace=test_namespace,
    )

    with (
        patch.object(service.es_store, "delete_key_secret", AsyncMock()) as rm,
        pytest.raises(ExternalServiceError, match="cannot delete API key"),
    ):
        await service.delete_api_key_from_store(
            session=db_session,
            namespace=test_namespace,
            api_key_id=api_key.id,
            kube_client=mock_kube_client,
            openbao_client=None,
        )

    # Nothing may be torn down when the token cannot be revoked, or the raw token would
    # outlive every record that points at it.
    rm.assert_not_awaited()
    assert await get_api_key_by_id(db_session, api_key.id, test_namespace) is not None


@pytest.mark.asyncio
async def test_delete_api_key_not_found(
    db_session: AsyncSession,
    test_namespace: str,
    mock_kube_client: AsyncMock,
    mock_openbao_client: AsyncMock,
) -> None:
    """Deleting a non-existent key raises NotFoundException."""
    with pytest.raises(NotFoundException, match="not found"):
        await service.delete_api_key_from_store(
            session=db_session,
            namespace=test_namespace,
            api_key_id=uuid4(),
            kube_client=mock_kube_client,
            openbao_client=mock_openbao_client,
        )


# ── startup guard ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_store_matches_existing_keys_refuses_disabled_store_with_keys(
    db_session: AsyncSession,
    test_namespace: str,
) -> None:
    """Keys in the database with the store disabled must stop startup."""
    await factory.create_api_key(db_session, display_name="Left behind", namespace=test_namespace)

    with pytest.raises(RuntimeError, match="1 API key"):
        await service.ensure_store_matches_existing_keys(db_session, openbao_client=None)


@pytest.mark.asyncio
async def test_ensure_store_matches_existing_keys_allows_disabled_store_without_keys(
    db_session: AsyncSession,
) -> None:
    """A fresh install without OpenBao has no keys and starts normally."""
    await service.ensure_store_matches_existing_keys(db_session, openbao_client=None)


@pytest.mark.asyncio
async def test_ensure_store_matches_existing_keys_allows_enabled_store_with_keys(
    db_session: AsyncSession,
    test_namespace: str,
    mock_openbao_client: AsyncMock,
) -> None:
    """With the store enabled, existing keys are the normal state."""
    await factory.create_api_key(db_session, display_name="Managed", namespace=test_namespace)

    await service.ensure_store_matches_existing_keys(db_session, openbao_client=mock_openbao_client)


# ── rebind ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_api_key_bindings_in_store(
    db_session: AsyncSession,
    test_namespace: str,
    mock_kube_client: AsyncMock,
    mock_openbao_client: AsyncMock,
) -> None:
    """update_bindings calls es_store.set_key_bindings and returns updated details."""
    api_key = await factory.create_api_key(
        db_session,
        display_name="Key to Update",
        namespace=test_namespace,
    )

    target_aim = str(uuid4())
    api_key_update = ApiKeyUpdate(aim_ids=[target_aim])

    with (
        patch.object(service.es_store, "set_key_bindings", AsyncMock()) as sync,
        patch.object(service.es_store, "list_workload_ids_for_key", AsyncMock(return_value=[target_aim])),
    ):
        result = await service.update_api_key_bindings_in_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_id=api_key.id,
            api_key_update=api_key_update,
            openbao_client=mock_openbao_client,
        )

    # set_key_bindings must be called with the exact target set.
    sync.assert_awaited_once()
    assert sync.await_args is not None
    assert sync.await_args.args[-1] == {target_aim}

    # Result is the updated details.
    assert result.id == api_key.id
    assert result.groups == [target_aim]


@pytest.mark.asyncio
async def test_update_api_key_bindings_empty_aim_ids(
    db_session: AsyncSession,
    test_namespace: str,
    mock_kube_client: AsyncMock,
    mock_openbao_client: AsyncMock,
) -> None:
    """Sending an empty aim_ids list revokes all bindings."""
    api_key = await factory.create_api_key(
        db_session,
        display_name="Key to Unbind",
        namespace=test_namespace,
    )

    api_key_update = ApiKeyUpdate(aim_ids=[])

    with (
        patch.object(service.es_store, "set_key_bindings", AsyncMock()) as sync,
        patch.object(service.es_store, "list_workload_ids_for_key", AsyncMock(return_value=[])),
    ):
        result = await service.update_api_key_bindings_in_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_id=api_key.id,
            api_key_update=api_key_update,
            openbao_client=mock_openbao_client,
        )

    sync.assert_awaited_once()
    # Target set must be empty.
    assert sync.await_args is not None
    assert sync.await_args.args[-1] == set()
    assert result.groups == []


@pytest.mark.asyncio
async def test_update_api_key_bindings_without_openbao_client(
    db_session: AsyncSession,
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """A rebind is refused while the store is disabled, and no binding label changes."""
    api_key = await factory.create_api_key(
        db_session,
        display_name="Key to Update",
        namespace=test_namespace,
    )

    with (
        patch.object(service.es_store, "set_key_bindings", AsyncMock()) as sync,
        pytest.raises(ExternalServiceError, match="cannot update API key"),
    ):
        await service.update_api_key_bindings_in_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_id=api_key.id,
            api_key_update=ApiKeyUpdate(aim_ids=[str(uuid4())]),
            openbao_client=None,
        )

    sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_api_key_bindings_not_found(
    db_session: AsyncSession,
    test_namespace: str,
    mock_kube_client: AsyncMock,
    mock_openbao_client: AsyncMock,
) -> None:
    """Updating bindings for a non-existent key raises NotFoundException."""
    nonexistent_id = uuid4()
    api_key_update = ApiKeyUpdate(aim_ids=[str(uuid4())])

    with pytest.raises(NotFoundException, match="not found"):
        await service.update_api_key_bindings_in_store(
            session=db_session,
            kube_client=mock_kube_client,
            namespace=test_namespace,
            api_key_id=nonexistent_id,
            api_key_update=api_key_update,
            openbao_client=mock_openbao_client,
        )


# ── Metrics ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_api_key_usage_metrics_returns_response(
    db_session: AsyncSession,
    test_namespace: str,
    mock_prometheus_client: MagicMock,
) -> None:
    """Returns a metrics response built from Prometheus query_range results."""
    api_key = await factory.create_api_key(db_session, display_name="metrics-key", namespace=test_namespace)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 2, tzinfo=UTC)

    ts = 1704067800.0
    service_id = "aim-inference-llama3"

    def mock_query_range(query: str, **_kwargs: object) -> list[dict]:
        if "gen_ai_token_type" in query:
            return [
                {"metric": {"aim_service_id": service_id, "gen_ai_token_type": "input"}, "values": [[ts, "120.0"]]},
                {"metric": {"aim_service_id": service_id, "gen_ai_token_type": "output"}, "values": [[ts, "80.0"]]},
            ]
        if 'error_type!=""' in query:
            return [{"metric": {"aim_service_id": service_id}, "values": [[ts, "1.0"]]}]
        return [{"metric": {"aim_service_id": service_id}, "values": [[ts, "9.0"]]}]

    def mock_query(query: str, **_kwargs: object) -> list[dict]:
        if "gen_ai_client_token_usage" in query:
            return [{"metric": {}, "value": [ts, "200.0"]}]
        if 'error_type!=""' in query:
            return [{"metric": {}, "value": [ts, "1.0"]}]
        return [{"metric": {}, "value": [ts, "10.0"]}]

    mock_prometheus_client.custom_query_range.side_effect = mock_query_range
    mock_prometheus_client.custom_query.side_effect = mock_query

    result = await service.get_api_key_usage_metrics(
        session=db_session,
        namespace=test_namespace,
        api_key_id=api_key.id,
        start=start,
        end=end,
        prometheus_client=mock_prometheus_client,
    )

    assert result.services == [service_id]
    assert result.stats.total_requests == 10
    assert result.stats.total_tokens == 200
    assert result.stats.linked_deployments == 1
    assert result.stats.successful_requests == 9
    assert result.stats.failed_requests == 1
    assert len(result.requests_over_time.total) == 1
    assert result.requests_over_time.total[0]["date"].endswith("Z")
    assert result.requests_over_time.total[0][service_id] == 10.0
    assert len(result.requests_over_time.successful) == 1
    assert result.requests_over_time.successful[0][service_id] == 9.0
    assert len(result.requests_over_time.failed) == 1
    assert result.requests_over_time.failed[0][service_id] == 1.0
    assert len(result.tokens_over_time.input) == 1
    assert result.tokens_over_time.input[0][service_id] == 120.0
    assert result.tokens_over_time.output[0][service_id] == 80.0
    assert result.tokens_over_time.total[0][service_id] == 200.0


@pytest.mark.asyncio
async def test_get_api_key_usage_metrics_not_found(
    db_session: AsyncSession,
    test_namespace: str,
    mock_prometheus_client: MagicMock,
) -> None:
    """Raises NotFoundException when the API key does not exist in the namespace."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 2, tzinfo=UTC)

    with pytest.raises(NotFoundException, match="not found"):
        await service.get_api_key_usage_metrics(
            session=db_session,
            namespace=test_namespace,
            api_key_id=uuid4(),
            start=start,
            end=end,
            prometheus_client=mock_prometheus_client,
        )
