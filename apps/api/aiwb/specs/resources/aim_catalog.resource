# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test templates for AIM catalog testing.
...                 These templates contain all test logic for end-to-end AIM testing.
...                 Python orchestration layer only controls which models to test and in what order.
...
...                 Each template implements a specific test scenario:
...                 - Deploy: Deploy AIM and verify AIM service creation
...                 - Running State: Verify deployment reaches Running status
...                 - Inference: Test inference via external endpoint
...                 - Metrics: Verify AIM service details and resources
...                 - Undeploy: Remove deployment and verify cleanup

Resource            aiwb_aims.resource
Resource            aims/api_keys.resource
Resource            api/aims.resource
Resource            api/models.resource
Library             Collections
Library             RequestsLibrary
Library             OperatingSystem
Library             Process
Library             TestPrefix
Library             libraries/CatalogProjectCleanup.py


*** Variables ***
# Catalog configuration defaults. Defined here, not only in the importing suite, because the
# keywords below read them: a suite that imports this resource without redeclaring every one
# of them fails at run time with "Variable '${...}' not found". A suite may still override any
# of these in its own Variables table, and the listener overrides MAX_GPU_COUNT per run.
${TEST_MODE}                        full    # full, smoke, or quick
${MAX_GPU_COUNT}                    1    # Raised by the listener to the max across discovered models
${AIM_DEPLOY_TIMEOUT}               5400    # Seconds to reach Running; covers a first-time 671B pull
${AIM_CATALOG_MODEL}                ${None}    # One image name to test; ${None} tests all Ready AIMs
${SELECTED_AIM_RECORD}              ${None}    # Exact Ready AIM resolved by the listener for one-model runs
${SELECTED_AIM_IMAGE}               ${None}    # Exact Docker reference reused through the selected lifecycle
${SELECTED_AIM_HF}                  ${False}    # HuggingFace token requirement for the selected AIM

# Track AIM state for catalog tests
@{DEPLOYED_AIMS_LIST}               @{EMPTY}
&{DEPLOYED_AIM_NAMES}               &{EMPTY}

# Image pull secret for private ghcr.io/silogen AIM images. Two ways to provide it,
# both work for `uv run robot`:
#   1. Value from CLI (masked):  --variable "PULL_SECRET_VALUE: Secret:$REGCRED_DOCKERCONFIGJSON"
#   2. Copy an existing secret from another namespace (default e2e-test-runner).
# Leave ${PULL_SECRET} empty to skip pull secrets entirely (public images).
${PULL_SECRET}                      regcred
${PULL_SECRET_SOURCE}              e2e-test-runner
${PULL_SECRET_VALUE: Secret}       %{PULL_SECRET_VALUE=}


*** Keywords ***
Test Template: Deploy AIM Model
    [Documentation]    Test template for deploying an AIM model.
    ...                This template:
    ...                - Ensures project exists with user access (Given)
    ...                - Ensures HuggingFace token secret exists if needed (Given)
    ...                - Looks up the AIM by image name (substring match on spec.image)
    ...                - Prepares deployment configuration
    ...                - Deploys the AIM (When)
    ...                - Verifies AIM service is created (Then)
    ...
    ...                Args:
    ...                - docker_image: Full docker image reference (e.g., ghcr.io/silogen/aim-foo:0.11.0)
    ...                - requires_hf_token: Boolean indicating if HuggingFace token is required
    [Arguments]    ${docker_image}    ${requires_hf_token}

    Log    Deploying AIM: ${docker_image} (HF token required: ${requires_hf_token})    INFO

    # GIVEN - Ensure prerequisites (each test is self-contained)
    ${catalog_project}=    Test Name    aim-catalog
    A ready project "${catalog_project}" with user access exists
    Project quota is set to    gpu_count=${MAX_GPU_COUNT}
    IF    ${requires_hf_token}
        HuggingFace token secret exists in namespace
    END

    # Look up AIM by docker image reference; need both resource_name (for deploy)
    # and spec.aimId (for the profile precondition check below).
    ${aim}=    Find AIM record by image name    ${docker_image}
    ${aim_resource_name}=    Set Variable    ${aim}[metadata][name]
    ${aim_id}=    Set Variable    ${aim}[spec][aimId]
    ${namespace}=    Get Project Namespace

    # Precondition: cluster must publish v1alpha2 AIMClusterProfiles for this aimId.
    # Pre-PR-#4019 the deploy passed allowUnoptimized=True so aim-engine would fall
    # back to any profile in the catalog; v1alpha2 dropped that knob, so an
    # under-provisioned catalog now surfaces as a clean skip with a concrete
    # remediation instead of an opaque deploy failure.
    Skip if no cluster profiles for AIM    ${aim_id}

    # Prepare deployment configuration. imagePullSecrets lets the kserve predictor pods pull
    # private ghcr.io/silogen images; the secret itself is provisioned in suite setup. When
    # ${PULL_SECRET} is empty the field is omitted entirely (public images).
    ${deploy_data}=    Create Dictionary    replicas=1
    IF    $PULL_SECRET
        ${pull_secrets}=    Create List    ${PULL_SECRET}
        Set To Dictionary    ${deploy_data}    imagePullSecrets=${pull_secrets}
    END

    # Add HF token secret if required by this model
    IF    ${requires_hf_token}
        Set To Dictionary    ${deploy_data}    hfToken=${HF_TOKEN_SECRET_NAME}
        Log    Added HF token secret ${HF_TOKEN_SECRET_NAME} to deployment configuration    DEBUG
    END

    # Deploy the AIM (creates an AIMService)
    ${response}=    Deploy AIM
    ...    ${aim_resource_name}
    ...    ${deploy_data}
    ...    ${namespace}
    ...    expected_status=any

    # Handle both new deployment (202) and already deployed (409)
    IF    ${response.status_code} == 202
        # New deployment - extract AIM service ID
        ${json}=    Set Variable    ${response.json()}
        ${service_id}=    Get From Dictionary    ${json}    id

        # Track deployed AIM service for cleanup
        Append To List    ${DEPLOYED_AIMS_LIST}    ${service_id}

        Log    Created new AIM service ${service_id} for ${docker_image}    INFO
    ELSE IF    ${response.status_code} == 409
        # Already deployed - get existing service
        Log    AIM ${docker_image} already deployed, using existing service    WARN
        ${service_id}=    Get existing workload ID for AIM    ${aim_resource_name}

        # Track deployed AIM service for cleanup
        Append To List    ${DEPLOYED_AIMS_LIST}    ${service_id}

        Log    Using existing AIM service ${service_id} for ${docker_image}    INFO
    ELSE
        Fail    Unexpected status code ${response.status_code} when deploying AIM ${docker_image}
    END

    # Preserve the K8s AIMService name in suite scope so teardown can still verify
    # predictor deletion after the API resource has already become 404.
    ${service}=    Get AIM Service By ID    ${service_id}    expected_status=200
    ${service_metadata}=    Get From Dictionary    ${service.json()}    metadata
    ${service_name}=    Get From Dictionary    ${service_metadata}    name
    Set To Dictionary    ${DEPLOYED_AIM_NAMES}    ${service_id}=${service_name}

    # Set variables for subsequent tests
    Set Test Variable    ${TEST_AIM_ID}    ${service_id}
    Set Test Variable    ${TEST_AIM_NAME}    ${aim_resource_name}

    # Verify AIM service exists
    ${response}=    Get AIM Service By ID    ${service_id}    expected_status=200
    Should Not Be Empty    ${response.json()}    msg=AIM service ${service_id} should exist

    # Ensure API key exists for this test (creates if needed, reuses existing)
    Api key exists for user

    # Assign API key to this AIM for external endpoint access
    Api key is assigned to AIMS model
    Log    Assigned API key to AIM ${docker_image}    DEBUG

    Log    Successfully deployed AIM ${docker_image} with service ID ${service_id}    INFO

Test Template: Verify AIM Running State
    [Documentation]    Test template for verifying AIM reaches Running state.
    ...                This template:
    ...                - Verifies AIM is deployed (Given - fails if not)
    ...                - Waits for the deployed AIM service to reach Running status
    ...                - Verifies service has proper status
    ...                - Fails fast if service enters Failed or Degraded state
    ...
    ...                Args:
    ...                - docker_image: Full docker image reference for logging purposes
    [Arguments]    ${docker_image}

    # GIVEN - Verify prerequisites from previous test
    AIM "${docker_image}" is deployed

    Log    Waiting for AIM ${docker_image} (service ${TEST_AIM_ID}) to reach Running state    INFO

    # Wait for AIM service to reach Running state (uses aiwb_aims keyword with fast-fail)
    Wait for AIM workload to reach state    Running    timeout=${AIM_DEPLOY_TIMEOUT}    interval=10

    Log    AIM ${docker_image} successfully reached Running state    INFO

Test Template: Run AIM Inference
    [Documentation]    Test template for running inference on a deployed AIM.
    ...                This template:
    ...                - Verifies AIM is Running (Given - fails if not)
    ...                - Gets external endpoint from AIM service
    ...                - Lists available models from endpoint
    ...                - Runs a simple inference request
    ...                - Verifies response is valid
    ...
    ...                Args:
    ...                - docker_image: Full docker image reference
    [Arguments]    ${docker_image}

    Log    Testing inference for AIM ${docker_image}    INFO

    # GIVEN - Verify prerequisites from previous test
    AIM "${docker_image}" is Running

    # Ensure API key exists for this test (self-contained)
    Api key exists for user

    # Assign API key to this AIM for external endpoint access
    Api key is assigned to AIMS model
    Key assignment should succeed
    Log    API key assigned for inference testing    DEBUG

    # Get AIM service details to get inference endpoint
    ${response}=    Get AIM Service By ID    ${TEST_AIM_ID}    expected_status=200
    ${json}=    Set Variable    ${response.json()}

    # Prefer internal endpoint when running inside K8s (external is unreachable from in-cluster)
    Dictionary Should Contain Key    ${json}    endpoints    msg=AIM service should have endpoints field
    ${endpoints}=    Get From Dictionary    ${json}    endpoints
    Should Not Be Equal    ${endpoints}    ${None}    msg=AIM service endpoints should not be None
    ${in_cluster}=    Evaluate    __import__('os').path.exists('/var/run/secrets/kubernetes.io/serviceaccount/token')
    ${has_internal}=    Run Keyword And Return Status    Dictionary Should Contain Key    ${endpoints}    internal
    IF    ${in_cluster} and ${has_internal}
        ${inference_host}=    Get From Dictionary    ${endpoints}    internal
        Log    Running in-cluster, using internal endpoint: ${inference_host}    INFO
    ELSE
        Dictionary Should Contain Key    ${endpoints}    external    msg=Endpoints should contain external
        ${inference_host}=    Get From Dictionary    ${endpoints}    external
        Should Not Be Empty    ${inference_host}    msg=external endpoint should not be empty
        Log    Using external endpoint: ${inference_host}    DEBUG
    END

    # List available models from endpoint (using API key)
    Api key binding should take effect    host=${inference_host}
    ${models}=    List models from external endpoint    ${inference_host}    ${TEST_AIM_ID}    ${TEST_API_KEY_VALUE}
    Should Be True    isinstance($models, list)    msg=Models data should be a list
    ${model_count}=    Get Length    ${models}
    Should Be True    ${model_count} > 0    msg=Endpoint should return at least one model

    # Get the first available model name for inference
    ${model_data}=    Get From List    ${models}    0
    ${model_id}=    Get From Dictionary    ${model_data}    id

    Log    Running inference with model: ${model_id}    DEBUG

    # Run a simple inference request
    ${inference_response}=    Run simple inference    ${inference_host}    ${model_id}    ${TEST_AIM_ID}

    # Verify inference response
    Should Not Be Empty    ${inference_response}    msg=Inference response should not be empty
    Log    Inference completed successfully for ${docker_image}    INFO

Test Template: Verify AIM Metrics
    [Documentation]    Test template for verifying AIM service details are complete.
    ...                This template:
    ...                - Verifies AIM is Running (Given - fails if not)
    ...                - Verifies AIM service has complete metadata, spec, and status
    ...                - Checks endpoints are populated
    ...                - Verifies model spec information
    ...
    ...                Args:
    ...                - docker_image: Full docker image reference
    [Arguments]    ${docker_image}

    Log    Verifying details for AIM ${docker_image}    INFO

    # GIVEN - Verify prerequisites from previous test
    AIM "${docker_image}" is Running

    # Get AIM service details
    ${response}=    Get AIM Service By ID    ${TEST_AIM_ID}    expected_status=200
    ${json}=    Set Variable    ${response.json()}

    # Verify core AIM service fields exist
    Dictionary Should Contain Key    ${json}    id    msg=AIM service should have id
    Dictionary Should Contain Key    ${json}    metadata    msg=AIM service should have metadata
    Dictionary Should Contain Key    ${json}    spec    msg=AIM service should have spec
    Dictionary Should Contain Key    ${json}    status    msg=AIM service should have status
    Dictionary Should Contain Key    ${json}    endpoints    msg=AIM service should have endpoints

    # Verify metadata
    ${metadata}=    Get From Dictionary    ${json}    metadata
    Dictionary Should Contain Key    ${metadata}    name    msg=Metadata should have name
    Dictionary Should Contain Key    ${metadata}    namespace    msg=Metadata should have namespace

    # Verify spec contains model info
    ${spec}=    Get From Dictionary    ${json}    spec
    Dictionary Should Contain Key    ${spec}    model    msg=Spec should have model field
    ${model}=    Get From Dictionary    ${spec}    model
    Dictionary Should Contain Key    ${model}    name    msg=Model should have name field

    # Verify status is Running
    ${status_dict}=    Get From Dictionary    ${json}    status
    ${status}=    Get From Dictionary    ${status_dict}    status
    Should Be Equal    ${status}    Running    msg=AIM service should be Running

    # Verify endpoints are populated (should be when Running)
    ${endpoints}=    Get From Dictionary    ${json}    endpoints
    Should Not Be Equal    ${endpoints}    ${None}    msg=Endpoints should not be None when Running
    Dictionary Should Contain Key    ${endpoints}    external    msg=Endpoints should have external field
    ${external}=    Get From Dictionary    ${endpoints}    external
    Should Not Be Empty    ${external}    msg=External endpoint should not be empty when Running

    Log    Details verification passed for ${docker_image}    INFO

Test Template: Undeploy AIM Model
    [Documentation]    Test template for undeploying an AIM model.
    ...                This template:
    ...                - Verifies AIM is deployed (Given - fails if not)
    ...                - Sends undeploy request
    ...                - Waits for AIM service to be deleted
    ...                - Verifies cleanup from database
    ...                - Verifies cleanup from Kubernetes
    ...
    ...                Args:
    ...                - docker_image: Full docker image reference
    [Arguments]    ${docker_image}

    Log    Undeploying AIM ${docker_image}    INFO

    # GIVEN - Verify prerequisites from previous test
    AIM "${docker_image}" is deployed
    ${namespace}=    Get Project Namespace

    # Get AIM service details for Kubernetes verification later
    ${response}=    Get AIM Service By ID    ${TEST_AIM_ID}    expected_status=200
    ${service_data}=    Set Variable    ${response.json()}
    ${metadata}=    Get From Dictionary    ${service_data}    metadata
    ${service_name}=    Get From Dictionary    ${metadata}    name

    # Send undeploy request (uses service_id and namespace)
    ${response}=    Undeploy AIM
    ...    ${TEST_AIM_ID}
    ...    ${namespace}
    ...    expected_status=204

    Log    Undeploy request sent for AIM ${docker_image}    DEBUG

    # Wait for AIM service to reach Deleted state or be removed (up to 60 seconds)
    Wait for catalog AIM workload to reach state    Deleted    timeout=60    interval=5    workload_id=${TEST_AIM_ID}

    # Verify AIM service is removed from database
    ${response}=    Get AIM Service By ID    ${TEST_AIM_ID}    expected_status=any
    IF    ${response.status_code} == 404
        Log    AIM service ${TEST_AIM_ID} removed from database    DEBUG
    ELSE IF    ${response.status_code} == 200
        ${json}=    Set Variable    ${response.json()}
        ${status_dict}=    Get From Dictionary    ${json}    status
        ${status}=    Get From Dictionary    ${status_dict}    status
        Should Be Equal    ${status}    Deleted
        ...    msg=AIM service should have Deleted status
        Log    AIM service ${TEST_AIM_ID} marked as Deleted in database    DEBUG
    ELSE
        Fail    Unexpected status code: ${response.status_code}
    END

    # Verify deployment removed from Kubernetes
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Verify AIM deployment gone    ${service_name}    ${namespace}

    # Remove from tracking list
    ${list_contains}=    Run Keyword And Return Status
    ...    List Should Contain Value    ${DEPLOYED_AIMS_LIST}    ${TEST_AIM_ID}
    IF    ${list_contains}
        Remove Values From List    ${DEPLOYED_AIMS_LIST}    ${TEST_AIM_ID}
    END

    Log    Successfully undeployed AIM ${docker_image}    INFO

# Helper keywords for catalog testing

AIM "${image_name}" is deployed
    [Documentation]    Verifies that an AIM has been deployed (AIM service exists).
    ...                Accepts full docker image reference or short image name.
    ...                Sets TEST_AIM_NAME and TEST_AIM_ID variables.
    ...                Skips the test (rather than failing) when the AIM is not deployed,
    ...                so that dependent steps show as SKIP when deploy itself failed.
    ${catalog_project}=    Test Name    aim-catalog
    A ready project "${catalog_project}" with user access exists

    ${aim_resource_name}=    Find AIM by image name    ${image_name}
    ${service_id}=    Get existing workload ID for AIM    ${aim_resource_name}
    Skip If    $service_id is None
    ...    Deploy step failed or AIM ${image_name} is not deployed — skipping dependent step

    Set Test Variable    ${TEST_AIM_NAME}    ${aim_resource_name}
    Set Test Variable    ${TEST_AIM_ID}    ${service_id}
    Log    AIM ${image_name} is deployed with service ${service_id}    DEBUG

AIM "${image_name}" is Running
    [Documentation]    Verifies that an AIM is in Running state.
    ...                Accepts full docker image reference or short image name.
    ...                Sets TEST_AIM_NAME and TEST_AIM_ID variables.
    ...                Skips the test when service_id is None (deploy step failed).
    ...                Fails if the AIM is deployed but not in Running state.
    ${catalog_project}=    Test Name    aim-catalog
    A ready project "${catalog_project}" with user access exists

    ${aim_resource_name}=    Find AIM by image name    ${image_name}
    ${service_id}=    Get existing workload ID for AIM    ${aim_resource_name}
    Skip If    $service_id is None
    ...    Deploy step failed or AIM ${image_name} is not deployed — skipping dependent step

    ${response}=    Get AIM Service By ID    ${service_id}    expected_status=200
    ${json}=    Set Variable    ${response.json()}
    ${status_dict}=    Get From Dictionary    ${json}    status
    ${status}=    Get From Dictionary    ${status_dict}    status

    Should Be Equal    ${status}    Running
    ...    msg=AIM ${image_name} is not Running (status: ${status})

    Set Test Variable    ${TEST_AIM_NAME}    ${aim_resource_name}
    Set Test Variable    ${TEST_AIM_ID}    ${service_id}
    Log    AIM ${image_name} is Running (service ${service_id})    DEBUG

Find AIM by image name
    [Documentation]    Finds an AIM cluster model by image name substring match on spec.image.
    ...                Returns the AIM's metadata.name (Kubernetes resource name). Fails if not found.
    ...
    ...                Accepts either a full docker image reference
    ...                (e.g., ghcr.io/silogen/aim-foo:0.11.0) or a short image name
    ...                (e.g., aim-foo). Uses substring matching so both forms work.
    [Arguments]    ${image_name}

    ${aim}=    Find AIM record by image name    ${image_name}
    RETURN    ${aim}[metadata][name]

Find AIM record by image name
    [Documentation]    Resolves an exact tag/digest-free image basename among all Ready AIMs.
    ...                One-model runs reuse the listener's exact resolved record so tags and
    ...                every lifecycle lookup cannot drift if the catalog changes mid-run.
    [Arguments]    ${image_name}

    IF    $SELECTED_AIM_RECORD != $None
        RETURN    ${SELECTED_AIM_RECORD}
    END
    ${selected}=    Resolve Ready AIM    ${image_name}
    RETURN    ${selected}[aim]

A selected Ready AIM from the catalog
    [Documentation]    Resolves the ${AIM_CATALOG_MODEL} workflow selector to one Ready AIM and
    ...                records its image name, HuggingFace-token requirement, and GPU count as
    ...                suite state for the lifecycle steps. Fails clearly when no selector is set,
    ...                so the behavioral scenario is only meaningful for a single chosen model.
    Should Not Be Equal    ${AIM_CATALOG_MODEL}    ${None}
    ...    msg=Set AIM_CATALOG_MODEL to one Ready AIM image name to run the selected-AIM lifecycle scenario

    Should Not Be Equal    ${SELECTED_AIM_RECORD}    ${None}
    ...    msg=The AIM catalog listener did not resolve the selected Ready AIM
    Log    Selected Ready AIM ${SELECTED_AIM_IMAGE} (hfToken=${SELECTED_AIM_HF}, gpus=${MAX_GPU_COUNT})    INFO

The selected AIM is deployed
    [Documentation]    Deploys the selected Ready AIM through the shared catalog deploy template.
    Test Template: Deploy AIM Model    ${SELECTED_AIM_IMAGE}    ${SELECTED_AIM_HF}

The selected AIM should reach Running state
    [Documentation]    Waits for the selected AIM to report Running through the shared template.
    Test Template: Verify AIM Running State    ${SELECTED_AIM_IMAGE}

The selected AIM should serve inference
    [Documentation]    Runs an inference request against the selected AIM's endpoint.
    Test Template: Run AIM Inference    ${SELECTED_AIM_IMAGE}

The selected AIM should be removed when undeployed
    [Documentation]    Undeploys the selected AIM and verifies cleanup through the shared template.
    Test Template: Undeploy AIM Model    ${SELECTED_AIM_IMAGE}

Skip if no cluster profiles for AIM
    [Documentation]    Lists AIMClusterProfiles filtered by aimId and skips the current test
    ...                if none are published. Use as a precondition gate in catalog deploy
    ...                templates so under-provisioned dev clusters produce a clear skip with
    ...                concrete remediation instead of an opaque deploy failure (the
    ...                v1alpha2 deploy path has no ``allowUnoptimized`` fallback).
    [Arguments]    ${aim_id}

    ${response}=    List AIM Profiles    aim_id=${aim_id}    expected_status=200
    VAR    ${profiles}    ${response.json()}[data]
    IF    not ${profiles}
        Skip    No AIMClusterProfile published for aimId '${aim_id}' on this cluster — provision the v1alpha2 profile catalog (or limit AIM_CATALOG_FILTER to AIMs the cluster supports) to enable this test.
    END

Get existing workload ID for AIM
    [Documentation]    Gets the existing AIM service ID for a deployed AIM.
    ...                Uses AIMServices API to find a service for the given model resource_name.
    [Arguments]    ${aim_resource_name}

    ${namespace}=    Get Project Namespace
    ${existing}=    Find Existing AIM Service    ${namespace}    ${aim_resource_name}
    IF    $existing == $None
        RETURN    ${None}
    END
    ${service_id}=    Get From Dictionary    ${existing}    id
    RETURN    ${service_id}

Wait for catalog AIM workload to reach state
    [Documentation]    Waits for the catalog test AIM service to reach the specified state.
    ...                Delegates to the shared polling keyword from catalog_aims.resource
    ...                after setting TEST_AIM_ID to the provided workload_id.
    [Arguments]    ${target_state}    ${timeout}=1800    ${interval}=5    ${workload_id}=${None}

    Should Not Be Equal    ${workload_id}    ${None}    msg=workload_id must be provided
    Set Test Variable    ${TEST_AIM_ID}    ${workload_id}
    Wait for AIM workload to reach state    ${target_state}    timeout=${timeout}    interval=${interval}

Run simple inference
    [Documentation]    Runs an inference request to test the model.
    ...                Automatically detects if model supports chat interface and uses appropriate endpoint.
    ...                Chat models: Tests /v1/chat/completions with instruction-following
    ...                Completion models: Tests /v1/completions with text continuation
    [Arguments]    ${external_host}    ${model_id}    ${workload_id}

    # Detect if model supports chat based on AIM metadata tags
    ${supports_chat}=    Model Supports Chat    ${TEST_AIM_NAME}

    IF    ${supports_chat}
        Log    Model supports chat - testing /v1/chat/completions endpoint    INFO
        ${response}=    Run Chat Inference    ${external_host}    ${model_id}    ${workload_id}    ${TEST_API_KEY_VALUE}
        Log    Chat inference successful: ${response}    INFO
        RETURN    ${response}
    ELSE
        Log    Model does not support chat - testing /v1/completions endpoint    INFO
        ${response}=    Run Completion Inference    ${external_host}    ${model_id}    ${workload_id}    ${TEST_API_KEY_VALUE}
        Log    Completion inference successful: ${response}    INFO
        RETURN    ${response}
    END

Ensure GHCR pull secret exists in namespace
    [Documentation]    Ensures the image pull secret exists in the project namespace so kserve
    ...                predictor pods can pull private ghcr.io/silogen images. The secret is
    ...                either created from the masked ${PULL_SECRET_VALUE} (dockerconfigjson
    ...                supplied via CLI/env) or copied from ${source_namespace} — default
    ...                e2e-test-runner, the test runner's own namespace, so no privileged
    ...                aim-system access is needed. A missing source is tolerated (warn + skip)
    ...                so public-image runs don't fail. Retries through transient OIDC 401s.
    [Arguments]    ${namespace}    ${source_namespace}=${PULL_SECRET_SOURCE}    ${secret_name}=${PULL_SECRET}

    IF    not $secret_name
        Log    No pull secret configured (PULL_SECRET empty) — assuming public images    INFO
        RETURN
    END

    Wait Until Keyword Succeeds    1 min    5 sec
    ...    Provision pull secret in namespace    ${namespace}    ${source_namespace}    ${secret_name}

Provision pull secret in namespace
    [Documentation]    Idempotent body of pull-secret provisioning, retried by the caller.
    ...                Prefers a CLI/env-supplied masked value; otherwise copies from the source
    ...                namespace. Existing secret / AlreadyExists race counts as success.
    [Arguments]    ${namespace}    ${source_namespace}    ${secret_name}

    ${existing}=    Run Process    kubectl    get    secret    ${secret_name}    -n    ${namespace}    stderr=STDOUT
    IF    ${existing.rc} == 0
        Log    Pull secret "${secret_name}" already exists in namespace ${namespace}    DEBUG
        RETURN
    END

    # Prefer a value supplied on the CLI/env (masked) over copying from another namespace.
    # Same shared helper as the HF token, just with dockerconfigjson create flags.
    ${has_value}=    Evaluate    bool($PULL_SECRET_VALUE.value)
    IF    ${has_value}
        Create secret from value    ${secret_name}    ${namespace}    ${PULL_SECRET_VALUE}
        ...    --type\=kubernetes.io/dockerconfigjson    --from-file\=.dockerconfigjson\=/dev/stdin
        RETURN
    END

    # Otherwise copy it from the source namespace (the test runner's own namespace).
    ${get_result}=    Run Process    kubectl    get    secret    ${secret_name}
    ...    -n    ${source_namespace}    -o    json    stderr=STDOUT
    IF    ${get_result.rc} != 0
        Log    Pull secret "${secret_name}" not found in ${source_namespace} — skipping copy (images may be public). ${get_result.stdout}    WARN
        RETURN
    END

    # Strip cluster-specific metadata fields so the secret can be recreated in a new namespace.
    # Wrap the result in a Secret so the credential blob is masked in logs (it is still
    # delivered to kubectl in full via stdin). Uses stdin to avoid shell quoting issues too.
    ${clean_json}=    Evaluate
    ...    __import__('robot.api.types', fromlist=['Secret']).Secret((lambda d: json.dumps({**d, 'metadata': {k: v for k, v in d['metadata'].items() if k not in ['namespace', 'resourceVersion', 'uid', 'creationTimestamp', 'ownerReferences', 'annotations']}}))(json.loads($get_result.stdout)))
    ...    json
    ${copy_result}=    Run Process    kubectl    create    -n    ${namespace}    -f    -
    ...    stdin=${clean_json}    stderr=STDOUT
    IF    $copy_result.rc == 0 or "AlreadyExists" in $copy_result.stdout
        Log    Pull secret "${secret_name}" copied from ${source_namespace} to ${namespace}    INFO
        RETURN
    END
    Fail    Failed to copy ${secret_name} to ${namespace}: ${copy_result.stdout}

Setup AIM catalog testing
    [Documentation]    Suite setup for AIM catalog testing.
    ...                Cleans up the AIM catalog test project if it exists from a previous run,
    ...                then creates a fresh one. Only touches the test project — never other projects.

    Log    Starting AIM catalog testing suite    INFO
    Log    Test mode: ${TEST_MODE}    INFO

    ${catalog_project}=    Test Name    aim-catalog

    # Clean up stale test project from previous runs (only our project, never others).
    # Waits for deletion to complete so the next step creates a truly fresh project.
    TRY
        ${response}=    Get projects    expected_status=any
        IF    ${response.status_code} == 200
            VAR    ${projects}    ${response.json()}[data]
            FOR    ${project}    IN    @{projects}
                IF    "${project}[name]" == "${catalog_project}"
                    Log    Deleting stale test project: ${project}[name] (${project}[id])    INFO
                    Delete project    ${project}[id]    expected_status=any
                    Wait Until Project Deleted    ${project}[id]    timeout=5 min
                END
            END
        END
    EXCEPT    AS    ${cleanup_error}
        Log    Pre-test cleanup: ${cleanup_error}    WARN
    END

    # Initialize tracking lists (for cleanup)
    VAR    @{DEPLOYED_AIMS_LIST}    scope=SUITE
    VAR    &{DEPLOYED_AIM_NAMES}    scope=SUITE
    VAR    @{CREATED_PROJECT_IDS}    scope=SUITE
    VAR    @{TEST_API_KEYS}    scope=SUITE

    # Create the project for testing
    A ready project "${catalog_project}" with user access exists

    # Snapshot the adopted project at SUITE scope for the teardown to delete. The creation
    # keyword publishes it through Set Test Variable, which does reach a suite teardown when
    # called from suite setup - but that is a subtle enough rule to read as a bug, and every
    # per-test call to the same keyword rebinds the name in its own scope. Capturing it here
    # makes the teardown's target explicit and independent of both, matching the suite-scope
    # convention already used by "Initialize api key test environment".
    VAR    ${CATALOG_PROJECT_ID}    ${TEST_PROJECT_ID}    scope=SUITE

    # AIM inference server images are private on ghcr.io/silogen — provision the pull secret in
    # the project namespace (from PULL_SECRET_VALUE if given, else copied from e2e-test-runner).
    ${namespace}=    Get Project Namespace
    Ensure GHCR pull secret exists in namespace    ${namespace}

    Log    AIM catalog testing suite initialized    INFO

Undeploy all tracked AIM catalog services
    [Documentation]    Undeploys every AIM service tracked in ${DEPLOYED_AIMS_LIST}: waits for
    ...    each to reach the API's Deleted state (or confirms it is already 404), then confirms
    ...    the predictor Deployment is actually gone from Kubernetes for each one — while the
    ...    project (and its namespace) still exists.
    ...
    ...    Factored out of "Cleanup AIM catalog testing" so both the suite teardown and direct
    ...    E2E regression tests can assert Kubernetes-level predictor absence before the project
    ...    namespace is deleted: kubectl against an already-deleted namespace fails "Verify AIM
    ...    deployment gone"'s own rc==0 check, which would be a false test failure rather than a
    ...    real proof of leaking cleanup.
    ${project_id}=    Get Variable Value    ${TEST_PROJECT_ID}    ${None}
    IF    $project_id is None    RETURN    END

    ${aims_count}=    Get Length    ${DEPLOYED_AIMS_LIST}
    Log    Found ${aims_count} deployed AIM services to clean up    DEBUG
    IF    ${aims_count} == 0    RETURN    END

    ${namespace}=    Get Project Namespace
    FOR    ${service_id}    IN    @{DEPLOYED_AIMS_LIST}
        ${service_name}=    Get From Dictionary    ${DEPLOYED_AIM_NAMES}    ${service_id}
        ${service}=    Get AIM Service    ${service_id}    ${namespace}    expected_status=any
        IF    ${service.status_code} == 404
            Log    AIM service ${service_id} is already absent from the API    DEBUG
        ELSE
            Should Be Equal As Integers    ${service.status_code}    200
            ...    msg=Unexpected status ${service.status_code} while reading AIM service ${service_id}

            ${response}=    Undeploy AIM
            ...    ${service_id}
            ...    ${namespace}
            ...    expected_status=any
            Should Be True    ${response.status_code} in [204, 404, 409]
            ...    msg=Unexpected status ${response.status_code} while undeploying AIM service ${service_id}

            Wait for catalog AIM workload to reach state
            ...    Deleted
            ...    timeout=120
            ...    interval=5
            ...    workload_id=${service_id}
        END
        Wait Until Keyword Succeeds    2 min    5 sec
        ...    Verify AIM deployment gone    ${service_name}    ${namespace}
        Log    AIM service ${service_id} deletion confirmed    DEBUG
    END

    VAR    @{DEPLOYED_AIMS_LIST}    scope=SUITE
    VAR    &{DEPLOYED_AIM_NAMES}    scope=SUITE

Cleanup AIM catalog testing
    [Documentation]    Suite teardown for AIM catalog testing.
    ...                Undeploys every remaining AIM and waits for its API resource and
    ...                Kubernetes deployment to disappear, then deletes test projects.
    ...                Cleans up only this suite's adopted catalog project, because standalone
    ...                execution does not run the parent directory's Suite Teardown.

    Log    Cleaning up AIM catalog testing suite    INFO
    Undeploy all tracked AIM catalog services
    Clean Up All Created Projects With Wait
    Clean Up Catalog Project
    Log    AIM catalog testing suite cleanup complete    INFO

Clean Up Catalog Project
    [Documentation]    Deletes only the catalog project this suite adopted, then drops only
    ...                that ID from global adopted tracking. See CatalogProjectCleanup.py for
    ...                why the list-scoping lives in Python and why the confirmation flag must
    ...                come from the atomic Run Keyword And Return Status rather than a
    ...                follow-up assignment.
    ...
    ...                Project cleanup is best-effort: an unconfirmed deletion warns and
    ...                returns rather than failing, because a failing suite teardown is
    ...                reported by Robot as a failure of every test in the suite. DELETE has
    ...                already been issued by that point, so "unconfirmed" means the 404 did
    ...                not arrive within the timeout, not that the server refused. The ID is
    ...                kept in tracking so a directory-level run still drains it — but a
    ...                standalone run has no directory Suite Teardown, so there the WARN is
    ...                the only signal and a genuinely failed delete needs external cleanup.
    ...
    ...                This does NOT generalize — "Undeploy all tracked AIM catalog services"
    ...                deliberately fails on incomplete deletion, since leaked GPU pods are
    ...                expensive and silent. Match the step, not the file.
    # Deleting here is safe even when both catalog suites run in one directory pass. They
    # never hold the project at the same time: Setup AIM catalog testing deletes any
    # existing project of this name and waits for that deletion BEFORE creating its own, so
    # each suite works on a project it made. Removing it at teardown is also what lets the
    # next suite's stale-project sweep find nothing and skip that wait.
    #
    # Prefer the suite-scoped snapshot, but fall back to the creation keyword's own
    # ${TEST_PROJECT_ID}. Setup takes the snapshot on the line AFTER
    # "A ready project ... exists" returns, so a setup failure inside that keyword - after
    # it created and tracked the project, while waiting for readiness or granting access -
    # leaves the snapshot unset while the project exists. Standalone runs have no directory
    # teardown to drain the tracking list, so without this fallback that project leaks.
    #
    # Both names are passed ESCAPED. Get Variable Value accepts either spelling, but its
    # documented contract is that the unescaped form works only when the variable already
    # exists - which is precisely what these two lookups cannot assume.
    ${catalog_project_id}=    Get Variable Value    \${CATALOG_PROJECT_ID}    ${None}
    IF    $catalog_project_id is None
        ${catalog_project_id}=    Get Variable Value    \${TEST_PROJECT_ID}    ${None}
    END
    IF    $catalog_project_id is None    RETURN    END

    TRY
        Delete project    ${catalog_project_id}    expected_status=any
    EXCEPT    AS    ${delete_error}
        Log    Failed to delete catalog project ${catalog_project_id}: ${delete_error}    WARN
    END

    ${deletion_confirmed}=    Run Keyword And Return Status
    ...    Wait Until Project Deleted    ${catalog_project_id}    timeout=1 min
    IF    not ${deletion_confirmed}
        Log    Catalog project ${catalog_project_id} deletion not confirmed within 1 min; it stays in adopted tracking, which a directory-level run drains from its own Suite Teardown - a standalone run has none, so delete this project manually    WARN
    END

    # No early return when the list is absent: an unconfirmed deletion still has to be
    # recorded somewhere, and setup can abort after creating the project but before
    # anything adopted it, which is exactly when the list does not exist yet.
    ${adopted}=    Get Variable Value    \${ADOPTED_PROJECT_IDS}    ${None}
    IF    $adopted is None
        @{adopted}=    Create List
    END
    ${remaining}=    Scoped Cleanup Result    ${adopted}    ${catalog_project_id}    ${deletion_confirmed}
    Set Global Variable    ${ADOPTED_PROJECT_IDS}    ${remaining}

# --- Business-layer keywords for aim_catalog_cleanup.robot ---
# The regression suite drives "Undeploy all tracked AIM catalog services" directly as its
# keyword under test; everything else it needs (deploy, predictor-exists preconditions, name
# capture, already-404 setup, API/Kubernetes absence checks) is wrapped here so the test file
# itself never calls a template, an API-layer keyword, or an inline dict lookup.

A catalog AIM is deployed for cleanup testing
    [Documentation]    Deploys a real AIM via the catalog deploy template, hiding the template's
    ...    technical argument shape (image + requires_hf_token) behind a BDD-phrased Given step.
    [Arguments]    ${docker_image}
    Test Template: Deploy AIM Model    ${docker_image}    ${False}

The catalog AIM's predictor should be running in kubernetes
    [Documentation]    Bounded-polling precondition confirming the controller-created predictor
    ...    Deployment actually exists in Kubernetes before any cleanup assertion runs. Deploying
    ...    an AIMService only waits for the API's asynchronous create to be accepted — not for
    ...    aim-engine's controller to reconcile the predictor Deployment — so a one-shot check run
    ...    immediately afterward races that reconciliation. Without this precondition, a cleanup
    ...    test that never observed the predictor existing cannot prove its later absence means
    ...    anything was actually cleaned up.
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    AIM deployment should exist in kubernetes

The deployed catalog AIM's Kubernetes name is captured
    [Documentation]    Captures the Kubernetes AIMService name tracked at deploy time
    ...    (${DEPLOYED_AIM_NAMES}) into ${TEST_AIM_SERVICE_NAME}, so later steps can verify
    ...    predictor absence without the test file reading the tracking dict directly.
    ${service_name}=    Get From Dictionary    ${DEPLOYED_AIM_NAMES}    ${TEST_AIM_ID}
    VAR    ${TEST_AIM_SERVICE_NAME}    ${service_name}    scope=TEST

The predictor Deployment for the deployed catalog AIM should no longer exist in kubernetes
    [Documentation]    Polls until the captured catalog AIM's predictor Deployment is gone from
    ...    Kubernetes. Requires "The deployed catalog AIM's Kubernetes name is captured" to have
    ...    run first.
    Variable Should Exist    ${TEST_AIM_SERVICE_NAME}
    ...    msg=TEST_AIM_SERVICE_NAME is not set - call "The deployed catalog AIM's Kubernetes name is captured" first
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Verify AIM deployment gone    ${TEST_AIM_SERVICE_NAME}    ${namespace}

Predictor absence verification should fail while the predictor exists
    [Documentation]    Negative check proving the Kubernetes-level absence assertion has teeth:
    ...    called while the captured catalog AIM's predictor Deployment is still genuinely
    ...    running, it must raise the specific "still exists" error the polling wraps — not
    ...    merely any failure — otherwise an unrelated error (auth, API outage) could satisfy
    ...    this check without ever proving the leak-detection logic itself works. Requires "The
    ...    deployed catalog AIM's Kubernetes name is captured" to have run first.
    Run Keyword And Expect Error
    ...    *The last error was: Deployment matching ${TEST_AIM_SERVICE_NAME}-*-predictor still exists in namespace *
    ...    The predictor Deployment for the deployed catalog AIM should no longer exist in kubernetes

The deployed catalog AIM should no longer exist in the API
    [Documentation]    Confirms the catalog AIM's AIMService resource reads 404 from the API.
    Get AIM Service By ID    ${TEST_AIM_ID}    expected_status=404

The deployed catalog AIM is undeployed directly via the API
    [Documentation]    Undeploys the catalog AIM through the API directly (bypassing the per-model
    ...    Undeploy test template), so the AIMService is gone from the API while suite tracking
    ...    (${DEPLOYED_AIMS_LIST}) still carries it — mirroring a model whose own Undeploy test
    ...    failed or was excluded, which is the already-404 branch "Undeploy all tracked AIM
    ...    catalog services" must still handle correctly.
    ${namespace}=    Get Project Namespace
    Undeploy AIM    ${TEST_AIM_ID}    ${namespace}    expected_status=204
    Wait for catalog AIM workload to reach state    Deleted    timeout=60    interval=5
    ...    workload_id=${TEST_AIM_ID}
