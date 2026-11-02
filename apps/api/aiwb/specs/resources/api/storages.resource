# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Low-level keywords for AIWB project storage endpoints.
Library             RequestsLibrary
Resource            resources/api/common.resource


*** Keywords ***
AIWB Storages Endpoint
    [Documentation]    Return the storages endpoint URL for a project.
    [Arguments]    ${project}
    ${endpoint}=    Service API Endpoint    aiwb    endpoint=projects/${project}/storages
    RETURN    ${endpoint}

Create AIWB Storage
    [Documentation]    Create a project storage configuration.
    [Arguments]    ${project}    ${body}    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=    AIWB Storages Endpoint    ${project}
    Log    POST ${endpoint} body=${body}    DEBUG
    ${response}=    Safe Post Request    ${endpoint}
    ...    json=${body}
    ...    expected_status=${expected_status}
    Log    Response status: ${response.status_code}    DEBUG
    RETURN    ${response}

List AIWB Storages
    [Documentation]    List project storage configurations, optionally filtered by type.
    [Arguments]    ${project}    ${storage_type}=${None}    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=    AIWB Storages Endpoint    ${project}
    &{params}=    Create Dictionary
    IF    $storage_type is not None
        Set To Dictionary    ${params}    type=${storage_type}
    END
    Log    GET ${endpoint} params=${params}    DEBUG
    ${response}=    Safe Get Request
    ...    ${endpoint}
    ...    params=${params}
    ...    expected_status=${expected_status}
    Log    Response status: ${response.status_code}    DEBUG
    RETURN    ${response}
