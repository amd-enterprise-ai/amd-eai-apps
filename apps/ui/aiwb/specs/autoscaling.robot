# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for autoscaling features in AIWB.
...                 Tests verify autoscaling configuration in deployment flow
...                 and autoscaling status display in workload details.
...
...                 Suite Efficiency Design:
...                 Uses Suite Setup/Teardown for project tracking and cleanup. Each test declares
...                 its own preconditions via Given steps (idempotent - first test creates, subsequent
...                 tests reuse). Tests deploy AIMs with and without autoscaling to verify both states.

# UI resources (feature layer + browser setup)
Resource            resources/common/browser_setup.resource
Resource            resources/aims.resource
Resource            resources/workloads.resource
Resource            resources/autoscaling.resource

# API resources (infrastructure preconditions, resolved via pythonpath)
Resource            resources/aiwb_aims.resource
Resource            resources/airm_projects.resource

Suite Teardown      Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
Deploy wizard shows autoscaling toggle
    [Documentation]    Verify that the deployment wizard includes an autoscaling toggle
    ...                that can be enabled to show autoscaling configuration fields.
    [Tags]    ui    autoscaling    deploy

    Given a ready project with user access exists
    And an AIM exists in system
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user opens deploy wizard for "${TEST_AIM_DISPLAY_NAME}"
    Then deploy wizard should be open
    And autoscaling toggle should be visible

Deploy wizard shows autoscaling configuration when enabled
    [Documentation]    Verify that enabling the autoscaling toggle displays
    ...                all autoscaling configuration fields.
    [Tags]    ui    autoscaling    deploy    fields

    Given a ready project with user access exists
    And an AIM exists in system
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    And user opens deploy wizard for "${TEST_AIM_DISPLAY_NAME}"
    When user enables autoscaling in deploy wizard
    Then autoscaling toggle should be enabled
    And autoscaling fields should be visible

Deployed workload shows autoscaling status card
    [Documentation]    Verify that when an AIM is deployed with autoscaling enabled,
    ...                the workload details page displays the autoscaling status card
    ...                showing current scaling configuration and replica counts.
    [Tags]    ui    autoscaling    workloads    details    gpu

    Given a ready project with user access exists
    And AIM is deployed with autoscaling    min_replicas=1    max_replicas=3    metric=running_requests    target_value=10
    And user is logged in
    And project for deployed AIM is selected
    When user opens inference workload details
    Then workload details should show autoscaling card
    And autoscaling card should show replica range "1" to "3"
    And autoscaling card should show metric "Running requests"
    And autoscaling card should show target value "10"

Deployed workload displays custom autoscaling configuration
    [Documentation]    Verify that when an AIM is deployed with custom autoscaling configuration
    ...                (non-default replica range, metric, and target value), the workload details
    ...                page correctly displays all configured values on the autoscaling status card.
    ...                This validates the full round-trip: API deployment → K8s → UI display.
    [Tags]    ui    autoscaling    workloads    details    configuration    gpu

    Given a ready project with user access exists
    And AIM is deployed with autoscaling    min_replicas=2    max_replicas=5    metric=running_requests    target_value=20
    And user is logged in
    And project for deployed AIM is selected
    When user opens inference workload details
    Then workload details should show autoscaling card
    And autoscaling card should show replica range "2" to "5"
    And autoscaling card should show metric "Running requests"
    And autoscaling card should show target value "20"

Autoscaling settings drawer opens from status card
    [Documentation]    Verify that the autoscaling status card has a Settings button
    ...                that opens the deployment settings drawer for updating autoscaling configuration.
    [Tags]    ui    autoscaling    workloads    settings    gpu

    Given a ready project with user access exists
    And AIM is deployed with autoscaling    min_replicas=1    max_replicas=3    metric=running_requests    target_value=10
    And user is logged in
    And project for deployed AIM is selected
    And user opens inference workload details
    When user opens autoscaling settings
    Then deployment settings drawer should be open

Running workload shows expandable replica list
    [Documentation]    Verify that when an AIM is running with autoscaling, the autoscaling
    ...                card shows a chevron button that expands to display individual replica rows.
    [Tags]    ui    autoscaling    workloads    replicas    gpu

    Given a ready project with user access exists
    And an AIM with autoscaling is running
    And user is logged in
    And project for deployed AIM is selected
    And user opens inference workload details
    When user expands replicas list on autoscaling card
    Then replicas list should be visible
    And replicas list should show at least one replica
