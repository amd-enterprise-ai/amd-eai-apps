# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Low-level keywords for the fine-tuning capability endpoints.
...                 Provides direct API operation wrappers for /v1/projects/{project}/fine-tuning/*.
...                 This is part of the API layer that handles raw HTTP requests/responses.
Library             RequestsLibrary
Library             Collections
Resource            resources/api/common.resource
Resource            resources/airm_projects.resource
Resource            workloads.resource


*** Keywords ***
Fine-tuning jobs endpoint
    [Documentation]    Returns the project-scoped fine-tuning jobs collection URL.
    ...                Pattern: /projects/{project}/fine-tuning/jobs
    [Arguments]    ${project}
    ${endpoint}=    Service API Endpoint    aiwb    endpoint=projects/${project}/fine-tuning/jobs
    RETURN    ${endpoint}

Finetune model
    [Documentation]    Submit a fine-tuning job against the given base model.
    ...                Uses the project-scoped capability endpoint:
    ...                POST /projects/{project}/fine-tuning/jobs
    ...
    ...                The base model identifier now lives in the request body
    ...                (FineTuningJobRequest.baseModel) — under the legacy URL
    ...                it was a path segment.
    ...
    ...                Args:
    ...                base_model: AIMModel UUID or HuggingFace canonical name
    ...                            (e.g., "meta-llama/Llama-3.2-1B-Instruct")
    ...                finetune_data: Dictionary with the rest of the FinetuneCreate fields
    ...                               (displayName, datasetIds, epochs, learningRate, batchSize,
    ...                               hfTokenSecretName). Deprecated datasetId is also accepted.
    ...                namespace: Project namespace for the request
    ...                expected_status: Expected HTTP status code (default: any)
    ...                display_name: Optional display name for the workload
    ...
    ...                Returns:
    ...                response: API response containing the created fine-tuning workload
    [Arguments]    ${base_model}    ${finetune_data}    ${namespace}    ${expected_status}=any
    ...    ${display_name}=${None}
    Create api session    aiwb

    ${endpoint}=    Fine-tuning jobs endpoint    ${namespace}

    # Hoist base model into the request body — the capability API expects it there.
    ${body}=    Copy Dictionary    ${finetune_data}
    Set To Dictionary    ${body}    baseModel=${base_model}

    ${params}=    Create Dictionary
    IF    $display_name is not None
        Set To Dictionary    ${params}    displayName=${display_name}
    END

    Log    POST ${endpoint}    DEBUG
    Log    Request body: ${body}    DEBUG

    ${response}=    Safe Post Request    ${endpoint}    json=${body}
    ...    params=${params}    expected_status=${expected_status}

    Log    Response status: ${response.status_code}    DEBUG
    RETURN    ${response}

Cancel finetuning job
    [Documentation]    Cancel an in-progress fine-tuning job and tear down its Kubernetes
    ...                components via the project-scoped capability endpoint:
    ...                DELETE /projects/{project}/fine-tuning/jobs/{job_id}
    ...
    ...                Args:
    ...                job_id: Workload UUID of the fine-tuning job
    ...                namespace: Project namespace for the request
    ...                expected_status: Expected HTTP status code (default: any)
    ...
    ...                Returns:
    ...                response: API response (204 No Content on success)
    [Arguments]    ${job_id}    ${namespace}    ${expected_status}=any
    Create api session    aiwb

    ${endpoint}=    Fine-tuning jobs endpoint    ${namespace}
    Log    DELETE ${endpoint}/${job_id}    DEBUG
    ${response}=    Safe Delete Request    ${endpoint}/${job_id}    expected_status=${expected_status}
    Log    Cancel fine-tuning job response: status=${response.status_code}    DEBUG
    RETURN    ${response}
