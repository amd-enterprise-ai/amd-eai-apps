# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Feature-layer keywords for AIRM UI project management testing.
...                 Composes page-layer interactions into business-meaningful keywords
...                 for project creation, editing, quota, members, and deletion flows.
Resource            common/session.resource
Resource            common/navigation.resource
Resource            pages/projects_page.resource
Resource            resources/resource_tracking.resource


*** Variables ***
${PROJECT_CREATION_TIMEOUT}     30s
${PROJECT_STATUS_TIMEOUT}       120s


*** Keywords ***
# =============================================================================
# Precondition keywords (Given steps)
# =============================================================================

An admin user is on the projects page
    [Documentation]    Logs in as admin and navigates to the projects page.
    Admin user is logged in
    Navigate to page    ${UI_BASE_URL}    /projects
    Projects page should be loaded

An admin user is editing a project
    [Documentation]    Logs in as admin, navigates to projects, opens the first project,
    ...                and goes to its edit/settings page. Sets TEST_PROJECT_ID and
    ...                TEST_PROJECT_NAME for later use.
    Admin user is logged in
    Navigate to page    ${UI_BASE_URL}    /projects
    Projects page should be loaded

    ${project_ids}=    Get project IDs from list
    ${count}=    Get Length    ${project_ids}
    IF    ${count} == 0
        Fail    No projects available to edit
    END

    VAR    ${project_id}    ${project_ids}[0]
    VAR    ${TEST_PROJECT_ID}    ${project_id}    scope=TEST

    ${project_name}=    Get project name by ID    ${project_id}
    VAR    ${TEST_PROJECT_NAME}    ${project_name}    scope=TEST

    Navigate to page    ${UI_BASE_URL}    /projects/${project_id}/edit
    Project settings page should be loaded

An admin user is viewing a project dashboard
    [Documentation]    Logs in as admin, navigates to a project dashboard.
    Admin user is logged in
    Navigate to page    ${UI_BASE_URL}    /projects
    Projects page should be loaded

    ${project_ids}=    Get project IDs from list
    ${count}=    Get Length    ${project_ids}
    IF    ${count} == 0
        Fail    No projects available to view
    END

    VAR    ${project_id}    ${project_ids}[0]
    VAR    ${TEST_PROJECT_ID}    ${project_id}    scope=TEST

    Navigate to page    ${UI_BASE_URL}    /projects/${project_id}
    Project dashboard metrics should be visible

A platform user exists who is not a project member
    [Documentation]    Environment precondition: the dev cluster has multiple platform users,
    ...                and newly created or existing projects have fewer members than total
    ...                platform users. The Add Member drawer will fail with a clear error
    ...                if no available users exist when the test attempts to add one.
    ...                This keyword is intentionally a no-op because verifying available
    ...                non-members requires navigating to the members tab and opening the
    ...                drawer, which is what the When step does.
    No Operation

A ready project exists on the projects page
    [Documentation]    Creates a project via the UI and waits until it reaches Ready status.
    ...                Combines project creation and status polling into a single precondition.
    An admin user is on the projects page
    The user creates a project with a name and cluster assignment
    The project status should eventually be ready

A healthy cluster is connected
    [Documentation]    Verifies that the projects page is accessible, which implies at least
    ...                one cluster is available. On the dev cluster, clusters are always
    ...                available. This keyword is a precondition assertion, not a setup action.
    Navigate to page    ${UI_BASE_URL}    /projects
    Projects page should be loaded

# =============================================================================
# Action keywords (When steps)
# =============================================================================

The user creates a project with a name and cluster assignment
    [Documentation]    Creates a project through the UI with a unique name and cluster.
    ...                Sets TEST_CREATED_PROJECT_NAME for later verification.
    Navigate to page    ${UI_BASE_URL}    /projects
    Projects page should be loaded

    ${unique_suffix}=    Evaluate    __import__('uuid').uuid4().hex[:8]
    VAR    ${project_name}    e2e-proj-${unique_suffix}
    VAR    ${TEST_CREATED_PROJECT_NAME}    ${project_name}    scope=TEST

    Click create project button
    Create project drawer should be open

    Fill project name field    ${project_name}
    Fill project description field    E2E test project created by automated tests
    Select cluster in create form

    Click create project submit button

The user creates a project with preemption enabled
    [Documentation]    Creates a project with GPU preemption settings enabled.
    ...                Enables the preemption switch and uses default policy/threshold/grace period
    ...                values which are pre-filled by the form.
    ...                Sets TEST_CREATED_PROJECT_NAME for later verification.
    Navigate to page    ${UI_BASE_URL}    /projects
    Projects page should be loaded

    ${unique_suffix}=    Evaluate    __import__('uuid').uuid4().hex[:8]
    VAR    ${project_name}    e2e-preempt-${unique_suffix}
    VAR    ${TEST_CREATED_PROJECT_NAME}    ${project_name}    scope=TEST

    Click create project button
    Create project drawer should be open

    Fill project name field    ${project_name}
    Fill project description field    E2E preemption test project
    Select cluster in create form

    # Enable preemption -- defaults are pre-filled (policy: During GPU pressure,
    # threshold: 10%, grace period: 30 min)
    Toggle preemption switch
    Wait for preemption fields to render

    Click create project submit button

The user navigates to the quota tab
    [Documentation]    Navigates to the quota tab on the project edit page.
    Click quota tab

The user notes the current CPU guaranteed allocation on the quota tab
    [Documentation]    Records the displayed CPU guaranteed allocation for a later assertion.
    Note current CPU guaranteed allocation on quota tab

The user increases the CPU guaranteed allocation once without saving
    [Documentation]    Adjusts the CPU allocation control without submitting the form.
    Increase CPU guaranteed allocation once without saving

The user discards changes to the project settings form
    [Documentation]    Reverts unsaved edits on the project edit page.
    Click discard changes on project settings

The user navigates to the members tab
    [Documentation]    Navigates to the members/users tab on the project edit page.
    Click users tab

Adds the user as a project member
    [Documentation]    Opens the Add Member drawer, selects the first available user,
    ...                and submits the form to add them to the project.
    ...                Sets TEST_ADDED_MEMBER_NAME for later verification.
    Click add member button
    Add member drawer should be open
    ${user_name}=    Select first available member
    # The drawer shows "LastName, FirstName" but the members table shows "FirstName LastName",
    # so extract the last name (before the comma) for matching.
    ${last_name}=    Evaluate    "${user_name}".split(",")[0].strip()
    VAR    ${TEST_ADDED_MEMBER_NAME}    ${last_name}    scope=TEST
    Click add to project button

The user navigates to the secrets tab
    [Documentation]    Navigates to the secrets tab on the project edit page.
    Click secrets tab

The user navigates to the storages tab
    [Documentation]    Navigates to the storages tab on the project edit page.
    Click storages tab

The user initiates project deletion from dashboard and confirms
    [Documentation]    Initiates project deletion via the Actions dropdown and confirms.
    Open project actions menu
    Click delete menu item
    Confirm deletion in modal

The user navigates to the created project dashboard
    [Documentation]    Navigates to the dashboard of the most recently created project.
    ...                Finds the project ID from the list, then navigates directly via URL.
    Navigate to page    ${UI_BASE_URL}    /projects
    Projects page should be loaded

    # Filter to find the project (handles pagination) and get its ID
    Filter projects by name    ${TEST_CREATED_PROJECT_NAME}
    ${project_id}=    Get project ID by name    ${TEST_CREATED_PROJECT_NAME}
    Navigate to page    ${UI_BASE_URL}    /projects/${project_id}
    Wait for project dashboard to load

# =============================================================================
# Assertion keywords (Then steps)
# =============================================================================

The project appears in the project list
    [Documentation]    Verifies the created project is visible in the projects list.
    ...                Waits for redirect and project list to load. Tracks the project
    ...                for Suite Teardown cleanup.
    Navigate to page    ${UI_BASE_URL}    /projects
    Projects page should be loaded

    Wait Until Keyword Succeeds    ${PROJECT_CREATION_TIMEOUT}    3s
    ...    Project row should exist    ${TEST_CREATED_PROJECT_NAME}
    Track created project for cleanup    ${TEST_CREATED_PROJECT_NAME}

The user is taken to the project edit page
    [Documentation]    Verifies the user is on the project edit page after creation.

    ${current_url}=    Get current page URL
    ${is_edit_page}=    Evaluate    "/edit" in "${current_url}"
    IF    not ${is_edit_page}
        # After creation, the app redirects to edit page. Wait briefly for redirect.
        Project settings heading should be visible    timeout=${PROJECT_CREATION_TIMEOUT}
    END

The quota tab shows resource allocation values
    [Documentation]    Verifies the quota table displays all four resource types with
    ...                numeric allocation values (GPU, CPU, Memory, Disk).
    Quota table should be visible
    Quota table should contain resource types

Admin quota controls are visible
    [Documentation]    Verifies admin-specific controls are present on the quota tab.
    ...                Save/Discard buttons indicate the user has admin edit permissions.
    Save changes button should be visible
    Discard changes button should be visible

The CPU guaranteed allocation matches the noted value
    [Documentation]    Verifies the CPU allocation display matches the earlier recorded value.
    CPU guaranteed allocation should match noted value

The user appears in the project members list
    [Documentation]    Verifies that the newly added member appears in the members table.
    Wait Until Keyword Succeeds    15s    2s
    ...    Member should be in members table    ${TEST_ADDED_MEMBER_NAME}

The secrets tab shows available secrets
    [Documentation]    Verifies the secrets tab panel is loaded with content.
    Secrets section should be visible

The storages tab shows available storages
    [Documentation]    Verifies the storages tab panel is loaded with content.
    Storages section should be visible

The project dashboard shows overview metrics
    [Documentation]    Verifies that the project dashboard displays overview metrics.
    Project dashboard metrics should be visible

The project dashboard shows workloads
    [Documentation]    Verifies that the project dashboard shows the workloads section.
    Project workloads section should be visible

The project is removed from the project list
    [Documentation]    Verifies the project no longer appears in the project list after deletion.

    Wait for redirect to projects page

    ${current_url}=    Get current page URL
    ${on_projects}=    Evaluate    "${current_url}".rstrip("/").endswith("/projects")
    IF    not ${on_projects}
        Navigate to page    ${UI_BASE_URL}    /projects
    END

    Projects page should be loaded
    Wait Until Keyword Succeeds    15s    3s
    ...    Project should not be in list    ${TEST_CREATED_PROJECT_NAME}

The project status should eventually be ready
    [Documentation]    Waits for the project to transition from pending/syncing to ready.
    ...                Uses polling to check the project list status without manual refresh.
    ...                Tracks the project for Suite Teardown cleanup.

    Wait Until Keyword Succeeds    ${PROJECT_STATUS_TIMEOUT}    5s
    ...    Project status should be ready in list    ${TEST_CREATED_PROJECT_NAME}
    Track created project for cleanup    ${TEST_CREATED_PROJECT_NAME}

The preemption settings should be saved with the project
    [Documentation]    Verifies that preemption settings are visible after project creation.
    ...                Navigates to the project's details tab to check for preemption section.
    ...                Tracks the project for Suite Teardown cleanup.

    # After creation, we should be on the edit page
    Project settings heading should be visible    timeout=${PROJECT_CREATION_TIMEOUT}

    Click details tab
    ${content}=    Get preemption status text
    # The details tab shows preemption form fields when preemption is configured.
    # The presence of "Pre-emption policy" confirms preemption is enabled.
    Should Contain    ${content}    Pre-emption policy    msg=Preemption settings should show policy field

    # Track for cleanup -- navigate to list to get the project ID
    Navigate to page    ${UI_BASE_URL}    /projects
    Projects page should be loaded
    Track created project for cleanup    ${TEST_CREATED_PROJECT_NAME}

# =============================================================================
# Internal helper keywords
# =============================================================================

Filter projects by name
    [Documentation]    Filters the project list using the search input.
    [Arguments]    ${project_name}

    Filter projects by search text    ${project_name}

Project row should exist
    [Documentation]    Asserts a project row with the given name exists in the project list.
    ...                Uses the search filter to handle pagination.
    [Arguments]    ${project_name}

    Filter projects by name    ${project_name}
    ${text}=    Get project row text by name    ${project_name}
    Should Not Be Empty    ${text}    msg=Project '${project_name}' not found in project list

Project status should be ready in list
    [Documentation]    Asserts a project in the list shows Ready status.
    ...                Uses the search filter to find the project when pagination is active.
    [Arguments]    ${project_name}

    Navigate to page    ${UI_BASE_URL}    /projects
    Projects page should be loaded
    # Use search filter to find the project (handles pagination)
    Filter projects by name    ${project_name}
    ${row_text}=    Get project row text by name    ${project_name}
    Should Contain    ${row_text}    Ready    msg=Project '${project_name}' is not Ready yet

Project should not be in list
    [Documentation]    Asserts a project row with the given name does NOT exist in the list.
    [Arguments]    ${project_name}

    Project name should not appear in search results    ${project_name}

Track created project for cleanup
    [Documentation]    Looks up the project ID by name from the project list and tracks it
    ...                for Suite Teardown cleanup via the AIRM API delete endpoint.
    ...                Tolerates failures so tracking issues don't break test assertions.
    [Arguments]    ${project_name}

    TRY
        ${project_id}=    Get project ID by name    ${project_name}
        Track Project For Cleanup    ${project_id}
    EXCEPT
        Log    Could not track project '${project_name}' for cleanup    WARN
    END
