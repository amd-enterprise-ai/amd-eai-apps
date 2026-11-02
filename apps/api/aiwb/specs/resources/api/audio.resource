# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       API-layer helpers for the AIM OpenAI-compatible audio endpoints
...                 (``/v1/audio/transcriptions``, ``/v1/audio/translations``). These take a
...                 ``multipart/form-data`` file upload, so they route through
...                 ``Post Multipart To AIM External Endpoint`` to keep ``verify=${VERIFY_SSL}``
...                 honored, and attach a synthetic WAV via the ``SpeechToText`` library rather
...                 than a committed fixture.

Resource            external_aim.resource
Library             Collections
Library             SpeechToText


*** Keywords ***
Transcribe audio via external endpoint
    [Documentation]    POST a synthetic audio clip to ``/v1/audio/transcriptions`` on an AIM's
    ...                external endpoint with the given API key. Returns the raw response without
    ...                asserting status so callers can distinguish success from auth/other errors.
    [Arguments]    ${external_host}    ${workload_id}    ${model_id}    ${api_key}    ${timeout}=120
    ${response}=    Post audio to external endpoint
    ...    ${external_host}    ${workload_id}    ${model_id}    ${api_key}
    ...    /v1/audio/transcriptions    ${timeout}
    RETURN    ${response}

Translate audio via external endpoint
    [Documentation]    POST a synthetic audio clip to ``/v1/audio/translations`` on an AIM's
    ...                external endpoint with the given API key. Returns the raw response.
    [Arguments]    ${external_host}    ${workload_id}    ${model_id}    ${api_key}    ${timeout}=120
    ${response}=    Post audio to external endpoint
    ...    ${external_host}    ${workload_id}    ${model_id}    ${api_key}
    ...    /v1/audio/translations    ${timeout}
    RETURN    ${response}

Post audio to external endpoint
    [Documentation]    Shared multipart audio POST: opens the external session, attaches the API
    ...                key, and uploads a synthetic WAV plus the ``model`` form field to ``path``.
    ...                The multipart boundary is set by requests, so no Content-Type is passed.
    [Arguments]    ${external_host}    ${workload_id}    ${model_id}    ${api_key}    ${path}    ${timeout}=120
    # Use an audio-specific session alias so it never collides with the
    # aim_external_${workload_id} session the deploy/API-key discovery flow
    # (List models from external endpoint) already opened for the same workload.
    ${session_name}=    Create AIM external session    ${external_host}    session_name=aim_audio_${workload_id}
    ${headers}=    Create Dictionary    Authorization=Bearer ${api_key}
    ${files}=    Synthetic Audio Upload
    ${data}=    Create Dictionary    model=${model_id}
    ${response}=    Post Multipart To AIM External Endpoint    ${session_name}    ${path}
    ...    files=${files}    data=${data}    headers=${headers}    expected_status=any    timeout=${timeout}
    RETURN    ${response}
