# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       API-level RBAC tests for AIRM team member role.
...                 Verifies that the AIRM API enforces role-based access control:
...                 team members can access their assigned projects, cannot perform
...                 admin-only operations, and cannot access unassigned project details.
...
...                 Note on GET /projects list behavior: The AIRM API returns all
...                 organization projects in the list endpoint regardless of membership.
...                 Access control is enforced at the individual resource level
...                 (GET /projects/{id} returns 404 for non-members). The original
...                 ticket scenario "Role-based data filtering in API responses" assumed
...                 list filtering, which does not match the API design. That scenario
...                 is replaced with a positive access test for assigned project details.
...
...                 Prerequisites:
...                 - A team member user exists in Keycloak (derived from admin credentials)
...                 - Admin user has Platform Administrator role
Resource            ../resources/airm_rbac.resource
Resource            ../resources/airm_projects.resource
Resource            ../resources/airm_clusters.resource

Suite Setup         Initialize RBAC Test Suite
Suite Teardown      Clean Up All Created Projects


*** Keywords ***
Initialize RBAC Test Suite
    [Documentation]    Sets up the RBAC test suite by creating admin and team member
    ...    API sessions, and ensuring projects exist for RBAC testing:
    ...    1. A project the team member IS assigned to (for access tests)
    ...    2. A project the team member is NOT assigned to (for isolation tests)
    ...
    ...    Fails the entire suite when the team-member account is not provisioned
    ...    in the target environment's Keycloak, since every test needs that user.

    Require the team member account
    Set up admin and team member API sessions
    Create RBAC test projects

Set up admin and team member API sessions
    [Documentation]    Ensures the admin session and a cluster exist, then creates
    ...    the parallel team member API session used for RBAC requests.

    # Ensure admin session is established and a cluster exists
    A cluster exists in system

    # Create the team member API session (parallel to admin session)
    Create team member API session

Create RBAC test projects
    [Documentation]    Creates the two suite-scoped projects used by RBAC tests:
    ...    one the team member belongs to and one only the admin can access.
    ...    Sets: MEMBER_PROJECT_ID, ADMIN_ONLY_PROJECT_ID

    # Create a project that the team member IS assigned to.
    # The admin creates it, adds the team member user, then refreshes the token.
    ${member_name}=    Test Name    rbac-member-project
    A Ready Project "${member_name}" With User Access Exists
    Add team member to project    ${TEST_PROJECT_ID}
    VAR    ${MEMBER_PROJECT_ID}    ${TEST_PROJECT_ID}    scope=SUITE

    # Create a project that only the admin has access to (team member is NOT added).
    # This project is used to verify cross-project isolation.
    ${admin_only_name}=    Test Name    rbac-admin-only
    Project "${admin_only_name}" exists in system
    VAR    ${ADMIN_ONLY_PROJECT_ID}    ${TEST_PROJECT_ID}    scope=SUITE

    Log    RBAC suite initialized. Member project: ${MEMBER_PROJECT_ID}, Admin-only project: ${ADMIN_ONLY_PROJECT_ID}    INFO


*** Test Cases ***
Team member can access assigned project via API
    [Documentation]    Verifies that a team member can access their assigned project's
    ...    details through the API. The team member should receive a successful response
    ...    with project data when requesting a project they belong to.
    [Tags]    rbac    access-control    projects    smoke

    Given a team member API session exists
    And the member project exists

    When team member gets project "${MEMBER_PROJECT_ID}"

    Then response should be successful
    And response should contain project details

Team member cannot perform admin-only API operations
    [Documentation]    Verifies that a team member is denied access to admin-only API
    ...    endpoints. Operations like creating clusters, deleting projects, updating
    ...    project settings, and listing users require Platform Administrator role.
    [Tags]    rbac    access-control    negative    smoke

    Given a team member API session exists

    When team member creates cluster
    Then response should be forbidden

    When team member deletes project "${ADMIN_ONLY_PROJECT_ID}"
    Then response should be forbidden

    When team member updates project "${MEMBER_PROJECT_ID}"
    Then response should be forbidden

    When team member lists users
    Then response should be forbidden

Team member cannot access unassigned project via API
    [Documentation]    Verifies cross-project isolation at the API level. While the
    ...    project list endpoint returns all organization projects, access control
    ...    is enforced at the resource detail level. A team member requesting details
    ...    of a project they are not assigned to should be denied.
    [Tags]    rbac    access-control    cross-project    negative

    Given a team member API session exists
    And the admin-only project exists

    When team member gets project "${ADMIN_ONLY_PROJECT_ID}"

    Then response should be forbidden or not found
