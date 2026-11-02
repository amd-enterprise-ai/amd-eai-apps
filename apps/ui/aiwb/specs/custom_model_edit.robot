# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for editing a custom model.
...
...                 Covers deep-link entry and recovery when the requested model is not
...                 available, happy-path display name edit via the card actions menu,
...                 the duplicate display name advisory warning, and the immutability of
...                 the model's import source.

Resource            resources/common/browser_setup.resource
Resource            resources/custom_model_import.resource
Resource            resources/custom_model_edit.resource
Resource            resources/airm_projects.resource

Suite Teardown      Run Keywords    Clean Up All Created Custom Models    AND    Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Variables ***
${EDIT_UNKNOWN_MODEL_ID}    aiwb-e2e-no-such-custom-model-cr


*** Test Cases ***
Edit deep link for a missing model shows a clear error and a path back to the list
    [Documentation]    When someone opens the edit URL for a model that does not exist,
    ...                the UI explains that loading failed and offers navigation back to
    ...                the Custom Models tab without leaving a broken shell.
    [Tags]    ui    models    custom-models    edit    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    When user opens the custom model edit page for model "${EDIT_UNKNOWN_MODEL_ID}"
    Then the custom model edit page should show the edit title
    And the custom model edit load error should be visible
    When user returns to the custom models list from the edit wizard header
    Then the custom models tab should be shown

Editing a model's runtime profile from Model settings persists the change
    [Documentation]    A user opens Model settings for an onboarded model, revises the runtime
    ...                profile in the edit wizard, and saves. The revised engine argument must
    ...                persist on the model — verified through the API to prove the edit reached
    ...                the backend. The model is onboarded via the API so the wizard has a Ready
    ...                model with an editable runtime profile to load.
    [Tags]    ui    models    custom-models    edit    profile    kubectl

    Given a ready project with user access exists
    And a custom model is onboarded in the project
    And custom model onboarding status should be "Ready"
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user opens the model settings for the onboarded model
    And user advances the edit wizard to the runtime profile step
    Then the runtime profile should be editable
    When user revises the runtime profile engine arguments to "max-model-len: 4096"
    And user saves the model settings
    Then the edited model should carry engine argument "max-model-len" set to "4096"

Editing a custom model display name from the model card saves and returns to the list
    [Documentation]    A user who opens model settings from the card, renames the model,
    ...                and completes the wizard should land back on the Custom Models tab —
    ...                confirming the PATCH succeeded and the UI redirected after saving.
    [Tags]    ui    models    custom-models    edit    smoke

    Given a ready project with user access exists
    And an onboarded custom model exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    When user opens model settings from the custom model card
    And user advances past the source step in edit mode
    And user changes the display name to "Edited TinyLlama"
    And user advances from the information step
    And user submits the import wizard
    Then the custom models tab should be shown
    And a custom model card with display name "Edited TinyLlama" should be shown

Model settings presents the import source as unchangeable
    [Documentation]    A model keeps the source it was onboarded from. Verify the edit wizard
    ...                shows where the model came from but does not let the user repoint it.
    [Tags]    ui    models    custom-models    edit    s3    smoke

    Given a ready project with user access exists
    And an onboarded custom model exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user opens the model settings for the onboarded model
    Then the model source type should be shown as "Hugging Face"
    And the model source should be shown as read only

Duplicate display name warning is shown when editing to a name already used in the project
    [Documentation]    When a user edits a model and types a display name already assigned
    ...                to another model in the same project, the wizard must surface an
    ...                advisory warning — the user is not hard-blocked but is informed of
    ...                the conflict before submitting.
    [Tags]    ui    models    custom-models    edit    smoke

    Given a ready project with user access exists
    And an onboarded model and its copy exist in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    When user opens the custom model edit page for model "${TEST_COPY_MODEL_NAME}"
    And user advances past the source step in edit mode
    And user changes the display name to "${TEST_ORIGINAL_DISPLAY_NAME}"
    Then the duplicate display name warning should be shown
