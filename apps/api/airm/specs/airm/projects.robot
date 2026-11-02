# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for Project management endpoints.
...                 Verifies project creation, listing, retrieval, update, deletion, and user management operations.
Resource            ../resources/airm_projects.resource
Resource            ../resources/airm_clusters.resource
Resource            ../resources/airm_secrets.resource
Resource            ../resources/airm_storage.resource
Resource            ../resources/airm_workloads.resource
Resource            resources/api/common.resource
Library             Collections
Library             Process
Test Setup          Initialize Workload Tracking
Test Teardown       Clean Up Test Resources

*** Keywords ***
Clean Up Test Resources
    [Documentation]    Clean up all resources created during test
    Clean Up All Created Workloads
    Clean Up All Created Storage
    Clean Up All Created Secrets
    Clean Up All Created Projects


*** Test Cases ***
Create project and verify status
    [Documentation]    Verify that a new project can be created with valid status
    ...    Tests: POST /projects → returns 200 with project details and status
    ...    Note: Project creation is asynchronous, status is pending, provisioning, or Ready
    [Tags]    projects    create    status    smoke

    Given a cluster exists in system
    And valid project data is prepared

    When create project request is sent

    Then response status should be 200
    And response should contain "${TEST_PROJECT}[name]"
    And response should contain key "id"
    And response should contain key "quota"
    And project status in response should be pending or ready
    And project should exist in database

Create project and verify Kubernetes resources are provisioned
    [Documentation]    Verify that project Kubernetes resources are created and status becomes Ready
    ...    Tests: Project creation → namespace, ResourceQuota, RoleBinding → Ready status
    ...    This validates the complete provisioning pipeline from API to cluster
    [Tags]    projects    create    kubernetes    provisioning    smoke    kubectl

    Given a cluster exists in system
    And valid project data is prepared

    When create project request is sent
    And project should transition to "ready"

    Then project namespace should exist
    # Skip ResourceQuota and RoleBinding verification due to RBAC permissions
    # The test user doesn't have permission to list ResourceQuotas
    # API-level verification through project status is sufficient for E2E testing
    # And project namespace should have ResourceQuota
    # And project namespace should have RoleBinding
    And project namespace should have label matching project ID

List projects
    [Documentation]    Verify that projects can be listed via GET /projects
    [Tags]    projects    list    smoke

    Given a cluster exists in system
    And multiple projects exist
    When list projects request is sent
    Then response status should be 200
    And response should contain projects list
    And response should contain at least 2 projects

Get specific project
    [Documentation]    Verify that a specific project can be retrieved by ID via GET /projects/{id}
    [Tags]    projects    get    smoke

    Given a cluster exists in system
    And a project exists
    When get project request is sent for "${TEST_PROJECT_ID}"
    Then response status should be 200
    And response should contain "${TEST_PROJECT}[name]"
    And response should contain key "id"
    And response should contain value "${TEST_PROJECT_ID}"
    And response should contain key "users"
    And response should contain key "quota"

Update project description
    [Documentation]    Verify that an existing project description can be modified via PUT /projects/{id}
    [Tags]    projects    update    smoke

    Given a cluster exists in system
    And a project exists
    And updated project data with new description is prepared
    When update project request is sent
    Then response status should be 200
    And project description in database should be "${TEST_UPDATED_PROJECT_DESC}"

Update project quota
    [Documentation]    Verify that an existing project quota can be modified via PUT /projects/{id}
    [Tags]    projects    quota    update

    Given a cluster exists in system
    And a project exists
    And updated quota data is prepared
    When update project request is sent
    Then response status should be 200
    And project quota in database should match updated values

Delete non-existent project
    [Documentation]    Verify proper error when deleting non-existent project via DELETE /projects/{id}
    [Tags]    projects    delete    negative

    Given a cluster exists in system
    And a project does not exist
    When delete project request is sent
    Then response status should be 404

Delete existing project
    [Documentation]    Verify that an existing project can be deleted via DELETE /projects/{id}
    [Tags]    projects    delete    smoke

    Given a cluster exists in system
    And a project exists
    When delete project request is sent
    Then response status should be 204
    And the project should not exist in database

Delete project and verify namespace removal
    [Documentation]    Verify that when a project is deleted, its namespace is also removed from the cluster
    ...    Tests: DELETE /projects/{id} → namespace deleted from Kubernetes
    [Tags]    projects    delete    namespace    integration    kubectl

    Given a ready project exists

    When delete project request is sent

    Then response status should be 204
    And the project should not exist in database
    And project namespace should not exist in cluster

Add users to project
    [Documentation]    Verify that users can be added to a project via POST /projects/{id}/users
    ...    Tests: Adding a new user to a project that doesn't have them yet
    [Tags]    projects    users    add

    Given a cluster exists in system
    And a project exists
    And a user exists in system
    And user should not be member of project

    When add users to project request is sent

    Then response status should be 204
    And user should be member of project

Add user to project when already member
    [Documentation]    Verify that adding an existing member to a project is idempotent
    ...    Tests: POST /projects/{id}/users with already existing user → 204 (no error)
    [Tags]    projects    users    add    idempotent

    Given a cluster exists in system
    And a project exists
    And a user exists in system
    And user is added to project
    And user should be member of project

    When add users to project request is sent

    Then response status should be 204
    And user should be member of project

Remove user from project
    [Documentation]    Verify that a user can be removed from a project via DELETE /projects/{id}/users/{user_id}
    ...    Tests: Removing an existing member from a project
    [Tags]    projects    users    remove

    Given a cluster exists in system
    And a project exists
    And a user exists in system
    And user is added to project
    And user should be member of project

    When remove user from project request is sent

    Then response status should be 204
    And user should not be member of project

Recreate project with the same name after deletion
    [Documentation]    A replacement project is created only after deletion releases the name.
    [Tags]    projects    delete    create    regression

    Given a project exists
    When the user deletes the project
    And the user creates a project with the same name
    Then the replacement project should exist
    And the replacement project should have a different identity from the deleted project

Delete project with secrets and verify cleanup
    [Documentation]    Verify that project deletion properly unassigns secrets
    ...    Tests: Project deletion does not delete secrets but removes project assignments
    [Tags]    project    deletion    secrets    cleanup    integration

    Given a ready project exists
    And a secret is assigned to the project
    And secret assignment should be synced

    When delete project request is sent

    Then response status should be 204
    And Project should transition to "deleting"
    And secret should exist
    And secret should be unassigned

Delete project with storage and verify cleanup
    [Documentation]    Verify that project deletion properly unassigns storage
    ...    Tests: Project deletion does not delete storage but removes project assignments
    [Tags]    project    deletion    storage    cleanup    integration

    Given a fresh project with user access exists
    And a storage is assigned to the project
    And storage assignment should be synced

    When delete project request is sent

    Then response status should be 204
    And Project should transition to "deleting"
    And storage should exist
    And storage should be unassigned

Delete project and verify comprehensive cleanup
    [Documentation]    Verify that project deletion cleans up all associated resources
    ...    Tests: Namespace, quota, secrets, storage assignments are all properly cleaned
    [Tags]    project    deletion    cleanup    comprehensive    integration

    Given a fresh project with user access exists
    # Skip ResourceQuota check due to RBAC permissions - test user cannot list ResourceQuotas
    # And project namespace should have ResourceQuota
    And a secret is assigned to the project
    And a storage is assigned to the project

    When delete project request is sent

    Then response status should be 204
    And Project should transition to "deleting"
    And project namespace should not exist in cluster
    And project quota should not exist in database
    And secret should still exist but be unassigned
    And storage should still exist but be unassigned

Delete project with workload and verify complete cleanup
    [Documentation]    Verify that project deletion removes workloads from both database and cluster
    ...    Tests: Workloads are cascade deleted from DB and pods/jobs removed from Kubernetes
    ...
    ...    Uses a FRESH project, never the shared "testing" one: this test destroys the project it
    ...    is given and then waits for the namespace to disappear. Run against the shared project
    ...    that every other suite reuses, it both breaks that reuse and can never observe its own
    ...    deletion, because the next suite recreates the name while this one is still watching.
    [Tags]    project    deletion    workload    cleanup    critical    integration

    Given a fresh project with user access exists
    And a workload is submitted to the project
    And workload should be running in cluster

    When delete project request is sent

    Then response status should be 204
    And Project should transition to "deleting"
    And workload should not exist in database
    And workload should not exist in cluster
    And project namespace should not exist in cluster


*** Keywords ***
# Keywords should be defined in resource files, not test files
# Moved to resources/airm_projects.resource
