# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Business-logic keywords for the unified Envoy AI Gateway.
...                 Provides Given/When/Then steps for
...                 model discovery and OpenAI-compatible inference through the
...                 single gateway endpoint exposed by ai-gateway-discovery.
...
...                 Owns TEST_AI_GATEWAY_URL (resolved once per suite) and reuses
...                 TEST_AIM_ID / TEST_AIM_MODEL_ID / TEST_API_KEY_VALUE set by
...                 the shared AIM and API-key keywords. The served model name
...                 is currently sourced from the per-AIM external endpoint via
...                 `An AIM model is running with api key`; this becomes a TODO
...                 once that route is removed.
Resource            resources/aiwb_common.resource
Resource            resources/aiwb_aims.resource
Resource            resources/aims/api_keys.resource
Resource            resources/aim_catalog.resource
Resource            resources/api/ai_gateway.resource
Resource            resources/api/projects.resource
Resource            resources/deployment.resource
Resource            resources/airm_projects.resource
Library             Collections
Library             String
Library             Process
Library             DateTime
Library             GatewayAssertions


*** Variables ***
${AI_GATEWAY_URL}            ${EMPTY}
${AIWB_NAMESPACE}            aiwb
${AIM_RESOURCE_OVERRIDE}     ${EMPTY}
# Footprint reserved for a pinned AIM the catalog cannot place. Two GPUs is the largest
# single-model footprint these suites deployed before quota was sized from the catalog.
${OVERRIDE_FALLBACK_GPU_COUNT}    ${2}


*** Keywords ***
# Resource resolver

The AI Gateway endpoint
    [Documentation]    Resolves the unified AI Gateway base URL once per suite.
    ...    Order: ${AI_GATEWAY_URL} override → read AI_GATEWAY_URL from the aiwb-ui
    ...    deployment (the value aiwb itself uses) → fail with a clear message.
    ...    Caches the result in ${TEST_AI_GATEWAY_URL} (suite scope) so subsequent
    ...    calls return the same URL without re-querying the cluster.
    ${cached}=    Get Variable Value    ${TEST_AI_GATEWAY_URL}    ${EMPTY}
    IF    "${cached}" != ""
        RETURN    ${cached}
    END

    IF    "${AI_GATEWAY_URL}" != ""
        VAR    ${TEST_AI_GATEWAY_URL}    ${AI_GATEWAY_URL}    scope=SUITE
        Log    Using AI Gateway URL from variable: ${AI_GATEWAY_URL}    INFO
        RETURN    ${AI_GATEWAY_URL}
    END

    ${url}=    Get AI Gateway URL From AIWB
    IF    "${url}" == ""
        Fail    Could not resolve AI Gateway URL: set --variable AI_GATEWAY_URL:<url> or ensure the aiwb-ui deployment in namespace ${AIWB_NAMESPACE} has AI_GATEWAY_URL set
    END
    VAR    ${TEST_AI_GATEWAY_URL}    ${url}    scope=SUITE
    Log    Discovered AI Gateway URL from aiwb-ui deployment: ${url}    INFO
    RETURN    ${url}

Get AI Gateway URL From AIWB
    [Documentation]    Reads AI_GATEWAY_URL from the aiwb-ui deployment — the value
    ...    aiwb itself uses for the unified gateway endpoint, so the test exercises
    ...    exactly what the product is configured with. Read from the stable aiwb
    ...    namespace (${AIWB_NAMESPACE}) rather than the ai-gateway-discovery
    ...    controller, whose namespace varies across installs. Returns the full URL
    ...    (scheme included), or empty string if the deployment is not found or the
    ...    env var is unset.
    VAR    ${jsonpath}    jsonpath={.spec.template.spec.containers[?(@.name=="aiwb-ui")].env[?(@.name=="AI_GATEWAY_URL")].value}
    ${result}=    Run Process    kubectl    get    deployment    aiwb-ui
    ...    -n    ${AIWB_NAMESPACE}
    ...    -o    ${jsonpath}
    ...    timeout=10s
    IF    ${result.rc} != 0
        Log    Could not read AI_GATEWAY_URL from aiwb-ui deployment: ${result.stderr}    WARN
        RETURN    ${EMPTY}
    END
    RETURN    ${result.stdout.strip()}

# Given-step keywords

The AI Gateway endpoint is available
    [Documentation]    Resolves and caches the AI Gateway base URL.
    The AI Gateway endpoint

The smallest deployable AIM is selected
    [Documentation]    Pins one exact deployable AIM/profile pair and its GPU count for gateway tests.
    ${override}=    Get Variable Value    ${AIM_RESOURCE_OVERRIDE}    ${EMPTY}
    IF    "${override}" != ""
        ${resource_name}    ${profile_name}    ${gpu_count}=    The pinned AIM override    ${override}
    ELSE
        ${resource_name}    ${profile_name}    ${gpu_count}=
        ...    Smallest deployable AIM resource name, profile and GPU count
    END
    VAR    ${TEST_AIM_NAME}    ${resource_name}    scope=TEST
    VAR    ${TEST_AIM_PROFILE_NAME}    ${profile_name}    scope=TEST
    VAR    ${TEST_AIM_GPU_COUNT}    ${gpu_count}    scope=TEST

The pinned AIM override
    [Documentation]    Resolves an operator-pinned AIM into a profile and GPU count.
    ...    The override exists to keep these suites running on clusters where catalog
    ...    profile provisioning is incomplete, so a catalog lookup that cannot place the
    ...    pinned model must not fail the test. When the lookup fails, the model stays
    ...    pinned, no profile is pinned with it, and quota reserves the documented
    ...    fallback footprint — leaving profile choice to the deploy path, as before.
    [Arguments]    ${override}
    ${response}=    List AIMs    expected_status=200    status_filter=Ready    page_size=100
    VAR    ${aims_list}    ${response.json()}[data]
    ${profiles}=    All inference profiles
    TRY
        ${profile_name}    ${gpu_count}=    Get Deployable Aim Profile
        ...    ${aims_list}    ${profiles}    ${override}
    EXCEPT    AS    ${error}
        VAR    ${warning}    Pinned AIM ${override} has no auto-selectable catalog profile
        ...    (${error}); deploying without a pinned profile and reserving
        ...    ${OVERRIDE_FALLBACK_GPU_COUNT} GPU
        Log    ${warning}    WARN
        VAR    ${profile_name}    ${None}
        VAR    ${gpu_count}    ${OVERRIDE_FALLBACK_GPU_COUNT}
    END
    Log    Using pinned AIM override: ${override} (profile: ${profile_name}, ${gpu_count} GPU)    INFO
    RETURN    ${override}    ${profile_name}    ${gpu_count}

The gateway project has GPU quota available
    [Documentation]    Applies gateway selection, including overrides, before sizing matching quota.
    The smallest deployable AIM is selected
    Set project quota for model GPU count    ${TEST_AIM_GPU_COUNT}

# `A HuggingFace token is available for AIM deployment` and the secret helpers it uses
# live in aiwb_common.resource (imported above), shared across AIM suites.

# When-step keywords

The unified /v1/models endpoint is queried with a valid API key
    [Documentation]    Lists models from the AI Gateway using the active test API key.
    ...    Requires: TEST_API_KEY_VALUE
    ...    Sets: TEST_RESPONSE, TEST_GATEWAY_MODELS
    Variable Should Exist    ${TEST_API_KEY_VALUE}    msg=TEST_API_KEY_VALUE is not set
    ${gateway}=    The AI Gateway endpoint
    ${response}=    Get Models From AI Gateway    ${gateway}    api_key=${TEST_API_KEY_VALUE}
    ...    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST
    # The gateway serves /v1/models from the ext_authz handler, which short-circuits with
    # HTTP 203 (Non-Authoritative Information); a cluster without that handler returns 200.
    IF    ${response.status_code} in [200, 203]
        ${body}=    Set Variable    ${response.json()}
        ${models}=    Get From Dictionary    ${body}    data    default=${None}
        VAR    ${TEST_GATEWAY_MODELS}    ${models}    scope=TEST
    END

A chat completion request is sent to the AI Gateway for that model
    [Documentation]    Sends a chat completion through the AI Gateway with the test API key,
    ...    addressing the AIM precisely via its backend UUID (x-ai-eg-backend). This routes
    ...    to this project's AIM even when the same model name is deployed in another project,
    ...    so the happy path is deterministic on a multi-tenant cluster.
    ...    Requires: TEST_AIM_MODEL_ID (served model name), TEST_AIM_ID (backend UUID), TEST_API_KEY_VALUE
    ...    Sets: TEST_RESPONSE
    Variable Should Exist    ${TEST_AIM_MODEL_ID}    msg=TEST_AIM_MODEL_ID is not set
    Variable Should Exist    ${TEST_AIM_ID}    msg=TEST_AIM_ID is not set
    Variable Should Exist    ${TEST_API_KEY_VALUE}    msg=TEST_API_KEY_VALUE is not set
    ${gateway}=    The AI Gateway endpoint
    ${response}=    Send Chat Completion To AI Gateway    ${gateway}    ${TEST_AIM_MODEL_ID}
    ...    api_key=${TEST_API_KEY_VALUE}    backend=${TEST_AIM_ID}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

A transcription request is sent to the AI Gateway without routing headers
    [Documentation]    Sends a multipart /v1/audio/transcriptions request carrying no
    ...    x-ai-eg-backend and no x-ai-eg-model, which is what a stock OpenAI client sends.
    ...    With no routing header the request falls to the gateway's catch-all rule and is
    ...    authorized on its body, so this is the path that exercises multipart parsing in the
    ...    body-aware authorizer and in the endpoint picker.
    ...    Requires: TEST_AIM_MODEL_ID, TEST_API_KEY_VALUE
    ...    Sets: TEST_RESPONSE
    Variable Should Exist    ${TEST_AIM_MODEL_ID}    msg=TEST_AIM_MODEL_ID is not set
    Variable Should Exist    ${TEST_API_KEY_VALUE}    msg=TEST_API_KEY_VALUE is not set
    ${gateway}=    The AI Gateway endpoint
    ${response}=    Send Transcription To AI Gateway    ${gateway}    ${TEST_AIM_MODEL_ID}
    ...    api_key=${TEST_API_KEY_VALUE}    set_model_header=${False}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

A transcription request is sent to the AI Gateway for the other model with the authorized key
    [Documentation]    Sends a multipart transcription request naming the OTHER model while
    ...    presenting a key bound only to this suite's AIM, with no routing headers so the
    ...    decision is made on the body. Proves per-model authorization still holds on the
    ...    multipart path, which is parsed by different code than the JSON path.
    ...    Requires: TEST_OTHER_MODEL_ID, TEST_API_KEY_VALUE
    ...    Sets: TEST_RESPONSE
    Variable Should Exist    ${TEST_OTHER_MODEL_ID}    msg=TEST_OTHER_MODEL_ID is not set
    Variable Should Exist    ${TEST_API_KEY_VALUE}    msg=TEST_API_KEY_VALUE is not set
    ${gateway}=    The AI Gateway endpoint
    ${response}=    Send Transcription To AI Gateway    ${gateway}    ${TEST_OTHER_MODEL_ID}
    ...    api_key=${TEST_API_KEY_VALUE}    set_model_header=${False}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The gateway does not reject the request as malformed
    [Documentation]    Asserts the multipart body reached the backend rather than being refused
    ...    inside the gateway.
    ...
    ...    This deliberately does not assert a transcription came back: the suite's AIM is a chat
    ...    model with no audio endpoint, so it answers with an OpenAI error saying it does not
    ...    serve that API. That is the correct outcome here and still proves the point, because
    ...    both failures this guards against are produced by the gateway before any backend is
    ...    reached — "invalid json body" from the body-aware authorizer, and "error unmarshaling
    ...    request bodyMap" from the endpoint picker, each of which JSON-decoded the multipart
    ...    body and failed on the leading "--" of its boundary.
    ...
    ...    Because a chat model refuses the audio path, its refusal alone could also be the
    ...    gateway's catch-all "route-not-found" response (nothing routed). The two are told
    ...    apart by body: every response the gateway generates itself is plain text, while the
    ...    model server answers in the OpenAI envelope. That judgement lives in
    ...    GatewayAssertions, which also records why Envoy's own upstream-timing header cannot
    ...    carry it and what the body check can and cannot prove.
    Variable Should Exist    ${TEST_RESPONSE}    msg=TEST_RESPONSE is not set
    VAR    ${body}    ${TEST_RESPONSE.text}
    # Checked first so a regression names the component that caused it rather than
    # only reporting an unexpected status code.
    Should Not Contain    ${body}    invalid json body
    ...    msg=The body-aware authorizer JSON-decoded a multipart body: ${body}
    Should Not Contain    ${body}    error unmarshaling request body
    ...    msg=The endpoint picker JSON-decoded a multipart body: ${body}
    # The catch-all's text is written by Envoy AI Gateway, not this repo, so match it loosely;
    # the body-shape check below still fails the step if it is reworded.
    Should Not Contain    ${body}    No matching route found    ignore_case=True
    ...    msg=The request fell to the gateway's catch-all route instead of reaching the model: ${body}
    Response Should Come From The Model    ${TEST_RESPONSE}

A valid API key authorized for this model exists
    [Documentation]    Creates a fresh API key and binds it to the deployed AIM
    ...    (via aimIds), making it a valid credential for model-T. Stores the
    ...    value in TEST_OUTSIDER_API_KEY_VALUE without disturbing TEST_API_KEY or
    ...    TEST_API_KEY_VALUE. Used with "another model is available on the gateway"
    ...    to test cross-model authorization.
    Variable Should Exist    ${TEST_AIM_ID}
    ...    msg=TEST_AIM_ID not set — ensure "An AIM model is running with api key" ran first
    VAR    ${saved_key}    ${TEST_API_KEY}
    VAR    ${saved_key_value}    ${TEST_API_KEY_VALUE}
    Api key exists for user
    VAR    ${outsider_value}    ${TEST_API_KEY_VALUE}
    # Authorize the outsider key for the test AIM by binding it (aimIds) — not a group.
    Api key is assigned to AIMS model    api_key=${TEST_API_KEY}    aim_id=${TEST_AIM_ID}
    Key assignment should succeed
    # The negative assertion is meaningful only after this key is accepted by its own model;
    # otherwise an unpropagated binding would be rejected by every model and pass falsely.
    Api key binding should take effect    api_key_value=${outsider_value}
    VAR    ${TEST_OUTSIDER_API_KEY_VALUE}    ${outsider_value}    scope=TEST
    VAR    ${TEST_API_KEY}    ${saved_key}    scope=TEST
    VAR    ${TEST_API_KEY_VALUE}    ${saved_key_value}    scope=TEST

Another model is available on the gateway
    [Documentation]    Provisions a second, distinct AIM in the test project so the gateway
    ...    serves at least two models, then records the second model's served name in
    ...    TEST_OTHER_MODEL_ID. The cross-model regression needs two AIMs on the same hostname so
    ...    the buggy hostname-only route selection has a wrong route to pick; deploying its own
    ...    second AIM makes the scenario independent of cluster residue and test order rather
    ...    than scraping /v1/models for a model some other test happened to leave behind.
    ...    Reuses "A second model with its own key is available", which deploys the
    ...    second-smallest deployable AIM (asserted distinct from the test AIM) and records its
    ...    served model id in TEST_AIM_B_MODEL_ID, restoring the test AIM's state on exit.
    A second model with its own key is available
    Variable Should Exist    ${TEST_AIM_B_MODEL_ID}
    ...    msg=TEST_AIM_B_MODEL_ID not set — the second AIM did not yield a served model id
    Should Not Be Equal    ${TEST_AIM_B_MODEL_ID}    ${TEST_AIM_MODEL_ID}
    ...    msg=Second AIM serves the same model as the test AIM; the cross-model test needs two DISTINCT models
    VAR    ${TEST_OTHER_MODEL_ID}    ${TEST_AIM_B_MODEL_ID}    scope=TEST
    Log    Cross-model auth test will request: ${TEST_OTHER_MODEL_ID}    INFO

A chat completion request is sent to the AI Gateway for the other model with the authorized key
    [Documentation]    Sends a chat completion for TEST_OTHER_MODEL_ID using
    ...    TEST_OUTSIDER_API_KEY_VALUE, which is authorized for the test AIM but not
    ...    for the other model. Sets: TEST_RESPONSE
    Variable Should Exist    ${TEST_OTHER_MODEL_ID}
    ...    msg=TEST_OTHER_MODEL_ID not set — ensure "Another model is available on the gateway" ran
    Variable Should Exist    ${TEST_OUTSIDER_API_KEY_VALUE}
    ...    msg=TEST_OUTSIDER_API_KEY_VALUE not set — ensure "A valid API key authorized for this model exists" ran
    ${gateway}=    The AI Gateway endpoint
    ${response}=    Send Chat Completion To AI Gateway    ${gateway}    ${TEST_OTHER_MODEL_ID}
    ...    api_key=${TEST_OUTSIDER_API_KEY_VALUE}    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

A chat completion request is sent to the AI Gateway without an API key
    [Documentation]    Sends a chat completion through the AI Gateway with no Authorization header.
    ...    Requires: TEST_AIM_MODEL_ID
    ...    Sets: TEST_RESPONSE
    Variable Should Exist    ${TEST_AIM_MODEL_ID}    msg=TEST_AIM_MODEL_ID is not set
    ${gateway}=    The AI Gateway endpoint
    ${response}=    Send Chat Completion To AI Gateway    ${gateway}    ${TEST_AIM_MODEL_ID}
    ...    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

A chat completion request is sent to the AI Gateway with an invalid API key
    [Documentation]    Sends a chat completion through the AI Gateway with a bogus Bearer token.
    ...    Requires: TEST_AIM_MODEL_ID
    ...    Sets: TEST_RESPONSE
    Variable Should Exist    ${TEST_AIM_MODEL_ID}    msg=TEST_AIM_MODEL_ID is not set
    ${gateway}=    The AI Gateway endpoint
    ${response}=    Send Chat Completion To AI Gateway    ${gateway}    ${TEST_AIM_MODEL_ID}
    ...    api_key=invalid-api-key-12345    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

A chat completion request is sent for a model name that does not exist
    [Documentation]    Sends a chat completion for a model the gateway does not know about.
    ...    Requires: TEST_API_KEY_VALUE
    ...    Sets: TEST_RESPONSE
    Variable Should Exist    ${TEST_API_KEY_VALUE}    msg=TEST_API_KEY_VALUE is not set
    ${gateway}=    The AI Gateway endpoint
    ${response}=    Send Chat Completion To AI Gateway    ${gateway}
    ...    model_name=this-model-does-not-exist    api_key=${TEST_API_KEY_VALUE}
    ...    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

# Then-step keywords

The deployed AIM is listed among the available models
    [Documentation]    Verifies the gateway /v1/models response includes the served
    ...    model name for the currently deployed AIM.
    ...    Requires: TEST_RESPONSE (from the /v1/models query), TEST_AIM_MODEL_ID
    Should Be True    ${TEST_RESPONSE.status_code} in [200, 203]
    ...    msg=/v1/models should return 200 or 203, got ${TEST_RESPONSE.status_code}
    Variable Should Exist    ${TEST_GATEWAY_MODELS}    msg=TEST_GATEWAY_MODELS not set — /v1/models did not return a parsable body
    Variable Should Exist    ${TEST_AIM_MODEL_ID}    msg=TEST_AIM_MODEL_ID is not set
    ${model_ids}=    Evaluate    [m.get('id') for m in $TEST_GATEWAY_MODELS]
    Should Contain    ${model_ids}    ${TEST_AIM_MODEL_ID}
    ...    msg=Deployed model ${TEST_AIM_MODEL_ID} not found in gateway /v1/models response: ${model_ids}

The model returns a successful response
    [Documentation]    Verifies the chat completion response is 200 with an OpenAI-shaped body
    ...    and that the response came from the correct backend. vLLM echoes its own
    ...    served-model-name, not the requested model — a mismatch means the gateway
    ...    routed to the wrong backend (catches cluster-auth misrouting bugs).
    ...    Requires: TEST_RESPONSE, TEST_AIM_MODEL_ID
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    ...    msg=Expected 200, got ${TEST_RESPONSE.status_code}: ${TEST_RESPONSE.text}
    ${body}=    Set Variable    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${body}    choices    msg=Response should contain choices array
    ${choices}=    Get From Dictionary    ${body}    choices
    Should Not Be Empty    ${choices}    msg=Choices array should not be empty
    ${served_model}=    Get From Dictionary    ${body}    model    default=${None}
    Should Be Equal    ${served_model}    ${TEST_AIM_MODEL_ID}
    ...    msg=Gateway routed to wrong backend: requested ${TEST_AIM_MODEL_ID} but response model is ${served_model}

The request is rejected with an authentication error
    [Documentation]    Verifies the response is a 401 or 403. Body inspection is
    ...    intentionally minimal — Envoy may return a plain-text or empty body for
    ...    rejected auth, so the status code is the contract.
    ...    Requires: TEST_RESPONSE
    Should Be True    ${TEST_RESPONSE.status_code} in [401, 403]
    ...    msg=Expected 401 or 403, got ${TEST_RESPONSE.status_code}: ${TEST_RESPONSE.text}

The AIM's AI Gateway route is removed
    [Documentation]    Polls until ai-gateway-discovery has deleted the AIGatewayRoute for the
    ...    undeployed AIM. Verifies via kubectl that no route in the project namespace still
    ...    targets this AIM's backend UUID. This is collision-proof: unlike the /v1/models
    ...    listing (which reports model names shared across projects on a multi-tenant cluster),
    ...    the backend UUID is unique to this AIM, so its absence proves this specific route was
    ...    garbage-collected. Discovery reconciliation can take a handful of seconds after undeploy.
    ...    Requires: TEST_AIM_ID
    Variable Should Exist    ${TEST_AIM_ID}    msg=TEST_AIM_ID is not set
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    No AI Gateway route targets backend    ${TEST_AIM_ID}    ${namespace}

The request fails with a client error
    [Documentation]    Verifies the response is a 4xx (not 5xx). Used for unknown-model
    ...    routing where the gateway should reject the request without surfacing a
    ...    server-side failure.
    ...    Requires: TEST_RESPONSE
    Should Be True    400 <= ${TEST_RESPONSE.status_code} < 500
    ...    msg=Expected 4xx client error, got ${TEST_RESPONSE.status_code}: ${TEST_RESPONSE.text}

# Internal helpers

No AI Gateway route targets backend
    [Documentation]    Helper for polling: asserts no AIGatewayRoute in the namespace has an
    ...    x-ai-eg-backend match header equal to the given AIM UUID. ai-gateway-discovery stamps
    ...    this header (rule 1) with the AIM's workload-id, so its absence across all routes means
    ...    the AIM's route was deleted. Reads routes by their fully-qualified resource name so the
    ...    lookup does not depend on the short-name registration.
    [Arguments]    ${aim_uuid}    ${namespace}
    ${result}=    Run Process    kubectl    get    aigatewayroutes.aigateway.envoyproxy.io
    ...    -n    ${namespace}    -o    json    timeout=15s
    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Could not list AIGatewayRoutes in ${namespace}: ${result.stderr}
    ${data}=    Evaluate    json.loads($result.stdout)    modules=json
    ${backends}=    Evaluate
    ...    [h.get('value') for item in $data.get('items', []) for rule in item.get('spec', {}).get('rules', []) for match in rule.get('matches', []) for h in match.get('headers', []) if h.get('name') == 'x-ai-eg-backend']
    Should Not Contain    ${backends}    ${aim_uuid}
    ...    msg=AIGatewayRoute still targets backend ${aim_uuid} in namespace ${namespace}

# ===========================================================================
# Backend-UUID routing without the model header
# ===========================================================================
# A request that targets a backend by UUID (x-ai-eg-backend) but omits the
# optional x-ai-eg-model header must still bind to that backend's apiKeyAuth.
# Before the fix the backend route rule required x-ai-eg-model, so a model-less
# backend request matched no backend rule and was authorized against the wrong
# (or no) policy: the correct key was rejected and an unauthorized key could get
# through. The fix adds a Host + x-ai-eg-backend rule (no model) so routing and
# auth bind to the correct backend regardless of whether the model header is set.

An API key not authorized for this model exists
    [Documentation]    Creates a fresh API key that is NOT bound to the deployed AIM — a real
    ...    gateway credential that is not authorized for this backend. Stored in
    ...    TEST_UNAUTHORIZED_API_KEY_VALUE; the authorized TEST_API_KEY/_VALUE are preserved so the
    ...    rest of the test still sees them.
    VAR    ${saved_key}    ${TEST_API_KEY}
    VAR    ${saved_key_value}    ${TEST_API_KEY_VALUE}
    Api key exists for user
    VAR    ${TEST_UNAUTHORIZED_API_KEY_VALUE}    ${TEST_API_KEY_VALUE}    scope=TEST
    VAR    ${TEST_API_KEY}    ${saved_key}    scope=TEST
    VAR    ${TEST_API_KEY_VALUE}    ${saved_key_value}    scope=TEST

A chat completion is sent to the backend by UUID without the model header
    [Documentation]    Sends a chat completion addressed to the AIM by backend UUID
    ...    (x-ai-eg-backend) with x-ai-eg-model omitted (the model stays only in the body), using
    ...    the authorized key. Exercises the backend-only routing/auth path.
    ...    Requires: TEST_AIM_MODEL_ID, TEST_AIM_ID, TEST_API_KEY_VALUE
    ...    Sets: TEST_RESPONSE
    Variable Should Exist    ${TEST_AIM_ID}    msg=TEST_AIM_ID is not set
    Variable Should Exist    ${TEST_API_KEY_VALUE}    msg=TEST_API_KEY_VALUE is not set
    ${gateway}=    The AI Gateway endpoint
    ${response}=    Send Chat Completion To AI Gateway    ${gateway}    ${TEST_AIM_MODEL_ID}
    ...    api_key=${TEST_API_KEY_VALUE}    backend=${TEST_AIM_ID}    set_model_header=${False}
    ...    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

A chat completion is sent to the backend by UUID without the model header using an unauthorized key
    [Documentation]    Same backend-only routing path, but with a key not bound to this AIM. Must be
    ...    rejected — without the backend-only rule this request matched no backend rule and slipped past the
    ...    backend's apiKeyAuth, letting an unauthorized key through.
    ...    Requires: TEST_AIM_ID, TEST_AIM_MODEL_ID, TEST_UNAUTHORIZED_API_KEY_VALUE
    ...    Sets: TEST_RESPONSE
    Variable Should Exist    ${TEST_UNAUTHORIZED_API_KEY_VALUE}
    ...    msg=TEST_UNAUTHORIZED_API_KEY_VALUE not set — run "An API key not authorized for this model exists"
    ${gateway}=    The AI Gateway endpoint
    ${response}=    Send Chat Completion To AI Gateway    ${gateway}    ${TEST_AIM_MODEL_ID}
    ...    api_key=${TEST_UNAUTHORIZED_API_KEY_VALUE}    backend=${TEST_AIM_ID}    set_model_header=${False}
    ...    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

# ===========================================================================
# Backend UUID wins over a mismatched x-ai-eg-model
# ===========================================================================
# A request that targets backend A by UUID must be authorized against A even
# when x-ai-eg-model names a different, deployed model B. Before the wildcard
# backend rule, the mismatched model header pulled the request onto B's route,
# so B's SecurityPolicy authorized a request that x-ai-eg-backend still served
# from A — a key valid only for B could invoke A. The fix makes the backend rule
# match any x-ai-eg-model value, so it out-ranks B's model-only rule and A's own
# apiKeyAuth authorizes. Needs two DISTINCT deployed models (A and B), each keyed.

A second model with its own key is available
    [Documentation]    Deploys a second, distinct AIM (model B) alongside the already-running AIM-A,
    ...    creates an API key bound only to B, and records B's served model id — so a request can
    ...    target backend A by UUID while naming model B in x-ai-eg-model.
    ...    Requires: TEST_AIM_ID (A) and TEST_API_KEY/_VALUE (A's key) from
    ...    "An AIM model is running with api key".
    ...    Sets: TEST_AIM_B_ID, TEST_AIM_B_MODEL_ID, TEST_AIM_B_API_KEY_VALUE (A's key restored active).
    A second AIM model is running
    VAR    ${saved_key}    ${TEST_API_KEY}
    VAR    ${saved_key_value}    ${TEST_API_KEY_VALUE}
    Api key exists for user
    Api key is assigned to AIMS model    api_key=${TEST_API_KEY}    aim_id=${TEST_AIM_B_ID}
    Key assignment should succeed
    VAR    ${TEST_AIM_B_API_KEY_VALUE}    ${TEST_API_KEY_VALUE}    scope=TEST
    Api key binding should take effect
    ...    host=${TEST_AIM_B_EXTERNAL_HOST}
    ...    aim_id=${TEST_AIM_B_ID}
    ...    api_key_value=${TEST_AIM_B_API_KEY_VALUE}
    ${models}=    List models from external endpoint
    ...    ${TEST_AIM_B_EXTERNAL_HOST}    ${TEST_AIM_B_ID}    ${TEST_AIM_B_API_KEY_VALUE}
    ${first}=    Get From List    ${models}    0
    VAR    ${TEST_AIM_B_MODEL_ID}    ${first}[id]    scope=TEST
    VAR    ${TEST_API_KEY}    ${saved_key}    scope=TEST
    VAR    ${TEST_API_KEY_VALUE}    ${saved_key_value}    scope=TEST

A chat completion targets backend A by UUID naming model B, using model B's key
    [Documentation]    backend=A (x-ai-eg-backend) + x-ai-eg-model=B + B's key. Must be rejected:
    ...    B's key is not authorized for backend A. Body model stays A's, so serving would be A.
    ...    Requires: TEST_AIM_ID (A), TEST_AIM_MODEL_ID (A), TEST_AIM_B_MODEL_ID, TEST_AIM_B_API_KEY_VALUE
    ...    Sets: TEST_RESPONSE
    ${gateway}=    The AI Gateway endpoint
    ${response}=    Send Chat Completion To AI Gateway    ${gateway}    ${TEST_AIM_MODEL_ID}
    ...    api_key=${TEST_AIM_B_API_KEY_VALUE}    backend=${TEST_AIM_ID}    model_header=${TEST_AIM_B_MODEL_ID}
    ...    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

A chat completion targets backend A by UUID naming model B, using model A's key
    [Documentation]    backend=A + x-ai-eg-model=B + A's key. Must be served by A: the backend header
    ...    is authoritative and the mismatched model header is ignored (backend wins).
    ...    Requires: TEST_AIM_ID (A), TEST_AIM_MODEL_ID (A), TEST_AIM_B_MODEL_ID, TEST_API_KEY_VALUE (A)
    ...    Sets: TEST_RESPONSE
    ${gateway}=    The AI Gateway endpoint
    ${response}=    Send Chat Completion To AI Gateway    ${gateway}    ${TEST_AIM_MODEL_ID}
    ...    api_key=${TEST_API_KEY_VALUE}    backend=${TEST_AIM_ID}    model_header=${TEST_AIM_B_MODEL_ID}
    ...    expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

# ===========================================================================
# Same-model routing regression
# ===========================================================================
# When two AIMs serve the same model name (in two projects), a request that
# targets a backend by UUID must reach that exact backend. Without precise
# routing, Envoy merges the per-AIM AIGatewayRoutes and an equal-specificity
# model-name fallback rule can win by creation timestamp, mis-routing to the
# wrong deployment. The fix makes the UUID route (Host + x-ai-eg-backend +
# x-ai-eg-model) more specific so it wins; clients set both routing headers.
# There is no per-backend identity in the response (both backends echo the
# same served model name), so routing is verified via per-backend generated-
# token counters: vLLM's generation_tokens_total, exposed by the aiwb API as
# the raw cumulative `total_tokens` metric scoped by workload_id (= the
# backend UUID), compared before/after as a delta.

# Given-step keywords

The same AIM model is deployed in a second project
    [Documentation]    Deploys the SAME catalog AIM (same served model name) into a fresh
    ...    second project so two backends share a model name on the gateway — the
    ...    precondition for the same-model mis-routing bug. AIM-A must already be running
    ...    (run "An AIM model is running with api key" first).
    ...
    ...    Records A-side coordinates for the metric comparison (TEST_AIM_A_ID /
    ...    TEST_AIM_A_NAMESPACE), creates project B as the same user, deploys the same
    ...    model there, and creates a B-authorized API key. AIM-A's shared state
    ...    (TEST_PROJECT, TEST_AIM_ID, TEST_AIM_MODEL_ID, TEST_API_KEY/_VALUE) is
    ...    restored on exit so the rest of the suite still sees A.
    ...    Sets: TEST_AIM_A_ID, TEST_AIM_A_NAMESPACE, TEST_AIM_B_ID,
    ...    TEST_AIM_B_NAMESPACE, TEST_AIM_B_API_KEY_VALUE.
    Variable Should Exist    ${TEST_AIM_ID}    msg=TEST_AIM_ID not set — run "An AIM model is running with api key" first
    Variable Should Exist    ${TEST_AIM_MODEL_ID}    msg=TEST_AIM_MODEL_ID is not set
    Variable Should Exist    ${TEST_AIM_NAME}    msg=TEST_AIM_NAME is not set

    # Record A-side coordinates (the model name and backend we expect to stay idle).
    ${a_namespace}=    Get Project Namespace
    VAR    ${TEST_AIM_A_ID}    ${TEST_AIM_ID}    scope=TEST
    VAR    ${TEST_AIM_A_NAMESPACE}    ${a_namespace}    scope=TEST

    # Save A-side state we are about to overwrite while standing up project B.
    VAR    ${saved_project}    ${TEST_PROJECT}
    VAR    ${saved_project_id}    ${TEST_PROJECT_ID}
    VAR    ${saved_aim_id}    ${TEST_AIM_ID}
    VAR    ${saved_model_id}    ${TEST_AIM_MODEL_ID}
    VAR    ${saved_api_key}    ${TEST_API_KEY}
    VAR    ${saved_api_key_value}    ${TEST_API_KEY_VALUE}

    # Stand up project B (same user) and size it to the same selected model as project A.
    A Fresh Project With User Access Exists
    The project has GPU quota available

    # Deploy the SAME model into B (TEST_AIM_NAME is unchanged). This yields a new
    # backend UUID (TEST_AIM_ID = B) but the same served model name as A.
    An AIM model is running
    ${b_namespace}=    Get Project Namespace
    VAR    ${TEST_AIM_B_ID}    ${TEST_AIM_ID}    scope=TEST
    VAR    ${TEST_AIM_B_NAMESPACE}    ${b_namespace}    scope=TEST

    # Create an API key authorized for backend B (bound to B's cluster-auth group).
    User is authenticated
    Api key exists for user
    Api key is assigned to AIMS model
    Key assignment should succeed
    VAR    ${TEST_AIM_B_API_KEY_VALUE}    ${TEST_API_KEY_VALUE}    scope=TEST
    Api key binding should take effect
    ...    host=${TEST_AIM_EXTERNAL_HOST}
    ...    aim_id=${TEST_AIM_B_ID}
    ...    api_key_value=${TEST_AIM_B_API_KEY_VALUE}

    # Sanity: B serves the same model name as A (the whole premise of the bug).
    ${b_models}=    List models from external endpoint
    ...    ${TEST_AIM_EXTERNAL_HOST}    ${TEST_AIM_B_ID}    ${TEST_AIM_B_API_KEY_VALUE}
    ${b_first}=    Get From List    ${b_models}    0
    Should Be Equal    ${b_first}[id]    ${saved_model_id}
    ...    msg=Second project's AIM serves a different model (${b_first}[id]) than A (${saved_model_id}); both projects must serve the SAME model name

    # Restore A-side context for the rest of the suite (TEST_PROJECT and
    # TEST_PROJECT_ID were both repointed at B by the fresh-project setup).
    VAR    ${TEST_PROJECT}    ${saved_project}    scope=TEST
    VAR    ${TEST_PROJECT_ID}    ${saved_project_id}    scope=TEST
    VAR    ${TEST_AIM_ID}    ${saved_aim_id}    scope=TEST
    VAR    ${TEST_AIM_MODEL_ID}    ${saved_model_id}    scope=TEST
    VAR    ${TEST_API_KEY}    ${saved_api_key}    scope=TEST
    VAR    ${TEST_API_KEY_VALUE}    ${saved_api_key_value}    scope=TEST
    Log    AIM-A backend=${TEST_AIM_A_ID} (ns ${TEST_AIM_A_NAMESPACE}); AIM-B backend=${TEST_AIM_B_ID} (ns ${TEST_AIM_B_NAMESPACE}); shared model=${saved_model_id}    INFO

# When-step keywords

A chat completion is sent through the AI Gateway targeting backend B
    [Documentation]    Baselines both backends' generated-token counters, then sends a few chat
    ...    completions to the gateway addressed to backend B by UUID (x-ai-eg-backend +
    ...    x-ai-eg-model, using B's API key). Status is logged, not asserted — a mis-route to a
    ...    same-named backend also returns 200; the per-backend token counter is the routing
    ...    signal (see the Then step).
    ...    Requires: TEST_AIM_MODEL_ID, TEST_AIM_*_ID/_NAMESPACE, TEST_AIM_B_API_KEY_VALUE
    ...    Sets: TEST_TOKENS_A_BEFORE, TEST_TOKENS_B_BEFORE
    Variable Should Exist    ${TEST_AIM_B_ID}    msg=TEST_AIM_B_ID not set — run "The same AIM model is deployed in a second project" first
    Variable Should Exist    ${TEST_AIM_B_API_KEY_VALUE}    msg=TEST_AIM_B_API_KEY_VALUE is not set
    Baseline both backend token counters
    Send gateway completions to backend    ${TEST_AIM_B_ID}    ${TEST_AIM_B_API_KEY_VALUE}

A chat completion is sent through the AI Gateway targeting backend A
    [Documentation]    Symmetric to the backend-B step: re-baselines both counters, then sends a
    ...    few chat completions addressed to backend A by UUID, using A's API key. Verifying
    ...    BOTH directions guards against routing that collapses onto a single backend (e.g. the
    ...    creation-timestamp race always resolving to the older route): if every request went
    ...    to A, the backend-B phase fails; if every request went to B, this phase fails.
    ...    Requires: TEST_AIM_MODEL_ID, TEST_AIM_*_ID/_NAMESPACE, TEST_API_KEY_VALUE (A's key)
    ...    Sets: TEST_TOKENS_A_BEFORE, TEST_TOKENS_B_BEFORE
    Variable Should Exist    ${TEST_AIM_A_ID}    msg=TEST_AIM_A_ID not set — run the earlier Given steps first
    Variable Should Exist    ${TEST_API_KEY_VALUE}    msg=TEST_API_KEY_VALUE (A's key) is not set
    Baseline both backend token counters
    Send gateway completions to backend    ${TEST_AIM_A_ID}    ${TEST_API_KEY_VALUE}

# Then-step keywords

Only backend B served the request
    [Documentation]    Verifies the backend-B request reached B's vLLM and NOT co-hosted A, via
    ...    per-backend generated-token counters (vLLM generation_tokens_total, exposed as the
    ...    raw cumulative `total_tokens` metric scoped by workload_id = backend UUID): B's
    ...    counter must rise above its pre-send baseline (it produced output → it served), while
    ...    A's must stay flat. A raw cumulative counter is used — not a windowed increase() — so
    ...    a short burst right after backend startup is not missed (increase() over a window that
    ...    only sees post-burst samples reads 0). Polls to absorb Prometheus scrape lag. Fails
    ...    if the request is mis-routed to the co-hosted backend.
    ...    Requires: TEST_TOKENS_*_BEFORE, TEST_AIM_*_ID/_NAMESPACE
    Variable Should Exist    ${TEST_TOKENS_B_BEFORE}    msg=TEST_TOKENS_B_BEFORE not set — run the When step first
    Wait Until Keyword Succeeds    3 min    15 sec    Backend serves while peer stays idle
    ...    ${TEST_AIM_B_ID}    ${TEST_AIM_B_NAMESPACE}    ${TEST_TOKENS_B_BEFORE}
    ...    ${TEST_AIM_A_ID}    ${TEST_AIM_A_NAMESPACE}    ${TEST_TOKENS_A_BEFORE}

Only backend A served the request
    [Documentation]    Mirror of "Only backend B served the request" for the backend-A phase: A's
    ...    token counter must rise while B's stays flat, proving a UUID-targeted request reaches
    ...    A and is not pulled to B.
    ...    Requires: TEST_TOKENS_*_BEFORE, TEST_AIM_*_ID/_NAMESPACE
    Variable Should Exist    ${TEST_TOKENS_A_BEFORE}    msg=TEST_TOKENS_A_BEFORE not set — run the When step first
    Wait Until Keyword Succeeds    3 min    15 sec    Backend serves while peer stays idle
    ...    ${TEST_AIM_A_ID}    ${TEST_AIM_A_NAMESPACE}    ${TEST_TOKENS_A_BEFORE}
    ...    ${TEST_AIM_B_ID}    ${TEST_AIM_B_NAMESPACE}    ${TEST_TOKENS_B_BEFORE}

# Internal helpers

Baseline both backend token counters
    [Documentation]    Snapshots A's and B's cumulative generated-token counters into
    ...    TEST_TOKENS_A_BEFORE / TEST_TOKENS_B_BEFORE so a Then step can assert a per-backend
    ...    delta. Re-run before each send phase to re-baseline against the current totals.
    ${a_before}=    Total generated tokens for backend    ${TEST_AIM_A_ID}    ${TEST_AIM_A_NAMESPACE}
    ${b_before}=    Total generated tokens for backend    ${TEST_AIM_B_ID}    ${TEST_AIM_B_NAMESPACE}
    VAR    ${TEST_TOKENS_A_BEFORE}    ${a_before}    scope=TEST
    VAR    ${TEST_TOKENS_B_BEFORE}    ${b_before}    scope=TEST

Send gateway completions to backend
    [Documentation]    Sends 3 chat completions to the gateway addressed to the given backend
    ...    UUID with the given API key. Status is logged, not asserted.
    [Arguments]    ${backend_id}    ${api_key}
    ${gateway}=    The AI Gateway endpoint
    FOR    ${i}    IN RANGE    3
        ${response}=    Send Chat Completion To AI Gateway    ${gateway}    ${TEST_AIM_MODEL_ID}
        ...    api_key=${api_key}    backend=${backend_id}    expected_status=any
        Log    Gateway completion #${i} targeting backend ${backend_id} → HTTP ${response.status_code}    INFO
    END

Backend serves while peer stays idle
    [Documentation]    Single poll iteration: the target backend's cumulative generated-token
    ...    counter must have risen above its pre-send baseline, and the peer backend's must be
    ...    unchanged.
    [Arguments]    ${target_id}    ${target_ns}    ${target_before}    ${peer_id}    ${peer_ns}    ${peer_before}
    ${target_after}=    Total generated tokens for backend    ${target_id}    ${target_ns}
    ${peer_after}=    Total generated tokens for backend    ${peer_id}    ${peer_ns}
    Log    Generated tokens — target ${target_id}: ${target_before} -> ${target_after}; peer ${peer_id}: ${peer_before} -> ${peer_after}    INFO
    Should Be True    ${target_after} > ${target_before}
    ...    msg=Intended backend ${target_id} generated no new tokens (${target_before} -> ${target_after}); request did not reach it
    Should Be Equal As Numbers    ${peer_after}    ${peer_before}
    ...    msg=Peer backend ${peer_id} generated tokens (${peer_before} -> ${peer_after}); request was mis-routed

Total generated tokens for backend
    [Documentation]    Returns a backend's cumulative generated-token count (vLLM
    ...    generation_tokens_total) via the aiwb API `total_tokens` metric. The endpoint
    ...    scopes the query by workload_id (= the backend UUID), isolating one backend even
    ...    when several share a model name. This is a raw cumulative scalar (not a windowed
    ...    increase), so before/after snapshots give a reliable per-backend delta. A missing
    ...    series resolves to 0. Returns a float.
    ...
    ...    The endpoint requires a start/end range even though total_tokens is an instantaneous
    ...    cumulative query that ignores it, so a nominal 1-hour window is passed.
    [Arguments]    ${service_id}    ${namespace}
    ${end}=    Get Current Date    time_zone=UTC    result_format=%Y-%m-%dT%H:%M:%SZ
    ${start}=    Get Current Date    time_zone=UTC    increment=-1 hour    result_format=%Y-%m-%dT%H:%M:%SZ
    &{params}=    Create Dictionary    start=${start}    end=${end}
    ${response}=    Get AIM Service Metric    ${service_id}    total_tokens    ${namespace}
    ...    expected_status=200    params=${params}
    ${data}=    Get From Dictionary    ${response.json()}    data
    RETURN    ${data}

AIWB workbench endpoints should remain accessible for 6 seconds after undeploy
    [Documentation]    Polls the three AIWB routes that share the Envoy gateway in a
    ...    tight loop for 6 seconds after AIM undeploy. Fails immediately on HTTP 500.
    ...    200 and 404 are acceptable — the AIM is gone so the inference list may be
    ...    empty, but Envoy must not reject the requests outright.
    ${namespace}=    Get Project Namespace
    ${deadline}=     Evaluate    time.time() + 6    modules=time

    WHILE    True    limit=NONE
        ${now}=    Evaluate    time.time()    modules=time
        IF    ${now} >= ${deadline}    BREAK

        ${r_inference}=    List AIM Services                   ${namespace}
        ${r_workloads}=    Get AIWB workloads                  ${namespace}
        ${r_metrics}=      Get AIWB Project Workloads Metrics  ${namespace}

        Should Contain    ${{[200, 404]}}    ${r_inference.status_code}
        ...    msg=GET .../inference returned HTTP ${r_inference.status_code} during post-undeploy window (expected 200 or 404)
        Should Contain    ${{[200, 404]}}    ${r_workloads.status_code}
        ...    msg=GET .../workloads returned HTTP ${r_workloads.status_code} during post-undeploy window (expected 200 or 404)
        Should Contain    ${{[200, 404]}}    ${r_metrics.status_code}
        ...    msg=GET .../workloads/metrics returned HTTP ${r_metrics.status_code} during post-undeploy window (expected 200 or 404)
    END
