# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for the global user menu.
...
...                 The user menu is rendered by the shared component library and is
...                 available from any page, so the dashboard is used only as a place
...                 where the app chrome is present.

Resource            resources/common/browser_setup.resource
Resource            resources/dashboard.resource
Resource            resources/user_menu.resource

Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
User menu is labeled for actions
    [Documentation]    Verify that the global user menu exposes an accessible label
    ...                describing its actions, rather than an untranslated key.
    [Tags]    ui    airm    navigation    user-menu    i18n    smoke

    Given an admin user is logged in
    And the user is on the dashboard
    When the user opens the user menu
    Then the user menu should be labeled for actions

Report issue menu entry links user to support mailto
    [Documentation]    Verify that the global user menu exposes the support mailto link.
    [Tags]    ui    airm    navigation    user-menu    i18n    smoke

    Given an admin user is logged in
    And the user is on the dashboard
    When the user opens the user menu
    Then report issue menu entry should link to support mailto
