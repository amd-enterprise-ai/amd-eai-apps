# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for the custom model import wizard.
...
...                 Verifies the toolbar entry point on the Custom Models tab, the
...                 wizard layout (three steps), source-step validation for both Hugging
...                 Face and S3 sources, preview wiring for the credential each source
...                 needs, navigation back to the custom models list, full wizard
...                 submission, and credential error handling.

Resource            resources/common/browser_setup.resource
Resource            resources/custom_model_import.resource
Resource            resources/airm_projects.resource
Resource            resources/airm_secrets.resource

Suite Teardown      Run Keywords    Clean Up All Created Custom Models    AND    Clean Up All Created AIWB Secrets    AND    Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
Custom models tab exposes the import model entry point
    [Documentation]    Verify that the Custom Models tab shows an "Import model"
    ...                toolbar button that opens the full-page import wizard.
    [Tags]    ui    models    custom-models    import    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    When user opens the custom model import wizard
    Then the import wizard should be open
    And the import wizard should show all three steps

Fine-tune models tab does not expose the import model entry point
    [Documentation]    Verify that the "Import model"
    ...                toolbar button on the Custom Models tab only — the
    ...                Fine-tune Models tab must not surface it.
    [Tags]    ui    models    custom-models    import    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on fine-tune models tab
    Then the import model entry point should not be available

Import wizard refuses to advance when the source is empty
    [Documentation]    Verify that the source step's primary action does not advance
    ...                the wizard until a source is provided.
    [Tags]    ui    models    custom-models    import    validation

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    When user attempts to advance from the source step
    Then the import wizard should remain on the source step

Cancel returns the user to the custom models list
    [Documentation]    Verify that the wizard's Cancel action returns the user to
    ...                the Custom Models tab without onboarding anything.
    [Tags]    ui    models    custom-models    import    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    When user cancels the import wizard
    Then the custom models tab should be shown

Header back link returns the user to the custom models list
    [Documentation]    Verify that the back link rendered above the wizard title
    ...                returns the user to the Custom Models tab without
    ...                onboarding anything.
    [Tags]    ui    models    custom-models    import    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    When user returns to the custom models list via the header back link
    Then the custom models tab should be shown

Import wizard warns when the display name matches an existing custom model
    [Documentation]    Custom-model dedupe is keyed on the display name, so reusing an
    ...                existing name may overwrite that model or be rejected. Verify the
    ...                information step warns about the duplicate and clears the warning
    ...                for a unique name.
    [Tags]    ui    models    custom-models    import    smoke

    Given a ready project with user access exists
    And a custom model named "Duplicate Probe Model" exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    And user enters source "${CUSTOM_MODEL_IMPORT_PREVIEW_SOURCE}" in the import wizard
    And user attempts to advance from the source step
    When user enters display name "Duplicate Probe Model" in the import wizard
    Then the duplicate display name warning should be shown
    When user enters display name "A Clearly Unique Model Name" in the import wizard
    Then the duplicate display name warning should not be shown

Importing a custom model with runtime profile settings persists them
    [Documentation]    Step 3 of the import wizard collects the runtime profile. Filling the
    ...                engine-arguments and environment-variables YAML and onboarding must persist
    ...                those values on the model, so a later deploy runs with them. Verified through
    ...                the API to prove the wizard wrote them to the backend, not just the form.
    [Tags]    ui    models    custom-models    import    profile

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    And user enters source "${CUSTOM_MODEL_IMPORT_PREVIEW_SOURCE}" in the import wizard
    And user attempts to advance from the source step
    And user advances to the runtime profile step
    When user sets runtime profile engine settings to "max-model-len: 8192" and "VLLM_LOGGING_LEVEL: DEBUG"
    And user saves the runtime profile and starts onboarding
    Then the onboarded model should carry engine argument "max-model-len" set to "8192"
    And the onboarded model should carry environment variable "VLLM_LOGGING_LEVEL" set to "DEBUG"

Importing a custom model with a non-default precision persists it
    [Documentation]    Step 3 of the import wizard lets the user pick a precision. Because the
    ...                AIMModel CRD prunes spec.profiles.overrides.precision, a non-default
    ...                choice (FP8) must be preserved on a durable annotation so a later edit
    ...                and deploy honour it. Verified through the API to prove the wizard wrote
    ...                the selection to the backend, not just the form.
    [Tags]    ui    models    custom-models    import    profile

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    And user enters source "${CUSTOM_MODEL_IMPORT_PREVIEW_SOURCE}" in the import wizard
    And user attempts to advance from the source step
    And user advances to the runtime profile step
    When user selects runtime profile precision "fp8"
    And user saves the runtime profile and starts onboarding
    Then the onboarded model should use precision "fp8"

Importing a custom model on a runtime combination the wizard offers succeeds
    [Documentation]    The wizard offers only runtime choices the base supports, so a user can
    ...                pick a combination the model actually runs and onboarding is accepted,
    ...                rather than being left with a submit that fails on an unsupported choice.
    [Tags]    ui    models    custom-models    import    profile

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    And user enters source "${CUSTOM_MODEL_IMPORT_PREVIEW_SOURCE}" in the import wizard
    And user attempts to advance from the source step
    And user advances to the runtime profile step
    When user onboards on a runtime combination the wizard offers
    Then the onboarded model should use the chosen precision

Runtime profile image picker lists base families and latest tags first
    [Documentation]    The import wizard runtime profile should offer discovered
    ...                (non-automatic) image families and default the version field to
    ...                the newest option for the selected family.
    [Tags]    ui    models    custom-models    import    profile

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    And user enters source "${CUSTOM_MODEL_IMPORT_PREVIEW_SOURCE}" in the import wizard
    And user attempts to advance from the source step
    And user advances to the runtime profile step
    Then the runtime profile should offer at least one non-automatic container image family
    When user selects the first non-automatic runtime profile container image family
    Then the runtime profile should default to the newest container version option

Custom model import preview names the Kubernetes secret for the selected token
    [Documentation]    When a saved Hugging Face token's display label differs from its
    ...                Kubernetes secret name, previewing the source must send the secret
    ...                resource name as ``hfTokenSecretName`` so the API resolves the credential.
    [Tags]    ui    models    custom-models    import    hf-token    smoke

    Given a ready project with user access exists
    And a secret "hf-ui-wire" with use case "HuggingFace" is created via AIWB
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    And user enters source "${CUSTOM_MODEL_IMPORT_PREVIEW_SOURCE}" in the import wizard
    And user selects saved Hugging Face token by display name    ${TEST_AIWB_SECRET_NAME}
    ${preview_wait}=    Promise To    Wait For Response    matcher=**/models/preview    timeout=60s
    When user attempts to advance from the source step
    ${preview}=    Wait For    ${preview_wait}
    Then the custom model preview request should name the Hugging Face secret    ${preview}    ${TEST_AIWB_SECRET_K8S_NAME}

Import wizard offers a choice of model source and asks for the matching credential
    [Documentation]    A model can come from a Hugging Face repository or an object storage
    ...                bucket, and each needs a different credential. Verify the source step
    ...                lets the user switch between them and shows only the credential field
    ...                belonging to the chosen source — a stale credential from the other
    ...                source must not ride along on the import.
    [Tags]    ui    models    custom-models    import    s3    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    Then the wizard should ask for a Hugging Face token
    When user chooses S3 as the model source
    Then the wizard should ask for an S3 configuration
    When user chooses Hugging Face as the model source
    Then the wizard should ask for a Hugging Face token

Import wizard refuses to preview an S3 source that is not a bucket location
    [Documentation]    An S3 import needs a bucket location; a Hugging Face style repository
    ...                reference cannot be read from object storage. Verify the wizard keeps
    ...                the user on the source step instead of sending a request that can only
    ...                fail in the backend.
    [Tags]    ui    models    custom-models    import    s3    validation

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    And user chooses S3 as the model source
    When user enters source "${CUSTOM_MODEL_IMPORT_PREVIEW_SOURCE}" in the import wizard
    And user attempts to advance from the source step
    Then the import wizard should remain on the source step

Import wizard refuses to preview an S3 source without an S3 configuration
    [Documentation]    Object storage is never anonymous, so an S3 import cannot proceed until
    ...                the user picks an S3 configuration. Verify the wizard blocks on the source
    ...                step when a bucket location is given without one.
    [Tags]    ui    models    custom-models    import    s3    validation

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    And user chooses S3 as the model source
    When user enters source "s3://default-bucket/aiwb-e2e/no-such-model" in the import wizard
    And user attempts to advance from the source step
    Then the import wizard should remain on the source step

Previewing an S3 source with missing files warns the user but lets them continue
    [Documentation]    An object storage folder is not guaranteed to hold a complete model, and
    ...                the user is better placed than the wizard to judge whether an incomplete
    ...                folder is a problem. The user creates an S3 configuration inline, binding
    ...                an existing S3 secret to the bucket. Verify the wizard reports what is
    ...                missing yet still advances, and that the S3 configuration the user created
    ...                is the one carried on the preview as ``s3StorageName``.
    [Tags]    ui    models    custom-models    import    s3    smoke

    Given a ready project with user access exists
    And object storage credentials are ready in the project
    And a model folder missing recommended files exists in object storage
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    And user chooses S3 as the model source
    And user enters the prepared object storage folder in the import wizard
    And user creates an S3 configuration named "minio-preview-config" backed by secret "minio-credentials"
    ${preview_wait}=    Promise To    Wait For Response    matcher=**/models/preview    timeout=60s
    When user attempts to advance from the source step
    ${preview}=    Wait For    ${preview_wait}
    Then the custom model preview request should name the S3 configuration    ${preview}    ${TEST_S3_STORAGE_K8S_NAME}
    And the import wizard should reach the information step
    And the import wizard should warn about the source contents

Import wizard reuses an existing S3 configuration for preview
    [Documentation]    Once an S3 configuration exists in the project it should be selectable from
    ...                the dropdown on a later import without recreating it. The user creates a
    ...                configuration, switches source away and back to clear the selection, then
    ...                reselects the existing configuration and previews with it.
    [Tags]    ui    models    custom-models    import    s3    smoke

    Given a ready project with user access exists
    And object storage credentials are ready in the project
    And a model folder missing recommended files exists in object storage
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    And user chooses S3 as the model source
    And user enters the prepared object storage folder in the import wizard
    And user creates an S3 configuration named "minio-reuse-config" backed by secret "minio-credentials"
    When user chooses Hugging Face as the model source
    And user chooses S3 as the model source
    And user enters the prepared object storage folder in the import wizard
    And user selects saved S3 configuration named    minio-reuse-config
    ${preview_wait}=    Promise To    Wait For Response    matcher=**/models/preview    timeout=60s
    And user attempts to advance from the source step
    ${preview}=    Wait For    ${preview_wait}
    Then the custom model preview request should name the S3 configuration    ${preview}    ${TEST_S3_STORAGE_K8S_NAME}

Completing the import wizard onboards the model and shows it in the list
    [Documentation]    A user who steps through all three wizard steps and submits should
    ...                see the model card appear on the Custom Models tab in Ready state,
    ...                confirming the onboard API accepted the request and the list page
    ...                reflects the new model.
    [Tags]    ui    models    custom-models    import    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    And user enters source "${CUSTOM_MODEL_IMPORT_PREVIEW_SOURCE}" in the import wizard
    When user attempts to advance from the source step
    And user advances from the information step
    And user submits the import wizard
    Then the custom models tab should be shown
    And a custom model card should appear as ready

Import wizard shows an error when preview fails with an invalid token
    [Documentation]    When a user selects an invalid Hugging Face token and attempts to
    ...                preview a gated model, the wizard must stay on the source step and
    ...                surface an error toast — the user is not silently advanced past a
    ...                credential failure.
    [Tags]    ui    models    custom-models    import    hf-token    smoke

    Given a ready project with user access exists
    And a secret "hf-token-invalid" with use case "HuggingFace" is created via AIWB
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on custom models tab
    And user opens the custom model import wizard
    And user enters source "${CUSTOM_MODEL_IMPORT_GATED_SOURCE}" in the import wizard
    And user selects saved Hugging Face token by display name    ${TEST_AIWB_SECRET_NAME}
    When user attempts to advance from the source step
    Then the import wizard should remain on the source step
    And the import wizard should show a preview error
