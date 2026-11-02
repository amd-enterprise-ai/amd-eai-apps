# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for the AIRM admin dashboard.
...
...                 The dashboard is the admin landing page showing cluster-wide statistics,
...                 GPU utilization charts, and per-project resource consumption. These tests
...                 verify that dashboard elements render with real backend data.
...
...                 Dashboard access is admin-only. Non-admin access restriction is covered
...                 in the RBAC test suite.

Resource            resources/common/browser_setup.resource
Resource            resources/dashboard.resource

Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
Dashboard displays cluster statistics
    [Documentation]    Verify that the admin dashboard shows cluster-wide statistics
    ...                including cluster count, GPU node count, and GPU availability.
    [Tags]    ui    airm    dashboard    statistics    smoke

    Given an admin user is logged in
    When the user views the dashboard
    Then cluster statistics should be displayed

Dashboard displays GPU utilization charts
    [Documentation]    Verify that the dashboard renders GPU memory and device utilization
    ...                charts with the time range selector.
    [Tags]    ui    airm    dashboard    charts    metrics

    Given an admin user is logged in
    And the user is on the dashboard
    When the user views the utilization charts
    Then GPU memory utilization chart should be displayed
    And GPU device utilization chart should be displayed
    And time range selector should offer expected options

Shared component labels on the dashboard show readable text
    [Documentation]    Verify that shared chart controls show human-readable labels
    ...                instead of untranslated key strings.
    [Tags]    ui    airm    dashboard    i18n    shared-components    smoke

    Given an admin user is logged in
    And the user is on the dashboard
    Then the chart time range control should be labeled for selection

Dashboard shows per-project resource consumption
    [Documentation]    Verify that the consumption-by-project table displays project names
    ...                with GPU allocation, utilization, and workload counts.
    [Tags]    ui    airm    dashboard    consumption    projects

    Given an admin user is logged in
    And the user is on the dashboard
    When the user views the consumption table
    Then projects should be listed with GPU allocation and utilization
    And running and pending workload counts should be shown per project

Changing time range updates dashboard charts
    [Documentation]    Verify that selecting a different time range tab causes the
    ...                utilization charts to update to the selected period.
    [Tags]    ui    airm    dashboard    charts    time-range

    Given an admin user is logged in
    And the user is on the dashboard
    When the user selects the "24 hours" time range
    Then utilization charts should update to reflect the selected period    24 hours

Dashboard displays allocation and workload summary
    [Documentation]    Verify that the dashboard shows summary cards for GPU utilization,
    ...                running workloads, and pending workloads alongside the consumption table.
    [Tags]    ui    airm    dashboard    statistics    workloads

    Given an admin user is logged in
    And the user is on the dashboard
    When the user views the allocations section
    Then allocation and workload summary cards should be displayed
