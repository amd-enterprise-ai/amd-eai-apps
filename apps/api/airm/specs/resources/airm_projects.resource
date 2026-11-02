# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level project testing keywords for AIRM.
...                 Provides business-logic level keywords for testing project operations.
...                 Uses the low-level API keywords from api/projects.resource to implement
...                 higher-level testing scenarios.
Resource            api/projects.resource
Resource            api/secrets.resource
Resource            resources/api/common.resource
Resource            resources/authorization.resource
Resource            airm_clusters.resource
Resource            kubectl_verification.resource
Resource            kubectl_priority_class.resource
Resource            common/airm_resource_cleanup.resource
Resource            resources/common/resource_lifecycle.resource
Resource            resources/common/resource_resolver.resource
Library             Collections
Library             String
Library             BuiltIn
Library             Process
Library             SecretLookup
Library             TestPrefix
Library             ../libraries/Quota.py


*** Variables ***
# CREATED_PROJECT_IDS is lazy-initialized by Track Project For Cleanup, and holds isolated
# projects a test created — those may be deleted by a per-test teardown. ADOPTED_PROJECT_IDS is
# lazy-initialized by Track Adopted Project For Suite Cleanup and holds shared projects, whether
# this run adopted or created them; those are deleted once, at the end of the whole directory suite.


*** Keywords ***
# Quota Preparation Keywords

Prepare Quota
    [Documentation]    Universal quota preparation with flexible parameters
    ...    Creates quota dictionary with specified resource limits.
    ...    Sets TEST_QUOTA_DATA for test consistency.
    [Arguments]    ${cpu_milli_cores}=0    ${memory_bytes}=0    ${ephemeral_storage_bytes}=0    ${gpu_count}=0

    # Convert to integers to ensure proper JSON serialization
    ${cpu_int}=    Convert To Integer    ${cpu_milli_cores}
    ${mem_int}=    Convert To Integer    ${memory_bytes}
    ${storage_int}=    Convert To Integer    ${ephemeral_storage_bytes}
    ${gpu_int}=    Convert To Integer    ${gpu_count}

    ${quota_data}=    Create Dictionary
    ...    cpuMilliCores=${cpu_int}
    ...    memoryBytes=${mem_int}
    ...    ephemeralStorageBytes=${storage_int}
    ...    gpuCount=${gpu_int}

    Set Test Variable    ${TEST_QUOTA_DATA}    ${quota_data}

    Log    Prepared quota: ${cpu_int}m CPU, ${mem_int} bytes memory, ${gpu_int} GPUs    DEBUG
    RETURN    ${quota_data}

# Convenience Keywords for Common Quota Patterns

Prepare CPU Quota Data
    [Documentation]    Prepares quota data with specific CPU allocation (convenience wrapper)
    [Arguments]    ${cpu_milli_cores}
    ${quota_data}=    Prepare Quota    cpu_milli_cores=${cpu_milli_cores}
    RETURN    ${quota_data}

Prepare Memory Quota Data
    [Documentation]    Prepares quota data with specific memory allocation (convenience wrapper)
    [Arguments]    ${memory_bytes}
    ${quota_data}=    Prepare Quota    memory_bytes=${memory_bytes}
    RETURN    ${quota_data}

Prepare Custom Quota Data
    [Documentation]    Prepares quota data with custom values for quota-specific tests.
    ...                Defaults: 4 CPU cores, 4GB RAM, 4GB storage, 0 GPUs.
    ...                DO NOT change CPU, memory, or storage to zeros - quota tests depend on non-zero values.
    ...                GPU defaults to 0 because CI runners have no GPUs.
    [Arguments]    ${cpu_milli_cores}=4000    ${memory_bytes}=4294967296    ${ephemeral_storage_bytes}=4294967296    ${gpu_count}=0
    ${quota_data}=    Prepare Quota    ${cpu_milli_cores}    ${memory_bytes}    ${ephemeral_storage_bytes}    ${gpu_count}
    RETURN    ${quota_data}

Prepare Minimum Quota
    [Documentation]    Prepares minimum quota allocation for quota-specific tests.
    ...                Uses 1 CPU core, 1GB RAM, 1GB storage, 0 GPUs.
    ...                DO NOT change CPU, memory, or storage to zeros - quota tests depend on non-zero values.
    ${quota_data}=    Prepare Quota    cpu_milli_cores=1000    memory_bytes=1073741824    ephemeral_storage_bytes=1073741824    gpu_count=0
    RETURN    ${quota_data}

Prepare Default Quota
    [Documentation]    Prepares default quota allocation (convenience wrapper)
    ${quota_data}=    Prepare Quota
    RETURN    ${quota_data}


# Universal Project Creation Keyword

Wait for project name to be available
    [Documentation]    Waits for a project name to become available (no existing project with that name)
    ...    This handles cases where a previous test's project is still being deleted
    [Arguments]    ${project_name}    ${timeout}=5 min

    Log    Checking if project name ${project_name} is available    DEBUG
    Wait Until Keyword Succeeds    ${timeout}    5 sec
    ...    Verify project name is available    ${project_name}
    Log    Project name ${project_name} is available    DEBUG

Verify project name is available
    [Documentation]    Verifies that no project with the given name exists.
    ...    A project keeps its unique name until hard deletion removes its row.
    [Arguments]    ${project_name}

    ${response}=    Get projects    expected_status=any
    Should Be True    ${response.status_code} in [200, 201]    msg=Get projects returned unexpected status ${response.status_code}
    ${response_json}=    Set variable    ${response.json()}
    ${projects}=    Set variable    ${response_json['data']}

    FOR    ${project}    IN    @{projects}
        ${name}=    Get From Dictionary    ${project}    name
        ${status}=    Get From Dictionary    ${project}    status
        IF    $name == $project_name
            Fail    Project ${project_name} still exists with status ${status}, waiting for deletion to complete
        END
    END

    Log    No project found with name ${project_name}    TRACE

Create Project With Validation
    [Documentation]    Create a basic project without user access
    ...    For projects needing user access, use "Create Project With User Access" instead
    [Arguments]    ${quota_data}=${None}    ${project_name}=${None}

    # Set default quota if none provided
    ${final_quota}=    Set Variable If    $quota_data != $None    ${quota_data}    ${EMPTY}
    IF    "${final_quota}" == ""
        ${final_quota}=    Prepare Default Quota
    END

    # Ensure prerequisites exist
    A cluster exists in system

    # If project name is specified, wait for any existing project with that name to be fully deleted
    IF    $project_name != $None
        Wait for project name to be available    ${project_name}
    END

    # Create project with the specified quota
    Set Test Variable    ${TEST_QUOTA_DATA}    ${final_quota}
    IF    $project_name != $None
        Valid project data is prepared    ${project_name}
    ELSE
        Valid project data with quota is prepared
    END
    Create project request is sent

    Project should transition to "ready"

    # Mint minio-credentials in the project namespace (configure.sh only does this for the demo
    # project at install; storage/dataset/adapter suites need it). Best-effort — it must never
    # crash setup, so a provisioning failure is logged and the MinIO-dependent tests fail instead.
    MinIO credentials are available in the current project

    Log    Project ${TEST_PROJECT}[name] (${TEST_PROJECT_ID}) created successfully    INFO

Create Project With User Access
    [Documentation]    Create a project with user access and RBAC setup
    ...    This ensures user is added to project and tokens are refreshed for RBAC
    [Arguments]    ${quota_data}=${None}    ${project_name}=${None}

    # Ensure user exists
    A user exists in system

    # Create the basic project
    Create Project With Validation    quota_data=${quota_data}    project_name=${project_name}

    # Add user with token refresh (CRITICAL for RBAC!)
    User is added to project

    Log    Project ${TEST_PROJECT}[name] (${TEST_PROJECT_ID}) created with user access    INFO

# Convenience Keywords for Common Project Patterns

A Project Exists
    [Documentation]    Creates a basic project (compatibility wrapper)
    [Arguments]    ${project_name}=${None}
    Create Project With Validation    project_name=${project_name}

A Project "${project_name}" Exists
    [Documentation]    Ensures a project with specific name exists (reuses existing or creates new)
    ...    Checks if project already exists by name, reuses it if found, creates if not.
    ...    This is an alias for Project "${project_name}" Exists In System
    Project "${project_name}" Exists In System

A Ready Project Exists
    [Documentation]    Creates a project and waits for ready state
    [Arguments]    ${project_name}=${None}
    Create Project With Validation    project_name=${project_name}

A Ready Project With User Access Exists
    [Documentation]    SYNCHRONOUS: Ensures project exists with user access and RBAC fully ready.
    ...
    ...    This keyword is BLOCKING - when it returns, the project is FULLY OPERATIONAL:
    ...    - Project exists in AIRM database
    ...    - Current user is added as member
    ...    - Keycloak tokens refreshed with new group membership
    ...    - RBAC permissions propagated (user can create resources)
    ...
    ...    This is the default keyword for most tests - uses shared prefixed "testing" project.
    ...    For tests requiring isolated/fresh projects, use "A Fresh Project With User Access Exists".
    ...    Sets: TEST_PROJECT_ID, TEST_PROJECT
    [Arguments]    ${project_name}=${None}    ${quota_data}=${None}
    IF    $project_name is None
        ${project_name}=    Test Name    testing
    END
    A user exists in system
    IF    $quota_data != $None
        Set Test Variable    ${TEST_QUOTA_DATA}    ${quota_data}
    END
    Project "${project_name}" exists in system
    A user exists in system
    User is added to project

A Ready Project With GPU Quota Exists
    [Documentation]    Ensures a project with GPU quota exists for workload/AIM tests
    ...    Sets sufficient quota for GPU-based workloads
    [Arguments]    ${project_name}=${None}
    IF    $project_name is None
        ${project_name}=    Test Name    testing
    END
    ${quota_data}=    Prepare Quota    cpu_milli_cores=8000    memory_bytes=17179869184    ephemeral_storage_bytes=21474836480    gpu_count=2
    A Ready Project With User Access Exists    ${project_name}    ${quota_data}

A Fresh Project With User Access Exists
    [Documentation]    Creates a new isolated project with random name and user access
    ...    Use this when tests require a clean/empty project state
    ...    Examples: Testing project creation count, testing empty project assertions, isolation testing
    ...    For shared testing, use "A Ready Project With User Access Exists" instead
    [Arguments]    ${quota_data}=${None}
    Create Project With User Access    quota_data=${quota_data}    project_name=${None}

A fresh project with ${gpu_count} GPU quota and user access exists
    [Documentation]    Creates a new project with specified GPU quota and user access
    ...    Quota is set during project creation (not updated afterward) to ensure Kueue sees it immediately
    ...    Uses minimal quota values to work even when cluster is heavily allocated
    ...    Jobs can still borrow additional resources via Kueue cohort borrowing
    ${quota_data}=    Prepare Quota    gpu_count=${gpu_count}    cpu_milli_cores=100    memory_bytes=134217728    ephemeral_storage_bytes=134217728
    Create Project With User Access    quota_data=${quota_data}    project_name=${None}

A Ready Project "${project_name}" With User Access Exists
    [Documentation]    Ensures a named ready project with user access exists (reuses existing or creates new)
    ...    Checks if project already exists by name, reuses it if found, creates if not.
    ...    Only sets TEST_* test-level variables for self-contained tests.
    [Arguments]    ${quota_data}=${None}
    A user exists in system
    Project "${project_name}" exists in system
    A user exists in system
    User is added to project

A Project Exists With Minimum Quota
    [Documentation]    Creates a project with minimum quota allocation
    ${quota_data}=    Prepare Minimum Quota
    Create Project With Validation    quota_data=${quota_data}

A Project Exists With Custom Quota
    [Documentation]    Creates a project with custom quota allocation
    ${quota_data}=    Prepare Quota    cpu_milli_cores=4000    memory_bytes=4294967296    ephemeral_storage_bytes=4294967296    gpu_count=0
    Create Project With Validation    quota_data=${quota_data}

A project with GPU pre-emption enabled exists
    [Documentation]    Creates a project with GPU pre-emption enabled (default settings).
    ...    Sets: TEST_PROJECT_ID, TEST_PROJECT, TEST_GPU_PREEMPTION_DATA
    [Arguments]    ${threshold}=10    ${gracePeriod}=1800    ${policy}=OnPressure
    A cluster exists in system
    Project data with gpu preemption is prepared    threshold=${threshold}    gracePeriod=${gracePeriod}    policy=${policy}
    Create project request is sent

Project With GPU Quota Exists
    [Documentation]    Creates or finds project with sufficient GPU quota for AIM deployments
    ...    Uses shared project name and includes user access. Alias for A Ready Project With GPU Quota Exists
    A Ready Project With GPU Quota Exists

Create Project With User Access And Quota
    [Documentation]    Legacy wrapper - creates project with user access and quota (maintains backward compatibility)
    [Arguments]    ${quota_data}    ${project_name}=${None}
    Create Project With Validation    quota_data=${quota_data}    project_name=${project_name}
    User is added to project

Project "${project_name}" Exists In System
    [Documentation]    Ensures a project exists in system (creates if needed, finds if exists).
    ...    Reused projects are tracked for cleanup so Suite Teardown can delete them even
    ...    if the project was originally created by a previous (possibly interrupted) run.
    ...    If project is being deleted, waits for complete deletion before creating new one.
    ...    Sets: TEST_PROJECT_ID, TEST_PROJECT

    # Find project by name using helper keyword
    ${project}=    Get Project By Name    ${project_name}

    # If not found, create it
    IF    $project == $None
        Log    Project "${project_name}" not found, creating new one    INFO
        Create Shared Project With Validation    project_name=${project_name}
        RETURN
    END

    # Found project - check its status
    ${status}=    Get From Dictionary    ${project}    status
    ${project_id}=    Get From Dictionary    ${project}    id

    # Handle non-active states explicitly
    IF    "${status}" == "Deleting"
        Log    Project "${project_name}" is Deleting, waiting for deletion to complete    INFO
        Wait Until Project Deleted    ${project_id}    timeout=3 min
        Log    Project "${project_name}" fully deleted, creating new one    INFO
        Create Shared Project With Validation    project_name=${project_name}
        RETURN
    ELSE IF    "${status}" in ["Deleted", "Failed"]
        Log    Project "${project_name}" is ${status}, creating new one    INFO
        TRY
            Delete project    ${project_id}    expected_status=any
        EXCEPT
            Log    Project ${project_id} cleanup failed, proceeding    DEBUG
        END
        Wait Until Project Deleted    ${project_id}    timeout=1 min
        Create Shared Project With Validation    project_name=${project_name}
        RETURN
    END

    # Project exists and is usable - reuse it
    Set Test Variable    ${TEST_PROJECT_ID}    ${project_id}
    Set Test Variable    ${TEST_PROJECT}    ${project}

    # Adopted, not created. Registered for run-scoped cleanup only, never for per-test cleanup:
    # creating a project and borrowing one are different acts, and only the former may be torn
    # down by the test that did it. Tracking an adopted project the same way made every suite
    # using a per-test teardown delete and recreate the shared fixed-name project once per test,
    # after which the next test's setup waited out the still in-flight deletion in the branch
    # above. The interrupted-run guarantee is preserved by Clean Up Adopted Projects.
    Track Adopted Project For Suite Cleanup    ${project_id}

    Log    Reusing existing project "${project_name}" (ID: ${TEST_PROJECT_ID})    INFO

    # Wait for project to be Ready if not already
    IF    "${status}" != "Ready"
        Log    Project "${project_name}" is ${status}, waiting for Ready    INFO
        Wait Until Keyword Succeeds    5 min    5 sec
        ...    Verify project status in any of    ready, Ready
    END

# Natural Language Keywords for BDD Tests

A Project Exists With CPU Quota "${cpu_milli_cores}"
    [Documentation]    Creates a project with specific CPU quota allocation (natural language wrapper)
    ${quota_data}=    Prepare CPU Quota Data    ${cpu_milli_cores}
    Create Project With Validation    quota_data=${quota_data}

A Ready Project With CPU Quota "${cpu_milli_cores}" And User Access Exists
    [Documentation]    Creates a ready project with specific CPU quota, user access, and token refresh (natural language wrapper)
    ${quota_data}=    Prepare CPU Quota Data    ${cpu_milli_cores}
    Create Project With Validation    quota_data=${quota_data}
    User is added to project

A Project Exists With Memory Quota "${memory_bytes}"
    [Documentation]    Creates a project with specific memory quota allocation (natural language wrapper)
    ${quota_data}=    Prepare Memory Quota Data    ${memory_bytes}
    Create Project With Validation    quota_data=${quota_data}

A Ready Project With Memory Quota "${memory_mb}" And User Access Exists
    [Documentation]    Creates a ready project with specific memory quota, user access, and token refresh (natural language wrapper)
    ${quota_data}=    Prepare Memory Quota Data    ${memory_mb}
    Create Project With Validation    quota_data=${quota_data}
    User is added to project

Valid project data is prepared
    [Documentation]    Prepares valid test data for project creation.
    ...    Sets: TEST_PROJECT_DATA
    [Arguments]    ${project_name}=${None}

    # Ensure TEST_QUOTA_DATA exists, use default if not set
    ${quota_data}=    Get Variable Value    ${TEST_QUOTA_DATA}    ${None}
    IF    $quota_data == $None
        ${quota_data}=    Prepare Quota    cpu_milli_cores=0    memory_bytes=0    ephemeral_storage_bytes=0    gpu_count=0
        Set Test Variable    ${TEST_QUOTA_DATA}    ${quota_data}
    END

    IF    $project_name == $None
        ${prefix}=    Test Prefix
        ${unique_suffix}=    Generate Random String    8    [LOWER]
        ${project_name}=    Set Variable    ${prefix}proj-${unique_suffix}
    END
    ${project_description}=    Set Variable    Test project for automated testing

    ${project_data}=    Create Dictionary
    ...    name=${project_name}
    ...    description=${project_description}
    ...    clusterId=${TEST_CLUSTER_ID}
    ...    quota=${TEST_QUOTA_DATA}

    Set Test Variable    ${TEST_PROJECT_DESC}    ${project_description}
    Set Test Variable    ${TEST_PROJECT_DATA}    ${project_data}
    Log    Prepared project data: ${project_name}    DEBUG

Project data with gpu preemption is prepared
    [Documentation]    Prepares a create-project payload with configurable GPU pre-emption settings.
    ...    Sets: TEST_PROJECT_DATA, TEST_GPU_PREEMPTION_DATA
    [Arguments]    ${threshold}=10    ${gracePeriod}=1800    ${policy}=OnPressure
    Valid project data is prepared
    ${gpu_preemption}=    Create Dictionary
    ...    enabled=${TRUE}
    ...    threshold=${threshold}
    ...    gracePeriod=${gracePeriod}
    ...    policy=${policy}
    ${project_data}=    Copy Dictionary    ${TEST_PROJECT_DATA}
    Set To Dictionary    ${project_data}    gpuPreemption=${gpu_preemption}
    Set Test Variable    ${TEST_PROJECT_DATA}    ${project_data}
    Set Test Variable    ${TEST_GPU_PREEMPTION_DATA}    ${gpu_preemption}

Valid project data with quota is prepared
    [Documentation]    Prepares valid project data with the current quota configuration.
    ...    Sets: TEST_PROJECT_DATA

    # Ensure TEST_QUOTA_DATA exists, use default if not set
    ${quota_data}=    Get Variable Value    ${TEST_QUOTA_DATA}    ${None}
    IF    $quota_data == $None
        ${quota_data}=    Prepare Quota    cpu_milli_cores=0    memory_bytes=0    ephemeral_storage_bytes=0    gpu_count=0
        Set Test Variable    ${TEST_QUOTA_DATA}    ${quota_data}
    END

    ${prefix}=    Test Prefix
    ${unique_suffix}=    Generate Random String    8    [LOWER]
    ${project_name}=    Set Variable    ${prefix}proj-${unique_suffix}
    ${project_description}=    Set Variable    Test project for automated testing

    ${project_data}=    Create Dictionary
    ...    name=${project_name}
    ...    description=${project_description}
    ...    clusterId=${TEST_CLUSTER_ID}
    ...    quota=${TEST_QUOTA_DATA}

    Set Test Variable    ${TEST_PROJECT_DESC}    ${project_description}
    Set Test Variable    ${TEST_PROJECT_DATA}    ${project_data}

# Updated Data Preparation Keywords (for project updates/modifications)

Minimum Quota Data Is Prepared
    [Documentation]    Prepares minimum quota allocation using unified approach
    ${quota_data}=    Prepare Quota    cpu_milli_cores=1000    memory_bytes=1073741824    ephemeral_storage_bytes=1073741824    gpu_count=0

Custom Quota Data Is Prepared
    [Documentation]    Prepares custom quota allocation using unified approach
    ${quota_data}=    Prepare Quota    cpu_milli_cores=4000    memory_bytes=4294967296    ephemeral_storage_bytes=4294967296    gpu_count=0

Increased Quota Data Is Prepared
    [Documentation]    Prepares increased quota allocation data for project updates
    ${quota_data}=    Prepare Quota    cpu_milli_cores=8000    memory_bytes=8589934592    ephemeral_storage_bytes=8589934592    gpu_count=0
    ${project_data}=    Create Dictionary
    ...    description=${TEST_PROJECT_DESC}
    ...    quota=${quota_data}
    Set Test Variable    ${TEST_PROJECT_DATA}    ${project_data}

Decreased Quota Data Is Prepared
    [Documentation]    Prepares decreased quota allocation data for project updates
    ${quota_data}=    Prepare Quota    cpu_milli_cores=2000    memory_bytes=2147483648    ephemeral_storage_bytes=2147483648    gpu_count=0
    ${project_data}=    Create Dictionary
    ...    description=${TEST_PROJECT_DESC}
    ...    quota=${quota_data}
    Set Test Variable    ${TEST_PROJECT_DATA}    ${project_data}

Updated CPU Quota Is Prepared
    [Documentation]    Prepares updated CPU quota allocation preserving other values
    ${current_quota}=    Set Variable    ${TEST_RESPONSE.json()['quota']}

    # Convert to integers to ensure proper JSON serialization
    ${cpu_int}=    Convert To Integer    6000

    ${quota_data}=    Create Dictionary
    ...    cpuMilliCores=${cpu_int}
    ...    memoryBytes=${current_quota['memoryBytes']}
    ...    ephemeralStorageBytes=${current_quota['ephemeralStorageBytes']}
    ...    gpuCount=${current_quota['gpuCount']}
    ${project_data}=    Create Dictionary
    ...    description=${TEST_PROJECT_DESC}
    ...    quota=${quota_data}
    Set Test Variable    ${TEST_QUOTA_DATA}    ${quota_data}
    Set Test Variable    ${TEST_PROJECT_DATA}    ${project_data}

Updated Memory Quota Is Prepared
    [Documentation]    Prepares updated memory quota allocation preserving other values
    ${current_quota}=    Set Variable    ${TEST_RESPONSE.json()['quota']}

    # Convert to integers to ensure proper JSON serialization
    ${memory_int}=    Convert To Integer    8589934592

    ${quota_data}=    Create Dictionary
    ...    cpuMilliCores=${current_quota['cpuMilliCores']}
    ...    memoryBytes=${memory_int}
    ...    ephemeralStorageBytes=${current_quota['ephemeralStorageBytes']}
    ...    gpuCount=${current_quota['gpuCount']}
    ${project_data}=    Create Dictionary
    ...    description=${TEST_PROJECT_DESC}
    ...    quota=${quota_data}
    Set Test Variable    ${TEST_QUOTA_DATA}    ${quota_data}
    Set Test Variable    ${TEST_PROJECT_DATA}    ${project_data}

Updated GPU Quota Is Prepared
    [Documentation]    Prepares the smallest GPU quota increase that fits current cluster allocations.
    ...    Polls for capacity released by asynchronous project cleanup.
    ...    Requires: TEST_CLUSTER_ID, TEST_RESPONSE
    ...    Sets: TEST_QUOTA_DATA, TEST_PROJECT_DATA
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Prepare Admissible GPU Quota Increase

Prepare Admissible GPU Quota Increase
    [Documentation]    Builds an update using live cluster quota allocation.
    ${current_quota}=    Set Variable    ${TEST_RESPONSE.json()['quota']}
    ${cluster_response}=    Get cluster    ${TEST_CLUSTER_ID}    expected_status=200
    ${cluster}=    Set Variable    ${cluster_response.json()}
    ${gpu_count}=    Next GPU Quota
    ...    ${current_quota['gpuCount']}
    ...    ${cluster['availableResources']['gpuCount']}
    ...    ${cluster['allocatedResources']['gpuCount']}

    ${quota_data}=    Create Dictionary
    ...    cpuMilliCores=${current_quota['cpuMilliCores']}
    ...    memoryBytes=${current_quota['memoryBytes']}
    ...    ephemeralStorageBytes=${current_quota['ephemeralStorageBytes']}
    ...    gpuCount=${gpu_count}
    ${project_data}=    Create Dictionary
    ...    description=${TEST_PROJECT_DESC}
    ...    quota=${quota_data}
    Set Test Variable    ${TEST_QUOTA_DATA}    ${quota_data}
    Set Test Variable    ${TEST_PROJECT_DATA}    ${project_data}

Updated Quota Data Is Prepared
    [Documentation]    Prepares updated quota data using unified approach
    ${quota_data}=    Prepare Quota    cpu_milli_cores=3000    memory_bytes=3221225472    ephemeral_storage_bytes=3221225472    gpu_count=0
    ${project_data}=    Create Dictionary
    ...    description=${TEST_PROJECT_DESC}
    ...    quota=${quota_data}
    Set Test Variable    ${TEST_PROJECT_DATA}    ${project_data}

Updated project data is prepared
    [Documentation]    Alias for backward compatibility - prepares updated project data
    Updated project data with new description is prepared

Updated project data with new description is prepared
    [Documentation]    Prepares project update data with a new description while preserving quota
    ...    Sets TEST_UPDATED_PROJECT_DESC to "Updated project description for testing"
    ${new_description}=    Set Variable    Updated project description for testing

    ${project_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    ${current_quota_response}=    Set Variable    ${project_response.json()['quota']}

    ${current_quota}=    Create Dictionary
    ...    cpuMilliCores=${current_quota_response['cpuMilliCores']}
    ...    memoryBytes=${current_quota_response['memoryBytes']}
    ...    ephemeralStorageBytes=${current_quota_response['ephemeralStorageBytes']}
    ...    gpuCount=${current_quota_response['gpuCount']}

    ${project_data}=    Create Dictionary
    ...    description=${new_description}
    ...    quota=${current_quota}

    Set Test Variable    ${TEST_UPDATED_PROJECT_DESC}    ${new_description}
    Set Test Variable    ${TEST_PROJECT_DATA}    ${project_data}

Updated project data with gpu preemption enabled is prepared
    [Documentation]    Prepares update payload enabling GPU pre-emption with default values.
    ...    Requires: TEST_PROJECT_ID
    ...    Sets: TEST_PROJECT_DATA, TEST_GPU_PREEMPTION_DATA
    [Arguments]    ${threshold}=10    ${gracePeriod}=1800    ${policy}=OnPressure
    ${project_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    VAR    ${current_quota_response}    ${project_response.json()['quota']}
    ${current_quota}=    Create Dictionary
    ...    cpuMilliCores=${current_quota_response['cpuMilliCores']}
    ...    memoryBytes=${current_quota_response['memoryBytes']}
    ...    ephemeralStorageBytes=${current_quota_response['ephemeralStorageBytes']}
    ...    gpuCount=${current_quota_response['gpuCount']}
    ${gpu_preemption}=    Create Dictionary
    ...    enabled=${TRUE}
    ...    threshold=${threshold}
    ...    gracePeriod=${gracePeriod}
    ...    policy=${policy}
    ${project_data}=    Create Dictionary
    ...    description=${project_response.json()['description']}
    ...    quota=${current_quota}
    ...    gpuPreemption=${gpu_preemption}
    Set Test Variable    ${TEST_PROJECT_DATA}    ${project_data}
    Set Test Variable    ${TEST_GPU_PREEMPTION_DATA}    ${gpu_preemption}

Updated project data with gpu preemption disabled is prepared
    [Documentation]    Prepares update payload disabling GPU pre-emption.
    ...    Requires: TEST_PROJECT_ID
    ...    Sets: TEST_PROJECT_DATA
    ${project_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    VAR    ${current_quota_response}    ${project_response.json()['quota']}
    ${current_quota}=    Create Dictionary
    ...    cpuMilliCores=${current_quota_response['cpuMilliCores']}
    ...    memoryBytes=${current_quota_response['memoryBytes']}
    ...    ephemeralStorageBytes=${current_quota_response['ephemeralStorageBytes']}
    ...    gpuCount=${current_quota_response['gpuCount']}
    ${gpu_preemption}=    Create Dictionary
    ...    enabled=${FALSE}
    ${project_data}=    Create Dictionary
    ...    description=${project_response.json()['description']}
    ...    quota=${current_quota}
    ...    gpuPreemption=${gpu_preemption}
    Set Test Variable    ${TEST_PROJECT_DATA}    ${project_data}

Updated project data with new description preserving gpu preemption is prepared
    [Documentation]    Prepares update payload with new description, preserving current GPU pre-emption and quota.
    ...    Requires: TEST_PROJECT_ID
    ...    Sets: TEST_PROJECT_DATA, TEST_UPDATED_PROJECT_DESC
    VAR    ${new_description}    Updated project description for testing
    ${project_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    VAR    ${current_quota_response}    ${project_response.json()['quota']}
    ${current_quota}=    Create Dictionary
    ...    cpuMilliCores=${current_quota_response['cpuMilliCores']}
    ...    memoryBytes=${current_quota_response['memoryBytes']}
    ...    ephemeralStorageBytes=${current_quota_response['ephemeralStorageBytes']}
    ...    gpuCount=${current_quota_response['gpuCount']}
    ${project_data}=    Create Dictionary
    ...    description=${new_description}
    ...    quota=${current_quota}
    ...    gpuPreemption=${project_response.json()['gpuPreemption']}
    Set Test Variable    ${TEST_UPDATED_PROJECT_DESC}    ${new_description}
    Set Test Variable    ${TEST_PROJECT_DATA}    ${project_data}

Create project request is sent
    [Documentation]    Sends request to create a project using prepared test data.
    ...    Note: Waits for project to be fully provisioned before returning.
    ...    Requires: TEST_PROJECT_DATA
    ...    Sets: TEST_PROJECT_ID, TEST_PROJECT, TEST_RESPONSE
    ${creation_response}=    Create project    ${TEST_PROJECT_DATA}    expected_status=200

    ${project_id}=    Get from dictionary    ${creation_response.json()}    id
    ${project_name}=    Get from dictionary    ${creation_response.json()}    name
    Set test variable    ${TEST_PROJECT_ID}    ${project_id}

    Log    Project created: ${project_name} (ID: ${project_id})    INFO
    Track Project For Cleanup    ${project_id}

    Wait Until Keyword Succeeds    2 min    2 sec
    ...    Verify project is fully provisioned

    # Fetch the fully provisioned project and store as TEST_PROJECT for attribute access
    ${provisioned_response}=    Get project    ${project_id}    expected_status=200
    Set Test Variable    ${TEST_PROJECT}    ${provisioned_response.json()}
    Set Test Variable    ${TEST_RESPONSE}    ${provisioned_response}

Verify project is fully provisioned
    [Documentation]    Helper keyword to verify project is fully provisioned with quota
    Log    Polling project ${TEST_PROJECT_ID} provisioning status    TRACE
    ${project_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200

    Dictionary should contain key    ${project_response.json()}    quota
    Log    Project ${TEST_PROJECT_ID} is fully provisioned with quota    INFO

List projects request is sent
    [Documentation]    Sends request to list all projects.
    ...    Sets: TEST_RESPONSE
    ${response}=    Get projects    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Log    Retrieved projects list    DEBUG
    RETURN    ${response}

Update project request is sent
    [Documentation]    Sends request to update an existing project.
    ...    Requires: TEST_PROJECT_ID, TEST_PROJECT_DATA
    ...    Sets: TEST_RESPONSE
    Log    Updating project ${TEST_PROJECT_ID}    INFO
    ${response}=    Update project    ${TEST_PROJECT_ID}    ${TEST_PROJECT_DATA}    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Log    Project ${TEST_PROJECT_ID} update requested    DEBUG
    RETURN    ${response}

Delete project request is sent
    [Documentation]    Sends request to delete a project.
    ...    Requires: TEST_PROJECT_ID
    ...    Sets: TEST_RESPONSE
    Log    Deleting project ${TEST_PROJECT_ID}    INFO
    ${response}=    Delete project    ${TEST_PROJECT_ID}    expected_status=any
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Log    Project ${TEST_PROJECT_ID} deletion requested    DEBUG
    RETURN    ${response}

The user deletes the project
    [Documentation]    Deletes the current project and preserves its name and identity for replacement checks.
    Set Test Variable    ${TEST_DELETED_PROJECT_ID}    ${TEST_PROJECT_ID}
    Set Test Variable    ${TEST_DELETED_PROJECT_NAME}    ${TEST_PROJECT}[name]
    Delete project request is sent
    Response status should be 204

The user creates a project with the same name
    [Documentation]    Creates a replacement after the deleted project releases its name.
    Create Project With Validation    project_name=${TEST_DELETED_PROJECT_NAME}

The replacement project should exist
    [Documentation]    Verifies that the same-named replacement is available through the API.
    Project should exist in database
    Should Be Equal    ${TEST_PROJECT}[name]    ${TEST_DELETED_PROJECT_NAME}
    ...    msg=Replacement project name differs from deleted project: ${TEST_PROJECT}[name] != ${TEST_DELETED_PROJECT_NAME}

The replacement project should have a different identity from the deleted project
    [Documentation]    Verifies that recreation produced a new project.
    Project ID Should Be Different Than "${TEST_DELETED_PROJECT_ID}"

Add users to project request is sent
    [Documentation]    Sends request to add users to a project.
    ...    Requires: TEST_PROJECT_ID, TEST_USER_ID (unless explicit args provided)
    ...    Sets: TEST_RESPONSE
    [Arguments]    ${project_id}=${None}    ${user_id}=${None}
    ${resolved_project_id}=    The project    id=${project_id}
    ${resolved_user_id}=    The user    id=${user_id}
    ${user_ids}=    Create List    ${resolved_user_id}
    ${response}=    Add users to project    ${resolved_project_id}    ${user_ids}    expected_status=204
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    RETURN    ${response}

Remove user from project request is sent
    [Documentation]    Sends request to remove a user from a project
    [Arguments]    ${project_id}=${None}    ${user_id}=${None}
    ${resolved_project_id}=    The project    id=${project_id}
    ${resolved_user_id}=    The user    id=${user_id}
    ${response}=    Remove user from project    ${resolved_project_id}    ${resolved_user_id}    expected_status=204
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    RETURN    ${response}

Project ID Should Be Different Than "${old_id}"
    [Documentation]    Verifies that the current TEST_PROJECT_ID is different from the provided ID
    ...    Used to verify a recreated project has a new ID
    Should Not Be Equal    ${TEST_PROJECT_ID}    ${old_id}
    ...    msg=Project has same ID as before: ${old_id}
    Log    New project ID ${TEST_PROJECT_ID} differs from old ID ${old_id}    INFO

Multiple projects exist
    [Documentation]    Creates multiple projects for testing list endpoints
    [Arguments]    ${count}=2

    Log    Creating ${count} test projects    INFO
    FOR    ${index}    IN RANGE    ${count}
        Log    Creating project ${index+1} of ${count}    DEBUG
        Valid project data is prepared
        Create project request is sent
    END
    Log    Successfully created ${count} projects    INFO

A project does not exist
    [Documentation]    Sets up a non-existent project ID for testing
    ${project_id}=    Evaluate    str(uuid.uuid4())    modules=uuid
    Set test variable    ${TEST_PROJECT_ID}    ${project_id}

A user exists in system
    [Documentation]    Gets the current authenticated user from the system for testing.
    ...    Decodes the JWT token to get the email, then finds that user in the system.
    ...    Requires Platform Administrator role (GET /v1/users is admin-only).
    ...    Sets: TEST_USER_ID, TEST_USER_EMAIL
    Create api session    airm

    # Get the current user's email from their JWT token
    ${token}=    Authorization token
    ${token_parts}=    Split String    ${token}    .
    ${payload_b64}=    Get From List    ${token_parts}    1
    ${payload_json}=    Evaluate    __import__('base64').b64decode('${payload_b64}' + '==').decode('utf-8')    modules=base64
    ${token_data}=    Evaluate    __import__('json').loads('''${payload_json}''')    modules=json
    ${current_user_email}=    Get From Dictionary    ${token_data}    email

    # GET /v1/users requires Platform Administrator role
    ${users_endpoint}=    Service API Endpoint    airm    endpoint=users
    ${users_response}=    Safe Get Request    ${users_endpoint}    expected_status=200
    ${users_data}=    Set Variable    ${users_response.json()}
    ${users}=    Set Variable    ${users_data['data']}

    # Find the user that matches the authenticated email
    Log    Looking for user email: ${current_user_email}    INFO
    ${user_count}=    Get Length    ${users}
    Log    Total users in list: ${user_count}    INFO
    FOR    ${user}    IN    @{users}
        ${user_email}=    Get From Dictionary    ${user}    email
        IF    '${user_email}' == '${current_user_email}'
            ${user_id}=    Get From Dictionary    ${user}    id
            Set Test Variable    ${TEST_USER_ID}    ${user_id}
            Set Test Variable    ${TEST_USER_EMAIL}    ${user_email}
            Log    Using authenticated user: ${TEST_USER_EMAIL} (ID: ${TEST_USER_ID})    INFO
            RETURN
        END
    END

    Fail    Authenticated user ${current_user_email} not found in system users list

User is added to project
    [Documentation]    GIVEN keyword - ensures user is added to project and verifies membership.
    ...    This is a precondition keyword that:
    ...    1. Adds test user to project via API
    ...    2. Refreshes tokens (CRITICAL for RBAC - Keycloak groups are embedded in JWT)
    ...    3. Verifies user is actually a member of the project
    ...    4. Initializes TEST_QUERY_PARAMS with project_id for API calls
    ...    Use this for test preconditions. For testing the add user operation itself,
    ...    use "Add users to project request is sent" followed by explicit verification.
    Add users to project request is sent
    Refresh kubectl and API tokens
    User should be member of project
    # Initialize TEST_QUERY_PARAMS with the project context for API calls
    &{query_params}=    Create dictionary    projectId=${TEST_PROJECT_ID}
    Set test variable    &{TEST_QUERY_PARAMS}    &{query_params}

Project should exist in database
    [Documentation]    Verify project exists in database by fetching it via API
    ...    Polls for project to be fully provisioned with quota
    Wait Until Keyword Succeeds    2 min    2 sec
    ...    Verify project exists in API

Verify project exists in API
    [Documentation]    Helper keyword to verify project exists and is fully provisioned
    ...    Used with polling to wait for async project creation to complete
    Log    Polling project ${TEST_PROJECT_ID} existence in API    TRACE
    ${db_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200

    Dictionary should contain key    ${db_response.json()}    id
    Dictionary should contain value    ${db_response.json()}    ${TEST_PROJECT_ID}
    Dictionary should contain key    ${db_response.json()}    name
    Dictionary should contain key    ${db_response.json()}    createdAt
    Dictionary should contain key    ${db_response.json()}    quota

    Log    Project ${TEST_PROJECT_ID} verified in API    INFO

Project GPU pre-emption should be disabled
    [Documentation]    Verifies GPU pre-emption is disabled on the current project.
    ...    Requires: TEST_PROJECT_ID
    ${project_id}=    The project
    ${response}=    Get project    ${project_id}    expected_status=200
    ${gp}=    Get From Dictionary    ${response.json()}    gpuPreemption
    ${enabled}=    Get From Dictionary    ${gp}    enabled
    Should Not Be True    ${enabled}    msg=GPU pre-emption should be disabled but is enabled

Project GPU pre-emption config should match
    [Documentation]    Verifies GPU pre-emption config matches expected values.
    ...    Fetches fresh project data from API to verify persisted state.
    ...    Requires: TEST_PROJECT_ID
    [Arguments]    ${enabled}=${TRUE}    ${threshold}=10    ${gracePeriod}=1800    ${policy}=OnPressure
    ${project_id}=    The project
    ${response}=    Get project    ${project_id}    expected_status=200
    ${gp}=    Get From Dictionary    ${response.json()}    gpuPreemption
    ${actual_enabled}=    Get From Dictionary    ${gp}    enabled
    Should Be Equal    ${actual_enabled}    ${enabled}    msg=GPU pre-emption enabled: expected ${enabled}, got ${actual_enabled}
    ${actual_threshold}=    Get From Dictionary    ${gp}    threshold
    Should Be Equal As Integers    ${actual_threshold}    ${threshold}    msg=GPU pre-emption threshold: expected ${threshold}, got ${actual_threshold}
    ${actual_grace}=    Get From Dictionary    ${gp}    gracePeriod
    Should Be Equal As Integers    ${actual_grace}    ${gracePeriod}    msg=GPU pre-emption grace period: expected ${gracePeriod}, got ${actual_grace}
    ${actual_policy}=    Get From Dictionary    ${gp}    policy
    Should Be Equal    ${actual_policy}    ${policy}    msg=GPU pre-emption policy: expected ${policy}, got ${actual_policy}

Clean Up GPU Pre-emption Test Resources
    [Documentation]    Cleans up kubectl deployments and tracked resources from GPU pre-emption tests.
    ${project}=    Get Variable Value    ${TEST_PROJECT}    ${None}
    IF    $project != $None
        ${namespace}=    Get From Dictionary    ${project}    name
        Run Process    kubectl    delete    deployments    --all    -n    ${namespace}    --ignore-not-found\=true
    END
    Clean Up All Created Workloads
    Clean Up All Created Projects

GPU pre-emption is enabled on the project
    [Documentation]    Enables GPU pre-emption on the current test project via update API.
    ...    Requires: TEST_PROJECT_ID
    ...    Sets: TEST_PROJECT_DATA, TEST_GPU_PREEMPTION_DATA
    [Arguments]    ${threshold}=10    ${gracePeriod}=1800    ${policy}=OnPressure
    Updated project data with gpu preemption enabled is prepared
    ...    threshold=${threshold}    gracePeriod=${gracePeriod}    policy=${policy}
    Update project request is sent
    Project should transition to "ready"

An idle GPU workload is running in the project
    [Documentation]    Submits a GPU Deployment that sleeps (zero GPU utilization) and waits for it to run.
    ...    Uses a Deployment because Kaiwo only tracks Deployment-backed GPU pods for idle pre-emption —
    ...    plain batch Jobs are not visible to the Kaiwo idle pre-emption controller.
    ...    Requires: TEST_PROJECT (with name attribute)
    ...    Sets: TEST_IDLE_DEPLOY_NAME
    VAR    ${namespace}    ${TEST_PROJECT}[name]

    ${deploy_name}=    Submit GPU deployment via kubectl    ${namespace}

    Set test variable    ${TEST_IDLE_DEPLOY_NAME}    ${deploy_name}

    Kubectl deployment should be running    ${namespace}    ${deploy_name}    timeout=5 min
    Log    Idle GPU Deployment ${deploy_name} is running in ${namespace}    INFO

Verify idle workload pre-empted
    [Documentation]    Checks if a GPU Deployment has been pre-empted by Kaiwo.
    ...    Kaiwo creates GpuWorkload resources for each GPU-using Deployment pod and transitions
    ...    their phase to Preempted or Deleted when idle workloads exceed the grace period.
    [Arguments]    ${namespace}    ${deploy_name}

    ${result}=    Run process    kubectl    get    gpuworkloads
    ...    -n    ${namespace}
    ...    -o    jsonpath\={.items[*].status.phase}

    IF    "Preempted" in "${result.stdout}" or "Deleted" in "${result.stdout}"
        Log    Deployment ${deploy_name} was pre-empted (GpuWorkload phases: ${result.stdout.strip()})    INFO
        RETURN
    END

    Fail    Deployment ${deploy_name} not yet pre-empted. GpuWorkload phases: ${result.stdout.strip()}

The workload should be pre-empted
    [Documentation]    Verifies that the idle GPU Deployment has been pre-empted by Kaiwo.
    ...    Polls with a long timeout since the grace period must elapse before pre-emption occurs.
    ...    Requires: TEST_IDLE_DEPLOY_NAME, TEST_PROJECT
    [Arguments]    ${timeout}=20 min
    VAR    ${namespace}    ${TEST_PROJECT}[name]

    Wait Until Keyword Succeeds    ${timeout}    15 sec
    ...    Verify idle workload pre-empted    ${namespace}    ${TEST_IDLE_DEPLOY_NAME}

The project should not exist in database
    [Documentation]    Uses API 404 as the observable signal that hard deletion removed the row and released its name.
    Wait Until Project Deleted    ${TEST_PROJECT_ID}    timeout=2 min

Project description in database should be "${expected_desc}"
    [Documentation]    Verifies project description is updated in database
    ...    Polls for description update to handle async API operations
    Wait Until Keyword Succeeds    2 min    2 sec
    ...    Verify project description    ${expected_desc}

Verify project description
    [Documentation]    Helper keyword to verify project description (used with polling)
    [Arguments]    ${expected_desc}
    Log    Polling project ${TEST_PROJECT_ID} description update    TRACE
    ${db_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    Dictionary should contain item    ${db_response.json()}    description    ${expected_desc}
    Log    Project description verified: ${expected_desc}    DEBUG

Project quota in database should match updated values
    [Documentation]    Verifies project quota values match expected values
    ...    Polls for quota update to handle async API operations
    Wait Until Keyword Succeeds    2 min    2 sec
    ...    Verify project quota values

Verify project quota values
    [Documentation]    Helper keyword to verify project quota (used with polling)
    Log    Polling project ${TEST_PROJECT_ID} quota values    TRACE
    ${db_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    ${quota}=    Set Variable    ${db_response.json()['quota']}

    Should Be Equal As Integers    ${quota['cpuMilliCores']}    ${TEST_QUOTA_DATA}[cpuMilliCores]
    Should Be Equal As Integers    ${quota['memoryBytes']}    ${TEST_QUOTA_DATA}[memoryBytes]
    Should Be Equal As Integers    ${quota['ephemeralStorageBytes']}    ${TEST_QUOTA_DATA}[ephemeralStorageBytes]
    Should Be Equal As Integers    ${quota['gpuCount']}    ${TEST_QUOTA_DATA}[gpuCount]
    Log    Project quota verified    DEBUG

Project quota should match minimum values
    [Documentation]    Verifies project quota matches minimum allocation
    ${quota}=    Set Variable    ${TEST_RESPONSE.json()['quota']}

    Should Be Equal As Integers    ${quota['cpuMilliCores']}    ${TEST_QUOTA_DATA}[cpuMilliCores]
    Should Be Equal As Integers    ${quota['memoryBytes']}    ${TEST_QUOTA_DATA}[memoryBytes]
    Should Be Equal As Integers    ${quota['ephemeralStorageBytes']}    ${TEST_QUOTA_DATA}[ephemeralStorageBytes]
    Should Be Equal As Integers    ${quota['gpuCount']}    ${TEST_QUOTA_DATA}[gpuCount]

Project quota should match custom values
    [Documentation]    Verifies project quota matches custom allocation
    ${quota}=    Set Variable    ${TEST_RESPONSE.json()['quota']}

    Should Be Equal As Integers    ${quota['cpuMilliCores']}    ${TEST_QUOTA_DATA}[cpuMilliCores]
    Should Be Equal As Integers    ${quota['memoryBytes']}    ${TEST_QUOTA_DATA}[memoryBytes]
    Should Be Equal As Integers    ${quota['ephemeralStorageBytes']}    ${TEST_QUOTA_DATA}[ephemeralStorageBytes]
    Should Be Equal As Integers    ${quota['gpuCount']}    ${TEST_QUOTA_DATA}[gpuCount]

Project quota in database should match increased values
    [Documentation]    Verifies increased quota values in database
    Project quota in database should match updated values

Project quota in database should match decreased values
    [Documentation]    Verifies decreased quota values in database
    Project quota in database should match updated values

Project CPU quota in database should match updated value
    [Documentation]    Verifies CPU quota is updated in database
    ...    Polls for quota update to handle async API operations
    Wait Until Keyword Succeeds    2 min    2 sec
    ...    Verify CPU quota value

Verify CPU quota value
    [Documentation]    Helper keyword to verify CPU quota (used with polling)
    Log    Polling project ${TEST_PROJECT_ID} CPU quota update    TRACE
    ${db_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    ${quota}=    Set Variable    ${db_response.json()['quota']}
    Should Be Equal As Integers    ${quota['cpuMilliCores']}    ${TEST_QUOTA_DATA}[cpuMilliCores]
    Log    CPU quota verified: ${TEST_QUOTA_DATA}[cpuMilliCores]    DEBUG

Project memory quota in database should match updated value
    [Documentation]    Verifies memory quota is updated in database
    ...    Polls for quota update to handle async API operations
    Wait Until Keyword Succeeds    2 min    2 sec
    ...    Verify memory quota value

Verify memory quota value
    [Documentation]    Helper keyword to verify memory quota (used with polling)
    Log    Polling project ${TEST_PROJECT_ID} memory quota update    TRACE
    ${db_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    ${quota}=    Set Variable    ${db_response.json()['quota']}
    Should Be Equal As Integers    ${quota['memoryBytes']}    ${TEST_QUOTA_DATA}[memoryBytes]
    Log    Memory quota verified: ${TEST_QUOTA_DATA}[memoryBytes]    DEBUG

Project GPU quota in database should match updated value
    [Documentation]    Verifies GPU quota is updated in database
    ...    Polls for quota update to handle async API operations
    Wait Until Keyword Succeeds    2 min    2 sec
    ...    Verify GPU quota value

Verify GPU quota value
    [Documentation]    Helper keyword to verify GPU quota (used with polling)
    Log    Polling project ${TEST_PROJECT_ID} GPU quota update    TRACE
    ${db_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    ${quota}=    Set Variable    ${db_response.json()['quota']}
    Should Be Equal As Integers    ${quota['gpuCount']}    ${TEST_QUOTA_DATA}[gpuCount]
    Log    GPU quota verified: ${TEST_QUOTA_DATA}[gpuCount]    DEBUG

Quota should have valid status
    [Documentation]    Verifies that quota has a valid status field
    ${quota}=    Set Variable    ${TEST_RESPONSE.json()['quota']}
    Dictionary should contain key    ${quota}    status

Quota status should be one of "${status_list}"
    [Documentation]    Verifies quota status matches one of the expected values (case-insensitive)
    ...    Example: Quota status should be one of "active, pending, provisioning, Ready"
    ${quota}=    Set Variable    ${TEST_RESPONSE.json()['quota']}
    ${status}=    Get from dictionary    ${quota}    status
    @{expected_statuses}=    Split String    ${status_list}    ,${SPACE}

    # Check if status matches any expected value (case-insensitive)
    ${status_matches}=    Set Variable    ${False}
    FOR    ${expected_status}    IN    @{expected_statuses}
        IF    '${status.lower()}' == '${expected_status.lower()}'
            ${status_matches}=    Set Variable    ${True}
            BREAK
        END
    END

    Should Be True    ${status_matches}
    ...    msg=Quota status is ${status}, expected one of: ${status_list}

# Backward compatibility keyword (can be removed later)
Quota status should be "active" or "pending"
    [Documentation]    DEPRECATED: Use 'Quota status should be one of "active, pending, provisioning, Ready"' instead
    Quota status should be one of "active, pending, provisioning, Ready"

Response should contain projects list
    [Documentation]    Verifies response contains a projects list
    ${body}=    Set variable    ${TEST_RESPONSE.json()}
    Dictionary should contain key    ${body}    data
    ${projects}=    Get from dictionary    ${body}    data
    ${is_list}=    Evaluate    isinstance(${projects}, list)
    Should Be True    ${is_list}    msg=Projects field is not a list: ${projects}

Response should contain at least ${expected_count} projects
    [Documentation]    Verifies response list contains at least the expected number of projects
    ${body}=    Set variable    ${TEST_RESPONSE.json()}
    ${projects}=    Get from dictionary    ${body}    data
    ${count}=    Get length    ${projects}
    Should be true    ${count} >= ${expected_count}    msg=Expected at least ${expected_count} projects, but found ${count}

User should be member of project
    [Documentation]    Verifies user is a member of the project
    ${db_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    ${users}=    Set Variable    ${db_response.json()['users']}

    ${is_member}=    Set Variable    ${False}
    FOR    ${user}    IN    @{users}
        ${user_id}=    Get From Dictionary    ${user}    id
        IF    '${user_id}' == '${TEST_USER_ID}'
            ${is_member}=    Set Variable    ${True}
            BREAK
        END
    END

    Should Be True    ${is_member}    msg=User ${TEST_USER_ID} is not a member of project ${TEST_PROJECT_ID}

User should not be member of project
    [Documentation]    Verifies user is not a member of the project
    ${db_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    ${users}=    Set Variable    ${db_response.json()['users']}

    ${is_member}=    Set Variable    ${False}
    FOR    ${user}    IN    @{users}
        ${user_id}=    Get From Dictionary    ${user}    id
        IF    '${user_id}' == '${TEST_USER_ID}'
            ${is_member}=    Set Variable    ${True}
            BREAK
        END
    END

    Should Not Be True    ${is_member}    msg=User ${TEST_USER_ID} is still a member of project ${TEST_PROJECT_ID}

Create Shared Project With Validation
    [Documentation]    Creates a project used by shared-project setup and moves its cleanup to
    ...    run scope. Normal creation records the new ID in suite-scoped CREATED_PROJECT_IDS;
    ...    leaving it there lets the first child-suite teardown delete a project later suites
    ...    still expect to reuse. Remove this one ID from that list, then add it to the same
    ...    deduplicated global list used for projects adopted from an earlier run.
    [Arguments]    ${project_name}    ${quota_data}=${None}
    Create Project With Validation    project_name=${project_name}    quota_data=${quota_data}
    ${created}=    Get Variable Value    ${CREATED_PROJECT_IDS}    ${None}
    ${tracked_as_created}=    Evaluate    $created is not None and $TEST_PROJECT_ID in $created
    IF    ${tracked_as_created}
        Remove Values From List    ${CREATED_PROJECT_IDS}    ${TEST_PROJECT_ID}
    END
    Track Adopted Project For Suite Cleanup    ${TEST_PROJECT_ID}

Track Adopted Project For Suite Cleanup
    [Documentation]    Records a shared project for run-scoped cleanup, whether this run adopted
    ...    or created it. Deliberately kept out of CREATED_PROJECT_IDS, so neither the generic
    ...    "Clean Up All Tracked Resources" teardown nor a per-suite project teardown destroys a
    ...    project later tests still share. Recorded once per id — many tests use the same shared
    ...    project — and at GLOBAL scope, because the run-scoped teardown that consumes it lives
    ...    in the directory suite, which cannot see variables set inside a child suite.
    [Arguments]    ${project_id}
    ${adopted}=    Get Variable Value    ${ADOPTED_PROJECT_IDS}    ${None}
    IF    $adopted is None
        @{adopted}=    Create List
        Set Global Variable    ${ADOPTED_PROJECT_IDS}    ${adopted}
    END
    ${already}=    Evaluate    $project_id in $ADOPTED_PROJECT_IDS
    IF    not ${already}
        Append To List    ${ADOPTED_PROJECT_IDS}    ${project_id}
        Log    Tracking adopted project ${project_id} for run-scoped cleanup    DEBUG
    END

Clean Up Adopted Projects
    [Documentation]    Deletes the shared projects tracked for run-scoped cleanup — whether this run
    ...    adopted them or created them via Create Shared Project With Validation. Run once at the
    ...    directory-suite teardown of both the AIRM and AIWB suites. This is what preserves the
    ...    guarantee that a project left behind by a previous interrupted run is still removed,
    ...    without letting a per-test teardown delete a shared project other tests are still using.
    ${adopted}=    Get Variable Value    ${ADOPTED_PROJECT_IDS}    ${None}
    IF    $adopted is None    RETURN
    ${count}=    Get Length    ${adopted}
    IF    ${count} == 0    RETURN    END
    Log    Deleting ${count} adopted project(s) at suite teardown    INFO

    FOR    ${project_id}    IN    @{adopted}
        TRY
            Delete project    ${project_id}    expected_status=any
        EXCEPT    AS    ${error}
            Log    Failed to delete adopted project ${project_id}: ${error}    WARN
        END
    END

    @{empty_list}=    Create List
    Set Global Variable    ${ADOPTED_PROJECT_IDS}    ${empty_list}
    Log    Adopted project cleanup complete    INFO

Clean Up All Created Projects With Wait
    [Documentation]    Extended cleanup that waits for complete project deletion
    ...    Uses the standard cleanup from airm_resource_cleanup.resource but adds waiting
    ...    for complete deletion verification. This is project-specific behavior.
    ${tracking_list}=    Get Variable Value    ${CREATED_PROJECT_IDS}    ${None}
    IF    $tracking_list is None    RETURN
    ${count}=    Get Length    ${tracking_list}
    IF    ${count} == 0    RETURN    END
    Log    Starting cleanup of ${count} projects    INFO

    FOR    ${project_id}    IN    @{tracking_list}
        TRY
            Log    Deleting project ${project_id}    INFO
            Delete project    ${project_id}    expected_status=any
        EXCEPT    AS    ${delete_error}
            Log    Failed to delete project ${project_id}: ${delete_error}    WARN
        END
    END

    Log    Waiting for all ${count} project deletions to complete    INFO
    FOR    ${project_id}    IN    @{tracking_list}
        TRY
            Wait Until Project Deleted    ${project_id}    timeout=1 min
            Log    Project ${project_id} deletion confirmed    DEBUG
        EXCEPT    AS    ${wait_error}
            Log    Project ${project_id} deletion verification failed: ${wait_error}    WARN
        END
    END

    @{empty_list}=    Create List
    Set Suite Variable    ${CREATED_PROJECT_IDS}    ${empty_list}
    Log    Project cleanup complete    INFO

Project Should Be Deleted
    [Documentation]    Verifies that a project has been fully deleted (returns 404)
    [Arguments]    ${project_id}
    Resource Should Not Exist    Get project    ${project_id}

Wait Until Project Deleted
    [Documentation]    Waits for project deletion to complete (polls until returns 404)
    ...    Use when you need to wait for async deletion to fully complete before recreating
    [Arguments]    ${project_id}    ${timeout}=1 min

    Log    Waiting for project ${project_id} deletion to complete    INFO
    Wait For Resource Deletion    Get project    ${project_id}    timeout=${timeout}
    Log    Project ${project_id} fully deleted (404)    INFO

Get Project By Name
    [Documentation]    Finds a project by name and returns it (or None if not found)
    ...    Returns the project dictionary if found, ${None} if not found
    [Arguments]    ${project_name}

    ${response}=    Get projects    expected_status=any
    Should Be True    ${response.status_code} in [200, 201]    msg=Get projects returned unexpected status ${response.status_code}
    ${response_json}=    Set variable    ${response.json()}
    ${projects}=    Set variable    ${response_json['data']}

    FOR    ${project}    IN    @{projects}
        IF    '${project['name']}' == '${project_name}'
            RETURN    ${project}
        END
    END

    RETURN    ${None}

# Helper Keywords from test files

Get project request is sent for "${project_id}"
    [Documentation]    Helper keyword to get a specific project and store the response
    ${response}=    Get project    ${project_id}    expected_status=200
    Set Test Variable    ${TEST_RESPONSE}    ${response}
    Log    Retrieved project ${project_id}    DEBUG
    RETURN    ${response}

# Project Status Verification Keywords

Project should have status pending
    [Documentation]    Verifies project initial status is pending or provisioning
    ${project}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    Project status should be one of    pending, provisioning    ${project.json()}

Verify project status in any of
    [Documentation]    Verifies project status matches one of expected values (polling-compatible wrapper)
    ...    This is a wrapper around "Project status should be one of" for use with Wait Until Keyword Succeeds
    [Arguments]    ${expected_statuses}
    Project status should be one of    ${expected_statuses}

Project status should be one of
    [Documentation]    Generic keyword to verify project status matches one of expected values
    ...    Logs detailed status information for troubleshooting
    ...    Returns the actual project status for further processing
    ...    Args: expected_statuses - comma-separated list like "pending, provisioning, ready, failed"
    [Arguments]    ${expected_statuses}    ${project_data}=${None}

    # Fetch current project data if none provided
    IF    $project_data == $None
        ${project_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
        ${data}=    Set Variable    ${project_response.json()}
    ELSE
        ${data}=    Set Variable    ${project_data}
    END
    ${project_status}=    Get From Dictionary    ${data}    status    default=Unknown
    ${project_status_reason}=    Get From Dictionary    ${data}    statusReason    default=No reason provided

    # Get quota details for context
    ${quota}=    Get From Dictionary    ${data}    quota
    ${quota_status}=    Get From Dictionary    ${quota}    status    default=Unknown
    ${quota_status_reason}=    Get From Dictionary    ${quota}    statusReason    default=No reason provided

    # Check if project status matches expected values (case-insensitive)
    @{expected_list}=    Split String    ${expected_statuses}    ,${SPACE}
    ${status_matches}=    Set Variable    ${False}
    FOR    ${expected_status}    IN    @{expected_list}
        IF    '${project_status.lower()}' == '${expected_status.lower()}'
            ${status_matches}=    Set Variable    ${True}
            BREAK
        END
    END

    IF    not ${status_matches}
        # Status doesn't match - log details as ERROR and fail
        Log    Project Status: ${project_status}    ERROR
        Log    Project Status Reason: ${project_status_reason}    ERROR
        Log    Quota Status: ${quota_status}    ERROR
        Log    Quota Status Reason: ${quota_status_reason}    ERROR
        FAIL    Expected project status to be one of [${expected_statuses}], but got ${project_status}
    ELSE
        # Status matches - log details for visibility
        Log    Project Status: ${project_status}    INFO
        Log    Project Status Reason: ${project_status_reason}    INFO
        Log    Quota Status: ${quota_status}    INFO
        Log    Quota Status Reason: ${quota_status_reason}    INFO

        # If status is Failed and it was expected, warn about polling implications
        IF    '${project_status}' == 'Failed'
            Log    WARNING: Project status is Failed. Polling operations should stop.    WARN
        END

        Log    Project status '${project_status}' matches expected values    INFO
    END

    # Return the actual status for caller to use
    RETURN    ${project_status}

Project should transition to "${target_status}"
    [Documentation]    Generic keyword to wait for project to transition to target status
    ...    Handles terminal states (Failed, Deleted) by failing immediately if encountered
    ...    Uses intelligent polling - stops on terminal states, continues on transitional ones
    ...    Args:
    ...      target_status - The desired end status (e.g., "ready", "deleted") - embedded from keyword name
    ...      timeout - How long to wait (default: 1 min)
    ...      interval - How often to check (default: 5 sec)
    [Arguments]    ${timeout}=1 min    ${interval}=5 sec

    # Define terminal states that should stop polling immediately
    @{terminal_states}=    Create List    Failed    Deleted    Completed
    ${project_id}=    Set Variable If    "${TEST_PROJECT_ID}" != "${None}"    ${TEST_PROJECT_ID}    ${TEST_PROJECT_ID}


    Log    Waiting for project to transition to status: ${target_status}    INFO

    # Custom polling loop that respects terminal states
    ${start_time}=    Get Time    epoch
    ${timeout_seconds}=    Convert Time    ${timeout}    result_format=number
    ${interval_seconds}=    Convert Time    ${interval}    result_format=number

    WHILE    True
        ${current_time}=    Get Time    epoch
        ${elapsed}=    Evaluate    ${current_time} - ${start_time}

        # Check if we've exceeded timeout
        IF    ${elapsed} > ${timeout_seconds}
            FAIL    Timeout waiting for project to transition to ${target_status} after ${timeout}
        END

        ${project}=    Get project    ${project_id}    expected_status=200
        ${project_data}=    Set Variable    ${project.json()}
        ${current_status}=    Get From Dictionary    ${project_data}    status    default=Unknown

        # Check if we've reached target status
        IF    '${current_status.lower()}' == '${target_status.lower()}'
            Log    Project ${project_id} successfully transitioned to ${target_status}    INFO
            RETURN    # Success - exit the polling loop
        END

        # Check if we've hit a terminal failure that isn't our target
        ${is_terminal}=    Set Variable    ${False}
        FOR    ${terminal_state}    IN    @{terminal_states}
            IF    '${current_status.lower()}' == '${terminal_state.lower()}'
                ${is_terminal}=    Set Variable    ${True}
                BREAK
            END
        END

        IF    ${is_terminal}
            # Terminal failure - use Project status should be one of for the nice error reporting
            Project status should be one of    ${target_status}    ${project_data}
            # This will FAIL with detailed error info and stop polling
        END

        Log    Project ${project_id} current status: ${current_status}, waiting for: ${target_status}    DEBUG
        Sleep    ${interval_seconds}
    END

Project status in response should be pending or ready
    [Documentation]    Verifies the creation response has pending, provisioning, or Ready status
    ...    This checks the immediate response from project creation
    ...    Note: Project provisioning may be very fast, resulting in immediate Ready status
    Project status should be one of    pending, provisioning, ready

Project status in response should be ready
    [Documentation]    Verifies the response has ready status
    Project status should be one of    ready

Project namespace should exist
    [Documentation]    Verifies project namespace exists in K8s cluster
    ...    Uses TEST_PROJECT variable set during project creation
    Namespace should exist    ${TEST_PROJECT}[name]
    Log    Project namespace ${TEST_PROJECT}[name] exists in cluster    INFO

Project namespace should not exist in cluster
    [Documentation]    Verifies project namespace does not exist in K8s cluster
    ...    Uses TEST_PROJECT variable set during project creation
    ...    Polls for namespace deletion to complete
    Namespace should not exist in cluster    ${TEST_PROJECT}[name]
    Log    Project namespace ${TEST_PROJECT}[name] deleted from cluster    INFO

Project namespace should have ResourceQuota
    [Documentation]    Verifies ResourceQuota was created in project namespace
    ...    Uses TEST_PROJECT variable set during project creation
    ${quota}=    ResourceQuota should exist in namespace    ${TEST_PROJECT}[name]
    Log    ResourceQuota found in namespace ${TEST_PROJECT}[name]    INFO

Project namespace should have RoleBinding
    [Documentation]    Verifies RoleBinding was created in project namespace
    ...    Uses TEST_PROJECT variable set during project creation
    RoleBinding should exist in namespace    ${TEST_PROJECT}[name]
    Log    RoleBinding found in namespace ${TEST_PROJECT}[name]    INFO

Project namespace should have label matching project ID
    [Documentation]    Verifies namespace has correct airm.silogen.ai/project-id label
    ...    Uses TEST_PROJECT and TEST_PROJECT_ID variables
    Namespace should have label    ${TEST_PROJECT}[name]    airm.silogen.ai/project-id    ${TEST_PROJECT_ID}
    Log    Namespace ${TEST_PROJECT}[name] has correct project ID label    INFO

Project namespace should have GPU pre-emption annotations
    [Documentation]    Verifies kaiwo GPU pre-emption annotations exist on the project namespace with expected values.
    ...    Requires: TEST_PROJECT (with name attribute for namespace lookup)
    [Arguments]    ${threshold}=10    ${gracePeriod}=1800s    ${policy}=OnPressure
    VAR    ${namespace}    ${TEST_PROJECT}[name]
    Namespace should have annotation    ${namespace}    kaiwo.silogen.ai/gpu-preemption.enabled    true
    Namespace should have annotation    ${namespace}    kaiwo.silogen.ai/gpu-preemption.threshold    ${threshold}
    Namespace should have annotation    ${namespace}    kaiwo.silogen.ai/gpu-preemption.grace-period    ${gracePeriod}
    Namespace should have annotation    ${namespace}    kaiwo.silogen.ai/gpu-preemption.policy    ${policy}

Project namespace should not have GPU pre-emption annotations
    [Documentation]    Verifies kaiwo GPU pre-emption annotations do not exist on the project namespace.
    ...    Requires: TEST_PROJECT (with name attribute for namespace lookup)
    VAR    ${namespace}    ${TEST_PROJECT}[name]
    Namespace should not have annotation    ${namespace}    kaiwo.silogen.ai/gpu-preemption.enabled
    Namespace should not have annotation    ${namespace}    kaiwo.silogen.ai/gpu-preemption.threshold
    Namespace should not have annotation    ${namespace}    kaiwo.silogen.ai/gpu-preemption.grace-period
    Namespace should not have annotation    ${namespace}    kaiwo.silogen.ai/gpu-preemption.policy



A secret is assigned to the project
    [Documentation]    Creates and assigns a secret to the current test project
    ...    Sets up test data for project deletion cleanup tests
    ${manifest}=    Get File    ${CURDIR}/../test_data/secrets/valid-externalsecret.yaml

    @{project_ids}=    Create List    ${TEST_PROJECT_ID}

    ${secret_data}=    Create Dictionary
    ...    name=test-project-secret-${TEST_PROJECT_ID}
    ...    type=ExternalSecret
    ...    scope=Organization
    ...    manifest=${manifest}
    ...    projectIds=${project_ids}

    ${response}=    Create secret
    ...    secret_data=${secret_data}
    ...    expected_status=200

    ${secret_id}=    Get From Dictionary    ${response.json()}    id
    Set Test Variable    ${TEST_SECRET_ID}    ${secret_id}

    Track Secret For Cleanup    ${secret_id}

    Log    Secret ${secret_id} assigned to project ${TEST_PROJECT_ID}    INFO

Secret assignment should be synced
    [Documentation]    Waits for the secret assignment to reach synced status
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Verify secret assignment is synced

MinIO credentials are available in the current project
    [Documentation]    Ensures the minio-credentials-fetcher ExternalSecret is assigned to the
    ...    current test project, so the minio-credentials Secret lands in the project namespace.
    ...    Mirrors airm-api configure.sh (add_minio_secret_and_storage_to_project), which only
    ...    provisions the demo project at install; E2E suites create their own projects and would
    ...    otherwise never get minio-credentials, failing storage/dataset/adapter tests.
    ...    Best-effort: this runs in universal project setup, so it must NEVER crash setup —
    ...    a provisioning failure (permissions, a deployed API whose secrets shape differs from
    ...    HEAD, etc.) is logged and swallowed, and the MinIO-dependent storage/dataset tests then
    ...    fail on their own with a clear signal instead of taking down every project-creating test.
    ...    Requires: TEST_PROJECT_ID    Idempotent: skips if already assigned.
    TRY
        VAR    ${secret_name}    minio-credentials-fetcher
        ${response}=    Get secrets    expected_status=any
        # Return the full matching item — tolerant of both supported name shapes — so its id comes
        # from one read. Python owns the lookup because Robot's Evaluate cannot reliably expose a
        # local scalar variable inside generator-expression scope.
        ${match}=    Find Secret By Name    ${response}    ${secret_name}
        IF    $match is None
            Assign fresh MinIO credentials fetcher to current project    ${secret_name}
            RETURN
        END
        ${secret_id}=    Get From Dictionary    ${match}    id
        # Use the additive project-scoped endpoint. The organization-scoped assign endpoint replaces
        # the complete assignment set and can revoke a project added concurrently after this read.
        ${assign_response}=    Assign secret to project
        ...    ${TEST_PROJECT_ID}    ${secret_id}    expected_status=any
        # Already-assigned is the endpoint's only ValidationException, returned as HTTP 400
        # ("Secret already assigned to this Project"), so treat 400 as the idempotent no-op.
        IF    ${assign_response.status_code} == 204
            Log    Assigned minio-credentials-fetcher to project ${TEST_PROJECT_ID}    INFO
        ELSE IF    ${assign_response.status_code} == 400
            Log    minio-credentials-fetcher already assigned to project ${TEST_PROJECT_ID}    DEBUG
        ELSE
            Log    Assigning minio-credentials-fetcher to project ${TEST_PROJECT_ID} failed (HTTP ${assign_response.status_code}): ${assign_response.text}    WARN
        END
    EXCEPT    AS    ${error}
        Log    MinIO credential provisioning skipped (best-effort): ${error}    WARN
    END

Assign fresh MinIO credentials fetcher to current project
    [Documentation]    Creates the minio-credentials-fetcher ExternalSecret assigned to the current
    ...    project, mirroring the manifest airm-api configure.sh installs for the demo project.
    [Arguments]    ${secret_name}
    ${manifest}=    Catenate    SEPARATOR=\n
    ...    apiVersion: external-secrets.io/v1beta1
    ...    kind: ExternalSecret
    ...    metadata:
    ...    ${SPACE}${SPACE}name: ${secret_name}
    ...    spec:
    ...    ${SPACE}${SPACE}data:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}- remoteRef:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}key: minio-api-access-key
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}property: value
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}secretKey: minio-access-key
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}- remoteRef:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}key: minio-api-secret-key
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}property: value
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}${SPACE}secretKey: minio-secret-key
    ...    ${SPACE}${SPACE}refreshInterval: 1h
    ...    ${SPACE}${SPACE}secretStoreRef:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}kind: ClusterSecretStore
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}name: openbao-secret-store
    ...    ${SPACE}${SPACE}target:
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}creationPolicy: Owner
    ...    ${SPACE}${SPACE}${SPACE}${SPACE}name: minio-credentials
    @{project_ids}=    Create List    ${TEST_PROJECT_ID}
    ${secret_data}=    Create Dictionary
    ...    name=${secret_name}
    ...    type=ExternalSecret
    ...    useCase=S3
    ...    scope=Organization
    ...    manifest=${manifest}
    ...    projectIds=${project_ids}
    Create secret    secret_data=${secret_data}    expected_status=any
    Log    Created minio-credentials-fetcher for project ${TEST_PROJECT_ID}    INFO

Verify secret assignment is synced
    [Documentation]    Helper to verify secret project assignment is synced
    Log    Polling secret ${TEST_SECRET_ID} assignment sync status    TRACE
    ${response}=    Get secret    ${TEST_SECRET_ID}    expected_status=200
    ${json}=    Set Variable    ${response.json()}
    ${project_secrets}=    Get From Dictionary    ${json}    projectSecrets

    FOR    ${ps}    IN    @{project_secrets}
        ${project}=    Get From Dictionary    ${ps}    project
        ${project_id}=    Get From Dictionary    ${project}    id
        IF    '${project_id}' == '${TEST_PROJECT_ID}'
            ${status}=    Get From Dictionary    ${ps}    status
            Should Be Equal    ${status}    Synced
            ...    msg=Project secret status is ${status}, expected Synced
            Log    Secret assignment synced for project ${TEST_PROJECT_ID}    INFO
            RETURN
        END
    END

    Fail    Project ${TEST_PROJECT_ID} not found in secret assignments

Secret should exist
    [Documentation]    Verifies that the secret exists (returns 200)
    ${response}=    Get secret    ${TEST_SECRET_ID}    expected_status=200
    ${json}=    Set Variable    ${response.json()}
    Dictionary Should Contain Key    ${json}    id
    Log    Secret ${TEST_SECRET_ID} exists    INFO

Secret should be unassigned
    [Documentation]    Verifies that the secret has Unassigned status and no project assignments
    ...    Waits for the secret status to transition to Unassigned after project deletion
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Verify secret is unassigned

Verify secret is unassigned
    [Documentation]    Helper to verify secret is unassigned (used with polling)
    ...    When a project is deleted, secret may be SyncedError (namespace gone) or Unassigned (assignment cleaned)
    ...    The exact status depends on timing and reconciliation order
    Log    Polling secret ${TEST_SECRET_ID} unassignment status    TRACE
    ${response}=    Get secret    ${TEST_SECRET_ID}    expected_status=200
    ${json}=    Set Variable    ${response.json()}

    # Get current status
    ${status}=    Get From Dictionary    ${json}    status
    ${project_secrets}=    Get From Dictionary    ${json}    projectSecrets
    ${count}=    Get Length    ${project_secrets}

    # Accept either SyncedError (namespace gone) or Unassigned (assignment cleaned)
    # Both states should have 0 assignments (cleaned up when project deleted)
    Should Be Equal As Integers    ${count}    0
    ...    msg=Expected 0 project assignments (cleaned up), found ${count}

    IF    '${status}' == 'SyncedError'
        Log    Secret ${TEST_SECRET_ID} is in SyncedError state (namespace deleted, assignment cleaned)    INFO
    ELSE IF    '${status}' == 'Unassigned'
        Log    Secret ${TEST_SECRET_ID} is Unassigned (no assignments)    INFO
    ELSE
        Fail    Expected secret status SyncedError or Unassigned, got ${status}
    END

Secret should still exist but be unassigned
    [Documentation]    Legacy keyword - calls the two atomic keywords for backward compatibility
    Secret should exist
    Secret should be unassigned

A storage is assigned to the project
    [Documentation]    Creates and assigns storage to the current test project
    ...    Sets up test data for project deletion cleanup tests

    # First create a secret for storage credentials
    ${manifest}=    Get File    ${CURDIR}/../test_data/secrets/valid-externalsecret.yaml

    ${secret_data}=    Create Dictionary
    ...    name=storage-secret-${TEST_PROJECT_ID}
    ...    type=ExternalSecret
    ...    scope=Organization
    ...    useCase=S3
    ...    manifest=${manifest}
    ...    projectIds=@{EMPTY}

    ${secret_response}=    Create secret
    ...    secret_data=${secret_data}
    ...    expected_status=200

    ${storage_secret_id}=    Get From Dictionary    ${secret_response.json()}    id
    Set Test Variable    ${TEST_STORAGE_SECRET_ID}    ${storage_secret_id}

    Track Secret For Cleanup    ${storage_secret_id}

    &{storage_spec}=    Create Dictionary
    ...    bucketUrl=https://s3.amazonaws.com/test-bucket-${TEST_PROJECT_ID}
    ...    accessKeyName=ACCESS_KEY_ID
    ...    secretKeyName=SECRET_ACCESS_KEY

    @{project_ids}=    Create List    ${TEST_PROJECT_ID}

    ${storage_data}=    Create Dictionary
    ...    name=test-project-storage-${TEST_PROJECT_ID}
    ...    type=S3
    ...    scope=Organization
    ...    secretId=${storage_secret_id}
    ...    projectIds=${project_ids}
    ...    spec=${storage_spec}

    ${response}=    Create storage
    ...    storage_data=${storage_data}
    ...    expected_status=200

    ${storage_id}=    Get From Dictionary    ${response.json()}    id
    Set Test Variable    ${TEST_STORAGE_ID}    ${storage_id}

    Track Storage For Cleanup    ${storage_id}

    Log    Storage ${storage_id} assigned to project ${TEST_PROJECT_ID}    INFO

Storage assignment should be synced
    [Documentation]    Waits for the storage assignment to reach synced status
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Verify storage assignment is synced

Verify storage assignment is synced
    [Documentation]    Helper to verify storage project assignment is synced
    Log    Polling storage ${TEST_STORAGE_ID} assignment sync status    TRACE
    ${response}=    Get storage    ${TEST_STORAGE_ID}    expected_status=200
    ${json}=    Set Variable    ${response.json()}
    ${project_storages}=    Get From Dictionary    ${json}    projectStorages

    FOR    ${ps}    IN    @{project_storages}
        ${project}=    Get From Dictionary    ${ps}    project
        ${project_id}=    Get From Dictionary    ${project}    id
        IF    '${project_id}' == '${TEST_PROJECT_ID}'
            ${status}=    Get From Dictionary    ${ps}    status
            Should Be Equal    ${status}    Synced
            ...    msg=Project storage status is ${status}, expected Synced
            Log    Storage assignment synced for project ${TEST_PROJECT_ID}    INFO
            RETURN
        END
    END

    Fail    Project ${TEST_PROJECT_ID} not found in storage assignments

Storage should exist
    [Documentation]    Verifies that the storage exists (returns 200)
    ...    Retries to handle async project deletion causing temporary 400 errors
    Wait Until Keyword Succeeds    30 sec    2 sec
    ...    Verify storage exists

Verify storage exists
    [Documentation]    Helper to verify storage exists (used with polling)
    ${response}=    Get storage    ${TEST_STORAGE_ID}    expected_status=200
    ${json}=    Set Variable    ${response.json()}
    Dictionary Should Contain Key    ${json}    id
    Log    Storage ${TEST_STORAGE_ID} exists    INFO

Storage should be unassigned
    [Documentation]    Verifies that the storage has Unassigned status and no project assignments
    ...    Waits for the storage status to transition to Unassigned after project deletion
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Verify storage is unassigned

Verify storage is unassigned
    [Documentation]    Helper to verify storage is unassigned (used with polling)
    ...    When a project is deleted, storage may be SyncedError (namespace gone) or Unassigned (assignment cleaned)
    ...    The exact status depends on timing and reconciliation order
    Log    Polling storage ${TEST_STORAGE_ID} unassignment status    TRACE
    ${response}=    Get storage    ${TEST_STORAGE_ID}    expected_status=200
    ${json}=    Set Variable    ${response.json()}

    # Get current status
    ${status}=    Get From Dictionary    ${json}    status
    ${project_storages}=    Get From Dictionary    ${json}    projectStorages
    ${count}=    Get Length    ${project_storages}

    # Accept either SyncedError (namespace gone) or Unassigned (assignment cleaned)
    # Both states should have 0 assignments (cleaned up when project deleted)
    Should Be Equal As Integers    ${count}    0
    ...    msg=Expected 0 project assignments (cleaned up), found ${count}

    IF    '${status}' == 'SyncedError'
        Log    Storage ${TEST_STORAGE_ID} is in SyncedError state (namespace deleted, assignment cleaned)    INFO
    ELSE IF    '${status}' == 'Unassigned'
        Log    Storage ${TEST_STORAGE_ID} is Unassigned (no assignments)    INFO
    ELSE
        Fail    Expected storage status SyncedError or Unassigned, got ${status}
    END

Storage should still exist but be unassigned
    [Documentation]    Legacy keyword - calls the two atomic keywords for backward compatibility
    Storage should exist
    Storage should be unassigned

Project quota should not exist in database
    [Documentation]    Verifies that the project's quota has been deleted from the database
    ...    Note: This requires checking via the API as we don't have direct DB access
    # Since quotas are tied to projects, when a project is deleted, its quota should also be deleted
    # The quota is cascade deleted with the project, so we verify by checking the project doesn't exist
    ${response}=    Get project    ${TEST_PROJECT_ID}    expected_status=404
    Log    Project and its quota have been deleted from database    INFO

A workload is submitted to the project
    [Documentation]    Submits a simple test workload to the current project
    ...    Sets up test data for workload cleanup verification
    Should Not Be Equal    ${TEST_PROJECT_ID}    ${None}
    ...    msg=TEST_PROJECT_ID not set. Create project first.

    # Use test manifest from test data directory
    ${manifest_path}=    Set Variable    ${CURDIR}/../test_data/manifests/test-workload-job.yaml

    # Submit workload via API
    ${response}=    Submit workload with manifest
    ...    manifest_path=${manifest_path}
    ...    project_id=${TEST_PROJECT_ID}
    ...    display_name=test-workload
    ...    expected_status=200

    ${workload_id}=    Get From Dictionary    ${response.json()}    id
    Set Test Variable    ${TEST_WORKLOAD_ID}    ${workload_id}

    Track Workload For Cleanup    ${workload_id}

    Log    Workload ${workload_id} submitted to project ${TEST_PROJECT_ID}    INFO

Workload should be running in cluster
    [Documentation]    Verifies the workload is running in the Kubernetes cluster
    ...    Waits for workload to transition to Running status
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Workload status should be one of "Running, Complete"

Verify workload status is any of
    [Documentation]    Verifies workload status matches one of the acceptable statuses (case-insensitive)
    [Arguments]    ${workload_id}    @{acceptable_statuses}
    ${status_list}=    Evaluate    ', '.join(${acceptable_statuses})
    ${actual_status}=    Resource Status Should Be One Of    Get workload    ${workload_id}    ${status_list}
    RETURN    ${actual_status}

Workload status should be "${expected_status}"
    [Documentation]    Verifies workload has exactly the expected status
    Verify Resource Status    Get workload    ${TEST_WORKLOAD_ID}    ${expected_status}

Workload status should be one of "${status_list}"
    [Documentation]    Verifies workload status matches one of the comma-separated statuses
    ...    Example: Workload status should be one of "Running, Complete"
    Resource Status Should Be One Of    Get workload    ${TEST_WORKLOAD_ID}    ${status_list}

Workload should not exist in database
    [Documentation]    Verifies the workload record exists (historical data) but may be in Deleted/Terminated state
    ...    Workloads are NOT cascade deleted - they remain as historical records
    ...    This allows tracking of what workloads ran, even after project deletion
    ${response}=    Get workload    ${TEST_WORKLOAD_ID}    expected_status=200
    ${json}=    Set Variable    ${response.json()}
    ${status}=    Get From Dictionary    ${json}    status
    Log    Workload ${TEST_WORKLOAD_ID} exists with status ${status} (expected after project deletion)    INFO

Workload should not exist in cluster
    [Documentation]    Verifies the workload resources have been removed from Kubernetes
    ...    Checks that pods/jobs for the workload no longer exist
    Should Not Be Equal    ${TEST_PROJECT}[name]    ${None}
    ...    msg=TEST_PROJECT not set. Create project first.

    # Check for any pods with the workload ID label
    ${result}=    Run Process    kubectl    get    pods
    ...    -n    ${TEST_PROJECT}[name]
    ...    -l    workload-id\=${TEST_WORKLOAD_ID}
    ...    --no-headers

    # If namespace doesn't exist, kubectl will fail - that's ok
    IF    ${result.rc} != 0
        Should Contain    ${result.stderr}    namespace "${TEST_PROJECT}[name]" not found
        Log    Namespace ${TEST_PROJECT}[name] doesn't exist - workload cleaned up    INFO
    ELSE
        # If namespace exists, there should be no pods
        Should Be Empty    ${result.stdout}
        ...    msg=Found workload pods in cluster after project deletion: ${result.stdout}
        Log    No workload pods found in cluster - properly cleaned up    INFO
    END

    # Also check for jobs
    ${result}=    Run Process    kubectl    get    jobs
    ...    -n    ${TEST_PROJECT}[name]
    ...    -l    workload-id\=${TEST_WORKLOAD_ID}
    ...    --no-headers

    IF    ${result.rc} == 0
        Should Be Empty    ${result.stdout}
        ...    msg=Found workload jobs in cluster after project deletion: ${result.stdout}
    END

# ============================================================================
# Two-Step Project Creation Keywords (Clean Separation of Concerns)
# ============================================================================
# These keywords separate project setup from quota configuration, allowing
# for clearer test intent and better reusability.
# NOTE: The first step uses the existing keyword "A Ready Project With User Access Exists" (line 177)

Project quota is set to
    [Documentation]    SYNCHRONOUS: Updates project quota and waits for Kueue propagation
    ...
    ...    This keyword is BLOCKING - when it returns, the quota is FULLY PROPAGATED:
    ...    - Quota updated in AIRM database (via PUT request)
    ...    - AIRM QuotaReconciler processed the change
    ...    - Kueue ClusterQueue configured with new quota
    ...    - kubectl workloads can be submitted immediately without suspension
    ...
    ...    CRITICAL: For kubectl-based workload tests, this wait is essential.
    ...    Submitting jobs before ClusterQueue is configured causes Kueue to suspend them.
    ...
    ...    Usage:
    ...    Project quota is set to    gpu_count=8
    ...    Project quota is set to    cpu_milli_cores=4000    memory_bytes=4294967296    gpu_count=2
    [Arguments]    ${cpu_milli_cores}=${None}    ${memory_bytes}=${None}    ${ephemeral_storage_bytes}=${None}    ${gpu_count}=${None}

    # Get current project state
    ${project_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    ${current_quota}=    Set Variable    ${project_response.json()['quota']}
    ${current_desc}=    Set Variable    ${project_response.json()['description']}

    # Build updated quota preserving unspecified values
    ${new_cpu}=    Set Variable If    $cpu_milli_cores != $None    ${cpu_milli_cores}    ${current_quota['cpuMilliCores']}
    ${new_memory}=    Set Variable If    $memory_bytes != $None    ${memory_bytes}    ${current_quota['memoryBytes']}
    ${new_storage}=    Set Variable If    $ephemeral_storage_bytes != $None    ${ephemeral_storage_bytes}    ${current_quota['ephemeralStorageBytes']}
    ${new_gpu}=    Set Variable If    $gpu_count != $None    ${gpu_count}    ${current_quota['gpuCount']}

    # Minimums just prevent API rejection (0 CPU/memory with GPUs is invalid).
    # AIM pods need ~4 CPU + 32Gi memory per GPU — callers must set explicit values.
    IF    ${new_gpu} > 0
        ${new_cpu}=    Set Variable If    ${new_cpu} == 0    100    ${new_cpu}
        ${new_memory}=    Set Variable If    ${new_memory} == 0    134217728    ${new_memory}
        ${new_storage}=    Set Variable If    ${new_storage} == 0    134217728    ${new_storage}
    END

    ${updated_quota}=    Create Dictionary
    ...    cpuMilliCores=${new_cpu}
    ...    memoryBytes=${new_memory}
    ...    ephemeralStorageBytes=${new_storage}
    ...    gpuCount=${new_gpu}

    ${project_data}=    Create Dictionary
    ...    description=${current_desc}
    ...    quota=${updated_quota}

    # Update project via API
    Update project    ${TEST_PROJECT_ID}    ${project_data}    expected_status=200

    Set Test Variable    ${TEST_QUOTA_DATA}    ${updated_quota}

    # Wait for quota update to propagate
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Verify project quota was updated

    Log    Project ${TEST_PROJECT_ID} quota updated: ${new_gpu} GPUs    INFO

Verify project quota was updated
    [Documentation]    Helper to verify quota update completed (used with polling)
    ${db_response}=    Get project    ${TEST_PROJECT_ID}    expected_status=200
    ${quota}=    Set Variable    ${db_response.json()['quota']}

    Should Be Equal As Integers    ${quota['cpuMilliCores']}    ${TEST_QUOTA_DATA}[cpuMilliCores]
    Should Be Equal As Integers    ${quota['memoryBytes']}    ${TEST_QUOTA_DATA}[memoryBytes]
    Should Be Equal As Integers    ${quota['ephemeralStorageBytes']}    ${TEST_QUOTA_DATA}[ephemeralStorageBytes]
    Should Be Equal As Integers    ${quota['gpuCount']}    ${TEST_QUOTA_DATA}[gpuCount]

    Log    Quota update verified for project ${TEST_PROJECT_ID}    DEBUG

# ============================================================================
# Additional Keywords for Compatibility
# ============================================================================

Project Exists In System
    [Documentation]    Ensures the default e2e project exists and sets its ID as a test variable.
    ...    Compatibility wrapper (formerly in catalog_projects.resource)
    ${project_name}=    Test Name    testing
    A Ready Project "${project_name}" With User Access Exists

A Second Ready Project With User Access Exists
    [Documentation]    Creates a second project for multi-project testing
    ...    Compatibility wrapper (formerly in catalog_projects.resource)

    # Save the first project ID if it exists
    ${first_project_id}=    Get Variable Value    ${TEST_PROJECT_ID}    ${None}

    # Ensure the first project exists
    IF    $first_project_id == $None or $first_project_id == ""
        ${first_name}=    Test Name    testing
        A Ready Project "${first_name}" With User Access Exists
        ${first_project_id}=    Set Variable    ${TEST_PROJECT_ID}
    END

    # Create second project
    ${second_name}=    Test Name    testing-2
    A Ready Project "${second_name}" With User Access Exists
    ${second_project_id}=    Set Variable    ${TEST_PROJECT_ID}

    # Validate we have different projects
    Should Not Be Equal    ${second_project_id}    ${first_project_id}
    ...    msg=Second project ID same as first project ID

    Set Test Variable    ${TEST_SECOND_PROJECT_ID}    ${second_project_id}
    Set Test Variable    ${TEST_PROJECT_ID}    ${first_project_id}

    Log    First project: ${TEST_PROJECT_ID}, Second project: ${TEST_SECOND_PROJECT_ID}    INFO

Project query parameters are set up
    [Documentation]    Sets up query parameters with project ID for API calls
    Should Not Be Empty     ${TEST_PROJECT_ID}      msg=Project ID is required for query parameters setup.
    ${query_params}=        Create Dictionary       projectId=${TEST_PROJECT_ID}
    Set Test Variable       ${TEST_QUERY_PARAMS}         ${query_params}
    Log                     Query parameters set up with project ID: ${TEST_PROJECT_ID}    DEBUG
