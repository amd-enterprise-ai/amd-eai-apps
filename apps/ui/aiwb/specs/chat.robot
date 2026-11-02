# Copyright (c) Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for chat with models, inference interaction and image input support.
...
...                 These tests verify chat page navigation, model selection, message
...                 sending with streamed response rendering, and the compare tab for
...                 side-by-side model comparison. All tests require at least one AIM
...                 deployed and running with chat support.
...
...                 These tests also verify that the image attachment UI is available when a
...                 compatible (multimodal) AIM deployment is selected in Chat, and that
...                 images can be attached to messages before sending.
...
...                 Compatibility is determined by workload tags: a deployment tagged
...                 vision, vision-language, image-to-text, image-text-to-text, or
...                 multimodal will show the attachment button; untagged deployments will not.
...
...                 All image-input tests require a running GPU-backed AIM deployment.
...
...                 Suite Efficiency Design:
...                 Uses Suite Teardown for project cleanup. Each test declares its own
...                 preconditions via Given steps. The AIM deployment precondition is
...                 idempotent — first test deploys, subsequent tests reuse.

# UI resources (feature layer + browser setup)
Resource            resources/common/browser_setup.resource
Resource            resources/chat.resource
Resource            resources/workloads.resource

# API resources (infrastructure preconditions, resolved via pythonpath)
Resource            resources/aiwb_aims.resource
Resource            resources/airm_projects.resource

Suite Teardown      Run Keywords    Clean Up Temporary Users    AND    Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
# =============================================================================
# Chat page basic access
# =============================================================================

Chat page is accessible from workload details
    [Documentation]    Verify that a user can reach the Chat page from the workload details
    ...                view. The chat input must be visible after navigation.
    [Tags]    ui    chat    smoke    gpu

    Given a ready project with user access exists
    And AIM is deployed and running
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on AIM details page
    When user navigates to chat from details
    Then chat input should be visible

# =============================================================================
# Image input availability for multimodal deployments
# =============================================================================

Image attachment button is visible for a multimodal AIM deployment
    [Documentation]    Verify that when the selected deployment has a multimodal tag
    ...                (e.g. vision, image-text-to-text), the attachment button appears
    ...                in the chat input, indicating image input is supported.
    [Tags]    ui    chat    gpu

    Given a ready project with user access exists
    And a multimodal AIM is deployed and running
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on chat page with workload "${TEST_AIM_ID}"
    Then image attachment button should be available

Image can be attached to a message for a multimodal deployment
    [Documentation]    Verify that a user can attach an image to a chat message when
    ...                the selected deployment supports image input. After attaching,
    ...                a thumbnail preview appears and the send button becomes enabled.
    [Tags]    ui    chat    gpu

    Given a ready project with user access exists
    And a multimodal AIM is deployed and running
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on chat page with workload "${TEST_AIM_ID}"
    When user attaches image "${CURDIR}/fixtures/test_image.png" to chat
    Then attached image should appear in preview
    And chat input should be ready to send

# =============================================================================
# Chat Page Navigation and Model Selection
# =============================================================================

Chat page shows available models for selection
    [Documentation]    Verify that a logged-in user can navigate to the chat page
    ...                and see deployed models available for selection.
    [Tags]    ui    chat    inference    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And AIM is deployed and running
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user navigates to the chat page
    Then available models should be listed for selection
    And user should be able to select a model

Single deployed model is auto-selected on chat page
    [Documentation]    When exactly one inference deployment is running in the project,
    ...                navigating to the chat page should make the input ready without
    ...                the user manually selecting a model.
    [Tags]    ui    chat    inference    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And AIM is deployed and running
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user navigates to the chat page
    Then chat input should be enabled

Chat model selector shows default model name when no custom deployment name is set
    [Documentation]    Verify the chat model selector shows the model's default name
    ...                for a catalog deployment when the user does not provide a
    ...                custom deployment name.
    [Tags]    ui    chat    inference    display-name    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And AIM is deployed without custom deployment name and running
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user navigates to the chat page
    Then the chat model selector should show default model name when no custom deployment name is set

Chat model selector shows custom deployment name
    [Documentation]    Verify the chat model selector prefers the custom deployment
    ...                name the user provided when creating the deployment.
    [Tags]    ui    chat    inference    display-name    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    ${deploy_name}=    Test Name    chat-deploy
    And AIM is deployed with custom deployment name and running    ${deploy_name}
    When user navigates to the chat page
    Then the chat model selector should offer the deployment labeled "${deploy_name}"

# =============================================================================
# Chat Message and Response Rendering
# =============================================================================

Chat response streams and renders after sending a message
    [Documentation]    Verify that when a user sends a message on the chat page,
    ...                the model response streams and renders in the chat interface.
    [Tags]    ui    chat    inference    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And AIM is deployed and running
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user has selected a model on the chat page
    When user types a message and sends it
    Then response should stream and render in the chat interface

# =============================================================================
# Compare Mode
# =============================================================================

Compare tab shows responses from two models side by side
    [Documentation]    Verify that a user can open the compare tab, select two models,
    ...                send a message, and see responses from both models displayed
    ...                side by side.
    [Tags]    ui    chat    inference    compare    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And AIM is deployed and running
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user has selected a model on the chat page
    When user opens the compare tab and selects two models
    And user sends a message
    Then responses from both models should be displayed side by side

# =============================================================================
# Project membership boundary (multi-user)
# =============================================================================

Chat respects project membership
    [Documentation]    A project member can chat with a chattable AIM in that project;
    ...                a non-member's request is rejected.
    [Tags]    ui    chat    inference    multi-user    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And a chattable AIM exists in project A
    And user Alice has access to project A
    And user Bob does not have access to project A
    When Alice sends a chat message to project A's AIM
    Then she receives a streamed reply
    When Bob attempts to chat with project A's AIM
    Then his request is rejected
