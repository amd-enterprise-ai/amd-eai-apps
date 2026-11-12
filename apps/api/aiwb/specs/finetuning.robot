# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for Catalog API finetune endpoints.
...                 Verifies finetuning creation, workload lifecycle, and error handling.
...
...                 Suite Efficiency Design:
...                 GPU tests share a project and finetuning workload via idempotent Given
...                 preconditions backed by a suite-level cache. The cache avoids re-creating
...                 the same 30+ minute GPU job for each test. Every test is independently
...                 executable — Given steps re-create missing resources if run in isolation.
...                 Tests that destroy cached resources (force-delete) reset the cache so
...                 subsequent tests re-create via the same idempotent precondition.
...
...                 Destructive lifecycle scenarios are the deliberate exception: a test that
...                 cancels or deletes its own job asks for its own in-progress job instead of
...                 the shared one. Cancelling the shared workload would leave it Deleted and
...                 force every later scenario to pay for a second full fine-tuning run.
...
...                 Adapter lifetime coverage still requires a recipe that completes with a
...                 reusable artifact. Submission and running-workload classification are tested
...                 whenever a LoRA recipe is available; the job is cancelled after classification.
Resource    resources/aiwb_test_data.resource
Resource    resources/aiwb_models.resource
Resource    resources/aiwb_aims.resource
Resource    resources/aiwb_custom_models.resource
Resource    resources/aiwb_datasets.resource
Resource    resources/airm_keywords.resource
Resource    resources/api/common.resource
Resource    resources/airm_projects.resource
Library             Collections
Suite Teardown      Teardown Finetuning Suite


*** Test Cases ***
Finetuning workload starts running
    [Documentation]    Verify that the finetuning workload reaches Running status
    [Tags]    finetuning    workload    status    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists
    Then Finetuning workload should reach status "Running"

Fine-tuning job runs on a GPU its base model supports
    [Documentation]    A base model may offer different training settings for each GPU family.
    ...    A run has to land on hardware its settings were written for, or it can run out of
    ...    memory or never start on a cluster with more than one GPU family.
    [Tags]    finetuning    workload    placement    requires-gpu    kubectl    needs-aim-images    requires-finetunable-model    requires-gpu-unallocated:1

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists
    Then the fine-tuning job should run on a GPU its base model supports

Running fine-tuning job reports its planned output
    [Documentation]    A fine-tuning job tells users whether it will produce a full model,
    ...    merged model, or reusable adapter while work is still in progress.
    [Tags]    finetuning    workload    list    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists
    Then Fine-tuning job should report its planned output
    And Fine-tuning job detail should report its planned output

Adapter fine-tuning job reports its planned output
    [Documentation]    A submitted adapter run is distinguishable from model-producing runs
    ...    before its reusable artifact has been created.
    [Tags]    finetuning    adapters    workload    list    gpu
    [Teardown]    The current fine-tuning job is torn down

    Given a ready project with user access exists
    And the project has adapter fine-tuning quota available
    And finetuning storage credentials are available to the project
    And finetune dataset exists
    When an adapter-output fine-tuning job is started
    Then Fine-tuning job should report its planned output
    And Fine-tuning job detail should report its planned output

Fine-tuning accepts the settings its base model reports
    [Documentation]    A user who starts a run from the settings shown against a base model does
    ...    not have to translate them: the numbers offered when choosing the model are the same
    ...    numbers a job submission takes.
    [Tags]    finetuning    models    create    gpu
    [Teardown]    The current fine-tuning job is torn down

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And finetune dataset exists
    When a fine-tuning job is submitted with the settings its base model reports
    Then the fine-tuning job should be accepted

Fine-tuning without settings trains with the base model's own
    [Documentation]    A user who starts a run without naming any training settings gets the run
    ...    their chosen base model describes, rather than one trained at numbers the platform
    ...    picked on their behalf.
    [Tags]    finetuning    models    create    gpu    kubectl
    [Teardown]    The current fine-tuning job is torn down

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And finetune dataset exists
    When a fine-tuning job is submitted without any training settings
    Then the fine-tuning job should be accepted
    And the fine-tuning job should train with the settings its base model reports

Finetuning workload completes
    [Documentation]    Verify that the finetuning workload completes successfully
    [Tags]    finetuning    workload    complete    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists
    Then Finetuning workload should reach status "Complete"

Finetuned model exists with expected fields
    [Documentation]    Verify that a finetuned model exists and has expected fields (name, status, creator).
    ...    Runs after workload completes so the AIMModel CR is guaranteed to exist.
    [Tags]    finetuning    create    smoke    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists

    Then Finetuned model should have expected fields

Finetuned model keeps its description
    [Documentation]    A user's explanation of a fine-tuning run remains attached to the model
    ...    it produces and is returned when the model is inspected later.
    [Tags]    finetuning    model    description    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists
    And Finetuning workload should reach status "Complete"

    Then the finetuned model should carry its description
    And the fine-tuning workload should carry its description

Finetuning model appears in model list
    [Documentation]    Verify that a completed finetuned model appears in the namespace model list.
    ...    The list is K8s-based — it shows completed AIMModel CRs with workload-id labels.
    ...    Runs after workload completes so the AIMModel CR is guaranteed to exist.
    [Tags]    finetuning    models    list    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists

    Then the finetuned model should appear in the namespace model list

User can browse fine-tuned models page by page
    [Documentation]    Fine-tuned models in a project are served in pages rather
    ...                than as one flat list.
    [Tags]    finetuning    models    list    pagination

    Given a ready project with user access exists
    When fine-tuned models are listed for the project
    Then the result is returned page by page

Fine-tuning job uses every selected dataset
    [Documentation]    A user can start one fine-tuning job with multiple datasets
    ...                and see each dataset in the job details.
    [Tags]    finetuning    datasets    create
    [Teardown]    The multi-dataset fine-tuning job is torn down

    Given a ready project with user access exists
    And finetuning storage credentials are available to the project
    And two finetuning datasets exist
    When a multi-dataset finetuning job is started
    Then the fine-tuning job should list every selected dataset

Deleted dataset remains in fine-tuning job history
    [Documentation]    Deleting a dataset does not erase its association with an
    ...                existing fine-tuning job.
    [Tags]    finetuning    datasets    delete
    [Teardown]    The multi-dataset fine-tuning job is torn down

    Given a ready project with user access exists
    And finetuning storage credentials are available to the project
    And a fine-tuning job using multiple datasets exists
    When the first selected dataset is deleted
    Then the fine-tuning job should still show the deleted dataset

Fine-tuning that was not asked for an adapter leaves none behind
    [Documentation]    Verify a run that asked for a model produces no adapter alongside it.
    ...    Adapter output is opt-in, so a user who never asked for one must not have to
    ...    discover, name, and clean up an artifact they did not request.
    [Tags]    finetuning    adapters    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists
    And Finetuning workload should reach status "Complete"

    Then the project should hold no adapter from that fine-tuning run

Finetuned model becomes ready
    [Documentation]    Verify that the finetuned model onboarding status becomes ready after workload completes
    [Tags]    finetuning    model    onboarding    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists
    Then Finetuned model onboarding status should be "ready"

Finetuned model can be used as base model for a new finetuning run
    [Documentation]    Verify that a completed fine-tuned model can be selected as the base for a
    ...    new finetuning run, that the request is accepted, and that the new job actually loads
    ...    and trains against that base to completion — not merely admitted and left Running,
    ...    which would only prove the pod was scheduled.
    [Tags]    finetuning    create    models    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a completed fine-tuned model usable as a finetuning base exists
    And finetune dataset exists

    When a finetune request from an existing model is sent

    Then response status should be 202
    And the workload should use the AIMModel as base model
    And Finetuning workload should reach status "Complete"

Finetune with invalid data fails
    [Documentation]    Verify that a finetune request with invalid data fails with 422
    [Tags]    finetuning    error    invalid-data

    Given a ready project with user access exists

    # Prepare invalid finetune parameters
    VAR    &{invalid_finetune_data}
    ...    batchSize=-1
    ...    learningRate=-0.001
    ...    epochs=0
    VAR    ${base_model_name}    meta-llama/Llama-3.2-1B-Instruct

    When finetune request is sent with data    ${base_model_name}    ${invalid_finetune_data}

    Then response status should be 422

Fine-tuning request with ambiguous dataset selection is rejected
    [Documentation]    A fine-tuning request must use one dataset selection format.
    [Tags]    finetuning    datasets    error    invalid-data

    Given a ready project with user access exists
    And finetune dataset exists
    When the same dataset is submitted through both selection formats
    Then response status should be 422

Base models say whether they can produce an adapter
    [Documentation]    Verify every base model on offer reports how it trains, so a user can
    ...    tell which ones can leave a reusable adapter behind before committing to a run.
    [Tags]    finetuning    models    list    smoke

    Given a ready project with user access exists

    When finetunable models list is requested

    Then every base model should say whether it can produce an adapter

Asking for an adapter from a base model that cannot produce one is refused
    [Documentation]    Verify a base model that trains every weight refuses an adapter request
    ...    up front. Training for hours and then discarding what was asked for is the outcome
    ...    this prevents, so the refusal must arrive before any job starts.
    [Tags]    finetuning    adapters    negative    smoke

    Given a ready project with user access exists
    And a base model that cannot produce an adapter is offered
    And finetune dataset exists

    When an adapter is requested from that base model

    Then the request should be refused with a reason that names an alternative
    And no fine-tuning job should have started

Tuning LoRA settings on a base model that has none is refused
    [Documentation]    Verify LoRA hyperparameters are refused for a base model that trains
    ...    every weight. Accepting settings that cannot take effect would report success for a
    ...    run that trained something other than what was asked for.
    [Tags]    finetuning    negative    smoke

    Given a ready project with user access exists
    And a base model that cannot produce an adapter is offered
    And finetune dataset exists

    When LoRA settings are requested for that base model

    Then the request should be refused with a reason that names an alternative
    And no fine-tuning job should have started

Fine-tuned model can be deployed for inference
    [Documentation]    Verify a fine-tuned model can be deployed via the inference
    ...    capability endpoint. Deployment creates an AIMService CR referencing the
    ...    namespace-scoped AIMModel using the same deploy endpoint as cluster models —
    ...    the API auto-detects the model type.
    [Tags]    finetuning    aims    deploy    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists
    And finetuned model onboarding status should be "ready"
    And fine-tuned model deployment configurations are available

    When fine-tuned model is deployed as an AIM service

    Then deployed AIMService should reference the fine-tuned model

Fine-tuned model is deployable without a prior custom-model import
    [Documentation]    Regression guard: a fine-tuned model must be deployable in a project
    ...    that has never imported a custom model. Deployment requires generated profiles,
    ...    and those are derived from a base model the platform must provision at fine-tune
    ...    launch. Previously the base existed only as a side effect of the custom-import
    ...    flow, so fine-tuned models in fresh projects had no profiles and could not deploy.
    [Tags]    finetuning    models    deploy    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And no custom model has been imported into the project
    And a finetuning workload exists
    And finetuned model onboarding status should be "ready"

    Then fine-tuned model deployment configurations are available

Fine-tuned model deploy pins namespace AIMProfile when profiles are available
    [Documentation]    When aim-engine has emitted a Ready namespace AIMProfile, fine-tuned
    ...    deploy pins ``spec.profile.name`` to that profile even if the deploy request
    ...    includes runtime selector/override fields.
    [Tags]    finetuning    aims    deploy    gpu    kubectl

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists
    And finetuned model onboarding status should be "ready"
    And fine-tuned model deployment configurations are available

    When fine-tuned model is deployed with runtime profile overrides

    Then AIMService CR should pin namespace profile for model in kubernetes    ${TEST_FINETUNING_RESOURCE_NAME}

Deployed fine-tuned model is accessible for inference
    [Documentation]    Verify a deployed fine-tuned model AIMService is accessible for inference.
    ...    Once the service reaches Running state, it appears in the chattable services list
    ...    and can be used for chat from the playground.
    [Tags]    finetuning    aims    inference    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists
    And finetuned model onboarding status should be "ready"
    And fine-tuned model is deployed as an AIM service

    When deployed AIM reaches Running state

    Then deployed fine-tuned model should have an inference endpoint
    And deployed fine-tuned model should be accessible for inference

Cancel a running finetuning job
    [Documentation]    Verify a user can cancel an in-progress finetuning job and that
    ...    the underlying workload transitions to the Deleted state.
    [Tags]    finetuning    delete    gpu
    [Teardown]    The current fine-tuning job is torn down

    Given a ready project with user access exists
    And the project has fine-tuning quota available    concurrent_workloads=2
    And finetuning storage credentials are available to the project
    And an in-progress fine-tuning job exists
    When the finetuning job is cancelled
    Then the workload status should become "Deleted"

Fine-tuned model shows deployment configurations
    [Documentation]    Verify that a ready fine-tuned model has AIMProfiles with
    ...    hardware configuration details (model name, precision) so users can choose
    ...    the right deployment profile.
    [Tags]    finetuning    models    deploy    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists
    And finetuned model onboarding status should be "ready"
    And fine-tuned model deployment configurations are available

    Then fine-tuned model deployment configurations should include hardware details

Deleting fine-tuned model with active deployment is blocked
    [Documentation]    Verify the API rejects deletion of a fine-tuned model while it has
    ...    active deployments. Non-destructive — model and deployment remain intact.
    [Tags]    finetuning    models    delete    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists
    And finetuned model onboarding status should be "ready"
    And fine-tuned model is deployed as an AIM service

    When user deletes the fine-tuned model

    Then the request should be rejected because the deployment is active

Force-deleting fine-tuned model cascades deployment removal
    [Documentation]    Verify force-delete removes the model and cascades removal of its
    ...    deployments.
    ...
    ...    DESTRUCTIVE: This test removes the fine-tuned model. Must be the last GPU test.
    [Tags]    finetuning    models    delete    gpu

    Given a ready project with user access exists
    And the project has fine-tuning quota available
    And finetuning storage credentials are available to the project
    And a finetuning workload exists
    And finetuned model onboarding status should be "ready"
    And fine-tuned model is deployed as an AIM service

    When user force-deletes the fine-tuned model

    Then the fine-tuned model should be removed
    And the fine-tuned model deployment should be removed
    And the fine-tuned model storage should be removed
