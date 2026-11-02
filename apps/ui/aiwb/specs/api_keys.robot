# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for API key lifecycle in AIWB UI.
...
...                 Tests cover the full API key lifecycle: page navigation, creation,
...                 table verification, clipboard copy, and deletion.
...
...                 Suite Efficiency Design:
...                 Uses Suite Setup/Teardown for project tracking and cleanup. Each test declares
...                 its own preconditions via Given steps (idempotent - first test creates, subsequent
...                 tests reuse). Tests are ordered to allow key reuse where possible, but each test
...                 is independently runnable.

# UI resources (feature layer + browser setup)
Resource            resources/common/browser_setup.resource
Resource            resources/api_keys.resource

# API resources (infrastructure preconditions, resolved via pythonpath)
Resource            resources/airm_projects.resource
Resource            resources/aims/api_keys.resource

Suite Setup         Initialize API Key Suite
Suite Teardown      Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Variables ***
${TEST_API_KEY_NAME}    ${EMPTY}


*** Test Cases ***
API keys page loads with expected elements
    [Documentation]    Verify that the API keys page loads and displays the page heading
    ...                and the create button.
    [Tags]    ui    api-keys    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on API keys page
    Then API keys page should be visible
    And create API key button should be visible

Create API key through UI
    [Documentation]    Verify that a new API key can be created via the UI form.
    ...                After creation, the key created drawer should appear showing the
    ...                generated key value.
    [Tags]    ui    api-keys    create

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on API keys page
    When user creates API key "${TEST_API_KEY_NAME}"
    Then key created drawer should be visible
    And copy API key button should be visible

API key appears in table after creation
    [Documentation]    Verify that after creating an API key and closing the drawer,
    ...                the key name is visible in the API keys table.
    [Tags]    ui    api-keys    list

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on API keys page
    And user creates API key "${TEST_API_KEY_NAME}-list"
    And user closes key created drawer
    Then API key "${TEST_API_KEY_NAME}-list" should be visible in table

Copy API key button is clickable after creation
    [Documentation]    Verify that the copy button in the key created drawer is clickable.
    ...                Note: In headless Playwright, clipboard access may not work due to
    ...                browser security restrictions. This test verifies the button is present
    ...                and can be clicked without errors.
    [Tags]    ui    api-keys    clipboard

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on API keys page
    When user creates API key "${TEST_API_KEY_NAME}-copy"
    Then copy API key button should be visible
    And user clicks copy API key button

Delete API key through UI
    [Documentation]    Verify that an API key can be deleted via the actions menu.
    ...                Creates a key first, then deletes it and verifies removal from the table.
    [Tags]    ui    api-keys    delete

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on API keys page
    And user creates API key "${TEST_API_KEY_NAME}-delete"
    And user closes key created drawer
    And API key "${TEST_API_KEY_NAME}-delete" should be visible in table
    When user deletes API key "${TEST_API_KEY_NAME}-delete"
    Then API key deleted successfully toast should appear
    And API key "${TEST_API_KEY_NAME}-delete" should not be visible in table

Edit API key drawer shows linked model deployments
    [Documentation]    Verify that the Edit API Key drawer correctly shows the model
    ...                deployments already associated with the key, without requiring
    ...                the user to reopen the drawer.
    [Tags]    ui    api-keys    edit    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And an AIM model is running with api key
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on API keys page
    When user opens edit drawer for API key "${TEST_API_KEY}[displayName]"
    Then edit drawer should show linked deployment "${TEST_AIM_NAME}"

Deselecting all model deployments in edit drawer clears API key access
    [Documentation]    Verify that removing every linked model deployment from an API key
    ...                through the edit drawer clears its access, both in the UI and via
    ...                the underlying API bindings.
    [Tags]    ui    api-keys    edit    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And an AIM model is running with api key
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on API keys page
    And user opens edit drawer for API key "${TEST_API_KEY}[displayName]"
    When user deselects model deployment "${TEST_AIM_NAME}" in edit drawer
    And user saves API key edit
    And user opens edit drawer for API key "${TEST_API_KEY}[displayName]"
    Then edit drawer should show no linked deployments
    And Api key should have no model bindings

Deselecting one of several model deployments in edit drawer keeps the others linked
    [Documentation]    Verify that removing one of several linked model deployments from an
    ...                API key through the edit drawer keeps the remaining deployments linked,
    ...                both in the UI and via the underlying API bindings.
    [Tags]    ui    api-keys    edit    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And an AIM model is running with api key
    And a second AIM model is running
    And the API key is also linked to the second AIM model
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on API keys page
    And user opens edit drawer for API key "${TEST_API_KEY}[displayName]"
    When user deselects model deployment "${TEST_AIM_NAME}" in edit drawer
    And user saves API key edit
    And user opens edit drawer for API key "${TEST_API_KEY}[displayName]"
    Then edit drawer should show linked deployment "${TEST_AIM_B_NAME}"
    And edit drawer should not show linked deployment "${TEST_AIM_NAME}"
    And Api key should be bound to AIM "${TEST_AIM_B_ID}"
