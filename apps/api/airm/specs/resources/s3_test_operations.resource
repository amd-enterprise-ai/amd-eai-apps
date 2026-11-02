# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       S3 test operations using Kubernetes Jobs.
...                 Provides keywords to perform real S3 read/write/cleanup operations
...                 via Kubernetes Jobs running Python with boto3.
Library             Process
Library             Collections
Library             String
Library             OperatingSystem
Library             StorageCredentials


*** Variables ***
${S3_JOB_TIMEOUT}       60s
${S3_JOB_POLL_INTERVAL}    2s


*** Keywords ***
Submit S3 Writer Job
    [Documentation]    Submit a Kubernetes Job to write data to S3
    ...    This modifies the s3-writer-job.yaml template with actual values
    ...    and submits it to the specified namespace.
    ...
    ...    Arguments:
    ...    - namespace: Kubernetes namespace (project name)
    ...    - storage_config_map_name: Name of the ConfigMap with storage info
    ...    - secret_name: Name of the ExternalSecret with credentials
    ...    - access_key_name: Key name in secret for access key
    ...    - secret_key_name: Key name in secret for secret key
    ...    - test_data_key: S3 object key (e.g., e2e-test-storage-123/file.txt)
    ...    - test_data_content: Content to write
    ...
    ...    Returns: Job name
    [Arguments]    ${namespace}    ${storage_config_map_name}    ${secret_name}    ${access_key_name}    ${secret_key_name}    ${test_data_key}    ${test_data_content}    ${random_suffix}

    ${job_name}=    Set Variable    s3-writer-test-${random_suffix}
    ${manifest_path}=    Set Variable    ${CURDIR}/../test_data/manifests/s3-writer-job.yaml

    # Read the manifest template
    ${manifest}=    Get File    ${manifest_path}

    # Replace placeholders
    ${manifest}=    Replace String    ${manifest}    STORAGE_CONFIG_MAP_NAME    ${storage_config_map_name}
    ${manifest}=    Replace String    ${manifest}    SECRET_NAME_PLACEHOLDER    ${secret_name}
    ${manifest}=    Replace String    ${manifest}    ACCESS_KEY_NAME_PLACEHOLDER    ${access_key_name}
    ${manifest}=    Replace String    ${manifest}    SECRET_KEY_NAME_PLACEHOLDER    ${secret_key_name}
    ${manifest}=    Replace String    ${manifest}    name: s3-writer-test-job    name: ${job_name}
    ${manifest}=    Replace String    ${manifest}    value: "PLACEHOLDER"    value: "${test_data_key}"    count=1
    ${manifest}=    Replace String    ${manifest}    value: "PLACEHOLDER"    value: "${test_data_content}"    count=1

    # Write to temp file
    ${temp_file}=    Set Variable    /tmp/${job_name}.yaml
    Create File    ${temp_file}    ${manifest}

    # Apply the Job
    ${result}=    Run Process    kubectl apply -f ${temp_file} -n ${namespace}    shell=True
    Should Be Equal As Integers    ${result.rc}    0    msg=Failed to submit S3 writer job: ${result.stderr}

    Log    Submitted S3 writer job: ${job_name} in namespace: ${namespace}    INFO

    RETURN    ${job_name}

Submit S3 Reader Job
    [Documentation]    Submit a Kubernetes Job to read and verify data from S3
    ...    Similar to Submit S3 Writer Job but for reading/verification
    [Arguments]    ${namespace}    ${storage_config_map_name}    ${secret_name}    ${access_key_name}    ${secret_key_name}    ${test_data_key}    ${expected_content}    ${random_suffix}

    ${job_name}=    Set Variable    s3-reader-test-${random_suffix}
    ${manifest_path}=    Set Variable    ${CURDIR}/../test_data/manifests/s3-reader-job.yaml

    ${manifest}=    Get File    ${manifest_path}

    ${manifest}=    Replace String    ${manifest}    STORAGE_CONFIG_MAP_NAME    ${storage_config_map_name}
    ${manifest}=    Replace String    ${manifest}    SECRET_NAME_PLACEHOLDER    ${secret_name}
    ${manifest}=    Replace String    ${manifest}    ACCESS_KEY_NAME_PLACEHOLDER    ${access_key_name}
    ${manifest}=    Replace String    ${manifest}    SECRET_KEY_NAME_PLACEHOLDER    ${secret_key_name}
    ${manifest}=    Replace String    ${manifest}    name: s3-reader-test-job    name: ${job_name}
    ${manifest}=    Replace String    ${manifest}    value: "PLACEHOLDER"    value: "${test_data_key}"    count=1
    ${manifest}=    Replace String    ${manifest}    value: "PLACEHOLDER"    value: "${expected_content}"    count=1

    ${temp_file}=    Set Variable    /tmp/${job_name}.yaml
    Create File    ${temp_file}    ${manifest}

    ${result}=    Run Process    kubectl apply -f ${temp_file} -n ${namespace}    shell=True
    Should Be Equal As Integers    ${result.rc}    0    msg=Failed to submit S3 reader job: ${result.stderr}

    Log    Submitted S3 reader job: ${job_name} in namespace: ${namespace}    INFO

    RETURN    ${job_name}

Submit S3 Cleanup Job
    [Documentation]    Submit a Kubernetes Job to cleanup e2e test data from S3.
    ...
    ...    The prefix bounds what is deleted to the objects the calling test wrote — passing the
    ...    test's own key prefix keeps cleanup from reaching anything else that happens to share
    ...    the bucket.
    [Arguments]    ${namespace}    ${storage_config_map_name}    ${secret_name}    ${access_key_name}    ${secret_key_name}    ${test_data_prefix}    ${random_suffix}

    ${job_name}=    Set Variable    s3-cleanup-test-${random_suffix}
    ${manifest_path}=    Set Variable    ${CURDIR}/../test_data/manifests/s3-cleanup-job.yaml

    ${manifest}=    Get File    ${manifest_path}

    ${manifest}=    Replace String    ${manifest}    STORAGE_CONFIG_MAP_NAME    ${storage_config_map_name}
    ${manifest}=    Replace String    ${manifest}    SECRET_NAME_PLACEHOLDER    ${secret_name}
    ${manifest}=    Replace String    ${manifest}    ACCESS_KEY_NAME_PLACEHOLDER    ${access_key_name}
    ${manifest}=    Replace String    ${manifest}    SECRET_KEY_NAME_PLACEHOLDER    ${secret_key_name}
    ${manifest}=    Replace String    ${manifest}    name: s3-cleanup-test-job    name: ${job_name}
    ${manifest}=    Replace String    ${manifest}    value: "PLACEHOLDER"    value: "${test_data_prefix}"    count=1

    ${temp_file}=    Set Variable    /tmp/${job_name}.yaml
    Create File    ${temp_file}    ${manifest}

    ${result}=    Run Process    kubectl apply -f ${temp_file} -n ${namespace}    shell=True
    Should Be Equal As Integers    ${result.rc}    0    msg=Failed to submit S3 cleanup job: ${result.stderr}

    Log    Submitted S3 cleanup job: ${job_name} in namespace: ${namespace}    INFO

    RETURN    ${job_name}

Wait For Job Completion
    [Documentation]    Wait for a Kubernetes Job to complete (succeed or fail)
    [Arguments]    ${job_name}    ${namespace}    ${timeout}=${S3_JOB_TIMEOUT}

    Wait Until Keyword Succeeds    ${timeout}    ${S3_JOB_POLL_INTERVAL}
    ...    Check Job Completed    ${job_name}    ${namespace}

    Log    Job ${job_name} completed    INFO

Check Job Completed
    [Documentation]    Helper keyword to check if a Job has completed
    [Arguments]    ${job_name}    ${namespace}

    ${kubectl_cmd}=    Set Variable    kubectl get job ${job_name} -n ${namespace} -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}'
    ${result}=    Run Process    ${kubectl_cmd}    shell=True
    ${complete_status}=    Set Variable    ${result.stdout}

    ${kubectl_cmd}=    Set Variable    kubectl get job ${job_name} -n ${namespace} -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}'
    ${result}=    Run Process    ${kubectl_cmd}    shell=True
    ${failed_status}=    Set Variable    ${result.stdout}

    Should Be True    '${complete_status}' == 'True' or '${failed_status}' == 'True'
    ...    msg=Job ${job_name} not yet completed (Complete=${complete_status}, Failed=${failed_status})

Verify Job Succeeded
    [Documentation]    Verify that a Job completed successfully.
    ...    Captures job logs and status before asserting, so failures include diagnostics.
    [Arguments]    ${job_name}    ${namespace}

    # Capture job status for diagnostics
    ${status_cmd}=    Set Variable
    ...    kubectl get job ${job_name} -n ${namespace} -o jsonpath='{.status.conditions[*].type}: {.status.conditions[*].message}'
    ${status_result}=    Run Process    ${status_cmd}    shell=True

    # Capture pod logs before asserting so failures show what went wrong
    ${logs}=    Set Variable    (no logs captured)
    ${pod_cmd}=    Set Variable
    ...    kubectl get pods -n ${namespace} -l job-name\=${job_name} -o jsonpath='{.items[0].metadata.name}'
    ${pod_result}=    Run Process    ${pod_cmd}    shell=True
    IF    '${pod_result.stdout}' != '${EMPTY}'
        ${log_result}=    Run Process
        ...    kubectl logs ${pod_result.stdout} -n ${namespace}    shell=True
        ${logs}=    Set Variable    ${log_result.stdout}
    END

    # Now check success
    ${succeeded_cmd}=    Set Variable
    ...    kubectl get job ${job_name} -n ${namespace} -o jsonpath='{.status.succeeded}'
    ${result}=    Run Process    ${succeeded_cmd}    shell=True
    Should Be Equal    ${result.stdout}    1
    ...    msg=Job ${job_name} did not succeed.\nJob status: ${status_result.stdout}\nPod logs:\n${logs}

    Log    Job ${job_name} succeeded    INFO

Get Job Logs
    [Documentation]    Get logs from a completed Job's pod
    [Arguments]    ${job_name}    ${namespace}

    # Get the pod name for this job
    ${kubectl_cmd}=    Set Variable    kubectl get pods -n ${namespace} -l job-name\=${job_name} -o jsonpath='{.items[0].metadata.name}'
    ${result}=    Run Process    ${kubectl_cmd}    shell=True
    ${pod_name}=    Set Variable    ${result.stdout}

    Should Not Be Empty    ${pod_name}    msg=No pod found for job ${job_name}

    # Get logs from the pod
    ${kubectl_cmd}=    Set Variable    kubectl logs ${pod_name} -n ${namespace}
    ${result}=    Run Process    ${kubectl_cmd}    shell=True
    ${logs}=    Set Variable    ${result.stdout}

    Log    Job ${job_name} logs:\n${logs}    INFO

    RETURN    ${logs}

Delete Job
    [Documentation]    Delete a Kubernetes Job and its pods
    [Arguments]    ${job_name}    ${namespace}

    ${kubectl_cmd}=    Set Variable    kubectl delete job ${job_name} -n ${namespace} --ignore-not-found\=true
    ${result}=    Run Process    ${kubectl_cmd}    shell=True
    Log    Deleted job ${job_name}: ${result.stdout}    DEBUG

Remove S3 Test Objects
    [Documentation]    Delete the objects a test wrote under its own key prefix.
    ...
    ...    Call it while the storage ConfigMap and Secret still exist, since the cleanup Job reads
    ...    the bucket and credentials from them. After deleting the objects, the Job deletes only
    ...    buckets named e2e-test-bucket-* (the dedicated test-bucket convention); every other
    ...    bucket is preserved as platform- or user-owned.
    ...
    ...    Best effort: a cleanup that cannot run must not fail a test whose assertions already
    ...    passed, so a failure becomes a warning naming the prefix that was left behind.
    [Arguments]    ${namespace}    ${storage_config_map_name}    ${secret_name}    ${access_key_name}    ${secret_key_name}    ${test_data_prefix}

    # Empty until the Job exists, so the FINALLY below can tell "never submitted" from
    # "submitted and then something went wrong".
    VAR    ${job_name}    ${EMPTY}

    TRY
        ${random_suffix}=    Generate Random Suffix
        ${job_name}=    Submit S3 Cleanup Job
        ...    ${namespace}
        ...    ${storage_config_map_name}
        ...    ${secret_name}
        ...    ${access_key_name}
        ...    ${secret_key_name}
        ...    ${test_data_prefix}
        ...    ${random_suffix}

        Wait For Job Completion    ${job_name}    ${namespace}    timeout=2 min
        ${logs}=    Get Job Logs    ${job_name}    ${namespace}
        Verify Job Succeeded    ${job_name}    ${namespace}

        Log    Removed S3 test objects under prefix: ${test_data_prefix}    INFO
    EXCEPT    AS    ${error}
        Log    Could not remove S3 test objects under prefix ${test_data_prefix}: ${error}    WARN
    FINALLY
        # A Job that never reaches a finished state is never reaped by ttlSecondsAfterFinished,
        # so a wait timeout would otherwise strand it. Delete on every path.
        IF    '${job_name}' != '${EMPTY}'
            Delete Job    ${job_name}    ${namespace}
        END
    END

Generate Random Suffix
    [Documentation]    Generate a unique suffix for resource names and S3 key prefixes.
    ...
    ...    The timestamp keeps the value sortable when inspecting leftovers; the random token is
    ...    what makes it unique. A 4-digit random was not enough for concurrently-created
    ...    Kubernetes Jobs in the same namespace — a collision is a hard create failure.
    ...
    ...    Lowercase hex keeps the result valid inside a Kubernetes resource name.
    ${timestamp}=    Evaluate    int(__import__('time').time())
    ${token}=    Evaluate    __import__('uuid').uuid4().hex[:12]
    RETURN    ${timestamp}-${token}

Create Storage ConfigMap For Local Testing
    [Documentation]    Create ConfigMap for storage in local development (Agent doesn't run)
    ...    This ConfigMap would normally be created by the Agent
    [Arguments]    ${namespace}    ${config_map_name}    ${bucket_url}    ${access_key_name}    ${secret_key_name}    ${secret_name}

    ${manifest}=    Catenate    SEPARATOR=\n
    ...    apiVersion: v1
    ...    kind: ConfigMap
    ...    metadata:
    ...    ${SPACE}${SPACE}name: ${config_map_name}
    ...    ${SPACE}${SPACE}namespace: ${namespace}
    ...    data:
    ...    ${SPACE}${SPACE}BUCKET_URL: "${bucket_url}"
    ...    ${SPACE}${SPACE}ACCESS_KEY_NAME: "${access_key_name}"
    ...    ${SPACE}${SPACE}SECRET_KEY_NAME: "${secret_key_name}"
    ...    ${SPACE}${SPACE}SECRET_NAME: "${secret_name}"

    ${temp_file}=    Set Variable    /tmp/storage-configmap-${config_map_name}.yaml
    Create File    ${temp_file}    ${manifest}

    ${kubectl_cmd}=    Set Variable    kubectl apply -f ${temp_file} -n ${namespace}
    ${result}=    Run Process    ${kubectl_cmd}    shell=True
    Should Be Equal As Integers    ${result.rc}    0    msg=Failed to create ConfigMap: ${result.stderr}

    Log    Created ConfigMap ${config_map_name} in namespace ${namespace}    INFO

Create ExternalSecret For Local Testing
    [Documentation]    Create the Secret the S3 Jobs mount, in local development.
    ...    This Secret would normally be created by the Agent.
    ...    Uses the per-project credentials the platform syncs into the project namespace — the
    ...    access path a project's own workloads use — rather than a cluster storage-admin identity
    ...    from a MinIO tenant no current release deploys.
    ...    The read, decode and apply all happen inside one Python keyword: Robot logs every
    ...    variable assignment at INFO, so holding the credentials in Robot variables here would put
    ...    the access key and secret key into routine test output.
    ...    bucket_url is the storage spec's own, the same value the Jobs' ConfigMap carries, so the
    ...    absent-credentials skip is decided about the store those Jobs actually use.
    [Arguments]    ${namespace}    ${secret_name}    ${access_key_name}    ${secret_key_name}    ${bucket_url}

    Provision Storage Credentials Secret
    ...    ${namespace}    ${secret_name}    ${access_key_name}    ${secret_key_name}    ${bucket_url}

    Log    Created Secret ${secret_name} in namespace ${namespace}    INFO

Delete Storage Resources For Local Testing
    [Documentation]    Delete ConfigMap and Secret created for local testing
    [Arguments]    ${namespace}    ${config_map_name}    ${secret_name}

    ${kubectl_cmd}=    Set Variable    kubectl delete configmap ${config_map_name} -n ${namespace} --ignore-not-found=true
    ${result}=    Run Process    ${kubectl_cmd}    shell=True
    Log    Deleted ConfigMap ${config_map_name}: ${result.stdout}    DEBUG

    ${kubectl_cmd}=    Set Variable    kubectl delete secret ${secret_name} -n ${namespace} --ignore-not-found=true
    ${result}=    Run Process    ${kubectl_cmd}    shell=True
    Log    Deleted Secret ${secret_name}: ${result.stdout}    DEBUG
