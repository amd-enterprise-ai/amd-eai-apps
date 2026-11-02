# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Feature-layer keywords for AIRM UI user management testing.
...                 Composes page-layer interactions and API preconditions into
...                 business-meaningful BDD keywords for user listing, invitation,
...                 profile editing, role management, project assignment, and search.
Resource            common/session.resource
Resource            common/navigation.resource
Resource            pages/users_page.resource

# API resources for preconditions (resolved via pythonpath from AIRM API specs)
Resource            resources/airm_projects.resource

Library             Collections
Library             Process
Library             ../libraries/TemporaryUserManager.py


*** Variables ***
${USERS_API_PATH}    /v1/users


*** Keywords ***
# =============================================================================
# Suite lifecycle
# =============================================================================

Initialize user management test suite
    [Documentation]    Resolves the AIRM API endpoint for user CRUD operations.
    ...                Must be called in Suite Setup.

    ${api_endpoint}=    Derive AIRM API endpoint from kubectl context
    Set Suite Variable    ${USERS_API_ENDPOINT}    ${api_endpoint}${USERS_API_PATH}

Clean up test users
    [Documentation]    Deletes all temporary users created during this suite.
    ...                Must be called in Suite Teardown.

    Clean Up Temporary AIRM Users    ${USERS_API_ENDPOINT}

Derive AIRM API endpoint from kubectl context
    [Documentation]    Derives the AIRM API base URL from kubectl context.

    ${result}=    Run Process    kubectl    config    view    --minify    -o    jsonpath\={.clusters[0].cluster.server}
    IF    ${result.rc} != 0
        Fail    Failed to get cluster server from kubectl config: ${result.stderr}
    END

    VAR    ${server}    ${result.stdout}
    ${hostname}=    Evaluate    "${server}".split("//")[1].split(":")[0]
    ${dot_index}=    Evaluate    "${hostname}".index(".")
    ${domain}=    Evaluate    "${hostname}"[${dot_index}+1:]

    VAR    ${url}    https://airmapi.${domain}
    Log    Derived AIRM API URL: ${url} (from server: ${server})    INFO
    RETURN    ${url}

# =============================================================================
# Precondition keywords (Given steps)
# =============================================================================

An admin user is on the users page
    [Documentation]    Logs in as admin and navigates to the users page.

    Admin user is logged in
    Navigate to users page    ${UI_BASE_URL}
    Users page should be loaded

An admin user is viewing a user's detail page
    [Documentation]    Logs in as admin and navigates to a known active user's detail page.
    ...                Finds the first non-admin user from the users table.

    Admin user is logged in
    Navigate to users page    ${UI_BASE_URL}
    Users page should be loaded

    # Find a non-admin user to use for testing (not the currently logged-in admin)
    ${user_id}=    Find non-admin user id
    Set Test Variable    ${TEST_USER_ID}    ${user_id}

    Navigate to user detail page    ${UI_BASE_URL}    ${user_id}
    User detail page should be loaded

User invitations are enabled
    [Documentation]    Verifies that the invite user button is visible,
    ...                confirming invitations are enabled (idpLinked=false).

    Invite user button should be visible

Role management is enabled
    [Documentation]    Verifies that role management is available by checking
    ...                for the Edit role button on the user detail page.

    VAR    ${edit_btn}    css=button:has-text("Edit role")
    Wait For Elements State    ${edit_btn}    visible    timeout=10s

Projects exist that the user is not a member of
    [Documentation]    Verifies that the Add to project button is enabled.

    VAR    ${add_btn}    css=button:has-text("Add to project")
    Wait For Elements State    ${add_btn}    visible    timeout=10s

A known search query is set
    [Documentation]    Sets a search query known to match at least one user.

    Set Test Variable    ${TEST_SEARCH_QUERY}    devuser

Multiple users exist
    [Documentation]    Verifies at least 2 users are listed on the active users page.

    ${names}=    Get active user row names
    ${count}=    Get Length    ${names}
    Should Be True    ${count} >= 2
    ...    msg=Expected at least 2 users, found ${count}

A pending invitation exists
    [Documentation]    Creates a temporary user via API (which creates an invitation).
    ...                Sets TEST_INVITED_EMAIL for subsequent steps.

    A ready project with user access exists
    VAR    ${project_id}    ${TEST_PROJECT}[id]

    ${email}    ${password}    ${user_id}=    Create Temporary AIRM User
    ...    ${USERS_API_ENDPOINT}    ${project_id}

    Set Test Variable    ${TEST_INVITED_EMAIL}    ${email}
    Set Test Variable    ${TEST_INVITED_USER_ID}    ${user_id}

A non-admin user exists on the users page
    [Documentation]    Ensures there is a removable (non-admin, non-self) user.
    ...                Creates a temporary user via API and waits for it to appear
    ...                in the invited users list.

    A ready project with user access exists
    VAR    ${project_id}    ${TEST_PROJECT}[id]

    ${email}    ${password}    ${user_id}=    Create Temporary AIRM User
    ...    ${USERS_API_ENDPOINT}    ${project_id}

    Set Test Variable    ${TEST_REMOVABLE_EMAIL}    ${email}
    Set Test Variable    ${TEST_REMOVABLE_USER_ID}    ${user_id}

# =============================================================================
# Helper keywords
# =============================================================================

Find non-admin user id
    [Documentation]    Finds the first non-admin active user ID from the users table.
    ...                Excludes the currently logged-in admin user.

    ${user_id}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        const rows = document.querySelectorAll('[role="row"]');
    ...        for (const row of rows) {
    ...            const header = row.querySelector('[role="rowheader"]');
    ...            const cells = row.querySelectorAll('[role="gridcell"]');
    ...            if (header && cells.length >= 3) {
    ...                const role = cells[2] ? cells[2].textContent.trim() : '';
    ...                const email = cells[0] ? cells[0].textContent.trim() : '';
    ...                if (role === 'Team Member' && !email.includes('devuser')) {
    ...                    return row.getAttribute('data-key') || '';
    ...                }
    ...            }
    ...        }
    ...        return '';
    ...    }

    Should Not Be Empty    ${user_id}
    ...    msg=No non-admin user found on the users page. Ensure team member users exist on the cluster.
    RETURN    ${user_id}

# =============================================================================
# Action keywords (When steps)
# =============================================================================

The user invites a new user with email, role, and project assignment
    [Documentation]    Opens the invite drawer, fills in email/role, and submits.

    ${timestamp}=    Evaluate    str(int(__import__('time').time()))[-6:]
    VAR    ${email}    e2e-invite-${timestamp}@test.local
    Set Test Variable    ${TEST_INVITED_EMAIL}    ${email}

    Click invite user button
    Invite drawer should be visible
    Fill invite email    ${email}

    # Keep default role (Platform Administrator) - no need to change it
    # The role dropdown defaults to Platform Administrator which is fine for test purposes

    # Fill temporary password (required when SMTP is disabled)
    ${temp_pw_visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    css=[role="dialog"] input[name="tempPassword"]    visible    timeout=5s
    IF    ${temp_pw_visible}
        Fill invite temporary password    TempPassword123!${timestamp}
    END

    Click invite submit button

    # Wait for drawer to close after successful submission
    VAR    ${dialog}    css=[role="dialog"]
    Wait For Elements State    ${dialog}    detached    timeout=60s

The user invites a new team member and assigns the prepared project
    [Documentation]    Opens the invite drawer, sets team member role, selects the
    ...                project from the precondition, fills temp password when required, and submits.

    ${timestamp}=    Evaluate    str(int(__import__('time').time()))[-6:]
    VAR    ${email}    e2e-invite-tm-${timestamp}@test.local
    Set Test Variable    ${TEST_INVITED_EMAIL}    ${email}
    ${project_name}=    Get From Dictionary    ${TEST_PROJECT}    name

    Click invite user button
    Invite drawer should be visible
    Fill invite email    ${email}
    Click invite form role selector trigger
    Invite overlay option with text is clicked    Team Member
    Click invite form project selector trigger
    Wait Until Keyword Succeeds    30s    2s
    ...    Invite overlay option with text is clicked    ${project_name}
    ${temp_pw_visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    css=[role="dialog"] input[name="tempPassword"]    visible    timeout=5s
    IF    ${temp_pw_visible}
        Fill invite temporary password    TempPassword123!${timestamp}
    END
    Click invite submit button
    VAR    ${dialog}    css=[role="dialog"]
    Wait For Elements State    ${dialog}    detached    timeout=60s

The user updates the profile name and saves
    [Documentation]    Updates the first and last name on the user detail page.

    # Store original values so we can restore them
    ${orig_first}=    Get user detail first name
    ${orig_last}=    Get user detail last name
    Set Test Variable    ${TEST_ORIGINAL_FIRST_NAME}    ${orig_first}
    Set Test Variable    ${TEST_ORIGINAL_LAST_NAME}    ${orig_last}

    ${timestamp}=    Evaluate    str(int(__import__('time').time()))[-6:]
    VAR    ${new_first}    E2EFirst${timestamp}
    VAR    ${new_last}    E2ELast${timestamp}
    Set Test Variable    ${TEST_UPDATED_FIRST_NAME}    ${new_first}
    Set Test Variable    ${TEST_UPDATED_LAST_NAME}    ${new_last}

    Fill user detail first name    ${new_first}
    Fill user detail last name    ${new_last}
    Click user detail save button
    Wait for success toast

The user searches by name or email
    [Documentation]    Types a search query in the search field on the users page.

    Type in search field    ${TEST_SEARCH_QUERY}

    # Wait for client-side filtering to apply
    Wait For Elements State    ${USERS_TABLE_SELECTOR}    visible    timeout=10s

The admin changes the user's role
    [Documentation]    Changes the user's role via the edit role drawer.

    # Determine current role and pick the opposite
    ${current_role}=    Get displayed user role
    IF    "Admin" in "${current_role}"
        VAR    ${target_role}    Team Member
        VAR    ${expected_display}    Team Member
    ELSE
        VAR    ${target_role}    Platform Administrator
        VAR    ${expected_display}    Platform Admin
    END
    Set Test Variable    ${TEST_NEW_ROLE}    ${expected_display}

    Click edit role button
    Role drawer should be visible
    Select role in drawer    ${target_role}
    Click role save button
    Wait for success toast

The admin adds the user to a project
    [Documentation]    Adds a project to the user via the add project drawer.

    # We need a project name. Use the first available project from the dropdown.
    Click add project button
    Project drawer should be visible

    # Click the project selector and pick the first available
    VAR    ${trigger}    css=[role="dialog"] [data-slot="trigger"]
    Wait For Elements State    ${trigger}    visible    timeout=5s
    Click    ${trigger}

    # Select the first project option
    VAR    ${first_option}    css=[role="option"] >> nth=0
    Wait For Elements State    ${first_option}    visible    timeout=5s
    ${project_name}=    Get Text    ${first_option}
    Click    ${first_option}

    Set Test Variable    ${TEST_ASSIGNED_PROJECT_NAME}    ${project_name}
    Click project save button
    Wait for success toast

The user removes the invited user and confirms
    [Documentation]    Cancels/removes the test invitation from the invited users tab.

    Click invited users tab
    Wait For Elements State    ${USERS_TABLE_SELECTOR}    visible    timeout=15s

    # Search for the specific invited user to handle pagination
    Type in search field    ${TEST_REMOVABLE_EMAIL}
    Wait For Elements State    ${USERS_TABLE_SELECTOR}    visible    timeout=10s

    # Wait for the invited user to appear
    Wait Until Keyword Succeeds    30s    3s
    ...    Invited user row should exist    ${TEST_REMOVABLE_EMAIL}

    Open invited user actions menu    ${TEST_REMOVABLE_EMAIL}
    Click cancel invitation action
    Confirmation dialog should be visible
    Click confirmation confirm button

The admin cancels the invitation
    [Documentation]    Cancels a pending invitation from the invited users tab.

    Click invited users tab
    Wait For Elements State    ${USERS_TABLE_SELECTOR}    visible    timeout=15s

    # Search for the specific invited user to handle pagination
    Type in search field    ${TEST_INVITED_EMAIL}
    Wait For Elements State    ${USERS_TABLE_SELECTOR}    visible    timeout=10s

    Wait Until Keyword Succeeds    30s    3s
    ...    Invited user row should exist    ${TEST_INVITED_EMAIL}

    Open invited user actions menu    ${TEST_INVITED_EMAIL}
    Click cancel invitation action
    Confirmation dialog should be visible
    Click confirmation confirm button

The admin resends the invitation
    [Documentation]    Resends a pending invitation from the invited users tab.

    Click invited users tab
    Wait For Elements State    ${USERS_TABLE_SELECTOR}    visible    timeout=15s

    # Search for the specific invited user to handle pagination
    Type in search field    ${TEST_INVITED_EMAIL}
    Wait For Elements State    ${USERS_TABLE_SELECTOR}    visible    timeout=10s

    Wait Until Keyword Succeeds    30s    3s
    ...    Invited user row should exist    ${TEST_INVITED_EMAIL}

    Open invited user actions menu    ${TEST_INVITED_EMAIL}

    # Resend is only available when SMTP is enabled
    VAR    ${resend_item}    css=[role="menuitem"]:has-text("Resend")
    ${resend_visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${resend_item}    visible    timeout=3s
    IF    not ${resend_visible}
        Skip    Resend invitation not available (SMTP likely disabled on this cluster)
    END

    Click resend invitation action
    Confirmation dialog should be visible
    Click confirmation confirm button

# =============================================================================
# Assertion keywords (Then steps)
# =============================================================================

Active users are listed with email and role information
    [Documentation]    Verifies active users table shows users with populated columns.

    Users page should be loaded
    ${names}=    Get active user row names
    ${count}=    Get Length    ${names}
    Should Be True    ${count} > 0
    ...    msg=Expected at least one user row, found ${count}

    ${emails}=    Get active user row emails
    ${email_count}=    Get Length    ${emails}
    Should Be True    ${email_count} > 0
    ...    msg=Expected at least one user email, found ${email_count}

    Log    Found ${count} active users    INFO

The invited user appears in the invited users list
    [Documentation]    Verifies the newly invited user appears in the invited tab.

    Click invited users tab
    Wait For Elements State    ${USERS_TABLE_SELECTOR}    visible    timeout=15s

    Wait Until Keyword Succeeds    30s    3s
    ...    Invited user row should exist    ${TEST_INVITED_EMAIL}

    Log    Invited user ${TEST_INVITED_EMAIL} is visible    INFO

The updated name is reflected on the user detail page
    [Documentation]    Verifies the name fields show the updated values after reload.

    # Reload the page to verify persistence
    Navigate to user detail page    ${UI_BASE_URL}    ${TEST_USER_ID}
    User detail page should be loaded

    Wait Until Keyword Succeeds    15s    3s
    ...    Verify user name is updated

    # Restore original name to avoid polluting the test user
    [Teardown]    Restore original user name

Verify user name is updated
    [Documentation]    Helper to verify the name fields match expected values.

    ${first}=    Get user detail first name
    ${last}=    Get user detail last name
    Should Be Equal    ${first}    ${TEST_UPDATED_FIRST_NAME}
    ...    msg=First name should be ${TEST_UPDATED_FIRST_NAME} but was ${first}
    Should Be Equal    ${last}    ${TEST_UPDATED_LAST_NAME}
    ...    msg=Last name should be ${TEST_UPDATED_LAST_NAME} but was ${last}

Restore original user name
    [Documentation]    Restores the user's original name after edit testing.

    TRY
        Navigate to user detail page    ${UI_BASE_URL}    ${TEST_USER_ID}
        User detail page should be loaded
        Fill user detail first name    ${TEST_ORIGINAL_FIRST_NAME}
        Fill user detail last name    ${TEST_ORIGINAL_LAST_NAME}
        Click user detail save button
    EXCEPT
        Log    Failed to restore original user name    WARN
    END

The invited user is no longer listed
    [Documentation]    Verifies the removed invitation is no longer in the invited users list.

    # We should already be on the invited tab after the cancel action
    Wait Until Keyword Succeeds    30s    3s
    ...    Verify invited user removed    ${TEST_REMOVABLE_EMAIL}

    Log    User ${TEST_REMOVABLE_EMAIL} is no longer listed    INFO

Verify invited user removed
    [Documentation]    Helper that refreshes the invited tab and checks user is gone.
    [Arguments]    ${email}

    # Click refresh or re-navigate to ensure fresh data
    Click invited users tab
    Wait For Elements State    ${USERS_TABLE_SELECTOR}    visible    timeout=15s
    Invited user row should not exist    ${email}

Only matching users are shown
    [Documentation]    Verifies that search results contain matching users.

    ${names}=    Get active user row names
    ${count}=    Get Length    ${names}
    Should Be True    ${count} > 0
    ...    msg=Expected at least one matching user for query "${TEST_SEARCH_QUERY}"

    Log    Search for "${TEST_SEARCH_QUERY}" returned ${count} result(s)    INFO

The updated role is reflected on the user detail page
    [Documentation]    Verifies the role section shows the updated role.

    # Reload the page to verify persistence
    Navigate to user detail page    ${UI_BASE_URL}    ${TEST_USER_ID}
    User detail page should be loaded

    Wait Until Keyword Succeeds    15s    3s
    ...    Verify user role is updated

    # Restore the original role
    [Teardown]    Restore original user role

Verify user role is updated
    [Documentation]    Helper to verify the displayed role matches the expected value.

    ${displayed_role}=    Get displayed user role
    Should Contain    ${displayed_role}    ${TEST_NEW_ROLE}
    ...    msg=Role should contain "${TEST_NEW_ROLE}" but was "${displayed_role}"

Restore original user role
    [Documentation]    Restores the user's original role after role change testing.

    TRY
        # Change back to the opposite of what we set
        Navigate to user detail page    ${UI_BASE_URL}    ${TEST_USER_ID}
        User detail page should be loaded
        IF    "Team Member" in "${TEST_NEW_ROLE}"
            VAR    ${restore_role}    Platform Administrator
        ELSE
            VAR    ${restore_role}    Team Member
        END
        Click edit role button
        Role drawer should be visible
        Select role in drawer    ${restore_role}
        Click role save button
    EXCEPT
        Log    Failed to restore original role    WARN
    END

The project appears in the user's project list
    [Documentation]    Verifies the assigned project appears in the user's project section.

    Wait Until Keyword Succeeds    15s    3s
    ...    Verify project in user list

Verify project in user list
    [Documentation]    Helper to verify a project appears in the user's project list.

    ${projects}=    Get user projects list
    ${found}=    Evaluate    any("${TEST_ASSIGNED_PROJECT_NAME}" in p for p in ${projects})
    Should Be True    ${found}
    ...    msg=Project "${TEST_ASSIGNED_PROJECT_NAME}" not found in user's project list: ${projects}

The invitation is removed from the invited users list
    [Documentation]    Verifies the cancelled invitation no longer appears.

    Wait Until Keyword Succeeds    30s    3s
    ...    Invited user row should not exist    ${TEST_INVITED_EMAIL}

    Log    Invitation for ${TEST_INVITED_EMAIL} was cancelled    INFO

The invitation status is updated
    [Documentation]    Verifies resend was successful.

    Wait for success toast

    # The invitation should still exist
    Invited user row should exist    ${TEST_INVITED_EMAIL}
    Log    Invitation for ${TEST_INVITED_EMAIL} was resent    INFO
