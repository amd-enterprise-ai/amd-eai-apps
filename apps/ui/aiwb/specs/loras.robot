# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for the project LoRA adapter listing.
Resource            resources/common/browser_setup.resource
Resource            resources/loras.resource
Resource            resources/finetune.resource
Resource            resources/airm_projects.resource
Suite Teardown      Run Keywords
...                 Clean Up All Created Adapter Artifacts
...                 AND
...                 Clean Up All Created Adapter Weights
...                 AND
...                 Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Run Keywords
...                 Close test browser
...                 AND
...                 Remove blocking AIM deployment for adapter if present


*** Test Cases ***
Registered LoRA adapters are listed with compatible base models
    [Documentation]    Verify users can discover registered project adapters and the
    ...                base models with which each adapter is compatible.
    [Tags]    ui    loras    list    smoke

    Given a ready project with user access exists
    And a fine-tuning adapter artifact exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on LoRAs page
    Then LoRA adapters should be listed with their base models
    And the adapter should show no deployments

LoRA adapter usage is shown in the list
    [Documentation]    Verify users can see how many deployments use an adapter.
    [Tags]    ui    loras    list    gpu
    [Teardown]    Run Keywords
    ...    Remove the deployment created by this test
    ...    AND
    ...    Close test browser
    ...    AND
    ...    Remove blocking AIM deployment for adapter if present

    Given a ready project with user access exists
    And the project has adapter-serving quota available
    And an adapter the model can serve exists in the project
    And a running deployment already serving a compatible adapter exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on LoRAs page
    Then the adapter should show one deployment

Running LoRA fine-tuning jobs appear only with LoRA adapters
    [Documentation]    Verify active adapter-output jobs are grouped with LoRA adapters
    ...                rather than fine-tuned models.
    [Tags]    ui    loras    finetune    gpu
    [Teardown]    Run Keywords
    ...    The current fine-tuning job is torn down
    ...    AND
    ...    Close test browser
    ...    AND
    ...    Remove blocking AIM deployment for adapter if present

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2
    And finetuning storage credentials are available to the project
    And finetune dataset exists
    And a LoRA-output fine-tuning job exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on LoRAs page
    Then the running LoRA fine-tuning job should be listed
    When user is on fine-tune models page
    Then the running LoRA fine-tuning job should not be listed

Cancel a running LoRA fine-tuning job
    [Documentation]    Verify users can cancel an active adapter-output job from the LoRAs page.
    [Tags]    ui    loras    finetune    delete    gpu
    [Teardown]    Run Keywords
    ...    The current fine-tuning job is torn down
    ...    AND
    ...    Close test browser
    ...    AND
    ...    Remove blocking AIM deployment for adapter if present

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2
    And finetuning storage credentials are available to the project
    And finetune dataset exists
    And a LoRA-output fine-tuning job exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on LoRAs page
    Then the running LoRA fine-tuning job should be listed
    When user cancels the running LoRA fine-tuning job
    Then the running LoRA fine-tuning job should no longer be listed

User can start fine-tuning from the LoRAs page
    [Documentation]    Verify users can start a new fine-tuning workflow from the LoRAs page.
    [Tags]    ui    loras    finetune    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on LoRAs page
    When user opens fine-tuning wizard from LoRAs page
    Then fine-tuning wizard should be open

User finds a LoRA adapter by search
    [Documentation]    Verify users can narrow the adapter list by name.
    [Tags]    ui    loras    list    search

    Given a ready project with user access exists
    And several registered LoRA adapters exist in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on LoRAs page
    When user searches for a LoRA adapter
    Then only the matching LoRA adapter should be listed

Project without LoRA adapters shows an empty state
    [Documentation]    Verify an empty project communicates that no registered adapters exist.
    [Tags]    ui    loras    list

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on LoRAs page
    Then the registered LoRA adapter list should be empty

User browses a long LoRA adapter list
    [Documentation]    Verify users can move between pages when the registered adapter
    ...                collection exceeds the table page size.
    [Tags]    ui    loras    pagination

    Given a ready project with user access exists
    And the project contains more LoRA adapters than fit on a single page
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on LoRAs page
    Then the LoRAs table should show a full first page
    And LoRAs pagination controls should be visible
    And the user can navigate to the next LoRAs page

Unregistered adapter weights stay hidden
    [Documentation]    Verify users only see adapters registered with the project,
    ...                not unclaimed weight files left in storage.
    [Tags]    ui    loras    list

    Given a ready project with user access exists
    And adapter weights that no artifact claims exist in the project storage
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on LoRAs page
    Then unregistered adapter weights should not be listed

An unready LoRA adapter cannot be attached
    [Documentation]    Verify users cannot attach an adapter until its weights are ready.
    [Tags]    ui    loras    attach    negative

    Given a ready project with user access exists
    And an unready LoRA adapter exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on LoRAs page
    Then the unready adapter should be unavailable for attachment

Adapter deployment requirements are explained when no model is deployed
    [Documentation]    Verify users are told how to make a deployment eligible for an adapter.
    [Tags]    ui    loras    attach    negative

    Given a ready project with user access exists
    And a registered LoRA adapter exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user tries to attach the adapter
    Then the deployment requirements should be explained

Already attached LoRA remains visible but unavailable
    [Documentation]    Verify users can identify an existing attachment without attaching
    ...                the same adapter to that deployment again.
    [Tags]    ui    loras    attach    gpu
    [Teardown]    Run Keywords
    ...    Remove the deployment created by this test
    ...    AND
    ...    Close test browser
    ...    AND
    ...    Remove blocking AIM deployment for adapter if present

    Given a ready project with user access exists
    And the project has adapter-serving quota available
    And an adapter the model can serve exists in the project
    And a running deployment already serving a compatible adapter exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user tries to attach the adapter
    And user opens the deployment choices
    Then the attached deployment should remain visible but unavailable

Incompatible LoRA deployment remains visible but unavailable
    [Documentation]    Verify users can identify a running deployment that cannot accept
    ...                dynamic adapter changes and understand why it is unavailable.
    [Tags]    ui    loras    attach    gpu
    [Teardown]    Run Keywords
    ...    Remove the deployment created by this test
    ...    AND
    ...    Close test browser
    ...    AND
    ...    Remove blocking AIM deployment for adapter if present

    Given a ready project with user access exists
    And the project has adapter-serving quota available
    And an adapter the model can serve exists in the project
    And a running deployment that cannot accept the adapter exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user tries to attach the adapter
    And user opens the deployment choices
    Then the incompatible deployment should remain visible but unavailable

Attaching a LoRA adapter to a deployment updates its usage count
    [Documentation]    Verify users can attach a registered adapter to an eligible running
    ...                deployment and see the attachment reflected in the adapter's usage count.
    [Tags]    ui    loras    attach    gpu
    [Teardown]    Run Keywords
    ...    Remove the deployment created by this test
    ...    AND
    ...    Close test browser
    ...    AND
    ...    Remove blocking AIM deployment for adapter if present

    Given a ready project with user access exists
    And the project has adapter-serving quota available
    And an adapter the model can serve exists in the project
    And an eligible running deployment with no adapters exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user attaches the adapter to that deployment
    Then the attachment should be accepted
    And the adapter usage count should update to reflect the attachment

View a LoRA adapter's details
    [Documentation]    Verify users can inspect the complete registered adapter response.
    [Tags]    ui    loras    details    smoke

    Given a ready project with user access exists
    And a registered LoRA adapter exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user opens the adapter details
    Then the adapter full details should be displayed
Delete an unused LoRA adapter
    [Documentation]    Verify users can confirm deletion and see the adapter removed.
    [Tags]    ui    loras    delete    smoke

    Given a ready project with user access exists
    And a registered LoRA adapter that is not in use exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on LoRAs page
    When user deletes the adapter
    Then the adapter should no longer be listed

User can manually refresh the LoRAs list
    [Documentation]    Verify users can refresh the adapter list to see an adapter registered
    ...                after the page was loaded.
    [Tags]    ui    loras    list

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on LoRAs page
    And the registered LoRA adapter list should be empty
    When a fine-tuning adapter artifact exists in the project
    And user manually refreshes the LoRAs list
    Then LoRA adapters should be listed with their base models

User filters LoRAs by base model
    [Documentation]    Verify users can narrow the adapter list to those compatible with a
    ...                selected base model.
    [Tags]    ui    loras    list    filter

    Given a ready project with user access exists
    And registered LoRA adapters exist with different base models
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on LoRAs page
    When user filters LoRAs by the first adapter's base model
    Then only the adapter with the selected base model should be listed

Deletion is unavailable for a LoRA adapter that is in use
    [Documentation]    Verify users cannot delete an adapter used by a running deployment.
    [Tags]    ui    loras    delete    negative    gpu
    [Teardown]    Run Keywords
    ...    Remove the deployment created by this test
    ...    AND
    ...    Close test browser
    ...    AND
    ...    Remove blocking AIM deployment for adapter if present

    Given a ready project with user access exists
    And the project has adapter-serving quota available
    And an adapter the model can serve exists in the project
    And a running deployment already serving a compatible adapter exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on LoRAs page
    When user opens the adapter actions
    Then the adapter delete action should be disabled

Deleting a LoRA adapter that is in use is refused with an explanation
    [Documentation]    Verify deletion of an adapter referenced by a deployment is refused and
    ...                names the deployment, even when that deployment is not running -- the
    ...                backend blocks the delete for any reference, not only a running one.
    [Tags]    ui    loras    delete    negative    kubectl

    Given a ready project with user access exists
    And a registered LoRA adapter in use by a deployment exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on LoRAs page
    When user attempts to delete the adapter
    Then the deletion should be blocked with an explanation of what is using it

Dynamic LoRA deployment shows its profile on the dashboard
    [Documentation]    Verify users can see both the resolved profile and adapter capacity
    ...                for a deployment with dynamic LoRA support.
    [Tags]    ui    loras    deploy    gpu
    [Teardown]    Run Keywords
    ...    Remove AIM deployment if present
    ...    AND
    ...    Close test browser
    ...    AND
    ...    Remove blocking AIM deployment for adapter if present

    Given a ready project with user access exists
    And the project has GPU quota available
    And an AIM exists in system
    And a dynamic LoRA deployment exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user views project deployments
    Then the dynamic LoRA deployment should describe its profile and adapter capacity
