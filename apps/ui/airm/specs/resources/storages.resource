# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Feature-layer keywords for AIRM UI storage management testing.
...                 Composes page-layer interactions and API preconditions into
...                 business-meaningful BDD keywords for storage CRUD operations.
Resource            common/session.resource
Resource            common/navigation.resource
Resource            pages/storages_page.resource

# API resources for preconditions (resolved via pythonpath from AIRM API specs)
Resource            resources/airm_storage.resource
Resource            resources/airm_secrets.resource
Resource            resources/airm_projects.resource
Resource            resources/common/airm_resource_cleanup.resource

Library             Collections
Library             TestPrefix


*** Keywords ***
# =============================================================================
# Precondition keywords (Given steps)
# =============================================================================

An admin user is on the storages page
    [Documentation]    Logs in as admin and navigates to the storages page.

    Admin user is logged in
    Navigate to storages page    ${UI_BASE_URL}
    Storages page should be loaded

An S3 storage secret exists via API
    [Documentation]    Creates an S3-scoped secret via the API for use in storage creation.
    ...                Sets UI_SECRET_NAME and TEST_STORAGE_SECRET_ID.

    A valid ExternalSecret manifest exists
    A secret for storage credentials exists

    # Retrieve the secret name from the API for use in UI dropdown selection
    ${response}=    Get secret    ${TEST_STORAGE_SECRET_ID}    expected_status=200
    ${secret_name}=    Get From Dictionary    ${response.json()}    name
    Set Test Variable    ${UI_SECRET_NAME}    ${secret_name}
    Track Secret For Cleanup    ${TEST_STORAGE_SECRET_ID}

An unassigned storage exists via API
    [Documentation]    Creates an S3 storage via the API without project assignment.
    ...                Requires an S3 secret to already exist.
    ...                Sets TEST_STORAGE_ID and TEST_STORAGE_NAME.

    ${timestamp}=    Evaluate    str(int(__import__('time').time()))[-6:]
    ${storage_name}=    Test Name    stor-${timestamp}
    A valid S3 storage spec exists
    Storage is created without project assignment    storage_name=${storage_name}
    Set Test Variable    ${TEST_STORAGE_NAME}    ${storage_name}
    Track Storage For Cleanup    ${TEST_STORAGE_ID}

A ready project exists via API
    [Documentation]    Creates a project via API and waits for it to be ready.
    ...                Sets TEST_PROJECT_ID, TEST_PROJECT, and TEST_PROJECT_NAME.

    A ready project with user access exists
    Set Test Variable    ${TEST_PROJECT_NAME}    ${TEST_PROJECT}[name]

# =============================================================================
# Action keywords (When steps)
# =============================================================================

The user creates a new S3 storage with bucket URL and secret
    [Documentation]    Fills in the S3 storage creation form with a unique name
    ...                and submits it. Uses the secret created via API.

    ${timestamp}=    Evaluate    str(int(__import__('time').time()))[-6:]
    ${storage_name}=    Test Name    stor-${timestamp}
    Set Test Variable    ${TEST_STORAGE_NAME}    ${storage_name}

    Click add storage button
    Select S3 bucket type
    Storage form should be visible
    Fill storage name    ${storage_name}
    Fill bucket URL    http://minio.example.com:9000/e2e-test-bucket
    Select storage secret    ${UI_SECRET_NAME}
    Click add bucket submit

The user assigns the storage to the project
    [Documentation]    Opens the assignment dialog for the storage and selects the project.

    Open storage actions menu    ${TEST_STORAGE_NAME}
    Click edit assignment action
    Assignment dialog should be visible
    Select project in assignment dialog    ${TEST_PROJECT_NAME}
    Click save assignment

The user deletes the storage and confirms
    [Documentation]    Deletes the test storage through the actions menu and confirms.

    Open storage actions menu    ${TEST_STORAGE_NAME}
    Click delete action
    Delete confirmation dialog should be visible
    Confirm storage deletion

# =============================================================================
# Assertion keywords (Then steps)
# =============================================================================

Storages should be listed with type and status columns
    [Documentation]    Verifies the storages table is visible and has rows with data.

    Storages page should be loaded
    ${names}=    Get storage row names
    ${count}=    Get Length    ${names}
    Should Be True    ${count} > 0
    ...    msg=Expected at least one storage row, found ${count}
    Log    Found ${count} storage rows    INFO

The new storage should appear in the storages list
    [Documentation]    Verifies that the newly created storage appears in the table.

    Storage row should exist    ${TEST_STORAGE_NAME}
    Log    Storage ${TEST_STORAGE_NAME} is visible in the list    INFO

The storage should show a project assignment
    [Documentation]    Verifies the Assigned to column shows a project name.

    # Wait for the UI to refresh after assignment
    Wait Until Keyword Succeeds    30s    3s
    ...    Verify storage assignment is visible    ${TEST_STORAGE_NAME}

Verify storage assignment is visible
    [Documentation]    Helper to verify a storage row shows a project assignment.
    [Arguments]    ${storage_name}

    # Column index 3 = Assigned to (0=Type, 1=Status, 2=Scope, 3=Assigned to)
    ${assigned}=    Get storage row cell text    ${storage_name}    ${3}
    Should Not Be Equal    ${assigned}    —
    ...    msg=Storage ${storage_name} should have a project assignment but shows —
    Should Not Be Empty    ${assigned}
    ...    msg=Storage ${storage_name} Assigned to column is empty
    Log    Storage ${storage_name} is assigned to: ${assigned}    INFO

The storage should not be in the list
    [Documentation]    Verifies that the storage is no longer visible in the table.

    Storage row should not exist    ${TEST_STORAGE_NAME}
    Log    Storage ${TEST_STORAGE_NAME} is no longer in the list    INFO
