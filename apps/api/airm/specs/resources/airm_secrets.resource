# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level secret testing keywords.
...                 Provides business-logic level keywords for testing secret operations.
...                 Uses the low-level API keywords from api/secrets.resource to implement
...                 higher-level testing scenarios for secrets management and project assignments.
Resource            api/secrets.resource
Resource            common/airm_resource_cleanup.resource
Resource            resources/common/resource_lifecycle.resource
Resource            airm_projects.resource
Library             Collections
Library             String
Library             OperatingSystem
Library             Process


*** Variables ***
${TEST_SECRET_ID}                ${None}
${SECOND_SECRET_ID}              ${None}
# CREATED_SECRET_IDS is lazy-initialized by Track Secret For Cleanup
${TEST_SECOND_PROJECT_ID}        ${None}
${TEST_VALID_MANIFEST}           ${EMPTY}
${TEST_INVALID_MANIFEST}         ${EMPTY}
${TEST_POD_NAME}                 ${None}
${TEST_KUBECTL_ES_NAME}          ${None}
# Override these via --variable if the deployment name differs in your cluster
${AIRM_CONTROLLER_NAMESPACE}     airm
${AIRM_CONTROLLER_DEPLOYMENT}    airm-agent


*** Keywords ***

A valid ExternalSecret manifest exists
    [Documentation]    Creates a valid ExternalSecret manifest for testing.
    ...    Loads template file and replaces placeholder name with unique timestamp-based name.
    ...    Sets: TEST_VALID_MANIFEST, TEST_SECRET_NAME

    ${timestamp}=    Evaluate    int(__import__('time').time())
    ${unique_name}=    Set Variable    e2e-test-secret-${timestamp}

    # Store the target secret name for later use
    Set Test Variable    ${TEST_SECRET_NAME}    ${unique_name}

    # Load template and replace placeholder names
    ${template}=    Get File    ${CURDIR}/../test_data/secrets/valid-externalsecret.yaml
    ${manifest}=    Replace String    ${template}    name: e2e-test-secret    name: ${unique_name}

    Set Test Variable    ${TEST_VALID_MANIFEST}    ${manifest}
    Log    Valid ExternalSecret manifest created with unique name: ${unique_name}    DEBUG

An invalid ExternalSecret manifest exists
    [Documentation]    Creates an invalid ExternalSecret manifest (missing spec)

    ${manifest}=    Get File    ${CURDIR}/../test_data/secrets/invalid-externalsecret.yaml

    Set Test Variable    ${TEST_INVALID_MANIFEST}    ${manifest}
    Log    Invalid ExternalSecret manifest loaded from file    DEBUG

A valid ExternalSecret manifest with invalid path exists
    [Documentation]    Creates a valid ExternalSecret manifest but with invalid external paths
    ...    This manifest has correct structure but references non-existent secrets in the external store

    ${manifest}=    Get File    ${CURDIR}/../test_data/secrets/valid-manifest-invalid-path.yaml

    Set Test Variable    ${TEST_VALID_MANIFEST}    ${manifest}
    Log    Valid ExternalSecret manifest with invalid path loaded from file    DEBUG

Secret is created without project assignment
    [Documentation]    Creates a secret without assigning it to any project.
    ...    Uses default configuration: type=ExternalSecret, scope=Organization.
    ...    Requires: TEST_VALID_MANIFEST
    ...    Sets: TEST_SECRET_ID
    [Arguments]    ${secret_name}=${EMPTY}

    ${name}=    Run Keyword If    "${secret_name}" == "${EMPTY}"
    ...    Evaluate    "e2e-secret-" + str(int(__import__('time').time()))
    ...    ELSE    Set Variable    ${secret_name}

    Should Not Be Equal    ${TEST_VALID_MANIFEST}    ${EMPTY}
    ...    msg=Valid manifest not set. Call 'a valid ExternalSecret manifest exists' first.

    @{empty_project_ids}=    Create List

    ${secret_data}=    Create Dictionary
    ...    name=${name}
    ...    type=ExternalSecret
    ...    scope=Organization
    ...    manifest=${TEST_VALID_MANIFEST}
    ...    projectIds=${empty_project_ids}

    ${response}=    Create secret
    ...    secret_data=${secret_data}
    ...    expected_status=200

    ${secret_id}=    Get From Dictionary    ${response.json()}    id
    Set Test Variable    ${TEST_SECRET_ID}    ${secret_id}

    Track Secret For Cleanup    ${secret_id}

    Log    Created secret: id=${secret_id}, name=${name}, status=Unassigned    INFO

Secret is created and assigned to project
    [Documentation]    Creates a secret and assigns it to the current project.
    ...    Requires: TEST_VALID_MANIFEST, TEST_PROJECT_ID
    ...    Sets: TEST_SECRET_ID
    [Arguments]    ${secret_name}=${EMPTY}

    ${name}=    Run Keyword If    "${secret_name}" == "${EMPTY}"
    ...    Evaluate    "e2e-secret-" + str(int(__import__('time').time()))
    ...    ELSE    Set Variable    ${secret_name}

    Should Not Be Equal    ${TEST_VALID_MANIFEST}    ${EMPTY}
    ...    msg=Valid manifest not set. Call 'a valid ExternalSecret manifest exists' first.
    Should Not Be Equal    ${TEST_PROJECT_ID}    ${None}
    ...    msg=Current project not set. Create a project first.

    @{project_ids}=    Create List    ${TEST_PROJECT_ID}

    ${secret_data}=    Create Dictionary
    ...    name=${name}
    ...    type=ExternalSecret
    ...    scope=Organization
    ...    manifest=${TEST_VALID_MANIFEST}
    ...    projectIds=${project_ids}

    ${response}=    Create secret
    ...    secret_data=${secret_data}
    ...    expected_status=200

    ${secret_id}=    Get From Dictionary    ${response.json()}    id
    Set Test Variable    ${TEST_SECRET_ID}    ${secret_id}

    Track Secret For Cleanup    ${secret_id}

    Log    Created secret: id=${secret_id}, name=${name}, assigned to project=${TEST_PROJECT_ID}    INFO

# Removed duplicate keyword - now using shared definition from common.resource

Secret "${secret_name}" is assigned to project
    [Documentation]    Finds a secret by name and assigns it to the current project
    ...    If the secret is already assigned to the project, logs and continues
    ...    This is useful for infrastructure secrets like minio-credentials
    Should Not Be Equal    ${TEST_PROJECT_ID}    ${None}
    ...    msg=TEST_PROJECT_ID not set. Create a project first.

    # Find the secret by name
    ${response}=    Get secrets    expected_status=200
    ${secrets}=    Set Variable    ${response.json()['data']}

    ${secret_id}=    Set Variable    ${None}
    FOR    ${secret}    IN    @{secrets}
        IF    '${secret['name']}' == '${secret_name}'
            ${secret_id}=    Set Variable    ${secret['id']}
            Log    Found secret ${secret_name} with ID ${secret_id}    DEBUG
            BREAK
        END
    END

    Should Not Be Equal    ${secret_id}    ${None}
    ...    msg=Secret ${secret_name} not found in system

    # Use the additive project-scoped endpoint. The organization-scoped assign endpoint replaces
    # the whole assignment set (projects omitted from the PUT lose access), so under the
    # concurrent-run model a full-replace here would strip this shared secret from another run's
    # project. This adds only the current project and never reads the existing assignment set.
    ${assign_response}=    Assign secret to project
    ...    ${TEST_PROJECT_ID}    ${secret_id}    expected_status=any
    # Already-assigned is the endpoint's only ValidationException, returned as HTTP 400
    # ("Secret already assigned to this Project"), so treat 400 as the idempotent no-op.
    IF    ${assign_response.status_code} == 204
        Log    Assigned secret ${secret_name} to project ${TEST_PROJECT_ID}    INFO
    ELSE IF    ${assign_response.status_code} == 400
        Log    Secret ${secret_name} already assigned to project ${TEST_PROJECT_ID}    INFO
    ELSE
        Fail    Assigning secret ${secret_name} to project ${TEST_PROJECT_ID} failed (HTTP ${assign_response.status_code}): ${assign_response.text}
    END

Secret is assigned to second project
    [Documentation]    Assigns the current secret to the second project
    Should Not Be Equal    ${TEST_SECRET_ID}    ${None}
    ...    msg=TEST_SECRET_ID not set. Create secret first.
    Should Not Be Equal    ${TEST_SECOND_PROJECT_ID}    ${None}
    ...    msg=TEST_SECOND_PROJECT_ID not set. Create second project first.

    @{project_ids}=    Create List    ${TEST_PROJECT_ID}    ${TEST_SECOND_PROJECT_ID}

    ${response}=    Assign secret to projects
    ...    ${TEST_SECRET_ID}
    ...    ${project_ids}
    ...    expected_status=200

    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Log    Assigned secret ${TEST_SECRET_ID} to second project ${TEST_SECOND_PROJECT_ID}    INFO
    RETURN    ${response}

Project assignment is removed
    [Documentation]    Removes all project assignments from the secret
    Should Not Be Equal    ${TEST_SECRET_ID}    ${None}
    ...    msg=TEST_SECRET_ID not set. Create secret first.

    @{empty_list}=    Create List

    ${response}=    Assign secret to projects
    ...    ${TEST_SECRET_ID}
    ...    ${empty_list}
    ...    expected_status=200

    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Log    Removed all project assignments from secret ${TEST_SECRET_ID}    INFO
    RETURN    ${response}

Attempting to create secret with same name
    [Documentation]    Attempts to create a secret with a duplicate name (should fail with 409)
    Should Not Be Equal    ${TEST_VALID_MANIFEST}    ${EMPTY}
    ...    msg=Valid manifest not set.

    ${secret_response}=    Get secret    ${TEST_SECRET_ID}
    ${secret_name}=    Get From Dictionary    ${secret_response.json()}    name

    @{empty_project_ids}=    Create List

    ${secret_data}=    Create Dictionary
    ...    name=${secret_name}
    ...    type=ExternalSecret
    ...    scope=Organization
    ...    manifest=${TEST_VALID_MANIFEST}
    ...    projectIds=${empty_project_ids}

    ${response}=    Create secret
    ...    secret_data=${secret_data}
    ...    expected_status=409

    Set Test Variable    ${TEST_RESPONSE}    ${response}
    RETURN    ${response}

Attempting to create secret with invalid manifest
    [Documentation]    Attempts to create a secret with an invalid manifest (should fail)
    Should Not Be Equal    ${TEST_INVALID_MANIFEST}    ${EMPTY}
    ...    msg=Invalid manifest not set.

    ${secret_data}=    Create Dictionary
    ...    name=invalid-secret
    ...    type=ExternalSecret
    ...    scope=Organization
    ...    manifest=${TEST_INVALID_MANIFEST}

    ${response}=    Create secret
    ...    secret_data=${secret_data}
    ...    expected_status=422

    Set Test Variable    ${TEST_RESPONSE}    ${response}
    RETURN    ${response}

Secret should be visible via API
    [Documentation]    Verifies that the secret is visible via GET /secrets/{id}
    Should Not Be Equal    ${TEST_SECRET_ID}    ${None}
    ...    msg=TEST_SECRET_ID not set. Create secret first.

    ${response}=    Get secret    ${TEST_SECRET_ID}    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

    Log    Secret ${TEST_SECRET_ID} is visible via API    INFO
    RETURN    ${response}

Secret should not be visible via API
    [Documentation]    Verifies that the secret returns 404 via GET /secrets/{id}
    Should Not Be Equal    ${TEST_SECRET_ID}    ${None}
    ...    msg=TEST_SECRET_ID not set.

    ${response}=    Get secret    ${TEST_SECRET_ID}    expected_status=404

    Log    Secret ${TEST_SECRET_ID} correctly not found (404)    INFO

Secret should have valid ID and status
    [Documentation]    Verifies secret response contains valid id and status fields
    Should Not Be Equal    ${TEST_RESPONSE}    ${None}
    ...    msg=Response not set. Call 'secret should be visible via API' first.

    ${json}=    Set Variable    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    id
    Dictionary Should Contain Key    ${json}    status

    ${secret_id}=    Get From Dictionary    ${json}    id
    ${status}=    Get From Dictionary    ${json}    status

    Log    Secret has valid ID: ${secret_id}, Status: ${status}    INFO

Secret status should be "${expected_status}"
    [Documentation]    Verifies the secret has the expected status by fetching fresh state
    ...    Always fetches current secret state using TEST_SECRET_ID
    ...    For checking immediate API response, use 'Secret status should be "${status}" in response'
    Verify Resource Status    Get secret    ${TEST_SECRET_ID}    ${expected_status}

Secret status should be "${expected_status}" in response
    [Documentation]    Verifies the secret status in the cached ${TEST_RESPONSE} variable
    ...    Use this immediately after an API call to check the response without extra fetch
    ${json}=    Set Variable    ${TEST_RESPONSE.json()}
    ${status}=    Get From Dictionary    ${json}    status
    Should Be Equal    ${status}    ${expected_status}
    ...    msg=Expected secret status to be ${expected_status} in response, but got ${status}
    Log    Secret status in response: ${status}    INFO

Secret status should be any of "${status_list}"
    [Documentation]    Verifies secret has one of the specified statuses
    ...    Takes a comma-separated list of acceptable statuses like "Pending, Synced"
    Resource Status Should Be One Of    Get secret    ${TEST_SECRET_ID}    ${status_list}

Secret status should be any of "${status_list}" in response
    [Documentation]    Verifies secret status in cached ${TEST_RESPONSE} is one of the specified statuses
    ...    Use this immediately after an API call to check the response without extra fetch
    ${json}=    Set Variable    ${TEST_RESPONSE.json()}
    ${actual_status}=    Get From Dictionary    ${json}    status

    # Convert comma-separated string to list
    @{acceptable_statuses}=    Split String    ${status_list}    ,${SPACE}

    # Check if actual status is in the list
    ${status_found}=    Set Variable    ${FALSE}
    FOR    ${status}    IN    @{acceptable_statuses}
        IF    "${actual_status}" == "${status}"
            ${status_found}=    Set Variable    ${TRUE}
            BREAK
        END
    END

    Should Be True    ${status_found}
    ...    msg=Secret status '${actual_status}' in response not in acceptable statuses [${status_list}]
    Log    Secret status ${actual_status} in response is acceptable (one of: ${status_list})    INFO

# Backward compatibility keywords (can be removed later)
Secret status should be unassigned
    [Documentation]    DEPRECATED: Use 'Secret status should be "Unassigned"' instead
    Secret status should be "Unassigned"

Secret status should be pending
    [Documentation]    DEPRECATED: Use 'Secret status should be "Pending"' instead
    Secret status should be "Pending"

Secret status should be synced
    [Documentation]    DEPRECATED: Use 'Secret status should be "Synced"' instead
    Secret status should be "Synced"

Secret status should be deleting
    [Documentation]    DEPRECATED: Use 'Secret status should be "Deleting"' instead
    Secret status should be "Deleting"

Secret should have "${count}" project assignment
    [Documentation]    Verifies the secret has the specified number of project assignments by fetching fresh state
    ...    Always fetches current secret state using TEST_SECRET_ID
    ...    For checking immediate API response, use 'Secret should have "${count}" project assignment in response'
    ${count_int}=    Convert To Integer    ${count}

    # Fetch the latest secret state
    ${secret_response}=    Get secret    ${TEST_SECRET_ID}    expected_status=200
    ${json}=    Set Variable    ${secret_response.json()}
    ${project_secrets}=    Get From Dictionary    ${json}    projectSecrets
    ${actual_count}=    Get Length    ${project_secrets}

    Should Be Equal As Integers    ${actual_count}    ${count_int}
    ...    msg=Expected ${count_int} project assignments, found ${actual_count}

    Log    Secret has ${actual_count} project assignment(s)    INFO

Secret should have "${count}" project assignment in response
    [Documentation]    Verifies project assignment count in cached ${TEST_RESPONSE} variable
    ...    Use this immediately after an API call to check the response without extra fetch
    ${count_int}=    Convert To Integer    ${count}

    ${json}=    Set Variable    ${TEST_RESPONSE.json()}
    ${project_secrets}=    Get From Dictionary    ${json}    projectSecrets
    ${actual_count}=    Get Length    ${project_secrets}

    Should Be Equal As Integers    ${actual_count}    ${count_int}
    ...    msg=Expected ${count_int} project assignments in response, found ${actual_count}

    Log    Secret has ${actual_count} project assignment(s) in response    INFO

Secret should have "${count}" project assignments
    [Documentation]    Plural variant - calls singular keyword
    Secret should have "${count}" project assignment

Secret should have "${count}" project assignments in response
    [Documentation]    Plural variant - calls singular keyword
    Secret should have "${count}" project assignment in response

Secret transitions to "${expected_status}"
    [Documentation]    Waits for secret to transition to expected status
    ...    Polls the secret endpoint until status becomes expected value.
    ...    Fetches fresh state after success so ${response} is up to date.
    ...    Timeout reduced to 2 min - sufficient for dispatcher processing and ExternalSecret sync
    Log    Waiting for secret ${TEST_SECRET_ID} to transition to ${expected_status}    INFO
    Wait For Resource Status    Get secret    ${TEST_SECRET_ID}    ${expected_status}
    ${response}=    Get secret    ${TEST_SECRET_ID}    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Log    Secret ${TEST_SECRET_ID} successfully transitioned to ${expected_status}    INFO
    RETURN    ${response}

Verify secret has status "${expected_status}"
    [Documentation]    Helper keyword to verify secret status (used with polling)
    Verify Resource Status    Get secret    ${TEST_SECRET_ID}    ${expected_status}

# Backward compatibility keywords (can be removed later)
Secret transitions to synced
    [Documentation]    DEPRECATED: Use 'Secret transitions to "Synced"' instead
    Secret transitions to "Synced"

Verify secret is synced
    [Documentation]    DEPRECATED: Use 'Verify secret has status "Synced"' instead
    Verify secret has status "Synced"

All project assignments should be synced
    [Documentation]    Verifies that all project assignments have Synced status by fetching fresh state
    ${secret_response}=    Get secret    ${TEST_SECRET_ID}    expected_status=200
    ${json}=    Set Variable    ${secret_response.json()}
    ${project_secrets}=    Get From Dictionary    ${json}    projectSecrets

    FOR    ${project_secret}    IN    @{project_secrets}
        ${status}=    Get From Dictionary    ${project_secret}    status
        Should Be Equal    ${status}    Synced
        ...    msg=Project secret status is ${status}, expected Synced
    END

    Log    All project assignments are synced    INFO

Secret is deleted
    [Documentation]    Deletes the secret via DELETE /secrets/{id}
    Should Not Be Equal    ${TEST_SECRET_ID}    ${None}
    ...    msg=TEST_SECRET_ID not set. Create secret first.

    ${response}=    Delete secret    ${TEST_SECRET_ID}    expected_status=204

    Log    Deleted secret ${TEST_SECRET_ID} via API    INFO

Secret creation should fail with conflict
    [Documentation]    Verifies that secret creation failed with 409 Conflict
    ${status_code}=    Set Variable    ${TEST_RESPONSE.status_code}
    Should Be Equal As Integers    ${status_code}    409
    ...    msg=Expected 409 Conflict, but got ${status_code}

    Log    Secret creation correctly failed with 409 Conflict    INFO

Secret creation should fail with validation error
    [Documentation]    Verifies that secret creation failed with 422 Validation Error
    ${status_code}=    Set Variable    ${TEST_RESPONSE.status_code}
    Should Be Equal As Integers    ${status_code}    422
    ...    msg=Expected 422 Validation Error, but got ${status_code}

    Log    Secret creation correctly failed with 422 Validation Error    INFO

Secret should be deleted or deleting
    [Documentation]    Verifies that secret is either already deleted (404) or in Deleting status
    ...    This handles the case where deletion happens very quickly
    Should Not Be Equal    ${TEST_SECRET_ID}    ${None}
    ...    msg=TEST_SECRET_ID not set. Create secret first.

    # Try to get the secret - expect either 404 (deleted) or 200 (deleting)
    ${secret_response}=    Get secret    ${TEST_SECRET_ID}    expected_status=any

    IF    ${secret_response.status_code} == 404
        Log    Secret already deleted (not found) - deletion was immediate    INFO
    ELSE IF    ${secret_response.status_code} == 200
        ${json}=    Set Variable    ${secret_response.json()}
        ${status}=    Get From Dictionary    ${json}    status
        Should Be Equal    ${status}    Deleting
        ...    msg=Expected secret status to be Deleting, but got ${status}
        Log    Secret status: ${status} (will be fully deleted soon)    INFO
    ELSE
        Fail    Unexpected response status: ${secret_response.status_code}
    END

Listing all secrets
    [Documentation]    Lists all secrets for the organization
    ${response}=    Get secrets    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Log    Listed all secrets for organization    INFO
    RETURN    ${response}

At least "${count}" secret should be visible
    [Documentation]    Verifies at least the specified number of secrets are visible
    ${count_int}=    Convert To Integer    ${count}

    ${json}=    Set Variable    ${TEST_RESPONSE.json()}
    ${secrets_list}=    Get From Dictionary    ${json}    data
    ${actual_count}=    Get Length    ${secrets_list}

    Should Be True    ${actual_count} >= ${count_int}
    ...    msg=Expected at least ${count_int} secrets, found ${actual_count}

    Log    Found ${actual_count} secrets (expected at least ${count_int})    INFO

Secret ExternalSecret should exist in cluster
    [Documentation]    Verifies that secret has created ExternalSecret in Kubernetes
    ...    Uses TEST_SECRET_ID to find the ExternalSecret
    Should Not Be Equal    ${TEST_SECRET_ID}    ${None}
    ...    msg=TEST_SECRET_ID not set.

    ${secret}=    Get secret    ${TEST_SECRET_ID}    expected_status=200
    ${secret_name}=    Get From Dictionary    ${secret.json()}    name

    Log    Checking for ExternalSecret: name=${secret_name}, namespace=${TEST_PROJECT}[name]    DEBUG
    ${result}=    Run Process    kubectl    get    externalsecret
    ...    -n    ${TEST_PROJECT}[name]
    ...    ${secret_name}
    ...    -o    json
    ...    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to get ExternalSecret for secret ${TEST_SECRET_ID}. Error: ${result.stderr}

    ${externalsecret_json}=    Evaluate    json.loads(r'''${result.stdout}''')    modules=json
    Dictionary Should Contain Key    ${externalsecret_json}    metadata
    Log    ExternalSecret manifest details: ${externalsecret_json}    DEBUG

    Log    ExternalSecret verified: secret_id=${TEST_SECRET_ID}, name=${secret_name}, namespace=${TEST_PROJECT}[name]    INFO

Secret ExternalSecret should not exist in cluster
    [Documentation]    Verifies that secret ExternalSecret has been deleted from Kubernetes
    Should Not Be Equal    ${TEST_SECRET_ID}    ${None}
    ...    msg=TEST_SECRET_ID not set.

    Log    Waiting for ExternalSecret deletion for secret ${TEST_SECRET_ID}    INFO
    Wait Until Keyword Succeeds    2 min    2 sec
    ...    Verify secret ExternalSecret is deleted
    Log    ExternalSecret deletion confirmed for secret ${TEST_SECRET_ID}    INFO

Verify secret ExternalSecret is deleted
    [Documentation]    Helper keyword to verify ExternalSecret doesn't exist (used with polling)
    ${secret}=    Get secret    ${TEST_SECRET_ID}    expected_status=any
    ${secret_name}=    Get From Dictionary    ${secret.json()}    name

    ${result}=    Run Process    kubectl    get    externalsecret
    ...    -n    ${TEST_PROJECT}[name]
    ...    ${secret_name}
    ...    -o    json
    ...    stderr=PIPE

    Should Not Be Equal As Integers    ${result.rc}    0
    ...    msg=ExternalSecret still exists for secret ${TEST_SECRET_ID}

    Log    Polling: ExternalSecret deleted for secret ${TEST_SECRET_ID}    TRACE

A pod that uses the secret is deployed
    [Documentation]    Deploys a test pod that references the secret
    ...    The pod attempts to read the secret value via environment variable
    Should Not Be Equal    ${TEST_SECRET_ID}    ${None}
    ...    msg=TEST_SECRET_ID not set.
    Should Not Be Equal    ${TEST_PROJECT}[name]    ${None}
    ...    msg=TEST_PROJECT not set. Create project first.
    Should Not Be Equal    ${TEST_SECRET_NAME}    ${None}
    ...    msg=TEST_SECRET_NAME not set. Call 'a valid ExternalSecret manifest exists' first.

    # Load static pod manifest and replace secret name
    ${pod_manifest}=    Get File    ${CURDIR}/../test_data/manifests/pod-with-secret.yaml
    ${updated_manifest}=    Replace String    ${pod_manifest}    name: e2e-test-secret    name: ${TEST_SECRET_NAME}
    ${updated_manifest}=    Replace String    ${updated_manifest}    key: username    key: ACCESS_KEY_ID

    Log    Updated pod manifest to reference secret: ${TEST_SECRET_NAME}    DEBUG

    ${temp_file}=    Set Variable    /tmp/e2e-pod-with-secret.yaml
    Create File    ${temp_file}    ${updated_manifest}

    Log    Deploying test pod to namespace ${TEST_PROJECT}[name]    DEBUG
    ${result}=    Run Process    kubectl    apply
    ...    -n    ${TEST_PROJECT}[name]
    ...    -f    ${temp_file}
    ...    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to deploy pod: ${result.stderr}

    Set Test Variable    ${TEST_POD_NAME}    e2e-pod-with-secret
    Log    Deployed test pod: name=${TEST_POD_NAME}, namespace=${TEST_PROJECT}[name]    INFO

Pod can access secret values
    [Documentation]    Verifies that the pod successfully accessed secret values
    ...    Checks pod logs or status to confirm secret was mounted/readable
    Should Not Be Equal    ${TEST_POD_NAME}    ${None}
    ...    msg=TEST_POD_NAME not set.
    Should Not Be Equal    ${TEST_PROJECT}[name]    ${None}
    ...    msg=TEST_PROJECT not set. Create project first.

    Log    Waiting for pod ${TEST_POD_NAME} to access secret    INFO
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Verify pod accessed secret
    Log    Pod ${TEST_POD_NAME} successfully accessed secret values    INFO

Verify pod accessed secret
    [Documentation]    Helper to verify pod successfully read secret
    ${cmd}=    Set Variable    kubectl get pod ${TEST_POD_NAME} -n ${TEST_PROJECT}[name] -o jsonpath={.status.phase}
    ${result}=    Run Process    bash    -c    ${cmd}    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to get pod status: ${result.stderr}

    ${phase}=    Set Variable    ${result.stdout}
    Log    Polling: pod phase=${phase}    TRACE

    Should Match Regexp    ${phase}    ^(Running|Succeeded)$
    ...    msg=Pod is in phase ${phase}, expected Running or Succeeded

    ${log_result}=    Run Process    kubectl    logs
    ...    -n    ${TEST_PROJECT}[name]
    ...    ${TEST_POD_NAME}
    ...    stderr=PIPE

    Should Be Equal As Integers    ${log_result.rc}    0
    ...    msg=Failed to get pod logs: ${log_result.stderr}

    Should Contain    ${log_result.stdout}    SECRET_USERNAME
    ...    msg=Pod logs don't contain SECRET_USERNAME - secret was not mounted

    Log    Polling: pod accessed secret successfully    TRACE

Clean up test pod
    [Documentation]    Removes the test pod from the namespace
    IF    '${TEST_POD_NAME}' != '${None}'
        Log    Deleting test pod ${TEST_POD_NAME}    DEBUG
        ${result}=    Run Process    kubectl    delete    pod
        ...    -n    ${TEST_PROJECT}[name]
        ...    ${TEST_POD_NAME}
        ...    --ignore-not-found
        ...    stderr=PIPE
        IF    ${result.rc} == 0
            Log    Test pod ${TEST_POD_NAME} deleted successfully    INFO
        ELSE
            Log    Failed to delete test pod ${TEST_POD_NAME}: ${result.stderr}    WARN
        END
    END

Secret with invalid path is created and assigned to project
    [Documentation]    Creates a secret with invalid external path and assigns it to the current project
    ...    This secret will have a valid manifest structure but will fail to sync due to invalid paths
    [Arguments]    ${secret_name}=${EMPTY}

    ${name}=    Run Keyword If    "${secret_name}" == "${EMPTY}"
    ...    Evaluate    "e2e-secret-invalid-" + str(int(__import__('time').time()))
    ...    ELSE    Set Variable    ${secret_name}

    Should Not Be Equal    ${TEST_VALID_MANIFEST}    ${EMPTY}
    ...    msg=Valid manifest not set. Call 'a valid ExternalSecret manifest with invalid path exists' first.
    Should Not Be Equal    ${TEST_PROJECT_ID}    ${None}
    ...    msg=Current project not set. Create a project first.

    @{project_ids}=    Create List    ${TEST_PROJECT_ID}

    ${secret_data}=    Create Dictionary
    ...    name=${name}
    ...    type=ExternalSecret
    ...    scope=Organization
    ...    manifest=${TEST_VALID_MANIFEST}
    ...    projectIds=${project_ids}

    ${response}=    Create secret
    ...    secret_data=${secret_data}
    ...    expected_status=200

    ${secret_id}=    Get From Dictionary    ${response.json()}    id
    Set Test Variable    ${TEST_SECRET_ID}    ${secret_id}

    Track Secret For Cleanup    ${secret_id}

    Log    Created secret with invalid path: id=${secret_id}, name=${name}, assigned to project=${TEST_PROJECT_ID}    INFO

Secret initial status should be pending
    [Documentation]    Verifies the secret initially has Pending or SyncedError status after creation
    ...    For invalid secrets, it may immediately go to SyncedError without Pending state
    ${json}=    Set Variable    ${TEST_RESPONSE.json()}
    ${status}=    Get From Dictionary    ${json}    status
    # Allow both Pending and SyncedError for initial status (can fail immediately)
    ${valid_status}=    Evaluate    "${status}" in ["Pending", "SyncedError"]
    Should Be True    ${valid_status}
    ...    msg=Expected initial secret status to be Pending or SyncedError, but got ${status}
    Log    Initial secret status: ${status}    INFO

Secret with invalid path transitions to error state
    [Documentation]    Waits for secret with invalid path to transition to SyncedError status
    ...    Polls the secret endpoint until status becomes SyncedError.
    ...    Fetches fresh state after success so ${TEST_RESPONSE} is up to date.
    ...    Timeout reduced to 2 min - sufficient for dispatcher processing and sync attempts
    Log    Waiting for secret ${TEST_SECRET_ID} to transition to SyncedError    INFO
    Wait For Resource Status    Get secret    ${TEST_SECRET_ID}    SyncedError
    ${response}=    Get secret    ${TEST_SECRET_ID}    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Log    Secret ${TEST_SECRET_ID} successfully transitioned to SyncedError    INFO

Verify secret is in error state
    [Documentation]    Helper keyword to verify secret has SyncedError status (used with polling)
    Verify Resource Status    Get secret    ${TEST_SECRET_ID}    SyncedError

Secret status should be synced error
    [Documentation]    Verifies the secret has SyncedError status
    ${json}=    Set Variable    ${TEST_RESPONSE.json()}
    ${status}=    Get From Dictionary    ${json}    status
    Should Be Equal    ${status}    SyncedError
    ...    msg=Expected secret status to be SyncedError, but got ${status}

    # Optionally check for error message if available
    ${error_message}=    Get From Dictionary    ${json}    errorMessage    ${None}
    Run Keyword If    '${error_message}' != '${None}'
    ...    Log    Secret error message: ${error_message}    WARN

    Log    Secret status confirmed: ${status}    INFO

Get secret name
    [Documentation]    Retrieves the name of the current test secret
    Should Not Be Equal    ${TEST_SECRET_ID}    ${None}
    ...    msg=TEST_SECRET_ID not set. Create secret first.

    ${response}=    Get secret    ${TEST_SECRET_ID}    expected_status=200
    ${secret_json}=    Set Variable    ${response.json()}
    ${secret_name}=    Get From Dictionary    ${secret_json}    name
    RETURN    ${secret_name}

Wait for secret deletion to complete
    [Documentation]    Polls until secret is fully deleted from the system
    ...    For unassigned secrets, deletion is immediate
    ...    For assigned secrets, waits for DELETED status then removal
    Log    Waiting for secret ${TEST_SECRET_ID} deletion to complete    INFO
    Wait For Resource Deletion    Get secret    ${TEST_SECRET_ID}
    Log    Secret ${TEST_SECRET_ID} deletion completed successfully    INFO

Verify secret is fully deleted
    [Documentation]    Helper to verify secret no longer exists (404)
    Resource Should Not Exist    Get secret    ${TEST_SECRET_ID}

Secret with same name "${name}" can be created
    [Documentation]    Creates a new secret with the specified name after deletion
    ...    Validates that name constraint allows recreation
    Should Not Be Equal    ${TEST_VALID_MANIFEST}    ${EMPTY}
    ...    msg=Valid manifest not set. Call 'a valid ExternalSecret manifest exists' first.

    @{empty_project_ids}=    Create List

    ${secret_data}=    Create Dictionary
    ...    name=${name}
    ...    type=ExternalSecret
    ...    scope=Organization
    ...    manifest=${TEST_VALID_MANIFEST}
    ...    projectIds=${empty_project_ids}

    ${response}=    Create secret
    ...    secret_data=${secret_data}
    ...    expected_status=200

    ${new_secret_id}=    Get From Dictionary    ${response.json()}    id
    Set Test Variable    ${TEST_NEW_SECRET_ID}    ${new_secret_id}

    Track Secret For Cleanup    ${new_secret_id}

    Log    Created secret with reused name: id=${new_secret_id}, name=${name}    INFO

New secret should have different ID than "${old_id}"
    [Documentation]    Verifies the recreated secret has a different ID
    Should Not Be Equal    ${TEST_NEW_SECRET_ID}    ${old_id}
    ...    msg=Recreated secret has same ID as deleted secret
    Log    New secret ID ${TEST_NEW_SECRET_ID} differs from old ID ${old_id}    INFO

# --- Kubectl-based auto-discovery keywords ---

A Kubernetes secret is applied via kubectl
    [Documentation]    Creates a plain Opaque K8s Secret in the project namespace via kubectl.
    ...    The mutating webhook should intercept it and inject tracking labels.
    Should Not Be Equal    ${TEST_PROJECT}    ${None}
    ...    msg=TEST_PROJECT not set. Create a project first.

    ${timestamp}=    Evaluate    int(__import__('time').time())
    ${secret_name}=    Set Variable    e2e-autodiscovered-${timestamp}
    Set Test Variable    ${TEST_KUBECTL_SECRET_NAME}    ${secret_name}

    ${result}=    Run Process    kubectl    create    secret    generic
    ...    ${secret_name}
    ...    --from-literal\=test-key\=test-value
    ...    -n    ${TEST_PROJECT}[name]
    ...    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to create K8s secret via kubectl: ${result.stderr}

    Log    Applied K8s secret via kubectl: name=${secret_name}, namespace=${TEST_PROJECT}[name]    INFO

Kubectl secret should have tracking labels
    [Documentation]    Verifies that the webhook injected tracking labels on the K8s Secret.
    ...    Polls because the webhook mutation should be synchronous on CREATE,
    ...    but allows a short window for propagation.
    Should Not Be Equal    ${TEST_KUBECTL_SECRET_NAME}    ${None}
    ...    msg=TEST_KUBECTL_SECRET_NAME not set. Apply a secret via kubectl first.

    Wait Until Keyword Succeeds    30 sec    2 sec
    ...    Verify kubectl secret has tracking labels

Verify kubectl secret has tracking labels
    [Documentation]    Helper: checks that the K8s Secret has the expected AIRM tracking labels.
    ${result}=    Run Process    kubectl    get    secret
    ...    ${TEST_KUBECTL_SECRET_NAME}
    ...    -n    ${TEST_PROJECT}[name]
    ...    -o    jsonpath\={.metadata.labels}
    ...    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to get secret labels: ${result.stderr}

    ${labels}=    Set Variable    ${result.stdout}
    Should Contain    ${labels}    airm.silogen.ai/project-secret-id
    ...    msg=Secret missing project-secret-id tracking label (webhook may not have intercepted)
    Should Contain    ${labels}    airm.silogen.ai/project-id
    ...    msg=Secret missing project-id tracking label

    Log    Tracking labels verified on kubectl secret ${TEST_KUBECTL_SECRET_NAME}    INFO

Secret SHOULD be discovered by AIRM
    [Documentation]    Verifies the auto-discovered secret appears in the AIRM API.
    ...    Fails the test if the secret is not found within the timeout.
    [Arguments]    ${expected_kind}=KubernetesSecret
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Find auto-discovered secret in AIRM API    ${TEST_KUBECTL_SECRET_NAME}    ${expected_kind}
    Log    Secret discovered by AIRM: kind=${expected_kind}, name=${TEST_KUBECTL_SECRET_NAME}    INFO

Find auto-discovered secret in AIRM API
    [Documentation]    Searches the secrets list for a secret matching the given name and kind.
    ...    Fails if not found (used with polling).
    ...    Sets TEST_SECRET_ID when found.
    [Arguments]    ${secret_name}    ${expected_kind}=${None}

    Log    Polling for auto-discovered secret ${secret_name} (kind=${expected_kind}) in AIRM API    TRACE

    ${response}=    Get secrets    expected_status=200
    ${secrets_list}=    Set Variable    ${response.json()['data']}

    FOR    ${secret}    IN    @{secrets_list}
        ${name}=    Get From Dictionary    ${secret}    name
        IF    '${name}' == '${secret_name}'
            IF    $expected_kind != $None
                ${kind}=    Get From Dictionary    ${secret}    type    ${None}
                IF    $kind != $expected_kind
                    CONTINUE
                END
            END
            ${secret_id}=    Get From Dictionary    ${secret}    id
            Set Test Variable    ${TEST_SECRET_ID}    ${secret_id}
            Track Secret For Cleanup    ${secret_id}
            Log    Discovered secret ${secret_name} in AIRM API: id=${secret_id}, kind=${expected_kind}    INFO
            RETURN
        END
    END

    FAIL    Secret ${secret_name} (kind=${expected_kind}) not found in AIRM API yet

Kubectl secret is deleted
    [Documentation]    Deletes the kubectl-applied secret from the namespace via kubectl.
    ...    This simulates a user running 'kubectl delete secret <name>'.
    Should Not Be Equal    ${TEST_KUBECTL_SECRET_NAME}    ${None}
    ...    msg=TEST_KUBECTL_SECRET_NAME not set. Apply a secret via kubectl first.
    Should Not Be Equal    ${TEST_PROJECT}    ${None}
    ...    msg=TEST_PROJECT not set. Create a project first.

    ${result}=    Run Process    kubectl    delete    secret
    ...    ${TEST_KUBECTL_SECRET_NAME}
    ...    -n    ${TEST_PROJECT}[name]
    ...    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to delete K8s secret via kubectl: ${result.stderr}

    Log    Deleted K8s secret via kubectl: name=${TEST_KUBECTL_SECRET_NAME}, namespace=${TEST_PROJECT}[name]    INFO

Secret SHOULD be removed from AIRM
    [Documentation]    Verifies the auto-discovered secret is removed from the AIRM API
    ...    after kubectl deletion. Polls because the deletion pipeline is asynchronous
    ...    (controller → finalizer → DELETED status → API cleanup).
    ...    Fails the test if the secret is not removed within the timeout.
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Verify auto-discovered secret removed from AIRM API    ${TEST_KUBECTL_SECRET_NAME}
    Log    Secret removed from AIRM after kubectl deletion    INFO

Verify auto-discovered secret removed from AIRM API
    [Documentation]    Checks that a secret with the given name no longer appears in the AIRM API.
    ...    Fails if found (used with polling).
    [Arguments]    ${secret_name}

    Log    Polling for removal of secret ${secret_name} from AIRM API    TRACE

    ${response}=    Get secrets    expected_status=200
    ${secrets_list}=    Set Variable    ${response.json()['data']}

    FOR    ${secret}    IN    @{secrets_list}
        ${name}=    Get From Dictionary    ${secret}    name
        IF    '${name}' == '${secret_name}'
            FAIL    Secret ${secret_name} still found in AIRM API (deletion not yet processed)
        END
    END

    Log    Secret ${secret_name} confirmed removed from AIRM API    INFO

Kubectl secret should still exist
    [Documentation]    Verifies that the kubectl-applied K8s Secret still exists in the cluster.
    ...    Used to confirm secrets survive pod restarts.
    Should Not Be Equal    ${TEST_KUBECTL_SECRET_NAME}    ${None}
    ...    msg=TEST_KUBECTL_SECRET_NAME not set. Apply a secret via kubectl first.

    Wait Until Keyword Succeeds    30 sec    5 sec
    ...    Verify kubectl secret still exists

Verify kubectl secret still exists
    [Documentation]    Helper: checks that the K8s Secret exists in the project namespace.
    ${result}=    Run Process    kubectl    get    secret
    ...    ${TEST_KUBECTL_SECRET_NAME}
    ...    -n    ${TEST_PROJECT}[name]
    ...    -o    name
    ...    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=K8s Secret ${TEST_KUBECTL_SECRET_NAME} no longer exists in cluster: ${result.stderr}

    Log    K8s Secret ${TEST_KUBECTL_SECRET_NAME} still exists in cluster    INFO

Auto-discovered secret should not be duplicated
    [Documentation]    Verifies no duplicate entries exist for the auto-discovered secret.
    ...    Checks that the secret ID matches the original and only one entry exists.
    [Arguments]    ${original_secret_id}

    ${response}=    Get secrets    expected_status=200
    ${secrets_list}=    Set Variable    ${response.json()['data']}

    ${match_count}=    Set Variable    ${0}
    FOR    ${secret}    IN    @{secrets_list}
        ${name}=    Get From Dictionary    ${secret}    name
        IF    '${name}' == '${TEST_KUBECTL_SECRET_NAME}'
            ${match_count}=    Evaluate    ${match_count} + 1
            ${found_id}=    Get From Dictionary    ${secret}    id
            Should Be Equal As Strings    ${found_id}    ${original_secret_id}
            ...    msg=Secret ID mismatch: expected ${original_secret_id}, got ${found_id} (possible duplicate)
        END
    END

    Should Be Equal As Integers    ${match_count}    1
    ...    msg=Expected exactly 1 secret named ${TEST_KUBECTL_SECRET_NAME}, found ${match_count}

    Log    No duplicate entries: secret ${TEST_KUBECTL_SECRET_NAME} has unique ID ${original_secret_id}    INFO

A Kubernetes secret with use-case "${use_case}" is applied via kubectl
    [Documentation]    Creates a K8s Secret with an airm.silogen.ai/use-case label via kubectl apply.
    ...    Uses JSON manifest to include the label at creation time so the webhook
    ...    and controller see it during initial processing.
    Should Not Be Equal    ${TEST_PROJECT}    ${None}
    ...    msg=TEST_PROJECT not set. Create a project first.

    ${timestamp}=    Evaluate    int(__import__('time').time())
    ${secret_name}=    Set Variable    e2e-usecase-${timestamp}
    Set Test Variable    ${TEST_KUBECTL_SECRET_NAME}    ${secret_name}

    ${namespace}=    Set Variable    ${TEST_PROJECT}[name]
    ${manifest}=    Catenate    SEPARATOR=
    ...    {"apiVersion":"v1","kind":"Secret",
    ...    "metadata":{"name":"${secret_name}",
    ...    "namespace":"${namespace}",
    ...    "labels":{"airm.silogen.ai/use-case":"${use_case}"}},
    ...    "type":"Opaque",
    ...    "stringData":{"test-key":"test-value"}}

    ${result}=    Run Process    bash    -c
    ...    echo '${manifest}' | kubectl apply -f -
    ...    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to create K8s secret with use-case label: ${result.stderr}

    Log    Applied K8s secret with use-case="${use_case}": name=${secret_name}, namespace=${namespace}    INFO

Discovered secret should have use case "${expected_use_case}"
    [Documentation]    Verifies the auto-discovered secret has the expected use_case value.
    ...    Polls because the use_case may need time to propagate through the pipeline.
    ...    Requires TEST_SECRET_ID (set by 'secret SHOULD be discovered by AIRM').
    ${secret_id}=    Get Variable Value    ${TEST_SECRET_ID}    ${None}
    Should Not Be Equal    ${secret_id}    ${None}
    ...    msg=TEST_SECRET_ID not set. Secret must be discovered by AIRM first.

    Wait Until Keyword Succeeds    30 sec    5 sec
    ...    Verify secret use case    ${expected_use_case}

Verify secret use case
    [Documentation]    Helper: checks that the secret has the expected use_case value in the AIRM API.
    [Arguments]    ${expected_use_case}

    ${response}=    Get secret    ${TEST_SECRET_ID}    expected_status=200
    ${secret}=    Set Variable    ${response.json()}
    ${use_case}=    Get From Dictionary    ${secret}    useCase
    Should Be Equal As Strings    ${use_case}    ${expected_use_case}
    ...    msg=Expected use_case "${expected_use_case}" but got "${use_case}"

    Log    Secret use_case verified: ${use_case}    INFO

Clean Up Kubectl Secret
    [Documentation]    Removes the kubectl-applied secret from the namespace.
    ...    Tolerant of missing variables or already-deleted secrets.
    ${secret_name}=    Get Variable Value    ${TEST_KUBECTL_SECRET_NAME}    ${None}
    ${project}=    Get Variable Value    ${TEST_PROJECT}    ${None}

    IF    $secret_name != $None and $project != $None
        ${result}=    Run Process    kubectl    delete    secret
        ...    ${secret_name}
        ...    -n    ${project}[name]
        ...    --ignore-not-found
        ...    stderr=PIPE
        IF    ${result.rc} == 0
            Log    Kubectl secret ${secret_name} deleted successfully    INFO
        ELSE
            Log    Failed to delete kubectl secret ${secret_name}: ${result.stderr}    WARN
        END
    END

Clean Up Kubectl ExternalSecret
    [Documentation]    Removes the kubectl-applied ExternalSecret from the namespace.
    ...    Tolerant of missing variables or already-deleted resources.
    ...    Should run before Clean Up Kubectl Secret so the ExternalSecret owner reference
    ...    triggers cascade deletion of the child K8s Secret.
    ${es_name}=    Get Variable Value    ${TEST_KUBECTL_ES_NAME}    ${None}
    ${project}=    Get Variable Value    ${TEST_PROJECT}    ${None}

    IF    $es_name != $None and $project != $None
        ${result}=    Run Process    kubectl    delete    externalsecret
        ...    ${es_name}
        ...    -n    ${project}[name]
        ...    --ignore-not-found
        ...    stderr=PIPE
        IF    ${result.rc} == 0
            Log    ExternalSecret ${es_name} deleted successfully    INFO
        ELSE
            Log    Failed to delete ExternalSecret ${es_name}: ${result.stderr}    WARN
        END
    END

An ExternalSecret is applied via kubectl
    [Documentation]    Applies an ExternalSecret manifest to the project namespace via kubectl.
    ...    Uses the existing test data template with a unique timestamp-based name.
    ...    The AIRM webhook should detect it and register it for auto-discovery.
    ...    Sets: TEST_KUBECTL_SECRET_NAME, TEST_KUBECTL_ES_NAME
    Should Not Be Equal    ${TEST_PROJECT}    ${None}
    ...    msg=TEST_PROJECT not set. Create a project first.

    ${timestamp}=    Evaluate    int(__import__('time').time())
    ${es_name}=    Set Variable    e2e-es-${timestamp}
    Set Test Variable    ${TEST_KUBECTL_SECRET_NAME}    ${es_name}
    Set Test Variable    ${TEST_KUBECTL_ES_NAME}    ${es_name}

    # Load template and replace placeholder name in metadata.name and target.name
    ${template}=    Get File    ${CURDIR}/../test_data/secrets/valid-externalsecret.yaml
    ${manifest}=    Replace String    ${template}    name: e2e-test-secret    name: ${es_name}

    ${temp_file}=    Set Variable    /tmp/e2e-es-${timestamp}.yaml
    Create File    ${temp_file}    ${manifest}

    ${result}=    Run Process    kubectl    apply
    ...    -n    ${TEST_PROJECT}[name]
    ...    -f    ${temp_file}
    ...    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to apply ExternalSecret via kubectl: ${result.stderr}

    Log    Applied ExternalSecret via kubectl: name=${es_name}, namespace=${TEST_PROJECT}[name]    INFO

An ExternalSecret with use-case "${use_case}" is applied via kubectl
    [Documentation]    Applies an ExternalSecret with a use-case label via kubectl apply.
    ...    Uses JSON manifest to include the label at creation time so the webhook
    ...    and controller see it during initial processing.
    ...    Sets: TEST_KUBECTL_SECRET_NAME, TEST_KUBECTL_ES_NAME
    Should Not Be Equal    ${TEST_PROJECT}    ${None}
    ...    msg=TEST_PROJECT not set. Create a project first.

    ${timestamp}=    Evaluate    int(__import__('time').time())
    ${es_name}=    Set Variable    e2e-es-usecase-${timestamp}
    Set Test Variable    ${TEST_KUBECTL_SECRET_NAME}    ${es_name}
    Set Test Variable    ${TEST_KUBECTL_ES_NAME}    ${es_name}

    ${namespace}=    Set Variable    ${TEST_PROJECT}[name]
    ${manifest}=    Catenate    SEPARATOR=
    ...    {"apiVersion":"external-secrets.io/v1beta1","kind":"ExternalSecret",
    ...    "metadata":{"name":"${es_name}","namespace":"${namespace}",
    ...    "labels":{"airm.silogen.ai/use-case":"${use_case}"}},
    ...    "spec":{"refreshInterval":"10s",
    ...    "secretStoreRef":{"name":"openbao-secret-store","kind":"ClusterSecretStore"},
    ...    "target":{"name":"${es_name}","creationPolicy":"Owner"},
    ...    "data":[{"secretKey":"ACCESS_KEY_ID","remoteRef":{"key":"minio-api-access-key","property":"value"}},
    ...    {"secretKey":"SECRET_ACCESS_KEY","remoteRef":{"key":"minio-api-secret-key","property":"value"}}]}}

    ${result}=    Run Process    bash    -c
    ...    echo '${manifest}' | kubectl apply -f -
    ...    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to apply ExternalSecret with use-case label: ${result.stderr}

    Log    Applied ExternalSecret with use-case="${use_case}": name=${es_name}, namespace=${namespace}    INFO

Kubectl ExternalSecret is deleted
    [Documentation]    Deletes the kubectl-applied ExternalSecret from the namespace via kubectl.
    ...    This simulates a user running 'kubectl delete externalsecret <name>'.
    Should Not Be Equal    ${TEST_KUBECTL_ES_NAME}    ${None}
    ...    msg=TEST_KUBECTL_ES_NAME not set. Apply an ExternalSecret via kubectl first.
    Should Not Be Equal    ${TEST_PROJECT}    ${None}
    ...    msg=TEST_PROJECT not set. Create a project first.

    ${result}=    Run Process    kubectl    delete    externalsecret
    ...    ${TEST_KUBECTL_ES_NAME}
    ...    -n    ${TEST_PROJECT}[name]
    ...    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to delete ExternalSecret via kubectl: ${result.stderr}

    Log    Deleted ExternalSecret via kubectl: name=${TEST_KUBECTL_ES_NAME}, namespace=${TEST_PROJECT}[name]    INFO

Auto-discovered secret metadata should be correct
    [Documentation]    Verifies the auto-discovered secret has correct metadata fields.
    ...    Checks kind, scope, and use_case against expected values.
    ...    Requires: TEST_SECRET_ID (set by 'Secret SHOULD be discovered by AIRM')
    [Arguments]    ${expected_kind}    ${expected_scope}=Project    ${expected_use_case}=Generic

    Should Not Be Equal    ${TEST_SECRET_ID}    ${None}
    ...    msg=TEST_SECRET_ID not set. Call 'Secret SHOULD be discovered by AIRM' first.

    ${response}=    Get secret    ${TEST_SECRET_ID}    expected_status=200
    ${json}=    Set Variable    ${response.json()}

    ${kind}=    Get From Dictionary    ${json}    type
    ${scope}=    Get From Dictionary    ${json}    scope
    ${use_case}=    Get From Dictionary    ${json}    useCase

    Should Be Equal    ${kind}    ${expected_kind}
    ...    msg=Expected kind=${expected_kind}, got ${kind}
    Should Be Equal    ${scope}    ${expected_scope}
    ...    msg=Expected scope=${expected_scope}, got ${scope}
    Should Be Equal    ${use_case}    ${expected_use_case}
    ...    msg=Expected use_case=${expected_use_case}, got ${use_case}

    Log    Auto-discovered secret metadata verified: kind=${kind}, scope=${scope}, use_case=${use_case}    INFO

Child KubernetesSecret should not be separately discovered by AIRM
    [Documentation]    Verifies that the K8s Secret automatically created by an ExternalSecret
    ...    is NOT registered as a separate auto-discovered secret in AIRM.
    ...    AIRM should track only the ExternalSecret, not its owner-referenced child.
    ...    Polls for the child K8s Secret to exist in the cluster first to avoid
    ...    a false-positive when the ESO controller hasn't created it yet.
    Should Not Be Equal    ${TEST_KUBECTL_ES_NAME}    ${None}
    ...    msg=TEST_KUBECTL_ES_NAME not set. Apply an ExternalSecret via kubectl first.

    # Wait for the child K8s Secret to actually exist before checking AIRM excluded it.
    Wait Until Keyword Succeeds    1 min    2 sec
    ...    Verify child KubernetesSecret exists in cluster

    # The child K8s Secret has the same name as the ExternalSecret (from target.name in manifest).
    # Verify no entry exists with that name and kind=KubernetesSecret.
    ${response}=    Get secrets    expected_status=200
    ${secrets_list}=    Set Variable    ${response.json()['data']}

    FOR    ${secret}    IN    @{secrets_list}
        ${name}=    Get From Dictionary    ${secret}    name
        IF    '${name}' == '${TEST_KUBECTL_ES_NAME}'
            ${kind}=    Get From Dictionary    ${secret}    type
            Should Not Be Equal    ${kind}    KubernetesSecret
            ...    msg=Child KubernetesSecret '${TEST_KUBECTL_ES_NAME}' was incorrectly registered as a separate AIRM secret (should only track the ExternalSecret)
        END
    END

    Log    Verified: child KubernetesSecret is not separately registered in AIRM    INFO

Verify child KubernetesSecret exists in cluster
    [Documentation]    Helper: checks that the child K8s Secret created by the ExternalSecret
    ...    controller exists in the project namespace. Used with polling.
    ${result}=    Run Process    kubectl    get    secret
    ...    ${TEST_KUBECTL_ES_NAME}
    ...    -n    ${TEST_PROJECT}[name]
    ...    -o    name
    ...    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Child K8s Secret ${TEST_KUBECTL_ES_NAME} not yet created by ESO controller: ${result.stderr}

AIRM controller pod is restarted
    [Documentation]    Triggers a restart by deleting every AIRM controller pod replica at once.
    ...    Uses -l app=... so all running pods for the workload are removed; the Deployment recreates them
    ...    without patch permission on deployments (unlike kubectl rollout restart).
    ...    Expects pods labeled app=${AIRM_CONTROLLER_DEPLOYMENT} (matches airm-agent Helm chart).
    ...    Override AIRM_CONTROLLER_NAMESPACE and AIRM_CONTROLLER_DEPLOYMENT variables
    ...    if your cluster uses different names (e.g. --variable AIRM_CONTROLLER_DEPLOYMENT:airm-api).

    Log    Deleting all pod replicas (-l app=${AIRM_CONTROLLER_DEPLOYMENT}) in namespace ${AIRM_CONTROLLER_NAMESPACE}    INFO

    ${result}=    Run Process    kubectl    delete    pods
    ...    -n    ${AIRM_CONTROLLER_NAMESPACE}
    ...    -l    app\=${AIRM_CONTROLLER_DEPLOYMENT}
    ...    --wait\=false
    ...    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Failed to delete AIRM controller pod replica(s) for app=${AIRM_CONTROLLER_DEPLOYMENT}: ${result.stderr}

    Log    Delete issued for all matching replicas of ${AIRM_CONTROLLER_DEPLOYMENT}; replacements will be scheduled    INFO

AIRM controller pod should be ready
    [Documentation]    Waits for the AIRM controller deployment to finish replacing pod(s)
    ...    and all pods to be ready again.
    Log    Waiting for ${AIRM_CONTROLLER_DEPLOYMENT} rollout to complete    INFO
    Wait Until Keyword Succeeds    3 min    5 sec
    ...    Verify AIRM controller deployment is ready

Verify AIRM controller deployment is ready
    [Documentation]    Helper: verifies the deployment rollout has completed successfully.
    ...    Used with polling — fails if rollout is still in progress.
    ${result}=    Run Process    kubectl    rollout    status
    ...    deployment/${AIRM_CONTROLLER_DEPLOYMENT}
    ...    -n    ${AIRM_CONTROLLER_NAMESPACE}
    ...    --timeout\=10s
    ...    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Deployment ${AIRM_CONTROLLER_DEPLOYMENT} rollout not yet complete: ${result.stdout} ${result.stderr}

    Log    AIRM controller deployment is ready    INFO
