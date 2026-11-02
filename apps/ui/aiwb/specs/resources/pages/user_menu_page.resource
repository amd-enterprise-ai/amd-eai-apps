# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for the global user menu (dropdown next to the avatar).
...                 Contains selectors and atomic browser interactions only.
...                 Business logic and assertions belong in feature resources.


*** Variables ***
# The user menu trigger is the avatar pill in the global toolbar. Pages render
# their own dropdown triggers, so the lookup is scoped to the shared user-menu
# container rather than relying on DOM order.
${USER_MENU_TRIGGER_SELECTOR}        [data-testid="user-menu"] [data-slot="dropdown-trigger"]
${USER_MENU_SELECTOR}                [role="menu"]
${REPORT_ISSUE_ITEM_SELECTOR}        ${USER_MENU_SELECTOR} [role="menuitem"]:has-text("Report issue")


*** Keywords ***
Open user menu
    [Documentation]    Clicks the user avatar/menu trigger to open the global user menu
    ...                and waits for the dropdown menu to be visible.

    Click    css=${USER_MENU_TRIGGER_SELECTOR}
    Wait For Elements State    css=${USER_MENU_SELECTOR}    visible    timeout=10s

Get user menu accessible name
    [Documentation]    Returns the accessible name of the open user menu.

    ${name}=    Get Attribute    css=${USER_MENU_SELECTOR}    aria-label
    RETURN    ${name}

Get report issue menu item href
    [Documentation]    Returns the href of the "Report issue" entry in the (open) user menu.

    Wait For Elements State    css=${REPORT_ISSUE_ITEM_SELECTOR}    visible    timeout=10s
    ${href}=    Get Attribute    css=${REPORT_ISSUE_ITEM_SELECTOR}    href
    RETURN    ${href}
