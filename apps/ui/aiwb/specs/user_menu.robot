# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for the global user menu.
...
...                 These tests verify user menu entries that are available from any
...                 page in the app (e.g. "Report issue"). A minimal project context
...                 is required so the app chrome, including the user menu, is rendered.

# UI resources (feature layer + browser setup)
Resource            resources/common/browser_setup.resource
Resource            resources/aims.resource
Resource            resources/user_menu.resource

# API resources (infrastructure preconditions, resolved via pythonpath)
Resource            resources/airm_projects.resource

Suite Teardown      Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
# =============================================================================
# Report Issue
# =============================================================================

Report issue menu entry links user to support mailto
    [Documentation]    Verify that the user menu exposes a "Report issue" entry that
    ...                opens a pre-addressed support mailto link so users can report
    ...                problems to the support team from any page.
    [Tags]    ui    navigation    user-menu    report-issue    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user opens the user menu
    Then report issue menu entry should link to support mailto

User menu is labeled for actions
    [Documentation]    Verify that the global user menu exposes an accessible label
    ...                describing its actions.
    [Tags]    ui    navigation    user-menu    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user opens the user menu
    Then the user menu should be labeled for actions
