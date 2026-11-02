# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for LoRA adapter deployment details.
Resource            resources/common/browser_setup.resource
Resource            resources/workloads.resource
Resource            resources/loras.resource
Resource            resources/aiwb_adapter_serving.resource
Resource            resources/airm_projects.resource
Suite Teardown      Run Keywords
...                     Clean Up All Created Adapter Artifacts
...                     AND    Clean Up All Created Adapter Weights
...                     AND    Clean Up All Created Projects With Wait
Test Setup          Open test browser
Test Teardown       Run Keywords
...                     Remove the deployment created by this test
...                     AND    Close test browser


*** Test Cases ***
Deployment LoRA adapters can be reviewed, replaced, and removed
    [Documentation]    A user can identify an attached adapter, replace it with another compatible
    ...    adapter, and clear the deployment's adapter selection.
    [Tags]    ui    loras    aims    workloads    adapters    details    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And an adapter-capable AIM exists in system
    And an adapter the model can serve exists in the project
    And another adapter the model can serve exists in the project
    And the model is deployed with a compatible adapter and a maximum LoRA rank
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on AIM details page
    Then LoRA adapters should be listed with their supported ranks
    When user replaces the attached LoRA with another compatible LoRA
    Then deployment should show only the replacement LoRA
    When user removes all attached LoRAs
    Then deployment should show no attached LoRAs

Deploy wizard applies the selected maximum LoRA rank
    [Documentation]    A user can enable dynamic adapters, select a rank, and see that
    ...    selected capacity reflected on the resulting deployment.
    [Tags]    ui    loras    aims    deploy    gpu

    Given a ready project with user access exists
    And the project has adapter-serving quota available
    And an adapter the model can serve exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user deploys the model with dynamic LoRA adapters and maximum rank "64"
    Then the deployment should show maximum LoRA rank "64"
