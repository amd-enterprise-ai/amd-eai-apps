# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Business-logic keywords for cluster runtime profile catalog APIs.
Resource            api/cluster.resource
Resource            resources/airm_projects.resource
Library             ClusterImageFamilies
Library             Collections


*** Keywords ***
The user requests the aim-engine image catalog
    [Documentation]    Fetches aim-engine image families for runtime profile selection.
    ${response}=    List aim image families    expected_status=200
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The user requests cluster accelerators
    [Documentation]    Fetches accelerator products available on the cluster.
    ${response}=    List cluster accelerators    expected_status=200
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

The cluster reports accelerator hardware
    [Documentation]    Records reported hardware and fails when none is available to validate.
    ${accelerators}=    List cluster accelerators    expected_status=200
    VAR    ${TEST_CLUSTER_ACCELERATORS}    ${accelerators.json()}[data]    scope=TEST
    Should Not Be Empty    ${TEST_CLUSTER_ACCELERATORS}
    ...    msg=Cluster reported no accelerators; accelerator discovery is broken, so the discovered base image family cannot be validated against hardware

The user requests base image families for the reported hardware
    [Documentation]    Records the base-image catalog for comparison with reported hardware.
    ${families}=    List aim image families    expected_status=200
    VAR    ${TEST_AIM_IMAGE_FAMILIES}    ${families.json()}[data]    scope=TEST

The aim-engine image catalog includes automatic selection
    [Documentation]    Verifies Automatic is offered with no fixed repository.
    VAR    ${body}    ${TEST_RESPONSE.json()}
    ${data}=    Get From Dictionary    ${body}    data
    VAR    ${automatic}    ${None}
    FOR    ${family}    IN    @{data}
        ${family_id}=    Get From Dictionary    ${family}    familyId
        IF    '${family_id}' == 'automatic'
            VAR    ${automatic}    ${family}
            BREAK
        END
    END
    Should Not Be Equal    ${automatic}    ${None}    msg=Automatic image family missing from catalog
    ${repository}=    Get From Dictionary    ${automatic}    repository
    Should Be Equal    ${repository}    ${None}

The aim-engine image catalog lists a discovered family with repository and tags
    [Documentation]    Verifies at least one non-automatic family is present with repository and tag metadata.
    VAR    ${body}    ${TEST_RESPONSE.json()}
    ${data}=    Get From Dictionary    ${body}    data
    VAR    ${discovered_family}    ${None}
    FOR    ${family}    IN    @{data}
        ${family_id}=    Get From Dictionary    ${family}    familyId
        IF    '${family_id}' != 'automatic'
            VAR    ${discovered_family}    ${family}
            BREAK
        END
    END
    Should Not Be Equal    ${discovered_family}    ${None}
    ...    msg=No discovered (non-automatic) image family found in catalog
    Dictionary Should Contain Key    ${discovered_family}    displayName
    Dictionary Should Contain Key    ${discovered_family}    repository
    Dictionary Should Contain Key    ${discovered_family}    tags
    ${repository}=    Get From Dictionary    ${discovered_family}    repository
    Should Not Be Empty    ${repository}    msg=Discovered family should expose a repository
    ${tags}=    Get From Dictionary    ${discovered_family}    tags
    Should Not Be Empty    ${tags}    msg=Discovered family should expose at least one image tag

Accelerators are returned as a list
    [Documentation]    Verifies the response uses the standard data list envelope.
    VAR    ${body}    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${body}    data
    ${data}=    Get From Dictionary    ${body}    data
    ${is_list}=    Evaluate    isinstance($data, list)
    Should Be True    ${is_list}    msg=Accelerators response data is not a list

Each accelerator entry describes a product and capacity
    [Documentation]    When accelerators are present, each entry has product and count fields.
    ...    The canonical aim-engine model is exposed separately from the display product name.
    VAR    ${body}    ${TEST_RESPONSE.json()}
    ${data}=    Get From Dictionary    ${body}    data
    FOR    ${entry}    IN    @{data}
        Dictionary Should Contain Key    ${entry}    acceleratorType
        Dictionary Should Contain Key    ${entry}    deviceId
        Dictionary Should Contain Key    ${entry}    productName
        Dictionary Should Contain Key    ${entry}    acceleratorVendor
        Dictionary Should Contain Key    ${entry}    allocatableCount
        Dictionary Should Contain Key    ${entry}    acceleratorModel
    END

The required base image families should be available
    [Documentation]    Cross-references the two catalogs: every base-image family class the
    ...    cluster's own reported accelerators require must appear among the discovered
    ...    non-automatic families. Required classes are derived by the same mapping the backend
    ...    applies: any Radeon GPU requires the Radeon family, any other GPU the default family,
    ...    and any EPYC CPU the EPYC family; non-GPU/CPU accelerators contribute no family, and
    ...    an otherwise-empty result falls back to the default. Extra supported families are
    ...    allowed. Self-describing, so it holds on any hardware without a per-environment lookup.
    ...    Requires: ${TEST_CLUSTER_ACCELERATORS}, ${TEST_AIM_IMAGE_FAMILIES}
    Discovered Families Should Cover Cluster Hardware
    ...    ${TEST_CLUSTER_ACCELERATORS}    ${TEST_AIM_IMAGE_FAMILIES}
