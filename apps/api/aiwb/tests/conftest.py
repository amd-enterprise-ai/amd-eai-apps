# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import contextlib
import json
import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import docker
import httpx
import pytest
import pytest_asyncio
from fastapi import Request
from filelock import FileLock
from loguru import logger
from prometheus_api_client import PrometheusConnect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from tenacity import retry, stop_after_attempt, wait_exponential
from testcontainers.postgres import PostgresContainer

import api_common.database as db_module
from api_common.models import BaseEntity
from app.minio import MinioClient

# Test database configuration
TEST_DB_USER = "postgres"
TEST_DB_PASSWORD = "postgres"
TEST_DB_NAME_PREFIX = "aiwb_test"


def _get_session_tmp_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Get the session-scoped temporary path.

    xdist workers get per-worker basetemp (e.g. /tmp/pytest-of-user/pytest-123/gw0),
    so .parent gives the shared session dir. Without xdist, basetemp is already the
    session dir. Using the session dir (not its parent) prevents cleanup from
    accidentally killing containers belonging to other concurrent pytest sessions.
    """
    return (
        tmp_path_factory.getbasetemp().parent
        if os.environ.get("PYTEST_XDIST_WORKER")
        else tmp_path_factory.getbasetemp()
    )


def cleanup_containers(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Clean up testcontainers to prevent resource leaks."""
    docker_client = docker.from_env()
    base_path = _get_session_tmp_path(tmp_path_factory)

    for container_file in base_path.rglob("*_container.json"):
        try:
            container_info = json.loads(container_file.read_text())
            containers = docker_client.containers.list(filters={"id": container_info["container_id"]})

            if containers:
                for container in containers:
                    container.stop()
                    container.wait()
                    container.remove(force=True, v=True)

            container_file.unlink(missing_ok=True)
        except Exception:
            # Cleanup failures shouldn't break tests
            pass


def pytest_sessionstart(session: pytest.Session) -> None:
    """Clean up containers before session starts."""
    if not hasattr(session.config, "workerinput"):
        cleanup_containers(session.config._tmp_path_factory)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Clean up containers after session finishes."""
    if not hasattr(session.config, "workerinput"):
        cleanup_containers(session.config._tmp_path_factory)


@pytest.fixture(autouse=True)
def global_init_dependencies(monkeypatch):
    """Patch app startup dependencies to prevent external service connections during tests."""
    # Set dummy env vars to prevent startup errors
    monkeypatch.setenv("PROMETHEUS_URL", "http://dummy-prometheus-server.com")

    # Create an AsyncMock for kube_client that can be awaited during shutdown
    mock_kube_client = AsyncMock()

    with (
        patch("app.init_db", autospec=True),
        patch("app.refuse_disabled_store_with_existing_keys", autospec=True),
        patch("app.load_k8s_config", autospec=True),
        patch("app.init_kube_client", return_value=mock_kube_client),
        patch("app.start_pollers", autospec=True),
        patch("app.init_prometheus_client") as mock_init_prometheus,
        patch("app.init_loki_client") as mock_init_loki,
    ):
        # Ensure the mock returns a MagicMock that can be used as if it's a PrometheusConnect client
        mock_init_prometheus.return_value = MagicMock(spec=PrometheusConnect)
        # Ensure the mock returns a properly configured Loki client
        mock_init_loki.return_value = MagicMock(spec=httpx.AsyncClient)
        yield


@retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=2.5), stop=stop_after_attempt(5), reraise=True)
async def _connect_to_postgres(host: str, port: int) -> asyncpg.Connection:
    """Connect to postgres default database with retry logic."""
    return await asyncpg.connect(f"postgresql://{TEST_DB_USER}:{TEST_DB_PASSWORD}@{host}:{port}/postgres", timeout=10)


@retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=2.5), stop=stop_after_attempt(5), reraise=True)
async def _create_schema(database_url: str) -> None:
    """Create database schema with retry logic. Called once per worker."""
    engine = create_async_engine(database_url, echo=False, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(BaseEntity.metadata.create_all)
    finally:
        await engine.dispose()


def _coordinate_container_across_workers(
    tmp_path_factory: Any,
    worker_id: str,
    container_name: str,
    setup_fn: Any,
) -> tuple[Any, dict[str, Any]]:
    """Coordinate container startup across pytest-xdist workers."""
    fn = tmp_path_factory.getbasetemp().parent / f"{container_name}.json"

    if worker_id == "master":
        # Not running with xdist, start container normally
        container, container_info = setup_fn()
        fn.write_text(json.dumps(container_info))
        return container, container_info
    else:
        # Running with xdist - coordinate via lockfile
        lock_fn = tmp_path_factory.getbasetemp().parent / f"{container_name}.lock"
        with FileLock(str(lock_fn)):
            if not fn.exists():
                # First worker to acquire lock starts the container
                container, container_info = setup_fn()
                fn.write_text(json.dumps(container_info))
                return container, container_info
            else:
                # Subsequent workers read container info
                container_info = json.loads(fn.read_text())
                return None, container_info


@pytest.fixture(scope="session")
def postgres_container(tmp_path_factory: Any, worker_id: str) -> Generator[dict[str, Any]]:
    """Start PostgreSQL container (shared across all workers)."""

    def setup_postgres():
        container = PostgresContainer(
            image="postgres:17",
            username=TEST_DB_USER,
            password=TEST_DB_PASSWORD,
        )
        container.start()
        container_info = {
            "host": container.get_container_host_ip(),
            "port": container.get_exposed_port(5432),
            "container_id": container.get_wrapped_container().id,
        }
        return container, container_info

    container, info = _coordinate_container_across_workers(
        tmp_path_factory, worker_id, "postgres_container", setup_postgres
    )

    yield info

    # Container shutdown is deferred to master's pytest_sessionfinish hook
    # (cleanup_containers). Stopping here would race sibling xdist workers
    # that may still hold a reference to the shared container.


@pytest.fixture(scope="session")
def database_url(postgres_container: dict[str, Any], worker_id: str) -> Generator[str]:
    """Get database URL for worker-specific database."""

    host = postgres_container["host"]
    port = postgres_container["port"]

    # Each worker gets its own database
    db_name = f"{TEST_DB_NAME_PREFIX}_{worker_id}" if worker_id != "master" else TEST_DB_NAME_PREFIX

    # Create database
    async def create_db():
        conn = None
        try:
            conn = await _connect_to_postgres(host, port)
            await conn.execute(f"DROP DATABASE IF EXISTS {db_name}")
            await conn.execute(f"CREATE DATABASE {db_name}")
        except (asyncpg.exceptions.ConnectionDoesNotExistError, OSError, ConnectionRefusedError) as e:
            raise RuntimeError(f"Failed to connect to PostgreSQL container during database setup: {e}")
        finally:
            if conn is not None:
                try:
                    if not conn.is_closed():
                        await conn.close()
                except (asyncpg.exceptions.ConnectionDoesNotExistError, AttributeError):
                    pass

    asyncio.run(create_db())

    url = f"postgresql+asyncpg://{TEST_DB_USER}:{TEST_DB_PASSWORD}@{host}:{port}/{db_name}"

    # Create schema once per worker, not per test
    asyncio.run(_create_schema(url))

    yield url

    # Cleanup database
    async def cleanup_db():
        conn = None
        try:
            conn = await _connect_to_postgres(host, port)
        except Exception:
            # Any connection failure during cleanup should be silent - container may be stopped
            # Database cleanup will be handled by container cleanup hooks
            return

        try:
            # Terminate other connections to this database
            await conn.execute(
                f"""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = '{db_name}'
                AND pid <> pg_backend_pid()
                """
            )
            # Drop the database
            await conn.execute(f"DROP DATABASE IF EXISTS {db_name}")
        except (asyncpg.exceptions.ConnectionDoesNotExistError, asyncpg.exceptions.InvalidCatalogNameError):
            # Connection was terminated during cleanup or database already dropped
            # This can happen in parallel test execution
            pass
        except Exception:
            # Suppress all other cleanup errors to avoid masking test failures
            pass
        finally:
            if conn is not None:
                try:
                    if not conn.is_closed():
                        await conn.close()
                except Exception:
                    # Suppress all connection close errors during cleanup
                    pass

    asyncio.run(cleanup_db())


@pytest_asyncio.fixture
async def engine_and_session_maker(database_url: str) -> AsyncGenerator[tuple[Any, Any]]:
    """
    Create database engine and session maker for tests.

    Uses NullPool to avoid connection pool management overhead and prevent
    ConnectionDoesNotExistError under parallel xdist execution. Each operation
    gets a fresh connection, eliminating pool exhaustion and stale connection issues.

    Also sets api_common.database globals so that code paths using get_session()
    (e.g. overlay router tests via FastAPI TestClient) work correctly.
    """
    engine = create_async_engine(database_url, echo=False, poolclass=NullPool)
    session_local = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Set globals so get_session() works for router tests using TestClient.
    # Save and restore the previous values: this fixture is function-scoped and each
    # test runs in its own event loop (asyncio_default_fixture_loop_scope=function).
    # Disposing the engine below does not retire it — dispose() drops the current pool
    # and a fresh one is built on next use — so leaving it installed in the module
    # globals keeps it reachable after this test's loop is gone. The hazard is event
    # loop affinity: a later get_session() would open asyncpg connections through an
    # engine whose asyncio state belongs to a finished loop, binding them to whichever
    # loop happens to be running then. Restoring confines each engine to the loop it
    # was created on.
    previous_engine = db_module.engine
    previous_session_maker = db_module.session_maker
    db_module.engine = engine
    db_module.session_maker = session_local

    try:
        yield engine, session_local
    finally:
        db_module.engine = previous_engine
        db_module.session_maker = previous_session_maker
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine_and_session_maker: tuple[Any, Any]) -> AsyncGenerator[AsyncSession]:
    """
    Provide a transactional database session for each test.

    Each test runs inside a single transaction that is rolled back at teardown, so
    changes never leak between tests and the schema is never recreated per test.

    Architecture:
    1. Creates a new session from the session factory
    2. Begins one transaction
    3. Yields the session to the test
    4. Rolls back the transaction and closes the session afterwards (discards all changes)

    This pattern ensures:
    - Test isolation: Changes don't leak between tests
    - Performance: Uses a transaction instead of recreating schema
    - Simplicity: Tests just use db_session without cleanup code

    Isolation is not a structural guarantee: if rollback fails (see the defensive
    teardown below), the connection is invalidated rather than rolled back, and
    whatever the test wrote up to that point is not undone.
    """
    engine, session_local = engine_and_session_maker

    session = session_local()
    # Open a single transaction explicitly and roll it back exactly once at teardown.
    #
    # The previous pattern nested `async with session.begin()` (a real transaction)
    # around an explicit `begin_nested()` (a SAVEPOINT) and then called
    # `await session.rollback()` inside the block. That rollback unwound the *whole*
    # transaction stack, after which the `session.begin()` and `session_local()`
    # context managers each ran their own teardown (commit-attempt / close) against a
    # session whose connection was already being torn down. With NullPool the close
    # releases the underlying asyncpg connection immediately, so whenever a teardown
    # statement raced an in-flight close the run failed intermittently with
    # asyncpg's "connection was closed in the middle of operation".
    #
    # A single transaction with one rollback leaves only one teardown path, so no two
    # teardowns can race each other. The session is always closed in `finally`.
    try:
        await session.begin()
        yield session
    finally:
        # Roll back everything the test did, guaranteeing isolation, and never leave an
        # open transaction for the close to fight with.
        #
        # A test may hand the session back while its asyncpg connection is still busy.
        # Code under test that fans out with `asyncio.gather` (without
        # `return_exceptions=True`) re-raises the first sibling failure as soon as it
        # happens, but the other coroutines are *not* cancelled — they keep running. If
        # one of them is a DB query on this session, the caller unwinds and the test
        # asserts on the exception while that query is still in flight, leaving the
        # connection with an operation in progress. `rollback()` on such a connection
        # raises asyncpg's "another operation is in progress".
        #
        # So tear down defensively. If rollback fails, invalidate the connection: under
        # NullPool connections are never reused, so invalidation discards the poisoned
        # one rather than crashing teardown, and no state can leak into another test.
        # invalidate() and close() are suppressed for the same reason — they run on a
        # connection already known to be unusable, and a teardown failure there would
        # mask the test's real result. Healthy tests take the normal path and are still
        # genuinely rolled back, so isolation is unchanged.
        #
        # This does not remove the race; it makes the teardown survive it.
        try:
            await session.rollback()
        except Exception:
            logger.warning("db_session rollback failed, invalidating connection instead")
            with contextlib.suppress(Exception):
                await session.invalidate()
        finally:
            with contextlib.suppress(Exception):
                await session.close()


@pytest.fixture
def test_namespace() -> str:
    """Provide a test namespace name."""
    return "test-namespace"


@pytest.fixture
def test_user() -> str:
    """Provide a test user email."""
    return "test@example.com"


@pytest.fixture
def mock_openbao_client() -> AsyncMock:  # type: ignore[misc]
    """
    Mock OpenBaoClient for testing API key service functions.

    Provides AsyncMock instance with common response patterns for OpenBao operations.
    Tests should configure return values or side_effect for specific method calls as needed.
    """
    mock = AsyncMock()
    mock.put_token.return_value = None
    mock.get_token.return_value = "amd_aim_api_key_hvs.abc123"
    mock.delete_token.return_value = None
    return mock


@pytest.fixture
def mock_kube_client():  # type: ignore[misc]
    """
    Mock KubernetesClient for testing secrets service functions.

    Provides AsyncMock instance with common response patterns for K8s operations.
    Tests should configure return values for specific method calls as needed.
    """

    mock = AsyncMock()

    # Mock core_v1 API for native K8s secrets
    mock.core_v1 = MagicMock()
    mock.core_v1.create_namespaced_secret = MagicMock()
    mock.core_v1.replace_namespaced_secret = MagicMock()
    mock.core_v1.delete_namespaced_secret = MagicMock()

    # Mock custom_objects API for CRDs (ExternalSecrets)
    mock.create_crd.return_value = None
    mock.delete_crd.return_value = None

    return mock


@pytest.fixture
def mock_kube_api_client():  # type: ignore[misc]
    """
    Mock KubeAPIClient for testing gateway and syncer functions.

    Provides Mock instance with common response patterns for K8s API operations.
    Tests should configure return values for specific method calls as needed.
    """

    mock = MagicMock()

    # Mock core_v1 API
    mock.core_v1 = MagicMock()
    mock.core_v1.list_namespaced_secret.return_value = MagicMock(items=[])

    # Mock custom_objects API
    mock.custom_objects = MagicMock()
    mock.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    # Mock namespace discovery
    mock.get_namespaces_with_label.return_value = []

    return mock


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create a mock database session for unit tests.

    This is a lightweight mock for testing service functions without a real database.
    For integration tests that need a real database, use the 'db_session' fixture instead.
    """
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_prometheus_client() -> MagicMock:
    """Create a mock Prometheus client for unit tests.

    Provides a mock PrometheusConnect instance for testing metrics-related functions.
    Tests should configure return values for specific query methods as needed.
    """
    mock = MagicMock()
    mock.custom_query = MagicMock(return_value=[])
    mock.custom_query_range = MagicMock(return_value=[])
    return mock


@pytest.fixture
def minio_environment(monkeypatch):
    """Set up necessary environment variables for MinIO testing."""
    monkeypatch.setattr("app.minio.config.MINIO_ACCESS_KEY", "test-access-key")
    monkeypatch.setattr("app.minio.config.MINIO_URL", "http://localhost:9000")
    monkeypatch.setattr("app.minio.config.MINIO_SECRET_KEY", "test-secret-key")
    monkeypatch.setattr("app.minio.config.MINIO_BUCKET", "test-bucket")
    monkeypatch.setattr("app.datasets.config.DATASETS_PATH", "test-bucket/datasets")
    return monkeypatch


@pytest.fixture
def mock_minio_client():
    """Create a mock MinioClient for testing."""
    client = MagicMock(spec=MinioClient)
    client.upload_object = MagicMock()
    client.download_object = MagicMock(return_value=b'{"text": "test"}\n{"text": "test2"}')
    client.get_object_sizes = MagicMock(return_value={})
    _stat = MagicMock(size=len(b'{"text": "test"}\n{"text": "test2"}'))
    client.stat_object = MagicMock(return_value=_stat)
    inner = MagicMock()
    inner.stat_object = MagicMock(return_value=_stat)
    client.client = inner
    return client


@pytest.fixture
def mock_request() -> MagicMock:
    """Create a mock FastAPI Request for testing service functions that accept requests."""
    return MagicMock(spec=Request)
