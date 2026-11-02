# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for AIWB Secrets management.
...
...                 Suite Efficiency Design:
...                 Uses Suite Setup/Teardown for project tracking and cleanup. Each test declares
...                 its own preconditions via Given steps (idempotent - first test creates, subsequent
...                 tests reuse). Secrets are created via API for reliable test data setup and
...                 verified via UI for cross-boundary integration.

# UI resources (feature layer + browser setup)
Resource            resources/common/browser_setup.resource
Resource            resources/secrets.resource

# API resources (infrastructure preconditions, resolved via pythonpath)
Resource            resources/aiwb_secrets.resource
Resource            resources/airm_projects.resource

Library             TestPrefix

Suite Teardown      Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
Secrets page displays all secrets
    [Documentation]    Verify that secrets created via API are displayed in the UI secrets list.
    [Tags]    ui    secrets    list

    Given a ready project with user access exists
    And a secret "ui-list-test" is created via AIWB
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on secrets page
    Then secret "${TEST_AIWB_SECRET_NAME}" should be visible in the list

Add secret through UI form
    [Documentation]    Verify that a user can create a new secret via the UI form
    ...                and it appears in the secrets list.
    [Tags]    ui    secrets    create

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on secrets page
    When user creates a secret "ui-created-secret" with use case "HuggingFace" and value "hf_test_token_value"
    Then secret "ui-created-secret" should be visible in the list

Add S3 secret through UI form
    [Documentation]    Verify that a user can create an S3 secret via the UI form
    ...                and it appears in the secrets list with S3 use case.
    [Tags]    ui    secrets    create    s3

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on secrets page
    When user creates an S3 secret "ui-s3-secret" with access key "AKIAEXAMPLE" and secret key "secret-access-key-value"
    Then secret "ui-s3-secret" should be visible in the list
    And secrets table should contain text "S3"

Delete secret through UI
    [Documentation]    Verify that a user can delete a secret via the UI actions menu
    ...                and it is removed from the list.
    [Tags]    ui    secrets    delete

    Given a ready project with user access exists
    And a secret "ui-delete-test" is created via AIWB
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on secrets page
    And secret "${TEST_AIWB_SECRET_NAME}" should be visible in the list
    When user deletes secret "${TEST_AIWB_SECRET_NAME}"
    Then secret "${TEST_AIWB_SECRET_NAME}" should not be visible in the list

Delete confirmation references the display name
    [Documentation]    Verify the delete confirmation modal references the user-facing display name
    ...                shown in the table, not the internal Kubernetes resource name.
    [Tags]    ui    secrets    delete

    Given a ready project with user access exists
    And a secret "ui-delete-confirm-name" is created via AIWB
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on secrets page
    And secret "${TEST_AIWB_SECRET_NAME}" should be visible in the list
    When user opens the delete confirmation for secret "${TEST_AIWB_SECRET_NAME}"
    Then the delete confirmation should reference "${TEST_AIWB_SECRET_NAME}"
    And the delete confirmation should not reference "${TEST_AIWB_SECRET_K8S_NAME}"

No duplicate secrets after namespace switching
    [Documentation]    Regression test: switching between projects should not cause
    ...                duplicate entries in the secrets list.
    [Tags]    ui    secrets    regression    namespace

    # Set up first project with a secret
    ${first_project_name}=    Test Name    testing
    Given a ready project "${first_project_name}" with user access exists
    And a secret "ns-switch-a" is created via AIWB

    # Set up second project with a secret
    ${second_project_name}=    Test Name    testing-2
    And a ready project "${second_project_name}" with user access exists
    And a secret "ns-switch-b" is created via AIWB

    And user is logged in

    # View secrets in second project
    And project "${second_project_name}" is selected
    And user is on secrets page

    # Switch to first project and verify secrets load correctly
    When user switches to project "${first_project_name}"
    And user is on secrets page
    Then secrets list should contain at least "1" secrets

Workspace deploy form shows only image pull secrets in dropdown
    [Documentation]    Verify imagePullSecrets dropdown filters secrets by type,
    ...                showing only ImagePullSecret-type secrets.
    [Tags]    ui    secrets    workspace    regression

    # Compute expected full names for assertions
    ${hf_name}=    Test Name    hf-token
    ${pull_name}=    Test Name    pull-secret
    ${generic_name}=    Test Name    generic-cred

    Given a ready project with user access exists
    And a secret "hf-token" with use case "HuggingFace" is created via AIWB
    And a secret "pull-secret" with use case "ImagePullSecret" is created via AIWB
    And a secret "generic-cred" with use case "Generic" is created via AIWB
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When the user opens the workspace deploy form
    Then the imagePullSecrets dropdown should only show image pull secrets
    And the imagePullSecrets dropdown should contain "${pull_name}"
    And the imagePullSecrets dropdown should not contain "${hf_name}"
    And the imagePullSecrets dropdown should not contain "${generic_name}"
