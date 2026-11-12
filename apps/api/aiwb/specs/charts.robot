# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Test scenarios for Catalog API charts endpoints.
...                 Verifies chart creation, listing and deletion operations.
Resource    resources/aiwb_charts.resource
Library             OperatingSystem
Test Teardown       Clean Up All Created Charts


*** Test Cases ***
Create new chart
    [Documentation]    Verify that a new chart can be created with required files
    [Tags]                  charts                  create                  smoke

    Given required chart files exist
    And valid chart data is prepared
    When create chart request is sent
    Then response status should be 201
    And chart should exist in database

List charts with pagination
    [Documentation]    Verify that charts can be listed with pagination
    ...    Prerequisites:
    ...    - Multiple test charts exist in database
    ...
    ...    Steps:
    ...    1. Request paginated list of charts
    ...    2. Verify pagination metadata
    ...    3. Verify response content structure
    ...    4. Verify total count meets minimum
    [Tags]                  charts                  list                    smoke

    # Ensure we can create test charts for listing
    Given multiple charts exist
    When list charts request is sent
    ...                     page_number=1
    ...                     page_size=2
    Then response status should be 200
    And total count should be greater than 2

Update existing chart
    [Documentation]    Verify that an existing chart can be updated with new files
    [Tags]                  charts                  update

    Given a chart exists
    When update chart request is sent
    Then response status should be 200
    And chart should be updated

Delete existing chart
    [Documentation]    Verify that an existing chart can be deleted
    ...    Steps:
    ...    1. Create a test chart
    ...    2. Delete the chart
    ...    3. Verify deletion response
    ...    4. Verify chart no longer exists in database
    [Tags]                  charts                  delete

    Given a chart exists
    When delete chart request is sent
    Then response status should be 204  # HTTP 204 No Content is correct for successful deletion
    And the chart should not exist in database

Create chart with nested template files
    [Documentation]    Verify that chart files organised in subdirectories are accepted and kept in place
    [Tags]                  charts                  create                  smoke

    Given valid chart data is prepared
    When a chart is uploaded with a file in a subdirectory
    Then the chart upload should be accepted
    And the chart should keep the file in its subdirectory

Reject chart upload with a file escaping the chart directory
    [Documentation]    Verify that a chart cannot place files outside its own directory on the server
    [Tags]                  charts                  create                  negative                security                smoke

    Given valid chart data is prepared
    When a chart is uploaded with a file that escapes the chart directory
    Then the chart upload should be rejected
    And the chart should not be in the catalog

Reject chart upload with a file at an absolute location
    [Documentation]    Verify that a chart cannot place files at arbitrary absolute locations on the server
    [Tags]                  charts                  create                  negative                security                smoke

    Given valid chart data is prepared
    When a chart is uploaded with a file at an absolute location
    Then the chart upload should be rejected
    And the chart should not be in the catalog

Reject chart update with a file escaping the chart directory
    [Documentation]    Verify that updating a chart cannot place files outside its own directory on the server
    [Tags]                  charts                  update                  negative                security                smoke

    Given a chart exists
    When the chart is updated with a file that escapes the chart directory
    Then the chart update should be rejected
    And the chart files should be unchanged

Delete non-existent chart
    [Documentation]    Verify proper error when deleting non-existent chart
    ...    Steps:
    ...    1. Attempt to delete chart with invalid ID
    ...    2. Verify error response
    [Tags]                  charts                  delete                  negative

    Given a chart does not exist
    When delete chart request is sent
    Then response status should be 404
