# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for the custom profiles scenarios, covering the list
...                 screen and the add/edit profile drawer.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)

Resource            common/session.resource
Resource            pages/models_page.resource
Resource            resources/aiwb_custom_models.resource


*** Keywords ***
# =============================================================================
# Given keywords (preconditions)
# =============================================================================

An onboarded custom model with a default profile exists
    [Documentation]    Previews and onboards the public test fixture, then waits for its
    ...                default profile to resolve. Onboarding only records the model; the
    ...                default profile's runtime parameters are filled in asynchronously,
    ...                so the list can otherwise render before there is anything to show.

    A custom model is onboarded in the project
    The onboarded model's Default profile is ready

The model has a saved profile named "${display_name}"
    [Documentation]    Saves an extra profile against the onboarded model so the list has
    ...                more than the default to show. Saved through the API because this
    ...                screen only lists profiles; authoring them is a separate flow.

    The user adds a profile named "${display_name}" to the onboarded custom model
    Custom model profile create response status should be "201"

The model has a saved profile named "${display_name}" that is ready to serve
    [Documentation]    Saves an extra profile and waits until it has reconciled, because a
    ...                profile that cannot yet serve a deployment is not offered for one.

    The model has a saved profile named "${display_name}"
    The profile the user added is ready to serve

User is on custom models tab
    [Documentation]    Navigates to the Custom Models tab for the selected project.

    Navigate to custom models page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

User is on the custom profiles list
    [Documentation]    Opens the profiles list for the onboarded model directly.

    Navigate to custom profiles page
    ...    ${UI_BASE_URL}    ${TEST_PROJECT}[name]    ${TEST_CUSTOM_MODEL_NAME}

A profile named "${name}" was added to the model
    [Documentation]    Adds a profile through the drawer so a scenario has a saved
    ...                profile to edit or to collide with.

    Navigate to custom profiles page
    ...    ${UI_BASE_URL}    ${TEST_PROJECT}[name]    ${TEST_CUSTOM_MODEL_NAME}
    Click new profile on custom profiles page
    Wait for custom profile drawer
    Fill custom profile name    ${name}
    Save custom profile drawer
    Wait for custom profiles table
    Wait for custom profile row showing "${name}"

User is adding a profile
    [Documentation]    Opens the add profile drawer from the list header.

    Click new profile on custom profiles page
    Wait for custom profile drawer

# =============================================================================
# When keywords (actions)
# =============================================================================

User opens the profiles view from the custom model card
    [Documentation]    Opens the card actions menu on the first visible model card
    ...                and selects "Profiles".

    Click actions menu on first custom model card
    Click profiles action in custom model card menu

User opens the row actions for the default profile
    [Documentation]    Opens the row actions menu on the first profile row, which is
    ...                the Default profile because the list is ordered oldest first.

    Click actions menu on custom profile row    0

User returns to the custom models list
    [Documentation]    Uses the back control in the profiles page header.

    Click back from custom profiles page

User searches the profiles for "${text}"
    [Documentation]    Narrows the list using the search field above the table.

    Enter search filter text    ${text}

User edits the default profile
    [Documentation]    Chooses Edit on the Default profile's row, which is the first row.

    Click actions menu on custom profile row    0
    Click edit action in custom profile row menu

User adds a profile named "${name}" and deploys it
    [Documentation]    Names a new profile and saves it through the action that continues
    ...                into a deploy, leaving the runtime parameters as offered.

    Click new profile on custom profiles page
    Wait for custom profile drawer
    Fill custom profile name    ${name}
    Save and deploy custom profile drawer

User deploys the profile named "${display_name}"
    [Documentation]    Chooses "Deploy with this profile" on that profile's row.

    Wait for custom profiles table
    Click actions menu on custom profile row showing "${display_name}"
    Click deploy action in custom profile row menu

User adds a profile named "${name}"
    [Documentation]    Opens the drawer, names the profile, and saves it, leaving the
    ...                runtime parameters at the values the drawer offers.

    Click new profile on custom profiles page
    Wait for custom profile drawer
    Fill custom profile name    ${name}
    Save custom profile drawer

User adds a profile named "${name}" with engine arguments "${yaml}"
    [Documentation]    Opens the drawer, names the profile, overrides a runtime setting, and
    ...                saves, so what the drawer sent can be compared with what the model
    ...                kept rather than only with what the screen shows.

    Click new profile on custom profiles page
    Wait for custom profile drawer
    Fill custom profile name    ${name}
    Fill custom profile engine arguments    ${yaml}
    Save custom profile drawer

User adds a profile named "${name}" on an offered runtime precision
    [Documentation]    Opens the drawer, names the profile, switches to the last precision the
    ...                drawer offers, and saves. The precision select lists only values the
    ...                base emits with the current accelerator/count, so a chosen option always
    ...                resolves to one base profile and the save is accepted rather than 400ing
    ...                on an axis combination the base never emits.

    Click new profile on custom profiles page
    Wait for custom profile drawer
    Fill custom profile name    ${name}
    ${precision}=    Select the last offered runtime precision
    VAR    ${TEST_PROFILE_CHOSEN_PRECISION}    ${precision}    scope=TEST
    Save custom profile drawer

User names the profile "${name}"
    [Documentation]    Enters a profile name without saving, so inline feedback on the
    ...                name can be observed.

    Fill custom profile name    ${name}

User edits the profile named "${name}"
    [Documentation]    Opens the drawer on the named profile from its row actions.

    Wait for custom profiles table
    Click actions menu on custom profile row showing "${name}"
    Click edit action in custom profile row menu
    Wait for custom profile drawer

User changes the engine arguments to "${yaml}" and saves
    [Documentation]    Changes the one runtime setting that is free text, then saves.

    Fill custom profile engine arguments    ${yaml}
    Save custom profile drawer

User abandons the profile drawer
    [Documentation]    Dismisses the drawer without saving.

    Cancel custom profile drawer

# =============================================================================
# Then keywords (verification)
# =============================================================================

The custom profiles list should be shown
    [Documentation]    Confirms the profiles table rendered for the selected model.

    Wait for custom profiles table

The default profile should be listed first
    [Documentation]    Confirms the model's onboarding profile is present and leads
    ...                the list, which is what the default ordering guarantees.

    Wait for custom profiles table
    ${rows}=    Get custom profile row count
    Should Be True    ${rows} > 0    msg=Expected at least the Default profile to be listed
    Wait for custom profile row "0" showing "Default"

The profile named "${display_name}" should be listed
    [Documentation]    Confirms a saved profile gets its own row alongside the default,
    ...                which is the reason this screen lists more than one profile.

    Wait for custom profiles table
    Wait for custom profile row showing "${display_name}"
    ${rows}=    Get custom profile row count
    Should Be True    ${rows} >= 2
    ...    msg=Expected the default and the saved profile to be listed, found ${rows} row(s)

Each profile should show its accelerator, metric, and precision
    [Documentation]    Confirms the summary columns show the runtime parameters the model
    ...                resolved at onboarding. These assert the values rather than merely
    ...                that text is present, because a profile whose parameters have not
    ...                resolved renders a placeholder that any non-empty check accepts.

    ${accelerator}    ${metric}    ${precision}=    Get custom profile summary at row "0"
    Should Contain    ${accelerator}    ${TEST_PROFILE_ACCELERATOR_MODEL}
    Should Contain    ${metric}    ${TEST_PROFILE_METRIC}    ignore_case=True
    Should Contain    ${precision}    ${TEST_PROFILE_PRECISION}    ignore_case=True

The default profile should show no author but show when it was created
    [Documentation]    Confirms the Default is presented as engine-owned: nobody submitted
    ...                it, so its author column shows the table's no-value placeholder,
    ...                while its creation time comes from the profile set itself.

    ${author}=    Get custom profile author at row "0"
    Should Be Equal    ${author}    ${CUSTOM_PROFILES_NO_VALUE}
    ...    msg=Expected the engine-owned Default to show no author, found "${author}"
    ${created}=    Get custom profile created time at row "0"
    Should Not Be Equal    ${created}    ${CUSTOM_PROFILES_NO_VALUE}
    ...    msg=Expected the Default to show when it was created

The saved profile should show its author and when it was created
    [Documentation]    Confirms a profile authored through the workbench is attributed,
    ...                which is what distinguishes it from the engine-owned Default. The
    ...                author is checked for presence rather than for a literal identity,
    ...                because the submitter depends on who the suite logs in as. The saved
    ...                profile is the second row, since the Default keeps the first.

    ${author}=    Get custom profile author at row "1"
    Should Not Be Equal    ${author}    ${CUSTOM_PROFILES_NO_VALUE}
    ...    msg=Expected the saved profile to name its author
    Should Not Be Empty    ${author}
    ${created}=    Get custom profile created time at row "1"
    Should Not Be Equal    ${created}    ${CUSTOM_PROFILES_NO_VALUE}
    ...    msg=Expected the saved profile to show when it was created

Only the profile named "${display_name}" should be listed
    [Documentation]    Confirms the search narrowed the list to the matching profile, so
    ...                profiles that do not match are left out rather than merely reordered.

    Wait for custom profile row "0" showing "${display_name}"
    Wait for no custom profile row showing "Default"
    ${rows}=    Get custom profile row count
    Should Be Equal As Integers    ${rows}    1
    ...    msg=Expected only the matching profile to be listed, found ${rows} row(s)

The model settings should be shown for editing
    [Documentation]    Confirms editing the Default leads to the model's own settings, which
    ...                is where its runtime parameters live, rather than to a profile form.

    Custom model edit page should show edit title

Deleting the default profile should be prevented
    [Documentation]    Confirms the Default profile cannot be deleted: the row's delete
    ...                action is disabled, so no confirmation dialog can be reached.

    ${state}=    Get custom profile delete action disabled state
    Should Be Equal    ${state}    true

The deploy should start on the profile named "${display_name}"
    [Documentation]    Confirms the deploy opens already set to the profile chosen in the
    ...                list, rather than to the model's default, so the choice carries over
    ...                and the user does not have to make it twice.

    Wait for custom model deploy drawer
    Deploy drawer should show profile selector
    ${shown}=    Get deploy drawer selected profile text
    Should Contain    ${shown}    ${display_name}
    ...    msg=Expected the deploy to start on "${display_name}", found "${shown}"

The custom models list should be shown
    [Documentation]    Confirms navigation returned to the Custom Models tab.

    Custom models tab should be visible

The profile named "${name}" should not be listed
    [Documentation]    Confirms an abandoned profile was never saved.

    Wait for custom profiles table
    Wait for no custom profile row showing "${name}"

The profile should open with the name "${name}" for editing
    [Documentation]    Confirms editing starts from what was saved rather than from an
    ...                empty form, so saving cannot silently reset the profile.

    ${shown}=    Get custom profile name
    Should Be Equal    ${shown}    ${name}

The profile named "${display_name}" should run on the same settings as the default profile
    [Documentation]    Confirms a profile added without touching the runtime settings runs on
    ...                the combination the model already uses, which is one its base supports.
    ...                Compared as the list presents them, since that is what the user sees.

    Wait for custom profiles table
    ${gpu}    ${metric}    ${precision}=    Get custom profile summary for "Default"
    ${new_gpu}    ${new_metric}    ${new_precision}=
    ...    Get custom profile summary for "${display_name}"
    Should Be Equal    ${new_gpu}    ${gpu}
    Should Be Equal    ${new_metric}    ${metric}
    Should Be Equal    ${new_precision}    ${precision}

The profile named "${display_name}" should run on the chosen precision
    [Documentation]    Confirms the profile the drawer saved runs on the precision the user
    ...                picked from the offered options. Because the offered options are only
    ...                the base's emitted combinations, the save was accepted and the summary
    ...                reflects the chosen precision.

    Wait for custom profiles table
    ${gpu}    ${metric}    ${precision}=    Get custom profile summary for "${display_name}"
    Should Contain    ${precision}    ${TEST_PROFILE_CHOSEN_PRECISION}    ignore_case=True
    ...    msg=Saved profile precision "${precision}" does not reflect the chosen "${TEST_PROFILE_CHOSEN_PRECISION}"

The profile named "${display_name}" should have kept engine argument "${arg_key}" set to "${arg_value}"
    [Documentation]    Reads the saved profile back to prove the drawer's runtime settings
    ...                were persisted rather than only rendered, which a check against the
    ...                list alone cannot show: the list does not surface engine arguments.
    ...                Polled because a create answers before the profile set has settled.

    Wait Until Keyword Succeeds    60 sec    5 sec
    ...    Saved profile carries engine argument    ${display_name}    ${arg_key}    ${arg_value}

Saved profile carries engine argument
    [Documentation]    Single-poll helper: the named profile's authored configuration carries
    ...                the engine argument.
    [Arguments]    ${display_name}    ${arg_key}    ${arg_value}

    ${namespace}=    Get Project Namespace
    ${response}=    List Custom Model Profiles
    ...    ${namespace}    ${TEST_CUSTOM_MODEL_NAME}    expected_status=200
    ${profiles}=    Get From Dictionary    ${response.json()}    data
    # Interpolate the target as a literal: a generator expression has its own scope, where
    # Robot's $display_name local is not visible. $profiles is safe in the outermost iterable.
    ${match}=    Evaluate
    ...    next((p for p in $profiles if p.get("displayName") == '${display_name}'), None)
    Should Not Be Equal    ${match}    ${None}
    ...    msg=Expected a saved profile named '${display_name}'
    ${config}=    Get From Dictionary    ${match}    customProfile    default=&{EMPTY}
    ${args}=    Get From Dictionary    ${config}    engineArgs    default=&{EMPTY}
    Should Be Equal As Strings    ${args}[${arg_key}]    ${arg_value}
    ...    msg=Engine argument '${arg_key}' was not kept on profile '${display_name}'

The name should be reported as already used
    [Documentation]    Confirms a name another profile already uses is refused while the
    ...                user is still filling the form, not after a failed save.

    Wait for custom profile name error    Another profile on this model already uses this name.

The name should be reported as reserved
    [Documentation]    Confirms the name of the model's onboarding profile is protected.

    Wait for custom profile name error    is reserved for the model
