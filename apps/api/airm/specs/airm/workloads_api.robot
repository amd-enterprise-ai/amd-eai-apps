# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for workload submission via AIRM API.
...                 Tests workload lifecycle using the AIRM API POST /workloads endpoint (direct manifest submission).
...                 Verifies that workloads submitted via API are visible via API queries.
...                 This tests the API-to-API path, not the auto-discovery mechanism.
Resource            ../resources/airm_workloads.resource
Resource            ../resources/airm_projects.resource
Resource            ../resources/airm_clusters.resource
Resource            resources/api/common.resource
Resource            ../resources/api/workloads.resource
Library             Collections
Test Teardown       Clean Up Workload API Test Resources

*** Keywords ***
Clean Up Workload API Test Resources
    [Documentation]    Clean up all resources created during workload API tests
    Clean Up All Created Workloads Via API
    Clean Up All Created Projects


*** Test Cases ***
Submit workload via API and verify in API
    [Documentation]    Verify that a workload submitted via AIRM API with direct manifest appears in API queries
    ...    Tests: POST /workloads (with manifest) → GET /workloads/{id}
    [Tags]    workload    api    smoke

    Given a ready project with user access exists

    When workload is submitted with manifest via AIRM API

    Then workload should be visible via API
    And workload should have valid ID and status via API

Submit multiple workloads via API
    [Documentation]    Verify that multiple workloads can be submitted and queried via API
    ...    Tests: POST /workloads (multiple, with manifests) → GET /workloads
    ...    Uses a dedicated project to avoid counting workloads from other tests
    [Tags]    workload    api    multiple

    Given a ready project "multi-workloads-test" with user access exists

    When workload is submitted with manifest via AIRM API    display_name=test-workload-1
    And workload is submitted with manifest via AIRM API    display_name=test-workload-2
    And workload is submitted with manifest via AIRM API    display_name=test-workload-3

    Then "3" workloads should be visible via API list endpoint

Delete workload via API
    [Documentation]    Verify that workloads can be deleted via AIRM API
    ...    Tests: POST /workloads (with manifest) → DELETE /workloads/{id}
    ...    Uses stable manifest with sleep infinity to ensure workload stays alive
    [Tags]    workload    api    deletion

    Given a ready project with user access exists

    When workload is submitted with manifest via AIRM API
    ...    manifest_path=${CURDIR}/../test_data/manifests/stable-test-deployment.yaml
    ...    display_name=stable-delete-test
    Then workload should be visible via API

    When workload is deleted via AIRM API
    Then workload should report a deletion status via API

Submit workload and verify initial status is pending
    [Documentation]    Verify that a newly submitted workload has initial status PENDING
    ...    Tests: POST /workloads → initial status is PENDING
    [Tags]    workload    api    status    smoke

    Given a ready project with user access exists

    When workload is submitted with manifest via AIRM API

    Then workload should be visible via API
    And workload status in response should be "Pending"

Submit workload and verify it transitions to running
    [Documentation]    Verify that a workload transitions from PENDING to RUNNING status
    ...    Tests: Workload submission → wait for RUNNING status
    ...    Uses stable manifest with sleep infinity to ensure workload stays running
    ...
    ...    Runs in a fresh project so unrelated workloads cannot change the lifecycle being tested.
    [Tags]    workload    api    status    smoke

    Given a fresh project with user access exists
    And workload is submitted with manifest via AIRM API
    ...    manifest_path=${CURDIR}/../test_data/manifests/stable-test-deployment.yaml
    ...    display_name=stable-transition-test
    And workload status in response should be "Pending"

    When workload should transition to "Running"

    Then workload status in response should be "Running"
