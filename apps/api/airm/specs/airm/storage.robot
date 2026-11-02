# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for storage management via AIRM API.
...                 Tests storage lifecycle: create, project assignment, status transitions, and deletion.
...                 Storage resources are organization-scoped S3 configurations assigned to projects.
Resource            ../resources/airm_storage.resource
Resource            ../resources/airm_projects.resource
Resource            ../resources/airm_secrets.resource
Library             Collections
Test teardown       Run keywords
...                 Clean Up S3 Test Objects    AND
...                 Clean up all created storage    AND
...                 Clean up all created secrets    AND
...                 Clean up all created projects


*** Test Cases ***
Create storage with valid S3 spec
    [Documentation]    Verify that a storage can be created with valid S3 specification
    ...    Tests: POST /storages → storage creation with UNASSIGNED status
    [Tags]    storage    smoke

    Given a valid ExternalSecret manifest exists
    And a secret for storage credentials exists
    And a valid S3 storage spec exists

    When storage is created without project assignment

    Then storage should be visible via API
    And storage should have valid ID and status
    And storage status should be "Unassigned"

Create storage and assign to project
    [Documentation]    Verify that storage can be created and assigned to a project
    ...    Tests: POST /storages with projectIds → storage creation with PENDING status
    [Tags]    storage    project    assignment

    Given a ready project with user access exists
    And a valid ExternalSecret manifest exists
    And a secret for storage credentials exists
    And a valid S3 storage spec exists

    When storage is created and assigned to project

    Then storage should be visible via API
    And storage should have valid ID and status
    And storage status should be "Pending"
    And storage should have "1" project assignment

Storage transitions to synced
    [Documentation]    Verify that storage transitions from Pending to Synced
    ...    Tests: Storage status updates based on project sync status
    [Tags]    storage    status

    Given a ready project with user access exists
    And a valid ExternalSecret manifest exists
    And a secret for storage credentials exists
    And a valid S3 storage spec exists
    And storage is created and assigned to project

    When storage transitions to "Synced"

    Then storage status should be "Synced"
    And all storage project assignments should be synced

Assign storage to additional project
    [Documentation]    Verify that storage can be assigned to additional projects
    ...    Tests: PUT /storages/{id}/assign → add project assignments
    [Tags]    storage    project    assignment

    Given a ready project with user access exists
    And a second ready project with user access exists
    And a valid ExternalSecret manifest exists
    And a secret for storage credentials exists
    And a valid S3 storage spec exists
    And storage is created and assigned to project
    And storage transitions to "Synced"

    When storage is assigned to second project

    Then storage should have "2" project assignment
    And storage status should be "Pending"
    And storage transitions to "Synced"

Remove project assignment
    [Documentation]    Verify that project assignment can be removed
    ...    Tests: PUT /storages/{id}/assign → remove project assignments
    [Tags]    storage    project    unassignment

    Given a ready project with user access exists
    And a valid ExternalSecret manifest exists
    And a secret for storage credentials exists
    And a valid S3 storage spec exists
    And storage is created and assigned to project
    And storage transitions to "Synced"

    When storage project assignment is removed

    Then storage transitions to "Unassigned"
    And storage should have "0" project assignment

Delete unassigned storage
    [Documentation]    Verify that unassigned storage can be deleted immediately
    ...    Tests: DELETE /storages/{id} → immediate deletion for unassigned storage
    [Tags]    storage    deletion

    Given a valid ExternalSecret manifest exists
    And a secret for storage credentials exists
    And a valid S3 storage spec exists
    And storage is created without project assignment

    When storage is deleted

    Then storage should not be visible via API

Delete assigned storage
    [Documentation]    Verify that assigned storage transitions to DELETING
    ...    Tests: DELETE /storages/{id} → async deletion for assigned storage
    [Tags]    storage    deletion

    Given a ready project with user access exists
    And a valid ExternalSecret manifest exists
    And a secret for storage credentials exists
    And a valid S3 storage spec exists
    And storage is created and assigned to project
    And storage transitions to "Synced"

    When storage is deleted

    Then storage status should be "Deleting"

Reject duplicate storage name
    [Documentation]    Verify that duplicate storage names are rejected
    ...    Tests: Unique constraint on storage name per organization
    [Tags]    storage    validation    negative

    Given a valid ExternalSecret manifest exists
    And a secret for storage credentials exists
    And a valid S3 storage spec exists
    And storage is created without project assignment

    When attempting to create storage with same name

    Then storage creation should fail with conflict

Reject invalid storage name
    [Documentation]    Verify that invalid storage names are rejected
    ...    Tests: Name format validation (DNS subdomain)
    [Tags]    storage    validation    negative

    Given a valid ExternalSecret manifest exists
    And a secret for storage credentials exists
    And a valid S3 storage spec exists

    When attempting to create storage with invalid name

    Then storage creation should fail with validation error

Reject non-existent secret reference
    [Documentation]    Verify that non-existent secret references are rejected
    ...    Tests: Secret existence validation
    [Tags]    storage    validation    negative

    Given a valid S3 storage spec exists

    When attempting to create storage with non-existent secret

    Then storage creation should fail with not found

List storage for organization
    [Documentation]    Verify that storage resources can be listed for organization
    ...    Tests: GET /storages → list all organization storage resources
    [Tags]    storage    list

    Given a valid ExternalSecret manifest exists
    And a secret for storage credentials exists
    And a valid S3 storage spec exists
    And storage is created without project assignment

    When listing all storage

    Then at least "1" storage should be visible

Recreate storage with same name after deletion
    [Documentation]    Verify that storage can be recreated with the same name after deletion
    ...    Tests: Storage deletion completes fully and name constraint allows recreation
    [Tags]    storage    deletion    recreation    regression

    Given a valid ExternalSecret manifest exists
    And a secret for storage credentials exists
    And a valid S3 storage spec exists
    And storage is created without project assignment
    ${original_name}=    Get storage name
    ${original_id}=    Set Variable    ${TEST_STORAGE_ID}

    When storage is deleted
    And wait for storage deletion to complete

    Then storage with same name "${original_name}" can be created
    And new storage should have different ID than "${original_id}"

S3 data persists after storage deletion
    [Documentation]    Verify that S3 bucket data is NOT deleted when storage resource is deleted
    ...    This is expected behavior - storage resources manage access, not data lifecycle
    ...    Tests: Storage deletion does not clean up S3 bucket contents (by design)
    [Tags]    storage    deletion    s3

    Given a ready project with user access exists
    And a valid ExternalSecret manifest exists
    And a secret for storage credentials exists
    And a valid S3 storage spec exists
    And storage is created and assigned to project
    And storage transitions to "Synced"
    ${bucket_url}=    Get storage bucket URL
    ${test_data}=    Set Variable    test-data-should-be-deleted

    When test data "${test_data}" is written to S3 bucket
    And storage is deleted
    And wait for storage deletion to complete

    Then S3 bucket data should still exist    ${bucket_url}    ${test_data}
    # This verifies expected behavior - storage manages access, not data lifecycle

Storage pointing to same S3 bucket can access data from previous storage
    [Documentation]    Verify that new storage pointing to same S3 bucket can access existing data
    ...    This is expected behavior - multiple storage resources can point to the same S3 bucket
    ...    Tests: Storage resources pointing to the same bucket share access to bucket data
    [Tags]    storage    deletion    s3    multi-project

    Given a ready project with user access exists
    And a valid ExternalSecret manifest exists
    And a secret for storage credentials exists
    And a valid S3 storage spec exists
    And storage is created and assigned to project
    And storage transitions to "Synced"
    ${bucket_url}=    Get storage bucket URL
    ${test_data}=    Set Variable    sensitive-data-from-deleted-storage

    When test data "${test_data}" is written to S3 bucket
    And storage is deleted
    And wait for storage deletion to complete
    And new storage is created pointing to same bucket "${bucket_url}"

    Then new storage can access data from previous storage "${test_data}"
    # This verifies expected behavior - multiple storage resources can share the same S3 bucket
