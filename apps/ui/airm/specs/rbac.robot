# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for AIRM role-based access control.
...
...                 These tests verify that team member users see a restricted UI view
...                 compared to platform administrators. The AIRM UI enforces RBAC
...                 by filtering sidebar navigation items, redirecting from admin-only
...                 pages, and hiding admin-only settings.
...
...                 All tests log in as a team member user to verify restrictions.

Resource            resources/common/browser_setup.resource
Resource            resources/rbac.resource

Suite Setup         Require the team member account
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
Team member sees restricted sidebar navigation
    [Documentation]    Verify that a team member user only sees navigation items
    ...                accessible to their role, and admin-only items are hidden.
    [Tags]    ui    airm    rbac    access-control    smoke

    Given a team member user is logged in
    When the sidebar navigation is rendered
    Then admin-only navigation items should be hidden
    And team member navigation items should be visible

Team member cannot access admin-only pages
    [Documentation]    Verify that directly navigating to admin-only page URLs
    ...                redirects the team member to an accessible page.
    ...                Dashboard and Users pages enforce server-side RBAC and redirect.
    [Tags]    ui    airm    rbac    access-control

    Given a team member user is logged in
    When the user navigates to the admin dashboard directly
    Then the page should not be accessible

    When the user navigates to the users page directly
    Then the page should not be accessible

Team member views their project dashboard
    [Documentation]    Verify that a team member can navigate to a project dashboard
    ...                and see project-level metrics and workloads.
    [Tags]    ui    airm    rbac    access-control    projects

    Given a team member with project access is logged in
    And an accessible project exists
    When the user views a project dashboard
    Then project metrics should be visible

Team member sees restricted project settings
    [Documentation]    Verify that admin-only settings (like project deletion) are
    ...                hidden or read-only for team member users.
    [Tags]    ui    airm    rbac    access-control    projects    settings

    Given a team member with project access is logged in
    And an accessible project exists
    When the user views a project dashboard
    And the user views project settings
    Then admin-only settings should be hidden

Team member can view the projects page
    [Documentation]    Verify that a team member can access the projects page
    ...                and see their assigned projects listed.
    [Tags]    ui    airm    rbac    access-control    projects

    Given a team member with project access is logged in
    When the user views the projects page
    Then at least one project should be visible
