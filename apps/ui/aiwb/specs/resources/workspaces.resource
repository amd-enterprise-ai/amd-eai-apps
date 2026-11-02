# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for workspace UI features.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)
Resource            common/session.resource
Resource            pages/workspaces_page.resource
Resource            resources/aiwb_workspaces.resource
Resource            resources/aiwb_secrets.resource
Library             Collections
Library             Process
Library             ../libraries/TemporaryUserManager.py
Library             TestPrefix

*** Variables ***
${TEST_WORKSPACE_NAME}          ${None}
&{TEST_IMAGE_PULL_SECRETS}      &{EMPTY}


*** Keywords ***
User is on workspaces page
    [Documentation]    Navigates to the Workspaces page via sidebar link to preserve project context.
    ...                Waits for the workspace catalog to load.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate To Workspaces Page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

User is on workspace catalog page
    [Documentation]    Navigates to the Workspaces catalog page.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to workspaces page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

User is on dashboard page
    [Documentation]    Navigates to the Dashboard page showing workloads.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to dashboard page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

Workspace name is "${workspace_name}"
    [Documentation]    Sets the workspace display name for UI verification keywords.
    ...                Used to bridge API-created workspaces to UI assertions.

    VAR    ${TEST_WORKSPACE_NAME}    ${workspace_name}    scope=TEST

User deploys a workspace "${workspace_type}"
    [Documentation]    Deploys a workspace of the specified type through the catalog UI.
    ...                Opens the deploy wizard, captures the default name, submits,
    ...                and tracks the workspace for cleanup via API.

    Click deploy button on workspace card    ${workspace_type}
    Wait for deploy wizard
    Submit workspace deployment from the settings step

User deploys a workspace "${workspace_type}" with image pull secrets "${first}" and "${second}"
    [Documentation]    Deploys a workspace through the catalog UI, choosing both image pull
    ...                secrets by the display names the user gave them.
    ...                Requires: the secrets to exist (see "Image pull secrets ... exist in the project")

    Click deploy button on workspace card    ${workspace_type}
    Wait for deploy wizard
    Open image pull secrets dropdown
    FOR    ${name}    IN    ${first}    ${second}
        ${display_name}=    Test Name    ${name}
        Select image pull secret option    ${display_name}
    END
    Close image pull secrets dropdown
    Submit workspace deployment from the settings step

Submit workspace deployment from the settings step
    [Documentation]    Advances past the settings step, captures the default workload name,
    ...                submits, and tracks the workspace for cleanup via API.
    ...                Sets: TEST_WORKSPACE_NAME

    Advance deploy wizard
    ${name}=    Get deploy wizard workload name
    VAR    ${TEST_WORKSPACE_NAME}    ${name}    scope=TEST
    Submit deploy wizard
    Wait for deploy wizard to close
    Track UI deployed workspace    ${name}

Image pull secrets "${first}" and "${second}" exist in the project
    [Documentation]    Creates two image pull secrets via the AIWB API and records each one's
    ...                Kubernetes name against its display name for later verification.
    ...                Sets: TEST_IMAGE_PULL_SECRETS (display name -> Kubernetes secret name)

    VAR    &{pull_secrets}    &{EMPTY}
    FOR    ${name}    IN    ${first}    ${second}
        A secret "${name}" with use case "ImagePullSecret" is created via AIWB
        Set To Dictionary    ${pull_secrets}    ${TEST_AIWB_SECRET_NAME}=${TEST_AIWB_SECRET_K8S_NAME}
    END
    VAR    &{TEST_IMAGE_PULL_SECRETS}    &{pull_secrets}    scope=TEST

User starts deploying a workspace "${workspace_type}"
    [Documentation]    Opens the deployment flow for the selected workspace type.

    Click deploy button on workspace card    ${workspace_type}

Workspace deployment settings should be available
    [Documentation]    Verifies that the selected workspace details and image settings are available.

    Wait for deploy wizard settings

User navigates to the workspace list
    [Documentation]    Navigates to the Dashboard to view workloads including workspaces.

    Navigate to dashboard page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

User opens the undeploy confirmation for the workspace
    [Documentation]    Opens the delete confirmation modal for the workspace via the actions menu.
    ...                Expects ${TEST_WORKSPACE_NAME} to be set.

    Should Not Be Equal    ${TEST_WORKSPACE_NAME}    ${None}
    ...    msg=TEST_WORKSPACE_NAME not set. Deploy a workspace first.
    Click workload actions menu    ${TEST_WORKSPACE_NAME}
    Click delete in actions menu

Undeploy confirmation should name the workspace
    [Documentation]    Verifies the open delete confirmation names the workspace being removed,
    ...                so the user isn't left guessing which workspace they are about to undeploy.

    ${confirmation_text}=    Get Delete Confirmation Modal Text
    Should Contain    ${confirmation_text}    ${TEST_WORKSPACE_NAME}
    ...    msg=Undeploy confirmation should name the workspace being removed

User confirms the undeploy
    [Documentation]    Confirms deletion in the currently open delete confirmation modal.

    Confirm delete in modal

Workspace catalog should display cards
    [Documentation]    Verifies that the workspace catalog displays workspace template cards.
    ...                Polls for cards to appear as UI rendering may take a moment.

    Wait Until Keyword Succeeds    30s    2s
    ...    Catalog Cards Should Be Visible

Catalog Cards Should Be Visible
    [Documentation]    Helper to verify catalog cards are visible.
    ...                Called by Wait Until Keyword Succeeds for polling.

    ${count}=    Check Workspace Catalog Has Cards
    Should Be True    ${count} > 0    msg=No workspace cards found on catalog page. Catalog may not have loaded.

Workspace cards should show deploy button
    [Documentation]    Verifies that workspace cards display Deploy buttons.
    ...                Checks that cards have the primary action button for deployment.

    Wait Until Keyword Succeeds    10s    2s
    ...    Deploy Buttons Should Be Visible

Deploy Buttons Should Be Visible
    [Documentation]    Helper to verify deploy buttons exist.
    ...                Called by Wait Until Keyword Succeeds for polling.

    ${count}=    Get Deploy Button Count
    Should Be True    ${count} > 0    msg=No Deploy buttons found on workspace cards.

Workspace should display launch button on card
    [Documentation]    Verifies that the workspace card displays a Launch button (ready action).
    ...                This button only appears when the workspace status is Running.
    ...                Polls for the button to appear as UI rendering may take a moment.

    Wait Until Keyword Succeeds    30s    2s
    ...    Launch Button Should Be Present

Launch Button Should Be Present
    [Documentation]    Helper to verify launch button is visible.
    ...                Called by Wait Until Keyword Succeeds for polling.

    ${count}=    Get Launch Button Count
    Should Be True    ${count} > 0    msg=No Launch button found on workspace cards. Workspace may not be in Running status.

Workspace launch button should be clickable
    [Documentation]    Verifies that the workspace launch button is in a clickable state.
    ...                Checks that the button is visible and enabled.

    Wait For Launch Button Enabled

User-scoped workspace should display launch button on card
    [Documentation]    Verifies that a user-scoped workspace card displays a Launch button.
    ...                User-scoped workspaces are only visible to their creator.
    ...                Polls for the button to appear as UI rendering may take a moment.

    Wait Until Keyword Succeeds    30s    2s
    ...    Launch Button Should Be Present

User-scoped workspace should not be visible
    [Documentation]    Verifies that a user-scoped workspace deployment is not accessible to other users.
    ...                This tests access boundaries: when a new user (who has never deployed anything)
    ...                logs in, they should see the template catalog but have no Launch buttons
    ...                showing running deployments created by other users.

    ${count}=    Get Launch Button Count
    Should Be Equal As Integers    ${count}    0    msg=Expected no running deployments visible, but found ${count} Launch buttons. Access boundary may not be enforced.

Request workspace card should link to support mailto
    [Documentation]    Verifies the "Request workspace" card exposes a support mailto link
    ...                with the expected subject. Clicking a mailto cannot be verified
    ...                end-to-end in the browser, so we assert the anchor target instead.

    ${href}=    Get Request Workspace Card Mailto Href
    Should Start With    ${href}    mailto:amd-eai-support@amd.com
    Should Contain    ${href}    subject=Workspace%20request

Workspace should appear in the workspace list
    [Documentation]    Verifies the workspace appears in the dashboard workloads grid.
    ...                Polls with retry since the workspace may take time to appear.

    Should Not Be Equal    ${TEST_WORKSPACE_NAME}    ${None}
    ...    msg=TEST_WORKSPACE_NAME not set. Deploy a workspace first.
    Wait Until Keyword Succeeds    30s    5s
    ...    Workload row should exist    ${TEST_WORKSPACE_NAME}

Workspace should be listed by its catalog name "${catalog_name}"
    [Documentation]    Verifies the dashboard workloads table shows the deployed workspace by
    ...                the human-readable catalog name (e.g. "JupyterLab") rather than an
    ...                autogenerated identifier.
    ...                Expects ${TEST_WORKSPACE_NAME} to hold the name the workspace was
    ...                deployed under so it can be located and tracked.

    Should Not Be Equal    ${TEST_WORKSPACE_NAME}    ${None}
    ...    msg=TEST_WORKSPACE_NAME not set. Deploy a workspace first.
    Wait Until Keyword Succeeds    30s    5s
    ...    Workload row should exist    ${catalog_name}
    IF    "${catalog_name}" != "${TEST_WORKSPACE_NAME}"
        Workload row should not exist    ${TEST_WORKSPACE_NAME}
    END

The workspace should use image pull secrets "${first}" and "${second}"
    [Documentation]    Verifies the deployed workspace's pods are configured with every one of
    ...                the selected registry credentials. Polls because the workload's Deployment
    ...                is created asynchronously after submission.
    ...                Requires: TEST_WORKSPACE_ID (set when the UI deployment is tracked),
    ...                TEST_IMAGE_PULL_SECRETS

    ${workload_id}=    Get Variable Value    ${TEST_WORKSPACE_ID}    ${None}
    Should Not Be Equal    ${workload_id}    ${None}
    ...    msg=TEST_WORKSPACE_ID not set. Deploy a workspace first.
    VAR    @{expected}    @{EMPTY}
    FOR    ${name}    IN    ${first}    ${second}
        ${display_name}=    Test Name    ${name}
        Append To List    ${expected}    ${TEST_IMAGE_PULL_SECRETS}[${display_name}]
    END
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    2 min    5s
    ...    Workload pods should reference image pull secrets    ${workload_id}    ${namespace}    @{expected}

Workload pods should reference image pull secrets
    [Documentation]    Helper: reads the workload's Deployments and checks their pod template
    ...                lists every expected image pull secret (used with polling). The cluster
    ...                may add its own registry credentials, so extra secrets are allowed.
    [Arguments]    ${workload_id}    ${namespace}    @{expected}

    ${result}=    Run Process    kubectl    get    deployments
    ...    -n    ${namespace}
    ...    -l    airm.silogen.ai/workload-id\=${workload_id}
    ...    -o    json
    ...    stderr=PIPE
    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to get Deployments for workload ${workload_id}: ${result.stderr}
    ${deployments}=    Evaluate    json.loads($result.stdout)['items']    modules=json
    Should Not Be Empty    ${deployments}
    ...    msg=No Deployment found yet for workload ${workload_id} in ${namespace}
    ${pod_specs}=    Evaluate    [d['spec']['template']['spec'] for d in $deployments]
    ${actual}=    Evaluate    sorted({s.get('name') or '' for p in $pod_specs for s in p.get('imagePullSecrets') or []})
    List Should Contain Sub List    ${actual}    ${expected}
    ...    msg=Workspace image pull secrets ${actual} are missing some of the selected ${expected}

Workspace status should be displayed
    [Documentation]    Verifies the workspace row shows a recognized status indicator.

    Should Not Be Equal    ${TEST_WORKSPACE_NAME}    ${None}
    ...    msg=TEST_WORKSPACE_NAME not set. Deploy a workspace first.
    ${status}=    Get workload status text    ${TEST_WORKSPACE_NAME}
    ${has_status}=    Evaluate
    ...    any(s in '''${status}''' for s in ['Running', 'Pending', 'Starting', 'Failed', 'Complete', 'Deleting'])
    Should Be True    ${has_status}
    ...    msg=Workspace should show a status indicator, got: ${status}

Workspace should have an access link
    [Documentation]    Verifies the running workspace provides an access link via the actions menu.
    ...                Opens the actions menu, checks for "Launch" or "Open" menu item, then closes.

    Should Not Be Equal    ${TEST_WORKSPACE_NAME}    ${None}
    ...    msg=TEST_WORKSPACE_NAME not set. Deploy a workspace first.
    Click workload actions menu    ${TEST_WORKSPACE_NAME}
    TRY
        ${menu_text}=    Get actions menu items text
        ${has_link}=    Evaluate
        ...    'Launch' in '''${menu_text}''' or 'Open' in '''${menu_text}'''
        Should Be True    ${has_link}
        ...    msg=Workspace actions menu should contain 'Launch' or 'Open', got: ${menu_text}
    FINALLY
        Close actions menu
    END

Workspace should be removed from the list
    [Documentation]    Verifies the workspace is no longer visible in the workloads grid.
    ...                Polls with retry since deletion may take time.

    Should Not Be Equal    ${TEST_WORKSPACE_NAME}    ${None}
    ...    msg=TEST_WORKSPACE_NAME not set. Deploy a workspace first.
    Wait Until Keyword Succeeds    10 min    15s
    ...    Verify workspace removed from list    ${TEST_WORKSPACE_NAME}

Verify workspace removed from list
    [Documentation]    Helper: reloads dashboard and checks workspace is gone or deleted (used with polling).
    [Arguments]    ${workspace_name}

    Reload
    VAR    ${grid}    css=[role="grid"]
    Wait For Elements State    ${grid}    visible    timeout=15s
    # Use fast existence check so the outer polling interval stays predictable
    VAR    ${workspace_row}    css=${grid} >> [role="row"]:has-text("${workspace_name}")
    ${row_count}=    Get Element Count    ${workspace_row}
    IF    ${row_count} > 0
        ${status}=    Get workload status text    ${workspace_name}
        Should Contain    ${status}    Deleted
        ...    msg=Workspace row still visible with status: ${status}
    END

Track UI deployed workspace
    [Documentation]    Finds a workspace by display name via API and tracks it for cleanup.
    ...    Called after UI deployment to ensure the workspace can be cleaned up between tests.
    [Arguments]    ${workspace_name}

    ${project}=    Get Variable Value    ${TEST_PROJECT}    ${None}
    IF    $project is None
        Log    Cannot track workspace: TEST_PROJECT not set    WARN
        RETURN
    END
    ${namespace}=    Get From Dictionary    ${project}    name
    TRY
        Wait Until Keyword Succeeds    30s    5s
        ...    Find and track workspace by name    ${workspace_name}    ${namespace}
    EXCEPT    AS    ${error}
        Log    Could not find workspace ${workspace_name} for tracking: ${error}    WARN
    END

Find and track workspace by name
    [Documentation]    Helper: lists workloads and tracks the one matching the display name.
    [Arguments]    ${workspace_name}    ${namespace}

    ${response}=    Get AIWB workloads    ${namespace}    expected_status=200
    ${workloads}=    Evaluate    $response.json().get('data', [])
    FOR    ${workload}    IN    @{workloads}
        ${name}=    Get From Dictionary    ${workload}    displayName    default=${EMPTY}
        IF    '${name}' == '${workspace_name}'
            ${workload_id}=    Get From Dictionary    ${workload}    id
            Track Workload For Cleanup    ${workload_id}
            VAR    ${TEST_WORKSPACE_ID}    ${workload_id}    scope=TEST
            Log    Tracked UI-deployed workspace: ${workload_id} (${workspace_name})    INFO
            RETURN
        END
    END
    Fail    Workspace ${workspace_name} not found in namespace ${namespace}

Clean Up Workspaces Only
    [Documentation]    Cleans up workspace workloads created during a test without deleting projects.
    ...    Sends delete requests and waits for full removal to avoid 409 conflicts
    ...    in the next test (only one JupyterLab allowed per project).

    ${tracking_list}=    Get Variable Value    ${CREATED_WORKLOAD_IDS}    ${None}
    ${count}=    Evaluate    len($tracking_list) if $tracking_list is not None else 0
    IF    ${count} > 0
        Log    Cleaning up ${count} workspace(s) via AIWB API    INFO
        ${project}=    Get Variable Value    ${TEST_PROJECT}    ${None}
        IF    $project is not None
            ${namespace}=    Get From Dictionary    ${project}    name
            FOR    ${workload_id}    IN    @{tracking_list}
                TRY
                    Delete AIWB workload    ${workload_id}    namespace=${namespace}    expected_status=any
                    # AIWB workspaces use soft delete (status transitions to Deleted)
                    Wait For Resource Status    Get AIWB workload    ${workload_id}    Deleted
                    ...    timeout=2 min    interval=5 sec    namespace=${namespace}
                    Log    Workspace ${workload_id} has status Deleted    INFO
                EXCEPT    AS    ${error}
                    Log    Workspace cleanup for ${workload_id} incomplete: ${error}    WARN
                END
            END
        END
        VAR    @{CREATED_WORKLOAD_IDS}    scope=SUITE
    END

# =============================================================================
# When keywords (user actions for multi-user scenarios)
# =============================================================================

Different user logs in to project
    [Documentation]    Creates a temporary user via AIRM API (registers in both Keycloak and AIRM DB,
    ...                assigns to current project), then logs out and logs in as that user.
    ...                After login, navigates directly to the project URL so the project selector
    ...                is populated without requiring the user to have a previous namespace context.
    ...                The temporary user is automatically registered for cleanup in Suite Teardown.
    ...                Requires: TEST_PROJECT_ID, TEST_PROJECT, ${UI_BASE_URL}

    ${temp_email}    ${temp_password}    ${temp_user_id}=    Create temporary user via AIRM API
    User logs out    ${UI_BASE_URL}
    Log in via Keycloak With Credentials    ${UI_BASE_URL}    ${temp_email}    ${temp_password}
    # New users land on the home page without a namespace context.
    # Navigate directly to the project to populate the project selector in the header.
    Navigate To Project Page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

Create temporary user via AIRM API
    [Documentation]    Creates a temporary test user via POST /v1/users, which registers the user
    ...                in both Keycloak and the AIRM database and assigns them to the current project.
    ...                Tracks the user ID for suite teardown cleanup.
    ...                Requires: TEST_PROJECT_ID
    ...                Returns: (email, password, user_id) tuple for the created user

    ${users_endpoint}=    Service API Endpoint    airm    endpoint=users
    ${email}    ${password}    ${user_id}=    Create Temporary Airm User    ${users_endpoint}    ${TEST_PROJECT_ID}
    RETURN    ${email}    ${password}    ${user_id}

# =============================================================================
# Suite Teardown / Cleanup
# =============================================================================

Clean Up Temporary Users
    [Documentation]    Deletes all temporary users created during the test suite.
    ...                Tolerates partial failures (e.g., user already removed).

    ${users_endpoint}=    Service API Endpoint    airm    endpoint=users
    Clean Up Temporary Airm Users    ${users_endpoint}
