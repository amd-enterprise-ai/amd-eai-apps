# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for Secrets UI features.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)
Resource            common/session.resource
Resource            pages/secrets_page.resource
Resource            pages/workspaces_page.resource


*** Keywords ***
# =============================================================================
# Given keywords (UI preconditions)
# =============================================================================

User is on secrets page
    [Documentation]    Navigates to the Secrets page.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to secrets page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

# =============================================================================
# When keywords (actions)
# =============================================================================

User creates a secret "${name}" with use case "${use_case}" and value "${value}"
    [Documentation]    Fills in and submits the Add Secret form.

    Click add secret button
    Wait for add secret drawer
    Fill secret name    ${name}
    Select secret use case    ${use_case}
    Fill secret value    ${value}
    Click submit secret button
    Wait for drawer to close

User creates an S3 secret "${name}" with access key "${access_key_id}" and secret key "${secret_access_key}"
    [Documentation]    Fills in and submits the Add Secret form for use case S3.

    Click add secret button
    Wait for add secret drawer
    Fill secret name    ${name}
    Select secret use case    S3
    Fill S3 Access Key ID    ${access_key_id}
    Fill S3 Secret Access Key    ${secret_access_key}
    Click submit secret button
    Wait for drawer to close

User deletes secret "${name}"
    [Documentation]    Deletes a secret via the actions menu and confirms deletion.

    Click delete on secret row    ${name}
    Wait for confirmation modal
    Click confirm delete button
    Wait for confirmation modal to close

User opens the delete confirmation for secret "${name}"
    [Documentation]    Opens the delete confirmation modal for a secret without confirming.

    Click delete on secret row    ${name}
    Wait for confirmation modal

User switches to project "${project_name}"
    [Documentation]    Switches the active project using the project selector.

    Select project    ${project_name}

# =============================================================================
# Then keywords (verification)
# =============================================================================

Secret "${name}" should be visible in the list
    [Documentation]    Verifies that a secret with the given name appears in the table.

    Wait Until Keyword Succeeds    15s    2s
    ...    Secret row should contain name    ${name}

Secret "${name}" should not be visible in the list
    [Documentation]    Verifies that a secret with the given name is not shown in the table.

    Secret row should not be visible    ${name}

The delete confirmation should reference "${name}"
    [Documentation]    Verifies the delete confirmation modal references the given user-facing name.

    ${modal_text}=    Get confirmation modal text
    Should Contain    ${modal_text}    ${name}
    ...    msg=Expected delete confirmation to reference "${name}" but it did not. Modal text: ${modal_text}

The delete confirmation should not reference "${name}"
    [Documentation]    Verifies the delete confirmation modal does not reference the given name.

    ${modal_text}=    Get confirmation modal text
    Should Not Contain    ${modal_text}    ${name}
    ...    msg=Expected delete confirmation to NOT reference "${name}" but it did. Modal text: ${modal_text}

Secrets list should contain at least "${count}" secrets
    [Documentation]    Verifies the secrets table has at least the expected number of rows.

    ${actual}=    Get secret row count
    Should Be True    ${actual} >= ${count}
    ...    msg=Expected at least ${count} secrets, found ${actual}

Secrets table should contain text "${text}"
    [Documentation]    Verifies the secrets table contains expected text.

    ${table_text}=    Get secrets table text
    Should Contain    ${table_text}    ${text}

Secrets list should have exactly "${count}" secrets
    [Documentation]    Verifies the secrets table has exactly the expected number of rows.

    Wait Until Keyword Succeeds    15s    2s
    ...    Verify exact secret count    ${count}

Verify exact secret count
    [Documentation]    Helper: verifies exact secret row count (used with polling).
    [Arguments]    ${expected_count}

    ${actual}=    Get secret row count
    Should Be Equal As Integers    ${actual}    ${expected_count}
    ...    msg=Expected exactly ${expected_count} secrets, found ${actual}

# =============================================================================
# Workspace deploy form keywords (secret type filtering)
# =============================================================================

The user opens the workspace deploy form
    [Documentation]    Navigates to the workspaces page and opens the deploy wizard
    ...                on the first available workspace.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to workspaces page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]
    Click first workspace deploy button
    Wait for deploy wizard

The imagePullSecrets dropdown should only show image pull secrets
    [Documentation]    Opens the imagePullSecrets dropdown and verifies its contents are visible.

    Open image pull secrets dropdown

The imagePullSecrets dropdown should contain "${name}"
    [Documentation]    Verifies the imagePullSecrets dropdown options include the given secret name.

    ${options_text}=    Get image pull secrets options text
    Should Contain    ${options_text}    ${name}
    ...    msg=Expected imagePullSecrets dropdown to contain "${name}" but it was not found

The imagePullSecrets dropdown should not contain "${name}"
    [Documentation]    Verifies the imagePullSecrets dropdown options do not include the given secret name.

    ${options_text}=    Get image pull secrets options text
    Should Not Contain    ${options_text}    ${name}
    ...    msg=Expected imagePullSecrets dropdown to NOT contain "${name}" but it was found
