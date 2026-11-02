# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       AIWB project storage creation scenarios.
Resource            resources/airm_projects.resource
Resource            resources/aiwb_secrets.resource
Resource            resources/aiwb_storages.resource
Suite Teardown      Clean Up All Tracked Resources
Test Setup          Run Keywords    Initialize AIWB Secret Tracking    AND    Initialize AIWB Storage Tracking
Test Teardown       Run Keywords    Clean Up All Created AIWB Storages    AND    Clean Up All Created AIWB Secrets


*** Test Cases ***
Create storage without explicit credential key names
    [Documentation]    A user can create storage from an S3 secret without naming key fields.
    [Tags]    storage    create    smoke
    Given a ready project with user access exists
    And a secret "storage-creds" with use case "S3" is created via AIWB
    When a storage "auto-key-resolution" is created from prepared secret without credential key names
    Then Storage creation should succeed with resolved credential key names

Create storage preserves free-form display name and generates kubernetes identifier
    [Documentation]    A user can provide a mixed-case display name with spaces, and the API
    ...                preserves it while generating a distinct wb-storage-* resource name.
    [Tags]    storage    create    smoke
    Given a ready project with user access exists
    And a secret "storage-free-form-creds" with use case "S3" is created via AIWB
    When a storage "Team Alpha Mixed Case 42" is created from prepared secret without credential key names
    Then Storage creation should preserve free-form display name and generated kubernetes name

Create storage without explicit credential key names using storage aliases
    [Documentation]    A user can create storage from a secret that stores S3 credentials
    ...                with storage-specific alias keys.
    [Tags]    storage    create    smoke
    Given a ready project with user access exists
    And an unlabeled secret "storage-alias-creds" with storage credential aliases exists
    When a storage "storage-alias-key-resolution" is created from prepared secret without credential key names
    Then Storage creation should succeed with storage credential aliases

Create storage fails when omitted key names are not discoverable
    [Documentation]    A user gets a validation error when secret credentials cannot be inferred.
    [Tags]    storage    create    negative
    Given a ready project with user access exists
    And an unlabeled secret "storage-without-s3-keys" without S3 credential aliases exists
    When a storage "missing-key-resolution" is created from prepared secret without credential key names
    Then Storage creation should fail with a validation error
    And Storage validation error should mention missing credential aliases

List storages returns created storages in the project
    [Documentation]    A user can list storage configurations created in the project.
    [Tags]    storage    list    smoke
    Given a ready project with user access exists
    And a secret "storage-list-creds" with use case "S3" is created via AIWB
    And a storage "list-storage-a" is created from prepared secret without credential key names
    When Project storages are listed
    Then The storage list should include storage "list-storage-a"

List storages can be filtered by storage type
    [Documentation]    A user can filter storage list results by storage type.
    [Tags]    storage    list    smoke
    Given a ready project with user access exists
    And a secret "storage-filter-creds" with use case "S3" is created via AIWB
    And a storage "filtered-storage" is created from prepared secret without credential key names
    When Project storages are listed filtered by type "S3"
    Then The storage list should include storage "filtered-storage"
    And All listed storages should have type "S3"

Create storage fails when display name already exists
    [Documentation]    Storage display names must be unique within a project even when
    ...                Kubernetes resource names are auto-generated.
    [Tags]    storage    create    negative
    Given a ready project with user access exists
    And a secret "storage-conflict-creds" with use case "S3" is created via AIWB
    And a storage "duplicate-display-name" is created from prepared secret without credential key names
    When a storage "duplicate-display-name" is created from prepared secret without credential key names
    Then Storage creation should fail with a conflict error
    And Storage conflict error should mention duplicate display name
