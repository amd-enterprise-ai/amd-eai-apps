# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       AIWB Secrets management and AIRM autodiscovery integration.
...                 Tests AIWB secret CRUD operations, use case filtering,
...                 and cross-service autodiscovery with AIRM.

Library             TestPrefix

Resource            resources/aiwb_common.resource
Resource            resources/aiwb_secrets.resource
Resource            resources/airm_projects.resource
Resource            resources/airm_secrets.resource

Suite Teardown      Clean Up All Tracked Resources
Test Setup          Initialize AIWB Secret Tracking
Test Teardown       Run Keywords
...                 Clean Up All Created AIWB Secrets
...                 AND    Clean Up All Created Secrets


*** Test Cases ***
Create secret via AIWB API
    [Documentation]    Verify creating a secret via AIWB API
    [Tags]    secret    smoke    create

    Given a ready project with user access exists
    When a secret "test-secret" with use case "HuggingFace" is created via AIWB
    Then AIWB secret "test-secret" should exist

List secrets for namespace
    [Documentation]    Verify listing secrets returns the secrets this test created.
    ...    A newly provisioned project may already contain platform-managed baseline secrets,
    ...    so assert presence by display name instead of an exact total.
    [Tags]    secret    smoke    list

    Given a fresh project with user access exists
    And a secret "secret-one" is created via AIWB
    And a secret "secret-two" is created via AIWB
    When AIWB secrets are listed
    Then the secret list should include display name for "secret-one"
    And the secret list should include display name for "secret-two"

User can browse project secrets page by page
    [Documentation]    Secrets in a project are served in pages rather than as
    ...                one flat list.
    [Tags]    secret    list    pagination

    Given a ready project with user access exists
    When AIWB secrets are listed
    Then the result is returned page by page

Filter secrets by use case
    [Documentation]    Verify useCase filtering returns only matching secrets
    [Tags]    secret    list

    Given a ready project with user access exists
    And a secret "hf-token" with use case "HuggingFace" is created via AIWB
    And a secret "pull-secret" with use case "ImagePullSecret" is created via AIWB
    And a secret "generic-secret" with use case "Generic" is created via AIWB
    When AIWB secrets filtered by use case "HuggingFace" should return "1" results

Get secret details
    [Documentation]    Verify getting a specific secret by name
    [Tags]    secret    smoke    get

    Given a ready project with user access exists
    And a secret "detail-test" with use case "S3" is created via AIWB
    Then AIWB secret "detail-test" should exist

Create S3 secret via AIWB API
    [Documentation]    Verify an S3 secret with valid credentials can be created via AIWB
    [Tags]    secret    smoke    create    s3

    Given a ready project with user access exists
    When a secret "s3-creds" with use case "S3" is created via AIWB
    Then AIWB secret "s3-creds" should exist

S3 secret without credentials is rejected
    [Documentation]    Verify an S3 secret missing recognized access/secret keys is rejected
    [Tags]    secret    smoke    create    s3

    Given a ready project with user access exists
    When an S3 secret "no-creds" without credentials is submitted via AIWB
    Then the response should fail with a validation error
    And AIWB secret "no-creds" should not exist

Delete secret via AIWB API
    [Documentation]    Verify deleting a secret removes it
    [Tags]    secret    smoke    delete

    Given a ready project with user access exists
    And a secret "to-delete" is created via AIWB
    When AIWB secret "to-delete" is deleted
    Then AIWB secret "to-delete" should not exist

Display name with special characters is stored and returned
    [Documentation]    Verify a secret can be created with spaces, unicode, and special characters
    ...    in the display name, and the display name is returned unchanged in the response.
    [Tags]    secret    smoke    create    display-name

    Given a ready project with user access exists
    When a secret is created with display name "My HF Token (2024) – v1!"
    Then AIWB secret display name should be "${TEST_AIWB_SECRET_NAME}"

K8s resource name is auto-generated and differs from display name
    [Documentation]    Verify the K8s resource name is auto-generated
    ...    and is distinct from the user-provided display name.
    [Tags]    secret    smoke    create    display-name

    Given a ready project with user access exists
    When a secret "auto-name-check" is created via AIWB
    Then AIWB secret K8s name should be auto-generated

Display name is shown in secret list
    [Documentation]    Verify the displayName field is populated in the list response.
    [Tags]    secret    smoke    list    display-name

    Given a ready project with user access exists
    And a secret "listed-secret" is created via AIWB
    When AIWB secrets are listed
    Then the secret list should include display name for "listed-secret"

Error response uses camelCase envelope
    [Documentation]    When a request fails with extra error context, the additional
    ...    information must be exposed under the camelCase key "additionalInfo" and
    ...    never under the snake_case key "additional_info", per the API contract.
    [Tags]    secret    smoke    api-contract

    Given a ready project with user access exists
    When an image pull secret with invalid JSON content is submitted
    Then the response should fail with a validation error
    And the error envelope should expose extra context under "additionalInfo"
    And the error envelope should not contain "additional_info"

AIWB-created secret is discovered by AIRM
    [Documentation]    Verify AIRM autodiscovery finds AIWB-created secrets
    [Tags]    secret    autodiscovery

    Given a ready project with user access exists
    When a secret "cross-service" with use case "HuggingFace" is created via AIWB
    Then AIWB secret should be discovered by AIRM

AIWB-deleted secret is removed from AIRM
    [Documentation]    Verify AIRM removes secret after AIWB deletes it
    [Tags]    secret    autodiscovery    delete

    Given a ready project with user access exists
    And a secret "delete-cross" with use case "Generic" is created via AIWB
    And AIWB secret should be discovered by AIRM
    When AIWB secret "delete-cross" is deleted
    Then AIWB secret should be removed from AIRM

AIWB-created secret survives AIRM pod restart
    [Documentation]    Verify no duplicates after AIRM controller restart
    [Tags]    secret    autodiscovery    restart

    Given a ready project with user access exists
    And a secret "restart-test" is created via AIWB
    And AIWB secret should be discovered by AIRM
    When AIRM agent pod is restarted
    And AIRM agent pod should be ready
    Then AIWB auto-discovered secret should not be duplicated
