# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Keywords for interacting with the Catalog API charts endpoints.
...                 Provides low-level keywords for managing Helm charts through the API.
...                 Includes operations for creating, listing, and deleting charts.
Library             RequestsLibrary
Library             Collections
Library             OperatingSystem
Library             CallerAuthorization
Resource            resources/api/common.resource


*** Variables ***
&{HEADERS}      Content-Type=multipart/form-data
# Default value for signature file - can be overridden by test suites
${SIGNATURE_FILE}   ${CURDIR}/../../test_data/charts/signature.yaml


*** Keywords ***
Charts endpoint
    [Documentation]    Returns the full charts endpoint URL
    ${endpoint}=            Service API Endpoint    aiwb    endpoint=charts
    RETURN                  ${endpoint}

Create chart request
    [Documentation]    Create a new chart with the provided files.
    ...
    ...    Args:
    ...    name (str): Name of the chart
    ...    template_file (str): Path to chart template file
    ...    values_file (str): Path to values YAML file
    ...    values_schema_file (str): Path to values schema JSON file
    ...    signature_file (str): Path to signature YAML file (optional, defaults to test data)
    ...    additional_files (list): Optional additional chart files
    ...    template_name (str): Location of the template file within the chart, as sent in the upload
    ...    access_token (str): Token to upload with (optional, defaults to the run's admin token)
    ...
    ...    Returns:
    ...    response: API response containing the created chart
    ...
    ...    Raises:
    ...    HTTPError: If chart creation fails
    ...    IOError: If any of the required files cannot be read
    [Arguments]             ${name}                 ${template_file}        ${values_file}          ${values_schema_file}       ${signature_file}=${SIGNATURE_FILE}     @{additional_files}     ${expected_status}=any    ${template_name}=template.yaml    ${access_token}=${None}
    ${template_content}=    Get Binary File         ${template_file}
    ${values_content}=      Get Binary File         ${values_file}
    ${schema_content}=      Get Binary File         ${values_schema_file}
    ${signature_content}=   Get Binary File         ${signature_file}

    # Format: {'field_name': ('filename', filedata, 'content-type')}
    # No projectId needed for AIWB charts API
    ${data}=                Create dictionary       name=${name}            type=INFERENCE
    @{template}=            Create list             ${template_name}        ${template_content}
    @{values}=              Create list             values.yaml             ${values_content}
    @{schema}=              Create list             schema.json             ${schema_content}
    @{signature}=           Create list             signature.yaml          ${signature_content}
    &{files}=               Create dictionary
    ...                     files=${template}
    ...                     userInputs=${values}
    ...                     signature=${signature}

    ${endpoint} =           Charts endpoint
    &{headers}=             Bearer headers          ${access_token}

    Log                     POST ${endpoint} with data: ${data}             DEBUG
    ${response}=            POST                    ${endpoint}             headers=${headers}      data=${data}            files=${files}          expected_status=${expected_status}    verify=${VERIFY_SSL}
    Log                     Chart creation response: status=${response.status_code}                 DEBUG
    IF    ${response.status_code} in [200, 201]
        ${response_json}=       Set Variable            ${response.json()}
        ${chart_id}=        Get From Dictionary     ${response_json}        id
        ${chart_name}=      Get From Dictionary     ${response_json}        name
        Log                     Created chart ${chart_id} (${chart_name})      INFO
    END
    RETURN                  ${response}

List charts request
    [Documentation]    List charts with pagination and sorting.
    ...
    ...    Args:
    ...    page_number (int): Page number for pagination (default: 1)
    ...    page_size (int): Number of items per page (default: 10)
    ...    sort_by (str): Field to sort by (default: createdAt)
    ...    sort_order (str): Sort direction - asc or desc (default: desc)
    ...    access_token (str): Token to list with (optional, defaults to the session's admin token)
    ...
    ...    Returns:
    ...    response: API response containing list of charts
    [Arguments]             ${page_number}=1        ${page_size}=10         ${sort_by}=createdAt                            ${sort_order}=desc      ${expected_status}=any    ${access_token}=${None}
    ${params}=              Create dictionary
    ...                     pageNumber=${page_number}
    ...                     pageSize=${page_size}
    ...                     sortBy=${sort_by}
    ...                     sortOrder=${sort_order}

    Create api session    aiwb
    ${endpoint} =           Charts endpoint
    &{request_options}=     Request options for token    ${access_token}
    Log                     GET ${endpoint} with params: ${params}          DEBUG
    ${response}=            Safe Get Request          ${endpoint}             params=${params}        expected_status=${expected_status}    &{request_options}
    Log                     List charts response: status=${response.status_code}                    DEBUG
    RETURN                  ${response}

Delete chart
    [Documentation]    Delete a specific chart.
    ...
    ...    Args:
    ...    chart_id (str): UUID of the chart to delete
    ...    access_token (str): Token to delete with (optional, defaults to the session's admin token)
    ...
    ...    Returns:
    ...    response: API response (empty on success)
    ...
    ...    Raises:
    ...    HTTPError: If the chart is not found or deletion fails
    [Arguments]             ${chart_id}             ${expected_status}=any    ${access_token}=${None}
    Create api session    aiwb
    ${endpoint} =           Charts endpoint
    &{request_options}=     Request options for token    ${access_token}
    Log                     DELETE ${endpoint}/${chart_id}  DEBUG
    ${response}=            Safe Delete Request       ${endpoint}/${chart_id}                         expected_status=${expected_status}    &{request_options}
    Log                     Delete chart response: status=${response.status_code}                   DEBUG
    IF    ${response.status_code} == 204
        Log                     Deleted chart ${chart_id}       INFO
    END
    RETURN                  ${response}

Update chart request
    [Documentation]    Update an existing chart with the provided files.
    ...
    ...    Args:
    ...    chart_id (str): UUID of the chart to update
    ...    template_file (str): Optional path to updated chart template file
    ...    values_file (str): Optional path to updated values YAML file
    ...    values_schema_file (str): Optional path to updated values schema JSON file
    ...    signature_file (str): Optional path to updated signature YAML file
    ...    template_name (str): Location of the template file within the chart, as sent in the upload
    ...
    ...    Returns:
    ...    response: API response containing the updated chart
    [Arguments]             ${chart_id}             ${template_file}=${None}    ${values_file}=${None}      ${values_schema_file}=${None}       ${signature_file}=${None}    ${expected_status}=any    ${template_name}=template.yaml
    ${data}=                Create Dictionary
    &{files}=               Create Dictionary

    IF    $template_file is not None
        ${template_content}=    Get Binary File         ${template_file}
        @{template}=            Create List             ${template_name}        ${template_content}
        Set To Dictionary       ${files}                files=${template}
    END
    IF    $values_file is not None
        ${values_content}=      Get Binary File         ${values_file}
        @{values}=              Create List             values.yaml             ${values_content}
        Set To Dictionary       ${files}                userInputs=${values}
    END
    IF    $signature_file is not None
        ${signature_content}=   Get Binary File         ${signature_file}
        @{signature}=           Create List             signature.yaml          ${signature_content}
        Set To Dictionary       ${files}                signature=${signature}
    END

    ${endpoint}=            Service API Endpoint    aiwb    endpoint=charts/${chart_id}
    ${access_token}=        Authorization Token
    &{headers}=             Create Dictionary       Authorization=Bearer ${access_token}

    Log                     PUT ${endpoint}         DEBUG
    ${response}=            PUT                     ${endpoint}             headers=${headers}      data=${data}            files=${files}          expected_status=${expected_status}    verify=${VERIFY_SSL}
    Log                     Chart update response: status=${response.status_code}                   DEBUG
    RETURN                  ${response}

Get chart
    [Documentation]    Get a specific chart by ID
    [Arguments]             ${chart_id}             ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=            Service API Endpoint    aiwb    endpoint=charts/${chart_id}
    Log                     GET ${endpoint}         DEBUG
    ${response}=            Safe Get Request         ${endpoint}             expected_status=${expected_status}
    Log                     Get chart response: status=${response.status_code}                      DEBUG
    RETURN                  ${response}
