# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for the AIWB Secrets page.
...                 Contains selectors and atomic browser interactions only.
...                 Business logic and assertions belong in feature resources.


*** Variables ***
${SECRETS_PATH}                     /secrets
${SECRETS_TABLE_SELECTOR}           table
${SECRETS_ROW_SELECTOR}             tbody tr
${ADD_SECRET_BUTTON_TEXT}            Create new secret
${DRAWER_SELECTOR}                  [role="dialog"]
${DRAWER_HEADER_SELECTOR}           [role="dialog"] header
${CONFIRMATION_MODAL_SELECTOR}      [data-testid="confirmation-modal"]
${CONFIRM_BUTTON_SELECTOR}          [data-testid="confirm-button"]
${USE_CASE_SELECT_SELECTOR}         [data-testid="useCaseSelect"]
${ACTIONS_BUTTON_SELECTOR}          button[aria-label="Actions"]
${TOAST_SUCCESS_SELECTOR}           [data-testid="toast-success"]


*** Keywords ***
Navigate To Secrets Page
    [Documentation]    Navigates to the Secrets page via sidebar link to preserve project context.
    [Arguments]    ${base_url}    ${project}

    # Use sidebar navigation to avoid full page reload which resets project context
    VAR    ${sidebar_link}    css=a[href="/${project}/secrets"]
    ${link_visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${sidebar_link}    visible    timeout=5s
    IF    ${link_visible}
        Click    ${sidebar_link}
    ELSE
        Go To    ${base_url}/${project}${SECRETS_PATH}
    END
    VAR    ${table}    css=${SECRETS_TABLE_SELECTOR}
    Wait For Elements State    ${table}    visible    timeout=30s

Get Secret Row Count
    [Documentation]    Returns the number of rows in the secrets table.

    VAR    ${rows}    css=${SECRETS_ROW_SELECTOR}
    ${count}=    Get Element Count    ${rows}
    RETURN    ${count}

Get Secrets Table Text
    [Documentation]    Returns the full text content of the secrets table.

    VAR    ${table}    css=${SECRETS_TABLE_SELECTOR}
    ${text}=    Get Text    ${table}
    RETURN    ${text}

Secret Row Should Contain Name
    [Documentation]    Returns whether a secret with the given name is visible in the table.
    [Arguments]    ${secret_name}

    VAR    ${row}    css=${SECRETS_ROW_SELECTOR}:has-text("${secret_name}")
    Wait For Elements State    ${row}    visible    timeout=15s

Secret Row Should Not Be Visible
    [Documentation]    Waits until a secret with the given name is not visible in the table.
    [Arguments]    ${secret_name}

    VAR    ${row}    css=${SECRETS_ROW_SELECTOR}:has-text("${secret_name}")
    Wait For Elements State    ${row}    detached    timeout=15s

Click Add Secret Button
    [Documentation]    Clicks the "Create new secret" button on the secrets page.

    Click    text="${ADD_SECRET_BUTTON_TEXT}"

Wait For Add Secret Drawer
    [Documentation]    Waits for the Add Secret drawer to become visible.

    VAR    ${drawer}    css=${DRAWER_SELECTOR}
    Wait For Elements State    ${drawer}    visible    timeout=15s

Fill Secret Name
    [Documentation]    Fills in the secret name field in the Add Secret drawer.
    [Arguments]    ${name}

    Fill Text    css=${DRAWER_SELECTOR} input[name="name"]    ${name}

Select Secret Use Case
    [Documentation]    Selects a use case from the dropdown in the Add Secret drawer.
    [Arguments]    ${use_case}

    VAR    ${trigger}    css=${DRAWER_SELECTOR} ${USE_CASE_SELECT_SELECTOR}
    Click    ${trigger}
    VAR    ${option}    css=[data-testid="use-case-option-${use_case}"]
    Wait For Elements State    ${option}    visible    timeout=10s
    Click    ${option}

Fill Secret Value
    [Documentation]    Fills in the secret value textarea in the Add Secret drawer.
    [Arguments]    ${value}

    VAR    ${textarea}    css=${DRAWER_SELECTOR} textarea[name="value"]
    Wait For Elements State    ${textarea}    visible    timeout=10s
    Fill Text    ${textarea}    ${value}

Fill S3 Access Key ID
    [Documentation]    Fills in S3 Access Key ID field in the Add Secret drawer.
    [Arguments]    ${access_key_id}

    VAR    ${input}    css=${DRAWER_SELECTOR} input[name="s3AccessKeyId"]
    Wait For Elements State    ${input}    visible    timeout=10s
    Fill Text    ${input}    ${access_key_id}

Fill S3 Secret Access Key
    [Documentation]    Fills in S3 Secret Access Key field in the Add Secret drawer.
    [Arguments]    ${secret_access_key}

    VAR    ${input}    css=${DRAWER_SELECTOR} input[name="s3SecretAccessKey"]
    Wait For Elements State    ${input}    visible    timeout=10s
    Fill Text    ${input}    ${secret_access_key}

Click Submit Secret Button
    [Documentation]    Clicks the "Add secret" submit button in the drawer.

    VAR    ${submit}    css=${DRAWER_SELECTOR} button[aria-label="Add secret"]
    Click    ${submit}

Wait For Drawer To Close
    [Documentation]    Waits for the drawer to close after submission.

    VAR    ${drawer}    css=${DRAWER_SELECTOR}
    Wait For Elements State    ${drawer}    detached    timeout=15s

Click Delete On Secret Row
    [Documentation]    Clicks the actions menu on a secret row, then clicks Delete.
    [Arguments]    ${secret_name}

    VAR    ${row}    css=${SECRETS_ROW_SELECTOR}:has-text("${secret_name}")
    VAR    ${actions_btn}    ${row} >> css=${ACTIONS_BUTTON_SELECTOR}
    Click    ${actions_btn}
    # Wait for the dropdown menu to appear and click Delete
    VAR    ${delete_option}    css=[role="menuitem"]:has-text("Delete")
    Wait For Elements State    ${delete_option}    visible    timeout=5s
    Click    ${delete_option}

Wait For Confirmation Modal
    [Documentation]    Waits for the confirmation modal to become visible.

    VAR    ${modal}    css=${CONFIRMATION_MODAL_SELECTOR}
    Wait For Elements State    ${modal}    visible    timeout=10s

Get Confirmation Modal Text
    [Documentation]    Returns the full text content of the confirmation modal.

    VAR    ${modal}    css=${CONFIRMATION_MODAL_SELECTOR}
    ${text}=    Get Text    ${modal}
    RETURN    ${text}

Click Confirm Delete Button
    [Documentation]    Clicks the confirm button in the delete confirmation modal.

    VAR    ${confirm}    css=${CONFIRM_BUTTON_SELECTOR}
    Click    ${confirm}

Wait For Confirmation Modal To Close
    [Documentation]    Waits for the confirmation modal to close.

    VAR    ${modal}    css=${CONFIRMATION_MODAL_SELECTOR}
    Wait For Elements State    ${modal}    detached    timeout=15s
