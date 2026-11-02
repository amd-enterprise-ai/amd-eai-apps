# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for the AIRM admin dashboard.
...                 Contains selectors, atomic browser interactions, and page-level
...                 visibility/wait verification helpers for the cluster statistics,
...                 utilization charts, project consumption table, and time range selector.
Library             Collections


*** Variables ***
${DASHBOARD_PATH}                       /

# Cluster statistics section
${CLUSTERS_AND_NODES_HEADING}           css=h2:has-text("Clusters and Nodes")
${ALLOCATIONS_HEADING}                  css=h2:has-text("Allocations and Workloads")

# Consumption table
${CONSUMPTION_TABLE_HEADING}            css=span:has-text("Consumption by project")

# Chart cards
${GPU_MEMORY_CHART_HEADING}             css=span:has-text("GPU memory utilization")
${GPU_DEVICE_CHART_HEADING}             css=span:has-text("GPU device utilization")

# Time range selector
${TIME_RANGE_TABLIST}                   css=[role="tablist"]


*** Keywords ***
Navigate to dashboard
    [Documentation]    Navigates to the admin dashboard (root page) and waits for it to load.
    [Arguments]    ${base_url}

    Go To    ${base_url}${DASHBOARD_PATH}
    Wait For Elements State    css=main    visible    timeout=15s

Dashboard heading should be loaded
    [Documentation]    Waits for the "Clusters and Nodes" section heading to be visible,
    ...                indicating the dashboard has loaded its main content.

    Wait For Elements State    ${CLUSTERS_AND_NODES_HEADING}    visible    timeout=15s

Allocations section should be visible
    [Documentation]    Waits for the "Allocations and Workloads" section heading to be visible.

    Wait For Elements State    ${ALLOCATIONS_HEADING}    visible    timeout=15s

Statistics card should be visible
    [Documentation]    Asserts a statistics card with the given title text is visible
    ...                in the "Clusters and Nodes" section. Scoped to the section container
    ...                to avoid matching identically-named sidebar or nav items.
    [Arguments]    ${card_title}

    # Scope to the clusters section to avoid ambiguous matches with sidebar items
    VAR    ${selector}    css=h2:has-text("Clusters and Nodes") ~ div >> text="${card_title}"
    Wait For Elements State    ${selector}    visible    timeout=10s

Consumption table should be visible
    [Documentation]    Waits for the consumption-by-project table to be visible.

    Wait For Elements State    ${CONSUMPTION_TABLE_HEADING}    visible    timeout=15s

Get consumption table column headers
    [Documentation]    Returns the text of all column headers in the consumption table.

    VAR    ${header_selector}    css=[role="columnheader"]
    ${elements}=    Get Elements    ${header_selector}
    VAR    @{headers}
    FOR    ${element}    IN    @{elements}
        ${text}=    Get Text    ${element}
        IF    "${text}" != "${EMPTY}"
            Append To List    ${headers}    ${text}
        END
    END
    RETURN    ${headers}

Get consumption table row count
    [Documentation]    Returns the number of data rows in the consumption table.
    ...                Waits for at least one data row to render before counting.

    VAR    ${row_selector}    css=[role="row"][data-key]
    Wait For Elements State    ${row_selector} >> nth=0    visible    timeout=15s
    ${elements}=    Get Elements    ${row_selector}
    ${count}=    Get Length    ${elements}
    RETURN    ${count}

Scroll to chart section
    [Documentation]    Scrolls the chart section heading into view.

    Scroll To Element    ${GPU_MEMORY_CHART_HEADING}

Scroll to consumption section
    [Documentation]    Scrolls the consumption table heading into view.

    Scroll To Element    ${CONSUMPTION_TABLE_HEADING}

Scroll to allocations section
    [Documentation]    Scrolls the allocations section heading into view.

    Scroll To Element    ${ALLOCATIONS_HEADING}

GPU memory utilization chart should be visible
    [Documentation]    Waits for the GPU memory utilization chart card to be visible.

    Wait For Elements State    ${GPU_MEMORY_CHART_HEADING}    visible    timeout=15s

GPU device utilization chart should be visible
    [Documentation]    Waits for the GPU device utilization chart card to be visible.

    Wait For Elements State    ${GPU_DEVICE_CHART_HEADING}    visible    timeout=15s

Time range selector should be visible
    [Documentation]    Waits for the time range tab selector to be visible.

    Wait For Elements State    ${TIME_RANGE_TABLIST}    visible    timeout=10s

Get chart time range control label
    [Documentation]    Returns the accessible label of the chart time range control.

    ${label}=    Get Attribute    ${TIME_RANGE_TABLIST}    aria-label
    RETURN    ${label}

Get selected time range tab
    [Documentation]    Returns the text of the currently selected time range tab.

    VAR    ${selected_tab}    css=[role="tab"][aria-selected="true"]
    ${text}=    Get Text    ${selected_tab}
    RETURN    ${text}

Click time range tab
    [Documentation]    Clicks a time range tab by its visible text label.
    [Arguments]    ${tab_label}

    VAR    ${tab_selector}    css=[role="tab"]:has-text("${tab_label}")
    Click    ${tab_selector}

Get time range tab labels
    [Documentation]    Returns a list of all available time range tab labels.

    VAR    ${tab_selector}    css=[role="tab"]
    ${elements}=    Get Elements    ${tab_selector}
    VAR    @{labels}
    FOR    ${element}    IN    @{elements}
        ${text}=    Get Text    ${element}
        Append To List    ${labels}    ${text}
    END
    RETURN    ${labels}

Get allocation stat card count
    [Documentation]    Returns the number of matching stat cards in the allocations section.
    ...                Some stat card titles (e.g. "GPU utilization") also appear as table column
    ...                headers, so this keyword targets cards in the summary panel specifically.
    [Arguments]    ${card_title}

    # The summary stat cards are rendered as siblings of the consumption table card,
    # inside the allocations section. Target the card outside the table grid.
    VAR    ${selector}    css=div:not([role="grid"]) > div:not([role="columnheader"]) >> text="${card_title}"
    ${count}=    Get Element Count    ${selector}
    RETURN    ${count}
