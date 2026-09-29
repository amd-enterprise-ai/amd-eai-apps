# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level node testing keywords for AIRM.
...                 Provides business-logic level keywords for working with cluster nodes in tests.
...                 Owns test state (TEST_* variables) and calls API resource keywords.
Resource            api/nodes.resource
Resource            airm_metrics.resource
Resource            resources/api/common.resource
Resource            resources/common/resource_resolver.resource
Resource            kubectl_verification.resource
Library             Collections
Library             String


*** Keywords ***
Cluster nodes exist in system
    [Documentation]    Ensures cluster nodes exist and stores the first node's ID.
    ...                Requires: TEST_CLUSTER_ID (set by "A cluster exists in system")
    ...                Sets: TEST_NODE_ID, TEST_NODE, TEST_NODES
    [Arguments]    ${cluster_id}=${None}

    ${id}=    The cluster    id=${cluster_id}
    ${response}=    Get cluster nodes    ${id}    expected_status=200
    ${nodes}=    Set Variable    ${response.json()['data']}

    ${node_count}=    Get Length    ${nodes}
    Should Be True    ${node_count} > 0    msg=No nodes found in cluster ${id}

    ${first_node}=    Set Variable    ${nodes[0]}

    Set Test Variable    ${TEST_NODES}    ${nodes}
    Set Test Variable    ${TEST_NODE}    ${first_node}
    Set Test Variable    ${TEST_NODE_ID}    ${first_node['id']}
    Log    Found ${node_count} nodes. Using: ${first_node['name']} (ID: ${first_node['id']})

Node details should be returned from API
    [Documentation]    Fetches a single node via API and validates the response structure.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_NODE_DETAIL
    [Arguments]    ${cluster_id}=${None}    ${node_id}=${None}

    ${cid}=    The cluster    id=${cluster_id}
    ${nid}=    The node    id=${node_id}
    ${response}=    Get cluster node    ${cid}    ${nid}    expected_status=200
    ${node}=    Set Variable    ${response.json()}

    Should Not Be Empty    ${node['id']}
    Should Not Be Empty    ${node['name']}
    Should Not Be Empty    ${node['status']}
    Should Be True    ${node['cpuMilliCores']} > 0
    Should Be True    ${node['memoryBytes']} > 0

    Set Test Variable    ${TEST_NODE_DETAIL}    ${node}
    Log    Node: ${node['name']}, status: ${node['status']}, GPUs: ${node['gpuCount']}

Node should have GPU info
    [Documentation]    Validates that the node detail includes GPU information.
    ...                Requires: TEST_NODE_DETAIL

    ${node}=    Set Variable    ${TEST_NODE_DETAIL}
    Should Be True    ${node['gpuCount']} > 0    msg=Node has no GPUs
    Should Not Be Equal    ${node['gpuInfo']}    ${None}    msg=Node GPU info is missing
    Should Not Be Empty    ${node['gpuInfo']['name']}    msg=GPU name is missing

GPU devices should be returned from API
    [Documentation]    Fetches GPU device snapshots for a node via API and validates the response.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_GPU_DEVICES
    [Arguments]    ${cluster_id}=${None}    ${node_id}=${None}

    ${cid}=    The cluster    id=${cluster_id}
    ${nid}=    The node    id=${node_id}
    ${response}=    Get node GPU devices    ${cid}    ${nid}    expected_status=200
    ${data}=    Set Variable    ${response.json()}
    ${devices}=    Set Variable    ${data['gpuDevices']}

    ${device_count}=    Get Length    ${devices}
    Should Be True    ${device_count} > 0    msg=No GPU devices found for node

    ${first}=    Set Variable    ${devices[0]}
    Should Not Be Empty    ${first['gpuUuid']}
    Should Not Be Empty    ${first['gpuId']}

    Set Test Variable    ${TEST_GPU_DEVICES}    ${devices}
    Log    Found ${device_count} GPU devices on node

GPU core utilization metrics are requested
    [Documentation]    Fetches GPU core utilization metrics for a node.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get node GPU utilization
    ...    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

GPU memory utilization metrics are requested
    [Documentation]    Fetches GPU memory utilization metrics for a node.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get node GPU memory utilization
    ...    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

GPU clock speed metrics are requested
    [Documentation]    Fetches GPU clock speed metrics for a node.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get node GPU clock speed
    ...    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Power usage metrics are requested
    [Documentation]    Fetches power usage metrics for a node.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get node power usage
    ...    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Junction temperature metrics are requested
    [Documentation]    Fetches junction temperature metrics for a node.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get node junction temperature
    ...    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Memory temperature metrics are requested
    [Documentation]    Fetches memory temperature metrics for a node.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get node memory temperature
    ...    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

PCIe bandwidth metrics are requested
    [Documentation]    Fetches PCIe bandwidth metrics for a node.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get node PCIe bandwidth
    ...    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

PCIe efficiency metrics are requested
    [Documentation]    Fetches PCIe efficiency metrics for a node.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_RESPONSE

    ${time_range}=    Get metrics time range
    ${response}=    Get node PCIe efficiency
    ...    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Node workloads metrics are requested
    [Documentation]    Fetches workloads with metrics running on a node.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_RESPONSE
    [Arguments]    ${cluster_id}=${None}    ${node_id}=${None}

    ${cid}=    The cluster    id=${cluster_id}
    ${nid}=    The node    id=${node_id}
    ${response}=    Get node workloads metrics    ${cid}    ${nid}    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}

Response should contain core GPU utilization data
    [Documentation]    Validates that the GPU core utilization response contains the expected
    ...                structure and gpuActivityPct series label on each device entry.
    ...                Requires: TEST_RESPONSE

    Response should have valid GPU device metric structure    expected_series_label=gpuActivityPct

Response should contain GPU VRAM utilization data
    [Documentation]    Validates that the GPU VRAM utilization response contains the expected
    ...                structure and vramUtilizationPct series label on each device entry.
    ...                Requires: TEST_RESPONSE

    Response should have valid GPU device metric structure    expected_series_label=vramUtilizationPct

Response should contain junction temperature data
    [Documentation]    Validates that the junction temperature response contains the expected
    ...                structure and junctionTemperatureCelsius series label on each device entry.
    ...                Requires: TEST_RESPONSE

    Response should have valid GPU device metric structure    expected_series_label=junctionTemperatureCelsius

Response should contain power usage data
    [Documentation]    Validates that the power usage response contains the expected
    ...                structure and powerWatts series label on each device entry.
    ...                Requires: TEST_RESPONSE

    Response should have valid GPU device metric structure    expected_series_label=powerWatts

Response should contain clock speed data
    [Documentation]    Validates that the clock speed response contains the expected
    ...                structure and clockSpeedMhz series label on each device entry.
    ...                Requires: TEST_RESPONSE

    VAR    ${data}    ${TEST_RESPONSE.json()}
    Validate GPU device metric response structure    ${data}
    Validate per-GPU metric structure    ${data}    clockSpeedMhz

Response should contain memory temperature data
    [Documentation]    Validates that the memory temperature response contains the expected
    ...                structure and memoryTemperatureCelsius series label on each device entry.
    ...                Requires: TEST_RESPONSE

    Response should have valid GPU device metric structure    expected_series_label=memoryTemperatureCelsius

Response should contain PCIe bandwidth data
    [Documentation]    Validates that the PCIe bandwidth response contains the expected
    ...                structure and pcieBandwidth series label on each device entry.
    ...                Requires: TEST_RESPONSE

    Response should have valid GPU device metric structure    expected_series_label=pcieBandwidth

Response should contain PCIe efficiency data
    [Documentation]    Validates that the PCIe efficiency response contains the expected
    ...                structure and pcieEfficiency series label on each device entry.
    ...                Requires: TEST_RESPONSE

    Response should have valid GPU device metric structure    expected_series_label=pcieEfficiency

Response should have valid node workloads structure
    [Documentation]    Validates that TEST_RESPONSE contains a valid node workloads response.
    ...                Requires: TEST_RESPONSE

    ${data}=    Set Variable    ${TEST_RESPONSE.json()}
    Dictionary Should Contain Key    ${data}    data

# =============================================================================
# Scenario: GPU utilization metrics endpoint
# =============================================================================

GPU utilization metrics are fetched for the node
    [Documentation]    Fetches GPU core utilization, VRAM utilization, and junction temperature
    ...                and validates each returns per-GPU device entries with timeseries data.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_GPU_UTILIZATION, TEST_GPU_VRAM, TEST_GPU_TEMPERATURE

    ${time_range}=    Get metrics time range

    ${util_resp}=    Get node GPU utilization
    ...    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    ${util_data}=    Set Variable    ${util_resp.json()}
    Dictionary Should Contain Key    ${util_data}    gpuDevices
    Dictionary Should Contain Key    ${util_data}    range
    Set Test Variable    ${TEST_GPU_UTILIZATION}    ${util_data}
    ${device_count}=    Get Length    ${util_data['gpuDevices']}
    Log    GPU utilization: ${device_count} device(s)

    ${vram_resp}=    Get node GPU memory utilization
    ...    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    ${vram_data}=    Set Variable    ${vram_resp.json()}
    Dictionary Should Contain Key    ${vram_data}    gpuDevices
    Dictionary Should Contain Key    ${vram_data}    range
    Set Test Variable    ${TEST_GPU_VRAM}    ${vram_data}
    ${device_count}=    Get Length    ${vram_data['gpuDevices']}
    Log    GPU VRAM utilization: ${device_count} device(s)

    ${temp_resp}=    Get node junction temperature
    ...    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}
    ...    ${time_range}[start]    ${time_range}[end]
    ...    expected_status=200
    ${temp_data}=    Set Variable    ${temp_resp.json()}
    Dictionary Should Contain Key    ${temp_data}    gpuDevices
    Dictionary Should Contain Key    ${temp_data}    range
    Set Test Variable    ${TEST_GPU_TEMPERATURE}    ${temp_data}
    ${device_count}=    Get Length    ${temp_data['gpuDevices']}
    Log    GPU temperature: ${device_count} device(s)

Each GPU metric response should have per-device entries
    [Documentation]    Validates that utilization, VRAM, and temperature responses each contain
    ...                per-GPU device entries with gpuUuid, hostname, gpuId, and a metric timeseries.
    ...                Requires: TEST_GPU_UTILIZATION, TEST_GPU_VRAM, TEST_GPU_TEMPERATURE

    Validate per-GPU metric structure    ${TEST_GPU_UTILIZATION}    gpuActivityPct
    Validate per-GPU metric structure    ${TEST_GPU_VRAM}    vramUtilizationPct
    Validate per-GPU metric structure    ${TEST_GPU_TEMPERATURE}    junctionTemperatureCelsius

# =============================================================================
# Scenario: Per-node GPU data
# =============================================================================

Multiple nodes with GPUs exist in cluster
    [Documentation]    Ensures cluster has nodes and at least one has GPUs.
    ...                Requires: TEST_CLUSTER_ID
    ...                Sets: TEST_NODES, TEST_GPU_NODE, TEST_NODE_ID

    ${response}=    Get cluster nodes    ${TEST_CLUSTER_ID}    expected_status=200
    ${nodes}=    Set Variable    ${response.json()['data']}
    ${node_count}=    Get Length    ${nodes}
    Should Be True    ${node_count} > 0    msg=No nodes found in cluster

    VAR    ${gpu_node}    ${None}
    FOR    ${n}    IN    @{nodes}
        IF    ${n['gpuCount']} > 0
            ${gpu_node}=    Set Variable    ${n}
            BREAK
        END
    END

    Should Not Be Equal    ${gpu_node}    ${None}    msg=No GPU nodes found in cluster

    Set Test Variable    ${TEST_NODES}    ${nodes}
    Set Test Variable    ${TEST_GPU_NODE}    ${gpu_node}
    Set Test Variable    ${TEST_NODE_ID}    ${gpu_node['id']}
    Log    Found ${node_count} node(s), using GPU node: ${gpu_node['name']} (${gpu_node['gpuCount']} GPUs)

Node details are fetched for the GPU node
    [Documentation]    Fetches single node detail and validates CPU, memory, and GPU info are present.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_NODE_DETAIL

    ${response}=    Get cluster node    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}    expected_status=200
    ${node}=    Set Variable    ${response.json()}

    Should Not Be Empty    ${node['id']}
    Should Not Be Empty    ${node['name']}
    Should Not Be Empty    ${node['status']}
    Should Be True    ${node['cpuMilliCores']} > 0    msg=CPU milli-cores should be > 0
    Should Be True    ${node['memoryBytes']} > 0    msg=Memory bytes should be > 0
    Should Be True    ${node['gpuCount']} > 0    msg=GPU count should be > 0
    Should Not Be Equal    ${node['gpuInfo']}    ${None}    msg=GPU info should not be null
    Should Not Be Empty    ${node['gpuInfo']['name']}    msg=GPU product name should not be empty

    Set Test Variable    ${TEST_NODE_DETAIL}    ${node}
    Log    Node ${node['name']}: ${node['cpuMilliCores']}m CPU, ${node['memoryBytes']} bytes RAM, ${node['gpuCount']} GPUs (${node['gpuInfo']['name']})

GPU devices snapshot should contain per-device metrics
    [Documentation]    Fetches GPU device snapshots and validates per-device fields.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_GPU_DEVICES

    ${response}=    Get node GPU devices    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}    expected_status=200
    ${data}=    Set Variable    ${response.json()}
    ${devices}=    Set Variable    ${data['gpuDevices']}

    ${device_count}=    Get Length    ${devices}
    Should Be True    ${device_count} > 0    msg=No GPU devices found on node

    FOR    ${device}    IN    @{devices}
        Should Not Be Empty    ${device['gpuUuid']}    msg=GPU device missing gpuUuid
        Should Not Be Empty    ${device['gpuId']}    msg=GPU device missing gpuId
        Dictionary Should Contain Key    ${device}    temperature
        Dictionary Should Contain Key    ${device}    powerConsumption
        Dictionary Should Contain Key    ${device}    vramUtilization
    END

    Set Test Variable    ${TEST_GPU_DEVICES}    ${devices}
    Log    Found ${device_count} GPU device(s) with per-device metrics

# =============================================================================
# Scenario: Per-workload GPU data
# =============================================================================

Node workloads metrics are fetched
    [Documentation]    Fetches workloads running on a node and stores the data for validation.
    ...                Requires: TEST_CLUSTER_ID, TEST_NODE_ID
    ...                Sets: TEST_NODE_WORKLOADS

    ${response}=    Get node workloads metrics    ${TEST_CLUSTER_ID}    ${TEST_NODE_ID}    expected_status=200
    ${data}=    Set Variable    ${response.json()}
    Dictionary Should Contain Key    ${data}    data

    Set Test Variable    ${TEST_NODE_WORKLOADS}    ${data['data']}
    ${workload_count}=    Get Length    ${data['data']}
    Log    Found ${workload_count} workload(s) on node

Workloads should have GPU device details
    [Documentation]    If workloads are present, validates each has gpuDevices with gpuId and hostname.
    ...                Requires: TEST_NODE_WORKLOADS

    ${workload_count}=    Get Length    ${TEST_NODE_WORKLOADS}
    IF    ${workload_count} == 0
        Log    No workloads on this node — skipping per-GPU validation    WARN
        RETURN
    END

    FOR    ${workload}    IN    @{TEST_NODE_WORKLOADS}
        Should Not Be Empty    ${workload['id']}    msg=Workload missing id
        Dictionary Should Contain Key    ${workload}    gpuCount
        Dictionary Should Contain Key    ${workload}    vram
        Dictionary Should Contain Key    ${workload}    gpuDevices

        ${gpu_devices}=    Set Variable    ${workload['gpuDevices']}
        ${device_count}=    Get Length    ${gpu_devices}
        Should Be True    ${device_count} > 0
        ...    msg=Workload ${workload['id']} has gpuCount but no gpuDevices

        FOR    ${device}    IN    @{gpu_devices}
            Should Not Be Empty    ${device['gpuId']}    msg=GPU device missing gpuId
            Should Not Be Empty    ${device['hostname']}    msg=GPU device missing hostname
        END
        ${display_name}=    Get From Dictionary    ${workload}    displayName    default=${workload['id']}
        Log    Workload ${display_name}: ${device_count} GPU device(s)
    END

The cluster should have GPU nodes
    [Documentation]    Validates that the cluster has at least one node with GPUs.
    ...                Requires: TEST_NODES

    ${nodes}=    Set Variable    ${TEST_NODES}

    VAR    ${found_gpu_node}    ${False}
    FOR    ${n}    IN    @{nodes}
        IF    ${n['gpuCount']} > 0
            ${found_gpu_node}=    Set Variable    ${True}
            Log    GPU node found: ${n['name']} with ${n['gpuCount']} GPU(s)
        END
    END
    Should Be True    ${found_gpu_node}    msg=No nodes with GPUs found in cluster

# =============================================================================
# Scenario: NVIDIA GPU node detection
# =============================================================================

A node running the NVIDIA device plugin exists
    [Documentation]    Finds a Kubernetes node that advertises nvidia.com/gpu capacity and stores
    ...                what the device plugin and GPU Feature Discovery report for it.
    ...                Skips the test when the cluster has no such node.
    ...                Sets: TEST_NVIDIA_NODE_NAME, TEST_NVIDIA_GPU_COUNT,
    ...                TEST_NVIDIA_GPU_PRODUCT, TEST_NVIDIA_GPU_MEMORY_MIB

    ${nodes}=    NVIDIA GPU nodes from Kubernetes
    ${count}=    Get Length    ${nodes}
    Skip If    ${count} == 0    No node in this cluster advertises nvidia.com/gpu capacity

    ${node}=    Set Variable    ${nodes[0]}
    ${labels}=    Set Variable    ${node['metadata'].get('labels', {})}

    Set Test Variable    ${TEST_NVIDIA_NODE_NAME}    ${node['metadata']['name']}
    Set Test Variable    ${TEST_NVIDIA_GPU_COUNT}    ${node['status']['capacity']['nvidia.com/gpu']}
    Set Test Variable    ${TEST_NVIDIA_GPU_PRODUCT}    ${labels.get('nvidia.com/gpu.product')}
    Set Test Variable    ${TEST_NVIDIA_GPU_MEMORY_MIB}    ${labels.get('nvidia.com/gpu.memory')}
    Log    NVIDIA node ${TEST_NVIDIA_NODE_NAME}: ${TEST_NVIDIA_GPU_COUNT} GPU(s), product=${TEST_NVIDIA_GPU_PRODUCT}, memory=${TEST_NVIDIA_GPU_MEMORY_MIB} MiB

The NVIDIA node is fetched from the API
    [Documentation]    Looks up the NVIDIA node by name in the AIRM cluster node list and fetches its detail.
    ...                Requires: TEST_CLUSTER_ID, TEST_NVIDIA_NODE_NAME
    ...                Sets: TEST_NODE_ID, TEST_NODE_DETAIL

    ${response}=    Get cluster nodes    ${TEST_CLUSTER_ID}    expected_status=200
    VAR    ${match}    ${None}
    FOR    ${n}    IN    @{response.json()['data']}
        IF    '${n['name']}' == '${TEST_NVIDIA_NODE_NAME}'
            ${match}=    Set Variable    ${n}
            BREAK
        END
    END
    Should Not Be Equal    ${match}    ${None}
    ...    msg=Node ${TEST_NVIDIA_NODE_NAME} is not registered in AIRM cluster ${TEST_CLUSTER_ID}

    ${detail}=    Get cluster node    ${TEST_CLUSTER_ID}    ${match['id']}    expected_status=200
    Set Test Variable    ${TEST_NODE_ID}    ${match['id']}
    Set Test Variable    ${TEST_NODE_DETAIL}    ${detail.json()}

Node GPU vendor should be NVIDIA
    [Documentation]    Validates the node is reported with NVIDIA GPU info.
    ...                Requires: TEST_NODE_DETAIL

    Should Not Be Equal    ${TEST_NODE_DETAIL['gpuInfo']}    ${None}
    ...    msg=Node ${TEST_NVIDIA_NODE_NAME} has no GPU info in AIRM
    Should Be Equal    ${TEST_NODE_DETAIL['gpuInfo']['vendor']}    NVIDIA

Node GPU count should match the device plugin capacity
    [Documentation]    Validates the GPU count equals the node's nvidia.com/gpu capacity.
    ...                Requires: TEST_NODE_DETAIL, TEST_NVIDIA_GPU_COUNT

    Should Be Equal As Integers    ${TEST_NODE_DETAIL['gpuCount']}    ${TEST_NVIDIA_GPU_COUNT}

Node GPU product and VRAM should match the GPU Feature Discovery labels
    [Documentation]    Validates the product name and per-device VRAM against the GPU Feature Discovery
    ...                labels (nvidia.com/gpu.product, nvidia.com/gpu.memory in MiB), when they are set.
    ...                Requires: TEST_NODE_DETAIL, TEST_NVIDIA_GPU_PRODUCT, TEST_NVIDIA_GPU_MEMORY_MIB

    ${gpu_info}=    Set Variable    ${TEST_NODE_DETAIL['gpuInfo']}
    IF    $TEST_NVIDIA_GPU_PRODUCT is not None
        ${expected_name}=    Replace String    ${TEST_NVIDIA_GPU_PRODUCT}    -    ${SPACE}
        Should Be Equal    ${gpu_info['name']}    ${expected_name}
    ELSE
        Log    nvidia.com/gpu.product label not set, skipping product check    WARN
    END
    IF    $TEST_NVIDIA_GPU_MEMORY_MIB is not None
        ${expected_bytes}=    Evaluate    int($TEST_NVIDIA_GPU_MEMORY_MIB) * 1024 * 1024
        Should Be Equal As Integers    ${gpu_info['memoryBytesPerDevice']}    ${expected_bytes}
    ELSE
        Log    nvidia.com/gpu.memory label not set, skipping VRAM check    WARN
    END
