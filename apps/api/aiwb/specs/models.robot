# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for AIM model API endpoints.
...                 Verifies model listing, retrieval, deletion, and error handling.
...
...                 IMPORTANT: Models are created through finetuning workflows (see finetuning.robot),
...                 not through direct POST /v1/models endpoint (which was removed from the API).
...                 The delete endpoint uses the AIMModel CR name (not a DB UUID).
...                 Pre-created AIMModel CRs via kubectl are used for CPU tests.
Resource    resources/airm_keywords.resource
Resource    resources/airm_projects.resource
Resource    resources/aiwb_models.resource
Resource    resources/aiwb_finetuning_recipes.resource
Resource    resources/aiwb_test_data.resource
Resource    resources/api/common.resource
Test Teardown       Clean Up All Created Models


*** Test Cases ***
AIM model appears in namespace model list
    [Documentation]    Verify that an AIM model appears in the namespace model list.
    [Tags]    models    list    cpu

    Given Project exists in system
    And a dummy AIMModel CR exists in the namespace

    Then the dummy AIMModel should appear in the namespace model list

AIM model is retrievable by resource name
    [Documentation]    Verify that an AIM model can be retrieved by resource name.
    [Tags]    models    get    cpu

    Given Project exists in system
    And a dummy AIMModel CR exists in the namespace

    Then the dummy AIMModel should be retrievable by resource name

Requesting a non-existent AIM model returns not-found error
    [Documentation]    Verify that requesting a non-existent model by resource name returns 404.
    [Tags]    models    error    cpu

    Given Project exists in system

    Then getting a non-existent model should return 404

Finetunable models include GPU hardware compatibility information
    [Documentation]    Verify finetunable models are returned with GPU hardware details
    ...    so users can identify which models are compatible with their cluster's accelerators.
    [Tags]    models    finetunable    smoke

    Given Project exists in system
    When finetunable models list is requested
    Then each finetunable model should include GPU hardware compatibility details

Every recipe that supports the cluster's GPUs is offered for fine-tuning
    [Documentation]    Verify every registered recipe for a model the cluster can serve, on GPUs the
    ...    cluster has, is offered as a fine-tuning base model however it writes the GPU ID, such as
    ...    ``0x75a8`` against a ``75a8`` node label. Recipes come from an external repository that
    ...    uses both notations, and a mismatch silently hides the model from every user on that
    ...    hardware.
    [Tags]    models    finetunable    requires-gpu    needs-aim-images

    Given Project exists in system
    And the cluster has fine-tuning recipes for models it can serve on its GPUs
    When finetunable models list is requested
    Then every recipe that supports the cluster's GPUs should be offered as a base model

Finetunable models report Hugging Face token gating
    [Documentation]    Verify every model offered for fine-tuning reports whether pulling its base
    ...    weights needs a Hugging Face token, so a user is asked for one before starting a gated job.
    ...    A model whose gating cannot be determined is reported as gated, never as open.
    [Tags]    models    finetunable    smoke

    Given Project exists in system
    When finetunable models list is requested
    Then each finetunable model should report Hugging Face token gating

Finetunable models report the training settings their recipe defines
    [Documentation]    Verify a user choosing a base model is shown the batch size, epoch count and
    ...    learning-rate multiplier that model's own recipe trains with, rather than blank fields
    ...    they have to fill in blind. A setting the recipe never defines is reported as null, not
    ...    invented, so nobody unknowingly trains on a made-up value for hours.
    [Tags]    models    finetunable    smoke

    Given Project exists in system
    When finetunable models list is requested
    Then each finetunable model should report the training settings its recipe defines

Base models that train with LoRA report their LoRA settings
    [Documentation]    Verify a base model whose run tunes LoRA tells the user the rank, alpha and
    ...    dropout it will use, so those controls start from the recipe instead of a guess.
    [Tags]    models    finetunable    smoke

    Given Project exists in system
    When finetunable models list is requested
    Then each model that trains with LoRA should report its LoRA settings

Base models that train full-parameter offer no LoRA settings
    [Documentation]    Verify a base model that trains every weight offers no LoRA settings at all.
    ...    Such a run has no LoRA to tune and a job asking it to is refused, so showing the controls
    ...    would hand the user a knob the platform will not accept.
    [Tags]    models    finetunable    smoke

    Given Project exists in system
    When finetunable models list is requested
    Then each model that trains full-parameter should report no LoRA settings

Deleting a non-existent model returns not-found error
    [Documentation]    Verify the API returns a not-found error when attempting to delete
    ...    a model that does not exist.
    [Tags]                  models                  delete                  negative
    Given Project exists in system
    And a model does not exist
    When delete model request is sent
    Then response status should be 404

Delete AIMModel CR via API
    [Documentation]    Verify a fine-tuned model is deleted when the API endpoint is called with its name.
    ...    Tests the full deletion path: API call → AIMModel CR removal from the cluster.
    ...
    ...    Steps:
    ...    1. Pre-create an AIMModel CR directly in the cluster
    ...    2. Call the fine-tuning capability delete endpoint with the CR name
    ...    3. Verify 204 No Content response
    ...    4. Verify the AIMModel CR no longer exists in the cluster
    [Tags]                  models                  delete                  kubectl
    Given Project exists in system
    And an AIMModel CR exists in the namespace
    When delete AIMModel CR request is sent
    Then response status should be 204
    And the AIMModel CR should not exist

# Note: Model creation tests are in finetuning.robot since models are created
# through the fine-tuning capability endpoint (POST /v1/projects/{project}/fine-tuning/jobs),
# not through direct creation. The POST /v1/models endpoint was removed from the API.
