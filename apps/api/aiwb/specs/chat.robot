# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for the AIWB chattable inference listing.
...                 The AIWB-proxied chat endpoints have been removed: AIM service
...                 chat moved to the UI direct-to-AIM bypass, and
...                 generic workload chat was dropped. This suite now
...                 only verifies the chattable inference listing surface used by
...                 the UI to discover chat-capable deployments. The external
...                 OpenAI-compatible endpoints are tested in api_keys.robot.
Resource            resources/aiwb_chat.resource
Resource            resources/aiwb_aims.resource
Resource            resources/airm_keywords.resource
Resource            resources/airm_projects.resource
Suite Teardown      Clean Up All Tracked Resources


*** Test Cases ***
Chattable AIM services only include ready models
    [Documentation]    Verify that listing inference deployments with the chat capability
    ...    filter returns only AIMs whose serving stack is fully ready
    ...    (InferenceServiceReady and HTTPRouteReady). A running AIM should appear in the list.
    [Tags]    chat    aims    chattable    gpu

    Given a ready project with user access exists
    And the project has GPU quota available
    And AIM is deployed and running
    When chattable AIM services are listed
    Then response status should be 200
    And the running AIM should appear in chattable list
