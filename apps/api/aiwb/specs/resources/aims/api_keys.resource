# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       LAYER 2: Business Logic - AIMS-specific API key management keywords.
...
...                 This resource provides high-level keywords for API key operations specific to AIMS models.
...                 It builds on top of the generic API key testing framework in resources/api_keys.resource.
...
...                 This file contains:
...                 - AIMS model deployment keywords for API key testing
...                 - API key assignment to AIMS models
...                 - AIMS model access verification with API keys
...                 - AIMS-specific lifecycle management
...                 - Dual-AIM deployment keywords for multi-model regression tests
...
...                 Usage:
...                 - Import this file for AIMS-specific API key tests
...                 - This file automatically imports the generic api_keys.resource
...                 - All generic keywords are available through this import

Resource            resources/api_keys.resource
Resource            resources/airm_keywords.resource
Resource            resources/aiwb_aims.resource
Resource            resources/airm_workloads.resource
Resource            resources/airm_projects.resource
Resource            resources/api/common.resource
Resource            resources/api/api_keys_api.resource
Library             BuiltIn
Library             Collections
Library             ModelCatalog


*** Keywords ***
# ========================================================================
# AIMS-Specific Keywords
# ========================================================================

# AIMS Deployment Keywords
An AIM model is running
    [Documentation]    Ensure an AIMS model is in Running state
    AIM is deployed and running
    # Get the external endpoint from AIM Service (AIWB API)
    ${response}=    Get AIM Service By ID    ${TEST_AIM_ID}    expected_status=200
    ${json}=    Set variable    ${response.json()}
    ${endpoints}=    Get from dictionary    ${json}    endpoints
    ${external_url}=    Get from dictionary    ${endpoints}    external
    Set test variable    ${TEST_AIM_EXTERNAL_HOST}    ${external_url}

An AIM model is running with api key
    [Documentation]    Ensure AIMS model is running and has API key assigned
    An AIM model is running
    User is authenticated
    Api key exists for user
    Api key is assigned to AIMS model
    Key assignment should succeed
    Api key binding should take effect
    # Discover model ID using the API key for auth (external endpoint requires it)
    ${models}=    List models from external endpoint    ${TEST_AIM_EXTERNAL_HOST}    ${TEST_AIM_ID}    ${TEST_API_KEY_VALUE}
    ${first_model}=    Get from list    ${models}    0
    ${model_id}=    Get from dictionary    ${first_model}    id
    Set test variable    ${TEST_AIM_MODEL_ID}    ${model_id}

# API Key Assignment Keywords for AIMS
Api key is assigned to AIMS model
    [Documentation]    Assign API key to a single AIMS model using AIWB API
    ...    Convenience wrapper around "Api key is assigned to AIMS models" for the
    ...    common single-model case.
    ...    Can specify api_key and aim_id or use defaults (TEST_API_KEY, TEST_AIM_ID)
    [Arguments]    ${api_key}=${TEST_API_KEY}    ${aim_id}=${TEST_AIM_ID}

    Should not be empty    ${aim_id}
    ...    msg=AIM service ID required - pass aim_id= or ensure TEST_AIM_ID is set

    @{aim_ids}=    Create list    ${aim_id}
    Api key is assigned to AIMS models    ${aim_ids}    api_key=${api_key}

Api key is assigned to AIMS models
    [Documentation]    Assign the API key to multiple AIMS models in a single PATCH.
    ...    The API replaces the whole aimIds list on each PATCH, so calling the
    ...    singular keyword a second time would overwrite the first binding
    ...    rather than add to it — use this keyword to bind more than one model.
    [Arguments]    ${aim_ids}    ${api_key}=${TEST_API_KEY}

    Should not be empty    ${api_key}
    ...    msg=API key required - pass api_key= or ensure TEST_API_KEY is set
    Should not be empty    ${aim_ids}
    ...    msg=AIM service IDs required - pass a non-empty list of aim_ids

    ${update_data}=    Create dictionary    aimIds=${aim_ids}

    ${project}=    Get Project Namespace
    ${response}=    Update api key
    ...    ${api_key}[id]
    ...    ${update_data}
    ...    project=${project}
    ...    expected_status=any

    Set test variable    ${TEST_RESPONSE}    ${response}

Api key binding should take effect
    [Documentation]    Wait until a freshly bound API key is accepted by the model gateway.
    ...    The management API returns before the binding reaches the gateway authorizer, so
    ...    callers that bind and immediately use a key must wait for propagation.
    [Arguments]    ${host}=${TEST_AIM_EXTERNAL_HOST}    ${aim_id}=${TEST_AIM_ID}
    ...    ${api_key_value}=${TEST_API_KEY_VALUE}

    Should not be empty    ${host}
    ...    msg=Host required - pass host= or ensure TEST_AIM_EXTERNAL_HOST is set
    Should not be empty    ${api_key_value}
    ...    msg=API key value required - pass api_key_value= or ensure TEST_API_KEY_VALUE is set
    Wait until keyword succeeds    2 min    5 sec
    ...    External endpoint should accept the api key    ${host}    ${aim_id}    ${api_key_value}

External endpoint should accept the api key
    [Documentation]    Assert that the model gateway authorizes an assigned API key.
    [Arguments]    ${host}    ${aim_id}    ${api_key_value}
    ${response}=    Get models response from external endpoint
    ...    ${host}    ${aim_id}    ${api_key_value}    timeout=4
    Should be equal as integers    ${response.status_code}    200
    ...    msg=External endpoint has not accepted the bound API key yet (got ${response.status_code})

# AIMS Model Access Keywords
Request is made to AIMS model with valid api key
    [Documentation]    Make a request to AIMS model endpoint with valid API key
    ...    Can specify api_key_value and host or use defaults (TEST_API_KEY_VALUE, TEST_AIM_EXTERNAL_HOST)
    ...    Waits for a freshly assigned key before discovering the model ID and sending chat.
    [Arguments]    ${api_key_value}=${TEST_API_KEY_VALUE}    ${host}=${TEST_AIM_EXTERNAL_HOST}

    Should not be empty    ${api_key_value}
    ...    msg=API key value required - pass api_key_value= or ensure TEST_API_KEY_VALUE is set
    Should not be empty    ${host}
    ...    msg=Host required - pass host= or ensure TEST_AIM_EXTERNAL_HOST is set
    Api key binding should take effect    host=${host}    api_key_value=${api_key_value}

    # Discover model ID if not already set (external endpoint requires API key auth)
    ${model_id_set}=    Get variable value    ${TEST_AIM_MODEL_ID}    ${None}
    IF    $model_id_set is None
        # This is the first call made with a freshly created and assigned key. AIWB stores the
        # key-to-AIM binding immediately, but the gateway authorises against a cluster auth group
        # that is populated asynchronously, so the endpoint can still answer 401 for a key that is
        # perfectly valid. Verified against the live gateway that an unknown key is rejected with
        # 401 too, so a single 401 here cannot distinguish "not propagated yet" from "wrong key" —
        # poll instead of reading once, and let a genuinely bad key fail on the timeout.
        ${models}=    Wait until keyword succeeds    2 min    5 sec
        ...    List models from external endpoint    ${host}    ${TEST_AIM_ID}    ${api_key_value}
        ${first_model}=    Get from list    ${models}    0
        ${discovered_id}=    Get from dictionary    ${first_model}    id
        Set test variable    ${TEST_AIM_MODEL_ID}    ${discovered_id}
    END

    ${response}=    Send chat completion request to external endpoint
    ...    ${host}    ${TEST_AIM_MODEL_ID}    api_key=${api_key_value}

    Set test variable    ${TEST_RESPONSE}    ${response}

Request is made to AIMS model with invalid api key
    [Documentation]    Make a request to AIMS model with invalid API key
    Variable should exist    ${TEST_AIM_EXTERNAL_HOST}
    Variable should exist    ${TEST_AIM_MODEL_ID}

    ${response}=    Send chat completion request to external endpoint
    ...    ${TEST_AIM_EXTERNAL_HOST}    ${TEST_AIM_MODEL_ID}    api_key=invalid-api-key-12345

    Set test variable    ${TEST_RESPONSE}    ${response}

Request is made to AIMS model without api key
    [Documentation]    Make a request to AIMS model without API key
    Variable should exist    ${TEST_AIM_EXTERNAL_HOST}
    Variable should exist    ${TEST_AIM_MODEL_ID}

    ${response}=    Send chat completion request to external endpoint
    ...    ${TEST_AIM_EXTERNAL_HOST}    ${TEST_AIM_MODEL_ID}

    Set test variable    ${TEST_RESPONSE}    ${response}

AIMS model access works with api key
    [Documentation]    Verify that AIMS model access works with the assigned API key
    Request is made to AIMS model with valid api key
    Request should succeed

# AIMS Model Lifecycle Keywords
AIMS model is permanently deleted
    [Documentation]    Permanently delete the deployed AIMS model
    Variable should exist    ${TEST_AIM_ID}
    Variable should exist    ${TEST_PROJECT_ID}
    Undeploy AIM request is sent
    Response status should be 204
    Deployed workload should be removed

Response should contain model information
    [Documentation]    Verify that response contains valid chat completion
    Should be equal as integers    ${TEST_RESPONSE.status_code}    200
    ${response_data}=    Set variable    ${TEST_RESPONSE.json()}
    # Chat completions endpoint should return choices array
    Should contain    ${response_data}    choices

Response error message should indicate authentication failure
    [Documentation]    Verify response error message indicates authentication failure
    ...    Handles both JSON responses (from service) and non-JSON responses (from Envoy gateway)
    ${status}=    Set variable    ${TEST_RESPONSE.status_code}
    # Authentication gateways may return denial statuses without a structured JSON body.
    IF    ${status} in [401, 403, 404]
        Log    Gateway returned ${status} (expected for authentication failure)    INFO
        RETURN
    END
    # For other error codes, verify JSON error message
    ${error_response}=    Set variable    ${TEST_RESPONSE.json()}
    Should contain    ${error_response}    error
    ${error_message}=    Get from dictionary    ${error_response}    error
    ${error_lower}=    Convert to lowercase    ${error_message}
    Should contain any    ${error_lower}    unauthorized    authentication    invalid

AIMS model should reject the revoked api key
    [Documentation]    Verify that a revoked key is rejected when accessing AIMS model,
    ...    waiting up to 120 seconds for revocation to propagate through the auth cache.
    ...    The gateway returns 404 for any unknown credential (revoked or fake alike)
    ...    to avoid leaking whether a key ever existed. 401/403 may still be observed
    ...    depending on which auth layer enforces the rejection.
    Wait Until Keyword Succeeds    120s    10s    Revoked api key request should be denied

Revoked api key request should be denied
    [Documentation]    Make a request with the revoked key and assert it is rejected.
    ...    Used as the polling condition inside Wait Until Keyword Succeeds.
    # TEST_API_KEY_VALUE still holds the revoked key's value string. Send directly: this
    # path waits for rejection propagation, so it must not wait for the key to be accepted.
    ${response}=    Send chat completion request to external endpoint
    ...    ${TEST_AIM_EXTERNAL_HOST}    ${TEST_AIM_MODEL_ID}    api_key=${TEST_API_KEY_VALUE}
    Set test variable    ${TEST_RESPONSE}    ${response}
    ${status}=    Set variable    ${TEST_RESPONSE.status_code}
    Should be true    ${status} in [401, 403, 404]
    ...    Expected 401/403/404 for revoked key, got ${status}

# AIM Redeployment Keywords
Same AIM is redeployed
    [Documentation]    Redeploy the same AIM that was just undeployed
    # Use the existing deployment keyword which handles everything
    AIM is deployed and running
    # Get the new external host from AIM Service (AIWB API)
    ${response}=    Get AIM Service By ID    ${TEST_AIM_ID}    expected_status=200
    ${json}=    Set variable    ${response.json()}
    ${endpoints}=    Get from dictionary    ${json}    endpoints
    ${external_url}=    Get from dictionary    ${endpoints}    external
    Set test variable    ${TEST_AIM_EXTERNAL_HOST}    ${external_url}
    # Model ID stays the same after redeployment (same AIM, same vLLM model).
    # No need to rediscover — the old key can't auth against the new deployment anyway.

Api key should not be bound to redeployed AIM
    [Documentation]    Verify the key's model bindings don't include the redeployed AIM.
    ...    Redeployment creates a new AIM (new workload id); the key stays bound to the
    ...    OLD id, so the binding is stale. A key's ``groups`` are the bound-<workload-id>
    ...    labels — the AIM ids it is bound to — so the redeployed AIM's id must not appear.

    # ${TEST_AIM_ID} now holds the redeployed AIM's (new) id.
    # Get the key's current model bindings.
    ${project}=    Get Project Namespace
    ${key_response}=    api_keys_api.Get api key    ${TEST_API_KEY}[id]
    ...    project=${project}    expected_status=200
    ${groups}=    Get from dictionary    ${key_response.json()}    groups

    # The key was bound to the old id, so the redeployed AIM's id must not appear.
    Should not contain    ${groups}    ${TEST_AIM_ID}
    ...    API key should not be bound to the redeployed AIM's id after redeployment

Api key should still exist in system
    [Documentation]    Verify the API key still exists and is retrievable
    ${project}=    Get Project Namespace
    ${response}=    api_keys_api.Get api key    ${TEST_API_KEY}[id]
    ...    project=${project}    expected_status=200
    ${key_data}=    Set variable    ${response.json()}
    Should be equal    ${key_data}[id]    ${TEST_API_KEY}[id]

# Binding Lifecycle Keywords for AIMS
Api key should have no model bindings
    [Documentation]    Verify the API key's groups field is empty (key not bound to any AIM).
    ...    Fetches the key details and checks the groups field.
    ${project}=    Get Project Namespace
    ${response}=    api_keys_api.Get api key    ${TEST_API_KEY}[id]
    ...    project=${project}    expected_status=200
    ${key_data}=    Set variable    ${response.json()}
    Should contain    ${key_data}    groups
    ${groups}=    Get from dictionary    ${key_data}    groups
    Should be empty    ${groups}
    ...    Expected no model bindings (groups=[]), got ${groups}

Api key should be bound to the AIM
    [Documentation]    Verify the API key's groups field contains the running AIM's workload ID.
    ...    Convenience wrapper around "Api key should be bound to AIM" for TEST_AIM_ID.

    Api key should be bound to AIM "${TEST_AIM_ID}"

Api key should be bound to AIM "${aim_id}"
    [Documentation]    Verify the API key's groups field contains the given AIM service ID.
    ...    Generalizes "Api key should be bound to the AIM" for tests binding multiple AIMs,
    ...    where the binding to check is not necessarily TEST_AIM_ID.
    ${project}=    Get Project Namespace
    ${response}=    api_keys_api.Get api key    ${TEST_API_KEY}[id]
    ...    project=${project}    expected_status=200
    ${key_data}=    Set variable    ${response.json()}
    Should contain    ${key_data}    groups
    ${groups}=    Get from dictionary    ${key_data}    groups
    Should not be empty    ${groups}
    ...    Expected AIM to appear in groups, but groups is empty
    Should contain    ${groups}    ${aim_id}
    ...    Expected groups to contain AIM ID ${aim_id}, got ${groups}

Api key bindings are cleared
    [Documentation]    Unbind the API key from all AIMs by PATCHing aimIds to an empty list.
    ...    Uses the same PATCH bindings flow as assignment, but with an empty aimIds list.
    @{empty_aims}=    Create list
    ${update_data}=    Create dictionary    aimIds=${empty_aims}
    ${project}=    Get Project Namespace
    ${response}=    Update api key
    ...    ${TEST_API_KEY}[id]
    ...    ${update_data}
    ...    project=${project}
    ...    expected_status=200
    Set test variable    ${TEST_RESPONSE}    ${response}

# ========================================================================
# Dual-AIM keywords for multi-model regression tests (Bug A)
# ========================================================================

Second smallest deployable AIM resource name, profile and GPU count
    [Documentation]    Returns the model, exact profile, and GPU count of the second-smallest AIM.
    ${response}=    List AIMs    expected_status=200    status_filter=Ready    page_size=100
    VAR    ${aims_list}    ${response.json()}[data]
    ${count}=    Get Length    ${aims_list}
    Should Be True    ${count} > 1
    ...    msg=Need at least two Ready AIMs on cluster for dual-AIM regression test
    ${profiles}=    All inference profiles
    ${resource_name}    ${profile_name}    ${gpu_count}=    Get Second Smallest Deployable Aim With Profile
    ...    ${aims_list}    ${profiles}
    Log    Selected second-smallest AIM: ${resource_name} (profile: ${profile_name}, ${gpu_count} GPU)    INFO
    RETURN    ${resource_name}    ${profile_name}    ${gpu_count}

Second smallest deployable AIM resource name and GPU count
    [Documentation]    Returns model resource name and GPU count for compatibility callers.
    ${resource_name}    ${profile_name}    ${gpu_count}=
    ...    Second smallest deployable AIM resource name, profile and GPU count
    RETURN    ${resource_name}    ${gpu_count}

Second smallest deployable AIM resource name
    [Documentation]    Returns only the resource name of the second-smallest deployable AIM.
    ${resource_name}    ${profile_name}    ${gpu_count}=
    ...    Second smallest deployable AIM resource name, profile and GPU count
    RETURN    ${resource_name}

A second AIM model is running
    [Documentation]    Deploys a second AIM (distinct from TEST_AIM_NAME / TEST_AIM_ID)
    ...    and records its external host in TEST_AIM_B_* variables.
    ...    AIM-A state (TEST_AIM_NAME, TEST_AIM_ID, TEST_AIM_EXTERNAL_HOST) is preserved
    ...    — only the B-suffixed variables are set.
    ...    Used by the Bug-A regression: "Inference is authorized per model when two AIMs
    ...    share the workloads host".

    # Remember A-side state so we can restore after touching TEST_AIM_* in AIM-B setup.
    VAR    ${saved_aim_name}    ${TEST_AIM_NAME}
    VAR    ${saved_aim_id}    ${TEST_AIM_ID}
    VAR    ${saved_ext_host}    ${TEST_AIM_EXTERNAL_HOST}
    VAR    ${saved_profile_name}    ${TEST_AIM_PROFILE_NAME}
    VAR    ${saved_gpu_count}    ${TEST_AIM_GPU_COUNT}

    # Select and deploy AIM-B (second-smallest, different from AIM-A).
    ${aim_b_name}    ${aim_b_profile_name}    ${aim_b_gpu_count}=
    ...    Second smallest deployable AIM resource name, profile and GPU count
    Should Not Be Equal    ${aim_b_name}    ${TEST_AIM_NAME}
    ...    msg=Second smallest AIM resolves to the same model as AIM-A (${TEST_AIM_NAME}); need a second distinct model on cluster
    ${combined_gpu_count}=    Evaluate    int($saved_gpu_count) + int($aim_b_gpu_count)
    Set project quota for model GPU count    ${combined_gpu_count}
    VAR    ${TEST_AIM_NAME}    ${aim_b_name}    scope=TEST
    VAR    ${TEST_AIM_PROFILE_NAME}    ${aim_b_profile_name}    scope=TEST
    VAR    ${TEST_AIM_GPU_COUNT}    ${aim_b_gpu_count}    scope=TEST

    AIM is deployed and running

    # Capture AIM-B service details.
    ${response}=    Get AIM Service By ID    ${TEST_AIM_ID}    expected_status=200
    ${json}=    Set Variable    ${response.json()}
    ${endpoints}=    Get From Dictionary    ${json}    endpoints
    ${ext_b}=    Get From Dictionary    ${endpoints}    external
    VAR    ${TEST_AIM_B_NAME}    ${aim_b_name}    scope=TEST
    VAR    ${TEST_AIM_B_ID}    ${TEST_AIM_ID}    scope=TEST
    VAR    ${TEST_AIM_B_EXTERNAL_HOST}    ${ext_b}    scope=TEST

    # Restore AIM-A state so subsequent steps see A's coordinates again.
    VAR    ${TEST_AIM_NAME}    ${saved_aim_name}    scope=TEST
    VAR    ${TEST_AIM_ID}    ${saved_aim_id}    scope=TEST
    VAR    ${TEST_AIM_EXTERNAL_HOST}    ${saved_ext_host}    scope=TEST
    VAR    ${TEST_AIM_PROFILE_NAME}    ${saved_profile_name}    scope=TEST
    VAR    ${TEST_AIM_GPU_COUNT}    ${saved_gpu_count}    scope=TEST

The API key is also linked to the second AIM model
    [Documentation]    Binds the existing API key to AIM-B in addition to AIM-A,
    ...    in a single PATCH (the API replaces the whole aimIds list on each call,
    ...    so binding both models requires one call carrying both IDs).
    ...    Requires: TEST_AIM_ID, TEST_AIM_B_ID (from "A second AIM model is running")
    Variable Should Exist    ${TEST_AIM_B_ID}
    ...    msg=TEST_AIM_B_ID not set — run "A second AIM model is running" first
    @{aim_ids}=    Create list    ${TEST_AIM_ID}    ${TEST_AIM_B_ID}
    Api key is assigned to AIMS models    ${aim_ids}
    Key assignment should succeed

An api key authorized only for model A is created
    [Documentation]    Creates a fresh API key bound to AIM-A only (via aimIds binding).
    ...    AIM-B is intentionally excluded so cross-model enforcement is testable.
    ...    Stores the key in TEST_API_KEY / TEST_API_KEY_VALUE.
    ...    Requires: TEST_AIM_ID (set by "An AIM model is running")
    Variable Should Exist    ${TEST_AIM_ID}
    ...    msg=TEST_AIM_ID not set — run "An AIM model is running" first
    Api key exists for user
    # Bind the key to AIM-A by ID — AIM-B's ID is intentionally omitted.
    Api key is assigned to AIMS model    api_key=${TEST_API_KEY}    aim_id=${TEST_AIM_ID}
    Key assignment should succeed
    Api key binding should take effect
    # Discover model ID for AIM-A so requests can target the correct model name.
    ${models}=    List models from external endpoint
    ...    ${TEST_AIM_EXTERNAL_HOST}    ${TEST_AIM_ID}    ${TEST_API_KEY_VALUE}
    ${first}=    Get From List    ${models}    0
    VAR    ${TEST_AIM_MODEL_ID}    ${first}[id]    scope=TEST

A request is made to model A with key A
    [Documentation]    Sends a chat completion to AIM-A's external endpoint with the
    ...    key that is authorized only for AIM-A.
    ...    Sets: TEST_RESPONSE
    ...    Requires: TEST_AIM_EXTERNAL_HOST, TEST_AIM_MODEL_ID, TEST_API_KEY_VALUE
    Variable Should Exist    ${TEST_AIM_EXTERNAL_HOST}
    ...    msg=TEST_AIM_EXTERNAL_HOST not set — run "An AIM model is running" first
    Variable Should Exist    ${TEST_AIM_MODEL_ID}
    ...    msg=TEST_AIM_MODEL_ID not set — run "An api key authorized only for model A is created" first
    ${response}=    Send chat completion request to external endpoint
    ...    ${TEST_AIM_EXTERNAL_HOST}    ${TEST_AIM_MODEL_ID}
    ...    api_key=${TEST_API_KEY_VALUE}
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Model A should accept the request
    [Documentation]    Verifies that AIM-A's external endpoint returned HTTP 200,
    ...    confirming the authorized key was accepted (Bug-A false-denial regression:
    ...    cluster-auth hostname-only lookup would have wrongly denied this key).
    ...    Requires: TEST_RESPONSE (from "A request is made to model A with key A")
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    ...    msg=Key authorized for model A should be ACCEPTED on model A's endpoint; got ${TEST_RESPONSE.status_code}: ${TEST_RESPONSE.text}

A request is made to model B with key A
    [Documentation]    Sends a chat completion to AIM-B's external endpoint with the
    ...    key authorized only for AIM-A. Lists AIM-B's models with the key first:
    ...    200 yields the real model id; an expected auth denial (401/403/404) falls
    ...    back to AIM-B's resource name (the chat request is denied either way); any
    ...    other status fails the test rather than masking a regression.
    ...    Sets: TEST_RESPONSE
    ...    Requires: TEST_AIM_B_EXTERNAL_HOST, TEST_AIM_B_ID, TEST_AIM_B_NAME,
    ...              TEST_API_KEY_VALUE
    Variable Should Exist    ${TEST_AIM_B_EXTERNAL_HOST}
    ...    msg=TEST_AIM_B_EXTERNAL_HOST not set — run "A second AIM model is running" first
    ${models_resp}=    Get models response from external endpoint
    ...    ${TEST_AIM_B_EXTERNAL_HOST}    ${TEST_AIM_B_ID}    ${TEST_API_KEY_VALUE}
    ${status}=    Set Variable    ${models_resp.status_code}
    IF    ${status} == 200
        ${body}=    Set Variable    ${models_resp.json()}
        VAR    ${model_b_id}    ${body}[data][0][id]
    ELSE IF    ${status} in [401, 403, 404]
        # Expected: the key is authorized for A, not B, so listing B's models is denied.
        # Fall back to AIM-B's resource name; the chat request below is denied anyway.
        VAR    ${model_b_id}    ${TEST_AIM_B_NAME}
        Log    Model listing on AIM-B denied (${status}) as expected; using resource name    INFO
    ELSE
        Fail    Unexpected status ${status} listing models on AIM-B: ${models_resp.text}
    END
    ${response}=    Send chat completion request to external endpoint
    ...    ${TEST_AIM_B_EXTERNAL_HOST}    ${model_b_id}
    ...    api_key=${TEST_API_KEY_VALUE}
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Model B should reject the request
    [Documentation]    Verifies that AIM-B's external endpoint returned HTTP 401/403/404,
    ...    confirming that a key authorized only for AIM-A is denied on AIM-B
    ...    (cross-model enforcement half of the Bug-A regression).
    ...    Requires: TEST_RESPONSE (from "A request is made to model B with key A")
    ${status}=    Set Variable    ${TEST_RESPONSE.status_code}
    Should Be True    ${status} in [401, 403, 404]
    ...    msg=Key authorized only for model A should be REJECTED on model B's endpoint; got ${status}: ${TEST_RESPONSE.text}

# Setup and Teardown for AIMS
Initialize AIMS API key test environment
    [Documentation]    Initialize test environment for AIMS API key testing.
    ...    Uses Set Suite Variable so variables are available in all tests when called
    ...    from Suite Setup.
    Initialize api key test environment
