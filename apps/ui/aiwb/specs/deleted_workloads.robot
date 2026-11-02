# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for hiding deleted workloads on the Deployed Models page.
...
...                 A deleted deployment is kept as a record but clutters the day-to-day list,
...                 so it is hidden by default and shown only to a user who asks for it. The
...                 request has no on-screen control — it is handed out as a link and remembered
...                 for later visits — so these scenarios describe opting in, not how the opt-in
...                 is expressed.
...
...                 Suite efficiency design:
...                 Scenarios that need a genuinely deleted deployment deploy and then delete an
...                 AIM, and are tagged gpu. Scenarios that only inspect which statuses the
...                 filter offers need no deployment at all and are tagged smoke.

# UI resources (feature layer + browser setup)
Resource            resources/common/browser_setup.resource
Resource            resources/deleted_workloads.resource
Resource            resources/workloads.resource

# API resources (infrastructure preconditions, resolved via pythonpath)
Resource            resources/aiwb_aims.resource
Resource            resources/airm_projects.resource

Suite Teardown      Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
Deleted deployments are absent from the deployed models list by default
    [Documentation]    A user who deletes a deployment should stop seeing it in the Deployed
    ...                Models list, without having to filter it away themselves.
    [Tags]    ui    workloads    deleted    gpu

    Given a ready project with user access exists
    And AIM is deployed
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And AIM has been deleted
    When user is on the deployed models page
    Then the deleted deployment should not be listed

Deleted is not offered as a workload status to filter by
    [Documentation]    Hiding deleted deployments also removes Deleted from the statuses the
    ...                list can be filtered by, so a user is not offered a filter that can only
    ...                ever match nothing.
    [Tags]    ui    workloads    deleted    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on the deployed models page
    When user opens the workload status filter
    Then deleted should not be offered as a workload status to filter by
    And live workload statuses should still be offered

Opting in lists deleted deployments again
    [Documentation]    A user who opts in to seeing deleted workloads gets the deleted
    ...                deployment back in the Deployed Models list.
    [Tags]    ui    workloads    deleted    gpu

    Given a ready project with user access exists
    And AIM is deployed
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And AIM has been deleted
    When user opts in to showing deleted workloads
    Then the deleted deployment should be listed

Opting in offers deleted as a workload status to filter by
    [Documentation]    Once deleted workloads are shown, Deleted becomes a status the list can
    ...                be filtered by, so a user can narrow the list down to just the history.
    [Tags]    ui    workloads    deleted    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user opts in to showing deleted workloads
    And user opens the workload status filter
    Then deleted should be offered as a workload status to filter by

Opting in to showing deleted workloads is remembered on the next visit
    [Documentation]    The choice survives navigating away and coming back, so a user who was
    ...                given the opt-in once does not have to repeat it on every visit.
    [Tags]    ui    workloads    deleted    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And the user has opted in to showing deleted workloads
    When user returns to the deployed models page
    And user opens the workload status filter
    Then deleted should be offered as a workload status to filter by

Opting back out of showing deleted workloads is remembered on the next visit
    [Documentation]    A user who opted in can reverse the choice, and the reversal is
    ...                remembered the same way the opt-in was.
    [Tags]    ui    workloads    deleted    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And the user has opted in to showing deleted workloads
    When user opts out of showing deleted workloads
    And user returns to the deployed models page
    And user opens the workload status filter
    Then deleted should not be offered as a workload status to filter by

Deleted deployments stay reachable by their own address while hidden from the list
    [Documentation]    Hiding a deleted deployment must not discard it: a user following an
    ...                older link to that deployment still sees its historical details.
    [Tags]    ui    workloads    deleted    gpu

    Given a ready project with user access exists
    And AIM is deployed
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And AIM has been deleted
    When user is on the deployed models page
    Then the deleted deployment should not be listed
    When user navigates directly to the deleted AIM detail page by ID
    Then historical AIM details should be rendered
