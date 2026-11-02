# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level dataset testing keywords.
...                 Provides business-logic level keywords for testing dataset operations.
...                 Uses the low-level API keywords from api/datasets.resource to implement
...                 higher-level testing scenarios. This is the main interface that
...                 test cases should use.
Resource            api/datasets.resource
Resource    resources/airm_projects.resource
Resource    resources/aiwb_test_data.resource
Resource            resources/resource_tracking.resource
Resource    aiwb_common.resource
Library             Collections
Library             String
Library             OperatingSystem


*** Variables ***
# CREATED_DATASET_IDS is lazy-initialized by Track Dataset For Cleanup


*** Keywords ***

Upload dataset request is sent
    [Documentation]    Sends request to upload a dataset using prepared test data
    [Arguments]             ${namespace}=${None}
    IF    $namespace == $None
        ${namespace}=    Get Project Namespace
    END
    ${response}=            Upload dataset
    ...                     jsonl_file_path=${TEST_DATASET_FILE}
    ...                     name=${TEST_DATASET}[name]
    ...                     description=${TEST_DATASET}[description]
    ...                     dataset_type=${TEST_DATASET}[type]
    ...                     namespace=${namespace}
    ...                     expected_status=200
    Set Test Variable       ${TEST_RESPONSE}             ${response}
    ${dataset_id}=          Get from dictionary     ${response.json()}      id
    Set test variable       ${TEST_DATASET_ID}      ${dataset_id}
    Track Dataset For Cleanup    ${dataset_id}

Finetune dataset exists
    [Documentation]    Creates a finetune dataset for testing and stores its ID as a test variable
    Valid dataset upload data is prepared
    Upload dataset request is sent
    Response status should be 200
    Dataset should exist in database  # Verify creation

A dataset exists
    [Documentation]    Creates a dataset via API and stores its ID as a test variable
    ...    This is a precondition keyword that:
    ...    1. Prepares valid dataset upload data
    ...    2. Uploads the dataset via API (only supported method in AIWB)
    ...    3. Stores the ID for later use in test variable ${TEST_DATASET_ID}
    Valid dataset upload data is prepared
    Upload dataset request is sent
    Dataset should exist in database  # Verify creation

A dataset is uploaded
    [Documentation]    Uploads a dataset via API and stores its ID as a test variable
    ...    This is a precondition keyword that:
    ...    1. Prepares valid dataset upload data
    ...    2. Uploads the dataset via API
    ...    3. Stores the ID for later use in test variable ${TEST_DATASET_ID}
    Valid dataset upload data is prepared
    Upload dataset request is sent
    Dataset should exist in database  # Verify creation

Dataset should exist in database
    [Documentation]    Verify dataset exists in database by fetching it via API
    ${dataset_id}=          Set Variable            ${TEST_DATASET_ID}
    ${namespace}=           Get Project Namespace
    ${db_response}=         Get dataset             ${dataset_id}           namespace=${namespace}   expected_status=200

    Log                     Verifying dataset ${dataset_id} exists via API                          DEBUG

    # Verify basic fields
    Dictionary should contain key                   ${db_response.json()}                           id
    Dictionary should contain value                 ${db_response.json()}                           ${dataset_id}
    Dictionary should contain key                   ${db_response.json()}                           name
    Dictionary should contain key                   ${db_response.json()}                           createdAt
    Dictionary should contain key                   ${db_response.json()}                           updatedAt

The dataset should not exist in database
    [Documentation]    Verifies the dataset no longer exists in database
    ${dataset_id}=          Set Variable            ${TEST_DATASET_ID}
    ${namespace}=           Get Project Namespace
    ${db_response}=         Get dataset             ${dataset_id}           namespace=${namespace}   expected_status=404
    Log                     Dataset ${dataset_id} no longer exists in database (404 Not Found) as expected            DEBUG

Multiple datasets exist
    [Documentation]    Creates multiple datasets for testing list endpoints
    ...    Note: This keyword only creates datasets. Tests are responsible for their own verification.
    [Arguments]             ${count}=3

    FOR    ${index}    IN RANGE    ${count}
        Log                     Creating dataset ${index+1} of ${count}         DEBUG
        Valid dataset upload data is prepared
        Upload dataset request is sent
    END
    Log                     Successfully created ${count} datasets: ${CREATED_DATASET_IDS}                  INFO

List datasets request is sent
    [Documentation]    Sends request to list datasets with optional filters
    [Arguments]             ${type}=${None}         ${name}=${None}
    ${namespace}=           Get Project Namespace
    ${response}=            List datasets           type=${type}            name=${name}            expected_status=200     namespace=${namespace}
    Set Test Variable       ${TEST_RESPONSE}             ${response}

List datasets request is sent with type "${dataset_type}"
    [Documentation]    Sends a request to list datasets filtered by type
    ${namespace}=           Get Project Namespace
    ${response}=            List datasets with type filter                  ${dataset_type}         namespace=${namespace}
    Set test variable       ${TEST_RESPONSE}             ${response}

List datasets request is sent with name "${name}"
    [Documentation]    Sends a request to list datasets filtered by name
    ${namespace}=           Get Project Namespace
    ${response}=            List datasets with name filter                  ${name}                 namespace=${namespace}
    Set test variable       ${TEST_RESPONSE}             ${response}

A dataset does not exist
    [Documentation]    Sets up a non-existent dataset ID for testing
    ${dataset_id}=          Evaluate                str(uuid.uuid4())       modules=uuid
    Set test variable       ${TEST_DATASET_ID}      ${dataset_id}

Modify Dataset Request Is Sent
    [Documentation]    NOT SUPPORTED: Sends request to modify an existing dataset.
    ...    This keyword is kept for backward compatibility but will always fail.
    ...    The AIWB API does not support modifying datasets - they are immutable after creation.
    [Arguments]             ${new_desc}
    ${dataset_data}=        Create dictionary       description=${new_desc}

    Log                     Sending modify request for dataset ${TEST_DATASET_ID} - NOTE: This will fail, endpoint not supported!                   WARN
    ${namespace}=           Get Project Namespace
    ${response}=            Modify dataset          ${TEST_DATASET_ID}      ${dataset_data}         expected_status=any     namespace=${namespace}
    Set test variable       ${TEST_RESPONSE}             ${response}

Delete dataset request is sent
    [Documentation]    Sends a request to delete a dataset
    ${namespace}=           Get Project Namespace
    ${response}=            Delete dataset          ${TEST_DATASET_ID}      expected_status=any     namespace=${namespace}
    Set test variable       ${TEST_RESPONSE}             ${response}

Clean Up Dataset Test Resources
    [Documentation]    Clean up all dataset resources created during tests.
    ...    Resolves namespace from test state and passes it explicitly to API keywords.
    ${tracking_list}=       Get Variable Value    ${CREATED_DATASET_IDS}    ${None}
    IF    $tracking_list is None    RETURN
    ${count}=               Get Length    ${tracking_list}
    IF    ${count} == 0    RETURN    END
    Log                     Cleaning up ${count} dataset(s)    INFO
    ${namespace}=           Get Project Namespace
    FOR    ${dataset_id}    IN    @{tracking_list}
        TRY
            Delete dataset    ${dataset_id}    ${namespace}    expected_status=any
            Log               Deleted dataset ${dataset_id}    INFO
        EXCEPT    AS    ${error}
            Log               Failed to delete dataset ${dataset_id}: ${error}    WARN
        END
    END
    @{empty_list}=          Create List
    Set Suite Variable      ${CREATED_DATASET_IDS}    ${empty_list}

Send download dataset request and expect status
    [Documentation]    Sends a request to download a dataset and expect a specific status
    [Arguments]             ${status}               ${dataset_id}=${TEST_DATASET_ID}
    ${namespace}=           Get Project Namespace
    ${response}=            Download dataset        ${dataset_id}           expected_status=${status}                       namespace=${namespace}
    Set test variable       ${TEST_RESPONSE}             ${response}

Download dataset request is sent
    [Documentation]    Sends a request to download a dataset's content expecting status 200
    Send download dataset request and expect status                         200

Response should contain datasets list
    [Documentation]    Verifies response contains a list of datasets
    ${body}=                Set variable            ${TEST_RESPONSE.json()}
    ${datasets}=            Get from dictionary     ${body}                 data
    ${is_list}=             Evaluate                isinstance(${datasets}, list)
    Should Be True          ${is_list}              msg=Response body 'data' field is not a list: ${datasets}
    ${count}=               Get length              ${datasets}
    Should be true          ${count} >= 0           msg=Dataset list is unexpectedly empty or invalid

Response should contain at least ${expected_count} datasets
    [Documentation]    Verifies response list contains at least the expected number of datasets
    ${body}=                Set variable            ${TEST_RESPONSE.json()}
    ${datasets}=            Get from dictionary     ${body}                 data
    ${count}=               Get length              ${datasets}
    Should be true          ${count} >= ${expected_count}                   msg=Expected at least ${expected_count} datasets, but found ${count}

Listed datasets should report their file sizes
    [Documentation]    Verifies every listed dataset reports a non-negative file size.
    VAR                     ${body}                 ${TEST_RESPONSE.json()}
    FOR    ${dataset}    IN    @{body}[data]
        Dictionary Should Contain Key              ${dataset}              sizeBytes
        Should Be True                             ${dataset}[sizeBytes] >= 0
    END

Response should contain only datasets with type "${expected_type}"
    [Documentation]    Verifies all datasets in the response list have the specified type
    ${body}=                Set variable            ${TEST_RESPONSE.json()}
    ${datasets}=            Get from dictionary     ${body}                 data
    Should Not Be Empty     ${datasets}             msg=Dataset list is empty, cannot verify type filter.
    FOR    ${dataset}    IN    @{datasets}
        Dictionary should contain item                  ${dataset}              type                    ${expected_type}
    END

Response should contain only datasets with name "${expected_name}"
    [Documentation]    Verifies all datasets in the response list have the specified name
    ${body}=                Set variable            ${TEST_RESPONSE.json()}
    ${datasets}=            Get from dictionary     ${body}                 data
    Should Not Be Empty     ${datasets}             msg=Dataset list is empty, cannot verify name filter.
    FOR    ${dataset}    IN    @{datasets}
        Dictionary should contain item                  ${dataset}              name                    ${expected_name}
    END

Response should contain downloaded file content
    [Documentation]    Verifies the download response contains non-empty content and correct headers
    Should Not Be Empty     ${TEST_RESPONSE.content}     msg=Downloaded file content is empty.
    Dictionary Should Contain Key                   ${TEST_RESPONSE.headers}     Content-Disposition
    Dictionary Should Contain Key                   ${TEST_RESPONSE.headers}     Content-Type
    Should Contain          ${TEST_RESPONSE.headers['Content-Disposition']}      attachment; filename=
    Should Contain          ${TEST_RESPONSE.headers['Content-Type']}             application/jsonl

Downloaded content should match uploaded file
    [Documentation]    Verifies the downloaded content matches the original uploaded file
    ${expected_content}=    Get Binary File         ${TEST_DATASET_FILE}
    Should Be Equal         ${TEST_RESPONSE.content}     ${expected_content}

Dataset size should match uploaded file
    [Documentation]    Verifies the reported dataset size matches its uploaded file.
    ${expected_size}=       Get File Size           ${TEST_DATASET_FILE}
    VAR                     ${body}                 ${TEST_RESPONSE.json()}
    Dictionary Should Contain Item                  ${body}                 sizeBytes               ${expected_size}

Get dataset request is sent for "${dataset_id}"
    [Documentation]    Get a specific dataset and store the response as test variable.
    ${namespace}=           Get Project Namespace
    ${response}=            Get dataset             ${dataset_id}           namespace=${namespace}   expected_status=200
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Get dataset request is sent
    [Documentation]    Get the current test dataset and store the response
    ${namespace}=           Get Project Namespace
    ${response}=            Get dataset             ${TEST_DATASET_ID}      namespace=${namespace}   expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Get request is sent for non-existent dataset
    [Documentation]    Sends a GET request for a dataset ID that does not exist
    ${fake_id}=             Evaluate                str(uuid.uuid4())       modules=uuid
    ${namespace}=           Get Project Namespace
    ${response}=            Get dataset             ${fake_id}              namespace=${namespace}   expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Download request is sent for non-existent dataset
    [Documentation]    Sends a download request for a dataset ID that does not exist
    ${fake_id}=             Evaluate                str(uuid.uuid4())       modules=uuid
    ${namespace}=           Get Project Namespace
    ${response}=            Download dataset        ${fake_id}              namespace=${namespace}   expected_status=any
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Oversized dataset upload request is sent
    [Documentation]    Generates and uploads a dataset exceeding the maximum file size limit.
    ...    Uses in-memory JSONL generation to avoid creating large temp files on disk.
    # K8s/DB resource names must be lowercase.
    ${random_suffix}=       Generate random string                          8                       [LOWER][NUMBERS]
    VAR    ${dataset_name}    test-oversized-${random_suffix}
    ${namespace}=           Get Project Namespace
    ${response}=            Upload oversized dataset                        ${dataset_name}         ${namespace}
    IF    ${response.status_code} == 200 or ${response.status_code} == 201
        VAR    ${body}    ${response.json()}
        Track Dataset For Cleanup    ${body}[id]
    END
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Upload dataset with same name is attempted
    [Documentation]    Attempts to upload a dataset with the same name as an existing one.
    ...    Expects a 409 Conflict response.
    ${namespace}=           Get Project Namespace
    ${response}=            Upload dataset
    ...                     jsonl_file_path=${TEST_DATASET_FILE}
    ...                     name=${TEST_DATASET}[name]
    ...                     description=${TEST_DATASET}[description]
    ...                     dataset_type=${TEST_DATASET}[type]
    ...                     namespace=${namespace}
    ...                     expected_status=any
    IF    ${response.status_code} == 200 or ${response.status_code} == 201
        VAR    ${body}    ${response.json()}
        Set Test Variable       ${TEST_DATASET_ID}    ${body}[id]
        Track Dataset For Cleanup    ${body}[id]
    END
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

Response should contain the uploaded dataset
    [Documentation]    Verifies the uploaded dataset appears in the dataset list response
    VAR    ${body}    ${TEST_RESPONSE.json()}
    VAR    ${found}    ${False}
    FOR    ${dataset}    IN    @{body}[data]
        IF    "${dataset}[name]" == "${TEST_DATASET}[name]"
            VAR    ${found}    ${True}
            BREAK
        END
    END
    Should be true          ${found}                msg=Uploaded dataset '${TEST_DATASET}[name]' not found in list response
