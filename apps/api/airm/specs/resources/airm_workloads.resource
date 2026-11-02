# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level workload testing keywords for AIRM.
...                 Provides business-logic level keywords for testing workload operations.
...                 Uses low-level kubectl and API keywords to implement higher-level testing scenarios.
Resource            kubectl_workloads.resource
Resource            kubectl_verification.resource
Resource            kubectl_priority_class.resource
Resource            api/workloads.resource
Resource            resources/api/common.resource
Resource            airm_projects.resource
Resource            airm_clusters.resource
Resource            common/airm_resource_cleanup.resource
Resource            resources/common/resource_lifecycle.resource
Resource            resources/common/resource_resolver.resource
Library             Collections
Library             String
Library             BuiltIn
Library             OperatingSystem


*** Variables ***
# CREATED_WORKLOAD_IDS is lazy-initialized by Track Workload For Cleanup
@{CREATED_HELM_RELEASES}        # List to track helm releases for cleanup
${TEST_WORKLOAD_RELEASE_NAME}   ${EMPTY}
${TEST_WORKLOAD_ID}             ${EMPTY}


*** Keywords ***
Initialize Workload Tracking
    [Documentation]    Initializes helm release tracking list.
    ...    Workload IDs are lazy-initialized by Track Workload For Cleanup.
    @{empty_releases}=    Create List
    Set Suite Variable    ${CREATED_HELM_RELEASES}    ${empty_releases}
    Log    Helm release tracking initialized    DEBUG

# Given keywords - Setup and data preparation

A simple test workload is prepared
    [Documentation]    Prepares a simple test workload configuration.
    ...    Optional sleep_duration overrides the default 10s sleep in the job.
    ...    Returns: config dict with release_name, chart_path, type, and optional sleep_duration.
    [Arguments]    ${sleep_duration}=${NONE}
    ${unique_suffix}=    Generate Random String    6    [LOWER][NUMBERS]
    ${config}=    Create Dictionary
    ...    release_name=test-job-${unique_suffix}
    ...    chart_path=${CURDIR}/../test_workloads/simple-job
    ...    type=simple-job
    IF    $sleep_duration is not None
        Set To Dictionary    ${config}    sleep_duration=${sleep_duration}
    END
    RETURN    ${config}

A long-running workload is prepared
    [Documentation]    Prepares a long-running test workload configuration.
    ...    Returns: config dict with release_name, chart_path, type, and sleep_duration.
    ${unique_suffix}=    Generate Random String    6    [LOWER][NUMBERS]
    ${config}=    Create Dictionary
    ...    release_name=test-longrun-${unique_suffix}
    ...    chart_path=${CURDIR}/../test_workloads/long-running
    ...    type=long-running
    ...    sleep_duration=300
    RETURN    ${config}

A failing workload is prepared
    [Documentation]    Prepares a workload that will fail intentionally.
    ...    Returns: config dict with release_name, chart_path, and type.
    ${unique_suffix}=    Generate Random String    6    [LOWER][NUMBERS]
    ${config}=    Create Dictionary
    ...    release_name=test-fail-${unique_suffix}
    ...    chart_path=${CURDIR}/../test_workloads/failing-job
    ...    type=failing-job
    RETURN    ${config}

A GPU workload is prepared
    [Documentation]    Prepares a GPU test workload configuration.
    ...    Returns: config dict with release_name, chart_path, type, and gpu_count.
    [Arguments]    ${gpu_count}=2
    ${unique_suffix}=    Generate Random String    6    [LOWER][NUMBERS]
    ${config}=    Create Dictionary
    ...    release_name=test-gpu-${unique_suffix}
    ...    chart_path=${CURDIR}/../test_workloads/gpu-job
    ...    type=gpu-job
    ...    gpu_count=${gpu_count}
    RETURN    ${config}

# When keywords - Actions

Test workload is submitted via helm
    [Documentation]    Submits a test workload via helm to project namespace.
    ...    Accepts a config dict from a prepare keyword.
    ...    When wait_for_airm is True (default), polls AIRM API until workload appears.
    ...    When False, only submits to K8s without waiting for AIRM discovery.
    ...    Requires: config dict (from prepare keyword), TEST_PROJECT
    ...    Sets: TEST_WORKLOAD_RELEASE_NAME (always), TEST_WORKLOAD_ID (only when wait_for_airm=True)
    [Arguments]    ${config}    ${wait_for_airm}=${TRUE}
    ${chart_path}=    Get From Dictionary    ${config}    chart_path
    ${release_name}=    Get From Dictionary    ${config}    release_name
    ${type}=    Get From Dictionary    ${config}    type

    # Set test variable so downstream verification keywords work
    Set Test Variable    ${TEST_WORKLOAD_RELEASE_NAME}    ${release_name}

    ${values}=    Create Dictionary

    IF    '${type}' == 'gpu-job'
        ${gpu_count}=    Get From Dictionary    ${config}    gpu_count
        Set To Dictionary    ${values}    resources.requests.amd\.com/gpu=${gpu_count}
        Set To Dictionary    ${values}    resources.limits.amd\.com/gpu=${gpu_count}
    ELSE IF    '${type}' == 'cpu-limited'
        ${cpu_limit}=    Get From Dictionary    ${config}    cpu_limit
        Set To Dictionary    ${values}    resources.requests.cpu=${cpu_limit}
        Set To Dictionary    ${values}    resources.limits.cpu=${cpu_limit}
    ELSE IF    '${type}' == 'memory-limited'
        ${memory_limit}=    Get From Dictionary    ${config}    memory_limit
        Set To Dictionary    ${values}    resources.requests.memory=${memory_limit}
        Set To Dictionary    ${values}    resources.limits.memory=${memory_limit}
    END

    # Override sleep duration if specified in config
    ${has_sleep}=    Run Keyword And Return Status
    ...    Dictionary Should Contain Key    ${config}    sleep_duration
    IF    ${has_sleep}
        ${sleep}=    Get From Dictionary    ${config}    sleep_duration
        Set To Dictionary    ${values}    sleepDuration=${sleep}
    END

    ${release_result}=    Install workload via helm
    ...    ${chart_path}
    ...    ${release_name}
    ...    ${TEST_PROJECT}[name]
    ...    ${values}

    Append To List    ${CREATED_HELM_RELEASES}    ${release_name}:::${TEST_PROJECT}[name]
    Log    Submitted workload ${release_name} to namespace ${TEST_PROJECT}[name]    INFO

    IF    ${wait_for_airm}
        Wait Until Keyword Succeeds    2 min    5 sec
        ...    Find workload in AIRM API    ${release_name}
    END

    RETURN    ${TEST_WORKLOAD_ID}

Find workload in AIRM API
    [Documentation]    Find workload by release name in AIRM API (used with polling)
    ...    Matches workloads by display_name field (primary) based on API schema
    [Arguments]    ${release_name}

    Log    Polling for workload ${release_name} in AIRM API    TRACE
    ${response}=    Get workloads    expected_status=200
    ${response_json}=    Set variable    ${response.json()}
    ${workloads}=    Set variable    ${response_json['data']}

    FOR    ${workload}    IN    @{workloads}
        ${workload_id}=    Get From Dictionary    ${workload}    id
        ${display_name}=    Get From Dictionary    ${workload}    displayName    default=${EMPTY}

        # Match by display_name (this is the correct field per API schema)
        IF    '${display_name}' == '${release_name}'
            Set Test Variable    ${TEST_WORKLOAD_ID}    ${workload_id}
            Track Workload For Cleanup    ${workload_id}
            Log    Discovered workload ${release_name} in AIRM API with ID: ${workload_id}    INFO
            RETURN
        END
    END

    FAIL    Workload ${release_name} not found in AIRM API yet

Workload is deleted via kubectl
    [Documentation]    Deletes workload via helm uninstall.
    ...    Only performs the K8s deletion (helm uninstall). AIRM state verification
    ...    is a separate concern — use "workload should not exist in AIRM" if needed.
    ...    Uses TEST_WORKLOAD_RELEASE_NAME by default, or explicit release_name if provided.
    [Arguments]    ${release_name}=${TEST_WORKLOAD_RELEASE_NAME}
    Log    Deleting workload ${release_name} via helm    DEBUG
    ${success}=    Uninstall workload via helm    ${release_name}    ${TEST_PROJECT}[name]

    Should Be True    ${success}    msg=Failed to uninstall helm release
    Log    Deleted workload ${release_name} via kubectl    INFO

Verify workload deleted in AIRM
    [Documentation]    Verify workload is deleted in AIRM API (used with polling)
    Log    Polling for workload ${TEST_WORKLOAD_ID} deletion status    TRACE
    TRY
        ${response}=    Get workload    ${TEST_WORKLOAD_ID}    expected_status=any
        IF    ${response.status_code} == 404
            RETURN
        END
        ${status}=    Set Variable    ${response.json()['status']}
        Should Be Equal    ${status}    Deleted    msg=Workload not deleted yet: ${status}
    EXCEPT
        Log    Workload ${TEST_WORKLOAD_ID} not found (deleted)    DEBUG
    END

Workload is terminated
    [Documentation]    Terminates a running workload by deleting it
    Workload is deleted via kubectl

# Then keywords - Assertions

Workload status in AIRM should be "${expected_status}"
    [Documentation]    Verifies workload status matches expected value
    ...    Polls GET /workloads/{id} with periodic intervals
    Wait For Resource Status    Get workload    ${TEST_WORKLOAD_ID}    ${expected_status}    timeout=1 min    interval=2 sec

Verify workload status in AIRM
    [Documentation]    Helper to verify workload status (used with polling)
    [Arguments]    ${expected_status}    ${workload_id}=${None}

    ${id}=    Set Variable If    '${workload_id}' != '${None}'    ${workload_id}    ${TEST_WORKLOAD_ID}

    Verify Resource Status    Get workload    ${id}    ${expected_status}

Workload status should transition to "${expected_status}"
    [Documentation]    Waits for workload to transition to expected status.
    ...    Default timeout is 90 sec. Use longer timeout for preemption scenarios
    ...    where Kueue rescheduling and AIRM sync add latency.
    [Arguments]    ${workload_id}=${None}    ${timeout}=90 sec

    ${id}=    The workload    id=${workload_id}

    Wait For Resource Status    Get workload    ${id}    ${expected_status}    timeout=${timeout}    interval=3 sec

Workload should be preempted
    [Documentation]    Verifies workload was preempted/suspended
    ...    Waits for preemption to occur as it may take time for K8s to react
    [Arguments]    ${workload_id}=${None}    ${timeout}=2 min

    ${id}=    The workload    id=${workload_id}

    # Wait for workload to be preempted - give K8s time to react to quota pressure
    Wait Until Keyword Succeeds    ${timeout}    5 sec
    ...    Verify workload is preempted    ${id}

Verify workload is preempted
    [Documentation]    Helper to verify workload has been preempted
    [Arguments]    ${workload_id}

    ${response}=    Get workload    ${workload_id}    expected_status=200
    ${status}=    Set variable    ${response.json()['status']}
    Log    Checking workload ${workload_id} preemption status: ${status}    DEBUG

    # Preempted workloads should be Pending (waiting for resources)
    Should be true    '${status}' in ['Preempted', 'Suspended', 'Pending']
    ...    msg=Expected workload to be preempted but status is ${status}

Workload should be pending due to quota
    [Documentation]    Verifies workload is pending in AIRM due to quota enforcement
    ...    NOTE: We use AIRM API verification here because the test user doesn't have
    ...    permissions to query K8s resources directly (ResourceQuotas, Pod conditions, etc.)
    ...    The AIRM service monitors K8s quota enforcement and reflects it in workload status

    Wait For Resource Status    Get workload    ${TEST_WORKLOAD_ID}    Pending    timeout=1 min    interval=2 sec

Workload should exist in AIRM
    [Documentation]    Verifies workload exists in AIRM API
    ...    First discovers the workload by release name, then verifies it exists
    ...    NOTE: Extended timeout to allow for AIRM auto-discovery latency
    [Arguments]    ${workload_id}=${None}

    Wait Until Keyword Succeeds    3 min    1 sec
    ...    Find workload in AIRM API    ${TEST_WORKLOAD_RELEASE_NAME}
    Wait Until Keyword Succeeds    1 min    2 sec
    ...    Verify workload exists    ${workload_id}

Verify workload exists
    [Documentation]    Helper to verify workload exists (used with polling)
    [Arguments]    ${workload_id}=${None}

    ${id}=    The workload    id=${workload_id}

    Log    Polling for workload ${id} existence    TRACE
    ${response}=    Get workload    ${id}    expected_status=200
    Dictionary Should Contain Key    ${response.json()}    id
    Dictionary Should Contain Key    ${response.json()}    status
    Log    Verified workload ${id} exists    DEBUG

Workload should be displayed under the deployed name
    [Documentation]    The auto-discovered workload must appear under the name the user
    ...    deployed (the Helm release / Deployment name), never a hash-suffixed ReplicaSet or
    ...    Pod name generated by Kubernetes. Discovery messages for a Deployment and its
    ...    children race, so this asserts the display name converges on the owning name.
    ...    Uses TEST_WORKLOAD_ID and TEST_WORKLOAD_RELEASE_NAME.
    ${id}=    The workload
    ${response}=    Get workload    ${id}    expected_status=200
    ${display_name}=    Get From Dictionary    ${response.json()}    displayName
    Should Be Equal    ${display_name}    ${TEST_WORKLOAD_RELEASE_NAME}
    ...    msg=Workload shown as ${display_name}, expected the deployed name ${TEST_WORKLOAD_RELEASE_NAME}

Workload should not exist in AIRM
    [Documentation]    Verifies workload does not exist in AIRM API
    Wait For Resource Deletion    Get workload    ${TEST_WORKLOAD_ID}    timeout=1 min    interval=2 sec
    Log    Verified workload ${TEST_WORKLOAD_ID} does not exist    INFO

Verify workload not found
    [Documentation]    Helper to verify workload doesn't exist (used with polling)
    Resource Should Not Exist    Get workload    ${TEST_WORKLOAD_ID}

# Cleanup keywords
# Clean Up All Created Workloads is defined in airm_resource_cleanup.resource
#     ${workload_count}=    Get Length    ${CREATED_WORKLOAD_IDS}
#     ${release_count}=    Get Length    ${CREATED_HELM_RELEASES}
#
#     Log    Cleaning up ${release_count} helm releases and ${workload_count} AIRM workloads    INFO
#
#     FOR    ${release_info}    IN    @{CREATED_HELM_RELEASES}
#         ${parts}=    Split String    ${release_info}    :::
#         ${release_name}=    Get From List    ${parts}    0
#         ${namespace}=    Get From List    ${parts}    1
#
#         TRY
#             Log    Deleting helm release ${release_name} in namespace ${namespace}    DEBUG
#             Uninstall workload via helm    ${release_name}    ${namespace}
#             Log    Deleted helm release ${release_name}    INFO
#         EXCEPT    AS    ${error}
#             Log    Failed to delete helm release ${release_name}: ${error}    WARN
#         END
#     END
#
#     Clean Up All Created Workloads Via API
#
#     @{empty_releases}=    Create List
#     Set Suite Variable    ${CREATED_HELM_RELEASES}    ${empty_releases}
#     Log    Workload cleanup complete    INFO

# Kubernetes Resource Verification Keywords

Job should exist in project namespace
    [Documentation]    Verifies that the workload Job exists in the project namespace
    ...    This is the PRIMARY verification - the actual K8s resource must exist
    ${job}=    Job should exist in namespace    ${TEST_WORKLOAD_RELEASE_NAME}    ${TEST_PROJECT}[name]
    Log    Job ${TEST_WORKLOAD_RELEASE_NAME} exists in namespace ${TEST_PROJECT}[name]    INFO
    RETURN    ${job}

Deployment should exist in project namespace
    [Documentation]    Verifies that the workload Deployment exists in the project namespace
    ${deployment}=    Deployment should exist in namespace    ${TEST_WORKLOAD_RELEASE_NAME}    ${TEST_PROJECT}[name]
    Log    Deployment ${TEST_WORKLOAD_RELEASE_NAME} exists in namespace ${TEST_PROJECT}[name]    INFO
    RETURN    ${deployment}

Pod should exist for Job
    [Documentation]    Verifies that a Pod was created for the Job
    ${pod}=    kubectl_verification.Pod should exist for Job    ${TEST_WORKLOAD_RELEASE_NAME}    ${TEST_PROJECT}[name]
    Log    Pod exists for Job ${TEST_WORKLOAD_RELEASE_NAME}    INFO
    RETURN    ${pod}

Pod should exist for Deployment
    [Documentation]    Verifies that Pods were created for the Deployment
    ${pods}=    kubectl_verification.Pods should exist for Deployment    ${TEST_WORKLOAD_RELEASE_NAME}    ${TEST_PROJECT}[name]
    ${count}=    Get Length    ${pods}
    Log    ${count} Pod(s) exist for Deployment ${TEST_WORKLOAD_RELEASE_NAME}    INFO
    RETURN    ${pods}

Pod should transition to "Running"
    [Documentation]    Waits for the Job Pod to reach Running status
    kubectl_verification.Wait for Pod status    ${TEST_WORKLOAD_RELEASE_NAME}    ${TEST_PROJECT}[name]    Running    timeout=2 min
    Log    Pod for Job ${TEST_WORKLOAD_RELEASE_NAME} is Running    INFO

Deployment Pod should transition to "Running"
    [Documentation]    Waits for at least one Deployment Pod to reach Running status
    kubectl_verification.Wait for Deployment Pod status    ${TEST_WORKLOAD_RELEASE_NAME}    ${TEST_PROJECT}[name]    Running    timeout=2 min
    Log    At least one Pod for Deployment ${TEST_WORKLOAD_RELEASE_NAME} is Running    INFO

Job should complete successfully
    [Documentation]    Waits for the Job to complete successfully
    kubectl_verification.Job should complete successfully    ${TEST_WORKLOAD_RELEASE_NAME}    ${TEST_PROJECT}[name]    timeout=5 min
    Log    Job ${TEST_WORKLOAD_RELEASE_NAME} completed successfully    INFO

Job should fail
    [Documentation]    Waits for the Job to fail
    kubectl_verification.Job should fail    ${TEST_WORKLOAD_RELEASE_NAME}    ${TEST_PROJECT}[name]    timeout=5 min
    Log    Job ${TEST_WORKLOAD_RELEASE_NAME} failed as expected    INFO

Verify GPU capacity is exhausted
    [Documentation]    Verifies that some jobs are Suspended, indicating GPU capacity is full
    ...    This is critical for preemption testing - we need resource pressure
    [Arguments]    @{job_names}

    ${suspended_count}=    Set Variable    ${0}
    ${running_count}=    Set Variable    ${0}
    ${pending_count}=    Set Variable    ${0}

    FOR    ${job_name}    IN    @{job_names}
        ${is_suspended}=    Run Keyword And Return Status
        ...    Verify kubectl job suspended    ${TEST_PROJECT}[name]    ${job_name}
        ${is_running}=    Run Keyword And Return Status
        ...    Verify kubectl job running    ${TEST_PROJECT}[name]    ${job_name}

        IF    ${is_suspended}
            ${suspended_count}=    Evaluate    ${suspended_count} + 1
        ELSE IF    ${is_running}
            ${running_count}=    Evaluate    ${running_count} + 1
        ELSE
            ${pending_count}=    Evaluate    ${pending_count} + 1
        END
    END

    # Capacity is exhausted when at least one job is suspended (can't get resources)
    Should Be True    ${suspended_count} >= 1
    ...    msg=No jobs are suspended yet - capacity not exhausted. Running: ${running_count}, Suspended: ${suspended_count}, Pending: ${pending_count}

    Log    GPU capacity exhausted: ${running_count} running, ${suspended_count} suspended, ${pending_count} pending    INFO

# Unified BDD-style Keywords for Priority Class Testing

Cluster GPU resources are exhausted with workloads
    [Documentation]    Given keyword: Exhausts cluster GPU capacity with workloads of specified priority
    ...    Submits one more single-GPU job than physical cluster GPU count (N+1) so the scheduler cannot
    ...    admit every workload; at least one job stays suspended. That satisfies Verify GPU capacity is exhausted,
    ...    which requires a suspended job and was flaky when the loop only submitted N jobs (all could run).
    ...    Uses cluster GPU capacity to fill the cluster, not just project quota (cohort borrowing).
    [Arguments]    ${priority_class}=low

    # Physical GPU slots in the cluster; submit N+1 single-GPU jobs to force quota pressure.
    ${cluster_gpu_capacity}=    Get cluster GPU capacity
    ${job_target_count}=    Evaluate    int(${cluster_gpu_capacity}) + 1

    @{job_names}=    Create List

    FOR    ${i}    IN RANGE    ${job_target_count}
        ${job_name}=    Submit GPU job with priority class via kubectl
        ...    ${TEST_PROJECT}[name]    ${1}    ${priority_class}
        Append To List    ${job_names}    ${job_name}
        Log    Submitted ${priority_class} priority job ${i+1}/${job_target_count}: ${job_name}    INFO
    END

    # Wait for Kueue to admit jobs until capacity is exhausted
    Wait Until Keyword Succeeds    3 min    5 sec
    ...    Verify GPU capacity is exhausted    @{job_names}

    # Store job names for later verification
    IF    "${priority_class}" == "low"
        Set test variable    @{TEST_LOW_PRIORITY_JOB_NAMES}    @{job_names}
    ELSE IF    "${priority_class}" == "medium"
        Set test variable    @{TEST_MEDIUM_PRIORITY_JOB_NAMES}    @{job_names}
    ELSE IF    "${priority_class}" == "high"
        Set test variable    @{TEST_HIGH_PRIORITY_JOB_NAMES}    @{job_names}
    END

    Log    Cluster GPU resources exhausted (${job_target_count} ${priority_class} priority jobs, ${cluster_gpu_capacity} GPU slots)    INFO

A "${priority_class}" priority GPU workload is submitted
    [Documentation]    When keyword: Submits a GPU workload with specified priority class.
    ...    Returns immediately after kubectl job creation.
    ...    Subsequent verification steps poll for job status and preemption.
    ...    Returns the job name for explicit variable passing.
    [Arguments]    ${gpu_count}=1

    ${job_name}=    Submit GPU job with priority class via kubectl
    ...    ${TEST_PROJECT}[name]    ${gpu_count}    ${priority_class}

    # Store job name in both generic and priority-specific variables
    Set test variable    ${TEST_JOB_NAME}    ${job_name}
    IF    "${priority_class}" == "low"
        Set test variable    ${TEST_LOW_PRIORITY_JOB_NAME}    ${job_name}
    ELSE IF    "${priority_class}" == "medium"
        Set test variable    ${TEST_MEDIUM_PRIORITY_JOB_NAME}    ${job_name}
    ELSE IF    "${priority_class}" == "high"
        Set test variable    ${TEST_HIGH_PRIORITY_JOB_NAME}    ${job_name}
    END

    Log    Submitted ${priority_class} priority workload: ${job_name}    INFO
    RETURN    ${job_name}

Workload should be running
    [Documentation]    Then keyword: Waits for a workload to reach Running state
    ...    Uses TEST_JOB_NAME by default, or explicit job_name if provided
    [Arguments]    ${job_name}=${None}

    ${resolved_name}=    Set Variable If    $job_name != $None    ${job_name}    ${TEST_JOB_NAME}
    Kubectl job should be running    ${TEST_PROJECT}[name]    ${resolved_name}
    Log    Workload ${resolved_name} is running    INFO

At least one "${priority_class}" priority workload should be suspended
    [Documentation]    Then keyword: Verifies at least one workload of specified priority was preempted
    ...    Generic suspension check that works with any priority class

    # Get the job names list for this priority class
    ${job_names_var}=    Set Variable    TEST_${priority_class.upper()}_PRIORITY_JOB_NAMES
    ${job_names}=    Get Variable Value    \${${job_names_var}}    ${None}

    IF    ${job_names} is ${None}
        Fail    No ${priority_class} priority workloads found. TEST variable ${job_names_var} not set.
    END

    ${suspended_count}=    Set Variable    ${0}

    FOR    ${job_name}    IN    @{job_names}
        ${is_suspended}=    Run Keyword And Return Status
        ...    Verify kubectl job suspended    ${TEST_PROJECT}[name]    ${job_name}
        IF    ${is_suspended}
            ${suspended_count}=    Evaluate    ${suspended_count} + 1
            Log    Job ${job_name} is suspended (preempted)    INFO
        END
    END

    Should Be True    ${suspended_count} >= 1
    ...    msg=Expected at least one ${priority_class} priority suspended job (indicating preemption), but found ${suspended_count}
    Log    ${suspended_count} ${priority_class} priority workload(s) suspended - preemption verified    INFO

Workload should be pending or suspended
    [Documentation]    Then keyword: Verifies that a workload is either Pending or Suspended
    ...    Uses TEST_JOB_NAME by default, or explicit job_name if provided
    ...    This is used for negative preemption tests where we verify a workload did NOT get admitted
    [Arguments]    ${job_name}=${None}

    ${resolved_name}=    Set Variable If    $job_name != $None    ${job_name}    ${TEST_JOB_NAME}

    # The job should be either pending (not admitted) or suspended (admitted but no resources)
    # Both states indicate the workload is not running
    ${is_pending}=    Run Keyword And Return Status
    ...    Verify kubectl job pending    ${TEST_PROJECT}[name]    ${resolved_name}
    ${is_suspended}=    Run Keyword And Return Status
    ...    Verify kubectl job suspended    ${TEST_PROJECT}[name]    ${resolved_name}

    Should Be True    ${is_pending} or ${is_suspended}
    ...    msg=Expected job ${job_name} to be Pending or Suspended, but it's neither (possibly Running)

    IF    ${is_pending}
        Log    Workload ${job_name} is Pending (not admitted)    INFO
    ELSE
        Log    Workload ${job_name} is Suspended (admitted but no resources)    INFO
    END

None of the initial "${priority_class}" priority workloads should be newly suspended
    [Documentation]    Then keyword: Verifies that none of the initial workloads were preempted by a new workload
    ...    This is for negative tests - verifying same-priority workloads don't preempt each other
    ...    NOTE: This checks that jobs are NOT suspended. Some jobs may have been suspended initially
    ...    when cluster was exhausted, but we verify no NEW suspensions occurred.

    # Get the job names list for this priority class (created by "Cluster GPU resources are exhausted")
    ${job_names_var}=    Set Variable    TEST_${priority_class.upper()}_PRIORITY_JOB_NAMES
    ${job_names}=    Get Variable Value    \${${job_names_var}}    ${None}

    IF    ${job_names} is ${None}
        Fail    No ${priority_class} priority workloads found. TEST variable ${job_names_var} not set.
    END

    # Count how many jobs are currently running vs suspended
    ${running_count}=    Set Variable    ${0}
    ${suspended_count}=    Set Variable    ${0}

    FOR    ${job_name}    IN    @{job_names}
        ${is_running}=    Run Keyword And Return Status
        ...    Verify kubectl job running    ${TEST_PROJECT}[name]    ${job_name}
        ${is_suspended}=    Run Keyword And Return Status
        ...    Verify kubectl job suspended    ${TEST_PROJECT}[name]    ${job_name}

        IF    ${is_running}
            ${running_count}=    Evaluate    ${running_count} + 1
            Log    Job ${job_name} is Running    TRACE
        ELSE IF    ${is_suspended}
            ${suspended_count}=    Evaluate    ${suspended_count} + 1
            Log    Job ${job_name} is Suspended    TRACE
        ELSE
            Log    Job ${job_name} is in an unknown state (not Running, not Suspended)    WARN
        END
    END

    # Verify: The distribution of running vs suspended jobs should match what we saw when cluster was exhausted
    # We can't check exact numbers without tracking initial state, but we can verify SOME jobs are still running
    # If a same-priority job preempted others, ALL initial jobs would be suspended (or fewer running than before)
    Should Be True    ${running_count} > 0
    ...    msg=Expected some ${priority_class} priority jobs to still be running (FIFO order preserved), but found 0 running and ${suspended_count} suspended. This suggests preemption may have occurred.

    Log    Verified ${priority_class} priority workloads: ${running_count} running, ${suspended_count} suspended. No new preemption detected.    INFO

# API-based workload keywords (merged from former catalog_workloads.resource)

Workload is submitted with manifest via AIRM API
    [Documentation]    Submits a workload via AIRM API using POST /workloads with direct manifest.
    ...    This is the preferred method for testing workload submission without charts.
    ...    Requires: TEST_PROJECT_ID
    ...    Sets: TEST_WORKLOAD_ID, TEST_RESPONSE
    [Arguments]             ${manifest_path}=${CURDIR}/../test_data/manifests/test-deployment.yaml    ${display_name}=test-workload    ${workload_type}=CUSTOM

    # Verify project exists
    Should Not Be Equal     ${TEST_PROJECT_ID}    ${None}    msg=TEST_PROJECT_ID not set. Create a project first.

    # Submit workload with manifest
    ${response}=            Submit workload with manifest
    ...                     manifest_path=${manifest_path}
    ...                     project_id=${TEST_PROJECT_ID}
    ...                     display_name=${display_name}
    ...                     workload_type=${workload_type}
    ...                     expected_status=200

    # Verify creation succeeded
    Should Be Equal As Integers    ${response.status_code}    200
    ...    msg=Failed to submit workload with manifest. Status: ${response.status_code}, Body: ${response.text}

    ${json}=                Set Variable    ${response.json()}
    Dictionary Should Contain Key    ${json}    id    msg=Workload response missing 'id' field
    ${workload_id}=         Get From Dictionary    ${json}    id
    Set Test Variable       ${TEST_WORKLOAD_ID}    ${workload_id}
    Set Test Variable       ${TEST_RESPONSE}    ${response}

    Track Workload For Cleanup    ${workload_id}

    Log                     Submitted workload with manifest via AIRM API, ID: ${workload_id}    INFO
    RETURN    ${response}

Workload should be visible via API
    [Documentation]    Verifies that the workload is visible via GET /workloads/{id}
    ...    Polls for workload to appear in database to handle async operations
    Should Not Be Equal     ${TEST_WORKLOAD_ID}    ${None}    msg=TEST_WORKLOAD_ID not set. Submit workload first.

    Wait Until Keyword Succeeds    10 sec    1 sec
    ...    Workload is in database

    Log                     Workload ${TEST_WORKLOAD_ID} is visible via API    INFO

Workload is in database
    [Documentation]    Verifies workload exists in database via API
    ...    Used with polling to wait for async workload creation
    Log                     Polling for workload ${TEST_WORKLOAD_ID} in database    TRACE
    ${response}=            Get workload    ${TEST_WORKLOAD_ID}    expected_status=200
    Set Test Variable       ${TEST_RESPONSE}    ${response}

Workload should have valid ID and status via API
    [Documentation]    Verifies workload response contains valid id and status fields
    Should Not Be Equal     ${TEST_RESPONSE}    ${None}    msg=Response not set. Call 'workload should be visible via API' first.

    ${json}=                Set Variable    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    id
    Dictionary Should Contain Key    ${json}    status

    ${workload_id}=         Get From Dictionary    ${json}    id
    ${status}=              Get From Dictionary    ${json}    status

    Log                     Workload has valid ID: ${workload_id}, Status: ${status}    INFO

"${count}" workloads should be visible via API list endpoint
    [Documentation]    Verifies that the specified number of workloads are visible via GET /workloads in the current project
    ...    Uses TEST_PROJECT_ID to filter workloads from this test only
    ${count_int}=           Convert To Integer    ${count}

    # Get all workloads and count those in current project
    ${response}=            Get workloads    expected_status=200
    ${all_workloads}=       Set Variable    ${response.json()['data']}

    # Count workloads belonging to current project
    ${project_workload_count}=    Set Variable    ${0}
    FOR    ${workload}    IN    @{all_workloads}
        IF    "${workload['projectId']}" == "${TEST_PROJECT_ID}"
            ${project_workload_count}=    Evaluate    ${project_workload_count} + 1
        END
    END

    Should Be Equal As Integers    ${project_workload_count}    ${count_int}
    ...    msg=Expected ${count_int} workloads in project ${TEST_PROJECT_ID}, found ${project_workload_count}

    Log                     Found ${project_workload_count} workloads in project ${TEST_PROJECT_ID} via API    INFO

Workload is deleted via AIRM API
    [Documentation]    Deletes the workload via DELETE /workloads/{id}
    Should Not Be Equal     ${TEST_WORKLOAD_ID}    ${None}    msg=TEST_WORKLOAD_ID not set. Submit workload first.

    ${response}=            Delete workload    ${TEST_WORKLOAD_ID}    expected_status=204

    Log                     Deleted workload ${TEST_WORKLOAD_ID} via AIRM API    INFO

Workload should report a deletion status via API
    [Documentation]    Waits until an out-of-band workload deletion reaches AIRM's soft-delete state.
    ...    AIRM reconciles helm/kubectl deletion asynchronously, so a single immediate GET races
    ...    the reconciler. Poll until the workload reports Deleting or Deleted.
    Should Not Be Equal    ${TEST_WORKLOAD_ID}    ${None}    msg=TEST_WORKLOAD_ID not set.
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Workload status should be Deleting or Deleted via API

Workload status should be Deleting or Deleted via API
    [Documentation]    One polling attempt for "Workload should report a deletion status via API".
    ${response}=    Get workload    ${TEST_WORKLOAD_ID}    expected_status=200
    VAR    ${json}    ${response.json()}
    Dictionary Should Contain Key    ${json}    status
    ${status}=    Get From Dictionary    ${json}    status
    Should Match Regexp    ${status}    ^(Deleting|Deleted)$
    ...    msg=Expected workload status to be Deleting or Deleted, but got ${status}
    Log    Workload ${TEST_WORKLOAD_ID} has deletion status: ${status}    INFO

# Workload Status Verification Keywords (API-based)

Workload status in response should be "${expected_status}"
    [Documentation]    Verifies the workload response has the expected status
    ...    Checks the response (either from creation or from a GET request)
    ${json}=                Set Variable    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${json}    status
    ${status}=              Get From Dictionary    ${json}    status
    Should Be Equal         ${status}    ${expected_status}
    ...    msg=Expected workload status to be ${expected_status}, but got ${status}
    Log                     Workload status: ${status}    INFO

Workload should transition to "${expected_status}"
    [Documentation]    Waits for workload to transition to expected status
    ...    Polls the workload endpoint until status becomes expected value.
    ...    Fetches fresh state after success so ${TEST_RESPONSE} is up to date.
    Wait For Resource Status    Get workload    ${TEST_WORKLOAD_ID}    ${expected_status}
    ${response}=    Get workload    ${TEST_WORKLOAD_ID}    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Verify workload has status "${expected_status}"
    [Documentation]    Helper keyword to verify workload status (used with polling)
    Verify Resource Status    Get workload    ${TEST_WORKLOAD_ID}    ${expected_status}
