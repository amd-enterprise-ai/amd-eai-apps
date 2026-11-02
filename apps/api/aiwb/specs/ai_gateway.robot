# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       E2E coverage for the unified Envoy AI Gateway.
...                 Verifies the single OpenAI-compatible endpoint that serves all
...                 deployed AIMs: model discovery on /v1/models, inference happy
...                 path with API-key auth, auth enforcement, undeploy cleanup,
...                 error mapping for unknown models, and correct
...                 per-backend routing when two AIMs share a model name. The
...                 AI Gateway is the only external entry point
...                 for AIM inference (the per-AIM /workbench/{uuid} route is
...                 removed), so this suite is the canonical coverage for that
...                 contract.
...
...                 Suite design mirrors api_keys.robot: a single project is
...                 created once in Suite Setup, the AIM is deployed lazily by
...                 the idempotent precondition keywords and reused across
...                 tests, and the destructive undeploy scenario runs last so
...                 it doesn't tear down state needed by earlier tests.
Resource            resources/aiwb_ai_gateway.resource
Resource            resources/aims/api_keys.resource
Resource            resources/aiwb_aims.resource
Resource            resources/airm_projects.resource

Suite Setup         Initialize AIMS API key test environment
Suite Teardown      Clean Up All Tracked Resources


*** Test Cases ***
Deployed AIM appears in the unified model listing
    [Documentation]    Verify that an AIM deployed in the user's project shows up in the
    ...    OpenAI-compatible /v1/models response served by the AI Gateway.
    [Tags]    ai-gateway    inference    api-keys    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    When the unified /v1/models endpoint is queried with a valid API key
    Then the deployed AIM is listed among the available models

Inference works through the AI Gateway with a valid API key
    [Documentation]    Verify that a chat completion request routed through the AI
    ...    Gateway with a valid API key reaches the deployed AIM and returns an
    ...    OpenAI-shaped response.
    [Tags]    ai-gateway    inference    api-keys    positive    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    When a chat completion request is sent to the AI Gateway for that model
    Then the model returns a successful response

Inference is rejected for an API key authorized for a different model
    [Documentation]    Verify that per-model authorization is enforced even when the API key
    ...    holds valid credentials for another model on the same gateway hostname. Regression
    ...    test: old cluster-auth matched HTTPRoutes by hostname only, so a key
    ...    authorized for model-A could reach model-B because the wrong route was selected.
    [Tags]    ai-gateway    inference    api-keys    negative    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    And a valid API key authorized for this model exists
    And another model is available on the gateway
    When a chat completion request is sent to the AI Gateway for the other model with the authorized key
    Then the request is rejected with an authentication error

Multipart inference requests reach the backend instead of being rejected by the gateway
    [Documentation]    Verify that an OpenAI-shaped audio request — multipart/form-data with the
    ...    model as a form field and no routing headers — is parsed and authorized by the
    ...    gateway rather than refused inside it.
    ...
    ...    Regression test for the audio path being unusable: two components on the request path
    ...    JSON-decoded every body in order to read the model, and a multipart body fails that
    ...    decode on the leading "--" of its boundary. The body-aware authorizer answered
    ...    "invalid json body" and the endpoint picker answered "error unmarshaling request
    ...    bodyMap", so no audio endpoint was reachable on any model.
    ...
    ...    The suite's AIM is a chat model, so the backend itself refuses an audio path with an
    ...    OpenAI error saying it does not serve that API. That is the expected outcome: the
    ...    assertion is that the model answered at all, which is what both regressions prevent.
    [Tags]    ai-gateway    inference    api-keys    multipart    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    When a transcription request is sent to the AI Gateway without routing headers
    Then the gateway does not reject the request as malformed

Multipart inference is rejected for an API key authorized for a different model
    [Documentation]    Verify that per-model authorization holds on the multipart path. The
    ...    multipart body is read by different code than the JSON body, so the authorization
    ...    decision has to be proved separately here.
    ...
    ...    Regression test for a cross-model bypass: an earlier revision inferred the multipart
    ...    boundary from the body when Content-Type was unavailable. RFC 2046 makes a compliant
    ...    reader discard everything before the first real boundary, so a body could open with a
    ...    decoy document naming an allowed model and be authorized on it while every parser
    ...    downstream read a second, forbidden one.
    [Tags]    ai-gateway    inference    api-keys    multipart    negative    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    And a valid API key authorized for this model exists
    And another model is available on the gateway
    When a transcription request is sent to the AI Gateway for the other model with the authorized key
    Then the request is rejected with an authentication error

Inference is rejected without an API key
    [Documentation]    Verify that the AI Gateway enforces authentication: a chat
    ...    completion request with no Authorization header is rejected before
    ...    reaching the backend.
    [Tags]    ai-gateway    inference    api-keys    negative    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    When a chat completion request is sent to the AI Gateway without an API key
    Then the request is rejected with an authentication error

Inference is rejected with an invalid API key
    [Documentation]    Verify that the AI Gateway rejects requests carrying an
    ...    unrecognised Bearer token, distinct from the no-header case.
    [Tags]    ai-gateway    inference    api-keys    negative    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    When a chat completion request is sent to the AI Gateway with an invalid API key
    Then the request is rejected with an authentication error

Chat completion request for an unknown model is rejected
    [Documentation]    Verify that the AI Gateway maps an unknown model name to a
    ...    client error (4xx) rather than surfacing a 5xx server failure.
    [Tags]    ai-gateway    inference    api-keys    negative    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    When a chat completion request is sent for a model name that does not exist
    Then the request fails with a client error

Inference routes to the correct backend when two AIMs share a model name
    [Documentation]    Regression test: when two AIMs serve the same
    ...    model name (deployed in two projects), a request that targets a backend by UUID
    ...    must reach that exact backend, not the co-hosted one. Without precise routing,
    ...    Envoy merges the per-AIM AIGatewayRoutes and an equal-specificity model-name rule
    ...    can win by creation timestamp, mis-routing to the wrong deployment. This is fixed
    ...    by making the UUID route (Host + x-ai-eg-backend + x-ai-eg-model) more specific so
    ...    it wins; the client sets both routing headers (see Send Chat Completion To AI
    ...    Gateway).
    ...
    ...    No response field identifies the backend (both echo the same served model name),
    ...    so routing is verified via per-backend generated-token counters (vLLM
    ...    generation_tokens_total, exposed as the raw cumulative `total_tokens` metric scoped
    ...    by workload_id = backend UUID). Both directions are checked: a request targeting B
    ...    must increment only B's counter, and a request targeting A only A's — guarding
    ...    against routing collapsing onto a single backend.
    [Tags]    ai-gateway    inference    routing    metrics    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    And the same AIM model is deployed in a second project
    When a chat completion is sent through the AI Gateway targeting backend B
    Then only backend B served the request
    When a chat completion is sent through the AI Gateway targeting backend A
    Then only backend A served the request

Inference through the backend-UUID path without a model header authorizes the correct key
    [Documentation]    Regression test: a request that targets a backend by UUID
    ...    (x-ai-eg-backend) but omits the optional x-ai-eg-model header must still bind to that
    ...    backend's apiKeyAuth and serve. Before the backend-only route rule was added, a
    ...    model-less backend request matched no backend rule and the correct key was wrongly
    ...    rejected on this path.
    [Tags]    ai-gateway    inference    api-keys    routing    positive    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    When a chat completion is sent to the backend by UUID without the model header
    Then the model returns a successful response

Inference through the backend-UUID path without a model header is rejected for an unauthorized key
    [Documentation]    Regression test for an auth bypass: a key not bound to the AIM
    ...    must be rejected on the backend-UUID / no-model-header path. Before the fix this request
    ...    matched no backend rule and was authorized against the wrong policy, letting an
    ...    unauthorized key invoke the model.
    [Tags]    ai-gateway    inference    api-keys    routing    negative    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    And an API key not authorized for this model exists
    When a chat completion is sent to the backend by UUID without the model header using an unauthorized key
    Then the request is rejected with an authentication error

Inference targeting a backend by UUID is authorized against that backend, not a model named in the header
    [Documentation]    Regression test: a request that targets backend A by
    ...    UUID (x-ai-eg-backend) but names a different deployed model B in x-ai-eg-model must be
    ...    authorized against A. A key valid only for B must be rejected — before the wildcard backend
    ...    rule, the mismatched model header pulled the request onto B's route and B's SecurityPolicy
    ...    wrongly authorized a request that x-ai-eg-backend still served from A (cross-model bypass).
    [Tags]    ai-gateway    inference    api-keys    routing    negative    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    And a second model with its own key is available
    When a chat completion targets backend A by UUID naming model B, using model B's key
    Then the request is rejected with an authentication error

Inference targeting a backend by UUID with the correct key is served despite a mismatched model header
    [Documentation]    Backend-wins semantics: the same backend-A/UUID request
    ...    naming model B in x-ai-eg-model, but carrying A's key, must be served by A — the backend
    ...    header is authoritative and the mismatched model header is ignored.
    [Tags]    ai-gateway    inference    api-keys    routing    positive    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    And a second model with its own key is available
    When a chat completion targets backend A by UUID naming model B, using model A's key
    Then the model returns a successful response

# Destructive — runs last so it doesn't tear down state shared with earlier tests.
Undeploying an AIM keeps workbench endpoints available and removes its route
    [Documentation]    Two post-undeploy guarantees in one flow.
    ...    After an AIM is undeployed, the AIWB inference list, workloads, and
    ...    workload-metrics endpoints must remain available (no HTTP 500).
    ...    The AIM's AI Gateway route must also be removed — verified via kubectl on the
    ...    route's unique backend UUID rather than the /v1/models listing, because model
    ...    names are shared across projects on a multi-tenant cluster and would not
    ...    disappear when only this project's AIM is removed.
    [Tags]    ai-gateway    undeploy    cleanup    regression    kubectl    gpu

    Given a ready project with user access exists
    And the gateway project has GPU quota available
    And the AI Gateway endpoint is available
    And a HuggingFace token is available for AIM deployment
    And an AIM model is running with api key
    When AIM is undeployed
    Then AIWB workbench endpoints should remain accessible for 6 seconds after undeploy
    And the AIM's AI Gateway route is removed
