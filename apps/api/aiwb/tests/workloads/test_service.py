# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.collections import SortCondition, SortDirection
from app.aims.crds import AIMServiceResource, AIMServiceSpec, AIMServiceStatusFields
from app.aims.enums import AIMServiceStatus
from app.dispatch.crds import K8sMetadata
from app.projects.crds import Namespace
from app.workloads.constants import DISPLAY_NAME_ANNOTATION, WORKLOAD_ID_LABEL
from app.workloads.enums import WorkloadStatus, WorkloadType
from app.workloads.service import (
    _process_aim_services_to_metrics,
    _process_workloads_to_metrics,
    delete_workload_components,
    get_workload_metrics_paginated,
    get_workload_stats_counts,
    resolve_workload_datasets,
    resolve_workloads_datasets,
)
from tests import factory
from tests.factory import DEFAULT_TEST_MANIFEST, create_aim_service_db, create_workload, make_aim_service_k8s


@pytest.mark.asyncio
async def test_resolve_workload_datasets_keeps_deleted_dataset_snapshot(db_session: AsyncSession) -> None:
    available = await factory.create_dataset(
        db_session,
        name="Available dataset",
        path="available.jsonl",
    )
    deleted = await factory.create_dataset(
        db_session,
        name="Deleted dataset",
        path="deleted.jsonl",
    )
    workload = await factory.create_workload(db_session)
    workload.dataset_refs = [
        {"id": str(available.id), "name": available.name},
        {"id": str(deleted.id), "name": deleted.name},
    ]
    await db_session.delete(deleted)
    await db_session.flush()

    result = await resolve_workload_datasets(db_session, workload.id)

    assert [dataset.model_dump() for dataset in result] == [
        {"id": available.id, "name": "Available dataset", "available": True},
        {"id": deleted.id, "name": "Deleted dataset", "available": False},
    ]


@pytest.mark.asyncio
async def test_resolve_workload_datasets_returns_empty_without_refs(db_session: AsyncSession) -> None:
    workload = await factory.create_workload(db_session)

    result = await resolve_workload_datasets(db_session, workload.id)

    assert result == []


@pytest.mark.asyncio
async def test_resolve_workloads_datasets_populates_each_workload(db_session: AsyncSession) -> None:
    datasets = [
        await factory.create_dataset(
            db_session,
            name=f"Dataset {index}",
            path=f"dataset-{index}.jsonl",
        )
        for index in range(2)
    ]
    workloads = [await factory.create_workload(db_session) for _ in range(2)]
    for workload, dataset in zip(workloads, datasets, strict=True):
        workload.dataset_refs = [{"id": str(dataset.id), "name": dataset.name}]

    result = await resolve_workloads_datasets(db_session, workloads)

    assert {
        workload_id: [dataset.model_dump() for dataset in resolved] for workload_id, resolved in result.items()
    } == {
        workload.id: [{"id": dataset.id, "name": dataset.name, "available": True}]
        for workload, dataset in zip(workloads, datasets, strict=True)
    }


@pytest.mark.asyncio
async def test_delete_workload_components_success(db_session: AsyncSession) -> None:
    """Test successful deletion of workload components."""
    workload = await factory.create_workload(db_session, namespace="test-ns", status=WorkloadStatus.RUNNING)

    with patch("app.workloads.service.delete_workload_resources") as mock_delete:
        mock_delete.return_value = None

        await delete_workload_components("test-ns", workload.id, db_session)

        # Verify gateway was called
        mock_delete.assert_called_once_with("test-ns", str(workload.id))

        # Verify workload status was updated to DELETED
        await db_session.refresh(workload)
        assert workload.status == WorkloadStatus.DELETED


@pytest.mark.asyncio
async def test_delete_workload_components_not_found(db_session: AsyncSession) -> None:
    """Test deleting a non-existent workload logs warning but doesn't error."""
    non_existent_id = uuid4()

    with patch("app.workloads.service.delete_workload_resources") as mock_delete:
        # Should not raise exception, just log warning
        await delete_workload_components("test-ns", non_existent_id, db_session)

        # Gateway should not be called if workload not found
        mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_workload_components_gateway_error(db_session: AsyncSession) -> None:
    """Test handling of Kubernetes gateway errors during deletion."""
    workload = await factory.create_workload(db_session, namespace="test-ns", status=WorkloadStatus.RUNNING)

    with patch("app.workloads.service.delete_workload_resources") as mock_delete:
        mock_delete.side_effect = RuntimeError("K8s API error")

        with pytest.raises(RuntimeError, match="K8s API error"):
            await delete_workload_components("test-ns", workload.id, db_session)


# Section 3.3: delete_workload_components() status transitions


@pytest.mark.asyncio
async def test_delete_workload_components_deleting_status(db_session: AsyncSession) -> None:
    """Test that workload status is set to DELETING before gateway call, and DELETED after success."""
    workload = await factory.create_workload(db_session, namespace="test-ns", status=WorkloadStatus.RUNNING)

    with (
        patch("app.workloads.service.update_workload_status") as mock_update_status,
        patch("app.workloads.service.delete_workload_resources") as mock_delete,
    ):
        mock_update_status.return_value = None
        mock_delete.return_value = None

        await delete_workload_components("test-ns", workload.id, db_session)

        # Verify status was updated to DELETING before gateway call
        assert mock_update_status.call_count == 2
        first_call = mock_update_status.call_args_list[0]
        assert first_call.args[1] == workload.id
        assert first_call.args[2] == WorkloadStatus.DELETING

        # Verify gateway was called
        mock_delete.assert_called_once_with("test-ns", str(workload.id))

        # Verify status was updated to DELETED after gateway call
        second_call = mock_update_status.call_args_list[1]
        assert second_call.args[1] == workload.id
        assert second_call.args[2] == WorkloadStatus.DELETED


@pytest.mark.asyncio
async def test_delete_workload_components_status_update_failure(db_session: AsyncSession) -> None:
    """Test handling when status update fails."""
    workload = await factory.create_workload(db_session, namespace="test-ns", status=WorkloadStatus.RUNNING)

    with (
        patch("app.workloads.service.update_workload_status") as mock_update_status,
        patch("app.workloads.service.delete_workload_resources") as mock_delete,
    ):
        # Simulate status update failure on first call
        mock_update_status.side_effect = RuntimeError("Database error")

        with pytest.raises(RuntimeError, match="Database error"):
            await delete_workload_components("test-ns", workload.id, db_session)

        # Verify status update was attempted
        mock_update_status.assert_called_once()

        # Gateway should not be called if status update fails
        mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_workload_components_logs_deletion(db_session: AsyncSession) -> None:
    """Test deletion is properly logged."""
    workload = await factory.create_workload(db_session, namespace="test-ns", status=WorkloadStatus.RUNNING)

    with (
        patch("app.workloads.service.delete_workload_resources") as mock_delete,
        patch("app.workloads.service.logger") as mock_logger,
    ):
        mock_delete.return_value = None

        await delete_workload_components("test-ns", workload.id, db_session)

        # Verify deletion was logged
        assert mock_logger.info.call_count >= 2
        log_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any(f"Deleting workload {workload.id}" in str(call) for call in log_calls)
        assert any("marked as DELETED" in str(call) for call in log_calls)


# =========================================================================
# Tests migrated from tests/projects/test_service.py
# =========================================================================


# Tests for get_workload_metrics_paginated
@pytest.mark.asyncio
async def test_get_workload_metrics_paginated_with_aim_services_and_workloads(
    mock_kube_client: MagicMock,
    db_session: AsyncSession,
    mock_prometheus_client: MagicMock,
) -> None:
    """Test get_workload_metrics_paginated with both AIM services and workloads."""
    # Create mock namespace
    namespace = MagicMock(spec=Namespace)
    namespace.name = "test-namespace"
    namespace.id = "test-namespace-id"

    # Create mock AIM service from K8s
    aim_service_id = uuid4()
    mock_aim_service = make_aim_service_k8s(
        namespace="test-namespace",
        workload_id=aim_service_id,
        status=AIMServiceStatus.RUNNING,
    )

    # Create real AIM service in DB
    mock_aim_db = await create_aim_service_db(
        db_session,
        id=aim_service_id,
        namespace="test-namespace",
        status=AIMServiceStatus.RUNNING,
        created_by="test-user",
    )

    # Create real workload in DB
    workload = await create_workload(
        db_session,
        name="test-workload",
        display_name="Test Workload",
        namespace="test-namespace",
        workload_type=WorkloadType.INFERENCE,
        status=WorkloadStatus.RUNNING,
        submitter="test-user-2",
    )

    # Mock GPU and VRAM data
    gpu_counts = {str(aim_service_id): 2, str(workload.id): 4}
    vram_usage = {str(aim_service_id): 16000.0, str(workload.id): 32000.0}

    with (
        patch("app.workloads.service.list_aim_services", autospec=True) as mock_list_aims,
        patch("app.workloads.service.get_gpu_utilization_by_workload_in_namespace", autospec=True) as mock_gpu,
        patch("app.workloads.service.get_gpu_vram_by_workload_in_namespace", autospec=True) as mock_vram,
    ):
        mock_list_aims.return_value = [mock_aim_service]
        mock_gpu.return_value = gpu_counts
        mock_vram.return_value = vram_usage

        result = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
        )

        # Verify service calls — no status filter requested means status_filter=None.
        mock_list_aims.assert_called_once_with(mock_kube_client, namespace.name, status_filter=None)
        mock_gpu.assert_called_once()
        mock_vram.assert_called_once()

        # Verify response structure and pagination
        assert len(result.data) == 2
        assert result.pagination.total == 2
        assert result.pagination.page == 1
        assert result.pagination.page_size == 10

        # Verify AIM service metrics (k8s-first: SUBMITTER_ANNOTATION on the CR wins over the DB row)
        aim_metric = next(m for m in result.data if m.id == aim_service_id)
        assert aim_metric.name == mock_aim_service.metadata.name
        assert aim_metric.type == WorkloadType.INFERENCE
        assert aim_metric.status == WorkloadStatus.RUNNING
        assert aim_metric.gpu_count == 2
        assert aim_metric.vram == 16000.0
        assert aim_metric.created_by == "test@example.com"

        # Verify workload metrics
        workload_metric = next(m for m in result.data if m.id == workload.id)
        assert workload_metric.name == "test-workload"
        assert workload_metric.display_name == "Test Workload"
        assert workload_metric.type == WorkloadType.INFERENCE
        assert workload_metric.status == WorkloadStatus.RUNNING
        assert workload_metric.gpu_count == 4
        assert workload_metric.vram == 32000.0
        assert workload_metric.created_by == "test-user-2"


@pytest.mark.asyncio
async def test_get_workload_metrics_paginated_pagination(
    mock_kube_client: MagicMock,
    db_session: AsyncSession,
    mock_prometheus_client: MagicMock,
) -> None:
    """Test that get_workload_metrics_paginated correctly paginates results."""
    namespace = MagicMock(spec=Namespace)
    namespace.name = "test-namespace"
    namespace.id = "test-namespace-id"

    # Create 5 real workloads in database
    workloads = []
    for i in range(5):
        workload = await create_workload(
            db_session,
            name=f"workload-{i}",
            display_name=f"Workload {i}",
            namespace="test-namespace",
            workload_type=WorkloadType.INFERENCE,
            status=WorkloadStatus.RUNNING,
            submitter="test-user",
        )
        workloads.append(workload)

    with (
        patch("app.workloads.service.list_aim_services", autospec=True) as mock_list_aims,
        patch("app.workloads.service.get_gpu_utilization_by_workload_in_namespace", autospec=True) as mock_gpu,
        patch("app.workloads.service.get_gpu_vram_by_workload_in_namespace", autospec=True) as mock_vram,
    ):
        mock_list_aims.return_value = []
        mock_gpu.return_value = {}
        mock_vram.return_value = {}

        # Test first page with page_size=2
        result = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
            page=1,
            page_size=2,
        )

        assert len(result.data) == 2
        assert result.pagination.total == 5
        assert result.pagination.page == 1
        assert result.pagination.page_size == 2

        # Test second page
        result2 = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
            page=2,
            page_size=2,
        )

        assert len(result2.data) == 2
        assert result2.pagination.page == 2

        # Test last page (partial)
        result3 = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
            page=3,
            page_size=2,
        )

        assert len(result3.data) == 1
        assert result3.pagination.page == 3


@pytest.mark.asyncio
async def test_get_workload_metrics_paginated_empty_namespace(
    mock_kube_client: MagicMock,
    db_session: AsyncSession,
    mock_prometheus_client: MagicMock,
) -> None:
    """Test get_workload_metrics_paginated with empty namespace."""
    namespace = MagicMock(spec=Namespace)
    namespace.name = "empty-namespace"
    namespace.id = "empty-namespace-id"

    with (
        patch("app.workloads.service.list_aim_services", autospec=True) as mock_list_aims,
        patch("app.workloads.service.get_gpu_utilization_by_workload_in_namespace", autospec=True) as mock_gpu,
        patch("app.workloads.service.get_gpu_vram_by_workload_in_namespace", autospec=True) as mock_vram,
    ):
        mock_list_aims.return_value = []
        mock_gpu.return_value = {}
        mock_vram.return_value = {}

        result = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
        )

        # Verify empty results
        assert len(result.data) == 0
        assert result.pagination.total == 0
        assert result.pagination.page == 1


@pytest.mark.asyncio
async def test_get_workload_metrics_paginated_filter_by_workload_type(
    mock_kube_client: MagicMock,
    mock_db_session: AsyncMock,
    mock_prometheus_client: MagicMock,
) -> None:
    """Test get_workload_metrics_paginated filters by workload type."""
    namespace = MagicMock()
    namespace.name = "test-namespace"
    namespace.id = "test-namespace-id"

    # Create mock workloads of different types
    workload_inference = MagicMock()
    workload_inference.id = uuid4()
    workload_inference.name = "workload-inference"
    workload_inference.display_name = "Inference Workload"
    workload_inference.type = WorkloadType.INFERENCE
    workload_inference.status = WorkloadStatus.RUNNING
    workload_inference.manifest = DEFAULT_TEST_MANIFEST
    workload_inference.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    workload_inference.created_by = "test-user"

    workload_finetuning = MagicMock()
    workload_finetuning.id = uuid4()
    workload_finetuning.name = "workload-finetuning"
    workload_finetuning.display_name = "Fine-tuning Workload"
    workload_finetuning.type = WorkloadType.FINE_TUNING
    workload_finetuning.status = WorkloadStatus.RUNNING
    workload_finetuning.manifest = DEFAULT_TEST_MANIFEST
    workload_finetuning.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    workload_finetuning.created_by = "test-user"

    with (
        patch("app.workloads.service.list_aim_services", new_callable=AsyncMock) as mock_list_aims,
        patch("app.workloads.service.get_workloads", new_callable=AsyncMock) as mock_get_workloads,
        patch("app.workloads.service.get_gpu_utilization_by_workload_in_namespace", new_callable=AsyncMock) as mock_gpu,
        patch("app.workloads.service.get_gpu_vram_by_workload_in_namespace", new_callable=AsyncMock) as mock_vram,
    ):
        # Return only fine-tuning workload when filtering by FINE_TUNING
        mock_list_aims.return_value = []  # AIM services are always INFERENCE, so not included
        mock_get_workloads.return_value = [workload_finetuning]
        mock_gpu.return_value = {}
        mock_vram.return_value = {}

        result = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=mock_db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
            workload_types=[WorkloadType.FINE_TUNING],
        )

        # Both are fetched in parallel, AIM services returns empty
        mock_list_aims.assert_called_once()
        mock_get_workloads.assert_called_once()
        call_kwargs = mock_get_workloads.call_args.kwargs
        assert call_kwargs["workload_types"] == [WorkloadType.FINE_TUNING]

        # Only fine-tuning workload in result
        assert len(result.data) == 1
        assert result.data[0].type == WorkloadType.FINE_TUNING


@pytest.mark.asyncio
async def test_get_workload_metrics_paginated_filter_by_status(
    mock_kube_client: MagicMock,
    mock_db_session: AsyncMock,
    mock_prometheus_client: MagicMock,
) -> None:
    """Test get_workload_metrics_paginated filters by status."""
    namespace = MagicMock()
    namespace.name = "test-namespace"
    namespace.id = "test-namespace-id"

    # Create mock AIM service with RUNNING status
    aim_service_id = uuid4()
    mock_aim_service = MagicMock()
    mock_aim_service.id = str(aim_service_id)
    mock_aim_service.metadata.name = "test-aim-service"
    mock_aim_service.metadata.annotations = {}
    mock_aim_service.metadata.creation_timestamp = None
    mock_aim_service.status.status = AIMServiceStatus.RUNNING
    mock_aim_service.status.resolved_model = None

    # Create mock workload with PENDING status
    workload_pending = MagicMock()
    workload_pending.id = uuid4()
    workload_pending.name = "workload-pending"
    workload_pending.display_name = "Pending Workload"
    workload_pending.type = WorkloadType.INFERENCE
    workload_pending.status = WorkloadStatus.PENDING
    workload_pending.manifest = DEFAULT_TEST_MANIFEST
    workload_pending.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    workload_pending.created_by = "test-user"

    with (
        patch("app.workloads.service.list_aim_services", new_callable=AsyncMock) as mock_list_aims,
        patch("app.workloads.service.get_workloads", new_callable=AsyncMock) as mock_get_workloads,
        patch("app.workloads.service.get_aim_service_by_id", new_callable=AsyncMock) as mock_get_aim_db,
        patch("app.workloads.service.get_gpu_utilization_by_workload_in_namespace", new_callable=AsyncMock) as mock_gpu,
        patch("app.workloads.service.get_gpu_vram_by_workload_in_namespace", new_callable=AsyncMock) as mock_vram,
    ):
        mock_list_aims.return_value = [mock_aim_service]
        mock_get_workloads.return_value = []  # No RUNNING workloads
        mock_get_aim_db.return_value = None
        mock_gpu.return_value = {}
        mock_vram.return_value = {}

        # Filter for RUNNING status only
        result = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=mock_db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
            status_filter=[WorkloadStatus.RUNNING],
        )

        # Should pass status_filter to get_workloads
        mock_get_workloads.assert_called_once()
        call_kwargs = mock_get_workloads.call_args.kwargs
        assert call_kwargs["status_filter"] == [WorkloadStatus.RUNNING]

        # Only the AIM service (RUNNING) should be in results
        assert len(result.data) == 1
        assert result.data[0].status == WorkloadStatus.RUNNING


@pytest.mark.asyncio
async def test_get_workload_metrics_paginated_workload_only_status_skips_aim_query(
    mock_kube_client: MagicMock,
    mock_db_session: AsyncMock,
    mock_prometheus_client: MagicMock,
) -> None:
    """Filtering by a workload-only status (e.g. COMPLETE) must not return AIM services.

    ``list_aim_services`` treats a falsy ``status_filter`` as "no filter" and returns
    every AIM service, so the implementation must short-circuit the query when the
    user's filter maps to no AIM statuses.
    """
    namespace = MagicMock()
    namespace.name = "test-namespace"
    namespace.id = "test-namespace-id"

    workload_complete = MagicMock()
    workload_complete.id = uuid4()
    workload_complete.name = "workload-complete"
    workload_complete.display_name = "Complete Workload"
    workload_complete.type = WorkloadType.INFERENCE
    workload_complete.status = WorkloadStatus.COMPLETE
    workload_complete.manifest = DEFAULT_TEST_MANIFEST
    workload_complete.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    workload_complete.created_by = "test-user"

    with (
        patch("app.workloads.service.list_aim_services", new_callable=AsyncMock) as mock_list_aims,
        patch("app.workloads.service.get_workloads", new_callable=AsyncMock) as mock_get_workloads,
        patch("app.workloads.service.get_gpu_utilization_by_workload_in_namespace", new_callable=AsyncMock) as mock_gpu,
        patch("app.workloads.service.get_gpu_vram_by_workload_in_namespace", new_callable=AsyncMock) as mock_vram,
    ):
        mock_get_workloads.return_value = [workload_complete]
        mock_gpu.return_value = {}
        mock_vram.return_value = {}

        result = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=mock_db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
            status_filter=[WorkloadStatus.COMPLETE],
        )

        # AIM query must not be issued when the filter has no AIM-compatible statuses.
        mock_list_aims.assert_not_called()

        # Only the workload (COMPLETE) should be in results.
        assert len(result.data) == 1
        assert result.data[0].status == WorkloadStatus.COMPLETE


@pytest.mark.asyncio
async def test_get_workload_metrics_paginated_filter_by_type_and_status(
    mock_kube_client: MagicMock,
    mock_db_session: AsyncMock,
    mock_prometheus_client: MagicMock,
) -> None:
    """Test get_workload_metrics_paginated filters by both type and status."""
    namespace = MagicMock()
    namespace.name = "test-namespace"
    namespace.id = "test-namespace-id"

    # Create mock AIM service (INFERENCE, RUNNING)
    aim_service_id = uuid4()
    mock_aim_service = MagicMock()
    mock_aim_service.id = str(aim_service_id)
    mock_aim_service.metadata.name = "test-aim-service"
    mock_aim_service.metadata.annotations = {}
    mock_aim_service.metadata.creation_timestamp = None
    mock_aim_service.status.status = AIMServiceStatus.RUNNING
    mock_aim_service.status.resolved_model = None

    # Create mock INFERENCE workload (RUNNING)
    workload_inference = MagicMock()
    workload_inference.id = uuid4()
    workload_inference.name = "workload-inference"
    workload_inference.display_name = "Inference Workload"
    workload_inference.type = WorkloadType.INFERENCE
    workload_inference.status = WorkloadStatus.RUNNING
    workload_inference.manifest = DEFAULT_TEST_MANIFEST
    workload_inference.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    workload_inference.created_by = "test-user"

    with (
        patch("app.workloads.service.list_aim_services", new_callable=AsyncMock) as mock_list_aims,
        patch("app.workloads.service.get_workloads", new_callable=AsyncMock) as mock_get_workloads,
        patch("app.workloads.service.get_aim_service_by_id", new_callable=AsyncMock) as mock_get_aim_db,
        patch("app.workloads.service.get_gpu_utilization_by_workload_in_namespace", new_callable=AsyncMock) as mock_gpu,
        patch("app.workloads.service.get_gpu_vram_by_workload_in_namespace", new_callable=AsyncMock) as mock_vram,
    ):
        mock_list_aims.return_value = [mock_aim_service]
        mock_get_workloads.return_value = [workload_inference]
        mock_get_aim_db.return_value = None
        mock_gpu.return_value = {}
        mock_vram.return_value = {}

        # Filter for INFERENCE type and RUNNING status
        result = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=mock_db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
            workload_types=[WorkloadType.INFERENCE],
            status_filter=[WorkloadStatus.RUNNING],
        )

        # Verify correct calls
        mock_list_aims.assert_called_once()  # Should include AIM services (INFERENCE)
        mock_get_workloads.assert_called_once()
        call_kwargs = mock_get_workloads.call_args.kwargs
        assert call_kwargs["workload_types"] == [WorkloadType.INFERENCE]
        assert call_kwargs["status_filter"] == [WorkloadStatus.RUNNING]

        # Both RUNNING resources should be in results
        assert len(result.data) == 2
        assert all(m.status == WorkloadStatus.RUNNING for m in result.data)
        assert all(m.type == WorkloadType.INFERENCE for m in result.data)


@pytest.mark.asyncio
async def test_get_workload_metrics_paginated_sorting(
    mock_kube_client: MagicMock,
    mock_db_session: AsyncMock,
    mock_prometheus_client: MagicMock,
) -> None:
    """Test that get_workload_metrics_paginated sorts results before pagination."""
    namespace = MagicMock()
    namespace.name = "test-namespace"
    namespace.id = "test-namespace-id"

    # Create workloads with different created_at dates
    workload_old = MagicMock()
    workload_old.id = uuid4()
    workload_old.name = "workload-old"
    workload_old.display_name = "Old Workload"
    workload_old.type = WorkloadType.INFERENCE
    workload_old.status = WorkloadStatus.RUNNING
    workload_old.manifest = DEFAULT_TEST_MANIFEST
    workload_old.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    workload_old.created_by = "test-user"

    workload_new = MagicMock()
    workload_new.id = uuid4()
    workload_new.name = "workload-new"
    workload_new.display_name = "New Workload"
    workload_new.type = WorkloadType.INFERENCE
    workload_new.status = WorkloadStatus.RUNNING
    workload_new.manifest = DEFAULT_TEST_MANIFEST
    workload_new.created_at = datetime(2025, 1, 10, tzinfo=UTC)
    workload_new.created_by = "test-user"

    workload_mid = MagicMock()
    workload_mid.id = uuid4()
    workload_mid.name = "workload-mid"
    workload_mid.display_name = "Mid Workload"
    workload_mid.type = WorkloadType.INFERENCE
    workload_mid.status = WorkloadStatus.RUNNING
    workload_mid.manifest = DEFAULT_TEST_MANIFEST
    workload_mid.created_at = datetime(2025, 1, 5, tzinfo=UTC)
    workload_mid.created_by = "test-user"

    with (
        patch("app.workloads.service.list_aim_services", new_callable=AsyncMock) as mock_list_aims,
        patch("app.workloads.service.get_workloads", new_callable=AsyncMock) as mock_get_workloads,
        patch("app.workloads.service.get_gpu_utilization_by_workload_in_namespace", new_callable=AsyncMock) as mock_gpu,
        patch("app.workloads.service.get_gpu_vram_by_workload_in_namespace", new_callable=AsyncMock) as mock_vram,
    ):
        mock_list_aims.return_value = []
        # Return workloads in unsorted order
        mock_get_workloads.return_value = [workload_mid, workload_old, workload_new]
        mock_gpu.return_value = {}
        mock_vram.return_value = {}

        # Test descending sort by created_at
        result_desc = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=mock_db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
            sort=[SortCondition(field="created_at", direction=SortDirection.desc)],
        )

        assert len(result_desc.data) == 3
        assert result_desc.data[0].name == "workload-new"
        assert result_desc.data[1].name == "workload-mid"
        assert result_desc.data[2].name == "workload-old"

        # Test ascending sort by created_at
        result_asc = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=mock_db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
            sort=[SortCondition(field="created_at", direction=SortDirection.asc)],
        )

        assert len(result_asc.data) == 3
        assert result_asc.data[0].name == "workload-old"
        assert result_asc.data[1].name == "workload-mid"
        assert result_asc.data[2].name == "workload-new"


@pytest.mark.asyncio
async def test_get_workload_metrics_paginated_sorting_with_pagination(
    mock_kube_client: MagicMock,
    mock_db_session: AsyncMock,
    mock_prometheus_client: MagicMock,
) -> None:
    """Test that sorting applies to full dataset before pagination."""
    namespace = MagicMock()
    namespace.name = "test-namespace"
    namespace.id = "test-namespace-id"

    # Create 5 workloads
    workloads = []
    for i in range(5):
        workload = MagicMock()
        workload.id = uuid4()
        workload.name = f"workload-{i}"
        workload.display_name = f"Workload {i}"
        workload.type = WorkloadType.INFERENCE
        workload.status = WorkloadStatus.RUNNING
        workload.manifest = DEFAULT_TEST_MANIFEST
        workload.created_at = datetime(2025, 1, i + 1, tzinfo=UTC)
        workload.created_by = "test-user"
        workloads.append(workload)

    with (
        patch("app.workloads.service.list_aim_services", new_callable=AsyncMock) as mock_list_aims,
        patch("app.workloads.service.get_workloads", new_callable=AsyncMock) as mock_get_workloads,
        patch("app.workloads.service.get_gpu_utilization_by_workload_in_namespace", new_callable=AsyncMock) as mock_gpu,
        patch("app.workloads.service.get_gpu_vram_by_workload_in_namespace", new_callable=AsyncMock) as mock_vram,
    ):
        mock_list_aims.return_value = []
        mock_get_workloads.return_value = workloads
        mock_gpu.return_value = {}
        mock_vram.return_value = {}

        # Get page 1 with page_size=2 sorted descending
        result = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=mock_db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
            page=1,
            page_size=2,
            sort=[SortCondition(field="created_at", direction=SortDirection.desc)],
        )

        # Should have newest 2 workloads (workload-4 and workload-3)
        assert len(result.data) == 2
        assert result.pagination.total == 5
        assert result.data[0].name == "workload-4"
        assert result.data[1].name == "workload-3"

        # Get page 2
        result2 = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=mock_db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
            page=2,
            page_size=2,
            sort=[SortCondition(field="created_at", direction=SortDirection.desc)],
        )

        # Should have next 2 workloads (workload-2 and workload-1)
        assert len(result2.data) == 2
        assert result2.data[0].name == "workload-2"
        assert result2.data[1].name == "workload-1"


@pytest.mark.asyncio
async def test_get_workload_metrics_paginated_sorting_by_status_across_pages(
    mock_kube_client: MagicMock,
    mock_db_session: AsyncMock,
    mock_prometheus_client: MagicMock,
) -> None:
    """Test sorting by status groups all items by status across pages.

    Scenario: Page 1 has 3 RUNNING + 1 FAILED, Page 2 has 1 RUNNING.
    When sorted by status ascending, page 1 should have 1 FAILED + 3 RUNNING,
    and page 2 should have 1 RUNNING.
    When sorted descending, page 1 should have 4 RUNNING, page 2 should have 1 FAILED.
    """
    namespace = MagicMock()
    namespace.name = "test-namespace"
    namespace.id = "test-namespace-id"

    # Create 5 workloads: 4 RUNNING, 1 FAILED
    workloads = []
    for i in range(4):
        workload = MagicMock()
        workload.id = uuid4()
        workload.name = f"running-{i}"
        workload.display_name = f"Running Workload {i}"
        workload.type = WorkloadType.INFERENCE
        workload.status = WorkloadStatus.RUNNING
        workload.manifest = DEFAULT_TEST_MANIFEST
        workload.created_at = datetime(2025, 1, i + 1, tzinfo=UTC)
        workload.created_by = "test-user"
        workloads.append(workload)

    failed_workload = MagicMock()
    failed_workload.id = uuid4()
    failed_workload.name = "failed-0"
    failed_workload.display_name = "Failed Workload"
    failed_workload.type = WorkloadType.INFERENCE
    failed_workload.status = WorkloadStatus.FAILED
    failed_workload.manifest = DEFAULT_TEST_MANIFEST
    failed_workload.created_at = datetime(2025, 1, 5, tzinfo=UTC)
    failed_workload.created_by = "test-user"
    workloads.append(failed_workload)

    with (
        patch("app.workloads.service.list_aim_services", new_callable=AsyncMock) as mock_list_aims,
        patch("app.workloads.service.get_workloads", new_callable=AsyncMock) as mock_get_workloads,
        patch("app.workloads.service.get_gpu_utilization_by_workload_in_namespace", new_callable=AsyncMock) as mock_gpu,
        patch("app.workloads.service.get_gpu_vram_by_workload_in_namespace", new_callable=AsyncMock) as mock_vram,
    ):
        mock_list_aims.return_value = []
        mock_get_workloads.return_value = workloads
        mock_gpu.return_value = {}
        mock_vram.return_value = {}

        # Sort by status descending (RUNNING > FAILED alphabetically reversed)
        # Page 1 (page_size=4) should have all 4 RUNNING
        result_page1 = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=mock_db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
            page=1,
            page_size=4,
            sort=[SortCondition(field="status", direction=SortDirection.desc)],
        )

        # Page 2 should have the FAILED workload
        result_page2 = await get_workload_metrics_paginated(
            kube_client=mock_kube_client,
            session=mock_db_session,
            namespace=namespace,
            prometheus_client=mock_prometheus_client,
            page=2,
            page_size=4,
            sort=[SortCondition(field="status", direction=SortDirection.desc)],
        )

        # Verify total is 5 across both pages
        assert result_page1.pagination.total == 5
        assert result_page2.pagination.total == 5

        # Page 1: 4 items, all should be RUNNING (sorted desc, R > F)
        assert len(result_page1.data) == 4
        assert all(m.status == WorkloadStatus.RUNNING for m in result_page1.data)

        # Page 2: 1 item, should be FAILED
        assert len(result_page2.data) == 1
        assert result_page2.data[0].status == WorkloadStatus.FAILED


# Tests for get_workload_stats_counts
@pytest.mark.asyncio
async def test_get_workload_stats_counts_with_resources(
    mock_kube_client: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Test get_workload_stats_counts with both AIM services and workloads."""
    namespace = MagicMock(spec=Namespace)
    namespace.name = "test-namespace"
    namespace.id = "test-namespace-id"

    # Create mock AIM service from K8s
    aim_service_id = uuid4()
    mock_aim_service = make_aim_service_k8s(
        namespace="test-namespace",
        workload_id=aim_service_id,
        status=AIMServiceStatus.RUNNING,
    )

    # Create real workloads in DB with different statuses
    workload_running = await create_workload(
        db_session,
        name="workload-running",
        display_name="Workload Running",
        namespace="test-namespace",
        workload_type=WorkloadType.INFERENCE,
        status=WorkloadStatus.RUNNING,
        submitter="test-user-2",
    )

    workload_pending = await create_workload(
        db_session,
        name="workload-pending",
        display_name="Workload Pending",
        namespace="test-namespace",
        workload_type=WorkloadType.INFERENCE,
        status=WorkloadStatus.PENDING,
        submitter="test-user-2",
    )

    with (
        patch("app.workloads.service.list_aim_services", autospec=True) as mock_list_aims,
    ):
        mock_list_aims.return_value = [mock_aim_service]

        result = await get_workload_stats_counts(
            kube_client=mock_kube_client,
            session=db_session,
            namespace=namespace,
        )

        # Verify response structure
        assert result.project == "test-namespace"
        assert result.total == 3

        # Verify status counts
        status_dict = {count.status: count.count for count in result.status_counts}
        assert status_dict[WorkloadStatus.RUNNING] == 2
        assert status_dict[WorkloadStatus.PENDING] == 1


@pytest.mark.asyncio
async def test_get_workload_stats_counts_empty_namespace(
    mock_kube_client: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Test get_workload_stats_counts with empty namespace."""
    namespace = MagicMock(spec=Namespace)
    namespace.name = "empty-namespace"
    namespace.id = "empty-namespace-id"

    with (
        patch("app.workloads.service.list_aim_services", autospec=True) as mock_list_aims,
    ):
        mock_list_aims.return_value = []

        result = await get_workload_stats_counts(
            kube_client=mock_kube_client,
            session=db_session,
            namespace=namespace,
        )

        # Verify empty results
        assert result.project == "empty-namespace"
        assert result.total == 0
        assert len(result.status_counts) == 0


@pytest.mark.asyncio
async def test_get_workload_stats_counts_all_statuses(
    mock_kube_client: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Test get_workload_stats_counts with resources in all statuses."""
    namespace = MagicMock(spec=Namespace)
    namespace.name = "test-namespace"
    namespace.id = "test-namespace-id"

    # Create real workloads in DB with different statuses
    workload_running = await create_workload(
        db_session,
        name="workload-running",
        display_name="Workload Running",
        namespace="test-namespace",
        workload_type=WorkloadType.INFERENCE,
        status=WorkloadStatus.RUNNING,
        submitter="test-user",
    )

    workload_pending = await create_workload(
        db_session,
        name="workload-pending",
        display_name="Workload Pending",
        namespace="test-namespace",
        workload_type=WorkloadType.INFERENCE,
        status=WorkloadStatus.PENDING,
        submitter="test-user",
    )

    workload_failed = await create_workload(
        db_session,
        name="workload-failed",
        display_name="Workload Failed",
        namespace="test-namespace",
        workload_type=WorkloadType.INFERENCE,
        status=WorkloadStatus.FAILED,
        submitter="test-user",
    )

    workload_complete = await create_workload(
        db_session,
        name="workload-complete",
        display_name="Workload Complete",
        namespace="test-namespace",
        workload_type=WorkloadType.INFERENCE,
        status=WorkloadStatus.COMPLETE,
        submitter="test-user",
    )

    with (
        patch("app.workloads.service.list_aim_services", autospec=True) as mock_list_aims,
    ):
        mock_list_aims.return_value = []

        result = await get_workload_stats_counts(
            kube_client=mock_kube_client,
            session=db_session,
            namespace=namespace,
        )

        # Verify totals
        assert result.project == "test-namespace"
        assert result.total == 4

        # Verify all statuses are represented
        status_dict = {count.status: count.count for count in result.status_counts}
        assert status_dict[WorkloadStatus.RUNNING] == 1
        assert status_dict[WorkloadStatus.PENDING] == 1
        assert status_dict[WorkloadStatus.FAILED] == 1
        assert status_dict[WorkloadStatus.COMPLETE] == 1


# Tests for _process_aim_services_to_metrics
@pytest.mark.asyncio
async def test_process_aim_services_to_metrics(db_session: AsyncSession) -> None:
    """Test _process_aim_services_to_metrics converts AIM services correctly."""
    aim_service_id = uuid4()

    # Create mock AIM service from K8s
    mock_aim_service = make_aim_service_k8s(
        namespace="test-namespace",
        workload_id=aim_service_id,
        status=AIMServiceStatus.RUNNING,
    )

    # Create real AIM service in DB
    mock_aim_db = await create_aim_service_db(
        db_session,
        id=aim_service_id,
        namespace="test-namespace",
        status=AIMServiceStatus.RUNNING,
        created_by="test-user",
    )

    gpu_counts = {str(aim_service_id): 4}
    vram_usage = {str(aim_service_id): 24000.0}

    result = await _process_aim_services_to_metrics(
        aim_services_k8s=[mock_aim_service],
        session=db_session,
        namespace_name="test-namespace",
        gpu_counts=gpu_counts,
        vram_usage=vram_usage,
    )

    assert len(result) == 1
    metric = result[0]
    assert metric.id == aim_service_id
    assert metric.name == mock_aim_service.metadata.name
    assert metric.type == WorkloadType.INFERENCE
    assert metric.status == WorkloadStatus.RUNNING
    assert metric.gpu_count == 4
    assert metric.vram == 24000.0
    # K8s SUBMITTER_ANNOTATION ("test@example.com") wins over the DB row's "test-user"
    assert metric.created_by == "test@example.com"


@pytest.mark.asyncio
async def test_process_aim_services_to_metrics_display_name_from_annotation(db_session: AsyncSession) -> None:
    """Display name resolves from the display-name annotation when present."""
    aim_service_id = uuid4()

    mock_aim_service = make_aim_service_k8s(
        namespace="test-namespace",
        workload_id=aim_service_id,
        status=AIMServiceStatus.RUNNING,
    )
    mock_aim_service.metadata.annotations[DISPLAY_NAME_ANNOTATION] = "My Llama Deployment"

    result = await _process_aim_services_to_metrics(
        aim_services_k8s=[mock_aim_service],
        session=db_session,
        namespace_name="test-namespace",
        gpu_counts={},
        vram_usage={},
    )

    assert len(result) == 1
    metric = result[0]
    # The annotation wins over both the resolved model name and the resource name.
    assert metric.display_name == "My Llama Deployment"
    assert metric.name == mock_aim_service.metadata.name


@pytest.mark.asyncio
async def test_process_aim_services_to_metrics_display_name_resolution_order(db_session: AsyncSession) -> None:
    """Without the annotation, display name falls back to resolved model name, then resource name."""
    aim_service_id = uuid4()

    mock_aim_service = make_aim_service_k8s(
        namespace="test-namespace",
        workload_id=aim_service_id,
        model_ref="llama3-70b",
        status=AIMServiceStatus.RUNNING,
    )

    result = await _process_aim_services_to_metrics(
        aim_services_k8s=[mock_aim_service],
        session=db_session,
        namespace_name="test-namespace",
        gpu_counts={},
        vram_usage={},
    )
    assert result[0].display_name == "llama3-70b"

    # No annotation and no resolved model (pre-reconciliation) -> fall back to resource name.
    mock_aim_service.status.resolved_model = None
    result = await _process_aim_services_to_metrics(
        aim_services_k8s=[mock_aim_service],
        session=db_session,
        namespace_name="test-namespace",
        gpu_counts={},
        vram_usage={},
    )
    assert result[0].display_name == mock_aim_service.metadata.name


@pytest.mark.asyncio
async def test_process_aim_services_to_metrics_uses_k8s_metadata_without_db_row(db_session: AsyncSession) -> None:
    """Test _process_aim_services_to_metrics uses K8s metadata when no DB record exists.

    Fine-tuned AIM services have no Postgres row (the syncer skips namespace-scoped
    AIMModels), so creation metadata comes from the AIMService CR itself.
    """
    aim_service_id = uuid4()
    creation_timestamp = datetime(2026, 1, 15, 12, 30, 0, tzinfo=UTC)

    mock_aim_service = make_aim_service_k8s(
        namespace="test-namespace",
        workload_id=aim_service_id,
        status=AIMServiceStatus.RUNNING,
    )
    mock_aim_service.metadata.creation_timestamp = creation_timestamp

    result = await _process_aim_services_to_metrics(
        aim_services_k8s=[mock_aim_service],
        session=db_session,
        namespace_name="test-namespace",
        gpu_counts={},
        vram_usage={},
    )

    assert len(result) == 1
    metric = result[0]
    assert metric.created_at == creation_timestamp
    assert metric.created_by == "test@example.com"


@pytest.mark.asyncio
async def test_process_aim_services_to_metrics_k8s_metadata_takes_precedence(db_session: AsyncSession) -> None:
    """Test _process_aim_services_to_metrics prefers K8s metadata over DB row values.

    Kubernetes is the source of truth for AIM service state, so creator/timestamp
    from the CR win over any DB row that may exist.
    """
    aim_service_id = uuid4()
    k8s_creation_timestamp = datetime(2026, 1, 15, 12, 30, 0, tzinfo=UTC)

    mock_aim_service = make_aim_service_k8s(
        namespace="test-namespace",
        workload_id=aim_service_id,
        status=AIMServiceStatus.RUNNING,
    )
    mock_aim_service.metadata.creation_timestamp = k8s_creation_timestamp

    db_record = await create_aim_service_db(
        db_session,
        id=aim_service_id,
        namespace="test-namespace",
        status=AIMServiceStatus.RUNNING,
        created_by="db-user@example.com",
    )

    result = await _process_aim_services_to_metrics(
        aim_services_k8s=[mock_aim_service],
        session=db_session,
        namespace_name="test-namespace",
        gpu_counts={},
        vram_usage={},
    )

    assert len(result) == 1
    metric = result[0]
    assert metric.created_at == k8s_creation_timestamp
    assert metric.created_at != db_record.created_at
    assert metric.created_by == "test@example.com"
    assert metric.created_by != "db-user@example.com"


@pytest.mark.asyncio
async def test_process_aim_services_to_metrics_falls_back_to_db_row(db_session: AsyncSession) -> None:
    """Test _process_aim_services_to_metrics falls back to DB row when K8s metadata is missing.

    If the AIMService CR has no creation_timestamp or SUBMITTER_ANNOTATION (e.g. annotation
    stripped by a controller), values from the DB row are used as a fallback.
    """
    aim_service_id = uuid4()

    mock_aim_service = make_aim_service_k8s(
        namespace="test-namespace",
        workload_id=aim_service_id,
        status=AIMServiceStatus.RUNNING,
    )
    mock_aim_service.metadata.creation_timestamp = None
    mock_aim_service.metadata.annotations = {}

    db_record = await create_aim_service_db(
        db_session,
        id=aim_service_id,
        namespace="test-namespace",
        status=AIMServiceStatus.RUNNING,
        created_by="db-user@example.com",
    )

    result = await _process_aim_services_to_metrics(
        aim_services_k8s=[mock_aim_service],
        session=db_session,
        namespace_name="test-namespace",
        gpu_counts={},
        vram_usage={},
    )

    assert len(result) == 1
    metric = result[0]
    assert metric.created_at == db_record.created_at
    assert metric.created_by == "db-user@example.com"


@pytest.mark.asyncio
async def test_process_aim_services_to_metrics_no_submitter_annotation(db_session: AsyncSession) -> None:
    """Test _process_aim_services_to_metrics handles missing submitter annotation.

    When neither the DB row nor a submitter annotation is available, created_by
    is None but created_at still comes from the K8s creation_timestamp.
    """
    aim_service_id = uuid4()
    creation_timestamp = datetime(2026, 1, 15, 12, 30, 0, tzinfo=UTC)

    mock_aim_service = make_aim_service_k8s(
        namespace="test-namespace",
        workload_id=aim_service_id,
        status=AIMServiceStatus.RUNNING,
    )
    mock_aim_service.metadata.annotations = {}
    mock_aim_service.metadata.creation_timestamp = creation_timestamp

    result = await _process_aim_services_to_metrics(
        aim_services_k8s=[mock_aim_service],
        session=db_session,
        namespace_name="test-namespace",
        gpu_counts={},
        vram_usage={},
    )

    assert len(result) == 1
    metric = result[0]
    assert metric.created_at == creation_timestamp
    assert metric.created_by is None


@pytest.mark.asyncio
async def test_process_aim_services_to_metrics_skips_invalid_workload_id(db_session: AsyncSession) -> None:
    """Test _process_aim_services_to_metrics skips AIM services with invalid workload IDs."""
    # Service with no workload ID label
    mock_aim_service_no_uid = MagicMock(spec=AIMServiceResource)
    mock_aim_service_no_uid.metadata = K8sMetadata(name="test-aim-service-1", labels={})
    # Mock the id property to return None
    mock_aim_service_no_uid.id = None

    # Service with invalid UUID in workload ID label
    mock_aim_service_invalid_uuid = MagicMock(spec=AIMServiceResource)
    mock_aim_service_invalid_uuid.metadata = K8sMetadata(
        name="test-aim-service-2",
        labels={WORKLOAD_ID_LABEL: "invalid-uuid"},
    )
    # Mock the id property to return the invalid UUID
    mock_aim_service_invalid_uuid.id = "invalid-uuid"

    result = await _process_aim_services_to_metrics(
        aim_services_k8s=[mock_aim_service_no_uid, mock_aim_service_invalid_uuid],
        session=db_session,
        namespace_name="test-namespace",
        gpu_counts={},
        vram_usage={},
    )

    assert len(result) == 0


@pytest.mark.asyncio
async def test_process_aim_services_to_metrics_fallback_display_name(db_session: AsyncSession) -> None:
    """Test _process_aim_services_to_metrics falls back to name when no other source is available."""
    aim_service_id = uuid4()

    mock_aim_service = MagicMock(spec=AIMServiceResource)
    mock_aim_service.metadata = K8sMetadata(
        name="test-aim-service",
        labels={WORKLOAD_ID_LABEL: str(aim_service_id)},
    )
    mock_aim_service.id = str(aim_service_id)
    mock_aim_service.spec = MagicMock(spec=AIMServiceSpec)
    mock_status = MagicMock(spec=AIMServiceStatusFields)
    mock_status.status = AIMServiceStatus.RUNNING
    # No display-name annotation and no resolved model -> fall back to metadata.name.
    mock_status.resolved_model = None
    mock_aim_service.status = mock_status

    result = await _process_aim_services_to_metrics(
        aim_services_k8s=[mock_aim_service],
        session=db_session,
        namespace_name="test-namespace",
        gpu_counts={},
        vram_usage={},
    )

    assert len(result) == 1
    metric = result[0]
    assert metric.display_name == "test-aim-service"


# Tests for _process_workloads_to_metrics
@pytest.mark.asyncio
async def test_process_workloads_to_metrics(db_session: AsyncSession) -> None:
    """Test _process_workloads_to_metrics converts workloads correctly."""
    # Create real workload in database
    workload = await create_workload(
        db_session,
        name="test-workload",
        display_name="Test Workload",
        namespace="test-namespace",
        workload_type=WorkloadType.FINE_TUNING,
        status=WorkloadStatus.RUNNING,
        submitter="test-user",
    )

    gpu_counts = {str(workload.id): 8}
    vram_usage = {str(workload.id): 48000.0}

    result = await _process_workloads_to_metrics(
        workloads_db=[workload],
        gpu_counts=gpu_counts,
        vram_usage=vram_usage,
    )

    assert len(result) == 1
    metric = result[0]
    assert metric.id == workload.id
    assert metric.name == "test-workload"
    assert metric.display_name == "Test Workload"
    assert metric.type == WorkloadType.FINE_TUNING
    assert metric.status == WorkloadStatus.RUNNING
    assert metric.gpu_count == 8
    assert metric.vram == 48000.0
    assert metric.created_by == "test-user"


@pytest.mark.asyncio
async def test_process_workloads_to_metrics_no_gpu_metrics(db_session: AsyncSession) -> None:
    """Test _process_workloads_to_metrics when GPU metrics are not available."""
    # Create real workload in database
    workload = await create_workload(
        db_session,
        name="test-workload",
        display_name="Test Workload",
        namespace="test-namespace",
        workload_type=WorkloadType.WORKSPACE,
        status=WorkloadStatus.PENDING,
        submitter="test-user",
    )

    result = await _process_workloads_to_metrics(
        workloads_db=[workload],
        gpu_counts={},
        vram_usage={},
    )

    assert len(result) == 1
    metric = result[0]
    assert metric.gpu_count is None
    assert metric.vram is None


@pytest.mark.asyncio
async def test_process_workloads_to_metrics_multiple_workloads(db_session: AsyncSession) -> None:
    """Test _process_workloads_to_metrics with multiple workloads."""
    # Create real workloads in database
    workloads = []
    for i in range(3):
        workload = await create_workload(
            db_session,
            name=f"workload-{i}",
            display_name=f"Workload {i}",
            namespace="test-namespace",
            workload_type=WorkloadType.INFERENCE,
            status=WorkloadStatus.RUNNING,
            submitter=f"user-{i}",
        )
        workloads.append(workload)

    result = await _process_workloads_to_metrics(
        workloads_db=workloads,
        gpu_counts={},
        vram_usage={},
    )

    assert len(result) == 3
    for i, metric in enumerate(result):
        assert metric.name == f"workload-{i}"
        assert metric.display_name == f"Workload {i}"
        assert metric.created_by == f"user-{i}"


@pytest.mark.asyncio
async def test_get_workload_metrics_paginated_prometheus_errors(
    mock_kube_client: MagicMock,
    db_session: AsyncSession,
    mock_prometheus_client: MagicMock,
) -> None:
    """Test get_workload_metrics_paginated when Prometheus queries fail."""
    namespace = MagicMock(spec=Namespace)
    namespace.name = "test-namespace"
    namespace.id = "test-namespace-id"

    # Create real workload in database
    workload = await create_workload(
        db_session,
        name="test-workload",
        display_name="Test Workload",
        namespace="test-namespace",
        workload_type=WorkloadType.INFERENCE,
        status=WorkloadStatus.RUNNING,
        submitter="test-user",
    )

    with (
        patch("app.workloads.service.list_aim_services", autospec=True) as mock_list_aims,
        patch("app.workloads.service.get_gpu_utilization_by_workload_in_namespace", autospec=True) as mock_gpu,
        patch("app.workloads.service.get_gpu_vram_by_workload_in_namespace", autospec=True) as mock_vram,
    ):
        mock_list_aims.return_value = []
        mock_gpu.side_effect = RuntimeError("Prometheus connection failed")
        mock_vram.return_value = {}

        with pytest.raises(RuntimeError, match="Prometheus connection failed"):
            await get_workload_metrics_paginated(
                kube_client=mock_kube_client,
                session=db_session,
                namespace=namespace,
                prometheus_client=mock_prometheus_client,
            )
