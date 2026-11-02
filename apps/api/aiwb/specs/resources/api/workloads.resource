# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Low-level keywords for AIWB workloads endpoints.
...                 Provides API operations for the polymorphic read-only workloads view.
...                 Mutations (deletion, chat) and capability-specific filters were moved
...                 to capability routers (inference, fine-tuning, workspaces).
...                 Uses project-scoped endpoints: /projects/{project}/workloads/
...                 The project identifier maps 1:1 to the underlying workbench namespace,
...                 so the `namespace` kwarg below holds the project value.
Library             RequestsLibrary
Library             Collections
Resource            resources/api/common.resource


*** Keywords ***
AIWB Workloads endpoint
    [Documentation]    Return the full AIWB workloads endpoint URL
    ...    Pattern: /projects/{project}/workloads
    [Arguments]    ${namespace}
    ${endpoint}=    Service API Endpoint    aiwb    endpoint=projects/${namespace}/workloads
    RETURN    ${endpoint}

Get AIWB workload
    [Documentation]    Retrieve a specific workload by ID via AIWB API
    ...    Uses: GET /projects/{project}/workloads/{workload_id}
    [Arguments]    ${workload_id}    ${namespace}    ${expected_status}=any    ${params}=${None}
    Create api session    aiwb
    ${endpoint}=    AIWB Workloads endpoint    ${namespace}
    Log    GET ${endpoint}/${workload_id}    DEBUG
    IF    $params is not None
        ${response}=    Safe Get Request    ${endpoint}/${workload_id}    params=${params}    expected_status=${expected_status}
    ELSE
        ${response}=    Safe Get Request    ${endpoint}/${workload_id}    expected_status=${expected_status}
    END
    Log    Get AIWB workload response: status=${response.status_code}    DEBUG
    RETURN    ${response}

Get AIWB workloads
    [Documentation]    List workloads in project via AIWB API
    ...    Uses: GET /projects/{project}/workloads
    ...    Optional filters: workloadType, statusFilter
    ...    Optional pagination: page, page_size
    [Arguments]    ${namespace}    ${workload_type}=${None}    ${status_filter}=${None}
    ...    ${page}=${None}    ${page_size}=${None}    ${expected_status}=any
    Create api session    aiwb
    ${params}=    Create Dictionary

    IF    "${workload_type}" != "${None}"    Set To Dictionary    ${params}    workloadType=${workload_type}
    IF    "${status_filter}" != "${None}"    Set To Dictionary    ${params}    statusFilter=${status_filter}
    IF    "${page}" != "${None}"    Set To Dictionary    ${params}    page=${page}
    IF    "${page_size}" != "${None}"    Set To Dictionary    ${params}    pageSize=${page_size}

    ${endpoint}=    AIWB Workloads endpoint    ${namespace}
    Log    GET ${endpoint} with params: ${params}    DEBUG
    ${response}=    Safe Get Request    ${endpoint}    params=${params}    expected_status=${expected_status}
    Log    List AIWB workloads response: status=${response.status_code}    DEBUG
    RETURN    ${response}

Send chat to AIWB workload
    [Documentation]    POST chat to a workload via the legacy workloads route.
    ...    Exists only to verify the route is removed (returns 404/405/422). The real
    ...    chat endpoint lives on the inference capability router.
    ...    Uses: POST /projects/{project}/workloads/{workload_id}/chat
    [Arguments]    ${workload_id}    ${namespace}    ${chat_body}    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=    AIWB Workloads endpoint    ${namespace}
    Log    POST ${endpoint}/${workload_id}/chat    DEBUG
    ${response}=    Safe Post Request    ${endpoint}/${workload_id}/chat
    ...    json=${chat_body}    expected_status=${expected_status}
    Log    Send chat to AIWB workload response: status=${response.status_code}    DEBUG
    RETURN    ${response}

Delete AIWB workload
    [Documentation]    DELETE a workload via the legacy workloads route.
    ...    Exists only to verify the route is removed (returns 404/405/422). Deletions
    ...    now live on capability routers (inference, fine-tuning, workspaces).
    ...    Uses: DELETE /projects/{project}/workloads/{workload_id}
    [Arguments]    ${workload_id}    ${namespace}    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=    AIWB Workloads endpoint    ${namespace}
    Log    DELETE ${endpoint}/${workload_id}    DEBUG
    ${response}=    Safe Delete Request    ${endpoint}/${workload_id}    expected_status=${expected_status}
    Log    Delete AIWB workload response: status=${response.status_code}    DEBUG
    RETURN    ${response}

List Chattable AIWB Workloads
    [Documentation]    GET chattable workloads via the legacy workloads route.
    ...    Exists only to verify the route is removed (returns 404/405/422). Chattable
    ...    filtering now lives on the inference capability router.
    ...    Uses: GET /projects/{project}/workloads/chattable
    [Arguments]    ${namespace}    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=    AIWB Workloads endpoint    ${namespace}
    Log    GET ${endpoint}/chattable    DEBUG
    ${response}=    Safe Get Request    ${endpoint}/chattable    expected_status=${expected_status}
    Log    List Chattable AIWB Workloads response: status=${response.status_code}    DEBUG
    RETURN    ${response}

Get AIWB workload logs
    [Documentation]    Retrieve logs for a workload via AIWB API
    ...    Uses: GET /projects/{project}/workloads/{workload_id}/logs
    ...    Optional params: start, end, limit, direction, level, logType, pageToken
    [Arguments]    ${workload_id}    ${namespace}    ${params}=${None}    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=    AIWB Workloads endpoint    ${namespace}
    Log    GET ${endpoint}/${workload_id}/logs with params: ${params}    DEBUG
    ${response}=    Safe Get Request    ${endpoint}/${workload_id}/logs    params=${params}    expected_status=${expected_status}
    Log    Get AIWB workload logs response: status=${response.status_code}    DEBUG
    RETURN    ${response}
