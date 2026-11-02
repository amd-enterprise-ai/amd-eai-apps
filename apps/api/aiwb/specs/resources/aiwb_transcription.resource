# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level keywords for the AIWB catalog speech-to-text (STT) flow:
...                 selecting a transcription-capable AIM from the catalog, discovering the
...                 running deployment through the transcription capability surface, and
...                 exercising the audio transcription / translation endpoints via the gateway.

Resource            aiwb_aims.resource
Resource            aiwb_common.resource
Resource            aims/api_keys.resource
Resource            api/audio.resource
Library             Collections
Library             SpeechToText


*** Keywords ***
# Given-step keywords

A transcription-capable AIM exists in the catalog
    [Documentation]    Selects a Ready AIM whose catalog tags mark it speech-to-text capable
    ...    (transcription / speech-to-text / automatic-speech-recognition) via Select AIM, which
    ...    populates the full model state (name, display/canonical) the deploy chain reads. Must run
    ...    before the GPU-quota step so that step sizes quota for this model, not the catalog's
    ...    smallest. Skips when no such model is published, so a cluster without a Whisper AIM image
    ...    reports skipped rather than failing.
    ...    Sets: TEST_AIM_NAME, TEST_AIM (and derived display/canonical).
    ${aims}=    All Ready AIMs
    ${name}=    First Transcription Capable Aim Name    ${aims}
    Skip If    $name is None
    ...    No transcription-capable (speech-to-text) AIM is published in this cluster's catalog — publish a Whisper-tagged AIM image to run this test.
    Select AIM    ${name}

The transcription AIM is deployed and running with an API key
    [Documentation]    Deploys the already-selected transcription AIM (see "A transcription-capable
    ...    AIM exists in the catalog"), waits for Running, and binds an API key so the external audio
    ...    endpoints authorize. Run after the GPU-quota step so the deploy uses this model's profile.
    ...    Sets: TEST_AIM_ID, TEST_AIM_MODEL_ID, TEST_AIM_EXTERNAL_HOST, TEST_API_KEY_VALUE.
    An AIM model is running with api key

# When-step keywords

Transcription-capable AIM services are listed
    [Documentation]    Lists inference deployments filtered to the transcription capability.
    ...    Sets: TEST_RESPONSE.
    ${namespace}=    Get Project Namespace
    ${response}=    List AIM Services    ${namespace}    expected_status=any    capability=transcription
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Audio is transcribed via the external endpoint
    [Documentation]    Uploads a synthetic audio clip to /v1/audio/transcriptions on the AIM's
    ...    external endpoint using the bound API key.
    ...    Requires: TEST_AIM_EXTERNAL_HOST, TEST_AIM_ID, TEST_AIM_MODEL_ID, TEST_API_KEY_VALUE.
    ...    Sets: TEST_RESPONSE.
    ${response}=    Transcribe audio via external endpoint
    ...    ${TEST_AIM_EXTERNAL_HOST}    ${TEST_AIM_ID}    ${TEST_AIM_MODEL_ID}    ${TEST_API_KEY_VALUE}
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Audio is translated to English via the external endpoint
    [Documentation]    Uploads a synthetic audio clip to /v1/audio/translations on the AIM's
    ...    external endpoint using the bound API key.
    ...    Requires: TEST_AIM_EXTERNAL_HOST, TEST_AIM_ID, TEST_AIM_MODEL_ID, TEST_API_KEY_VALUE.
    ...    Sets: TEST_RESPONSE.
    ${response}=    Translate audio via external endpoint
    ...    ${TEST_AIM_EXTERNAL_HOST}    ${TEST_AIM_ID}    ${TEST_AIM_MODEL_ID}    ${TEST_API_KEY_VALUE}
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

# Then-step keywords

The running AIM should appear in the transcription list
    [Documentation]    Verifies the transcription capability list includes the deployed AIM.
    ...    The 200 status is asserted by the preceding "response status should be 200" step.
    ...    Requires: TEST_AIM_ID, TEST_RESPONSE.
    ${services}=    Get From Dictionary    ${TEST_RESPONSE.json()}    data
    VAR    ${found}    ${False}
    FOR    ${service}    IN    @{services}
        ${service_id}=    Get From Dictionary    ${service}    id
        IF    "${service_id}" == "${TEST_AIM_ID}"
            VAR    ${found}    ${True}
            BREAK
        END
    END
    Should Be True    ${found}
    ...    msg=Running transcription AIM ${TEST_AIM_ID} should appear in the transcription capability list

The transcription response should return text
    [Documentation]    Asserts the transcription endpoint returned an OpenAI-compatible result:
    ...    a 200 with a string ``text`` field. A synthetic tone has no fixed transcript, so this
    ...    verifies the request contract, not the recognized words.
    ...    Requires: TEST_RESPONSE.
    Audio response should return text

The translation response should return text
    [Documentation]    Asserts the translation endpoint returned an OpenAI-compatible result:
    ...    a 200 with a string ``text`` field.
    ...    Requires: TEST_RESPONSE.
    Audio response should return text

Audio response should return text
    [Documentation]    Shared assertion for the audio endpoints — a 200 whose JSON carries a string
    ...    ``text`` field. Reads only the ``text`` field so the full (potentially large) response
    ...    body is never bound to a logged variable. Requires: TEST_RESPONSE.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    ...    msg=Audio endpoint should return 200, got status ${TEST_RESPONSE.status_code}
    ${has_text}=    Evaluate    isinstance($TEST_RESPONSE.json().get("text"), str)
    Should Be True    ${has_text}    msg=Audio response should contain a string 'text' field
