# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Guards Prometheus instrumentation against FastAPI's lazy router inclusion.

FastAPI 0.137 stopped flattening child routes on ``include_router`` and instead
appends a lazy wrapper object that exposes no ``path``. Instrumentation that walks
``app.routes`` naively either raises on every request or silently labels nested
routes as untemplated. Every ``/v1/*`` endpoint of this API is mounted through two
levels of ``include_router``, and the instrumentation middleware runs on every
request, so a regression here takes down the whole service rather than just its
metrics.

This is a forward guard. On the fastapi currently pinned here the lazy wrapper is
never constructed, so the test exercises only ordinary nested routing and cannot
fail. It arms itself the moment fastapi crosses 0.137: against that version it
fails on any instrumentator older than 8.0.1 with ``AttributeError:
'_IncludedRouter' object has no attribute 'path'``. Keep it after that bump lands
rather than treating it as redundant.
"""

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry
from prometheus_fastapi_instrumentator import Instrumentator


@pytest.fixture
def nested_route_app() -> FastAPI:
    """App whose only endpoint sits behind two levels of ``include_router``, mirroring ``app/__init__.py``."""
    leaf_router = APIRouter()

    @leaf_router.get("/widgets/{widget_id}")
    async def read_widget(widget_id: str) -> dict[str, str]:
        return {"widgetId": widget_id}

    versioned_router = APIRouter()
    versioned_router.include_router(leaf_router, prefix="/v1")

    app = FastAPI()
    app.include_router(versioned_router)
    return app


def test_instrumentation_labels_nested_route_with_its_path_template(nested_route_app: FastAPI) -> None:
    registry = CollectorRegistry()
    Instrumentator(registry=registry).instrument(nested_route_app)

    with TestClient(nested_route_app) as client:
        response = client.get("/v1/widgets/abc123")

    assert response.status_code == 200

    observed_handlers = {
        sample.labels["handler"]
        for metric in registry.collect()
        for sample in metric.samples
        if "handler" in sample.labels
    }
    # A bare "/v1/widgets/abc123" would mean the path parameter leaked into the
    # label; "none" would mean the route was written off as untemplated.
    assert observed_handlers == {"/v1/widgets/{widget_id}"}
