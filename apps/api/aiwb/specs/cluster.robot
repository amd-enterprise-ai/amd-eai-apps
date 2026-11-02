# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Runtime profile catalog APIs for aim-engine images and cluster accelerators.
Resource            resources/aiwb_cluster.resource


*** Test Cases ***
User can see aim-engine image options for runtime profiles
    [Documentation]    The workbench exposes a catalog of aim-engine image families,
    ...    including Automatic and a cluster-discovered family, for runtime profile configuration.
    [Tags]    cluster    smoke    list    skip-in-ci

    Given a ready project with user access exists
    When the user requests the aim-engine image catalog
    Then response status should be 200
    And the aim-engine image catalog includes automatic selection
    And the aim-engine image catalog lists a discovered family with repository and tags

User can see accelerators available on the cluster
    [Documentation]    The workbench reports accelerator products in a list. The endpoint
    ...    permits an empty list when no aim-accelerator node labels are present; the separate
    ...    hardware/family assertion requires a non-empty list because it cannot validate an
    ...    image family without reported hardware.
    [Tags]    cluster    smoke    list    skip-in-ci

    Given a ready project with user access exists
    When the user requests cluster accelerators
    Then response status should be 200
    And accelerators are returned as a list
    And each accelerator entry describes a product and capacity

Base image families match the cluster accelerator hardware
    [Documentation]    The workbench exposes every base-image family the cluster's
    ...    accelerator hardware requires. Runs on real hardware, so expectations come
    ...    from the cluster's reported accelerators rather than per-environment values.
    [Tags]    cluster    smoke    list    skip-in-ci

    Given a ready project with user access exists
    And the cluster reports accelerator hardware
    When the user requests base image families for the reported hardware
    Then the required base image families should be available
