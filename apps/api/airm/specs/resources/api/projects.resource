# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Keywords for interacting with the Projects API endpoints.
...                 Provides low-level keywords for managing projects through the API.
...                 Includes operations for listing, creating, and deleting projects.
Library             RequestsLibrary
Library             Collections
Resource            resources/api/common.resource


*** Keywords ***
Projects endpoint
    [Documentation]    Returns the full projects endpoint URL
    ${endpoint}=            Service API Endpoint    airm    endpoint=projects
    RETURN                  ${endpoint}

Get projects
    [Documentation]    Get list of all projects for the user's organization
    [Arguments]             ${expected_status}=any
    Create api session    airm
    ${endpoint}=            Projects endpoint
    Log    API Request: GET ${endpoint}    DEBUG
    ${response}=            Safe Get Request        ${endpoint}             expected_status=${expected_status}
    Log    API Response: ${response.status_code} - Body: ${response.text}    DEBUG
    RETURN                  ${response}

Get project
    [Documentation]    Get a specific project by ID
    [Arguments]             ${project_id}           ${expected_status}=any
    Create api session    airm
    ${endpoint}=            Projects endpoint
    Log    API Request: GET ${endpoint}/${project_id}    DEBUG
    ${response}=            Safe Get Request        ${endpoint}/${project_id}                       expected_status=${expected_status}
    Log    API Response: ${response.status_code} - Body: ${response.text}    DEBUG
    RETURN                  ${response}

Create project
    [Documentation]    Create a new project
    [Arguments]             ${project_data}         ${expected_status}=any
    Create api session    airm
    ${endpoint}=            Projects endpoint
    Log    API Request: POST ${endpoint} - Body: ${project_data}    DEBUG
    ${response}=            Safe Post Request       ${endpoint}             json=${project_data}    expected_status=${expected_status}
    Log    API Response: ${response.status_code} - Body: ${response.text}    DEBUG
    RETURN                  ${response}

Delete project
    [Documentation]    Delete a specific project
    [Arguments]             ${project_id}           ${expected_status}=any
    Create api session    airm
    ${endpoint}=            Projects endpoint
    Log    API Request: DELETE ${endpoint}/${project_id}    DEBUG
    ${response}=            Safe Delete Request     ${endpoint}/${project_id}                       expected_status=${expected_status}
    Log    API Response: ${response.status_code}    DEBUG
    RETURN                  ${response}

Update project
    [Documentation]    Update an existing project
    [Arguments]             ${project_id}           ${project_data}         ${expected_status}=any
    Create api session    airm
    ${endpoint}=            Projects endpoint
    Log    API Request: PUT ${endpoint}/${project_id} - Body: ${project_data}    DEBUG
    ${response}=            Safe Put Request        ${endpoint}/${project_id}                       json=${project_data}    expected_status=${expected_status}
    Log    API Response: ${response.status_code} - Body: ${response.text}    DEBUG
    # Log error details to console if request failed
    Run Keyword If    ${response.status_code} >= 400
    ...    Log    ERROR: PUT ${endpoint}/${project_id} returned ${response.status_code}\nResponse: ${response.text}    console=yes
    RETURN                  ${response}

Add users to project
    [Documentation]    Add users to a specific project
    [Arguments]             ${project_id}           ${user_ids}             ${expected_status}=any
    Create api session    airm
    ${endpoint}=            Projects endpoint
    ${user_data}=           Create Dictionary       userIds=${user_ids}
    Log    API Request: POST ${endpoint}/${project_id}/users - Body: ${user_data}    DEBUG
    ${response}=            Safe Post Request       ${endpoint}/${project_id}/users                 json=${user_data}       expected_status=${expected_status}
    Log    API Response: ${response.status_code}    DEBUG
    RETURN                  ${response}

Remove user from project
    [Documentation]    Remove a user from a specific project
    [Arguments]             ${project_id}           ${user_id}              ${expected_status}=any
    Create api session    airm
    ${endpoint}=            Projects endpoint
    Log    API Request: DELETE ${endpoint}/${project_id}/users/${user_id}    DEBUG
    ${response}=            Safe Delete Request     ${endpoint}/${project_id}/users/${user_id}      expected_status=${expected_status}
    Log    API Response: ${response.status_code}    DEBUG
    RETURN                  ${response}

Assign secret to project
    [Documentation]    Assign an organization secret to one project without replacing other assignments.
    [Arguments]    ${project_id}    ${secret_id}    ${expected_status}=204
    Create api session    airm
    ${endpoint}=    Projects endpoint
    ${response}=    Safe Put Request    ${endpoint}/${project_id}/secrets/${secret_id}/assign
    ...    expected_status=${expected_status}
    Log    API Response: ${response.status_code}    DEBUG
    RETURN    ${response}
