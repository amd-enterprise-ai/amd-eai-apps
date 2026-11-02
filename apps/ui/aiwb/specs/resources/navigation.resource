# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for sidebar navigation.
Resource            common/navigation.resource
Resource            pages/datasets_page.resource
Resource            pages/models_page.resource


*** Keywords ***
AI Workbench application title should be visible
    [Documentation]    Verifies the current application name in the sidebar.

    Wait for application title    AI Workbench

Menu page names should be visible
    [Documentation]    Verifies labels appear when the collapsed menu is revealed.

    Wait for menu page    Dashboard
    Wait for menu page    API Keys

${group} menu group should be ${state:expanded|collapsed}
    [Documentation]    Verifies whether a menu group is expanded.

    VAR    ${expected}    ${{ 'true' if $state == 'expanded' else 'false' }}
    ${expanded}=    Get menu group expanded state    ${group}
    Should Be Equal    ${expanded}    ${expected}

User selects ${group} in the menu
    [Documentation]    Expands or collapses a top-level menu group.

    Click menu group    ${group}

User selects ${page} from ${group} in the menu
    [Documentation]    Opens a page from a menu group.

    Click menu group    ${group}
    Click menu page    ${page}

User tabs from ${group} menu group
    [Documentation]    Moves focus onto a menu group's toggle button, then presses Tab.

    Focus menu group    ${group}
    Press Tab

User tabs to the next menu item
    [Documentation]    Presses Tab, moving focus to the next reachable sidebar element.

    Press Tab

Focus should be on ${group} menu group
    [Documentation]    Verifies a named menu group's toggle button currently has focus.

    ${focused}=    Get menu group focus state    ${group}
    Should Be True    ${focused}

Focus should be on ${page} page link
    [Documentation]    Verifies a named child page link currently has focus.

    ${focused}=    Get menu page focus state    ${page}
    Should Be True    ${focused}

AIM catalog should be shown
    [Documentation]    Verifies that the AIM catalog page is visible.

    Wait for AIM Catalog page

${page} should be highlighted in the menu
    [Documentation]    Verifies a child is the selected menu item.

    ${current}=    Get menu page current state    ${page}
    Should Be Equal    ${current}    page

${group} menu group should be highlighted
    [Documentation]    Verifies a menu group represents the current section.

    ${current}=    Get menu group current state    ${group}
    Should Be Equal    ${current}    true

User selects Fine-tune models in the menu
    [Documentation]    Opens Fine-tune models from the Fine-tuning group.

    Click menu group    Fine-tuning
    Click menu page    Fine-tune models

Datasets should be shown
    [Documentation]    Verifies that the Datasets page is visible.

    Wait for datasets page

Fine-tune models should be shown
    [Documentation]    Verifies that the Fine-tune models page is visible.

    Wait for fine-tune models page

The page location should be shown as
    [Documentation]    Verifies the page's group and title breadcrumbs.
    [Arguments]    ${group}    ${page}

    ${group_step}=    Get page location step    0
    ${page_step}=    Get page location step    1
    Should Be Equal    ${group_step}    ${group}
    Should Be Equal    ${page_step}    ${page}

The menu is collapsed
    [Documentation]    Collapses the desktop menu.

    Collapse desktop menu

User points at the menu
    [Documentation]    Records the content position and reveals the collapsed menu.

    ${main_x}=    Get page content horizontal position
    VAR    ${MAIN_X_BEFORE_MENU_HOVER}    ${main_x}    scope=TEST
    ${first_item}=    Get menu page bounds    Dashboard
    ${second_item}=    Get menu page bounds    API Keys
    ${item_spacing}=    Evaluate    ${second_item}[y] - ${first_item}[y]
    VAR    ${MENU_ITEM_HEIGHT_BEFORE_HOVER}    ${first_item}[height]    scope=TEST
    VAR    ${MENU_ITEM_SPACING_BEFORE_HOVER}    ${item_spacing}    scope=TEST
    Point at desktop menu

The page content should stay in place
    [Documentation]    Verifies revealing the menu does not reflow page content.

    ${main_x}=    Get page content horizontal position
    Should Be Equal As Numbers    ${main_x}    ${MAIN_X_BEFORE_MENU_HOVER}

Menu item spacing should stay the same
    [Documentation]    Verifies menu rows keep the same height and spacing on reveal.

    ${first_item}=    Get menu page bounds    Dashboard
    ${second_item}=    Get menu page bounds    API Keys
    ${item_spacing}=    Evaluate    ${second_item}[y] - ${first_item}[y]
    Should Be Equal As Numbers
    ...    ${first_item}[height]
    ...    ${MENU_ITEM_HEIGHT_BEFORE_HOVER}
    Should Be Equal As Numbers
    ...    ${item_spacing}
    ...    ${MENU_ITEM_SPACING_BEFORE_HOVER}

The selected menu item should fit within the collapsed menu
    [Documentation]    Verifies the selected item stays inside the mini sidebar.

    ${selected_item}=    Get selected menu item bounds
    ${collapsed_menu}=    Get collapsed menu bounds
    ${selected_right}=    Evaluate    ${selected_item}[x] + ${selected_item}[width]
    ${menu_right}=    Evaluate    ${collapsed_menu}[x] + ${collapsed_menu}[width]
    Should Be True    ${selected_item}[x] >= ${collapsed_menu}[x]
    Should Be True    ${selected_right} <= ${menu_right}

The page content should be dimmed
    [Documentation]    Verifies the page dimmer is visible behind the revealed menu.

    Wait for navigation dim layer

User points away from the menu
    [Documentation]    Moves the pointer from the menu to the page.

    Point at page content

Menu page names should be hidden
    [Documentation]    Verifies labels disappear after the collapse delay.

    Wait Until Keyword Succeeds    2s    100ms    Application title should be absent

Application title should be absent
    [Documentation]    Verifies the expanded-menu application title is not rendered.

    ${count}=    Get application title count    AI Workbench
    Should Be Equal As Integers    ${count}    0
