# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Common database utilities.
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

engine: AsyncEngine | None = None
session_maker: async_sessionmaker[AsyncSession] | None = None

DATABASE_PROTOCOL = os.environ.get("DATABASE_PROTOCOL", "postgresql+asyncpg")
DATABASE_HOST = os.environ.get("DATABASE_HOST", "localhost")
DATABASE_PORT = int(os.environ.get("DATABASE_PORT", 5432))
DATABASE_NAME = os.environ.get("DATABASE_NAME", "postgres")
DATABASE_USER = os.environ.get("DATABASE_USER", "postgres")
DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD", "postgres")
DATABASE_CONNECTION_STRING = os.environ.get(
    "DATABASE_CONNECTION_STRING",
    f"{DATABASE_PROTOCOL}://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}",
)

# Database connection pool settings
DATABASE_POOL_SIZE = os.environ.get("DATABASE_POOL_SIZE")
DATABASE_MAX_OVERFLOW = os.environ.get("DATABASE_MAX_OVERFLOW")
DATABASE_POOL_TIMEOUT = os.environ.get("DATABASE_POOL_TIMEOUT")
DATABASE_POOL_RECYCLE = os.environ.get("DATABASE_POOL_RECYCLE")


def create_engine(
    database_connection_string: str | None = None,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """
    Create and configure the database engine with connection pooling.

    Identical to AIRM's create_engine.
    """
    global engine, session_maker

    # Use provided connection string or build from env vars
    conn_string = database_connection_string or DATABASE_CONNECTION_STRING

    # Build engine kwargs, only including pool settings if they're configured
    engine_kwargs: dict[str, int | bool] = {
        "echo": False,
        "pool_pre_ping": True,
    }

    if DATABASE_POOL_SIZE is not None:
        engine_kwargs["pool_size"] = int(DATABASE_POOL_SIZE)
    if DATABASE_MAX_OVERFLOW is not None:
        engine_kwargs["max_overflow"] = int(DATABASE_MAX_OVERFLOW)
    if DATABASE_POOL_TIMEOUT is not None:
        engine_kwargs["pool_timeout"] = int(DATABASE_POOL_TIMEOUT)
    if DATABASE_POOL_RECYCLE is not None:
        engine_kwargs["pool_recycle"] = int(DATABASE_POOL_RECYCLE)

    engine = create_async_engine(
        conn_string,
        **engine_kwargs,
    )
    session_maker = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)

    return engine, session_maker


def init_db(database_connection_string: str | None = None) -> None:
    """Initialize database engine."""
    create_engine(database_connection_string)

    if not engine:
        raise RuntimeError("Database engine is not initialized")
    logger.info("Connected to database with url {0}", engine.sync_engine.url)


async def dispose_db() -> None:
    """
    Dispose of the database engine and close all connections.

    Called during application shutdown to properly clean up database resources.
    """
    if engine:
        await engine.dispose()


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession]:
    """
    Async context manager providing database session with automatic transaction handling.

    Identical to AIRM's session_scope.
    """
    if not session_maker:
        raise RuntimeError("Database not initialized")

    session = session_maker()
    try:
        yield session
        await session.commit()
    except Exception:
        # Never let a failing rollback replace the error that caused it — the original
        # exception is what the caller needs to see. Log instead of discarding: a
        # rollback that cannot complete usually means the connection is already broken,
        # which is a pool-health signal worth surfacing.
        #
        # Unlike the test fixture's teardown, this does not invalidate() the connection
        # on a failed rollback: the production engine uses a pooled QueuePool with
        # pool_pre_ping, so a broken connection is detected and discarded on next
        # checkout rather than needing to be force-invalidated here.
        try:
            await session.rollback()
        except Exception:
            logger.exception("Failed to roll back database session")
        raise
    finally:
        try:
            await session.close()
        except Exception:
            logger.exception("Failed to close database session")


async def get_session() -> AsyncGenerator[AsyncSession]:
    """
    FastAPI dependency that provides a database session with transaction management.

    Usage:
        @router.post("/workloads")
        async def create(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with session_scope() as session:
        yield session
