# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for adding a custom model profile.
...                 Verifies that a profile can be added from the list, that it can be added
...                 and deployed in one go, that it starts from the runtime settings the model
...                 already uses, that a setting chosen in the drawer is kept, and that names
...                 already taken or reserved are refused while the user is still typing.
...
...                 The editing scenarios are tagged skip: changing a saved profile needs
...                 an update endpoint the API does not serve yet, so the row's Edit action
...                 stays unavailable for saved profiles. Blocking an in-use profile needs
...                 a deployment pinned to a named profile, which arrives with the deploy
...                 integration.

Resource            resources/common/browser_setup.resource
Resource            resources/custom_model_profiles.resource
Resource            resources/airm_projects.resource
Resource            resources/airm_secrets.resource

Suite Teardown      Run Keywords    Clean Up All Created Custom Models    AND    Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
User can add a profile to a custom model
    [Documentation]    Verify that a profile added from the profiles list is saved and
    ...                offered alongside the model's other profiles.
    [Tags]    ui    models    custom-models    profiles

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And user is on the custom profiles list
    When user adds a profile named "Low latency"
    Then the profile named "Low latency" should be listed

A profile can be added and deployed in one go
    [Documentation]    Verify that a user who adds a profile in order to deploy it is carried
    ...                into the deploy on that profile, rather than having to find it in the
    ...                list and start again.
    [Tags]    ui    models    custom-models    profiles

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And user is on the custom profiles list
    When user adds a profile named "Deploy right away" and deploys it
    Then the deploy should start on the profile named "Deploy right away"

A new profile starts from the model's current runtime settings
    [Documentation]    Verify that a profile added without touching the runtime settings runs
    ...                on the combination the model already uses, so naming a profile is
    ...                enough and the user is not left to guess a supported combination.
    [Tags]    ui    models    custom-models    profiles

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And user is on the custom profiles list
    When user adds a profile named "Inherited setup"
    Then the profile named "Inherited setup" should be listed
    And the profile named "Inherited setup" should run on the same settings as the default profile

Runtime settings chosen in the drawer are kept
    [Documentation]    Verify that a runtime setting the user overrides while adding a profile
    ...                is actually saved against the model, rather than only shown in the
    ...                form before saving.
    [Tags]    ui    models    custom-models    profiles

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And user is on the custom profiles list
    When user adds a profile named "Long context" with engine arguments "max-model-len: 16384"
    Then the profile named "Long context" should be listed
    And the profile named "Long context" should have kept engine argument "max-model-len" set to "16384"

A profile saves on a runtime combination the drawer offers
    [Documentation]    Verify that a runtime choice the drawer offers can be saved, so a user
    ...                can only pick a combination the model actually supports and is never
    ...                left with a save that fails on an unsupported choice.
    [Tags]    ui    models    custom-models    profiles

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And user is on the custom profiles list
    When user adds a profile named "Offered combo" on an offered runtime precision
    Then the profile named "Offered combo" should be listed
    And the profile named "Offered combo" should run on the chosen precision

Abandoned profile is not saved
    [Documentation]    Verify that leaving the drawer without saving adds nothing.
    [Tags]    ui    models    custom-models    profiles    negative

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And user is on the custom profiles list
    And user is adding a profile
    When user names the profile "Discarded draft"
    And user abandons the profile drawer
    Then the profile named "Discarded draft" should not be listed

Editing a profile starts from what was saved
    [Documentation]    Verify that editing an existing profile opens with its saved
    ...                values, so a save cannot silently reset it.
    [Tags]    ui    models    custom-models    profiles    skip

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And a profile named "High speed" was added to the model
    When user edits the profile named "High speed"
    Then the profile should open with the name "High speed" for editing

User can change a saved profile
    [Documentation]    Verify that a change to a saved profile is kept.
    [Tags]    ui    models    custom-models    profiles    skip

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And a profile named "High speed" was added to the model
    And user edits the profile named "High speed"
    When user changes the engine arguments to "max-model-len: 32768" and saves
    Then the profile named "High speed" should be listed

A name another profile already uses is refused
    [Documentation]    Verify that a duplicate profile name is reported while the user is
    ...                still filling the form, rather than failing on save.
    [Tags]    ui    models    custom-models    profiles    negative

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And a profile named "High speed" was added to the model
    And user is adding a profile
    When user names the profile "High speed"
    Then the name should be reported as already used

The Default name is reserved
    [Documentation]    Verify that the name of the model's onboarding profile cannot be
    ...                reused for a new profile.
    [Tags]    ui    models    custom-models    profiles    negative

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And user is on the custom profiles list
    And user is adding a profile
    When user names the profile "Default"
    Then the name should be reported as reserved
