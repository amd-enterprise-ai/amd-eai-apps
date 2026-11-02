# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level storage testing keywords for AIWB project storages.
Resource            api/storages.resource
Resource            aiwb_common.resource
Resource            aiwb_secrets.resource
Library             Collections
Library             Process
Library             TestPrefix


*** Variables ***
@{CREATED_AIWB_STORAGE_NAMES}    # Track created storage configmaps for cleanup
${AIWB_E2E_S3_BUCKET_URL}        %{AIWB_SPECS_S3_BUCKET_URL=http://filer-s3.seaweedfs-instance.svc.cluster.local:80}


*** Keywords ***
Initialize AIWB Storage Tracking
    [Documentation]    Resets the AIWB storage tracking list for cleanup.
    @{empty_list}=    Create List
    Set Suite Variable    @{CREATED_AIWB_STORAGE_NAMES}    @{empty_list}

Find AIWB Storage Kubernetes Name By Display Name
    [Documentation]    Return the ConfigMap resource name for a storage display name, if present.
    [Arguments]    ${project}    ${display_name}
    ${response}=    List AIWB Storages    ${project}    storage_type=S3    expected_status=200
    FOR    ${storage}    IN    @{response.json()['data']}
        IF    '${storage["displayName"]}' == '${display_name}'
            RETURN    ${storage['name']}
        END
    END
    RETURN    ${None}

A storage "${name}" is created from prepared secret without credential key names
    [Documentation]    Creates an S3 storage request from the secret prepared by prior Given steps.
    Should Not Be Empty    ${TEST_AIWB_SECRET_K8S_NAME}
    A storage "${name}" is created from secret "${TEST_AIWB_SECRET_K8S_NAME}" without credential key names

A storage "${name}" is created from secret "${secret_name}" without credential key names
    [Documentation]    Creates an S3 storage request without explicit credential key names.
    ${project}=    Get Project Namespace
    ${full_name}=    Test Name    ${name}
    &{spec}=    Create Dictionary
    ...    bucketUrl=${AIWB_E2E_S3_BUCKET_URL}
    ...    region=us-east-1
    &{body}=    Create Dictionary
    ...    displayName=${full_name}
    ...    type=S3
    ...    secretName=${secret_name}
    ...    spec=${spec}
    ${response}=    Create AIWB Storage    ${project}    ${body}    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Set Test Variable    ${TEST_AIWB_STORAGE_DISPLAY_NAME}    ${full_name}
    IF    ${response.status_code} == 201
        VAR    ${created_name}    ${response.json()['name']}
        Append To List    ${CREATED_AIWB_STORAGE_NAMES}    ${created_name}
        Set Test Variable    ${TEST_AIWB_STORAGE_K8S_NAME}    ${created_name}
    END

An unlabeled secret "${name}" with storage credential aliases exists
    [Documentation]    Creates an unlabeled Kubernetes secret with storage-* credential aliases.
    ${project}=    Get Project Namespace
    ${full_name}=    Test Name    ${name}
    ${delete_result}=    Run Process
    ...    kubectl
    ...    delete
    ...    secret
    ...    ${full_name}
    ...    -n
    ...    ${project}
    ...    --ignore-not-found\=true
    ...    stderr=STDOUT
    Should Be Equal As Integers    ${delete_result.rc}    0
    ...    msg=Failed to clear existing secret ${full_name}: ${delete_result.stdout}
    ${create_result}=    Run Process
    ...    kubectl
    ...    create
    ...    secret
    ...    generic
    ...    ${full_name}
    ...    --from-literal\=storage-access-key\=test-access-key
    ...    --from-literal\=storage-secret-key\=test-secret-key
    ...    -n
    ...    ${project}
    ...    stderr=STDOUT
    Should Be Equal As Integers    ${create_result.rc}    0
    ...    msg=Failed to create storage alias secret ${full_name}: ${create_result.stdout}
    Append To List    ${CREATED_AIWB_SECRET_NAMES}    ${full_name}
    Set Test Variable    ${TEST_AIWB_SECRET_K8S_NAME}    ${full_name}

Clean Up All Created AIWB Storages
    [Documentation]    Deletes all storage ConfigMaps created during the test.
    ...    Tolerant of missing project or already-deleted storages.
    ${project_data}=    Get Variable Value    ${TEST_PROJECT}    ${None}
    IF    $project_data is None
        Log    No project set, skipping AIWB storage cleanup    DEBUG
        RETURN
    END
    ${project}=    Get From Dictionary    ${project_data}    name
    ${count}=    Get Length    ${CREATED_AIWB_STORAGE_NAMES}
    IF    ${count} == 0
        Log    No AIWB storages to clean up    DEBUG
        RETURN
    END
    Log    Cleaning up ${count} AIWB storage(s)    INFO
    FOR    ${storage_name}    IN    @{CREATED_AIWB_STORAGE_NAMES}
        TRY
            ${result}=    Run Process
            ...    kubectl
            ...    delete
            ...    configmap
            ...    ${storage_name}
            ...    -n
            ...    ${project}
            ...    --ignore-not-found\=true
            ...    stderr=STDOUT
            Should Be Equal As Integers    ${result.rc}    0
            ...    msg=Failed to delete AIWB storage ${storage_name}: ${result.stdout}
            Log    Deleted AIWB storage ${storage_name}    DEBUG
        EXCEPT    AS    ${error}
            Log    Failed to delete AIWB storage ${storage_name}: ${error}    WARN
        END
    END
    @{empty_list}=    Create List
    Set Suite Variable    @{CREATED_AIWB_STORAGE_NAMES}    @{empty_list}
    Log    AIWB storage cleanup complete    INFO

An unlabeled secret "${name}" without S3 credential aliases exists
    [Documentation]    Creates an unlabeled Kubernetes secret with unrelated keys.
    ${project}=    Get Project Namespace
    ${full_name}=    Test Name    ${name}
    ${delete_result}=    Run Process
    ...    kubectl
    ...    delete
    ...    secret
    ...    ${full_name}
    ...    -n
    ...    ${project}
    ...    --ignore-not-found\=true
    ...    stderr=STDOUT
    Should Be Equal As Integers    ${delete_result.rc}    0
    ...    msg=Failed to clear existing secret ${full_name}: ${delete_result.stdout}
    ${create_result}=    Run Process
    ...    kubectl
    ...    create
    ...    secret
    ...    generic
    ...    ${full_name}
    ...    --from-literal\=username\=test-user
    ...    --from-literal\=password\=test-pass
    ...    -n
    ...    ${project}
    ...    stderr=STDOUT
    Should Be Equal As Integers    ${create_result.rc}    0
    ...    msg=Failed to create unlabeled secret ${full_name}: ${create_result.stdout}
    Append To List    ${CREATED_AIWB_SECRET_NAMES}    ${full_name}
    Set Test Variable    ${TEST_AIWB_SECRET_K8S_NAME}    ${full_name}

Storage creation should succeed with resolved credential key names
    [Documentation]    Verifies omitted key names are resolved from secret aliases and
    ...    the API returns both generated resource name and requested display name.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    201
    VAR    ${body}    ${TEST_RESPONSE.json()}
    Should Not Be Empty    ${body['name']}
    Should Be Equal    ${body['displayName']}    ${TEST_AIWB_STORAGE_DISPLAY_NAME}
    Should Be Equal    ${body['spec']['accessKeyName']}    accessKeyId
    Should Be Equal    ${body['spec']['secretKeyName']}    secretAccessKey

Storage creation should preserve free-form display name and generated kubernetes name
    [Documentation]    Verifies displayName is preserved verbatim while name is generated
    ...    as a distinct wb-storage-* Kubernetes identifier.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    201
    VAR    ${body}    ${TEST_RESPONSE.json()}
    Should Be Equal    ${body['displayName']}    ${TEST_AIWB_STORAGE_DISPLAY_NAME}
    Should Match Regexp    ${body['name']}    ^wb-storage-(?:[a-z0-9-]+-)?[0-9a-f]{10}$
    Should Not Be Equal    ${body['name']}    ${body['displayName']}

Storage creation should succeed with storage credential aliases
    [Documentation]    Verifies omitted key names resolve from storage-* aliases.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    201
    VAR    ${body}    ${TEST_RESPONSE.json()}
    Should Not Be Empty    ${body['name']}
    Should Be Equal    ${body['displayName']}    ${TEST_AIWB_STORAGE_DISPLAY_NAME}
    Should Be Equal    ${body['spec']['accessKeyName']}    storage-access-key
    Should Be Equal    ${body['spec']['secretKeyName']}    storage-secret-key

Storage creation should fail with a validation error
    [Documentation]    Verifies storage creation fails when credentials cannot be resolved.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    400

Storage creation should fail with a conflict error
    [Documentation]    Verifies storage creation fails with 409 when display name duplicates.
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    409

Storage conflict error should mention duplicate display name
    [Documentation]    Verifies conflict message explains duplicate display name.
    VAR    ${detail}    ${TEST_RESPONSE.json()['detail']}
    Should Contain    ${detail}    display name

Storage validation error should mention missing credential aliases
    [Documentation]    Verifies the validation message explains credential alias expectations.
    VAR    ${detail}    ${TEST_RESPONSE.json()['detail']}
    Should Contain    ${detail}    does not contain a detectable access key

Project storages are listed
    [Documentation]    Lists project storage configurations and captures the response.
    ${project}=    Get Project Namespace
    ${response}=    List AIWB Storages    ${project}    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Project storages are listed filtered by type "${storage_type}"
    [Documentation]    Lists project storages filtered by storage type.
    ${project}=    Get Project Namespace
    ${response}=    List AIWB Storages    ${project}    storage_type=${storage_type}    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

The storage list should include storage "${name}"
    [Documentation]    Verifies a storage appears in the list by its display name.
    ${full_name}=    Test Name    ${name}
    VAR    ${storages}    ${TEST_RESPONSE.json()['data']}
    FOR    ${storage}    IN    @{storages}
        IF    '${storage["displayName"]}' == '${full_name}'
            RETURN
        END
    END
    FAIL    Storage display name ${full_name} was not found in storage list

All listed storages should have type "${storage_type}"
    [Documentation]    Verifies every listed storage carries the requested storage type.
    VAR    ${storages}    ${TEST_RESPONSE.json()['data']}
    FOR    ${storage}    IN    @{storages}
        Should Be Equal    ${storage['type']}    ${storage_type}
    END
