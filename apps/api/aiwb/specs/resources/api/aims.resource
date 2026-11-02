# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Low-level keywords for AIWB inference and AIM catalog endpoints.
...                 Provides direct API operation wrappers for the inference capability
...                 (cluster-scoped /v1/inference/models and project-scoped
...                 /v1/projects/{project}/inference) plus the namespace-scoped
...                 fine-tuned model templates endpoint.
...                 This is part of the API layer that handles raw HTTP requests/responses.
Library             RequestsLibrary
Library             Collections
Library             BuiltIn
Resource            resources/api/common.resource


*** Keywords ***
Inference models endpoint
    [Documentation]    Return the cluster-scoped inference base models endpoint URL.
    ${endpoint}=            Service API Endpoint    aiwb    endpoint=inference/models
    RETURN                  ${endpoint}

Project inference endpoint
    [Documentation]    Return the project-scoped inference deployments endpoint URL.
    [Arguments]             ${project}
    ${endpoint}=            Service API Endpoint    aiwb    endpoint=projects/${project}/inference
    RETURN                  ${endpoint}

Get AIM
    [Documentation]    Retrieve a specific cluster-scoped inference base model by resource name.
    ...
    ...    Args:
    ...    resource_name (str): Kubernetes resource name of the AIMClusterModel
    ...
    ...    Return:
    ...    response: API response containing the AIM details
    [Arguments]             ${resource_name}        ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=            Inference models endpoint
    ${response}=            Safe Get Request        ${endpoint}/${resource_name}                    expected_status=${expected_status}
    RETURN                  ${response}

List AIMs
    [Documentation]    List the cluster catalog of inference base models.
    ...
    ...    Args:
    ...    status_filter (str, optional): AIM status value to filter by (e.g. Ready)
    ...    accelerator_type (str or list, optional): Accelerator family to filter by
    ...        (cpu or gpu). Pass a list to repeat ``acceleratorType`` for OR semantics
    ...        on the wire, e.g. ['cpu','gpu'].
    ...    page (int, optional): Page number to request
    ...    page_size (int, optional): Items per page (max 100)
    ...
    ...    Return:
    ...    response: API response containing list of AIMs
    [Arguments]             ${expected_status}=any    ${status_filter}=${None}    ${accelerator_type}=${None}
    ...                     ${page}=${None}    ${page_size}=${None}
    Create api session    aiwb
    ${endpoint}=            Inference models endpoint
    # When accelerator_type is a list we need repeating params, which requires the
    # list-of-tuples form rather than the dict form RequestsLibrary normally takes.
    ${is_list}=             Evaluate    isinstance($accelerator_type, list)
    IF    ${is_list}
        VAR    @{tuples}    @{EMPTY}
        IF    $status_filter != $None
            ${pair}=                Evaluate                ("statusFilter", "${status_filter}")
            Append To List          ${tuples}               ${pair}
        END
        FOR    ${value}    IN    @{accelerator_type}
            ${pair}=                Evaluate                ("acceleratorType", "${value}")
            Append To List          ${tuples}               ${pair}
        END
        IF    $page != $None
            ${pair}=                Evaluate                ("page", "${page}")
            Append To List          ${tuples}               ${pair}
        END
        IF    $page_size != $None
            ${pair}=                Evaluate                ("pageSize", "${page_size}")
            Append To List          ${tuples}               ${pair}
        END
        ${response}=            Safe Get Request        ${endpoint}             params=${tuples}        expected_status=${expected_status}
        RETURN                  ${response}
    END
    VAR    ${params}    ${None}
    IF    $status_filter != $None or $accelerator_type != $None or $page != $None or $page_size != $None
        ${params}=              Create Dictionary
        IF    $status_filter != $None
            Set To Dictionary       ${params}               statusFilter=${status_filter}
        END
        IF    $accelerator_type != $None
            Set To Dictionary       ${params}               acceleratorType=${accelerator_type}
        END
        IF    $page != $None
            Set To Dictionary       ${params}               page=${page}
        END
        IF    $page_size != $None
            Set To Dictionary       ${params}               pageSize=${page_size}
        END
    END
    ${response}=            Safe Get Request        ${endpoint}             params=${params}        expected_status=${expected_status}
    RETURN                  ${response}

Deploy AIM
    [Documentation]    Deploy a model for inference in the given project.
    ...
    ...    Args:
    ...    model (str): AIMClusterModel resource name (e.g., 'meta-llama-3-8b') or
    ...                 project-scoped AIMModel name. The backend auto-detects.
    ...    deploy_data (dict): Deployment configuration (replicas, hfToken, etc.)
    ...    namespace (str): Project (1:1 with namespace) to deploy into
    ...
    ...    Return:
    ...    response: API response containing the inference deployment details
    [Arguments]             ${model}                ${deploy_data}          ${namespace}            ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=            Project inference endpoint    ${namespace}
    # Add model name to deploy data
    ${full_deploy_data}=    Create Dictionary       model=${model}
    Set To Dictionary       ${full_deploy_data}     &{deploy_data}
    ${response}=            Safe Post Request       ${endpoint}             json=${full_deploy_data}                        expected_status=${expected_status}
    RETURN                  ${response}

Undeploy AIM
    [Documentation]    Undeploy an inference deployment from the given project.
    ...
    ...    Args:
    ...    service_id (str): UUID of the inference deployment to undeploy
    ...    namespace (str): Project (1:1 with namespace) where the deployment lives
    ...
    ...    Return:
    ...    response: API response
    [Arguments]             ${service_id}           ${namespace}            ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=            Project inference endpoint    ${namespace}
    ${response}=            Safe Delete Request     ${endpoint}/${service_id}                       expected_status=${expected_status}
    RETURN                  ${response}

List AIM Services
    [Documentation]    List inference deployments in a project.
    ...
    ...    Args:
    ...    namespace (str): Project (1:1 with namespace) to list deployments from
    ...    capability (str): Optional capability filter (e.g. 'chat') to narrow the
    ...                      list to deployments matching a specific capability.
    ...    status_filter (str|list): Optional status value or list of status values
    ...                              to filter by (sent as repeated statusFilter query).
    ...    page (int, optional): Page number (default 1)
    ...    page_size (int, optional): Page size (default 10, max 100)
    ...
    ...    Return:
    ...    response: API response containing list of inference deployments
    [Arguments]             ${namespace}            ${expected_status}=any
    ...                     ${capability}=${None}    ${status_filter}=${None}    ${page_size}=${None}
    ...                     ${page}=${None}
    Create api session    aiwb
    ${endpoint}=            Project inference endpoint    ${namespace}
    VAR    ${params}    ${None}
    ${has_filter}=          Evaluate    $capability is not None or $status_filter is not None or $page_size is not None or $page is not None
    IF    ${has_filter}
        ${params}=              Create Dictionary
        IF    $capability is not None
            Set To Dictionary       ${params}    capability=${capability}
        END
        IF    $status_filter is not None
            Set To Dictionary       ${params}    statusFilter=${status_filter}
        END
        IF    $page is not None
            Set To Dictionary       ${params}    page=${page}
        END
        IF    $page_size is not None
            Set To Dictionary       ${params}    pageSize=${page_size}
        END
    END
    ${response}=            Safe Get Request        ${endpoint}             params=${params}        expected_status=${expected_status}
    RETURN                  ${response}

Get AIM Service
    [Documentation]    Get a specific inference deployment by ID.
    ...
    ...    Args:
    ...    service_id (str): UUID of the inference deployment
    ...    namespace (str): Project (1:1 with namespace)
    ...
    ...    Return:
    ...    response: API response containing the inference deployment details
    [Arguments]             ${service_id}           ${namespace}            ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=            Project inference endpoint    ${namespace}
    ${response}=            Safe Get Request        ${endpoint}/${service_id}                       expected_status=${expected_status}
    RETURN                  ${response}

Get AIM Service Metric
    [Documentation]    Retrieve a single inference-scoped metric for a deployment.
    ...
    ...    Args:
    ...    service_id (str): UUID of the inference deployment
    ...    metric (str): Metric name (see MetricName enum, e.g. 'requests', 'total_tokens')
    ...    namespace (str): Project (1:1 with namespace)
    ...    params (dict): Optional query params (e.g. start/end/podName)
    ...
    ...    Return:
    ...    response: API response containing the metric value(s)
    [Arguments]             ${service_id}           ${metric}               ${namespace}
    ...                     ${expected_status}=any    ${params}=${None}
    Create api session    aiwb
    ${endpoint}=            Project inference endpoint    ${namespace}
    ${response}=            Safe Get Request        ${endpoint}/${service_id}/metrics/${metric}
    ...                     params=${params}        expected_status=${expected_status}
    RETURN                  ${response}

List AIM Profiles
    [Documentation]    List AIMClusterProfiles, optionally filtered by aimId.
    ...
    ...    Args:
    ...    aim_id (str, optional): Filter by AIMClusterProfile spec.aimId. Omit to list all.
    ...    page (int, optional): Page number (default 1)
    ...    page_size (int, optional): Page size (default 10, max 100)
    ...
    ...    Return:
    ...    response: API response with paginated envelope (data + pagination)
    [Arguments]             ${aim_id}=${None}       ${page}=${None}         ${page_size}=${None}    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=            Service API Endpoint    aiwb    endpoint=inference/profiles
    ${params}=              Create Dictionary
    IF    $aim_id is not None
        Set To Dictionary       ${params}    aimId=${aim_id}
    END
    IF    $page is not None
        Set To Dictionary       ${params}    page=${page}
    END
    IF    $page_size is not None
        Set To Dictionary       ${params}    pageSize=${page_size}
    END
    ${response}=            Safe Get Request        ${endpoint}             params=${params}        expected_status=${expected_status}
    RETURN                  ${response}

Update AIM Service Scaling Policy
    [Documentation]    Update the scaling policy of an inference deployment.
    ...
    ...    Args:
    ...    service_id (str): UUID of the inference deployment
    ...    scaling_data (dict): Scaling configuration (minReplicas, maxReplicas, autoScaling)
    ...    namespace (str): Project (1:1 with namespace)
    ...
    ...    Return:
    ...    response: API response containing the updated inference deployment details
    [Arguments]             ${service_id}           ${scaling_data}         ${namespace}            ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=            Project inference endpoint    ${namespace}
    ${response}=            Safe Patch Request      ${endpoint}/${service_id}                       json=${scaling_data}                            expected_status=${expected_status}
    RETURN                  ${response}

Update AIM Service Adapters
    [Documentation]    Replace the adapters an inference deployment serves. The list is the
    ...    complete desired set, so an empty list detaches every adapter. Pass ``scaling`` to
    ...    change the scaling policy in the same request.
    ...
    ...    Return:
    ...    response: API response containing the updated inference deployment details
    [Arguments]             ${service_id}           ${adapters}             ${namespace}            ${scaling}=${None}
    ...                     ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=            Project inference endpoint    ${namespace}
    ${body}=                Create Dictionary       adapters=${adapters}
    IF                      $scaling is not None
        Set To Dictionary   ${body}                 &{scaling}
    END
    ${response}=            Safe Patch Request      ${endpoint}/${service_id}                       json=${body}                                    expected_status=${expected_status}
    RETURN                  ${response}

List Fine-Tuned AIM Profiles
    [Documentation]    List namespace-scoped AIMProfiles, optionally filtered by aimId.
    ...
    ...    Args:
    ...    project (str): Project identifier (1:1 with Kubernetes namespace)
    ...    aim_id (str, optional): Filter by AIMProfile spec.aimId. Omit to list all in the project.
    ...    page (int, optional): Page number (default 1)
    ...    page_size (int, optional): Page size (default 10, max 100)
    ...
    ...    Return:
    ...    response: API response with paginated envelope (data + pagination)
    [Arguments]             ${project}              ${aim_id}=${None}       ${page}=${None}         ${page_size}=${None}    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=            Service API Endpoint    aiwb    endpoint=projects/${project}/profiles
    ${params}=              Create Dictionary
    IF    $aim_id is not None
        Set To Dictionary       ${params}    aimId=${aim_id}
    END
    IF    $page is not None
        Set To Dictionary       ${params}    page=${page}
    END
    IF    $page_size is not None
        Set To Dictionary       ${params}    pageSize=${page_size}
    END
    ${response}=            Safe Get Request        ${endpoint}             params=${params}        expected_status=${expected_status}
    RETURN                  ${response}

Get Inference Replicas
    [Documentation]    List Kubernetes pod data for each replica of an inference deployment.
    ...
    ...    Args:
    ...    service_id (str): UUID of the inference deployment
    ...    namespace (str): Project (1:1 with namespace) the deployment lives in
    ...
    ...    Return:
    ...    response: API response containing list of replica pod records
    [Arguments]             ${service_id}           ${namespace}            ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=            Project inference endpoint    ${namespace}
    ${response}=            Safe Get Request        ${endpoint}/${service_id}/replicas               expected_status=${expected_status}
    RETURN                  ${response}
