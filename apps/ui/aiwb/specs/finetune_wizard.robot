# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for the fine-tuning wizard base model selector
...                 and the custom-model deploy drawer.
...
...                 Verifies that the fine-tuning wizard displays GPU-compatible recipes
...                 with hardware names and handles the empty state when no recipes are compatible
...                 with the cluster's GPU hardware.
...
...                 Verifies the custom-model deploy drawer for a ready model — drawer
...                 rendering, submit with default values, and AIMService existence and
...                 chat-accessibility after deployment.

Resource            resources/common/browser_setup.resource
Resource            resources/finetune.resource
Resource            resources/airm_projects.resource

Suite Teardown      Run Keywords    Clean Up All Created AIWB Secrets    AND    Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***

Fine-tuning wizard lists compatible recipes with GPU hardware names
    [Documentation]    Verify the fine-tuning wizard shows available base models with their
    ...    GPU hardware names displayed as descriptions below each model name.
    ...
    ...    Requires: at least one GPU-compatible fine-tuning recipe in the catalog.
    [Tags]    ui    models    finetune    smoke

    Given a ready project with user access exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user opens the base model selector
    Then compatible fine-tuning recipes should be listed with hardware names

Fine-tuning wizard shows each base model at most once
    [Documentation]    Verify that when a base model has recipes for multiple hardware types,
    ...    only the recipe matching the cluster's GPU appears — no model is listed twice.
    [Tags]    ui    models    finetune    smoke

    Given a ready project with user access exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user opens the base model selector
    Then each base model should appear at most once in the recipe list

Fine-tuning wizard shows empty state when no recipes match cluster hardware
    [Documentation]    Verify the fine-tuning wizard tells the user no recipes are available
    ...    when the cluster's GPU hardware has no compatible fine-tuning recipes.
    ...
    ...    Auto-skips on GPU clusters where recipes will match. Runs on CPU-only clusters
    ...    where no fine-tuning recipes are compatible with the hardware.
    [Tags]    ui    models    finetune    cpu-only

    Given a cluster with no GPU hardware exists
    And a ready project with user access exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    Then fine-tuning wizard should show no compatible recipes message

Fine-tuning wizard constrains batch size to multiples of the recipe's GPU count
    [Documentation]    Verify that selecting a multi-GPU recipe locks the batch size
    ...    input to multiples of the recipe's GPU count, preventing the user from
    ...    submitting batch sizes that would silently crash the workload.
    ...
    ...    Auto-skips when no GPU recipes are listed (CPU-only cluster) or when the
    ...    only listed recipes use a single GPU (no multiple-of constraint to verify).
    [Tags]    ui    models    finetune    validation    gpu

    Given a ready project with user access exists
    And a dataset exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects the first compatible recipe
    And user continues to training settings
    Then training datasets should show their file sizes
    When user selects the first training dataset
    And user continues to target settings
    And user continues to hyper-parameter settings
    And user enables hyper-parameter customization
    Then the batch size input should require multiples of the recipe's GPU count

Fine-tuning wizard shows selected recipe hyperparameter defaults
    [Documentation]    Verify the hyperparameter step shows the selected recipe's epoch and
    ...    learning-rate values when a user chooses to customize training.
    [Tags]    ui    models    finetune    smoke

    Given a ready project with user access exists
    And a dataset exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects the first compatible recipe
    And user continues to training settings
    And user selects the first training dataset
    And user continues to target settings
    And user continues to hyper-parameter settings
    And user enables hyper-parameter customization
    Then the hyperparameter defaults should show the selected recipe's values

Fine-tuning confirmation formats custom decimal hyperparameters
    [Documentation]    Verify the confirmation step displays rounded learning-rate and
    ...    dropout values after the user customizes a LoRA fine-tuning run.
    ...
    ...    Auto-skips when no LoRA-capable base model on this cluster can serve adapters.
    [Tags]    ui    models    finetune    smoke

    Given a ready project with user access exists
    And a dataset exists
    And a base model that can be fine-tuned with LoRA and can serve adapters exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects the base model that can serve adapters
    And user continues to training settings
    And user selects LoRA fine-tuning type
    And user selects the first training dataset
    And user continues to target settings
    And user continues to hyper-parameter settings
    And user enables hyper-parameter customization
    And user sets custom decimal hyperparameters
    And user continues to confirmation
    Then the confirmation should format decimal hyperparameters to their step precision

Fine-tune action is available on completed fine-tuned model row
    [Documentation]    Verify that a completed fine-tuned model row shows a Fine-tune option
    ...    in its row action menu, and that clicking it opens the fine-tuning wizard
    ...    with the selected model locked as the base model.
    [Tags]    ui    models    finetune    kubectl

    Given a ready project with user access exists
    And a completed fine-tuned model exists for the test project
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tune action on the completed model row
    Then fine-tuning wizard should be open
    And the base model selector should be locked to the completed model

Fine-tuned model identity is presented together
    [Documentation]    Verify that the model's identity details remain grouped in the Name cell
    ...    while its operational and creation details remain visible in separate columns.
    [Tags]    ui    models    finetune    kubectl

    Given a ready project with user access exists
    And a completed fine-tuned model exists for the test project
    And user is logged in
    And test project is selected
    When user is on fine-tune models page
    Then the completed fine-tuned model identity should be presented together
    And its operational and creation details should remain visible

Re-fine-tuning a fine-tuned model does not ask for a HuggingFace token
    [Documentation]    Verify that opening the fine-tuning wizard from a completed fine-tuned
    ...    model hides the HuggingFace token section and lets the user submit the form
    ...    without a token.
    ...
    ...    A fine-tuned source keeps its weights in project storage, so re-fine-tuning it
    ...    needs no HuggingFace token. The wizard must reflect that source's actual token
    ...    requirement rather than forcing a token on an unknown source — which previously
    ...    crashed the page when submitted without one.
    [Tags]    ui    models    finetune    hf-token    kubectl

    Given a ready project with user access exists
    And a completed fine-tuned model exists for the test project
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tune action on the completed model row
    Then the HuggingFace token section should not be visible
    And the user can submit the fine-tuning form without a token

Fine-tune models table paginates when more models exist than fit one page
    [Documentation]    Verify the fine-tune models table renders the first page only and
    ...    surfaces pagination controls when the project contains more fine-tuned
    ...    models than fit on a single page; the user can step to subsequent pages.
    [Tags]    ui    models    pagination    kubectl

    Given a ready project with user access exists
    And more fine-tuned models exist in the namespace than fit a single page
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    Then the fine-tune models table shows the first page of fine-tuned models
    And pagination controls are visible on the fine-tune models table
    When user navigates to the next page of fine-tune models
    Then the fine-tune models table shows the next page of fine-tuned models

Fine-tuning wizard requires a HuggingFace token for a gated base model
    [Documentation]    Verify that selecting a gated base model reveals the HuggingFace
    ...    token section, and that submitting the form without selecting a token is blocked.
    ...
    ...    Gated models carry weights behind a HuggingFace access gate. The wizard must
    ...    surface the token selector so the fine-tuning job can pull the weights.
    ...    Auto-skips when no gated recipes are available on the cluster.
    [Tags]    ui    models    finetune    hf-token    smoke

    Given a ready project with user access exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects a gated base model
    Then the HuggingFace token section should be visible
    And continuing without a token should be blocked

Fine-tuning wizard submits successfully after selecting an existing HuggingFace token
    [Documentation]    Verify that selecting a gated base model and choosing an already-saved
    ...    HuggingFace token lets the fine-tuning form submit successfully.
    ...
    ...    Complements the "requires a token" test, which only proves submission is blocked
    ...    without one — this proves the happy path where a token is selected actually works.
    ...    Auto-skips when no gated recipes are available on the cluster.
    [Tags]    ui    models    finetune    hf-token    smoke

    Given a ready project with user access exists
    And a secret "hf-finetune-existing" with use case "HuggingFace" is created via AIWB
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects a gated base model
    And user selects the existing HuggingFace token
    And user submits the fine-tuning form
    Then the fine-tuning job should start without a validation error

Fine-tuning wizard submits successfully after creating a new HuggingFace token via the selector
    [Documentation]    Verify that a user with no saved HuggingFace token can create one inline
    ...    from the token selector's "Add new" popover, and that the newly created token is
    ...    accepted for submitting the fine-tuning form for a gated base model.
    ...
    ...    Auto-skips when no gated recipes are available on the cluster.
    [Tags]    ui    models    finetune    hf-token    smoke

    Given a ready project with user access exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects a gated base model
    And user creates a new HuggingFace token via the token selector
    And user submits the fine-tuning form
    Then the fine-tuning job should start without a validation error

Fine-tuning wizard preserves entered values when navigating back
    [Documentation]    Verify values entered on a later step survive a back-then-forward
    ...    navigation through the wizard.
    ...
    ...    Auto-skips when no non-gated fine-tuning recipes are available on this cluster.
    [Tags]    ui    models    finetune    navigation    smoke

    Given a ready project with user access exists
    And a dataset exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects a non-gated base model
    And user continues to training settings
    And user selects the first training dataset
    And user continues to target settings
    And user names the fine-tuned model and continues    preserved-finetune-name
    And user goes back in fine-tuning wizard
    Then fine-tuning wizard display name should be    preserved-finetune-name

Fine-tuning wizard submits successfully with automatic hyper-parameters
    [Documentation]    Verify that fine-tuning succeeds with automatic hyper-parameters
    ...    when the user does not enable customization.
    ...
    ...    Auto-skips when no non-gated fine-tuning recipes are available on this cluster.
    [Tags]    ui    models    finetune    regression    smoke

    Given a ready project with user access exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects a non-gated base model
    And user submits the fine-tuning form
    Then the fine-tuning job should start without a validation error
    And the fine-tuning success toast should offer navigation to fine-tuned models

Fine-tuning wizard submits successfully when the batch size field is left at its default
    [Documentation]    Verify that fine-tuning a model while leaving the customized batch
    ...    size field untouched succeeds using the server's default, rather than erroring
    ...    as though the untouched field held an invalid value.
    ...
    ...    Regression coverage: a HeroUI v3 migration left the shared number-input
    ...    control briefly surfacing an invalid empty-string/NaN sentinel for an
    ...    untouched optional field once it was focused and blurred, which could block
    ...    submission or reach the backend as a validation error.
    ...
    ...    Auto-skips when no non-gated fine-tuning recipes are available on this cluster.
    [Tags]    ui    models    finetune    regression    smoke

    Given a ready project with user access exists
    And a dataset exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects a non-gated base model
    And user submits fine-tuning leaving the batch size field at its default
    Then the fine-tuning job should start without a validation error

Fine-tuning workload keeps the description entered by the user
    [Documentation]    A description entered while starting fine-tuning remains visible when
    ...    the user later inspects that workload.
    [Tags]    ui    models    finetune    description    gpu
    [Teardown]    Run Keywords    The current fine-tuning job is torn down    AND    Close test browser

    Given a ready project with user access exists
    And a dataset exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects a non-gated base model
    And user submits the fine-tuning form with a description
    Then the fine-tuning job should start without a validation error
    And fine-tuning workload details should show its description

Fine-tuning wizard submits with multiple training datasets
    [Documentation]    Verify a user can select multiple datasets and start fine-tuning.
    ...
    ...    Auto-skips when no non-gated fine-tuning recipes are available on this cluster.
    [Tags]    ui    models    finetune    datasets    gpu

    Given a ready project with user access exists
    And multiple datasets exist    count=2
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects a non-gated base model
    And user continues to training settings
    And user selects 2 training datasets
    And user submits fine-tuning with the selected training datasets
    Then the fine-tuning job should start without a validation error

Fine-tuning wizard limits training dataset selection
    [Documentation]    Verify the wizard explains when the user reaches the ten-dataset limit.
    ...
    ...    Auto-skips when no non-gated fine-tuning recipes are available on this cluster.
    [Tags]    ui    models    finetune    datasets    validation    gpu

    Given a ready project with user access exists
    And multiple datasets exist    count=11
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects a non-gated base model
    And user continues to training settings
    And user selects all training datasets
    Then the training dataset selection limit should be shown

Fine-tuning wizard creates a LoRA adapter
    [Documentation]    Verify a user can select LoRA output, configure its hyper-parameters,
    ...    and start fine-tuning with a compatible base model.
    ...
    ...    Auto-skips when no LoRA-capable base model on this cluster can serve adapters.
    [Tags]    ui    models    finetune    lora    gpu

    Given a ready project with user access exists
    And a dataset exists
    And a base model that can be fine-tuned with LoRA and can serve adapters exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects the base model that can serve adapters
    And user submits LoRA adapter fine-tuning
    Then the fine-tuning job should start without a validation error
    And the fine-tuning success toast should offer navigation to LoRAs

Fine-tuning wizard does not offer LoRA for a base model that cannot serve adapters
    [Documentation]    Verify a user cannot choose LoRA output when the selected base model has
    ...    no serving profile able to load an adapter — the run would produce an adapter that
    ...    could never be deployed.
    ...
    ...    The user is told why the option is unavailable rather than left to guess.
    ...    Auto-skips when every LoRA-capable base model on this cluster can serve adapters.
    [Tags]    ui    models    finetune    lora

    Given a ready project with user access exists
    And a base model that can be fine-tuned with LoRA but cannot serve adapters exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects the base model that cannot serve adapters
    And user continues to training settings
    Then LoRA fine-tuning should not be offered
    And the wizard should explain that adapters for this model cannot be deployed
    And a usable fine-tuning type should be chosen instead

Fine-tuning wizard hides HuggingFace token section for a non-gated base model
    [Documentation]    Verify that selecting a non-gated base model keeps the HuggingFace
    ...    token section hidden.
    ...
    ...    Non-gated models have publicly available weights — no HF token is needed to
    ...    pull them. Showing the token section would confuse users and block submission.
    ...    Auto-skips when no non-gated recipes are available on the cluster.
    [Tags]    ui    models    finetune    hf-token

    Given a ready project with user access exists
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens fine-tuning wizard
    And user selects a non-gated base model
    Then the HuggingFace token section should not be visible

Custom model deploy drawer shows model details and deployment settings
    [Documentation]    Verify the custom-model deploy drawer renders the model header
    ...    (name and namespace) and the deployment-settings section including a display-name
    ...    input and an autoscaling toggle — without performing an actual GPU deployment.
    ...
    ...    This is a GPU-free smoke check for drawer rendering only.
    [Tags]    ui    models    finetune    deploy    kubectl    smoke

    Given a ready project with user access exists
    And a completed fine-tuned model exists for the test project
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens the deploy drawer for the custom model
    Then the deploy drawer should show the custom model's details
    And the deploy drawer should offer a deployment name and autoscaling

Fine-tuned model details show the description entered by the user
    [Documentation]    A user inspecting a fine-tuned model can read the description supplied
    ...    when its training was started.
    [Tags]    ui    models    finetune    description    kubectl    smoke

    Given a ready project with user access exists
    And a completed described fine-tuned model exists for the test project
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens details for the completed fine-tuned model
    Then fine-tuned model details should show its description

Deploy a custom model and verify it is ready to chat
    [Documentation]    Full lifecycle: open the custom-model deploy drawer from a ready
    ...    AIMModel row, submit with all default values, then verify via the AIWB API
    ...    that an AIMService CR was created in the project namespace and that the
    ...    service appears in the chat-capable inference list.
    ...
    ...    Requires GPU — the AIMService must reach a running state before the chat
    ...    endpoint becomes accessible.
    [Tags]    ui    models    finetune    deploy    kubectl    gpu

    Given a ready project with user access exists
    And a completed fine-tuned model exists for the test project
    And user is logged in
    And test project is selected
    And user is on fine-tune models page
    When user opens the deploy drawer for the custom model
    And user deploys the model with default settings
    Then a deployment for the custom model should exist in the project
    And the deployed model should be ready to chat
