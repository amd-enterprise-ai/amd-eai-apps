# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       High-level keywords for reclaiming data left behind by deleted projects.
...
...                 Reclamation runs on a timer in the API pod. These keywords drive it on demand
...                 instead, so a scenario does not have to wait out an interval to observe it.

Resource            resources/airm_projects.resource
Resource            aiwb_common.resource
Resource            aiwb_datasets.resource
Library             Process
Library             String


*** Variables ***
${CLEANUP_NAMESPACE}        aiwb
${CLEANUP_DEPLOYMENT}       deploy/aiwb-api


*** Keywords ***
The platform reclaims data from deleted projects
    [Documentation]    Runs reclamation now rather than waiting for its interval.
    ${result}=    Run Process
    ...    kubectl    exec    -n    ${CLEANUP_NAMESPACE}    ${CLEANUP_DEPLOYMENT}
    ...    --    uv    run    reclaim-orphans
    ...    stderr=STDOUT
    Log    ${result.stdout}
    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Reclamation did not complete: ${result.stdout}

The project's stored data should be gone
    [Documentation]    Checks the objects as well as the record. Storage is the irreversible half,
    ...                and a record can be gone while every object it described is still billed for.
    ...
    ...                Storage is asked of a preview run rather than of the API, because the
    ...                project's namespace no longer exists and the API that would answer for it
    ...                went with it.
    The dataset should not exist in database
    ${remaining}=    A preview of what reclamation would remove is produced
    Should Not Contain    ${remaining}    ${TEST_PROJECT}[name]
    ...    msg=Storage for the deleted project is still present

A preview of what reclamation would remove is produced
    [Documentation]    Reads what is currently reclaimable without changing anything.
    ${result}=    Run Process
    ...    kubectl    exec    -n    ${CLEANUP_NAMESPACE}    ${CLEANUP_DEPLOYMENT}
    ...    --    uv    run    reclaim-orphans    --dry-run
    ...    stderr=STDOUT
    Log    ${result.stdout}
    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=Preview did not complete: ${result.stdout}
    RETURN    ${result.stdout}

The project's stored data should still be available
    [Documentation]    Asked of the API rather than of storage, so this is independent of anything
    ...                reclamation reports about itself.
    Dataset should exist in database

The project has stored a dataset
    A dataset is uploaded

A project whose name was previously used by a deleted project exists
    [Documentation]    Creates a project, deletes it, and creates another with the same name once
    ...                that name is free again.
    ...
    ...                For the predecessor's leftovers to be judged reclaimable at all, they must
    ...                predate the new namespace by more than the configured skew margin. A run
    ...                takes minutes, so the environment must set
    ...                DELETED_PROJECT_CLEANUP_SKEW_MARGIN_SECONDS low or this scenario passes
    ...                without ever exercising the reuse rule.
    Given a ready project with user access exists
    VAR    ${reused_name}    ${TEST_PROJECT}[name]
    The project has stored a dataset
    When the project is deleted
    Wait for project name to be available    ${reused_name}
    Create Project With User Access    project_name=${reused_name}

The project is deleted
    Delete project request is sent
    Wait Until Keyword Succeeds    5 min    10 sec    Project namespace should be gone

Project namespace should be gone
    ${namespace}=    Get Project Namespace
    ${result}=    Run Process
    ...    kubectl    get    namespace    ${namespace}
    ...    stderr=STDOUT
    Should Not Be Equal As Integers    ${result.rc}    0
    ...    msg=Namespace ${namespace} still exists
