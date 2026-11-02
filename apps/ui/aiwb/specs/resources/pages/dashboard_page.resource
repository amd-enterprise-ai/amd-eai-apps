# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for the AIWB Dashboard overview section.
...                 Contains selectors and atomic browser interactions only.
...                 The dashboard is the project landing page at /${project}/.
...                 Business logic and assertions belong in feature resources.


*** Variables ***
# Use exact text matching to avoid matching documentation section headings
# like "AMD AI Workbench Overview" or "Model Inference Overview"
${OVERVIEW_HEADING_SELECTOR}            h3:text-is("Overview")
${WORKLOADS_HEADING_SELECTOR}           h3:text-is("Workloads")
${WORKLOADS_STATS_TITLE_SELECTOR}       text="Workloads in project"
${TOTAL_WORKLOADS_SELECTOR}             text="total workloads"
${GPU_DEVICE_USAGE_SELECTOR}            text="GPU Device Usage"
${GPU_VRAM_USAGE_SELECTOR}              text="GPU VRAM Usage"
${TIME_RANGE_TABLIST_SELECTOR}          [role="tablist"]
${WORKLOADS_GRID_SELECTOR}              [role="grid"]
${PROJECT_SELECTOR_BUTTON}              [data-testid="project-select"]


*** Keywords ***
Navigate to project dashboard
    [Documentation]    Navigates to the project dashboard (landing page).
    [Arguments]    ${base_url}    ${project}

    Go To    ${base_url}/${project}/
    Wait For Elements State    ${OVERVIEW_HEADING_SELECTOR}    visible    timeout=30s

Wait for dashboard content
    [Documentation]    Waits for the key dashboard sections to be visible.

    Wait For Elements State    ${OVERVIEW_HEADING_SELECTOR}    visible    timeout=15s
    Wait For Elements State    ${WORKLOADS_HEADING_SELECTOR}    visible    timeout=15s

Get overview heading text
    [Documentation]    Returns the text of the Overview heading.

    ${text}=    Get Text    ${OVERVIEW_HEADING_SELECTOR}
    RETURN    ${text}

Get workloads heading text
    [Documentation]    Returns the text of the Workloads heading.

    ${text}=    Get Text    ${WORKLOADS_HEADING_SELECTOR}
    RETURN    ${text}

Is workload stats card visible
    [Documentation]    Returns whether the workloads stats card is visible.

    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${WORKLOADS_STATS_TITLE_SELECTOR}    visible    timeout=10s
    RETURN    ${visible}

Is total workloads label visible
    [Documentation]    Returns whether the total workloads label is visible.

    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${TOTAL_WORKLOADS_SELECTOR}    visible    timeout=10s
    RETURN    ${visible}

Is GPU device usage chart visible
    [Documentation]    Returns whether the GPU Device Usage chart is visible.

    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${GPU_DEVICE_USAGE_SELECTOR}    visible    timeout=10s
    RETURN    ${visible}

Is GPU VRAM usage chart visible
    [Documentation]    Returns whether the GPU VRAM Usage chart is visible.

    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${GPU_VRAM_USAGE_SELECTOR}    visible    timeout=10s
    RETURN    ${visible}

Is time range selector visible
    [Documentation]    Returns whether the time range selector tablist is visible.

    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    css=${TIME_RANGE_TABLIST_SELECTOR}    visible    timeout=10s
    RETURN    ${visible}

Get chart time range control label
    [Documentation]    Returns the accessible label of the chart time range control.

    ${label}=    Get Attribute    css=${TIME_RANGE_TABLIST_SELECTOR}    aria-label
    RETURN    ${label}

Is workloads grid visible
    [Documentation]    Returns whether the workloads table grid is visible.

    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    css=${WORKLOADS_GRID_SELECTOR}    visible    timeout=15s
    RETURN    ${visible}

Get selected project name
    [Documentation]    Returns the text of the project selector button (shows active project).

    VAR    ${btn}    css=${PROJECT_SELECTOR_BUTTON} >> nth=0
    ${text}=    Get Text    ${btn}
    RETURN    ${text}
