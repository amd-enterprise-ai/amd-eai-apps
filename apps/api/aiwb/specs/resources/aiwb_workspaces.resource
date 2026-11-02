# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level workspace testing keywords.
...                 Provides business-logic level keywords for testing workspace operations.
...                 Uses the low-level API keywords from api/workspaces.resource to implement
...                 higher-level testing scenarios for JupyterLab, MLflow, VS Code, and ComfyUI workspaces.
Resource            api/workspaces.resource
Resource            api/workloads.resource
Resource            resources/airm_projects.resource
Resource            resources/resource_tracking.resource
Resource            resources/common/resource_lifecycle.resource
Resource            aiwb_common.resource
Library             Collections
Library             String
Library             RequestsLibrary


*** Variables ***
${TEST_WORKSPACE_ID}        ${None}
# CREATED_WORKLOAD_IDS is lazy-initialized by Track Workload For Cleanup (workspaces are workloads)


*** Keywords ***
JupyterLab workspace is deployed
    [Documentation]    Deploys a JupyterLab workspace via AIWB API
    ...    Uses default configuration: 1 GPU, standard image
    [Arguments]    ${display_name}=test-jupyter    ${gpus}=1    ${image}=${None}

    ${workspace_data}=    Create Dictionary
    ...    gpus=${gpus}
    ...    memoryPerGpu=128
    ...    cpuPerGpu=4
    # Omit image when the caller didn't pass one so the server applies the chart's
    # default workspace image (matching the UI) rather than pinning a stale tag.
    IF    $image is not None
        Set To Dictionary    ${workspace_data}    image=${image}
    END

    ${namespace}=    Get Project Namespace
    ${response}=    Create workspace
    ...    workspace_type=jupyterlab
    ...    workspace_data=${workspace_data}
    ...    project_id=${TEST_PROJECT_ID}
    ...    display_name=${display_name}
    ...    namespace=${namespace}
    ...    expected_status=201

    ${workspace_id}=    Get From Dictionary    ${response.json()}    id
    VAR    ${TEST_WORKSPACE_ID}    ${workspace_id}    scope=TEST

    Track Workload For Cleanup    ${workspace_id}

    Log    Created JupyterLab workspace ${workspace_id} with name: ${display_name}    INFO

JupyterLab workspace is deployed with custom image
    [Documentation]    Deploys JupyterLab workspace with specified container image
    [Arguments]    ${image}    ${gpus}=0

    JupyterLab workspace is deployed    image=${image}    gpus=${gpus}

JupyterLab workspace is deployed with GPU allocation
    [Documentation]    Deploys JupyterLab workspace with specified GPU count
    [Arguments]    ${gpus}

    JupyterLab workspace is deployed    gpus=${gpus}

MLflow workspace is deployed
    [Documentation]    Deploys an MLflow workspace via AIWB API
    ...    MLflow is project-scoped - only one can be Running/Pending per project
    [Arguments]    ${display_name}=test-mlflow

    ${workspace_data}=    Create Dictionary
    ...    gpus=0
    ...    memoryPerGpu=20
    ...    cpuPerGpu=1

    ${namespace}=    Get Project Namespace
    ${response}=    Create workspace
    ...    workspace_type=mlflow
    ...    workspace_data=${workspace_data}
    ...    project_id=${TEST_PROJECT_ID}
    ...    display_name=${display_name}
    ...    namespace=${namespace}
    ...    expected_status=201

    ${workspace_id}=    Get From Dictionary    ${response.json()}    id
    VAR    ${TEST_WORKSPACE_ID}    ${workspace_id}    scope=TEST

    Track Workload For Cleanup    ${workspace_id}

    Log    Created MLflow workspace ${workspace_id} with name: ${display_name}    INFO

VSCode workspace is deployed
    [Documentation]    Deploys a VSCode workspace via AIWB API
    ...    Uses default configuration: 1 GPU, standard image
    [Arguments]    ${display_name}=test-vscode    ${gpus}=1    ${image}=${None}

    ${workspace_data}=    Create Dictionary
    ...    gpus=${gpus}
    ...    memoryPerGpu=128
    ...    cpuPerGpu=4
    # Omit image when the caller didn't pass one so the server applies the chart's
    # default workspace image (matching the UI) rather than pinning a stale tag.
    IF    $image is not None
        Set To Dictionary    ${workspace_data}    image=${image}
    END

    ${namespace}=    Get Project Namespace
    ${response}=    Create workspace
    ...    workspace_type=vscode
    ...    workspace_data=${workspace_data}
    ...    project_id=${TEST_PROJECT_ID}
    ...    display_name=${display_name}
    ...    namespace=${namespace}
    ...    expected_status=201

    ${workspace_id}=    Get From Dictionary    ${response.json()}    id
    VAR    ${TEST_WORKSPACE_ID}    ${workspace_id}    scope=TEST

    Track Workload For Cleanup    ${workspace_id}

    Log    Created VSCode workspace ${workspace_id} with name: ${display_name}    INFO

ComfyUI workspace is deployed
    [Documentation]    Deploys a ComfyUI workspace via AIWB API
    ...    Uses default configuration: 1 GPU, standard image
    ...    ComfyUI requires a GPU to start, so the default is 1.
    [Arguments]    ${display_name}=test-comfyui    ${gpus}=1    ${image}=${None}

    ${workspace_data}=    Create Dictionary
    ...    gpus=${gpus}
    ...    memoryPerGpu=128
    ...    cpuPerGpu=4
    # Omit image when the caller didn't pass one so the server applies the chart's
    # default workspace image (matching the UI) rather than pinning a stale tag.
    IF    $image is not None
        Set To Dictionary    ${workspace_data}    image=${image}
    END

    ${namespace}=    Get Project Namespace
    ${response}=    Create workspace
    ...    workspace_type=comfyui
    ...    workspace_data=${workspace_data}
    ...    project_id=${TEST_PROJECT_ID}
    ...    display_name=${display_name}
    ...    namespace=${namespace}
    ...    expected_status=201

    ${workspace_id}=    Get From Dictionary    ${response.json()}    id
    VAR    ${TEST_WORKSPACE_ID}    ${workspace_id}    scope=TEST

    Track Workload For Cleanup    ${workspace_id}

    Log    Created ComfyUI workspace ${workspace_id} with name: ${display_name}    INFO

Attempting to deploy second MLflow workspace
    [Documentation]    Attempts to deploy a second MLflow workspace (should fail with 409)
    ${workspace_data}=    Create Dictionary
    ...    gpus=0
    ...    memoryPerGpu=20
    ...    cpuPerGpu=1

    ${namespace}=    Get Project Namespace
    ${response}=    Create workspace
    ...    workspace_type=mlflow
    ...    workspace_data=${workspace_data}
    ...    project_id=${TEST_PROJECT_ID}
    ...    display_name=test-mlflow-2
    ...    namespace=${namespace}
    ...    expected_status=409

    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Attempting to deploy second JupyterLab workspace
    [Documentation]    Attempts to deploy a second JupyterLab workspace (should fail with 409)
    ${workspace_data}=    Create Dictionary
    ...    image=rocm/pytorch:rocm6.4_ubuntu24.04_py3.12_pytorch_release_2.6.0
    ...    gpus=0
    ...    memoryPerGpu=128
    ...    cpuPerGpu=4

    ${namespace}=    Get Project Namespace
    ${response}=    Create workspace
    ...    workspace_type=jupyterlab
    ...    workspace_data=${workspace_data}
    ...    project_id=${TEST_PROJECT_ID}
    ...    display_name=jupyter-2
    ...    namespace=${namespace}
    ...    expected_status=any

    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Attempting to deploy second VSCode workspace
    [Documentation]    Attempts to deploy a second VSCode workspace (should fail with 409)
    ${workspace_data}=    Create Dictionary
    ...    image=rocm/pytorch:rocm6.4_ubuntu24.04_py3.12_pytorch_release_2.6.0
    ...    gpus=0
    ...    memoryPerGpu=128
    ...    cpuPerGpu=4

    ${namespace}=    Get Project Namespace
    ${response}=    Create workspace
    ...    workspace_type=vscode
    ...    workspace_data=${workspace_data}
    ...    project_id=${TEST_PROJECT_ID}
    ...    display_name=vscode-2
    ...    namespace=${namespace}
    ...    expected_status=any

    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Attempting to deploy second ComfyUI workspace
    [Documentation]    Attempts to deploy a second ComfyUI workspace (should fail with 409)
    ${workspace_data}=    Create Dictionary
    ...    image=rocm/pytorch:rocm6.4_ubuntu24.04_py3.12_pytorch_release_2.6.0
    ...    gpus=0
    ...    memoryPerGpu=128
    ...    cpuPerGpu=4

    ${namespace}=    Get Project Namespace
    ${response}=    Create workspace
    ...    workspace_type=comfyui
    ...    workspace_data=${workspace_data}
    ...    project_id=${TEST_PROJECT_ID}
    ...    display_name=comfyui-2
    ...    namespace=${namespace}
    ...    expected_status=any

    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Workspace should be visible via API
    [Documentation]    Verifies that the workspace is visible via AIWB workloads API
    ...    Polls for workspace to appear in database to handle async operations
    Should Not Be Equal    ${TEST_WORKSPACE_ID}    ${None}    msg=TEST_WORKSPACE_ID not set. Deploy workspace first.

    Wait Until Keyword Succeeds    10 sec    1 sec
    ...    Workspace is in database

    Log    Workspace ${TEST_WORKSPACE_ID} is visible via API    INFO

Workspace is in database
    [Documentation]    Verifies workspace exists in database via AIWB workloads API
    ...    Used with polling to wait for async workspace creation
    ${namespace}=    Get Project Namespace
    ${response}=    Get AIWB workload    ${TEST_WORKSPACE_ID}    namespace=${namespace}    expected_status=200
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Workspace should have valid ID and status
    [Documentation]    Verifies workspace response contains valid id and status fields
    Should Not Be Equal    ${TEST_RESPONSE}    ${None}    msg=Response not set. Call 'workspace should be visible via API' first.

    VAR    ${json}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    id
    Dictionary Should Contain Key    ${json}    status

    ${workspace_id}=    Get From Dictionary    ${json}    id
    ${status}=    Get From Dictionary    ${json}    status

    Log    Workspace has valid ID: ${workspace_id}, Status: ${status}    INFO

Workspace status should be "${expected_status}"
    [Documentation]    Verifies the workspace has the expected status by fetching fresh state
    ...    Always fetches current workspace state using TEST_WORKSPACE_ID
    ...    For checking immediate API response, use 'Workspace status should be "${status}" in response'
    Should Not Be Equal    ${TEST_WORKSPACE_ID}    ${None}
    ...    msg=TEST_WORKSPACE_ID not set. Deploy workspace first.

    ${namespace}=    Get Project Namespace
    Verify Resource Status    Get AIWB workload    ${TEST_WORKSPACE_ID}    ${expected_status}    namespace=${namespace}

Workspace transitions to "${expected_status}"
    [Documentation]    Waits for workspace to transition to expected status
    ...    Polls the workspace endpoint until status becomes expected value
    ...    Timeout: 20 min (MLflow downloads large models and installs dependencies)
    ${namespace}=    Get Project Namespace
    Wait For Resource Status    Get AIWB workload    ${TEST_WORKSPACE_ID}    ${expected_status}    timeout=20 min    interval=10 sec    namespace=${namespace}

Verify workspace has status "${expected_status}"
    [Documentation]    Helper keyword to verify workspace status (used with polling)
    ${namespace}=    Get Project Namespace
    Verify Resource Status    Get AIWB workload    ${TEST_WORKSPACE_ID}    ${expected_status}    namespace=${namespace}

Workspace should have access URL
    [Documentation]    Verifies workspace has external_host and internal_host set
    ...    Polls for URLs to be populated as they may take a few seconds after Running status
    Should Not Be Equal    ${TEST_WORKSPACE_ID}    ${None}
    ...    msg=TEST_WORKSPACE_ID not set. Deploy workspace first.

    # Poll for URLs to be populated (may take a few seconds after Running)
    Wait Until Keyword Succeeds    30 sec    2 sec
    ...    Verify workspace has URLs populated

Verify workspace has URLs populated
    [Documentation]    Helper keyword to verify workspace URLs are set (used with polling)
    ...    AIWB uses computed 'endpoints' field with 'external' and 'internal' keys
    ${namespace}=    Get Project Namespace
    ${workspace_response}=    Get AIWB workload    ${TEST_WORKSPACE_ID}    namespace=${namespace}    expected_status=200
    VAR    ${json}    ${workspace_response.json()}

    # URLs are in the 'endpoints' computed field
    Dictionary Should Contain Key    ${json}    endpoints    msg=Workload should have endpoints field
    ${endpoints}=    Get From Dictionary    ${json}    endpoints
    Should Not Be Equal    ${endpoints}    ${None}    msg=Workload endpoints should not be None

    Dictionary Should Contain Key    ${endpoints}    internal    msg=Endpoints should contain internal URL
    ${internal_url}=    Get From Dictionary    ${endpoints}    internal
    Should Not Be Empty    ${internal_url}    msg=internal endpoint should not be empty

    # External URL may not be present if HTTPRoute is not yet created
    ${has_external}=    Evaluate    'external' in $endpoints
    IF    ${has_external}
        ${external_url}=    Get From Dictionary    ${endpoints}    external
        Log    Workspace access URLs - External: ${external_url}, Internal: ${internal_url}    INFO
    ELSE
        Log    Workspace access URLs - Internal: ${internal_url} (external not yet available)    INFO
    END

Workspace external URL should be accessible
    [Documentation]    Verifies that the workspace external URL is reachable and routed correctly.
    ...    The URL must be served on a dedicated workspaces.<domain> host (so it is not
    ...    shadowed by the inference-only workloads.<domain> vhost) and must not 404
    ...    (the regression this guards against). Auth challenges (401/403) and redirects
    ...    are accepted; connection errors, 404, and server errors (500+) fail.
    Should Not Be Equal    ${TEST_WORKSPACE_ID}    ${None}
    ...    msg=TEST_WORKSPACE_ID not set. Deploy workspace first.

    # Get the external URL from workspace endpoints
    ${namespace}=    Get Project Namespace
    ${workspace_response}=    Get AIWB workload    ${TEST_WORKSPACE_ID}    namespace=${namespace}    expected_status=200
    VAR    ${json}    ${workspace_response.json()}
    ${endpoints}=    Get From Dictionary    ${json}    endpoints
    Dictionary Should Contain Key    ${endpoints}    external    msg=Workspace should have external endpoint URL
    ${external_url}=    Get From Dictionary    ${endpoints}    external

    # The route must be pinned to the dedicated workspaces.<domain> host.
    Should Contain    ${external_url}    //workspaces.
    ...    msg=Workspace external URL ${external_url} is not on a workspaces.<domain> host

    # Make HTTP request - allow redirects and don't verify SSL for internal testing
    ${http_response}=    GET    ${external_url}    expected_status=any    verify=${VERIFY_SSL}

    # Reject 404 (the routing regression) and server errors; auth/redirects are fine.
    VAR    ${status}    ${http_response.status_code}
    Should Not Be Equal As Integers    ${status}    404
    ...    msg=Workspace URL returned 404 - route not matched (regression)
    Should Be True    ${status} < 500
    ...    msg=Workspace URL returned server error ${status}, expected < 500

    Log    Workspace external URL is accessible: ${external_url} (HTTP ${status})    INFO

Workspace is deleted
    [Documentation]    Deletes the workspace via AIWB DELETE /projects/{project}/workspaces/{id}
    Should Not Be Equal    ${TEST_WORKSPACE_ID}    ${None}    msg=TEST_WORKSPACE_ID not set. Deploy workspace first.

    ${namespace}=    Get Project Namespace
    ${response}=    Delete workspace    ${TEST_WORKSPACE_ID}    namespace=${namespace}    expected_status=204

    Log    Deleted workspace ${TEST_WORKSPACE_ID} via API    INFO

Workspace should not be visible via API
    [Documentation]    Verifies that the workspace has status "Deleted" via AIWB workloads API
    ...    Polls until workspace deletion is complete (soft delete with status=Deleted)
    ...    Timeout: 10 min (workspaces involve Kubernetes resource cleanup)
    ...
    ...    Note: Workspaces use soft delete - records remain in database with status=Deleted
    Should Not Be Equal    ${TEST_WORKSPACE_ID}    ${None}    msg=TEST_WORKSPACE_ID not set.

    Log    Waiting for workspace ${TEST_WORKSPACE_ID} deletion to complete    INFO
    ${namespace}=    Get Project Namespace
    Wait For Resource Status    Get AIWB workload    ${TEST_WORKSPACE_ID}    Deleted    timeout=10 min    interval=10 sec    namespace=${namespace}
    Log    Workspace ${TEST_WORKSPACE_ID} has status Deleted    INFO

Verify workspace is fully deleted
    [Documentation]    Helper to verify workspace has status "Deleted" (soft delete)
    ${namespace}=    Get Project Namespace
    Verify Resource Status    Get AIWB workload    ${TEST_WORKSPACE_ID}    Deleted    namespace=${namespace}

Workspace creation should fail with conflict
    [Documentation]    Verifies that workspace creation failed with 409 Conflict
    VAR    ${status_code}    ${TEST_RESPONSE.status_code}
    Should Be Equal As Integers    ${status_code}    409
    ...    msg=Expected 409 Conflict, but got ${status_code}

    Log    Workspace creation correctly failed with 409 Conflict    INFO

Deleting workspace by missing workload id is attempted
    [Documentation]    Attempts to delete via the workspace-typed endpoint using an id that
    ...    does not correspond to any workload, expecting a 404 response.
    [Arguments]    ${workload_id}
    ${namespace}=    Get Project Namespace
    ${response}=    Delete workspace    ${workload_id}    namespace=${namespace}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Workspace deletion should report workspace not found
    [Documentation]    Verifies that the response is 404 with a workspace-specific not-found error
    VAR    ${status_code}    ${TEST_RESPONSE.status_code}
    Should Be Equal As Integers    ${status_code}    404
    ...    msg=Expected 404 Not Found, but got ${status_code}

"${count}" workspaces of type "${workspace_type}" should be visible in project
    [Documentation]    Verifies that the specified number of workspaces are visible in the namespace
    ...    Only counts non-deleted workspaces (excludes Deleting/Deleted status)
    ${count_int}=    Convert To Integer    ${count}

    # Get all workloads filtered by type via AIWB API
    ${namespace}=    Get Project Namespace
    ${response}=    Get AIWB workloads
    ...    namespace=${namespace}
    ...    workload_type=${workspace_type}
    ...    expected_status=200

    # Extract data field from response (ListResponse has 'data' key)
    VAR    ${response_json}    ${response.json()}
    ${all_workspaces}=    Get From Dictionary    ${response_json}    data

    # Filter out workspaces with Deleting or Deleted status
    ${active_workspaces}=    Create List
    FOR    ${workspace}    IN    @{all_workspaces}
        ${status}=    Get From Dictionary    ${workspace}    status
        IF    "${status}" not in ["Deleting", "Deleted"]
            Append To List    ${active_workspaces}    ${workspace}
        END
    END

    ${actual_count}=    Get Length    ${active_workspaces}

    Should Be Equal As Integers    ${actual_count}    ${count_int}
    ...    msg=Expected ${count_int} ${workspace_type} workspaces, found ${actual_count}

    Log    Found ${actual_count} ${workspace_type} workspaces in namespace    INFO

Clean Up Workspace Test Resources
    [Documentation]    Clean up all resources created during workspace tests.
    ...    Uses the workspaces capability endpoint for cleanup (the generic /workloads
    ...    DELETE was removed), then cleans up projects.
    ${tracking_list}=    Get Variable Value    ${CREATED_WORKLOAD_IDS}    ${None}
    ${count}=    Evaluate    len($tracking_list) if $tracking_list is not None else 0
    IF    ${count} > 0
        Log    Cleaning up ${count} workspace(s) via AIWB API    INFO
        ${namespace}=    Get Project Namespace
        FOR    ${workload_id}    IN    @{tracking_list}
            TRY
                Delete workspace    ${workload_id}    namespace=${namespace}    expected_status=any
                Log    Deleted workspace ${workload_id}    INFO
            EXCEPT    AS    ${error}
                Log    Failed to delete workspace ${workload_id}: ${error}    WARN
            END
        END
        VAR    @{empty_list}    @{EMPTY}    scope=SUITE
        VAR    ${CREATED_WORKLOAD_IDS}    ${empty_list}    scope=SUITE
    END
    Clean Up All Created Projects
