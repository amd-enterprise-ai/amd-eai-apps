# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for dataset management in AIWB UI.
...
...                 Tests cover: uploading datasets through the UI, verifying the dataset
...                 list displays metadata, and download indicator behavior (appearing,
...                 auto-dismiss, manual dismiss).

# UI resources (feature layer + browser setup)
Resource            resources/common/browser_setup.resource
Resource            resources/datasets.resource

# API resources (infrastructure preconditions, resolved via pythonpath)
Resource            resources/airm_projects.resource

Suite Setup         Initialize Dataset UI Suite
Suite Teardown      Clean Up Dataset UI Suite
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
Dataset uploaded through UI appears in dataset list
    [Documentation]    Verify that a dataset uploaded via the UI upload form appears in the
    ...                dataset list after a successful upload.
    [Tags]    ui    datasets    upload    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on datasets page
    When user uploads a dataset through the UI
    Then the uploaded dataset should appear in the dataset list
    [Teardown]    Run Keywords    Track UI uploaded dataset for cleanup    AND    Close test browser

Datasets page displays all datasets with metadata
    [Documentation]    Verify that the datasets page lists existing datasets showing their
    ...                names and types so users can identify and manage their data.
    [Tags]    ui    datasets    list    smoke

    Given a ready project with user access exists
    And a dataset exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on datasets page
    Then datasets should be listed with their metadata

Datasets page displays file sizes
    [Documentation]    Verify dataset sizes use suitable units.
    [Tags]    ui    datasets    list

    Given a ready project with user access exists
    And datasets of different sizes exist
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on datasets page
    Then dataset file sizes should be displayed

Download indicator appears when dataset download starts
    [Documentation]    Verify that the download indicator appears in the preparing state
    ...                immediately after a dataset download is triggered from the table.
    [Tags]    ui    datasets    download    smoke

    Given a ready project with user access exists
    And a dataset exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on datasets page
    When user triggers download for dataset "${TEST_DATASET}[name]"
    Then download indicator should be in preparing state

Download indicator can be manually dismissed during preparing state
    [Documentation]    Verify that dismissing the download indicator while it is in the
    ...                preparing state keeps it hidden even after the download completes.
    ...                This verifies the race condition fix: a dismissed indicator must
    ...                not reappear when the in-flight download resolves.
    [Tags]    ui    datasets    download

    Given a ready project with user access exists
    And a dataset exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on datasets page
    And user triggers download for dataset "${TEST_DATASET}[name]"
    And download indicator should be in preparing state
    When user dismisses the download indicator
    Then download indicator should not be visible
    And download indicator should not reappear after dismissal

User browses a long list of datasets with pagination
    [Documentation]    Verifies the datasets table displays the first page and pagination
    ...                controls when more datasets exist than fit on a single page, and
    ...                that navigating to subsequent pages shows different datasets.
    [Tags]    ui    datasets    pagination

    Given a ready project with user access exists
    And the project contains more datasets than fit on a single page
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on datasets page
    Then the datasets table shows the first page of datasets
    And pagination controls should be visible
    And the user can navigate to the next page

Download indicator auto-dismisses after download completes
    [Documentation]    Verify that the download indicator transitions from preparing to done
    ...                once the download completes, then automatically disappears.
    [Tags]    ui    datasets    download

    Given a ready project with user access exists
    And a dataset exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on datasets page
    When user triggers download for dataset "${TEST_DATASET}[name]"
    Then download indicator should be in preparing state
    And download indicator should be in done state
    And download indicator should not be visible


*** Keywords ***
Initialize Dataset UI Suite
    [Documentation]    Initializes project tracking and the dataset ID tracking list
    ...                for cleanup at suite teardown.

    @{empty_list}=    Create List
    Set Suite Variable    ${CREATED_DATASET_IDS}    ${empty_list}

Clean Up Dataset UI Suite
    [Documentation]    Deletes all datasets and projects created during this suite.

    Clean Up Dataset Test Resources
    Clean Up All Created Projects
