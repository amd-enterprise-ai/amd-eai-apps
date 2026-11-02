# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Priority class-specific kubectl operations for workload preemption tests.
...
...                 Kaiwo's idle GPU pre-emption only applies to Deployment-backed pods — it creates
...                 GpuWorkload resources that track GPU utilization per pod and pre-empts the owning
...                 Deployment when utilization stays below the namespace threshold after the grace period.
...                 Plain batch Jobs are not tracked by Kaiwo and will never be pre-empted this way.
Resource            resources/common/resource_resolver.resource
Resource            resources/api/common.resource
Library             Process


*** Keywords ***
Submit GPU job with priority class via kubectl
    [Documentation]    Submits a GPU Job directly via kubectl, optionally with a Kueue priority class label.
    ...    When priority_class is None, the priority-class label is omitted from the Job metadata.
    [Arguments]    ${namespace}    ${gpu_count}    ${priority_class}=${None}    ${sleep_seconds}=600

    ${unique_suffix}=    Generate random string    6    [LOWER][NUMBERS]
    IF    $priority_class != $None
        ${job_name}=    Set variable    gpu-job-${priority_class}-${unique_suffix}
        ${priority_label}=    Set variable    ${SPACE}${SPACE}${SPACE}${SPACE}kueue.x-k8s.io/priority-class: ${priority_class}
    ELSE
        ${job_name}=    Set variable    gpu-job-${unique_suffix}
        ${priority_label}=    Set variable    ${EMPTY}
    END

    ${labels_block}=    Catenate    SEPARATOR=\n
    ...    ${SPACE}${SPACE}labels:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}kueue.x-k8s.io/queue-name: ${namespace}
    IF    "${priority_label}" != ""
        ${labels_block}=    Catenate    SEPARATOR=\n    ${labels_block}    ${priority_label}
    END

    ${job_yaml}=    Catenate    SEPARATOR=\n
    ...    apiVersion: batch/v1
    ...    kind: Job
    ...    metadata:
    ...    ${SPACE}${SPACE}name: ${job_name}
    ...    ${SPACE}${SPACE}namespace: ${namespace}
    ...    ${labels_block}
    ...    spec:
    ...    ${SPACE}${SPACE}ttlSecondsAfterFinished: 300
    ...    ${SPACE}${SPACE}template:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}spec:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}restartPolicy: Never
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}containers:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}- name: gpu-test
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}image: busybox:latest
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}command: ["sh", "-c", "echo 'GPU job starting' && sleep ${sleep_seconds} && echo 'Completed'"]
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}resources:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}requests:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}cpu: 100m
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}memory: 128Mi
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}amd.com/gpu: "${gpu_count}"
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}limits:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}cpu: 100m
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}memory: 128Mi
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}amd.com/gpu: "${gpu_count}"

    ${result}=    Run process    kubectl    apply    -f    -    stdin=${job_yaml}
    Should be equal as integers    ${result.rc}    0
    ...    msg=Failed to create Job: ${result.stderr}

    Log    Created Job ${job_name} in namespace ${namespace}    INFO
    RETURN    ${job_name}

Submit GPU deployment via kubectl
    [Documentation]    Submits a GPU Deployment directly via kubectl.
    ...    The container sleeps to hold a GPU with zero utilization — the signal Kaiwo uses
    ...    to identify idle workloads eligible for pre-emption.
    ...    Kaiwo tracks Deployment-backed GPU pods via GpuWorkload resources; batch Jobs are not tracked.
    [Arguments]    ${namespace}    ${gpu_count}=1    ${sleep_seconds}=7200

    ${unique_suffix}=    Generate random string    6    [LOWER][NUMBERS]
    ${deploy_name}=    Set variable    gpu-deploy-${unique_suffix}

    ${deploy_yaml}=    Catenate    SEPARATOR=\n
    ...    apiVersion: apps/v1
    ...    kind: Deployment
    ...    metadata:
    ...    ${SPACE}${SPACE}name: ${deploy_name}
    ...    ${SPACE}${SPACE}namespace: ${namespace}
    ...    spec:
    ...    ${SPACE}${SPACE}replicas: 1
    ...    ${SPACE}${SPACE}selector:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}matchLabels:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}app: ${deploy_name}
    ...    ${SPACE}${SPACE}template:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}metadata:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}labels:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}app: ${deploy_name}
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}spec:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}containers:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}- name: gpu-idle
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}image: busybox:latest
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}command: ["sh", "-c", "sleep ${sleep_seconds}"]
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}resources:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}requests:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}cpu: 100m
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}memory: 128Mi
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}amd.com/gpu: "${gpu_count}"
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}limits:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}cpu: 100m
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}memory: 128Mi
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}amd.com/gpu: "${gpu_count}"

    ${result}=    Run process    kubectl    apply    -f    -    stdin=${deploy_yaml}
    Should be equal as integers    ${result.rc}    0
    ...    msg=Failed to create Deployment: ${result.stderr}

    Log    Created Deployment ${deploy_name} in namespace ${namespace}    INFO
    RETURN    ${deploy_name}

Kubectl deployment should be running
    [Documentation]    Verifies that a kubectl-submitted Deployment has at least one ready pod
    [Arguments]    ${namespace}    ${deploy_name}    ${timeout}=5 min

    Wait until keyword succeeds    ${timeout}    10 sec
    ...    Verify kubectl deployment running    ${namespace}    ${deploy_name}

Verify kubectl deployment running
    [Documentation]    Helper to verify Deployment has at least 1 ready pod
    [Arguments]    ${namespace}    ${deploy_name}

    ${result}=    Run process    kubectl    get    deployment    ${deploy_name}
    ...    -n    ${namespace}
    ...    -o    jsonpath\={.status.readyReplicas}

    ${ready_count}=    Set variable if    "${result.stdout.strip()}" != ""    ${result.stdout.strip()}    0
    Should be true    ${ready_count} > 0
    ...    msg=Deployment ${deploy_name} has no ready pods (readyReplicas=${ready_count})

    Log    Deployment ${deploy_name} has ${ready_count} ready pods    DEBUG

Kubectl job should be pending
    [Documentation]    Verifies that a kubectl-submitted Job has Pending pods
    [Arguments]    ${namespace}    ${job_name}    ${timeout}=2 min

    Wait until keyword succeeds    ${timeout}    5 sec
    ...    Verify kubectl job pending    ${namespace}    ${job_name}

Verify kubectl job pending
    [Documentation]    Helper to verify Job has Pending pods
    [Arguments]    ${namespace}    ${job_name}

    ${result}=    Run process    kubectl    get    pods    -n    ${namespace}    -l    job-name\=${job_name}    -o    jsonpath\={.items[0].status.phase}

    Should be equal as integers    ${result.rc}    0
    ...    msg=Failed to get pod status: ${result.stderr}

    ${phase}=    Set variable    ${result.stdout.strip()}
    Should be equal    ${phase}    Pending
    ...    msg=Expected pod phase Pending, got ${phase}

    Log    Job ${job_name} pod is Pending    DEBUG

Kubectl job should be running
    [Documentation]    Verifies that a kubectl-submitted Job has Running pods
    [Arguments]    ${namespace}    ${job_name}    ${timeout}=2 min

    Wait until keyword succeeds    ${timeout}    5 sec
    ...    Verify kubectl job running    ${namespace}    ${job_name}

Verify kubectl job running
    [Documentation]    Helper to verify Job has Running pods.
    ...    Reads the Job ONCE and derives both the Suspended condition and the pod counts
    ...    from that single snapshot. Reading them with separate kubectl calls lets each
    ...    observe a different moment, which produced self-contradictory diagnostics such
    ...    as "SUSPENDED. Reason: Job resumed" — the status came from while the job was
    ...    suspended and the message from after Kueue had already resumed it.
    [Arguments]    ${namespace}    ${job_name}

    ${result}=    Run process    kubectl    get    job    ${job_name}    -n    ${namespace}    -o    json
    Should be equal as integers    ${result.rc}    0
    ...    msg=Failed to read job ${job_name}: ${result.stderr}
    ${job}=    Evaluate    json.loads($result.stdout)    modules=json

    # The Suspended condition as it stood in this one snapshot, or {} when absent.
    ${suspended}=    Evaluate
    ...    next((c for c in $job.get('status', {}).get('conditions', []) if c.get('type') == 'Suspended'), {})
    IF    $suspended.get('status') == 'True'
        ${why}=    Evaluate    f"{$suspended.get('reason', 'unknown')}: {$suspended.get('message', '')}"
        Fail    Job ${job_name} is SUSPENDED. ${why}
    END

    ${active_count}=    Evaluate    $job.get('status', {}).get('active', 0) or 0
    ${ready_count}=    Evaluate    $job.get('status', {}).get('ready', 0) or 0

    Should be true    ${active_count} > 0 or ${ready_count} > 0
    ...    msg=Job ${job_name} has no active or ready pods (active=${active_count}, ready=${ready_count}); suspended condition=${suspended}

    Log    Job ${job_name} pod is Running    DEBUG

Kubectl job should be suspended
    [Documentation]    Verifies that a kubectl-submitted Job is suspended (preempted)
    [Arguments]    ${namespace}    ${job_name}    ${timeout}=2 min

    Wait until keyword succeeds    ${timeout}    5 sec
    ...    Verify kubectl job suspended    ${namespace}    ${job_name}

Verify kubectl job suspended
    [Documentation]    Helper to verify Job is suspended
    [Arguments]    ${namespace}    ${job_name}

    ${result}=    Run process    kubectl    get    job    -n    ${namespace}    ${job_name}    -o    jsonpath\={.status.conditions[?(@.type\=\=\"Suspended\")].status}

    Should be equal as integers    ${result.rc}    0
    ...    msg=Failed to get job status: ${result.stderr}

    ${suspended_status}=    Set variable    ${result.stdout.strip()}
    Should be equal    ${suspended_status}    True
    ...    msg=Expected Job to be Suspended (status=True), got ${suspended_status}

    Log    Job ${job_name} is Suspended    DEBUG

Verify job has priority class
    [Documentation]    Verifies that a kubectl-submitted Job has the expected Kueue WorkloadPriorityClass label
    [Arguments]    ${namespace}    ${job_name}    ${expected_priority_class}

    ${result}=    Run process    kubectl    get    job    -n    ${namespace}    ${job_name}    -o    jsonpath\={.metadata.labels.kueue\\.x-k8s\\.io/priority-class}

    Should be equal as integers    ${result.rc}    0
    ...    msg=Failed to get job priority class label: ${result.stderr}

    ${actual_priority_class}=    Set variable    ${result.stdout.strip()}
    Should be equal    ${actual_priority_class}    ${expected_priority_class}
    ...    msg=Expected priority class ${expected_priority_class}, got ${actual_priority_class}

    Log    Job ${job_name} has Kueue WorkloadPriorityClass label ${actual_priority_class}    DEBUG
