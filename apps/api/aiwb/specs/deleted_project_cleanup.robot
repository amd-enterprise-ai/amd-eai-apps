# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Reclaiming the data a deleted project leaves behind.
...
...                 A deleted project takes its namespace with it but not its stored files, its
...                 API keys, or the credentials behind them. These scenarios cover both halves of
...                 that: that abandoned data is reclaimed, and that data belonging to a project
...                 still in use never is.
...
...                 Requires reclamation to be reachable in the environment under test, and the
...                 skew margin to be set low there — see the resource file for why.

Resource            resources/aiwb_common.resource
Resource            resources/aiwb_datasets.resource
Resource            resources/aiwb_deleted_project_cleanup.resource
Resource            resources/airm_projects.resource

Suite Teardown      Clean Up All Created Projects


*** Test Cases ***
Data left behind by a deleted project is reclaimed
    [Documentation]    The reason this exists: storage and credentials outlive the project.
    [Tags]    cleanup    projects    deletion
    Given a ready project with user access exists
    And the project has stored a dataset
    When the project is deleted
    And the platform reclaims data from deleted projects
    Then the project's stored data should be gone

A project that reuses a deleted project's name keeps its own data
    [Documentation]    The failure this design guards against. A name becomes available again as
    ...                soon as its project is deleted, so a successor's data sits under the same
    ...                storage prefix its predecessor used.
    [Tags]    cleanup    projects    deletion
    Given a project whose name was previously used by a deleted project exists
    And the project has stored a dataset
    When the platform reclaims data from deleted projects
    Then the project's stored data should still be available

A project in use is never reclaimed from
    [Documentation]    The regression guard: proves reclamation is discriminating rather than
    ...                simply deleting whatever it finds.
    [Tags]    cleanup    projects    deletion
    Given a ready project with user access exists
    And the project has stored a dataset
    When the platform reclaims data from deleted projects
    Then the project's stored data should still be available
