# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Dependency override utilities for AIWB testing.

Usage:
    from tests.dependency_overrides import override_dependencies, BASE_OVERRIDES

    @override_dependencies(BASE_OVERRIDES)
    def test_endpoint():
        pass
"""

import asyncio
from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import wraps
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from prometheus_api_client import PrometheusConnect
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.auth.security import get_user_email
from api_common.database import get_session
from app import app  # type: ignore[attr-defined]
from app.dispatch.kube_client import KubernetesClient, get_kube_client
from app.metrics.client import get_prometheus_client
from app.minio import get_minio_client
from app.openbao import get_openbao_client
from app.openbao.client import OpenBaoClient
from app.projects.security import ensure_access_to_project, ensure_access_to_workbench_namespace


@contextmanager
def runtime_dependency_overrides(overrides: dict[Callable[..., Any], Callable[..., Any]]) -> Generator[None]:
    """Context manager for temporarily applying dependency overrides."""
    old_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.update(overrides)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old_overrides)


def override_dependencies(overrides: dict[Callable[..., Any], Callable[..., Any]]) -> Callable:
    """Decorator to temporarily override FastAPI dependencies for a test function."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with runtime_dependency_overrides(overrides):
                    return await func(*args, **kwargs)

            return async_wrapper
        else:

            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with runtime_dependency_overrides(overrides):
                    return func(*args, **kwargs)

            return wrapper

    return decorator


# =============================================================================
# Override Patterns
# =============================================================================

# Base: user email, namespace, kube client
BASE_OVERRIDES: dict[Callable[..., Any], Callable[..., Any]] = {
    get_user_email: lambda: "test@example.com",
    ensure_access_to_workbench_namespace: lambda: "test-namespace",
    ensure_access_to_project: lambda: "test-namespace",
    get_kube_client: lambda: AsyncMock(spec=KubernetesClient),
}

# Base + database session
SESSION_OVERRIDES: dict[Callable[..., Any], Callable[..., Any]] = {
    **BASE_OVERRIDES,
    get_session: lambda: AsyncMock(spec=AsyncSession),
}

# Session + MinIO client (for dataset and model operations)
MINIO_OVERRIDES: dict[Callable[..., Any], Callable[..., Any]] = {
    **SESSION_OVERRIDES,
    get_minio_client: lambda: None,
}

# Session + OpenBao store client (the API-key path; cluster-auth is not involved).
APIKEY_OVERRIDES: dict[Callable[..., Any], Callable[..., Any]] = {
    **SESSION_OVERRIDES,
    get_openbao_client: lambda: AsyncMock(spec=OpenBaoClient),
}

# Session + Prometheus client (for metrics tests)
PROMETHEUS_OVERRIDES: dict[Callable[..., Any], Callable[..., Any]] = {
    **SESSION_OVERRIDES,
    get_prometheus_client: lambda: MagicMock(spec=PrometheusConnect),
}
