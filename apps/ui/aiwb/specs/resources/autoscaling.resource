# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for autoscaling UI features.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)
Resource            common/session.resource
Resource            pages/models_page.resource
Resource            pages/workloads_page.resource
Resource            pages/autoscaling_page.resource


*** Keywords ***
# =============================================================================
# Given keywords (preconditions)
# =============================================================================

Deploy AIM with autoscaling and wait until running
    [Documentation]    Deploys an AIM with autoscaling and waits until it reaches Running state.
    ...                Use this over "AIM is deployed with autoscaling" when the test needs
    ...                live replica data, which only loads once the service is Running.
    [Arguments]    ${min_replicas}=1    ${max_replicas}=3    ${metric}=running_requests    ${target_value}=10

    AIM is deployed with autoscaling    min_replicas=${min_replicas}    max_replicas=${max_replicas}    metric=${metric}    target_value=${target_value}
    Wait for AIM workload to be running

An AIM with autoscaling is running
    [Documentation]    Deploys an AIM with default autoscaling settings and waits until running.

    Deploy AIM with autoscaling and wait until running

Project for deployed AIM is selected
    [Documentation]    Selects the project that owns the deployed AIM.
    ...                Extracts the project name from TEST_PROJECT and selects it via the toolbar.

    Project "${TEST_PROJECT}[name]" is selected

# =============================================================================
# When keywords (actions)
# =============================================================================

User enables autoscaling in deploy wizard
    [Documentation]    Navigates to the Scaling step and enables autoscaling.

    Navigate to scaling step in deploy wizard
    Click autoscaling toggle
    Wait for autoscaling fields

User opens autoscaling settings
    [Documentation]    Opens the autoscaling settings drawer from the workload details page.

    Click settings button on scaling card
    Wait for deployment settings drawer

User expands replicas list on autoscaling card
    [Documentation]    Clicks the chevron toggle on the autoscaling card to expand the replica list.

    Click replicas toggle button
    Wait for replicas table

# =============================================================================
# Then keywords (verification)
# =============================================================================

Autoscaling toggle should be visible
    [Documentation]    Verifies that the autoscaling toggle is visible on the Scaling step.

    Navigate to scaling step in deploy wizard
    Wait for autoscaling toggle

Autoscaling toggle should be enabled
    [Documentation]    Verifies that the autoscaling toggle is in the enabled state.

    ${is_enabled}=    Check autoscaling toggle state
    Should Be True    ${is_enabled}    msg=Autoscaling toggle should be enabled

Autoscaling fields should be visible
    [Documentation]    Verifies that all autoscaling configuration fields are visible:
    ...                replica range, scaling metric, and target value.

    Wait for autoscaling fields

Workload details should show autoscaling card
    [Documentation]    Verifies that the autoscaling status card is visible on workload details page.

    ${text}=    Get scaling status card text
    Should Not Be Empty    ${text}

Autoscaling card should show replica range "${min}" to "${max}"
    [Documentation]    Verifies that the scaling card displays the correct replica range.

    ${text}=    Get scaling status card text
    Should Contain    ${text}    ${min}
    Should Contain    ${text}    ${max}

Autoscaling card should show metric "${metric}"
    [Documentation]    Verifies that the scaling card displays the correct scaling metric.

    ${text}=    Get scaling metric text
    Should Contain    ${text}    ${metric}

Autoscaling card should show target value "${target_value}"
    [Documentation]    Verifies that the scaling card displays the correct target value.

    ${text}=    Get target value text
    Should Contain    ${text}    ${target_value}

Deployment settings drawer should be open
    [Documentation]    Verifies that the deployment settings drawer is visible
    ...                and contains the autoscaling toggle.

    Wait for deployment settings drawer
    ${has_toggle}=    Check deployment settings drawer has autoscaling toggle
    Should Be True    ${has_toggle}    msg=Settings drawer should contain the autoscaling toggle

Replicas list should be visible
    [Documentation]    Verifies that the replicas table is visible on the autoscaling card.

    ${visible}=    Check replicas table visible
    Should Be True    ${visible}    msg=Replicas table should be visible after expanding

Replicas list should show at least one replica
    [Documentation]    Verifies that the replicas table contains at least one replica row.

    ${count}=    Get replica row count
    Should Be True    ${count} > 0    msg=Replicas list should show at least one replica row
