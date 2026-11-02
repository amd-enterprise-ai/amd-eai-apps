# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from textwrap import dedent
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.auth.security import get_user_email
from api_common.database import get_session
from api_common.schemas import QueryParam

from ..common_responses import PROJECT_ACCESS_RESPONSES
from ..dispatch.kube_client import KubernetesClient, get_kube_client
from ..projects.security import ensure_access_to_project
from ..workloads.schemas import DisplayNameQuery, WorkloadResponse
from .schemas import DevelopmentWorkspaceRequest
from .service import create_development_workspace, delete_development_workspace

router = APIRouter(tags=["Workspaces"])


@router.post(
    "/projects/{project}/workspaces",
    response_model=WorkloadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a development workspace",
    description=dedent("""
        Create an interactive development workspace (Jupyter, VS Code, MLflow, ComfyUI)
        for AI/ML development in the given project. Provisions a containerized
        environment with optional GPU access for model development and experimentation.

        The workspace type is selected via the `workspaceType` field in the request body.

        **Workspace Types:**
        - **jupyterlab**: Interactive notebook environment for data science
        - **vscode**: Browser-based Visual Studio Code with full IDE features
        - **comfyui**: Visual interface for AI image generation workflows
        - **mlflow**: Experiment tracking and model registry (namespace-scoped)

        **Workspace Limitations:**
        - MLflow workspaces are limited to one active instance per namespace
        - JupyterLab, VS Code, and ComfyUI workspaces are user-scoped and limited to one
          active instance per user per namespace

        Returns 409 Conflict if attempting to create a workspace of a given type when an
        instance with the same scope (namespace for MLflow; user and namespace for other
        types) is already running or pending.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        409: {
            "description": (
                "A workspace of the same type already exists in the conflicting scope "
                "(per-namespace for MLflow; per-user-per-namespace for the others)."
            )
        },
        422: {"description": "Invalid request body (e.g., gpus out of [0,8] range)."},
    },
)
async def create_workspace_endpoint(
    request: DevelopmentWorkspaceRequest,
    query: QueryParam[DisplayNameQuery],
    project: str = Depends(ensure_access_to_project),
    session: AsyncSession = Depends(get_session),
    submitter: str = Depends(get_user_email),
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> WorkloadResponse:
    workload = await create_development_workspace(
        session=session,
        kube_client=kube_client,
        submitter=submitter,
        namespace=project,
        request=request,
        workspace_type=request.workspace_type,
        display_name=query.display_name,
    )

    return WorkloadResponse.model_validate(workload)


@router.delete(
    "/projects/{project}/workspaces/{workload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a development workspace",
    description=dedent("""
        Delete a development workspace and tear down its Kubernetes components
        (deployment, service, ingress). PVC cleanup may be incomplete for
        workspaces whose Helm chart declares PVCs outside the standard label
        selector.

        Unsaved in-memory work is lost on deletion. Persistent data stored on
        the PVC should be exported beforehand (e.g., via the workspace's file
        browser) if it needs to be preserved.
    """),
    responses={
        **PROJECT_ACCESS_RESPONSES,
        404: {"description": "Project or namespace not found, or workspace not found."},
    },
)
async def delete_workspace_endpoint(
    workload_id: UUID = Path(..., description="Workload UUID of the workspace"),
    project: str = Depends(ensure_access_to_project),
    session: AsyncSession = Depends(get_session),
) -> None:
    await delete_development_workspace(session=session, namespace=project, workload_id=workload_id)
