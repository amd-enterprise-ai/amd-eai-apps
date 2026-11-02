# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation    Black-box executable specifications for the operator cluster environment check.
Resource         resources/environment_check.resource

Test Teardown    Clean Up Environment Check

Test Tags        cluster-environment-check    e2e


*** Test Cases ***
Scenario 1: A healthy cluster reports all clear
    [Tags]    smoke
    Given a healthy cluster
    When the operator runs the environment check
    Then the cluster should be reported healthy
    And the exit code should be 0

Scenario 2: No cluster access is not reported healthy
    Given a cluster the operator cannot reach
    When the operator runs the environment check
    Then the cluster should be reported unreachable
    And the cluster should not be reported healthy
    And the exit code should be 2

Scenario 3: Unverified Cilium MTU is not reported healthy
    Given a Cilium cluster whose MTU is left to auto-detect
    When the operator runs the environment check
    Then the cilium-mtu check should be inconclusive
    And the cluster should not be reported healthy
    And the exit code should be 3

Scenario 4: A model download that exceeded its deadline is surfaced
    Given a cluster where a model download exceeded its deadline
    When the operator runs the environment check
    Then the stuck-storage-pods check should be warn
    And the result should name DeadlineExceeded
    And the check should report problems
    And the exit code should be 1

Scenario 5: Missing GPU metrics are reported for an active workload
    Given a cluster running a GPU workload with no metrics delivered
    When the operator runs the environment check
    Then the gpu-metrics check should be warn
    And the check should report problems
    And the exit code should be 1

Scenario 6: An idle cluster does not report missing GPU metrics
    Given an idle cluster with no GPU workload
    When the operator runs the environment check
    Then the gpu-metrics check should be ok

Scenario 7: The test namespace must have usable GPU quota
    Given a cluster whose test namespace has no GPU quota
    When the operator runs the environment check
    Then the gpu-schedulable check should be warn
    And the check should report problems

Scenario 8: Unreadable routing coordinates do not fall back silently
    Given a cluster whose workbench routing coordinates cannot be read
    When the operator runs the environment check
    Then the aim-route-hostnames-ready check should be inconclusive
    And the cluster should not be reported healthy

Scenario 9: Several problems are reported together
    Given a cluster with several known problems
    When the operator runs the environment check
    Then the longhorn-health check should be warn
    And the stuck-storage-pods check should be warn
    And the check should report problems

Scenario 10: The E2E test identity missing its permissions is surfaced
    Given a cluster where the E2E test identity has no permissions
    When the operator runs the environment check
    Then the eai-e2e-rbac check should be warn
    And the check should report problems

Scenario 11: A project stuck being deleted is surfaced
    Given a cluster where a project is stuck being deleted
    When the operator runs the environment check
    Then the airm-quota-health check should be warn
    And the check should report problems

Scenario 12: The inference gateway is not reported healthy when its address cannot be read
    Given a cluster whose inference gateway address cannot be read
    When the operator runs the environment check
    Then the gateway-auth check should be inconclusive
    And the cluster should not be reported healthy

Scenario 13: Deployed products that contain the target specifications are compatible
    Given a cluster whose deployed products contain the target specifications
    When the operator runs the release-spec-skew check
    Then the release-spec-skew check should be ok
    And the exit code should be 0

Scenario 14: A deployed product that predates the target specifications is surfaced
    Given a cluster whose deployed product predates the target specifications
    When the operator runs the release-spec-skew check
    Then the release-spec-skew check should be warn
    And the check should report problems
    And the exit code should be 1

Scenario 15: An unresolvable deployed revision is not reported compatible
    Given a cluster whose deployed revision cannot be established
    When the operator runs the release-spec-skew check
    Then the release-spec-skew check should be inconclusive
    And the cluster should not be reported healthy
    And the exit code should be 3
