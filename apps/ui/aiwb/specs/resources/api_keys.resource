# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for API key UI features.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)
Library             DateTime
Resource            common/session.resource
Resource            pages/api_keys_page.resource


*** Keywords ***
# =============================================================================
# Suite setup
# =============================================================================

Initialize API Key Suite
    [Documentation]    Generates a unique API key name prefix for this suite run
    ...                and initializes project tracking.

    ${epoch}=    Get Current Date    result_format=epoch
    ${suffix}=    Evaluate    int(${epoch})
    Set Suite Variable    ${TEST_API_KEY_NAME}    e2e-key-${suffix}

# =============================================================================
# Given keywords (UI preconditions)
# =============================================================================

User is on API keys page
    [Documentation]    Navigates to the API Keys page via the sidebar link.
    ...                Expects ${TEST_PROJECT} to be set.

    Navigate to API keys page    ${TEST_PROJECT}[name]

# =============================================================================
# When keywords (actions)
# =============================================================================

User creates API key "${key_name}"
    [Documentation]    Creates a new API key with the given name through the UI.
    ...                Retries the entire open-fill-submit sequence because the
    ...                DrawerForm can close unexpectedly when React re-renders due
    ...                to async query resolution or project context changes.

    Wait Until Keyword Succeeds    60s    3s    Open fill and submit API key form    ${key_name}

Open fill and submit API key form
    [Documentation]    Opens the drawer, fills the name, submits, and waits for
    ...                the success drawer. Designed to be retried as a unit —
    ...                includes drawer opening so that if the drawer closes during
    ...                a previous attempt, it gets reopened.
    [Arguments]    ${key_name}

    # Dismiss any drawer left open from a previous failed attempt
    ${drawer_open}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${CREATE_DRAWER_TITLE}    visible    timeout=1s
    IF    ${drawer_open}
        Keyboard Key    press    Escape
        Wait For Elements State    ${CREATE_DRAWER_TITLE}    hidden    timeout=5s
    END

    Click create API key button
    Fill API key name    ${key_name}
    Submit API key form
    Wait For Elements State    ${KEY_CREATED_TITLE}    visible    timeout=15s

User closes key created drawer
    [Documentation]    Clicks Done on the key created drawer to return to the table.

    Click done on key created drawer

User opens edit drawer for API key "${key_name}"
    [Documentation]    Opens the Edit API Key drawer via the row actions menu.

    Click actions menu on API key row    ${key_name}
    Click edit action in actions menu
    Wait for edit drawer

User deletes API key "${key_name}"
    [Documentation]    Deletes an API key via the actions menu and confirms the deletion.

    Click actions menu on API key row    ${key_name}
    Click delete action in actions menu
    Wait for delete confirmation modal
    Confirm delete API key

User clicks copy API key button
    [Documentation]    Clicks the copy button on the key created drawer.

    Click copy API key button

User deselects model deployment "${deployment_name}" in edit drawer
    [Documentation]    Opens the model deployments select in the edit drawer and deselects
    ...                the deployment with the given name.

    Open model deployments select    ${MODEL_DEPLOYMENTS_EDIT_TRIGGER}
    Click model deployments option "${deployment_name}"

User saves API key edit
    [Documentation]    Submits the edit API key form and waits for the update to complete.
    ...                The drawer closes automatically on success.

    Submit API key form
    API key updated successfully toast should appear
    Wait for edit drawer to close

# =============================================================================
# Then keywords (verification)
# =============================================================================

API keys page should be visible
    [Documentation]    Verifies the API Keys page heading is visible.

    Wait For Elements State    ${API_KEYS_PAGE_HEADING}    visible    timeout=15s

Create API key button should be visible
    [Documentation]    Verifies the "Create API Key" button is present on the page.

    Wait For Elements State    css=${CREATE_API_KEY_BUTTON}    visible    timeout=10s

API key "${key_name}" should be visible in table
    [Documentation]    Verifies that an API key with the given name appears in the table.

    Table row containing text should exist    ${key_name}

API key "${key_name}" should not be visible in table
    [Documentation]    Verifies that an API key with the given name is not in the table.

    Table row containing text should not exist    ${key_name}

Key created drawer should be visible
    [Documentation]    Verifies the key created drawer is shown after creation.

    Wait For Elements State    ${KEY_CREATED_TITLE}    visible    timeout=10s

Copy API key button should be visible
    [Documentation]    Verifies the copy button is present in the key created drawer.

    VAR    ${btn}    css=${COPY_API_KEY_BUTTON}
    Wait For Elements State    ${btn}    visible    timeout=10s

API key deleted successfully toast should appear
    [Documentation]    Verifies the success toast notification appears after deletion.

    Wait For Elements State    text="API key deleted successfully"    visible    timeout=10s

API key updated successfully toast should appear
    [Documentation]    Verifies the success toast notification appears after an edit.

    Wait for API key updated toast

Edit drawer should show linked deployment "${deployment_name}"
    [Documentation]    Verifies the linked deployments section lists the given deployment.

    Linked deployments section should contain text "${deployment_name}"

Edit drawer should show no linked deployments
    [Documentation]    Verifies the edit drawer's linked deployments section shows the
    ...                empty-state message.

    Linked deployments section should contain text "No deployments linked to this API key"

Edit drawer should not show linked deployment "${deployment_name}"
    [Documentation]    Verifies the linked deployments section does not list the given deployment.

    Linked deployments section should not contain text "${deployment_name}"

Linked deployments section should contain text "${text}"
    [Documentation]    Verifies the linked deployments section contains the given text.

    Wait for linked deployments section to show text "${text}"

Linked deployments section should not contain text "${text}"
    [Documentation]    Verifies the linked deployments section does not contain the given text.
    ...                Checks the match count directly — a selector matching zero elements
    ...                is trivially "hidden" in Playwright, so asserting hidden on the
    ...                combined selector alone would pass even if the section never
    ...                rendered at all.

    ${count}=    Get linked deployments match count for text "${text}"
    Should Be Equal As Integers    ${count}    0

The API key deployment picker should offer the deployment labeled "${label}"
    [Documentation]    Opens the create drawer's model deployments picker and verifies a
    ...                deployment is offered under the given profile label, so the person scoping
    ...                a key can tell which profile it grants access to rather than seeing a
    ...                generic "Default".

    Click create API key button
    Open model deployments select
    Wait Until Keyword Succeeds    15s    2s    Deployment picker should offer an option labeled    ${label}

Deployment picker should offer an option labeled
    [Documentation]    Single-poll helper: asserts the open deployments picker offers at least
    ...                one option whose text includes the given label.
    [Arguments]    ${label}

    ${count}=    Get model deployments option count for text "${label}"
    Should Be True    ${count} > 0
    ...    msg=Deployment picker offered no option labeled "${label}"
