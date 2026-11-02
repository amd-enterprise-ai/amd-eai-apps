# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Business-logic keywords for AIRM API RBAC testing.
...                 Provides keywords for testing role-based access control at the API level.
...                 Supports switching between admin and team member API sessions.
Resource            api/projects.resource
Resource            api/clusters.resource
Resource            resources/api/common.resource
Resource            resources/authorization.resource
Resource            airm_projects.resource
Resource            airm_clusters.resource
Library             RequestsLibrary
Library             Collections
Library             ../libraries/APICredentials.py


*** Variables ***
${TEAM_MEMBER_SESSION}          ${None}
${ADMIN_SESSION_BACKUP}         ${None}
${ADMIN_SERVICE_NAME_BACKUP}    ${None}


*** Keywords ***
# --- Provisioning Detection ---

Require the team member account
    [Documentation]    Fails the suite, naming the missing prerequisite, when the
    ...    team-member account does not exist in the target environment's Keycloak.
    ...
    ...    Every test below authenticates as that account, so its absence is a setup
    ...    failure rather than a result. Reporting it as a skip is what let a whole
    ...    RBAC surface disappear into a total that read green: a skipped test is
    ...    never a pass. The chart provisions the account; the setup entrypoint
    ...    applies it.
    ...
    ...    A run that cannot carry a second password at all -- user passthrough with
    ...    no explicit override -- is a different thing and still skips: no account
    ...    is missing there, the run simply cannot log in as one.
    ${applicable}=    Team Member Is Applicable
    IF    not ${applicable}
        ${reason}=    Team Member Not Applicable Reason
        Skip    ${reason}
    END
    ${provisioned}=    Team Member Is Provisioned
    IF    not ${provisioned}
        ${reason}=    Team Member Unavailable Reason
        Fail    ${reason}
    END


# --- Session Management ---

Create team member API session
    [Documentation]    Creates a separate API session authenticated as the team member user.
    ...    Uses APICredentials library to get a team member token via password grant.
    ...    The team member session is stored separately from the admin session.
    ...    Sets: TEAM_MEMBER_SESSION

    # Endpoint keywords (e.g. Projects endpoint) return absolute URLs that include /v1,
    # so the session base URL is only a host fallback. Use Service API Endpoint as-is for
    # consistency with the admin session created in `Create api session`.
    ${base_url}=    Service API Endpoint    airm

    ${token}=    Get Team Member Api Token
    ${username}=    Get Team Member Username
    Log    Creating team member API session for ${username}    INFO

    &{headers}=    Create Dictionary
    ...    Content-Type=application/json
    ...    Authorization=Bearer ${token}
    ...    Connection=close

    Create Session    team_member_api    ${base_url}    headers=${headers}
    ...    verify=${VERIFY_SSL}    timeout=30    max_retries=3

    VAR    ${TEAM_MEMBER_SESSION}    team_member_api    scope=SUITE
    Log    Team member API session created for ${username}    INFO

Switch to team member session
    [Documentation]    Switches the active API session to the team member session.
    ...    Saves the current admin session so it can be restored later.
    ...    Requires: Create team member API session has been called.

    IF    $TEAM_MEMBER_SESSION is None
        Fail    No team member session exists. Call 'Create team member API session' first.
    END

    # Back up admin session
    VAR    ${ADMIN_SESSION_BACKUP}    ${API_SESSION}    scope=SUITE
    VAR    ${ADMIN_SERVICE_NAME_BACKUP}    ${SESSION_SERVICE_NAME}    scope=SUITE

    # Switch to team member session
    Set Suite Variable    ${API_SESSION}    ${TEAM_MEMBER_SESSION}
    Log    Switched to team member API session    INFO

Switch to admin session
    [Documentation]    Restores the active API session to the admin session.
    ...    Requires: Switch to team member session was called previously.

    IF    $ADMIN_SESSION_BACKUP is None
        Fail    No admin session backup exists. Was 'Switch to team member session' called?
    END

    Set Suite Variable    ${API_SESSION}    ${ADMIN_SESSION_BACKUP}
    Set Suite Variable    ${SESSION_SERVICE_NAME}    ${ADMIN_SERVICE_NAME_BACKUP}
    Log    Switched back to admin API session    INFO


# --- Team Member API Request Keywords ---

Team member gets project "${project_id}"
    [Documentation]    Gets a specific project as the team member user.
    ...    Sets: TEST_RESPONSE
    Switch to team member session
    ${endpoint}=    Projects endpoint
    ${response}=    Safe Get Request    ${endpoint}/${project_id}    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Switch to admin session
    RETURN    ${response}

Team member creates cluster
    [Documentation]    Attempts to create a cluster as the team member user.
    ...    This should be denied (admin-only operation).
    ...    Sets: TEST_RESPONSE
    Switch to team member session
    ${endpoint}=    Clusters endpoint
    ${cluster_data}=    Create Dictionary
    ...    name=rbac-test-cluster
    ...    kubeConfigBase64=dGVzdA==
    ${response}=    Safe Post Request    ${endpoint}    json=${cluster_data}    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Switch to admin session
    RETURN    ${response}

Team member deletes project "${project_id}"
    [Documentation]    Attempts to delete a project as the team member user.
    ...    This should be denied (admin-only operation).
    ...    Sets: TEST_RESPONSE
    Switch to team member session
    ${endpoint}=    Projects endpoint
    ${response}=    Safe Delete Request    ${endpoint}/${project_id}    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Switch to admin session
    RETURN    ${response}

Team member updates project "${project_id}"
    [Documentation]    Attempts to update a project's settings as the team member user.
    ...    Targets PUT /projects/{id}, the AIRM endpoint that modifies project
    ...    settings (description, quota, GPU preemption). This is an admin-only
    ...    operation; the platform-administrator dependency is declared before the
    ...    request body, so the request is rejected with 403 before payload
    ...    validation runs.
    ...    Sets: TEST_RESPONSE
    Switch to team member session
    ${endpoint}=    Projects endpoint
    ${quota}=    Create Dictionary
    ...    cpuMilliCores=1000
    ...    memoryBytes=1073741824
    ...    ephemeralStorageBytes=1073741824
    ...    gpuCount=0
    ${project_data}=    Create Dictionary    description=rbac test update    quota=${quota}
    ${response}=    Safe Put Request    ${endpoint}/${project_id}    json=${project_data}    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Switch to admin session
    RETURN    ${response}

Team member lists users
    [Documentation]    Attempts to list users as the team member user.
    ...    This should be denied (admin-only operation).
    ...    Sets: TEST_RESPONSE
    Switch to team member session
    ${endpoint}=    Service API Endpoint    airm    endpoint=users
    ${response}=    Safe Get Request    ${endpoint}    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Switch to admin session
    RETURN    ${response}


# --- Project Membership Keywords ---

Add team member to project
    [Documentation]    Adds the team member user to a project (called by admin).
    ...    Finds the team member by email in the user list, then adds them
    ...    to the specified project. Refreshes the team member session
    ...    afterwards so its JWT picks up the new group membership claim.
    [Arguments]    ${project_id}

    ${tm_username}=    Get Team Member Username
    Log    Adding team member ${tm_username} to project ${project_id}    INFO

    # Find the team member user ID from the admin users list
    Create api session    airm
    ${users_endpoint}=    Service API Endpoint    airm    endpoint=users
    ${users_response}=    Safe Get Request    ${users_endpoint}    expected_status=200
    ${users}=    Set Variable    ${users_response.json()['data']}

    VAR    ${found_id}    ${None}
    FOR    ${user}    IN    @{users}
        ${email}=    Get From Dictionary    ${user}    email
        IF    '${email}' == '${tm_username}'
            ${found_id}=    Get From Dictionary    ${user}    id
            BREAK
        END
    END

    IF    $found_id is None
        Fail    Team member user ${tm_username} not found in system users list. Ensure the user exists in Keycloak.
    END

    Log    Found team member user: ${tm_username} (ID: ${found_id})    INFO

    # Add team member to project via admin session
    ${endpoint}=    Projects endpoint
    ${user_ids}=    Create List    ${found_id}
    ${user_data}=    Create Dictionary    userIds=${user_ids}
    Safe Post Request    ${endpoint}/${project_id}/users    json=${user_data}    expected_status=204
    Log    Team member ${tm_username} added to project ${project_id}    INFO

    # Recreate team member session to pick up new group claims
    Create team member API session


# --- Precondition Keywords ---

A team member API session exists
    [Documentation]    Precondition: ensures the team member API session is available.
    ...    The session is created once in Suite Setup and reused across tests.
    Should Not Be Equal    ${TEAM_MEMBER_SESSION}    ${None}
    ...    msg=Team member API session not initialized. Check Suite Setup.

The member project exists
    [Documentation]    Precondition: verifies the member project (created in Suite Setup)
    ...    is available for access tests.
    Should Not Be Equal    ${MEMBER_PROJECT_ID}    ${None}
    ...    msg=Member project not created. Check Suite Setup.

The admin-only project exists
    [Documentation]    Precondition: verifies the admin-only project (created in Suite Setup)
    ...    is available for cross-project isolation tests.
    Should Not Be Equal    ${ADMIN_ONLY_PROJECT_ID}    ${None}
    ...    msg=Admin-only project not created. Check Suite Setup.


# --- Assertion Keywords ---

Response should be forbidden
    [Documentation]    Verifies the response has HTTP 403 Forbidden status.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    403
    ...    msg=Expected 403 Forbidden but got ${TEST_RESPONSE.status_code}: ${TEST_RESPONSE.text}

Response should be forbidden or not found
    [Documentation]    Verifies the response has HTTP 403 or 404 status.
    ...    AIRM API may return 404 for resources the user cannot see (security by obscurity).
    ${status}=    Set Variable    ${TEST_RESPONSE.status_code}
    Should Be True    ${status} == 403 or ${status} == 404
    ...    msg=Expected 403 or 404 but got ${status}: ${TEST_RESPONSE.text}

Response should be successful
    [Documentation]    Verifies the response has a successful HTTP status (200-299).
    ${status}=    Set Variable    ${TEST_RESPONSE.status_code}
    Should Be True    200 <= ${status} < 300
    ...    msg=Expected success (2xx) but got ${status}: ${TEST_RESPONSE.text}

Response should contain project details
    [Documentation]    Verifies the response contains valid project data (id, name, status).
    ${json}=    Set Variable    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    id
    Dictionary Should Contain Key    ${json}    name
    Dictionary Should Contain Key    ${json}    status
    Log    Response contains project: ${json['name']} (${json['id']})    INFO
