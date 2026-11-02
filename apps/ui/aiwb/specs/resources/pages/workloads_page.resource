# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for the AIWB Dashboard workloads section.
...                 Contains selectors and atomic browser interactions only.
...                 The workloads table is on the Dashboard page (/).
...                 Business logic and assertions belong in feature resources.


*** Variables ***
${DASHBOARD_PATH}                  /
${AIM_DETAILS_PATH}                /aims
${WORKLOADS_GRID_SELECTOR}         [role="grid"]
${WORKLOAD_ROW_SELECTOR}           [role="row"]
${ACTIONS_BUTTON_SELECTOR}         button[aria-label="Actions"]
${DETAILS_BUTTON_SELECTOR}         [data-testid="details"]
${CONTAINER_VERSION_SELECTOR}      h5:has-text("Container version") + p
${AIM_LABEL_SELECTOR}             text="AIM"
${CONTAINER_VERSION_LABEL}        text="Container version"
${LOGS_BUTTON_SELECTOR}           button:has-text("Logs")
${STATUS_DISPLAY_SELECTOR}        [class*="status"], [class*="Status"]
${METRICS_SECTION_SELECTOR}       text="Inference metrics"
${BASIC_INFO_SECTION_SELECTOR}    text="Basic information"
${CHAT_BUTTON_SELECTOR}           button:has-text("Chat")
${DELETE_BUTTON_SELECTOR}         button:has-text("Delete")
${CONNECT_TO_MODEL_BTN_SELECTOR}    [data-testid="connect-to-model-button"]
${CONNECT_MODAL_TITLE_SELECTOR}     [role="dialog"] >> text="Connect to model"
${LORA_ADAPTERS_CARD_SELECTOR}      [data-testid="lora-adapters-card"]
${EDIT_LORA_ADAPTERS_SELECTOR}      [data-testid="edit-lora-adapters-button"]
${EDIT_LORA_MODAL_SELECTOR}         [data-testid="edit-lora-adapters-modal"]
${APPLY_LORA_ADAPTERS_SELECTOR}     [data-testid="apply-lora-adapters-button"]
${EDIT_LORA_ADAPTERS_READY_SELECTOR}
...    [data-testid="edit-lora-adapters-modal"] [data-testid="lora-adapters-selector"][data-loading="false"]
# Stable testid on the code-example Snippet; its <pre> holds the curl body
# whose OpenAI `model` field is what we assert on.
${CONNECT_SNIPPET_SELECTOR}         [data-testid="connect-code-snippet"] >> css=pre
${WORKLOAD_DESCRIPTION_SELECTOR}    css=h5:has-text("Description") + p
${AIM_DETAILS_TITLE_SELECTOR}       css=h2


*** Keywords ***
Navigate to dashboard
    [Documentation]    Navigates to the Dashboard which contains the workloads table.
    [Arguments]    ${base_url}    ${project}

    Go To    ${base_url}/${project}${DASHBOARD_PATH}
    VAR    ${grid}    css=${WORKLOADS_GRID_SELECTOR}
    Wait For Elements State    ${grid}    visible    timeout=15s

Navigate to AIM details page
    [Documentation]    Navigates directly to an AIM service details page.
    [Arguments]    ${base_url}    ${project}    ${service_id}

    Go To    ${base_url}/${project}${AIM_DETAILS_PATH}/${service_id}
    Wait For Elements State    ${BASIC_INFO_SECTION_SELECTOR}    visible    timeout=30s

Navigate to workload details page by id
    [Documentation]    Navigates directly to a workload details page by URL.
    ...                Does not require the workload to exist — waits for the
    ...                project selector to be ready, which confirms the app shell
    ...                (including the header) is fully rendered and ready to switch projects.
    [Arguments]    ${base_url}    ${project}    ${workload_id}

    Go To    ${base_url}/${project}/workloads/${workload_id}
    VAR    ${project_selector}    css=[data-testid="project-select"]
    Wait For Elements State    ${project_selector}    visible    timeout=15s

Get inference workload row text
    [Documentation]    Returns the text content of the first inference workload row.

    VAR    ${row_selector}    css=${WORKLOAD_ROW_SELECTOR}:has-text("Inference")
    ${rows}=    Get Elements    ${row_selector}
    VAR    ${row}    ${rows}[0]
    ${text}=    Get Text    ${row}
    RETURN    ${text}

Get workload name cell text
    [Documentation]    Returns a workload's display name and profile summary.
    [Arguments]    ${workload_id}

    VAR    ${selector}    css=[role="row"]\[data-key="${workload_id}"] [role="rowheader"]
    Wait For Elements State    ${selector}    visible    timeout=30s
    ${text}=    Get Text    ${selector}
    RETURN    ${text}

Get workloads grid text
    [Documentation]    Returns the combined text content of the workloads grid, used to
    ...                assert which names are (and are not) shown in the table.

    VAR    ${grid}    css=${WORKLOADS_GRID_SELECTOR}
    Wait For Elements State    ${grid}    visible    timeout=15s
    ${text}=    Get Text    ${grid}
    RETURN    ${text}

Click actions menu on inference workload
    [Documentation]    Clicks the actions menu on the inference workload row.
    ...                If workload_id is provided, selects that specific workload.
    ...                Otherwise, selects the first inference workload found.
    [Arguments]    ${workload_id}=${None}

    IF    $workload_id is not None
        # Use data-key attribute to find specific workload by ID
        VAR    ${row_selector}    css=[role="row"]\[data-key="${workload_id}"]
        # Wait for the specific workload to appear in the table (may take time after deployment)
        # Longer timeout for workloads to sync from K8s to UI
        TRY
            Wait For Elements State    ${row_selector}    visible    timeout=30s
        EXCEPT
            Take Screenshot    workload-not-found-debug
            # Get all visible workload rows for debugging
            ${all_rows}=    Get Elements    css=[role="row"]
            ${count}=    Get Length    ${all_rows}
            Log    Found ${count} total rows in table    level=WARN
            FOR    ${row}    IN    @{all_rows}
                ${row_html}=    Get Property    ${row}    outerHTML
                Log    Row HTML: ${row_html}    level=DEBUG
            END
            Fail    Workload ${workload_id} not found in UI table after 30s. Check screenshot for details.
        END
    ELSE
        # Fall back to first inference workload
        VAR    ${row_selector}    css=${WORKLOAD_ROW_SELECTOR}:has-text("Inference") >> nth=0
    END

    ${row}=    Get Element    ${row_selector}
    VAR    ${actions_btn}    ${row} >> css=${ACTIONS_BUTTON_SELECTOR}
    Click    ${actions_btn}
    VAR    ${details}    css=${DETAILS_BUTTON_SELECTOR}
    Wait For Elements State    ${details}    visible    timeout=5s

Click open details in actions menu
    [Documentation]    Clicks "Open details" in the currently visible actions menu.

    VAR    ${details}    css=${DETAILS_BUTTON_SELECTOR}
    Click    ${details}
    Wait For Elements State    ${AIM_LABEL_SELECTOR}    visible    timeout=15s

Get container version text
    [Documentation]    Returns the Container version value from the workload details page.

    Wait For Elements State    ${CONTAINER_VERSION_LABEL}    visible    timeout=10s
    VAR    ${selector}    css=${CONTAINER_VERSION_SELECTOR}
    ${version}=    Get Text    ${selector}
    RETURN    ${version}

Get workload description text
    [Documentation]    Returns the description shown in workload basic information.

    Wait For Elements State    ${WORKLOAD_DESCRIPTION_SELECTOR}    visible    timeout=30s
    ${description}=    Get Text    ${WORKLOAD_DESCRIPTION_SELECTOR}
    RETURN    ${description}

Get AIM details title text
    [Documentation]    Returns the title shown in the AIM details page header.

    Wait For Elements State    ${AIM_DETAILS_TITLE_SELECTOR}    visible    timeout=30s
    ${title}=    Get Text    ${AIM_DETAILS_TITLE_SELECTOR}
    RETURN    ${title}

Get deployed workload row count
    [Documentation]    Returns the number of workload rows in the grid.

    ${elements}=    Get Elements    css=${WORKLOAD_ROW_SELECTOR}
    ${count}=    Get Length    ${elements}
    RETURN    ${count}

Get inference workload status text
    [Documentation]    Returns the text of the first inference workload row for status verification.

    VAR    ${row_selector}    css=${WORKLOAD_ROW_SELECTOR}:has-text("Inference")
    ${rows}=    Get Elements    ${row_selector}
    VAR    ${row}    ${rows}[0]
    ${text}=    Get Text    ${row}
    RETURN    ${text}

Is logs button visible
    [Documentation]    Returns whether the Logs button is visible on the workload or AIM details page.

    VAR    ${btn}    css=${LOGS_BUTTON_SELECTOR}
    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${btn}    visible    timeout=5s
    RETURN    ${visible}

Is performance metric visible
    [Documentation]    Returns whether the Performance metric field is visible on the workload or AIM details page.

    VAR    ${selector}    text="Performance metric"
    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${selector}    visible    timeout=5s
    RETURN    ${visible}

Get LoRA adapters card text
    [Documentation]    Returns the visible content of the LoRA adapters card.

    VAR    ${card}    css=${LORA_ADAPTERS_CARD_SELECTOR}
    Wait For Elements State    ${card}    visible    timeout=30s
    ${text}=    Get Text    ${card}
    RETURN    ${text}

Open LoRA adapters editor
    [Documentation]    Opens the adapter selection modal from the LoRA adapters card and waits for
    ...    its adapter table to finish loading. The dialog mounts before the adapters and the
    ...    serving profile arrive, so rows counted on mount describe a loading table rather than
    ...    the filtered offer.

    VAR    ${button}    css=${EDIT_LORA_ADAPTERS_SELECTOR}
    Click    ${button}
    VAR    ${modal}    css=${EDIT_LORA_MODAL_SELECTOR}
    Wait For Elements State    ${modal}    visible    timeout=15s
    VAR    ${table}    css=${EDIT_LORA_ADAPTERS_READY_SELECTOR}
    Wait For Elements State    ${table}    visible    timeout=30s

Get LoRA adapters editor text
    [Documentation]    Returns the visible content of the open adapter selection modal.

    VAR    ${modal}    css=${EDIT_LORA_MODAL_SELECTOR}
    Wait For Elements State    ${modal}    visible    timeout=30s
    ${text}=    Get Text    ${modal}
    RETURN    ${text}

LoRA adapters editor row is visible
    [Documentation]    Reports whether the open editor lists the named adapter.
    [Arguments]    ${display_name}

    VAR    ${row}    css=${EDIT_LORA_MODAL_SELECTOR} tbody tr:has-text("${display_name}")
    ${count}=    Get Element Count    ${row}
    RETURN    ${{ $count > 0 }}

Toggle LoRA adapter row
    [Documentation]    Toggles the checkbox for the adapter row containing the given display name.
    [Arguments]    ${display_name}

    VAR    ${checkbox}
    ...    css=${EDIT_LORA_MODAL_SELECTOR} tbody tr:has-text("${display_name}") [aria-label^="Select row "]
    Wait For Elements State    ${checkbox}    visible    timeout=15s
    Click    ${checkbox}

Clear selected LoRA adapters
    [Documentation]    Unchecks every selected adapter in the open editor.

    VAR    ${selected}
    ...    css=${EDIT_LORA_MODAL_SELECTOR} tbody [aria-label^="Select row "][aria-checked="true"]
    ${checkboxes}=    Get Elements    ${selected}
    FOR    ${checkbox}    IN    @{checkboxes}
        Click    ${checkbox}
    END

Apply LoRA adapter selection
    [Documentation]    Applies the selected adapters and waits for the editor to close.

    VAR    ${button}    css=${APPLY_LORA_ADAPTERS_SELECTOR}
    Click    ${button}
    VAR    ${modal}    css=${EDIT_LORA_MODAL_SELECTOR}
    Wait For Elements State    ${modal}    detached    timeout=30s

Click connect to model button
    [Documentation]    Clicks the Connect to model button in the Output card header.

    VAR    ${btn}    css=${CONNECT_TO_MODEL_BTN_SELECTOR}
    Wait For Elements State    ${btn}    visible    timeout=15s
    Click    ${btn}

Is connect modal visible
    [Documentation]    Returns whether the Connect to model modal is visible.

    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${CONNECT_MODAL_TITLE_SELECTOR}    visible    timeout=10s
    RETURN    ${visible}

Get connection snippet text
    [Documentation]    Returns the code-example snippet body shown in the Connect to
    ...                model dialog (the default curl example, which carries the
    ...                OpenAI `model` field).

    Wait For Elements State    ${CONNECT_SNIPPET_SELECTOR}    visible    timeout=10s
    ${text}=    Get Text    ${CONNECT_SNIPPET_SELECTOR}
    RETURN    ${text}

Is delete button disabled
    [Documentation]    Returns whether the Delete button on the AIM details page is disabled.

    ${disabled}=    Run Keyword And Return Status
    ...    Wait For Elements State    css=${DELETE_BUTTON_SELECTOR}    disabled    timeout=10s
    RETURN    ${disabled}

Is basic information section visible
    [Documentation]    Returns whether the Basic information section is visible on the
    ...                AIM details page.

    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${BASIC_INFO_SECTION_SELECTOR}    visible    timeout=30s
    RETURN    ${visible}
