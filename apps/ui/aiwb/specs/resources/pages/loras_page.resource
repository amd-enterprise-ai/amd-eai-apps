# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for the AIWB LoRAs page.
...                 Contains selectors and atomic browser interactions only.


*** Variables ***
${LORAS_PATH}                  /fine-tuning/loras
${LORAS_PAGE}                  css=[data-testid="loras-page"]
${LORAS_TABLE}                 css=[data-testid="loras-page"] table
${LORAS_ROWS}                  css=[data-testid="loras-page"] table tbody tr
${LORAS_FIRST_ROW}             css=[data-testid="loras-page"] table tbody tr:first-of-type
${LORAS_DEPLOYMENT_COUNT_CELL_SELECTOR}    td:nth-of-type(3)
${LORAS_EMPTY_STATE}           text="This project has no LoRA adapters or active LoRA fine-tuning jobs."
${LORAS_PAGINATION}            css=[data-testid="loras-page"] nav[aria-label="pagination navigation"]
${LORAS_PAGINATION_NEXT}       css=[data-testid="loras-page"] nav[aria-label="pagination navigation"] button[aria-label="next page button"]
${LORAS_SEARCH_INPUT}          css=[data-testid="loras-page"] input[placeholder="Search"]
${LORAS_FINETUNE_BUTTON}       css=[data-testid="loras-finetune"]
${LORAS_REFRESH_BUTTON}        css=[data-testid="loras-page"] button[aria-label="Refresh"]
${LORAS_BASE_MODEL_FILTER_TRIGGER}    css=[data-testid="loras-page"] [role="button"][aria-label="Base models"]
${LORAS_BASE_MODEL_FILTER_LISTBOX}    [role="listbox"][aria-label="Base models"]
${LORA_ATTACH_ACTION}          css=[data-testid="attach"]
${LORA_ATTACH_MODAL}           css=[role="dialog"]:has-text("Attach to deployment")
${LORA_ATTACH_EMPTY_STATE}     css=[data-testid="attach-lora-empty-state"]
${LORA_ATTACH_SELECT}          ${LORA_ATTACH_MODAL} button:has-text("Select deployment")
${LORA_ATTACH_LISTBOX}         css=[role="listbox"]
${LORA_ATTACH_SUBMIT}          ${LORA_ATTACH_MODAL} button:has-text("Attach")
${LORA_DETAILS_ACTION}         css=[data-testid="details"]
${LORA_DELETE_ACTION}          css=[data-testid="delete"]
${LORA_DELETE_MODAL}           css=[data-testid="confirmation-modal"]
${LORA_DELETE_CONFIRM}         css=[data-testid="confirm-button"]
${LORA_DETAILS_MODAL}          css=[data-testid="lora-details-modal"]
${LORA_DELETE_SUCCESS}         text="LoRA adapter successfully deleted."
${LORA_CANCEL_SUCCESS}         text="Fine-tuning job canceled successfully."
# The attach success toast also names the adapter and deployment, so it is matched by its
# stable "Attaching" prefix rather than full text.
${LORA_ATTACH_SUCCESS}         css=[data-slot="toast"]:has-text("Attaching")


*** Keywords ***
Navigate to LoRAs page
    [Documentation]    Opens the project LoRAs destination through the sidebar.
    [Arguments]    ${project}

    Wait Until Keyword Succeeds    30s    2s    Navigate to LoRAs via sidebar    ${project}

Navigate to LoRAs via sidebar
    [Documentation]    Clicks the sidebar LoRAs link and verifies the table loaded.
    [Arguments]    ${project}

    VAR    ${sidebar_link}    css=#sidebar-nav-panel a[href="/${project}${LORAS_PATH}"]
    Wait For Elements State    ${sidebar_link}    visible    timeout=5s
    Click    ${sidebar_link}
    Wait For Elements State    ${LORAS_PAGE}    visible    timeout=15s

Get LoRA row text
    [Documentation]    Returns the text of the row containing the named adapter.
    [Arguments]    ${adapter_name}

    VAR    ${row}    css=[data-testid="loras-page"] table tbody tr:has-text("${adapter_name}")
    Wait For Elements State    ${row}    visible    timeout=15s
    ${text}=    Get Text    ${row}
    RETURN    ${text}

Get LoRA deployment count text
    [Documentation]    Returns the deployment count shown for the named adapter.
    [Arguments]    ${adapter_name}

    VAR    ${row}    css=[data-testid="loras-page"] table tbody tr:has-text("${adapter_name}")
    Wait For Elements State    ${row}    visible    timeout=15s
    VAR    ${cell}    ${row} >> css=${LORAS_DEPLOYMENT_COUNT_CELL_SELECTOR}
    Wait For Elements State    ${cell}    visible    timeout=15s
    ${text}=    Get Text    ${cell}
    RETURN    ${text}

Get LoRAs table text
    [Documentation]    Returns all visible text in the LoRAs table.

    ${text}=    Get Text    ${LORAS_TABLE}
    RETURN    ${text}

Wait for LoRAs table to load
    [Documentation]    Waits until the LoRAs table's asynchronous data loading is complete.

    Wait For Elements State    ${LORAS_FINETUNE_BUTTON}    enabled    timeout=30s

Get LoRA table row count
    [Documentation]    Returns the number of visible adapter rows.

    ${count}=    Get Element Count    ${LORAS_ROWS}
    RETURN    ${count}

Get first LoRA row text
    [Documentation]    Returns the first visible adapter row text.

    Wait For Elements State    ${LORAS_FIRST_ROW}    visible    timeout=15s
    ${text}=    Get Text    ${LORAS_FIRST_ROW}
    RETURN    ${text}

Search LoRAs
    [Documentation]    Enters a search term in the LoRAs list.
    [Arguments]    ${search_term}

    Fill Text    ${LORAS_SEARCH_INPUT}    ${search_term}

Open fine-tuning wizard from LoRAs
    [Documentation]    Opens the fine-tuning wizard from the LoRAs toolbar.

    Wait For Elements State    ${LORAS_FINETUNE_BUTTON}    visible    timeout=15s
    Click    ${LORAS_FINETUNE_BUTTON}

LoRAs pagination is visible
    [Documentation]    Returns whether the LoRAs pagination controls are visible.

    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${LORAS_PAGINATION}    visible    timeout=15s
    RETURN    ${visible}

Click next LoRAs page
    [Documentation]    Opens the next page of adapters.

    Wait For Elements State    ${LORAS_PAGINATION_NEXT}    visible    timeout=15s
    Click    ${LORAS_PAGINATION_NEXT}

LoRAs empty state is visible
    [Documentation]    Returns whether the registered-adapter empty state is visible.

    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${LORAS_EMPTY_STATE}    visible    timeout=15s
    RETURN    ${visible}

Open LoRA row actions
    [Documentation]    Opens the actions menu for the named adapter row.
    [Arguments]    ${adapter_name}

    VAR    ${row}    css=[data-testid="loras-page"] table tbody tr:has-text("${adapter_name}")
    Wait For Elements State    ${row}    visible    timeout=15s
    Click    ${row} >> css=button[aria-label="Actions"]

Click LoRA details action
    [Documentation]    Opens the selected adapter's details modal.

    Wait For Elements State    ${LORA_DETAILS_ACTION}    visible    timeout=10s
    Click    ${LORA_DETAILS_ACTION}
    Wait For Elements State    ${LORA_DETAILS_MODAL}    visible    timeout=15s

Click LoRA attach action
    [Documentation]    Opens the selected adapter's deployment attachment modal.

    Wait For Elements State    ${LORA_ATTACH_ACTION}    visible    timeout=10s
    Click    ${LORA_ATTACH_ACTION}
    Wait For Elements State    ${LORA_ATTACH_MODAL}    visible    timeout=15s

Get LoRA attach action disabled state
    [Documentation]    Returns the open row action menu's Attach item aria-disabled value.

    Wait For Elements State    ${LORA_ATTACH_ACTION}    visible    timeout=10s
    ${state}=    Get Attribute    ${LORA_ATTACH_ACTION}    aria-disabled
    RETURN    ${state}

Open LoRA attachment deployment picker
    [Documentation]    Opens the attachment modal's deployment choices.

    Wait For Elements State    ${LORA_ATTACH_SELECT}    visible    timeout=15s
    Click    ${LORA_ATTACH_SELECT}
    Wait For Elements State    ${LORA_ATTACH_LISTBOX}    visible    timeout=15s

Get LoRA attachment deployment picker text
    [Documentation]    Returns all visible attachment deployment choices and section headings.

    ${text}=    Get Text    ${LORA_ATTACH_LISTBOX}
    RETURN    ${text}

Get LoRA attachment deployment disabled state
    [Documentation]    Returns the disabled state of the named attachment deployment.
    [Arguments]    ${deployment_name}

    VAR    ${option}    ${LORA_ATTACH_LISTBOX} [role="option"]:has-text("${deployment_name}")
    ${disabled}=    Get Attribute    ${option}    aria-disabled
    RETURN    ${disabled}

LoRA attachment deployment has attached marker
    [Documentation]    Returns whether the named deployment carries the accessible attached marker.
    [Arguments]    ${deployment_name}

    VAR    ${marker}    ${LORA_ATTACH_LISTBOX} [role="option"]:has-text("${deployment_name}") [role="img"][aria-label="Already attached"]
    ${count}=    Get Element Count    ${marker}
    RETURN    ${{ $count == 1 }}

Get LoRA attachment empty state text
    [Documentation]    Returns the explanation shown when no deployments can accept the adapter.

    Wait For Elements State    ${LORA_ATTACH_EMPTY_STATE}    visible    timeout=15s
    ${text}=    Get Text    ${LORA_ATTACH_EMPTY_STATE}
    RETURN    ${text}

Select LoRA attachment deployment
    [Documentation]    Picks the named deployment in the open attachment picker.
    [Arguments]    ${deployment_name}

    VAR    ${option}    ${LORA_ATTACH_LISTBOX} [role="option"]:has-text("${deployment_name}")
    Wait For Elements State    ${option}    visible    timeout=15s
    Click    ${option}
    Wait For Elements State    ${LORA_ATTACH_LISTBOX}    detached    timeout=10s

Confirm LoRA attachment
    [Documentation]    Submits the open attachment modal with the currently selected deployment.

    Wait For Elements State    ${LORA_ATTACH_SUBMIT}    enabled    timeout=10s
    Click    ${LORA_ATTACH_SUBMIT}

LoRA attachment success toast should be visible
    [Documentation]    Waits for the toast confirming the attachment request was accepted.

    Wait For Elements State    ${LORA_ATTACH_SUCCESS}    visible    timeout=30s

Click LoRA delete action
    [Documentation]    Opens the selected adapter's delete confirmation.

    Wait For Elements State    ${LORA_DELETE_ACTION}    visible    timeout=10s
    Click    ${LORA_DELETE_ACTION}
    Wait For Elements State    ${LORA_DELETE_MODAL}    visible    timeout=10s

Get LoRA delete action disabled state
    [Documentation]    Returns the open row action menu's Delete item aria-disabled value.

    Wait For Elements State    ${LORA_DELETE_ACTION}    visible    timeout=10s
    ${state}=    Get Attribute    ${LORA_DELETE_ACTION}    aria-disabled
    RETURN    ${state}

Confirm LoRA deletion
    [Documentation]    Confirms deletion in the open confirmation modal.

    Click    ${LORA_DELETE_CONFIRM}

Get LoRA details text
    [Documentation]    Returns the visible adapter details.

    ${text}=    Get Text    ${LORA_DETAILS_MODAL}
    RETURN    ${text}
LoRA row is visible
    [Documentation]    Returns whether the named adapter row is visible.
    [Arguments]    ${adapter_name}

    VAR    ${row}    css=[data-testid="loras-page"] table tbody tr:has-text("${adapter_name}")
    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${row}    visible    timeout=5s
    RETURN    ${visible}

LoRA delete success is visible
    [Documentation]    Returns whether the deletion success feedback is visible.

    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${LORA_DELETE_SUCCESS}    visible    timeout=30s
    RETURN    ${visible}

LoRA cancel success is visible
    [Documentation]    Returns whether the fine-tuning cancellation feedback is visible.

    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${LORA_CANCEL_SUCCESS}    visible    timeout=30s
    RETURN    ${visible}
Click LoRAs refresh
    [Documentation]    Clicks the manual refresh control above the LoRAs table.

    Wait For Elements State    ${LORAS_REFRESH_BUTTON}    enabled    timeout=15s
    Click    ${LORAS_REFRESH_BUTTON}

Filter LoRAs by base model
    [Documentation]    Opens the base model filter and selects the option matching the given model.
    [Arguments]    ${base_model}

    Wait For Elements State    ${LORAS_BASE_MODEL_FILTER_TRIGGER}    visible    timeout=15s
    Click    ${LORAS_BASE_MODEL_FILTER_TRIGGER}
    Wait For Elements State    ${LORAS_BASE_MODEL_FILTER_LISTBOX}    visible    timeout=10s
    VAR    ${option}    ${LORAS_BASE_MODEL_FILTER_LISTBOX} >> css=[role="option"]:has-text("${base_model}")
    Wait For Elements State    ${option}    visible    timeout=10s
    Click    ${option}
    Press Keys    None    Escape

Get LoRA delete error text
    [Documentation]    Waits for and returns deletion error feedback containing the expected text.
    [Arguments]    ${expected_text}

    VAR    ${error}    css=[data-slot="toast"]:has-text("${expected_text}")
    Wait For Elements State    ${error}    visible    timeout=30s
    ${text}=    Get Text    ${error}
    RETURN    ${text}
