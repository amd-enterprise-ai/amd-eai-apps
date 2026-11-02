# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level AIWB secret testing keywords.
...                 Provides business-logic level keywords for testing AIWB secret operations.
...                 Uses the low-level API keywords from api/secrets.resource to implement
...                 higher-level testing scenarios for secret CRUD and cross-service autodiscovery.
Resource            api/secrets.resource
Resource            resources/airm_projects.resource
Resource            resources/airm_secrets.resource
Resource            resources/resource_tracking.resource
Resource            aiwb_common.resource
Library             Collections
Library             Process
Library             TestPrefix


*** Variables ***
${TEST_AIWB_SECRET_NAME}        ${None}
${TEST_AIWB_SECRET_K8S_NAME}    ${None}
@{CREATED_AIWB_SECRET_NAMES}    # Track created K8s resource names for cleanup


*** Keywords ***
Initialize AIWB Secret Tracking
    [Documentation]    Resets the AIWB secret tracking list for cleanup.
    @{empty_list}=    Create List
    Set Suite Variable    @{CREATED_AIWB_SECRET_NAMES}    @{empty_list}

Clean Up All Created AIWB Secrets
    [Documentation]    Deletes all AIWB secrets created during the test.
    ...    Tolerant of missing variables or already-deleted secrets.
    ${project_data}=    Get Variable Value    ${TEST_PROJECT}    ${None}
    IF    $project_data is None
        Log    No project set, skipping AIWB secret cleanup    DEBUG
        RETURN
    END
    ${project}=    Get From Dictionary    ${project_data}    name

    ${count}=    Get Length    ${CREATED_AIWB_SECRET_NAMES}
    IF    ${count} == 0
        Log    No AIWB secrets to clean up    DEBUG
        RETURN
    END
    Log    Cleaning up ${count} AIWB secret(s)    INFO

    FOR    ${k8s_name}    IN    @{CREATED_AIWB_SECRET_NAMES}
        TRY
            Delete AIWB Secret    ${project}    ${k8s_name}    expected_status=any
            Log    Deleted AIWB secret ${k8s_name}    DEBUG
        EXCEPT    AS    ${error}
            Log    Failed to delete AIWB secret ${k8s_name}: ${error}    WARN
        END
    END

    @{empty_list}=    Create List
    Set Suite Variable    @{CREATED_AIWB_SECRET_NAMES}    @{empty_list}
    Log    AIWB secret cleanup complete    INFO

A secret "${name}" with use case "${use_case}" is created via AIWB
    [Documentation]    Creates a secret via the AIWB API with the given display name and use case.
    ...    Uses TestPrefix to generate a unique full name for concurrency safety.
    ...    ImagePullSecret use case requires .dockerconfigjson key with valid Docker config JSON.
    ...    Requires: TEST_PROJECT (set by project setup keywords).
    ...    Sets: TEST_AIWB_SECRET_NAME (display name), TEST_AIWB_SECRET_K8S_NAME (K8s resource name)
    ${full_name}=    Test Name    ${name}
    ${project}=    Get Project Namespace

    IF    "${use_case}" == "ImagePullSecret"
        ${docker_config}=    Set Variable    {"auths":{"registry.example.com":{"username":"user","password":"pass","auth":"dXNlcjpwYXNz"}}}
        ${encoded_value}=    Evaluate    base64.b64encode(b'${docker_config}').decode()    modules=base64
        &{secret_data}=    Create Dictionary    .dockerconfigjson=${encoded_value}
    ELSE IF    "${use_case}" == "S3"
        ${encoded_access}=    Evaluate    base64.b64encode(b"test-access-key").decode()    modules=base64
        ${encoded_secret}=    Evaluate    base64.b64encode(b"test-secret-key").decode()    modules=base64
        &{secret_data}=    Create Dictionary
        ...    accessKeyId=${encoded_access}
        ...    secretAccessKey=${encoded_secret}
    ELSE
        ${encoded_value}=    Evaluate    base64.b64encode(b"test-value").decode()    modules=base64
        &{secret_data}=    Create Dictionary    token=${encoded_value}
    END
    &{body}=    Create Dictionary
    ...    displayName=${full_name}
    ...    data=${secret_data}
    ...    useCase=${use_case}

    ${response}=    Create AIWB Secret    ${project}    ${body}    expected_status=201

    ${k8s_name}=    Set Variable    ${response.json()['metadata']['name']}
    Set Test Variable    ${TEST_AIWB_SECRET_NAME}    ${full_name}
    Set Test Variable    ${TEST_AIWB_SECRET_K8S_NAME}    ${k8s_name}
    Append To List    ${CREATED_AIWB_SECRET_NAMES}    ${k8s_name}
    Log    Created AIWB secret: displayName=${full_name}, k8sName=${k8s_name}, useCase=${use_case}    INFO

A secret "${name}" is created via AIWB
    [Documentation]    Creates a secret via AIWB API with Generic use case.
    ...    Convenience wrapper that defaults to Generic use case.
    A secret "${name}" with use case "Generic" is created via AIWB

List All AIWB Secrets
    [Documentation]    Returns every secret in the namespace as a single list, paging
    ...    through the API's paginated envelope so callers that scan the full set are
    ...    not silently truncated at the default page size.
    [Arguments]    ${namespace}
    VAR    @{all_secrets}    @{EMPTY}
    VAR    ${page}    ${1}
    WHILE    $True    limit=1000
        ${response}=    List AIWB Secrets    ${namespace}    page=${page}    page_size=100    expected_status=200
        ${body}=    Set Variable    ${response.json()}
        ${data}=    Get From Dictionary    ${body}    data
        ${page_count}=    Get Length    ${data}
        IF    ${page_count} == 0    BREAK
        Append To List    ${all_secrets}    @{data}
        ${pagination}=    Get From Dictionary    ${body}    pagination    default=&{EMPTY}
        ${total}=    Get From Dictionary    ${pagination}    total    default=${0}
        ${collected}=    Get Length    ${all_secrets}
        # Only trust total when the envelope reports it; otherwise page until an empty page.
        IF    ${total} > 0 and ${collected} >= ${total}    BREAK
        ${page}=    Evaluate    ${page} + 1
    END
    RETURN    ${all_secrets}

Get AIWB Secret K8s Name By Display Name
    [Documentation]    Lists secrets and returns the K8s resource name matching the given display name.
    ...    Fails if no secret with the given display name exists.
    [Arguments]    ${namespace}    ${display_name}
    ${secrets_list}=    List All AIWB Secrets    ${namespace}

    FOR    ${secret}    IN    @{secrets_list}
        ${dn}=    Get From Dictionary    ${secret}    displayName    default=${None}
        IF    '${dn}' == '${display_name}'
            ${k8s_name}=    Set Variable    ${secret['metadata']['name']}
            RETURN    ${k8s_name}
        END
    END
    FAIL    No secret with displayName '${display_name}' found in namespace ${namespace}

AIWB secret "${name}" should exist
    [Documentation]    Verifies that a secret with the given display name exists in the namespace.
    ...    GET keys on the auto-generated K8s name, so resolve it from the display name first.
    ${full_name}=    Test Name    ${name}
    ${project}=    Get Project Namespace

    ${k8s_name}=    Get AIWB Secret K8s Name By Display Name    ${project}    ${full_name}
    Get AIWB Secret    ${project}    ${k8s_name}    expected_status=200
    Log    AIWB secret ${full_name} exists    INFO

AIWB secret "${name}" should not exist
    [Documentation]    Verifies that no secret with the given display name exists (after deletion).
    ...    Asserts absence from the full paginated list, as the K8s name may be unknown
    ...    when secret creation was rejected.
    ${full_name}=    Test Name    ${name}
    ${project}=    Get Project Namespace
    ${secrets_list}=    List All AIWB Secrets    ${project}

    FOR    ${secret}    IN    @{secrets_list}
        ${display_name}=    Get From Dictionary    ${secret}    displayName    default=${None}
        Should Not Be Equal    ${display_name}    ${full_name}
        ...    msg=Secret with displayName '${full_name}' should be absent but is present
    END
    Log    AIWB secret ${full_name} confirmed not found    INFO

AIWB secrets are listed
    [Documentation]    Lists all AIWB secrets for the current project.
    ...    Sets: TEST_RESPONSE
    ${project}=    Get Project Namespace

    ${response}=    List AIWB Secrets    ${project}    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Log    Listed AIWB secrets for project ${project}    INFO

AIWB secrets filtered by use case "${use_case}" should return "${count}" results
    [Documentation]    Lists AIWB secrets filtered by useCase and verifies the count.
    ${project}=    Get Project Namespace

    ${response}=    List AIWB Secrets    ${project}    use_case=${use_case}    expected_status=200
    ${secrets_list}=    Set Variable    ${response.json()['data']}
    ${actual_count}=    Get Length    ${secrets_list}
    Should Be Equal As Integers    ${actual_count}    ${count}
    ...    msg=Expected ${count} secrets for useCase ${use_case}, found ${actual_count}
    Log    Filtered secret count for useCase=${use_case}: ${actual_count}    INFO


AIWB secret "${name}" is deleted
    [Documentation]    Deletes an AIWB secret by finding its K8s resource name via display name lookup.
    ${full_name}=    Test Name    ${name}
    ${project}=    Get Project Namespace

    ${k8s_name}=    Get AIWB Secret K8s Name By Display Name    ${project}    ${full_name}
    Delete AIWB Secret    ${project}    ${k8s_name}    expected_status=204
    Log    Deleted AIWB secret ${full_name}    INFO

An S3 secret "${name}" without credentials is submitted via AIWB
    [Documentation]    Attempts to create an S3 secret whose data carries no recognized
    ...    access/secret key alias, and captures the response for outcome assertions.
    ...    Sets: TEST_RESPONSE
    ${full_name}=    Test Name    ${name}
    ${project}=    Get Project Namespace
    ${encoded_value}=    Evaluate    base64.b64encode(b"test-value").decode()    modules=base64
    &{secret_data}=    Create Dictionary    unrelated=${encoded_value}
    &{body}=    Create Dictionary
    ...    displayName=${full_name}
    ...    data=${secret_data}
    ...    useCase=S3

    ${response}=    Create AIWB Secret    ${project}    ${body}    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Log    Submitted S3 secret without credentials; captured response for assertions    INFO

Creating duplicate AIWB secret "${name}" should fail
    [Documentation]    Verifies that creating a secret with the same display name fails with 409.
    ${full_name}=    Test Name    ${name}
    ${project}=    Get Project Namespace
    ${encoded_value}=    Evaluate    base64.b64encode(b"test-value").decode()    modules=base64
    &{secret_data}=    Create Dictionary    token=${encoded_value}
    &{body}=    Create Dictionary
    ...    displayName=${full_name}
    ...    data=${secret_data}
    ...    useCase=Generic

    ${response}=    Create AIWB Secret    ${project}    ${body}    expected_status=409
    Log    Duplicate AIWB secret creation correctly rejected with 409    INFO

AIWB secret display name should be "${expected}"
    [Documentation]    Verifies the most recently created secret has the expected display name.
    ...    Requires: TEST_AIWB_SECRET_K8S_NAME
    Should Not Be Equal    ${TEST_AIWB_SECRET_K8S_NAME}    ${None}
    ...    msg=TEST_AIWB_SECRET_K8S_NAME not set. Create an AIWB secret first.
    ${namespace}=    Get Project Namespace
    ${response}=    Get AIWB Secret    ${namespace}    ${TEST_AIWB_SECRET_K8S_NAME}    expected_status=200
    ${actual}=    Set Variable    ${response.json()['displayName']}
    Should Be Equal    ${actual}    ${expected}
    ...    msg=Expected displayName '${expected}', got '${actual}'
    Log    Secret displayName verified: ${actual}    INFO

AIWB secret K8s name should be auto-generated
    [Documentation]    Verifies the K8s resource name is a valid auto-generated identifier
    ...    (non-empty, a valid Kubernetes DNS subdomain, and different from the display name).
    ...    Requires: TEST_AIWB_SECRET_NAME, TEST_AIWB_SECRET_K8S_NAME
    Should Not Be Equal    ${TEST_AIWB_SECRET_K8S_NAME}    ${None}
    ...    msg=TEST_AIWB_SECRET_K8S_NAME not set. Create an AIWB secret first.
    Should Match Regexp    ${TEST_AIWB_SECRET_K8S_NAME}    ^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$
    ...    msg=K8s name '${TEST_AIWB_SECRET_K8S_NAME}' is not a valid Kubernetes DNS subdomain
    Should Not Be Equal    ${TEST_AIWB_SECRET_K8S_NAME}    ${TEST_AIWB_SECRET_NAME}
    ...    msg=K8s resource name should differ from display name
    Log    K8s name '${TEST_AIWB_SECRET_K8S_NAME}' is auto-generated and differs from displayName '${TEST_AIWB_SECRET_NAME}'    INFO

A secret is created with display name "${display_name}"
    [Documentation]    Creates a Generic secret with an arbitrary display name (no TestPrefix applied).
    ...    Used to test special characters, unicode, and spaces in display names.
    ...    A short unique hex suffix is appended to avoid conflicts on reruns or parallel runs.
    ...    Sets: TEST_AIWB_SECRET_NAME, TEST_AIWB_SECRET_K8S_NAME
    ${namespace}=    Get Project Namespace
    ${suffix}=    Evaluate    uuid.uuid4().hex[:6]    modules=uuid
    ${unique_display_name}=    Set Variable    ${display_name}-${suffix}
    ${encoded_value}=    Evaluate    base64.b64encode(b"test-value").decode()    modules=base64
    &{secret_data}=    Create Dictionary    token=${encoded_value}
    &{body}=    Create Dictionary
    ...    displayName=${unique_display_name}
    ...    data=${secret_data}
    ...    useCase=Generic

    ${response}=    Create AIWB Secret    ${namespace}    ${body}    expected_status=201
    ${k8s_name}=    Set Variable    ${response.json()['metadata']['name']}
    Log    Created AIWB secret ${unique_display_name}    INFO
    Set Test Variable    ${TEST_AIWB_SECRET_NAME}    ${unique_display_name}
    Set Test Variable    ${TEST_AIWB_SECRET_K8S_NAME}    ${k8s_name}
    Append To List    ${CREATED_AIWB_SECRET_NAMES}    ${k8s_name}
    Log    Created AIWB secret: displayName=${unique_display_name}, k8sName=${k8s_name}    INFO

The secret list should include display name for "${name}"
    [Documentation]    Verifies a secret with the given (TestPrefix-qualified) display name
    ...    appears with a non-empty displayName field. Pages through the full secret list so a
    ...    secret that lands on a later page is not missed at the API's default page size.
    ${full_name}=    Test Name    ${name}
    ${namespace}=    Get Project Namespace
    ${secrets_list}=    List All AIWB Secrets    ${namespace}

    FOR    ${secret}    IN    @{secrets_list}
        ${dn}=    Get From Dictionary    ${secret}    displayName    default=${None}
        IF    '${dn}' == '${full_name}'
            Should Not Be Empty    ${dn}    msg=displayName field should not be empty
            Log    Display name '${full_name}' found in list response    INFO
            RETURN
        END
    END
    FAIL    Secret with displayName '${full_name}' not found in list response

# API contract — camelCase error envelope keywords

An image pull secret with invalid JSON content is submitted
    [Documentation]    Submits an image pull secret whose .dockerconfigjson value is not
    ...    valid JSON. The API rejects it with a validation error whose detail carries
    ...    the parse-error message — the trigger that exercises the additionalInfo field.
    ...    Sets: TEST_RESPONSE
    ${project}=    Get Project Namespace
    ${display_name}=    Test Name    invalid-pull-secret-contract-check
    ${bad_b64}=    Evaluate    __import__('base64').b64encode(b'not-valid-json').decode()    modules=base64
    &{secret_data}=    Create Dictionary    .dockerconfigjson=${bad_b64}
    &{body}=    Create Dictionary
    ...    displayName=${display_name}
    ...    data=${secret_data}
    ...    useCase=ImagePullSecret
    ${response}=    Create AIWB Secret    ${project}    ${body}    expected_status=any
    IF    ${response.status_code} == 201
        ${k8s_name}=    Set Variable    ${response.json()['metadata']['name']}
        Append To List    ${CREATED_AIWB_SECRET_NAMES}    ${k8s_name}
    END
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The response should fail with a validation error
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    400
    ...    msg=Expected 400 validation error, got ${TEST_RESPONSE.status_code}. Body: ${TEST_RESPONSE.text}

The error envelope should expose extra context under "${key}"
    VAR    ${body}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${body}    ${key}
    ...    msg=Error envelope missing required key '${key}'. Actual keys: ${body.keys()}. Body: ${body}
    ${value}=    Get From Dictionary    ${body}    ${key}
    Should Not Be Empty    ${value}
    ...    msg=Key '${key}' is present but empty. Body: ${body}

The error envelope should not contain "${key}"
    VAR    ${body}    ${TEST_RESPONSE.json()}
    Dictionary Should Not Contain Key    ${body}    ${key}
    ...    msg=Error envelope must not expose snake_case key '${key}'. Actual keys: ${body.keys()}. Body: ${body}

# Cross-service autodiscovery keywords

AIWB secret should be discovered by AIRM
    [Documentation]    Verifies the AIWB-created secret appears in the AIRM API via autodiscovery.
    ...    Polls because the autodiscovery pipeline is asynchronous.
    ...    Requires: TEST_AIWB_SECRET_K8S_NAME
    Should Not Be Equal    ${TEST_AIWB_SECRET_K8S_NAME}    ${None}
    ...    msg=TEST_AIWB_SECRET_K8S_NAME not set. Create an AIWB secret first.

    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Find AIWB secret in AIRM API    ${TEST_AIWB_SECRET_K8S_NAME}
    Log    AIWB secret discovered by AIRM autodiscovery    INFO

Find AIWB secret in AIRM API
    [Documentation]    Searches the AIRM secrets list for a secret matching the given K8s resource name.
    ...    Fails if not found (used with polling).
    [Arguments]    ${k8s_name}

    Log    Polling for AIWB secret ${k8s_name} in AIRM API    TRACE

    ${response}=    Get secrets    expected_status=200
    ${secrets_list}=    Set Variable    ${response.json()['data']}

    FOR    ${secret}    IN    @{secrets_list}
        ${name}=    Get From Dictionary    ${secret}    name
        IF    '${name}' == '${k8s_name}'
            ${secret_id}=    Get From Dictionary    ${secret}    id
            Set Test Variable    ${TEST_SECRET_ID}    ${secret_id}
            Track Secret For Cleanup    ${secret_id}
            Log    Found AIWB secret ${k8s_name} in AIRM API with ID: ${secret_id}    INFO
            RETURN
        END
    END

    FAIL    Secret ${k8s_name} not found in AIRM API yet

AIWB secret should be removed from AIRM
    [Documentation]    Verifies the AIWB-created secret is removed from the AIRM API after deletion.
    ...    Polls because the deletion pipeline is asynchronous.
    ...    Requires: TEST_AIWB_SECRET_K8S_NAME
    Should Not Be Equal    ${TEST_AIWB_SECRET_K8S_NAME}    ${None}
    ...    msg=TEST_AIWB_SECRET_K8S_NAME not set. Create an AIWB secret first.

    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Verify AIWB secret removed from AIRM API    ${TEST_AIWB_SECRET_K8S_NAME}
    Log    AIWB secret removed from AIRM after deletion    INFO

Verify AIWB secret removed from AIRM API
    [Documentation]    Checks that a secret with the given K8s resource name no longer appears in the AIRM API.
    ...    Fails if found (used with polling).
    [Arguments]    ${k8s_name}

    Log    Polling for removal of secret ${k8s_name} from AIRM API    TRACE

    ${response}=    Get secrets    expected_status=200
    ${secrets_list}=    Set Variable    ${response.json()['data']}

    FOR    ${secret}    IN    @{secrets_list}
        ${name}=    Get From Dictionary    ${secret}    name
        IF    '${name}' == '${k8s_name}'
            FAIL    Secret ${k8s_name} still found in AIRM API (deletion not yet processed)
        END
    END

    Log    Secret ${k8s_name} confirmed removed from AIRM API    INFO

AIRM agent pod is restarted
    [Documentation]    Restarts the AIRM agent by deleting every matching pod replica at once;
    ...    the Deployment recreates them. Avoids patch on deployments (kubectl rollout restart).
    ...    Expects label app=airm-agent on all replicas. Triggers re-reconciliation of auto-discovered secrets.
    ${result}=    Run Process    kubectl    delete    pods
    ...    -n    airm
    ...    -l    app\=airm-agent
    ...    --wait\=false
    ...    stderr=PIPE
    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to delete AIRM agent pod replica(s): ${result.stderr}
    Log    Delete issued for all airm-agent replicas; replacements will be scheduled    INFO

AIRM agent pod should be ready
    [Documentation]    Waits for the AIRM agent pod to be ready after restart.
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Verify AIRM agent pod ready

Verify AIRM agent pod ready
    [Documentation]    Helper: checks that the AIRM agent deployment has ready replicas.
    ${result}=    Run Process    kubectl    rollout    status
    ...    deployment/airm-agent    -n    airm    --timeout\=10s
    ...    stderr=PIPE
    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=AIRM agent pod not ready: ${result.stderr}
    Log    AIRM agent pod is ready    INFO

AIWB auto-discovered secret should not be duplicated
    [Documentation]    Verifies no duplicate entries exist for the AIWB-created secret in AIRM.
    ...    Requires: TEST_AIWB_SECRET_K8S_NAME
    Should Not Be Equal    ${TEST_AIWB_SECRET_K8S_NAME}    ${None}
    ...    msg=TEST_AIWB_SECRET_K8S_NAME not set. Create an AIWB secret first.

    ${response}=    Get secrets    expected_status=200
    ${secrets_list}=    Set Variable    ${response.json()['data']}

    ${match_count}=    Set Variable    ${0}
    FOR    ${secret}    IN    @{secrets_list}
        ${name}=    Get From Dictionary    ${secret}    name
        IF    '${name}' == '${TEST_AIWB_SECRET_K8S_NAME}'
            ${match_count}=    Evaluate    ${match_count} + 1
        END
    END

    Should Be Equal As Integers    ${match_count}    1
    ...    msg=Expected exactly 1 secret named ${TEST_AIWB_SECRET_K8S_NAME}, found ${match_count}

    Log    No duplicate entries: secret ${TEST_AIWB_SECRET_K8S_NAME} appears exactly once in AIRM    INFO
