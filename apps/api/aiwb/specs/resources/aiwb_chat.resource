# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level keywords for the AIWB chattable inference listing.
...                 Both AIWB-proxied chat endpoints have been removed (AIM chat
...                 moved to a UI bypass and workload chat was dropped).
...                 What remains here are the listing helpers that let the UI
...                 discover which inference deployments are ready for chat.
Resource            api/aims.resource
Resource            aiwb_aims.resource
Resource            aiwb_common.resource
Library             Collections


*** Keywords ***
# When-step keywords

Chattable AIM services are listed
    [Documentation]    Lists AIM services that are ready for chat in the current namespace.
    ...    Uses the inference capability surface with capability=chat.
    ...    Sets: TEST_RESPONSE
    ${namespace}=    Get Project Namespace
    ${response}=    List AIM Services    ${namespace}    expected_status=any    capability=chat
    VAR    ${TEST_RESPONSE}    ${response}    scope=TEST

# Then-step keywords

The running AIM should appear in chattable list
    [Documentation]    Verifies the chattable AIM services list includes the deployed AIM.
    ...    Requires: TEST_AIM_ID
    Should Be Equal As Integers    ${TEST_RESPONSE.status_code}    200
    ...    msg=Chattable request should succeed, got status ${TEST_RESPONSE.status_code}
    Variable Should Exist    ${TEST_AIM_ID}    msg=TEST_AIM_ID is not set
    ${body}=    Set Variable    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${body}    data    msg=Response should contain data field
    ${services}=    Get From Dictionary    ${body}    data

    # Find the deployed AIM in the chattable list
    ${found}=    Set Variable    ${False}
    FOR    ${service}    IN    @{services}
        ${service_id}=    Get From Dictionary    ${service}    id
        IF    "${service_id}" == "${TEST_AIM_ID}"
            ${found}=    Set Variable    ${True}
            BREAK
        END
    END
    Should Be True    ${found}
    ...    msg=Running AIM ${TEST_AIM_ID} should appear in chattable services list
