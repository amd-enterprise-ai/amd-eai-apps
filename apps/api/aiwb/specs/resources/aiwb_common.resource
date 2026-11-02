# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Shared AIWB keywords used across multiple resource files.
...                 Contains utility keywords that don't belong to any specific domain.
Resource            resources/common/resource_resolver.resource
Resource            api/health.resource
Library             Collections
Library             KubernetesSecretHelper


*** Variables ***
# HuggingFace token, masked so it never lands in logs. Provide via the HF_TOKEN env var
# (export locally) or --variable "HF_TOKEN: Secret:...".
${HF_TOKEN: Secret}         %{HF_TOKEN=}
# Name of the HuggingFace token secret created in the project namespace.
${HF_TOKEN_SECRET_NAME}     huggingface-token
${TEST_HF_TOKEN_SECRET}     ${EMPTY}


*** Keywords ***
AIWB service is running
    [Documentation]    Verifies that AIWB service is running and healthy.
    Verify AIWB health

A HuggingFace token is available for AIM deployment
    [Documentation]    Opt-in: when the masked ${HF_TOKEN} is provided, creates the HuggingFace
    ...    secret in the project namespace and publishes its name via ${TEST_HF_TOKEN_SECRET} so
    ...    the shared `Valid AIM deploy data is prepared` includes hfToken in the deploy payload.
    ...    When no token is provided (open-model clusters), it is a no-op. Reads the masked
    ...    ${HF_TOKEN} Secret variable (not the raw env var) so the documented
    ...    --variable "HF_TOKEN: Secret:..." path is honored. Sets: TEST_HF_TOKEN_SECRET.
    ${has_token}=    Evaluate    bool($HF_TOKEN.value)
    IF    not ${has_token}
        Log    HF_TOKEN not provided — skipping HuggingFace secret; open models work without it    INFO
        RETURN
    END
    HuggingFace token secret exists in namespace
    VAR    ${TEST_HF_TOKEN_SECRET}    ${HF_TOKEN_SECRET_NAME}    scope=TEST

HuggingFace token secret exists in namespace
    [Documentation]    Ensures the HuggingFace token secret exists in the project namespace,
    ...                created from the masked ${HF_TOKEN} secret variable. The value is fed to
    ...                kubectl via stdin so it never appears in process args or logs. Retries to
    ...                ride through intermittent OIDC token-exchange (401 "Unauthorized") failures.
    [Arguments]    ${secret_name}=${HF_TOKEN_SECRET_NAME}    ${namespace}=${None}
    IF    $namespace == $None
        ${namespace}=    Get Project Namespace
    END

    # Read the value via the Secret object so it is never substituted into a log line.
    ${has_token}=    Evaluate    bool($HF_TOKEN.value)
    Should Be True    ${has_token}
    ...    msg=HF_TOKEN is not set. Provide it via the HF_TOKEN env var or --variable "HF_TOKEN: Secret:...".

    Wait Until Keyword Succeeds    1 min    5 sec
    ...    Create secret from value    ${secret_name}    ${namespace}    ${HF_TOKEN}    --from-file\=token\=/dev/stdin

Create secret from value
    [Documentation]    Thin wrapper around the Python secret helper: idempotently creates a secret
    ...    from a masked value sent only over stdin. ${create_args} carries the flags that differ
    ...    between secret kinds (opaque token vs. dockerconfigjson pull secret).
    [Arguments]    ${secret_name}    ${namespace}    ${secret_value}    @{create_args}
    Create Kubernetes Secret From Value    ${secret_name}    ${namespace}    ${secret_value}    @{create_args}

Get Project Namespace
    [Documentation]    Returns the Kubernetes namespace for the current test project.
    ...    Decouples AIWB from AIRM project internals -- if namespace derivation changes,
    ...    only this keyword needs updating.
    ${project}=    The project object
    ${namespace}=    Get From Dictionary    ${project}    name
    RETURN    ${namespace}

The response is a paginated list with page metadata
    [Documentation]    Verifies the response carries the nested paginated envelope
    ...    (data list plus a pagination object with page, pageSize, total).
    ...    Internal assertion helper; tests should prefer the behavioural
    ...    keyword `The result is returned page by page` instead.
    VAR    ${body}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${body}    data
    Dictionary Should Contain Key    ${body}    pagination
    ${pagination}=    Get From Dictionary    ${body}    pagination
    Dictionary Should Contain Key    ${pagination}    page
    Dictionary Should Contain Key    ${pagination}    pageSize
    Dictionary Should Contain Key    ${pagination}    total
    ${data}=    Get From Dictionary    ${body}    data
    ${is_list}=    Evaluate    isinstance($data, list)
    Should Be True    ${is_list}    msg=Response 'data' field is not a list

The result is returned page by page
    [Documentation]    Behavioural wrapper: verifies the call succeeded and the
    ...    items are returned in pages rather than as one flat list. Used by
    ...    scenarios so they don't have to mention response codes or envelope
    ...    shapes — those stay in the keyword layer.
    Should be equal as integers    ${TEST_RESPONSE.status_code}    200
    The response is a paginated list with page metadata

The result reflects the requested page
    [Documentation]    Behavioural wrapper for scenarios that navigate between
    ...    pages: asserts the response's reported page number matches what
    ...    the user just requested.
    [Arguments]    ${expected_page}
    VAR    ${body}    ${TEST_RESPONSE.json()}
    ${pagination}=    Get From Dictionary    ${body}    pagination
    ${actual_page}=    Get From Dictionary    ${pagination}    page
    Should Be Equal As Integers    ${actual_page}    ${expected_page}
