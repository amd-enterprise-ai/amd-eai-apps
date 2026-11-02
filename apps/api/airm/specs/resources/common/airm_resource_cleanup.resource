# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation    AIRM-specific resource cleanup keywords.
...    Provides cleanup for AIRM domain resources (projects, workloads, secrets, storage).
...    Uses the shared resource tracking keywords.
Library          Collections
Library          String
Resource         ../api/projects.resource
Resource         resources/resource_tracking.resource


*** Keywords ***
# Special case for projects with extended cleanup
Clean Up All Project Resources
    [Documentation]    Projects may have cascading deletes and need special handling
    ...    This is the actual implementation for project cleanup
    ${tracking_list}=    Get Variable Value    ${CREATED_PROJECT_IDS}    ${None}
    IF    $tracking_list is None    RETURN
    ${count}=    Get Length    ${tracking_list}
    IF    ${count} == 0    RETURN    END
    Log    Cleaning up ${count} projects and their resources    INFO

    FOR    ${project_id}    IN    @{tracking_list}
        TRY
            Log    Deleting project ${project_id} and associated resources    DEBUG
            Delete project    ${project_id}    expected_status=any
        EXCEPT    AS    ${error}
            Log    Failed to delete project ${project_id}: ${error}    WARN
        END
    END

    @{empty_list}=    Create List
    Set Suite Variable    ${CREATED_PROJECT_IDS}    ${empty_list}
    Log    Project cleanup complete    INFO

# Workload cleanup keywords
Clean Up All Created Workloads
    [Documentation]    Clean up all created workload resources including helm releases
    ${workload_list}=    Get Variable Value    ${CREATED_WORKLOAD_IDS}    ${None}
    ${release_list}=    Get Variable Value    ${CREATED_HELM_RELEASES}    ${None}
    ${wcount}=    Evaluate    len($workload_list) if $workload_list is not None else 0
    ${rcount}=    Evaluate    len($release_list) if $release_list is not None else 0
    Log    Cleaning up ${rcount} helm releases and ${wcount} AIRM workloads    INFO

    # Clean up helm releases
    IF    ${rcount} > 0
        FOR    ${release_info}    IN    @{release_list}
            ${parts}=    Split String    ${release_info}    :::
            ${release_name}=    Get From List    ${parts}    0
            ${namespace}=    Get From List    ${parts}    1

            TRY
                Log    Deleting helm release ${release_name} in namespace ${namespace}    DEBUG
                Uninstall workload via helm    ${release_name}    ${namespace}
                Log    Deleted helm release ${release_name}    INFO
            EXCEPT    AS    ${error}
                Log    Failed to delete helm release ${release_name}: ${error}    WARN
            END
        END
    END

    # Clean up workloads via API
    Clean Up All Created Workloads Via API

    # Clear the helm release tracking list
    @{empty_releases}=    Create List
    Set Suite Variable    ${CREATED_HELM_RELEASES}    ${empty_releases}
    Log    Workload cleanup complete    INFO

Clean Up All Created Workloads Via API
    [Documentation]    Clean up all created workload resources via API
    ${tracking_list}=    Get Variable Value    ${CREATED_WORKLOAD_IDS}    ${None}
    IF    $tracking_list is None    RETURN
    ${count}=    Get Length    ${tracking_list}
    IF    ${count} == 0    RETURN    END
    Log    Cleaning up ${count} Workload(s) via API    INFO

    FOR    ${workload_id}    IN    @{tracking_list}
        TRY
            Delete workload    ${workload_id}    expected_status=any
            Log    Deleted Workload ${workload_id}    INFO
        EXCEPT
            Log    Failed to delete Workload ${workload_id}    WARN
        END
    END

    @{empty_list}=    Create List
    Set Suite Variable    ${CREATED_WORKLOAD_IDS}    ${empty_list}
    Log    Workload cleanup complete    INFO

# These keywords delegate to the actual implementation to avoid pattern conflicts
Clean Up All Created Projects
    [Documentation]    Wrapper that delegates to the actual project cleanup implementation
    ...    This avoids conflict with the generic pattern Clean Up All Created ${resource_type}s
    Clean Up All Project Resources

# The following keywords now use the generic pattern
Clean Up All Created Storage
    [Documentation]    Clean up all created storage resources using generic pattern
    Generic Clean Up All Created Storage

Clean Up All Created Secrets
    [Documentation]    Clean up all created secret resources using generic pattern
    Generic Clean Up All Created Secret
