# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for the AIWB API Keys page.
...                 Contains selectors and atomic browser interactions only.
...                 Business logic and assertions belong in feature resources.


*** Variables ***
${API_KEYS_PATH}                       /api-keys

# Page elements — scoped to main content area to avoid matching sidebar nav links
${API_KEYS_PAGE_HEADING}               css=main div.text-md.font-semibold
${CREATE_API_KEY_BUTTON}               button:has-text("Create API Key")

# Create API key drawer — use header element to avoid matching the trigger button
${CREATE_DRAWER_TITLE}                 css=header:has-text("Create API Key")
${NAME_INPUT_PLACEHOLDER}              Enter API key name
# Shared by both the create and edit drawers — only one is ever open at a time.
${API_KEY_FORM_SUBMIT_BUTTON}          button[type="submit"]
# Model deployments multi-select — anchored on its placeholder, which the trigger
# shows until a deployment is picked. The trigger stays disabled until every
# deployment's title and profile subtitle have loaded.
${MODEL_DEPLOYMENTS_SELECT_TRIGGER}    css=button:has-text("Select model deployments")
${MODEL_DEPLOYMENTS_OPTION_SELECTOR}    css=[role="listbox"] [role="option"]
# In the edit drawer the trigger already shows the bound deployment names instead of
# the placeholder, so it is matched by accessible name (the field label) instead.
${MODEL_DEPLOYMENTS_EDIT_TRIGGER}      role=button[name="Model deployments"]

# Key created drawer
${KEY_CREATED_TITLE}                   text="Key created"
${COPY_API_KEY_BUTTON}                 button[aria-label="Copy API key"]
${KEY_CREATED_DONE_BUTTON}             button:has-text("Done")

# Edit API key drawer
${EDIT_DRAWER_TITLE}                   css=header:has-text("Edit API Key")
${LINKED_DEPLOYMENTS_SECTION}          css=div:has(> label:text-is("Linked deployments"))
${API_KEY_UPDATED_TOAST}               text="API key updated successfully"

# Delete confirmation modal
${DELETE_MODAL_SELECTOR}               [data-testid="confirmation-modal"]
${CONFIRM_DELETE_BUTTON}               [data-testid="confirm-button"]

# Table elements
${API_KEYS_TABLE_ROW}                  css=table tbody tr
${EMPTY_TABLE_TEXT}                     text="No API keys found for this project."

# Metrics page elements
${METRICS_KEY_NAME_HEADER}             [data-testid="metrics-header-key-name"]
${METRICS_USAGE_METRICS_LABEL}         text=Usage metrics
${METRICS_STAT_CARDS_GRID}             [data-testid="metrics-stat-cards"]
${METRICS_INFERENCE_CHART_TITLE}       text=Inference requests
${METRICS_TOKEN_CHART_TITLE}           text=Token consumption
${METRICS_TIME_TAB_7DAYS}             css=[role="tab"]:has-text("7 days")
${METRICS_TIME_TAB_7DAYS_SELECTED}    css=[role="tab"][aria-selected="true"]:has-text("7 days")


*** Keywords ***
Navigate to API keys page
    [Documentation]    Navigates to the API Keys page via the sidebar link (SPA navigation).
    ...                Using the sidebar link instead of Go To avoids a full page reload,
    ...                which would cause React to reinitialize and potentially redirect
    ...                away due to project context race conditions.
    ...                Uses retry because the sidebar link click occasionally doesn't
    ...                navigate (e.g., due to animation timing or project context
    ...                redirecting back to Dashboard).
    [Arguments]    ${project}

    Wait Until Keyword Succeeds    30s    2s    Navigate to API keys via sidebar    ${project}

Navigate to API keys via sidebar
    [Documentation]    Clicks the sidebar API Keys link and verifies the page loaded.
    [Arguments]    ${project}

    VAR    ${sidebar_link}    css=a[href="/${project}${API_KEYS_PATH}"]
    Wait For Elements State    ${sidebar_link}    visible    timeout=5s
    Click    ${sidebar_link}
    Wait For Elements State    ${API_KEYS_PAGE_HEADING}    visible    timeout=10s

Click create API key button
    [Documentation]    Clicks the "Create API Key" button to open the creation drawer.
    ...                Waits for the drawer to appear and its opening animation to settle
    ...                before returning control to the caller.

    Click    css=${CREATE_API_KEY_BUTTON}
    Wait For Elements State    ${CREATE_DRAWER_TITLE}    visible    timeout=15s
    Wait For Elements State    css=${API_KEY_FORM_SUBMIT_BUTTON}    stable    timeout=10s

Fill API key name
    [Documentation]    Fills in the API key name in the create drawer.
    ...                Uses Fill Text which replaces any existing value and
    ...                triggers React Hook Form's onChange handler, then
    ...                verifies the value was set correctly.
    [Arguments]    ${name}

    VAR    ${input}    css=input[placeholder="${NAME_INPUT_PLACEHOLDER}"]
    Wait For Elements State    ${input}    visible    timeout=5s
    Wait For Elements State    ${input}    stable    timeout=5s
    Click    ${input}
    Fill Text    ${input}    ${name}
    Get Text    ${input}    ==    ${name}

Submit API key form
    [Documentation]    Submits the create or edit API key form by clicking the submit
    ...                button. The DrawerForm's submit button is in the DrawerFooter,
    ...                OUTSIDE the <form> element, using React Aria's onPress to call
    ...                formRef.current.requestSubmit(). Uses Click which triggers
    ...                React Aria's pointer-based press handler.

    VAR    ${btn}    css=${API_KEY_FORM_SUBMIT_BUTTON}
    Wait For Elements State    ${btn}    visible    timeout=5s
    Wait For Elements State    ${btn}    enabled    timeout=5s
    Click    ${btn}

Click copy API key button
    [Documentation]    Clicks the copy button on the key created drawer.

    VAR    ${btn}    css=${COPY_API_KEY_BUTTON}
    Wait For Elements State    ${btn}    visible    timeout=10s
    Click    ${btn}

Click done on key created drawer
    [Documentation]    Clicks the "Done" button to close the key created drawer.

    Click    css=${KEY_CREATED_DONE_BUTTON}
    Wait For Elements State    ${KEY_CREATED_TITLE}    hidden    timeout=10s

Table row containing text should exist
    [Documentation]    Verifies a table row with the given text exists.
    [Arguments]    ${text}

    VAR    ${row}    css=table tbody tr:has-text("${text}")
    Wait For Elements State    ${row}    visible    timeout=15s

Click actions menu on API key row
    [Documentation]    Clicks the actions menu (three dots) on a specific API key row.
    [Arguments]    ${key_name}

    VAR    ${row}    css=table tbody tr:has-text("${key_name}")
    ${actions_btn}=    Get Element    ${row} >> css=button[aria-label="Actions"]
    Click    ${actions_btn}

Click edit action in actions menu
    [Documentation]    Clicks the "Edit API Key" option in the actions dropdown.

    VAR    ${edit_option}    text="Edit API Key"
    Wait For Elements State    ${edit_option}    visible    timeout=5s
    Click    ${edit_option}

Wait for edit drawer
    [Documentation]    Waits for the Edit API Key drawer to be visible and stable.

    Wait For Elements State    ${EDIT_DRAWER_TITLE}    visible    timeout=15s
    Wait For Elements State    css=${API_KEY_FORM_SUBMIT_BUTTON}    stable    timeout=10s

Wait for edit drawer to close
    [Documentation]    Waits for the Edit API Key drawer to close after a successful save.

    Wait For Elements State    ${EDIT_DRAWER_TITLE}    hidden    timeout=10s

Wait for API key updated toast
    [Documentation]    Waits for the "API key updated successfully" toast to appear.

    Wait For Elements State    ${API_KEY_UPDATED_TOAST}    visible    timeout=15s

Wait for linked deployments section to show text "${text}"
    [Documentation]    Waits for an element containing the given text to appear in the
    ...                linked deployments section.

    Wait For Elements State    ${LINKED_DEPLOYMENTS_SECTION}:has-text("${text}")    visible    timeout=15s

Get linked deployments match count for text "${text}"
    [Documentation]    Returns how many elements in the linked deployments section match
    ...                the given text. Waits for the section itself to be visible first,
    ...                since a selector matching zero elements is trivially absent and
    ...                would otherwise report 0 even if the section never rendered at all.

    Wait For Elements State    ${LINKED_DEPLOYMENTS_SECTION}    visible    timeout=15s
    ${count}=    Get Element Count    ${LINKED_DEPLOYMENTS_SECTION}:has-text("${text}")
    RETURN    ${count}

Open model deployments select
    [Documentation]    Opens the model deployments multi-select using the given trigger
    ...                selector — the create drawer's placeholder-based trigger by default,
    ...                or ${MODEL_DEPLOYMENTS_EDIT_TRIGGER} for the edit drawer, where the
    ...                trigger already displays the bound deployment names instead of a
    ...                placeholder. Waits for the trigger to be enabled first: the field is
    ...                gated on the deployment titles and profile subtitles having loaded,
    ...                so opening it early would read stale option text.
    [Arguments]    ${trigger}=${MODEL_DEPLOYMENTS_SELECT_TRIGGER}

    Wait For Elements State    ${trigger}    visible    timeout=15s
    Wait For Elements State    ${trigger}    enabled    timeout=30s
    Click    ${trigger}
    Wait For Elements State    css=[role="listbox"]    visible    timeout=10s

Click model deployments option "${text}"
    [Documentation]    Clicks the open deployments picker's option matching the given text,
    ...                toggling its selection on or off.

    VAR    ${option}    ${MODEL_DEPLOYMENTS_OPTION_SELECTOR}:has-text("${text}")
    Wait For Elements State    ${option}    visible    timeout=10s
    Click    ${option}

Get model deployments option count for text "${text}"
    [Documentation]    Returns how many options in the open deployments select include the given
    ...                text. Each option shows the deployment name and, below it, the profile
    ...                subtitle, so a match on either counts.

    VAR    ${options}    ${MODEL_DEPLOYMENTS_OPTION_SELECTOR}:has-text("${text}")
    ${count}=    Get Element Count    ${options}
    RETURN    ${count}

Click delete action in actions menu
    [Documentation]    Clicks the "Delete API Key" option in the actions dropdown.

    VAR    ${delete_option}    text="Delete API Key"
    Wait For Elements State    ${delete_option}    visible    timeout=5s
    Click    ${delete_option}

Wait for delete confirmation modal
    [Documentation]    Waits for the delete confirmation modal to appear.

    VAR    ${modal}    css=${DELETE_MODAL_SELECTOR}
    Wait For Elements State    ${modal}    visible    timeout=10s

Confirm delete API key
    [Documentation]    Clicks the confirm button on the delete confirmation modal.

    VAR    ${confirm}    css=${CONFIRM_DELETE_BUTTON}
    Click    ${confirm}
    VAR    ${modal}    css=${DELETE_MODAL_SELECTOR}
    Wait For Elements State    ${modal}    hidden    timeout=10s

Table row containing text should not exist
    [Documentation]    Verifies a table row with the given text does not exist.
    [Arguments]    ${text}

    VAR    ${row}    css=table tbody tr:has-text("${text}")
    Wait For Elements State    ${row}    hidden    timeout=15s

Navigate to API key metrics page
    [Documentation]    Navigates directly to the API key metrics page by URL.
    ...                Used when no sidebar link exists (metrics page is accessed via direct URL).
    [Arguments]    ${base_url}    ${project}    ${api_key_id}

    Go To    ${base_url}/${project}${API_KEYS_PATH}/${api_key_id}
    Wait For Elements State    ${METRICS_KEY_NAME_HEADER}    visible    timeout=15s

API key name should be visible in metrics header
    [Documentation]    Verifies the API key name appears in the metrics page header.
    [Arguments]    ${key_name}

    Wait For Elements State    ${METRICS_KEY_NAME_HEADER}:has-text("${key_name}")    visible    timeout=10s

Stat cards should be present on metrics page
    [Documentation]    Verifies the stat cards grid is visible on the metrics page.

    Wait For Elements State    ${METRICS_STAT_CARDS_GRID}    visible    timeout=10s

Inference requests chart should be visible
    [Documentation]    Verifies the inference requests chart section is present.

    Wait For Elements State    ${METRICS_INFERENCE_CHART_TITLE}    visible    timeout=10s

Token consumption chart should be visible
    [Documentation]    Verifies the token consumption chart section is present.

    Wait For Elements State    ${METRICS_TOKEN_CHART_TITLE}    visible    timeout=10s

Click 7 day time range tab
    [Documentation]    Clicks the "7 days" tab in the time range selector.

    Wait For Elements State    ${METRICS_TIME_TAB_7DAYS}    visible    timeout=10s
    Click    ${METRICS_TIME_TAB_7DAYS}

7 day tab should be selected
    [Documentation]    Verifies the "7 days" tab is the selected time range.

    Wait For Elements State    ${METRICS_TIME_TAB_7DAYS_SELECTED}    visible    timeout=5s
