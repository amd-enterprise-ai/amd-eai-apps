# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Feature-layer BDD keywords for AIRM dashboard testing.
...                 Composes page-layer interactions into business-meaningful keywords
...                 that describe dashboard overview, statistics, charts, and consumption behavior.
Resource            common/session.resource
Resource            common/navigation.resource
Resource            pages/dashboard_page.resource


*** Keywords ***
An admin user is logged in
    [Documentation]    Logs in as an admin user via Keycloak.
    Admin user is logged in

The user is on the dashboard
    [Documentation]    Navigates to the admin dashboard page.
    Navigate to dashboard    ${UI_BASE_URL}
    Dashboard heading should be loaded

The user views the dashboard
    [Documentation]    Navigates to the dashboard and waits for content to load.
    Navigate to dashboard    ${UI_BASE_URL}
    Dashboard heading should be loaded

The user views the utilization charts
    [Documentation]    Scrolls to the chart section so it is in view.
    Scroll to chart section

The user views the consumption table
    [Documentation]    Scrolls to the consumption-by-project section.
    Scroll to consumption section

The user views the allocations section
    [Documentation]    Scrolls to the allocations and workloads section of the dashboard.
    Scroll to allocations section

The user selects the "${time_range}" time range
    [Documentation]    Clicks a time range tab to change the chart period.
    Click time range tab    ${time_range}

Cluster statistics should be displayed
    [Documentation]    Verifies the "Clusters and Nodes" section is visible with its stat cards.
    ...                Checks that all four expected stat cards are rendered.

    Dashboard heading should be loaded
    Statistics card should be visible    Clusters
    Statistics card should be visible    GPU Nodes
    Statistics card should be visible    Available GPUs
    Statistics card should be visible    Allocated GPUs

GPU memory utilization chart should be displayed
    [Documentation]    Verifies the GPU memory utilization chart is rendered on the dashboard.
    GPU memory utilization chart should be visible

GPU device utilization chart should be displayed
    [Documentation]    Verifies the GPU device utilization chart is rendered on the dashboard.
    GPU device utilization chart should be visible

Projects should be listed with GPU allocation and utilization
    [Documentation]    Verifies the consumption table is visible and has the expected column headers
    ...                for project resource usage. Header text is compared case-insensitively
    ...                because HeroUI renders headers in uppercase via CSS text-transform.

    Consumption table should be visible

    ${headers}=    Get consumption table column headers
    Log    Table headers: ${headers}    INFO

    VAR    ${headers_upper}    ${{[h.upper() for h in $headers]}}
    Should Contain    ${headers_upper}    PROJECT
    Should Contain    ${headers_upper}    GPU ALLOCATION
    Should Contain    ${headers_upper}    GPU UTILIZATION

Running and pending workload counts should be shown per project
    [Documentation]    Verifies the consumption table includes columns for running and pending workloads.

    ${headers}=    Get consumption table column headers
    VAR    ${headers_upper}    ${{[h.upper() for h in $headers]}}

    Should Contain    ${headers_upper}    RUNNING WORKLOADS
    Should Contain    ${headers_upper}    PENDING WORKLOADS

    # Verify at least one data row exists
    ${row_count}=    Get consumption table row count
    Should Be True    ${row_count} > 0
    ...    msg=Consumption table should have at least one project row, but found ${row_count}

Utilization charts should update to reflect the selected period
    [Documentation]    Verifies the time range selector reflects the chosen tab.
    ...                After selecting a different time range, the charts reload. We verify
    ...                the tab selection changed and the charts are still rendered.
    [Arguments]    ${expected_tab}

    # Verify the tab is now selected
    ${selected}=    Get selected time range tab
    Should Contain    ${selected}    ${expected_tab}
    ...    msg=Expected time range "${expected_tab}" to be selected but found "${selected}"

    # Verify charts are still visible after the time range change
    GPU memory utilization chart should be visible
    GPU device utilization chart should be visible

Time range selector should offer expected options
    [Documentation]    Verifies the time range selector shows the expected period tabs.

    Time range selector should be visible

    ${labels}=    Get time range tab labels
    Log    Available time range options: ${labels}    INFO

    Should Contain    ${labels}    1 hour
    Should Contain    ${labels}    24 hours
    Should Contain    ${labels}    7 days

The chart time range control should be labeled for selection
    [Documentation]    Verifies the shared chart control uses a readable label.

    ${label}=    Get chart time range control label
    Should Be Equal    ${label}    Time range selection

Allocation and workload summary cards should be displayed
    [Documentation]    Verifies the allocation summary cards are visible in the dashboard.
    ...                "GPU utilization" appears both as a table column header and as a stat card,
    ...                so we verify the section heading and use nth-match for the stat card text.

    Allocations section should be visible

    # All three stat card titles also appear as table column headers,
    # so use the allocation-specific getter that avoids ambiguity.
    Allocation stat card should be visible    GPU utilization
    Allocation stat card should be visible    Running workloads
    Allocation stat card should be visible    Pending workloads

Allocation stat card should be visible
    [Documentation]    Asserts that an allocation summary stat card with the given title
    ...                is present on the dashboard.
    [Arguments]    ${card_title}

    ${count}=    Get allocation stat card count    ${card_title}
    Should Be True    ${count} > 0
    ...    msg=Expected allocation stat card "${card_title}" to be visible on the dashboard
