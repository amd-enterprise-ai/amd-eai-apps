# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Low-level keywords for Catalog API models endpoints.
...                 Provides direct API operation wrappers for the /models endpoints.
...                 This is part of the API layer that handles raw HTTP requests/responses.
...                 Higher-level test logic should use aiwb_models.resource instead.
Library             RequestsLibrary
Library             Collections
Library             OperatingSystem
Resource            resources/api/common.resource
Resource            resources/api/aims.resource
Resource            resources/api/external_aim.resource


*** Variables ***
${HEADERS}      Content-Type=application/json


*** Keywords ***
Models endpoint
    [Documentation]    Return the full models endpoint url
    ${endpoint}=            Service API Endpoint    aiwb    endpoint=models
    RETURN                  ${endpoint}

Create model
    [Documentation]    Create a new model using the provided data
    ...
    ...    Args:
    ...    model_data (dict): Model creation parameters including:
    ...    - name: Model name
    ...    - type: Model type (BaseModel or MergedModel)
    ...    - modelWeightsPath: Optional path to weights
    ...    - base_model_id: Required for MergedModel type
    ...
    ...    Return:
    ...    response: API response containing the created model
    ...
    ...    Raise:
    ...    HTTPError: If the API request fails
    [Arguments]             ${model_data}           ${expected_status}=any                          ${params}=${None}
    Create api session    aiwb
    TRY
        ${endpoint}=            Models endpoint
        ${headers}=             Create Dictionary       Content-Type=application/json
        Log                     POST ${endpoint} with data: ${model_data}       DEBUG
        ${response}=            Safe Post Request        ${endpoint}             json=${model_data}      headers=${headers}      expected_status=${expected_status}              params=${params}
        Log                     Model creation response: status=${response.status_code}                 DEBUG
        IF    ${response.status_code} in [200, 201]
            ${response_json}=       Set Variable            ${response.json()}
            ${model_id}=        Get From Dictionary     ${response_json}        id
            ${model_name}=      Get From Dictionary     ${response_json}        name
            Log                     Created model ${model_id} (${model_name})     INFO
        END
        RETURN                  ${response}
    EXCEPT    HTTPError    AS    ${error}
        Log                     Failed to create model: ${error}                ERROR                   console=yes
        FAIL                    Model creation failed: ${error}
    END

Get model
    [Documentation]    Retrieve a specific fine-tuned model by name using the
    ...                project-scoped fine-tuning capability endpoint:
    ...                GET /projects/{project}/fine-tuning/models/{model_id}
    ...
    ...                Args:
    ...                model_id (str): AIMModel CR name or workload UUID
    ...                expected_status (str): Expected HTTP status code (default: any)
    ...                namespace (str): Project namespace for the request (required)
    ...                project_id: DEPRECATED - kept for backward compatibility but ignored
    ...
    ...                Return:
    ...                response: API response containing the model details
    ...
    ...                Raise:
    ...                HTTPError: If the model is not found or request fails
    [Arguments]             ${model_id}             ${namespace}            ${expected_status}=any
    ...                     ${project_id}=${None}
    Create api session    aiwb

    # Verify that namespace is not None
    IF    $namespace == $None
        FAIL                    namespace cannot be None when calling Get model
    END

    ${endpoint}=            Service API Endpoint    aiwb    endpoint=projects/${namespace}/fine-tuning/models/${model_id}

    Log                     GET ${endpoint}         DEBUG
    ${response}=            Safe Get Request        ${endpoint}             expected_status=${expected_status}
    Log                     Get model response: status=${response.status_code}                      DEBUG
    RETURN                  ${response}

Get models
    [Documentation]    List fine-tuned models in a project via the fine-tuning
    ...                capability endpoint:
    ...                GET /projects/{project}/fine-tuning/models
    ...
    ...                Returns AIMModel CRs in the namespace.
    ...
    ...                Response shape per model follows the AIMModel CRD: metadata (name,
    ...                labels, annotations, creationTimestamp), spec (aimId, image,
    ...                modelSources, custom, env), and status (status, conditions,
    ...                imageMetadata, sourceType).
    ...
    ...                Args:
    ...                namespace (str): Project namespace for the request (required)
    ...                expected_status (str): Expected HTTP status code (default: any)
    ...                project_id: DEPRECATED - ignored
    ...                page (int, optional): Page number (default 1)
    ...                page_size (int, optional): Page size (default 10, max 100)
    ...
    ...                Returns:
    ...                response: API response containing list of AIMModelResource objects (in 'data' array)
    ...
    ...                Raises:
    ...                HTTPError: If the API request fails
    [Arguments]             ${namespace}            ${expected_status}=any    ${project_id}=${None}
    ...                     ${page}=${None}         ${page_size}=${None}
    Create api session    aiwb

    # Verify that namespace is not None
    IF    $namespace == $None
        FAIL                    namespace cannot be None when calling Get models
    END

    ${endpoint}=            Service API Endpoint    aiwb    endpoint=projects/${namespace}/fine-tuning/models
    ${params}=              Create Dictionary
    IF    $page is not None
        Set To Dictionary       ${params}    page=${page}
    END
    IF    $page_size is not None
        Set To Dictionary       ${params}    pageSize=${page_size}
    END

    Log                     GET ${endpoint} with params: ${params}         DEBUG
    ${response}=            Safe Get Request        ${endpoint}             params=${params}    expected_status=${expected_status}
    Log                     List models response: status=${response.status_code}                    DEBUG
    RETURN                  ${response}

Modify model
    [Documentation]    Update an existing model.
    ...
    ...    Args:
    ...    model_id (str): UUID of the model to modify
    ...    model_data (dict): Updated model parameters
    ...
    ...    Returns:
    ...    response: API response containing the updated model
    ...
    ...    Raises:
    ...    HTTPError: If the model is not found or update fails
    [Arguments]             ${model_id}             ${model_data}           ${namespace}            ${expected_status}=any
    Create api session    aiwb

    IF    $namespace == $None
        FAIL                    namespace cannot be None when calling Modify model
    END

    ${endpoint}=            Service API Endpoint    aiwb    endpoint=namespaces/${namespace}/aims/models/${model_id}
    TRY
        Log                     PUT ${endpoint} with data: ${model_data}                               DEBUG
        ${response}=            Safe Put Request        ${endpoint}             json=${model_data}      expected_status=${expected_status}
        Log                     Modify model response: status=${response.status_code}                   DEBUG
        IF    ${response.status_code} == 200
            Log                     Modified model ${model_id}      INFO
        END
        RETURN                  ${response}
    EXCEPT    HTTPError    AS    ${error}
        Log                     Failed to modify model ${model_id}: ${error}    ERROR
        FAIL                    Model modification failed: ${error}
    END

Delete model
    [Documentation]    Delete a specific model using namespace-based routing.
    ...                Pattern: /namespaces/{namespace}/aims/models/{model_id}
    ...
    ...    Args:
    ...    model_id (str): AIMModel CR name (not a DB UUID)
    ...    expected_status (str): Expected HTTP status code (default: any)
    ...    namespace (str): Namespace for the request (required)
    ...    force (bool): When True, cascade-deletes active AIMServices (default: False)
    ...    project_id: DEPRECATED - kept for backward compatibility but ignored
    ...
    ...    Returns:
    ...    response: API response (empty on success, 204; 409 when active deployments exist and force=False)
    ...
    ...    Raises:
    ...    HTTPError: If the model is not found or deletion fails
    [Arguments]             ${model_id}             ${namespace}            ${expected_status}=any
    ...                     ${force}=${False}        ${project_id}=${None}
    Create api session    aiwb

    # Verify that namespace is not None
    IF    $namespace == $None
        FAIL                    namespace cannot be None when calling Delete model
    END

    ${endpoint}=            Service API Endpoint    aiwb    endpoint=projects/${namespace}/fine-tuning/models/${model_id}

    # force=true query param is only set when requested; ${None} means no params sent
    VAR    ${params}    ${None}
    IF    $force
        ${params}=    Create Dictionary    force=true
    END

    Log                     DELETE ${endpoint} (force=${force})      DEBUG
    ${response}=            Safe Delete Request     ${endpoint}             expected_status=${expected_status}    params=${params}
    Log                     Delete model response: status=${response.status_code}                   DEBUG
    IF    ${response.status_code} == 204
        Log                     Deleted model ${model_id}       INFO
    END
    RETURN                  ${response}

Send chat completion request to external endpoint
    [Documentation]    Sends a chat completion request to an external endpoint.
    ...    Returns the raw response without validation.
    [Arguments]    ${external_host}    ${model_id}    ${api_key}=${None}    ${expected_status}=any

    ${session_name}=    Create AIM external session    ${external_host}
    ...    session_name=aim_external_chat_${model_id}

    ${headers}=    Create dictionary    Content-Type=application/json
    IF    "${api_key}" != "${None}"
        Set to dictionary    ${headers}    Authorization=Bearer ${api_key}
    END

    ${messages}=    Evaluate    [{"role": "user", "content": "Hello"}]
    ${request_data}=    Create dictionary
    ...    model=${model_id}
    ...    messages=${messages}
    ...    max_tokens=10

    ${response}=    Post To AIM External Endpoint    ${session_name}    /v1/chat/completions
    ...    json=${request_data}    headers=${headers}    expected_status=${expected_status}

    RETURN    ${response}

List models from external endpoint
    [Documentation]    Lists models from an external LLM inference endpoint
    ...    Makes an HTTP GET request to /v1/models to verify compatibility with standard LLM API format
    ...    Validates that the response contains a "data" field with the list of available models
    [Arguments]             ${external_host}        ${workload_id}=${None}    ${api_key}=${None}
    ...                     ${timeout}=180
    ${identifier}=          Set Variable If         $workload_id is not None        ${workload_id}    temp
    ${session_name}=        Create AIM external session    ${external_host}    identifier=${identifier}

    # Add Authorization header if API key provided
    ${headers}=             Create Dictionary
    IF    "${api_key}" != "${None}"
        Set To Dictionary   ${headers}              Authorization=Bearer ${api_key}
        Log                 Using API key authentication for external endpoint    DEBUG
    END

    ${response}=            Get From AIM External Endpoint    ${session_name}    /v1/models
    ...                     headers=${headers}      expected_status=200     timeout=${timeout}

    # Verify the response follows standard LLM API format with "data" field containing model list
    ${json}=                Set Variable            ${response.json()}
    Dictionary Should Contain Key                   ${json}                 data                    msg=Response should contain 'data' field with model list

    # Extract and return the models list
    ${models}=              Get From Dictionary     ${json}                 data
    ${model_count}=         Get Length              ${models}
    RETURN                  ${models}

Get models response from external endpoint
    [Documentation]    GET /v1/models on an external endpoint and return the raw response
    ...    WITHOUT asserting the status. Lets callers distinguish a 200 listing from an
    ...    expected auth denial (401/403/404) versus unexpected errors.
    [Arguments]             ${external_host}        ${workload_id}=${None}    ${api_key}=${None}
    ...                     ${timeout}=180
    ${identifier}=          Set Variable If         $workload_id is not None        ${workload_id}    temp
    ${session_name}=        Create AIM external session    ${external_host}    identifier=${identifier}
    ${headers}=             Create Dictionary
    IF    "${api_key}" != "${None}"
        Set To Dictionary   ${headers}              Authorization=Bearer ${api_key}
    END
    ${response}=            Get From AIM External Endpoint    ${session_name}    /v1/models
    ...                     headers=${headers}      expected_status=any     timeout=${timeout}
    RETURN                  ${response}

Model Supports Chat
    [Documentation]    Checks if a model supports chat interface based on metadata tags.
    ...                Returns ${True} if model supports chat, ${False} otherwise.
    ...                Uses the org.amd.silogen.model.tags field from AIM metadata labels.
    [Arguments]    ${aim_id}

    # Get AIM details to check labels (labels are in metadata for K8s CRD resources)
    ${response}=    Get AIM    ${aim_id}    expected_status=200
    ${aim_data}=    Set Variable    ${response.json()}

    # Extract tags from metadata.labels
    ${metadata}=    Get From Dictionary    ${aim_data}    metadata
    ${labels}=    Get From Dictionary    ${metadata}    labels
    ${tags}=    Get From Dictionary    ${labels}    org.amd.silogen.model.tags    default=${EMPTY}

    # Check if 'chat' is in the comma-separated tags
    ${supports_chat}=    Run Keyword And Return Status    Should Contain    ${tags}    chat

    Log    Model ${aim_id} tags: '${tags}' (supports chat: ${supports_chat})    INFO
    RETURN    ${supports_chat}

Run Chat Inference
    [Documentation]    Runs a chat inference request using /v1/chat/completions endpoint.
    ...                Uses OpenAI-compatible chat completions API format.
    ...                Tests instruction-following capability (chat models should follow instructions).
    [Arguments]    ${external_host}    ${model_id}    ${workload_id}    ${api_key}=${None}

    ${identifier}=    Set Variable If    $workload_id is not None    ${workload_id}    temp
    ${session_name}=    Create AIM external session    ${external_host}    identifier=${identifier}

    ${headers}=    Create Dictionary    Content-Type=application/json

    # Add Authorization header if API key provided
    IF    "${api_key}" != "${None}"
        Set To Dictionary    ${headers}    Authorization=Bearer ${api_key}
        Log    Using API key authentication for chat inference    DEBUG
    END

    # Chat API uses messages array - test instruction following
    ${messages}=    Create List
    ${user_message}=    Create Dictionary    role=user    content=Say hello and stop
    Append To List    ${messages}    ${user_message}

    ${body}=    Create Dictionary
    ...    model=${model_id}
    ...    messages=${messages}
    ...    max_tokens=20
    ...    temperature=0.7

    ${response}=    Post To AIM External Endpoint    ${session_name}    /v1/chat/completions
    ...    headers=${headers}    json=${body}    expected_status=200    timeout=120
    ${json}=    Set Variable    ${response.json()}

    # Verify response structure (OpenAI chat completions format)
    Dictionary Should Contain Key    ${json}    choices    msg=Response should contain choices array
    ${choices}=    Get From Dictionary    ${json}    choices
    Should Be True    isinstance($choices, list)    msg=Choices should be a list
    Should Not Be Empty    ${choices}    msg=Choices array should not be empty

    ${first_choice}=    Get From List    ${choices}    0
    Dictionary Should Contain Key    ${first_choice}    message    msg=Choice should contain message
    ${message}=    Get From Dictionary    ${first_choice}    message
    Dictionary Should Contain Key    ${message}    content    msg=Message should contain content

    ${content}=    Get From Dictionary    ${message}    content
    Log    Chat inference response: ${content}    INFO

    # Verify the response contains "hello" (case-insensitive)
    ${content_lower}=    Convert To Lower Case    ${content}
    Should Contain    ${content_lower}    hello    msg=Chat model should respond with 'hello' when instructed to say hello

    RETURN    ${content}

Run Completion Inference
    [Documentation]    Runs a completion inference request using /v1/completions endpoint.
    ...                Uses OpenAI-compatible completions API format.
    ...                Tests text continuation capability with HTML structure.
    ...                Uses HTML prompt to avoid language-specific issues.
    [Arguments]    ${external_host}    ${model_id}    ${workload_id}    ${api_key}=${None}

    ${identifier}=    Set Variable If    $workload_id is not None    ${workload_id}    temp
    ${session_name}=    Create AIM external session    ${external_host}    identifier=${identifier}

    ${headers}=    Create Dictionary    Content-Type=application/json

    # Add Authorization header if API key provided
    IF    "${api_key}" != "${None}"
        Set To Dictionary    ${headers}    Authorization=Bearer ${api_key}
        Log    Using API key authentication for completion inference    DEBUG
    END

    # Completion API uses prompt string - test HTML continuation (language-agnostic)
    # Incomplete HTML list that should be continued with more list items
    ${body}=    Create Dictionary
    ...    model=${model_id}
    ...    prompt=<html><body><ul><li>Item 1</li><li>Item 2</li><li>Item
    ...    max_tokens=30
    ...    temperature=0.7

    ${response}=    Post To AIM External Endpoint    ${session_name}    /v1/completions
    ...    headers=${headers}    json=${body}    expected_status=200    timeout=120
    ${json}=    Set Variable    ${response.json()}

    # Verify response structure (OpenAI completions format)
    Dictionary Should Contain Key    ${json}    choices    msg=Response should contain choices array
    ${choices}=    Get From Dictionary    ${json}    choices
    Should Be True    isinstance($choices, list)    msg=Choices should be a list
    Should Not Be Empty    ${choices}    msg=Choices array should not be empty

    ${first_choice}=    Get From List    ${choices}    0
    Dictionary Should Contain Key    ${first_choice}    text    msg=Choice should contain text field

    ${text}=    Get From Dictionary    ${first_choice}    text
    Log    Completion inference response: ${text}    INFO

    # Verify the response contains HTML tags (continuation of HTML structure)
    # Check for common HTML closing tags or continuation patterns
    ${text_lower}=    Convert To Lower Case    ${text}
    ${has_li}=    Run Keyword And Return Status    Should Contain    ${text_lower}    </li>
    ${has_ul}=    Run Keyword And Return Status    Should Contain    ${text_lower}    </ul>
    ${has_html_tag}=    Evaluate    ${has_li} or ${has_ul}
    Should Be True    ${has_html_tag}    msg=Completion model should continue HTML structure with tags like </li> or </ul>

    RETURN    ${text}

Get finetunable models
    [Documentation]    GET /v1/fine-tuning/models — returns GPU-compatible finetunable
    ...                base model objects from the fine-tuning capability catalog.
    [Arguments]    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=    Service API Endpoint    aiwb    endpoint=fine-tuning/models
    ${response}=    Safe Get Request    ${endpoint}    expected_status=${expected_status}
    RETURN    ${response}
