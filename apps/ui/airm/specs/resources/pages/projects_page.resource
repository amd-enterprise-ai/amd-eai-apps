# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for AIRM UI projects page.
...                 Provides selectors and atomic interactions for project list, dashboard,
...                 creation drawer, edit tabs, and deletion flow.


*** Keywords ***
# =============================================================================
# Projects list page
# =============================================================================

Projects page should be loaded
    [Documentation]    Waits for the projects list page to be fully loaded.

    Wait For Elements State    css=main    visible    timeout=10s

At least one project row should be visible
    [Documentation]    Asserts at least one project data row is visible in the list.

    VAR    ${project_row}    css=[role="row"][data-key] >> nth=0
    Wait For Elements State    ${project_row}    visible    timeout=15s

Get project IDs from list
    [Documentation]    Returns a list of project IDs from the visible data rows on the projects page.

    ${project_ids}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        return Array.from(document.querySelectorAll('[role="row"][data-key]'))
    ...            .map(el => el.getAttribute('data-key'))
    ...            .filter(key => key);
    ...    }
    RETURN    ${project_ids}

Filter projects by search text
    [Documentation]    Types text into the search filter on the projects page.
    ...                This filters the project list across all pages.
    [Arguments]    ${search_text}

    VAR    ${search_input}    css=input[placeholder="Search"]
    Wait For Elements State    ${search_input}    visible    timeout=10s
    Fill Text    ${search_input}    ${search_text}
    # Wait for the filtered results to render
    VAR    ${row}    css=[role="row"]:has-text("${search_text}")
    Wait For Elements State    ${row}    visible    timeout=10s

Click create project button
    [Documentation]    Clicks the "Create project" button on the projects list page.

    VAR    ${create_btn}    css=button:has-text("Create project")
    Wait For Elements State    ${create_btn}    visible    timeout=10s
    Click    ${create_btn}

Get project row text by name
    [Documentation]    Returns the text content of a project row matching the given name.
    [Arguments]    ${project_name}

    VAR    ${row_selector}    css=[role="row"]:has-text("${project_name}")
    Wait For Elements State    ${row_selector}    visible    timeout=15s
    ${text}=    Get Text    ${row_selector}
    RETURN    ${text}

Get project ID by name
    [Documentation]    Returns the data-key (project ID) of the row matching the given project name.
    [Arguments]    ${project_name}

    ${project_id}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        const rows = document.querySelectorAll('[role="row"][data-key]');
    ...        for (const row of rows) {
    ...            const header = row.querySelector('[role="rowheader"]');
    ...            if (header && header.textContent.trim() === '${project_name}') {
    ...                return row.getAttribute('data-key');
    ...            }
    ...        }
    ...        return null;
    ...    }
    IF    "${project_id}" == "None"
        Fail    Project '${project_name}' not found in the project list
    END
    RETURN    ${project_id}

Get project name by ID
    [Documentation]    Returns the project name from the row matching the given data-key (project ID).
    [Arguments]    ${project_id}

    ${project_name}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        const row = document.querySelector('[role="row"][data-key="${project_id}"]');
    ...        if (!row) return null;
    ...        const header = row.querySelector('[role="rowheader"]');
    ...        return header ? header.textContent.trim() : null;
    ...    }
    IF    "${project_name}" == "None"
        Fail    Project with ID '${project_id}' not found in the project list
    END
    RETURN    ${project_name}

# =============================================================================
# Create project drawer
# =============================================================================

Create project drawer should be open
    [Documentation]    Waits for the create project drawer dialog to be visible.
    ...                The drawer renders as a dialog element with role="dialog".

    VAR    ${drawer}    css=[role="dialog"]:has-text("Create project")
    Wait For Elements State    ${drawer}    visible    timeout=10s

Fill project name field
    [Documentation]    Fills the project name field in the create project drawer.
    [Arguments]    ${name}

    VAR    ${name_input}    css=[role="dialog"] input[name="name"]
    Wait For Elements State    ${name_input}    visible    timeout=5s
    Fill Text    ${name_input}    ${name}

Fill project description field
    [Documentation]    Fills the project description field in the create project drawer.
    [Arguments]    ${description}

    VAR    ${desc_input}    css=[role="dialog"] input[name="description"]
    Wait For Elements State    ${desc_input}    visible    timeout=5s
    Fill Text    ${desc_input}    ${description}

Select cluster in create form
    [Documentation]    Selects the first available cluster in the create project drawer.
    ...                Clicks the cluster dropdown trigger inside the dialog, then selects
    ...                the first non-disabled option from the listbox.

    # The cluster trigger is a button inside the dialog containing "Select an available cluster"
    VAR    ${cluster_trigger}    css=[role="dialog"] button:has-text("Select an available cluster")
    Wait For Elements State    ${cluster_trigger}    visible    timeout=5s
    Click    ${cluster_trigger}
    # Wait for listbox options to appear and click the first available option
    VAR    ${option}    css=[role="listbox"] [role="option"]:not([aria-disabled="true"]) >> nth=0
    Wait For Elements State    ${option}    visible    timeout=5s
    Click    ${option}

Toggle preemption switch
    [Documentation]    Toggles the GPU preemption switch in the create project drawer.
    ...                The switch renders with role="switch" in a clickable container.

    VAR    ${switch_container}    css=[role="dialog"] [role="switch"]
    Wait For Elements State    ${switch_container}    visible    timeout=5s
    Click    ${switch_container}

Click create project submit button
    [Documentation]    Clicks the submit button in the create project drawer.
    ...                Uses the last matching button in the dialog to target the footer action.

    VAR    ${submit_btn}    css=[role="dialog"] button:has-text("Create project") >> nth=-1
    Click    ${submit_btn}

# =============================================================================
# Project dashboard
# =============================================================================

Project dashboard metrics should be visible
    [Documentation]    Asserts that project dashboard content is visible.
    ...                The project dashboard shows an Overview heading with workload stats,
    ...                GPU usage metrics, and a workloads table.

    Wait For Elements State    css=main    visible    timeout=10s
    VAR    ${overview_heading}    css=h3:has-text("Overview")
    Wait For Elements State    ${overview_heading}    visible    timeout=15s

Project workloads section should be visible
    [Documentation]    Asserts the Workloads section heading is visible on the project dashboard.

    VAR    ${workloads_heading}    css=h3:has-text("Workloads")
    Wait For Elements State    ${workloads_heading}    visible    timeout=15s

Open project actions menu
    [Documentation]    Opens the Actions dropdown menu on the project dashboard.

    VAR    ${actions_btn}    css=button:has-text("Actions")
    Wait For Elements State    ${actions_btn}    visible    timeout=10s
    Click    ${actions_btn}

Click edit settings menu item
    [Documentation]    Clicks "Edit settings" in the project actions dropdown menu.

    VAR    ${edit_settings}    css=[role="menuitem"]:has-text("Edit settings")
    Wait For Elements State    ${edit_settings}    visible    timeout=5s
    Click    ${edit_settings}
    Wait For Elements State    css=main    visible    timeout=15s

Click delete menu item
    [Documentation]    Clicks "Delete" in the project actions dropdown menu.

    VAR    ${delete_item}    css=[role="menuitem"]:has-text("Delete")
    Wait For Elements State    ${delete_item}    visible    timeout=5s
    Click    ${delete_item}

Confirm deletion in modal
    [Documentation]    Clicks the confirm button in the deletion confirmation modal.

    VAR    ${confirm_btn}    css=button:has-text("Confirm")
    Wait For Elements State    ${confirm_btn}    visible    timeout=10s
    Click    ${confirm_btn}

# =============================================================================
# Project edit page - tabs
# =============================================================================

Project settings page should be loaded
    [Documentation]    Waits for the project settings/edit page to be loaded.

    VAR    ${settings_heading}    css=h2:has-text("Project settings")
    Wait For Elements State    ${settings_heading}    visible    timeout=15s

Click quota tab
    [Documentation]    Clicks the Quota tab on the project edit page.

    VAR    ${quota_tab}    css=[role="tab"]:has-text("Quota")
    Wait For Elements State    ${quota_tab}    visible    timeout=10s
    Click    ${quota_tab}

Click secrets tab
    [Documentation]    Clicks the Secrets tab on the project edit page.

    VAR    ${secrets_tab}    css=[role="tab"]:has-text("Secrets")
    Wait For Elements State    ${secrets_tab}    visible    timeout=10s
    Click    ${secrets_tab}

Click storages tab
    [Documentation]    Clicks the Storage tab on the project edit page.

    VAR    ${storages_tab}    css=[role="tab"]:has-text("Storage")
    Wait For Elements State    ${storages_tab}    visible    timeout=10s
    Click    ${storages_tab}

Click users tab
    [Documentation]    Clicks the Users tab on the project edit page.

    VAR    ${users_tab}    css=[role="tab"]:has-text("Users")
    Wait For Elements State    ${users_tab}    visible    timeout=10s
    Click    ${users_tab}

Click details tab
    [Documentation]    Clicks the Details tab on the project edit page.

    VAR    ${details_tab}    css=[role="tab"]:has-text("Details")
    Wait For Elements State    ${details_tab}    visible    timeout=10s
    Click    ${details_tab}

# =============================================================================
# Quota tab
# =============================================================================

Quota table should be visible
    [Documentation]    Asserts the quota allocation table is visible.
    ...                The table contains resource allocation rows for GPU, CPU, RAM, Disk.

    VAR    ${quota_section}    css=#guaranteed-quota
    Wait For Elements State    ${quota_section}    visible    timeout=10s

Quota table should contain resource types
    [Documentation]    Asserts that the quota table contains all four resource type rows.

    VAR    ${gpu_row}    css=#guaranteed-quota [role="row"]:has-text("GPUs")
    VAR    ${cpu_row}    css=#guaranteed-quota [role="row"]:has-text("CPU Cores")
    VAR    ${ram_row}    css=#guaranteed-quota [role="row"]:has-text("System Memory")
    VAR    ${disk_row}    css=#guaranteed-quota [role="row"]:has-text("Ephemeral Disk")
    Wait For Elements State    ${gpu_row}    visible    timeout=10s
    Wait For Elements State    ${cpu_row}    visible    timeout=5s
    Wait For Elements State    ${ram_row}    visible    timeout=5s
    Wait For Elements State    ${disk_row}    visible    timeout=5s

Save changes button should be visible
    [Documentation]    Asserts the "Save changes" button is visible on the form.

    VAR    ${save_btn}    css=button:has-text("Save changes")
    Wait For Elements State    ${save_btn}    visible    timeout=10s

Discard changes button should be visible
    [Documentation]    Asserts the "Discard changes" button is visible on the form.

    VAR    ${discard_btn}    css=button:has-text("Discard changes")
    Wait For Elements State    ${discard_btn}    visible    timeout=10s

Note current CPU guaranteed allocation on quota tab
    [Documentation]    Stores the numeric value shown for CPU guaranteed allocation
    ...                in a test-scoped variable for later comparison after discard.
    VAR    ${cpu_input}    css=#guaranteed-quota [role="row"]:has-text("CPU Cores") [role="textbox"]
    Wait For Elements State    ${cpu_input}    visible    timeout=10s
    ${val}=    Get Attribute    ${cpu_input}    value
    VAR    ${NOTED_CPU_QUOTA}    ${val}    scope=TEST

Increase CPU guaranteed allocation once without saving
    [Documentation]    Clicks the increment control once for the CPU allocation row.
    VAR    ${inc_btn}    css=#guaranteed-quota [role="row"]:has-text("CPU Cores") button[aria-label="Increase"]
    Wait For Elements State    ${inc_btn}    visible    timeout=10s
    Wait For Elements State    ${inc_btn}    enabled    timeout=10s
    Click    ${inc_btn}

Click discard changes on project settings
    [Documentation]    Clicks the Discard changes button for the project settings form.
    VAR    ${discard_btn}    css=button:has-text("Discard changes")
    Wait For Elements State    ${discard_btn}    visible    timeout=10s
    Click    ${discard_btn}

CPU guaranteed allocation should match noted value
    [Documentation]    Asserts the CPU allocation input matches the value stored earlier.
    VAR    ${cpu_input}    css=#guaranteed-quota [role="row"]:has-text("CPU Cores") [role="textbox"]
    Wait For Elements State    ${cpu_input}    visible    timeout=10s
    ${current}=    Get Attribute    ${cpu_input}    value
    Should Be Equal    ${current}    ${NOTED_CPU_QUOTA}

# =============================================================================
# Members/Users tab
# =============================================================================

Members section should be visible
    [Documentation]    Asserts the Members section is visible on the Users tab.

    VAR    ${members_heading}    css=h3:has-text("Members")
    Wait For Elements State    ${members_heading}    visible    timeout=10s

Click add member button
    [Documentation]    Clicks the "Add Member" button on the Users tab.
    ...                Waits for the button to be enabled -- it may be disabled while
    ...                the members list is loading or the project is not yet ready.

    VAR    ${add_member_btn}    css=button:has-text("Add Member")
    Wait For Elements State    ${add_member_btn}    enabled    timeout=30s
    Click    ${add_member_btn}

Add member drawer should be open
    [Documentation]    Waits for the Add Member drawer dialog to appear.

    VAR    ${drawer}    css=[role="dialog"]:has-text("Add User")
    Wait For Elements State    ${drawer}    visible    timeout=10s

Select first available member
    [Documentation]    Selects the first available user in the add member drawer by clicking
    ...                the user row. Returns the display name of the selected user.
    ...                The drawer shows names as "LastName, FirstName" format.

    # Get the display name of the user being added before clicking
    ${user_name}=    Get first available member name

    # Click the first user row in the scrollable list to toggle its checkbox.
    # Each user row is a div with cursor-pointer class inside the .max-h-64 container.
    VAR    ${first_user_row}    css=[role="dialog"] .max-h-64 > div.cursor-pointer >> nth=0
    Wait For Elements State    ${first_user_row}    visible    timeout=10s
    Click    ${first_user_row}

    RETURN    ${user_name}

Get first available member name
    [Documentation]    Returns the display name of the first available member in the add drawer.
    ...                The name is in a .font-medium div within the first user row of the
    ...                scrollable .max-h-64 container.

    ${name}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        const dialog = document.querySelector('[role="dialog"]');
    ...        if (!dialog) return null;
    ...        const userList = dialog.querySelector('.max-h-64');
    ...        if (!userList) return null;
    ...        const firstRow = userList.querySelector(':scope > div');
    ...        if (!firstRow) return null;
    ...        const nameEl = firstRow.querySelector('.font-medium');
    ...        return nameEl ? nameEl.textContent.trim() : null;
    ...    }
    IF    "${name}" == "None"
        Fail    No available members found in the add member drawer
    END
    RETURN    ${name}

Click add to project button
    [Documentation]    Clicks the "Add to project" submit button in the add member drawer.

    VAR    ${add_btn}    css=[role="dialog"] button:has-text("Add to project")
    Wait For Elements State    ${add_btn}    enabled    timeout=10s
    Click    ${add_btn}
    # Wait for the drawer to close
    Wait For Elements State    ${add_btn}    detached    timeout=15s

Member should be in members table
    [Documentation]    Asserts that a user with the given name appears in the members table.
    [Arguments]    ${member_name}

    VAR    ${member_row}    css=[role="grid"] [role="row"]:has-text("${member_name}")
    Wait For Elements State    ${member_row}    visible    timeout=10s

# =============================================================================
# Secrets tab
# =============================================================================

Secrets section should be visible
    [Documentation]    Asserts that the secrets section content is visible.

    Wait For Elements State    css=[role="tabpanel"]    visible    timeout=10s

# =============================================================================
# Storages tab
# =============================================================================

Storages section should be visible
    [Documentation]    Asserts that the storages section content is visible.

    Wait For Elements State    css=[role="tabpanel"]    visible    timeout=10s

# =============================================================================
# Details tab
# =============================================================================

Delete project section should not be visible
    [Documentation]    Asserts the delete project section is NOT present on the settings page.

    VAR    ${delete_section}    css=#delete-project
    Wait For Elements State    ${delete_section}    detached    timeout=5s

# =============================================================================
# Preemption settings (read-only view on details tab)
# =============================================================================

Get preemption status text
    [Documentation]    Returns the text content of the details tab panel.
    ...                Used to verify preemption configuration by checking for policy fields.

    ${text}=    Get Text    css=[role="tabpanel"]
    RETURN    ${text}

Wait for preemption fields to render
    [Documentation]    Waits for preemption form fields to appear in the create project drawer.

    VAR    ${selector}    css=[role="dialog"] select[name="gpuPreemptionPolicy"]
    Wait For Elements State    ${selector}    visible    timeout=5s

Wait for project dashboard to load
    [Documentation]    Waits for the project dashboard Overview heading to be visible.

    VAR    ${overview}    css=h3:has-text("Overview")
    Wait For Elements State    ${overview}    visible    timeout=30s

Wait for redirect to projects page
    [Documentation]    Waits for the main content area to be visible after a redirect.

    Wait For Elements State    css=main    visible    timeout=15s

Get current page URL
    [Documentation]    Returns the current browser URL.

    ${url}=    Get Url
    RETURN    ${url}

Project settings heading should be visible
    [Documentation]    Waits for the "Project settings" heading to be visible.
    [Arguments]    ${timeout}=30s

    VAR    ${heading}    css=h2:has-text("Project settings")
    Wait For Elements State    ${heading}    visible    timeout=${timeout}

Project name should not appear in search results
    [Documentation]    Types a project name into the search input and asserts no matching row appears.
    [Arguments]    ${project_name}

    VAR    ${search_input}    css=input[placeholder="Search"]
    Wait For Elements State    ${search_input}    visible    timeout=10s
    Fill Text    ${search_input}    ${project_name}
    VAR    ${row_selector}    css=[role="row"]:has-text("${project_name}")
    Wait For Elements State    ${row_selector}    detached    timeout=5s

# =============================================================================
# Backward-compatible aliases for keywords used by rbac.resource
# =============================================================================

Wait for projects page to load
    [Documentation]    Alias for Projects page should be loaded. Used by RBAC tests.
    Projects page should be loaded

Wait for project dashboard content
    [Documentation]    Alias for Project dashboard metrics should be visible. Used by RBAC tests.
    Project dashboard metrics should be visible

Wait for project rows
    [Documentation]    Alias for At least one project row should be visible. Used by RBAC tests.
    At least one project row should be visible
