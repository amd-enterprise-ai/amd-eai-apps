# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for the AIRM UI Secrets page.
...                 Contains selectors and atomic browser interactions only.
...                 Business logic and assertions belong in feature resources.
...
...                 The admin secrets page (/secrets) shows all secrets across the
...                 organization in a table. Each row displays: Name, Type, Use case,
...                 Status, Scope, Assigned to, Updated at. The Type column uses
...                 data-testid attributes to identify secret types (ExternalSecret
...                 vs KubernetesSecret). Each row has an actions menu with
...                 "Edit assignment" and "Delete" options.
...
...                 The page has filter controls: a search textbox, a Type dropdown,
...                 and a Scope dropdown. A "Create new secret" button opens a dialog.


*** Variables ***
${SECRETS_PATH}                     /secrets
${SECRETS_TABLE_SELECTOR}           main table
${SECRETS_ROW_SELECTOR}             main table tbody tr
${CREATE_SECRET_BUTTON}             button:has-text("Create new secret")
${ADD_SECRET_DIALOG_TITLE}          Add Secret
${ADD_SECRET_SUBMIT}                button:has-text("Add secret")
${SEARCH_INPUT_PLACEHOLDER}         Search
${DELETE_MENU_ITEM}                 Delete


*** Keywords ***
Navigate to secrets page
    [Documentation]    Navigates to the admin secrets page and waits for the table to load.
    [Arguments]    ${base_url}

    Go To    ${base_url}${SECRETS_PATH}
    VAR    ${table}    css=${SECRETS_TABLE_SELECTOR}
    Wait For Elements State    ${table}    visible    timeout=30s

Get secrets table column headers
    [Documentation]    Returns a list of column header texts from the secrets table.

    ${headers}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        const table = document.querySelector('${SECRETS_TABLE_SELECTOR}');
    ...        if (!table) return [];
    ...        const ths = table.querySelectorAll('thead th, [role="columnheader"]');
    ...        return Array.from(ths).map(el => el.textContent.trim()).filter(t => t);
    ...    }
    RETURN    ${headers}

Get secrets table row count
    [Documentation]    Returns the number of visible rows in the secrets table body.

    VAR    ${rows}    css=${SECRETS_ROW_SELECTOR}
    ${count}=    Get Element Count    ${rows}
    RETURN    ${count}

Secret row should exist with name
    [Documentation]    Verifies a table row containing the given secret name is visible.
    ...                Uses a short timeout to allow the outer retry loop to control polling.
    [Arguments]    ${secret_name}

    VAR    ${row}    css=${SECRETS_ROW_SELECTOR}:has-text("${secret_name}")
    Wait For Elements State    ${row}    visible    timeout=3s

Secret row should not exist with name
    [Documentation]    Verifies no table row containing the given secret name is visible.
    ...                Uses a short timeout to allow the outer retry loop to control polling.
    [Arguments]    ${secret_name}

    VAR    ${row}    css=${SECRETS_ROW_SELECTOR}:has-text("${secret_name}")
    Wait For Elements State    ${row}    detached    timeout=3s

Secret type indicator should exist
    [Documentation]    Verifies that at least one secret type indicator element exists in the
    ...                table. The type column renders data-testid="secret-type-{type}" which
    ...                distinguishes ExternalSecret from KubernetesSecret. Uses nth=0 to
    ...                avoid strict-mode violations when multiple rows share the same type.
    [Arguments]    ${secret_type}

    VAR    ${indicator}    css=[data-testid="secret-type-${secret_type}"] >> nth=0
    Wait For Elements State    ${indicator}    visible    timeout=15s

Secret type indicator should exist in row
    [Documentation]    Verifies that a specific secret row contains the expected type indicator.
    [Arguments]    ${secret_name}    ${secret_type}

    VAR    ${indicator}    css=${SECRETS_ROW_SELECTOR}:has-text("${secret_name}") [data-testid="secret-type-${secret_type}"]
    Wait For Elements State    ${indicator}    visible    timeout=15s

Get secret row cell text
    [Documentation]    Returns the text content of a specific cell in a secret row.
    ...                Column index is 1-based (1=Name, 2=Type, 3=Use case, 4=Status,
    ...                5=Scope, 6=Assigned to, 7=Updated at).
    [Arguments]    ${secret_name}    ${column_index}

    VAR    ${cell}    css=${SECRETS_ROW_SELECTOR}:has-text("${secret_name}") td:nth-child(${column_index})
    ${text}=    Get Text    ${cell}
    RETURN    ${text}

Click create new secret button
    [Documentation]    Clicks the "Create new secret" button to open the creation dialog.

    VAR    ${btn}    css=${CREATE_SECRET_BUTTON}
    Click    ${btn}
    # Wait for dialog to appear
    Wait For Elements State    css=section >> text="${ADD_SECRET_DIALOG_TITLE}"    visible    timeout=10s

Fill secret yaml field
    [Documentation]    Fills the external secret YAML textarea in the create dialog.
    ...                Uses the labeled textbox role to avoid strict mode violations
    ...                from a hidden shadow textarea.
    [Arguments]    ${yaml_content}

    VAR    ${field}    role=textbox[name=/External secret/]
    Fill Text    ${field}    ${yaml_content}

Click add secret submit
    [Documentation]    Clicks the "Add secret" button in the creation dialog.

    VAR    ${btn}    css=${ADD_SECRET_SUBMIT}
    Click    ${btn}

Add secret dialog should be closed
    [Documentation]    Waits for the add secret dialog to close after submission.

    Wait For Elements State    css=section >> text="${ADD_SECRET_DIALOG_TITLE}"    detached    timeout=15s

Open actions menu for secret
    [Documentation]    Opens the actions dropdown menu for a specific secret row.
    [Arguments]    ${secret_name}

    VAR    ${actions_btn}    css=${SECRETS_ROW_SELECTOR}:has-text("${secret_name}") button
    Click    ${actions_btn}
    # Wait for menu to appear
    Wait For Elements State    role=menu    visible    timeout=5s

Click delete in actions menu
    [Documentation]    Clicks the "Delete" option in the actions dropdown menu.

    VAR    ${delete_item}    role=menuitem[name="${DELETE_MENU_ITEM}"]
    Click    ${delete_item}

Confirm delete in dialog
    [Documentation]    Clicks the "Confirm" button in the delete confirmation dialog.

    VAR    ${confirm_btn}    role=button[name="Confirm"]
    Wait For Elements State    ${confirm_btn}    visible    timeout=5s
    Click    ${confirm_btn}

Enter secret search text
    [Documentation]    Types text into the search input field on the secrets page.
    [Arguments]    ${search_text}

    VAR    ${search}    role=textbox[name="${SEARCH_INPUT_PLACEHOLDER}"]
    Fill Text    ${search}    ${search_text}

Open actions menu for secret by row button
    [Documentation]    Opens the actions dropdown menu for a secret row using the
    ...                row-level button selector. Uses the grid role-based selectors
    ...                for compatibility with the HeroUI ClientSideDataTable component.
    [Arguments]    ${secret_name}

    VAR    ${actions_btn}    css=[role="row"]:has([role="rowheader"]:has-text("${secret_name}")) button[aria-label]
    Wait For Elements State    ${actions_btn}    visible    timeout=10s
    Click    ${actions_btn}
    Wait For Elements State    role=menu    visible    timeout=5s

Click edit assignment in actions menu
    [Documentation]    Clicks the "Edit assignment" option in the actions dropdown menu.

    VAR    ${edit_item}    css=[role="menuitem"]:has-text("Edit assignment")
    Wait For Elements State    ${edit_item}    visible    timeout=5s
    Click    ${edit_item}

Assignment dialog should be visible
    [Documentation]    Waits for the secret assignment dialog to be visible.

    VAR    ${dialog}    css=[role="dialog"]:has-text("Assign Secret")
    Wait For Elements State    ${dialog}    visible    timeout=10s

Select project in assignment dialog
    [Documentation]    Selects a project in the assignment dialog's project selector.
    [Arguments]    ${project_name}

    # Click the project selector trigger
    VAR    ${trigger}    css=[role="dialog"] button:has-text("Select project")
    TRY
        Wait For Elements State    ${trigger}    visible    timeout=5s
        Click    ${trigger}
    EXCEPT
        # Trigger may already be open or have different text if projects are already selected
        Log    Project selector trigger not found with default text, looking for alternatives    DEBUG
    END

    VAR    ${option}    css=[role="option"]:has-text("${project_name}")
    Wait For Elements State    ${option}    visible    timeout=5s
    Click    ${option}

Click save assignment
    [Documentation]    Clicks the "Save changes" button in the assignment dialog.

    VAR    ${save_btn}    css=[role="dialog"] button:has-text("Save changes")
    Wait For Elements State    ${save_btn}    visible    timeout=5s
    Click    ${save_btn}

Get all visible secret names
    [Documentation]    Returns a list of all secret names currently visible in the table.

    ${names}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        const rows = document.querySelectorAll('${SECRETS_ROW_SELECTOR}');
    ...        return Array.from(rows).map(row => {
    ...            const firstCell = row.querySelector('td:first-child, [role="rowheader"]');
    ...            return firstCell ? firstCell.textContent.trim() : '';
    ...        }).filter(t => t);
    ...    }
    RETURN    ${names}

Get secret assigned to text
    [Documentation]    Returns the text content of the "Assigned to" column for a secret row.
    ...                Uses grid role-based selectors for the HeroUI table.
    [Arguments]    ${secret_name}

    ${text}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        const rows = document.querySelectorAll('[role="row"]');
    ...        for (const row of rows) {
    ...            const header = row.querySelector('[role="rowheader"]');
    ...            if (header && header.textContent.trim().includes('${secret_name}')) {
    ...                const cells = row.querySelectorAll('[role="gridcell"]');
    ...                return cells[4] ? cells[4].textContent.trim() : '';
    ...            }
    ...        }
    ...        return '';
    ...    }
    RETURN    ${text}
