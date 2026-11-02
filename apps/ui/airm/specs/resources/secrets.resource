# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Feature-layer keywords for AIRM UI secrets testing.
...                 Composes page-level interactions into business-meaningful keywords
...                 that verify secrets operations (view, create, delete, search, assign)
...                 and autodiscovery through the browser UI.
...
...                 Layer: Feature (tests import this, NOT page resources directly)
Resource            common/session.resource
Resource            pages/secrets_page.resource
Library             Collections


*** Keywords ***
# =============================================================================
# Precondition keywords (Given steps)
# =============================================================================

An admin user is logged in
    [Documentation]    Logs in as a platform administrator who can access the secrets page.
    Admin user is logged in

An admin user is on the secrets page
    [Documentation]    Logs in as admin and navigates to the secrets page.
    Admin user is logged in
    Navigate to secrets page    ${UI_BASE_URL}

An organization-level secret and a ready project exist
    [Documentation]    Creates an unassigned organization-level secret and a ready project
    ...                via API. Sets TEST_SECRET_NAME and TEST_PROJECT_NAME.
    ...                Requires: TEST_VALID_MANIFEST (from 'a valid ExternalSecret manifest exists')
    A valid ExternalSecret manifest exists
    Secret is created without project assignment    ${TEST_SECRET_NAME}
    A ready project with user access exists
    Set Test Variable    ${TEST_PROJECT_NAME}    ${TEST_PROJECT}[name]

The user is on the secrets page
    [Documentation]    Navigates to the admin secrets page.
    ...                Expects ${UI_BASE_URL} to be set via login.
    Navigate to secrets page    ${UI_BASE_URL}

# =============================================================================
# Action keywords (When steps)
# =============================================================================

The user views the secrets page
    [Documentation]    Navigates to the admin secrets page.
    ...                Expects ${UI_BASE_URL} to be set via login.
    Navigate to secrets page    ${UI_BASE_URL}

The user creates a secret with the test manifest
    [Documentation]    Opens the create dialog and submits a new secret with the test manifest.
    ...                Expects ${TEST_VALID_MANIFEST} and ${TEST_SECRET_NAME} to be set
    ...                by a precondition keyword. After creation, finds the secret via API
    ...                and tracks it for cleanup.
    Click create new secret button
    Fill secret yaml field    ${TEST_VALID_MANIFEST}
    Click add secret submit
    Add secret dialog should be closed
    # Track the UI-created secret for cleanup via API
    Find and track secret by name    ${TEST_SECRET_NAME}

The user deletes the secret and confirms
    [Documentation]    Opens the actions menu for the test secret, clicks delete, and confirms.
    ...                Expects ${TEST_SECRET_NAME} to be set.
    Open actions menu for secret    ${TEST_SECRET_NAME}
    Click delete in actions menu
    Confirm delete in dialog

The user searches for "${search_text}"
    [Documentation]    Enters search text in the secrets table search field.
    Enter secret search text    ${search_text}

The user assigns the secret to the project
    [Documentation]    Opens the assignment dialog for the test secret and selects the project.
    ...                Expects ${TEST_SECRET_NAME} and ${TEST_PROJECT_NAME} to be set.
    Open actions menu for secret by row button    ${TEST_SECRET_NAME}
    Click edit assignment in actions menu
    Assignment dialog should be visible
    Select project in assignment dialog    ${TEST_PROJECT_NAME}
    Click save assignment

The user refreshes the secrets page
    [Documentation]    Reloads the secrets page to pick up backend state changes.
    ...                Expects ${UI_BASE_URL} to be set via login.
    Navigate to secrets page    ${UI_BASE_URL}

# =============================================================================
# Assertion keywords (Then steps)
# =============================================================================

The kubectl secret should be visible in the secrets table
    [Documentation]    Verifies the autodiscovered kubectl secret appears in the table.
    ...                Resolves the secret name from the test state set during preconditions.
    ${name}=    The kubectl secret name
    Wait Until Keyword Succeeds    15s    2s
    ...    Secret row should exist with name    ${name}

The kubectl secret should not be visible in the secrets table
    [Documentation]    Verifies the autodiscovered kubectl secret is no longer in the table.
    ...                Resolves the secret name from the test state set during preconditions.
    ${name}=    The kubectl secret name
    Wait Until Keyword Succeeds    15s    2s
    ...    Secret row should not exist with name    ${name}

The kubectl secret should be identified as "${secret_type}"
    [Documentation]    Verifies the autodiscovered kubectl secret row shows the expected
    ...                type indicator, confirming the UI distinguishes the secret source.
    ${name}=    The kubectl secret name
    Secret type indicator should exist in row    ${name}    ${secret_type}

The secrets table should distinguish secret sources
    [Documentation]    Verifies that the secrets table contains both ExternalSecret and
    ...                KubernetesSecret type indicators, confirming the UI renders
    ...                different secret sources as distinguishable.
    Secret type indicator should exist    ExternalSecret
    Secret type indicator should exist    KubernetesSecret

Secrets should be listed with table columns
    [Documentation]    Verifies that the secrets table is visible, has the expected column
    ...                headers, and contains at least one data row.
    Verify secrets table has expected columns
    ${count}=    Get secrets table row count
    Should Be True    ${count} > 0
    ...    msg=Expected at least one secret in the table, but found ${count} rows

Secret "${name}" should be visible in the secrets table
    [Documentation]    Verifies a secret with the given name appears in the table.
    Wait Until Keyword Succeeds    15s    2s
    ...    Secret row should exist with name    ${name}

Secret "${name}" should not be visible in the secrets table
    [Documentation]    Verifies a secret with the given name is no longer in the table.
    Wait Until Keyword Succeeds    15s    2s
    ...    Secret row should not exist with name    ${name}

Secret "${name}" should show scope "${expected_scope}"
    [Documentation]    Verifies the scope column for the given secret row.
    ${scope}=    Get secret row cell text    ${name}    5
    Should Contain    ${scope}    ${expected_scope}
    ...    msg=Expected scope "${expected_scope}" for secret "${name}", but got "${scope}"

Secret "${name}" should show type "${expected_type}"
    [Documentation]    Verifies the type column for the given secret row.
    ${type}=    Get secret row cell text    ${name}    2
    Should Contain    ${type}    ${expected_type}
    ...    msg=Expected type "${expected_type}" for secret "${name}", but got "${type}"

The project count for the secret is updated
    [Documentation]    Verifies the Assigned to column for the secret shows a project assignment.
    ...                Expects ${TEST_SECRET_NAME} to be set.
    Wait Until Keyword Succeeds    30s    3s
    ...    Verify secret assignment is visible    ${TEST_SECRET_NAME}

Verify secret assignment is visible
    [Documentation]    Helper to verify a secret row shows a project assignment.
    [Arguments]    ${secret_name}

    ${assigned}=    Get secret assigned to text    ${secret_name}
    Should Not Be Equal    ${assigned}    —
    ...    msg=Secret ${secret_name} should have a project assignment but shows dash
    Should Not Be Empty    ${assigned}
    ...    msg=Secret ${secret_name} Assigned to column is empty
    Log    Secret ${secret_name} is assigned to: ${assigned}    INFO

The secrets table should only show secrets matching "${search_text}"
    [Documentation]    Verifies that the search filter narrowed the results to show only
    ...                secrets whose name contains the search text. Retries to allow the
    ...                client-side filter debounce to complete.
    Wait Until Keyword Succeeds    15s    2s
    ...    Verify all visible secrets match search    ${search_text}

Verify all visible secrets match search
    [Documentation]    Helper: checks that every visible row name contains the search text.
    [Arguments]    ${search_text}

    ${count}=    Get secrets table row count
    Should Be True    ${count} > 0
    ...    msg=Expected at least one row matching "${search_text}"
    ${names}=    Get all visible secret names
    FOR    ${name}    IN    @{names}
        ${lower_name}=    Evaluate    "${name}".lower()
        ${lower_search}=    Evaluate    "${search_text}".lower()
        Should Contain    ${lower_name}    ${lower_search}
        ...    msg=Row "${name}" does not match search text "${search_text}"
    END

# =============================================================================
# Resource resolver keywords
# =============================================================================

The kubectl secret name
    [Documentation]    Returns the name of the kubectl secret created during preconditions.
    ...                Validates that the test state variable has been set.
    Should Not Be Equal    ${TEST_KUBECTL_SECRET_NAME}    ${None}
    ...    msg=TEST_KUBECTL_SECRET_NAME not set. Apply a secret via kubectl first.
    RETURN    ${TEST_KUBECTL_SECRET_NAME}

# =============================================================================
# Internal helper keywords
# =============================================================================

Verify secrets table has expected columns
    [Documentation]    Verifies the secrets table header contains the expected column names.
    ${headers}=    Get secrets table column headers
    ${expected}=    Create List    Name    Type    Use case    Status    Scope    Assigned to    Updated at
    FOR    ${col}    IN    @{expected}
        List Should Contain Value    ${headers}    ${col}
        ...    msg=Expected column "${col}" not found in table headers: ${headers}
    END

Find and track secret by name
    [Documentation]    Finds a secret by name via the AIRM API and tracks it for cleanup.
    ...                Used after UI-based secret creation to ensure proper teardown.
    [Arguments]    ${secret_name}

    Wait Until Keyword Succeeds    30s    5s
    ...    Find auto-discovered secret in AIRM API    ${secret_name}
