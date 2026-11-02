# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for the AIWB workloads polymorphic read-only view.
...                 The workloads endpoint is the cross-cutting surface that returns
...                 all workload types (inference, fine-tuning, workspaces) for shared
...                 read concerns. Mutations and capability-specific filters live on
...                 their own routers.
Resource            resources/aiwb_workloads.resource
Resource            resources/airm_projects.resource


*** Test Cases ***
Workloads endpoint serves only cross-cutting read operations
    [Documentation]    Acceptance scenario for the read-only workloads view.
    ...    Polymorphic list/get/logs/metrics remain on the workloads router;
    ...    chat, delete, and the chattable filter must respond from the
    ...    capability endpoints instead (inference / fine-tuning / workspaces).
    [Tags]    workloads    smoke

    Given a ready project with user access exists
    When the user lists workloads in the project
    Then the polymorphic list returns entries for the project
    When the user requests a removed workload mutation
    Then the removed routes should no longer be served

User can browse project workloads page by page
    [Documentation]    Workloads in a project are served in pages rather than as
    ...                one flat list.
    [Tags]    workloads    list    pagination

    Given a ready project with user access exists
    When the user lists workloads in the project
    Then the result is returned page by page

User can navigate between pages of project workloads
    [Documentation]    A consumer can move from one page of workloads to the
    ...                next without seeding many workloads — verified by
    ...                stepping through with a single-item page.
    [Tags]    workloads    list    pagination

    Given a ready project with user access exists
    When the user lists workloads with a page size of 1
    Then the result is returned page by page
    And the result reflects the requested page    1
    When the user requests page 2 with page size 1
    Then the result is returned page by page
    And the result reflects the requested page    2
