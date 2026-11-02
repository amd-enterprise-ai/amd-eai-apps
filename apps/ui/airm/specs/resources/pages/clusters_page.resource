# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for AIRM UI clusters list page.
...                 Provides selectors and atomic browser interactions for the cluster list,
...                 statistics cards, search filter, and connect cluster wizard.


*** Variables ***
${CLUSTERS_PATH}                    /clusters
${SEARCH_INPUT_PLACEHOLDER}         Search
${CONNECT_CLUSTER_BUTTON}           Connect a cluster
${CONNECT_WIZARD_TITLE}             Connect a new cluster
${ACTIVE_CLUSTERS_HEADING}          Active clusters


*** Keywords ***
Navigate to clusters page
    [Documentation]    Navigates to the clusters page and waits for it to load.
    [Arguments]    ${base_url}
    Go To    ${base_url}${CLUSTERS_PATH}
    Wait For Elements State    css=main    visible    timeout=15s

Get clusters stats text
    [Documentation]    Returns the text from the cluster statistics cards section.
    ...                Stats cards include: Clusters count, Available nodes, Allocated GPUs, Running workloads.
    ${text}=    Get Text    css=main
    RETURN    ${text}

Get cluster row count
    [Documentation]    Returns the number of cluster data rows in the active clusters table.
    ...                The active clusters grid is the first grid on the page.
    ${count}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        const grid = document.querySelector('[role="grid"]');
    ...        if (!grid) return 0;
    ...        const bodyGroup = grid.querySelectorAll('[role="rowgroup"]')[1];
    ...        if (!bodyGroup) return 0;
    ...        return bodyGroup.querySelectorAll('[role="row"]').length;
    ...    }
    RETURN    ${count}

Cluster row should be visible
    [Documentation]    Waits for a cluster row with the given name to be visible.
    [Arguments]    ${cluster_name}
    Wait For Elements State    text="${cluster_name}"    visible    timeout=15s

Click cluster row
    [Documentation]    Clicks on a cluster row to navigate to its detail page.
    [Arguments]    ${cluster_name}
    Click    text="${cluster_name}"

Active clusters heading should be visible
    [Documentation]    Waits for the "Active clusters" accordion heading to be visible.
    Wait For Elements State    css=h2:has-text("${ACTIVE_CLUSTERS_HEADING}")    visible    timeout=15s

Enter cluster search text
    [Documentation]    Types text into the search input field on the clusters page.
    [Arguments]    ${search_text}
    VAR    ${search_input}    css=input[placeholder="${SEARCH_INPUT_PLACEHOLDER}"]
    Fill Text    ${search_input}    ${search_text}

Get visible cluster names
    [Documentation]    Returns a list of cluster names currently visible in the active clusters table.
    ${names}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        const grid = document.querySelector('[role="grid"]');
    ...        if (!grid) return [];
    ...        const bodyGroup = grid.querySelectorAll('[role="rowgroup"]')[1];
    ...        if (!bodyGroup) return [];
    ...        const headers = bodyGroup.querySelectorAll('[role="rowheader"]');
    ...        return Array.from(headers).map(el => el.textContent.trim()).filter(t => t);
    ...    }
    RETURN    ${names}

Click connect cluster button
    [Documentation]    Clicks the "Connect a cluster" button to open the connection wizard.
    Wait For Elements State    css=button:has-text("${CONNECT_CLUSTER_BUTTON}")    visible    timeout=10s
    Click    css=button:has-text("${CONNECT_CLUSTER_BUTTON}")

Connect wizard should be visible
    [Documentation]    Checks that the connect cluster wizard modal is visible.
    ...                Uses the dialog/modal role for precise targeting.
    VAR    ${selector}    css=[role="dialog"]:has-text("${CONNECT_WIZARD_TITLE}")
    Wait For Elements State    ${selector}    visible    timeout=10s

Get connect wizard text
    [Documentation]    Returns the text content of the connect cluster wizard modal.
    VAR    ${selector}    css=[role="dialog"]
    ${text}=    Get Text    ${selector}
    RETURN    ${text}
