# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for dashboard UI features.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)
Resource            common/session.resource
Resource            pages/dashboard_page.resource


*** Keywords ***
# =============================================================================
# Given keywords (UI preconditions)
# =============================================================================

User is on the dashboard page
    [Documentation]    Navigates to the project dashboard (landing page).
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to project dashboard    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

# =============================================================================
# When keywords (actions)
# =============================================================================

User switches to project "${project_name}"
    [Documentation]    Switches to a different project using the project selector.

    Select project    ${project_name}

# =============================================================================
# Then keywords (verification)
# =============================================================================

Dashboard should display the overview section
    [Documentation]    Verifies the Overview heading is visible on the dashboard.

    ${text}=    Get overview heading text
    Should Be Equal    ${text}    Overview

Dashboard should display the workloads section
    [Documentation]    Verifies the Workloads heading is visible on the dashboard.

    ${text}=    Get workloads heading text
    Should Be Equal    ${text}    Workloads

Dashboard should show workload stats card
    [Documentation]    Verifies the workloads stats card with project info is displayed.

    ${visible}=    Is workload stats card visible
    Should Be True    ${visible}    msg=Workloads stats card should be visible

Dashboard should show total workloads count
    [Documentation]    Verifies the total workloads label is visible in the stats card.

    ${visible}=    Is total workloads label visible
    Should Be True    ${visible}    msg=Total workloads count label should be visible

Dashboard should show GPU usage charts
    [Documentation]    Verifies both GPU Device Usage and GPU VRAM Usage charts are displayed.

    ${gpu_visible}=    Is GPU device usage chart visible
    Should Be True    ${gpu_visible}    msg=GPU Device Usage chart should be visible
    ${vram_visible}=    Is GPU VRAM usage chart visible
    Should Be True    ${vram_visible}    msg=GPU VRAM Usage chart should be visible

Dashboard should show time range selector
    [Documentation]    Verifies the time range selector is visible for chart periods.

    ${visible}=    Is time range selector visible
    Should Be True    ${visible}    msg=Time range selector should be visible

The chart time range control should be labeled for selection
    [Documentation]    Verifies the shared chart control uses a readable label.

    ${label}=    Get chart time range control label
    Should Be Equal    ${label}    Time range selection

Dashboard should show workloads table
    [Documentation]    Verifies the workloads table grid is visible below the charts.

    ${visible}=    Is workloads grid visible
    Should Be True    ${visible}    msg=Workloads table should be visible

Dashboard should reflect project "${project_name}"
    [Documentation]    Verifies the project selector shows the expected project name.

    ${selected}=    Get selected project name
    Should Contain    ${selected}    ${project_name}
    Wait for dashboard content
