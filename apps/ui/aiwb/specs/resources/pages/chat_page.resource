# Copyright (c) Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for the AIWB Chat page.
...                 Contains selectors and atomic browser interactions only.
...                 Business logic and assertions belong in feature resources.


*** Variables ***
${CHAT_PATH}                       /chat
${CHAT_INPUT_SELECTOR}             [data-testid="chat-input"]
${ATTACH_IMAGE_BUTTON_SELECTOR}    [data-testid="attach-image-button"]
${SEND_BUTTON_SELECTOR}            [data-testid="send-button"]
${DRAG_OVERLAY_SELECTOR}           [data-testid="drag-overlay"]
${CHAT_TAB_SELECTOR}               [aria-label="Chat"]
${COMPARE_TAB_SELECTOR}            [aria-label="Compare"]
${MODEL_SELECT_SELECTOR}            [data-testid="model-deployment-select"]
${CHAT_MESSAGES_SELECTOR}           [data-testid="chat-messages"]
${LISTBOX_SELECTOR}                 [role="listbox"]
${LISTBOX_OPTION_SELECTOR}          [role="listbox"] [role="option"]


*** Keywords ***
Navigate to chat page
    [Documentation]    Navigates to the Chat page and waits for it to load and the input to appear.
    [Arguments]    ${base_url}    ${project}

    Go To    ${base_url}/${project}${CHAT_PATH}
    VAR    ${selector}    css=${CHAT_INPUT_SELECTOR}
    Wait For Elements State    ${selector}    visible    timeout=30s

Navigate to chat page with workload
    [Documentation]    Navigates to the Chat page with a pre-selected workload via URL param.
    [Arguments]    ${base_url}    ${project}    ${workload_id}

    Go To    ${base_url}/${project}${CHAT_PATH}?workload=${workload_id}
    Wait For Elements State    css=${CHAT_INPUT_SELECTOR}    visible    timeout=30s

Attach image button should be visible
    [Documentation]    Verifies the image attachment button is present in the chat input.

    Wait For Elements State    css=${ATTACH_IMAGE_BUTTON_SELECTOR}    visible    timeout=10s

Attach image button should not be visible
    [Documentation]    Verifies the image attachment button is absent (model does not support images).

    Wait For Elements State    css=${ATTACH_IMAGE_BUTTON_SELECTOR}    hidden    timeout=10s

Click attach image button
    [Documentation]    Clicks the paperclip button to open the file picker.

    Click    css=${ATTACH_IMAGE_BUTTON_SELECTOR}

Upload image file
    [Documentation]    Selects an image file via the hidden file input.
    ...                Uses Upload File By Selector which bypasses the OS file dialog.
    [Arguments]    ${file_path}

    Upload File By Selector    input[type="file"][accept="image/*"]    ${file_path}

Get attached image count
    [Documentation]    Returns how many image thumbnails are shown in the attachment preview area.

    ${elements}=    Get Elements    css=.relative.group img[alt]
    ${count}=    Get Length    ${elements}
    RETURN    ${count}

Attached image count should be greater than zero
    [Documentation]    Verifies at least one image thumbnail is displayed below the input.

    ${count}=    Get attached image count
    Should Be True    ${count} > 0    msg=No image thumbnails visible in chat input

Image thumbnails should be visible
    [Documentation]    Waits until at least one image thumbnail is displayed below the input.

    Wait Until Keyword Succeeds    10s    500ms    Attached image count should be greater than zero

Send button should be enabled
    [Documentation]    Verifies the send button is clickable (not disabled).

    Wait For Elements State    css=${SEND_BUTTON_SELECTOR}    enabled    timeout=10s

Send button should be disabled
    [Documentation]    Verifies the send button is disabled (no content to send).

    Wait For Elements State    css=${SEND_BUTTON_SELECTOR}    disabled    timeout=10s

Type chat message
    [Documentation]    Types text into the chat input textarea.
    [Arguments]    ${text}

    Fill Text    css=${CHAT_INPUT_SELECTOR}    ${text}

Get chat mode tabs text
    [Documentation]    Returns the visible text of the chat mode toolbar area.

    ${text}=    Get Text    css=[aria-label="Chat modes"]
    RETURN    ${text}

Get model selector count
    [Documentation]    Returns the number of model selector dropdowns visible on the page.

    ${elements}=    Get Elements    css=${MODEL_SELECT_SELECTOR}
    ${count}=    Get Length    ${elements}
    RETURN    ${count}

Click model selector
    [Documentation]    Clicks the first model selector dropdown to open it.
    ...                Uses nth=0 to target the first selector (relevant in compare mode
    ...                where two selectors exist).
    [Arguments]    ${index}=0

    VAR    ${selector}    css=${MODEL_SELECT_SELECTOR} >> nth=${index}
    Click    ${selector}

Wait for listbox visible
    [Documentation]    Waits for the listbox dropdown to become visible.

    VAR    ${listbox}    css=${LISTBOX_SELECTOR}
    Wait For Elements State    ${listbox}    visible    timeout=10s

Click first listbox option
    [Documentation]    Clicks the first option in the currently visible listbox.

    VAR    ${option}    css=${LISTBOX_OPTION_SELECTOR} >> nth=0
    Click    ${option}

Get listbox option count
    [Documentation]    Returns the number of options in the currently visible listbox.

    VAR    ${options}    css=${LISTBOX_OPTION_SELECTOR}
    ${elements}=    Get Elements    ${options}
    ${count}=    Get Length    ${elements}
    RETURN    ${count}

Get listbox option count for text "${text}"
    [Documentation]    Returns how many options in the open model selector include the given
    ...                text. An option renders its deployment name on the first line and its
    ...                description (the profile line) on the second, so a match on either counts.

    VAR    ${options}    css=${LISTBOX_OPTION_SELECTOR}:has-text("${text}")
    ${count}=    Get Element Count    ${options}
    RETURN    ${count}

Get listbox option name lines
    [Documentation]    Returns the first text line from each option in the open model
    ...                selector listbox, preserving visual option order.

    ${options}=    Get Elements    css=${LISTBOX_OPTION_SELECTOR}
    @{name_lines}=    Create List
    FOR    ${option}    IN    @{options}
        ${text}=    Get Text    ${option}
        @{lines}=    Split To Lines    ${text}
        VAR    ${name_line}    ${lines}[0]
        Append To List    ${name_lines}    ${name_line}
    END
    RETURN    ${name_lines}

Get chat input disabled state
    [Documentation]    Returns the disabled property of the chat input textarea.

    VAR    ${selector}    css=${CHAT_INPUT_SELECTOR}
    ${disabled}=    Get Property    ${selector}    disabled
    RETURN    ${disabled}

Click send button
    [Documentation]    Clicks the send button to submit the chat message.

    VAR    ${selector}    css=${SEND_BUTTON_SELECTOR}
    Wait For Elements State    ${selector}    enabled    timeout=5s
    Click    ${selector}

Click compare tab
    [Documentation]    Clicks the Compare tab to switch to compare mode.

    Click    css=${COMPARE_TAB_SELECTOR}

Get chat messages container count
    [Documentation]    Returns the number of chat message containers visible.
    ...                In regular mode there is one, in compare mode there are two.

    ${elements}=    Get Elements    css=${CHAT_MESSAGES_SELECTOR}
    ${count}=    Get Length    ${elements}
    RETURN    ${count}

Wait for assistant response
    [Documentation]    Waits for an assistant response to finish streaming.
    ...                The UI conditionally renders the send button only when not streaming,
    ...                so the send button becoming visible again is a reliable signal that
    ...                the response has fully loaded. Uses nth=0 for compare mode where
    ...                multiple send buttons may exist.

    VAR    ${send_btn}    css=${SEND_BUTTON_SELECTOR} >> nth=0
    Wait For Elements State    ${send_btn}    visible    timeout=120s

Get assistant message text
    [Documentation]    Returns the text content of the last assistant message only.
    ...                Targets the last .group element inside the chat-messages container,
    ...                which is always the most recent assistant response after sending.
    ...                Waits for streaming to complete before extracting text.

    Wait for assistant response
    VAR    ${last_msg}    css=${CHAT_MESSAGES_SELECTOR} .group >> nth=-1
    ${text}=    Get Text    ${last_msg}
    RETURN    ${text}

Get assistant message text from panel
    [Documentation]    Returns the text content of the last assistant message in a specific
    ...                chat panel. Used in compare mode where two panels exist side by side.
    [Arguments]    ${panel_index}=0

    VAR    ${last_msg}    css=${CHAT_MESSAGES_SELECTOR} >> nth=${panel_index} >> .group >> nth=-1
    ${text}=    Get Text    ${last_msg}
    RETURN    ${text}
