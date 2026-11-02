# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Low-level keywords for AIWB API project endpoints.
...                 Provides direct API operation wrappers for the /projects endpoints
...                 (project listing and project-scoped workload stats/metrics).
...                 This is part of the API layer that handles raw HTTP requests/responses.
Library             RequestsLibrary
Library             Collections
Resource            resources/api/common.resource


*** Keywords ***
AIWB Projects Endpoint
    [Documentation]    Return the full projects endpoint URL with optional project and workloads action.
    ...    When ${project} is provided, the URL is built under /projects/{project}/workloads/{action}.
    [Arguments]    ${project}=${None}    ${action}=${None}
    ${base_endpoint}=    Service API Endpoint    aiwb    endpoint=projects
    IF    $project is not None and $action is not None
        RETURN    ${base_endpoint}/${project}/workloads/${action}
    ELSE IF    $project is not None
        RETURN    ${base_endpoint}/${project}
    ELSE
        RETURN    ${base_endpoint}
    END

List AIWB Projects
    [Documentation]    List all projects via AIWB API.
    ...
    ...    Args:
    ...    expected_status (int/str): Expected HTTP status code
    ...
    ...    Returns:
    ...    response: API response containing project summaries under the "data" key
    [Arguments]    ${expected_status}=any
    Create api session    aiwb

    ${endpoint}=    AIWB Projects Endpoint

    Log    GET ${endpoint}    DEBUG

    ${response}=    Safe Get Request    ${endpoint}
    ...    expected_status=${expected_status}

    Log    Response status: ${response.status_code}    DEBUG

    RETURN    ${response}

Get AIWB Project Workloads Stats
    [Documentation]    Get workload stats for a specific project via AIWB API.
    ...
    ...    Args:
    ...    project (str): Project name
    ...    expected_status (int/str): Expected HTTP status code
    ...
    ...    Returns:
    ...    response: API response containing WorkloadStatsCounts
    [Arguments]    ${project}    ${expected_status}=any
    Create api session    aiwb

    ${endpoint}=    AIWB Projects Endpoint    project=${project}    action=stats

    Log    GET ${endpoint}    DEBUG

    ${response}=    Safe Get Request    ${endpoint}
    ...    expected_status=${expected_status}

    Log    Response status: ${response.status_code}    DEBUG

    RETURN    ${response}

Get AIWB Project Workloads Metrics
    [Documentation]    Get paginated workload metrics for a project via AIWB API.
    ...
    ...    Args:
    ...    project (str): Project name
    ...    page (int): Page number (1-indexed)
    ...    page_size (int): Items per page
    ...    workload_type (str): Filter by workload type
    ...    status_filter (str): Filter by status
    ...    sort_by (str): Field to sort by
    ...    sort_order (str): Sort direction (asc/desc)
    ...    expected_status (int/str): Expected HTTP status code
    ...
    ...    Returns:
    ...    response: API response containing WorkloadMetricsListPaginated
    [Arguments]    ${project}    ${page}=${None}    ${page_size}=${None}    ${workload_type}=${None}    ${status_filter}=${None}    ${sort_by}=${None}    ${sort_order}=${None}    ${expected_status}=any
    Create api session    aiwb

    ${params}=    Create Dictionary
    IF    $page is not None             Set To Dictionary    ${params}    page=${page}
    IF    $page_size is not None        Set To Dictionary    ${params}    pageSize=${page_size}
    IF    $workload_type is not None    Set To Dictionary    ${params}    workloadType=${workload_type}
    IF    $status_filter is not None    Set To Dictionary    ${params}    statusFilter=${status_filter}
    IF    $sort_by is not None          Set To Dictionary    ${params}    sortBy=${sort_by}
    IF    $sort_order is not None       Set To Dictionary    ${params}    sortOrder=${sort_order}

    ${endpoint}=    AIWB Projects Endpoint    project=${project}    action=metrics

    Log    GET ${endpoint} with params: ${params}    DEBUG

    ${response}=    Safe Get Request    ${endpoint}    params=${params}
    ...    expected_status=${expected_status}

    Log    Response status: ${response.status_code}    DEBUG

    RETURN    ${response}

Get AIWB Project Workloads Metric
    [Documentation]    Get a specific aggregated metric for a project via AIWB API.
    ...
    ...    Args:
    ...    project (str): Project name
    ...    metric (str): Metric name (e.g., gpu_device_utilization)
    ...    start (str): Start time in ISO 8601 format
    ...    end (str): End time in ISO 8601 format
    ...    expected_status (int/str): Expected HTTP status code
    ...
    ...    Returns:
    ...    response: API response containing MetricsTimeseries
    [Arguments]    ${project}    ${metric}    ${start}    ${end}    ${expected_status}=any
    Create api session    aiwb

    ${params}=    Create Dictionary    start=${start}    end=${end}

    ${endpoint}=    AIWB Projects Endpoint    project=${project}    action=metrics/${metric}

    Log    GET ${endpoint} with params: ${params}    DEBUG

    ${response}=    Safe Get Request    ${endpoint}    params=${params}
    ...    expected_status=${expected_status}

    Log    Response status: ${response.status_code}    DEBUG

    RETURN    ${response}
