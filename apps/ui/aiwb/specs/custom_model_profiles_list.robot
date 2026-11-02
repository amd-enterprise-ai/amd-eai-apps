# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for the custom profiles list screen.
...                 Verifies the card action reaches the list, that the model's
...                 default profile is shown with its summary parameters, author, and
...                 creation time alongside any saved profile, that searching narrows
...                 the list, that the default is edited through model settings, that a
...                 chosen profile can be deployed from its row, and that the default
...                 profile cannot be deleted.

Resource            resources/common/browser_setup.resource
Resource            resources/custom_model_profiles.resource
Resource            resources/airm_projects.resource
Resource            resources/airm_secrets.resource

Suite Teardown      Run Keywords    Clean Up All Created Custom Models    AND    Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
Custom model card opens the profiles list
    [Documentation]    Verify that choosing Profiles on a custom model card takes the
    ...                user to that model's profiles list.
    [Tags]    ui    models    custom-models    profiles

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And user is on custom models tab
    When user opens the profiles view from the custom model card
    Then the custom profiles list should be shown

Profiles list shows the model's default profile
    [Documentation]    Verify that an onboarded model lists its default profile first,
    ...                with the runtime parameters the user chose at onboarding.
    [Tags]    ui    models    custom-models    profiles

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    When user is on the custom profiles list
    Then the default profile should be listed first
    And each profile should show its accelerator, metric, and precision
    And the default profile should show no author but show when it was created

Profiles list shows a saved profile alongside the default
    [Documentation]    Verify that a profile saved against the model is listed together
    ...                with the default profile, which keeps its place at the top.
    [Tags]    ui    models    custom-models    profiles

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And the model has a saved profile named "Low latency"
    When user is on the custom profiles list
    Then the default profile should be listed first
    And the profile named "Low latency" should be listed
    And the saved profile should show its author and when it was created

Searching the profiles list narrows it to what matches
    [Documentation]    Verify that searching leaves only the profiles that match, so a model
    ...                with many profiles can be narrowed to the one the user is after.
    [Tags]    ui    models    custom-models    profiles

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And the model has a saved profile named "Low latency"
    And user is on the custom profiles list
    When user searches the profiles for "Low latency"
    Then only the profile named "Low latency" should be listed

Default profile is edited through model settings
    [Documentation]    Verify that editing the profile a model was onboarded with leads to
    ...                the model's own settings, because that is where its runtime
    ...                parameters are configured.
    [Tags]    ui    models    custom-models    profiles

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And user is on the custom profiles list
    When user edits the default profile
    Then the model settings should be shown for editing

Default profile cannot be deleted
    [Documentation]    Verify that the profile a model was onboarded with is protected
    ...                from deletion.
    [Tags]    ui    models    custom-models    profiles    negative

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And user is on the custom profiles list
    When user opens the row actions for the default profile
    Then deleting the default profile should be prevented

Profiles list starts a deploy on the chosen profile
    [Documentation]    Verify that a user who has picked a profile in the list can deploy the
    ...                model on it from there, and that the deploy starts on that profile
    ...                rather than on the model's default.
    [Tags]    ui    models    custom-models    profiles

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And the model has a saved profile named "Low latency" that is ready to serve
    And user is on the custom profiles list
    When user deploys the profile named "Low latency"
    Then the deploy should start on the profile named "Low latency"

User can return to the custom models list
    [Documentation]    Verify that the profiles list offers a way back to the models
    ...                the user came from.
    [Tags]    ui    models    custom-models    profiles

    Given a ready project with user access exists
    And secret "minio-credentials-fetcher" is assigned to project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And an onboarded custom model with a default profile exists
    And user is on the custom profiles list
    When user returns to the custom models list
    Then the custom models list should be shown
