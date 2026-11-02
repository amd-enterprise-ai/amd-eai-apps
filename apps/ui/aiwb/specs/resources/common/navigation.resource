# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Site-wide navigation keywords for AIWB UI.
...                 Covers project selection and other global navigation elements
...                 that appear across all pages.


*** Keywords ***
Navigate To Project Page
    [Documentation]    Navigates directly to the project URL and waits for the app to load.
    ...                Used after login flows where the user needs to land in a specific project
    ...                context (e.g., new users who have no previously selected namespace).
    [Arguments]    ${base_url}    ${project_name}

    Go To    ${base_url}/${project_name}
    Wait For Elements State    css=main    visible    timeout=30s

Select project
    [Documentation]    Selects a project from the project selector dropdown in the header.
    ...                Skips selection if the project is already active.
    [Arguments]    ${project_name}

    Wait For Elements State    css=main    visible    timeout=15s

    # Check if the project is already selected
    # Use data-testid with >> nth=0 to select the first (toolbar) project selector
    VAR    ${project_btn}    css=[data-testid="project-select"] >> nth=0
    ${already_selected}=    Run Keyword And Return Status
    ...    Get Text    ${project_btn}    contains    ${project_name}

    IF    ${already_selected}
        RETURN
    END

    Click    ${project_btn}

    # Wait for the React Aria listbox dropdown
    VAR    ${listbox}    css=[role="listbox"]
    Wait For Elements State    ${listbox}    visible    timeout=10s

    # Click the project option
    VAR    ${option}    css=li[role="option"][data-key="${project_name}"]
    Click    ${option}

    # Wait for the selector button to reflect the new project
    Wait For Elements State    button[aria-label="Selected project"]:has-text("${project_name}")    visible    timeout=15s

Get menu group expanded state
    [Documentation]    Returns the expanded state of a named menu group.
    [Arguments]    ${group_name}

    ${expanded}=    Get Attribute
    ...    css=#sidebar-nav-panel >> role=button[name="${group_name}"]
    ...    aria-expanded
    RETURN    ${expanded}

Wait for application title
    [Documentation]    Waits for the application title in the sidebar.
    [Arguments]    ${app_title}

    Wait For Elements State
    ...    css=#sidebar-nav-panel span:text-is("${app_title}")
    ...    visible
    ...    timeout=10s

Wait for menu page
    [Documentation]    Waits for a named child page link to be visible.
    [Arguments]    ${page_name}

    Wait For Elements State
    ...    role=link[name="${page_name}"]
    ...    visible
    ...    timeout=10s

Click menu group
    [Documentation]    Expands or collapses a named menu group.
    [Arguments]    ${group_name}

    Click    role=button[name="${group_name}"]

Click menu page
    [Documentation]    Selects a named child page.
    [Arguments]    ${page_name}

    Click    role=link[name="${page_name}"]

Focus menu group
    [Documentation]    Moves keyboard focus directly onto a named menu group's toggle button.
    [Arguments]    ${group_name}

    Focus    css=#sidebar-nav-panel >> role=button[name="${group_name}"]

Press Tab
    [Documentation]    Presses the Tab key, moving focus to the next focusable element.

    Keyboard Key    press    Tab

Get menu group focus state
    [Documentation]    Returns whether a named menu group's toggle button currently has focus.
    [Arguments]    ${group_name}

    ${focused}=    Get Element States
    ...    css=#sidebar-nav-panel >> role=button[name="${group_name}"]
    ...    then    bool(value & focused)
    RETURN    ${focused}

Get menu page focus state
    [Documentation]    Returns whether a named child page link currently has focus.
    [Arguments]    ${page_name}

    ${focused}=    Get Element States
    ...    css=#sidebar-nav-panel >> role=link[name="${page_name}"]
    ...    then    bool(value & focused)
    RETURN    ${focused}

Get page location step
    [Documentation]    Returns a breadcrumb label by its zero-based position.
    [Arguments]    ${index}

    ${label}=    Get Text
    ...    css=nav[aria-label="Breadcrumb"] li >> nth=${index}
    RETURN    ${label}

Get menu page current state
    [Documentation]    Returns whether a named child link marks the current page.
    [Arguments]    ${page_name}

    ${current}=    Get Attribute    role=link[name="${page_name}"]    aria-current
    RETURN    ${current}

Get menu group current state
    [Documentation]    Returns whether a named menu group represents the current section.
    [Arguments]    ${group_name}

    ${current}=    Get Attribute    role=button[name="${group_name}"]    aria-current
    RETURN    ${current}

Collapse desktop menu
    [Documentation]    Collapses the desktop navigation panel.

    Click    css=#sidebar-nav-panel button[aria-label="Collapse sidebar"]
    Wait For Elements State
    ...    css=#sidebar-nav-panel button[aria-label="Expand sidebar"]
    ...    visible
    ...    timeout=10s

Point at desktop menu
    [Documentation]    Moves the pointer over the desktop navigation panel.

    Hover    css=#sidebar-nav-panel .menu-item >> nth=0

Point at page content
    [Documentation]    Moves the pointer over the main page content.

    Hover    css=main

Get page content horizontal position
    [Documentation]    Returns the horizontal position of the main page content.

    ${bounds}=    Get BoundingBox    css=main
    RETURN    ${bounds}[x]

Get menu page bounds
    [Documentation]    Returns the bounds of a named menu link.
    [Arguments]    ${page_name}

    ${bounds}=    Get BoundingBox
    ...    css=#sidebar-nav-panel >> role=link[name="${page_name}"]
    RETURN    ${bounds}

Get selected menu item bounds
    [Documentation]    Returns the bounds of the selected menu link.

    ${bounds}=    Get BoundingBox
    ...    css=#sidebar-nav-panel .menu-item[aria-current="page"]
    RETURN    ${bounds}

Get collapsed menu bounds
    [Documentation]    Returns the bounds reserved by the collapsed menu.

    ${bounds}=    Get BoundingBox
    ...    css=[data-testid="desktop-navigation-spacer"]
    RETURN    ${bounds}

Wait for navigation dim layer
    [Documentation]    Waits for the navigation backdrop to be visible.

    Wait For Elements State
    ...    css=[data-testid="navigation-dim-layer"]
    ...    visible
    ...    timeout=10s

Get application title count
    [Documentation]    Returns the number of matching application title elements.
    [Arguments]    ${app_title}

    ${count}=    Get Element Count
    ...    css=#sidebar-nav-panel span:text-is("${app_title}")
    RETURN    ${count}
