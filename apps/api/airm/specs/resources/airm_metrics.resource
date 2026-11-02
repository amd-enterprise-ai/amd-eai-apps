# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level metrics testing keywords for AIRM.
...                 Provides business-logic level keywords for testing metrics endpoints
...                 across organization, cluster, project, and workload scopes.
...                 Owns test state (TEST_* variables) and calls API resource keywords.
Resource            api/metrics.resource
Resource            airm_clusters.resource
Resource            airm_projects.resource
Resource            airm_workloads.resource
Library             Collections
Library             DateTime


*** Keywords ***
# =============================================================================
# Shared helpers
# =============================================================================

Get metrics time range
    [Documentation]    Returns a dictionary with ISO-format start/end timestamps for the last 1 hour.

    ${now}=    Get Current Date    time_zone=UTC    result_format=%Y-%m-%dT%H:%M:%SZ
    ${start}=    Subtract Time From Date    ${now}    1 hour    result_format=%Y-%m-%dT%H:%M:%SZ
    ${result}=    Create Dictionary    start=${start}    end=${now}
    RETURN    ${result}

Validate timeseries response structure
    [Documentation]    Validates that a MetricsTimeseries response contains expected fields.
    [Arguments]    ${data}

    Dictionary Should Contain Key    ${data}    data
    Dictionary Should Contain Key    ${data}    range

Validate timeseries series labels
    [Documentation]    Validates that a MetricsTimeseries response contains series entries with
    ...                the expected metadata.label values. Warns and skips if data is empty
    ...                (cluster may have no active metrics).
    [Arguments]    ${data}    @{expected_labels}

    ${series}=    Set Variable    ${data['data']}
    ${series_count}=    Get Length    ${series}
    IF    ${series_count} == 0
        Log    No timeseries data returned (cluster may have no active metrics)    WARN
        RETURN
    END

    ${actual_labels}=    Create List
    FOR    ${s}    IN    @{series}
        ${label}=    Set Variable    ${s['metadata']['label']}
        Append To List    ${actual_labels}    ${label}
    END

    FOR    ${expected}    IN    @{expected_labels}
        Should Contain    ${actual_labels}    ${expected}
        ...    msg=Expected series label '${expected}' not found in response labels: ${actual_labels}
    END
    Log    Validated series labels: ${actual_labels}

Validate scalar with range response structure
    [Documentation]    Validates that a MetricsScalarWithRange response contains expected fields.
    [Arguments]    ${data}

    Dictionary Should Contain Key    ${data}    data
    Dictionary Should Contain Key    ${data}    range

Validate workloads with metrics response structure
    [Documentation]    Validates that a WorkloadsWithMetrics response contains data and a
    ...    nested pagination object with page, pageSize, and total.
    [Arguments]    ${data}

    Dictionary Should Contain Key    ${data}    data
    Dictionary Should Contain Key    ${data}    pagination
    VAR    ${pagination}    ${data['pagination']}
    Dictionary Should Contain Key    ${pagination}    page
    Dictionary Should Contain Key    ${pagination}    pageSize
    Dictionary Should Contain Key    ${pagination}    total

Validate GPU device metric response structure
    [Documentation]    Validates that a GpuDeviceSingleMetricResponse contains expected fields.
    [Arguments]    ${data}

    Dictionary Should Contain Key    ${data}    gpuDevices
    Dictionary Should Contain Key    ${data}    range

Validate per-GPU metric structure
    [Documentation]    Validates that a GPU metric response has per-device entries with expected fields.
    [Arguments]    ${metric_data}    ${expected_series_label}

    ${devices}=    Set Variable    ${metric_data['gpuDevices']}
    ${device_count}=    Get Length    ${devices}

    IF    ${device_count} == 0
        Log    No GPU device data returned (cluster may have no active metrics)    WARN
        RETURN
    END

    FOR    ${device}    IN    @{devices}
        Should Not Be Empty    ${device['gpuUuid']}    msg=Device missing gpuUuid
        Should Not Be Empty    ${device['gpuId']}    msg=Device missing gpuId
        Should Not Be Empty    ${device['hostname']}    msg=Device missing hostname
        Dictionary Should Contain Key    ${device}    metric
        ${metric}=    Set Variable    ${device['metric']}
        Should Be Equal As Strings    ${metric['seriesLabel']}    ${expected_series_label}
        ...    msg=Expected seriesLabel ${expected_series_label}, got ${metric['seriesLabel']}
        Dictionary Should Contain Key    ${metric}    values
    END

    ${range}=    Set Variable    ${metric_data['range']}
    Should Not Be Empty    ${range['start']}    msg=Range missing start
    Should Not Be Empty    ${range['end']}    msg=Range missing end
    Log    Validated ${device_count} device(s) with series_label=${expected_series_label}

# =============================================================================
# Cluster-level metrics keywords
# =============================================================================

Cluster GPU device utilization is requested
    [Documentation]    Fetches cluster GPU device utilization.
    ...    Requires: TEST_CLUSTER_ID
    ...    Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get cluster GPU device utilization
    ...    ${TEST_CLUSTER_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Cluster workloads metrics are requested
    [Documentation]    Fetches cluster workload metrics list.
    ...    Requires: TEST_CLUSTER_ID, platform administrator access
    ...    Sets: TEST_RESPONSE

    ${response}=    Get cluster workloads metrics
    ...    ${TEST_CLUSTER_ID}
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Response should have valid timeseries structure
    [Documentation]    Validates that TEST_RESPONSE contains a valid timeseries response.
    ...    Requires: TEST_RESPONSE

    ${data}=    Set Variable    ${TEST_RESPONSE.json()}
    Validate timeseries response structure    ${data}

Response should contain GPU device utilization series
    [Documentation]    Validates that the project GPU device utilization response contains
    ...    the expected utilizedGpus and allocatedGpus series labels.
    ...    Requires: TEST_RESPONSE

    ${data}=    Set Variable    ${TEST_RESPONSE.json()}
    Validate timeseries response structure    ${data}
    Validate timeseries series labels    ${data}    utilizedGpus    allocatedGpus

Response should contain GPU memory utilization series
    [Documentation]    Validates that the project GPU memory utilization response contains
    ...    the expected utilizedGpuVram and allocatedGpuVram series labels.
    ...    Requires: TEST_RESPONSE

    ${data}=    Set Variable    ${TEST_RESPONSE.json()}
    Validate timeseries response structure    ${data}
    Validate timeseries series labels    ${data}    utilizedGpuVram    allocatedGpuVram

Response should have valid workloads with metrics structure
    [Documentation]    Validates that TEST_RESPONSE contains a valid paginated workloads response.
    ...    Requires: TEST_RESPONSE

    ${data}=    Set Variable    ${TEST_RESPONSE.json()}
    Validate workloads with metrics response structure    ${data}

Response should have valid scalar with range structure
    [Documentation]    Validates that TEST_RESPONSE contains a valid scalar with range response.
    ...    Requires: TEST_RESPONSE

    ${data}=    Set Variable    ${TEST_RESPONSE.json()}
    Validate scalar with range response structure    ${data}

Response should have valid GPU device metric structure
    [Documentation]    Validates that TEST_RESPONSE contains a valid GPU device metric response.
    ...    Optionally asserts the seriesLabel value on each GPU device entry.
    ...    Requires: TEST_RESPONSE
    [Arguments]    ${expected_series_label}=${None}

    ${data}=    Set Variable    ${TEST_RESPONSE.json()}
    Validate GPU device metric response structure    ${data}
    IF    $expected_series_label is not None
        Validate per-GPU metric structure    ${data}    ${expected_series_label}
    END

Response should have valid workload metrics details
    [Documentation]    Validates that TEST_RESPONSE contains workload info card fields.
    ...    Requires: TEST_RESPONSE

    ${data}=    Set Variable    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${data}    workloadId
    Dictionary Should Contain Key    ${data}    clusterName
    Dictionary Should Contain Key    ${data}    clusterId
    Dictionary Should Contain Key    ${data}    nodesInUse
    Dictionary Should Contain Key    ${data}    gpuDevicesInUse
    Dictionary Should Contain Key    ${data}    createdAt

# =============================================================================
# Project-level metrics keywords
# =============================================================================

Project GPU device utilization is requested
    [Documentation]    Fetches project GPU device utilization.
    ...    Requires: TEST_PROJECT_ID
    ...    Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get project GPU device utilization
    ...    ${TEST_PROJECT_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Project GPU memory utilization is requested
    [Documentation]    Fetches project GPU memory utilization.
    ...    Requires: TEST_PROJECT_ID
    ...    Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get project GPU memory utilization
    ...    ${TEST_PROJECT_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Project workloads metrics are requested
    [Documentation]    Fetches project workload metrics list.
    ...    Requires: TEST_PROJECT_ID
    ...    Sets: TEST_RESPONSE

    ${response}=    Get project workloads metrics
    ...    ${TEST_PROJECT_ID}
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Project average wait time is requested
    [Documentation]    Fetches project average wait time.
    ...    Requires: TEST_PROJECT_ID
    ...    Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get project average wait time
    ...    ${TEST_PROJECT_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Project average GPU idle time is requested
    [Documentation]    Fetches project average GPU idle time.
    ...    Requires: TEST_PROJECT_ID
    ...    Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get project average GPU idle time
    ...    ${TEST_PROJECT_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

# =============================================================================
# Workload-level metrics keywords
# =============================================================================

A workload exists for metrics testing
    [Documentation]    Creates a project and submits a workload for metrics testing.
    ...    Sets: TEST_WORKLOAD_ID, TEST_PROJECT_ID, TEST_PROJECT

    A ready project with user access exists
    Workload is submitted with manifest via AIRM API
    Log    Created workload ${TEST_WORKLOAD_ID} for metrics testing

Workload VRAM utilization is requested
    [Documentation]    Fetches workload VRAM utilization.
    ...    Requires: TEST_WORKLOAD_ID
    ...    Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get workload VRAM utilization
    ...    ${TEST_WORKLOAD_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Workload GPU utilization is requested
    [Documentation]    Fetches workload GPU utilization.
    ...    Requires: TEST_WORKLOAD_ID
    ...    Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get workload GPU utilization
    ...    ${TEST_WORKLOAD_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Workload power usage is requested
    [Documentation]    Fetches workload power usage.
    ...    Requires: TEST_WORKLOAD_ID
    ...    Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get workload power usage
    ...    ${TEST_WORKLOAD_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Workload metrics details are requested
    [Documentation]    Fetches workload information card details.
    ...    Requires: TEST_WORKLOAD_ID
    ...    Sets: TEST_RESPONSE

    ${response}=    Get workload metrics details
    ...    ${TEST_WORKLOAD_ID}
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Response should contain workload VRAM utilization data
    [Documentation]    Validates that the workload VRAM utilization response contains
    ...    the expected structure and vramUtilizationPct series label on each device entry.
    ...    Requires: TEST_RESPONSE

    Response should have valid GPU device metric structure    expected_series_label=vramUtilizationPct

Response should contain workload GPU utilization data
    [Documentation]    Validates that the workload GPU utilization response contains
    ...    the expected structure and gpuActivityPct series label on each device entry.
    ...    Requires: TEST_RESPONSE

    Response should have valid GPU device metric structure    expected_series_label=gpuActivityPct

Response should contain workload power usage data
    [Documentation]    Validates that the workload power usage response contains
    ...    the expected structure and powerWatts series label on each device entry.
    ...    Requires: TEST_RESPONSE

    Response should have valid GPU device metric structure    expected_series_label=powerWatts
