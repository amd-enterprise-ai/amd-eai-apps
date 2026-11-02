# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Low-level keywords for AIWB API secrets endpoints.
...                 Provides direct API operation wrappers for the /projects/{project}/secrets endpoints.
...                 This is part of the API layer that handles raw HTTP requests/responses.
Library             RequestsLibrary
Library             Collections
Resource            resources/api/common.resource


*** Keywords ***
AIWB Secrets Endpoint
    [Documentation]    Return the full secrets endpoint URL for a project.
    ...    Pattern: /projects/{project}/secrets
    [Arguments]    ${project}
    ${endpoint}=    Service API Endpoint    aiwb    endpoint=projects/${project}/secrets
    RETURN    ${endpoint}

Create AIWB Secret
    [Documentation]    Create a new secret via AIWB API.
    ...
    ...    Args:
    ...    project (str): Project identifier (workbench namespace name)
    ...    body (dict): Secret creation payload (name, data, useCase)
    ...    expected_status (int/str): Expected HTTP status code
    ...
    ...    Returns:
    ...    response: API response containing the created secret
    [Arguments]    ${project}    ${body}    ${expected_status}=any
    Create api session    aiwb

    ${endpoint}=    AIWB Secrets Endpoint    ${project}

    Log    POST ${endpoint}    DEBUG
    Log    Request body: ${body}    DEBUG

    ${response}=    Safe Post Request    ${endpoint}
    ...    json=${body}
    ...    expected_status=${expected_status}

    Log    Response status: ${response.status_code}    DEBUG

    RETURN    ${response}

List AIWB Secrets
    [Documentation]    List all secrets in a project via AIWB API.
    ...    Optionally filter by useCase query parameter.
    ...    ``page`` and ``page_size`` select a page (API default 1/10, max page size 100).
    ...
    ...    Args:
    ...    project (str): Project identifier (workbench namespace name)
    ...    use_case (str): Optional useCase filter
    ...    page (int): Optional page number to request
    ...    page_size (int): Optional page size to request
    ...    expected_status (int/str): Expected HTTP status code
    ...
    ...    Returns:
    ...    response: API response containing the list of secrets
    [Arguments]    ${project}    ${use_case}=${None}    ${page}=${None}
    ...    ${page_size}=${None}    ${expected_status}=any
    Create api session    aiwb

    ${endpoint}=    AIWB Secrets Endpoint    ${project}

    &{params}=    Create Dictionary
    IF    $use_case is not None
        Set To Dictionary    ${params}    useCase=${use_case}
    END
    IF    $page is not None    Set To Dictionary    ${params}    page=${page}
    IF    $page_size is not None    Set To Dictionary    ${params}    pageSize=${page_size}

    Log    GET ${endpoint} params=${params}    DEBUG

    ${response}=    Safe Get Request    ${endpoint}
    ...    params=${params}
    ...    expected_status=${expected_status}

    Log    Response status: ${response.status_code}    DEBUG

    RETURN    ${response}

Get AIWB Secret
    [Documentation]    Get a specific secret by name via AIWB API.
    ...
    ...    Args:
    ...    project (str): Project identifier (workbench namespace name)
    ...    secret_name (str): Name of the secret
    ...    expected_status (int/str): Expected HTTP status code
    ...
    ...    Returns:
    ...    response: API response containing the secret details
    [Arguments]    ${project}    ${secret_name}    ${expected_status}=any
    Create api session    aiwb

    ${endpoint}=    AIWB Secrets Endpoint    ${project}

    Log    GET ${endpoint}/${secret_name}    DEBUG

    ${response}=    Safe Get Request    ${endpoint}/${secret_name}
    ...    expected_status=${expected_status}

    Log    Response status: ${response.status_code}    DEBUG

    RETURN    ${response}

Delete AIWB Secret
    [Documentation]    Delete a secret by name via AIWB API.
    ...
    ...    Args:
    ...    project (str): Project identifier (workbench namespace name)
    ...    secret_name (str): Name of the secret to delete
    ...    expected_status (int/str): Expected HTTP status code
    ...
    ...    Returns:
    ...    response: API response (204 No Content on success)
    [Arguments]    ${project}    ${secret_name}    ${expected_status}=any
    Create api session    aiwb

    ${endpoint}=    AIWB Secrets Endpoint    ${project}

    Log    DELETE ${endpoint}/${secret_name}    DEBUG

    ${response}=    Safe Delete Request    ${endpoint}/${secret_name}
    ...    expected_status=${expected_status}

    Log    Response status: ${response.status_code}    DEBUG

    RETURN    ${response}
