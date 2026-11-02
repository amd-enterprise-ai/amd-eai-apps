# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Low-level keywords for AIRM API cluster endpoints.
...                 Provides direct API operation wrappers for the /clusters endpoints.
...                 This is part of the API layer that handles raw HTTP requests/responses.
Library             RequestsLibrary
Library             Collections
Library             OperatingSystem
Resource            resources/api/common.resource


*** Variables ***
${HEADERS_JSON}         Content-Type=application/json
${HEADERS_MULTIPART}    Content-Type=multipart/form-data


*** Keywords ***
Clusters endpoint
    [Documentation]    Return the full cluster endpoint url
    [Arguments]             ${cluster_id}=${None}
    ${base_endpoint}=       Service API Endpoint    airm    endpoint=clusters
    IF    $cluster_id is not None
        RETURN                  ${base_endpoint}/${cluster_id}
    ELSE
        RETURN                  ${base_endpoint}
    END

Create cluster
    [Documentation]    Create a new cluster using the provided data
    ...
    ...    Args:
    ...    cluster_data (dict): Cluster creation parameters including:
    ...    - name: Cluster name
    ...
    ...    Return:
    ...    response: API response containing the created cluster
    ...
    ...    Raise:
    ...    HTTPError: If the API request fails
    [Arguments]             ${cluster_data}         ${expected_status}=any
    Create api session    airm
    ${endpoint}=            Clusters endpoint
    ${response}=            Safe Post Request         ${endpoint}             json=${cluster_data}    expected_status=${expected_status}

    RETURN                  ${response}

Delete cluster
    [Documentation]    Delete a cluster by ID
    [Arguments]             ${cluster_id}           ${expected_status}=any
    Create api session    airm
    ${endpoint}=            Clusters endpoint       ${cluster_id}
    ${response}=            Safe Delete Request       ${endpoint}             expected_status=${expected_status}
    RETURN                  ${response}

Get cluster
    [Documentation]    Get a cluster by ID
    ...
    ...    Args:
    ...    cluster_id: Cluster identifier
    ...
    ...    Return:
    ...    response: API response containing the cluster
    ...
    ...    Raise:
    ...    HTTPError: If the API request fails
    [Arguments]             ${cluster_id}           ${expected_status}=any
    Create api session    airm
    ${endpoint}=            Clusters endpoint       ${cluster_id}
    ${response}=            Safe Get Request          ${endpoint}             expected_status=${expected_status}
    RETURN                  ${response}

Get clusters
    [Documentation]    List all clusters
    ...
    ...    Return:
    ...    response: API response containing the list of clusters
    ...
    ...    Raise:
    ...    HTTPError: If the API request fails
    [Arguments]             ${expected_status}=any
    Create api session    airm
    ${endpoint}=            Clusters endpoint
    ${response}=            Safe Get Request          ${endpoint}             expected_status=${expected_status}
    RETURN                  ${response}
