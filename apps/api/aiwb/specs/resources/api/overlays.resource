# Copyright (c) Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Keywords for interacting with the Catalog API overlays endpoints.
...                 Provides low-level keywords for managing deployment overlays through the API.
...                 Includes operations for creating, listing, getting, updating, and deleting overlays.
Library             RequestsLibrary
Library             Collections
Library             OperatingSystem
Library             CallerAuthorization
Resource            resources/api/common.resource


*** Keywords ***
Overlays endpoint
    [Documentation]    Returns the full overlays endpoint URL
    ${endpoint}=            Service API Endpoint    aiwb    endpoint=overlays
    RETURN                  ${endpoint}

Create overlay request
    [Documentation]    Create a new overlay with the provided file and chart ID.
    ...
    ...    Args:
    ...    chart_id (str): UUID of the chart to associate the overlay with
    ...    overlay_file (str): Path to YAML overlay file
    ...    canonical_name (str): Optional canonical name for the overlay
    ...
    ...    Returns:
    ...    response: API response containing the created overlay
    [Arguments]             ${chart_id}             ${overlay_file}         ${canonical_name}=${None}    ${expected_status}=any
    ${overlay_content}=     Get Binary File         ${overlay_file}

    ${data}=                Create Dictionary       chartId=${chart_id}
    IF    $canonical_name is not None
        Set To Dictionary       ${data}                 canonicalName=${canonical_name}
    END
    @{overlay}=             Create List             overlay.yaml            ${overlay_content}
    &{files}=               Create Dictionary       overlayFile=${overlay}

    ${endpoint}=            Overlays endpoint
    ${access_token}=        Authorization Token
    &{headers}=             Create Dictionary       Authorization=Bearer ${access_token}

    Log                     POST ${endpoint} with chartId: ${chart_id}      DEBUG
    ${response}=            POST                    ${endpoint}             headers=${headers}      data=${data}            files=${files}          expected_status=${expected_status}    verify=${VERIFY_SSL}
    Log                     Overlay creation response: status=${response.status_code}               DEBUG
    IF    ${response.status_code} in [200, 201]
        ${response_json}=       Set Variable            ${response.json()}
        ${overlay_id}=          Get From Dictionary     ${response_json}        id
        Log                     Created overlay ${overlay_id}                   INFO
    END
    RETURN                  ${response}

List overlays request
    [Documentation]    List overlays with optional filtering.
    ...
    ...    Args:
    ...    chart_id (str): Optional chart ID to filter by
    ...    canonical_name (str): Optional canonical name to filter by
    ...
    ...    Returns:
    ...    response: API response containing list of overlays
    [Arguments]             ${chart_id}=${None}     ${canonical_name}=${None}    ${expected_status}=any
    ${params}=              Create Dictionary
    IF    $chart_id is not None
        Set To Dictionary       ${params}               chartId=${chart_id}
    END
    IF    $canonical_name is not None
        Set To Dictionary       ${params}               canonicalName=${canonical_name}
    END

    Create API Session      aiwb
    ${endpoint}=            Overlays endpoint
    Log                     GET ${endpoint} with params: ${params}          DEBUG
    ${response}=            Safe Get Request        ${endpoint}             params=${params}        expected_status=${expected_status}
    Log                     List overlays response: status=${response.status_code}                  DEBUG
    RETURN                  ${response}

Get overlay
    [Documentation]    Get a specific overlay by ID
    [Arguments]             ${overlay_id}           ${expected_status}=any
    Create API Session      aiwb
    ${endpoint}=            Service API Endpoint    aiwb    endpoint=overlays/${overlay_id}
    Log                     GET ${endpoint}         DEBUG
    ${response}=            Safe Get Request        ${endpoint}             expected_status=${expected_status}
    Log                     Get overlay response: status=${response.status_code}                    DEBUG
    RETURN                  ${response}

Update overlay request
    [Documentation]    Update an existing overlay.
    ...
    ...    Args:
    ...    overlay_id (str): UUID of the overlay to update
    ...    overlay_file (str): Optional path to updated YAML overlay file
    ...    chart_id (str): Optional new chart ID
    ...    canonical_name (str): Optional new canonical name
    ...
    ...    Returns:
    ...    response: API response containing the updated overlay
    [Arguments]             ${overlay_id}           ${overlay_file}=${None}     ${chart_id}=${None}     ${canonical_name}=${None}    ${expected_status}=any
    ${data}=                Create Dictionary
    &{files}=               Create Dictionary

    IF    $overlay_file is not None
        ${overlay_content}=     Get Binary File         ${overlay_file}
        @{overlay}=             Create List             overlay.yaml            ${overlay_content}
        Set To Dictionary       ${files}                overlayFile=${overlay}
    END
    IF    $chart_id is not None
        Set To Dictionary       ${data}                 chartId=${chart_id}
    END
    IF    $canonical_name is not None
        Set To Dictionary       ${data}                 canonicalName=${canonical_name}
    END

    ${endpoint}=            Service API Endpoint    aiwb    endpoint=overlays/${overlay_id}
    ${access_token}=        Authorization Token
    &{headers}=             Create Dictionary       Authorization=Bearer ${access_token}

    Log                     PUT ${endpoint}         DEBUG
    ${response}=            PUT                     ${endpoint}             headers=${headers}      data=${data}            files=${files}          expected_status=${expected_status}    verify=${VERIFY_SSL}
    Log                     Update overlay response: status=${response.status_code}                 DEBUG
    RETURN                  ${response}

Delete overlay
    [Documentation]    Delete a specific overlay.
    ...
    ...    Args:
    ...    overlay_id (str): UUID of the overlay to delete
    ...    access_token (str): Token to delete with (optional, defaults to the session's admin token)
    ...
    ...    Returns:
    ...    response: API response (empty on success)
    [Arguments]             ${overlay_id}           ${expected_status}=any    ${access_token}=${None}
    Create API Session      aiwb
    ${endpoint}=            Overlays endpoint
    &{request_options}=     Request options for token    ${access_token}
    Log                     DELETE ${endpoint}/${overlay_id}                 DEBUG
    ${response}=            Safe Delete Request     ${endpoint}/${overlay_id}    expected_status=${expected_status}    &{request_options}
    Log                     Delete overlay response: status=${response.status_code}                 DEBUG
    IF    ${response.status_code} == 204
        Log                     Deleted overlay ${overlay_id}                   INFO
    END
    RETURN                  ${response}
