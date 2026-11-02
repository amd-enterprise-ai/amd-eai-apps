# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Shared session and request helpers for AIM external endpoints
...                 (the OpenAI-compatible URL exposed at workloads.<cluster>.silogen.ai).
...
...                 RequestsLibrary requires `verify=` on each `*On Session` call —
...                 the session-level setting alone does not prevent strict cert
...                 validation. Routing every external-endpoint call through these
...                 helpers keeps `${VERIFY_SSL}` honored consistently and prevents
...                 the SSLError regression seen on a test cluster.
...
...                 New AIM external-endpoint keywords should reuse these helpers
...                 instead of calling `Create Session` / `*On Session` directly.

Library             RequestsLibrary
Library             Collections


*** Keywords ***
Create AIM external session
    [Documentation]    Create a RequestsLibrary session for an AIM external endpoint
    ...                with `verify=${VERIFY_SSL}` honored. Returns the session name
    ...                so callers can pass it to `Get From AIM External Endpoint` etc.
    ...
    ...                If `session_name` is not provided, derives one from `identifier`
    ...                (typically a workload or AIM ID) so concurrent tests get distinct
    ...                sessions.
    [Arguments]    ${external_host}    ${identifier}=temp    ${session_name}=${None}
    ${clean_host}=    Evaluate    $external_host.rstrip('/')
    ${name}=    IF    $session_name is not None    Set Variable    ${session_name}
    ...    ELSE    Set Variable    aim_external_${identifier}
    Create Session    ${name}    ${clean_host}    verify=${VERIFY_SSL}
    RETURN    ${name}

Get From AIM External Endpoint
    [Documentation]    GET against an AIM external session. Always passes
    ...                `verify=${VERIFY_SSL}` so the cluster cert chain is treated
    ...                consistently with the rest of the suite.
    [Arguments]    ${session_name}    ${path}    ${headers}=${None}
    ...    ${expected_status}=any    ${timeout}=${None}
    ${response}=    GET On Session    ${session_name}    ${path}
    ...    headers=${headers}    expected_status=${expected_status}
    ...    timeout=${timeout}    verify=${VERIFY_SSL}
    RETURN    ${response}

Post To AIM External Endpoint
    [Documentation]    POST against an AIM external session. Always passes
    ...                `verify=${VERIFY_SSL}` so the cluster cert chain is treated
    ...                consistently with the rest of the suite.
    [Arguments]    ${session_name}    ${path}    ${json}=${None}    ${headers}=${None}
    ...    ${expected_status}=any    ${timeout}=${None}
    ${response}=    POST On Session    ${session_name}    ${path}
    ...    json=${json}    headers=${headers}    expected_status=${expected_status}
    ...    timeout=${timeout}    verify=${VERIFY_SSL}
    RETURN    ${response}

Post Multipart To AIM External Endpoint
    [Documentation]    Multipart POST against an AIM external session — used by the audio
    ...                endpoints (`/v1/audio/transcriptions`, `/v1/audio/translations`),
    ...                which take a `multipart/form-data` file upload rather than a JSON
    ...                body. `files` and `data` are forwarded to requests unchanged; the
    ...                Content-Type boundary is set by requests, so do not pass one in
    ...                `headers`. Honors `verify=${VERIFY_SSL}` like the JSON variant.
    [Arguments]    ${session_name}    ${path}    ${files}    ${data}=${None}    ${headers}=${None}
    ...    ${expected_status}=any    ${timeout}=${None}
    ${response}=    POST On Session    ${session_name}    ${path}
    ...    files=${files}    data=${data}    headers=${headers}    expected_status=${expected_status}
    ...    timeout=${timeout}    verify=${VERIFY_SSL}
    RETURN    ${response}
