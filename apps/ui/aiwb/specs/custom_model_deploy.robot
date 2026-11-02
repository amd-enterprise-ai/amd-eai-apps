# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for deploying and undeploying a custom model.
...
...                 Covers the deploy drawer entry point from the Custom Models tab card,
...                 the full deploy → Deployed Models list → undeploy confirmation flow,
...                 and a GPU-free smoke check that verifies the drawer renders correctly
...                 for a Ready model without submitting.

Resource            resources/common/browser_setup.resource
Resource            resources/custom_model_deploy.resource
Resource            resources/chat.resource
Resource            resources/api_keys.resource
Resource            resources/workloads.resource
Resource            resources/airm_projects.resource
Resource            resources/airm_secrets.resource

Suite Teardown      Run Keywords    Clean Up All Created Custom Models    AND    Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
Deploy drawer opens with deployment settings for a Ready custom model
    [Documentation]    A user who clicks the Deploy button on a Ready model card should
    ...                see the deploy drawer with a display name input and an autoscaling
    ...                toggle — confirming the drawer rendered correctly without submitting
    ...                an actual deployment. The button is disabled for non-Ready models
    ...                so the Ready precondition is what gates the interaction.
    [Tags]    ui    models    custom-models    deploy    smoke

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a ready custom model exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the custom models tab
    When user opens the deploy drawer from the custom model card
    Then the deploy drawer should show deployment settings

Deploy drawer offers a profile to deploy with and describes what it runs
    [Documentation]    A user opening the deploy drawer for a Ready custom model should be able
    ...                to choose which of the model's profiles to deploy with, and see what the
    ...                current choice will run, without submitting a deployment.
    [Tags]    ui    models    custom-models    deploy    profile    smoke

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a ready custom model exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the custom models tab
    When user opens the deploy drawer from the custom model card
    Then the deploy drawer should offer a profile and describe what it runs

Deploying a custom model with a profile chosen in the drawer serves that profile
    [Documentation]    A user who picks one of the model's profiles in the deploy drawer and
    ...                submits should get a deployment serving that profile rather than the
    ...                model's Default.
    [Tags]    ui    models    custom-models    deploy    profile    gpu
    [Teardown]    Clean up custom model deployment if present

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a ready custom model exists in the project
    And the model has another profile that is ready to serve
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the custom models tab
    ${deploy_name}=    Test Name    ui-deploy-profile
    When user opens the deploy drawer from the custom model card
    And user chooses the profile they added
    And user fills the deployment display name "${deploy_name}"
    And user submits the deployment form
    Then the model deployment success toast should be shown
    And the deployment should serve the profile the user chose in the drawer
    And the deployed model "${deploy_name}" should describe the profile it runs

A deployed custom model can be chatted with from the chat page
    [Documentation]    A user who has a Ready custom model deployed and running can navigate
    ...                to the chat page for that deployment, send a message, and receive a
    ...                streamed response — confirming the inference endpoint is reachable
    ...                from the UI and the model processes input end-to-end.
    [Tags]    ui    models    custom-models    deploy    chat    gpu
    [Teardown]    Clean up custom model deployment if present

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a custom model is deployed and running in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on the chat page for the custom model deployment
    And user types a message and sends it
    Then response should stream and render in the chat interface

Deploying a custom model from the card and undeploying it from the Deployed Models tab
    [Documentation]    A user who opens the deploy drawer for a Ready custom model,
    ...                supplies a display name, and submits should see a success toast
    ...                and find the new deployment on the Deployed Models tab. Undeploying
    ...                it from there should show a confirmation modal, then a success toast,
    ...                and the entry should disappear from the list.
    [Tags]    ui    models    custom-models    deploy    undeploy    gpu
    [Teardown]    Clean up custom model deployment if present

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And a ready custom model exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the custom models tab
    ${deploy_name}=    Test Name    ui-deploy
    When user opens the deploy drawer from the custom model card
    And user fills the deployment display name "${deploy_name}"
    And user submits the deployment form
    Then the model deployment success toast should be shown
    When user is on the deployed models page
    Then a deployed model with display name "${deploy_name}" should appear in the list
    When user opens the undeploy action for the deployment with display name "${deploy_name}"
    And user confirms the undeploy
    Then the undeploy success toast should be shown
    And the deployed model should no longer appear in the list with display name "${deploy_name}"

Two deployments of one custom model are named by their distinct profiles in the pickers
    [Documentation]    Two running deployments of one custom model, each on a different profile,
    ...                must each be offered under its own profile name — not a shared "Default" —
    ...                everywhere a deployment is picked, so they can be told apart. Checks the
    ...                chat model selector, the API key creation deployment picker, and the
    ...                dashboard workloads table, and asserts each profile's label independently.
    [Tags]    ui    models    custom-models    deploy    profile    chat    api-keys    dashboard    gpu
    [Teardown]    Clean up custom model deployment if present

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And two custom model deployments run on different profiles
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on chat page
    Then the chat model selector should offer the deployment labeled "${TEST_PROFILE_LABEL_A}"
    And the chat model selector should offer the deployment labeled "${TEST_PROFILE_LABEL_B}"
    When user is on API keys page
    Then the API key deployment picker should offer the deployment labeled "${TEST_PROFILE_LABEL_A}"
    And the API key deployment picker should offer the deployment labeled "${TEST_PROFILE_LABEL_B}"
    When user is on workloads page
    Then the dashboard workloads table should offer the deployment labeled "${TEST_PROFILE_LABEL_A}"
    And the dashboard workloads table should offer the deployment labeled "${TEST_PROFILE_LABEL_B}"
