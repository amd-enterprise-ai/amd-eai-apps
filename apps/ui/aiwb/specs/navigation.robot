# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for sidebar navigation.
Resource            resources/common/browser_setup.resource
Resource            resources/dashboard.resource
Resource            resources/navigation.resource
Resource            resources/airm_projects.resource

Suite Teardown      Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
Models menu group is collapsed by default
    [Tags]    ui    navigation    models    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    Then AI Workbench application title should be visible
    And Models menu group should be collapsed

Fine-tuning menu group is collapsed by default
    [Tags]    ui    navigation    fine-tuning    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    Then Fine-tuning menu group should be collapsed

Selecting Models expands its pages
    [Tags]    ui    navigation    models    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    When user selects Models in the menu
    Then Models menu group should be expanded
    And Dashboard should display the overview section

Selecting AIM catalog opens the catalog
    [Tags]    ui    navigation    models    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    When user selects AIM Catalog from Models in the menu
    Then AIM catalog should be shown
    And Models menu group should be expanded
    And AIM catalog should be highlighted in the menu

Tabbing past a collapsed menu group skips its hidden sub-items
    [Tags]    ui    navigation    models    accessibility    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    And Models menu group should be collapsed
    When user tabs from Models menu group
    Then focus should be on Fine-tuning menu group

Tabbing through an expanded menu group reaches each sub-item in order
    [Tags]    ui    navigation    models    accessibility    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    And user selects Models in the menu
    And Models menu group should be expanded
    When user tabs from Models menu group
    Then focus should be on AIM Catalog page link
    When user tabs to the next menu item
    Then focus should be on Custom Models page link
    When user tabs to the next menu item
    Then focus should be on Deployed Models page link
    When user tabs to the next menu item
    Then focus should be on Fine-tuning menu group

Selecting Fine-tuning expands its pages
    [Tags]    ui    navigation    fine-tuning    datasets    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    When user selects Fine-tuning in the menu
    Then Fine-tuning menu group should be expanded
    And Dashboard should display the overview section

Selecting Datasets opens the dataset list
    [Tags]    ui    navigation    fine-tuning    datasets    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    When user selects Datasets from Fine-tuning in the menu
    Then Datasets should be shown
    And Fine-tuning menu group should be expanded
    And Datasets should be highlighted in the menu

Datasets shows the Fine-tuning group it belongs to
    [Tags]    ui    navigation    fine-tuning    datasets    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    When user selects Datasets from Fine-tuning in the menu
    Then Datasets should be shown
    And the page location should be shown as    Fine-tuning    Datasets

Fine-tune models shows the Fine-tuning group it belongs to
    [Tags]    ui    navigation    fine-tuning    models    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    When user selects Fine-tune models in the menu
    Then Fine-tune models should be shown
    And the page location should be shown as    Fine-tuning    Fine-tune models

Hovering the collapsed menu reveals it without moving the page
    [Tags]    ui    navigation    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    And the menu is collapsed
    When user points at the menu
    Then menu page names should be visible
    And the page content should stay in place
    And menu item spacing should stay the same

Selected item fits within the collapsed menu
    [Tags]    ui    navigation    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    When user selects Chat in the menu
    And the menu is collapsed
    Then the selected menu item should fit within the collapsed menu

Collapsing the menu keeps the active group highlighted
    [Tags]    ui    navigation    models    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    When user selects AIM Catalog from Models in the menu
    And the menu is collapsed
    Then Models menu group should be highlighted

Page content is dimmed while the collapsed menu is revealed
    [Tags]    ui    navigation    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    And the menu is collapsed
    When user points at the menu
    Then the page content should be dimmed

Menu hides again shortly after the pointer leaves
    [Tags]    ui    navigation    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the dashboard page
    And the menu is collapsed
    And user points at the menu
    When user points away from the menu
    Then menu page names should be hidden
