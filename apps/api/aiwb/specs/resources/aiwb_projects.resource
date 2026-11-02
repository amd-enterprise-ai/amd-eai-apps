# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level AIWB project testing keywords.
...                 Provides business-logic level keywords for testing AIWB project operations.
...                 Uses the low-level API keywords from api/projects.resource to implement
...                 higher-level testing scenarios for project listing, project-scoped
...                 workload stats and metrics, and access control.
Resource            api/projects.resource
Resource            api/cluster.resource
Resource            resources/airm_projects.resource
Resource            aiwb_common.resource
Library             Collections
Library             DateTime


*** Keywords ***
# When-step keywords (used by projects.robot)

AIWB list projects request is sent
    [Documentation]    Sends request to list all projects accessible via the AIWB API.
    ...    Sets: TEST_RESPONSE
    ${response}=    List AIWB Projects    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}

AIWB project workload stats request is sent
    [Documentation]    Sends request to get workload stats for the current project via the AIWB API.
    ...    Sets: TEST_RESPONSE
    ${project}=    Get Project Namespace
    ${response}=    Get AIWB Project Workloads Stats    ${project}    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}

AIWB project workload metrics request is sent
    [Documentation]    Sends request to get paginated project workload metrics via the AIWB API.
    ...    Supports optional page, page_size, and workload_type filter.
    ...    Sets: TEST_RESPONSE
    [Arguments]    ${page}=${None}    ${page_size}=${None}    ${workload_type}=${None}
    ${project}=    Get Project Namespace
    ${response}=    Get AIWB Project Workloads Metrics
    ...    ${project}
    ...    page=${page}
    ...    page_size=${page_size}
    ...    workload_type=${workload_type}
    ...    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}

AIWB project workload metric request is sent for "${metric_name}"
    [Documentation]    Sends request to get a specific project workload metric via the AIWB API
    ...    with a valid date range. Uses a 1-hour window ending at current time.
    ...    Sets: TEST_RESPONSE
    ${project}=    Get Project Namespace
    ${end}=    Get Current Date    time_zone=UTC    result_format=%Y-%m-%dT%H:%M:%SZ
    ${start}=    Evaluate    (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')    modules=datetime
    ${response}=    Get AIWB Project Workloads Metric    ${project}    ${metric_name}    ${start}    ${end}    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}

AIWB project workload metric request is sent with invalid date range
    [Documentation]    Sends a project workload metric request via the AIWB API with an
    ...    intentionally invalid date range.
    ...    Supports three violation types:
    ...    - start_after_end: start is after end
    ...    - start_too_old: start is more than 30 days ago
    ...    - end_in_future: end is in the future
    ...    Sets: TEST_RESPONSE
    [Arguments]    ${violation_type}
    ${project}=    Get Project Namespace

    IF    "${violation_type}" == "start_after_end"
        ${end}=    Evaluate    (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')    modules=datetime
        ${start}=    Evaluate    (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')    modules=datetime
    ELSE IF    "${violation_type}" == "start_too_old"
        ${start}=    Evaluate    (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=31)).strftime('%Y-%m-%dT%H:%M:%SZ')    modules=datetime
        ${end}=    Evaluate    (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')    modules=datetime
    ELSE IF    "${violation_type}" == "end_in_future"
        ${start}=    Evaluate    (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')    modules=datetime
        ${end}=    Evaluate    (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')    modules=datetime
    ELSE
        Fail    Unknown violation type: ${violation_type}. Expected: start_after_end, start_too_old, end_in_future
    END

    ${response}=    Get AIWB Project Workloads Metric    ${project}    gpu_device_utilization    ${start}    ${end}    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}

# When-step keywords (used by cross_service.robot)

AIWB projects are listed
    [Documentation]    Lists all AIWB projects for the current user.
    ...    Sets: TEST_RESPONSE
    ${response}=    List AIWB Projects    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

AIWB project workload stats are requested
    [Documentation]    Requests workload stats for the current project.
    ...    Sets: TEST_RESPONSE
    ${project}=    Get Project Namespace
    ${response}=    Get AIWB Project Workloads Stats    ${project}    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

# Then-step keywords (used by projects.robot)

Response should contain project list
    [Documentation]    Verifies response contains a list of project summaries in the "data" key.
    VAR    ${body}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${body}    data
    ${projects}=    Get From Dictionary    ${body}    data
    ${is_list}=    Evaluate    isinstance($projects, list)
    Should Be True    ${is_list}    msg=Response 'data' field is not a list: ${projects}

Project list should include current project
    [Documentation]    Verifies the project list includes the current project's identifier.
    ${project}=    Get Project Namespace
    VAR    ${body}    ${TEST_RESPONSE.json()}
    ${projects}=    Get From Dictionary    ${body}    data
    ${expected}=    Create Dictionary    id=${project}    name=${project}
    List Should Contain Value    ${projects}    ${expected}
    ...    msg=Current project '${project}' not found in project list: ${projects}

Project list should not include inaccessible project
    [Documentation]    Verifies the project list does NOT include the inaccessible project.
    ...    Requires TEST_UNAUTHORIZED_NAMESPACE to be set.
    VAR    ${body}    ${TEST_RESPONSE.json()}
    ${projects}=    Get From Dictionary    ${body}    data
    ${unexpected}=    Create Dictionary
    ...    id=${TEST_UNAUTHORIZED_NAMESPACE}
    ...    name=${TEST_UNAUTHORIZED_NAMESPACE}
    List Should Not Contain Value    ${projects}    ${unexpected}
    ...    msg=Inaccessible project '${TEST_UNAUTHORIZED_NAMESPACE}' was found in project list

Response should contain workload stats structure
    [Documentation]    Verifies the response has the expected workload stats structure.
    ...    Expected fields: project, total, statusCounts
    VAR    ${body}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${body}    project
    Dictionary Should Contain Key    ${body}    total
    Dictionary Should Contain Key    ${body}    statusCounts
    ${total}=    Get From Dictionary    ${body}    total
    ${total_int}=    Convert To Integer    ${total}
    Should Be True    ${total_int} >= 0    msg=Total count should be non-negative, got ${total_int}

Response should contain paginated metrics structure
    [Documentation]    Verifies the response carries the nested paginated envelope
    ...    (data list plus a pagination object with page, pageSize, total).
    VAR    ${body}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${body}    data
    Dictionary Should Contain Key    ${body}    pagination
    ${pagination}=    Get From Dictionary    ${body}    pagination
    Dictionary Should Contain Key    ${pagination}    page
    Dictionary Should Contain Key    ${pagination}    pageSize
    Dictionary Should Contain Key    ${pagination}    total
    ${data}=    Get From Dictionary    ${body}    data
    ${is_list}=    Evaluate    isinstance($data, list)
    Should Be True    ${is_list}    msg=Response 'data' field is not a list

GPU device metric should report an allocation ceiling of "${expected_gpu_count}"
    [Documentation]    Verifies the GPU device utilization response includes an allocation
    ...    series reflecting the project's assigned GPU quota.
    VAR    ${body}    ${TEST_RESPONSE.json()}
    ${series}=    Get From Dictionary    ${body}    data
    ${allocation_series}=    Evaluate    [s for s in $series if s['metadata']['label'] == 'allocated_gpus']
    Should Not Be Empty    ${allocation_series}    msg=No allocation series found in response: ${series}
    ${values}=    Get From Dictionary    ${allocation_series}[0]    values
    Should Not Be Empty    ${values}    msg=Allocation series has no datapoints
    FOR    ${datapoint}    IN    @{values}
        ${value}=    Get From Dictionary    ${datapoint}    value
        Should Be Equal As Numbers    ${value}    ${expected_gpu_count}
    END

GPU device metric should report cluster capacity as its available ceiling
    [Documentation]    Verifies a project without a dedicated GPU quota reports the
    ...    cluster GPU capacity available for borrowing.
    ${response}=    Get AIWB Cluster Resources    expected_status=200
    ${expected_gpu_count}=    Get From Dictionary    ${response.json()}[data][availableResources]    gpuCount
    GPU device metric should report an allocation ceiling of "${expected_gpu_count}"

# Then-step keywords (used by cross_service.robot)

AIWB project list should contain current project
    [Documentation]    Verifies the project list contains the current project's identifier.
    ...    Requires: TEST_PROJECT (set by project setup keywords), TEST_RESPONSE
    ${project}=    Get Project Namespace
    VAR    ${projects_list}    ${TEST_RESPONSE.json()['data']}
    ${expected}=    Create Dictionary    id=${project}    name=${project}
    List Should Contain Value    ${projects_list}    ${expected}
    ...    msg=Project ${project} not found in AIWB project list

AIWB project workload stats response should contain project
    [Documentation]    Verifies the project workload stats response contains the project identifier.
    ...    Requires: TEST_PROJECT (set by project setup keywords), TEST_RESPONSE
    ${project}=    Get Project Namespace
    VAR    ${response_json}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${response_json}    project
    Should Be Equal As Strings    ${response_json}[project]    ${project}
    ...    msg=Stats response project does not match expected ${project}

AIWB project list should not contain "${project}"
    [Documentation]    Verifies the project list does NOT contain the specified project.
    ...    Requires: TEST_RESPONSE
    VAR    ${projects_list}    ${TEST_RESPONSE.json()['data']}
    ${unexpected}=    Create Dictionary    id=${project}    name=${project}
    List Should Not Contain Value    ${projects_list}    ${unexpected}
    ...    msg=Project ${project} should NOT be in AIWB project list but was found

AIWB project list should not contain unauthorized project
    [Documentation]    Verifies the project list does NOT contain the unauthorized project's identifier.
    ...    Requires: TEST_UNAUTHORIZED_NAMESPACE, TEST_RESPONSE
    Variable Should Exist    ${TEST_UNAUTHORIZED_NAMESPACE}
    ...    msg=No unauthorized project created yet. Use 'A project without user access exists' first.
    AIWB project list should not contain "${TEST_UNAUTHORIZED_NAMESPACE}"

AIWB project workload stats should be denied for "${project}"
    [Documentation]    Verifies that requesting workload stats for the specified project returns 403.
    ${response}=    Get AIWB Project Workloads Stats    ${project}    expected_status=403
    Log    AIWB project workload stats correctly denied for ${project}    INFO

AIWB project workload stats should be denied for unauthorized project
    [Documentation]    Verifies that requesting workload stats for the unauthorized project returns 403.
    ...    Requires: TEST_UNAUTHORIZED_NAMESPACE
    Variable Should Exist    ${TEST_UNAUTHORIZED_NAMESPACE}
    ...    msg=No unauthorized project created yet. Use 'A project without user access exists' first.
    AIWB project workload stats should be denied for "${TEST_UNAUTHORIZED_NAMESPACE}"

The fine-tuned AIM service entry should expose its creator and creation time
    [Documentation]    Verifies the project workload metrics entry for the deployed fine-tuned AIM service
    ...    has non-null creator and creation time, sourced from the K8s AIMService CR
    ...    when no Postgres record exists.
    ...    Requires: TEST_AIM_ID, TEST_RESPONSE
    Should Not Be Equal    ${TEST_AIM_ID}    ${None}    msg=No deployed AIM service ID set
    VAR    ${body}    ${TEST_RESPONSE.json()}
    VAR    ${entries}    ${body}[data]
    VAR    ${matched}    ${None}
    FOR    ${entry}    IN    @{entries}
        IF    $entry["id"] == $TEST_AIM_ID
            VAR    ${matched}    ${entry}
            BREAK
        END
    END
    Should Not Be Equal    ${matched}    ${None}
    ...    msg=Deployed fine-tuned AIM service ${TEST_AIM_ID} not found in project workload metrics
    Dictionary Should Contain Key    ${matched}    createdAt
    Dictionary Should Contain Key    ${matched}    createdBy
    Should Not Be Equal    ${matched}[createdAt]    ${None}
    ...    msg=createdAt is null for fine-tuned AIM service ${TEST_AIM_ID}
    Should Not Be Equal    ${matched}[createdBy]    ${None}
    ...    msg=createdBy is null for fine-tuned AIM service ${TEST_AIM_ID}

# Precondition keywords

A project without user access exists
    [Documentation]    Creates a project WITHOUT adding the current user.
    ...    The user will not have access to this project's namespace.
    ...    Waits for the project to reach Ready state.
    ...    Sets: TEST_UNAUTHORIZED_NAMESPACE
    ...    Preserves: TEST_PROJECT_ID, TEST_PROJECT (restored after creation)

    # Save current project context so we can restore it
    ${saved_project_id}=    Get Variable Value    ${TEST_PROJECT_ID}    ${None}
    ${saved_project}=    Get Variable Value    ${TEST_PROJECT}    ${None}

    # Create project without user access
    Create Project With Validation

    # Capture the unauthorized namespace (namespace = project name)
    ${unauthorized_namespace}=    Get From Dictionary    ${TEST_PROJECT}    name
    Set Test Variable    ${TEST_UNAUTHORIZED_NAMESPACE}    ${unauthorized_namespace}
    Log    Created unauthorized project with namespace: ${unauthorized_namespace}    INFO

    # Restore the original project context
    IF    $saved_project_id != $None
        Set Test Variable    ${TEST_PROJECT_ID}    ${saved_project_id}
        Set Test Variable    ${TEST_PROJECT}    ${saved_project}
    END
