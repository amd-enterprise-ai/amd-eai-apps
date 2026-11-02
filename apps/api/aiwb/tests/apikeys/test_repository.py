# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ConflictException
from app.apikeys.repository import (
    create_api_key,
    delete_api_key,
    get_all_api_keys,
    get_api_key_by_id,
    get_api_keys_for_namespace,
)
from tests import factory


@pytest.mark.asyncio
async def test_create_api_key(db_session: AsyncSession, test_namespace: str, test_user: str) -> None:
    """Test creating an API key."""
    unique_suffix = str(uuid4())[:8]
    name = f"Test API Key {unique_suffix}"

    api_key = await create_api_key(
        session=db_session,
        display_name=name,
        truncated_key="aiwb_api_key_••••••••1234",
        namespace=test_namespace,
        creator=test_user,
    )

    assert api_key.display_name == name
    assert api_key.truncated_key == "aiwb_api_key_••••••••1234"
    assert api_key.namespace == test_namespace
    assert api_key.created_by == test_user


@pytest.mark.asyncio
async def test_create_api_key_duplicate_name_raises_conflict(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Test that creating a duplicate API key name raises ConflictException."""
    unique_suffix = str(uuid4())[:8]
    name = f"Duplicate Key {unique_suffix}"

    # Create first API key
    await create_api_key(
        session=db_session,
        display_name=name,
        truncated_key="aiwb_api_key_••••••••1234",
        namespace=test_namespace,
        creator=test_user,
    )

    # Try to create duplicate
    with pytest.raises(ConflictException) as exc_info:
        await create_api_key(
            session=db_session,
            display_name=name,
            truncated_key="aiwb_api_key_••••••••5678",
            namespace=test_namespace,
            creator=test_user,
        )

    assert "already exists" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_api_keys_for_namespace(db_session: AsyncSession, test_namespace: str, test_user: str) -> None:
    """Test retrieving all API keys for a namespace."""
    unique_suffix = str(uuid4())[:8]

    api_key1 = await factory.create_api_key(
        db_session, display_name=f"Key 1 {unique_suffix}", namespace=test_namespace, created_by=test_user
    )

    api_key2 = await factory.create_api_key(
        db_session, display_name=f"Key 2 {unique_suffix}", namespace=test_namespace, created_by=test_user
    )

    # Create key in different namespace
    await factory.create_api_key(
        db_session, display_name=f"Other NS Key {unique_suffix}", namespace="other-namespace", created_by=test_user
    )

    keys = await get_api_keys_for_namespace(db_session, test_namespace)

    assert len(keys) == 2
    key_ids = {k.id for k in keys}
    assert api_key1.id in key_ids
    assert api_key2.id in key_ids


@pytest.mark.asyncio
async def test_get_api_key_by_id(db_session: AsyncSession, test_namespace: str, test_user: str) -> None:
    """Test retrieving a specific API key by ID."""
    unique_suffix = str(uuid4())[:8]

    created_key = await factory.create_api_key(
        db_session,
        display_name=f"Specific Key {unique_suffix}",
        namespace=test_namespace,
        truncated_key="aiwb_api_key_••••••••9999",
        created_by=test_user,
    )

    retrieved_key = await get_api_key_by_id(db_session, created_key.id, test_namespace)

    assert retrieved_key is not None
    assert retrieved_key.id == created_key.id
    assert retrieved_key.display_name == f"Specific Key {unique_suffix}"


@pytest.mark.asyncio
async def test_get_api_key_by_id_wrong_namespace_returns_none(db_session: AsyncSession, test_user: str) -> None:
    """Test that getting an API key from wrong namespace returns None."""
    unique_suffix = str(uuid4())[:8]

    created_key = await factory.create_api_key(
        db_session,
        display_name=f"Namespace 1 Key {unique_suffix}",
        namespace="namespace-1",
        truncated_key="aiwb_api_key_••••••••8888",
        created_by=test_user,
    )

    retrieved_key = await get_api_key_by_id(db_session, created_key.id, "namespace-2")

    assert retrieved_key is None


@pytest.mark.asyncio
async def test_delete_api_key(db_session: AsyncSession, test_namespace: str, test_user: str) -> None:
    """Test deleting an API key."""
    unique_suffix = str(uuid4())[:8]

    created_key = await factory.create_api_key(
        db_session,
        display_name=f"Key to Delete {unique_suffix}",
        namespace=test_namespace,
        truncated_key="aiwb_api_key_••••••••6666",
        created_by=test_user,
    )

    key_id = created_key.id

    await delete_api_key(db_session, created_key)

    # Verify it's deleted
    deleted_key = await get_api_key_by_id(db_session, key_id, test_namespace)
    assert deleted_key is None


@pytest.mark.asyncio
async def test_get_all_api_keys_spans_namespaces(db_session: AsyncSession, test_user: str) -> None:
    """Auditing keys against surviving namespaces needs the ones a scoped query cannot reach."""
    unique_suffix = str(uuid4())[:8]
    namespace_a = f"ns-a-{unique_suffix}"
    namespace_b = f"ns-b-{unique_suffix}"

    await factory.create_api_key(
        db_session,
        display_name=f"Key A {unique_suffix}",
        namespace=namespace_a,
        truncated_key="aiwb_api_key_••••••••1111",
        created_by=test_user,
    )
    await factory.create_api_key(
        db_session,
        display_name=f"Key B {unique_suffix}",
        namespace=namespace_b,
        truncated_key="aiwb_api_key_••••••••2222",
        created_by=test_user,
    )

    all_keys = await get_all_api_keys(db_session)

    # Equality, not containment: the fixture rolls back per test and nothing else seeds the table,
    # so a looser assertion would hide both duplicate rows and leakage across tests. Comparing the
    # sequence also pins the namespace ordering the query promises, which callers group on.
    assert [key.namespace for key in all_keys] == [namespace_a, namespace_b]
