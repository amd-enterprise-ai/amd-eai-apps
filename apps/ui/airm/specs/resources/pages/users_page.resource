# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for AIRM UI users page.
...                 Provides selectors and atomic browser interactions for active users list,
...                 invited users tab, invite user drawer, user detail page, role management,
...                 project assignment, search, and confirmation dialogs.
...                 Business logic and assertions belong in feature resources.


*** Variables ***
${USERS_PATH}                   /users
${USERS_TABLE_SELECTOR}         css=[role="grid"]
${SEARCH_INPUT_SELECTOR}        css=input[placeholder="Search"]
${TOAST_SUCCESS_SELECTOR}       css=.toast--success
${TOAST_ERROR_SELECTOR}         css=.toast--danger


*** Keywords ***
# =============================================================================
# Navigation
# =============================================================================

Navigate to users page
    [Documentation]    Navigates to the users page and waits for the table to load.
    [Arguments]    ${base_url}

    Go To    ${base_url}${USERS_PATH}
    Wait For Elements State    css=main    visible    timeout=15s

Users page should be loaded
    [Documentation]    Waits for the users table grid to be visible.

    Wait For Elements State    ${USERS_TABLE_SELECTOR}    visible    timeout=15s

Navigate to user detail page
    [Documentation]    Navigates to a specific user's detail page.
    [Arguments]    ${base_url}    ${user_id}

    Go To    ${base_url}${USERS_PATH}/${user_id}
    Wait For Elements State    css=main    visible    timeout=15s

# =============================================================================
# Tabs
# =============================================================================

Click invited users tab
    [Documentation]    Clicks the "Invited Users" tab.

    VAR    ${tab}    css=[role="tab"]:has-text("Invited Users")
    Wait For Elements State    ${tab}    visible    timeout=10s
    Click    ${tab}

# =============================================================================
# Active users table
# =============================================================================

Get active user row names
    [Documentation]    Returns a list of user names (Name column) from visible table rows.

    ${names}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        return Array.from(document.querySelectorAll('[role="rowheader"]'))
    ...            .map(el => el.textContent.trim())
    ...            .filter(name => name);
    ...    }
    RETURN    ${names}

Get active user row emails
    [Documentation]    Returns the email text for all visible user rows.

    ${emails}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        return Array.from(document.querySelectorAll('[role="row"]'))
    ...            .slice(1)
    ...            .map(row => {
    ...                const cells = row.querySelectorAll('[role="gridcell"]');
    ...                return cells[0] ? cells[0].textContent.trim() : '';
    ...            })
    ...            .filter(email => email);
    ...    }
    RETURN    ${emails}

# =============================================================================
# Search
# =============================================================================

Type in search field
    [Documentation]    Types a search query into the users search input.
    [Arguments]    ${query}

    Wait For Elements State    ${SEARCH_INPUT_SELECTOR}    visible    timeout=10s
    Fill Text    ${SEARCH_INPUT_SELECTOR}    ${query}

# =============================================================================
# Invite user drawer
# =============================================================================

Click invite user button
    [Documentation]    Clicks the "Invite user" button to open the invite drawer.

    VAR    ${btn}    css=button:has-text("Invite user")
    Wait For Elements State    ${btn}    visible    timeout=10s
    Click    ${btn}

Invite user button should be visible
    [Documentation]    Verifies the Invite user button is visible.

    VAR    ${btn}    css=button:has-text("Invite user")
    Wait For Elements State    ${btn}    visible    timeout=10s

Invite drawer should be visible
    [Documentation]    Waits for the invite user drawer/dialog to be visible.

    VAR    ${drawer}    css=[role="dialog"]
    Wait For Elements State    ${drawer}    visible    timeout=10s

Fill invite email
    [Documentation]    Fills the email field in the invite user form.
    [Arguments]    ${email}

    VAR    ${input}    css=[role="dialog"] input[name="email"]
    Wait For Elements State    ${input}    visible    timeout=5s
    Fill Text    ${input}    ${email}

Fill invite temporary password
    [Documentation]    Fills the temporary password field in the invite form.
    [Arguments]    ${password}

    VAR    ${input}    css=[role="dialog"] input[name="tempPassword"]
    Wait For Elements State    ${input}    visible    timeout=5s
    Fill Text    ${input}    ${password}

Click invite submit button
    [Documentation]    Clicks the "Send invite" submit button in the invite drawer.

    VAR    ${btn}    css=[role="dialog"] button[type="submit"]:has-text("Send invite")
    Wait For Elements State    ${btn}    visible    timeout=5s
    Click    ${btn}

Click invite form role selector trigger
    [Documentation]    Opens the role dropdown in the invite user drawer (first select trigger).

    VAR    ${trigger}    css=[role="dialog"] [data-slot="trigger"] >> nth=0
    Wait For Elements State    ${trigger}    visible    timeout=10s
    Click    ${trigger}

Click invite form project selector trigger
    [Documentation]    Opens the project dropdown in the invite user drawer (second select trigger).

    VAR    ${trigger}    css=[role="dialog"] [data-slot="trigger"] >> nth=1
    Wait For Elements State    ${trigger}    visible    timeout=10s
    Click    ${trigger}

Invite overlay option with text is clicked
    [Documentation]    Clicks a listbox option in an open overlay by visible label text.
    [Arguments]    ${text}

    VAR    ${option}    css=[role="option"]:has-text("${text}")
    Wait For Elements State    ${option}    visible    timeout=10s
    Click    ${option}

# =============================================================================
# Invited users table
# =============================================================================

Invited user row should exist
    [Documentation]    Asserts that a row with the given email exists in the invited users table.
    [Arguments]    ${email}

    VAR    ${row_selector}    css=[role="row"]:has([role="rowheader"]:has-text("${email}"))
    Wait For Elements State    ${row_selector}    visible    timeout=30s

Invited user row should not exist
    [Documentation]    Asserts that no row with the given email exists in the invited users table.
    [Arguments]    ${email}

    VAR    ${row_selector}    css=[role="row"]:has([role="rowheader"]:has-text("${email}"))
    Wait For Elements State    ${row_selector}    detached    timeout=30s

Open invited user actions menu
    [Documentation]    Opens the actions dropdown for a specific invited user row.
    [Arguments]    ${email}

    VAR    ${actions_btn}    css=[role="row"]:has([role="rowheader"]:has-text("${email}")) button[aria-label]
    Wait For Elements State    ${actions_btn}    visible    timeout=10s
    Click    ${actions_btn}

Click cancel invitation action
    [Documentation]    Clicks "Cancel" in the invited user actions menu.

    VAR    ${cancel_item}    css=[role="menuitem"]:has-text("Cancel")
    Wait For Elements State    ${cancel_item}    visible    timeout=5s
    Click    ${cancel_item}

Click resend invitation action
    [Documentation]    Clicks "Resend" in the invited user actions menu.

    VAR    ${resend_item}    css=[role="menuitem"]:has-text("Resend")
    Wait For Elements State    ${resend_item}    visible    timeout=5s
    Click    ${resend_item}

# =============================================================================
# Confirmation modals
# =============================================================================

Confirmation dialog should be visible
    [Documentation]    Waits for any confirmation dialog to be visible.

    VAR    ${dialog}    css=[role="dialog"]
    Wait For Elements State    ${dialog}    visible    timeout=10s

Click confirmation confirm button
    [Documentation]    Clicks the confirm/action button in the confirmation dialog.
    ...                Finds the primary or danger-styled button, skipping cancel/close.

    ${confirm_btn}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        const dialog = document.querySelector('[role="dialog"]');
    ...        if (!dialog) return null;
    ...        const buttons = dialog.querySelectorAll('button');
    ...        for (const btn of buttons) {
    ...            const text = btn.textContent.trim().toLowerCase();
    ...            if (text === 'cancel' || text === 'close') continue;
    ...            if (btn.className.includes('danger') || btn.className.includes('primary')) {
    ...                btn.click();
    ...                return 'clicked';
    ...            }
    ...        }
    ...        return null;
    ...    }
    IF    "${confirm_btn}" == "None"
        Evaluate JavaScript    ${None}
        ...    (elem) => {
        ...        const dialog = document.querySelector('[role="dialog"]');
        ...        if (!dialog) return;
        ...        const buttons = Array.from(dialog.querySelectorAll('button'));
        ...        const actionBtn = buttons.find(b => !['cancel', 'close'].includes(b.textContent.trim().toLowerCase()));
        ...        if (actionBtn) actionBtn.click();
        ...    }
    END

# =============================================================================
# User detail page
# =============================================================================

User detail page should be loaded
    [Documentation]    Waits for the user detail page to be fully loaded.
    ...                Checks for the firstName input field as the form indicator.

    VAR    ${input}    css=input[name="firstName"]
    Wait For Elements State    ${input}    visible    timeout=30s

Get user detail first name
    [Documentation]    Returns the current value of the first name input field.

    VAR    ${input}    css=input[name="firstName"]
    ${value}=    Get Property    ${input}    value
    RETURN    ${value}

Get user detail last name
    [Documentation]    Returns the current value of the last name input field.

    VAR    ${input}    css=input[name="lastName"]
    ${value}=    Get Property    ${input}    value
    RETURN    ${value}

Fill user detail first name
    [Documentation]    Clears and fills the first name field.
    [Arguments]    ${first_name}

    VAR    ${input}    css=input[name="firstName"]
    Wait For Elements State    ${input}    visible    timeout=5s
    Fill Text    ${input}    ${first_name}

Fill user detail last name
    [Documentation]    Clears and fills the last name field.
    [Arguments]    ${last_name}

    VAR    ${input}    css=input[name="lastName"]
    Wait For Elements State    ${input}    visible    timeout=5s
    Fill Text    ${input}    ${last_name}

Click user detail save button
    [Documentation]    Clicks the save/submit button on the user detail form.

    VAR    ${btn}    css=form button[type="submit"]
    Wait For Elements State    ${btn}    visible    timeout=5s
    Click    ${btn}

# =============================================================================
# User roles section (user detail page)
# =============================================================================

Get displayed user role
    [Documentation]    Returns the currently displayed role text on the user detail page.
    ...                The h3 heading says "Role" (CSS makes it visually uppercase).

    VAR    ${role_heading}    css=h3:has-text("Role")
    Wait For Elements State    ${role_heading}    visible    timeout=10s

    ${role_text}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        const headings = document.querySelectorAll("h3");
    ...        let heading = null;
    ...        for (const h of headings) {
    ...            if (h.textContent.trim() === "Role") { heading = h; break; }
    ...        }
    ...        if (!heading) return "";
    ...        const container = heading.parentElement;
    ...        if (!container) return "";
    ...        const parent = container.parentElement || container;
    ...        const mt4 = parent.querySelector(".mt-4");
    ...        if (!mt4) return "";
    ...        const lines = mt4.innerText.split("\\n");
    ...        return lines[0] ? lines[0].trim() : "";
    ...    }
    RETURN    ${role_text}

Click edit role button
    [Documentation]    Clicks the "Edit role" button in the roles section.

    VAR    ${btn}    css=button:has-text("Edit role")
    Wait For Elements State    ${btn}    visible    timeout=10s
    Click    ${btn}

Role drawer should be visible
    [Documentation]    Waits for the role edit drawer to be visible.

    VAR    ${drawer}    css=[role="dialog"]
    Wait For Elements State    ${drawer}    visible    timeout=10s

Select role in drawer
    [Documentation]    Selects a role in the role edit drawer.
    [Arguments]    ${role_text}

    VAR    ${trigger}    css=[role="dialog"] [data-slot="trigger"]
    Wait For Elements State    ${trigger}    visible    timeout=5s
    Click    ${trigger}

    VAR    ${option}    css=[role="option"]:has-text("${role_text}")
    Wait For Elements State    ${option}    visible    timeout=5s
    Click    ${option}

Click role save button
    [Documentation]    Clicks the save/confirm button in the role edit drawer.

    VAR    ${btn}    css=[role="dialog"] button[type="submit"]
    Wait For Elements State    ${btn}    visible    timeout=5s
    Click    ${btn}

# =============================================================================
# User projects section (user detail page)
# =============================================================================

Get user projects list
    [Documentation]    Returns a list of project names displayed in the user's project section.

    ${projects}=    Evaluate JavaScript    ${None}
    ...    (elem) => {
    ...        const headings = document.querySelectorAll("h3");
    ...        let heading = null;
    ...        for (const h of headings) {
    ...            if (h.textContent.trim() === "Projects") { heading = h; break; }
    ...        }
    ...        if (!heading) return [];
    ...        const container = heading.parentElement;
    ...        if (!container) return [];
    ...        const parent = container.parentElement || container;
    ...        const mt4 = parent.querySelector(".mt-4");
    ...        if (!mt4) return [];
    ...        const textContent = mt4.innerText.trim();
    ...        if (!textContent) return [];
    ...        return textContent.split("\\n").filter(t => t.trim()).map(t => t.trim());
    ...    }
    RETURN    ${projects}

Click add project button
    [Documentation]    Clicks the "Add to project" button in the user's projects section.

    VAR    ${btn}    css=button:has-text("Add to project")
    Wait For Elements State    ${btn}    visible    timeout=10s
    Click    ${btn}

Project drawer should be visible
    [Documentation]    Waits for the add project drawer to be visible.

    VAR    ${drawer}    css=[role="dialog"]
    Wait For Elements State    ${drawer}    visible    timeout=10s

Click project save button
    [Documentation]    Clicks the save/confirm button in the add project drawer.

    VAR    ${btn}    css=[role="dialog"] button[type="submit"]
    Wait For Elements State    ${btn}    visible    timeout=5s
    Click    ${btn}

# =============================================================================
# Toast notifications
# =============================================================================

Wait for success toast
    [Documentation]    Waits for a success toast to appear.
    ...                The toast auto-closes after 5 seconds.

    Wait For Elements State    ${TOAST_SUCCESS_SELECTOR}    visible    timeout=10s

Wait for success toast to disappear
    [Documentation]    Waits for the success toast to disappear after appearing.

    Wait For Elements State    ${TOAST_SUCCESS_SELECTOR}    detached    timeout=10s
