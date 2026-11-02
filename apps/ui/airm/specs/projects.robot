# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for AIRM project management.
...
...                 These tests verify the admin user experience for project lifecycle:
...                 creation, dashboard, quota configuration, member management,
...                 secrets and storages visibility, GPU preemption settings,
...                 status polling, and project deletion.
...
...                 Tests run against a live AIRM deployment and require an admin user
...                 with access to at least one healthy cluster.

Resource            resources/common/browser_setup.resource
Resource            resources/projects.resource

# API resources for project cleanup (resolved via pythonpath to AIRM API specs)
Resource            resources/common/airm_resource_cleanup.resource

Suite Teardown      Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
Admin creates a new project through the UI
    [Documentation]    Verify that an admin can create a project with a name and cluster,
    ...                the project appears in the list, and the user lands on the edit page.
    [Tags]    ui    airm    projects    create    smoke

    Given an admin user is logged in to AIRM
    And a healthy cluster is connected
    When the user creates a project with a name and cluster assignment
    Then the user is taken to the project edit page
    And the project appears in the project list

Newly created project transitions to ready status
    [Documentation]    Verify that a newly created project transitions from pending to ready
    ...                without manual page refresh, via automatic status polling.
    [Tags]    ui    airm    projects    status    polling

    Given an admin user is on the projects page
    When the user creates a project with a name and cluster assignment
    Then the project status should eventually be ready

Admin creates a project with GPU preemption enabled
    [Documentation]    Verify that an admin can enable GPU preemption settings during
    ...                project creation and the settings are saved.
    [Tags]    ui    airm    projects    create    preemption

    Given an admin user is on the projects page
    When the user creates a project with preemption enabled
    Then the preemption settings should be saved with the project

Admin views quota allocation details for a project
    [Documentation]    Verify that the quota tab displays resource allocation values
    ...                and admin controls for GPU, CPU, memory, and disk.
    [Tags]    ui    airm    projects    quota

    Given an admin user is editing a project
    When the user navigates to the quota tab
    Then the quota tab shows resource allocation values
    And admin quota controls are visible

Admin discards unsaved quota changes
    [Documentation]    Verify that after changing a guaranteed allocation on the quota tab,
    ...                discarding restores the previous values without saving.
    [Tags]    ui    airm    projects    quota

    Given an admin user is editing a project
    When the user navigates to the quota tab
    And the user notes the current CPU guaranteed allocation on the quota tab
    And the user increases the CPU guaranteed allocation once without saving
    And the user discards changes to the project settings form
    Then the CPU guaranteed allocation matches the noted value

Admin adds a team member to a project
    [Documentation]    Verify that an admin can add a platform user who is not yet
    ...                a project member via the members tab, and the user then
    ...                appears in the project members list.
    [Tags]    ui    airm    projects    members

    Given an admin user is editing a project
    And a platform user exists who is not a project member
    When the user navigates to the members tab
    And adds the user as a project member
    Then the user appears in the project members list

Admin views project secrets tab
    [Documentation]    Verify that the secrets tab is accessible and displays available
    ...                secrets on the project edit page.
    [Tags]    ui    airm    projects    secrets

    Given an admin user is editing a project
    When the user navigates to the secrets tab
    Then the secrets tab shows available secrets

Admin views project storages tab
    [Documentation]    Verify that the storages tab is accessible and displays available
    ...                storages on the project edit page.
    [Tags]    ui    airm    projects    storages

    Given an admin user is editing a project
    When the user navigates to the storages tab
    Then the storages tab shows available storages

Admin views project dashboard with metrics
    [Documentation]    Verify that the project dashboard displays overview metrics
    ...                including workload statistics and GPU usage information.
    [Tags]    ui    airm    projects    dashboard    metrics

    Given an admin user is viewing a project dashboard
    Then the project dashboard shows overview metrics
    And the project dashboard shows workloads

Admin deletes a project through the UI
    [Documentation]    Verify that an admin can delete a project via the dashboard
    ...                actions menu and the project is removed from the project list.
    [Tags]    ui    airm    projects    delete

    Given a ready project exists on the projects page
    When the user navigates to the created project dashboard
    And the user initiates project deletion from dashboard and confirms
    Then the project is removed from the project list
