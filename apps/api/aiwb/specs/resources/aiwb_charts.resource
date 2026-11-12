# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level chart testing keywords.
...                 Provides business-logic level keywords for testing chart operations.
...                 Uses the low-level API keywords from api/charts.resource to implement
...                 higher-level testing scenarios.
Resource            api/charts.resource
Resource    resources/aiwb_test_data.resource
Resource    resources/resource_tracking.resource
Library             String
Library             uuid
Library             TestPrefix
Library             ChartCatalog


*** Variables ***
${TEMPLATE_FILE}        ${CURDIR}/../test_data/charts/template.yaml
${VALUES_FILE}          ${CURDIR}/../test_data/charts/values.yaml
${SCHEMA_FILE}          ${CURDIR}/../test_data/charts/schema.json
${SIGNATURE_FILE}       ${CURDIR}/../test_data/charts/signature.yaml
${TEST_CHART_ID}        ${None}
${TEST_CHART_NAME}      ${None}
${TEST_CHART_DATA}      ${None}
# CREATED_CHART_IDS is lazy-initialized by Track Chart For Cleanup


*** Keywords ***
Create chart request is sent
    [Documentation]    Sends a request to create a new chart and stores the ID
    [Arguments]             ${name}=${TEST_CHART_NAME}                      ${template}=${TEMPLATE_FILE}                    ${values}=${VALUES_FILE}                        ${schema}=${SCHEMA_FILE}       ${signature}=${SIGNATURE_FILE}
    ${response}=            Create chart request    ${name}                 ${template}             ${values}               ${schema}       ${signature}
    Set Test Variable       ${TEST_RESPONSE}        ${response}

    Response status should be 201

    ${json}=                Set Variable            ${TEST_RESPONSE.json()}
    ${chart_id}=            Get From Dictionary     ${json}                 id
    Set Test Variable       ${TEST_CHART_ID}        ${chart_id}

    Track Chart For Cleanup    ${chart_id}

List charts request is sent
    [Documentation]    Sends a list charts request and stores the response
    [Arguments]             ${page_number}=1        ${page_size}=10         ${sort_by}=createdAt    ${sort_order}=desc
    ${response}=            List charts request     ${page_number}          ${page_size}            ${sort_by}              ${sort_order}
    Set Test Variable       ${TEST_RESPONSE}        ${response}

Delete chart request is sent
    [Documentation]    Sends a delete chart request for the current test chart
    ${response}=            Delete chart            ${TEST_CHART_ID}
    Set Test Variable       ${TEST_RESPONSE}        ${response}

Valid chart data is prepared
    [Documentation]    Creates chart data with valid test values using unique chart name
    [Arguments]             ${chart_name}=${None}                           ${chart_type}=INFERENCE

    # Generate unique chart name to avoid 409 conflicts from stale data
    IF    $chart_name is None
        # Chart names must be lowercase (K8s/DB constraint).
        ${random_suffix}=       Generate random string                          8                       [LOWER][NUMBERS]
        ${prefix}=              Test Prefix
        ${test_chart_name}=     Set Variable            ${prefix}chart-${random_suffix}
    ELSE
        ${test_chart_name}=     Set Variable            ${chart_name}
    END
    Set Test Variable       ${TEST_CHART_NAME}      ${test_chart_name}

    # No projectId needed for AIWB charts
    &{chart_data}=          Create Dictionary       name=${test_chart_name}                         type=${chart_type}
    Set Test Variable       ${TEST_CHART_DATA}      ${chart_data}

Chart should exist in database
    [Documentation]    Verifies the created chart exists in database and is ready for use
    ${chart_id}=            Set Variable            ${TEST_CHART_ID}
    Get chart               ${chart_id}             expected_status=200

The chart should not exist in database
    [Documentation]    Verifies the chart no longer exists in database
    ${chart_id}=            Set Variable            ${TEST_CHART_ID}

    ${chart}=               Get chart               ${chart_id}             expected_status=404
    Log                     Chart ${chart_id} does not exist in database (404 Not Found) as expected              DEBUG

A chart exists
    [Documentation]    Creates a new chart and stores its ID as a test variable
    Valid chart data is prepared
    Create chart request is sent

    Response status should be 201

    # Extract chart ID as a test variable to ensure test independence
    ${json}=                Set Variable            ${TEST_RESPONSE.json()}

    # Try to get direct ID first
    ${has_direct_id}=       Evaluate                'id' in $json

    IF    ${has_direct_id}
        ${chart_id}=            Get from dictionary     ${json}                 id
        Set test variable       ${TEST_CHART_ID}        ${chart_id}
        Log                     Using chart ID: ${chart_id}                     DEBUG
    ELSE
        # Try to get it from charts array
        Dictionary Should Contain Key                   ${json}                 charts                  Chart response does not contain either direct ID or charts array
        ${charts}=              Get from dictionary     ${json}                 charts
        @{charts_list}=         Convert to list         ${charts}
        Should not be empty     ${charts_list}          Charts array is empty, cannot extract chart ID
        ${chart}=               Get from list           ${charts_list}          0
        Dictionary Should Contain Key                   ${chart}                id                      First chart in array does not contain ID
        ${chart_id}=            Get from dictionary     ${chart}                id
        Set test variable       ${TEST_CHART_ID}        ${chart_id}
        Log                     Using chart ID from charts array: ${chart_id}                   DEBUG
    END

    # Verify chart was actually created by making a separate verification call
    ${verify_response}=     Get chart               ${TEST_CHART_ID}        expected_status=200

Multiple charts exist
    [Documentation]    Creates multiple charts to ensure listing/pagination tests have data
    FOR    ${i}    IN RANGE    3
        Valid chart data is prepared
        Create chart request is sent
    END

Required chart files exist
    [Documentation]    Verifies required chart files exist
    File should exist       ${TEMPLATE_FILE}        Template file does not exist
    File should exist       ${VALUES_FILE}          Values file does not exist
    File should exist       ${SCHEMA_FILE}          Schema file does not exist

A chart does not exist
    [Documentation]    Sets up a non-existent chart ID for testing
    ${chart_id}=            Evaluate                str(uuid.uuid4())       modules=uuid
    Set test variable       ${TEST_CHART_ID}        ${chart_id}

Update chart request is sent
    [Documentation]    Sends a request to update an existing chart with new template files
    [Arguments]             ${template}=${TEMPLATE_FILE}    ${signature}=${SIGNATURE_FILE}
    ${response}=            Update chart request    ${TEST_CHART_ID}        template_file=${template}    signature_file=${signature}
    Set Test Variable       ${TEST_RESPONSE}        ${response}

Chart should be updated
    [Documentation]    Verifies the chart was successfully updated by fetching it
    ${chart_id}=            Set Variable            ${TEST_CHART_ID}
    Get chart               ${chart_id}             expected_status=200

Find chart ID by name
    [Documentation]    Find chart ID by chart name through API and set as variable.
    ...    Returns None when no chart has that name.
    [Arguments]             ${chart_name}           ${variable_name}=TEST_CHART_ID
    ${response}=            List charts request     expected_status=200
    ${chart_id}=            Find chart id           ${response.json()}      ${chart_name}
    IF    $chart_id is not None
        VAR    ${${variable_name}}    ${chart_id}    scope=TEST
    END
    RETURN                  ${chart_id}

A chart is uploaded with a file that escapes the chart directory
    [Documentation]    Uploads a new chart whose template file is placed above the chart root
    Upload chart with template at    ../../escaped-template.yaml

A chart is uploaded with a file at an absolute location
    [Documentation]    Uploads a new chart whose template file is placed at an absolute filesystem location
    Upload chart with template at    /tmp/escaped-template.yaml

A chart is uploaded with a file in a subdirectory
    [Documentation]    Uploads a new chart whose template file is nested inside the chart
    Upload chart with template at    templates/deployment.yaml

Upload chart with template at
    [Documentation]    Uploads the prepared chart with its template file sent under the given location.
    ...    Any chart the API accepts is tracked so it is cleaned up even when the test expected a rejection.
    ...    Uploads with the given token, or with the run's admin token when none is given.
    [Arguments]    ${template_location}    ${access_token}=${None}
    ${response}=    Create chart request    ${TEST_CHART_NAME}    ${TEMPLATE_FILE}    ${VALUES_FILE}    ${SCHEMA_FILE}
    ...    ${SIGNATURE_FILE}    template_name=${template_location}    access_token=${access_token}
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST
    ${chart_id}=    Created chart id    ${response}
    IF    $chart_id is not None
        VAR    ${TEST_CHART_ID}    ${chart_id}    scope=TEST
        Track Chart For Cleanup    ${chart_id}
    END

The chart is updated with a file that escapes the chart directory
    [Documentation]    Records the chart's current files, then replaces them with a template placed above the chart root
    ${before}=    Get chart    ${TEST_CHART_ID}    expected_status=200
    VAR    ${TEST_CHART_FILES_BEFORE}    ${before.json()}[files]    scope=TEST
    ${response}=    Update chart request    ${TEST_CHART_ID}    template_file=${TEMPLATE_FILE}
    ...    template_name=../../escaped-template.yaml
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The chart upload should be accepted
    [Documentation]    Verifies the upload was stored as a new chart
    Response status should be 201

The chart upload should be rejected
    [Documentation]    Verifies the upload was refused as invalid input
    Response status should be 400

The chart update should be rejected
    [Documentation]    Verifies the update was refused as invalid input
    Response status should be 400

The chart should not be in the catalog
    [Documentation]    Verifies no chart with the prepared name was stored
    ${response}=    List charts request    expected_status=200
    Catalog should not contain chart    ${response.json()}    ${TEST_CHART_NAME}

The catalog listing should include the chart
    [Documentation]    Verifies the last catalog listing includes the chart with the prepared name
    Catalog should contain chart    ${TEST_RESPONSE.json()}    ${TEST_CHART_NAME}

The chart should still be in the catalog
    [Documentation]    Verifies the chart with the prepared name is still listed in the catalog
    ${response}=    List charts request    expected_status=200
    Catalog should contain chart    ${response.json()}    ${TEST_CHART_NAME}

The chart files should be unchanged
    [Documentation]    Verifies the chart still holds exactly the files it had before the rejected update
    ${after}=    Get chart    ${TEST_CHART_ID}    expected_status=200
    Should Be Equal    ${after.json()}[files]    ${TEST_CHART_FILES_BEFORE}

The chart should keep the file in its subdirectory
    [Documentation]    Verifies the nested template file was stored at its location within the chart
    ${response}=    Get chart    ${TEST_CHART_ID}    expected_status=200
    Chart should contain file    ${response.json()}    templates/deployment.yaml

Clean Up All Created Charts
    [Documentation]    Clean up all created chart resources using generic pattern
    Generic Clean Up All Created Chart
