# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for secrets management via AIRM API.
...                 Tests secret lifecycle: create, project assignment, status transitions, and deletion.
...                 Secrets are organization-scoped ExternalSecret manifests assigned to projects.
Resource            ../resources/airm_secrets.resource
Resource            ../resources/airm_projects.resource
Resource            ../resources/kubectl_verification.resource
Library             Collections
Test Teardown       Clean Up Secret Test Resources

*** Keywords ***
Clean Up Secret Test Resources
    [Documentation]    Clean up all resources created during secret tests
    Clean Up All Created Secrets
    Clean Up All Created Projects


*** Test Cases ***
Create secret with valid manifest
    [Documentation]    Verify that a secret can be created with valid ExternalSecret manifest
    ...    Tests: POST /secrets → secret creation with UNASSIGNED status
    [Tags]    secret    smoke

    Given a valid ExternalSecret manifest exists

    When secret is created without project assignment

    Then secret should be visible via API
    And secret should have valid ID and status
    And secret status should be "Unassigned"

Create secret and assign to project
    [Documentation]    Verify that secret can be created and assigned to a project
    ...    Tests: POST /secrets with projectIds → secret creation with initial status (Pending or Synced)
    [Tags]    secret    project    assignment

    Given a ready project with user access exists
    And a valid ExternalSecret manifest exists

    When secret is created and assigned to project

    Then secret should be visible via API
    And secret should have valid ID and status
    And secret status should be any of "Pending, Synced"  # Can be immediately synced
    And secret should have "1" project assignment

Secret transitions to Synced
    [Documentation]    Verify that secret transitions from Pending to Synced
    ...    Tests: Secret status updates based on project sync status
    [Tags]    secret    status

    Given a ready project with user access exists
    And a valid ExternalSecret manifest exists
    And secret is created and assigned to project

    When secret transitions to "Synced"

    Then secret status should be "Synced"
    And all project assignments should be synced

Secret has ExternalSecret in cluster
    [Documentation]    Verify that secret creates ExternalSecret in project namespace
    ...    Tests: Kubernetes ExternalSecret creation for secret sync
    [Tags]    secret    kubernetes    integration

    Given a ready project with user access exists
    And a valid ExternalSecret manifest exists
    And secret is created and assigned to project
    And secret transitions to "Synced"

    Then secret ExternalSecret should exist in cluster

Assign secret to additional project
    [Documentation]    Verify that secret can be assigned to additional projects
    ...    Tests: PUT /secrets/{id}/assign → add project assignments
    [Tags]    secret    project    assignment

    Given a ready project with user access exists
    And airm_projects.A Second Ready Project With User Access Exists
    And a valid ExternalSecret manifest exists
    And secret is created and assigned to project
    And secret transitions to "Synced"

    When secret is assigned to second project

    Then secret should have "2" project assignments
    And secret status should be any of "Pending, Synced"  # Can be immediately synced
    And secret transitions to "Synced"

Remove project assignment
    [Documentation]    Verify that project assignment can be removed
    ...    Tests: PUT /secrets/{id}/assign → remove project assignments
    [Tags]    secret    project    unassignment

    Given a ready project with user access exists
    And a valid ExternalSecret manifest exists
    And secret is created and assigned to project
    And secret transitions to "Synced"

    When project assignment is removed

    Then secret transitions to "Unassigned"
    And secret should have "0" project assignments
    And secret ExternalSecret should not exist in cluster

Delete unassigned secret
    [Documentation]    Verify that unassigned secret can be deleted immediately
    ...    Tests: DELETE /secrets/{id} → immediate deletion for unassigned secret
    [Tags]    secret    deletion

    Given a valid ExternalSecret manifest exists
    And secret is created without project assignment

    When secret is deleted

    Then secret should not be visible via API

Delete assigned secret
    [Documentation]    Verify that assigned secret transitions to DELETING
    ...    Tests: DELETE /secrets/{id} → async deletion for assigned secret
    [Tags]    secret    deletion

    Given a ready project with user access exists
    And a valid ExternalSecret manifest exists
    And secret is created and assigned to project
    And secret transitions to "Synced"

    When secret is deleted

    Then secret should be deleted or deleting
    And wait for secret deletion to complete

Reject duplicate secret name
    [Documentation]    Verify that duplicate secret names are rejected
    ...    Tests: Unique constraint on secret name per organization
    [Tags]    secret    validation    negative

    Given a valid ExternalSecret manifest exists
    And secret is created without project assignment

    When attempting to create secret with same name

    Then secret creation should fail with conflict

Reject invalid ExternalSecret manifest
    [Documentation]    Verify that invalid ExternalSecret manifests are rejected
    ...    Tests: Manifest validation for apiVersion, kind, spec
    [Tags]    secret    validation    negative

    Given an invalid ExternalSecret manifest exists

    When attempting to create secret with invalid manifest

    Then secret creation should fail with validation error

List secrets for organization
    [Documentation]    Verify that secrets can be listed for organization
    ...    Tests: GET /secrets → list all organization secrets
    [Tags]    secret    list

    Given a valid ExternalSecret manifest exists
    And secret is created without project assignment

    When listing all secrets

    Then at least "1" secret should be visible

Workload can use synced secret
    [Documentation]    Verify that a workload can access secret values
    ...    Tests: End-to-end secret usage in pod via environment variable
    [Tags]    secret    workload    integration
    [Teardown]    Clean up test pod

    Given a ready project with user access exists
    And a valid ExternalSecret manifest exists
    And secret is created and assigned to project
    And secret transitions to synced

    When a pod that uses the secret is deployed

    Then pod can access secret values

External secret with invalid path transitions to error state
    [Documentation]    Verify that external secret with valid manifest but invalid external path transitions to SyncedError
    ...    Tests: Secret status updates to SyncedError when external path cannot be resolved
    [Tags]    secret    status    error    negative

    Given a ready project with user access exists
    And a valid ExternalSecret manifest with invalid path exists

    When secret with invalid path is created and assigned to project

    Then secret should be visible via API
    And secret should have valid ID and status
    And secret initial status should be pending
    And secret with invalid path transitions to error state
    And secret status should be synced error

Recreate secret with same name after deletion
    [Documentation]    Verify that a secret can be recreated with the same name after deletion
    ...    Tests: Secret deletion completes and name constraint allows recreation
    [Tags]    secret    deletion    recreation    regression

    Given a valid ExternalSecret manifest exists
    And secret is created without project assignment
    ${original_name}=    Get secret name
    ${original_id}=    Set Variable    ${TEST_SECRET_ID}

    When secret is deleted
    And wait for secret deletion to complete

    Then secret with same name "${original_name}" can be created
    And new secret should have different ID than "${original_id}"
