# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       E2E test scenarios for cluster node GPU metrics via the AIRM API.
...                 Covers GPU utilization metrics, per-node GPU data, and per-workload GPU data.
...                 All tests hit real API endpoints against a live cluster.
Resource            ../resources/airm_nodes.resource
Resource            ../resources/airm_clusters.resource
Resource            ../resources/airm_metrics.resource
Library             Collections


*** Test Cases ***
# =============================================================================
# Scenario 1: GPU utilization metrics endpoint
# =============================================================================

GPU utilization metrics return per-GPU utilization, VRAM, and temperature
    [Documentation]    Verify that querying GPU utilization metrics for a node returns
    ...    per-GPU utilization, VRAM usage, and temperature data for each GPU device.
    [Tags]    nodes    metrics    gpu    smoke

    Given a cluster exists in system
    And cluster nodes exist in system

    When GPU utilization metrics are fetched for the node

    Then each GPU metric response should have per-device entries

GPU core utilization metrics return valid response
    [Documentation]    Verify the GPU core utilization endpoint returns 200 with expected structure.
    [Tags]    nodes    metrics    gpu

    Given a cluster exists in system
    And cluster nodes exist in system

    When GPU core utilization metrics are requested

    Then response should contain core GPU utilization data

GPU memory utilization metrics return valid response
    [Documentation]    Verify the GPU VRAM utilization endpoint returns 200 with expected structure.
    [Tags]    nodes    metrics    gpu    vram

    Given a cluster exists in system
    And cluster nodes exist in system

    When GPU memory utilization metrics are requested

    Then response should contain GPU VRAM utilization data

Junction temperature metrics return valid response
    [Documentation]    Verify the GPU junction temperature endpoint returns 200 with expected structure.
    [Tags]    nodes    metrics    temperature    gpu

    Given a cluster exists in system
    And cluster nodes exist in system

    When junction temperature metrics are requested

    Then response should contain junction temperature data

Power usage metrics return valid response
    [Documentation]    Verify the GPU power usage endpoint returns 200 with expected structure.
    [Tags]    nodes    metrics    power    gpu

    Given a cluster exists in system
    And cluster nodes exist in system

    When power usage metrics are requested

    Then response should contain power usage data

GPU clock speed metrics return valid response
    [Documentation]    Verify the GPU clock speed endpoint returns 200 with expected structure.
    [Tags]    nodes    metrics    gpu

    Given a cluster exists in system
    And cluster nodes exist in system

    When GPU clock speed metrics are requested

    Then response should contain clock speed data

Memory temperature metrics return valid response
    [Documentation]    Verify the GPU memory temperature endpoint returns 200 with expected structure.
    [Tags]    nodes    metrics    temperature    gpu

    Given a cluster exists in system
    And cluster nodes exist in system

    When memory temperature metrics are requested

    Then response should contain memory temperature data

PCIe bandwidth metrics return valid response
    [Documentation]    Verify the PCIe bandwidth endpoint returns 200 with expected structure.
    [Tags]    nodes    metrics    pcie    gpu

    Given a cluster exists in system
    And cluster nodes exist in system

    When PCIe bandwidth metrics are requested

    Then response should contain PCIe bandwidth data

PCIe efficiency metrics return valid response
    [Documentation]    Verify the PCIe efficiency endpoint returns 200 with expected structure.
    [Tags]    nodes    metrics    pcie    gpu

    Given a cluster exists in system
    And cluster nodes exist in system

    When PCIe efficiency metrics are requested

    Then response should contain PCIe efficiency data


# =============================================================================
# Scenario 2: Per-node GPU data
# =============================================================================

Per-node details return CPU, memory, and GPU metrics
    [Documentation]    Verify that requesting a specific node's details via the API returns
    ...    node-level metrics including CPU cores, memory, GPU count, and GPU info.
    [Tags]    nodes    details    gpu    smoke

    Given a cluster exists in system
    And multiple nodes with GPUs exist in cluster

    When node details are fetched for the GPU node

    Then GPU devices snapshot should contain per-device metrics

Node list returns nodes with GPU information
    [Documentation]    Verify that listing cluster nodes returns nodes with GPU counts.
    [Tags]    nodes    list    gpu

    Given a cluster exists in system
    And cluster nodes exist in system

    Then the cluster should have GPU nodes

Single node detail includes GPU info fields
    [Documentation]    Verify that a single node response contains gpuInfo with vendor and name.
    [Tags]    nodes    details    gpu

    Given a cluster exists in system
    And multiple nodes with GPUs exist in cluster

    Then node details should be returned from API
    And node should have GPU info


Node running the NVIDIA device plugin reports NVIDIA GPU info
    [Documentation]    Verify that a node exposing GPUs through the NVIDIA device plugin is reported
    ...    with vendor NVIDIA, the device plugin's GPU count, and the product name and VRAM from
    ...    the GPU Feature Discovery labels. Needs a cluster with an NVIDIA GPU node; skipped otherwise.
    [Tags]    nodes    details    gpu    nvidia    skip-in-ci

    Given a cluster exists in system
    And a node running the NVIDIA device plugin exists

    When the NVIDIA node is fetched from the API

    Then node GPU vendor should be NVIDIA
    And node GPU count should match the device plugin capacity
    And node GPU product and VRAM should match the GPU Feature Discovery labels


# =============================================================================
# Scenario 3: Per-workload GPU data
# =============================================================================

Per-workload GPU metrics return per-GPU device data
    [Documentation]    Verify that requesting workload metrics on a node returns per-GPU
    ...    utilization metrics for each workload, including gpuId and hostname.
    ...    Note: This endpoint requires platform administrator access.
    [Tags]    nodes    workloads    gpu    admin    smoke

    Given a cluster exists in system
    And cluster nodes exist in system

    When node workloads metrics are fetched

    Then workloads should have GPU device details

Node workloads endpoint returns valid response structure
    [Documentation]    Verify the workloads metrics endpoint returns 200 with a data array.
    [Tags]    nodes    workloads    admin

    Given a cluster exists in system
    And cluster nodes exist in system

    When node workloads metrics are requested

    Then response should have valid node workloads structure
