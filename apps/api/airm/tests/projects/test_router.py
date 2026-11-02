# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from api_common.collections import PaginationMetadata
from api_common.exceptions import ConflictException, NotFoundException, ValidationException
from api_common.secrets import SecretUseCase
from app import app  # type: ignore
from app.clusters.schemas import ClusterResources, ClusterResponse, ClusterWithResources  # Add import for ClusterStatus
from app.metrics.schemas import (
    Datapoint,
    DatapointsWithMetadata,
    DateRange,
    MetricsScalarWithRange,
    MetricsTimeseries,
    ProjectDatapointMetadata,
    TimeseriesRange,
    WorkloadsWithMetrics,
    WorkloadWithMetrics,
)
from app.projects.enums import ProjectStatus
from app.projects.models import Project
from app.projects.schemas import (
    GpuPreemptionConfig,
    ProjectAddUsers,
    ProjectAssignment,
    ProjectCreate,
    ProjectEdit,
    ProjectResponse,
    Projects,
    ProjectsWithResourceAllocation,
    ProjectWithClusterAndQuota,
    ProjectWithResourceAllocation,
    ProjectWithUsers,
)
from app.quotas.schemas import QuotaBase, QuotaResponse  # Add import for QuotaCreate
from app.secrets.enums import ProjectSecretStatus, SecretKind, SecretScope, SecretStatus
from app.secrets.models import OrganizationScopedSecret, ProjectScopedSecret
from app.secrets.schemas import (
    ProjectSecretsWithParentSecret,
    ProjectSecretWithParentSecret,
    SecretResponse,
    SecretWithProjects,
)
from app.storages.enums import ProjectStorageStatus, StorageScope, StorageStatus, StorageType
from app.storages.models import ProjectStorage as ProjectStorageModel
from app.storages.schemas import ProjectStoragesWithParentStorage, ProjectStorageWithParentStorage, StorageResponse
from app.users.schemas import InvitedUser, UserResponse
from app.utilities.security import (
    Roles,
    auth_token_claimset,
    get_projects_accessible_to_user,
)
from app.workloads.enums import WorkloadStatus
from app.workloads.schemas import WorkloadStatusCount, WorkloadStatusStats, WorkloadType
from tests.dependency_overrides import (
    ADMIN_FORBIDDEN_OVERRIDES,
    ADMIN_OVERRIDES,
    SUBMITTABLE_PROJECTS_OVERRIDES,
    SUBMITTABLE_PROJECTS_UNAUTHORIZED_OVERRIDES,
    USER_EMAIL_UNAUTHORIZED_OVERRIDES,
    USER_EMAIL_WITH_SESSION_OVERRIDES,
    USER_PROJECT_SESSION_OVERRIDES,
    USER_PROJECT_VIEW_AUTH_OVERRIDES,
    USER_PROJECT_VIEW_FORBIDDEN_OVERRIDES,
    USER_PROJECT_VIEW_OVERRIDES,
    USER_WITH_KEYCLOAK_ID_OVERRIDES,
    override_dependencies,
    runtime_dependency_overrides,
)

COMMON_METRICS_TIMESERIES = MetricsTimeseries(
    data=[
        DatapointsWithMetadata(
            metadata=ProjectDatapointMetadata(
                label="default_label",
                project=ProjectResponse(
                    id=UUID("0aa18e92-002c-45b7-a06e-dcdb0277974c"),
                    name="project1",
                    description="project 1",
                    cluster_id=UUID("0aa22e92-002c-41b7-a06e-dcdb0244974c"),
                    created_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
                    updated_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
                    created_by="test@example.com",
                    updated_by="test@example.com",
                    status="Pending",
                    status_reason="Creating",
                ),
            ),
            values=[
                Datapoint(value=0.1, timestamp=datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC)),
                Datapoint(value=0.3, timestamp=datetime(2025, 3, 10, 12, 1, 0, tzinfo=UTC)),
            ],
        ),
        DatapointsWithMetadata(
            metadata=ProjectDatapointMetadata(
                label="default_label",
                project=ProjectResponse(
                    id=UUID("19465a28-1649-4f55-887f-536dd36a47f8"),
                    name="project2",
                    description="project 2",
                    cluster_id=UUID("1ab22e52-102c-31b7-a06e-dcdb0244974c"),
                    created_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
                    updated_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
                    created_by="test@example.com",
                    updated_by="test@example.com",
                    status="Pending",
                    status_reason="Creating",
                ),
            ),
            values=[
                Datapoint(value=0.2, timestamp=datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC)),
                Datapoint(value=0.4, timestamp=datetime(2025, 3, 10, 12, 1, 0, tzinfo=UTC)),
            ],
        ),
    ],
    range=TimeseriesRange(
        start=datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC),
        end=datetime(2025, 3, 11, 12, 0, 0, tzinfo=UTC),
        interval_seconds=60,
        timestamps=[
            datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC),
            datetime(2025, 3, 10, 12, 1, 0, tzinfo=UTC),
        ],
    ),
)


# Helper function to create a valid ProjectCreate instance
def get_test_project_with_quota(name="project", description="A test project", cluster_id=None):
    if cluster_id is None:
        cluster_id = uuid4()

    return ProjectCreate(
        name=name,
        description=description,
        cluster_id=cluster_id,
        status=ProjectStatus.READY,
        quota=QuotaBase(
            cpu_milli_cores=1000,
            memory_bytes=1024 * 1024 * 1024,  # 1 GB
            ephemeral_storage_bytes=5 * 1024 * 1024 * 1024,  # 5 GB
            gpu_count=0,
        ),
    )


# Reusable test data

COMMON_CLUSTER_WITH_RESOURCES = ClusterWithResources(
    id=uuid4(),
    name="TestCluster",
    workbench_base_url="http://test-cluster.example.com",
    kube_api_url=None,
    last_heartbeat_at=datetime.now(tz=UTC),
    created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
    updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
    created_by="test@example.com",
    updated_by="test@example.com",
    available_resources=ClusterResources(
        cpu_milli_cores=10000,  # 10 cores
        memory_bytes=16 * 1024**3,
        ephemeral_storage_bytes=100 * 1024**3,
        gpu_count=4,
    ),
    allocated_resources=ClusterResources(cpu_milli_cores=0, memory_bytes=0, ephemeral_storage_bytes=0, gpu_count=0),
    total_node_count=1,
    available_node_count=1,
    assigned_quota_count=0,
    gpu_info=None,
)

COMMON_QUOTA = QuotaResponse(
    id=uuid4(),
    cpu_milli_cores=1000,
    memory_bytes=1024 * 1024 * 1024,  # 1 GB
    ephemeral_storage_bytes=5 * 1024 * 1024 * 1024,  # 5 GB
    gpu_count=0,
    status="Pending",
    created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
    updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
    created_by="test@example.com",
    updated_by="test@example.com",
)

COMMON_PROJECT_OUT = ProjectWithClusterAndQuota(
    id="0aa18e92-002c-45b7-a06e-dcdb0277974c",
    name="project1",
    description="Description 1",
    cluster_id=uuid4(),
    created_at=datetime.now(tz=UTC),
    updated_at=datetime.now(tz=UTC),
    created_by="test@example.com",
    updated_by="test@example.com",
    status="Pending",
    status_reason="Creating",
    cluster=ClusterResponse(
        id="e60079a8-a2a2-4fe4-b5d6-480d03c2a666",
        name="cluster1",
        workbench_base_url="http://cluster1.example.com",
        kube_api_url="https://k8s.example.com:6443",
        last_heartbeat_at=datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC),
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
    ),
    quota=QuotaResponse(
        id=uuid4(),
        cpu_milli_cores=1000,
        memory_bytes=1024 * 1024 * 1024,
        ephemeral_storage_bytes=5 * 1024 * 1024 * 1024,
        gpu_count=0,
        status="Pending",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
        description="project quota",
    ),
)

COMMON_SECRET = SecretResponse(
    id=uuid4(),
    name="secretname",
    type=SecretKind.EXTERNAL_SECRET,
    scope=SecretScope.ORGANIZATION,
    status=SecretStatus.SYNCED,
    status_reason=None,
    created_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
    updated_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
    created_by="test@example.com",
    updated_by="test@example.com",
)

COMMON_STORAGE = StorageResponse(
    id=uuid4(),
    name="storagename",
    secret_id=COMMON_SECRET.id,
    type=StorageType.S3,
    scope=StorageScope.ORGANIZATION,
    status=StorageStatus.SYNCED,
    status_reason=None,
    created_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
    updated_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
    created_by="test@example.com",
    updated_by="test@example.com",
)

COMMON_PROJECT_SECRET = ProjectSecretWithParentSecret(
    id=uuid4(),
    secret=COMMON_SECRET,
    project=ProjectResponse(
        id=uuid4(),
        name="test-project",
        description="Test project description",
        cluster_id=uuid4(),
        status=ProjectStatus.READY,
        status_reason=None,
        created_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
    ),
    status=ProjectSecretStatus.SYNCED,
    status_reason=None,
    created_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
    updated_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
    created_by="test@example.com",
    updated_by="test@example.com",
)

COMMON_PROJECT_STORAGE = ProjectStorageWithParentStorage(
    id=uuid4(),
    storage=COMMON_STORAGE,
    project=ProjectResponse(
        id=uuid4(),
        name="test-project",
        description="Test project description",
        cluster_id=uuid4(),
        status=ProjectStatus.READY,
        status_reason=None,
        created_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
    ),
    status=ProjectStorageStatus.SYNCED,
    status_reason=None,
    created_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
    updated_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
    created_by="test@example.com",
    updated_by="test@example.com",
)


@pytest.mark.asyncio
@patch(
    "app.projects.router.create_project_in_db",
    return_value=Project(
        id="0aa18e92-002c-45b7-a06e-dcdb0277974c",
        name="project",
        description="Description 1",
        cluster_id="b4884301-b87c-4e4a-89bc-e60f458f176d",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
        status=ProjectStatus.READY,
        status_reason="Project is ready",
        gpu_preemption_enabled=False,
    ),
)
@patch(
    "app.projects.router.get_cluster_by_id",
    return_value=ClusterResponse(
        id=uuid4(),
        name="TestCluster",
        workbench_base_url="https://test-cluster.example.com",
        kube_api_url="https://k8s.example.com:6443",
        last_heartbeat_at=datetime.now(tz=UTC),
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
    ),
)
@override_dependencies(ADMIN_OVERRIDES)
async def test_create_project_success(
    mock_get_cluster_by_id: MagicMock,
    mock_create_project_in_db: MagicMock,
) -> None:
    project_create = get_test_project_with_quota(name="project", description="Description 1")

    with TestClient(app) as client:
        response = client.post("/v1/projects", json=json.loads(project_create.model_dump_json(by_alias=True)))

    assert response.status_code == status.HTTP_200_OK

    mock_create_project_in_db.assert_called_once()
    mock_get_cluster_by_id.assert_called_once()


@pytest.mark.asyncio
@patch(
    "app.projects.router.create_project_in_db",
    side_effect=ConflictException("A project with name 'project' already exists in this cluster"),
)
@patch(
    "app.projects.router.get_cluster_by_id",
    return_value=ClusterResponse(
        id=uuid4(),
        name="TestCluster",
        workbench_base_url="https://test-cluster.example.com",
        kube_api_url="https://k8s.example.com:6443",
        last_heartbeat_at=datetime.now(tz=UTC),
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
    ),
)
@override_dependencies(ADMIN_OVERRIDES)
async def test_create_project_name_conflict(_: MagicMock, __: MagicMock) -> None:
    project_create = get_test_project_with_quota(name="project", description="Description 1")

    with TestClient(app) as client:
        response = client.post("/v1/projects", json=json.loads(project_create.model_dump_json(by_alias=True)))

    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
@override_dependencies(USER_EMAIL_UNAUTHORIZED_OVERRIDES)
async def test_create_project_no_user() -> None:
    project_create = get_test_project_with_quota(name="project1", description="Description 1")

    with TestClient(app) as client:
        response = client.post("/v1/projects", json=json.loads(project_create.model_dump_json(by_alias=True)))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
@override_dependencies(ADMIN_FORBIDDEN_OVERRIDES)
async def test_create_project_not_in_role() -> None:
    project_create = get_test_project_with_quota(name="project1", description="Description 1")

    with TestClient(app) as client:
        response = client.post("/v1/projects", json=json.loads(project_create.model_dump_json(by_alias=True)))

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
@override_dependencies(ADMIN_OVERRIDES)
async def test_create_project_invalid_input() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/v1/projects", json={"name": "project 1", "description": "Description 1", "cluster_id": str(uuid4())}
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
@patch(
    "app.projects.router.get_project_by_id",
    return_value=Project(id="0aa18e92-002c-45b7-a06e-dcdb0277974c", name="project1", description="Description 1"),
)
@patch("app.projects.router.add_users_to_project_and_keycloak_group", return_value=None)
@pytest.mark.asyncio
@override_dependencies(ADMIN_OVERRIDES)
async def test_add_users_to_project_success(_: MagicMock, __: MagicMock) -> None:
    body = ProjectAddUsers(user_ids=["9a6898dc-c8ef-4b7c-9b45-c1841d661a51", "f8cec8de-436c-4405-957d-ee36468c72c7"])

    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/b7c13f41-258d-44b1-a694-5dd4ccda660c/users",
            json=json.loads(body.model_dump_json(by_alias=True)),
        )

    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
@override_dependencies(ADMIN_FORBIDDEN_OVERRIDES)
async def test_add_users_to_project_not_in_role() -> None:
    body = ProjectAddUsers(user_ids=["9a6898dc-c8ef-4b7c-9b45-c1841d661a51", "f8cec8de-436c-4405-957d-ee36468c72c7"])

    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/b7c13f41-258d-44b1-a694-5dd4ccda660c/users",
            json=json.loads(body.model_dump_json(by_alias=True)),
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id", side_effect=NotFoundException("Project not found"))
@pytest.mark.asyncio
@override_dependencies(ADMIN_OVERRIDES)
async def test_add_users_to_project_no_project_found(_: MagicMock) -> None:
    body = ProjectAddUsers(user_ids=["9a6898dc-c8ef-4b7c-9b45-c1841d661a51", "f8cec8de-436c-4405-957d-ee36468c72c7"])

    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/b7c13f41-258d-44b1-a694-5dd4ccda660c/users",
            json=json.loads(body.model_dump_json(by_alias=True)),
        )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
@patch(
    "app.projects.router.get_project_by_id",
    return_value=Project(id="0aa18e92-002c-45b7-a06e-dcdb0277974c", name="project1", description="Description 1"),
)
@patch("app.projects.router.add_users_to_project_and_keycloak_group")
@override_dependencies(ADMIN_OVERRIDES)
async def test_add_users_to_project_value_error(
    add_users_to_project_and_keycloak_group: MagicMock, _: MagicMock
) -> None:
    add_users_to_project_and_keycloak_group.side_effect = ValueError("Some users not found in the organization.")

    body = ProjectAddUsers(user_ids=["9a6898dc-c8ef-4b7c-9b45-c1841d661a51", "f8cec8de-436c-4405-957d-ee36468c72c7"])

    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/b7c13f41-258d-44b1-a694-5dd4ccda660c/users",
            json=json.loads(body.model_dump_json(by_alias=True)),
        )
    assert response.json() == {"detail": "Some users not found in the organization."}


@pytest.mark.asyncio
@patch(
    "app.projects.router.get_project_by_id",
    return_value=Project(id="0aa18e92-002c-45b7-a06e-dcdb0277974c", name="project1", description="Description 1"),
)
@patch("app.projects.router.remove_user_from_project_and_keycloak_group", return_value=None)
@pytest.mark.asyncio
@override_dependencies(ADMIN_OVERRIDES)
async def test_remove_user_from_project_success(_: MagicMock, __: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.delete(
            "/v1/projects/b7c13f41-258d-44b1-a694-5dd4ccda660c/users/9a6898dc-c8ef-4b7c-9b45-c1841d661a51"
        )

    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
@override_dependencies(ADMIN_FORBIDDEN_OVERRIDES)
async def test_remove_user_from_project_not_in_role() -> None:
    with TestClient(app) as client:
        response = client.delete(
            "/v1/projects/b7c13f41-258d-44b1-a694-5dd4ccda660c/users/9a6898dc-c8ef-4b7c-9b45-c1841d661a51"
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id", side_effect=NotFoundException("Project not found"))
@pytest.mark.asyncio
@override_dependencies(ADMIN_OVERRIDES)
async def test_remove_user_from_project_no_project_found(_: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.delete(
            "/v1/projects/b7c13f41-258d-44b1-a694-5dd4ccda660c/users/9a6898dc-c8ef-4b7c-9b45-c1841d661a51"
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
@patch(
    "app.projects.router.get_project_by_id",
    return_value=Project(id="0aa18e92-002c-45b7-a06e-dcdb0277974c", name="project1", description="Description 1"),
)
@patch("app.projects.router.remove_user_from_project_and_keycloak_group")
@override_dependencies(ADMIN_OVERRIDES)
async def test_remove_user_from_project_value_error(
    remove_user_from_project_and_keycloak_group: MagicMock, _: MagicMock
) -> None:
    remove_user_from_project_and_keycloak_group.side_effect = ValueError("User does not belong to the project.")

    with TestClient(app) as client:
        response = client.delete(
            "/v1/projects/b7c13f41-258d-44b1-a694-5dd4ccda660c/users/9a6898dc-c8ef-4b7c-9b45-c1841d661a51"
        )

    assert response.json() == {"detail": "User does not belong to the project."}


@pytest.mark.asyncio
@override_dependencies(ADMIN_OVERRIDES)
async def test_update_project_success() -> None:
    project_obj = Project(
        id="0aa18e92-002c-45b7-a06e-dcdb0277974c",
        name="project1",
        description="Description 1",
        cluster_id="b4884301-b87c-4e4a-89bc-e60f458f176d",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
        status=ProjectStatus.READY,
        status_reason="Project is ready",
        gpu_preemption_enabled=False,
    )

    updated_quota = QuotaBase(
        cpu_milli_cores=2000,
        memory_bytes=2 * 1024 * 1024 * 1024,
        ephemeral_storage_bytes=10 * 1024 * 1024 * 1024,
        gpu_count=1,
        description="Updated quota",
    )
    project_update = ProjectEdit(
        description="An updated project", quota=updated_quota, gpu_preemption=GpuPreemptionConfig()
    )

    project_output = COMMON_PROJECT_OUT

    mock_get_project = AsyncMock()
    mock_get_project.return_value = project_obj

    mock_update_project = AsyncMock()
    mock_update_project.return_value = project_obj

    mock_validate = MagicMock()
    mock_validate.return_value = project_output

    with (
        patch("app.projects.router.get_project_by_id", mock_get_project),
        patch("app.projects.router.update_project_in_db", mock_update_project),
        TestClient(app) as client,
    ):
        response = client.put(
            "/v1/projects/b7c13f41-258d-44b1-a694-5dd4ccda660c",
            json=json.loads(project_update.model_dump_json(by_alias=True)),
        )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
@override_dependencies(ADMIN_FORBIDDEN_OVERRIDES)
async def test_update_project_not_in_role() -> None:
    with TestClient(app) as client:
        response = client.put("/v1/projects/b7c13f41-258d-44b1-a694-5dd4ccda660c")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id", side_effect=NotFoundException("Project not found"))
@pytest.mark.asyncio
@override_dependencies(ADMIN_OVERRIDES)
async def test_update_project_no_project_found(_: MagicMock) -> None:
    project_update = ProjectEdit(
        description="Updated Description",
        quota=QuotaBase(
            cpu_milli_cores=1000,
            memory_bytes=1024 * 1024 * 1024,  # 1 GB
            ephemeral_storage_bytes=5 * 1024 * 1024 * 1024,  # 5 GB
            gpu_count=0,
        ),
        gpu_preemption=GpuPreemptionConfig(),
    )

    with TestClient(app) as client:
        response = client.put(
            "/v1/projects/b7c13f41-258d-44b1-a694-5dd4ccda660c",
            json=json.loads(project_update.model_dump_json(by_alias=True)),
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
@override_dependencies(ADMIN_OVERRIDES)
async def test_update_project_invalid_input() -> None:
    # Set up authentication mocks (but don't mock the validation layer)
    valid_project_id = "b7c13f41-258d-44b1-a694-5dd4ccda660c"

    with TestClient(app) as client:
        # Test 1: Description too short (min_length=2)
        response = client.put(
            f"/v1/projects/{valid_project_id}",
            json={
                "description": "a",
                "quota": {
                    "cpuMilliCores": 1000,
                    "memoryBytes": 1000000000,
                    "ephemeralStorageBytes": 1000000000,
                    "gpuCount": 0,
                },
            },
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        # Test 2: Description too long (max_length=1024)
        response = client.put(
            f"/v1/projects/{valid_project_id}",
            json={
                "description": "x" * 1025,
                "quota": {
                    "cpuMilliCores": 1000,
                    "memoryBytes": 1000000000,
                    "ephemeralStorageBytes": 1000000000,
                    "gpuCount": 0,
                },
            },
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        # Test 3: Missing required quota field
        response = client.put(f"/v1/projects/{valid_project_id}", json={"description": "Valid description"})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        # Test 4: Extra forbidden field
        response = client.put(
            f"/v1/projects/{valid_project_id}",
            json={
                "description": "Valid description",
                "quota": {
                    "cpuMilliCores": 1000,
                    "memoryBytes": 1000000000,
                    "ephemeralStorageBytes": 1000000000,
                    "gpuCount": 0,
                },
                "forbiddenField": "should not be allowed",
            },
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id", side_effect=NotFoundException("Project not found"))
@override_dependencies(USER_PROJECT_SESSION_OVERRIDES)
async def test_get_project_not_found(_: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.get("/v1/projects/0aa18e92-002c-45b7-a06e-dcdb0277974c")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Project not found"}


@pytest.mark.asyncio
@patch(
    "app.projects.router.get_project_by_id",
    return_value=Project(id="0aa18e92-002c-45b7-a06e-dcdb0277974c", name="project1", description="Description 1"),
)
@patch(
    "app.projects.router.get_project_with_users",
    return_value=ProjectWithUsers(
        id="0aa18e92-002c-45b7-a06e-dcdb0277974c",
        name="project1",
        description="Description 1",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
        status="Pending",
        status_reason="Creating",
        users=[],
        invited_users=[
            InvitedUser(
                id="0aa18e92-002c-45b7-a06e-dcdc0277974d",
                email="user2@test.com",
                role=Roles.PLATFORM_ADMINISTRATOR.value,
                invited_at="2025-02-11T03:42:02.524263Z",
                invited_by="user1",
                created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                created_by="test@example.com",
                updated_by="test@example.com",
            )
        ],
        cluster_id="1ab18e82-012c-45b7-a36e-dc3c0277974d",
        cluster=ClusterResponse(
            id="e60079a8-a2a2-4fe4-b5d6-480d03c2a666",
            name="cluster1",
            workbench_base_url="https://test-cluster.example.com",
            kube_api_url="https://k8s.example.com:6443",
            last_heartbeat_at=datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC),
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            created_by="test@example.com",
            updated_by="test@example.com",
        ),
        quota=QuotaResponse(
            id="78f6da5c-e78c-46df-bb2d-934abd05221f",
            cpu_milli_cores=1000,
            memory_bytes=1024 * 1024 * 1024,  # 1 GB
            ephemeral_storage_bytes=5 * 1024 * 1024 * 1024,  # 5 GB
            gpu_count=0,
            status="Pending",
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            created_by="test@example.com",
            updated_by="test@example.com",
        ),
    ),
)
@override_dependencies(USER_PROJECT_SESSION_OVERRIDES)
async def test_get_project_with_invited_users_success(_: MagicMock, __: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.get("/v1/projects/0aa18e92-002c-45b7-a06e-dcdb0277974c")

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    expected = {
        "name": "project1",
        "description": "Description 1",
        "id": "0aa18e92-002c-45b7-a06e-dcdb0277974c",
        "clusterId": "1ab18e82-012c-45b7-a36e-dc3c0277974d",
        "status": "Pending",
        "statusReason": "Creating",
        "gpuPreemption": {"enabled": False, "threshold": None, "gracePeriod": None, "policy": None},
        "users": [],
        "invitedUsers": [
            {
                "id": "0aa18e92-002c-45b7-a06e-dcdc0277974d",
                "email": "user2@test.com",
                "role": "Platform Administrator",
                "invitedAt": "2025-02-11T03:42:02.524263Z",
                "invitedBy": "user1",
                "createdAt": "2025-01-01T12:00:00Z",
                "updatedAt": "2025-01-01T12:00:00Z",
                "createdBy": "test@example.com",
                "updatedBy": "test@example.com",
            }
        ],
        "cluster": {
            "id": "e60079a8-a2a2-4fe4-b5d6-480d03c2a666",
            "lastHeartbeatAt": "2025-03-10T12:00:00Z",
            "name": "cluster1",
            "status": "unhealthy",
            "createdAt": "2025-01-01T12:00:00Z",
            "createdBy": "test@example.com",
            "updatedAt": "2025-01-01T12:00:00Z",
            "updatedBy": "test@example.com",
            "workbenchBaseUrl": "https://test-cluster.example.com",
            "kubeApiUrl": "https://k8s.example.com:6443",
        },
        "quota": {
            "cpuMilliCores": 1000,
            "ephemeralStorageBytes": 5368709120,
            "gpuCount": 0,
            "id": "78f6da5c-e78c-46df-bb2d-934abd05221f",
            "memoryBytes": 1073741824,
            "status": "Pending",
            "statusReason": None,
            "createdAt": "2025-01-01T12:00:00Z",
            "updatedAt": "2025-01-01T12:00:00Z",
            "createdBy": "test@example.com",
            "updatedBy": "test@example.com",
        },
        "createdAt": "2025-01-01T12:00:00Z",
        "updatedAt": "2025-01-01T12:00:00Z",
        "createdBy": "test@example.com",
        "updatedBy": "test@example.com",
    }
    assert response_json == expected


@pytest.mark.asyncio
@patch(
    "app.projects.router.get_project_by_id",
    return_value=Project(id="0aa18e92-002c-45b7-a06e-dcdb0277974c", name="project1", description="Description 1"),
)
@patch(
    "app.projects.router.get_project_with_users",
    return_value=ProjectWithUsers(
        id="0aa18e92-002c-45b7-a06e-dcdb0277974c",
        name="project1",
        description="Description 1",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        created_by="test@example.com",
        updated_by="test@example.com",
        users=[
            UserResponse(
                id="0aa18e92-002c-45b7-a06e-dcdc0277974c",
                first_name="John",
                last_name="Doe",
                email="test@test.com",
                role=Roles.PLATFORM_ADMINISTRATOR.value,
                created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                created_by="test@example.com",
                updated_by="test@example.com",
            )
        ],
        invited_users=[],
        cluster_id="1ab18e82-012c-45b7-a36e-dc3c0277974d",
        status="Pending",
        status_reason="Creating",
        cluster=ClusterResponse(
            id="e60079a8-a2a2-4fe4-b5d6-480d03c2a666",
            name="cluster1",
            last_heartbeat_at=datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC),
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            created_by="test@example.com",
            updated_by="test@example.com",
            workbench_base_url="https://example.com",
            kube_api_url="https://k8s.example.com:6443",
        ),
        quota=QuotaResponse(
            id="78f6da5c-e78c-46df-bb2d-934abd05221f",
            cpu_milli_cores=1000,
            memory_bytes=1024 * 1024 * 1024,
            ephemeral_storage_bytes=5 * 1024 * 1024 * 1024,
            gpu_count=0,
            status="Pending",
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            created_by="test@example.com",
            updated_by="test@example.com",
        ),
    ),
)
@override_dependencies(USER_PROJECT_SESSION_OVERRIDES)
async def test_get_project_success(_: MagicMock, __: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.get("/v1/projects/0aa18e92-002c-45b7-a06e-dcdb0277974c")

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    expected = {
        "name": "project1",
        "description": "Description 1",
        "id": "0aa18e92-002c-45b7-a06e-dcdb0277974c",
        "clusterId": "1ab18e82-012c-45b7-a36e-dc3c0277974d",
        "status": "Pending",
        "statusReason": "Creating",
        "gpuPreemption": {"enabled": False, "threshold": None, "gracePeriod": None, "policy": None},
        "users": [
            {
                "firstName": "John",
                "lastName": "Doe",
                "email": "test@test.com",
                "id": "0aa18e92-002c-45b7-a06e-dcdc0277974c",
                "role": "Platform Administrator",
                "createdAt": "2025-01-01T12:00:00Z",
                "updatedAt": "2025-01-01T12:00:00Z",
                "createdBy": "test@example.com",
                "updatedBy": "test@example.com",
                "lastActiveAt": None,
            }
        ],
        "cluster": {
            "id": "e60079a8-a2a2-4fe4-b5d6-480d03c2a666",
            "lastHeartbeatAt": "2025-03-10T12:00:00Z",
            "name": "cluster1",
            "status": "unhealthy",
            "createdAt": "2025-01-01T12:00:00Z",
            "createdBy": "test@example.com",
            "updatedAt": "2025-01-01T12:00:00Z",
            "updatedBy": "test@example.com",
            "workbenchBaseUrl": "https://example.com",
            "kubeApiUrl": "https://k8s.example.com:6443",
        },
        "invitedUsers": [],
        "quota": {
            "cpuMilliCores": 1000,
            "ephemeralStorageBytes": 5368709120,
            "gpuCount": 0,
            "id": "78f6da5c-e78c-46df-bb2d-934abd05221f",
            "memoryBytes": 1073741824,
            "status": "Pending",
            "statusReason": None,
            "createdAt": "2025-01-01T12:00:00Z",
            "updatedAt": "2025-01-01T12:00:00Z",
            "createdBy": "test@example.com",
            "updatedBy": "test@example.com",
        },
        "createdAt": "2025-01-01T12:00:00Z",
        "updatedAt": "2025-01-01T12:00:00Z",
        "createdBy": "test@example.com",
        "updatedBy": "test@example.com",
    }
    assert response_json == expected


@pytest.mark.asyncio
@patch(
    "app.projects.router.get_projects_with_resource_allocation",
    return_value=ProjectsWithResourceAllocation(
        data=[
            ProjectWithResourceAllocation(
                id="0aa18e92-002c-45b7-a06e-dcdb0277974c",
                name="project1",
                description="Description 1",
                created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                created_by="test@example.com",
                updated_by="test@example.com",
                cluster_id="0aa18e92-102c-45b7-a06e-dcdb0277974c",
                status="Pending",
                status_reason="Creating",
                cluster=ClusterWithResources(
                    id="e60079a8-a2a2-4fe4-b5d6-480d03c2a666",
                    name="cluster1",
                    last_heartbeat_at=datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC),
                    created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    created_by="test@example.com",
                    updated_by="test@example.com",
                    workbench_base_url="https://example.com",
                    kube_api_url="https://k8s.example.com:6443",
                    available_resources=ClusterResources(
                        cpu_milli_cores=8000,
                        memory_bytes=16 * 1024 * 1024 * 1024,  # 16 GB
                        ephemeral_storage_bytes=100 * 1024 * 1024 * 1024,  # 100 GB
                        gpu_count=2,
                    ),
                    allocated_resources=ClusterResources(
                        cpu_milli_cores=1000,
                        memory_bytes=1024 * 1024 * 1024,  # 1 GB
                        ephemeral_storage_bytes=5 * 1024 * 1024 * 1024,  # 5 GB
                        gpu_count=0,
                    ),
                    total_node_count=3,
                    available_node_count=2,
                    assigned_quota_count=1,
                ),
                quota=QuotaResponse(
                    id="0aa18e92-202c-45b7-a06e-dcdb0277974c",
                    cpu_milli_cores=1000,
                    memory_bytes=1024 * 1024 * 1024,  # 1 GB
                    ephemeral_storage_bytes=5 * 1024 * 1024 * 1024,  # 5 GB
                    gpu_count=0,
                    status="Pending",
                    created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    created_by="test@example.com",
                    updated_by="test@example.com",
                ),
            ),
            ProjectWithResourceAllocation(
                id="65b44238-556d-4e59-82ea-ddfafc5491f3",
                name="project2",
                description="Description 2",
                created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                created_by="test@example.com",
                updated_by="test@example.com",
                cluster_id="0aa18e92-302c-45b7-a06e-dcdb0277974c",
                status="Pending",
                status_reason="Creating",
                cluster=ClusterWithResources(
                    id="e60079a8-a2a2-4fe4-b5d6-480d03c2a666",
                    name="cluster1",
                    last_heartbeat_at=datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC),
                    created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    created_by="test@example.com",
                    updated_by="test@example.com",
                    workbench_base_url="https://example.com",
                    kube_api_url="https://k8s.example.com:6443",
                    available_resources=ClusterResources(
                        cpu_milli_cores=8000,
                        memory_bytes=16 * 1024 * 1024 * 1024,  # 16 GB
                        ephemeral_storage_bytes=100 * 1024 * 1024 * 1024,  # 100 GB
                        gpu_count=2,
                    ),
                    allocated_resources=ClusterResources(
                        cpu_milli_cores=1000,
                        memory_bytes=1024 * 1024 * 1024,  # 1 GB
                        ephemeral_storage_bytes=5 * 1024 * 1024 * 1024,  # 5 GB
                        gpu_count=0,
                    ),
                    total_node_count=3,
                    available_node_count=2,
                    assigned_quota_count=1,
                ),
                quota=QuotaResponse(
                    id="0aa18e92-402c-45b7-a06e-dcdb0277974c",
                    cpu_milli_cores=2000,
                    memory_bytes=2 * 1024 * 1024 * 1024,  # 2 GB
                    ephemeral_storage_bytes=10 * 1024 * 1024 * 1024,  # 10 GB
                    gpu_count=1,
                    status="Pending",
                    created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    created_by="test@example.com",
                    updated_by="test@example.com",
                ),
            ),
        ]
    ),
)
@patch("app.projects.router.is_user_in_role", return_value=True)
@override_dependencies(USER_WITH_KEYCLOAK_ID_OVERRIDES)
async def test_get_projects_success(_: MagicMock, __: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.get("/v1/projects")

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    expected = {
        "data": [
            {
                "id": "0aa18e92-002c-45b7-a06e-dcdb0277974c",
                "name": "project1",
                "description": "Description 1",
                "clusterId": "0aa18e92-102c-45b7-a06e-dcdb0277974c",
                "status": "Pending",
                "statusReason": "Creating",
                "gpuPreemption": {"enabled": False, "threshold": None, "gracePeriod": None, "policy": None},
                "cluster": {
                    "id": "e60079a8-a2a2-4fe4-b5d6-480d03c2a666",
                    "createdAt": "2025-01-01T12:00:00Z",
                    "updatedAt": "2025-01-01T12:00:00Z",
                    "createdBy": "test@example.com",
                    "updatedBy": "test@example.com",
                    "workbenchBaseUrl": "https://example.com",
                    "kubeApiUrl": "https://k8s.example.com:6443",
                    "name": "cluster1",
                    "lastHeartbeatAt": "2025-03-10T12:00:00Z",
                    "availableResources": {
                        "cpuMilliCores": 8000,
                        "memoryBytes": 17179869184,
                        "ephemeralStorageBytes": 107374182400,
                        "gpuCount": 2,
                    },
                    "allocatedResources": {
                        "cpuMilliCores": 1000,
                        "memoryBytes": 1073741824,
                        "ephemeralStorageBytes": 5368709120,
                        "gpuCount": 0,
                    },
                    "totalNodeCount": 3,
                    "availableNodeCount": 2,
                    "assignedQuotaCount": 1,
                    "gpuInfo": None,
                    "status": "unhealthy",
                    "priorityClasses": [
                        {"name": "low", "priority": -100},
                        {"name": "medium", "priority": 0},
                        {"name": "high", "priority": 100},
                    ],
                    "gpuAllocationPercentage": 0.0,
                    "cpuAllocationPercentage": 12.5,
                    "memoryAllocationPercentage": 6.25,
                },
                "quota": {
                    "cpuMilliCores": 1000,
                    "ephemeralStorageBytes": 5368709120,
                    "gpuCount": 0,
                    "id": "0aa18e92-202c-45b7-a06e-dcdb0277974c",
                    "memoryBytes": 1073741824,
                    "status": "Pending",
                    "statusReason": None,
                    "createdAt": "2025-01-01T12:00:00Z",
                    "updatedAt": "2025-01-01T12:00:00Z",
                    "createdBy": "test@example.com",
                    "updatedBy": "test@example.com",
                },
                "gpuAllocationPercentage": 0.0,
                "gpuAllocationExceeded": False,
                "cpuAllocationPercentage": 12.5,
                "cpuAllocationExceeded": False,
                "memoryAllocationPercentage": 6.25,
                "memoryAllocationExceeded": False,
                "createdAt": "2025-01-01T12:00:00Z",
                "updatedAt": "2025-01-01T12:00:00Z",
                "createdBy": "test@example.com",
                "updatedBy": "test@example.com",
            },
            {
                "id": "65b44238-556d-4e59-82ea-ddfafc5491f3",
                "name": "project2",
                "description": "Description 2",
                "clusterId": "0aa18e92-302c-45b7-a06e-dcdb0277974c",
                "status": "Pending",
                "statusReason": "Creating",
                "gpuPreemption": {"enabled": False, "threshold": None, "gracePeriod": None, "policy": None},
                "cluster": {
                    "id": "e60079a8-a2a2-4fe4-b5d6-480d03c2a666",
                    "createdAt": "2025-01-01T12:00:00Z",
                    "updatedAt": "2025-01-01T12:00:00Z",
                    "createdBy": "test@example.com",
                    "updatedBy": "test@example.com",
                    "workbenchBaseUrl": "https://example.com",
                    "kubeApiUrl": "https://k8s.example.com:6443",
                    "name": "cluster1",
                    "lastHeartbeatAt": "2025-03-10T12:00:00Z",
                    "availableResources": {
                        "cpuMilliCores": 8000,
                        "memoryBytes": 17179869184,
                        "ephemeralStorageBytes": 107374182400,
                        "gpuCount": 2,
                    },
                    "allocatedResources": {
                        "cpuMilliCores": 1000,
                        "memoryBytes": 1073741824,
                        "ephemeralStorageBytes": 5368709120,
                        "gpuCount": 0,
                    },
                    "totalNodeCount": 3,
                    "availableNodeCount": 2,
                    "assignedQuotaCount": 1,
                    "gpuInfo": None,
                    "status": "unhealthy",
                    "priorityClasses": [
                        {"name": "low", "priority": -100},
                        {"name": "medium", "priority": 0},
                        {"name": "high", "priority": 100},
                    ],
                    "gpuAllocationPercentage": 0.0,
                    "cpuAllocationPercentage": 12.5,
                    "memoryAllocationPercentage": 6.25,
                },
                "quota": {
                    "cpuMilliCores": 2000,
                    "ephemeralStorageBytes": 10737418240,
                    "gpuCount": 1,
                    "id": "0aa18e92-402c-45b7-a06e-dcdb0277974c",
                    "memoryBytes": 2147483648,
                    "status": "Pending",
                    "statusReason": None,
                    "createdAt": "2025-01-01T12:00:00Z",
                    "updatedAt": "2025-01-01T12:00:00Z",
                    "createdBy": "test@example.com",
                    "updatedBy": "test@example.com",
                },
                "gpuAllocationPercentage": 50.0,
                "gpuAllocationExceeded": False,
                "cpuAllocationPercentage": 25.0,
                "cpuAllocationExceeded": False,
                "memoryAllocationPercentage": 12.5,
                "memoryAllocationExceeded": False,
                "createdAt": "2025-01-01T12:00:00Z",
                "updatedAt": "2025-01-01T12:00:00Z",
                "createdBy": "test@example.com",
                "updatedBy": "test@example.com",
            },
        ]
    }
    assert response_json == expected


@pytest.mark.asyncio
@patch(
    "app.projects.router.get_projects_with_resource_allocation", return_value=ProjectsWithResourceAllocation(data=[])
)
@patch("app.projects.router.is_user_in_role", return_value=True)
@override_dependencies(USER_WITH_KEYCLOAK_ID_OVERRIDES)
async def test_get_projects_no_projects(_: MagicMock, __: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.get("/v1/projects")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"data": []}


@pytest.mark.asyncio
@patch("app.projects.router.is_user_in_role", return_value=False)
@patch("app.projects.router.get_projects_accessible_to_user", return_value=[MagicMock(cluster=MagicMock())])
@patch(
    "app.projects.router.get_projects_with_resource_allocation_in_clusters",
    return_value=ProjectsWithResourceAllocation(
        data=[
            ProjectWithResourceAllocation(
                id="0aa18e92-002c-45b7-a06e-dcdb0277974c",
                name="accessible-project",
                description="Description 1",
                cluster_id="0aa18e92-102c-45b7-a06e-dcdb0277974c",
                created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                created_by="test@example.com",
                updated_by="test@example.com",
                status=ProjectStatus.READY,
                status_reason=None,
                cluster=ClusterWithResources(
                    id="e60079a8-a2a2-4fe4-b5d6-480d03c2a666",
                    name="cluster1",
                    last_heartbeat_at=datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC),
                    created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    created_by="test@example.com",
                    updated_by="test@example.com",
                    workbench_base_url="https://example.com",
                    kube_api_url="https://k8s.example.com:6443",
                    available_resources=ClusterResources(
                        cpu_milli_cores=8000,
                        memory_bytes=16 * 1024 * 1024 * 1024,
                        ephemeral_storage_bytes=100 * 1024 * 1024 * 1024,
                        gpu_count=2,
                    ),
                    allocated_resources=ClusterResources(
                        cpu_milli_cores=1000,
                        memory_bytes=1024 * 1024 * 1024,
                        ephemeral_storage_bytes=5 * 1024 * 1024 * 1024,
                        gpu_count=0,
                    ),
                    total_node_count=3,
                    available_node_count=2,
                    assigned_quota_count=1,
                ),
                quota=QuotaResponse(
                    id="0aa18e92-202c-45b7-a06e-dcdb0277974c",
                    cpu_milli_cores=1000,
                    memory_bytes=1024 * 1024 * 1024,
                    ephemeral_storage_bytes=5 * 1024 * 1024 * 1024,
                    gpu_count=0,
                    status="Ready",
                    created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    created_by="test@example.com",
                    updated_by="test@example.com",
                ),
            ),
        ]
    ),
)
@override_dependencies(USER_PROJECT_VIEW_AUTH_OVERRIDES)
async def test_get_projects_non_admin_success(_: Any, __: Any, ___: Any) -> None:
    with TestClient(app) as client:
        response = client.get("/v1/projects")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["name"] == "accessible-project"
    assert data["data"][0]["status"] == "Ready"


@pytest.mark.asyncio
@override_dependencies(SUBMITTABLE_PROJECTS_UNAUTHORIZED_OVERRIDES)
async def test_get_submittable_projects_no_user() -> None:
    with TestClient(app) as client:
        response = client.get("/v1/projects/submittable")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
@patch(
    "app.projects.router.get_submittable_projects_from_db",
    return_value=Projects(
        data=[
            ProjectWithClusterAndQuota(
                id="0aa18e92-002c-45b7-a06e-dcdb0277974c",
                name="project1",
                description="Description 1",
                created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                created_by="test@example.com",
                updated_by="test@example.com",
                cluster_id=uuid4(),
                status=ProjectStatus.READY,
                cluster=ClusterResponse(
                    id="e60079a8-a2a2-4fe4-b5d6-480d03c2a666",
                    name="cluster1",
                    workbench_base_url="https://test-cluster.example.com",
                    kube_api_url="https://k8s.example.com:6443",
                    last_heartbeat_at=datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC),
                    created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    created_by="test@example.com",
                    updated_by="test@example.com",
                ),
                quota=QuotaResponse(
                    id=uuid4(),
                    cpu_milli_cores=1000,
                    memory_bytes=1024 * 1024 * 1024,  # 1 GB
                    ephemeral_storage_bytes=5 * 1024 * 1024 * 1024,  # 5 GB
                    gpu_count=0,
                    status="Pending",
                    created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    created_by="test@example.com",
                    updated_by="test@example.com",
                ),
            ),
        ]
    ),
)
@override_dependencies(SUBMITTABLE_PROJECTS_OVERRIDES)
async def test_get_submittable_projects_success(_: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.get("/v1/projects/submittable")

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id")
@patch("app.projects.router.get_cluster_with_resources")
@patch("app.projects.router.submit_delete_project")
@override_dependencies(ADMIN_OVERRIDES)
async def test_delete_project_with_quota_success(
    mock_submit_delete_project: AsyncMock, mock_get_cluster_with_resources: AsyncMock, mock_get_project_by_id: AsyncMock
) -> None:
    quota = MagicMock()
    quota.cluster = MagicMock()
    quota.cluster.gpu_info = None
    project = MagicMock()
    project.quota = quota
    project.cluster = quota.cluster
    mock_get_project_by_id.return_value = project

    mock_get_cluster_with_resources.return_value = MagicMock(gpu_info=None)

    with TestClient(app) as client:
        response = client.delete(f"/v1/projects/{uuid4()}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_get_project_by_id.assert_called_once()


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id", side_effect=NotFoundException("Project not found"))
@override_dependencies(ADMIN_OVERRIDES)
async def test_delete_project_not_found(mock_get_project_by_id: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.delete(f"/v1/projects/{uuid4()}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Project not found"}


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id")
@patch("app.projects.router.get_stats_for_workloads_in_project")
@override_dependencies(USER_PROJECT_VIEW_OVERRIDES)
async def test_get_project_workload_stats_success(mock_get_stats: MagicMock, mock_get_project: MagicMock) -> None:
    project_id = uuid4()
    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_project.name = "Test Project"

    mock_get_project.return_value = mock_project

    mock_get_stats.return_value = WorkloadStatusStats(
        name="Test Project",
        total_workloads=5,
        statusCounts=[
            WorkloadStatusCount(status=WorkloadStatus.RUNNING, count=3),
            WorkloadStatusCount(status=WorkloadStatus.PENDING, count=2),
        ],
    )

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{project_id}/workloads/stats")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["name"] == "Test Project"
    assert data["totalWorkloads"] == 5
    assert {sc["status"] for sc in data["statusCounts"]} == {"Running", "Pending"}


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id", return_value=None)
@patch("app.projects.router.get_stats_for_workloads_in_project", return_value=None)
@override_dependencies(USER_PROJECT_VIEW_OVERRIDES)
async def test_get_project_workload_stats_project_not_found(_: MagicMock, __: MagicMock) -> None:
    project_id = uuid4()

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{project_id}/workloads/stats")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == f"Project with ID {project_id} not found"


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id", autospec=True)
@patch("app.projects.router.get_workloads_metrics_by_project", autospec=True)
@override_dependencies(USER_PROJECT_VIEW_OVERRIDES)
async def test_get_project_workload_metrics_success(mock_get_metrics: MagicMock, mock_get_project: MagicMock) -> None:
    project_id = uuid4()

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_project.name = "TestProject"

    mock_get_project.return_value = mock_project

    mock_get_metrics.return_value = WorkloadsWithMetrics(
        data=[
            WorkloadWithMetrics(
                id=uuid4(),
                project_id=project_id,
                cluster_id=uuid4(),
                status=WorkloadStatus.RUNNING,
                display_name="Mock Workload",
                type=WorkloadType.CUSTOM,
                gpu_count=2,
                vram=8192,
                run_time=3600,
                created_at=None,
                created_by="tester",
                updated_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC),
                updated_by="tester",
            )
        ],
        pagination=PaginationMetadata(page=1, page_size=10, total=1),
    )

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{project_id}/workloads/metrics")

    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]) == 1
    assert data["data"][0]["displayName"] == "Mock Workload"
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["pageSize"] == 10
    assert data["pagination"]["total"] == 1


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id", autospec=True)
@patch("app.projects.router.get_workloads_metrics_by_project", autospec=True)
@override_dependencies(USER_PROJECT_VIEW_OVERRIDES)
async def test_get_project_workload_metrics_project_not_found(
    mock_get_metrics: MagicMock, mock_get_project: MagicMock
) -> None:
    project_id = uuid4()

    mock_get_project.return_value = None
    mock_get_metrics.return_value = None

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{project_id}/workloads/metrics")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Project not found"


@pytest.mark.asyncio
@patch(
    "app.projects.router.get_project_by_id",
    return_value=Project(id="0aa18e92-002c-45b7-a06e-dcdb0277974c", name="project1"),
)
@patch(
    "app.projects.router.get_gpu_device_utilization_timeseries_for_project_from_ds",
    return_value=COMMON_METRICS_TIMESERIES,
)
@patch("app.metrics.schemas.datetime")
@override_dependencies(USER_PROJECT_SESSION_OVERRIDES)
async def test_get_gpu_device_utilization_timeseries_for_project_success(
    _: MagicMock, __: MagicMock, mock_dt: MagicMock
) -> None:
    mock_dt.now.return_value = datetime(2025, 3, 11, 12, 1, 0, tzinfo=UTC)
    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{uuid4()}/metrics/gpu_device_utilization?start=2025-03-10T12:00:00Z&end=2025-03-11T12:00:00Z"
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "data": [
            {
                "metadata": {
                    "label": "default_label",
                    "project": {
                        "description": "project 1",
                        "id": "0aa18e92-002c-45b7-a06e-dcdb0277974c",
                        "name": "project1",
                        "clusterId": "0aa22e92-002c-41b7-a06e-dcdb0244974c",
                        "createdAt": "2025-03-10T10:00:00Z",
                        "updatedAt": "2025-03-10T10:00:00Z",
                        "createdBy": "test@example.com",
                        "updatedBy": "test@example.com",
                        "status": "Pending",
                        "statusReason": "Creating",
                        "gpuPreemption": {"enabled": False, "threshold": None, "gracePeriod": None, "policy": None},
                    },
                },
                "values": [
                    {"timestamp": "2025-03-10T12:00:00Z", "value": 0.1},
                    {"timestamp": "2025-03-10T12:01:00Z", "value": 0.3},
                ],
            },
            {
                "metadata": {
                    "label": "default_label",
                    "project": {
                        "description": "project 2",
                        "id": "19465a28-1649-4f55-887f-536dd36a47f8",
                        "name": "project2",
                        "clusterId": "1ab22e52-102c-31b7-a06e-dcdb0244974c",
                        "createdAt": "2025-03-10T10:00:00Z",
                        "updatedAt": "2025-03-10T10:00:00Z",
                        "createdBy": "test@example.com",
                        "updatedBy": "test@example.com",
                        "status": "Pending",
                        "statusReason": "Creating",
                        "gpuPreemption": {"enabled": False, "threshold": None, "gracePeriod": None, "policy": None},
                    },
                },
                "values": [
                    {"timestamp": "2025-03-10T12:00:00Z", "value": 0.2},
                    {"timestamp": "2025-03-10T12:01:00Z", "value": 0.4},
                ],
            },
        ],
        "range": {
            "end": "2025-03-11T12:00:00Z",
            "intervalSeconds": 60,
            "start": "2025-03-10T12:00:00Z",
            "timestamps": ["2025-03-10T12:00:00Z", "2025-03-10T12:01:00Z"],
        },
    }


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id", autospec=True)
@patch("app.metrics.schemas.datetime")
@override_dependencies(USER_PROJECT_VIEW_OVERRIDES)
async def test_get_gpu_device_utilization_timeseries_for_project_project_not_found(
    mock_dt: MagicMock, mock_get_project: MagicMock
) -> None:
    mock_dt.now.return_value = datetime(2025, 3, 11, 12, 1, 0, tzinfo=UTC)
    project_id = uuid4()

    mock_get_project.return_value = None

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{project_id}/metrics/gpu_device_utilization?start=2025-03-10T12:00:00Z&end=2025-03-11T12:00:00Z"
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Project not found"


@pytest.mark.asyncio
@override_dependencies(USER_PROJECT_VIEW_FORBIDDEN_OVERRIDES)
async def test_get_gpu_device_utilization_timeseries_for_project_not_in_role() -> None:
    project_id = uuid4()

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{project_id}/metrics/gpu_device_utilization?start=2025-03-10T12:00:00Z&end=2025-03-11T12:00:00Z"
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
@patch(
    "app.projects.router.get_project_by_id",
    return_value=Project(id="0aa18e92-002c-45b7-a06e-dcdb0277974c", name="project1"),
)
@patch(
    "app.projects.router.get_gpu_memory_utilization_timeseries_for_project_from_ds",
    return_value=COMMON_METRICS_TIMESERIES,
)
@patch("app.metrics.schemas.datetime")
@override_dependencies(USER_PROJECT_SESSION_OVERRIDES)
async def test_get_gpu_memory_utilization_timeseries_for_project_success(
    mock_dt: MagicMock, _: MagicMock, __: MagicMock
) -> None:
    mock_dt.now.return_value = datetime(2025, 3, 11, 12, 1, 0, tzinfo=UTC)
    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{uuid4()}/metrics/gpu_memory_utilization?start=2025-03-10T12:00:00Z&end=2025-03-11T12:00:00Z"
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "data": [
            {
                "metadata": {
                    "label": "default_label",
                    "project": {
                        "description": "project 1",
                        "id": "0aa18e92-002c-45b7-a06e-dcdb0277974c",
                        "name": "project1",
                        "clusterId": "0aa22e92-002c-41b7-a06e-dcdb0244974c",
                        "createdAt": "2025-03-10T10:00:00Z",
                        "updatedAt": "2025-03-10T10:00:00Z",
                        "createdBy": "test@example.com",
                        "updatedBy": "test@example.com",
                        "status": "Pending",
                        "statusReason": "Creating",
                        "gpuPreemption": {"enabled": False, "threshold": None, "gracePeriod": None, "policy": None},
                    },
                },
                "values": [
                    {"timestamp": "2025-03-10T12:00:00Z", "value": 0.1},
                    {"timestamp": "2025-03-10T12:01:00Z", "value": 0.3},
                ],
            },
            {
                "metadata": {
                    "label": "default_label",
                    "project": {
                        "description": "project 2",
                        "id": "19465a28-1649-4f55-887f-536dd36a47f8",
                        "name": "project2",
                        "clusterId": "1ab22e52-102c-31b7-a06e-dcdb0244974c",
                        "createdAt": "2025-03-10T10:00:00Z",
                        "updatedAt": "2025-03-10T10:00:00Z",
                        "createdBy": "test@example.com",
                        "updatedBy": "test@example.com",
                        "status": "Pending",
                        "statusReason": "Creating",
                        "gpuPreemption": {"enabled": False, "threshold": None, "gracePeriod": None, "policy": None},
                    },
                },
                "values": [
                    {"timestamp": "2025-03-10T12:00:00Z", "value": 0.2},
                    {"timestamp": "2025-03-10T12:01:00Z", "value": 0.4},
                ],
            },
        ],
        "range": {
            "end": "2025-03-11T12:00:00Z",
            "intervalSeconds": 60,
            "start": "2025-03-10T12:00:00Z",
            "timestamps": ["2025-03-10T12:00:00Z", "2025-03-10T12:01:00Z"],
        },
    }


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id", autospec=True)
@patch("app.metrics.schemas.datetime")
@override_dependencies(USER_PROJECT_VIEW_OVERRIDES)
async def test_get_gpu_memory_utilization_timeseries_for_project_project_not_found(
    mock_dt: MagicMock, mock_get_project: MagicMock
) -> None:
    mock_dt.now.return_value = datetime(2025, 3, 11, 12, 1, 0, tzinfo=UTC)
    project_id = uuid4()

    mock_get_project.return_value = None

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{project_id}/metrics/gpu_memory_utilization?start=2025-03-10T12:00:00Z&end=2025-03-11T12:00:00Z"
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Project not found"


@pytest.mark.asyncio
@override_dependencies(USER_PROJECT_VIEW_FORBIDDEN_OVERRIDES)
async def test_get_gpu_memory_utilization_timeseries_for_project_not_in_role() -> None:
    project_id = uuid4()

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{project_id}/metrics/gpu_memory_utilization?start=2025-03-10T12:00:00Z&end=2025-03-11T12:00:00Z"
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
@patch(
    "app.projects.router.get_average_wait_time_for_project_from_ds",
    new_callable=AsyncMock,
    return_value=MetricsScalarWithRange(
        data=10000,
        range=DateRange(
            start=datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC), end=datetime(2025, 3, 11, 12, 0, 0, tzinfo=UTC)
        ),
    ),
)
@patch("app.projects.router.get_project_by_id", new_callable=AsyncMock)
@patch("app.metrics.schemas.datetime")
@override_dependencies(USER_PROJECT_VIEW_OVERRIDES)
async def test_average_wait_time_for_project_success(
    mock_dt: MagicMock, mock_get_project: AsyncMock, _: MagicMock
) -> None:
    mock_dt.now.return_value = datetime(2025, 3, 11, 12, 1, 0, tzinfo=UTC)
    project_id = uuid4()

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_project.name = "Test Project"

    mock_get_project.return_value = mock_project

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{project_id}/metrics/average_wait_time?start=2025-03-10T12:00:00Z&end=2025-03-11T12:00:00Z"
        )

    assert response.status_code == 200
    assert response.json() == {
        "data": 10000,
        "range": {
            "start": "2025-03-10T12:00:00Z",
            "end": "2025-03-11T12:00:00Z",
        },
    }


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id", autospec=True)
@patch("app.metrics.schemas.datetime")
@override_dependencies(USER_PROJECT_VIEW_OVERRIDES)
async def test_get_average_wait_time_for_project_project_not_found(
    mock_dt: MagicMock, mock_get_project: MagicMock
) -> None:
    mock_dt.now.return_value = datetime(2025, 3, 11, 12, 1, 0, tzinfo=UTC)
    project_id = uuid4()

    mock_get_project.return_value = None

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{project_id}/metrics/average_wait_time?start=2025-03-10T12:00:00Z&end=2025-03-11T12:00:00Z"
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Project not found"


@pytest.mark.asyncio
@override_dependencies(USER_PROJECT_VIEW_FORBIDDEN_OVERRIDES)
async def test_get_average_wait_time_for_project_not_in_role() -> None:
    project_id = uuid4()

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{project_id}/metrics/average_wait_time?start=2025-03-10T12:00:00Z&end=2025-03-11T12:00:00Z"
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
@patch(
    "app.projects.router.get_avg_gpu_idle_time_for_project_from_ds",
    new_callable=AsyncMock,
    return_value=MetricsScalarWithRange(
        data=20000,
        range=DateRange(
            start=datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC), end=datetime(2025, 3, 11, 12, 0, 0, tzinfo=UTC)
        ),
    ),
)
@patch("app.projects.router.get_project_by_id", new_callable=AsyncMock)
@patch("app.metrics.schemas.datetime")
@override_dependencies(USER_PROJECT_VIEW_OVERRIDES)
async def test_get_avg_gpu_idle_time_for_project_success(
    mock_dt: MagicMock, mock_get_project: AsyncMock, _: MagicMock
) -> None:
    mock_dt.now.return_value = datetime(2025, 3, 11, 12, 1, 0, tzinfo=UTC)
    project_id = uuid4()

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_project.name = "Test Project"

    mock_get_project.return_value = mock_project

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{project_id}/metrics/average_gpu_idle_time?start=2025-03-10T12:00:00Z&end=2025-03-11T12:00:00Z"
        )

    assert response.status_code == 200
    assert response.json() == {
        "data": 20000,
        "range": {
            "start": "2025-03-10T12:00:00Z",
            "end": "2025-03-11T12:00:00Z",
        },
    }


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id", autospec=True)
@patch("app.metrics.schemas.datetime")
@override_dependencies(USER_PROJECT_VIEW_OVERRIDES)
async def test_get_avg_gpu_idle_time_for_project_project_not_found(
    mock_dt: MagicMock, mock_get_project: MagicMock
) -> None:
    mock_dt.now.return_value = datetime(2025, 3, 11, 12, 1, 0, tzinfo=UTC)
    project_id = uuid4()

    mock_get_project.return_value = None

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{project_id}/metrics/average_gpu_idle_time?start=2025-03-10T12:00:00Z&end=2025-03-11T12:00:00Z"
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Project not found"


@pytest.mark.asyncio
@override_dependencies(USER_PROJECT_VIEW_FORBIDDEN_OVERRIDES)
async def test_get_avg_gpu_idle_time_for_project_not_in_role() -> None:
    project_id = uuid4()

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{project_id}/metrics/average_gpu_idle_time?start=2025-03-10T12:00:00Z&end=2025-03-11T12:00:00Z"
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
@patch("app.projects.router.get_project_storages_in_project")
@patch("app.projects.router.is_user_in_role", return_value=True)
@patch("app.projects.router.get_project_by_id", return_value=MagicMock(spec=Project))
@override_dependencies(USER_PROJECT_VIEW_AUTH_OVERRIDES)
async def test_get_project_storages_platform_admin(
    _: MagicMock, __: MagicMock, mock_get_project_storages_in_project: MagicMock
) -> None:
    mock_get_project_storages_in_project.return_value = ProjectStoragesWithParentStorage(data=[COMMON_PROJECT_STORAGE])

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{uuid4()}/storages")

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
@patch("app.projects.router.get_project_storages_in_project")
@patch("app.projects.router.is_user_in_role", return_value=False)
@patch("app.projects.router.get_projects_accessible_to_user", return_value=MagicMock(autospec=True))
@patch("app.projects.router.get_project_by_id", return_value=MagicMock(spec=Project))
@override_dependencies(USER_PROJECT_VIEW_AUTH_OVERRIDES)
async def test_get_project_storages_team_member(
    _: MagicMock, __: MagicMock, ___: MagicMock, mock_get_project_storages_in_project: MagicMock
) -> None:
    mock_get_project_storages_in_project.return_value = ProjectStoragesWithParentStorage(data=[COMMON_PROJECT_STORAGE])

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{uuid4()}/storages")

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
@patch("app.projects.router.is_user_in_role", return_value=True)
@patch("app.projects.router.get_project_by_id", return_value=None)
@override_dependencies(USER_PROJECT_SESSION_OVERRIDES)
async def test_get_project_storages_team_member_no_project(_: MagicMock, __: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{uuid4()}/storages")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
@patch("app.projects.router.get_project_storage", return_value=None)
@patch("app.projects.router.submit_delete_project_storage")
@override_dependencies(ADMIN_OVERRIDES)
async def test_delete_project_storage_not_found(_: MagicMock, __: MagicMock) -> None:
    project_id = uuid4()
    storage_id = uuid4()

    with TestClient(app) as client:
        response = client.delete(f"/v1/projects/{project_id}/storages/{storage_id}")

    assert response.status_code == 404
    assert "Project Storage not found" in response.json()["detail"]


@pytest.mark.asyncio
@patch("app.projects.router.get_project_storage")
@patch("app.projects.router.submit_delete_project_storage")
@override_dependencies(ADMIN_OVERRIDES)
async def test_delete_project_storage_success(
    mock_submit_delete_project_storage: AsyncMock, mock_get_project_storage: MagicMock
) -> None:
    project_id = uuid4()
    storage_id = uuid4()

    mock_project_storage = ProjectStorageModel(
        id=uuid4(), storage_id=storage_id, project_id=project_id, status=ProjectStorageStatus.SYNCED
    )
    mock_get_project_storage.return_value = mock_project_storage

    with TestClient(app) as client:
        response = client.delete(f"/v1/projects/{project_id}/storages/{storage_id}")

    assert response.status_code == 204
    mock_submit_delete_project_storage.assert_called_once()


@pytest.mark.asyncio
@patch("app.projects.router.get_project_secrets_in_project")
@patch("app.projects.router.is_user_in_role", return_value=False)
@patch("app.projects.router.get_projects_accessible_to_user", return_value=MagicMock(autospec=True))
@patch("app.projects.router.get_project_by_id", return_value=MagicMock(spec=Project))
@override_dependencies(USER_PROJECT_VIEW_AUTH_OVERRIDES)
async def test_get_project_secrets_team_member(
    _: MagicMock, __: MagicMock, ___: MagicMock, mock_get_project_secrets_in_project: MagicMock
) -> None:
    mock_get_project_secrets_in_project.return_value = ProjectSecretsWithParentSecret(data=[COMMON_PROJECT_SECRET])

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{uuid4()}/secrets")

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
@patch("app.projects.router.get_project_secrets_in_project")
@patch("app.projects.router.is_user_in_role", return_value=True)
@patch("app.projects.router.get_project_by_id", new_callable=AsyncMock)
@override_dependencies(USER_PROJECT_VIEW_AUTH_OVERRIDES)
async def test_get_project_secrets_filtered_by_use_case(
    mock_get_project: AsyncMock, _is_admin: MagicMock, mock_get_project_secrets_in_project: MagicMock
) -> None:
    mock_project = MagicMock(spec=Project)
    mock_get_project.return_value = mock_project

    mock_get_project_secrets_in_project.return_value = ProjectSecretsWithParentSecret(data=[])

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{uuid4()}/secrets",
            params={
                "useCase": SecretUseCase.HUGGING_FACE.value,
                "secretType": SecretKind.KUBERNETES_SECRET.value,
            },
        )

    assert response.status_code == status.HTTP_200_OK
    mock_get_project.assert_called_once()
    mock_get_project_secrets_in_project.assert_called_once()
    args, kwargs = mock_get_project_secrets_in_project.call_args
    # Arguments are passed positionally; ensure filters were forwarded.
    assert len(args) >= 4
    assert args[2] == SecretKind.KUBERNETES_SECRET
    assert args[3] == SecretUseCase.HUGGING_FACE


@pytest.mark.asyncio
@patch("app.projects.router.is_user_in_role", return_value=True)
@patch("app.projects.router.get_project_by_id", return_value=None)
@override_dependencies(USER_PROJECT_SESSION_OVERRIDES)
async def test_get_project_secrets_team_member_no_project(_: MagicMock, __: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{uuid4()}/secrets")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
@patch("app.projects.router.get_secret", return_value=None)
@patch("app.projects.router.delete_project_scoped_secret")
@patch("app.projects.router.ensure_can_remove_secret_from_projects")
@override_dependencies(USER_EMAIL_WITH_SESSION_OVERRIDES)
async def test_delete_project_secret_not_found(_: MagicMock, __: MagicMock, ___: MagicMock) -> None:
    project_id = uuid4()
    secret_id = uuid4()

    # Mock project with matching ID to ensure user has access
    mock_project = MagicMock(spec=Project)
    mock_project.id = project_id

    # Mock claimset without platform admin role (regular user)
    mock_claimset: dict = {"realm_access": {"roles": []}}

    with runtime_dependency_overrides(
        {
            get_projects_accessible_to_user: lambda: [mock_project],
            auth_token_claimset: lambda: mock_claimset,
        }
    ):
        with TestClient(app) as client:
            response = client.delete(f"/v1/projects/{project_id}/secrets/{secret_id}")

        assert response.status_code == 404
        assert "Secret not found" in response.json()["detail"]


@pytest.mark.asyncio
@patch("app.projects.router.get_secret")
@patch("app.projects.router.delete_project_scoped_secret")
@patch("app.projects.router.ensure_can_remove_secret_from_projects")
@override_dependencies(USER_EMAIL_WITH_SESSION_OVERRIDES)
async def test_delete_project_secret_success(
    mock_ensure_can_remove_secret_from_projects: AsyncMock,
    mock_delete_project_scoped_secret: AsyncMock,
    mock_get_project_secret: MagicMock,
) -> None:
    project_id = uuid4()
    secret_id = uuid4()

    # Mock project with matching ID to ensure user has access
    mock_project = MagicMock(spec=Project)
    mock_project.id = project_id

    # Mock claimset without platform admin role (regular user)
    mock_claimset: dict = {"realm_access": {"roles": []}}

    mock_project_scoped_secret = ProjectScopedSecret(
        id=secret_id, name="test-secret", project_id=project_id, status=SecretStatus.SYNCED
    )
    mock_get_project_secret.return_value = mock_project_scoped_secret

    with runtime_dependency_overrides(
        {
            get_projects_accessible_to_user: lambda: [mock_project],
            auth_token_claimset: lambda: mock_claimset,
        }
    ):
        with TestClient(app) as client:
            response = client.delete(f"/v1/projects/{project_id}/secrets/{secret_id}")

        assert response.status_code == 204
        mock_delete_project_scoped_secret.assert_called_once()
        mock_ensure_can_remove_secret_from_projects.assert_called_once()


@pytest.mark.asyncio
@patch("app.projects.router.get_secret")
@patch("app.projects.router.delete_project_scoped_secret")
@patch("app.projects.router.ensure_can_remove_secret_from_projects")
@override_dependencies(USER_EMAIL_WITH_SESSION_OVERRIDES)
async def test_delete_project_secret_platform_admin_no_membership(
    mock_ensure_can_remove_secret_from_projects: AsyncMock,
    mock_delete_project_scoped_secret: AsyncMock,
    mock_get_project_secret: MagicMock,
) -> None:
    """Platform admins can delete secrets from any project, even if they're not members."""
    project_id = uuid4()
    secret_id = uuid4()

    # Mock claimset WITH platform admin role
    mock_claimset: dict[str, dict[str, list[str]]] = {"realm_access": {"roles": [Roles.PLATFORM_ADMINISTRATOR.value]}}

    mock_project_scoped_secret = ProjectScopedSecret(
        id=secret_id, name="test-secret", project_id=project_id, status=SecretStatus.SYNCED
    )
    mock_get_project_secret.return_value = mock_project_scoped_secret

    with runtime_dependency_overrides(
        {
            get_projects_accessible_to_user: lambda: [],  # Empty accessible projects list - admin is NOT a member of this project
            auth_token_claimset: lambda: mock_claimset,
        }
    ):
        with TestClient(app) as client:
            response = client.delete(f"/v1/projects/{project_id}/secrets/{secret_id}")

        assert response.status_code == 204
        mock_delete_project_scoped_secret.assert_called_once()
        mock_ensure_can_remove_secret_from_projects.assert_called_once()


@pytest.mark.asyncio
@patch("app.projects.router.get_secret")
@patch("app.projects.router.delete_project_scoped_secret")
@patch("app.projects.router.ensure_can_remove_secret_from_projects")
@override_dependencies(USER_EMAIL_WITH_SESSION_OVERRIDES)
async def test_delete_project_secret_secret_ref_by_storage_error(
    mock_ensure_can_remove_secret_from_projects: AsyncMock,
    mock_delete_project_scoped_secret: AsyncMock,
    mock_get_project_secret: MagicMock,
) -> None:
    """
    When the secret is still referenced by storages in the project, the delete
    should fail and must not submit a delete message.
    """
    # Platform admin but business rule still applies
    mock_claimset: dict[str, dict[str, list[str]]] = {"realm_access": {"roles": [Roles.PLATFORM_ADMINISTRATOR.value]}}

    project_id = uuid4()
    secret_id = uuid4()

    # The project-secret exists
    mock_project_scoped_secret = ProjectScopedSecret(
        id=secret_id, name="test-secret", project_id=project_id, status=SecretStatus.SYNCED
    )
    mock_get_project_secret.return_value = mock_project_scoped_secret

    # Simulate validation failure: secret still referenced by storages
    mock_ensure_can_remove_secret_from_projects.side_effect = ValidationException(
        "Cannot remove this secret because it is still referenced by storages in the project."
    )

    with runtime_dependency_overrides(
        {
            auth_token_claimset: lambda: mock_claimset,
            get_projects_accessible_to_user: lambda: [],  # Admin is not a member of the project (doesn't matter for this error path)
        }
    ):
        with TestClient(app) as client:
            response = client.delete(f"/v1/projects/{project_id}/secrets/{secret_id}")

        assert response.status_code == 400
        mock_ensure_can_remove_secret_from_projects.assert_called_once()
        mock_delete_project_scoped_secret.assert_not_called()


@pytest.mark.asyncio
@patch("app.projects.router.get_secret")
@patch("app.projects.router.remove_organization_secret_assignments")
@patch("app.projects.router.ensure_can_remove_secret_from_projects")
@override_dependencies(USER_EMAIL_WITH_SESSION_OVERRIDES)
async def test_delete_organization_scoped_secret_success(
    mock_ensure_can_remove_secret_from_projects: AsyncMock,
    mock_remove_organization_secret_assignments: AsyncMock,
    mock_get_secret: MagicMock,
) -> None:
    """Test deleting an organization-scoped secret from a project."""
    project_id = uuid4()
    secret_id = uuid4()

    # Mock project with matching ID to ensure user has access
    mock_project = MagicMock(spec=Project)
    mock_project.id = project_id

    # Mock claimset without platform admin role (regular user)
    mock_claimset: dict[str, dict[str, list[str]]] = {"realm_access": {"roles": []}}

    # Mock organization-scoped secret
    mock_org_secret = OrganizationScopedSecret(id=secret_id, name="test-org-secret", status=SecretStatus.SYNCED)
    mock_get_secret.return_value = mock_org_secret

    with runtime_dependency_overrides(
        {
            get_projects_accessible_to_user: lambda: [mock_project],
            auth_token_claimset: lambda: mock_claimset,
        }
    ):
        with TestClient(app) as client:
            response = client.delete(f"/v1/projects/{project_id}/secrets/{secret_id}")

        assert response.status_code == 204
        mock_ensure_can_remove_secret_from_projects.assert_called_once_with(
            mock_ensure_can_remove_secret_from_projects.call_args[0][0], [project_id], secret_id
        )
        mock_remove_organization_secret_assignments.assert_called_once_with(
            mock_remove_organization_secret_assignments.call_args[0][0],
            mock_org_secret,
            [project_id],
            mock_remove_organization_secret_assignments.call_args[0][3],
        )


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id")
@patch("app.projects.router.get_organization_scoped_secret")
@patch("app.projects.router.get_organization_secret_assignment")
@patch("app.projects.router.add_organization_secret_assignments")
@override_dependencies(ADMIN_OVERRIDES)
async def test_assign_project_secrets_success(
    mock_add_organization_secret_assignments: AsyncMock,
    mock_get_organization_secret_assignment: MagicMock,
    mock_get_secret: MagicMock,
    mock_get_project: MagicMock,
) -> None:
    # Mock get project
    project_id = uuid4()
    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_project.name = "Test Project"
    mock_get_project.return_value = mock_project

    secret_id = uuid4()
    mock_secret = MagicMock()
    mock_secret.id = secret_id
    mock_secret.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_secret.name = "Test Secret"
    mock_get_secret.return_value = mock_secret

    mock_get_organization_secret_assignment.return_value = None

    with TestClient(app) as client:
        response = client.put(f"/v1/projects/{project_id}/secrets/{secret_id}/assign")

    # Assert
    assert response.status_code == 204
    mock_get_project.assert_called_once()
    mock_get_secret.assert_called_once()
    mock_get_organization_secret_assignment.assert_called_once()
    mock_add_organization_secret_assignments.assert_called_once()


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id")
@patch("app.projects.router.get_organization_scoped_secret")
@patch("app.projects.router.get_organization_secret_assignment")
@patch("app.projects.router.add_organization_secret_assignments")
@override_dependencies(ADMIN_OVERRIDES)
async def test_assign_project_secrets_project_not_found(
    mock_add_organization_secret_assignments: AsyncMock,
    mock_get_organization_secret_assignment: MagicMock,
    mock_get_secret: MagicMock,
    mock_get_project: MagicMock,
) -> None:
    project_id = uuid4()
    mock_get_project.return_value = None

    secret_id = uuid4()

    with TestClient(app) as client:
        response = client.put(f"/v1/projects/{project_id}/secrets/{secret_id}/assign")

    assert response.status_code == 404
    assert "Project not found" in response.json()["detail"]
    mock_get_project.assert_called_once()
    mock_get_secret.assert_not_called()
    mock_get_organization_secret_assignment.assert_not_called()
    mock_add_organization_secret_assignments.assert_not_called()


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id")
@patch("app.projects.router.get_organization_scoped_secret")
@patch("app.projects.router.get_organization_secret_assignment")
@patch("app.projects.router.add_organization_secret_assignments")
@override_dependencies(ADMIN_OVERRIDES)
async def test_assign_project_secrets_secret_not_found(
    mock_add_organization_secret_assignments: AsyncMock,
    mock_get_project_secret: MagicMock,
    mock_get_secret: MagicMock,
    mock_get_project: MagicMock,
) -> None:
    project_id = uuid4()
    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_project.name = "Test Project"
    mock_get_project.return_value = mock_project

    secret_id = uuid4()
    mock_get_secret.return_value = None

    mock_get_project_secret.return_value = None

    with TestClient(app) as client:
        response = client.put(f"/v1/projects/{project_id}/secrets/{secret_id}/assign")

    assert response.status_code == 404
    mock_get_project.assert_called_once()
    mock_get_secret.assert_called_once()
    mock_get_project_secret.assert_not_called()
    mock_add_organization_secret_assignments.assert_not_called()

    assert response.status_code == 404
    assert "Secret not found" in response.json()["detail"]


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id")
@patch("app.projects.router.get_organization_scoped_secret")
@patch("app.projects.router.get_organization_secret_assignment")
@patch("app.projects.router.add_organization_secret_assignments")
@override_dependencies(ADMIN_OVERRIDES)
async def test_assign_project_secrets_already_assigned(
    mock_add_organization_secret_assignments: AsyncMock,
    mock_get_organization_secret_assignment: MagicMock,
    mock_get_secret: MagicMock,
    mock_get_project: MagicMock,
) -> None:
    project_id = uuid4()
    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_project.name = "Test Project"
    mock_get_project.return_value = mock_project

    secret_id = uuid4()
    mock_secret = MagicMock()
    mock_secret.id = secret_id
    mock_secret.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_secret.name = "Test Secret"
    mock_get_secret.return_value = mock_secret

    organization_secret_assignment_id = uuid4()
    organization_secret_assignment = MagicMock()
    organization_secret_assignment.id = organization_secret_assignment_id
    organization_secret_assignment.project_id = project_id
    organization_secret_assignment.organization_secret_id = secret_id
    mock_get_organization_secret_assignment.return_value = organization_secret_assignment

    with TestClient(app) as client:
        response = client.put(f"/v1/projects/{project_id}/secrets/{secret_id}/assign")

    assert response.status_code == 400
    assert response.json()["detail"] == "Secret already assigned to this Project"
    mock_get_project.assert_called_once()
    mock_get_secret.assert_called_once()
    mock_get_organization_secret_assignment.assert_called_once()
    mock_add_organization_secret_assignments.assert_not_called()


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id")
@patch("app.projects.router.get_storage_by_id")
@patch("app.projects.router.get_project_storage")
@patch("app.projects.router.assign_projects_to_storage")
@override_dependencies(ADMIN_OVERRIDES)
async def test_assign_project_storage_success(
    mock_assign_projects_to_storage: AsyncMock,
    mock_get_project_storage: MagicMock,
    mock_get_storage: MagicMock,
    mock_get_project: MagicMock,
) -> None:
    # Mock get project
    project_id = uuid4()
    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_project.name = "Test Project"
    mock_get_project.return_value = mock_project

    storage_id = uuid4()
    mock_storage = MagicMock()
    mock_storage.id = storage_id
    mock_storage.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_storage.name = "Test Storage"
    mock_get_storage.return_value = mock_storage

    mock_get_project_storage.return_value = None

    with TestClient(app) as client:
        response = client.put(f"/v1/projects/{project_id}/storages/{storage_id}/assign")

    # Assert
    assert response.status_code == 204
    mock_get_project.assert_called_once()
    mock_get_storage.assert_called_once()
    mock_get_project_storage.assert_called_once()
    mock_assign_projects_to_storage.assert_called_once()


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id")
@patch("app.projects.router.get_storage_by_id")
@patch("app.projects.router.get_project_storage")
@patch("app.projects.router.assign_projects_to_storage")
@override_dependencies(ADMIN_OVERRIDES)
async def test_assign_project_storage_project_not_found(
    mock_assign_projects_to_storage: AsyncMock,
    mock_get_project_storage: MagicMock,
    mock_get_storage: MagicMock,
    mock_get_project: MagicMock,
) -> None:
    project_id = uuid4()
    mock_get_project.return_value = None

    storage_id = uuid4()
    mock_get_storage.return_value = None

    with TestClient(app) as client:
        response = client.put(f"/v1/projects/{project_id}/storages/{storage_id}/assign")

    assert response.status_code == 404
    assert "Project not found" in response.json()["detail"]
    mock_get_project.assert_called_once()
    mock_get_storage.assert_not_called()
    mock_get_project_storage.assert_not_called()
    mock_assign_projects_to_storage.assert_not_called()


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id")
@patch("app.projects.router.get_storage_by_id")
@patch("app.projects.router.get_project_storage")
@patch("app.projects.router.assign_projects_to_storage")
@override_dependencies(ADMIN_OVERRIDES)
async def test_assign_project_storage_storage_not_found(
    mock_assign_projects_to_storage: AsyncMock,
    mock_get_project_storage: MagicMock,
    mock_get_storage: MagicMock,
    mock_get_project: MagicMock,
) -> None:
    project_id = uuid4()
    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_project.name = "Test Project"
    mock_get_project.return_value = mock_project

    storage_id = uuid4()
    mock_get_storage.return_value = None

    mock_get_project_storage.return_value = None

    with TestClient(app) as client:
        response = client.put(f"/v1/projects/{project_id}/storages/{storage_id}/assign")

    assert response.status_code == 404
    mock_get_project.assert_called_once()
    mock_get_storage.assert_called_once()
    mock_get_project_storage.assert_not_called()
    mock_assign_projects_to_storage.assert_not_called()

    assert response.status_code == 404
    assert "Storage not found" in response.json()["detail"]


@pytest.mark.asyncio
@patch("app.projects.router.get_project_by_id")
@patch("app.projects.router.get_storage_by_id")
@patch("app.projects.router.get_project_storage")
@patch("app.projects.router.assign_projects_to_storage")
@override_dependencies(ADMIN_OVERRIDES)
async def test_assign_project_storages_already_assigned(
    mock_assign_projects_to_storage: AsyncMock,
    mock_get_project_storage: MagicMock,
    mock_get_storage: MagicMock,
    mock_get_project: MagicMock,
) -> None:
    project_id = uuid4()
    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_project.name = "Test Project"
    mock_get_project.return_value = mock_project

    storage_id = uuid4()
    mock_storage = MagicMock()
    mock_storage.id = storage_id
    mock_storage.organization_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    mock_storage.name = "Test Storage"
    mock_get_storage.return_value = mock_storage

    project_storage_id = uuid4()
    project_storage = MagicMock()
    project_storage.id = project_storage_id
    project_storage.project_id = project_id
    project_storage.storage_id = storage_id
    mock_get_project_storage.return_value = project_storage

    with TestClient(app) as client:
        response = client.put(f"/v1/projects/{project_id}/storages/{storage_id}/assign")

    assert response.status_code == 400
    assert response.json()["detail"] == "Storage already assigned to this Project"
    mock_get_project.assert_called_once()
    mock_get_storage.assert_called_once()
    mock_get_project_storage.assert_called_once()
    mock_assign_projects_to_storage.assert_not_called()


@pytest.mark.asyncio
@patch("app.projects.router.create_project_scoped_secret")
@patch("app.projects.router.is_user_in_role", return_value=True)
@override_dependencies(USER_EMAIL_WITH_SESSION_OVERRIDES)
async def test_create_project_secret(
    mock_is_user_in_role: MagicMock, mock_create_project_scoped_secret: AsyncMock
) -> None:
    mock_project = Project(id="0aa18e92-002c-45b7-a06e-dcdb0277974c", name="project1", description="Description 1")

    project_id = "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    secret_id = str(uuid4())
    now = datetime(2025, 3, 10, 10, 0, 0, tzinfo=UTC)

    project_secret = ProjectAssignment(
        project=ProjectResponse(
            id=UUID(project_id),
            name="project1",
            description="Test project description",
            cluster_id=uuid4(),
            status=ProjectStatus.READY,
            status_reason=None,
            created_at=now,
            updated_at=now,
            created_by="test@example.com",
            updated_by="test@example.com",
        ),
        status=ProjectSecretStatus.SYNCED,
        status_reason=None,
        created_at=now,
        updated_at=now,
        created_by="test@example.com",
        updated_by="test@example.com",
        id=uuid4(),
    )

    secret_response = SecretWithProjects(
        id=secret_id,
        name="test-secret",
        type=SecretKind.KUBERNETES_SECRET,
        scope=SecretScope.PROJECT,
        status=SecretStatus.SYNCED,
        status_reason=None,
        created_at=now,
        updated_at=now,
        created_by="test@example.com",
        updated_by="test@example.com",
        use_case=SecretUseCase.HUGGING_FACE,
        project_secrets=[project_secret],
    )
    mock_create_project_scoped_secret.return_value = secret_response

    manifest_yaml = """apiVersion: v1
        kind: Secret
        metadata:
          name: test-secret
        type: Opaque
        data:
          username: dXNlcm5hbWU=
          password: cGFzc3dvcmQ="""

    payload = {
        "name": "test-secret",
        "scope": "Project",
        "type": "KubernetesSecret",
        "useCase": "HuggingFace",
        "manifest": manifest_yaml,
    }

    with runtime_dependency_overrides(
        {
            auth_token_claimset: lambda: {"realm_access": {"roles": ["PlatformAdministrator"]}},
            get_projects_accessible_to_user: lambda: [
                Project(id="0aa18e92-002c-45b7-a06e-dcdb0277974c", name="project1", description="Description 1")
            ],
        }
    ):
        with TestClient(app) as client:
            response = client.post(
                f"/v1/projects/{project_id}/secrets", json=payload, headers={"Authorization": "Bearer testtoken"}
            )

        if response.status_code != 201:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == secret_id
        assert data["name"] == "test-secret"
        assert data["type"] == "KubernetesSecret"
        assert data["scope"] == "Project"
        assert data["useCase"] == "HuggingFace"
        assert len(data["projectSecrets"]) == 1
        assert data["projectSecrets"][0]["project"]["id"] == project_id

        mock_create_project_scoped_secret.assert_called_once()
