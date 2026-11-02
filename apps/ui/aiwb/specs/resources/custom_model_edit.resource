# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for the custom model edit wizard (deep link and recovery).
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)

Resource            common/session.resource
Resource            pages/models_page.resource
Resource            resources/aiwb_custom_models.resource


*** Keywords ***
# =============================================================================
# Given keywords (preconditions)
# =============================================================================

An onboarded custom model exists in the project
    [Documentation]    Previews and onboards the public test fixture so UI edit
    ...                scenarios have a model to open in the edit wizard.

    A custom model is onboarded in the project

An onboarded model and its copy exist in the project
    [Documentation]    Onboards the public fixture, renames it to a known display name,
    ...                then copies it — leaving two models in the project.
    ...                Sets ${TEST_ORIGINAL_DISPLAY_NAME} and ${TEST_COPY_MODEL_NAME}
    ...                so tests can reference each model by role.

    A custom model is onboarded in the project
    The user updates the model display name to "E2E Original Model"
    VAR    ${TEST_ORIGINAL_DISPLAY_NAME}    E2E Original Model    scope=TEST
    A copy of the onboarded custom model is created in the project

# =============================================================================
# When keywords (actions)
# =============================================================================

User opens the custom model edit page for model "${model_id}"
    [Documentation]    Deep-links to the edit wizard for the given AIMModel CR name.
    ...                Used when bookmarks or support links carry a stable model id.

    Navigate to custom model edit page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]    ${model_id}

User opens the model settings for the onboarded model
    [Documentation]    Deep-links to the edit wizard for the model onboarded in this test
    ...                (``TEST_CUSTOM_MODEL_NAME``), the same destination the "Model settings"
    ...                card action opens.

    Navigate to custom model edit page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]    ${TEST_CUSTOM_MODEL_NAME}

User advances the edit wizard to the runtime profile step
    [Documentation]    Steps the loaded edit wizard from the source step through the information
    ...                step to the runtime profile step.

    Click import wizard next on source step
    Click import wizard next on information step
    Wait for runtime profile step

User revises the runtime profile engine arguments to "${engine_args_yaml}"
    [Documentation]    Replaces the engine-arguments YAML in the runtime profile step.

    Fill runtime profile engine arguments    ${engine_args_yaml}

User saves the model settings
    [Documentation]    Submits the edit wizard's runtime step to persist the revised profile.

    Submit import wizard runtime step

User opens model settings from the custom model card
    [Documentation]    Opens the card actions menu on the first visible model card
    ...                and selects "Model settings" to navigate to the edit wizard.

    Click actions menu on first custom model card
    Click model settings action in custom model card menu

User advances past the source step in edit mode
    [Documentation]    In edit mode the source step shows the model source as read-only
    ...                with no preview call. Waits for the wizard to finish mounting
    ...                after navigation, then clicks Next.

    Click import wizard next on source step in edit mode

User changes the display name to "${new_name}"
    [Documentation]    Replaces the current value in the display name field with the
    ...                given name on the information step.

    Fill import wizard display name    ${new_name}

User returns to the custom models list from the edit wizard header
    [Documentation]    Uses the header back control shared with the import wizard.

    Click import wizard header back

# =============================================================================
# Then keywords (verification)
# =============================================================================

The model source should be shown as read only
    [Documentation]    Confirms the source cannot be retyped in the edit wizard because
    ...                the onboarded model keeps its original source reference.

    Import wizard source input should be read only

The model source type should be shown as "${label}"
    [Documentation]    Confirms the edit wizard names the family the model was imported from
    ...                instead of offering the source-type choice again.

    Import wizard source type field should read    ${label}

The custom model edit page should show the edit title
    [Documentation]    Confirms the shell is in edit mode (not the import flow).

    Custom model edit page should show edit title

The custom model edit load error should be visible
    [Documentation]    Confirms the user-visible failure state when the model cannot be loaded.

    Wait for custom model edit load error

The runtime profile should be editable
    [Documentation]    Confirms the runtime profile step is editable for a Ready model — the
    ...                "becomes editable once onboarding finishes" notice must be absent.

    Runtime profile step should be editable

A custom model card with display name "${name}" should be shown
    [Documentation]    Confirms the renamed model card is visible on the Custom Models tab
    ...                after the edit wizard redirects back, verifying the display name
    ...                change persisted and the list reflects it.

    Custom model card with text "${name}" should be visible

The edited model should carry engine argument "${arg_key}" set to "${arg_value}"
    [Documentation]    Reads the model's persisted runtime overrides via the API to prove the
    ...                edit wizard saved the revised value, not just rendered it. Polled because
    ...                the save writes the AIMModel and its derived AIMProfile under one lock.

    Wait Until Keyword Succeeds    60 sec    5 sec
    ...    Edited model overrides should carry engine argument    ${arg_key}    ${arg_value}

Edited model overrides should carry engine argument
    [Documentation]    Single-poll helper: the model's ``engineArgs`` override carries the value.
    [Arguments]    ${arg_key}    ${arg_value}
    ${overrides}=    Get onboarded model overrides
    ${args}=    Get From Dictionary    ${overrides}    engineArgs    default=&{EMPTY}
    Should Be Equal As Strings    ${args}[${arg_key}]    ${arg_value}
    ...    msg=Edited runtime profile engine argument '${arg_key}' was not persisted on the model
