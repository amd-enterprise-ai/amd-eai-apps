# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Feature-layer keywords for AIRM UI RBAC testing.
...                 Composes page-layer interactions into business-meaningful keywords
...                 that describe role-based access control behavior.
Library             ../libraries/UICredentials.py
Resource            common/session.resource
Resource            common/navigation.resource
Resource            pages/sidebar_page.resource
Resource            pages/projects_page.resource


*** Keywords ***
Require the team member account
    [Documentation]    Fails the suite, naming the missing prerequisite, when the
    ...    team-member account does not exist in the target environment's Keycloak.
    ...
    ...    Every test below logs in as that account, so its absence is a setup failure
    ...    rather than a result. Reporting it as a skip is what let a whole RBAC surface
    ...    disappear into a total that read green: a skipped test is never a pass.
    ...
    ...    A run that cannot carry a second password at all -- user passthrough with no
    ...    explicit override -- is a different thing and still skips: no account is
    ...    missing there, the run simply cannot log in as one.
    ${applicable}=    Team Member Is Applicable
    IF    not ${applicable}
        ${reason}=    Team Member Not Applicable Reason
        Skip    ${reason}
    END
    ${provisioned}=    Team Member Is Provisioned
    IF    not ${provisioned}
        ${reason}=    Team Member Unavailable Reason
        Fail    ${reason}
    END

A team member user is logged in
    [Documentation]    Logs in as a team member (non-admin) user.
    Team member user is logged in

A team member with project access is logged in
    [Documentation]    Logs in as a team member who has access to at least one project.
    ...                On the dev cluster, the team member user is assigned to projects.
    Team member user is logged in

An accessible project exists
    [Documentation]    Finds an accessible project for the team member from the projects list.
    ...                Navigates to the projects page, collects project IDs, then tries each
    ...                until finding one the team member can access. Stores the project ID
    ...                as a test variable for subsequent navigation keywords.
    Navigate to page    ${UI_BASE_URL}    /projects
    Wait for projects page to load

    ${project_ids}=    Get project IDs from list

    VAR    ${found}    ${FALSE}

    FOR    ${project_id}    IN    @{project_ids}
        IF    ${found}
            BREAK
        END
        Navigate to page    ${UI_BASE_URL}    /projects/${project_id}

        ${current_url}=    Get Url
        ${on_dashboard}=    Evaluate    "/projects/${project_id}" in "${current_url}"
        IF    ${on_dashboard}
            VAR    ${found}    ${TRUE}
            VAR    ${TEST_PROJECT_ID}    ${project_id}    scope=TEST
            Log    Found accessible project: ${project_id}    INFO
        ELSE
            Log    Project ${project_id} not accessible, trying next    INFO
        END
    END

    IF    not ${found}
        Fail    Team member could not access any project dashboard. Ensure the team member user is assigned to at least one project.
    END

The sidebar navigation is rendered
    [Documentation]    Waits for the sidebar to be rendered after login.
    ...                The sidebar renders automatically, but this keyword ensures
    ...                it is fully loaded before assertions run.
    Wait for sidebar to load

The user navigates to the admin dashboard directly
    [Documentation]    Navigates directly to the root URL which is the admin dashboard.
    Navigate to page    ${UI_BASE_URL}    /

The user navigates to the users page directly
    [Documentation]    Navigates directly to the admin-only users page URL.
    Navigate to page    ${UI_BASE_URL}    /users

The user views the projects page
    [Documentation]    Navigates to the projects list page.
    Navigate to page    ${UI_BASE_URL}    /projects

The user views a project dashboard
    [Documentation]    Navigates to the dashboard of the previously identified accessible project.
    ...                Requires 'An accessible project exists' to have been called first.
    Navigate to page    ${UI_BASE_URL}    /projects/${TEST_PROJECT_ID}

The user views project settings
    [Documentation]    Navigates to project settings via the Actions dropdown on the project dashboard.

    Open project actions menu
    Click edit settings menu item

Admin-only navigation items should be hidden
    [Documentation]    Verifies that sidebar items restricted to PLATFORM_ADMIN are not shown.
    ...                Admin-only items: Dashboard, Secrets, Storage, Users.

    ${items}=    Get visible sidebar items
    Log    Visible sidebar items: ${items}    INFO

    Should Not Contain    ${items}    Dashboard
    Should Not Contain    ${items}    Secrets
    Should Not Contain    ${items}    Storage
    Should Not Contain    ${items}    Users

Team member navigation items should be visible
    [Documentation]    Verifies that sidebar items accessible to all roles are shown.
    ...                All-user items: Clusters, Projects.

    ${items}=    Get visible sidebar items
    Should Contain    ${items}    Clusters
    Should Contain    ${items}    Projects

The page should not be accessible
    [Documentation]    Verifies that the current page is not the admin-only page.
    ...                Non-admin access results in a redirect to the first accessible route
    ...                (typically /projects) rather than showing an error page.

    ${current_url}=    Get Url
    ${stripped_url}=    Evaluate    "${current_url}".rstrip("/")
    ${stripped_base}=    Evaluate    "${UI_BASE_URL}".rstrip("/")

    # The dashboard page (/) redirects non-admins to /projects or /clusters
    # Admin-only pages like /secrets, /storages, /users should also redirect
    ${ends_with_admin}=    Evaluate    "${stripped_url}".endswith(("/secrets", "/storages", "/users"))
    ${is_root}=    Evaluate    "${stripped_url}" == "${stripped_base}"
    ${is_admin_page}=    Evaluate    ${ends_with_admin} or ${is_root}

    IF    ${is_admin_page}
        Fail    User was not redirected from admin-only page. Current URL: ${current_url}
    END

    Log    Non-admin user was correctly redirected. Current URL: ${current_url}    INFO

Project metrics should be visible
    [Documentation]    Verifies that project-level dashboard metrics and workloads are visible.

    Wait for project dashboard content

Admin-only settings should be hidden
    [Documentation]    Verifies that admin-only settings (like Delete Project) are not shown
    ...                to team member users on the project settings page.

    VAR    ${delete_section}    css=#delete-project
    Wait For Elements State    ${delete_section}    detached    timeout=5s

At least one project should be visible
    [Documentation]    Verifies the projects page loads and shows at least one project
    ...                the team member has access to.

    Wait for projects page to load
    Wait for project rows
