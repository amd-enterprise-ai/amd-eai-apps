# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Feature-layer BDD keywords for the global user menu.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
Resource            pages/user_menu_page.resource


*** Keywords ***
The user opens the user menu
    [Documentation]    Opens the global user menu dropdown from the header.

    Open user menu

The user menu should be labeled for actions
    [Documentation]    Verifies the shared menu label renders as user-facing text.

    ${accessible_name}=    Get user menu accessible name
    Should Be Equal As Strings    ${accessible_name}    Actions

Report issue menu entry should link to support mailto
    [Documentation]    Verifies the "Report issue" entry exposes a support mailto link.

    ${href}=    Get report issue menu item href
    Should Start With    ${href}    mailto:amd-eai-support@amd.com
    Should Contain    ${href}    subject=Issue%20report
