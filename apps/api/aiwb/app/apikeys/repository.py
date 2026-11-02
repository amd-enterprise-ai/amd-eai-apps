# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ConflictException

from .models import ApiKey


async def get_api_keys_for_namespace(
    session: AsyncSession,
    namespace: str,
) -> list[ApiKey]:
    """
    Get all API keys for a specific namespace.

    Args:
        session: Database session
        namespace: The namespace name

    Returns:
        List of API keys
    """
    result = await session.execute(
        select(ApiKey).where(ApiKey.namespace == namespace).order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


async def count_api_keys(session: AsyncSession) -> int:
    """Count every API key across all namespaces."""
    return (await session.execute(select(func.count()).select_from(ApiKey))).scalar_one()


async def get_all_api_keys(session: AsyncSession) -> list[ApiKey]:
    """
    Get every API key across all namespaces.

    Unscoped on purpose: callers auditing keys against the namespaces that still exist have to see
    the ones whose namespace does not, which a per-namespace query cannot reach.
    """
    result = await session.execute(select(ApiKey).order_by(ApiKey.namespace, ApiKey.created_at))
    return list(result.scalars().all())


async def get_api_key_by_id(
    session: AsyncSession,
    api_key_id: UUID,
    namespace: str,
) -> ApiKey | None:
    """
    Get an API key by its ID within a namespace.

    Args:
        session: Database session
        api_key_id: The ID of the API key
        namespace: The namespace name

    Returns:
        The API key if found, None otherwise
    """
    result = await session.execute(select(ApiKey).where(ApiKey.id == api_key_id, ApiKey.namespace == namespace))
    return result.scalar_one_or_none()


async def create_api_key(
    session: AsyncSession,
    display_name: str,
    truncated_key: str,
    namespace: str,
    creator: str,
    expires_at: datetime | None = None,
) -> ApiKey:
    """
    Create a new API key in the database.

    Args:
        session: Database session
        display_name: User-friendly display name for the API key
        truncated_key: Truncated key for display
        namespace: The namespace name
        creator: Email of the user creating the key
        expires_at: Expiry timestamp (None = never); OpenBao enforces the actual drop.

    Returns:
        The created API key

    Raises:
        ConflictException: If an API key with the same display name already exists in the namespace
    """
    new_api_key = ApiKey(
        display_name=display_name,
        truncated_key=truncated_key,
        namespace=namespace,
        expires_at=expires_at,
        created_by=creator,
        updated_by=creator,
    )

    session.add(new_api_key)
    try:
        await session.flush()
        return new_api_key
    except IntegrityError as e:
        error_message = str(e)
        if "uq_api_keys_display_name_namespace" in error_message or "display_name" in error_message.lower():
            raise ConflictException(
                f"An API key with the display name '{display_name}' already exists in the namespace '{namespace}'"
            )
        raise e


async def delete_api_key(session: AsyncSession, api_key: ApiKey) -> None:
    """
    Delete an API key from the database.

    Args:
        session: Database session
        api_key: The API key to delete
    """
    await session.delete(api_key)
    await session.flush()
