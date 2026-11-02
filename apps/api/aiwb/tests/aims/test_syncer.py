# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for AIMs syncer."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.aims.crds import ResolvedRef
from app.aims.enums import AIMServiceStatus
from app.aims.syncer import sync_aim_services
from app.workloads.constants import WORKLOAD_ID_LABEL
from tests.factory import make_aim_cluster_model, make_aim_service_k8s


@pytest.fixture
def kube_client() -> MagicMock:
    """Mock K8s client."""
    return MagicMock()


def _mock_namespace(name: str) -> MagicMock:
    """Create mock namespace."""
    ns = MagicMock()
    ns.name = name
    return ns


@pytest.mark.asyncio
async def test_sync_creates_new_db_records(kube_client: MagicMock) -> None:
    """Test sync creates DB records for K8s services not in DB."""
    wid = uuid4()
    k8s_svc = make_aim_service_k8s(workload_id=wid, namespace="test-ns", status=AIMServiceStatus.RUNNING)
    aim = make_aim_cluster_model()

    mock_session = AsyncMock()

    with (
        patch("app.aims.syncer.get_namespaces", return_value=[_mock_namespace("test-ns")]),
        patch("app.aims.syncer.list_aim_services", return_value=[k8s_svc]),
        patch("app.aims.syncer.list_aim_services_history", return_value=[]),
        patch("app.aims.syncer.get_aim_by_name", return_value=aim),
        patch("app.aims.syncer.create_aim_service") as mock_create,
    ):
        await sync_aim_services(mock_session, kube_client)

    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["id"] == wid
    assert call_kwargs["namespace"] == "test-ns"


@pytest.mark.asyncio
async def test_sync_uses_spec_model_name_when_resolved_model_name_is_canonical_id(
    kube_client: MagicMock,
) -> None:
    """Sync must look up the AIM by spec.model.name, not status.resolvedModel.name.

    Under the v1alpha2 profile reconciler, status.resolvedModel.name holds the
    canonical model id (e.g. "amd/Llama-3.1-8B-Instruct-FP8-KV") which contains
    a slash and is not a valid K8s resource name. Using it for get_aim_by_name
    causes 403s. spec.model.name remains the AIMClusterModel resource name.
    """
    wid = uuid4()
    k8s_svc = make_aim_service_k8s(
        workload_id=wid,
        namespace="test-ns",
        model_ref="llama3-8b",
        status=AIMServiceStatus.RUNNING,
    )
    # Simulate v1alpha2 profile reconciler: status holds the canonical id
    # (with a slash), which is NOT a valid K8s resource name.
    k8s_svc.status.resolved_model = ResolvedRef(name="amd/Llama-3.1-8B-Instruct-FP8-KV")

    aim = make_aim_cluster_model(name="llama3-8b")

    mock_session = AsyncMock()

    with (
        patch("app.aims.syncer.get_namespaces", return_value=[_mock_namespace("test-ns")]),
        patch("app.aims.syncer.list_aim_services", return_value=[k8s_svc]),
        patch("app.aims.syncer.list_aim_services_history", return_value=[]),
        patch("app.aims.syncer.get_aim_by_name", return_value=aim) as mock_get_aim,
        patch("app.aims.syncer.create_aim_service") as mock_create,
    ):
        await sync_aim_services(mock_session, kube_client)

    # The lookup must use the spec name, not the canonical id from status.
    mock_get_aim.assert_called_once_with(kube_client, "llama3-8b")
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_sync_updates_status(kube_client: MagicMock) -> None:
    """Test sync updates status of existing DB records."""
    wid = uuid4()
    db_svc = MagicMock()
    db_svc.id = wid
    db_svc.namespace = "test-ns"
    db_svc.status = AIMServiceStatus.PENDING.value

    k8s_svc = make_aim_service_k8s(workload_id=wid, status=AIMServiceStatus.RUNNING)

    mock_session = AsyncMock()

    with (
        patch("app.aims.syncer.get_namespaces", return_value=[_mock_namespace("test-ns")]),
        patch("app.aims.syncer.list_aim_services", return_value=[k8s_svc]),
        patch("app.aims.syncer.list_aim_services_history", return_value=[db_svc]),
        patch("app.aims.syncer.update_aim_service_status") as mock_update,
    ):
        await sync_aim_services(mock_session, kube_client)

    mock_update.assert_called_once()
    call_args = mock_update.call_args
    assert call_args[0][1] == db_svc
    assert call_args[0][2] == AIMServiceStatus.RUNNING


@pytest.mark.asyncio
async def test_sync_marks_deleted(kube_client: MagicMock) -> None:
    """Test sync marks services as deleted when not in K8s."""
    wid = uuid4()
    db_svc = MagicMock()
    db_svc.id = wid
    db_svc.namespace = "test-ns"
    db_svc.status = AIMServiceStatus.RUNNING.value

    mock_session = AsyncMock()

    with (
        patch("app.aims.syncer.get_namespaces", return_value=[_mock_namespace("test-ns")]),
        patch("app.aims.syncer.list_aim_services", return_value=[]),
        patch("app.aims.syncer.list_aim_services_history", return_value=[db_svc]),
        patch("app.aims.syncer.update_aim_service_status") as mock_update,
    ):
        await sync_aim_services(mock_session, kube_client)

    mock_update.assert_called_once()
    call_args = mock_update.call_args
    assert call_args[0][2] == AIMServiceStatus.DELETED


@pytest.mark.asyncio
async def test_sync_skips_already_deleted(kube_client: MagicMock) -> None:
    """Test sync doesn't update already deleted services."""
    db_svc = MagicMock()
    db_svc.id = uuid4()
    db_svc.namespace = "test-ns"
    db_svc.status = AIMServiceStatus.DELETED.value  # Already deleted

    mock_session = AsyncMock()

    with (
        patch("app.aims.syncer.get_namespaces", return_value=[_mock_namespace("test-ns")]),
        patch("app.aims.syncer.list_aim_services", return_value=[]),
        patch("app.aims.syncer.list_aim_services_history", return_value=[db_svc]),
        patch("app.aims.syncer.update_aim_service_status") as mock_update,
    ):
        await sync_aim_services(mock_session, kube_client)

    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_sync_handles_empty_namespaces(kube_client: MagicMock) -> None:
    """Test sync handles no accessible namespaces."""
    mock_session = AsyncMock()

    with (
        patch("app.aims.syncer.get_namespaces", return_value=[]),
        patch("app.aims.syncer.list_aim_services_history", return_value=[]),
    ):
        await sync_aim_services(mock_session, kube_client)

    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_sync_skips_services_without_model_ref(kube_client: MagicMock) -> None:
    """Test sync skips K8s services without model ref."""
    k8s_svc = make_aim_service_k8s()
    k8s_svc.spec.model.name = None  # No ref

    mock_session = AsyncMock()

    with (
        patch("app.aims.syncer.get_namespaces", return_value=[_mock_namespace("test-ns")]),
        patch("app.aims.syncer.list_aim_services", return_value=[k8s_svc]),
        patch("app.aims.syncer.list_aim_services_history", return_value=[]),
        patch("app.aims.syncer.create_aim_service") as mock_create,
    ):
        await sync_aim_services(mock_session, kube_client)

    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_sync_skips_invalid_uuid(kube_client: MagicMock) -> None:
    """Test sync skips services with invalid UUID labels."""
    k8s_svc = make_aim_service_k8s()
    k8s_svc.metadata.labels[WORKLOAD_ID_LABEL] = "invalid-uuid"

    mock_session = AsyncMock()

    with (
        patch("app.aims.syncer.get_namespaces", return_value=[_mock_namespace("test-ns")]),
        patch("app.aims.syncer.list_aim_services", return_value=[k8s_svc]),
        patch("app.aims.syncer.list_aim_services_history", return_value=[]),
        patch("app.aims.syncer.create_aim_service") as mock_create,
    ):
        await sync_aim_services(mock_session, kube_client)

    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_sync_skips_services_without_namespace(kube_client: MagicMock) -> None:
    """Test sync skips K8s services without namespace."""
    k8s_svc = make_aim_service_k8s()
    k8s_svc.metadata.namespace = None  # type: ignore

    mock_session = AsyncMock()

    with (
        patch("app.aims.syncer.get_namespaces", return_value=[_mock_namespace("test-ns")]),
        patch("app.aims.syncer.list_aim_services", return_value=[k8s_svc]),
        patch("app.aims.syncer.list_aim_services_history", return_value=[]),
        patch("app.aims.syncer.create_aim_service") as mock_create,
    ):
        await sync_aim_services(mock_session, kube_client)

    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_sync_skips_when_aim_not_found(kube_client: MagicMock) -> None:
    """Test sync skips when AIM CRD not found."""
    k8s_svc = make_aim_service_k8s()

    mock_session = AsyncMock()

    with (
        patch("app.aims.syncer.get_namespaces", return_value=[_mock_namespace("test-ns")]),
        patch("app.aims.syncer.list_aim_services", return_value=[k8s_svc]),
        patch("app.aims.syncer.list_aim_services_history", return_value=[]),
        patch("app.aims.syncer.get_aim_by_name", return_value=None),
        patch("app.aims.syncer.create_aim_service") as mock_create,
    ):
        await sync_aim_services(mock_session, kube_client)

    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_sync_handles_create_exception(kube_client: MagicMock) -> None:
    """Test sync handles exception during DB create."""
    k8s_svc = make_aim_service_k8s()
    aim = make_aim_cluster_model()

    mock_session = AsyncMock()

    with (
        patch("app.aims.syncer.get_namespaces", return_value=[_mock_namespace("test-ns")]),
        patch("app.aims.syncer.list_aim_services", return_value=[k8s_svc]),
        patch("app.aims.syncer.list_aim_services_history", return_value=[]),
        patch("app.aims.syncer.get_aim_by_name", return_value=aim),
        patch("app.aims.syncer.create_aim_service", side_effect=Exception("DB error")),
    ):
        # Should not raise - exception is caught and logged
        await sync_aim_services(mock_session, kube_client)

    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_sync_lists_namespaces_in_parallel(kube_client: MagicMock) -> None:
    """list_aim_services calls across namespaces must run concurrently.

    Each per-namespace call waits on a shared barrier that's only released
    once all expected calls have started. If the syncer awaited them
    sequentially, the second call would never start and asyncio.wait_for
    would time out, failing the test.
    """
    namespaces = [_mock_namespace(f"ns-{i}") for i in range(3)]
    expected_calls = len(namespaces)
    barrier = asyncio.Event()
    call_count = 0

    async def gated_list_aim_services(_client: object, _namespace: str) -> list:
        nonlocal call_count
        call_count += 1
        if call_count == expected_calls:
            barrier.set()
        await asyncio.wait_for(barrier.wait(), timeout=1.0)
        return []

    mock_session = AsyncMock()

    with (
        patch("app.aims.syncer.get_namespaces", return_value=namespaces),
        patch("app.aims.syncer.list_aim_services", side_effect=gated_list_aim_services),
        patch("app.aims.syncer.list_aim_services_history", return_value=[]),
    ):
        await sync_aim_services(mock_session, kube_client)

    assert call_count == expected_calls
