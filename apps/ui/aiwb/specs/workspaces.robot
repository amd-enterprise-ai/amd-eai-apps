# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for workspace catalog browsing and deployment.
...
...                 These tests verify that users can see workspace cards in the catalog,
...                 deploy workspaces, see launch buttons for running deployments,
...                 verify workspace status display, access links, and termination flow.
...
...                 Tests use API calls for setup (deploying workspaces via backend)
...                 and then verify the UI renders them correctly.
...
...                 Multi-User Testing:
...                 Tests that verify access boundaries create temporary users via the AIRM API
...                 (POST /v1/users), which registers them in both Keycloak and the AIRM database
...                 and assigns them to the test project. Temporary users are deleted in Suite Teardown.
...                 Requires: platform-admin permissions on the AIRM API (kubeconfig/OIDC credentials).

# UI resources (feature layer + browser setup)
Resource            resources/common/browser_setup.resource
Resource            resources/workspaces.resource

# API resources (infrastructure preconditions, resolved via pythonpath)
Resource            resources/aiwb_workspaces.resource
Resource            resources/airm_projects.resource
Resource            resources/airm_secrets.resource

Library             TestPrefix

Suite Teardown      Run Keywords    Clean Up Temporary Users    AND    Clean Up All Created AIWB Secrets
...                 AND    Clean Up Workspace Test Resources
Test Setup          Open test browser
Test Teardown       Run Keywords    Close test browser    AND    Clean Up Workspaces Only


*** Test Cases ***
Workspace catalog displays available workspace templates
    [Documentation]    Verify that the workspace catalog page loads and displays
    ...                available workspace template cards (JupyterLab, MLflow, VSCode, ComfyUI).
    ...                Tests catalog UI rendering without requiring deployments.
    [Tags]    ui    workspace    catalog    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on workspaces page
    Then workspace catalog should display cards
    And workspace cards should show deploy button

Workspace deployment begins with workspace settings
    [Documentation]    Verify that starting a deployment presents the selected workspace
    ...                details and image settings without an intermediate empty wizard.
    [Tags]    ui    workspace    catalog    deploy    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on workspaces page
    When user starts deploying a workspace "JupyterLab"
    Then workspace deployment settings should be available

Namespace-scoped workspace shows launch button when running
    [Documentation]    Verify that a logged-in user can see a Launch button for a deployed
    ...                namespace-scoped workspace.
    ...                This tests that an MLflow workspace (namespace scope) is rendered in the UI
    ...                with a usable Launch action once it is running.
    [Tags]    ui    workspace    mlflow    sharing    launch

    # API setup: deploy a namespace-scoped (MLflow) workspace
    ${project_name}=    Test Name    mlflow-workspace
    Given a ready project "${project_name}" with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And MLflow workspace is deployed
    And workspace transitions to "Running"

    # UI verification: navigate and check for launch button
    When user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on workspaces page
    Then workspace should display launch button on card
    And workspace launch button should be clickable

Namespace-scoped workspace is visible and launchable by all users in namespace
    [Documentation]    Verify that namespace-scoped workspaces are visible and launchable
    ...                by all users in the same project/namespace, not just the creator.
    ...                MLflow workspaces are project-scoped and shared across all users with
    ...                project access. This tests that User A and User B can both see and
    ...                launch the same MLflow workspace.
    [Tags]    ui    workspace    mlflow    sharing    multi-user

    # Setup: Create namespace-scoped workspace as current user (User A)
    ${project_name}=    Test Name    mlflow-shared-workspace
    Given a ready project "${project_name}" with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And MLflow workspace is deployed
    And workspace transitions to "Running"

    # Verify User A can see and launch the workspace
    When user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on workspaces page
    Then workspace should display launch button on card
    And workspace launch button should be clickable

    # Verify multi-user access: User B should also see and launch the same workspace
    When different user logs in to project
    And project "${TEST_PROJECT}[name]" is selected
    And user is on workspaces page
    Then workspace should display launch button on card
    And workspace launch button should be clickable

User-scoped workspace shows launch button when created by current user
    [Documentation]    Verify that users can see a Launch button for a deployed user-scoped workspace
    ...                that they created. User-scoped workspaces (JupyterLab, VSCode, ComfyUI)
    ...                are only visible to the user who created them.
    ...                Tests: UI correctly displays user-scoped running workspace with Launch action
    [Tags]    ui    workspace    jupyterlab    user-scoped    launch

    # API setup: deploy a user-scoped (JupyterLab) workspace
    ${project_name}=    Test Name    jupyterlab-workspace
    Given a ready project "${project_name}" with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And JupyterLab workspace is deployed    gpus=0
    And workspace transitions to "Running"

    # UI verification: navigate and check for launch button
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on workspaces page
    Then user-scoped workspace should display launch button on card
    And workspace launch button should be clickable

User-scoped workspace is hidden from other users
    [Documentation]    Verify that user-scoped workspaces are only visible to the user
    ...                who created them, not to other users in the same project.
    ...                Tests the access boundary: a workspace created by User A should not
    ...                be visible to User B, even if User B has project access.
    [Tags]    ui    workspace    jupyterlab    access-control    security

    # Setup: Create workspace as current user (User A)
    ${project_name}=    Test Name    user-scope-boundary
    Given a ready project "${project_name}" with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And JupyterLab workspace is deployed    gpus=0
    And workspace transitions to "Running"

    # Verify User A can see the workspace
    When user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on workspaces page
    Then user-scoped workspace should display launch button on card

    # Verify access boundary: User B should NOT see the workspace
    When different user logs in to project
    And project "${TEST_PROJECT}[name]" is selected
    And user is on workspaces page
    Then user-scoped workspace should not be visible

Request workspace card links user to support mailto
    [Documentation]    Verify that the workspace catalog page shows a "Request workspace"
    ...                card linking to the support mailbox so users can ask for missing
    ...                workspace templates.
    [Tags]    ui    workspace    catalog    request    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on workspaces page
    Then request workspace card should link to support mailto

Deploy workspace through catalog UI
    [Documentation]    Verify that a user can deploy a workspace by selecting a type
    ...                from the catalog and submitting the deployment form.
    [Tags]    ui    workspaces    deploy    gpu

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on workspace catalog page
    When user deploys a workspace "JupyterLab"
    And user navigates to the workspace list
    Then workspace should appear in the workspace list

Workspace deployed without a custom name shows its catalog name on the dashboard
    [Documentation]    Verify that when a user deploys a workspace from the catalog without
    ...                typing a custom name, the dashboard workloads table lists it by the
    ...                human-readable catalog name rather than an autogenerated identifier.
    [Tags]    ui    workspaces    deploy    display-name    gpu

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on workspace catalog page
    When user deploys a workspace "JupyterLab"
    And user navigates to the workspace list
    Then workspace should be listed by its catalog name "JupyterLab"

Workspace deployed with several image pull secrets uses every selected credential
    [Documentation]    Verify that a user can choose more than one private-registry credential,
    ...                by the name they gave it, when deploying a workspace, and that the
    ...                workspace is given every credential they chose.
    [Tags]    ui    workspaces    secrets    deploy    kubectl    gpu

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And image pull secrets "registry-a" and "registry-b" exist in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on workspace catalog page
    When user deploys a workspace "JupyterLab" with image pull secrets "registry-a" and "registry-b"
    Then the workspace should use image pull secrets "registry-a" and "registry-b"

View workspace status in UI
    [Documentation]    Verify that a deployed workspace shows its current status
    ...                in the workloads list on the dashboard.
    [Tags]    ui    workspaces    status

    ${workspace_name}=    Test Name    jupyter
    Given a ready project with user access exists
    And JupyterLab workspace is deployed    display_name=${workspace_name}    gpus=0
    And workspace name is "${workspace_name}"
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on dashboard page
    Then workspace should appear in the workspace list
    And workspace status should be displayed

Open workspace link from UI
    [Documentation]    Verify that a running workspace provides an access link
    ...                that the user can open from the dashboard.
    [Tags]    ui    workspaces    access    gpu

    ${workspace_name}=    Test Name    jupyter
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And JupyterLab workspace is deployed    display_name=${workspace_name}    gpus=1
    And workspace transitions to "Running"
    And workspace name is "${workspace_name}"
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on dashboard page
    Then workspace should appear in the workspace list
    And workspace should have an access link

Terminate workspace from UI
    [Documentation]    Verify that a user can terminate a running workspace through the UI
    ...                actions menu, that the confirmation names the workspace being removed
    ...                so multiple workspaces aren't ambiguous, and that it is removed from the list.
    [Tags]    ui    workspaces    delete    gpu

    ${workspace_name}=    Test Name    jupyter
    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And JupyterLab workspace is deployed    display_name=${workspace_name}    gpus=1
    And workspace transitions to "Running"
    And workspace name is "${workspace_name}"
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on dashboard page
    And workspace should appear in the workspace list
    When user opens the undeploy confirmation for the workspace
    Then undeploy confirmation should name the workspace
    When user confirms the undeploy
    Then workspace should be removed from the list
