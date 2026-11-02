# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for workspace deployment via AIWB API.
...                 Tests workspace lifecycle: create, status transitions, access URLs, and deletion.
...                 All workspace types are limited to one per type per user per project.
Resource    resources/aiwb_workspaces.resource
Resource    resources/airm_projects.resource
Resource    resources/airm_secrets.resource
Resource    resources/airm_clusters.resource
Resource    resources/kubectl_verification.resource
Library             Collections
Test Teardown       Clean Up Workspace Test Resources

*** Test Cases ***
Deploy JupyterLab workspace without GPU
    [Documentation]    Verify that a JupyterLab workspace can be deployed via AIWB API without GPU
    ...    Tests: POST /workspaces (workspaceType=jupyterlab) → workspace creation with Pending status (CPU-only)
    [Tags]    workspace    jupyterlab    smoke

    Given a ready project with user access exists

    When JupyterLab workspace is deployed    gpus=0

    Then workspace should be visible via API
    And workspace should have valid ID and status
    And workspace status should be "Pending"

Deploy JupyterLab workspace with GPU
    [Documentation]    Verify that a JupyterLab workspace can be deployed via AIWB API with GPU
    ...    Tests: POST /workspaces (workspaceType=jupyterlab) → workspace creation with Pending status (1 GPU)
    [Tags]    workspace    jupyterlab    gpu

    Given a ready project with user access exists

    When JupyterLab workspace is deployed    gpus=1

    Then workspace should be visible via API
    And workspace should have valid ID and status
    And workspace status should be "Pending"

JupyterLab workspace transitions to Running without GPU
    [Documentation]    Verify that a JupyterLab workspace transitions from Pending to Running (CPU-only)
    ...    Tests: Workspace deployment → wait for Running status
    ...    Requires: MinIO credentials secret assigned to project
    [Tags]    workspace    jupyterlab    status

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And JupyterLab workspace is deployed    gpus=0
    And workspace status should be "Pending"

    When workspace transitions to "Running"

    Then workspace status should be "Running"

JupyterLab workspace transitions to Running with GPU
    [Documentation]    Verify that a JupyterLab workspace transitions from Pending to Running (1 GPU)
    ...    Tests: Workspace deployment → wait for Running status
    ...    Requires: MinIO credentials secret assigned to project
    [Tags]    workspace    jupyterlab    status    gpu

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And JupyterLab workspace is deployed    gpus=1
    And workspace status should be "Pending"

    When workspace transitions to "Running"

    Then workspace status should be "Running"

JupyterLab workspace has access URL
    [Documentation]    Verify that Running workspace has external_host and internal_host URLs
    ...    Tests: Access URL availability and HTTP accessibility after workspace becomes Running
    ...    Note: URLs may take a few seconds after Running status to be populated
    [Tags]    workspace    jupyterlab    url    gpu

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And JupyterLab workspace is deployed    gpus=1
    And workspace transitions to "Running"

    Then workspace should have access URL
    And workspace external URL should be accessible

Delete JupyterLab workspace
    [Documentation]    Verify that JupyterLab workspace can be deleted
    ...    Tests: DELETE /workspaces/{id} → workspace deletion (204 response)
    ...    Note: Complete removal from API may take several minutes due to Helm/K8s cleanup
    [Tags]    workspace    jupyterlab    deletion    gpu

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And JupyterLab workspace is deployed    gpus=1
    And workspace transitions to "Running"

    When workspace is deleted

    # Note: We only verify DELETE request succeeds (204)
    # Complete removal can take 10+ minutes and is verified during cleanup

Deploy MLflow workspace
    [Documentation]    Verify that MLflow workspace can be deployed (CPU-only)
    ...    Tests: POST /workspaces (workspaceType=mlflow) → MLflow creation
    ...    Note: MLflow typically doesn't require GPU
    [Tags]    workspace    mlflow

    Given a ready project with user access exists

    When MLflow workspace is deployed    gpus=0

    Then workspace should be visible via API
    And workspace should have valid ID and status
    And workspace status should be "Pending"

MLflow workspace transitions to Running
    [Documentation]    Verify that MLflow workspace transitions to Running (CPU-only)
    ...    Tests: MLflow deployment → wait for Running status
    [Tags]    workspace    mlflow    status

    Given a ready project "e2e-test-mlflow-running" with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And MLflow workspace is deployed    gpus=0
    And workspace status should be "Pending"

    When workspace transitions to "Running"

    Then workspace status should be "Running"
    And workspace should have access URL

Only one MLflow workspace per project
    [Documentation]    Verify that only one MLflow workspace can exist per project
    ...    Tests: MLflow project-scoped constraint (409 Conflict)
    ...
    ...    Runs in a fresh project so only the workspace created by this scenario can occupy it.
    [Tags]    workspace    mlflow    constraint

    Given a fresh project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And MLflow workspace is deployed    gpus=0
    And workspace transitions to "Running"

    When attempting to deploy second MLflow workspace

    Then workspace creation should fail with conflict

MLflow allows new workspace after deletion
    [Documentation]    Verify that new MLflow can be created after deletion
    ...    Tests: MLflow deletion frees up project slot
    [Tags]    workspace    mlflow    deletion

    Given a ready project "e2e-test-mlflow-deletion" with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And MLflow workspace is deployed    gpus=0
    And workspace transitions to "Running"
    And workspace is deleted
    And workspace should not be visible via API

    When MLflow workspace is deployed    gpus=0

    Then workspace should be visible via API
    And workspace status should be "Pending"

Only one JupyterLab workspace per user per project
    [Documentation]    Verify that only one JupyterLab workspace can exist per user per project
    ...    Tests: User-scoped workspace constraint (409 Conflict on duplicate)
    [Tags]    workspace    jupyterlab    constraint

    Given a ready project with user access exists
    And JupyterLab workspace is deployed    display_name=jupyter-1    gpus=0

    When attempting to deploy second JupyterLab workspace

    Then workspace creation should fail with conflict

Workspace with custom image
    [Documentation]    Verify that workspace can be created with custom container image
    ...    Tests: Custom image parameter in workspace creation (CPU-only)
    [Tags]    workspace    jupyterlab    custom-image

    Given a ready project with user access exists

    When JupyterLab workspace is deployed with custom image    image=rocm/pytorch:rocm6.4_ubuntu24.04_py3.12_pytorch_release_2.6.0    gpus=0

    Then workspace should be visible via API
    And workspace should have valid ID and status

Workspace with GPU allocation
    [Documentation]    Verify that workspace can be created with specific GPU allocation
    ...    Tests: GPU resource allocation (0-8 GPUs)
    [Tags]    workspace    jupyterlab    resources                                gpu

    Given a ready project with user access exists

    When JupyterLab workspace is deployed with GPU allocation    gpus=2

    Then workspace should be visible via API
    And workspace should have valid ID and status

JupyterLab workspace without MinIO credentials stays pending
    [Documentation]    Verify that workspace without MinIO credentials remains in Pending status
    ...    Tests: Infrastructure dependency - workspace requires MinIO credentials to start
    ...    Creates a separate project without MinIO secret assignment (CPU-only)
    [Tags]    workspace    jupyterlab    negative    infrastructure

    Given a ready project "e2e-test-workspace-failure" with user access exists

    When JupyterLab workspace is deployed    gpus=0

    Then workspace should be visible via API
    And workspace should have valid ID and status
    And workspace status should be "Pending"
    # Verify workspace remains in Pending status without MinIO credentials
    And Wait Until Keyword Succeeds    30 sec    5 sec    Workspace status should be "Pending"

Deploy VSCode workspace without GPU
    [Documentation]    Verify that a VSCode workspace can be deployed via AIWB API without GPU
    ...    Tests: POST /workspaces (workspaceType=vscode) → workspace creation with Pending status (CPU-only)
    [Tags]    workspace    vscode    smoke

    Given a ready project with user access exists

    When VSCode workspace is deployed    gpus=0

    Then workspace should be visible via API
    And workspace should have valid ID and status
    And workspace status should be "Pending"

Deploy VSCode workspace with GPU
    [Documentation]    Verify that a VSCode workspace can be deployed via AIWB API with GPU
    ...    Tests: POST /workspaces (workspaceType=vscode) → workspace creation with Pending status (1 GPU)
    [Tags]    workspace    vscode    gpu

    Given a ready project with user access exists

    When VSCode workspace is deployed    gpus=1

    Then workspace should be visible via API
    And workspace should have valid ID and status
    And workspace status should be "Pending"

VSCode workspace transitions to Running
    [Documentation]    Verify that a VSCode workspace transitions from Pending to Running (CPU-only)
    ...    Tests: Workspace deployment → wait for Running status
    ...    Requires: MinIO credentials secret assigned to project
    [Tags]    workspace    vscode    status

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And VSCode workspace is deployed    gpus=0
    And workspace status should be "Pending"

    When workspace transitions to "Running"

    Then workspace status should be "Running"

VSCode workspace has access URL
    [Documentation]    Verify that Running workspace has external_host and internal_host URLs
    ...    Tests: Access URL availability and HTTP accessibility after workspace becomes Running
    ...    Note: URLs may take a few seconds after Running status to be populated
    [Tags]    workspace    vscode    url    gpu

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And VSCode workspace is deployed    gpus=1
    And workspace transitions to "Running"

    Then workspace should have access URL
    And workspace external URL should be accessible

Delete VSCode workspace
    [Documentation]    Verify that VSCode workspace can be deleted
    ...    Tests: DELETE /workspaces/{id} → workspace deletion
    [Tags]    workspace    vscode    deletion    gpu

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And VSCode workspace is deployed    gpus=1
    And workspace transitions to "Running"

    When workspace is deleted

    Then workspace should not be visible via API

Only one VSCode workspace per user per project
    [Documentation]    Verify that only one VSCode workspace can exist per user per project
    ...    Tests: User-scoped workspace constraint (409 Conflict on duplicate)
    [Tags]    workspace    vscode    constraint

    Given a ready project "e2e-test-vscode-constraint" with user access exists
    And VSCode workspace is deployed    display_name=vscode-1    gpus=0

    When attempting to deploy second VSCode workspace

    Then workspace creation should fail with conflict

Deploy ComfyUI workspace without GPU
    [Documentation]    Verify that a ComfyUI workspace can be deployed via AIWB API without GPU
    ...    Tests: POST /workspaces (workspaceType=comfyui) → workspace creation with Pending status (CPU-only)
    [Tags]    workspace    comfyui    smoke

    Given a ready project with user access exists

    When ComfyUI workspace is deployed    gpus=0

    Then workspace should be visible via API
    And workspace should have valid ID and status
    And workspace status should be "Pending"

Deploy ComfyUI workspace with GPU
    [Documentation]    Verify that a ComfyUI workspace can be deployed via AIWB API with GPU
    ...    Tests: POST /workspaces (workspaceType=comfyui) → workspace creation with Pending status (1 GPU)
    [Tags]    workspace    comfyui    gpu

    Given a ready project with user access exists

    When ComfyUI workspace is deployed    gpus=1

    Then workspace should be visible via API
    And workspace should have valid ID and status
    And workspace status should be "Pending"

ComfyUI workspace transitions to Running
    [Documentation]    Verify that a ComfyUI workspace transitions from Pending to Running
    ...    Tests: Workspace deployment → wait for Running status
    ...    Requires: MinIO credentials secret assigned to project, GPU cluster for model download
    ...    NOTE: All `comfyui`-tagged tests are excluded from CI (--exclude comfyui in
    ...    the AIWB E2E step): ComfyUI's container does heavy runtime setup that exceeds
    ...    its startupProbe budget and crash-loops on a cold cluster, so this never
    ...    reaches Running.
    ...    TODO: re-enable once the fixed ai-workloads chart deploys.
    [Tags]    workspace    comfyui    status    gpu

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And ComfyUI workspace is deployed    gpus=1
    And workspace status should be "Pending"

    When workspace transitions to "Running"

    Then workspace status should be "Running"

ComfyUI workspace has access URL
    [Documentation]    Verify that Running workspace has external_host and internal_host URLs
    ...    Tests: Access URL availability and HTTP accessibility after workspace becomes Running
    ...    Note: URLs may take a few seconds after Running status to be populated
    [Tags]    workspace    comfyui    url    gpu

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And ComfyUI workspace is deployed    gpus=1
    And workspace transitions to "Running"

    Then workspace should have access URL
    And workspace external URL should be accessible

Delete ComfyUI workspace
    [Documentation]    Verify that ComfyUI workspace can be deleted
    ...    Tests: DELETE /workspaces/{id} → workspace deletion
    [Tags]    workspace    comfyui    deletion    gpu

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And ComfyUI workspace is deployed    gpus=1
    And workspace transitions to "Running"

    When workspace is deleted

    Then workspace should not be visible via API

Only one ComfyUI workspace per user per project
    [Documentation]    Verify that only one ComfyUI workspace can exist per user per project
    ...    Tests: User-scoped workspace constraint (409 Conflict on duplicate)
    [Tags]    workspace    comfyui    constraint

    Given a ready project "e2e-test-comfyui-constraint" with user access exists
    And ComfyUI workspace is deployed    display_name=comfyui-1    gpus=0

    When attempting to deploy second ComfyUI workspace

    Then workspace creation should fail with conflict

Deleting a missing workload via the workspace endpoint returns 404
    [Documentation]    Verify that the workspace-scoped delete endpoint returns 404 for a
    ...    workload id that does not exist. The service-level type-guard is covered by
    ...    test_delete_development_workspace_rejects_non_workspace.
    [Tags]    workspace    delete    negative

    Given a ready project with user access exists

    When deleting workspace by missing workload id is attempted    00000000-0000-0000-0000-000000000000

    Then workspace deletion should report workspace not found
