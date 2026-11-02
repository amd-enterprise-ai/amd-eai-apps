# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Low-level keywords for the unified Envoy AI Gateway endpoint.
...                 Stateless HTTP wrappers for OpenAI-compatible /v1/models and
...                 /v1/chat/completions routes published by ai-gateway-discovery.
...                 All inputs are explicit arguments —
...                 callers in the business-logic layer own TEST_* state and
...                 resolve the gateway URL.
...
...                 SSL verification follows the suite-wide ${VERIFY_SSL} convention.
...                 Sessions are created via Create AI Gateway
...                 session so verify= is honored on every request.
Resource            resources/api/external_aim.resource
Library             RequestsLibrary
Library             Collections


*** Keywords ***
Create AI Gateway session
    [Documentation]    Creates a RequestsLibrary session for the AI Gateway base URL
    ...    with ${VERIFY_SSL} honored. Reuses the AIM external session helper since
    ...    the gateway is the same kind of cluster-external HTTPS endpoint.
    [Arguments]    ${gateway_url}    ${session_name}=ai_gateway
    ${name}=    Create AIM external session    ${gateway_url}    session_name=${session_name}
    RETURN    ${name}

Get Models From AI Gateway
    [Documentation]    GET /v1/models on the unified AI Gateway endpoint.
    ...    The endpoint follows the OpenAI listing contract: {"data": [{"id": ...}, ...]}.
    ...    Returns the raw RequestsLibrary response so callers can inspect status and body.
    [Arguments]    ${gateway_url}    ${api_key}=${None}    ${expected_status}=any    ${timeout}=60

    ${session}=    Create AI Gateway session    ${gateway_url}
    ${headers}=    Create Dictionary
    IF    "${api_key}" != "${None}"
        Set To Dictionary    ${headers}    Authorization=Bearer ${api_key}
    END

    ${response}=    Get From AIM External Endpoint    ${session}    /v1/models
    ...    headers=${headers}    expected_status=${expected_status}    timeout=${timeout}
    RETURN    ${response}

Send Transcription To AI Gateway
    [Documentation]    POST /v1/audio/transcriptions on the unified AI Gateway endpoint as
    ...    multipart/form-data — the shape the OpenAI SDK uses for audio, where the model is a
    ...    form field rather than a JSON key.
    ...
    ...    Content-Type is deliberately NOT set here. RequestsLibrary sets it, with the
    ...    generated boundary, when files= is passed. That matters: the gateway's body-aware
    ...    authorizer takes the multipart boundary from Content-Type and refuses to infer one
    ...    from the body, so a hand-set header without a matching boundary would not exercise
    ...    the real path.
    ...
    ...    Set ${set_model_header}=${False} to omit x-ai-eg-model entirely, which is what a
    ...    stock OpenAI client sends. That request carries no routing header at all, so it
    ...    falls to the gateway's catch-all rule and is authorized on the body.
    [Arguments]    ${gateway_url}    ${model_name}    ${api_key}=${None}
    ...    ${set_model_header}=${True}    ${expected_status}=any    ${timeout}=120

    ${session}=    Create AI Gateway session    ${gateway_url}
    ${headers}=    Create Dictionary
    IF    "${api_key}" != "${None}"
        Set To Dictionary    ${headers}    Authorization=Bearer ${api_key}
    END
    IF    ${set_model_header}
        Set To Dictionary    ${headers}    x-ai-eg-model=${model_name}
    END

    ${audio}=    Silent WAV bytes
    ${files}=    Evaluate    {"file": ("sample.wav", $audio, "audio/wav")}
    ${form}=    Create Dictionary    model=${model_name}    response_format=json

    ${response}=    POST On Session    ${session}    /v1/audio/transcriptions
    ...    data=${form}    files=${files}    headers=${headers}
    ...    expected_status=${expected_status}    timeout=${timeout}    verify=${VERIFY_SSL}
    RETURN    ${response}

Silent WAV bytes
    [Documentation]    A minimal valid 8 kHz mono 16-bit WAV of silence, built in memory so the
    ...    suite carries no binary fixture. Content is irrelevant: these tests assert on how the
    ...    gateway treats a multipart body, not on transcription quality.
    ${wav}=    Evaluate
    ...    __import__("struct").pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 1636, b"WAVE", b"fmt ", 16, 1, 1, 8000, 16000, 2, 16, b"data", 1600) + bytes(1600)
    RETURN    ${wav}

Send Chat Completion To AI Gateway
    [Documentation]    POST /v1/chat/completions on the unified AI Gateway endpoint.
    ...    Sends a minimal OpenAI-compatible chat completion request and returns
    ...    the raw response. Callers handle status assertions and body parsing.
    ...    When ${backend} is set, the AIM is selected by its UUID so routing is
    ...    unambiguous even when the same model name is deployed in another project.
    ...    Without it, the gateway routes by model name.
    ...
    ...    Backend-targeted routing requires the client to set BOTH
    ...    routing headers explicitly — x-ai-eg-backend AND x-ai-eg-model — so the
    ...    AIM's 3-condition route (Host + x-ai-eg-backend + x-ai-eg-model) is matched
    ...    at routing time and wins by specificity over any model-name fallback. The
    ...    model must also stay in the body for the backend. Relying on the gateway's
    ...    Lua to derive x-ai-eg-model from the body is NOT enough for UUID routing:
    ...    the Lua-set header is not present when the 3-condition rule is evaluated, so
    ...    only the 2-condition model-name rule matches and the request can be
    ...    mis-routed to an older co-hosted backend of the same model.
    ...
    ...    Set ${set_model_header}=${False} to send x-ai-eg-backend WITHOUT x-ai-eg-model
    ...    (the model still travels in the body). This exercises the backend-only
    ...    route rule (Host + x-ai-eg-backend): a backend-targeted request that omits the
    ...    optional model header must still bind to that backend's apiKeyAuth.
    ...
    ...    Set ${model_header} to send a specific x-ai-eg-model value that differs from the body
    ...    model — used to prove x-ai-eg-backend is authoritative when the model header names a
    ...    DIFFERENT model (the cross-model bypass check). Overrides ${set_model_header}.
    [Arguments]    ${gateway_url}    ${model_name}    ${api_key}=${None}
    ...    ${backend}=${None}    ${set_model_header}=${True}    ${model_header}=${None}
    ...    ${expected_status}=any    ${timeout}=120

    ${session}=    Create AI Gateway session    ${gateway_url}
    ${headers}=    Create Dictionary    Content-Type=application/json
    IF    "${api_key}" != "${None}"
        Set To Dictionary    ${headers}    Authorization=Bearer ${api_key}
    END
    IF    "${backend}" != "${None}"
        Set To Dictionary    ${headers}    x-ai-eg-backend=${backend}
        IF    "${model_header}" != "${None}"
            Set To Dictionary    ${headers}    x-ai-eg-model=${model_header}
        ELSE IF    ${set_model_header}
            Set To Dictionary    ${headers}    x-ai-eg-model=${model_name}
        END
    END

    ${messages}=    Evaluate    [{"role": "user", "content": "Hello"}]
    # max_tokens MUST be an integer. Create Dictionary stringifies "10", and the
    # AI Gateway ext-proc rejects a quoted number as malformed JSON (BadRequest),
    # unlike vLLM directly which coerces it.
    ${body}=    Create Dictionary
    ...    model=${model_name}
    ...    messages=${messages}
    ...    max_tokens=${10}

    ${response}=    Post To AIM External Endpoint    ${session}    /v1/chat/completions
    ...    json=${body}    headers=${headers}    expected_status=${expected_status}    timeout=${timeout}
    RETURN    ${response}
