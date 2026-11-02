# Copyright (c) Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for Chat UI features.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)
Resource            common/session.resource
Resource            common/login.resource
Resource            pages/chat_page.resource
Resource            pages/workloads_page.resource
Library             libraries/ChatAimSelector.py
Library             ../libraries/TemporaryUserManager.py


*** Keywords ***
# =============================================================================
# Given keywords (UI preconditions)
# =============================================================================

User is on chat page
    [Documentation]    Navigates to the Chat page.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to chat page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

User is on chat page with workload "${workload_id}"
    [Documentation]    Navigates to the Chat page with the given workload pre-selected.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to chat page with workload    ${UI_BASE_URL}    ${TEST_PROJECT}[name]    ${workload_id}

A multimodal AIM is deployed and running
    [Documentation]    Ensures a multimodal-capable AIM is deployed and running in the test project.
    ...                Searches the AIM catalog for a Ready model tagged vision, vision-language,
    ...                image-to-text, image-text-to-text, or multimodal (without HF token requirement).
    ...                Deploys it into the current test project namespace (or reuses an existing
    ...                running service for that model — idempotent with AIM is deployed and running).
    ...                Fails with a clear message if no multimodal AIM is available in the catalog.
    ...                Sets: TEST_AIM_NAME, TEST_AIM_ID

    ${response}=    List AIMs    expected_status=200
    VAR    ${aims_list}    ${response.json()['data']}

    ${found_aim}=    Find multimodal aim    ${aims_list}
    Should Not Be Equal    ${found_aim}    ${None}
    ...    msg=No multimodal-capable AIM found in cluster catalog. Need a Ready AIM (no HF token) tagged vision, vision-language, image-to-text, image-text-to-text, or multimodal.

    VAR    ${aim_name}    ${found_aim['metadata']['name']}
    Set Test Variable    ${TEST_AIM_NAME}    ${aim_name}
    Set Test Variable    ${TEST_AIM}    ${found_aim}

    AIM is deployed and running

User has selected a model on the chat page
    [Documentation]    Navigates to the Chat page and selects the first available model.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to chat page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]
    User selects a model

# =============================================================================
# When keywords (actions)
# =============================================================================

User navigates to chat from details
    [Documentation]    Clicks the Chat button on the AIM details page to open the chat view.
    ...                Expects the user to already be on an AIM details page.

    Click    css=${CHAT_BUTTON_SELECTOR}
    Wait For Elements State    css=${CHAT_INPUT_SELECTOR}    visible    timeout=60s

User attaches image "${file_path}" to chat
    [Documentation]    Uploads an image file via the attach-image button file picker.
    ...                Verifies the attach-image control is visible before upload to avoid
    ...                interacting with a hidden file input when image input is disabled.

    Attach image button should be visible
    Upload image file    ${file_path}

User types "${message}" in chat
    [Documentation]    Enters text into the chat input field.

    Type chat message    ${message}

User navigates to the chat page
    [Documentation]    Navigates to the Chat page.

    Navigate to chat page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

User selects a model
    [Documentation]    Selects the first model in the model dropdown.
    ...                Waits for the model selector to have loaded options before selecting.

    Wait Until Keyword Succeeds    60s    3s    Open selector and pick first model
    Chat input should be enabled

User types a message and sends it
    [Documentation]    Types a test message and clicks the send button.

    Type chat message    Hello, can you tell me what you are?
    Click send button

User opens the compare tab and selects two models
    [Documentation]    Switches to compare mode and selects a model in the second selector.
    ...                The first model carries over from chat mode.

    Click compare tab
    Wait Until Keyword Succeeds    10s    1s    Two model selectors should be visible
    Click model selector    index=1
    Wait for listbox visible
    Click first listbox option

User sends a message
    [Documentation]    Types a test message and sends it (alias for compare scenario).

    Type chat message    What is machine learning?
    Click send button

# =============================================================================
# Then keywords (verification)
# =============================================================================

Chat input should be visible
    [Documentation]    Verifies the chat input is visible, confirming the user reached the chat view.

    Wait For Elements State    css=${CHAT_INPUT_SELECTOR}    visible    timeout=15s

Image attachment button should be available
    [Documentation]    Verifies the image attachment button is visible on the chat input,
    ...                indicating the selected deployment supports image input.

    Attach image button should be visible

Image attachment button should not be available
    [Documentation]    Verifies the image attachment button is absent from the chat input,
    ...                indicating the selected deployment does not support image input.

    Attach image button should not be visible

Attached image should appear in preview
    [Documentation]    Verifies an image thumbnail appears in the attachment preview area
    ...                below the chat input.

    Image thumbnails should be visible

Chat input should be ready to send
    [Documentation]    Verifies the send button is enabled, indicating the input has content.

    Send button should be enabled

Available models should be listed for selection
    [Documentation]    Verifies that the model selector is present and has options.

    ${count}=    Get model selector count
    Should Be True    ${count} > 0    msg=At least one model selector should be visible

User should be able to select a model
    [Documentation]    Verifies a model can be selected from the dropdown by opening
    ...                the selector, checking options exist, and selecting the first one.

    Click model selector
    Wait for listbox visible
    ${option_count}=    Get listbox option count
    Should Be True    ${option_count} > 0    msg=Model selector should have at least one option
    Click first listbox option
    Chat input should be enabled

Response should stream and render in the chat interface
    [Documentation]    Verifies that the assistant response appears and contains meaningful text.
    ...                Gets only the assistant message content (excluding the user prompt) to
    ...                ensure the assertion reflects actual model output.

    ${text}=    Get assistant message text
    ${length}=    Get Length    ${text}
    Should Be True    ${length} > 10    msg=Assistant response should contain meaningful text

Responses from both models should be displayed side by side
    [Documentation]    Verifies that both chat message containers are visible in compare mode
    ...                and that each panel contains an assistant response with content.

    ${count}=    Get chat messages container count
    Should Be Equal As Integers    ${count}    2
    ...    msg=Compare mode should show two chat message panels side by side
    Wait for assistant response
    ${text_panel_0}=    Get assistant message text from panel    panel_index=0
    ${length_0}=    Get Length    ${text_panel_0}
    Should Be True    ${length_0} > 10
    ...    msg=First model panel should contain an assistant response
    ${text_panel_1}=    Get assistant message text from panel    panel_index=1
    ${length_1}=    Get Length    ${text_panel_1}
    Should Be True    ${length_1} > 10
    ...    msg=Second model panel should contain an assistant response

Chat input should be enabled
    [Documentation]    Verifies the chat input textarea is enabled.

    ${disabled}=    Get chat input disabled state
    Should Not Be True    ${disabled}    msg=Chat input should be enabled after model selection

The chat model selector should offer the deployment labeled "${label}"
    [Documentation]    Opens the model selector and verifies a deployment option includes
    ...                the given label in its rendered text (name or description line).

    Wait Until Keyword Succeeds    60s    3s    Open model selector and show its options
    Wait Until Keyword Succeeds    15s    2s    Model selector should offer an option labeled    ${label}

The chat model selector should show default model name when no custom deployment name is set
    [Documentation]    Verifies the model's default name is shown when no custom
    ...                deployment name is provided and, when that default differs
    ...                from the catalog title, the title is not offered as the label.
    ...                Requires: TEST_AIM_CANONICAL_NAME, TEST_AIM_DISPLAY_NAME.

    Wait Until Keyword Succeeds    15s    2s    Open model selector and show its options
    Wait Until Keyword Succeeds    15s    2s    Model selector should offer an option named exactly    ${TEST_AIM_CANONICAL_NAME}
    IF    '${TEST_AIM_CANONICAL_NAME}' != '${TEST_AIM_DISPLAY_NAME}'
        Model selector should not offer an option named exactly    ${TEST_AIM_DISPLAY_NAME}
    END

Open model selector and show its options
    [Documentation]    Single-poll helper: opens the model selector and waits for its listbox.
    ...                Retried while the deployment list is still loading.

    Click model selector
    Wait for listbox visible
    ${option_count}=    Get listbox option count
    Should Be True    ${option_count} > 0    msg=Model selector options have not loaded yet

Model selector should offer an option labeled
    [Documentation]    Single-poll helper: asserts the open model selector offers at least one
    ...                option whose text includes the given label.
    [Arguments]    ${label}

    ${count}=    Get listbox option count for text "${label}"
    Should Be True    ${count} > 0
    ...    msg=Model selector offered no option labeled "${label}"

Model selector should offer an option named exactly
    [Documentation]    Single-poll helper: asserts the open model selector offers at least one
    ...                option whose first text line exactly matches the given label.
    [Arguments]    ${label}

    ${name_lines}=    Get listbox option name lines
    List Should Contain Value    ${name_lines}    ${label}
    ...    msg=Expected an option name line exactly matching "${label}" (names: ${name_lines})

Model selector should not offer an option named exactly
    [Documentation]    Single-poll helper: asserts the open selector has no option whose
    ...                first text line exactly matches the given label.
    [Arguments]    ${label}

    ${name_lines}=    Get listbox option name lines
    List Should Not Contain Value    ${name_lines}    ${label}
    ...    msg=Unexpected option name line "${label}" found in selector (names: ${name_lines})

# =============================================================================
# Internal helper keywords
# =============================================================================

Open selector and pick first model
    [Documentation]    Opens the model selector and picks the first option.
    ...                Used with Wait Until Keyword Succeeds for polling until workloads load.

    Click model selector
    Wait for listbox visible
    Click first listbox option

Two model selectors should be visible
    [Documentation]    Checks that two model selectors are visible (compare mode).
    ...                Used with Wait Until Keyword Succeeds for polling.

    ${count}=    Get model selector count
    Should Be Equal As Integers    ${count}    2
    ...    msg=Compare mode should show two model selectors

# =============================================================================
# Multi-user / authorization keywords (project membership scenario)
# =============================================================================

A chattable AIM exists in project A
    [Documentation]    Ensures the current test project (project A) has a Running AIM
    ...                deployment ready for chat. Sets the project as project A.
    ...                Sets: ${TEST_AIM_ID}, ${TEST_PROJECT}

    AIM is deployed and running

User Alice has access to project A
    [Documentation]    The kubeconfig-provided user (project member) acts as Alice and
    ...                signs in to AIWB. Project A is selected so subsequent navigation
    ...                resolves the project namespace.

    User is logged in
    Project "${TEST_PROJECT}[name]" is selected

User Bob does not have access to project A
    [Documentation]    Creates a temporary AIRM user that is registered but not added to
    ...                project A's membership. Tracked for suite-teardown cleanup.
    ...                Sets: ${TEST_BOB_EMAIL}, ${TEST_BOB_PASSWORD}

    ${users_endpoint}=    Service API Endpoint    airm    endpoint=users
    ${email}    ${password}    ${user_id}=    Create Temporary Airm User    ${users_endpoint}
    Set Test Variable    ${TEST_BOB_EMAIL}    ${email}
    Set Test Variable    ${TEST_BOB_PASSWORD}    ${password}

Alice sends a chat message to project A's AIM
    [Documentation]    As Alice, opens the chat for project A's AIM and sends a message.

    Navigate to chat page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]
    Wait Until Keyword Succeeds    60s    3s    Open selector and pick first model
    Chat input should be enabled
    Type chat message    Hello, can you tell me what you are?
    Click send button

She receives a streamed reply
    [Documentation]    Verifies the assistant produced a non-empty streamed response.

    ${text}=    Get assistant message text
    ${length}=    Get Length    ${text}
    Should Be True    ${length} > 10
    ...    msg=Expected a streamed assistant reply, got "${text}"

Bob attempts to chat with project A's AIM
    [Documentation]    Switches the browser session to Bob, navigates to project A's chat
    ...                view, and tries to send a message.

    User logs out    ${UI_BASE_URL}
    Log in via Keycloak With Credentials
    ...    ${UI_BASE_URL}    ${TEST_BOB_EMAIL}    ${TEST_BOB_PASSWORD}
    Navigate to chat page with workload    ${UI_BASE_URL}    ${TEST_PROJECT}[name]    ${TEST_AIM_ID}
    Type chat message    Hello, can you tell me what you are?
    Click send button

His request is rejected
    [Documentation]    Verifies the AIWB UI shows the chat-response failure toast,
    ...                indicating Bob's request was not served.

    VAR    ${error_toast}    text="Error fetching chat response. Please try again."
    Wait For Elements State    ${error_toast}    visible    timeout=30s

Clean Up Temporary Users
    [Documentation]    Deletes all temporary AIRM users created during the suite.
    ...                Tolerates partial failures so cleanup runs to completion.

    ${users_endpoint}=    Service API Endpoint    airm    endpoint=users
    Clean Up Temporary Airm Users    ${users_endpoint}
