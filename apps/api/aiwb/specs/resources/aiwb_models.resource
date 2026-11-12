# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level model testing keywords.
...                 Provides business-logic level keywords for testing model operations.
...                 Uses the low-level API keywords from api/models.resource to implement
...                 higher-level testing scenarios. This is the main interface that
...                 test cases should use.
Resource            api/models.resource
Resource            api/aims.resource
Resource            api/finetuning.resource
Resource            api/artifacts.resource
Resource            resources/api/workloads.resource
Resource            resources/airm_projects.resource
Resource            resources/airm_secrets.resource
Resource            resources/resource_tracking.resource
Resource            resources/common/resource_lifecycle.resource
Resource            aiwb_common.resource
Resource            aiwb_datasets.resource
Library             libraries/ModelCatalog.py
Library             libraries/FineTuningOutput.py
Library             AIMModelHelper
Library             Process


*** Variables ***
${TEST_MODEL_ID}            ${None}
${TEST_MODEL_NAME}          test-model
${TEST_BASE_MODEL_ID}       ${None}
${TEST_BASE_MODEL_WORKLOAD_ID}    ${None}
${TEST_MODEL_DATA}                ${None}
@{CREATED_MODEL_IDS}        # List to track created model IDs for cleanup
${TEST_DUMMY_AIMMODEL_NAME}             ${None}
${TEST_FULL_TRAINING_BASE_MODEL}        ${None}
${TEST_FINE_TUNING_JOB_COUNT}           ${None}
${TEST_FINETUNING_BASE_MODEL}            ${None}
${TEST_ADAPTER_RECIPE_NAME}              ${None}
${TEST_FINETUNING_OUTPUT}                ${None}
${TEST_FINETUNING_STORAGE_URI}           ${None}
${TEST_FINETUNING_STORAGE_URIS}          ${None}
${TEST_FINETUNING_STORAGE_CONTENTS}      ${None}
${TEST_FINETUNING_REPORTED_SETTINGS}     ${None}
${TEST_FINETUNING_GPU_COUNT}             ${None}
${FINETUNING_FIXTURE_SUFFIX}             shared-finetuning-model
# Display-name prefix for jobs a destructive scenario creates and then destroys. It is only a
# naming convention, never a selection key: discovery adopts a workload by matching
# FINETUNING_FIXTURE_SUFFIX exactly, so anything named differently is already excluded.
${FINETUNING_CANCELLATION_PREFIX}        cancellation-finetuning-job
${FINETUNED_MODEL_DESCRIPTION}          Fine-tuned for sentiment analysis.
${FINETUNING_COMPLETION_TIMEOUT}         15 min
${FINETUNED_MODEL_BASE_MODEL}           example-org/base-model


*** Keywords ***
Valid base model data is prepared
    [Documentation]    Prepares valid base model test data
    # Ensure we have a project to work with
    Project exists in system

    ${random_suffix}=       Generate Random String                          8                       [LOWER][NUMBERS]
    ${model_name}=          Set Variable            test-model-${random_suffix}
    Set Test Variable       ${TEST_MODEL_NAME}      ${model_name}

    ${namespace}=           Get Project Namespace
    ${model_data}=          Create Dictionary
    ...                     type=BaseModel
    ...                     name=${model_name}
    ...                     modelWeightsPath=default-bucket/models/${namespace}/models/${model_name}
    ...                     canonicalName=${model_name}
    Set Test Variable       ${TEST_MODEL_DATA}            ${model_data}

Create model request is sent
    [Documentation]    Sends request to create a model using prepared test data and the project ID
    ${endpoint}=            Models endpoint
    ${query_params}=        Create Dictionary       projectId=${TEST_PROJECT_ID}
    ${response}=            Safe Post Request         ${endpoint}             json=${TEST_MODEL_DATA}       params=${query_params}
    Set Test Variable       ${TEST_RESPONSE}             ${response}

    ${model_id}=            Get from dictionary     ${response.json()}      id
    Track Model For Cleanup    ${model_id}

Base model exists in system
    [Documentation]    Creates a base model and stores its ID as a test variable
    ...    This is a precondition keyword that:
    ...    1. Prepares valid base model data
    ...    2. Creates the model via API
    ...    3. Stores the ID for later use in test variable
    Valid base model data is prepared
    Create model request is sent
    Response status should be 201

    ${model_id}=            Get from dictionary     ${TEST_RESPONSE.json()}      id
    Set test variable       ${TEST_BASE_MODEL_ID}                           ${model_id}

    # Verify model was actually created
    ${namespace}=           Get Project Namespace
    ${verify_response}=     Get model               ${model_id}             namespace=${namespace}   expected_status=200
    Log                     Base model ${model_id} (${TEST_MODEL_NAME}) successfully created and verified                         INFO

Multiple models exist in system
    [Documentation]    Creates multiple models of different types for testing
    [Arguments]             ${base_model_count}=2                           ${adapter_count}=2

    VAR    @{created_base_models}
    VAR    @{created_adapters}

    Log                     Creating ${base_model_count} base models and ${adapter_count} adapters for testing           INFO

    FOR    ${index}    IN RANGE    ${base_model_count}
        Log                     Creating base model ${index+1} of ${base_model_count}               DEBUG
        Valid base model data is prepared
        Create model request is sent
        Response status should be 201

        ${model_id}=            Get from dictionary     ${TEST_RESPONSE.json()}      id
        Append to list          ${created_base_models}                          ${model_id}

        IF    ${index} == 0
            Set test variable       ${TEST_BASE_MODEL_ID}                           ${model_id}
            Log                     Set base model ID for adapter creation: ${model_id}             DEBUG
        END
    END

    FOR    ${index}    IN RANGE    ${adapter_count}
        Log                     Creating adapter ${index+1} of ${adapter_count}                 DEBUG

        # Verify we have a base model ID before attempting adapter creation
        Should not be empty     ${TEST_BASE_MODEL_ID}                           Cannot create adapter: No base model ID available

        Valid adapter data is prepared
        Create model request is sent
        Response status should be 201

        ${model_id}=            Get from dictionary     ${TEST_RESPONSE.json()}      id
        Append to list          ${created_adapters}     ${model_id}
    END

    Log                     Successfully created ${base_model_count} base models and ${adapter_count} adapters               INFO

Model exists in system
    [Documentation]    Creates a model for modification testing and stores its ID as a test variable
    Valid base model data is prepared
    Create model request is sent
    Response status should be 201

    ${model_id}=            Get from dictionary     ${TEST_RESPONSE.json()}      id
    Set test variable       ${TEST_MODEL_ID}        ${model_id}

    # Verify model was actually created by making a separate verification call
    ${namespace}=           Get Project Namespace
    ${response}=            Get model               ${model_id}             namespace=${namespace}   expected_status=200

A model does not exist
    [Documentation]    Sets up a non-existent model ID for testing
    ${model_id}=            Evaluate                str(uuid.uuid4())       modules=uuid
    Set test variable       ${TEST_MODEL_ID}        ${model_id}

Modify model request is sent with name "${new_name}" and type "${type}"
    [Documentation]    Sends request to modify an existing model with new name and type
    ${namespace}=           Get Project Namespace
    ${model_data}=          Create dictionary       name=${new_name}        type=${type}
    ${response}=            Modify model            ${TEST_MODEL_ID}        ${model_data}           namespace=${namespace}
    Set test variable       ${TEST_RESPONSE}             ${response}

Delete model request is sent
    [Documentation]    Sends a request to delete a model
    ${namespace}=           Get Project Namespace
    ${response}=            Delete model            ${TEST_MODEL_ID}        namespace=${namespace}
    Set test variable       ${TEST_RESPONSE}             ${response}

Model name in database should be "${expected_name}"
    [Documentation]    Verifies model name is updated in database
    ${namespace}=           Get Project Namespace
    ${db_response}=         Get model               ${TEST_MODEL_ID}        namespace=${namespace}
    Response should contain "${expected_name}"

The model should not exist in database
    [Documentation]    Verifies the model no longer exists in database
    ${model_id}=            Set Variable            ${TEST_MODEL_ID}

    ${namespace}=           Get Project Namespace
    ${db_response}=         Get model               ${model_id}             namespace=${namespace}   expected_status=404

Finetune request is sent with data
    [Documentation]    Sends a finetune request with provided data (may be invalid for error testing).
    ...                Sets TEST_RESPONSE for status verification.
    [Arguments]             ${model_name}           ${finetune_data}
    ${namespace}=           Get Project Namespace
    ${response}=            Finetune model          ${model_name}           ${finetune_data}
    ...                     namespace=${namespace}
    Set Test Variable       ${TEST_RESPONSE}        ${response}

The same dataset is submitted through both selection formats
    [Documentation]    Sends an ambiguous fine-tuning request using both dataset fields.
    Should Not Be Empty    ${TEST_DATASET_ID}    msg=Dataset ID is required for fine-tuning.
    ${dataset_ids}=    Create List    ${TEST_DATASET_ID}
    ${finetune_data}=    Create Dictionary
    ...    displayName=ambiguous-dataset-selection
    ...    datasetId=${TEST_DATASET_ID}
    ...    datasetIds=${dataset_ids}
    Finetune request is sent with data
    ...    meta-llama/Llama-3.2-1B-Instruct
    ...    ${finetune_data}

Get smallest finetunable catalog model
    [Documentation]    Returns the canonicalName of the smallest open finetunable catalog model.
    ...    Prefers open models (non-gated) over models requiring HF token (meta-llama/, google/gemma).
    ...    Among open models, sorts by gpuCount then parameter count — picks the cheapest option.
    ...    Stores the selected recipe's GPU requirement for project quota setup.
    ...    Skips the test if no models are configured for this cluster.
    ${cached}=    Get Variable Value    ${TEST_FINETUNING_BASE_MODEL}    ${None}
    IF    $cached is not None    RETURN    ${cached}
    ${response}=    Get finetunable models    expected_status=200
    VAR    ${models}    ${response.json()['data']}
    IF    len($models) == 0
        Skip    No finetunable models are configured for this cluster — skipping GPU finetuning tests
    END
    ${canonical_name}    ${gpu_count}=    Get Smallest Finetunable Model With GPU Count    ${models}
    ${training_type}=    Get Finetunable Model Training Type    ${models}    ${canonical_name}
    ${expected_output}=    Evaluate    "merged" if $training_type == "lora" else "full"
    VAR    ${TEST_FINETUNING_BASE_MODEL}    ${canonical_name}    scope=TEST
    VAR    ${TEST_FINETUNING_OUTPUT}    ${expected_output}    scope=TEST
    VAR    ${TEST_FINETUNING_GPU_COUNT}    ${gpu_count}    scope=TEST
    Log    Selected smallest finetunable model: ${canonical_name} (${gpu_count} GPU)    INFO
    RETURN    ${canonical_name}

The project has fine-tuning quota available
    [Documentation]    Ensures the project has enough quota for the selected fine-tuning recipe.
    ...    ``concurrent_workloads`` sizes the project for more than one run at a time. A
    ...    scenario that starts its own job while the shared fixture is still alive needs two,
    ...    or the second job stays Pending against the quota and any wait on it times out.
    [Arguments]    ${concurrent_workloads}=1
    Get smallest finetunable catalog model
    ${total_gpus}=    Evaluate    ${TEST_FINETUNING_GPU_COUNT} * ${concurrent_workloads}
    ${gpu_count}    ${cpu_milli_cores}    ${memory_bytes}=    Get Model Resource Quota
    ...    ${total_gpus}
    project quota is set to
    ...    gpu_count=${gpu_count}
    ...    cpu_milli_cores=${cpu_milli_cores}
    ...    memory_bytes=${memory_bytes}

A finetune request is sent
    [Documentation]    Sends a finetune request using the smallest finetunable catalog model.
    ...                Selects the model dynamically from GET /finetunable so the test always
    ...                uses a cluster-supported model with pre-configured overlays.
    ...                Skips if no finetunable models are configured for this cluster.
    ...
    ...                Schema fields (from FineTuningJobRequest, wire names):
    ...                - baseModel: AIMModel UUID or HuggingFace canonical name (set by the API keyword)
    ...                - displayName: Name of the finetuning job and resulting model
    ...                - datasetId: Deprecated UUID of a single dataset
    ...                - epochs, learningRate, batchSize: optional; each falls back to the base
    ...                model recipe's own value when left out.
    Should Not Be Empty     ${TEST_DATASET_ID}      msg=Dataset ID is required for finetuning.
    ${namespace}=           Get Project Namespace

    ${model_name}=    Test Name    ${FINETUNING_FIXTURE_SUFFIX}
    ${base_model_name}=     Get smallest finetunable catalog model

    # Generate finetune data matching FinetuneCreate schema. The settings are named explicitly to
    # keep this shared GPU run as short and small as possible, not because they are required: a
    # request that omits them trains with the recipe's own values instead.
    ${finetune_data}=       Create Dictionary
    ...                     displayName=${model_name}
    ...                     description=${FINETUNED_MODEL_DESCRIPTION}
    ...                     datasetId=${TEST_DATASET_ID}
    ...                     batchSize=2
    ...                     learningRate=1.41421
    ...                     epochs=1

    Log                     Sending finetune request for catalog model: ${base_model_name}           DEBUG
    ${response}=            Finetune model          ${base_model_name}      ${finetune_data}
    ...                     expected_status=202     namespace=${namespace}
    Set Test Variable       ${TEST_RESPONSE}             ${response}
    Log                     Finetune request response: ${response.json()}                   DEBUG

    ${workload_id}=    Get From Dictionary    ${response.json()}    workloadId
    VAR    ${TEST_FINETUNING_WORKLOAD_ID}      ${workload_id}    scope=TEST
    # CR name is assigned by the finetuning engine (not known yet); resolved lazily via workload-id label.
    # No tracking needed — project teardown cascades namespace deletion which removes the AIMModel CR.
    VAR    ${TEST_FINETUNING_RESOURCE_NAME}    ${None}           scope=TEST
    VAR    ${TEST_FINETUNING_STORAGE_URI}      ${None}           scope=TEST
    VAR    ${TEST_FINETUNING_STORAGE_URIS}     ${None}           scope=TEST
    VAR    ${TEST_FINETUNING_STORAGE_CONTENTS}    ${None}        scope=TEST


An in-progress fine-tuning job exists
    [Documentation]    Starts a fine-tuning job and waits until it is actually running.
    ...    A scenario that cancels or deletes its job must not be handed the shared fixture:
    ...    destroying it forces every later scenario in the suite to pay for a second full GPU
    ...    fine-tuning run. This job is therefore dedicated, tracked for cleanup, and never
    ...    stored in the shared cache, and its display name deliberately differs from the
    ...    fixture marker so "Find owned finetuning workload in namespace" can never adopt it.
    ...    The wait matters: submission is asynchronous, so without it a destructive scenario
    ...    would act on a Pending job and silently stop covering the in-progress case it names.
    Finetune dataset exists
    ${namespace}=    Get Project Namespace
    ${base_model_name}=    Get smallest finetunable catalog model
    ${random_suffix}=    Generate random string    8    [LOWER][NUMBERS]
    VAR    &{finetune_data}
    ...    displayName=${FINETUNING_CANCELLATION_PREFIX}-${random_suffix}
    ...    datasetId=${TEST_DATASET_ID}
    ...    batchSize=2
    ...    learningRate=1.41421
    ...    epochs=1
    ${response}=    Finetune model
    ...    ${base_model_name}
    ...    ${finetune_data}
    ...    namespace=${namespace}
    ...    expected_status=202
    VAR    ${body}    ${response.json()}
    VAR    ${TEST_FINETUNING_WORKLOAD_ID}    ${body}[workloadId]    scope=TEST
    VAR    ${TEST_FINETUNING_RESOURCE_NAME}    ${None}    scope=TEST
    VAR    ${TEST_FINETUNING_STORAGE_URI}      ${None}    scope=TEST
    VAR    ${TEST_FINETUNING_STORAGE_URIS}     ${None}    scope=TEST
    VAR    ${TEST_FINETUNING_STORAGE_CONTENTS}    ${None}    scope=TEST
    Track workload for cleanup    ${TEST_FINETUNING_WORKLOAD_ID}
    Wait For Resource Status    Get AIWB workload    ${TEST_FINETUNING_WORKLOAD_ID}    Running
    ...    timeout=15 min    interval=10 sec    namespace=${namespace}

An adapter-output fine-tuning job is started
    [Documentation]    Starts an adapter-producing run with the cheapest available LoRA recipe.
    Should Not Be Empty    ${TEST_DATASET_ID}    msg=Dataset ID is required for fine-tuning.
    ${namespace}=    Get Project Namespace
    ${base_model_name}=    The smallest adapter fine-tuning recipe
    ${random_suffix}=    Generate random string    8    [LOWER][NUMBERS]
    VAR    &{finetune_data}
    ...    displayName=finetuned-adapter-${random_suffix}
    ...    datasetId=${TEST_DATASET_ID}
    ...    output=adapter
    ...    epochs=1
    ${response}=    Finetune model
    ...    ${base_model_name}
    ...    ${finetune_data}
    ...    namespace=${namespace}
    ...    expected_status=202
    VAR    ${TEST_FINETUNING_WORKLOAD_ID}    ${response.json()}[workloadId]    scope=TEST
    VAR    ${TEST_FINETUNING_DISPLAY_NAME}    ${finetune_data}[displayName]    scope=TEST
    VAR    ${TEST_FINETUNING_OUTPUT}    lora    scope=TEST

The smallest adapter fine-tuning recipe
    [Documentation]    Selects the cheapest available LoRA recipe and records its GPU requirement
    ...    so the project quota can be sized to it. Idempotent within a test: the first call caches
    ...    the selection so the quota precondition and the job submission agree on one recipe.
    ...    Skips when no LoRA recipe is configured for this cluster.
    ${cached}=    Get Variable Value    ${TEST_ADAPTER_RECIPE_NAME}    ${None}
    IF    $cached is not None    RETURN    ${cached}
    ${response}=    Get finetunable models    expected_status=200
    VAR    ${models}    ${response.json()}[data]
    ${lora_models}=    Evaluate    [model for model in $models if model["trainingType"] == "lora"]
    IF    len($lora_models) == 0
        Skip    No LoRA fine-tuning recipe is configured for this cluster
    END
    ${base_model_name}    ${gpu_count}=    Get Smallest Finetunable Model With GPU Count    ${lora_models}
    VAR    ${TEST_ADAPTER_RECIPE_NAME}    ${base_model_name}    scope=TEST
    VAR    ${TEST_FINETUNING_GPU_COUNT}    ${gpu_count}    scope=TEST
    Log    Selected smallest adapter recipe: ${base_model_name} (${gpu_count} GPU)    INFO
    RETURN    ${base_model_name}

The project has adapter fine-tuning quota available
    [Documentation]    Ensures the project has enough quota for the selected adapter recipe.
    ${base_model_name}=    The smallest adapter fine-tuning recipe
    ${gpu_count}    ${cpu_milli_cores}    ${memory_bytes}=    Get Model Resource Quota
    ...    ${TEST_FINETUNING_GPU_COUNT}
    project quota is set to
    ...    gpu_count=${gpu_count}
    ...    cpu_milli_cores=${cpu_milli_cores}
    ...    memory_bytes=${memory_bytes}

The current fine-tuning job is torn down
    [Documentation]    Releases the current test's fine-tuning resources.
    ${workload_id}=    Get variable value    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}
    IF    $workload_id is None    RETURN
    ${namespace}=    Get Project Namespace
    Cancel finetuning job    ${workload_id}    namespace=${namespace}    expected_status=any


Two finetuning datasets exist
    [Documentation]    Creates two datasets and remembers both for a multi-dataset job.
    VAR    @{dataset_ids}
    VAR    @{dataset_names}
    FOR    ${index}    IN RANGE    2
        Valid dataset upload data is prepared
        Upload dataset request is sent
        Append to list    ${dataset_ids}    ${TEST_DATASET_ID}
        Append to list    ${dataset_names}    ${TEST_DATASET}[name]
    END
    VAR    ${TEST_FINETUNING_DATASET_IDS}    ${dataset_ids}    scope=TEST
    VAR    ${TEST_FINETUNING_DATASET_NAMES}    ${dataset_names}    scope=TEST


A multi-dataset finetuning job is started
    [Documentation]    Starts a fine-tuning job using every selected test dataset.
    Should not be empty    ${TEST_FINETUNING_DATASET_IDS}
    ${namespace}=    Get project namespace
    ${base_model_name}=    Get smallest finetunable catalog model
    ${random_suffix}=    Generate random string    8    [LOWER][NUMBERS]
    VAR    &{finetune_data}
    ...    displayName=multi-dataset-${random_suffix}
    ...    datasetIds=${TEST_FINETUNING_DATASET_IDS}
    ...    epochs=1
    ${response}=    Finetune model
    ...    ${base_model_name}
    ...    ${finetune_data}
    ...    namespace=${namespace}
    ...    expected_status=202
    VAR    ${body}    ${response.json()}
    VAR    ${TEST_FINETUNING_WORKLOAD_ID}    ${body}[workloadId]    scope=TEST
    Track workload for cleanup    ${TEST_FINETUNING_WORKLOAD_ID}


A fine-tuning job using multiple datasets exists
    [Documentation]    Creates two datasets and starts a job that uses both.
    Two finetuning datasets exist
    A multi-dataset finetuning job is started


The fine-tuning job should list every selected dataset
    [Documentation]    Verifies every selected dataset remains associated with the job.
    FOR    ${dataset_id}    IN    @{TEST_FINETUNING_DATASET_IDS}
        ${dataset}=    The job dataset    ${dataset_id}
        Should be equal    ${dataset}[available]    ${True}
    END


The first selected dataset is deleted
    [Documentation]    Deletes one dataset used by the current fine-tuning job.
    ${namespace}=    Get project namespace
    Delete dataset
    ...    ${TEST_FINETUNING_DATASET_IDS}[0]
    ...    ${namespace}
    ...    expected_status=204


The fine-tuning job should still show the deleted dataset
    [Documentation]    Verifies the deleted dataset snapshot remains visible on the job.
    ${deleted}=    The job dataset    ${TEST_FINETUNING_DATASET_IDS}[0]
    Should be equal    ${deleted}[name]    ${TEST_FINETUNING_DATASET_NAMES}[0]
    Should be equal    ${deleted}[available]    ${False}
    ${surviving}=    The job dataset    ${TEST_FINETUNING_DATASET_IDS}[1]
    Should be equal    ${surviving}[available]    ${True}


The multi-dataset fine-tuning job is torn down
    [Documentation]    Releases resources held by the job created by the current test.
    ${workload_id}=    Get variable value    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}
    IF    $workload_id is None    RETURN
    ${namespace}=    Get project namespace
    Cancel finetuning job    ${workload_id}    namespace=${namespace}    expected_status=any


The job dataset
    [Documentation]    Returns the fine-tuning job dataset with the requested ID.
    [Arguments]    ${dataset_id}
    ${namespace}=    Get project namespace
    ${response}=    Get AIWB workload
    ...    ${TEST_FINETUNING_WORKLOAD_ID}
    ...    namespace=${namespace}
    ...    expected_status=200
    VAR    ${datasets}    ${response.json()}[datasets]
    FOR    ${dataset}    IN    @{datasets}
        IF    $dataset["id"] == $dataset_id    RETURN    ${dataset}
    END
    Fail    Dataset ${dataset_id} is missing from the fine-tuning job


Clean Up All Created Models
    [Documentation]    Deletes all models created during test execution
    ...    This keyword should be used in a test suite teardown to ensure
    ...    all models created during testing are cleaned up properly.
    ...    Note: Models require project_id for deletion, so this has a special implementation
    ${tracking_list}=       Get Variable Value      ${CREATED_MODEL_IDS}    ${None}
    IF    $tracking_list is None    RETURN
    ${count}=               Get Length              ${tracking_list}
    IF    ${count} == 0    RETURN

    Log                     Cleaning up ${count} models: ${CREATED_MODEL_IDS}                       INFO

    ${namespace}=           Get Project Namespace
    # Delete each model individually
    FOR    ${model_id}    IN    @{tracking_list}
        TRY
            Log                     Deleting model ${model_id}                      DEBUG
            Delete model            model_id=${model_id}    namespace=${namespace}   expected_status=any     project_id=${TEST_PROJECT_ID}
        EXCEPT    AS    ${error}
            Log                     Failed to delete model ${model_id}: ${error}    WARN
        END
    END

    # Reset the list of created models
    VAR    @{CREATED_MODEL_IDS}    scope=SUITE
    Log                     Model cleanup complete. CREATED_MODEL_IDS reset to: ${CREATED_MODEL_IDS}                        INFO

Finetuning storage credentials are available to the project
    [Documentation]    A fine-tuning workload reads its training data from project storage
    ...    through a platform-managed credential; this ensures that credential is in place
    ...    before the workload starts.
    Secret "minio-credentials-fetcher" is assigned to project

A finetuning workload exists
    [Documentation]    Idempotent: ensures a finetuning workload exists.
    ...    Sets TEST_FINETUNING_WORKLOAD_ID and TEST_FINETUNING_RESOURCE_NAME as test variables.
    ...    Uses suite-level cache to avoid re-querying the API across tests,
    ...    but always sets test-level variables so each test has explicit preconditions.
    ...    TEST_FINETUNING_RESOURCE_NAME may be ${None} if the workload is still Running
    ...    and the AIMModel CR has not been created yet — resolved lazily on subsequent calls.
    # Check suite cache first, but revalidate it because another scenario can delete its AIMModel.
    ${cached_workload_id}=    Get Variable Value    ${_CACHED_FINETUNING_WORKLOAD_ID}     ${None}
    ${cached_output}=         Get Variable Value    ${_CACHED_FINETUNING_OUTPUT}          ${None}
    IF    $cached_workload_id != $None
        ${reusable}    ${resource_name}=    Owned finetuning workload is reusable    ${cached_workload_id}
        IF    $reusable
            VAR    ${TEST_FINETUNING_WORKLOAD_ID}      ${cached_workload_id}    scope=TEST
            VAR    ${TEST_FINETUNING_RESOURCE_NAME}    ${resource_name}         scope=TEST
            VAR    ${TEST_FINETUNING_OUTPUT}           ${cached_output}         scope=TEST
            VAR    ${_CACHED_FINETUNING_RESOURCE_NAME}  ${resource_name}        scope=SUITE
            Log    Reusing cached finetuning workload: ${cached_workload_id}, resource: ${resource_name}    DEBUG
            RETURN
        END
        Log    Cached finetuning workload ${cached_workload_id} is stale; finding a replacement    DEBUG
        Clear cached finetuning workload
    END
    ${workload_id}    ${resource_name}=    Find owned finetuning workload in namespace
    IF    $workload_id != $None
        VAR    ${TEST_FINETUNING_WORKLOAD_ID}       ${workload_id}    scope=TEST
        VAR    ${TEST_FINETUNING_RESOURCE_NAME}     ${resource_name}    scope=TEST
        VAR    ${TEST_FINETUNING_OUTPUT}            ${None}    scope=TEST
        VAR    ${_CACHED_FINETUNING_WORKLOAD_ID}    ${workload_id}    scope=SUITE
        VAR    ${_CACHED_FINETUNING_RESOURCE_NAME}  ${resource_name}    scope=SUITE
        VAR    ${_CACHED_FINETUNING_OUTPUT}         ${None}    scope=SUITE
        RETURN
    END
    Finetune dataset exists
    A finetune request is sent
    # Cache after A finetune request is sent, which sets TEST_FINETUNING_WORKLOAD_ID and TEST_FINETUNING_RESOURCE_NAME
    VAR    ${_CACHED_FINETUNING_WORKLOAD_ID}      ${TEST_FINETUNING_WORKLOAD_ID}    scope=SUITE
    VAR    ${_CACHED_FINETUNING_RESOURCE_NAME}    ${TEST_FINETUNING_RESOURCE_NAME}  scope=SUITE
    VAR    ${_CACHED_FINETUNING_OUTPUT}           ${TEST_FINETUNING_OUTPUT}         scope=SUITE

Clear cached finetuning workload
    [Documentation]    Clears all suite state for the shared fine-tuning fixture.
    VAR    ${_CACHED_FINETUNING_WORKLOAD_ID}      ${None}    scope=SUITE
    VAR    ${_CACHED_FINETUNING_RESOURCE_NAME}    ${None}    scope=SUITE
    VAR    ${_CACHED_FINETUNING_OUTPUT}           ${None}    scope=SUITE

Owned finetuning workload is reusable
    [Documentation]    Validates that a workload belongs to the shared fixture and can be reused.
    ...    Active work is reusable before its AIMModel exists. Complete work is reusable only
    ...    while its workload-labelled AIMModel still exists.
    [Arguments]    ${workload_id}
    ${namespace}=    Get Project Namespace
    ${response}=    Get AIWB workload    ${workload_id}    namespace=${namespace}    expected_status=any
    IF    ${response.status_code} != 200    RETURN    ${False}    ${None}
    VAR    ${workload}    ${response.json()}
    ${fixture_name}=    Test Name    ${FINETUNING_FIXTURE_SUFFIX}
    IF    $workload["displayName"] != $fixture_name    RETURN    ${False}    ${None}
    ${status}=    Get From Dictionary    ${workload}    status
    IF    $status not in ["Pending", "Starting", "Running", "Complete"]
        RETURN    ${False}    ${None}
    END
    TRY
        ${resource_name}=    Get finetuned model resource name from workload    ${workload_id}
        RETURN    ${True}    ${resource_name}
    EXCEPT
        IF    $status in ["Pending", "Starting", "Running"]    RETURN    ${True}    ${None}
        RETURN    ${False}    ${None}
    END

Find owned finetuning workload in namespace
    [Documentation]    Finds a reusable workload created by this suite's shared fixture.
    ...    The fixture's stable display name is its durable ownership marker across Robot
    ...    process restarts. Other fine-tuning scenarios use different display names and
    ...    cannot be adopted even when they share the project namespace.
    ${namespace}=    Get Project Namespace
    ${fixture_name}=    Test Name    ${FINETUNING_FIXTURE_SUFFIX}
    VAR    ${page}    ${1}
    WHILE    $True    limit=1000
        ${response}=    Get AIWB workloads    namespace=${namespace}    workload_type=FINE_TUNING
        ...    page=${page}    page_size=100
        IF    ${response.status_code} != 200
            RETURN    ${None}    ${None}
        END
        VAR    ${body}    ${response.json()}
        ${workloads}=    Get From Dictionary    ${body}    data
        FOR    ${workload}    IN    @{workloads}
            IF    $workload["displayName"] != $fixture_name    CONTINUE
            ${id}=    Get From Dictionary    ${workload}    id
            ${reusable}    ${resource_name}=    Owned finetuning workload is reusable    ${id}
            IF    $reusable
                Log    Found reusable suite-owned finetuning workload: ${id}    DEBUG
                RETURN    ${id}    ${resource_name}
            END
        END
        ${pagination}=    Get From Dictionary    ${body}    pagination
        ${total}=    Get From Dictionary    ${pagination}    total
        ${page_size}=    Get From Dictionary    ${pagination}    pageSize
        IF    ${page} * ${page_size} >= ${total}
            RETURN    ${None}    ${None}
        END
        ${page}=    Evaluate    ${page} + 1
    END
    RETURN    ${None}    ${None}

Get finetuned model resource name from workload
    [Documentation]    Returns the AIMModel CR name for a finetuning workload.
    ...    Pages through the namespace model list and matches the workload ID label.
    ...    Fails if no matching AIMModel CR exists (e.g., workload still Running).
    [Arguments]    ${workload_id}
    ${namespace}=    Get Project Namespace
    VAR    ${page}    ${1}
    WHILE    $True    limit=1000
        ${response}=    Get models    namespace=${namespace}    expected_status=200
        ...    page=${page}    page_size=100
        VAR    ${body}    ${response.json()}
        ${models}=    Get From Dictionary    ${body}    data
        FOR    ${model}    IN    @{models}
            ${wid}=    Evaluate    $model.get('metadata', {}).get('labels', {}).get('airm.silogen.ai/workload-id')
            IF    "${wid}" == "${workload_id}"
                ${resource_name}=    Get From Dictionary    ${model}[metadata]    name
                RETURN    ${resource_name}
            END
        END
        ${pagination}=    Get From Dictionary    ${body}    pagination
        ${total}=    Get From Dictionary    ${pagination}    total
        ${page_size}=    Get From Dictionary    ${pagination}    pageSize
        IF    ${page} * ${page_size} >= ${total}    BREAK
        ${page}=    Evaluate    ${page} + 1
    END
    Fail    Could not find model with workload-id label=${workload_id} in the namespace model list

The finetuned model should appear in the namespace model list
    [Documentation]    Verifies the finetuned model appears in the K8s-based namespace model list.
    ...    The list combines in-progress finetuning jobs and completed AIMModel CRs.
    ...    Searches by workload ID label and checks that the expected response fields are present.
    Should Not Be Equal    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}    msg=No finetuning workload ID set
    ${namespace}=    Get Project Namespace
    ${response}=    Get models    namespace=${namespace}    expected_status=200
    ${json}=    Set Variable    ${response.json()}
    ${models}=    Get From Dictionary    ${json}    data
    FOR    ${model}    IN    @{models}
        ${wid}=    Evaluate    $model.get('metadata', {}).get('labels', {}).get('airm.silogen.ai/workload-id')
        IF    "${wid}" == "${TEST_FINETUNING_WORKLOAD_ID}"
            Dictionary Should Contain Key    ${model}    metadata
            Dictionary Should Contain Key    ${model}    status
            Dictionary Should Contain Key    ${model}[metadata]    name
            Log    Found model in list: name=${model['metadata']['name']} status=${model['status']['status']}    INFO
            RETURN
        END
    END
    Fail    Finetuning model with workload-id label=${TEST_FINETUNING_WORKLOAD_ID} not found in model list

Fine-tuned models are listed for the project
    [Documentation]    Lists fine-tuned models in the current project with no filters.
    ...    Sets: TEST_RESPONSE
    ${namespace}=    Get Project Namespace
    ${response}=    Get models    namespace=${namespace}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Finetuned model should have expected fields
    [Documentation]    Verifies the finetuned model can be retrieved by resource name and has expected K8s-sourced fields.
    ...    Fetches the model by TEST_FINETUNING_RESOURCE_NAME and checks: metadata.name, status, creator annotation.
    Should Not Be Equal    ${TEST_FINETUNING_RESOURCE_NAME}    ${None}    msg=No finetuning resource name set
    ${namespace}=    Get Project Namespace
    ${response}=    Get model    ${TEST_FINETUNING_RESOURCE_NAME}    expected_status=200    namespace=${namespace}
    ${json}=    Set Variable    ${response.json()}
    Dictionary Should Contain Key    ${json}    metadata
    Dictionary Should Contain Key    ${json}    status
    Dictionary Should Contain Key    ${json}[metadata]    name
    VAR    ${annotations}    ${json}[metadata][annotations]
    Dictionary Should Contain Key    ${annotations}    airm.silogen.ai/submitter
    Should Be Equal    ${annotations}[airm.silogen.ai/submitter]    ${TEST_USER_EMAIL}
    ...    msg=submitter annotation is empty for fine-tuned model ${TEST_FINETUNING_RESOURCE_NAME}

The finetuned model should carry its description
    [Documentation]    Verifies the description supplied with the fine-tuning job remains on the
    ...    produced model and is returned when the model is inspected.
    Should Not Be Equal    ${TEST_FINETUNING_RESOURCE_NAME}    ${None}    msg=No finetuning resource name set
    ${namespace}=    Get Project Namespace
    ${response}=    Get model    ${TEST_FINETUNING_RESOURCE_NAME}    expected_status=200    namespace=${namespace}
    VAR    ${annotations}    ${response.json()}[metadata][annotations]
    Should Be Equal
    ...    ${annotations}[aiwb.apps.eai.amd.com/source-description]
    ...    ${FINETUNED_MODEL_DESCRIPTION}

The fine-tuning workload should carry its description
    [Documentation]    Verifies the description supplied with the fine-tuning job is returned
    ...    when that workload is inspected.
    Should Not Be Equal    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}    msg=No finetuning workload ID set
    ${namespace}=    Get Project Namespace
    ${response}=    Get AIWB workload
    ...    ${TEST_FINETUNING_WORKLOAD_ID}
    ...    namespace=${namespace}
    ...    expected_status=200
    Should Be Equal    ${response.json()}[description]    ${FINETUNED_MODEL_DESCRIPTION}

Finetuning workload should reach status "${target_status}"
    [Documentation]    Polls the workloads API until the finetuning workload reaches the
    ...    target status. Fails if the workload enters a terminal Failed state.
    Should Not Be Equal    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}    msg=No finetuning workload ID set
    ${namespace}=    Get Project Namespace
    # Completion includes the training lifecycle; Running covers admission only.
    IF    "${target_status}" == "Complete"
        VAR    ${timeout}    ${FINETUNING_COMPLETION_TIMEOUT}
    ELSE
        VAR    ${timeout}    5 min
    END
    Wait Until Keyword Succeeds    ${timeout}    10 sec
    ...    Finetuning workload status should be    ${target_status}    ${namespace}

Finetuning workload status should be
    [Documentation]    Single-poll check used by Wait Until Keyword Succeeds.
    ...    Fails on terminal Failed state; returns normally if target or an allowed
    ...    intermediate state (Running→Complete transition) is reached.
    [Arguments]    ${target_status}    ${namespace}
    ${response}=    Get AIWB workload    ${TEST_FINETUNING_WORKLOAD_ID}    namespace=${namespace}
    ${status}=    Get From Dictionary    ${response.json()}    status
    IF    "${status}" == "Failed" and "${target_status}" != "Failed"
        Fail    Finetuning workload entered Failed state (expected ${target_status})
    END
    # Workload already Completed — it transited through Running
    IF    "${target_status}" == "Running" and "${status}" == "Complete"
        RETURN
    END
    Should Be Equal    ${status}    ${target_status}    Workload status: ${status}

Finetuned model onboarding status should be "${target_status}"
    [Documentation]    Polls the namespace model list until the finetuned model reaches the
    ...    target onboarding status. Searches by workload-id label so it works once the
    ...    AIMModel CR exists after training completes.
    Should Not Be Equal    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}    msg=No finetuning workload ID set
    ${namespace}=    Get Project Namespace
    # Map "ready" to the K8s AIMModel onboarding status value returned by the API
    VAR    ${k8s_status}    ${target_status}
    IF    "${target_status}" == "ready"
        VAR    ${k8s_status}    Ready
    END
    Wait Until Keyword Succeeds    ${FINETUNING_COMPLETION_TIMEOUT}    10 sec
    ...    Finetuned model status should be    ${k8s_status}    ${target_status}    ${namespace}

Finetuned model status should be
    [Documentation]    Single-poll check used by Wait Until Keyword Succeeds.
    ...    Once the AIMModel CR name is known (TEST_FINETUNING_RESOURCE_NAME), polls it directly
    ...    with a targeted Get model call instead of re-scanning the full model list on every
    ...    retry. Falls back to the list scan, matched by workload-id label, only until the
    ...    resource name is first resolved — before that the CR may not exist yet.
    [Arguments]    ${k8s_status}    ${display_status}    ${namespace}
    ${resource_name}=    Get Variable Value    ${TEST_FINETUNING_RESOURCE_NAME}    ${None}
    IF    $resource_name is not None
        ${response}=    Get model    ${resource_name}    namespace=${namespace}    expected_status=200
        ${status}=    Get From Dictionary    ${response.json()}[status]    status
        Finetuned model status outcome should not block progress    ${status}    ${k8s_status}    ${display_status}
        RETURN
    END
    ${response}=    Get models    namespace=${namespace}    expected_status=200
    ${models}=    Get From Dictionary    ${response.json()}    data
    FOR    ${model}    IN    @{models}
        ${wid}=    Evaluate    $model.get('metadata', {}).get('labels', {}).get('airm.silogen.ai/workload-id')
        IF    "${wid}" != "${TEST_FINETUNING_WORKLOAD_ID}"    CONTINUE
        ${resolved_name}=    Get From Dictionary    ${model}[metadata]    name
        VAR    ${TEST_FINETUNING_RESOURCE_NAME}    ${resolved_name}    scope=TEST
        VAR    ${_CACHED_FINETUNING_RESOURCE_NAME}    ${resolved_name}    scope=SUITE
        ${status}=    Get From Dictionary    ${model}[status]    status
        Finetuned model status outcome should not block progress    ${status}    ${k8s_status}    ${display_status}
        RETURN
    END
    Fail    Finetuned model with workload-id ${TEST_FINETUNING_WORKLOAD_ID} not found yet

Finetuned model status outcome should not block progress
    [Documentation]    Shared terminal-check for one polled status value, used by both the
    ...    targeted and list-scan paths above so their pass/fail semantics stay identical.
    ...    Returns normally on a target-status match; fails (so Wait Until Keyword Succeeds
    ...    gives up or retries) otherwise.
    [Arguments]    ${status}    ${k8s_status}    ${display_status}
    ${outcome}=    Classify Finetuned Model Status    ${status}    ${k8s_status}
    IF    "${outcome}" == "reached"    RETURN
    IF    "${outcome}" == "failed"
        Fail    Finetuned model entered Failed status (expected ${display_status})
    END
    Fail    Finetuned model status is ${status} (waiting for ${display_status})

A dummy AIMModel CR exists in the namespace
    [Documentation]    Creates a minimal AIMModel CR in the project namespace via kubectl.
    ...    Simulates a completed fine-tuned model without requiring GPU or actual fine-tuning.
    ...    Idempotent: caches the CR name at suite level to avoid redundant kubectl calls.
    ...    Sets TEST_DUMMY_AIMMODEL_NAME for later use in assertions.
    [Arguments]    ${name}=dummy-finetuned-model
    # Check suite cache first — reuse across tests
    ${cached}=    Get Variable Value    ${_CACHED_DUMMY_AIMMODEL_NAME}    ${None}
    IF    $cached != $None
        VAR    ${TEST_DUMMY_AIMMODEL_NAME}    ${cached}    scope=TEST
        Log    Reusing cached dummy AIMModel CR: ${cached}    DEBUG
        RETURN
    END
    ${namespace}=    Get Project Namespace
    Apply Dummy AIMModel CR    ${name}    ${namespace}
    VAR    ${TEST_DUMMY_AIMMODEL_NAME}    ${name}    scope=TEST
    VAR    ${_CACHED_DUMMY_AIMMODEL_NAME}    ${name}    scope=SUITE
    Log    Created dummy AIMModel CR '${name}' in namespace ${namespace}    INFO

The dummy AIMModel should appear in the namespace model list
    [Documentation]    Verifies the dummy AIMModel CR appears in the namespace model list and exposes
    ...    the metadata.name and status.status fields downstream consumers depend on.
    Should Not Be Equal    ${TEST_DUMMY_AIMMODEL_NAME}    ${None}    msg=No dummy AIMModel name set
    ${namespace}=    Get Project Namespace
    ${response}=    Get models    namespace=${namespace}    expected_status=200
    VAR    ${json}    ${response.json()}
    ${models}=    Get From Dictionary    ${json}    data
    FOR    ${model}    IN    @{models}
        ${metadata}=    Get From Dictionary    ${model}    metadata
        ${name}=    Get From Dictionary    ${metadata}    name
        IF    "${name}" == "${TEST_DUMMY_AIMMODEL_NAME}"
            Dictionary Should Contain Key    ${model}    status
            ${status_obj}=    Get From Dictionary    ${model}    status
            ${status}=    Get From Dictionary    ${status_obj}    status
            Log    Found dummy model in list: name=${name} status=${status}    INFO
            RETURN
        END
    END
    Fail    Dummy AIMModel '${TEST_DUMMY_AIMMODEL_NAME}' not found in model list

The dummy AIMModel should be retrievable by resource name
    [Documentation]    Verifies the dummy AIMModel can be fetched by resource name and exposes
    ...    the expected metadata and status sections.
    Should Not Be Equal    ${TEST_DUMMY_AIMMODEL_NAME}    ${None}    msg=No dummy AIMModel name set
    ${namespace}=    Get Project Namespace
    ${response}=    Get model    ${TEST_DUMMY_AIMMODEL_NAME}    expected_status=200    namespace=${namespace}
    VAR    ${json}    ${response.json()}
    Dictionary Should Contain Key    ${json}    metadata
    Dictionary Should Contain Key    ${json}    status
    ${metadata}=    Get From Dictionary    ${json}    metadata
    ${name}=    Get From Dictionary    ${metadata}    name
    Should Be Equal    ${name}    ${TEST_DUMMY_AIMMODEL_NAME}
    ${status_obj}=    Get From Dictionary    ${json}    status
    ${status}=    Get From Dictionary    ${status_obj}    status
    Log    Retrieved dummy model: name=${name} status=${status}    INFO

Getting a non-existent model should return 404
    [Documentation]    Verifies that requesting a model by a non-existent resource name returns 404.
    ${namespace}=    Get Project Namespace
    ${response}=    Get model    nonexistent-model-xyz    expected_status=404    namespace=${namespace}

Resolve Fine-Tuned Model aimId
    [Documentation]    Read status.aimId for a fine-tuned AIMModel CR. Fails when
    ...    the controller has not yet populated the field — profile listing
    ...    cannot proceed until reconciliation completes.
    [Arguments]    ${resource_name}    ${namespace}
    ${response}=    Get model    ${resource_name}    expected_status=200    namespace=${namespace}
    ${status}=    Get From Dictionary    ${response.json()}    status
    ${aim_id}=    Get From Dictionary    ${status}    aimId    default=${None}
    Should Not Be Equal    ${aim_id}    ${None}
    ...    msg=AIMModel ${resource_name} has no status.aimId yet — engine has not reconciled
    RETURN    ${aim_id}

Fine-tuned model deployment configurations are available
    [Documentation]    Verifies deployment configurations exist for the ready finetuned model.
    ...    These are provisioned automatically once model onboarding completes.
    ...    Requires: TEST_FINETUNING_RESOURCE_NAME
    Should Not Be Equal    ${TEST_FINETUNING_RESOURCE_NAME}    ${None}
    ...    msg=No finetuning resource name set — call "A finetuning workload exists" first
    ${namespace}=    Get Project Namespace
    # status.aimId is populated asynchronously by the engine — poll until it appears.
    ${aim_id}=    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Resolve Fine-Tuned Model aimId    ${TEST_FINETUNING_RESOURCE_NAME}    ${namespace}
    ${response}=    List Fine-Tuned AIM Profiles
    ...    ${namespace}
    ...    aim_id=${aim_id}
    ...    expected_status=200
    VAR    ${json}    ${response.json()}
    ${profiles}=    Get From Dictionary    ${json}    data
    ${count}=    Get Length    ${profiles}
    Should Be True    ${count} > 0
    ...    msg=No deployment configurations found for fine-tuned model ${TEST_FINETUNING_RESOURCE_NAME}
    Log    Found ${count} deployment configurations for fine-tuned model ${TEST_FINETUNING_RESOURCE_NAME}    INFO

Fine-tuned model is deployed as an AIM service
    [Documentation]    Deploys the finetuned model via the inference capability endpoint.
    ...    Uses the same endpoint as cluster model deployment — the API auto-detects the model type.
    ...    Idempotent: reuses an existing AIMService for the model when present.
    ...    Requires: TEST_FINETUNING_RESOURCE_NAME
    ...    Sets: TEST_AIM_ID
    Should Not Be Equal    ${TEST_FINETUNING_RESOURCE_NAME}    ${None}
    ...    msg=No finetuning resource name set — call "A finetuning workload exists" first
    ${namespace}=    Get Project Namespace
    # Reuse an existing AIMService for this model if available
    ${existing}=    Find Existing Fine-Tuned AIM Service    ${namespace}    ${TEST_FINETUNING_RESOURCE_NAME}
    IF    $existing != $None
        ${service_id}=    Get From Dictionary    ${existing}    id
        VAR    ${TEST_AIM_ID}    ${service_id}    scope=TEST
        Log    Reusing existing AIMService ${service_id} for fine-tuned model    INFO
        RETURN
    END
    # Cluster models and fine-tuned project-scoped models share the same deploy endpoint
    # — the API auto-detects the model type from the resource name.
    ${deploy_data}=    Create Dictionary    replicas=${1}
    ${response}=    Deploy AIM    ${TEST_FINETUNING_RESOURCE_NAME}    ${deploy_data}    ${namespace}    expected_status=202
    ${json}=    Set Variable    ${response.json()}
    ${service_id}=    Get From Dictionary    ${json}    id
    VAR    ${TEST_AIM_ID}    ${service_id}    scope=TEST
    Log    Deployed fine-tuned model ${TEST_FINETUNING_RESOURCE_NAME} as AIMService ${service_id}    INFO

Fine-tuned model is deployed with runtime profile overrides
    [Documentation]    Deploys the finetuned model with runtime profile override fields in
    ...    the API request. Undeploys any existing service first so the CR reflects this
    ...    deploy. When a Ready namespace AIMProfile exists, those fields are not written
    ...    to the AIMService CR — the profile is pinned by name instead.
    ...    Requires: TEST_FINETUNING_RESOURCE_NAME
    ...    Sets: TEST_AIM_ID
    Should Not Be Equal    ${TEST_FINETUNING_RESOURCE_NAME}    ${None}
    ...    msg=No finetuning resource name set — call "A finetuning workload exists" first
    ${namespace}=    Get Project Namespace
    ${existing}=    Find Existing Fine-Tuned AIM Service    ${namespace}    ${TEST_FINETUNING_RESOURCE_NAME}
    IF    $existing != $None
        ${service_id}=    Get From Dictionary    ${existing}    id
        Undeploy AIM    ${service_id}    ${namespace}    expected_status=any
    END
    ${engine_args}=    Create Dictionary    max-model-len=${8192}
    ${engine_env_entry}=    Create Dictionary    name=VLLM_LOGGING_LEVEL    value=DEBUG
    ${engine_env}=    Create List    ${engine_env_entry}
    ${container_env_entry}=    Create Dictionary    name=FOO    value=bar
    ${container_env}=    Create List    ${container_env_entry}
    ${deploy_data}=    Create Dictionary
    ...    replicas=${1}
    ...    precision=fp8
    ...    gpuModel=MI300X
    ...    gpuCount=${2}
    ...    engineArgs=${engine_args}
    ...    engineEnv=${engine_env}
    ...    containerEnv=${container_env}
    ${response}=    Deploy AIM    ${TEST_FINETUNING_RESOURCE_NAME}    ${deploy_data}    ${namespace}    expected_status=202
    VAR    ${json}    ${response.json()}
    ${service_id}=    Get From Dictionary    ${json}    id
    VAR    ${TEST_AIM_ID}    ${service_id}    scope=TEST
    Log    Deployed fine-tuned model ${TEST_FINETUNING_RESOURCE_NAME} with runtime profile overrides as AIMService ${service_id}    INFO

Find Existing Fine-Tuned AIM Service
    [Documentation]    Finds an existing AIMService for a fine-tuned model in a namespace.
    ...    Returns the service dict if found, ${None} otherwise.
    [Arguments]    ${namespace}    ${model_resource_name}
    ${services_response}=    List AIM Services    ${namespace}    expected_status=200
    ${services_data}=    Set Variable    ${services_response.json()}
    ${services_list}=    Set Variable    ${services_data['data']}
    FOR    ${service}    IN    @{services_list}
        ${model}=    Get From Dictionary    ${service['spec']}    model
        ${model_name}=    Get From Dictionary    ${model}    name
        IF    "${model_name}" == "${model_resource_name}"
            RETURN    ${service}
        END
    END
    RETURN    ${None}

Deployed AIMService should reference the fine-tuned model
    [Documentation]    Verifies the AIMService spec.model.name matches the finetuned model resource name.
    ...    Requires: TEST_AIM_ID, TEST_FINETUNING_RESOURCE_NAME
    Should Not Be Equal    ${TEST_AIM_ID}    ${None}    msg=No AIM service ID set
    ${namespace}=    Get Project Namespace
    ${response}=    Get AIM Service    ${TEST_AIM_ID}    ${namespace}    expected_status=200
    ${json}=    Set Variable    ${response.json()}
    ${spec}=    Get From Dictionary    ${json}    spec
    ${model}=    Get From Dictionary    ${spec}    model
    ${model_name}=    Get From Dictionary    ${model}    name
    Should Be Equal    ${model_name}    ${TEST_FINETUNING_RESOURCE_NAME}
    ...    msg=AIMService model name '${model_name}' does not match finetuned model '${TEST_FINETUNING_RESOURCE_NAME}'
    Log    AIMService correctly references fine-tuned model: ${model_name}    INFO

Deployed fine-tuned model should have an inference endpoint
    [Documentation]    Verifies the deployed fine-tuned AIMService has an internal inference endpoint.
    ...    Requires: TEST_AIM_ID
    Should Not Be Equal    ${TEST_AIM_ID}    ${None}    msg=No AIM service ID set
    ${namespace}=    Get Project Namespace
    ${response}=    Get AIM Service    ${TEST_AIM_ID}    ${namespace}    expected_status=200
    ${json}=    Set Variable    ${response.json()}
    Dictionary Should Contain Key    ${json}    endpoints    msg=AIMService should have endpoints field
    ${endpoints}=    Get From Dictionary    ${json}    endpoints
    Dictionary Should Contain Key    ${endpoints}    internal    msg=AIMService should have an internal inference endpoint
    ${internal_url}=    Get From Dictionary    ${endpoints}    internal
    Should Not Be Empty    ${internal_url}    msg=Internal inference endpoint should not be empty
    Log    Fine-tuned model inference endpoint: ${internal_url}    INFO

Deployed fine-tuned model should be accessible for inference
    [Documentation]    Verifies the fine-tuned AIMService appears in the inference deployments list
    ...    filtered by capability=chat, confirming it is accessible from the playground for chat.
    ...    Requires: TEST_AIM_ID
    Should Not Be Equal    ${TEST_AIM_ID}    ${None}    msg=No AIM service ID set
    ${namespace}=    Get Project Namespace
    ${response}=    List AIM Services    ${namespace}    expected_status=200    capability=chat
    ${json}=    Set Variable    ${response.json()}
    ${services}=    Get From Dictionary    ${json}    data
    FOR    ${service}    IN    @{services}
        ${service_id}=    Get From Dictionary    ${service}    id
        IF    "${service_id}" == "${TEST_AIM_ID}"
            Log    Fine-tuned model AIMService ${TEST_AIM_ID} is accessible for inference    INFO
            RETURN
        END
    END
    Fail    Fine-tuned model AIMService ${TEST_AIM_ID} not found in chat-capable inference deployments list

Fine-tuned model deployment configurations should include hardware details
    [Documentation]    Verifies each deployment configuration for the fine-tuned model exposes
    ...    the hardware details users need to choose a profile: model reference and precision.
    ...    Requires: TEST_FINETUNING_RESOURCE_NAME (set by "a finetuning workload exists")
    Should Not Be Equal    ${TEST_FINETUNING_RESOURCE_NAME}    ${None}
    ...    msg=No finetuning resource name set
    ${namespace}=    Get Project Namespace
    # status.aimId is populated asynchronously by the engine — poll until it appears.
    ${aim_id}=    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Resolve Fine-Tuned Model aimId    ${TEST_FINETUNING_RESOURCE_NAME}    ${namespace}
    ${response}=    List Fine-Tuned AIM Profiles
    ...    ${namespace}
    ...    aim_id=${aim_id}
    ...    expected_status=200
    ${configurations}=    Get From Dictionary    ${response.json()}    data
    Should Not Be Empty    ${configurations}
    ...    msg=No deployment configurations found for model ${TEST_FINETUNING_RESOURCE_NAME}
    FOR    ${config}    IN    @{configurations}
        ${spec}=    Get From Dictionary    ${config}    spec
        Dictionary Should Contain Key    ${spec}    aimId
        ...    msg=Deployment configuration missing aim reference
        Dictionary Should Contain Key    ${spec}    precision
        ...    msg=Deployment configuration missing precision
        Dictionary Should Contain Key    ${config}    status
        ...    msg=Deployment configuration missing hardware profile metadata
    END
    ${config_count}=    Get Length    ${configurations}
    Log    All ${config_count} deployment configurations expose hardware details    INFO

User deletes the fine-tuned model
    [Documentation]    Sends a non-forced delete request for the current finetuned model.
    ...    Stores the response so subsequent Then steps can inspect the outcome.
    ...    Requires: TEST_FINETUNING_RESOURCE_NAME
    Should Not Be Equal    ${TEST_FINETUNING_RESOURCE_NAME}    ${None}
    ...    msg=No finetuning resource name set
    ${namespace}=    Get Project Namespace
    ${response}=    Delete model    ${TEST_FINETUNING_RESOURCE_NAME}    ${namespace}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The request should be rejected because the deployment is active
    [Documentation]    Verifies the previous delete request was rejected with a conflict response,
    ...    indicating an active deployment is preventing deletion.
    ...    Requires: TEST_RESPONSE (set by "user deletes the fine-tuned model")
    Should Not Be Equal    ${TEST_RESPONSE}    ${None}    msg=No prior delete response captured
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    409
    ...    msg=Expected 409 Conflict (active deployment), got ${TEST_RESPONSE.status_code}

User force-deletes the fine-tuned model
    [Documentation]    Sends a force-delete request for the current finetuned model.
    ...    Resets the suite-level finetuning cache so any subsequent test re-creates
    ...    the workload through the idempotent "a finetuning workload exists" precondition.
    ...    Requires: TEST_FINETUNING_RESOURCE_NAME
    Should Not Be Equal    ${TEST_FINETUNING_RESOURCE_NAME}    ${None}
    ...    msg=No finetuning resource name set
    ${namespace}=    Get Project Namespace
    ${model_response}=    Get model    ${TEST_FINETUNING_RESOURCE_NAME}    ${namespace}    expected_status=200
    VAR    ${model}    ${model_response.json()}
    ${storage_uris}=    Fine-Tuned Model Source And Parent Storage Locations    ${model}
    VAR    ${storage_uri}    ${storage_uris}[0]
    ${stored}=    Objects Stored At Storage Locations    ${namespace}    ${storage_uris}
    Should Not Be Empty    ${stored}
    ...    msg=Nothing stored at ${storage_uris} before delete, so the cleanup assertion would pass vacuously
    VAR    ${TEST_FINETUNING_STORAGE_URI}    ${storage_uri}    scope=TEST
    VAR    ${TEST_FINETUNING_STORAGE_URIS}    ${storage_uris}    scope=TEST
    VAR    ${TEST_FINETUNING_STORAGE_CONTENTS}    ${stored}    scope=TEST
    Log    Captured fine-tuning cleanup location ${storage_uri} before delete    DEBUG
    Delete model    ${TEST_FINETUNING_RESOURCE_NAME}    ${namespace}    expected_status=204    force=${True}
    Log    Force-deleted model ${TEST_FINETUNING_RESOURCE_NAME}    INFO
    VAR    ${_CACHED_FINETUNING_WORKLOAD_ID}      ${None}    scope=SUITE
    VAR    ${_CACHED_FINETUNING_RESOURCE_NAME}    ${None}    scope=SUITE

The fine-tuned model should be removed
    [Documentation]    Verifies the finetuned model no longer exists in the namespace.
    ...    Requires: TEST_FINETUNING_RESOURCE_NAME
    Should Not Be Equal    ${TEST_FINETUNING_RESOURCE_NAME}    ${None}
    ...    msg=No finetuning resource name set
    ${namespace}=    Get Project Namespace
    Get model    ${TEST_FINETUNING_RESOURCE_NAME}    namespace=${namespace}    expected_status=404

The fine-tuned model deployment should be removed
    [Documentation]    Verifies the deployment of the finetuned model no longer exists.
    ...    Requires: TEST_AIM_ID
    Should Not Be Equal    ${TEST_AIM_ID}    ${None}    msg=No deployment ID set
    ${namespace}=    Get Project Namespace
    Get AIM Service    ${TEST_AIM_ID}    ${namespace}    expected_status=404

Captured fine-tuned model storage objects should be removed
    [Documentation]    Asserts each object recorded before delete no longer exists afterward.
    [Arguments]    ${namespace}
    Stored Object Keys Should Be Removed    ${namespace}    ${TEST_FINETUNING_STORAGE_CONTENTS}

Fine-tuned model storage locations should be empty
    [Documentation]    Asserts all recorded storage locations hold no remaining objects.
    [Arguments]    ${namespace}
    Storage Locations Should Be Empty    ${namespace}    ${TEST_FINETUNING_STORAGE_URIS}

The fine-tuned model storage should be removed
    [Documentation]    Verifies the deleted model's object-storage prefix is fully reclaimed.
    Should Not Be Equal    ${TEST_FINETUNING_STORAGE_URI}    ${None}
    ...    msg=No fine-tuned model storage location captured before delete
    Should Not Be Equal    ${TEST_FINETUNING_STORAGE_CONTENTS}    ${None}
    ...    msg=No pre-delete storage contents captured for fine-tuned model
    Should Not Be Empty    ${TEST_FINETUNING_STORAGE_CONTENTS}
    ...    msg=No objects were captured before delete, so post-delete checks are not meaningful
    Should Not Be Equal    ${TEST_FINETUNING_STORAGE_URIS}    ${None}
    ...    msg=No storage locations captured for fine-tuned model
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Captured fine-tuned model storage objects should be removed    ${namespace}
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Fine-tuned model storage locations should be empty    ${namespace}

Setup Finetuning Suite
    [Documentation]    Initialize tracking for finetuning resource cleanup.
    ...    Models, datasets, and workloads are namespace-scoped and cascade-deleted
    ...    when the project is deleted. Model tracking is initialized for the
    ...    non-finetuning model tests (e.g. dummy AIMModel CR tests).
    Initialize Project Tracking
    Initialize Model Tracking
    Initialize Dataset Tracking

Teardown Finetuning Suite
    [Documentation]    Clean up by deleting the project. Project deletion cascades namespace
    ...    deletion which removes all namespace-scoped resources (models, datasets, workloads).
    Clean Up All Created Projects

An AIMModel CR exists in the namespace
    [Documentation]    Creates an AIMModel CR directly via kubectl for deletion testing.
    ...    Sets TEST_MODEL_NAME to the created CR name and registers it for teardown cleanup.
    [Tags]    kubectl
    ${namespace}=           Get Project Namespace
    ${random_suffix}=       Generate Random String              8                   [LOWER][NUMBERS]
    VAR    ${model_name}    test-model-${random_suffix}
    VAR    ${TEST_MODEL_NAME}    ${model_name}    scope=TEST
    Apply Dummy AIMModel CR    ${model_name}    ${namespace}
    Append To List          ${CREATED_MODEL_IDS}                ${model_name}
    Log                     Created AIMModel CR ${model_name} in namespace ${namespace}     INFO

A non-custom AIMModel exists in the namespace
    [Documentation]    Seeds a fine-tuned AIMModel CR that is not a custom import: no
    ...    ``model-source-type=custom`` label and no onboard revision/source-sha stamps.
    ...    Sets ``TEST_MODEL_NAME`` for copy and eligibility negative tests.
    [Tags]    kubectl
    An AIMModel CR exists in the namespace
    ${namespace}=    Get Project Namespace
    AIMModel Should Not Be Custom Import    ${TEST_MODEL_NAME}    ${namespace}

A completed fine-tuned model exists in the namespace
    [Documentation]    Creates an image-only AIMModel CR for scenarios that need a listed
    ...    fine-tuning model shape, not one usable as a new run's base. Its workload-id label makes
    ...    the API expose an item id and the UI show the Fine-tune row action; the status patch
    ...    makes the fixture appear Complete before the engine's next reconcile.
    ...
    ...    This fixture carries no weights and cannot serve as a fine-tuning base. Scenarios that
    ...    start another run must use "A completed fine-tuned model usable as a finetuning base
    ...    exists" instead; that fixture lets the engine publish its identity.
    [Tags]    kubectl
    An AIMModel CR exists in the namespace
    ${namespace}=    Get Project Namespace
    ${workload_id}=    Evaluate    str(uuid.uuid4())    modules=uuid
    ${result}=    Run Process
    ...    kubectl    patch    aimmodels    ${TEST_MODEL_NAME}
    ...    -n    ${namespace}
    ...    --type\=merge
    ...    -p    {"metadata":{"labels":{"airm.silogen.ai/workload-id":"${workload_id}","aiwb.apps.eai.amd.com/model-name":"${TEST_MODEL_NAME}"},"annotations":{"aiwb.apps.eai.amd.com/source-description":"${FINETUNED_MODEL_DESCRIPTION}","aiwb.apps.eai.amd.com/training-output":"full"}},"spec":{"profiles":{"overrides":{"modelSources":[{"modelId":"${FINETUNED_MODEL_BASE_MODEL}","sourceUri":"s3://example-bucket/models/base-model"}]}}}}
    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to patch AIMModel ${TEST_MODEL_NAME} labels: ${result.stderr}
    ${result}=    Run Process
    ...    kubectl    patch    aimmodels    ${TEST_MODEL_NAME}
    ...    -n    ${namespace}
    ...    --subresource\=status
    ...    --type\=merge
    # status.aimId, not just spec.aimId: deriving a fine-tuning recipe from this model reads the
    # aimId off the STATUS subresource, and refuses with "Cannot determine aimId for fine-tuning
    # recipe" when it is absent — which a real reconciled model would always carry.
    ...    -p    {"status":{"status":"Ready","aimId":"test/base-model"}}
    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to patch AIMModel ${TEST_MODEL_NAME} status to Ready: ${result.stderr}

A completed described fine-tuned model exists in the namespace
    [Documentation]    Creates a completed fine-tuned model carrying the description users
    ...    supplied when starting training.
    [Tags]    kubectl
    A completed fine-tuned model exists in the namespace
    ${namespace}=    Get Project Namespace
    ${result}=    Run Process
    ...    kubectl    patch    aimmodels    ${TEST_MODEL_NAME}
    ...    -n    ${namespace}
    ...    --type\=merge
    ...    -p    {"metadata":{"annotations":{"aiwb.apps.eai.amd.com/source-description":"${FINETUNED_MODEL_DESCRIPTION}"}}}
    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to patch AIMModel ${TEST_MODEL_NAME} description: ${result.stderr}

A completed fine-tuned model usable as a finetuning base exists
    [Documentation]    Selects a real, fully-trained fine-tuned model as the base for a new run,
    ...    by reusing the suite's shared finetuning workload (the same one most other GPU scenarios
    ...    in this suite exercise) rather than fabricating a stand-in. Its weights, recipe and aimId
    ...    all come from an actual completed training run, so a request built from it exercises
    ...    exactly what a real "continue from an existing fine-tuned model" request would use —
    ...    a fabricated checkpoint or a cluster model picked outside the finetunable catalog could
    ...    not make that guarantee. Sets TEST_MODEL_NAME, TEST_MODEL_AIM_ID and
    ...    TEST_BASE_MODEL_WORKLOAD_ID.
    ...
    ...    Kept apart from "A completed fine-tuned model exists in the namespace", which seeds an
    ...    image-only CR for list, delete and row-visibility scenarios. That shape cannot be a
    ...    base: it carries no weights, and its identity would have to be written into the
    ...    engine-owned status, which the engine drops on its next reconcile.
    A finetuning workload exists
    Finetuning workload should reach status "Complete"
    ${namespace}=    Get Project Namespace
    # "A finetuning workload exists" resolves TEST_FINETUNING_RESOURCE_NAME lazily and may leave
    # it ${None} (e.g. a cold cache whose workload was still Running when first seen). Waiting for
    # Complete only polls the workload, not the AIMModel CR, so it does not fix a stale ${None} —
    # re-resolve the CR name from the workload id now that Complete guarantees the CR exists, and
    # update both caches before copying identity, so this base is never built from a stale name.
    ${resource_name}=    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Get finetuned model resource name from workload    ${TEST_FINETUNING_WORKLOAD_ID}
    VAR    ${TEST_FINETUNING_RESOURCE_NAME}       ${resource_name}    scope=TEST
    VAR    ${_CACHED_FINETUNING_RESOURCE_NAME}    ${resource_name}    scope=SUITE
    VAR    ${TEST_MODEL_NAME}    ${resource_name}    scope=TEST
    VAR    ${TEST_BASE_MODEL_WORKLOAD_ID}    ${TEST_FINETUNING_WORKLOAD_ID}    scope=TEST
    # status.aimId is engine-authored, so it appears only after reconciliation.
    ${aim_id}=    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Resolve Fine-Tuned Model aimId    ${resource_name}    ${namespace}
    VAR    ${TEST_MODEL_AIM_ID}    ${aim_id}    scope=TEST

Delete AIMModel CR request is sent
    [Documentation]    Sends a DELETE request using the AIMModel CR name (TEST_MODEL_NAME).
    ${namespace}=           Get Project Namespace
    ${response}=            Delete model            ${TEST_MODEL_NAME}      namespace=${namespace}
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The AIMModel CR should not exist
    [Documentation]    Verifies the AIMModel CR no longer exists in the namespace.
    ${namespace}=           Get Project Namespace
    AIMModel CR Should Be Absent    ${TEST_MODEL_NAME}    ${namespace}
    Log                     Confirmed AIMModel CR ${TEST_MODEL_NAME} was deleted    INFO

A finetune request from an existing model is sent
    [Documentation]    Sends a finetune request naming an existing fine-tuned model as the base,
    ...    by the workload id clients hold for it — the identifier the models API surfaces and the
    ...    UI sends, and the one the fine-tuning endpoint accepts alongside a HuggingFace canonical
    ...    name. A fine-tuning output's own resource name is engine-generated and is not that
    ...    identifier. Requires TEST_BASE_MODEL_WORKLOAD_ID (from "A completed fine-tuned model
    ...    usable as a finetuning base exists") and TEST_DATASET_ID (from
    ...    "Finetune dataset exists").
    Should Not Be Empty    ${TEST_BASE_MODEL_WORKLOAD_ID}    msg=Base model workload id not set — call "A completed fine-tuned model usable as a finetuning base exists" first
    Should Not Be Empty    ${TEST_DATASET_ID}    msg=Dataset ID not set — call "Finetune dataset exists" first
    ${namespace}=    Get Project Namespace
    ${random_suffix}=    Generate Random String    8    [LETTERS][NUMBERS]
    VAR    ${model_name}    finetuned-from-model-${random_suffix}
    ${finetune_data}=    Create Dictionary
    ...    displayName=${model_name}
    ...    datasetId=${TEST_DATASET_ID}
    ...    batchSize=2
    ...    learningRate=1.41421
    ...    epochs=1
    ${response}=    Finetune model    ${TEST_BASE_MODEL_WORKLOAD_ID}    ${finetune_data}
    ...    namespace=${namespace}    expected_status=202
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST
    ${workload_id}=    Get From Dictionary    ${response.json()}    workloadId
    VAR    ${TEST_FINETUNING_WORKLOAD_ID}    ${workload_id}    scope=TEST
    # This run's own AIMModel CR is engine-assigned and does not exist yet, so drop the cached
    # resource name the base fixture left behind. Without this the next status poll takes the
    # cached path and polls the BASE model — already Complete — and would report success
    # immediately, passing before the new run had done anything.
    VAR    ${TEST_FINETUNING_RESOURCE_NAME}    ${None}    scope=TEST
    Track Workload For Cleanup    ${workload_id}

The workload should use the AIMModel as base model
    [Documentation]    Verifies the finetuning response's baseModel is the base model's own aimId
    ...    (TEST_MODEL_AIM_ID), not the identifier the request named. This distinguishes "the CR
    ...    was resolved and its published identity used" from "the identifier was silently passed
    ...    through as a HuggingFace model id".
    Should Not Be Empty    ${TEST_MODEL_AIM_ID}
    ...    msg=TEST_MODEL_AIM_ID not set — call "A completed fine-tuned model usable as a finetuning base exists" first
    ${base_model}=    Get From Dictionary    ${TEST_RESPONSE.json()}    baseModel
    Should Be Equal    ${base_model}    ${TEST_MODEL_AIM_ID}
    ...    msg=baseModel should be the AIMModel's aimId (${TEST_MODEL_AIM_ID}), not the workload id named by the request

Finetunable models list is requested
    [Documentation]    Requests the list of finetunable models and stores the response.
    ${response}=    Get finetunable models    expected_status=200
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The finetuning job is cancelled
    [Documentation]    Cancels the in-progress finetuning workload identified by
    ...                TEST_FINETUNING_WORKLOAD_ID via the fine-tuning capability API.
    Should Not Be Equal    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}
    ...    msg=No finetuning workload ID set — call "An in-progress fine-tuning job exists" first
    ${namespace}=    Get Project Namespace
    ${response}=    Cancel finetuning job    ${TEST_FINETUNING_WORKLOAD_ID}    namespace=${namespace}
    ...    expected_status=204
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST
    Log    Cancelled finetuning job ${TEST_FINETUNING_WORKLOAD_ID}    INFO
    # Deliberately does NOT touch the shared cache. Callers own a disposable job, so the shared
    # fixture is unaffected; clearing it here would discard an intact workload and force the
    # very redundant GPU run this separation exists to avoid.

The workload status should become "${target_status}"
    [Documentation]    Polls the AIWB workloads API until the finetuning workload
    ...                identified by TEST_FINETUNING_WORKLOAD_ID reaches the target status.
    Should Not Be Equal    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}
    ...    msg=No finetuning workload ID set — call "An in-progress fine-tuning job exists" (destructive scenarios) or "A finetuning workload exists" (shared fixture) first
    ${namespace}=    Get Project Namespace
    Wait For Resource Status    Get AIWB workload    ${TEST_FINETUNING_WORKLOAD_ID}    ${target_status}
    ...    timeout=5 min    interval=10 sec    namespace=${namespace}
    Log    Finetuning workload ${TEST_FINETUNING_WORKLOAD_ID} reached status ${target_status}    INFO

Fine-tuning job should report its planned output
    [Documentation]    The project workload list classifies the submitted fine-tuning job by
    ...    the resource it will produce.
    ...    A reused workload (discovery/cache path) carries no expected classification, so the
    ...    scenario skips rather than asserting against an unknown expectation.
    Should Not Be Equal    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}
    IF    $TEST_FINETUNING_OUTPUT is None
        Skip    Planned-output expectation is unknown for a reused fine-tuning workload; cannot assert independently
    END
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Fine-tuning job output should be    ${namespace}    ${TEST_FINETUNING_WORKLOAD_ID}
    ...    ${TEST_FINETUNING_OUTPUT}

Fine-tuning job output should be
    [Documentation]    Assert one fine-tuning job's reported output in the project list.
    [Arguments]    ${namespace}    ${workload_id}    ${expected_output}
    ${response}=    Get AIWB workloads
    ...    ${namespace}
    ...    workload_type=FINE_TUNING
    ...    expected_status=200
    VAR    ${workloads}    ${response.json()}[data]
    ${matches}=    Evaluate    [item for item in $workloads if item["id"] == $workload_id]
    Length Should Be    ${matches}    1
    Workload Planned Output Should Be    ${matches}[0]    ${expected_output}

Fine-tuning job detail should report its planned output
    [Documentation]    The single-workload detail endpoint classifies the fine-tuning job by the
    ...    resource it will produce, matching the project list.
    ...    Skips when the expected classification is unknown (reused workload), like the list check.
    Should Not Be Equal    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}
    IF    $TEST_FINETUNING_OUTPUT is None
        Skip    Planned-output expectation is unknown for a reused fine-tuning workload; cannot assert independently
    END
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Fine-tuning job output by id should be    ${namespace}    ${TEST_FINETUNING_WORKLOAD_ID}
    ...    ${TEST_FINETUNING_OUTPUT}

Fine-tuning job output by id should be
    [Documentation]    Assert one fine-tuning job's reported output on the detail endpoint.
    [Arguments]    ${namespace}    ${workload_id}    ${expected_output}
    ${response}=    Get AIWB workload    ${workload_id}    ${namespace}    expected_status=200
    Workload Planned Output Should Be    ${response.json()}    ${expected_output}

Each finetunable model should include GPU hardware compatibility details
    [Documentation]    Verifies every finetunable model includes meaningful GPU hardware
    ...    compatibility information: model name, a positive required GPU count, and at least
    ...    one compatible accelerator (both as IDs and human-readable names).
    ...    Skips gracefully when no models are compatible with the current cluster hardware.
    VAR    ${models}    ${TEST_RESPONSE.json()['data']}
    IF    len($models) == 0
        Skip    No finetunable models are compatible with the current cluster hardware configuration
    END
    Assert Finetunable Models Report Gpu Compatibility    ${models}

Each finetunable model should report Hugging Face token gating
    [Documentation]    Verifies every offered model reports its gating up front as a definite yes or
    ...    no. A model advertised as open when its family is in fact gated leaves the user unasked
    ...    for a token and the job fails on the weight pull.
    ...    Skips gracefully when no models are compatible with the current cluster hardware.
    VAR    ${models}    ${TEST_RESPONSE.json()['data']}
    IF    len($models) == 0
        Skip    No finetunable models are compatible with the current cluster hardware configuration
    END
    Assert Finetunable Models Report Hf Token Gating    ${models}

Every base model should say whether it can produce an adapter
    [Documentation]    Verifies every offered base model reports how it trains. A user choosing
    ...    a base model has to know before committing GPU time whether the run can leave a
    ...    reusable adapter behind, and a model that stays silent forces them to guess.
    ...    Skips gracefully when the cluster offers no finetunable base models at all.
    VAR    ${models}    ${TEST_RESPONSE.json()['data']}
    IF    len($models) == 0
        Skip    No finetunable models are configured for this cluster
    END
    Assert Finetunable Models Report Training Type    ${models}

Each finetunable model should report the training settings its recipe defines
    [Documentation]    Verifies every offered base model reports the batch size, epoch count and
    ...    learning-rate multiplier its own recipe trains with, so a user setting up a run starts
    ...    from what the recipe already does instead of blank fields. A setting the recipe never
    ...    defines is reported as null rather than filled in with a guess.
    ...    Skips gracefully when the cluster offers no finetunable base models at all.
    VAR    ${models}    ${TEST_RESPONSE.json()}[data]
    IF    len($models) == 0
        Skip    No finetunable models are configured for this cluster
    END
    Assert Models Report Recipe Settings    ${models}

Each model that trains with LoRA should report its LoRA settings
    [Documentation]    Verifies a base model whose run tunes LoRA offers the rank, alpha and
    ...    dropout it will train with. Offering the model without them leaves the user inventing
    ...    values for controls the run is going to use either way.
    ...    Skips when no base model offered on this cluster trains with LoRA.
    VAR    ${models}    ${TEST_RESPONSE.json()}[data]
    ${lora_models}=    Models That Train With Lora    ${models}
    IF    len($lora_models) == 0
        Skip    No base model offered on this cluster trains with LoRA
    END
    Assert Lora Models Report Lora Settings    ${models}

Each model that trains full-parameter should report no LoRA settings
    [Documentation]    Verifies a base model that trains every weight offers no LoRA settings at
    ...    all. Such a run has no LoRA to tune and a job asking it to is refused, so showing the
    ...    controls would offer the user something they cannot act on.
    ...    Skips when every base model offered on this cluster trains with LoRA.
    VAR    ${models}    ${TEST_RESPONSE.json()}[data]
    ${full_models}=    Models That Train Full Parameter    ${models}
    IF    len($full_models) == 0
        Skip    Every base model offered on this cluster trains with LoRA
    END
    Assert Full Parameter Models Report No Lora Settings    ${models}

A fine-tuning job is submitted with the settings its base model reports
    [Documentation]    Starts a run on the cheapest offered base model using the very settings
    ...    that model advertises, so acceptance shows the numbers a user is shown are numbers
    ...    they can submit unchanged.
    ...    Fails rather than skips when the chosen model advertises nothing: every offered recipe
    ...    declares an epoch count and a learning-rate multiplier, so an empty set is the listing
    ...    failing to read the recipe — the very regression this scenario exists to catch.
    ...    Sets: TEST_RESPONSE, TEST_FINETUNING_WORKLOAD_ID
    Should Not Be Empty    ${TEST_DATASET_ID}    msg=Dataset ID is required for fine-tuning.
    ${base_model_name}=    Get smallest finetunable catalog model
    ${response}=    Get finetunable models    expected_status=200
    ${reported}=    Job Settings From Reported Settings    ${response.json()}[data]    ${base_model_name}
    Should Not Be Empty    ${reported}
    ...    msg=Base model ${base_model_name} advertises no training settings at all, so a user choosing it is shown blank fields with nothing to submit back.
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    ${finetune_data}=    Create Dictionary
    ...    displayName=reported-settings-${suffix}
    ...    datasetId=${TEST_DATASET_ID}
    Set To Dictionary    ${finetune_data}    &{reported}
    ${response}=    Finetune model    ${base_model_name}    ${finetune_data}
    ...    namespace=${namespace}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST
    VAR    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}    scope=TEST
    IF    ${response.status_code} == 202
        VAR    ${TEST_FINETUNING_WORKLOAD_ID}    ${response.json()}[workloadId]    scope=TEST
    END

The fine-tuning job should be accepted
    [Documentation]    A run a user could plausibly start from what a base model tells them must
    ...    be accepted. A refusal means the values the user is shown when choosing that model
    ...    describe something other than the run they can actually start.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    202
    ...    msg=A fine-tuning job built from the base model's own reported settings was refused: ${TEST_RESPONSE.text}

A fine-tuning job is submitted without any training settings
    [Documentation]    Starts a run on the cheapest offered base model naming nothing but the
    ...    dataset, the way a user who accepts what they are shown does. Remembers what that base
    ...    model reports so the run can be held to it.
    ...    Fails rather than skips when the chosen model advertises nothing: every offered recipe
    ...    declares an epoch count and a learning-rate multiplier, so an empty set is the listing
    ...    failing to read the recipe.
    ...    Sets: TEST_RESPONSE, TEST_FINETUNING_WORKLOAD_ID, TEST_FINETUNING_REPORTED_SETTINGS
    Should Not Be Empty    ${TEST_DATASET_ID}    msg=Dataset ID is required for fine-tuning.
    ${base_model_name}=    Get smallest finetunable catalog model
    ${response}=    Get finetunable models    expected_status=200
    ${reported}=    Job Settings From Reported Settings    ${response.json()}[data]    ${base_model_name}
    Should Not Be Empty    ${reported}
    ...    msg=Base model ${base_model_name} advertises no training settings at all, so there is nothing a run started against it could be held to.
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    ${finetune_data}=    Create Dictionary
    ...    displayName=recipe-settings-${suffix}
    ...    datasetId=${TEST_DATASET_ID}
    ${response}=    Finetune model    ${base_model_name}    ${finetune_data}
    ...    namespace=${namespace}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST
    VAR    ${TEST_FINETUNING_REPORTED_SETTINGS}    ${reported}    scope=TEST
    VAR    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}    scope=TEST
    IF    ${response.status_code} == 202
        VAR    ${TEST_FINETUNING_WORKLOAD_ID}    ${response.json()}[workloadId]    scope=TEST
    END

The fine-tuning job should train with the settings its base model reports
    [Documentation]    The started run has to be training at the numbers the user was shown for
    ...    the base model they chose, not at numbers the platform picked for them.
    ...    The effective settings are deliberately not returned by the API, so they are read back
    ...    from the configuration the run itself was started with.
    ...    Requires: TEST_FINETUNING_WORKLOAD_ID, TEST_FINETUNING_REPORTED_SETTINGS
    Should Not Be Equal    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}
    ...    msg=No fine-tuning job was started, so there is no run to check.
    ${namespace}=    Get Project Namespace
    ${training_config}=    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Training configuration of fine-tuning run    ${TEST_FINETUNING_WORKLOAD_ID}    ${namespace}
    Trained Settings Should Match Reported Settings    ${training_config}    ${TEST_FINETUNING_REPORTED_SETTINGS}

Training configuration of fine-tuning run
    [Documentation]    Helper for polling: returns the training configuration a started run was
    ...    launched with. Everything a run creates is stamped with the run's id, and the
    ...    configuration it reads at startup is published among those resources moments after
    ...    the submission is accepted.
    [Tags]    kubectl
    [Arguments]    ${workload_id}    ${namespace}
    ${result}=    Run Process    kubectl    get    configmap
    ...    -n    ${namespace}    -l    airm.silogen.ai/workload-id\=${workload_id}
    ...    -o    json    stderr=PIPE    timeout=30s
    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Could not read the configuration of fine-tuning run ${workload_id} in ${namespace}: ${result.stderr}
    ${published}=    Evaluate    json.loads($result.stdout)    modules=json
    ${training_config}=    Training Configuration Of Run    ${published}[items]
    RETURN    ${training_config}

The fine-tuning job should run on a GPU its base model supports
    [Documentation]    A base model may offer different settings per GPU family, each written for
    ...    that hardware's memory and GPU count. On a cluster with more than one family, a run that
    ...    lands on another family's GPUs can run out of memory or never start. The shared
    ...    fine-tuning run always trains the smallest catalog model, so the GPUs that model reports
    ...    are the ones its run must be on.
    ...    Skips when the model's settings name no GPU, since then any GPU is the right one.
    ...    Requires: TEST_FINETUNING_WORKLOAD_ID
    [Tags]    kubectl
    ${base_model_name}=    Get smallest finetunable catalog model
    ${response}=    Get finetunable models    expected_status=200
    ${supported_gpus}=    Get Base Model Supported Gpus    ${response.json()}[data]    ${base_model_name}
    IF    not $supported_gpus
        Skip    Base model ${base_model_name} names no GPU its settings were written for, so any GPU is the right one
    END
    ${namespace}=    Get Project Namespace
    ${node}=    Wait Until Keyword Succeeds    10 min    10 sec
    ...    Node running fine-tuning run    ${TEST_FINETUNING_WORKLOAD_ID}    ${namespace}
    Node Should Have A Supported Gpu    ${node}    ${supported_gpus}

Node running fine-tuning run
    [Documentation]    Helper for polling: returns the node a run's training pod was placed on.
    ...    The run stamps its id on the job it creates, and the job's pods are found through it.
    [Tags]    kubectl
    [Arguments]    ${workload_id}    ${namespace}
    ${jobs}=    Run Process    kubectl    get    jobs
    ...    -n    ${namespace}    -l    airm.silogen.ai/workload-id\=${workload_id}
    ...    -o    json    stderr=PIPE    timeout=30s
    Should Be Equal As Integers    ${jobs.rc}    0
    ...    msg=Could not read the jobs of fine-tuning run ${workload_id} in ${namespace}: ${jobs.stderr}
    ${job_name}=    Name Of Fine Tuning Job    ${{json.loads($jobs.stdout)["items"]}}
    ${pods}=    Run Process    kubectl    get    pods
    ...    -n    ${namespace}    -l    batch.kubernetes.io/job-name\=${job_name}
    ...    -o    json    stderr=PIPE    timeout=30s
    Should Be Equal As Integers    ${pods.rc}    0
    ...    msg=Could not read the pods of fine-tuning job ${job_name} in ${namespace}: ${pods.stderr}
    ${node_name}=    Node Running Fine Tuning Job    ${{json.loads($pods.stdout)["items"]}}
    ${node}=    Run Process    kubectl    get    node    ${node_name}
    ...    -o    json    stderr=PIPE    timeout=30s
    Should Be Equal As Integers    ${node.rc}    0
    ...    msg=Could not read node ${node_name}: ${node.stderr}
    RETURN    ${{json.loads($node.stdout)}}

A base model that cannot produce an adapter is offered
    [Documentation]    Selects a base model whose recipe trains every weight and so has no
    ...    adapter to keep. Skips when the cluster offers no such model — without one the
    ...    refusal under test cannot be provoked at all.
    ...    Sets: TEST_FULL_TRAINING_BASE_MODEL
    ${response}=    Get finetunable models    expected_status=200
    ${canonical_name}=    Get Full Training Base Model    ${response.json()['data']}
    IF    not $canonical_name
        Skip    No base model offered on this cluster trains full-parameter — cannot exercise the adapter refusal
    END
    VAR    ${TEST_FULL_TRAINING_BASE_MODEL}    ${canonical_name}    scope=TEST
    Log    Selected full-parameter base model: ${canonical_name}    INFO

An adapter is requested from that base model
    [Documentation]    Submits a fine-tuning job that is valid in every respect except that it
    ...    asks a full-parameter base model to keep an adapter, so any refusal is attributable
    ...    to the adapter request alone.
    VAR    &{adapter_request}    output=adapter
    Fine-tuning job for the full-parameter base model is submitted    ${adapter_request}

LoRA settings are requested for that base model
    [Documentation]    Submits a fine-tuning job that is valid in every respect except that it
    ...    tunes LoRA hyperparameters on a base model that trains every weight and therefore
    ...    has none.
    VAR    &{lora}    rank=${16}    alpha=${32}
    VAR    &{lora_request}    lora=${lora}
    Fine-tuning job for the full-parameter base model is submitted    ${lora_request}

Fine-tuning job for the full-parameter base model is submitted
    [Documentation]    Internal helper for the refusal scenarios: submits an otherwise-valid job
    ...    against the selected full-parameter base model with the given extra request fields.
    ...    Records how many fine-tuning jobs the project held immediately beforehand, so a later
    ...    "no job started" check holds without assuming the project was empty.
    ...    Sets: TEST_RESPONSE, TEST_FINE_TUNING_JOB_COUNT
    [Arguments]    ${extra_fields}
    Should Not Be Equal    ${TEST_FULL_TRAINING_BASE_MODEL}    ${None}
    ...    msg=No full-parameter base model selected — call "a base model that cannot produce an adapter is offered" first
    Should Not Be Empty    ${TEST_DATASET_ID}
    ...    msg=Dataset ID not set — call "Finetune dataset exists" first
    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    ${finetune_data}=    Create Dictionary
    ...    displayName=finetuned-model-${suffix}
    ...    datasetId=${TEST_DATASET_ID}
    ...    batchSize=2
    ...    learningRate=1.41421
    ...    epochs=1
    Set To Dictionary    ${finetune_data}    &{extra_fields}
    ${jobs_before}=    Fine-tuning job count in namespace    ${namespace}
    VAR    ${TEST_FINE_TUNING_JOB_COUNT}    ${jobs_before}    scope=TEST
    ${response}=    Finetune model    ${TEST_FULL_TRAINING_BASE_MODEL}    ${finetune_data}
    ...    namespace=${namespace}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Fine-tuning job count in namespace
    [Documentation]    Internal helper: how many fine-tuning jobs the project currently holds.
    ...    Reads the reported total rather than the page, so the count does not silently
    ...    saturate once the project holds more jobs than fit on one page.
    [Arguments]    ${namespace}
    ${response}=    Get AIWB workloads    namespace=${namespace}    workload_type=FINE_TUNING
    ...    expected_status=200
    VAR    ${body}    ${response.json()}
    ${pagination}=    Get From Dictionary    ${body}    pagination
    RETURN    ${pagination}[total]

The request should be refused with a reason that names an alternative
    [Documentation]    A refusal is only useful if it says which base model cannot do this and
    ...    what to choose instead. One that does neither leaves the user retrying the same
    ...    request against the same model.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    400
    ...    msg=Expected the request to be refused, got ${TEST_RESPONSE.status_code}
    VAR    ${body}    ${TEST_RESPONSE.json()}
    Should Contain    ${body}[detail]    ${TEST_FULL_TRAINING_BASE_MODEL}
    ...    msg=The refusal does not say which base model cannot do this
    Should Contain    ${body}[detail]    lora
    ...    msg=The refusal does not point at the kind of base model that can

No fine-tuning job should have started
    [Documentation]    A refused request must leave the project exactly as it found it. A job
    ...    that starts and is only then rejected has already taken GPU capacity from the queue.
    Should Not Be Equal    ${TEST_FINE_TUNING_JOB_COUNT}    ${None}
    ...    msg=No job count captured — the submitting keyword records it before sending
    ${namespace}=    Get Project Namespace
    ${jobs_now}=    Fine-tuning job count in namespace    ${namespace}
    Should Be Equal As Integers    ${jobs_now}    ${TEST_FINE_TUNING_JOB_COUNT}
    ...    msg=The project gained a fine-tuning job even though the request was refused

The project should hold no adapter from that fine-tuning run
    [Documentation]    Verifies the project's adapter list holds nothing attributable to the
    ...    fine-tuning run. A run that was never asked for an adapter must not leave one behind
    ...    for the user to find, name, or clean up.
    Should Not Be Equal    ${TEST_FINETUNING_WORKLOAD_ID}    ${None}
    ...    msg=No finetuning workload ID set — call "A finetuning workload exists" first
    ${namespace}=    Get Project Namespace
    # Positive control: seed an artifact carrying the workload-id label the check matches on,
    # and prove the check actually flags it. Without this, an empty adapter list -- or a label
    # the platform stopped stamping -- would report an absence the check was never able to detect.
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${control_workload_id}    e2e-attribution-control-${suffix}
    Apply AIMArtifact CR    e2e-control-adapter-${suffix}    ${namespace}    workload_id=${control_workload_id}
    ${control_response}=    List Artifacts    ${namespace}    expected_status=200    type=adapter
    ${control_adapters}=    Get From Dictionary    ${control_response.json()}    data
    Run Keyword And Expect Error    *
    ...    Assert No Adapter Attributable To Workload    ${control_adapters}    ${control_workload_id}
    ${response}=    List Artifacts    ${namespace}    expected_status=200    type=adapter
    ${adapters}=    Get From Dictionary    ${response.json()}    data
    Assert No Adapter Attributable To Workload    ${adapters}    ${TEST_FINETUNING_WORKLOAD_ID}
