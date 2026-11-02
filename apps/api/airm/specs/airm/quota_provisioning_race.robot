# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Regression scenarios for project quota provisioning.
Resource            ../resources/airm_quota_provisioning_race.resource
Test Setup          An isolated cluster is ready for a new project
Test Teardown       Clean up quota provisioning race test
Suite Teardown      Cleanup All Port Forwards


*** Test Cases ***
A new project survives an early quota snapshot
    [Documentation]    A project must not fail when the cluster reports allocations before
    ...                the project's quota has reached the cluster.
    [Tags]    quotas    create    regression
    Given a new project is still being provisioned
    When the cluster reports an allocation snapshot without the new project
    Then the project remains in progress and finishes ready instead of failing

A raised quota survives a lagging allocation snapshot
    [Documentation]    A project must not fail when the cluster still reports the previous
    ...                allocation after its quota has been raised.
    [Tags]    quotas    update    regression
    Given a provisioned project with a confirmed quota exists
    When the project quota is raised
    And the cluster reports the previous allocation
    Then the project remains in progress and finishes ready with the raised quota

A quota failure is always explained and stops being reported once it recovers
    [Documentation]    A failure the cluster does not explain must still be explained to the
    ...                user, and a recovered quota must stop reporting it.
    [Tags]    quotas    status    regression
    Given a new project is still being provisioned
    When the cluster reports a quota failure without saying why
    Then the project explains the failure and stops explaining it once the quota recovers
