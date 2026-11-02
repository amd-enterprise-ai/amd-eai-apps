# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Low-level keywords for the AIWB API project artifact endpoints.
...                 Provides direct HTTP wrappers for list, detail, download, and delete.
...
...                 This is the API layer -- stateless, no TEST_* variables.
...                 All inputs arrive as explicit arguments; all state is
...                 returned to the caller.
Library             RequestsLibrary
Library             Collections
Resource            resources/api/common.resource


*** Keywords ***
Artifacts endpoint
    [Documentation]    Return the base artifact list URL for a project.
    [Arguments]    ${namespace}
    ${endpoint}=    Service API Endpoint    aiwb    endpoint=projects/${namespace}/artifacts
    RETURN    ${endpoint}

List Artifacts
    [Documentation]    Retrieve the project artifact list, passing the query params that were
    ...    provided and omitting the rest, so the default request exercises the endpoint's own
    ...    defaults rather than a spelled-out equivalent.
    ...
    ...    type and readiness are repeatable filters; pass a list to send several values.
    [Arguments]
    ...    ${namespace}
    ...    ${expected_status}=any
    ...    ${page_size}=${None}
    ...    ${type}=${None}
    ...    ${readiness}=${None}
    Create api session    aiwb
    ${endpoint}=    Artifacts endpoint    ${namespace}
    ${params}=    Create Dictionary
    IF    $page_size is not None
        Set To Dictionary    ${params}    pageSize=${page_size}
    END
    IF    $type is not None
        Set To Dictionary    ${params}    type=${type}
    END
    IF    $readiness is not None
        Set To Dictionary    ${params}    readiness=${readiness}
    END
    ${response}=    Safe Get Request    ${endpoint}    params=${params}    expected_status=${expected_status}
    RETURN    ${response}

Create Artifact With Upload
    [Documentation]    Register an artifact whose files do not exist yet, and receive an upload
    ...    location for each declared file. Registered as an adapter, the only type the endpoint
    ...    accepts.
    [Arguments]    ${namespace}    ${model_id}    ${compatible_with}    ${files}    ${description}=${None}
    ...    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=    Artifacts endpoint    ${namespace}
    ${source}=    Create Dictionary    type=upload
    ${body}=    Create Dictionary
    ...    type=adapter
    ...    source=${source}
    ...    modelId=${model_id}
    ...    compatibleWith=${compatible_with}
    ...    files=${files}
    IF    $description is not None
        Set To Dictionary    ${body}    description=${description}
    END
    ${response}=    Safe Post Request    ${endpoint}    json=${body}    expected_status=${expected_status}
    RETURN    ${response}

Create Artifact From S3 Source
    [Documentation]    Register an artifact whose files already sit at an S3 prefix. Registered as
    ...    an adapter, the only type the endpoint accepts.
    [Arguments]    ${namespace}    ${uri}    ${model_id}    ${compatible_with}    ${description}=${None}
    ...    ${rank}=${None}    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=    Artifacts endpoint    ${namespace}
    ${source}=    Create Dictionary    type=s3    uri=${uri}
    ${body}=    Create Dictionary
    ...    type=adapter
    ...    source=${source}
    ...    modelId=${model_id}
    ...    compatibleWith=${compatible_with}
    IF    $description is not None
        Set To Dictionary    ${body}    description=${description}
    END
    IF    $rank is not None
        Set To Dictionary    ${body}    rank=${rank}
    END
    ${response}=    Safe Post Request    ${endpoint}    json=${body}    expected_status=${expected_status}
    RETURN    ${response}

Create Artifact For Upload
    [Documentation]    Register an artifact whose files are still to come, receiving one upload
    ...    instruction per declared file. A caller that never uses them leaves the project owning an
    ...    artifact with nothing in its storage. Registered as an adapter, the only type the
    ...    endpoint accepts.
    [Arguments]    ${namespace}    ${model_id}    ${compatible_with}    ${files}=${None}
    ...    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=    Artifacts endpoint    ${namespace}
    IF    $files is None
        ${files}=    Create List    adapter_config.json    adapter_model.safetensors
    END
    ${source}=    Create Dictionary    type=upload
    ${body}=    Create Dictionary
    ...    type=adapter
    ...    source=${source}
    ...    modelId=${model_id}
    ...    compatibleWith=${compatible_with}
    ...    files=${files}
    ${response}=    Safe Post Request    ${endpoint}    json=${body}    expected_status=${expected_status}
    RETURN    ${response}

Get Artifact
    [Documentation]    Retrieve a single project artifact by name.
    [Arguments]    ${namespace}    ${name}    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=    Artifacts endpoint    ${namespace}
    ${response}=    Safe Get Request    ${endpoint}/${name}    expected_status=${expected_status}
    RETURN    ${response}

Download Artifact
    [Documentation]    Retrieve the download description of a single project artifact by name.
    [Arguments]    ${namespace}    ${name}    ${expected_status}=any
    Create api session    aiwb
    ${endpoint}=    Artifacts endpoint    ${namespace}
    ${response}=    Safe Get Request    ${endpoint}/${name}/download    expected_status=${expected_status}
    RETURN    ${response}

Delete Artifact
    [Documentation]    Delete a project artifact by name.
    ...    Returns 202 when accepted, 204 when already absent, 409 when still referenced.
    ...
    ...    force (bool): When True, deletes despite referencing AIMServices (default: False).
    [Arguments]    ${namespace}    ${name}    ${expected_status}=any    ${force}=${False}
    Create api session    aiwb
    ${endpoint}=    Artifacts endpoint    ${namespace}
    # force=true is only sent when requested; ${None} means no params at all, so the
    # default request exercises the guard rather than an explicit force=false.
    VAR    ${params}    ${None}
    IF    $force
        ${params}=    Create Dictionary    force=true
    END
    ${response}=    Safe Delete Request
    ...    ${endpoint}/${name}    expected_status=${expected_status}    params=${params}
    RETURN    ${response}
