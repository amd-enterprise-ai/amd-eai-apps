# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from keycloak import KeycloakAdmin
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ConflictException, NotFoundException, UnhealthyException, ValidationException
from app.messaging.sender import MessageSender
from app.namespaces.enums import NamespaceStatus
from app.namespaces.repository import get_namespace_by_project_and_cluster
from app.projects.enums import GpuPreemptionPolicy, ProjectStatus
from app.projects.repository import get_project_by_id, get_project_by_name
from app.projects.schemas import (
    GpuPreemptionConfig,
    ProjectCreate,
    ProjectEdit,
    Projects,
    ProjectsWithResourceAllocation,
)
from app.projects.service import (
    add_users_to_project_and_keycloak_group,
    create_project,
    delete_project_if_components_deleted,
    delete_project_with_cleanup,
    get_projects_with_resource_allocation,
    get_projects_with_resource_allocation_in_clusters,
    get_submittable_projects,
    remove_user_from_project_and_keycloak_group,
    submit_delete_project,
    update_project,
    update_project_status_from_components,
)
from app.quotas.enums import QuotaStatus
from app.quotas.schemas import QuotaBase
from app.secrets.enums import ProjectSecretStatus, SecretScope, SecretStatus
from app.secrets.repository import get_secret
from app.storages.enums import ProjectStorageStatus, StorageStatus
from app.storages.repository import get_storage_by_id
from tests import factory  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_create_project(db_session: AsyncSession) -> None:
    """Test project creation with real database operations."""
    cluster = await factory.create_cluster(db_session, name="TestCluster")
    cluster.last_heartbeat_at = datetime.now(tz=UTC)
    await db_session.flush()

    project_data = ProjectCreate(
        name="test-project",
        description="A test project",
        cluster_id=cluster.id,
        quota=QuotaBase(
            cpu_milli_cores=0,
            memory_bytes=0,
            ephemeral_storage_bytes=0,
            gpu_count=0,
        ),
    )
    creator = "test_creator"

    kc_admin = AsyncMock(spec=KeycloakAdmin)
    mock_message_sender = AsyncMock(spec=MessageSender)

    with patch("app.projects.service.create_group", return_value="1fa3c3b8-31af-1413-3143-1234567890ab"):
        project = await create_project(kc_admin, db_session, mock_message_sender, cluster, project_data, creator)

    assert project.name == "test-project"
    assert project.description == "A test project"
    assert project.keycloak_group_id == "1fa3c3b8-31af-1413-3143-1234567890ab"
    assert project.quota.cpu_milli_cores == 0

    namespace = await get_namespace_by_project_and_cluster(db_session, project.id, cluster.id)
    assert namespace.name == "test-project"

    assert mock_message_sender.enqueue.call_count == 2

    stored_project = await get_project_by_name(db_session, "test-project")
    assert stored_project is not None
    assert stored_project.name == "test-project"


@pytest.mark.asyncio
async def test_create_project_with_gpu_preemption(db_session: AsyncSession) -> None:
    """Test that gpu preemption fields are persisted during project creation."""
    cluster = await factory.create_cluster(db_session, name="PreemptCluster")
    cluster.last_heartbeat_at = datetime.now(tz=UTC)
    await db_session.flush()

    project_data = ProjectCreate(
        name="preempt-project",
        description="A project with GPU preemption",
        cluster_id=cluster.id,
        quota=QuotaBase(
            cpu_milli_cores=0,
            memory_bytes=0,
            ephemeral_storage_bytes=0,
            gpu_count=0,
        ),
        gpu_preemption=GpuPreemptionConfig(
            enabled=True,
            threshold=75,
            grace_period=1800,
            policy=GpuPreemptionPolicy.ALWAYS,
        ),
    )

    kc_admin = AsyncMock(spec=KeycloakAdmin)
    mock_message_sender = AsyncMock(spec=MessageSender)

    with patch("app.projects.service.create_group", return_value="aabbccdd-1234-5678-9abc-def012345678"):
        project = await create_project(kc_admin, db_session, mock_message_sender, cluster, project_data, "creator")

    assert project.gpu_preemption_enabled is True
    assert project.gpu_preemption_threshold == 75
    assert project.gpu_preemption_grace_period == 1800
    assert project.gpu_preemption_policy == GpuPreemptionPolicy.ALWAYS

    stored = await get_project_by_name(db_session, "preempt-project")
    assert stored is not None
    assert stored.gpu_preemption_enabled is True
    assert stored.gpu_preemption_policy == GpuPreemptionPolicy.ALWAYS


@pytest.mark.asyncio
async def test_create_project_unhealthy_cluster(db_session: AsyncSession) -> None:
    """Test that creating a project for an unhealthy cluster raises UnhealthyException."""
    # Create cluster with old heartbeat (unhealthy)
    cluster = await factory.create_cluster(
        db_session,
        name="TestCluster",
        workbench_base_url="https://test-cluster.example.com",
    )
    cluster.last_heartbeat_at = datetime.now(tz=UTC) - timedelta(10)
    await db_session.flush()

    project_data = ProjectCreate(
        name="test-project",
        description="A test project",
        cluster_id=cluster.id,
        quota=QuotaBase(
            cpu_milli_cores=0,
            memory_bytes=0,
            ephemeral_storage_bytes=0,
            gpu_count=0,
        ),
    )
    creator = "test_creator"

    mock_message_sender = AsyncMock(spec=MessageSender)
    with pytest.raises(UnhealthyException) as e:
        await create_project(
            AsyncMock(spec=KeycloakAdmin),
            db_session,
            mock_message_sender,
            cluster,
            project_data,
            creator,
        )

    assert "Project cannot be created for an unhealthy cluster." in str(e.value)
    mock_message_sender.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_create_project_duplicate_name(db_session: AsyncSession) -> None:
    """Test creating project with duplicate name raises ConflictException."""
    cluster = await factory.create_cluster(db_session, name="TestCluster")
    cluster.last_heartbeat_at = datetime.now(tz=UTC)
    await db_session.flush()
    await factory.create_project(db_session, cluster, name="test-project")

    project_data = ProjectCreate(
        name="test-project",
        description="A test project",
        cluster_id=cluster.id,
        quota=QuotaBase(
            cpu_milli_cores=0,
            memory_bytes=0,
            ephemeral_storage_bytes=0,
            gpu_count=0,
        ),
    )
    creator = "test_creator"

    kc_admin = AsyncMock(spec=KeycloakAdmin)
    mock_message_sender = AsyncMock(spec=MessageSender)

    with pytest.raises(ConflictException) as e:
        await create_project(kc_admin, db_session, mock_message_sender, cluster, project_data, creator)

    assert "Project with name test-project already exists." in str(e.value)
    mock_message_sender.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_create_project_too_many_projects(db_session: AsyncSession) -> None:
    """Test that creating a project when cluster has 999 projects raises ValidationException."""
    cluster = await factory.create_cluster(db_session, name="TestCluster")
    cluster.last_heartbeat_at = datetime.now(tz=UTC)
    await db_session.flush()

    # Create 999 real projects to test the actual limit
    for i in range(999):
        await factory.create_project(db_session, cluster, name=f"existing-project-{i}")

    project_data = ProjectCreate(
        name="test-project",
        description="A test project",
        cluster_id=cluster.id,
        quota=QuotaBase(
            cpu_milli_cores=0,
            memory_bytes=0,
            ephemeral_storage_bytes=0,
            gpu_count=0,
        ),
    )
    creator = "test_creator"

    mock_message_sender = AsyncMock(spec=MessageSender)
    with pytest.raises(ValidationException) as e:
        await create_project(
            AsyncMock(spec=KeycloakAdmin), db_session, mock_message_sender, cluster, project_data, creator
        )

    assert "Maximum of 999 projects per cluster exceeded." in str(e.value)
    mock_message_sender.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_create_project_namespace_collision_with_unmanaged(db_session: AsyncSession) -> None:
    """Test that creating a project fails when an unmanaged namespace with the same name exists."""
    env = await factory.create_basic_test_environment(db_session)
    cluster = env.cluster
    cluster.last_heartbeat_at = datetime.now(tz=UTC)
    await db_session.flush()

    # Create unmanaged namespace (project_id=None) using factory
    await factory.create_namespace(
        db_session,
        cluster=cluster,
        project_id=None,  # Unmanaged
        name="external-namespace",
        status=NamespaceStatus.ACTIVE,
        creator="system",
    )

    project_data = ProjectCreate(
        name="external-namespace",
        description="A test project",
        cluster_id=cluster.id,
        quota=QuotaBase(
            cpu_milli_cores=0,
            memory_bytes=0,
            ephemeral_storage_bytes=0,
            gpu_count=0,
        ),
    )

    mock_message_sender = AsyncMock(spec=MessageSender)
    with pytest.raises(ConflictException) as e:
        await create_project(
            AsyncMock(spec=KeycloakAdmin), db_session, mock_message_sender, cluster, project_data, "test_creator"
        )

    # Error message for unmanaged namespace collision
    assert "already exists in cluster" in str(e.value)
    assert "'external-namespace'" in str(e.value)
    assert cluster.name in str(e.value)  # Verify cluster name is in error message
    mock_message_sender.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_create_project_namespace_collision_with_managed(db_session: AsyncSession) -> None:
    """Test that creating a project fails when a managed namespace with the same name exists."""
    env = await factory.create_basic_test_environment(db_session)
    cluster = env.cluster
    cluster.last_heartbeat_at = datetime.now(tz=UTC)
    await db_session.flush()

    # Create another project with a managed namespace
    other_project = await factory.create_project(db_session, cluster, name="existing-project")
    await factory.create_namespace(
        db_session,
        cluster=cluster,
        project_id=other_project.id,  # Managed namespace
        name="existing-project",
        status=NamespaceStatus.ACTIVE,
        creator="user@example.com",
    )

    project_data = ProjectCreate(
        name="existing-project",
        description="A test project",
        cluster_id=cluster.id,
        quota=QuotaBase(
            cpu_milli_cores=0,
            memory_bytes=0,
            ephemeral_storage_bytes=0,
            gpu_count=10,
        ),
    )

    mock_message_sender = AsyncMock(spec=MessageSender)
    with pytest.raises(ConflictException) as e:
        await create_project(
            AsyncMock(spec=KeycloakAdmin), db_session, mock_message_sender, cluster, project_data, "test_creator"
        )

    # Error message for duplicate project name (caught before namespace collision check)
    assert "Project with name existing-project already exists." in str(e.value)
    mock_message_sender.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_create_project_refuses_a_name_sharing_storage_with_a_legacy_namespace(
    db_session: AsyncSession,
) -> None:
    """A namespace that predates the naming rule still holds the prefix a compliant name resolves to.

    'data--science' could not be created today, but rows created before the rule existed are not
    retroactively renamed, and its object-storage prefix is 'data-science/'. A new project named
    'data-science' passes name validation and is uniquely named, yet would write into and read
    from that same prefix — so uniqueness has to be judged on the prefix, not on the name.
    """
    env = await factory.create_basic_test_environment(db_session)
    cluster = env.cluster
    cluster.last_heartbeat_at = datetime.now(tz=UTC)
    await db_session.flush()

    await factory.create_namespace(
        db_session,
        cluster=cluster,
        project_id=None,
        name="data--science",
        status=NamespaceStatus.ACTIVE,
        creator="system",
    )

    project_data = ProjectCreate(
        name="data-science",
        description="A test project",
        cluster_id=cluster.id,
        quota=QuotaBase(cpu_milli_cores=0, memory_bytes=0, ephemeral_storage_bytes=0, gpu_count=0),
    )

    mock_message_sender = AsyncMock(spec=MessageSender)
    with pytest.raises(ConflictException) as e:
        await create_project(
            AsyncMock(spec=KeycloakAdmin), db_session, mock_message_sender, cluster, project_data, "test_creator"
        )

    assert "would share object storage with 'data-science'" in str(e.value)
    assert "'data--science'" in str(e.value)
    mock_message_sender.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_create_project_allows_a_name_that_resolves_to_its_own_storage_prefix(db_session: AsyncSession) -> None:
    """The prefix check must only refuse real sharing — a distinct prefix is not a collision.

    'data--science' folds to 'data-science/', so 'data-analytics' has to remain creatable
    alongside it; a check that compared names loosely rather than by resolved prefix would
    block unrelated projects.
    """
    env = await factory.create_basic_test_environment(db_session)
    cluster = env.cluster
    cluster.last_heartbeat_at = datetime.now(tz=UTC)
    await db_session.flush()

    await factory.create_namespace(
        db_session,
        cluster=cluster,
        project_id=None,
        name="data--science",
        status=NamespaceStatus.ACTIVE,
        creator="system",
    )

    project_data = ProjectCreate(
        name="data-analytics",
        description="A test project",
        cluster_id=cluster.id,
        quota=QuotaBase(cpu_milli_cores=0, memory_bytes=0, ephemeral_storage_bytes=0, gpu_count=0),
    )

    with patch("app.projects.service.create_group", return_value="1fa3c3b8-31af-1413-3143-1234567890ab"):
        created = await create_project(
            AsyncMock(spec=KeycloakAdmin),
            db_session,
            AsyncMock(spec=MessageSender),
            cluster,
            project_data,
            "test_creator",
        )

    assert created.name == "data-analytics"


@pytest.mark.asyncio
async def test_update_project(db_session: AsyncSession) -> None:
    env = await factory.create_basic_test_environment(db_session, create_project_quota=True)
    await factory.create_cluster_node(
        db_session,
        env.cluster,
        cpu_milli_cores=16000,
        memory_bytes=64 * 1024**3,
        ephemeral_storage_bytes=200 * 1024**3,
        gpu_count=10,
    )

    project_data = ProjectEdit(
        description="A new project description",
        quota=QuotaBase(
            cpu_milli_cores=0,
            memory_bytes=0,
            ephemeral_storage_bytes=0,
            gpu_count=10,
        ),
        gpu_preemption=GpuPreemptionConfig(),
    )

    mock_message_sender = AsyncMock(spec=MessageSender)

    project = await update_project(db_session, mock_message_sender, env.project, project_data, "test")

    assert project.name == "test-project"
    assert project.description == "A new project description"
    assert project.quota.gpu_count == 10

    mock_message_sender.enqueue.assert_called_once()


@pytest.mark.asyncio
async def test_update_project_clears_project_level_failure_from_a_re_requested_quota(
    db_session: AsyncSession,
) -> None:
    """Re-requesting a failed quota must also clear the failure the project itself reports."""
    env = await factory.create_basic_test_environment(db_session, create_project_quota=True)
    await factory.create_cluster_node(
        db_session,
        env.cluster,
        cpu_milli_cores=16000,
        memory_bytes=64 * 1024**3,
        ephemeral_storage_bytes=200 * 1024**3,
        gpu_count=10,
    )
    await factory.create_namespace(db_session, env.cluster, env.project, status=NamespaceStatus.ACTIVE)

    env.project.quota.status = QuotaStatus.FAILED
    env.project.quota.status_reason = "Quota was removed from the cluster."
    env.project.status = ProjectStatus.FAILED
    env.project.status_reason = "Failed components: quota. quota: Quota was removed from the cluster."
    await db_session.flush()

    project_data = ProjectEdit(
        description="Retry the quota",
        quota=QuotaBase(
            cpu_milli_cores=2000, memory_bytes=8 * 1024**3, ephemeral_storage_bytes=10 * 1024**3, gpu_count=1
        ),
        gpu_preemption=GpuPreemptionConfig(),
    )

    project = await update_project(db_session, AsyncMock(spec=MessageSender), env.project, project_data, "test")

    assert project.quota.status == QuotaStatus.PENDING
    assert project.quota.status_reason is None
    assert project.status != ProjectStatus.FAILED, "a re-requested quota must not leave the project Failed"
    assert "Quota was removed from the cluster." not in project.status_reason
    assert project.updated_by == "test", "recomputing a derived status must not overwrite who made the edit"


@pytest.mark.asyncio
async def test_update_project_leaves_status_alone_when_the_project_has_no_namespace(
    db_session: AsyncSession,
) -> None:
    """An edit must not be the thing that condemns a project whose namespace is not recorded yet."""
    env = await factory.create_basic_test_environment(db_session, create_project_quota=True)
    await factory.create_cluster_node(
        db_session,
        env.cluster,
        cpu_milli_cores=16000,
        memory_bytes=64 * 1024**3,
        ephemeral_storage_bytes=200 * 1024**3,
        gpu_count=10,
    )

    # READY is a status the recompute could not produce here - the edit leaves the quota PENDING -
    # so seeing it survive proves the no-namespace branch returned rather than reaching a verdict.
    env.project.status = ProjectStatus.READY
    env.project.status_reason = "left exactly as it was"
    await db_session.flush()

    project_data = ProjectEdit(
        description="Edited while the namespace is unknown",
        quota=QuotaBase(
            cpu_milli_cores=2000, memory_bytes=8 * 1024**3, ephemeral_storage_bytes=10 * 1024**3, gpu_count=1
        ),
        gpu_preemption=GpuPreemptionConfig(),
    )

    project = await update_project(db_session, AsyncMock(spec=MessageSender), env.project, project_data, "test")

    assert project.status == ProjectStatus.READY, "no namespace means no verdict, not a failure"
    assert project.status_reason == "left exactly as it was"


@pytest.mark.asyncio
async def test_update_project_conflict_when_deleting(db_session: AsyncSession) -> None:
    env = await factory.create_basic_test_environment(db_session, create_project_quota=True)
    await factory.create_cluster_node(
        db_session,
        env.cluster,
        cpu_milli_cores=16000,
        memory_bytes=64 * 1024**3,
        ephemeral_storage_bytes=200 * 1024**3,
        gpu_count=10,
    )

    env.project.status = ProjectStatus.DELETING
    await db_session.flush()

    project_data = ProjectEdit(
        description="Should not apply",
        quota=QuotaBase(
            cpu_milli_cores=0,
            memory_bytes=0,
            ephemeral_storage_bytes=0,
            gpu_count=10,
            description="test quota",
        ),
        gpu_preemption=GpuPreemptionConfig(),
    )

    mock_message_sender = AsyncMock(spec=MessageSender)

    with pytest.raises(ConflictException) as exc_info:
        await update_project(db_session, mock_message_sender, env.project, project_data, "test")

    assert "deletion" in str(exc_info.value).lower()
    mock_message_sender.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_add_users_to_project_success(db_session: AsyncSession) -> None:
    """Test adding users to project with real database operations."""
    env = await factory.create_basic_test_environment(db_session)

    users = await factory.create_multiple_users(db_session, user_count=2)
    user_ids = [user.id for user in users]
    kc_admin = AsyncMock(spec=KeycloakAdmin)

    await add_users_to_project_and_keycloak_group(kc_admin, db_session, env.project, user_ids)


@pytest.mark.asyncio
async def test_add_users_to_project_user_not_found(db_session: AsyncSession) -> None:
    """Test adding non-existent users to project raises NotFoundException."""
    env = await factory.create_basic_test_environment(db_session)

    user_ids = [uuid4()]
    kc_admin = AsyncMock(spec=KeycloakAdmin)

    with pytest.raises(NotFoundException) as exc_info:
        await add_users_to_project_and_keycloak_group(kc_admin, db_session, env.project, user_ids)

    assert "Some users not found." in str(exc_info.value)


@pytest.mark.asyncio
async def test_remove_user_from_project_success(db_session: AsyncSession) -> None:
    """Test removing user from project with real database operations."""
    env = await factory.create_full_test_environment(db_session)
    kc_admin = AsyncMock(spec=KeycloakAdmin)

    await remove_user_from_project_and_keycloak_group(kc_admin, db_session, env.project, env.user.id)


@pytest.mark.asyncio
async def test_get_projects_with_resource_allocation(db_session: AsyncSession) -> None:
    """Test getting projects with resource allocation information."""
    # Create environment with project that has a quota
    env = await factory.create_basic_test_environment(db_session, create_project_quota=True)
    project1, quota1 = await factory.create_project_with_quota(
        db_session, env.cluster, project_name="test-project-with-quota"
    )

    # Test the function
    result = await get_projects_with_resource_allocation(db_session)

    assert isinstance(result, ProjectsWithResourceAllocation)
    assert len(result.data) >= 1  # Should include our project plus potentially the base environment project

    # Find our project in the results
    project_result = None
    for p in result.data:
        if p.id == project1.id:
            project_result = p
            break

    assert project_result is not None, "Project not found in results"
    assert project_result.name == project1.name

    # Check that computed fields are present
    assert hasattr(project_result, "gpu_allocation_percentage")
    assert hasattr(project_result, "gpu_allocation_exceeded")
    assert hasattr(project_result, "cpu_allocation_percentage")
    assert hasattr(project_result, "cpu_allocation_exceeded")
    assert hasattr(project_result, "memory_allocation_percentage")
    assert hasattr(project_result, "memory_allocation_exceeded")

    # Verify allocation percentages are numeric values
    assert isinstance(project_result.gpu_allocation_percentage, int | float)
    assert isinstance(project_result.cpu_allocation_percentage, int | float)
    assert isinstance(project_result.memory_allocation_percentage, int | float)

    # Verify exceeded flags are boolean values
    assert isinstance(project_result.gpu_allocation_exceeded, bool)
    assert isinstance(project_result.cpu_allocation_exceeded, bool)
    assert isinstance(project_result.memory_allocation_exceeded, bool)


@pytest.mark.asyncio
async def test_get_projects_with_resource_allocation_no_projects(db_session: AsyncSession) -> None:
    """Test getting projects with resource allocation when no projects exist."""
    result = await get_projects_with_resource_allocation(db_session)

    assert isinstance(result, ProjectsWithResourceAllocation)
    assert len(result.data) == 0


@pytest.mark.asyncio
async def test_get_projects_with_resource_allocation_in_clusters(db_session: AsyncSession) -> None:
    """Test getting projects with resource allocation for specific clusters."""
    env = await factory.create_basic_test_environment(db_session, create_project_quota=True)
    await factory.create_cluster_node(db_session, env.cluster, name="node1", gpu_count=8, status="Ready", is_ready=True)

    project1, _ = await factory.create_project_with_quota(
        db_session, env.cluster, project_name="project-1-cluster-1", quota_gpu=2, quota_cpu=4000
    )

    cluster2 = await factory.create_cluster(db_session, name="cluster2")
    await factory.create_cluster_node(db_session, cluster2, name="node1", gpu_count=4, status="Ready", is_ready=True)

    project2, __ = await factory.create_project_with_quota(
        db_session, cluster2, project_name="project-2-cluster-2", quota_gpu=3, quota_cpu=2000
    )

    cluster3 = await factory.create_cluster(db_session, name="cluster3")
    project3, ___ = await factory.create_project_with_quota(
        db_session, cluster3, project_name="project-3-cluster-3", quota_gpu=1
    )

    result = await get_projects_with_resource_allocation_in_clusters(db_session, [env.cluster, cluster2, env.cluster])

    assert isinstance(result, ProjectsWithResourceAllocation)
    project_ids = {p.id for p in result.data}
    assert project1.id in project_ids
    assert project2.id in project_ids
    assert project3.id not in project_ids

    project1_result = next(p for p in result.data if p.id == project1.id)
    assert project1_result.quota.gpu_count == 2
    assert project1_result.quota.cpu_milli_cores == 4000
    assert project1_result.cluster.name == env.cluster.name
    assert project1_result.cluster.available_resources.gpu_count == 8

    project2_result = next(p for p in result.data if p.id == project2.id)
    assert project2_result.quota.gpu_count == 3
    assert project2_result.quota.cpu_milli_cores == 2000
    assert project2_result.cluster.name == "cluster2"
    assert project2_result.cluster.available_resources.gpu_count == 4


@pytest.mark.asyncio
async def test_get_submittable_projects(db_session: AsyncSession) -> None:
    """Test getting submittable projects with new Keycloak-based approach."""
    env = await factory.create_basic_test_environment(db_session)

    # Create project with quota for this test
    project, quota = await factory.create_project_with_quota(
        db_session, env.cluster, project_name="submittable-project"
    )

    # Refresh project to load relationships
    await db_session.refresh(project, ["quota", "cluster"])

    # Test with list of accessible projects (from Keycloak groups)
    accessible_projects = [project]
    result = await get_submittable_projects(accessible_projects)

    assert isinstance(result, Projects)
    assert len(result.data) == 1
    assert result.data[0].id == project.id
    assert result.data[0].name == "submittable-project"
    assert result.data[0].cluster is not None
    assert result.data[0].quota is not None


@pytest.mark.asyncio
async def test_update_project_status_from_components_success(
    db_session: AsyncSession,
) -> None:
    """Test successful update of project status from components."""
    env = await factory.create_basic_test_environment(db_session)
    project, quota = await factory.create_project_with_quota(
        db_session, env.cluster, project_name="test-project-with-quota"
    )
    project.status = ProjectStatus.PENDING
    await factory.create_namespace(
        db_session, name="test-project-with-quota", cluster=env.cluster, project_id=project.id
    )

    dummy_kc_admin = AsyncMock(spec=KeycloakAdmin)

    await update_project_status_from_components(dummy_kc_admin, db_session, project)

    updated = await get_project_by_id(db_session, project.id)
    assert updated.status == ProjectStatus.READY


@pytest.mark.asyncio
async def test_update_project_status_from_components_namespace_not_found(db_session: AsyncSession) -> None:
    """Test update when namespace is not found."""
    env = await factory.create_basic_test_environment(db_session)
    project, quota = await factory.create_project_with_quota(
        db_session, env.cluster, project_name="test-project-with-quota"
    )

    dummy_kc_admin = AsyncMock(spec=KeycloakAdmin)

    await update_project_status_from_components(dummy_kc_admin, db_session, project)

    updated = await get_project_by_id(db_session, project.id)
    assert updated.status == ProjectStatus.FAILED
    assert updated.status_reason == "Namespace not found"


@pytest.mark.asyncio
async def test_update_project_status_from_components_quota_not_found(db_session: AsyncSession) -> None:
    """Test update when quota is not found."""
    env = await factory.create_basic_test_environment(db_session)

    await factory.create_namespace(
        db_session, name="test-project-with-quota", cluster=env.cluster, project_id=env.project.id
    )

    dummy_kc_admin = AsyncMock(spec=KeycloakAdmin)
    await update_project_status_from_components(dummy_kc_admin, db_session, env.project)

    updated = await get_project_by_id(db_session, env.project.id)
    assert updated.status == ProjectStatus.FAILED
    assert updated.status_reason == "Quota not found"


@pytest.mark.asyncio
async def test_update_project_status_from_components_failed_status(
    db_session: AsyncSession,
) -> None:
    """Test update when components indicate failed status."""
    env = await factory.create_basic_test_environment(db_session)
    project, quota = await factory.create_project_with_quota(
        db_session, env.cluster, project_name="test-project-with-quota"
    )
    project.status = ProjectStatus.PENDING
    await factory.create_namespace(
        db_session,
        name="test-project-with-quota",
        cluster=env.cluster,
        project_id=project.id,
        status=NamespaceStatus.FAILED,
    )

    dummy_kc_admin = AsyncMock(spec=KeycloakAdmin)

    await update_project_status_from_components(dummy_kc_admin, db_session, project)

    updated = await get_project_by_id(db_session, project.id)
    assert updated.status == ProjectStatus.FAILED
    assert updated.status_reason == "Failed components: namespace. "


@pytest.mark.asyncio
async def test_submit_delete_project_success(
    db_session: AsyncSession,
) -> None:
    env = await factory.create_basic_test_environment(db_session)
    project, quota = await factory.create_project_with_quota(
        db_session, env.cluster, project_name="test-project-to-delete"
    )
    namespace = await factory.create_namespace(db_session, env.cluster, name=project.name, project_id=project.id)

    await db_session.refresh(project, ["cluster", "quota"])

    user = "test_user@example.com"
    gpu_vendor = "NVIDIA"
    mock_message_sender = AsyncMock()

    await submit_delete_project(db_session, project, user, gpu_vendor, mock_message_sender)
    assert mock_message_sender.enqueue.call_count == 2
    assert project.status == ProjectStatus.DELETING
    assert namespace.status == NamespaceStatus.TERMINATING
    assert quota.status == QuotaStatus.DELETING


@pytest.mark.asyncio
async def test_submit_delete_project_with_none_gpu_vendor(
    db_session: AsyncSession,
) -> None:
    env = await factory.create_basic_test_environment(db_session)
    project, quota = await factory.create_project_with_quota(
        db_session, env.cluster, project_name="test-project-no-gpu"
    )
    namespace = await factory.create_namespace(db_session, env.cluster, name=project.name, project_id=project.id)

    await db_session.refresh(project, ["cluster", "quota"])

    user = "test_user@example.com"
    gpu_vendor = None
    mock_message_sender = AsyncMock()

    await submit_delete_project(db_session, project, user, gpu_vendor, mock_message_sender)
    assert mock_message_sender.enqueue.call_count == 2
    assert project.status == ProjectStatus.DELETING
    assert namespace.status == NamespaceStatus.TERMINATING
    assert quota.status == QuotaStatus.DELETING


@pytest.mark.asyncio
async def test_submit_delete_project_not_safe_to_delete(
    db_session: AsyncSession,
) -> None:
    env = await factory.create_basic_test_environment(db_session)
    project, quota = await factory.create_project_with_quota(
        db_session, env.cluster, project_name="test-project-unsafe"
    )
    project.status = ProjectStatus.DELETING

    await db_session.refresh(project, ["cluster", "quota"])

    user = "test_user@example.com"
    gpu_vendor = "NVIDIA"
    mock_message_sender = AsyncMock()

    with pytest.raises(ConflictException) as exc_info:
        await submit_delete_project(db_session, project, user, gpu_vendor, mock_message_sender)

    assert "Project is already marked for deletion" in str(exc_info.value)


@pytest.mark.asyncio
@patch("app.projects.service.delete_group")
async def test_delete_project_if_components_deleted_success(
    mock_delete_group: MagicMock, db_session: AsyncSession
) -> None:
    env = await factory.create_basic_test_environment(db_session)
    project, quota = await factory.create_project_with_quota(
        db_session, env.cluster, project_name="test-project-to-delete"
    )

    namespace = MagicMock()
    namespace.status = NamespaceStatus.DELETED

    project.status = ProjectStatus.DELETING
    quota.status = QuotaStatus.DELETED
    project.keycloak_group_id = "test-group-id"

    dummy_kc_admin = AsyncMock(spec=KeycloakAdmin)

    result = await delete_project_if_components_deleted(dummy_kc_admin, db_session, project, quota, namespace)

    assert result is True
    assert await get_project_by_id(db_session, project.id) is None

    mock_delete_group.assert_called_once_with(dummy_kc_admin, "test-group-id")


@pytest.mark.asyncio
@patch("app.utilities.keycloak_admin.delete_group")
async def test_delete_project_if_components_deleted_project_not_deleting(
    mock_delete_group: MagicMock, db_session: AsyncSession
) -> None:
    """Test that project is not deleted when project status is not DELETING."""
    env = await factory.create_basic_test_environment(db_session)
    project, quota = await factory.create_project_with_quota(
        db_session, env.cluster, project_name="test-project-active"
    )

    namespace = MagicMock()
    namespace.status = NamespaceStatus.DELETED

    project.status = ProjectStatus.READY
    quota.status = QuotaStatus.DELETED

    dummy_kc_admin = AsyncMock(spec=KeycloakAdmin)

    result = await delete_project_if_components_deleted(dummy_kc_admin, db_session, project, quota, namespace)

    assert result is False
    assert await get_project_by_id(db_session, project.id) is not None
    mock_delete_group.assert_not_called()


@pytest.mark.asyncio
@patch("app.utilities.keycloak_admin.delete_group")
async def test_delete_project_if_components_deleted_quota_not_deleted(
    mock_delete_group: MagicMock, db_session: AsyncSession
) -> None:
    env = await factory.create_basic_test_environment(db_session)
    project, quota = await factory.create_project_with_quota(
        db_session, env.cluster, project_name="test-project-quota-pending"
    )

    namespace = MagicMock()
    namespace.status = NamespaceStatus.DELETED

    project.status = ProjectStatus.DELETING
    quota.status = QuotaStatus.PENDING

    dummy_kc_admin = AsyncMock(spec=KeycloakAdmin)

    result = await delete_project_if_components_deleted(dummy_kc_admin, db_session, project, quota, namespace)

    assert result is False
    assert await get_project_by_id(db_session, project.id) is not None
    mock_delete_group.assert_not_called()


@pytest.mark.asyncio
@patch("app.utilities.keycloak_admin.delete_group")
async def test_delete_project_if_components_deleted_namespace_not_deleted(
    mock_delete_group: MagicMock, db_session: AsyncSession
) -> None:
    env = await factory.create_basic_test_environment(db_session)
    project, quota = await factory.create_project_with_quota(
        db_session, env.cluster, project_name="test-project-namespace-active"
    )

    namespace = MagicMock()
    namespace.status = NamespaceStatus.ACTIVE

    project.status = ProjectStatus.DELETING
    quota.status = QuotaStatus.DELETED

    dummy_kc_admin = AsyncMock(spec=KeycloakAdmin)

    result = await delete_project_if_components_deleted(dummy_kc_admin, db_session, project, quota, namespace)

    assert result is False
    assert await get_project_by_id(db_session, project.id) is not None
    mock_delete_group.assert_not_called()


@pytest.mark.asyncio
async def test_delete_project_recalculates_secret_status(db_session: AsyncSession) -> None:
    """Test that deleting a project recalculates status for organization-scoped secrets."""

    # Create test environment with a project
    env = await factory.create_basic_test_environment(db_session)

    # Create 2 organization-scoped secrets in "Synced" state
    secret = await factory.create_secret_with_project_assignment(
        db_session,
        env.project,
        name="test-org-secret",
        secret_status=SecretStatus.SYNCED.value,
        project_secret_status=ProjectSecretStatus.SYNCED.value,
    )
    secret2 = await factory.create_secret_with_project_assignment(
        db_session,
        env.project,
        name="test-org-secret-2",
        secret_status=SecretStatus.SYNCED.value,
        project_secret_status=ProjectSecretStatus.SYNCED.value,
    )

    # Verify secret is in "Synced" state before deletion
    assert secret.status == SecretStatus.SYNCED
    assert secret2.status == SecretStatus.SYNCED

    # Delete the project (should cascade-delete the assignment and recalculate secret status)
    await delete_project_with_cleanup(db_session, env.project)

    # Refresh the secret and verify its status was recalculated to "Unassigned"
    refreshed_secret = await get_secret(db_session, secret.id)
    assert refreshed_secret.status == SecretStatus.UNASSIGNED

    refreshed_secret = await get_secret(db_session, secret2.id)
    assert refreshed_secret.status == SecretStatus.UNASSIGNED


@pytest.mark.asyncio
async def test_delete_project_preserves_secret_with_other_assignments(db_session: AsyncSession) -> None:
    """Test that deleting a project preserves secret status when other project assignments exist."""
    # Create test environment with two projects
    env = await factory.create_basic_test_environment(db_session)
    project2 = await factory.create_project(db_session, env.cluster, name="project-2", creator="test@example.com")

    # Create an organization-scoped secret in "Synced" state
    secret = await factory.create_secret(
        db_session,
        name="test-shared-secret",
        secret_scope=SecretScope.ORGANIZATION.value,
        status=SecretStatus.SYNCED.value,
    )

    # Assign the secret to both projects in "Synced" state
    await factory.create_organization_secret_assignment(
        db_session, env.project, secret, status=ProjectSecretStatus.SYNCED.value
    )
    await factory.create_organization_secret_assignment(
        db_session, project2, secret, status=ProjectSecretStatus.SYNCED.value
    )

    # Verify secret is in "Synced" state before deletion
    await db_session.refresh(secret)
    assert secret.status == SecretStatus.SYNCED

    # Delete the first project
    await delete_project_with_cleanup(db_session, env.project)

    # Refresh the secret and verify its status remains "Synced" because project2 still has it
    refreshed_secret = await get_secret(db_session, secret.id)
    assert refreshed_secret is not None
    assert refreshed_secret.status == SecretStatus.SYNCED
    assert refreshed_secret.status_reason is None


@pytest.mark.asyncio
async def test_delete_project_recalculates_storage_status(db_session: AsyncSession) -> None:
    """Test that deleting a project recalculates status for storages."""
    # Create test environment with a project
    env = await factory.create_basic_test_environment(db_session)

    # Create a secret for the storage
    secret = await factory.create_secret(db_session)

    # Create 2 storages in "Synced" state
    storage = await factory.create_storage_with_project_assignment(
        db_session,
        env.project,
        secret=secret,
        name="test-storage",
        storage_status=StorageStatus.SYNCED.value,
        project_storage_status=ProjectStorageStatus.SYNCED.value,
    )
    storage2 = await factory.create_storage_with_project_assignment(
        db_session,
        env.project,
        secret=secret,
        name="test-storage-2",
        storage_status=StorageStatus.SYNCED.value,
        project_storage_status=ProjectStorageStatus.SYNCED.value,
    )
    assert storage.status == StorageStatus.SYNCED
    assert storage2.status == StorageStatus.SYNCED

    # Delete the project (should cascade-delete the project storage and recalculate storage status)
    await delete_project_with_cleanup(db_session, env.project)

    # Refresh the storage and verify its status was recalculated to "Unassigned"
    refreshed_storage = await get_storage_by_id(db_session, storage.id)
    assert refreshed_storage.status == StorageStatus.UNASSIGNED

    refreshed_storage = await get_storage_by_id(db_session, storage2.id)
    assert refreshed_storage.status == StorageStatus.UNASSIGNED


@pytest.mark.asyncio
async def test_update_project_sends_namespace_update_when_preemption_changes(db_session: AsyncSession) -> None:
    """A namespace update message is sent when gpu preemption config changes."""
    env = await factory.create_basic_test_environment(db_session, create_project_quota=True)
    await factory.create_cluster_node(
        db_session,
        env.cluster,
        cpu_milli_cores=16000,
        memory_bytes=64 * 1024**3,
        ephemeral_storage_bytes=200 * 1024**3,
        gpu_count=10,
    )

    project_data = ProjectEdit(
        description="A new project description",
        quota=QuotaBase(
            cpu_milli_cores=0,
            memory_bytes=0,
            ephemeral_storage_bytes=0,
            gpu_count=0,
        ),
        gpu_preemption=GpuPreemptionConfig(
            enabled=True, threshold=50, grace_period=900, policy=GpuPreemptionPolicy.ON_PRESSURE
        ),
    )

    mock_message_sender = AsyncMock(spec=MessageSender)

    await update_project(db_session, mock_message_sender, env.project, project_data, "test")

    # One call for quota, one for namespace preemption update
    assert mock_message_sender.enqueue.call_count == 2
    namespace_call = next(
        call
        for call in mock_message_sender.enqueue.call_args_list
        if call.args[1].message_type == "project_namespace_update"
    )
    assert namespace_call.args[0] == env.project.cluster_id
    annotations = namespace_call.args[1].namespace_manifest.metadata.annotations
    assert annotations["kaiwo.silogen.ai/gpu-preemption.enabled"] == "true"
    assert annotations["kaiwo.silogen.ai/gpu-preemption.threshold"] == "50"
    assert annotations["kaiwo.silogen.ai/gpu-preemption.grace-period"] == "900s"
    assert annotations["kaiwo.silogen.ai/gpu-preemption.policy"] == "OnPressure"


@pytest.mark.asyncio
async def test_update_project_no_namespace_update_when_preemption_unchanged(db_session: AsyncSession) -> None:
    """No namespace update message is sent when gpu preemption config is unchanged."""
    env = await factory.create_basic_test_environment(db_session, create_project_quota=True)
    await factory.create_cluster_node(
        db_session,
        env.cluster,
        cpu_milli_cores=16000,
        memory_bytes=64 * 1024**3,
        ephemeral_storage_bytes=200 * 1024**3,
        gpu_count=10,
    )

    # Factory creates project with gpu_preemption_enabled=False — send same disabled config
    project_data = ProjectEdit(
        description="A new project description",
        quota=QuotaBase(
            cpu_milli_cores=0,
            memory_bytes=0,
            ephemeral_storage_bytes=0,
            gpu_count=0,
        ),
        gpu_preemption=GpuPreemptionConfig(enabled=False),
    )

    mock_message_sender = AsyncMock(spec=MessageSender)

    await update_project(db_session, mock_message_sender, env.project, project_data, "test")

    # Only the quota message — no namespace update
    assert mock_message_sender.enqueue.call_count == 1
    assert mock_message_sender.enqueue.call_args.args[1].message_type != "project_namespace_update"
