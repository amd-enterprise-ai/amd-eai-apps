# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for AIRM UI storages page.
...                 Provides selectors and atomic browser interactions for the storages list,
...                 S3 storage creation form, assignment dialog, and deletion modal.
...                 Business logic and assertions belong in feature resources.

*** Variables ***
${STORAGES_PATH}              /storages


*** Keywords ***
Navigate to storages page
    [Documentation]    Navigates to the storages page and waits for the table to load.
    [Arguments]    ${base_url}

    Go To    ${base_url}${STORAGES_PATH}
    Wait For Elements State    css=main    visible    timeout=15s

Storages page should be loaded
    [Documentation]    Waits for the storages table to be visible.

    Wait For Elements State    css=[role="grid"]    visible    timeout=15s

Get storage row names
    [Documentation]    Returns a list of storage names from visible table rows.

    ${names}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        return Array.from(document.querySelectorAll('[role="rowheader"]'))
    ...            .map(el => el.textContent.trim())
    ...            .filter(name => name);
    ...    }
    RETURN    ${names}

Storage row should exist
    [Documentation]    Asserts that a row with the given storage name exists in the table.
    [Arguments]    ${storage_name}

    VAR    ${row_selector}    css=[role="row"]:has([role="rowheader"]:has-text("${storage_name}"))
    Wait For Elements State    ${row_selector}    visible    timeout=30s

Storage row should not exist
    [Documentation]    Asserts that no row with the given storage name exists in the table.
    [Arguments]    ${storage_name}

    VAR    ${row_selector}    css=[role="row"]:has([role="rowheader"]:has-text("${storage_name}"))
    Wait For Elements State    ${row_selector}    detached    timeout=30s

Get storage row cell text
    [Documentation]    Returns the text content of a specific gridcell in a storage row.
    ...                Gridcell indices (excluding rowheader): 0=Type, 1=Status, 2=Scope, 3=Assigned to.
    [Arguments]    ${storage_name}    ${column_index}

    ${text}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        const rows = document.querySelectorAll('[role="row"]');
    ...        for (const row of rows) {
    ...            const header = row.querySelector('[role="rowheader"]');
    ...            if (header && header.textContent.trim() === '${storage_name}') {
    ...                const cells = row.querySelectorAll('[role="gridcell"]');
    ...                return cells[${column_index}] ? cells[${column_index}].textContent.trim() : '';
    ...            }
    ...        }
    ...        return '';
    ...    }
    RETURN    ${text}

Click add storage button
    [Documentation]    Clicks the "Add storage" button to open the type selection dropdown.

    VAR    ${add_btn}    css=button:has-text("Add storage")
    Wait For Elements State    ${add_btn}    visible    timeout=10s
    Click    ${add_btn}

Select S3 bucket type
    [Documentation]    Selects "S3 Bucket" from the storage type dropdown.

    VAR    ${s3_option}    css=[role="menuitem"]:has-text("S3 Bucket")
    Wait For Elements State    ${s3_option}    visible    timeout=5s
    Click    ${s3_option}

Storage form should be visible
    [Documentation]    Waits for the S3 storage creation dialog to be visible.

    VAR    ${dialog}    css=[role="dialog"]:has-text("Connect S3 Bucket")
    Wait For Elements State    ${dialog}    visible    timeout=10s

Fill storage name
    [Documentation]    Fills in the storage name field in the creation form.
    [Arguments]    ${name}

    VAR    ${name_input}    css=[role="dialog"] input[placeholder*="unique name"]
    Fill Text    ${name_input}    ${name}

Fill bucket URL
    [Documentation]    Fills in the bucket URL field in the creation form.
    [Arguments]    ${url}

    VAR    ${url_input}    css=[role="dialog"] input[placeholder*="S3 bucket connection URL"]
    Fill Text    ${url_input}    ${url}

Select storage secret
    [Documentation]    Selects a secret from the storage secret dropdown.
    [Arguments]    ${secret_name}

    # Click the secret dropdown trigger button
    VAR    ${secret_trigger}    css=[role="dialog"] button:has-text("Select a secret")
    Wait For Elements State    ${secret_trigger}    visible    timeout=10s
    Click    ${secret_trigger}

    # Select the secret by name from the listbox
    VAR    ${secret_option}    css=[role="option"]:has-text("${secret_name}")
    Wait For Elements State    ${secret_option}    visible    timeout=5s
    Click    ${secret_option}

Click add bucket submit
    [Documentation]    Clicks the "Add bucket" button to submit the storage creation form.

    VAR    ${submit_btn}    css=[role="dialog"] button:has-text("Add bucket")
    Click    ${submit_btn}

Open storage actions menu
    [Documentation]    Opens the actions dropdown for a specific storage row.
    [Arguments]    ${storage_name}

    VAR    ${actions_btn}    css=[role="row"]:has([role="rowheader"]:has-text("${storage_name}")) button[aria-label]
    Wait For Elements State    ${actions_btn}    visible    timeout=10s
    Click    ${actions_btn}

Click edit assignment action
    [Documentation]    Clicks "Edit assignment" in the storage actions menu.

    VAR    ${edit_item}    css=[role="menuitem"]:has-text("Edit assignment")
    Wait For Elements State    ${edit_item}    visible    timeout=5s
    Click    ${edit_item}

Click delete action
    [Documentation]    Clicks "Delete" in the storage actions menu.

    VAR    ${delete_item}    css=[role="menuitem"]:has-text("Delete")
    Wait For Elements State    ${delete_item}    visible    timeout=5s
    Click    ${delete_item}

Assignment dialog should be visible
    [Documentation]    Waits for the assignment dialog to be visible.

    VAR    ${dialog}    css=[role="dialog"]
    Wait For Elements State    ${dialog}    visible    timeout=10s

Select project in assignment dialog
    [Documentation]    Toggles a project checkbox in the assignment dialog.
    [Arguments]    ${project_name}

    # Click the project selector trigger
    VAR    ${trigger}    css=[role="dialog"] button:has-text("Select project")
    TRY
        Wait For Elements State    ${trigger}    visible    timeout=5s
        Click    ${trigger}
    EXCEPT
        # Trigger may already be open or have different text if projects already selected
        Log    Project selector trigger not found with default text, looking for alternatives    DEBUG
    END

    VAR    ${option}    css=[role="option"]:has-text("${project_name}")
    Wait For Elements State    ${option}    visible    timeout=5s
    Click    ${option}

Click save assignment
    [Documentation]    Clicks the save/submit button in the assignment dialog.

    VAR    ${save_btn}    css=[role="dialog"] button:has-text("Save")
    Wait For Elements State    ${save_btn}    visible    timeout=5s
    Click    ${save_btn}

Delete confirmation dialog should be visible
    [Documentation]    Waits for the delete/remove confirmation dialog to be visible.

    VAR    ${dialog}    css=[role="dialog"]:has-text("Remove S3 bucket")
    Wait For Elements State    ${dialog}    visible    timeout=10s

Confirm storage deletion
    [Documentation]    Clicks the "Remove" button in the delete confirmation dialog.

    VAR    ${confirm_btn}    css=[role="dialog"] button:has-text("Remove")
    Wait For Elements State    ${confirm_btn}    visible    timeout=5s
    Click    ${confirm_btn}
