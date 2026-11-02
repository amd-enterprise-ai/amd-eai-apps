# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for the AIWB Workspaces catalog and dashboard interactions.
...                 Contains selectors and atomic browser interactions only.
...                 Business logic and assertions belong in feature resources.
...
...                 Dashboard grid/row/actions selectors are imported from workloads_page.resource
...                 to avoid duplication (both pages use the same dashboard grid).
Resource            workloads_page.resource


*** Variables ***
${WORKSPACES_PATH}                      /workspaces
${DEPLOY_WIZARD_SELECTOR}               [role="dialog"]
${DEPLOY_WIZARD_NEXT_BTN}               [role="dialog"] button:has-text("Next")
${DEPLOY_WIZARD_SUBMIT_BTN}             [role="dialog"] button:has-text("Submit")
${DEPLOY_WIZARD_CANCEL_BTN}             [role="dialog"] button:has-text("Cancel")
${WORKSPACE_SEARCH_SELECTOR}            main input[placeholder="Search"]
${DELETE_MENU_ITEM}                     [role="menuitem"]:has-text("Delete")
${CONFIRMATION_MODAL_SELECTOR}          [data-testid="confirmation-modal"]
${CONFIRM_DELETE_BTN}                   [data-testid="confirm-button"]
${REQUEST_WORKSPACE_CARD_SELECTOR}      [data-testid="request-workspace"]


*** Keywords ***
Navigate To Workspaces Page
    [Documentation]    Navigates to the Workspaces page via sidebar link to preserve project context.
    [Arguments]    ${base_url}    ${project}

    # Use sidebar navigation to avoid full page reload which resets project context
    VAR    ${sidebar_link}    css=a[href="/${project}/workspaces"]
    ${link_visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${sidebar_link}    visible    timeout=5s
    IF    ${link_visible}
        Click    ${sidebar_link}
    ELSE
        Go To    ${base_url}/${project}${WORKSPACES_PATH}
    END
    VAR    ${search}    css=${WORKSPACE_SEARCH_SELECTOR}
    Wait For Elements State    ${search}    visible    timeout=30s

Click First Workspace Deploy Button
    [Documentation]    Clicks the "Deploy" button on the first workspace card.

    VAR    ${button}    css=button:has-text("Deploy") >> nth=0
    Click    ${button}

Click Deploy Button On Workspace Card
    [Documentation]    Clicks the Deploy button on a specific workspace card by name.
    [Arguments]    ${workspace_name}

    VAR    ${card}    css=main .grid > div:has-text("${workspace_name}")
    VAR    ${deploy_btn}    ${card} >> css=button:has-text("Deploy")
    Wait For Elements State    ${deploy_btn}    visible    timeout=10s
    Click    ${deploy_btn}

Wait For Deploy Wizard
    [Documentation]    Waits for the workspace deploy wizard to become ready.

    VAR    ${wizard}    css=${DEPLOY_WIZARD_SELECTOR}
    Wait For Elements State    ${wizard}    visible    timeout=15s
    VAR    ${next_btn}    css=${DEPLOY_WIZARD_NEXT_BTN}
    Wait For Elements State    ${next_btn}    enabled    timeout=30s

Wait For Deploy Wizard Settings
    [Documentation]    Waits for the selected workspace details and image field to become visible.

    VAR    ${details}    css=[data-testid="deploy-workspace-wizard-catalog-header"]
    Wait For Elements State    ${details}    visible    timeout=15s
    VAR    ${image}    css=${DEPLOY_WIZARD_SELECTOR} input[aria-label="Container image"]
    Wait For Elements State    ${image}    visible    timeout=15s

Advance Deploy Wizard
    [Documentation]    Advances the workspace deploy wizard to its next step.

    VAR    ${next_btn}    css=${DEPLOY_WIZARD_NEXT_BTN}
    Wait For Elements State    ${next_btn}    enabled    timeout=30s
    Click    ${next_btn}

Get Deploy Wizard Workload Name
    [Documentation]    Returns the default workload name from the target step.
    ...                Uses Get Property to read the input value attribute.

    VAR    ${input}    css=${DEPLOY_WIZARD_SELECTOR} input[aria-label="Workload name"]
    Wait For Elements State    ${input}    visible    timeout=10s
    ${value}=    Get Property    ${input}    value
    RETURN    ${value}

Submit Deploy Wizard
    [Documentation]    Advances to the check step and submits the workspace deployment.

    Advance deploy wizard
    VAR    ${submit_btn}    css=${DEPLOY_WIZARD_SUBMIT_BTN}
    Wait For Elements State    ${submit_btn}    enabled    timeout=30s
    Click    ${submit_btn}

Wait For Deploy Wizard To Close
    [Documentation]    Waits for the deploy wizard to close after submission.

    VAR    ${wizard}    css=${DEPLOY_WIZARD_SELECTOR}
    Wait For Elements State    ${wizard}    detached    timeout=30s

Open Image Pull Secrets Dropdown
    [Documentation]    Clicks the imagePullSecrets dropdown trigger to expand options.
    ...                Waits for the trigger to be visible since it loads asynchronously.

    VAR    ${trigger}    css=[role="dialog"] button[aria-label="Image pull secrets"]
    Wait For Elements State    ${trigger}    visible    timeout=30s
    Click    ${trigger}
    # Wait for the listbox popover to appear (ul element, not the wrapper div)
    VAR    ${listbox}    css=ul[role="listbox"][data-slot="listbox"]
    Wait For Elements State    ${listbox}    visible    timeout=10s

Select Image Pull Secret Option
    [Documentation]    Toggles an option in the open imagePullSecrets dropdown by its visible label.
    ...                The dropdown is multi-select, so it stays open after each selection.
    [Arguments]    ${option_label}

    VAR    ${option}    css=ul[role="listbox"][data-slot="listbox"] [role="option"]:has-text("${option_label}")
    Wait For Elements State    ${option}    visible    timeout=10s
    Click    ${option}

Close Image Pull Secrets Dropdown
    [Documentation]    Closes the open imagePullSecrets dropdown without leaving the deploy wizard.

    Keyboard Key    press    Escape
    VAR    ${listbox}    css=ul[role="listbox"][data-slot="listbox"]
    Wait For Elements State    ${listbox}    detached    timeout=10s

Get Image Pull Secrets Options Text
    [Documentation]    Returns the text content of all visible options in the imagePullSecrets dropdown.

    VAR    ${listbox}    css=ul[role="listbox"][data-slot="listbox"]
    ${text}=    Get Text    ${listbox}
    RETURN    ${text}

Close Deploy Wizard
    [Documentation]    Closes the deploy wizard by clicking Cancel.

    VAR    ${cancel}    css=${DEPLOY_WIZARD_CANCEL_BTN}
    Click    ${cancel}
    VAR    ${wizard}    css=${DEPLOY_WIZARD_SELECTOR}
    Wait For Elements State    ${wizard}    detached    timeout=10s

Check Workspace Catalog Has Cards
    [Documentation]    Returns the number of visible workspace cards on the page.
    ...                Delegates to Get Workspace Card Count to avoid selector duplication.

    ${count}=    Get Workspace Card Count
    RETURN    ${count}

Get Deploy Button Count
    [Documentation]    Returns the number of Deploy buttons visible on workspace cards.

    VAR    ${deploy_buttons}    css=button:has-text("Deploy")
    ${count}=    Get Element Count    ${deploy_buttons}
    RETURN    ${count}

Get Launch Button Count
    [Documentation]    Returns the number of Launch buttons visible on workspace cards.
    ...                Launch buttons appear on cards with Running status.

    VAR    ${launch_button}    css=button:has-text("Launch")
    ${count}=    Get Element Count    ${launch_button}
    RETURN    ${count}

Get Workspace Card Count
    [Documentation]    Returns the total number of workspace cards displayed in the catalog.

    VAR    ${workspace_cards}    css=[data-testid="workspace-card"]
    ${count}=    Get Element Count    ${workspace_cards}
    RETURN    ${count}

Wait For Launch Button Enabled
    [Documentation]    Waits for the launch button to be visible and enabled.
    ...                Uses polling with configurable timeout.

    VAR    ${launch_button}    css=button:has-text("Launch") >> nth=0
    Wait For Elements State    ${launch_button}    visible    timeout=10s
    Wait For Elements State    ${launch_button}    enabled    timeout=10s

Get Request Workspace Card Mailto Href
    [Documentation]    Returns the href of the anchor inside the "Request workspace" card.
    ...                Waits for the card to be visible since it renders after the catalog list.

    VAR    ${card}    css=${REQUEST_WORKSPACE_CARD_SELECTOR}
    Wait For Elements State    ${card}    visible    timeout=15s
    ${href}=    Get Attribute    css=${REQUEST_WORKSPACE_CARD_SELECTOR} a    href
    RETURN    ${href}

Navigate To Dashboard Page
    [Documentation]    Navigates to the Dashboard page which shows the workloads grid.
    [Arguments]    ${base_url}    ${project}

    VAR    ${sidebar_link}    css=a[href="/${project}"]
    ${link_visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${sidebar_link}    visible    timeout=5s
    IF    ${link_visible}
        Click    ${sidebar_link}
    ELSE
        Go To    ${base_url}/${project}/
    END
    VAR    ${grid}    css=${WORKLOADS_GRID_SELECTOR}
    Wait For Elements State    ${grid}    visible    timeout=30s

Workload Row Should Exist
    [Documentation]    Verifies a workload row with the given name exists in the dashboard grid.
    [Arguments]    ${workload_name}    ${timeout}=30s

    VAR    ${row}    css=${WORKLOAD_ROW_SELECTOR}:has-text("${workload_name}")
    Wait For Elements State    ${row}    visible    timeout=${timeout}

Workload Row Should Not Exist
    [Documentation]    Verifies no workload row with the given name appears in the dashboard grid.
    [Arguments]    ${workload_name}    ${timeout}=10s

    VAR    ${row}    css=${WORKLOAD_ROW_SELECTOR}:has-text("${workload_name}")
    Wait For Elements State    ${row}    hidden    timeout=${timeout}

Get Workload Status Text
    [Documentation]    Returns the status text from the Status column of a workload row.
    [Arguments]    ${workload_name}

    VAR    ${row}    css=${WORKLOAD_ROW_SELECTOR}:has-text("${workload_name}")
    # Positional index: Status is the 3rd column in the dashboard grid.
    # No data-testid exists on status cells; update if columns are reordered.
    VAR    ${status_cell}    ${row} >> css=[role="gridcell"]:nth-child(3)
    ${text}=    Get Text    ${status_cell}
    RETURN    ${text}

Click Workload Actions Menu
    [Documentation]    Clicks the actions menu button on a workload row.
    [Arguments]    ${workload_name}

    VAR    ${row}    css=${WORKLOAD_ROW_SELECTOR}:has-text("${workload_name}")
    VAR    ${actions_btn}    ${row} >> css=${ACTIONS_BUTTON_SELECTOR}
    Click    ${actions_btn}

Click Delete In Actions Menu
    [Documentation]    Clicks Delete in the currently visible actions menu.

    VAR    ${delete_item}    css=${DELETE_MENU_ITEM}
    Wait For Elements State    ${delete_item}    visible    timeout=5s
    Click    ${delete_item}

Confirm Delete In Modal
    [Documentation]    Confirms deletion in the confirmation modal dialog.

    VAR    ${modal}    css=${CONFIRMATION_MODAL_SELECTOR}
    Wait For Elements State    ${modal}    visible    timeout=10s
    VAR    ${confirm}    css=${CONFIRM_DELETE_BTN}
    Click    ${confirm}
    Wait For Elements State    ${modal}    detached    timeout=15s

Get Delete Confirmation Modal Text
    [Documentation]    Returns the text content of the currently visible delete confirmation modal.

    VAR    ${modal}    css=${CONFIRMATION_MODAL_SELECTOR}
    Wait For Elements State    ${modal}    visible    timeout=10s
    ${text}=    Get Text    ${modal}
    RETURN    ${text}

Get Actions Menu Items Text
    [Documentation]    Returns the combined text of all items in the currently open actions menu.
    ...                Caller is responsible for opening the menu first.

    VAR    ${menu}    css=[role="menu"]
    Wait For Elements State    ${menu}    visible    timeout=5s
    ${text}=    Get Text    ${menu}
    RETURN    ${text}

Close Actions Menu
    [Documentation]    Closes the currently open actions menu by pressing Escape.

    Keyboard Key    press    Escape
