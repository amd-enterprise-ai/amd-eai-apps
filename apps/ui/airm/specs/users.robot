# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for AIRM user management and invitations.
...
...                 These tests verify the user management lifecycle through the UI:
...                 listing active users, inviting new users, editing profiles,
...                 managing roles and project assignments, searching users,
...                 removing invited users, and managing invitations.
...                 Data preconditions are set up via API.

Resource            resources/common/browser_setup.resource
Resource            resources/users.resource

Suite Setup         Initialize user management test suite
Suite Teardown      Clean up test users
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
Admin views active platform users
    [Documentation]    Verify that an admin can view the users page with active users
    ...                listed with email and role information.
    [Tags]    ui    airm    users    list    smoke

    Given an admin user is on the users page
    Then active users are listed with email and role information

Admin invites a new user to the platform
    [Documentation]    Verify that an admin can invite a new user by filling in
    ...                the invite form with email and role.
    [Tags]    ui    airm    users    invite

    Given an admin user is on the users page
    And user invitations are enabled
    When the user invites a new user with email, role, and project assignment
    Then the invited user appears in the invited users list

Admin invites a team member and assigns a project from the invite flow
    [Documentation]    Verify that an admin can choose team member role and assign
    ...                a project when inviting; the invitation succeeds and appears in the list.
    [Tags]    ui    airm    users    invite

    Given a ready project with user access exists
    Given an admin user is on the users page
    And user invitations are enabled
    When the user invites a new team member and assigns the prepared project
    Then the invited user appears in the invited users list

Admin updates a user's profile information
    [Documentation]    Verify that an admin can update a user's first and last name
    ...                on the user detail page and the changes are persisted.
    [Tags]    ui    airm    users    edit    profile

    Given an admin user is viewing a user's detail page
    When the user updates the profile name and saves
    Then the updated name is reflected on the user detail page

Admin searches for a user by name
    [Documentation]    Verify that the search field filters the active users list
    ...                to show only matching users.
    [Tags]    ui    airm    users    search

    Given a known search query is set
    And an admin user is on the users page
    And multiple users exist
    When the user searches by name or email
    Then only matching users are shown

Admin changes a user's platform role
    [Documentation]    Verify that an admin can change a user's role from the user
    ...                detail page when role management is enabled.
    [Tags]    ui    airm    users    roles

    Given an admin user is viewing a user's detail page
    And role management is enabled
    When the admin changes the user's role
    Then the updated role is reflected on the user detail page

Admin adds a project to a user from user detail page
    [Documentation]    Verify that an admin can assign an additional project to a user
    ...                from the user detail page.
    [Tags]    ui    airm    users    projects

    Given an admin user is viewing a user's detail page
    And projects exist that the user is not a member of
    When the admin adds the user to a project
    Then the project appears in the user's project list

Admin removes an invited user from the platform
    [Documentation]    Verify that an admin can remove an invited user and the
    ...                invitation disappears from the invited users list.
    [Tags]    ui    airm    users    delete

    Given a non-admin user exists on the users page
    And an admin user is on the users page
    When the user removes the invited user and confirms
    Then the invited user is no longer listed

Admin cancels a pending invitation
    [Documentation]    Verify that an admin can cancel a pending invitation and the
    ...                invitation is removed from the invited users list.
    [Tags]    ui    airm    users    invite    cancel

    Given a pending invitation exists
    And an admin user is on the users page
    When the admin cancels the invitation
    Then the invitation is removed from the invited users list

Admin resends an invitation
    [Documentation]    Verify that an admin can resend a pending invitation
    ...                and the action is confirmed.
    [Tags]    ui    airm    users    invite    resend

    Given a pending invitation exists
    And an admin user is on the users page
    When the admin resends the invitation
    Then the invitation status is updated
