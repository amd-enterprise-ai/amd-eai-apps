# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       API-level RBAC tests for AIWB endpoints accessed by AIRM team members.
...                 Verifies that AIWB enforces the team-member access model: a user with the
...                 team member role assigned to an AIRM project can call AIWB namespace-scoped
...                 endpoints for that project's namespace, but cannot change the cluster-wide
...                 chart catalog that every project deploys from.
...
...                 The catalog scenarios cover one change per kind of catalog entry and one read.
...                 Every chart and overlay create, update and delete route is checked for the
...                 Platform Administrator role by the API unit tests.
...
...                 The team member session infrastructure lives in the AIRM specs
...                 (`airm_rbac.resource`, `APICredentials.py`) because team-member roles and
...                 project membership are AIRM concepts. The AIWB pythonpath includes
...                 `airm/specs` and `airm/specs/libraries`, so this suite reuses that
...                 infrastructure without duplication.
...
...                 Prerequisites:
...                 - A team member user exists in Keycloak (derived from admin credentials)
...                 - Admin user has Platform Administrator role
Resource            resources/aiwb_rbac.resource
Resource            resources/airm_projects.resource

Suite Setup         Initialize AIWB RBAC Test Suite
Suite Teardown      Run Keywords    Clean Up Overlay Test Environment    AND    Clean Up All Created Projects


*** Keywords ***
Initialize AIWB RBAC Test Suite
    [Documentation]    Sets up the AIWB RBAC suite: establishes a team member API session,
    ...    creates an AIRM project with the team member assigned, and captures the project's
    ...    namespace for use in AIWB endpoint URLs.

    Require the team member account
    Create team member API session

    # A fresh project, not a fixed name. This suite deletes its project at teardown, so a
    # fixed name means the next run's setup can find the previous one still Deleting and sit
    # in the 3-minute Wait Until Project Deleted branch until it gives up — which fails the
    # setup and takes every test in the suite with it. A name nobody used before cannot be
    # mid-deletion. The tests only need the project's name to build AIWB namespace URLs, and
    # a fresh project supplies that the same way.
    A Fresh Project With User Access Exists
    Add team member to project    ${TEST_PROJECT_ID}
    # The AIRM project name is also the Kubernetes namespace used by AIWB endpoints
    # such as /projects/{project}/inference. Capture it so cross-service RBAC tests
    # can build URLs.
    VAR    ${MEMBER_PROJECT_NAMESPACE}    ${TEST_PROJECT}[name]    scope=SUITE

    Log    AIWB RBAC suite initialized. Member project namespace: ${MEMBER_PROJECT_NAMESPACE}    INFO


*** Test Cases ***
Team member can list AIM services for assigned project via API
    [Documentation]    Verifies that a team member can list AIM services in their assigned
    ...    project's namespace through the AIWB API. The empty response is acceptable because
    ...    the test only verifies access, not deployed services.
    [Tags]    rbac    access-control    aims    smoke    cross-service

    Given a team member API session exists

    When team member lists AIM services for project namespace "${MEMBER_PROJECT_NAMESPACE}"

    Then response should be successful
    And response should contain AIM service list

Team member can read the chart catalog via API
    [Documentation]    Verifies that a team member can still see the cluster-wide catalog
    ...    they deploy from, although they cannot change it.
    [Tags]    rbac    access-control    charts    list    smoke    needs-team-member

    Given a team member API session exists
    And a chart exists

    When team member lists the chart catalog

    Then response should be successful
    And the catalog listing should include the chart

Team member cannot add a chart to the catalog via API
    [Documentation]    Verifies that a team member cannot add a chart to the cluster-wide
    ...    catalog, since every project would then deploy from it.
    [Tags]    rbac    access-control    charts    create    smoke    needs-team-member

    Given a team member API session exists
    And valid chart data is prepared

    When team member uploads the chart

    Then response should be forbidden
    And the chart should not be in the catalog

Team member cannot remove a chart from the catalog via API
    [Documentation]    Verifies that a team member cannot remove a chart that other projects
    ...    rely on from the cluster-wide catalog.
    [Tags]    rbac    access-control    charts    delete    smoke    needs-team-member

    Given a team member API session exists
    And a chart exists

    When team member deletes the chart

    Then response should be forbidden
    And the chart should still be in the catalog

Team member cannot remove an overlay from the catalog via API
    [Documentation]    Verifies that a team member cannot remove an overlay that shapes other
    ...    projects' deployments from the cluster-wide catalog.
    [Tags]    rbac    access-control    overlays    delete    smoke    needs-team-member

    Given a team member API session exists
    And a chart exists
    And an overlay exists

    When team member deletes the overlay

    Then response should be forbidden
    And overlay should exist in system
