# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for the LoRA adapter picker.
...                 A model groups several variants, and the variants differ in the base weights
...                 they load. Only adapters trained against weights a variant actually provides
...                 can be served, so only those may be offered.
Resource            resources/common/browser_setup.resource
Resource            resources/loras.resource
Resource            resources/airm_projects.resource
Suite Teardown      Run Keywords
...                     Clean Up All Created Adapter Artifacts
...                     AND    Clean Up All Created Adapter Weights
...                     AND    Clean Up All Created Projects With Wait
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
An adapter that no available variant of the model can serve is not offered
    [Documentation]    A user setting up a deployment is not offered an adapter that none of the
    ...    model's available variants can load. Offering one produces a deployment the engine
    ...    refuses at startup, which the user only discovers once the service fails to serve.
    [Tags]    ui    loras    aims    adapters    deploy

    Given a ready project with user access exists
    And an adapter-capable AIM exists in system
    And an adapter an available variant of the model can serve exists in the project
    And an adapter no available variant of the model can serve exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user sets up a deployment of that model on the hardware that adapter was trained for
    And user chooses adapters for that deployment
    Then that adapter should not be offered

An adapter that a servable variant can serve is offered and deploys
    [Documentation]    An adapter a servable variant can load stays offered, and choosing it
    ...    produces a deployment that starts and serves it.
    [Tags]    ui    loras    aims    adapters    deploy    gpu
    [Teardown]    Run Keywords
    ...    Remove the deployment created by this test
    ...    AND    Close test browser

    Given a ready project with user access exists
    And the project has adapter-serving quota available
    And an adapter an available variant of the model can serve exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user sets up a deployment of that model on the hardware that adapter was trained for
    And user chooses adapters for that deployment
    Then the adapter should be offered
    When user attaches that adapter and deploys the model
    Then the deployment should start and serve the adapter

Attaching to an existing deployment offers only adapters that deployment can serve
    [Documentation]    The same lineage rule governs attaching to a deployment that is already
    ...    running, where the weights it loaded are settled rather than still to be resolved.
    [Tags]    ui    loras    aims    workloads    adapters    gpu
    [Teardown]    Run Keywords
    ...    Remove the deployment created by this test
    ...    AND    Close test browser

    Given a ready project with user access exists
    And the project has adapter-serving quota available
    And an adapter an available variant of the model can serve exists in the project
    And an adapter no available variant of the model can serve exists in the project
    And an eligible running deployment with no adapters exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user looks for adapters to attach to that deployment
    Then only adapters that deployment can serve should be offered
