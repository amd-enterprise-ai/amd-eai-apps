# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for the custom model import wizard.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)

Library             Collections
Library             libraries/custom_model_import_network.py
Resource            common/session.resource
Resource            pages/models_page.resource
Resource            resources/airm_secrets.resource
Resource            resources/aiwb_secrets.resource
Resource            resources/aiwb_custom_models.resource


*** Variables ***
# Same tiny public fixture repo as AIWB API custom-model E2Es (`aiwb_custom_models.resource`).
${CUSTOM_MODEL_IMPORT_PREVIEW_SOURCE}    hf-internal-testing/tiny-random-LlamaForCausalLM
# Gated repo — requires a valid HuggingFace token; used to exercise credential failure paths.
${CUSTOM_MODEL_IMPORT_GATED_SOURCE}      hf-internal-testing/dummy_gated_model


*** Keywords ***
# =============================================================================
# Given keywords (UI preconditions)
# =============================================================================

User is on custom models tab
    [Documentation]    Navigates to the Custom Models tab of the models page.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to custom models page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

A custom model named "${display_name}" exists in the project
    [Documentation]    Seeds a minimal custom-model CR in the project namespace so the
    ...                import wizard's duplicate-name check has an existing name to match.

    Seed Custom Model With Display Name    duplicate-probe-model    ${display_name}    ${TEST_PROJECT}[name]
    Track Custom Model For Cleanup    ${TEST_PROJECT}[name]    duplicate-probe-model

User is on fine-tune models tab
    [Documentation]    Navigates to the Fine-tune Models tab of the models page.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to fine-tune models page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

A model folder missing recommended files exists in object storage
    [Documentation]    Seeds a folder in the platform's object storage that holds only a
    ...                config.json. Previewing it succeeds, but the missing tokenizer and
    ...                weight files give the wizard warnings to surface.

    A config-only S3 source is prepared for custom model preview

Object storage credentials are ready in the project
    [Documentation]    Assigns minio-credentials-fetcher and waits for the synced
    ...                minio-credentials secret before S3 import wizard steps use it.

    Secret "minio-credentials-fetcher" is assigned to project
    ${namespace}=    Get Project Namespace
    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Minio Credentials Secret Exists In Project Namespace    ${namespace}

# =============================================================================
# When keywords (actions)
# =============================================================================

User opens the custom model import wizard
    [Documentation]    Clicks the "Import model" toolbar button to open the wizard.

    Click import model button
    Wait for import wizard page

User attempts to advance from the source step
    [Documentation]    Clicks the source step primary action (Preview model). Also used
    ...                after filling valid data to advance the wizard.

    Click import wizard next on source step

User advances from the information step
    [Documentation]    Clicks the information step's "Next" button to move to the runtime
    ...                profile step. Expects the wizard to already be on step 2.

    Click import wizard next on information step

User submits the import wizard
    [Documentation]    Clicks the final "Import model" submit button on the runtime profile
    ...                step. The wizard redirects to the custom models tab on success.

    Click import wizard submit

User enters source "${value}" in the import wizard
    [Documentation]    Types a Hugging Face source value into the source input.

    Fill import wizard source    ${value}

User enters display name "${value}" in the import wizard
    [Documentation]    Types a display name into the information step's display-name input.

    Fill import wizard display name    ${value}

User selects saved Hugging Face token by display name
    [Arguments]    ${display_name}
    [Documentation]    Picks an existing project Hugging Face token in the import wizard
    ...                using the label shown in the dropdown (the secret display name).

    Open project Hugging Face token dropdown
    Click Hugging Face token option labeled    ${display_name}

User chooses Hugging Face as the model source
    [Documentation]    Picks the Hugging Face source family on the wizard's source step.

    Select import wizard source type    huggingFace

User chooses S3 as the model source
    [Documentation]    Picks the S3 source family on the wizard's source step.

    Select import wizard source type    s3

User enters the prepared object storage folder in the import wizard
    [Documentation]    Types the seeded object-storage folder into the source input. Requires
    ...                a preceding Given that prepared the folder.

    Should Not Be Equal    ${TEST_S3_PREVIEW_SOURCE}    ${None}
    ...    msg=No object storage folder was prepared for this test
    Fill import wizard source    ${TEST_S3_PREVIEW_SOURCE}

User selects saved S3 configuration named
    [Arguments]    ${name}
    [Documentation]    Picks an existing project S3 configuration in the import wizard by the
    ...                name shown in the dropdown.

    Open project S3 configuration dropdown
    Click S3 configuration option labeled    ${name}

User creates an S3 configuration named "${name}" backed by secret "${secret_label}"
    [Documentation]    Opens the inline create dialog on the source step, fills the S3
    ...                configuration details, picks an existing S3 secret to back it, and
    ...                saves. The wizard auto-selects the newly created configuration.

    Open project S3 configuration dropdown
    Open S3 configuration create dialog
    Fill S3 configuration dialog    ${name}    ${AIWB_E2E_S3_BUCKET_URL}    us-east-1
    Select S3 configuration dialog secret labeled    ${secret_label}
    Submit S3 configuration create dialog
    ${k8s_name}=    Resolve S3 storage Kubernetes name    ${TEST_PROJECT}[name]    ${name}
    Set Test Variable    ${TEST_S3_STORAGE_K8S_NAME}    ${k8s_name}

User cancels the import wizard
    [Documentation]    Cancels the wizard via the source step's Cancel button.

    Click import wizard cancel

User returns to the custom models list via the header back link
    [Documentation]    Navigates back to the Custom Models tab using the header
    ...                back link rendered above the wizard title.

    Click import wizard header back

User advances to the runtime profile step
    [Documentation]    From the information step, advances the wizard to the runtime profile
    ...                step and waits for it to render.

    Click import wizard next on information step
    Wait for runtime profile step

User sets runtime profile engine settings to "${engine_args_yaml}" and "${env_vars_yaml}"
    [Documentation]    Fills the runtime step's engine-arguments and environment-variables
    ...                YAML editors, the per-deployment runtime knobs the wizard collects.

    Fill runtime profile engine arguments    ${engine_args_yaml}
    Fill runtime profile environment variables    ${env_vars_yaml}

User selects runtime profile precision "${precision}"
    [Documentation]    Chooses a precision in the runtime step's precision select. The
    ...                selection must survive onboarding even though the AIMModel CRD
    ...                prunes it from spec.profiles.overrides.

    Select runtime profile precision    ${precision}

User selects runtime profile container image family "${family_label}"
    [Documentation]    Chooses a container-image family in the runtime profile step.

    Select runtime profile container image family    ${family_label}

User saves the runtime profile and starts onboarding
    [Documentation]    Submits the wizard's runtime step to onboard the model with the
    ...                supplied runtime profile.

    Submit import wizard runtime step

User onboards on a runtime combination the wizard offers
    [Documentation]    Switches to the last precision the wizard offers, then submits. The
    ...                precision select lists only values reachable from the current
    ...                accelerator/count, so a chosen option resolves to a base profile and
    ...                the onboard is accepted rather than failing on an unsupported choice.

    ${precision}=    Select the last offered runtime precision
    VAR    ${TEST_ONBOARD_CHOSEN_PRECISION}    ${precision}    scope=TEST
    Submit import wizard runtime step

# =============================================================================
# Then keywords (verification)
# =============================================================================

The import wizard should be open
    [Documentation]    Verifies the import wizard page is visible.

    Wait for import wizard page

The import wizard should show all three steps
    [Documentation]    Verifies the wizard renders the three-step stepper with the
    ...                expected step labels.

    Import wizard should show stepper labels

The import wizard should remain on the source step
    [Documentation]    Verifies the source step input is still visible — proving
    ...                the wizard did not advance after a failed validation.

    Import wizard source input should be visible

The wizard should ask for a Hugging Face token
    [Documentation]    Verifies the Hugging Face credential field is the one on offer, and the
    ...                S3 configuration field is not — the source families must not be mixed.

    Import wizard Hugging Face token selector should be visible
    Import wizard S3 configuration selector should be absent

The wizard should ask for an S3 configuration
    [Documentation]    Verifies the S3 configuration field is the one on offer, and the Hugging
    ...                Face token field is not — the source families must not be mixed.

    Import wizard S3 configuration selector should be visible
    Import wizard Hugging Face token selector should be absent

The import wizard should reach the information step
    [Documentation]    Verifies the wizard advanced past the source step to model information.

    Import wizard information step should be visible

The import wizard should warn about the source contents
    [Documentation]    Verifies the wizard reports what the preview found missing in the source
    ...                folder. The warning is advisory: the user can still continue.

    Import wizard preview warnings should be visible

The runtime profile should offer container image family "${family_label}"
    [Documentation]    Verifies the runtime profile image-family dropdown includes the
    ...                supplied family label among available options.

    Open runtime profile container image selector
    ${count}=    Get open select option count
    @{option_labels}=    Create List
    FOR    ${idx}    IN RANGE    ${count}
        ${label}=    Get open select option text    ${idx}
        Append To List    ${option_labels}    ${label}
    END
    List Should Contain Value    ${option_labels}    ${family_label}

User selects the first non-automatic runtime profile container image family
    [Documentation]    Picks the first discovered family that is not "Automatic".
    ...                Fails when only the automatic placeholder is available.

    Open runtime profile container image selector
    ${count}=    Get open select option count
    @{option_labels}=    Create List
    FOR    ${idx}    IN RANGE    ${count}
        ${label}=    Get open select option text    ${idx}
        Append To List    ${option_labels}    ${label}
    END
    ${selected_family}=    Evaluate    next((label for label in $option_labels if label.strip().lower() != "automatic"), None)
    Should Not Be Equal    ${selected_family}    ${None}
    ...    msg=Expected at least one discovered (non-automatic) container image family
    User selects runtime profile container image family "${selected_family}"

The runtime profile should offer at least one non-automatic container image family
    [Documentation]    Verifies the image-family dropdown includes at least one discovered
    ...                base family besides the automatic placeholder.

    Open runtime profile container image selector
    ${count}=    Get open select option count
    @{option_labels}=    Create List
    FOR    ${idx}    IN RANGE    ${count}
        ${label}=    Get open select option text    ${idx}
        Append To List    ${option_labels}    ${label}
    END
    ${non_automatic_count}=    Evaluate    len([label for label in $option_labels if label.strip().lower() != "automatic"])
    Should Be True    ${non_automatic_count} > 0
    ...    msg=Expected at least one discovered (non-automatic) container image family

The runtime profile should list container versions in this order
    [Documentation]    Verifies the runtime profile version dropdown starts with the
    ...                expected newest-first tag ordering for the selected image family.
    [Arguments]    @{expected_versions}

    Open runtime profile container version selector
    FOR    ${idx}    ${expected}    IN ENUMERATE    @{expected_versions}
        ${actual}=    Get open select option text    ${idx}
        Should Be Equal As Strings    ${actual}    ${expected}
        ...    msg=Version option at index ${idx} should be '${expected}' but was '${actual}'
    END

The runtime profile should default to the newest container version option
    [Documentation]    Verifies the version select defaults to the first (newest)
    ...                option shown in the version dropdown for the selected family.

    ${selected}=    Get runtime profile selected container version text
    Open runtime profile container version selector
    ${count}=    Get open select option count
    Should Be True    ${count} > 0
    ...    msg=Expected at least one container-version option for selected image family
    ${first}=    Get open select option text    0
    Should Be Equal As Strings    ${selected}    ${first}
    ...    msg=Expected selected container version '${selected}' to match first option '${first}'

The custom model preview request should name the S3 configuration
    [Arguments]    ${preview_response}    ${expected_storage_name}
    [Documentation]    Verifies the browser's preview POST carried the selected S3
    ...                configuration identifier as ``s3StorageName``.

    ${request}=    Get From Dictionary    ${preview_response}    request
    Should Not Be Equal    ${request}    ${None}
    ${post}=    Get From Dictionary    ${request}    postData
    ${post_dict}=    Normalize Json Post Payload    ${post}
    Dictionary Should Contain Key    ${post_dict}    s3StorageName
    ${actual}=    Get From Dictionary    ${post_dict}    s3StorageName
    Should Be Equal    ${actual}    ${expected_storage_name}

The duplicate display name warning should be shown
    [Documentation]    Verifies the wizard warns that the entered display name
    ...                matches an existing custom model, warning that saving may
    ...                overwrite that model's settings or be rejected.

    Import wizard duplicate name warning should be visible

The duplicate display name warning should not be shown
    [Documentation]    Verifies the wizard shows no duplicate-name warning when the
    ...                entered display name does not match an existing custom model.

    Import wizard duplicate name warning should be hidden

The custom models tab should be shown
    [Documentation]    Verifies the user is back on the Custom Models tab.

    Custom models tab should be visible

A custom model card should appear as ready
    [Documentation]    Polls until at least one custom model card reaches a
    ...                deployable ("Ready") state, detected by an enabled Deploy
    ...                button. Confirms the onboard API accepted the submission
    ...                and the list page reflects it.

    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Custom model card with ready status should be visible

The import wizard should show a preview error
    [Documentation]    Verifies that a preview failure surfaces an error toast to the user.
    ...                The toast message starts with "Failed to preview model source" regardless
    ...                of the specific backend error appended after the prefix.

    Wait For Elements State    text=Failed to preview model source    visible    timeout=30s

The import model entry point should not be available
    [Documentation]    Verifies the "Import model" toolbar button is absent —
    ...                used to confirm the entry point lives on the Custom
    ...                Models tab only and not on adjacent tabs.

    Import model button should be absent

The custom model preview request should name the Hugging Face secret
    [Arguments]    ${preview_response}    ${expected_k8s_secret_name}
    [Documentation]    Verifies the browser's preview POST carried the Kubernetes secret
    ...                resource name as ``hfTokenSecretName`` (not the human display label).

    Should Be Equal As Integers    ${preview_response.status}    200
    ${request}=    Get From Dictionary    ${preview_response}    request
    Should Not Be Equal    ${request}    ${None}
    ${post}=    Get From Dictionary    ${request}    postData
    ${post_dict}=    Normalize Json Post Payload    ${post}
    Dictionary Should Contain Key    ${post_dict}    hfTokenSecretName
    ${actual}=    Get From Dictionary    ${post_dict}    hfTokenSecretName
    Should Be Equal    ${actual}    ${expected_k8s_secret_name}

The onboarded model should carry engine argument "${arg_key}" set to "${arg_value}"
    [Documentation]    Reads the onboarded AIMModel's persisted runtime overrides via the API to
    ...                prove the wizard's runtime profile values reached the backend, not just the
    ...                form. Polled because onboarding writes the CR asynchronously after submit.

    Wait Until Keyword Succeeds    90 sec    5 sec
    ...    Onboarded model overrides should carry engine argument    ${arg_key}    ${arg_value}

Onboarded model overrides should carry engine argument
    [Documentation]    Single-poll helper: the onboarded model's ``engineArgs`` override carries
    ...                the supplied key and value.
    [Arguments]    ${arg_key}    ${arg_value}
    ${overrides}=    Get onboarded model overrides
    ${args}=    Get From Dictionary    ${overrides}    engineArgs    default=&{EMPTY}
    Should Be Equal As Strings    ${args}[${arg_key}]    ${arg_value}
    ...    msg=Wizard runtime profile engine argument '${arg_key}' was not persisted on the model

The onboarded model should carry environment variable "${var_name}" set to "${var_value}"
    [Documentation]    Reads the onboarded AIMModel's persisted runtime overrides via the API to
    ...                prove the wizard's environment variable value reached the backend.
    ...                Polled because onboarding writes the CR asynchronously after submit.

    Wait Until Keyword Succeeds    90 sec    5 sec
    ...    Onboarded model overrides should carry environment variable    ${var_name}    ${var_value}

Onboarded model overrides should carry environment variable
    [Documentation]    Single-poll helper: searches the onboarded model's ``engineEnv`` list for
    ...                an entry with the given name and asserts its value matches.
    [Arguments]    ${var_name}    ${var_value}
    ${overrides}=    Get onboarded model overrides
    ${env_list}=    Get From Dictionary    ${overrides}    engineEnv    default=@{EMPTY}
    FOR    ${entry}    IN    @{env_list}
        IF    '${entry}[name]' == '${var_name}'
            Should Be Equal As Strings    ${entry}[value]    ${var_value}
            ...    msg=Wizard runtime profile env var '${var_name}' is '${entry}[value]', expected '${var_value}'
            RETURN
        END
    END
    Fail    Environment variable '${var_name}' not found in onboarded model overrides engineEnv

The onboarded model should use precision "${precision}"
    [Documentation]    Reads the onboarded AIMModel's precision annotation via the API to prove the
    ...                wizard's precision selection reached the backend. Precision is pruned from
    ...                spec.profiles.overrides by the CRD, so it is persisted (and read back) on the
    ...                ``aiwb.apps.eai.amd.com/precision`` annotation. Polled because onboarding
    ...                writes the CR asynchronously after submit.

    Wait Until Keyword Succeeds    90 sec    5 sec
    ...    Onboarded model annotation should carry precision    ${precision}

The onboarded model should use the chosen precision
    [Documentation]    Confirms the onboarded model runs on the precision the wizard offered and the
    ...                user chose, proving the wizard only offers combinations the base supports.

    Wait Until Keyword Succeeds    90 sec    5 sec
    ...    Onboarded model annotation should carry precision    ${TEST_ONBOARD_CHOSEN_PRECISION}

Onboarded model annotation should carry precision
    [Documentation]    Single-poll helper: the onboarded model's precision annotation matches.
    [Arguments]    ${precision}
    ${annotations}=    Get onboarded model annotations
    ${actual}=    Get From Dictionary    ${annotations}    aiwb.apps.eai.amd.com/precision    default=${EMPTY}
    Should Be Equal As Strings    ${actual}    ${precision}
    ...    msg=Wizard precision selection was not persisted on the onboarded model annotation
