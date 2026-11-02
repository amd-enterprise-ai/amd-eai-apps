# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for workload submission via kubectl.
...                 Phase 1: Basic workload lifecycle testing.
...                 Verifies workload status transitions (PENDING → RUNNING → COMPLETE/FAILED/TERMINATED).
...                 Uses kubectl/helm for workload submission to test the full pipeline.
Resource            ../resources/airm_workloads.resource
Resource            ../resources/airm_projects.resource
Resource            ../resources/airm_clusters.resource
Resource            resources/api/common.resource
Library             Collections
Test Setup          Initialize Workload Tracking
Test Teardown       Run Keywords
...                 Clean Up All Created Workloads    AND
...                 Clean Up All Created Projects


*** Test Cases ***
Submit simple workload and verify completion
    [Documentation]    Verify that a simple workload completes successfully.
    ...    Tests project provisioning, K8s resource creation, and status transitions.
    [Tags]    workload    lifecycle    kubectl

    # Project Setup and Provisioning
    Given a ready project with user access exists

    # Workload Preparation
    ${config}=    A simple test workload is prepared

    # Workload Submission
    When test workload is submitted via helm    ${config}    wait_for_airm=${FALSE}

    # Kubernetes Resource Verification
    Then Job should exist in project namespace
    And airm_workloads.Pod should exist for Job
    And Pod should transition to "Running"
    And airm_workloads.Job should complete successfully

    # AIRM Auto-Discovery Verification
    And workload should exist in AIRM

Submit workload that fails
    [Documentation]    Verify that a workload failure is properly detected.
    ...    Tests project provisioning and workload failure detection.
    [Tags]    workload    lifecycle    failure    kubectl

    # Project Setup and Provisioning
    Given a ready project with user access exists

    # Workload Preparation
    ${config}=    A failing workload is prepared

    # Workload Submission
    When test workload is submitted via helm    ${config}    wait_for_airm=${FALSE}

    # Kubernetes Resource Verification
    Then Job should exist in project namespace
    And airm_workloads.Pod should exist for Job
    And airm_workloads.Job should fail

    # AIRM Auto-Discovery Verification
    And workload should exist in AIRM

Submit long-running workload and terminate it
    [Documentation]    Verify that workload termination works correctly.
    ...    Tests Deployment creation and termination.
    ...
    ...    Runs in a fresh project so unrelated workloads cannot interrupt the lifecycle being tested.
    [Tags]    workload    lifecycle    termination    kubectl

    # Project Setup and Provisioning
    Given a fresh project with user access exists

    # Workload Preparation
    ${config}=    A long-running workload is prepared

    # Workload Submission
    When test workload is submitted via helm    ${config}    wait_for_airm=${FALSE}

    # Kubernetes Resource Verification
    Then Deployment should exist in project namespace
    And Pod should exist for Deployment
    And Deployment Pod should transition to "Running"

    # AIRM Auto-Discovery Verification — must run while the workload still exists. The agent
    # discovers workloads by watching the Deployment/ReplicaSet/Pod objects, so terminating
    # first deletes the very objects discovery reads and the lookup can never succeed.
    And workload should exist in AIRM

    # Termination Test
    When workload is terminated

    # AIRM soft-deletes, so a terminated workload stays visible and its termination is
    # observable as Deleting or Deleted — either is a correct outcome at this point. The
    # deletion-status check reads the workload (HTTP 200), so it also confirms it still exists.
    Then workload should report a deletion status via API
    And workload should be displayed under the deployed name

Delete workload and verify cleanup
    [Documentation]    Verify that workload deletion works correctly.
    ...    Tests K8s resource creation and cleanup via helm uninstall.
    [Tags]    workload    lifecycle    deletion    kubectl

    # Project Setup and Provisioning
    Given a ready project with user access exists

    # Workload Preparation
    ${config}=    A simple test workload is prepared

    # Workload Submission
    When test workload is submitted via helm    ${config}    wait_for_airm=${FALSE}

    # Kubernetes Resource Verification
    Then Job should exist in project namespace

    # AIRM Auto-Discovery Verification — while the workload still exists. Discovery reads the
    # Job/Pod objects, so asserting it after the uninstall relies on the deleted objects
    # lingering long enough to be seen, which is timing, not behaviour.
    And workload should exist in AIRM

    # Deletion Test
    When workload is deleted via kubectl

    # AIRM soft-deletes, so the removal is observable as Deleting or Deleted.
    Then workload should report a deletion status via API
