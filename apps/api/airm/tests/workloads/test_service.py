# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Workloads service tests."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from prometheus_api_client import PrometheusConnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.workloads.enums import JobStatus, WorkloadComponentKind, WorkloadStatus, WorkloadType
from app.workloads.messaging import (
    AutoDiscoveredWorkloadComponentMessage,
    DeleteWorkloadMessage,
    WorkloadComponentStatusMessage,
    WorkloadStatusMessage,
)
from app.workloads.repository import (
    get_workload_by_id_in_cluster,
    get_workload_component_by_id,
    get_workload_time_summary_by_workload_id_and_status,
)
from app.workloads.service import (
    create_and_submit_workload,
    extract_components_and_submit_workload,
    get_stats_for_workloads,
    get_stats_for_workloads_in_accessible_clusters,
    get_stats_for_workloads_in_project,
    get_status_stats_for_workloads_in_cluster,
    get_workload_details,
    get_workload_with_components,
    get_workloads_accessible_to_user,
    get_workloads_by_project,
    increment_workload_time_summary,
    register_auto_discovered_workload_component,
    submit_delete_workload,
    update_workload_component_status,
    update_workload_status,
)
from tests import factory  # type: ignore[attr-defined]

# Mock YAML content for testing
MOCK_YAML_CONTENT = """
apiVersion: v1
kind: Deployment
metadata:
    name: test-pod
    namespace: some-namespace
spec:
    containers:
    - name: test-container
      image: test-image
"""


@pytest.mark.asyncio
async def test_create_and_submit_workload_success(db_session: AsyncSession) -> None:
    """Test successful workload creation and submission."""
    env = await factory.create_basic_test_environment(db_session)

    project, quota = await factory.create_project_with_quota(
        db_session,
        env.cluster,
        project_name="test_project",
        quota_cpu=1000,
        quota_memory=1000000000,
        quota_storage=1000000000,
        quota_gpu=0,
    )

    creator = "test@example.com"
    workload_type = WorkloadType.INFERENCE

    manifest = [{"apiVersion": "v1", "kind": "Deployment", "metadata": {"name": "test-deployment"}}]
    token = "test-token"
    display_name = "Test Workload Display"
    mock_message_sender = AsyncMock()

    with patch("app.workloads.service.extract_components_and_submit_workload") as mock_extract:
        result = await create_and_submit_workload(
            db_session, project, manifest, creator, token, workload_type, display_name, mock_message_sender
        )
    mock_extract.assert_awaited_once()

    assert result is not None
    assert result.display_name == display_name
    assert result.type == workload_type
    assert result.project_id == project.id
    assert result.cluster_id == env.cluster.id

    assert await get_workload_by_id_in_cluster(db_session, result.id, result.cluster_id) is not None


@pytest.mark.asyncio
async def test_submit_delete_workload_success(db_session: AsyncSession) -> None:
    """Test successful workload deletion submission."""
    env = await factory.create_basic_test_environment(db_session)
    workload = await factory.create_workload(
        db_session, env.cluster, env.project, status=WorkloadStatus.RUNNING.value, display_name="Test Workload"
    )

    user = "test@example.com"
    mock_message_sender = AsyncMock()

    await submit_delete_workload(db_session, workload, user, mock_message_sender)

    mock_message_sender.enqueue.assert_called_once()

    call_args = mock_message_sender.enqueue.call_args
    cluster_id, message = call_args[0]
    assert cluster_id == env.cluster.id
    assert isinstance(message, DeleteWorkloadMessage)
    assert message.workload_id == workload.id

    await db_session.refresh(workload)
    assert workload.status == WorkloadStatus.DELETING.value


@pytest.mark.asyncio
async def test_submit_delete_workload_already_pending_deletion(db_session: AsyncSession) -> None:
    """Test deletion of workload already marked for deletion."""
    env = await factory.create_basic_test_environment(db_session)
    workload = await factory.create_workload(db_session, env.cluster, env.project, status=WorkloadStatus.DELETING.value)

    user = "test@example.com"
    mock_message_sender = AsyncMock()

    with pytest.raises(Exception, match="Workload is already marked for deletion"):
        await submit_delete_workload(db_session, workload, user, mock_message_sender)

    mock_message_sender.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_submit_delete_workload_already_deleted(db_session: AsyncSession) -> None:
    """Test deletion of workload already deleted."""
    env = await factory.create_basic_test_environment(db_session)
    workload = await factory.create_workload(db_session, env.cluster, env.project, status=WorkloadStatus.DELETED.value)

    user = "test@example.com"
    mock_message_sender = AsyncMock()

    with pytest.raises(Exception, match="Workload has already been deleted"):
        await submit_delete_workload(db_session, workload, user, mock_message_sender)

    mock_message_sender.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_update_workload_status_success(db_session: AsyncSession) -> None:
    """Test successful workload status update."""
    env = await factory.create_basic_test_environment(db_session)
    workload = await factory.create_workload(db_session, env.cluster, env.project, status=WorkloadStatus.PENDING.value)

    message = WorkloadStatusMessage(
        message_type="workload_status_update",
        workload_id=workload.id,
        status=JobStatus.RUNNING,
        updated_at=datetime.now(UTC),
        status_reason="Test update",
    )

    await update_workload_status(db_session, env.cluster, message)

    # Verify the workload status was updated in the database
    await db_session.refresh(workload)
    assert workload.status == WorkloadStatus.RUNNING.value
    assert workload.updated_at == message.updated_at


@pytest.mark.asyncio
async def test_update_workload_status_no_workload(db_session: AsyncSession) -> None:
    """Test workload status update when workload doesn't exist."""
    # Create real test environment but don't create the workload
    env = await factory.create_basic_test_environment(db_session)

    # Create status message for non-existent workload
    non_existent_workload_id = uuid4()
    message = WorkloadStatusMessage(
        message_type="workload_status_update",
        workload_id=non_existent_workload_id,
        status=JobStatus.RUNNING,
        updated_at=datetime.now(UTC),
        status_reason="Test update for non-existent workload",
    )

    # Update workload status should handle gracefully when workload not found
    # This should not raise an exception, just log a warning
    await update_workload_status(db_session, env.cluster, message)


@pytest.mark.asyncio
async def test_update_workload_status_no_updates(db_session: AsyncSession) -> None:
    """Test workload status update when workload timestamp is newer than message."""
    env = await factory.create_basic_test_environment(db_session)

    # Create workload with a recent timestamp
    future_time = datetime.now(UTC) + timedelta(hours=1)
    workload = await factory.create_workload(
        db_session, env.cluster, env.project, status=WorkloadStatus.PENDING.value, last_status_transition_at=future_time
    )

    # Set workload updated_at to future time manually
    workload.updated_at = future_time
    await db_session.flush()

    # Create status message with older timestamp
    past_time = datetime.now(UTC) - timedelta(hours=1)
    message = WorkloadStatusMessage(
        message_type="workload_status_update",
        workload_id=workload.id,
        status=JobStatus.RUNNING,
        updated_at=past_time,
        status_reason="Outdated status update",
    )

    # Update workload status with older timestamp
    await update_workload_status(db_session, env.cluster, message)

    # Verify the workload status was NOT updated (timestamp was older)
    await db_session.refresh(workload)
    assert workload.status == WorkloadStatus.PENDING.value  # Should remain unchanged
    assert workload.updated_at == future_time  # Should remain unchanged


@pytest.mark.asyncio
async def test_get_workloads_by_project_success(db_session: AsyncSession) -> None:
    """Test retrieving workloads by project with real database operations."""
    # Create real test environment with multiple workloads
    env = await factory.create_basic_test_environment(db_session)

    # Create workloads in the project
    workload1 = await factory.create_workload(db_session, env.cluster, env.project, display_name="Workload 1")
    workload2 = await factory.create_workload(db_session, env.cluster, env.project, display_name="Workload 2")

    # Create workload in different project to verify isolation
    other_project = await factory.create_project(db_session, env.cluster, name="Other Project")
    other_workload = await factory.create_workload(
        db_session, env.cluster, other_project, display_name="Other Workload"
    )

    # Test getting workloads by project
    result = await get_workloads_by_project(db_session, env.project.id)

    # Verify only project workloads are returned
    assert len(result.data) == 2
    workload_names = {w.display_name for w in result.data}
    assert "Workload 1" in workload_names
    assert "Workload 2" in workload_names
    assert "Other Workload" not in workload_names


@pytest.mark.asyncio
async def test_get_workloads_accessible_to_user_success(db_session: AsyncSession) -> None:
    """Test retrieving workloads accessible to user with real database operations."""
    # Create multi-organization environment for access control testing
    env = await factory.create_basic_test_environment(db_session)
    cluster2 = await factory.create_cluster(db_session, name="Cluster 2")
    project2 = await factory.create_project(db_session, cluster2, name="Project 2")

    # Create accessible workload
    accessible_workload = await factory.create_workload(
        db_session, env.cluster, env.project, display_name="Accessible Workload"
    )

    # Create inaccessible workload in different organization
    _ = await factory.create_workload(db_session, cluster2, project2, display_name="Inaccessible Workload")

    # Test getting workloads accessible to user
    result = await get_workloads_accessible_to_user(db_session, [env.project])

    # Verify only accessible workloads are returned
    assert len(result.data) == 1
    assert result.data[0].display_name == "Accessible Workload"
    assert result.data[0].id == accessible_workload.id


@pytest.mark.asyncio
async def test_update_workload_component_status_success(db_session: AsyncSession) -> None:
    """Test successful workload component status update with real database operations."""
    # Create real test environment with workload and components
    env = await factory.create_basic_test_environment(db_session)
    workload = await factory.create_workload(db_session, env.cluster, env.project, display_name="Test Workload")

    workload.last_status_transition_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()

    # Create workload component
    component = await factory.create_workload_component(
        db_session,
        workload,
        name="test-component",
        kind=WorkloadComponentKind.DEPLOYMENT,
        api_version="apps/v1",
        status="Pending",
    )

    # Create component status message
    message = WorkloadComponentStatusMessage(
        message_type="workload_component_status_update",
        id=component.id,
        name="test-component",
        kind=WorkloadComponentKind.DEPLOYMENT,
        api_version="apps/v1",
        workload_id=workload.id,
        status=JobStatus.RUNNING,
        status_reason="Running successfully",
        updated_at=datetime.now(UTC),
    )

    await update_workload_component_status(db_session, env.cluster, message)

    # Verify the workload component status was updated in the database
    await db_session.refresh(component)
    assert component.status == JobStatus.RUNNING.value

    await db_session.refresh(workload)
    assert workload.status == WorkloadStatus.RUNNING.value

    pending_summary = await get_workload_time_summary_by_workload_id_and_status(
        db_session, workload.id, WorkloadStatus.PENDING
    )
    assert pending_summary.total_elapsed_seconds == 3600


@pytest.mark.asyncio
async def test_get_stats_for_workloads_in_project_success(db_session: AsyncSession) -> None:
    """Test getting workload statistics for project with real database operations."""
    # Create real test environment with workloads in different states
    env = await factory.create_basic_test_environment(db_session)

    # Create workloads with different statuses
    running_workload = await factory.create_workload(
        db_session, env.cluster, env.project, status=WorkloadStatus.RUNNING.value, display_name="Running Workload"
    )
    pending_workload = await factory.create_workload(
        db_session, env.cluster, env.project, status=WorkloadStatus.PENDING.value, display_name="Pending Workload"
    )
    failed_workload = await factory.create_workload(
        db_session, env.cluster, env.project, status=WorkloadStatus.FAILED.value, display_name="Failed Workload"
    )

    # Test getting workload stats using real database operations
    result = await get_stats_for_workloads_in_project(db_session, env.project)

    # Verify returned stats match the created workloads
    status_counts = {sc.status: sc.count for sc in result.status_counts}
    assert status_counts.get(WorkloadStatus.RUNNING, 0) == 1
    assert status_counts.get(WorkloadStatus.PENDING, 0) == 1
    assert status_counts.get(WorkloadStatus.FAILED, 0) == 1
    assert status_counts.get(WorkloadStatus.COMPLETE, 0) == 0
    assert status_counts.get(WorkloadStatus.DELETED, 0) == 0
    assert status_counts.get(WorkloadStatus.DELETING, 0) == 0


@pytest.mark.asyncio
async def test_get_status_stats_for_workloads_in_cluster_success(db_session: AsyncSession) -> None:
    """Test getting workload status statistics for cluster with real database operations."""
    # Create real test environment
    env = await factory.create_basic_test_environment(db_session)

    # Create another project in the same cluster
    other_project = await factory.create_project(db_session, env.cluster, name="Other Project")

    # Create workloads with different statuses across multiple projects
    await factory.create_workload(
        db_session, env.cluster, env.project, status=WorkloadStatus.RUNNING.value, display_name="Running Workload 1"
    )
    await factory.create_workload(
        db_session, env.cluster, env.project, status=WorkloadStatus.PENDING.value, display_name="Pending Workload 1"
    )
    await factory.create_workload(
        db_session, env.cluster, env.project, status=WorkloadStatus.FAILED.value, display_name="Failed Workload 1"
    )
    await factory.create_workload(
        db_session, env.cluster, other_project, status=WorkloadStatus.RUNNING.value, display_name="Running Workload 2"
    )
    await factory.create_workload(
        db_session, env.cluster, other_project, status=WorkloadStatus.COMPLETE.value, display_name="Complete Workload"
    )

    # Test getting workload status stats for cluster
    result = await get_status_stats_for_workloads_in_cluster(db_session, env.cluster)

    # Verify returned stats match the created workloads across all projects
    assert result.name == env.cluster.name
    assert result.total_workloads == 5
    status_counts = {sc.status: sc.count for sc in result.status_counts}
    assert status_counts.get(WorkloadStatus.RUNNING, 0) == 2
    assert status_counts.get(WorkloadStatus.PENDING, 0) == 1
    assert status_counts.get(WorkloadStatus.FAILED, 0) == 1
    assert status_counts.get(WorkloadStatus.COMPLETE, 0) == 1
    assert status_counts.get(WorkloadStatus.DELETED, 0) == 0


@pytest.mark.asyncio
async def test_get_workload_with_components_success(db_session: AsyncSession) -> None:
    """Test retrieving workload with components with real database operations."""
    # Create real test environment with workload and components
    env = await factory.create_basic_test_environment(db_session)
    workload = await factory.create_workload(db_session, env.cluster, env.project, display_name="Test Workload")

    # Create multiple components
    component1 = await factory.create_workload_component(
        db_session, workload, name="deployment", kind=WorkloadComponentKind.DEPLOYMENT
    )
    component2 = await factory.create_workload_component(
        db_session, workload, name="service", kind=WorkloadComponentKind.SERVICE
    )

    # Test retrieving workload with components using real database operations
    result = await get_workload_with_components(db_session, workload)

    # Verify workload and components are returned
    assert result.id == workload.id
    assert result.display_name == "Test Workload"
    assert len(result.components) == 2

    # Verify component details
    component_names = {comp.name for comp in result.components}
    assert "deployment" in component_names
    assert "service" in component_names


@pytest.mark.asyncio
async def test_get_stats_for_workloads(db_session: AsyncSession) -> None:
    """Test getting workload statistics for organization."""
    # Create real test environment with multiple clusters
    env = await factory.create_basic_test_environment(db_session)

    # Create additional cluster in same organization
    cluster2 = await factory.create_cluster(db_session, name="Cluster 2")
    project2 = await factory.create_project(db_session, cluster2, name="Project 2")

    # Create workloads with different statuses across clusters in the organization
    running_workload1 = await factory.create_workload(
        db_session, env.cluster, env.project, status=WorkloadStatus.RUNNING.value
    )
    running_workload2 = await factory.create_workload(
        db_session, cluster2, project2, status=WorkloadStatus.RUNNING.value
    )
    pending_workload = await factory.create_workload(
        db_session, env.cluster, env.project, status=WorkloadStatus.PENDING.value
    )
    completed_workload = await factory.create_workload(
        db_session, cluster2, project2, status=WorkloadStatus.COMPLETE.value
    )

    result = await get_stats_for_workloads(db_session)

    # Only RUNNING and PENDING are included stats
    assert result.running_workloads_count == 2  # Two running workloads across clusters
    assert result.pending_workloads_count == 1  # One pending workload across clusters


@pytest.mark.asyncio
async def test_get_stats_for_workloads_in_accessible_clusters(db_session: AsyncSession) -> None:
    """Test getting workload statistics filtered by accessible clusters."""
    # Create clusters and projects
    env = await factory.create_basic_test_environment(db_session)
    cluster2 = await factory.create_cluster(db_session, name="Cluster 2")
    cluster3 = await factory.create_cluster(db_session, name="Cluster 3")
    project2 = await factory.create_project(db_session, cluster2, name="Project 2")
    project3 = await factory.create_project(db_session, cluster3, name="Project 3")

    # Create workloads in accessible clusters
    await factory.create_workload(db_session, env.cluster, env.project, status=WorkloadStatus.RUNNING.value)
    await factory.create_workload(db_session, env.cluster, env.project, status=WorkloadStatus.RUNNING.value)
    await factory.create_workload(db_session, cluster2, project2, status=WorkloadStatus.PENDING.value)

    # Create workloads in non-accessible cluster
    await factory.create_workload(db_session, cluster3, project3, status=WorkloadStatus.RUNNING.value)
    await factory.create_workload(db_session, cluster3, project3, status=WorkloadStatus.PENDING.value)

    # User only has access to env.cluster and cluster2
    accessible_clusters = [env.cluster, cluster2]
    result = await get_stats_for_workloads_in_accessible_clusters(db_session, accessible_clusters)

    # Only workloads in accessible clusters should be counted
    assert result.running_workloads_count == 2
    assert result.pending_workloads_count == 1


@pytest.mark.asyncio
async def test_increment_workload_time_summary_new(db_session: AsyncSession) -> None:
    """Test incrementing workload time summary for new entry with real database operations."""
    env = await factory.create_basic_test_environment(db_session)
    workload = await factory.create_workload(db_session, env.cluster, env.project, display_name="Test Workload")

    status = WorkloadStatus.RUNNING
    increment_duration = timedelta(seconds=60)

    # Test incrementing workload time summary using real database operations
    await increment_workload_time_summary(db_session, workload.id, status, increment_duration)

    # Verify the time summary was created in the database
    time_summary = await get_workload_time_summary_by_workload_id_and_status(db_session, workload.id, status)
    assert time_summary is not None
    assert time_summary.workload_id == workload.id
    assert time_summary.status == status.value
    assert time_summary.total_elapsed_seconds == int(increment_duration.total_seconds())


@pytest.mark.asyncio
async def test_increment_workload_time_summary_existing(db_session: AsyncSession) -> None:
    """Test incrementing workload time summary for existing entry."""
    # Create real test environment with workload and existing time summary
    env = await factory.create_basic_test_environment(db_session)
    workload = await factory.create_workload(db_session, env.cluster, env.project, display_name="Test Workload")

    # Create existing time summary
    status = WorkloadStatus.RUNNING.value
    initial_seconds = 3600  # 1 hour
    time_summary = await factory.create_workload_time_summary(
        db_session, workload, status=status, total_elapsed_seconds=initial_seconds
    )

    # Test incrementing existing workload time summary
    increment_duration = timedelta(seconds=1800)  # 30 minutes
    await increment_workload_time_summary(db_session, workload.id, status, increment_duration)

    # Verify the time summary was updated in the database
    updated_summary = await get_workload_time_summary_by_workload_id_and_status(db_session, workload.id, status)

    assert updated_summary is not None
    assert updated_summary.id == time_summary.id  # Same record
    assert updated_summary.total_elapsed_seconds == initial_seconds + 1800  # Original + increment
    assert updated_summary.workload_id == workload.id
    assert updated_summary.status == status


@pytest.mark.asyncio
async def test_extract_components_and_submit_workload(db_session: AsyncSession) -> None:
    """Test detailed component extraction and submission flow."""
    env = await factory.create_basic_test_environment(db_session)
    workload = await factory.create_workload(db_session, env.cluster, env.project, display_name="Test Workload")

    # Create manifest with multiple components
    manifest = [
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "test-deployment", "namespace": "default"},
            "spec": {"replicas": 1},
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "test-service", "namespace": "default"},
            "spec": {"ports": [{"port": 80}]},
        },
    ]

    creator = "test@example.com"
    token = "test-token"
    mock_message_sender = AsyncMock()

    await extract_components_and_submit_workload(
        db_session, workload, env.project, manifest, creator, token, mock_message_sender
    )

    # Verify message submission
    mock_message_sender.enqueue.assert_called_once()
    call_args = mock_message_sender.enqueue.call_args[0]
    cluster_id, message = call_args
    assert cluster_id == env.project.cluster_id
    assert message.message_type == "workload"
    assert message.workload_id == workload.id
    assert message.user_token == token

    workload_with_components = await get_workload_with_components(db_session, workload)
    components = workload_with_components.components
    service = next((c for c in components if c.kind == WorkloadComponentKind.SERVICE), None)
    deployment = next((c for c in components if c.kind == WorkloadComponentKind.DEPLOYMENT), None)

    assert service is not None
    assert deployment is not None

    assert (
        message.manifest
        == f"""apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    airm.silogen.ai/component-id: {deployment.id}
    airm.silogen.ai/project-id: {workload.project_id}
    airm.silogen.ai/workload-id: {workload.id}
    kueue.x-k8s.io/queue-name: test-project
  name: test-deployment
  namespace: test-project
spec:
  replicas: 1
  template:
    metadata:
      labels:
        airm.silogen.ai/component-id: {deployment.id}
        airm.silogen.ai/project-id: {workload.project_id}
        airm.silogen.ai/workload-id: {workload.id}
---
apiVersion: v1
kind: Service
metadata:
  labels:
    airm.silogen.ai/component-id: {service.id}
    airm.silogen.ai/project-id: {workload.project_id}
    airm.silogen.ai/workload-id: {workload.id}
  name: test-service
  namespace: test-project
spec:
  ports:
  - port: 80
"""
    )


@pytest.mark.asyncio
async def test_register_auto_discovered_workload_component_no_workload(db_session: AsyncSession) -> None:
    env = await factory.create_basic_test_environment(db_session)

    workload_id = uuid4()
    component_id = uuid4()
    message = AutoDiscoveredWorkloadComponentMessage(
        message_type="auto_discovered_workload_component",
        workload_id=workload_id,
        component_id=component_id,
        project_id=env.project.id,
        name="test-component",
        submitter="test-submitter",
        kind=WorkloadComponentKind.DEPLOYMENT,
        api_version="apps/v1",
        updated_at=datetime.now(UTC),
    )

    await register_auto_discovered_workload_component(db_session, env.cluster, message)

    workload = await get_workload_by_id_in_cluster(db_session, workload_id, env.cluster.id)
    assert workload.id == workload_id
    assert workload.created_by == "test-submitter"

    component = await get_workload_component_by_id(db_session, component_id, workload.id)
    assert component.id == component_id
    assert component.created_by == "test-submitter"


@pytest.mark.asyncio
# owner_first=False is the bug this fixes: a child names the workload and the later owner must
# reclaim it. owner_first=True is a control: when the owner arrives first the name is already
# correct, so the later child message must NOT clobber it.
@pytest.mark.parametrize("owner_first", [False, True])
@pytest.mark.parametrize(
    ("child_name", "child_kind", "owner_name", "owner_kind"),
    [
        (
            "test-longrun-abc123-76d9cff8c",
            WorkloadComponentKind.REPLICA_SET,
            "test-longrun-abc123",
            WorkloadComponentKind.DEPLOYMENT,
        ),
        (
            "test-longrun-abc123-76d9cff8c-x7k9p",
            WorkloadComponentKind.POD,
            "test-longrun-abc123",
            WorkloadComponentKind.DEPLOYMENT,
        ),
        (
            "test-longrun-abc123-b",
            WorkloadComponentKind.REPLICA_SET,
            "test-longrun-abc123",
            WorkloadComponentKind.DEPLOYMENT,
        ),
        (
            "test-longrun-abc123-76d9cff8c-x7k9p",
            WorkloadComponentKind.POD,
            "test-longrun-abc123-76d9cff8c",
            WorkloadComponentKind.REPLICA_SET,
        ),
        # Job- and DaemonSet-owned Pods carry the same apiserver 5-char suffix as a ReplicaSet's Pod.
        (
            "test-longrun-abc123-x7k9p",
            WorkloadComponentKind.POD,
            "test-longrun-abc123",
            WorkloadComponentKind.JOB,
        ),
        (
            "test-longrun-abc123-x7k9p",
            WorkloadComponentKind.POD,
            "test-longrun-abc123",
            WorkloadComponentKind.DAEMON_SET,
        ),
    ],
)
async def test_auto_discovered_workload_is_named_after_its_owner_whatever_arrives_first(
    child_name: str,
    child_kind: WorkloadComponentKind,
    owner_name: str,
    owner_kind: WorkloadComponentKind,
    owner_first: bool,
    db_session: AsyncSession,
) -> None:
    """An owner names the workload regardless of which component is discovered first.

    The agent publishes an owner and its hash-suffixed children concurrently with one shared
    component id, so without deterministic naming the workload keeps whichever name won the
    race and users see a hash-suffixed child name instead of what they deployed.
    """
    env = await factory.create_basic_test_environment(db_session)

    workload_id = uuid4()
    component_id = uuid4()

    def _message(name: str, kind: WorkloadComponentKind) -> AutoDiscoveredWorkloadComponentMessage:
        return AutoDiscoveredWorkloadComponentMessage(
            message_type="auto_discovered_workload_component",
            workload_id=workload_id,
            component_id=component_id,
            project_id=env.project.id,
            name=name,
            submitter="test-submitter",
            kind=kind,
            api_version="apps/v1",
            updated_at=datetime.now(UTC),
        )

    first_message = _message(owner_name, owner_kind) if owner_first else _message(child_name, child_kind)
    await register_auto_discovered_workload_component(db_session, env.cluster, first_message)
    workload = await get_workload_by_id_in_cluster(db_session, workload_id, env.cluster.id)
    status_clock_before_second = workload.updated_at

    second_message = _message(child_name, child_kind) if owner_first else _message(owner_name, owner_kind)
    second_message.updated_at = status_clock_before_second + timedelta(seconds=2)
    await register_auto_discovered_workload_component(db_session, env.cluster, second_message)

    assert workload.display_name == owner_name
    assert workload.updated_at == status_clock_before_second
    assert workload.updated_by == ("test-submitter" if owner_first else "system")

    status_message = WorkloadStatusMessage(
        message_type="workload_status_update",
        workload_id=workload_id,
        status=WorkloadStatus.RUNNING,
        updated_at=status_clock_before_second + timedelta(seconds=1),
        status_reason=None,
    )
    await update_workload_status(db_session, env.cluster, status_message)
    await db_session.refresh(workload)
    assert workload.status == WorkloadStatus.RUNNING
    assert workload.updated_at == status_message.updated_at


@pytest.mark.asyncio
@pytest.mark.parametrize("discovery_order", [(0, 1, 2), (0, 2, 1), (1, 0, 2)])
async def test_auto_discovered_workload_uses_top_owner_across_three_discovery_levels(
    discovery_order: tuple[int, int, int],
    db_session: AsyncSession,
) -> None:
    """A workload resolves to its Deployment after child-first three-level discovery."""
    env = await factory.create_basic_test_environment(db_session)
    workload_id = uuid4()
    component_id = uuid4()

    components = (
        ("test-longrun-abc123-76d9cff8c-x7k9p", WorkloadComponentKind.POD),
        ("test-longrun-abc123-76d9cff8c", WorkloadComponentKind.REPLICA_SET),
        ("test-longrun-abc123", WorkloadComponentKind.DEPLOYMENT),
    )
    for index in discovery_order:
        name, kind = components[index]
        await register_auto_discovered_workload_component(
            db_session,
            env.cluster,
            AutoDiscoveredWorkloadComponentMessage(
                message_type="auto_discovered_workload_component",
                workload_id=workload_id,
                component_id=component_id,
                project_id=env.project.id,
                name=name,
                submitter="test-submitter",
                kind=kind,
                api_version="apps/v1",
                updated_at=datetime.now(UTC),
            ),
        )

    workload = await get_workload_by_id_in_cluster(db_session, workload_id, env.cluster.id)
    assert workload.display_name == "test-longrun-abc123"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("display_name", "component_name", "component_kind", "prior_component_kind", "prior_component_name"),
    [
        # No display name yet: nothing to preserve or clobber.
        (None, "totally-different", WorkloadComponentKind.POD, None, None),
        # A submitter-chosen name unrelated to any component.
        ("a-name-someone-chose", "totally-different", WorkloadComponentKind.POD, None, None),
        # Prefix match, but "prod" has a vowel so it is not an apiserver-generated suffix: the
        # shape guard vetoes the rename before any component is consulted.
        ("myapp-prod", "myapp", WorkloadComponentKind.DEPLOYMENT, None, None),
        # Generated-looking suffix but no component ever recorded that name: the lineage guard
        # vetoes over an empty component set.
        ("myapp-76d9cff8c", "myapp", WorkloadComponentKind.DEPLOYMENT, None, None),
        # Generated-looking suffix and a Pod component exists, but its name is not a descendant
        # of the display name, so lineage is still absent and the name is kept.
        (
            "myapp-76d9cff8c",
            "myapp",
            WorkloadComponentKind.DEPLOYMENT,
            WorkloadComponentKind.POD,
            "unrelated-workload-x7k9p",
        ),
        # A Pod message is not an owning kind, so it can never rename its owner.
        ("myapp-76d9cff8c", "myapp", WorkloadComponentKind.POD, None, None),
    ],
)
async def test_auto_discovered_workload_keeps_an_unrelated_display_name(
    display_name: str | None,
    component_name: str,
    component_kind: WorkloadComponentKind,
    prior_component_kind: WorkloadComponentKind | None,
    prior_component_name: str | None,
    db_session: AsyncSession,
) -> None:
    """A missing or submitter-chosen display name is left alone during component discovery."""
    env = await factory.create_basic_test_environment(db_session)

    workload_id = uuid4()
    workload = await factory.create_workload(
        db_session, env.cluster, env.project, id=workload_id, display_name=display_name
    )
    if prior_component_kind:
        await factory.create_workload_component(
            db_session,
            workload,
            name=prior_component_name,
            kind=prior_component_kind,
            api_version="apps/v1",
        )
    await register_auto_discovered_workload_component(
        db_session,
        env.cluster,
        AutoDiscoveredWorkloadComponentMessage(
            message_type="auto_discovered_workload_component",
            workload_id=workload_id,
            component_id=uuid4(),
            project_id=env.project.id,
            name=component_name,
            submitter="test-submitter",
            kind=component_kind,
            api_version="apps/v1",
            updated_at=datetime.now(UTC),
        ),
    )

    workload = await get_workload_by_id_in_cluster(db_session, workload_id, env.cluster.id)
    assert workload.display_name == display_name


@pytest.mark.asyncio
async def test_register_auto_discovered_workload_component_workload_exists(db_session: AsyncSession) -> None:
    env = await factory.create_basic_test_environment(db_session)
    workload = await factory.create_workload(db_session, env.cluster, env.project, display_name="Test Workload")

    component_id = uuid4()
    message = AutoDiscoveredWorkloadComponentMessage(
        message_type="auto_discovered_workload_component",
        workload_id=workload.id,
        component_id=component_id,
        project_id=env.project.id,
        name="test-component",
        kind=WorkloadComponentKind.DEPLOYMENT,
        api_version="apps/v1",
        updated_at=datetime.now(UTC),
    )

    await register_auto_discovered_workload_component(db_session, env.cluster, message)

    workload = await get_workload_by_id_in_cluster(db_session, workload.id, env.cluster.id)
    assert workload.id == workload.id

    component = await get_workload_component_by_id(db_session, component_id, workload.id)
    assert component.id == component_id


@pytest.mark.asyncio
async def test_register_auto_discovered_workload_component_with_workload_type(db_session: AsyncSession) -> None:
    """Test that workload type from label is used when auto-discovering workload."""
    env = await factory.create_basic_test_environment(db_session)

    workload_id = uuid4()
    component_id = uuid4()
    message = AutoDiscoveredWorkloadComponentMessage(
        message_type="auto_discovered_workload_component",
        workload_id=workload_id,
        component_id=component_id,
        project_id=env.project.id,
        name="test-inference-workload",
        submitter="test-user",
        kind=WorkloadComponentKind.DEPLOYMENT,
        api_version="apps/v1",
        updated_at=datetime.now(UTC),
        workload_type=WorkloadType.INFERENCE,
    )

    await register_auto_discovered_workload_component(db_session, env.cluster, message)

    workload = await get_workload_by_id_in_cluster(db_session, workload_id, env.cluster.id)
    assert workload.id == workload_id
    assert workload.type == WorkloadType.INFERENCE
    assert workload.created_by == "test-user"

    component = await get_workload_component_by_id(db_session, component_id, workload.id)
    assert component.id == component_id


@pytest.mark.asyncio
async def test_register_auto_discovered_workload_component_defaults_to_custom(db_session: AsyncSession) -> None:
    """Test that workload type defaults to CUSTOM when not provided in label."""
    env = await factory.create_basic_test_environment(db_session)

    workload_id = uuid4()
    component_id = uuid4()
    message = AutoDiscoveredWorkloadComponentMessage(
        message_type="auto_discovered_workload_component",
        workload_id=workload_id,
        component_id=component_id,
        project_id=env.project.id,
        name="test-custom-workload",
        submitter="test-user",
        kind=WorkloadComponentKind.JOB,
        api_version="batch/v1",
        updated_at=datetime.now(UTC),
        # workload_type not provided - should use default CUSTOM
    )

    await register_auto_discovered_workload_component(db_session, env.cluster, message)

    workload = await get_workload_by_id_in_cluster(db_session, workload_id, env.cluster.id)
    assert workload.id == workload_id
    assert workload.type == WorkloadType.CUSTOM

    component = await get_workload_component_by_id(db_session, component_id, workload.id)
    assert component.id == component_id


@pytest.mark.asyncio
@patch("app.workloads.service.get_gpu_and_node_counts_for_workload", new_callable=AsyncMock, return_value=(2, 1))
async def test_get_workload_details_basic(mock_get_gpu_and_node: AsyncMock, db_session: AsyncSession) -> None:
    """Test get_workload_details returns correct static fields."""
    env = await factory.create_basic_test_environment(db_session)
    workload = await factory.create_workload(
        db_session,
        env.cluster,
        env.project,
        status=WorkloadStatus.COMPLETE.value,
        display_name="My Workload",
    )

    await factory.create_workload_time_summary(
        db_session, workload, status=WorkloadStatus.PENDING.value, total_elapsed_seconds=120
    )
    await factory.create_workload_time_summary(
        db_session, workload, status=WorkloadStatus.RUNNING.value, total_elapsed_seconds=3600
    )

    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    result = await get_workload_details(db_session, workload, prometheus_client=prometheus_client_mock)

    assert result.name == "My Workload"
    assert result.workload_id == workload.id
    assert result.cluster_id == env.cluster.id
    assert result.cluster_name == env.cluster.name
    assert result.gpu_devices_in_use == 2
    assert result.nodes_in_use == 1
    assert result.queue_time == 120
    assert result.running_time == 3600
    assert result.created_at is not None
    assert result.updated_at is not None


@pytest.mark.asyncio
@patch("app.workloads.service.get_gpu_and_node_counts_for_workload", new_callable=AsyncMock, return_value=(0, 0))
async def test_get_workload_details_running_time_includes_live_delta(
    mock_get_gpu_and_node: AsyncMock, db_session: AsyncSession
) -> None:
    """Test that running_time adds live elapsed time for a currently running workload."""
    env = await factory.create_basic_test_environment(db_session)
    workload = await factory.create_workload(
        db_session,
        env.cluster,
        env.project,
        status=WorkloadStatus.RUNNING.value,
        last_status_transition_at=datetime.now(UTC) - timedelta(minutes=10),
    )

    await factory.create_workload_time_summary(
        db_session, workload, status=WorkloadStatus.RUNNING.value, total_elapsed_seconds=100
    )

    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    result = await get_workload_details(db_session, workload, prometheus_client=prometheus_client_mock)

    # 100 stored + ~600s from 10 min ago; allow for slight clock/rounding variance
    assert result.running_time >= 698


@pytest.mark.asyncio
@patch("app.workloads.service.get_gpu_and_node_counts_for_workload", new_callable=AsyncMock, return_value=(0, 0))
async def test_get_workload_details_no_time_summaries(
    mock_get_gpu_and_node: AsyncMock, db_session: AsyncSession
) -> None:
    """Test get_workload_details defaults to 0 when no time summaries exist."""
    env = await factory.create_basic_test_environment(db_session)
    workload = await factory.create_workload(db_session, env.cluster, env.project, status=WorkloadStatus.PENDING.value)

    prometheus_client_mock = AsyncMock(spec=PrometheusConnect)
    result = await get_workload_details(db_session, workload, prometheus_client=prometheus_client_mock)

    assert result.queue_time == 0
    assert result.running_time == 0
