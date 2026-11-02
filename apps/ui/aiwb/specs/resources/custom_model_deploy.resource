# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for custom model deploy and undeploy scenarios.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)

Resource            common/session.resource
Resource            pages/models_page.resource
Resource            pages/chat_page.resource
Resource            resources/aiwb_custom_models.resource


*** Keywords ***
# =============================================================================
# Given keywords (preconditions)
# =============================================================================

A ready custom model exists in the project
    [Documentation]    Onboards the public test fixture via the API and polls until the
    ...                onboarding phase reaches Ready so the model is deployable. UI tests
    ...                that click the Deploy button require this state.

    A custom model is onboarded in the project
    Custom model onboarding status should be "Ready"

A custom model is deployed and running in the project
    [Documentation]    Onboards the public test fixture, waits for Ready, deploys it as an
    ...                AIMService via the API, and waits for Running state. Use this as the
    ...                Given precondition for tests that exercise a live inference endpoint
    ...                (e.g. chat) rather than tests that only need the Deploy button enabled.
    ...                GPU quota is set before deploying so Kueue does not suspend the workload.
    ...                Sets: TEST_CUSTOM_MODEL_NAME, TEST_AIM_ID

    A custom model is onboarded in the project
    Custom model onboarding status should be "Ready"
    Project quota is set to    gpu_count=2
    Custom model is deployed as an AIM service
    Deployed AIM reaches Running state

Two custom model deployments run on different profiles
    [Documentation]    Onboards the fixture, adds two named profiles, then deploys and runs each
    ...                under its own profile. The project ends with two live deployments of one
    ...                model whose only difference is their profile — so the pickers must tell
    ...                them apart by label, not by their (identical) hardware. Quota covers both
    ...                single-model deployments at the profiles' accelerator count.
    ...                Sets: TEST_CUSTOM_MODEL_NAME, TEST_PROFILE_LABEL_A, TEST_PROFILE_LABEL_B.

    A custom model is onboarded in the project
    Custom model onboarding status should be "Ready"
    The onboarded model's Default profile is ready
    ${label_a}=    Test Name    ui-profile-a
    The user adds a profile named "${label_a}" to the onboarded custom model
    The profile the user added is ready to serve
    VAR    ${TEST_PROFILE_LABEL_A}    ${label_a}    scope=TEST
    VAR    ${profile_a}    ${TEST_SELECTED_PROFILE}    scope=TEST
    ${label_b}=    Test Name    ui-profile-b
    The user adds a profile named "${label_b}" to the onboarded custom model
    The profile the user added is ready to serve
    VAR    ${TEST_PROFILE_LABEL_B}    ${label_b}    scope=TEST
    VAR    ${profile_b}    ${TEST_SELECTED_PROFILE}    scope=TEST
    ${gpu_quota}=    Evaluate    2 * ${TEST_PROFILE_ACCELERATOR_COUNT}
    Project quota is set to    gpu_count=${gpu_quota}
    Custom model is deployed and running on profile "${profile_a}"
    Custom model is deployed and running on profile "${profile_b}"

User is on the chat page for the custom model deployment
    [Documentation]    Navigates to the chat page with the running custom model deployment
    ...                pre-selected, then polls until the chat input is enabled — confirming
    ...                the inference endpoint is actually serving requests before the test
    ...                types its first message. The API can report Running before the engine
    ...                is warm, so this extra wait prevents false failures on the send step.

    Navigate to chat page with workload    ${UI_BASE_URL}    ${TEST_PROJECT}[name]    ${TEST_AIM_ID}
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Custom model chat input should be enabled

Custom model chat input should be enabled
    [Documentation]    Single-poll helper: asserts the chat textarea is not disabled.
    ...                Used inside Wait Until Keyword Succeeds to retry until the endpoint warms up.

    ${disabled}=    Get chat input disabled state
    Should Not Be True    ${disabled}
    ...    msg=Chat input is still disabled — inference endpoint may still be warming up

The model has another profile that is ready to serve
    [Documentation]    Adds a second profile through the API and waits until it can serve, so
    ...                the deploy drawer has a real alternative to the model's Default to offer.
    ...                Sets: TEST_CREATED_PROFILE_NAME (the label shown in the drawer) and
    ...                TEST_SELECTED_PROFILE (the identifier the deploy is checked against).

    The onboarded model's Default profile is ready
    ${profile_name}=    Test Name    ui-profile
    The user adds a profile named "${profile_name}" to the onboarded custom model
    The profile the user added is ready to serve

User is on the custom models tab
    [Documentation]    Navigates to the Custom Models tab of the models page.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to custom models page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

User is on the deployed models page
    [Documentation]    Navigates directly to the Deployed Models tab.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to deployed models page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

# =============================================================================
# When keywords (actions)
# =============================================================================

User opens the deploy drawer from the custom model card
    [Documentation]    Clicks the Deploy button on the first custom model card to open
    ...                the deploy drawer. The button becomes enabled once the model reaches
    ...                Ready state — a precondition must guarantee that before this step.

    Click deploy button on custom model card

User fills the deployment display name "${name}"
    [Documentation]    Types the given display name into the deploy drawer's name input.

    Wait For Elements State    ${CUSTOM_DEPLOY_DISPLAY_NAME_INPUT}    visible    timeout=10s
    Fill Text    ${CUSTOM_DEPLOY_DISPLAY_NAME_INPUT}    ${name}

User chooses the profile they added
    [Documentation]    Picks the added profile in the deploy drawer, by the label it was
    ...                created with.

    Choose deploy drawer profile named "${TEST_CREATED_PROFILE_NAME}"

User submits the deployment form
    [Documentation]    Clicks the Deploy confirm button in the drawer footer to submit the
    ...                deploy request. Waits for the button to be enabled before clicking.

    Submit custom model deploy drawer

User opens the undeploy action for the deployment with display name "${name}"
    [Documentation]    Opens the row-actions menu for the deployed model entry with the
    ...                given display name and selects Undeploy to open the confirmation modal.

    Click undeploy action for deployed model with display name "${name}"

User confirms the undeploy
    [Documentation]    Clicks the confirm button in the undeploy confirmation modal to
    ...                proceed with the undeploy.

    Undeploy confirmation modal should be visible
    Confirm model undeploy in modal

# =============================================================================
# Then keywords (verification)
# =============================================================================

The deploy drawer should show deployment settings
    [Documentation]    Confirms the deploy drawer is open and exposes the display name
    ...                input and autoscaling toggle, verifying the form rendered correctly.

    Wait for custom model deploy drawer
    Deploy drawer should show display name input
    Deploy drawer should show autoscaling toggle

The deploy drawer should offer a profile and describe what it runs
    [Documentation]    Confirms the drawer lets the user choose which profile to deploy with,
    ...                and shows what the current choice will run so the choice can be checked
    ...                before submitting.

    Wait for custom model deploy drawer
    Deploy drawer should show profile selector
    Deploy drawer should show profile information

The deployment should serve the profile the user chose in the drawer
    [Documentation]    The deployment the drawer created must serve the profile that was picked
    ...                in it, rather than the model's Default.

    ${service_id}=    Wait Until Keyword Succeeds    1 min    5 sec
    ...    Id of the AIM service deployed for the custom model
    VAR    ${TEST_AIM_ID}    ${service_id}    scope=TEST
    The deployment should serve the profile identified by    ${TEST_SELECTED_PROFILE}

Id of the AIM service deployed for the custom model
    [Documentation]    Single-poll helper: finds the deployment the browser flow created for
    ...                the model this test onboarded. Matched on the model it serves because
    ...                the browser never sees the id, and this test deploys the model once.

    ${namespace}=    Get Project Namespace
    ${response}=    List AIM Services    ${namespace}    expected_status=200
    ${services}=    Get From Dictionary    ${response.json()}    data    default=@{EMPTY}
    FOR    ${svc}    IN    @{services}
        ${spec}=    Get From Dictionary    ${svc}    spec    default=&{EMPTY}
        ${model_obj}=    Get From Dictionary    ${spec}    model    default=&{EMPTY}
        ${svc_model}=    Get From Dictionary    ${model_obj}    name    default=${EMPTY}
        IF    "${svc_model}" == "${TEST_CUSTOM_MODEL_NAME}"
            RETURN    ${svc}[id]
        END
    END
    Fail    No deployment found for custom model ${TEST_CUSTOM_MODEL_NAME}

The model deployment success toast should be shown
    [Documentation]    Confirms the success feedback appears after the deploy form is
    ...                submitted — the toast text is "Model deployment started".

    Custom model deploy success toast should be shown

A deployed model with display name "${name}" should appear in the list
    [Documentation]    Confirms a row for the given display name appears in the Deployed
    ...                Models table. The row is visible as soon as the AIMService CR is
    ...                created, before the deployment reaches Running state.

    Deployed models table should contain a model with display name "${name}"

The deployed model "${name}" should describe the profile it runs
    [Documentation]    The deployed row's second line describes the running profile's hardware
    ...                the same way cluster-catalog models do — its accelerator model, count, and
    ...                precision — rather than leaving the line blank for a custom model. Reads
    ...                the axes recorded when the chosen profile became ready. The line fills in
    ...                asynchronously once the deployment's profile resolves, so this polls.
    ...                Requires TEST_PROFILE_* from "The model has another profile that is ready
    ...                to serve".

    Navigate to deployed models page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]
    Wait Until Keyword Succeeds    30s    3s
    ...    Deployed model row for "${name}" shows the chosen profile's settings

Deployed model row for "${name}" shows the chosen profile's settings
    [Documentation]    Single-poll helper: asserts the deployed row shows the chosen profile's
    ...                accelerator model, accelerator count, and precision. Accelerator model and
    ...                precision render verbatim; the count renders as "Nx" (GPU or CPU).

    ${text}=    Get deployed model row text    ${name}
    Should Contain    ${text}    ${TEST_PROFILE_ACCELERATOR_MODEL}
    ...    msg=Deployed row does not show accelerator model ${TEST_PROFILE_ACCELERATOR_MODEL}: ${text}
    Should Contain    ${text}    ${TEST_PROFILE_PRECISION}
    ...    msg=Deployed row does not show precision ${TEST_PROFILE_PRECISION}: ${text}
    Should Contain    ${text}    ${TEST_PROFILE_ACCELERATOR_COUNT}x
    ...    msg=Deployed row does not show accelerator count ${TEST_PROFILE_ACCELERATOR_COUNT}x: ${text}

The undeploy success toast should be shown
    [Documentation]    Confirms the "Workload deletion started" toast appears after the undeploy
    ...                is confirmed. The message signals async initiation, not completion.

    Undeploy success toast should be shown

The deployed model should no longer appear in the list with display name "${name}"
    [Documentation]    Confirms the row for the given display name is gone from the
    ...                Deployed Models table after undeploy completes.

    Deployed models table should not contain a model with display name "${name}"

# =============================================================================
# Teardown helpers
# =============================================================================

Clean up custom model deployment if present
    [Documentation]    Idempotent test teardown: scans the project for any AIMService whose
    ...                spec.model matches the model onboarded in this test and deletes it.
    ...                Runs after the test body so a mid-test failure cannot leave an
    ...                AIMService behind when the browser-based undeploy step did not
    ...                execute. Tolerates every failure — teardown must never mask the
    ...                actual test result.
    ${model_name}=    Get Variable Value    ${TEST_CUSTOM_MODEL_NAME}    ${None}
    IF    $model_name is None    RETURN
    ${namespace}=    Get Variable Value    ${TEST_PROJECT}    ${None}
    IF    $namespace is None    RETURN
    ${ns}=    Get From Dictionary    ${namespace}    name
    ${response}=    List AIM Services    ${ns}    expected_status=any
    IF    ${response.status_code} != 200    RETURN
    ${services}=    Get From Dictionary    ${response.json()}    data    default=@{EMPTY}
    FOR    ${svc}    IN    @{services}
        ${spec}=    Get From Dictionary    ${svc}    spec    default=&{EMPTY}
        ${model_obj}=    Get From Dictionary    ${spec}    model    default=&{EMPTY}
        ${svc_model}=    Get From Dictionary    ${model_obj}    name    default=${EMPTY}
        IF    "${svc_model}" == "${model_name}"
            ${svc_id}=    Get From Dictionary    ${svc}    id
            Undeploy AIM    ${svc_id}    ${ns}    expected_status=any
        END
    END
