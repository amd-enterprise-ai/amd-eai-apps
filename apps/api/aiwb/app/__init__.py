# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT


import asyncio
import os
import sys
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version as get_version

from dotenv import load_dotenv

# Suppress FastAPI deprecation warning for examples in Swagger UI
try:
    from fastapi.exceptions import FastAPIDeprecationWarning

    warnings.filterwarnings("ignore", category=FastAPIDeprecationWarning)
except ImportError:
    pass

from fastapi import APIRouter, Depends, FastAPI
from fastapi_mcp import FastApiMCP
from kubernetes.client.exceptions import ApiException
from loguru import logger
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from api_common import database
from api_common.auth.security import get_user_email
from api_common.database import dispose_db, init_db
from api_common.exceptions import (
    BaseApiException,
    ConflictException,
    ExternalServiceError,
    ForbiddenException,
    InconsistentStateException,
    NotFoundException,
    PreconditionNotMetException,
    UnhealthyException,
    UploadFailedException,
    ValidationException,
)
from api_common.fastapi import (
    base_api_exception_handler,
    conflict_exception_handler,
    exception_group_handler,
    external_service_error_handler,
    forbidden_exception_handler,
    generic_exception_handler,
    inconsistent_state_exception_handler,
    integrity_error_handler,
    not_found_exception_handler,
    precondition_not_met_exception_handler,
    unhealthy_exception_handler,
    upload_failed_exception_handler,
    validation_exception_handler,
    value_error_handler,
)
from api_common.health.router import router as health_router
from api_common.middleware import CamelCaseMiddleware

from .aims.syncer import sync_aim_services
from .apikeys.router import router as apikeys_router
from .apikeys.service import ensure_store_matches_existing_keys
from .artifacts.router import router as artifacts_router
from .charts.router import router as charts_router
from .cluster.router import router as cluster_router
from .common_responses import AUTH_RESPONSES
from .config import LOG_LEVEL
from .datasets.router import router as datasets_router
from .dispatch import poller
from .dispatch.config import load_k8s_config
from .dispatch.kube_client import close_dynamic_client, init_kube_client
from .exceptions import api_exception_handler
from .fine_tuning.router import router as fine_tuning_router
from .inference.router import router as inference_router
from .logs.client import close_loki_client, init_loki_client
from .metrics.client import init_prometheus_client
from .minio import init_minio_client
from .minio.config import MINIO_EXTERNAL_URL
from .openbao.client import OpenBaoClient, init_openbao_client
from .orphans.config import CLEANUP_ENABLED, CLEANUP_INTERVAL_SECONDS
from .orphans.syncer import bind_clients as bind_orphan_clients
from .orphans.syncer import reclaim_orphaned_data
from .overlays.router import router as overlays_router
from .projects.config import DEFAULT_NAMESPACE as DEFAULT_NAMESPACE
from .projects.router import router as projects_router
from .secrets.router import router as secrets_router
from .storages.router import router as storages_router
from .workloads.router import router as workloads_router
from .workloads.syncer import sync_workloads
from .workspaces.router import router as workspaces_router

load_dotenv(override=False)


def ensure_user_logged_in(user_email: str = Depends(get_user_email)) -> str:
    """Ensure user is authenticated by validating their email from token claims."""
    return user_email


async def init_services(app_state: FastAPI) -> None:
    """Initialize all external services and clients."""
    app_state.minio_client = init_minio_client()
    app_state.minio_external_client = init_minio_client(MINIO_EXTERNAL_URL)

    try:
        # Ensure Kubernetes configuration is loaded before creating the client
        await load_k8s_config()
        app_state.kube_client = await init_kube_client()
    except Exception as e:
        logger.error(f"Failed to connect to Kubernetes API: {e}")
        logger.error("Application cannot start without Kubernetes connection")
        os._exit(1)

    try:
        # Initialize Prometheus Client and store in app.state
        app_state.prometheus_client = init_prometheus_client()
    except Exception as e:
        logger.exception("Failed to initialize Prometheus client", e)

    try:
        # Initialize Loki Client and store in app.state
        app_state.loki_client = init_loki_client()
    except Exception as e:
        logger.exception("Failed to initialize Loki client", e)

    # OpenBao/ESO is the sole API-key store. A chart with openBao.enabled=false renders no
    # address or token, so the client stays None and API-key mutations answer with an error.
    # startup_event then refuses to run if keys already exist without the store.
    try:
        app_state.openbao_client = init_openbao_client()
    except Exception as e:
        logger.warning(f"Failed to initialize OpenBao client - API-key operations will fail: {e}")
        app_state.openbao_client = None

    bind_orphan_clients(app_state)


async def start_pollers() -> None:
    """Start all background pollers."""
    poller.register_syncer(sync_aim_services)
    poller.register_syncer(sync_workloads)
    if CLEANUP_ENABLED:
        poller.register_syncer(reclaim_orphaned_data, interval_seconds=CLEANUP_INTERVAL_SECONDS)
    await poller.start_poller()


@asynccontextmanager
async def lifespan(app_lifespan: FastAPI) -> AsyncIterator[None]:
    await startup_event(app_lifespan)
    yield
    await shutdown_event(app_lifespan)


async def startup_event(app_lifespan: FastAPI) -> None:
    # Set logging level
    logger.remove()
    logger.add(sys.stderr, level=LOG_LEVEL)

    try:
        init_db()
    except Exception as e:
        logger.exception("Failed to connect to database", e)
        sys.exit(1)

    await init_services(app_lifespan.state)
    await refuse_disabled_store_with_existing_keys(app_lifespan.state.openbao_client)
    await start_pollers()


async def refuse_disabled_store_with_existing_keys(openbao_client: OpenBaoClient | None) -> None:
    """Exit when the OpenBao store is disabled while API keys exist; see ensure_store_matches_existing_keys."""
    if database.session_maker is None:
        raise RuntimeError("Database is not initialized")
    async with database.session_maker() as session:
        try:
            await ensure_store_matches_existing_keys(session, openbao_client)
        except RuntimeError as e:
            logger.error(str(e))
            logger.error("Application cannot start with API keys that no store can revoke")
            sys.exit(1)
        except SQLAlchemyError as e:
            logger.error(f"Failed to count API keys while checking the OpenBao store: {e}")
            logger.error("Application cannot start without knowing whether API keys exist")
            sys.exit(1)


async def shutdown_event(app_lifespan: FastAPI) -> None:
    # Sync cleanups (instant)
    close_dynamic_client()

    # Async cleanups concurrently with a timeout to avoid hanging on reload
    async def _close_openbao() -> None:
        if hasattr(app_lifespan.state, "openbao_client") and app_lifespan.state.openbao_client:
            await app_lifespan.state.openbao_client.close()

    close_tasks = [
        poller.stop_poller(),
        _close_openbao(),
        close_loki_client(),
        app_lifespan.state.kube_client.close(),
        dispose_db(),
    ]
    results = await asyncio.wait_for(asyncio.gather(*close_tasks, return_exceptions=True), timeout=5)
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Error during shutdown: {result}")


app = FastAPI(
    name="AI Workbench API",
    lifespan=lifespan,
    title="AI Workbench API",
    version=get_version("aiwb-api"),
    swagger_ui_init_oauth={
        "clientId": os.getenv("OPENID_CLIENT_ID", "354a0fa1-35ac-4a6d-9c4d-d661129c2cd0"),
        "scopes": "openid",
        "usePkceWithAuthorizationCodeGrant": True,
    },
)

api_unsecured_router = APIRouter()
api_unsecured_router.include_router(health_router, prefix="/v1")

api_secured_router = APIRouter(dependencies=[Depends(ensure_user_logged_in)], responses=AUTH_RESPONSES)
api_secured_router.include_router(projects_router, prefix="/v1")
api_secured_router.include_router(artifacts_router, prefix="/v1")
api_secured_router.include_router(inference_router, prefix="/v1")
api_secured_router.include_router(charts_router, prefix="/v1")
api_secured_router.include_router(cluster_router, prefix="/v1")
api_secured_router.include_router(overlays_router, prefix="/v1")
api_secured_router.include_router(datasets_router, prefix="/v1")
api_secured_router.include_router(fine_tuning_router, prefix="/v1")
api_secured_router.include_router(workloads_router, prefix="/v1")
api_secured_router.include_router(workspaces_router, prefix="/v1")
api_secured_router.include_router(secrets_router, prefix="/v1")
api_secured_router.include_router(storages_router, prefix="/v1")
api_secured_router.include_router(apikeys_router, prefix="/v1")

app.add_middleware(CamelCaseMiddleware, exclude_path_suffixes=["/mcp/messages/"])

app.include_router(api_unsecured_router)
app.include_router(api_secured_router)

# Initialize MCP support AFTER routers are included
mcp = FastApiMCP(app)
mcp.mount()
# Refresh MCP server to ensure all routes are discovered
mcp.setup_server()


# Register exception handlers
# Note: More specific exception handlers must be registered before generic ones
app.add_exception_handler(ApiException, api_exception_handler)
app.add_exception_handler(ValueError, value_error_handler)
app.add_exception_handler(Exception, generic_exception_handler)
app.add_exception_handler(ExceptionGroup, exception_group_handler)
app.add_exception_handler(BaseApiException, base_api_exception_handler)
app.add_exception_handler(NotFoundException, not_found_exception_handler)
app.add_exception_handler(IntegrityError, integrity_error_handler)
app.add_exception_handler(ConflictException, conflict_exception_handler)
app.add_exception_handler(ValidationException, validation_exception_handler)
app.add_exception_handler(UploadFailedException, upload_failed_exception_handler)
app.add_exception_handler(ForbiddenException, forbidden_exception_handler)
app.add_exception_handler(UnhealthyException, unhealthy_exception_handler)
app.add_exception_handler(PreconditionNotMetException, precondition_not_met_exception_handler)
app.add_exception_handler(ExternalServiceError, external_service_error_handler)
app.add_exception_handler(InconsistentStateException, inconsistent_state_exception_handler)
