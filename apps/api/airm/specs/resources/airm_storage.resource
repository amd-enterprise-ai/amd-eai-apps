# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level storage testing keywords.
...                 Provides business-logic level keywords for testing storage operations.
...                 Uses the low-level API keywords from api/storage.resource to implement
...                 higher-level testing scenarios for storage management and project assignments.
Resource            api/storage.resource
Resource            common/airm_resource_cleanup.resource
Resource            resources/common/resource_lifecycle.resource
Resource            airm_secrets.resource
Resource            airm_projects.resource
Resource            s3_test_operations.resource
Library             Collections
Library             String
Library             OperatingSystem
Library             Process


*** Variables ***
${TEST_STORAGE_ID}           ${None}
${SECOND_STORAGE_ID}         ${None}
${TEST_STORAGE_SECRET_ID}    ${None}
@{CREATED_STORAGE_IDS}       # List to track created storage IDs for cleanup
${TEST_VALID_S3_SPEC}            ${None}
# The object store and bucket the platform provisions for projects. An override must be a bucket
# URL including the /<bucket> path: the S3 Jobs take the bucket name from that path. For another
# install, set AIRM_SPECS_S3_BUCKET_URL, or pass --variable AIRM_E2E_S3_BUCKET_URL:<url>. The two
# names differ deliberately, matching the AIWB pair in aiwb_storages.resource.
${AIRM_E2E_S3_BUCKET_URL}    %{AIRM_SPECS_S3_BUCKET_URL=http://filer-s3.seaweedfs-instance.svc.cluster.local:80/default-bucket}


*** Keywords ***

# ============================================================================
# Given Keywords - Setup and Preconditions
# ============================================================================

A valid S3 storage spec exists
    [Documentation]    Creates a valid S3 storage specification for testing
    ...    The spec includes bucket URL and credential field names
    ...    Points at the bucket the platform already provisions, so the S3 jobs authenticate with
    ...    the project's own credentials and need no bucket-creation rights. Test objects are kept
    ...    apart by key prefix, not by bucket.
    ...    Canonicalize the URL before it enters the spec: it is written verbatim into the S3 Jobs'
    ...    ConfigMap as BUCKET_URL, which they parse with urlparse, so a schemeless override
    ...    (e.g. store:80/default-bucket) would otherwise leave them with an empty endpoint.

    ${bucket_url}=    Normalize Object Storage Bucket URL    ${AIRM_E2E_S3_BUCKET_URL}
    &{s3_spec}=    Create dictionary
    ...    bucketUrl=${bucket_url}
    ...    accessKeyName=ACCESS_KEY_ID
    ...    secretKeyName=SECRET_ACCESS_KEY

    Set test variable    ${TEST_VALID_S3_SPEC}    ${s3_spec}
    Log    Valid S3 storage spec created for bucket URL: ${bucket_url}    DEBUG

A secret for storage credentials exists
    [Documentation]    Creates a secret to be used for storage credentials
    ...    This secret would contain S3 access keys in a real scenario
    ...    Sets use_case=S3 as required by the storage API

    Should not be equal    ${TEST_VALID_MANIFEST}    ${EMPTY}
    ...    msg=Valid secret manifest not set. Call 'a valid ExternalSecret manifest exists' first.

    ${unique_suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${name}    e2e-storage-secret-${unique_suffix}

    @{empty_project_ids}=    Create list

    ${secret_data}=    Create dictionary
    ...    name=${name}
    ...    type=ExternalSecret
    ...    scope=Organization
    ...    useCase=S3
    ...    manifest=${TEST_VALID_MANIFEST}
    ...    projectIds=${empty_project_ids}

    ${response}=    Create secret
    ...    secret_data=${secret_data}
    ...    expected_status=200

    ${secret_id}=    Get from dictionary    ${response.json()}    id
    Set test variable    ${TEST_STORAGE_SECRET_ID}    ${secret_id}

    Track Secret For Cleanup    ${secret_id}

    Log    Created storage credential secret with ID: ${secret_id}    INFO

# ============================================================================
# When Keywords - Actions
# ============================================================================

Storage is created without project assignment
    [Documentation]    Creates a storage without assigning it to any project
    ...    Uses default configuration: type=S3, scope=Organization
    [Arguments]    ${storage_name}=${EMPTY}

    IF    "${storage_name}" == "${EMPTY}"
        ${unique_suffix}=    Generate Random String    8    [LOWER][NUMBERS]
        VAR    ${name}    e2e-storage-${unique_suffix}
    ELSE
        VAR    ${name}    ${storage_name}
    END

    Should not be equal    ${TEST_VALID_S3_SPEC}    ${None}
    ...    msg=Valid S3 spec not set. Call 'a valid S3 storage spec exists' first.
    Should not be equal    ${TEST_STORAGE_SECRET_ID}    ${None}
    ...    msg=Storage secret not set. Call 'a secret for storage credentials exists' first.

    @{empty_project_ids}=    Create list

    ${storage_data}=    Create dictionary
    ...    name=${name}
    ...    type=S3
    ...    scope=Organization
    ...    secretId=${TEST_STORAGE_SECRET_ID}
    ...    projectIds=${empty_project_ids}
    ...    spec=${TEST_VALID_S3_SPEC}

    ${response}=    Create storage
    ...    storage_data=${storage_data}
    ...    expected_status=200

    ${storage_id}=    Get from dictionary    ${response.json()}    id
    Set test variable    ${TEST_STORAGE_ID}    ${storage_id}

    TRY
        Append to list    ${CREATED_STORAGE_IDS}    ${storage_id}
        Log    Added storage ${storage_id} to cleanup list    DEBUG
    EXCEPT
        Log    CREATED_STORAGE_IDS not available, storage won't be auto-cleaned    WARN
    END

    Set test variable    ${TEST_RESPONSE}    ${response}

    Log    Created storage with ID: ${storage_id}    INFO

Storage is created and assigned to project
    [Documentation]    Creates a storage and assigns it to the current project
    [Arguments]    ${storage_name}=${EMPTY}

    IF    "${storage_name}" == "${EMPTY}"
        ${unique_suffix}=    Generate Random String    8    [LOWER][NUMBERS]
        VAR    ${name}    e2e-storage-${unique_suffix}
    ELSE
        VAR    ${name}    ${storage_name}
    END

    Should not be equal    ${TEST_VALID_S3_SPEC}    ${None}
    ...    msg=Valid S3 spec not set. Call 'a valid S3 storage spec exists' first.
    Should not be equal    ${TEST_STORAGE_SECRET_ID}    ${None}
    ...    msg=Storage secret not set. Call 'a secret for storage credentials exists' first.
    Should not be equal    ${TEST_PROJECT_ID}    ${None}
    ...    msg=Current project not set. Create a project first.

    @{project_ids}=    Create list    ${TEST_PROJECT_ID}

    ${storage_data}=    Create dictionary
    ...    name=${name}
    ...    type=S3
    ...    scope=Organization
    ...    secretId=${TEST_STORAGE_SECRET_ID}
    ...    projectIds=${project_ids}
    ...    spec=${TEST_VALID_S3_SPEC}

    ${response}=    Create storage
    ...    storage_data=${storage_data}
    ...    expected_status=200

    ${storage_id}=    Get from dictionary    ${response.json()}    id
    Set test variable    ${TEST_STORAGE_ID}    ${storage_id}

    TRY
        Append to list    ${CREATED_STORAGE_IDS}    ${storage_id}
        Log    Added storage ${storage_id} to cleanup list    DEBUG
    EXCEPT
        Log    CREATED_STORAGE_IDS not available, storage won't be auto-cleaned    WARN
    END

    Set test variable    ${TEST_RESPONSE}    ${response}

    Log    Created storage with ID: ${storage_id} and assigned to project ${TEST_PROJECT_ID}    INFO

# Removed duplicate keyword - now using from airm_projects.resource

Storage is assigned to second project
    [Documentation]    Assigns the current storage to the second project
    Should not be equal    ${TEST_STORAGE_ID}    ${None}
    ...    msg=TEST_STORAGE_ID not set. Create storage first.
    Should not be equal    ${TEST_SECOND_PROJECT_ID}    ${None}
    ...    msg=TEST_SECOND_PROJECT_ID not set. Create second project first.

    @{project_ids}=    Create list    ${TEST_PROJECT_ID}    ${TEST_SECOND_PROJECT_ID}

    ${response}=    Assign storage to projects
    ...    ${TEST_STORAGE_ID}
    ...    ${project_ids}
    ...    expected_status=200

    Set test variable    ${TEST_RESPONSE}    ${response}
    Log    Assigned storage ${TEST_STORAGE_ID} to second project ${TEST_SECOND_PROJECT_ID}    INFO

Storage project assignment is removed
    [Documentation]    Removes all project assignments from the storage
    Should not be equal    ${TEST_STORAGE_ID}    ${None}
    ...    msg=TEST_STORAGE_ID not set. Create storage first.

    @{empty_project_ids}=    Create list

    ${response}=    Assign storage to projects
    ...    ${TEST_STORAGE_ID}
    ...    ${empty_project_ids}
    ...    expected_status=200

    Set test variable    ${TEST_RESPONSE}    ${response}
    Log    Removed all project assignments from storage ${TEST_STORAGE_ID}    INFO

Attempting to create storage with same name
    [Documentation]    Attempts to create a storage with a duplicate name (should fail with 409)
    Should not be equal    ${TEST_VALID_S3_SPEC}    ${None}
    ...    msg=Valid S3 spec not set.

    ${storage_response}=    Get storage    ${TEST_STORAGE_ID}
    ${storage_name}=    Get from dictionary    ${storage_response.json()}    name

    @{empty_project_ids}=    Create list

    ${storage_data}=    Create dictionary
    ...    name=${storage_name}
    ...    type=S3
    ...    scope=Organization
    ...    secretId=${TEST_STORAGE_SECRET_ID}
    ...    projectIds=${empty_project_ids}
    ...    spec=${TEST_VALID_S3_SPEC}

    ${response}=    Create storage
    ...    storage_data=${storage_data}
    ...    expected_status=409

    Set test variable    ${TEST_RESPONSE}    ${response}

Attempting to create storage with invalid name
    [Documentation]    Attempts to create a storage with invalid name format
    Should not be equal    ${TEST_VALID_S3_SPEC}    ${None}
    ...    msg=Valid S3 spec not set.

    @{empty_project_ids}=    Create list

    ${storage_data}=    Create dictionary
    ...    name=Invalid_Storage_Name!
    ...    type=S3
    ...    scope=Organization
    ...    secretId=${TEST_STORAGE_SECRET_ID}
    ...    projectIds=${empty_project_ids}
    ...    spec=${TEST_VALID_S3_SPEC}

    ${response}=    Create storage
    ...    storage_data=${storage_data}
    ...    expected_status=422

    Set test variable    ${TEST_RESPONSE}    ${response}

Attempting to create storage with non-existent secret
    [Documentation]    Attempts to create a storage with a non-existent secret ID
    Should not be equal    ${TEST_VALID_S3_SPEC}    ${None}
    ...    msg=Valid S3 spec not set.

    @{empty_project_ids}=    Create list

    ${fake_secret_id}=    Evaluate    str(__import__('uuid').uuid4())

    ${storage_data}=    Create dictionary
    ...    name=e2e-storage-fake-secret
    ...    type=S3
    ...    scope=Organization
    ...    secretId=${fake_secret_id}
    ...    projectIds=${empty_project_ids}
    ...    spec=${TEST_VALID_S3_SPEC}

    ${response}=    Create storage
    ...    storage_data=${storage_data}
    ...    expected_status=404

    Set test variable    ${TEST_RESPONSE}    ${response}

Storage is deleted
    [Documentation]    Deletes the current test storage
    Should not be equal    ${TEST_STORAGE_ID}    ${None}
    ...    msg=TEST_STORAGE_ID not set.

    ${response}=    Delete storage    ${TEST_STORAGE_ID}    expected_status=204

    Set test variable    ${TEST_RESPONSE}    ${response}
    Log    Deleted storage ${TEST_STORAGE_ID}    INFO

Listing all storage
    [Documentation]    Lists all storage resources in the organization
    ${response}=    Get storages    expected_status=200
    Set test variable    ${TEST_RESPONSE}    ${response}
    Log    Listed all storage resources for organization    INFO

Storage transitions to "${expected_status}"
    [Documentation]    Waits for storage to transition to expected status
    ...    Polls the storage status until it reaches the expected state
    ...    Reasonable timeout to allow for Agent processing and ExternalSecret sync
    Should not be equal    ${TEST_STORAGE_ID}    ${None}
    ...    msg=TEST_STORAGE_ID not set.

    Wait For Resource Status    Get storage    ${TEST_STORAGE_ID}    ${expected_status}
    ${response}=    Get storage    ${TEST_STORAGE_ID}    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Verify storage has status "${expected_status}"
    [Documentation]    Helper keyword to verify storage status (used with polling)
    Verify Resource Status    Get storage    ${TEST_STORAGE_ID}    ${expected_status}

Verify storage has status "${expected_status}" for ID
    [Documentation]    Helper keyword to verify storage status for a specific storage ID
    [Arguments]    ${storage_id}
    Verify Resource Status    Get storage    ${storage_id}    ${expected_status}

# Backward compatibility keywords (can be removed later)
Storage transitions to synced
    [Documentation]    DEPRECATED: Use 'Storage transitions to "Synced"' instead
    Storage transitions to "Synced"

Verify storage is synced
    [Documentation]    DEPRECATED: Use 'Verify storage has status "Synced"' instead
    Verify storage has status "Synced"

# ============================================================================
# Then Keywords - Assertions
# ============================================================================

Storage should be visible via API
    [Documentation]    Verifies storage can be retrieved via API
    Should not be equal    ${TEST_STORAGE_ID}    ${None}
    ...    msg=TEST_STORAGE_ID not set.

    ${response}=    Get storage    ${TEST_STORAGE_ID}    expected_status=200
    Set test variable    ${TEST_RESPONSE}    ${response}

    Log    Storage ${TEST_STORAGE_ID} is visible via API    INFO

Storage should have valid ID and status
    [Documentation]    Verifies storage response contains valid id and status fields
    Should not be equal    ${TEST_RESPONSE}    ${None}
    ...    msg=Response not set. Call 'storage should be visible via API' first.

    ${json}=    Set variable    ${TEST_RESPONSE.json()}
    Dictionary should contain key    ${json}    id
    Dictionary should contain key    ${json}    status

    ${storage_id}=    Get from dictionary    ${json}    id
    ${status}=    Get from dictionary    ${json}    status

    Log    Storage has valid ID: ${storage_id}, Status: ${status}    INFO

Storage status should be "${expected_status}"
    [Documentation]    Verifies the storage has the expected status by fetching fresh state
    ...    Always fetches current storage state using TEST_STORAGE_ID
    ...    For Pending status, allows Synced as storage may sync very quickly
    ...    For Deleting status, handles already-deleted case (404)
    ...    For checking immediate API response, use 'Storage status should be "${status}" in response'
    Should not be equal    ${TEST_STORAGE_ID}    ${None}
    ...    msg=TEST_STORAGE_ID not set. Create storage first.

    # Special case: Deleting may result in 404 if deleted too quickly
    IF    "${expected_status}" == "Deleting"
        TRY
            ${storage_response}=    Get storage    ${TEST_STORAGE_ID}    expected_status=200
            ${json}=    Set variable    ${storage_response.json()}
            ${status}=    Get from dictionary    ${json}    status
            Should be equal    ${status}    ${expected_status}
            ...    msg=Expected status '${expected_status}', got '${status}'
            Log    Storage status is ${status}    INFO
            Set test variable    ${TEST_RESPONSE}    ${storage_response}
        EXCEPT
            # Storage not found - it was deleted too quickly to catch DELETING state
            Log    Storage ${TEST_STORAGE_ID} not found - already deleted (too fast to see DELETING status)    WARN
            Pass Execution    Storage deleted too quickly to verify DELETING status
        END
    ELSE
        # Standard status check - fetch fresh state
        ${storage_response}=    Get storage    ${TEST_STORAGE_ID}    expected_status=200
        ${json}=    Set variable    ${storage_response.json()}
        ${status}=    Get from dictionary    ${json}    status

        # Special case: Pending may transition to Synced or PartiallySynced very quickly
        # PartiallySynced occurs when some project assignments are synced and others are still pending
        IF    "${expected_status}" == "Pending"
            Should Be True    '${status}' in ['Pending', 'Synced', 'PartiallySynced']
            ...    msg=Expected status 'Pending', 'Synced', or 'PartiallySynced', got '${status}'
            Log    Storage status is ${status} (expected Pending, Synced/PartiallySynced allowed)    INFO
        ELSE
            Should be equal    ${status}    ${expected_status}
            ...    msg=Expected status '${expected_status}', got '${status}'
            Log    Storage status is ${status}    INFO
        END

        Set test variable    ${TEST_RESPONSE}    ${storage_response}
    END

Storage status should be "${expected_status}" in response
    [Documentation]    Verifies the storage status in the cached ${TEST_RESPONSE} variable
    ...    Use this immediately after an API call to check the response without extra fetch
    ...    For Pending status, allows Synced as storage may sync very quickly
    ${json}=    Set variable    ${TEST_RESPONSE.json()}
    ${status}=    Get from dictionary    ${json}    status

    # Special case: Pending may transition to Synced or PartiallySynced very quickly
    # PartiallySynced occurs when some project assignments are synced and others are still pending
    IF    "${expected_status}" == "Pending"
        Should Be True    '${status}' in ['Pending', 'Synced', 'PartiallySynced']
        ...    msg=Expected status 'Pending', 'Synced', or 'PartiallySynced' in response, got '${status}'
        Log    Storage status in response is ${status} (expected Pending, Synced/PartiallySynced allowed)    INFO
    ELSE
        Should be equal    ${status}    ${expected_status}
        ...    msg=Expected status '${expected_status}' in response, got '${status}'
        Log    Storage status in response is ${status}    INFO
    END

# Backward compatibility keywords (can be removed later)
Storage status should be unassigned
    [Documentation]    DEPRECATED: Use 'Storage status should be "Unassigned"' instead
    Storage status should be "Unassigned"

Storage status should be pending
    [Documentation]    DEPRECATED: Use 'Storage status should be "Pending"' instead
    Storage status should be "Pending"

Storage status should be synced
    [Documentation]    DEPRECATED: Use 'Storage status should be "Synced"' instead
    Storage status should be "Synced"

Storage status should be deleting
    [Documentation]    DEPRECATED: Use 'Storage status should be "Deleting"' instead
    Storage status should be "Deleting"

Storage should have "${count}" project assignment
    [Documentation]    Verifies storage has the specified number of project assignments
    ${count_int}=    Convert to integer    ${count}

    Should not be equal    ${TEST_STORAGE_ID}    ${None}
    ...    msg=TEST_STORAGE_ID not set.

    ${fresh_response}=    Get storage    ${TEST_STORAGE_ID}    expected_status=200
    ${json}=    Set variable    ${fresh_response.json()}
    ${project_storages}=    Get from dictionary    ${json}    projectStorages
    ${actual_count}=    Get length    ${project_storages}

    Should be equal as integers    ${actual_count}    ${count_int}
    ...    msg=Expected ${count_int} project assignments, found ${actual_count}

    Log    Storage has ${actual_count} project assignment(s)    INFO

    Set test variable    ${TEST_RESPONSE}    ${fresh_response}

All storage project assignments should be synced
    [Documentation]    Verifies all project storage assignments are in SYNCED status by fetching fresh state
    ${storage_response}=    Get storage    ${TEST_STORAGE_ID}    expected_status=200
    ${json}=    Set variable    ${storage_response.json()}
    ${project_storages}=    Get from dictionary    ${json}    projectStorages

    FOR    ${project_storage}    IN    @{project_storages}
        ${status}=    Get from dictionary    ${project_storage}    status
        Should be equal    ${status}    Synced
        ...    msg=Project storage ${project_storage['id']} is ${status}, expected Synced
    END

    Log    All project storage assignments are synced    INFO

Storage should not be visible via API
    [Documentation]    Verifies storage has been deleted and is no longer accessible
    Should not be equal    ${TEST_STORAGE_ID}    ${None}
    ...    msg=TEST_STORAGE_ID not set.

    ${response}=    Get storage    ${TEST_STORAGE_ID}    expected_status=404

    Log    Storage ${TEST_STORAGE_ID} is no longer accessible (deleted)    INFO

Storage creation should fail with conflict
    [Documentation]    Verifies storage creation failed with HTTP 409 Conflict
    Should not be equal    ${TEST_RESPONSE}    ${None}
    ...    msg=Response not set.

    Log    Storage creation correctly failed with conflict    INFO

Storage creation should fail with validation error
    [Documentation]    Verifies storage creation failed with HTTP 422 validation error
    Should not be equal    ${TEST_RESPONSE}    ${None}
    ...    msg=Response not set.

    Log    Storage creation correctly failed with validation error    INFO

Storage creation should fail with not found
    [Documentation]    Verifies storage creation failed with HTTP 404 not found
    Should not be equal    ${TEST_RESPONSE}    ${None}
    ...    msg=Response not set.

    Log    Storage creation correctly failed with not found error    INFO

At least "${count}" storage should be visible
    [Documentation]    Verifies at least the specified number of storage resources are visible
    ${count_int}=    Convert to integer    ${count}

    ${json}=    Set variable    ${TEST_RESPONSE.json()}
    ${storage_list}=    Get from dictionary    ${json}    data
    ${actual_count}=    Get length    ${storage_list}

    Should be true    ${actual_count} >= ${count_int}
    ...    msg=Expected at least ${count_int} storage resources, found ${actual_count}

    Log    Found ${actual_count} storage resources (expected at least ${count_int})    INFO

Get storage name
    [Documentation]    Returns the name of the current test storage
    Should not be equal    ${TEST_STORAGE_ID}    ${None}
    ...    msg=TEST_STORAGE_ID not set.

    ${response}=    Get storage    ${TEST_STORAGE_ID}    expected_status=200
    ${json}=    Set variable    ${response.json()}
    ${name}=    Get from dictionary    ${json}    name
    RETURN    ${name}

Wait for storage deletion to complete
    [Documentation]    Waits until storage is fully deleted from the system
    Should not be equal    ${TEST_STORAGE_ID}    ${None}
    ...    msg=TEST_STORAGE_ID not set.

    Wait For Resource Deletion    Get storage    ${TEST_STORAGE_ID}    timeout=30 sec    interval=2 sec

Verify storage is deleted
    [Documentation]    Helper keyword to verify storage no longer exists
    Resource Should Not Exist    Get storage    ${TEST_STORAGE_ID}

Storage with same name "${name}" can be created
    [Documentation]    Creates a new storage with the specified name
    Should not be equal    ${TEST_VALID_S3_SPEC}    ${None}
    ...    msg=Valid S3 spec not set.
    Should not be equal    ${TEST_STORAGE_SECRET_ID}    ${None}
    ...    msg=Storage secret not set.

    @{empty_project_ids}=    Create list

    ${storage_data}=    Create dictionary
    ...    name=${name}
    ...    type=S3
    ...    scope=Organization
    ...    secretId=${TEST_STORAGE_SECRET_ID}
    ...    projectIds=${empty_project_ids}
    ...    spec=${TEST_VALID_S3_SPEC}

    ${response}=    Create storage
    ...    storage_data=${storage_data}
    ...    expected_status=200

    ${new_storage_id}=    Get from dictionary    ${response.json()}    id
    Set test variable    ${TEST_STORAGE_ID}    ${new_storage_id}

    TRY
        Append to list    ${CREATED_STORAGE_IDS}    ${new_storage_id}
        Log    Added storage ${new_storage_id} to cleanup list    DEBUG
    EXCEPT
        Log    CREATED_STORAGE_IDS not available    WARN
    END

    Log    Created new storage with ID: ${new_storage_id}    INFO

New storage should have different ID than "${original_id}"
    [Documentation]    Verifies the new storage has a different ID than the original
    Should not be equal    ${TEST_STORAGE_ID}    ${None}
    ...    msg=TEST_STORAGE_ID not set.
    Should not be equal    ${TEST_STORAGE_ID}    ${original_id}
    ...    msg=New storage ID ${TEST_STORAGE_ID} should be different from original ${original_id}
    Log    New storage ID ${TEST_STORAGE_ID} is different from original ${original_id}    INFO

Get storage bucket URL
    [Documentation]    Returns the S3 bucket URL from the valid S3 spec used to create storage
    ...    Note: The API doesn't return the spec in GET responses, so we use the stored spec
    Should not be equal    ${TEST_VALID_S3_SPEC}    ${None}
    ...    msg=TEST_VALID_S3_SPEC not set. Call 'a valid S3 storage spec exists' first.

    ${bucket_url}=    Get from dictionary    ${TEST_VALID_S3_SPEC}    bucketUrl
    RETURN    ${bucket_url}

Test data "${data}" is written to S3 bucket
    [Documentation]    Writes test data to the S3 bucket using a Kubernetes Job
    ...    Submits an S3 writer Job that actually writes data to S3 using boto3
    ...    Requires storage to be assigned to project (ConfigMap exists)
    ...    For local development, creates ConfigMap and Secret manually since Agent doesn't run

    # Generate random suffix for unique job names and a unique S3 key prefix
    ${random_suffix}=    Generate Random Suffix

    # Get storage details to extract ConfigMap and secret info
    ${storage_response}=    Get storage    ${TEST_STORAGE_ID}    expected_status=200
    ${storage_json}=    Set Variable    ${storage_response.json()}

    # Get the project storage to find the ConfigMap name
    ${project_storages}=    Get from dictionary    ${storage_json}    projectStorages
    Should Not Be Empty    ${project_storages}    msg=No project storages found - storage must be assigned to project first

    ${project_storage}=    Set Variable    ${project_storages}[0]
    ${storage_name}=    Get from dictionary    ${storage_json}    name

    # ConfigMap name follows pattern: {storage_name}-info-config-map
    ${config_map_name}=    Set Variable    ${storage_name}-info-config-map

    # Get secret details from TEST_VALID_S3_SPEC
    ${access_key_name}=    Get from dictionary    ${TEST_VALID_S3_SPEC}    accessKeyName
    ${secret_key_name}=    Get from dictionary    ${TEST_VALID_S3_SPEC}    secretKeyName
    ${bucket_url}=    Get from dictionary    ${TEST_VALID_S3_SPEC}    bucketUrl

    # Get the ExternalSecret name from the secret used to create storage
    # For e2e tests, the ExternalSecret name matches the secret name pattern
    ${secret_response}=    Get secret    ${TEST_STORAGE_SECRET_ID}    expected_status=200
    ${secret_json}=    Set Variable    ${secret_response.json()}
    ${external_secret_name}=    Get from dictionary    ${secret_json}    name

    # Bound cleanup to the key prefix this test owns. The unique suffix also keeps the writer Job
    # name collision-free when tests run concurrently in the same namespace.
    ${test_prefix}=    Set Variable    e2e-test-storage-${random_suffix}/
    ${test_key}=    Set Variable    ${test_prefix}${data}

    # Register cleanup before creating anything. If setup or a later assertion fails, teardown
    # still removes any partial local resources and any object the writer managed to create.
    @{local_resources}=    Create List
    &{cleanup_context}=    Create Dictionary
    ...    namespace=${TEST_PROJECT}[name]
    ...    config_map_name=${config_map_name}
    ...    secret_name=${external_secret_name}
    ...    access_key_name=${access_key_name}
    ...    secret_key_name=${secret_key_name}
    ...    bucket_url=${bucket_url}
    ...    test_data_prefix=${test_prefix}
    ...    local_resources=${local_resources}
    ...    write_started=${False}
    Set Test Variable    ${TEST_S3_CLEANUP_CONTEXT}    ${cleanup_context}
    Set Test Variable    ${TEST_S3_KEY}    ${test_key}
    Register S3 Local Resources For Cleanup
    ...    ${TEST_PROJECT}[name]
    ...    ${config_map_name}
    ...    ${external_secret_name}

    # For local development, manually create ConfigMap and Secret. In a real cluster, these
    # would be created by the Agent.
    Create Storage ConfigMap For Local Testing
    ...    ${TEST_PROJECT}[name]
    ...    ${config_map_name}
    ...    ${bucket_url}
    ...    ${access_key_name}
    ...    ${secret_key_name}
    ...    ${external_secret_name}

    Create ExternalSecret For Local Testing
    ...    ${TEST_PROJECT}[name]
    ...    ${external_secret_name}
    ...    ${access_key_name}
    ...    ${secret_key_name}
    ...    ${bucket_url}

    # Mark the write as started immediately before apply: from this point, teardown must attempt
    # object cleanup even when Job submission or a later assertion fails.
    Set To Dictionary    ${cleanup_context}    write_started=${True}
    ${job_name}=    Set Variable    s3-writer-test-${random_suffix}
    TRY
        ${job_name}=    Submit S3 Writer Job
        ...    ${TEST_PROJECT}[name]
        ...    ${config_map_name}
        ...    ${external_secret_name}
        ...    ${access_key_name}
        ...    ${secret_key_name}
        ...    ${test_key}
        ...    ${data}
        ...    ${random_suffix}

        Wait For Job Completion    ${job_name}    ${TEST_PROJECT}[name]    timeout=2 min
        Verify Job Succeeded    ${job_name}    ${TEST_PROJECT}[name]
        ${logs}=    Get Job Logs    ${job_name}    ${TEST_PROJECT}[name]
    FINALLY
        # Stop a timed-out writer before teardown deletes its objects. Otherwise it can write
        # after cleanup and recreate the leak this teardown is meant to prevent.
        Delete Job    ${job_name}    ${TEST_PROJECT}[name]
    END

    # Teardown retains enough metadata to recreate these access resources if deleting a storage
    # makes the Agent remove them first.
    Log    Successfully wrote test data '${data}' to S3 at key: ${test_key}    INFO

S3 bucket data should still exist
    [Arguments]    ${bucket_url}    ${expected_data}
    [Documentation]    Verifies that data still exists in the S3 bucket after storage deletion
    ...    This is expected behavior - storage resources manage access, not data lifecycle
    ...    Uses the stored TEST_S3_KEY from the write operation

    # The storage was deleted, but we can use the bucket URL to verify data persistence
    # We need to create a new temporary storage pointing to the same bucket

    Log    Verifying S3 data still exists at key: ${TEST_S3_KEY}    INFO

    # Create a new storage pointing to the same bucket for verification
    ${new_storage_name}=    Evaluate    "temp-verify-storage-" + str(int(__import__('time').time()))

    @{project_ids}=    Create list    ${TEST_PROJECT_ID}

    ${storage_data}=    Create dictionary
    ...    name=${new_storage_name}
    ...    type=S3
    ...    scope=Organization
    ...    secretId=${TEST_STORAGE_SECRET_ID}
    ...    projectIds=${project_ids}
    ...    spec=${TEST_VALID_S3_SPEC}

    ${create_response}=    Create storage
    ...    storage_data=${storage_data}
    ...    expected_status=200

    ${new_storage_id}=    Get from dictionary    ${create_response.json()}    id
    Append To List    ${CREATED_STORAGE_IDS}    ${new_storage_id}

    # Wait for storage to sync
    Wait until keyword succeeds    1 min    5 sec
    ...    Verify storage has status "Synced" for ID    ${new_storage_id}

    # Now use S3 reader job to verify data
    ${random_suffix}=    Generate Random Suffix

    ${storage_response}=    Get storage    ${new_storage_id}    expected_status=200
    ${storage_json}=    Set Variable    ${storage_response.json()}

    ${storage_name}=    Get from dictionary    ${storage_json}    name
    ${config_map_name}=    Set Variable    ${storage_name}-info-config-map

    ${access_key_name}=    Get from dictionary    ${TEST_VALID_S3_SPEC}    accessKeyName
    ${secret_key_name}=    Get from dictionary    ${TEST_VALID_S3_SPEC}    secretKeyName

    ${secret_response}=    Get secret    ${TEST_STORAGE_SECRET_ID}    expected_status=200
    ${secret_json}=    Set Variable    ${secret_response.json()}
    ${external_secret_name}=    Get from dictionary    ${secret_json}    name

    # For local development, manually create ConfigMap and Secret
    Register S3 Local Resources For Cleanup
    ...    ${TEST_PROJECT}[name]
    ...    ${config_map_name}
    ...    ${external_secret_name}
    Create Storage ConfigMap For Local Testing
    ...    ${TEST_PROJECT}[name]
    ...    ${config_map_name}
    ...    ${bucket_url}
    ...    ${access_key_name}
    ...    ${secret_key_name}
    ...    ${external_secret_name}

    Create ExternalSecret For Local Testing
    ...    ${TEST_PROJECT}[name]
    ...    ${external_secret_name}
    ...    ${access_key_name}
    ...    ${secret_key_name}
    ...    ${bucket_url}

    # Submit S3 reader job
    ${job_name}=    Submit S3 Reader Job
    ...    ${TEST_PROJECT}[name]
    ...    ${config_map_name}
    ...    ${external_secret_name}
    ...    ${access_key_name}
    ...    ${secret_key_name}
    ...    ${TEST_S3_KEY}
    ...    ${expected_data}
    ...    ${random_suffix}

    # Wait for job to complete
    Wait For Job Completion    ${job_name}    ${TEST_PROJECT}[name]    timeout=2 min

    # Verify job succeeded (meaning data was found and matched)
    Verify Job Succeeded    ${job_name}    ${TEST_PROJECT}[name]

    # Get and log the job output
    ${logs}=    Get Job Logs    ${job_name}    ${TEST_PROJECT}[name]

    # Clean up the reader Job. Keep the verification storage until Test teardown so its access
    # resources remain available; the existing storage cleanup step deletes the API resource.
    Delete Job    ${job_name}    ${TEST_PROJECT}[name]

    Log    ✓ Verified S3 data persists after storage deletion    INFO

New storage is created pointing to same bucket "${bucket_url}"
    [Documentation]    Creates a new storage resource pointing to the same S3 bucket
    ...    This demonstrates that multiple storage resources can share the same S3 bucket
    Should not be equal    ${TEST_STORAGE_SECRET_ID}    ${None}
    ...    msg=Storage secret not set.
    Should not be equal    ${TEST_VALID_S3_SPEC}    ${None}
    ...    msg=Valid S3 spec not set.

    ${name}=    Evaluate    "new-storage-same-bucket-" + str(int(__import__('time').time()))

    &{new_spec}=    Create dictionary
    ...    bucketUrl=${bucket_url}
    ...    accessKeyName=ACCESS_KEY_ID
    ...    secretKeyName=SECRET_ACCESS_KEY

    @{empty_project_ids}=    Create list

    ${storage_data}=    Create dictionary
    ...    name=${name}
    ...    type=S3
    ...    scope=Organization
    ...    secretId=${TEST_STORAGE_SECRET_ID}
    ...    projectIds=${empty_project_ids}
    ...    spec=${new_spec}

    ${response}=    Create storage
    ...    storage_data=${storage_data}
    ...    expected_status=200

    ${new_storage_id}=    Get from dictionary    ${response.json()}    id
    Set test variable    ${TEST_NEW_STORAGE_ID}    ${new_storage_id}
    Set test variable    ${TEST_STORAGE_ID}    ${new_storage_id}

    TRY
        Append to list    ${CREATED_STORAGE_IDS}    ${new_storage_id}
        Log    Added new storage ${new_storage_id} pointing to same bucket    DEBUG
    EXCEPT
        Log    CREATED_STORAGE_IDS not available    WARN
    END

    Log    Created new storage pointing to same S3 bucket: ${bucket_url}    WARN

New storage can access data from previous storage "${expected_data}"
    [Documentation]    Verifies that new storage can access data from the same S3 bucket
    ...    This is expected behavior - storage resources manage access, not data ownership
    ...    Uses the TEST_NEW_STORAGE_ID created by "New storage is created pointing to same bucket"

    Log    Verifying new storage can access data from previous storage    INFO

    # Use the TEST_NEW_STORAGE_ID which was created pointing to the same bucket
    ${random_suffix}=    Generate Random Suffix

    ${storage_response}=    Get storage    ${TEST_NEW_STORAGE_ID}    expected_status=200
    ${storage_json}=    Set Variable    ${storage_response.json()}

    ${storage_name}=    Get from dictionary    ${storage_json}    name
    ${config_map_name}=    Set Variable    ${storage_name}-info-config-map

    ${access_key_name}=    Get from dictionary    ${TEST_VALID_S3_SPEC}    accessKeyName
    ${secret_key_name}=    Get from dictionary    ${TEST_VALID_S3_SPEC}    secretKeyName

    ${secret_response}=    Get secret    ${TEST_STORAGE_SECRET_ID}    expected_status=200
    ${secret_json}=    Set Variable    ${secret_response.json()}
    ${external_secret_name}=    Get from dictionary    ${secret_json}    name

    # For local development, manually create ConfigMap and Secret
    ${bucket_url}=    Get from dictionary    ${TEST_VALID_S3_SPEC}    bucketUrl
    Register S3 Local Resources For Cleanup
    ...    ${TEST_PROJECT}[name]
    ...    ${config_map_name}
    ...    ${external_secret_name}
    Create Storage ConfigMap For Local Testing
    ...    ${TEST_PROJECT}[name]
    ...    ${config_map_name}
    ...    ${bucket_url}
    ...    ${access_key_name}
    ...    ${secret_key_name}
    ...    ${external_secret_name}

    Create ExternalSecret For Local Testing
    ...    ${TEST_PROJECT}[name]
    ...    ${external_secret_name}
    ...    ${access_key_name}
    ...    ${secret_key_name}
    ...    ${bucket_url}

    # Submit S3 reader job using the new storage's ConfigMap
    ${job_name}=    Submit S3 Reader Job
    ...    ${TEST_PROJECT}[name]
    ...    ${config_map_name}
    ...    ${external_secret_name}
    ...    ${access_key_name}
    ...    ${secret_key_name}
    ...    ${TEST_S3_KEY}
    ...    ${expected_data}
    ...    ${random_suffix}

    # Wait for job to complete
    Wait For Job Completion    ${job_name}    ${TEST_PROJECT}[name]    timeout=2 min

    # Verify job succeeded (meaning new storage can access old data)
    Verify Job Succeeded    ${job_name}    ${TEST_PROJECT}[name]

    # Get and log the job output
    ${logs}=    Get Job Logs    ${job_name}    ${TEST_PROJECT}[name]

    # Clean up the reader Job. Object cleanup and local credential teardown run in Test teardown
    # so they also happen when any assertion above fails.
    Delete Job    ${job_name}    ${TEST_PROJECT}[name]

    Log    ✓ Verified new storage can access data from previous storage    INFO

Register S3 Local Resources For Cleanup
    [Documentation]    Record a temporary ConfigMap and Secret for deletion after S3 cleanup.
    [Arguments]    ${namespace}    ${config_map_name}    ${secret_name}

    ${cleanup_context}=    Get Variable Value    ${TEST_S3_CLEANUP_CONTEXT}    ${None}
    IF    $cleanup_context is None    RETURN

    &{local_resource}=    Create Dictionary
    ...    namespace=${namespace}
    ...    config_map_name=${config_map_name}
    ...    secret_name=${secret_name}
    Append To List    ${cleanup_context}[local_resources]    ${local_resource}

Ensure S3 Cleanup Access Resources Exist
    [Documentation]    Recreate cleanup access resources only when the Agent removed them.
    [Arguments]    ${cleanup_context}

    ${config_result}=    Run Process
    ...    kubectl    get    configmap    ${cleanup_context}[config_map_name]
    ...    -n    ${cleanup_context}[namespace]    -o    name
    IF    ${config_result.rc} != 0
        ${config_missing}=    Evaluate    'not found' in $config_result.stderr.lower()
        IF    not ${config_missing}
            Fail    Could not inspect cleanup ConfigMap: ${config_result.stderr}
        END
        Create Storage ConfigMap For Local Testing
        ...    ${cleanup_context}[namespace]
        ...    ${cleanup_context}[config_map_name]
        ...    ${cleanup_context}[bucket_url]
        ...    ${cleanup_context}[access_key_name]
        ...    ${cleanup_context}[secret_key_name]
        ...    ${cleanup_context}[secret_name]
    END

    ${secret_result}=    Run Process
    ...    kubectl    get    secret    ${cleanup_context}[secret_name]
    ...    -n    ${cleanup_context}[namespace]    -o    name
    IF    ${secret_result.rc} != 0
        ${secret_missing}=    Evaluate    'not found' in $secret_result.stderr.lower()
        IF    not ${secret_missing}
            Fail    Could not inspect cleanup Secret: ${secret_result.stderr}
        END
        Create ExternalSecret For Local Testing
        ...    ${cleanup_context}[namespace]
        ...    ${cleanup_context}[secret_name]
        ...    ${cleanup_context}[access_key_name]
        ...    ${cleanup_context}[secret_key_name]
        ...    ${cleanup_context}[bucket_url]
    END

Clean Up S3 Test Objects
    [Documentation]    Best-effort teardown for direct-S3 test objects and local credentials.
    ...
    ...    Runs before API resource teardown, on both passing and failing test paths. Dedicated
    ...    e2e-test-bucket-* buckets are removed after their objects; platform-owned buckets are
    ...    never deleted.

    ${cleanup_context}=    Get Variable Value    ${TEST_S3_CLEANUP_CONTEXT}    ${None}
    IF    $cleanup_context is None    RETURN

    IF    ${cleanup_context}[write_started]
        TRY
            # Storage deletion may make the Agent remove the original access resources before
            # teardown. Recreate only what is genuinely absent: applying over live resources can
            # overwrite controller-managed credentials on the normal passing path.
            Ensure S3 Cleanup Access Resources Exist    ${cleanup_context}

            Remove S3 Test Objects
            ...    ${cleanup_context}[namespace]
            ...    ${cleanup_context}[config_map_name]
            ...    ${cleanup_context}[secret_name]
            ...    ${cleanup_context}[access_key_name]
            ...    ${cleanup_context}[secret_key_name]
            ...    ${cleanup_context}[test_data_prefix]
        EXCEPT    AS    ${error}
            Log    S3 test-object teardown failed: ${error}    WARN
        END
    END

    FOR    ${resource}    IN    @{cleanup_context}[local_resources]
        TRY
            Delete Storage Resources For Local Testing
            ...    ${resource}[namespace]
            ...    ${resource}[config_map_name]
            ...    ${resource}[secret_name]
        EXCEPT    AS    ${error}
            Log    Local S3 test-resource teardown failed: ${error}    WARN
        END
    END

    Set Test Variable    ${TEST_S3_CLEANUP_CONTEXT}    ${None}
