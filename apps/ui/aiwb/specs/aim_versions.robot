# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for AIM version display across models page, deployment flow,
...                 and workload tracking views.
...
...                 Suite Efficiency Design:
...                 Uses Suite Setup/Teardown for project tracking and cleanup. Each test declares
...                 its own preconditions via Given steps (idempotent - first test creates, subsequent
...                 tests reuse). Tests needing a deployed AIM include deployment preconditions;
...                 catalog-only tests skip deployment.

# UI resources (feature layer + browser setup)
Resource            resources/common/browser_setup.resource
Resource            resources/aims.resource
Resource            resources/workloads.resource

# API resources (infrastructure preconditions, resolved via pythonpath)
Resource            resources/aiwb_aims.resource
Resource            resources/airm_projects.resource

Suite Teardown      Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
Deployed model card shows AIM version on models page
    [Documentation]    Verify that when viewing deployed models, the AIM image version
    ...                is displayed on each deployed model card.
    [Tags]    ui    aims    versions    deployed    gpu

    Given a ready project with user access exists
    And AIM is deployed
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user views deployed models
    Then deployed model "${TEST_AIM_CANONICAL_NAME}" should show version

Workload list shows AIM version for inference workloads
    [Documentation]    Verify that the workloads page shows the AIM image version
    ...                for each inference workload in the list.
    [Tags]    ui    aims    versions    workloads    gpu

    Given a ready project with user access exists
    And AIM is deployed
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on workloads page
    Then inference workload should show AIM version in list

Workload details show AIM version
    [Documentation]    Verify that opening workload details shows the AIM image version
    ...                for that specific workload.
    [Tags]    ui    aims    versions    workloads    details    gpu

    Given a ready project with user access exists
    And AIM is deployed
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on workloads page
    When user opens inference workload details
    Then workload details should show AIM version

Actions menu shows deployment version info
    [Documentation]    Verify that the actions menu on an AIM card shows deployment version
    ...                information for models that have active deployments.
    [Tags]    ui    aims    versions    catalog    gpu

    Given a ready project with user access exists
    And AIM is deployed
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user opens actions menu for "${TEST_AIM_DISPLAY_NAME}"
    Then actions menu should be visible
    And actions menu should show version info

Deploy wizard includes AIM version selector
    [Documentation]    Verify that the deployment wizard includes a version selector
    ...                allowing the user to choose which AIM version to deploy.
    [Tags]    ui    aims    versions    deploy

    Given a ready project with user access exists
    And an AIM exists in system
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user opens deploy wizard for "${TEST_AIM_DISPLAY_NAME}"
    Then deploy wizard should be open
    And version selector should be visible in deploy wizard

Deploy wizard defaults to latest AIM version
    [Documentation]    Verify that when opening the deploy wizard, the version selector
    ...                defaults to the latest available version.
    [Tags]    ui    aims    versions    deploy    selection

    Given a ready project with user access exists
    And an AIM exists in system
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user opens deploy wizard for "${TEST_AIM_DISPLAY_NAME}"
    Then deploy wizard should be open
    And selected version should contain "Latest"
