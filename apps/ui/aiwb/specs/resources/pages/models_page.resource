# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for the AIWB Models / AIM Catalog page.
...                 Contains selectors and atomic browser interactions only.
...                 Business logic and assertions belong in feature resources.


*** Variables ***
${MODELS_PATH}                     /models/aim-catalog
${CUSTOM_MODELS_PATH}              /models/custom-models
${FINE_TUNE_MODELS_PATH}           /fine-tuning/models
${DEPLOYED_MODELS_PATH}            /models/deployed-models
${AIM_CATALOG_SELECTOR}            [data-testid="aim-catalog"]
${AIM_CATALOG_LOADING_SELECTOR}    [data-testid="aim-catalog-loading"]
${AIM_CARD_SELECTOR}               [data-testid="aim-catalog"] .grid > div
${DEPLOYED_MODELS_SELECTOR}        [data-testid="deployed-models"]
# The wizard's accessible name tracks the "deployAIM.title" translation ("Model Deployment"),
# not the AIM's name or the legacy "Deploy AIM" copy.
${DEPLOY_WIZARD_SELECTOR}          role=dialog[name="Model Deployment"]
${ACTIONS_MENU_SELECTOR}           [role="menu"]
${VERSION_SELECTOR}                [aria-label="Version"]
${METRIC_SELECTOR}                 [data-testid="deployAimPerformanceModeGroup"]
${UNSUPPORTED_BANNER_SELECTOR}     [data-testid="unsupported-banner"]
${DEPLOY_WIZARD_MODEL_HEADER_SELECTOR}    css=[data-testid="deploy-aim-wizard-model-header"]
${DEPLOY_WIZARD_MODEL_STEP_SELECTOR}      css=[data-testid="wizard-step-model"]
${SEARCH_FILTER_SELECTOR}          input[placeholder*="Search"]
${CATALOG_DESCRIPTION_SELECTOR}    [data-testid="aim-catalog"] > p
${REQUEST_MODEL_CARD_SELECTOR}     [data-testid="request-model"]
${ACCELERATOR_LABEL_SELECTOR}      [data-testid="aim-card-accelerator-types"]
${ACCELERATOR_FILTER_TRIGGER}      button[aria-label="Accelerator"]
${ACCELERATOR_FILTER_MENU}         [role="menu"][aria-label="Accelerator"]
${HAS_DEPLOYMENTS_CHIP_SELECTOR}   [data-testid="aim-card-has-deployments"]

# Fine-tune Models tab selectors
${FINE_TUNE_MODELS_SELECTOR}          [data-testid="fine-tune-models"]
${FINETUNE_BTN_SELECTOR}              css=[data-testid="fine-tune-models-finetune"]
${BASE_MODEL_SELECT_SELECTOR}         css=[data-testid="baseModelSelect"]
${BASE_MODEL_OPTION_SELECTOR}         css=[role="option"][data-testid^="model-select-"]
${BASE_MODEL_EMPTY_MSG}               No fine-tuning recipes available for your cluster hardware
${DATASET_SELECTOR_TABLE}             css=[data-testid="dataset-selector"]
${DATASET_ROW_CHECKBOX_SELECTOR}      css=[data-testid="dataset-selector"] [aria-label^="Select row "]
${DATASET_SELECT_ALL_SELECTOR}        css=[data-testid="dataset-selector"] [aria-label="Select all"]
${DATASET_SIZE_HEADER_SELECTOR}       css=[data-testid="dataset-selector"] th:has-text("Size")
${DATASET_SIZE_CELL_SELECTOR}         css=[data-testid="dataset-selector"] tr:has([aria-label^="Select row "]) td:nth-child(3)
${FINETUNE_WIZARD_NEXT_BTN}           css=[data-testid="wizard-next"]
${FINETUNE_WIZARD_BACK_BTN}           css=[data-testid="wizard-back"]
${HYPERPARAMETERS_SUMMARY_SELECTOR}   css=[data-testid="wizard-step-hyperparameters"]
${CUSTOMIZE_HYPERPARAMETERS_TOGGLE}   css=[data-testid="customize-hyperparameters-toggle"]
${LORA_TYPE_RADIO_SELECTOR}           role=radio[name="LoRA"]
${FINETUNE_TYPE_SELECTOR}             css=[data-testid="fine-tuning-type-selector"]
# HeroUI's NumberInput renders TWO inputs in the same wrapper: a hidden input
# carrying name= for form submission, and a type="text" input the user types into
# (react-aria avoids type="number" so locale formatting works). The visible input
# has data-slot="input" but no name; selectors must scope through the wrapper to
# disambiguate batchSize from epochs/learningRate.
${BATCH_SIZE_WRAPPER_SELECTOR}        css=[data-slot="inner-wrapper"]:has(input[name="batchSize"])
${BATCH_SIZE_INPUT_SELECTOR}          ${BATCH_SIZE_WRAPPER_SELECTOR} >> css=input[data-slot="input"]
${BATCH_SIZE_INCREMENT_SELECTOR}      ${BATCH_SIZE_WRAPPER_SELECTOR} >> css=[data-slot="increase-button"]
${LORA_RANK_INPUT_SELECTOR}           role=spinbutton[name="Rank"]
${LORA_ALPHA_INPUT_SELECTOR}          role=spinbutton[name="Alpha"]
${LORA_DROPOUT_INPUT_SELECTOR}        role=spinbutton[name="Dropout"]
${EPOCHS_INPUT_SELECTOR}              role=spinbutton[name="Number of epochs"]
${LEARNING_RATE_INPUT_SELECTOR}       role=spinbutton[name="Learning rate multiplier"]
${FINETUNE_DATASET_LIMIT_TOAST_SELECTOR}    css=[data-slot="toast"]:has-text("You can select up to 10 datasets")
${FINE_TUNE_MODELS_ROW_ACTION_BTN}    css=button[aria-label="Actions"]
${FINE_TUNE_MODELS_FINETUNE_OPTION}   css=[data-testid="finetune"]

# Custom-model deploy drawer — anchor on stable in-drawer markup (not translated title copy).
${CUSTOM_DEPLOY_DRAWER_SELECTOR}         css=[data-testid="runtime-profile-slot"]
# Profile selection, rendered only for custom-onboarded models
${CUSTOM_DEPLOY_PROFILE_SELECT}          css=[data-testid="deploy-profile-select"]
${CUSTOM_DEPLOY_PROFILE_TRIGGER}         ${CUSTOM_DEPLOY_PROFILE_SELECT} >> css=button
${CUSTOM_DEPLOY_PROFILE_DETAILS}         css=[data-testid="deploy-profile-details"]
${CUSTOM_DEPLOY_PROFILE_ADD_NEW}         css=[data-testid="deploy-profile-add-new"]
# Portalled, so matched by role rather than under the drawer
${CUSTOM_DEPLOY_PROFILE_LISTBOX}         css=[role="listbox"]
# Row action item for the Deploy option — data-testid is the action key ("deploy")
${FINE_TUNE_MODELS_DEPLOY_OPTION}        css=[data-testid="deploy"]
# Display-name input: FormInput renders an <input> whose name attr is "displayName"
${CUSTOM_DEPLOY_DISPLAY_NAME_INPUT}      css=input[name="displayName"]
# Autoscaling toggle: FormSwitch with data-testid="autoscaling-toggle"
${CUSTOM_DEPLOY_AUTOSCALING_TOGGLE}      css=[data-testid="autoscaling-toggle"]
# Deploy (confirm) button in the drawer footer: aria-label matches the confirmText prop
${CUSTOM_DEPLOY_SUBMIT_BTN}              css=button[aria-label="Deploy"]

# Custom Model Import wizard selectors
${IMPORT_MODEL_BUTTON_SELECTOR}            css=[data-testid="custom-models-import-model"]
${CUSTOM_MODEL_CARD_SELECTOR}              css=[data-testid="custom-model-card"]
${CUSTOM_MODEL_CARD_ACTIONS_SELECTOR}      css=[data-testid="custom-model-card-actions"]
${CUSTOM_MODEL_COPY_MENU_ITEM_SELECTOR}    css=[role="menuitem"]:has-text("Make a copy")
${CUSTOM_MODEL_SETTINGS_MENU_ITEM_SELECTOR}    css=[role="menuitem"]:has-text("Model settings")
${CUSTOM_MODEL_PROFILES_MENU_ITEM_SELECTOR}    css=[role="menuitem"]:has-text("Profiles")
${CUSTOM_MODEL_DELETE_MENU_ITEM_SELECTOR}      css=[role="menuitem"]:has-text("Delete")
${CUSTOM_MODEL_DELETE_MODAL_SELECTOR}          [data-testid="confirmation-modal"]
${CUSTOM_MODEL_DELETE_CONFIRM_BUTTON_SELECTOR}    [data-testid="confirm-button"]
${CUSTOM_MODEL_DELETE_CLOSE_BUTTON_SELECTOR}      css=[data-testid="confirmation-modal"] button:has-text("Close")
${IMPORT_WIZARD_PAGE_SELECTOR}             css=[data-testid="custom-model-import-page"]

# Custom profiles list page selectors
${CUSTOM_PROFILES_PATH_SUFFIX}             /profiles
${CUSTOM_PROFILES_TABLE_SELECTOR}          css=[data-testid="custom-profiles"]
${CUSTOM_PROFILES_BACK_SELECTOR}           css=[data-testid="custom-profiles-back"]
${CUSTOM_PROFILES_NEW_SELECTOR}            css=[data-testid="custom-profiles-new-profile"]
${CUSTOM_PROFILES_ROW_SELECTOR}            css=[data-testid="custom-profiles"] tbody tr
${CUSTOM_PROFILE_DELETE_MENU_ITEM_SELECTOR}    css=[role="menuitem"]:has-text("Delete")
${CUSTOM_PROFILE_EDIT_MENU_ITEM_SELECTOR}    css=[role="menuitem"]:has-text("Edit")
${CUSTOM_PROFILE_DEPLOY_MENU_ITEM_SELECTOR}    css=[role="menuitem"]:has-text("Deploy with this profile")
# Column positions, counted from 1 after the display name column.
${CUSTOM_PROFILES_ACCELERATOR_COLUMN}      2
${CUSTOM_PROFILES_METRIC_COLUMN}           3
${CUSTOM_PROFILES_PRECISION_COLUMN}        4
${CUSTOM_PROFILES_AUTHOR_COLUMN}           5
${CUSTOM_PROFILES_CREATED_COLUMN}          6
# The table renders an em dash where a profile has no value for a column.
${CUSTOM_PROFILES_NO_VALUE}                \u2014
# Add/edit profile drawer. The design system puts a field's data-testid on the
# <input> itself, and DrawerForm gives the confirm button an aria-label equal to
# its confirmText.
${CUSTOM_PROFILE_DRAWER_HEADING_SELECTOR}      css=[data-testid="custom-profile-heading"]
${CUSTOM_PROFILE_DRAWER_NAME_SELECTOR}         css=input[data-testid="custom-profile-display-name"]
${CUSTOM_PROFILE_DRAWER_ENGINE_ARGS_SELECTOR}    css=[data-testid="custom-profile-engine-args-yaml"]
${CUSTOM_PROFILE_DRAWER_SAVE_SELECTOR}         css=button[aria-label="Save"]
${CUSTOM_PROFILE_DRAWER_SAVE_DEPLOY_SELECTOR}    css=button[aria-label="Save and deploy"]
${CUSTOM_PROFILE_DRAWER_CANCEL_SELECTOR}       css=[role="dialog"] button:has-text("Cancel")
# The design system puts a field's data-testid on the <input> itself, so the
# wizard's text inputs are addressed directly rather than through a wrapper.
${IMPORT_WIZARD_SOURCE_INPUT_SELECTOR}     css=input[data-testid="custom-model-import-source"]
${IMPORT_WIZARD_NEXT_SOURCE_SELECTOR}          css=[data-testid="custom-model-import-next-source"]
${IMPORT_WIZARD_NEXT_INFORMATION_SELECTOR}    css=[data-testid="custom-model-import-next-information"]
${IMPORT_WIZARD_SUBMIT_SELECTOR}              css=[data-testid="custom-model-import-submit"]
${IMPORT_WIZARD_CANCEL_SELECTOR}              css=[data-testid="custom-model-import-cancel"]
${IMPORT_WIZARD_HEADER_BACK_SELECTOR}         css=[data-testid="custom-model-import-header-back"]
${CUSTOM_MODEL_CARD_READY_SELECTOR}           css=[data-testid="custom-model-card"] [data-testid="custom-model-card-deploy"]:enabled
${CUSTOM_MODEL_CARD_DEPLOY_BUTTON_SELECTOR}   css=[data-testid="custom-model-card-deploy"]
${CUSTOM_MODELS_EMPTY_STATE_SELECTOR}         css=[data-testid="custom-models-empty"]
${PROJECT_HF_TOKEN_SELECTOR}               css=[data-testid="project-hf-token-selector"]
${CUSTOM_MODEL_EDIT_LOAD_ERROR_SELECTOR}   css=[data-testid="custom-model-edit-error"]

# Source-family selectors. The wizard's first step picks between a Hugging Face
# repo and an S3 bucket; each family shows its own credential field, so tests
# assert on which selector is mounted rather than on internal form state.
${IMPORT_WIZARD_SOURCE_TYPE_SELECTOR}          css=[data-testid="custom-model-import-source-type"]
# Edit mode replaces the radio group with a read-only input carrying the same testid.
${IMPORT_WIZARD_SOURCE_TYPE_FIELD_SELECTOR}    css=input[data-testid="custom-model-import-source-type"]
${PROJECT_S3_STORAGE_SELECTOR}                 css=[data-testid="project-s3-storage-selector"]
# The S3 configuration dropdown stays disabled until the project's storages load,
# so interactions target its trigger button rather than the field wrapper.
${PROJECT_S3_STORAGE_TRIGGER_SELECTOR}         css=[data-testid="project-s3-storage-selector"] button
${S3_STORAGE_DIALOG_SECRET_SELECTOR}           css=[data-testid="s3-storage-selector-dialog-secret"] button
${IMPORT_WIZARD_PREVIEW_WARNINGS_SELECTOR}     css=[data-testid="custom-model-import-preview-warnings"]

# Custom Model Import/Edit wizard — runtime profile step selectors
# Engine args and env vars are YAML textareas in the runtime step (not a key/value editor).
${RUNTIME_ENGINE_ARGS_YAML_SELECTOR}           css=[data-testid="custom-model-import-engine-args-yaml"]
${RUNTIME_ENV_VARS_YAML_SELECTOR}              css=[data-testid="custom-model-import-env-vars-yaml"]
${RUNTIME_DISABLED_NOTICE_SELECTOR}            css=[data-testid="custom-model-import-runtime-disabled-notice"]
${RUNTIME_MODEL_PRECISION_SELECTOR}            css=[data-testid="custom-model-import-model-precision"]
${RUNTIME_CONTAINER_IMAGE_SELECTOR}            css=[data-testid="custom-model-import-container-image"]
${RUNTIME_CONTAINER_VERSION_SELECTOR}          css=[data-testid="custom-model-import-container-version"]
${SELECT_LISTBOX_OPTIONS_SELECTOR}             css=[role="listbox"] [role="option"]

# Catalog deploy wizard — advanced profile overrides.
${DEPLOY_ADVANCED_TOGGLE_SELECTOR}             css=[data-testid="deployAimPerformanceMode-advanced"]
${DEPLOY_ADVANCED_PRECISION_SELECTOR}          css=[aria-label="Precision"]
${DEPLOY_PERSONALIZATION_TOGGLE_SELECTOR}      css=[data-testid="personalization-toggle"]
${DEPLOY_PERSONALIZATION_MAX_RANK_SELECTOR}    css=[data-testid="deploy-personalization-max-rank"]
${DEPLOY_PERSONALIZATION_ADAPTERS_SELECTOR}    css=[data-testid="lora-adapters-selector"]
${DEPLOY_PERSONALIZATION_ADAPTERS_READY_SELECTOR}
...    css=[data-testid="lora-adapters-selector"][data-loading="false"]
${DEPLOY_WIZARD_SUBMIT_BUTTON_SELECTOR}        role=button[name="Deploy"]

# Deploy AIM wizard — the Next button's accessible name tracks the "actions.next"
# translation ("Next"); the wizard has no dedicated testid for it.
${DEPLOY_WIZARD_NEXT_BUTTON_SELECTOR}          role=button[name="Next"]
${DEPLOY_WIZARD_UNOPTIMIZED_WARNING_SELECTOR}  text="Unoptimized profile"
${CUSTOM_MODEL_EDIT_LOADING_SELECTOR}      css=[data-testid="custom-model-edit-loading"]
${IMPORT_WIZARD_DISPLAY_NAME_SELECTOR}     css=[data-testid="custom-model-import-page"] input[name="displayName"]
${IMPORT_WIZARD_DUP_WARNING_SELECTOR}      css=[data-testid="custom-model-import-duplicate-name-warning"]

# Pagination — HeroUI's Pagination component renders a sibling list with
# numbered buttons and prev/next controls. The next-page control carries
# aria-label="next page button" (HeroUI default). The fine-tune
# table lives on its own tab, not the Custom Models tab; selectors target the
# fine-tune-models testid root accordingly.
${FINE_TUNE_MODELS_TABLE_ROW}           css=${FINE_TUNE_MODELS_SELECTOR} table tbody tr
${FINE_TUNE_MODELS_PAGINATION}          css=${FINE_TUNE_MODELS_SELECTOR} [role="navigation"]
${FINE_TUNE_MODELS_NEXT_PAGE_BTN}       css=${FINE_TUNE_MODELS_SELECTOR} button[aria-label="next page button"]
# HF token section — the h4 heading is the stable anchor; the section is only
# mounted when the selected base model is gated, so its presence/absence
# proves the gating flag was respected.
${HF_TOKEN_SECTION_SELECTOR}            css=h4:has-text("Hugging Face Authentication")
${FINETUNE_CONFIRM_BTN_SELECTOR}        button[aria-label="Start training"]
${FINETUNE_DISPLAY_NAME_INPUT}          css=input[name="displayName"]
${FINETUNE_DESCRIPTION_INPUT}           css=input[name="description"]
${FINE_TUNE_MODELS_DETAILS_OPTION}      css=[data-testid="details"]

# HuggingFaceTokenSelector "Add new" popover — shared across every consumer of
# ProjectHuggingFaceTokenSelector (finetune wizard, catalog deploy wizard,
# custom-model import wizard), so these selectors are reused across specs.
${HF_TOKEN_ADD_NEW_SELECTOR}            css=[data-testid="hf-token-selector-add-new"]
${HF_TOKEN_DIALOG_NAME_SELECTOR}        css=[data-testid="hf-token-selector-dialog-name"]
${HF_TOKEN_DIALOG_TOKEN_SELECTOR}       css=[data-testid="hf-token-selector-dialog-token"]
${HF_TOKEN_DIALOG_SUBMIT_SELECTOR}      css=[data-testid="hf-token-selector-dialog-submit"]

# Deployed Models status filter. FilterDropdown renders its trigger as a
# div[role="button"] (not a <button>) carrying the filter label, and the open
# panel as a react-aria listbox with the same label. Each option renders its
# label twice — once as the label, once as the description — so options are
# matched by substring rather than exact text.
${STATUS_FILTER_TRIGGER}                [role="button"][aria-label="Statuses"]
${STATUS_FILTER_LISTBOX}                [role="listbox"][aria-label="Statuses"]


*** Keywords ***
Navigate to models page
    [Documentation]    Navigates to the AIM Catalog page and waits for it to load.
    [Arguments]    ${base_url}    ${project}

    Go To    ${base_url}/${project}${MODELS_PATH}
    Wait for AIM Catalog page

Wait for AIM Catalog page
    [Documentation]    Waits for the AIM Catalog content to become visible.

    Wait For Elements State    css=${AIM_CATALOG_SELECTOR}    visible    timeout=30s

Navigate to deployed models page
    [Documentation]    Navigates directly to the Deployed Models tab. ${query} appends a
    ...                query string (for example "?deleted=1") for entry points that are
    ...                only reachable by URL.
    [Arguments]    ${base_url}    ${project}    ${query}=${EMPTY}

    Go To    ${base_url}/${project}${DEPLOYED_MODELS_PATH}${query}
    Wait For Elements State    css=${DEPLOYED_MODELS_SELECTOR}    visible    timeout=30s

Click deploy button on card
    [Documentation]    Clicks the Deploy button on a specific AIM card.
    [Arguments]    ${aim_name}

    VAR    ${selector}    css=${AIM_CARD_SELECTOR}:has-text("${aim_name}") >> css=button:has-text("Deploy")
    Click    ${selector}

Click actions menu button on card
    [Documentation]    Clicks the actions menu (three dots) on a specific AIM card.
    ...                Waits for the button to become enabled since deployment data loads
    ...                asynchronously and the button is disabled until deployments are detected.
    [Arguments]    ${aim_name}

    VAR    ${selector}    css=${AIM_CARD_SELECTOR}:has-text("${aim_name}") >> css=button[aria-label="Actions"]
    Wait For Elements State    ${selector}    visible    timeout=15s
    Wait For Elements State    ${selector}    enabled    timeout=30s
    Click    ${selector}

Wait for deploy wizard
    [Documentation]    Waits for the Deploy AIM wizard to become visible.

    Wait For Elements State    ${DEPLOY_WIZARD_SELECTOR}    visible    timeout=15s

Get actions menu text
    [Documentation]    Returns the text content of the currently visible actions menu.

    VAR    ${menu}    css=${ACTIONS_MENU_SELECTOR}
    Wait For Elements State    ${menu}    visible    timeout=10s
    ${text}=    Get Text    ${menu}
    RETURN    ${text}

Get deployed model row text
    [Documentation]    Returns the text content of a deployed model row matching the given name.
    ...                Waits for the row to appear since the deployed models table loads
    ...                asynchronously (AIM services first, then catalog data for canonical name).
    [Arguments]    ${aim_name}

    VAR    ${selector}    css=${DEPLOYED_MODELS_SELECTOR} tr:has-text("${aim_name}")
    Wait For Elements State    ${selector}    visible    timeout=30s
    ${text}=    Get Text    ${selector}
    RETURN    ${text}

Get AIM card text
    [Documentation]    Returns the full text content of a specific AIM card.
    ...                Selects the first (outermost) card grid element matching the AIM name,
    ...                avoiding strict-mode violations when inner card divs also contain the text.
    [Arguments]    ${aim_name}

    VAR    ${selector}    css=${AIM_CARD_SELECTOR}:has-text("${aim_name}")
    ${elements}=    Get Elements    ${selector}
    ${text}=    Get Text    ${elements}[0]
    RETURN    ${text}

Get version selector text
    [Documentation]    Returns the currently selected version text from the version selector.

    VAR    ${selector}    css=${VERSION_SELECTOR}
    Wait For Elements State    ${selector}    visible    timeout=10s
    ${text}=    Get Text    ${selector}
    RETURN    ${text}

Get AIM card count
    [Documentation]    Returns the number of AIM cards displayed in the catalog grid.

    ${elements}=    Get Elements    css=${AIM_CARD_SELECTOR}
    ${count}=    Get Length    ${elements}
    RETURN    ${count}

Get catalog description text
    [Documentation]    Returns the catalog description text shown above the grid.

    ${text}=    Get Text    css=${CATALOG_DESCRIPTION_SELECTOR}
    RETURN    ${text}

AIM card should be visible
    [Documentation]    Verifies that a specific AIM card is visible in the catalog.
    ...                Uses Get Elements to avoid strict-mode violations from nested text matches.
    [Arguments]    ${aim_name}

    VAR    ${selector}    css=${AIM_CARD_SELECTOR}:has-text("${aim_name}")
    ${elements}=    Get Elements    ${selector}
    Should Be True    len($elements) > 0    msg=No AIM card found with name "${aim_name}"
    Wait For Elements State    ${elements}[0]    visible    timeout=15s

AIM card should have version count
    [Documentation]    Verifies a card contains a version count string (e.g. "N version(s)").
    [Arguments]    ${aim_name}

    ${text}=    Get AIM card text    ${aim_name}
    Should Match Regexp    ${text}    \\d+ versions?

AIM card should have tags
    [Documentation]    Verifies a card displays at least one tag.
    [Arguments]    ${aim_name}

    VAR    ${selector}    css=${AIM_CARD_SELECTOR}:has-text("${aim_name}") [class*="chip"], ${AIM_CARD_SELECTOR}:has-text("${aim_name}") [class*="tag"]
    ${count}=    Get Element Count    ${selector}
    Should Be True    ${count} > 0    msg=AIM card "${aim_name}" should display at least one tag

AIM card should have deploy button
    [Documentation]    Verifies a card has a Deploy button.
    [Arguments]    ${aim_name}

    VAR    ${selector}    css=${AIM_CARD_SELECTOR}:has-text("${aim_name}") >> css=button:has-text("Deploy")
    Wait For Elements State    ${selector}    visible    timeout=10s

Get unsupported banner count
    [Documentation]    Returns the number of unsupported banners visible in the catalog.

    ${elements}=    Get Elements    css=${UNSUPPORTED_BANNER_SELECTOR}
    ${count}=    Get Length    ${elements}
    RETURN    ${count}

AIM card should have unsupported banner
    [Documentation]    Verifies that a specific AIM card has the unsupported hardware banner.
    [Arguments]    ${aim_name}

    VAR    ${selector}    css=${AIM_CARD_SELECTOR}:has-text("${aim_name}") ${UNSUPPORTED_BANNER_SELECTOR}
    Wait For Elements State    ${selector}    visible    timeout=10s

AIM card has deployments chip should be visible
    [Documentation]    Verifies the "Has deployments" chip is visible on the given AIM card.
    [Arguments]    ${aim_name}

    VAR    ${selector}    css=${AIM_CARD_SELECTOR}:has-text("${aim_name}") ${HAS_DEPLOYMENTS_CHIP_SELECTOR}
    Wait For Elements State    ${selector}    visible    timeout=15s

AIM card has deployments chip should not be present
    [Documentation]    Verifies the "Has deployments" chip is absent from the given AIM card.
    [Arguments]    ${aim_name}

    VAR    ${card_selector}    css=${AIM_CARD_SELECTOR}:has-text("${aim_name}")
    Wait For Elements State    ${card_selector}    visible    timeout=15s
    VAR    ${selector}    css=${AIM_CARD_SELECTOR}:has-text("${aim_name}") ${HAS_DEPLOYMENTS_CHIP_SELECTOR}
    Wait For Elements State    ${selector}    detached    timeout=10s

Deploy wizard steps should be visible
    [Documentation]    Verifies the deploy wizard shows its model step and stepper labels.

    Wait For Elements State    ${DEPLOY_WIZARD_MODEL_STEP_SELECTOR}    visible    timeout=10s
    Wait For Elements State    text="Deployment"    visible    timeout=10s
    Wait For Elements State    text="Scaling"    visible    timeout=10s

Get metric selector text
    [Documentation]    Returns the currently selected metric text from the metric selector.

    VAR    ${selector}    css=${METRIC_SELECTOR}
    Wait For Elements State    ${selector}    visible    timeout=10s
    ${text}=    Get Text    ${selector}
    RETURN    ${text}

Deploy wizard should show model title
    [Documentation]    Verifies the deploy wizard shows the given model title.
    [Arguments]    ${aim_name}

    VAR    ${selector}    ${DEPLOY_WIZARD_MODEL_HEADER_SELECTOR}:has-text("${aim_name}")
    Wait For Elements State    ${selector}    visible    timeout=10s

Get deployed models row count
    [Documentation]    Returns the number of rows in the deployed models table.

    VAR    ${selector}    css=${DEPLOYED_MODELS_SELECTOR} [role="row"]
    ${elements}=    Get Elements    ${selector}
    ${count}=    Get Length    ${elements}
    RETURN    ${count}

Enter search filter text
    [Documentation]    Types text into the search filter input.
    [Arguments]    ${text}

    Fill Text    css=${SEARCH_FILTER_SELECTOR}    ${text}

Get AIM card accelerator label
    [Documentation]    Returns the accelerator label text shown in a specific AIM card's
    ...                metadata line, or an empty string when the card omits the label.
    [Arguments]    ${aim_name}

    VAR    ${selector}    css=${AIM_CARD_SELECTOR}:has-text("${aim_name}") ${ACCELERATOR_LABEL_SELECTOR}
    ${elements}=    Get Elements    ${selector}
    IF    len($elements) == 0    RETURN    ${EMPTY}
    ${text}=    Get Text    ${elements}[0]
    RETURN    ${text}

Get accelerator label match count
    [Documentation]    Returns how many catalog cards show exactly the given accelerator label.
    [Arguments]    ${label}

    ${count}=    Get Element Count    css=${ACCELERATOR_LABEL_SELECTOR}:text-is("${label}")
    RETURN    ${count}

Open accelerator filter
    [Documentation]    Opens the Accelerator multi-select filter dropdown.

    Wait For Elements State    css=${ACCELERATOR_FILTER_TRIGGER}    visible    timeout=10s
    Click    css=${ACCELERATOR_FILTER_TRIGGER}
    Wait For Elements State    css=${ACCELERATOR_FILTER_MENU}    visible    timeout=10s

Select accelerator filter option "${label}"
    [Documentation]    Selects an option (e.g. "GPU" or "CPU") inside the open Accelerator filter.

    VAR    ${selector}    css=${ACCELERATOR_FILTER_MENU} [role="menuitemcheckbox"]:has-text("${label}")
    Wait For Elements State    ${selector}    visible    timeout=10s
    Click    ${selector}

Close accelerator filter
    [Documentation]    Dismisses the Accelerator dropdown via Escape so subsequent
    ...                catalog cards are not obscured by the open menu.

    Press Keys    None    Escape

Open status filter
    [Documentation]    Opens the Statuses multi-select filter above the Deployed Models table.

    Wait For Elements State    css=${STATUS_FILTER_TRIGGER}    visible    timeout=15s
    Click    css=${STATUS_FILTER_TRIGGER}
    Wait For Elements State    css=${STATUS_FILTER_LISTBOX}    visible    timeout=10s

Get status filter option count for "${status}"
    [Documentation]    Returns how many options the open Statuses filter offers for the given
    ...                status. Matching is by substring because each option renders its label
    ...                a second time as its description.

    VAR    ${selector}    css=${STATUS_FILTER_LISTBOX} [role="option"]:has-text("${status}")
    ${count}=    Get Element Count    ${selector}
    RETURN    ${count}

Get status filter options text
    [Documentation]    Returns the full text of the open Statuses filter, so assertions about
    ...                a missing status can report what was offered instead.

    ${text}=    Get Text    css=${STATUS_FILTER_LISTBOX}
    RETURN    ${text}

Get request model card mailto href
    [Documentation]    Returns the href of the anchor inside the "Request model" card.
    ...                Waits for the card to be visible since it renders after the catalog list.

    VAR    ${card}    css=${REQUEST_MODEL_CARD_SELECTOR}
    Wait For Elements State    ${card}    visible    timeout=15s
    ${href}=    Get Attribute    css=${REQUEST_MODEL_CARD_SELECTOR} a    href
    RETURN    ${href}

Navigate to custom models page
    [Documentation]    Navigates to the Custom Models tab on the models page.
    [Arguments]    ${base_url}    ${project}

    Go To    ${base_url}/${project}${CUSTOM_MODELS_PATH}
    Wait For Elements State    css=[data-testid="custom-models"]    visible    timeout=30s

Navigate to custom profiles page
    [Documentation]    Opens the custom profiles list for a custom model by CR name.
    [Arguments]    ${base_url}    ${project}    ${model_id}

    Go To    ${base_url}/${project}${CUSTOM_MODELS_PATH}/${model_id}${CUSTOM_PROFILES_PATH_SUFFIX}
    Wait For Elements State    ${CUSTOM_PROFILES_TABLE_SELECTOR}    visible    timeout=30s

Wait for custom profiles table
    [Documentation]    Waits for the custom profiles table to render.

    Wait For Elements State    ${CUSTOM_PROFILES_TABLE_SELECTOR}    visible    timeout=30s

Get custom profile row count
    [Documentation]    Returns the number of profile rows currently shown.

    ${rows}=    Get Elements    ${CUSTOM_PROFILES_ROW_SELECTOR}
    ${count}=    Get Length    ${rows}
    RETURN    ${count}

Wait for custom profile row showing "${text}"
    [Documentation]    Waits until some profile row shows the given text.

    Wait For Elements State
    ...    ${CUSTOM_PROFILES_ROW_SELECTOR} >> text=${text}    visible    timeout=10s

Wait for custom profile row "${index}" showing "${text}"
    [Documentation]    Waits until the profile row at the given index shows the given text.

    Wait For Elements State
    ...    ${CUSTOM_PROFILES_ROW_SELECTOR} >> nth=${index} >> text=${text}    visible    timeout=10s

Wait for no custom profile row showing "${text}"
    [Documentation]    Waits until no profile row shows the given text.

    Wait For Elements State
    ...    ${CUSTOM_PROFILES_ROW_SELECTOR} >> text=${text}    detached    timeout=10s

Wait for custom profile name error
    [Documentation]    Waits for the drawer's inline name feedback to show the given text.
    [Arguments]    ${text}

    Wait For Elements State    text=${text}    visible    timeout=10s

Get custom profile summary at row "${index}"
    [Documentation]    Returns the accelerator, metric, and precision shown on the profile
    ...    row at the given index, in that order.

    ${accelerator}=    Get custom profile cell    ${index}    ${CUSTOM_PROFILES_ACCELERATOR_COLUMN}
    ${metric}=    Get custom profile cell    ${index}    ${CUSTOM_PROFILES_METRIC_COLUMN}
    ${precision}=    Get custom profile cell    ${index}    ${CUSTOM_PROFILES_PRECISION_COLUMN}
    RETURN    ${accelerator}    ${metric}    ${precision}

Get custom profile summary for "${text}"
    [Documentation]    Returns the accelerator, metric, and precision shown on the first
    ...    profile row showing the given text, in that order.

    VAR    ${row}    ${CUSTOM_PROFILES_ROW_SELECTOR}:has-text("${text}") >> nth=0
    Wait For Elements State    ${row}    visible    timeout=10s
    ${accelerator}=    Get Text    ${row} >> css=td:nth-child(${CUSTOM_PROFILES_ACCELERATOR_COLUMN})
    ${metric}=    Get Text    ${row} >> css=td:nth-child(${CUSTOM_PROFILES_METRIC_COLUMN})
    ${precision}=    Get Text    ${row} >> css=td:nth-child(${CUSTOM_PROFILES_PRECISION_COLUMN})
    RETURN    ${accelerator}    ${metric}    ${precision}

Get custom profile author at row "${index}"
    [Documentation]    Returns the author shown on the profile row at the given index.

    ${author}=    Get custom profile cell    ${index}    ${CUSTOM_PROFILES_AUTHOR_COLUMN}
    RETURN    ${author}

Get custom profile created time at row "${index}"
    [Documentation]    Returns the creation time shown on the profile row at the given index.

    ${created}=    Get custom profile cell    ${index}    ${CUSTOM_PROFILES_CREATED_COLUMN}
    RETURN    ${created}

Get custom profile cell
    [Documentation]    Returns the text of one profile row cell, addressed by row index and
    ...    1-based column position.
    [Arguments]    ${index}    ${column}

    VAR    ${cell}    ${CUSTOM_PROFILES_ROW_SELECTOR} >> nth=${index} >> css=td:nth-child(${column})
    Wait For Elements State    ${cell}    visible    timeout=10s
    ${text}=    Get Text    ${cell}
    RETURN    ${text}

Click actions menu on custom profile row showing "${text}"
    [Documentation]    Opens the row actions menu on the first profile row showing the text.

    VAR    ${row}    ${CUSTOM_PROFILES_ROW_SELECTOR}:has-text("${text}") >> nth=0
    Wait For Elements State    ${row}    visible    timeout=30s
    Click    ${row} >> css=button[aria-label="Actions"]

Click actions menu on custom profile row
    [Documentation]    Opens the row actions menu on the profile row at the given index.
    [Arguments]    ${index}

    Wait For Elements State    ${CUSTOM_PROFILES_ROW_SELECTOR}    visible    timeout=30s
    ${buttons}=    Get Elements    ${CUSTOM_PROFILES_ROW_SELECTOR} >> css=button[aria-label="Actions"]
    Should Be True    len($buttons) > ${index}    msg=Expected a profile row at index ${index}
    Click    ${buttons}[${index}]

Click edit action in custom profile row menu
    [Documentation]    Clicks the "Edit" action in the open profile row actions menu.

    Wait For Elements State
    ...    ${CUSTOM_PROFILE_EDIT_MENU_ITEM_SELECTOR}    visible    timeout=10s
    Click    ${CUSTOM_PROFILE_EDIT_MENU_ITEM_SELECTOR}

Click deploy action in custom profile row menu
    [Documentation]    Clicks the "Deploy with this profile" action in the open row menu.

    Wait For Elements State
    ...    ${CUSTOM_PROFILE_DEPLOY_MENU_ITEM_SELECTOR}    visible    timeout=10s
    Click    ${CUSTOM_PROFILE_DEPLOY_MENU_ITEM_SELECTOR}

Get custom profile delete action disabled state
    [Documentation]    Returns the open row action menu's Delete item aria-disabled value.

    Wait For Elements State
    ...    ${CUSTOM_PROFILE_DELETE_MENU_ITEM_SELECTOR}    visible    timeout=10s
    ${state}=    Get Attribute
    ...    ${CUSTOM_PROFILE_DELETE_MENU_ITEM_SELECTOR}    aria-disabled
    RETURN    ${state}

Click back from custom profiles page
    [Documentation]    Clicks the back control in the custom profiles page header.

    Wait For Elements State    ${CUSTOM_PROFILES_BACK_SELECTOR}    visible    timeout=10s
    Click    ${CUSTOM_PROFILES_BACK_SELECTOR}

Click new profile on custom profiles page
    [Documentation]    Opens the add profile drawer from the page header action.

    Wait For Elements State    ${CUSTOM_PROFILES_NEW_SELECTOR}    visible    timeout=10s
    Click    ${CUSTOM_PROFILES_NEW_SELECTOR}

Wait for custom profile drawer
    [Documentation]    Waits for the add/edit profile drawer to render its heading.

    Wait For Elements State
    ...    ${CUSTOM_PROFILE_DRAWER_HEADING_SELECTOR}    visible    timeout=30s

Fill custom profile name
    [Documentation]    Replaces the profile name in the add/edit profile drawer.
    [Arguments]    ${name}

    Wait For Elements State    ${CUSTOM_PROFILE_DRAWER_NAME_SELECTOR}    visible    timeout=10s
    Fill Text    ${CUSTOM_PROFILE_DRAWER_NAME_SELECTOR}    ${name}

Get custom profile name
    [Documentation]    Returns the profile name currently shown in the drawer.

    Wait For Elements State    ${CUSTOM_PROFILE_DRAWER_NAME_SELECTOR}    visible    timeout=10s
    ${value}=    Get Property    ${CUSTOM_PROFILE_DRAWER_NAME_SELECTOR}    value
    RETURN    ${value}

Fill custom profile engine arguments
    [Documentation]    Replaces the engine arguments YAML in the drawer.
    [Arguments]    ${yaml}

    Wait For Elements State
    ...    ${CUSTOM_PROFILE_DRAWER_ENGINE_ARGS_SELECTOR}    visible    timeout=10s
    Fill Text    ${CUSTOM_PROFILE_DRAWER_ENGINE_ARGS_SELECTOR}    ${yaml}

Save custom profile drawer
    [Documentation]    Submits the add/edit profile drawer.

    Wait For Elements State    ${CUSTOM_PROFILE_DRAWER_SAVE_SELECTOR}    visible    timeout=10s
    Click    ${CUSTOM_PROFILE_DRAWER_SAVE_SELECTOR}

Save and deploy custom profile drawer
    [Documentation]    Submits the add profile drawer through the action that carries the
    ...                saved profile into a deploy.

    Wait For Elements State
    ...    ${CUSTOM_PROFILE_DRAWER_SAVE_DEPLOY_SELECTOR}    visible    timeout=10s
    Click    ${CUSTOM_PROFILE_DRAWER_SAVE_DEPLOY_SELECTOR}

Cancel custom profile drawer
    [Documentation]    Dismisses the add/edit profile drawer without saving.

    Wait For Elements State    ${CUSTOM_PROFILE_DRAWER_CANCEL_SELECTOR}    visible    timeout=10s
    Click    ${CUSTOM_PROFILE_DRAWER_CANCEL_SELECTOR}

Navigate to custom model edit page
    [Documentation]    Opens the full-page edit wizard for a custom model by CR name.
    ...                The shell renders immediately; the model payload loads asynchronously.
    [Arguments]    ${base_url}    ${project}    ${model_id}

    Go To    ${base_url}/${project}/models/custom-models/${model_id}/edit
    Wait For Elements State    ${IMPORT_WIZARD_PAGE_SELECTOR}    visible    timeout=30s

Wait for custom model edit load error
    [Documentation]    Waits until the edit wizard shows the load-failure affordance
    ...                (missing model, wrong project, or upstream error).

    Wait For Elements State    ${CUSTOM_MODEL_EDIT_LOAD_ERROR_SELECTOR}    visible    timeout=45s

Custom model edit page should show edit title
    [Documentation]    Verifies the edit-mode page chrome (distinct from import).

    Wait For Elements State    ${IMPORT_WIZARD_PAGE_SELECTOR}    visible    timeout=15s
    ${text}=    Get Text    ${IMPORT_WIZARD_PAGE_SELECTOR}
    Should Contain    ${text}    Edit model

Navigate to fine-tune models page
    [Documentation]    Navigates to the Fine-tune Models tab on the models page.
    ...                Fine-tune flows live on this tab, split from the
    ...                previous Custom Models tab into Custom Models (imported
    ...                models) and Fine-tune Models (the fine-tune table).
    [Arguments]    ${base_url}    ${project}

    Go To    ${base_url}/${project}${FINE_TUNE_MODELS_PATH}
    Wait For Elements State    css=${FINE_TUNE_MODELS_SELECTOR}    visible    timeout=30s

Wait for fine-tune models page
    [Documentation]    Waits for the Fine-tune models page to become visible.

    Wait For Elements State    css=${FINE_TUNE_MODELS_SELECTOR}    visible    timeout=30s

Open finetune wizard
    [Documentation]    Clicks the Fine-tune button on the Fine-tune Models tab to open the wizard.
    ...                Waits for the button to be enabled since workload data loads asynchronously
    ...                and the button is disabled until the initial load completes.

    Wait For Elements State    ${FINETUNE_BTN_SELECTOR}    visible    timeout=15s
    Wait For Elements State    ${FINETUNE_BTN_SELECTOR}    enabled    timeout=15s
    Click    ${FINETUNE_BTN_SELECTOR}
    Wait For Elements State    ${BASE_MODEL_SELECT_SELECTOR}    visible    timeout=15s

Click base model select
    [Documentation]    Opens the base model dropdown by clicking the select trigger.

    Click    ${BASE_MODEL_SELECT_SELECTOR}

Get base model option count
    [Documentation]    Returns the number of options in the open base model dropdown.

    ${elements}=    Get Elements    ${BASE_MODEL_OPTION_SELECTOR}
    ${count}=    Get Length    ${elements}
    RETURN    ${count}

Get base model option text
    [Documentation]    Returns the full text content of a base model option by index.
    [Arguments]    ${index}=0

    ${elements}=    Get Elements    ${BASE_MODEL_OPTION_SELECTOR}
    ${text}=    Get Text    ${elements}[${index}]
    RETURN    ${text}

Base model select should show empty state
    [Documentation]    Verifies the base model select shows the no-compatible-recipes placeholder.
    ...                Uses polling since the message is populated asynchronously.

    Wait For Elements State    ${BASE_MODEL_SELECT_SELECTOR}    visible    timeout=10s
    Wait Until Keyword Succeeds    10s    500ms    Base model empty state text should be shown

Base model empty state text should be shown
    ${text}=    Get Text    ${BASE_MODEL_SELECT_SELECTOR}
    Should Contain    ${text}    ${BASE_MODEL_EMPTY_MSG}

Base model options should be non-empty
    [Documentation]    Verifies at least one option is visible in the open base model dropdown.

    ${count}=    Get base model option count
    Should Be True    ${count} > 0    msg=Expected at least one fine-tuning recipe option

Click first base model option
    [Documentation]    Selects the first option in the open base model dropdown.

    ${elements}=    Get Elements    ${BASE_MODEL_OPTION_SELECTOR}
    Click    ${elements}[0]

Click fine-tuning wizard next button
    [Documentation]    Advances to the next step of the fine-tuning wizard.

    Wait For Elements State    ${FINETUNE_WIZARD_NEXT_BTN}    enabled    timeout=10s
    Click    ${FINETUNE_WIZARD_NEXT_BTN}

Click fine-tuning wizard back button
    [Documentation]    Returns to the previous step of the fine-tuning wizard.

    Wait For Elements State    ${FINETUNE_WIZARD_BACK_BTN}    enabled    timeout=10s
    Click    ${FINETUNE_WIZARD_BACK_BTN}

Fine-tuning wizard display name should be
    [Documentation]    Verifies the fine-tuning wizard still shows the entered model name.
    [Arguments]    ${name}

    ${value}=    Get Property    ${FINETUNE_DISPLAY_NAME_INPUT}    value
    Should Be Equal    ${value}    ${name}

Fine-tuning wizard next button should be disabled
    [Documentation]    Verifies the current wizard step cannot be completed.

    Wait For Elements State    ${FINETUNE_WIZARD_NEXT_BTN}    disabled    timeout=10s

Select first training dataset
    [Documentation]    Selects the first available dataset in the Training step.

    Wait For Elements State    ${DATASET_SELECTOR_TABLE}    visible    timeout=10s
    Wait For Elements State    ${DATASET_ROW_CHECKBOX_SELECTOR}    visible    timeout=10s
    Click    ${DATASET_ROW_CHECKBOX_SELECTOR} >> nth=0

Select training dataset by index
    [Documentation]    Selects an available dataset by its zero-based row index.
    [Arguments]    ${index}

    VAR    ${selector}    ${DATASET_ROW_CHECKBOX_SELECTOR} >> nth=${index}
    Wait For Elements State    ${selector}    visible    timeout=10s
    Click    ${selector}

Select all training datasets
    [Documentation]    Selects every dataset available in the Training step.

    Wait For Elements State    ${DATASET_SELECT_ALL_SELECTOR}    visible    timeout=10s
    Click    ${DATASET_SELECT_ALL_SELECTOR}

Dataset selector should show file sizes
    [Documentation]    Verifies the dataset selector shows a formatted size for available data.

    Wait For Elements State    ${DATASET_SIZE_HEADER_SELECTOR}    visible    timeout=10s
    Wait For Elements State    ${DATASET_SIZE_CELL_SELECTOR}    visible    timeout=10s
    ${size}=    Get Text    ${DATASET_SIZE_CELL_SELECTOR} >> nth=0
    Should Match Regexp    ${size}    ^[0-9]+(?:\\.[0-9]{2})? (?:B|KB|MB|GB|TB|PB)$

Select LoRA fine-tuning type
    [Documentation]    Selects LoRA adapter output in the Training step.
    Wait For Elements State    ${LORA_TYPE_RADIO_SELECTOR}    enabled    timeout=10s
    Click    ${LORA_TYPE_RADIO_SELECTOR}

Get LoRA fine-tuning type enabled state
    [Documentation]    Returns whether the LoRA output option can be chosen in the Training step.

    ${enabled}=    Get Element States    ${LORA_TYPE_RADIO_SELECTOR}    then    bool(value & enabled)
    RETURN    ${enabled}

Get LoRA fine-tuning type checked state
    [Documentation]    Returns whether LoRA output is currently the chosen option.

    ${checked}=    Get Element States    ${LORA_TYPE_RADIO_SELECTOR}    then    bool(value & checked)
    RETURN    ${checked}

Get fine-tuning type options text
    [Documentation]    Returns everything the Training step's output options show the user,
    ...                including the per-option explanations rendered beneath their labels.

    Wait For Elements State    ${FINETUNE_TYPE_SELECTOR}    visible    timeout=15s
    ${text}=    Get Text    ${FINETUNE_TYPE_SELECTOR}
    RETURN    ${text}

Get chosen fine-tuning type name
    [Documentation]    Returns the label of the output option currently chosen.

    ${name}=    Get Attribute    ${FINETUNE_TYPE_SELECTOR} >> input:checked    value
    RETURN    ${name}

Enable hyper-parameter customization
    [Documentation]    Enables custom values in the Hyper-parameters step.

    Wait For Elements State    ${CUSTOMIZE_HYPERPARAMETERS_TOGGLE}    visible    timeout=10s
    Click    ${CUSTOMIZE_HYPERPARAMETERS_TOGGLE}
    Wait For Elements State    ${BATCH_SIZE_INPUT_SELECTOR}    attached    timeout=10s

Get hyperparameter input placeholders
    [Documentation]    Returns the epoch and learning-rate input placeholders.

    ${epochs}=    Get Attribute    ${EPOCHS_INPUT_SELECTOR}    placeholder
    ${learning_rate}=    Get Attribute    ${LEARNING_RATE_INPUT_SELECTOR}    placeholder
    RETURN    ${epochs}    ${learning_rate}

Fill LoRA rank
    [Documentation]    Fills the LoRA rank input.
    [Arguments]    ${rank}
    Fill Text    ${LORA_RANK_INPUT_SELECTOR}    ${rank}

Fill LoRA alpha
    [Documentation]    Fills the LoRA alpha input.
    [Arguments]    ${alpha}
    Fill Text    ${LORA_ALPHA_INPUT_SELECTOR}    ${alpha}

Fill LoRA dropout
    [Documentation]    Fills the LoRA dropout input.
    [Arguments]    ${dropout}
    Fill Text    ${LORA_DROPOUT_INPUT_SELECTOR}    ${dropout}

Fill learning rate
    [Documentation]    Fills the learning-rate input.
    [Arguments]    ${learning_rate}
    Fill Text    ${LEARNING_RATE_INPUT_SELECTOR}    ${learning_rate}

Get hyperparameters summary text
    [Documentation]    Returns the collapsed hyperparameters summary on the confirmation step.

    Get Text    ${HYPERPARAMETERS_SUMMARY_SELECTOR}

Click batch size increment button
    [Documentation]    Clicks the + stepper button on the batch size NumberInput.
    ...                The button steps the value by the recipe's GPU count (the
    ...                input's step prop), and clamps the result to >= the recipe's
    ...                GPU count (the input's minValue prop).

    Click    ${BATCH_SIZE_INCREMENT_SELECTOR}

Get batch size value
    [Documentation]    Returns the current value displayed in the batch size input as an
    ...                integer, or 0 when the input is empty. Reads the DOM `value`
    ...                property (not the `value` attribute, which only reflects the
    ...                initial value) so it sees user-typed and stepper-applied changes.

    ${raw}=    Get Property    ${BATCH_SIZE_INPUT_SELECTOR}    value
    IF    not $raw    RETURN    ${0}
    ${value}=    Convert To Integer    ${raw}
    RETURN    ${value}

Batch size input should be enabled
    [Documentation]    Waits for the customized batch size input to be interactive.

    Wait For Elements State    ${BATCH_SIZE_INPUT_SELECTOR}    enabled    timeout=5s

Focus and blur batch size input
    [Documentation]    Focuses the batch size input, then moves focus away without typing
    ...                anything. Reproduces the exact interaction (tab in, tab out) that
    ...                exposed the empty-value sentinel regression — as opposed to simply
    ...                never mounting/touching the field.

    Press Keys    ${BATCH_SIZE_INPUT_SELECTOR}    Tab

Fine-tuning wizard should be closed
    [Documentation]    Verifies the fine-tuning wizard has been dismissed after submission.

    Wait For Elements State    ${BASE_MODEL_SELECT_SELECTOR}    detached    timeout=10s

Click import model button
    [Documentation]    Clicks the "Import model" toolbar button on the custom models tab.
    ...                Waits for the button to be enabled (it disables while the models list
    ...                loads).

    Wait For Elements State    ${IMPORT_MODEL_BUTTON_SELECTOR}    visible    timeout=15s
    Wait For Elements State    ${IMPORT_MODEL_BUTTON_SELECTOR}    enabled    timeout=15s
    Click    ${IMPORT_MODEL_BUTTON_SELECTOR}

Click actions menu on first custom model card
    [Documentation]    Opens the actions menu on the first visible custom model card.
    ...                Waits for at least one card and an enabled actions button.

    Wait For Elements State    ${CUSTOM_MODEL_CARD_SELECTOR}    visible    timeout=30s
    ${buttons}=    Get Elements    ${CUSTOM_MODEL_CARD_SELECTOR} >> ${CUSTOM_MODEL_CARD_ACTIONS_SELECTOR}
    Should Be True    len($buttons) > 0    msg=Expected at least one custom model card actions button
    Wait For Elements State    ${buttons}[0]    enabled    timeout=10s
    Click    ${buttons}[0]

Click make copy action in custom model card menu
    [Documentation]    Clicks the "Make a copy" action in the open custom model card menu.

    Wait For Elements State    ${CUSTOM_MODEL_COPY_MENU_ITEM_SELECTOR}    visible    timeout=10s
    Click    ${CUSTOM_MODEL_COPY_MENU_ITEM_SELECTOR}

Click profiles action in custom model card menu
    [Documentation]    Clicks the "Profiles" action in the open custom model card menu,
    ...                which navigates to the custom profiles list for that model.

    Wait For Elements State    ${CUSTOM_MODEL_PROFILES_MENU_ITEM_SELECTOR}    visible    timeout=10s
    Click    ${CUSTOM_MODEL_PROFILES_MENU_ITEM_SELECTOR}

Click model settings action in custom model card menu
    [Documentation]    Clicks the "Model settings" action in the open custom model card menu,
    ...                which navigates to the full-page edit wizard for that model.

    Wait For Elements State    ${CUSTOM_MODEL_SETTINGS_MENU_ITEM_SELECTOR}    visible    timeout=10s
    Click    ${CUSTOM_MODEL_SETTINGS_MENU_ITEM_SELECTOR}

Click delete action in custom model card menu
    [Documentation]    Clicks the "Delete" action in the open custom model card menu.

    Wait For Elements State    ${CUSTOM_MODEL_DELETE_MENU_ITEM_SELECTOR}    visible    timeout=10s
    Click    ${CUSTOM_MODEL_DELETE_MENU_ITEM_SELECTOR}

Wait for custom model delete confirmation modal
    [Documentation]    Waits for the delete confirmation modal to appear after triggering delete.

    Wait For Elements State    ${CUSTOM_MODEL_DELETE_MODAL_SELECTOR}    visible    timeout=10s

Confirm model deletion in modal
    [Documentation]    Clicks the confirm button inside the delete confirmation modal.

    Click    css=${CUSTOM_MODEL_DELETE_CONFIRM_BUTTON_SELECTOR}

Close delete confirmation modal
    [Documentation]    Clicks the "Close" button to dismiss the delete confirmation modal
    ...                without triggering deletion.

    Wait For Elements State    ${CUSTOM_MODEL_DELETE_CLOSE_BUTTON_SELECTOR}    visible    timeout=10s
    Click    ${CUSTOM_MODEL_DELETE_CLOSE_BUTTON_SELECTOR}

Wait for delete success toast
    [Documentation]    Waits for the "Model successfully deleted." success toast to appear
    ...                after a successful deletion.

    Wait For Elements State    text=Model successfully deleted.    visible    timeout=30s

Custom model card should be absent
    [Documentation]    Asserts no custom model cards are visible. Used as a single-poll
    ...                check inside a Wait Until Keyword Succeeds wrapper.

    ${cards}=    Get Elements    ${CUSTOM_MODEL_CARD_SELECTOR}
    ${count}=    Get Length    ${cards}
    Should Be Equal As Integers    ${count}    0
    ...    msg=Expected no custom model cards but found ${count}

Click import wizard next on source step in edit mode
    [Documentation]    Waits for the edit wizard's source step to finish loading and
    ...                clicks Next to advance to the information step. Edit mode mounts
    ...                the wizard from a navigation event, so a visibility wait is needed
    ...                before the source-step Next button is interactable.

    Wait For Elements State    ${IMPORT_WIZARD_NEXT_SOURCE_SELECTOR}    visible    timeout=30s
    Wait For Elements State    ${IMPORT_WIZARD_NEXT_SOURCE_SELECTOR}    enabled    timeout=15s
    Click    ${IMPORT_WIZARD_NEXT_SOURCE_SELECTOR}

Get custom model card count
    [Documentation]    Returns the number of custom model cards currently shown.

    ${cards}=    Get Elements    ${CUSTOM_MODEL_CARD_SELECTOR}
    ${count}=    Get Length    ${cards}
    RETURN    ${count}

Wait for import wizard page
    [Documentation]    Waits for the custom model import wizard page to be visible.

    Wait For Elements State    ${IMPORT_WIZARD_PAGE_SELECTOR}    visible    timeout=15s

Click import wizard next on source step
    [Documentation]    Clicks the "Preview model" button on the source step of the wizard.

    Click    ${IMPORT_WIZARD_NEXT_SOURCE_SELECTOR}

Click import wizard next on information step
    [Documentation]    Clicks the "Next" button on the information step to advance to the
    ...                runtime profile step. Waits for the button to be enabled since the
    ...                information step only mounts once the wizard advances from step 1.

    Wait For Elements State    ${IMPORT_WIZARD_NEXT_INFORMATION_SELECTOR}    visible    timeout=30s
    Wait For Elements State    ${IMPORT_WIZARD_NEXT_INFORMATION_SELECTOR}    enabled    timeout=15s
    Click    ${IMPORT_WIZARD_NEXT_INFORMATION_SELECTOR}

Click import wizard submit
    [Documentation]    Clicks the "Import model" submit button on the runtime profile step.
    ...                Waits for the button to be enabled since the step loads asynchronously.

    Wait For Elements State    ${IMPORT_WIZARD_SUBMIT_SELECTOR}    visible    timeout=30s
    Wait For Elements State    ${IMPORT_WIZARD_SUBMIT_SELECTOR}    enabled    timeout=15s
    Click    ${IMPORT_WIZARD_SUBMIT_SELECTOR}

Custom model card with ready status should be visible
    [Documentation]    Asserts that at least one custom model card is in a
    ...                deployable ("Ready") state by checking for an enabled
    ...                Deploy button. Used as a single-poll check inside a
    ...                Wait Until Keyword Succeeds wrapper.

    ${ready}=    Get Elements    ${CUSTOM_MODEL_CARD_READY_SELECTOR}
    Should Be True    len($ready) > 0
    ...    msg=Expected at least one custom model card with enabled Deploy button

Click import wizard cancel
    [Documentation]    Clicks the "Cancel" button on the source step of the wizard.

    Click    ${IMPORT_WIZARD_CANCEL_SELECTOR}

Click import wizard header back
    [Documentation]    Clicks the header back link that returns to the custom models list.

    Click    ${IMPORT_WIZARD_HEADER_BACK_SELECTOR}

Fill import wizard source
    [Documentation]    Types into the wizard's model source input.
    [Arguments]    ${value}

    Fill Text    ${IMPORT_WIZARD_SOURCE_INPUT_SELECTOR}    ${value}

Open project Hugging Face token dropdown
    [Documentation]    Opens the Hugging Face token selector on the custom model import source step.

    Wait For Elements State    ${PROJECT_HF_TOKEN_SELECTOR}    visible    timeout=15s
    Click    ${PROJECT_HF_TOKEN_SELECTOR}

Click Hugging Face token option labeled
    [Documentation]    Selects an existing Hugging Face token in the open listbox by its visible label text.
    [Arguments]    ${label}

    Wait For Elements State    css=[role="listbox"]    visible    timeout=15s
    Click    css=[role="listbox"] [role="option"]:has-text("${label}")

Click Hugging Face token add new button
    [Documentation]    Clicks the "Add new" affordance at the bottom of the open Hugging Face
    ...                token dropdown, which opens the inline create-token popover.

    Wait For Elements State    ${HF_TOKEN_ADD_NEW_SELECTOR}    visible    timeout=10s
    Click    ${HF_TOKEN_ADD_NEW_SELECTOR}

Fill Hugging Face token dialog fields
    [Documentation]    Fills the create-token popover's display-name and token inputs.
    [Arguments]    ${name}    ${token}

    Wait For Elements State    ${HF_TOKEN_DIALOG_NAME_SELECTOR}    visible    timeout=10s
    Fill Text    ${HF_TOKEN_DIALOG_NAME_SELECTOR}    ${name}
    Fill Text    ${HF_TOKEN_DIALOG_TOKEN_SELECTOR}    ${token}

Click Hugging Face token dialog submit button
    [Documentation]    Submits the create-token popover form.

    Wait For Elements State    ${HF_TOKEN_DIALOG_SUBMIT_SELECTOR}    enabled    timeout=10s
    Click    ${HF_TOKEN_DIALOG_SUBMIT_SELECTOR}

Select import wizard source type
    [Documentation]    Picks a source family on the wizard's source step. Accepts the
    ...                family key used by the radio testids: huggingFace or s3.
    [Arguments]    ${source_type}

    Wait For Elements State    ${IMPORT_WIZARD_SOURCE_TYPE_SELECTOR}    visible    timeout=15s
    Click    css=[data-testid="custom-model-import-source-type-${source_type}"]

Open project S3 configuration dropdown
    [Documentation]    Opens the S3 configuration selector on the custom model import source
    ...                step. Waits for it to become enabled — the selector stays disabled
    ...                until the project's storages have loaded.

    Wait For Elements State    ${PROJECT_S3_STORAGE_SELECTOR}    visible    timeout=15s
    Wait For Elements State    ${PROJECT_S3_STORAGE_TRIGGER_SELECTOR}    enabled    timeout=30s
    Click    ${PROJECT_S3_STORAGE_TRIGGER_SELECTOR}

Click S3 configuration option labeled
    [Documentation]    Selects an existing S3 configuration in the open listbox by its name.
    [Arguments]    ${label}

    Wait For Elements State    css=[role="listbox"]    visible    timeout=15s
    Click    css=[role="listbox"] [role="option"]:has-text("${label}")

Open S3 configuration create dialog
    [Documentation]    Clicks the "Add new S3 configuration" affordance at the bottom of the
    ...                open S3 configuration dropdown and waits for the create dialog to render.

    Wait For Elements State    css=[data-testid="s3-storage-selector-add-new"]    visible    timeout=15s
    Click    css=[data-testid="s3-storage-selector-add-new"]
    Wait For Elements State    css=[data-testid="s3-storage-selector-dialog-name"]    visible    timeout=15s

Fill S3 configuration dialog
    [Documentation]    Fills the create dialog's name, bucket URL, and region inputs.
    [Arguments]    ${name}    ${bucket_url}    ${region}

    Fill Text    css=[data-testid="s3-storage-selector-dialog-name"]    ${name}
    Fill Text    css=[data-testid="s3-storage-selector-dialog-bucket-url"]    ${bucket_url}
    Fill Text    css=[data-testid="s3-storage-selector-dialog-region"]    ${region}

Select S3 configuration dialog secret labeled
    [Documentation]    Picks a backing S3 secret in the create dialog's secret dropdown by label.
    [Arguments]    ${label}

    Wait For Elements State    ${S3_STORAGE_DIALOG_SECRET_SELECTOR}    enabled    timeout=30s
    Click    ${S3_STORAGE_DIALOG_SECRET_SELECTOR}
    Wait For Elements State    css=[role="listbox"]    visible    timeout=15s
    Click    css=[role="listbox"] [role="option"]:has-text("${label}")

Submit S3 configuration create dialog
    [Documentation]    Clicks the create dialog's submit button, saving the new S3 configuration.

    Click    css=[data-testid="s3-storage-selector-dialog-submit"]

Import wizard S3 configuration selector should be visible
    [Documentation]    Verifies the S3 configuration selector is mounted on the source step.

    Wait For Elements State    ${PROJECT_S3_STORAGE_SELECTOR}    visible    timeout=15s

Import wizard S3 configuration selector should be absent
    [Documentation]    Verifies the S3 configuration selector is not mounted on the source step.

    Wait For Elements State    ${PROJECT_S3_STORAGE_SELECTOR}    detached    timeout=10s

Import wizard Hugging Face token selector should be visible
    [Documentation]    Verifies the Hugging Face token selector is mounted on the source step.

    Wait For Elements State    ${PROJECT_HF_TOKEN_SELECTOR}    visible    timeout=15s

Import wizard Hugging Face token selector should be absent
    [Documentation]    Verifies the Hugging Face token selector is not mounted on the source step.

    Wait For Elements State    ${PROJECT_HF_TOKEN_SELECTOR}    detached    timeout=10s

Import wizard source input should be read only
    [Documentation]    Verifies the source input cannot be edited — the wizard renders it
    ...                read-only once a model has been onboarded from it.

    Wait For Elements State    ${IMPORT_WIZARD_SOURCE_INPUT_SELECTOR}    readonly    timeout=15s

Import wizard source type field should read
    [Documentation]    Reads the value shown in the source-type field. In edit mode the field
    ...                is a read-only input rather than the radio group.
    [Arguments]    ${expected}

    Wait For Elements State    ${IMPORT_WIZARD_SOURCE_TYPE_FIELD_SELECTOR}    visible    timeout=30s
    ${value}=    Get Property    ${IMPORT_WIZARD_SOURCE_TYPE_FIELD_SELECTOR}    value
    Should Be Equal    ${value}    ${expected}

Import wizard information step should be visible
    [Documentation]    Verifies the wizard is on the model information step — its display-name
    ...                input only mounts once the wizard has advanced past the source step.

    Wait For Elements State    ${IMPORT_WIZARD_DISPLAY_NAME_SELECTOR}    visible    timeout=60s

Import wizard preview warnings should be visible
    [Documentation]    Verifies the information step surfaces the preview's warnings Alert.

    Wait For Elements State    ${IMPORT_WIZARD_PREVIEW_WARNINGS_SELECTOR}    visible    timeout=30s

Import wizard should show stepper labels
    [Documentation]    Verifies the wizard renders the three step labels: source,
    ...                information, and runtime.

    Wait For Elements State    ${IMPORT_WIZARD_PAGE_SELECTOR}    visible    timeout=15s
    ${page_text}=    Get Text    ${IMPORT_WIZARD_PAGE_SELECTOR}
    Should Contain    ${page_text}    Model source
    Should Contain    ${page_text}    Model information
    Should Contain    ${page_text}    Runtime profile

Import wizard source input should be visible
    [Documentation]    Verifies the wizard's source input is currently visible —
    ...                used to assert that the wizard has not advanced past the
    ...                source step (e.g. after a failed validation).

    Wait For Elements State    ${IMPORT_WIZARD_SOURCE_INPUT_SELECTOR}    visible    timeout=10s

Fill import wizard display name
    [Documentation]    Types into the information step's display-name input,
    ...                replacing any preview-seeded value. Waits for the input
    ...                first since it only mounts once the wizard reaches step 2.
    [Arguments]    ${value}

    Wait For Elements State    ${IMPORT_WIZARD_DISPLAY_NAME_SELECTOR}    visible    timeout=30s
    Fill Text    ${IMPORT_WIZARD_DISPLAY_NAME_SELECTOR}    ${value}

Import wizard duplicate name warning should be visible
    [Documentation]    Verifies the duplicate display-name warning Alert is shown
    ...                on the information step.

    Wait For Elements State    ${IMPORT_WIZARD_DUP_WARNING_SELECTOR}    visible    timeout=10s

Import wizard duplicate name warning should be hidden
    [Documentation]    Verifies the duplicate display-name warning Alert is not
    ...                present (the entered name does not collide).

    Wait For Elements State    ${IMPORT_WIZARD_DUP_WARNING_SELECTOR}    detached    timeout=10s

Custom models tab should be visible
    [Documentation]    Verifies the Custom Models tab content is currently visible.
    ...                Distinct from `Navigate to custom models page`: this only
    ...                asserts visibility without performing navigation, suitable
    ...                for post-action checks (e.g. after canceling the import
    ...                wizard).

    Wait For Elements State    css=[data-testid="custom-models"]    visible    timeout=15s

Import model button should be absent
    [Documentation]    Verifies the "Import model" toolbar button is not present
    ...                on the current tab. The button belongs on the
    ...                Custom Models tab only; it must not appear on the
    ...                Fine-tune Models tab.

    Wait For Elements State    ${IMPORT_MODEL_BUTTON_SELECTOR}    detached    timeout=10s

# =============================================================================
# Runtime profile wizard step page keywords
# =============================================================================

Wait for runtime profile step
    [Documentation]    Waits for the runtime profile step to render its engine-arguments
    ...                YAML field — the step's most stable, catalog-independent control.

    Wait For Elements State    ${RUNTIME_ENGINE_ARGS_YAML_SELECTOR}    visible    timeout=15s

Runtime profile step should be editable
    [Documentation]    Verifies the runtime profile fields are editable — the disabled
    ...                notice (shown when the profile is not yet ready) must be absent.

    Wait For Elements State    ${RUNTIME_ENGINE_ARGS_YAML_SELECTOR}    visible    timeout=15s
    Wait For Elements State    ${RUNTIME_DISABLED_NOTICE_SELECTOR}    detached    timeout=5s

Fill runtime profile engine arguments
    [Documentation]    Replaces the engine-arguments YAML textarea content.
    [Arguments]    ${yaml}

    Wait For Elements State    ${RUNTIME_ENGINE_ARGS_YAML_SELECTOR}    visible    timeout=15s
    Fill Text    ${RUNTIME_ENGINE_ARGS_YAML_SELECTOR}    ${yaml}

Fill runtime profile environment variables
    [Documentation]    Replaces the environment-variables YAML textarea content.
    [Arguments]    ${yaml}

    Wait For Elements State    ${RUNTIME_ENV_VARS_YAML_SELECTOR}    visible    timeout=15s
    Fill Text    ${RUNTIME_ENV_VARS_YAML_SELECTOR}    ${yaml}

Select runtime profile precision
    [Documentation]    Picks a precision value in the import/edit wizard runtime step's
    ...                precision select.
    [Arguments]    ${precision}

    Wait For Elements State    ${RUNTIME_MODEL_PRECISION_SELECTOR}    visible    timeout=15s
    Click    ${RUNTIME_MODEL_PRECISION_SELECTOR}
    Wait For Elements State    css=[role="listbox"]    visible    timeout=10s
    Click    css=[role="listbox"] [role="option"]:has-text("${precision}")

Select the last offered runtime precision
    [Documentation]    Opens the precision select and picks the last option offered. The
    ...                select lists only precisions reachable from the current
    ...                accelerator/count selection (the base's emitted combinations), so any
    ...                offered value resolves to a single base profile and the save succeeds.
    ...                Returns the chosen precision text for the caller to assert on.

    Wait For Elements State    ${RUNTIME_MODEL_PRECISION_SELECTOR}    visible    timeout=15s
    Click    ${RUNTIME_MODEL_PRECISION_SELECTOR}
    Wait For Elements State    css=[role="listbox"] [role="option"]    visible    timeout=10s
    ${chosen}=    Get Text    css=[role="listbox"] [role="option"] >> nth=-1
    Click    css=[role="listbox"] [role="option"] >> nth=-1
    RETURN    ${chosen}

Open runtime profile container image selector
    [Documentation]    Opens the runtime step's container-image family dropdown.

    Wait For Elements State    ${RUNTIME_CONTAINER_IMAGE_SELECTOR}    visible    timeout=15s
    Click    ${RUNTIME_CONTAINER_IMAGE_SELECTOR}
    Wait For Elements State    css=[role="listbox"]    visible    timeout=10s

Select runtime profile container image family
    [Documentation]    Selects a container-image family in the runtime step.
    [Arguments]    ${family_label}

    Open runtime profile container image selector
    Click    css=[role="listbox"] [role="option"]:has-text("${family_label}")

Open runtime profile container version selector
    [Documentation]    Opens the runtime step's container-version dropdown.

    Wait For Elements State    ${RUNTIME_CONTAINER_VERSION_SELECTOR}    visible    timeout=15s
    Wait For Elements State    ${RUNTIME_CONTAINER_VERSION_SELECTOR}    enabled    timeout=15s
    Click    ${RUNTIME_CONTAINER_VERSION_SELECTOR}
    Wait For Elements State    css=[role="listbox"]    visible    timeout=10s

Get open select option count
    [Documentation]    Returns the number of options in the currently open select listbox.

    ${options}=    Get Elements    ${SELECT_LISTBOX_OPTIONS_SELECTOR}
    ${count}=    Get Length    ${options}
    RETURN    ${count}

Get open select option text
    [Documentation]    Returns the option label text at the provided index from the open listbox.
    [Arguments]    ${index}

    VAR    ${selector}    ${SELECT_LISTBOX_OPTIONS_SELECTOR} >> nth=${index}
    ${text}=    Get Text    ${selector}
    RETURN    ${text}

Get runtime profile selected container version text
    [Documentation]    Returns the currently selected text shown by the runtime
    ...                container-version select trigger.

    Wait For Elements State    ${RUNTIME_CONTAINER_VERSION_SELECTOR}    visible    timeout=15s
    ${text}=    Get Text    ${RUNTIME_CONTAINER_VERSION_SELECTOR}
    RETURN    ${text}

Submit import wizard runtime step
    [Documentation]    Clicks the runtime step's primary action (Save and start onboarding
    ...                on import, Save on edit) to submit the wizard.

    Wait For Elements State    ${IMPORT_WIZARD_SUBMIT_SELECTOR}    visible    timeout=15s
    Wait For Elements State    ${IMPORT_WIZARD_SUBMIT_SELECTOR}    enabled    timeout=15s
    Click    ${IMPORT_WIZARD_SUBMIT_SELECTOR}

Open model settings on first custom model card
    [Documentation]    Opens the first custom model card's actions menu and clicks
    ...                "Model settings", which navigates to the edit wizard.

    Click actions menu on first custom model card
    Wait For Elements State    ${CUSTOM_MODEL_SETTINGS_MENU_ITEM_SELECTOR}    visible    timeout=10s
    Click    ${CUSTOM_MODEL_SETTINGS_MENU_ITEM_SELECTOR}

# =============================================================================
# Catalog deploy wizard — advanced profile override page keywords
# =============================================================================

Expand advanced profile parameters
    [Documentation]    Clicks the advanced-profile-parameters option in the deploy wizard
    ...                and waits for the precision override select to render.

    Wait For Elements State    ${DEPLOY_ADVANCED_TOGGLE_SELECTOR}    visible    timeout=10s
    Click    ${DEPLOY_ADVANCED_TOGGLE_SELECTOR}
    Wait For Elements State    ${DEPLOY_ADVANCED_PRECISION_SELECTOR}    visible    timeout=10s

Advanced profile parameters should be visible
    [Documentation]    Verifies the advanced override fields (precision select) are shown.

    Wait For Elements State    ${DEPLOY_ADVANCED_PRECISION_SELECTOR}    visible    timeout=10s

Select deploy precision override
    [Documentation]    Picks a precision value in the advanced override precision select.
    [Arguments]    ${precision}

    Click    ${DEPLOY_ADVANCED_PRECISION_SELECTOR}
    Wait For Elements State    css=[role="listbox"]    visible    timeout=10s
    Click    css=[role="listbox"] [role="option"]:has-text("${precision}")

# =============================================================================
# Deploy AIM wizard — step navigation page keywords
# =============================================================================

Click deploy wizard next
    [Documentation]    Clicks the deploy wizard's Next button to advance to the next step.

    Wait For Elements State    ${DEPLOY_WIZARD_NEXT_BUTTON_SELECTOR}    enabled    timeout=15s
    Click    ${DEPLOY_WIZARD_NEXT_BUTTON_SELECTOR}

Select deploy wizard image pull secret
    [Documentation]    Picks an option in the model step's image pull secrets dropdown by its
    ...                visible label, then closes the dropdown. The options list renders in a
    ...                popover outside the wizard dialog, so it is not scoped to the dialog.
    [Arguments]    ${option_label}

    VAR    ${trigger}    ${DEPLOY_WIZARD_SELECTOR} >> css=button[aria-label="Image pull secrets"]
    Wait For Elements State    ${trigger}    visible    timeout=30s
    Click    ${trigger}
    VAR    ${listbox}    css=ul[role="listbox"][data-slot="listbox"]
    VAR    ${option}    ${listbox} [role="option"]:has-text("${option_label}")
    Wait For Elements State    ${option}    visible    timeout=10s
    Click    ${option}
    # Multi-select keeps the popover open, and while open it hides the wizard's Next button.
    Keyboard Key    press    Escape
    Wait For Elements State    ${listbox}    detached    timeout=10s

Advance deploy wizard to review and submit
    [Documentation]    Clicks Next until the wizard reaches its review step, then submits.
    ...                The step count varies by model (adapter-capable models add a
    ...                personalization step), so it is not hard-coded.

    VAR    ${submit}    ${DEPLOY_WIZARD_SELECTOR} >> role=button[name="Submit"]
    FOR    ${_}    IN RANGE    6
        ${at_review}=    Run Keyword And Return Status
        ...    Wait For Elements State    ${submit}    visible    timeout=2s
        IF    ${at_review}    BREAK
        Click deploy wizard next
    END
    Wait For Elements State    ${submit}    enabled    timeout=15s
    Click    ${submit}

Enable dynamic LoRA adapters
    [Documentation]    Enables dynamic LoRA adapter support in the personalization step.

    Wait For Elements State    ${DEPLOY_PERSONALIZATION_TOGGLE_SELECTOR}    visible    timeout=15s
    Click    ${DEPLOY_PERSONALIZATION_TOGGLE_SELECTOR}

Select maximum LoRA rank
    [Documentation]    Chooses the maximum adapter rank in the personalization step.
    [Arguments]    ${rank}

    Wait For Elements State    ${DEPLOY_PERSONALIZATION_MAX_RANK_SELECTOR}    visible    timeout=15s
    Click    ${DEPLOY_PERSONALIZATION_MAX_RANK_SELECTOR}
    VAR    ${option}    css=[role="listbox"] [role="option"]:has-text("${rank}")
    Wait For Elements State    ${option}    visible    timeout=15s
    Click    ${option}

Select LoRA adapter named "${adapter_name}"
    [Documentation]    Selects an available adapter from the personalization table.

    VAR    ${checkbox}    ${DEPLOY_PERSONALIZATION_ADAPTERS_SELECTOR} [role="row"]:has-text("${adapter_name}") [role="checkbox"]
    Wait For Elements State    ${checkbox}    visible    timeout=15s
    Click    ${checkbox}

Wait for deploy wizard LoRA adapter choices
    [Documentation]    Waits for the personalization step's adapter table to finish loading. The
    ...    table mounts before the adapters and profile data it filters against arrive, so a read
    ...    taken on mount sees a list that is merely incomplete rather than filtered.

    Wait For Elements State    ${DEPLOY_PERSONALIZATION_ADAPTERS_SELECTOR}    visible    timeout=30s
    Wait For Elements State
    ...    ${DEPLOY_PERSONALIZATION_ADAPTERS_READY_SELECTOR}    visible    timeout=30s

Get deploy wizard LoRA adapter choices text
    [Documentation]    Returns the visible content of the personalization step's adapter table.

    ${text}=    Get Text    ${DEPLOY_PERSONALIZATION_ADAPTERS_SELECTOR}
    RETURN    ${text}

Deploy wizard LoRA adapter row is visible
    [Documentation]    Reports whether the personalization step lists the named adapter.
    [Arguments]    ${display_name}

    VAR    ${row}    ${DEPLOY_PERSONALIZATION_ADAPTERS_SELECTOR} [role="row"]:has-text("${display_name}")
    ${count}=    Get Element Count    ${row}
    RETURN    ${{ $count > 0 }}

Submit deploy wizard
    [Documentation]    Submits the completed deployment wizard.

    Wait For Elements State    ${DEPLOY_WIZARD_SUBMIT_BUTTON_SELECTOR}    enabled    timeout=15s
    Click    ${DEPLOY_WIZARD_SUBMIT_BUTTON_SELECTOR}

Navigate to scaling step in deploy wizard
    [Documentation]    Advances the deploy wizard from the Model step, through the Target
    ...                step, to reach the Scaling step.

    Click deploy wizard next
    Click deploy wizard next

Target step summary should show unoptimized profile warning
    [Documentation]    Verifies the collapsed Target step summary shows the warning that
    ...                no optimized profile is available for the current selection.

    Wait For Elements State    ${DEPLOY_WIZARD_UNOPTIMIZED_WARNING_SELECTOR}    visible    timeout=10s

# =============================================================================
# Custom-model deploy drawer page keywords
# =============================================================================

Open deploy action from model row
    [Documentation]    Opens the row actions menu for the given model row and clicks
    ...                the Deploy option. Waits for the model row to appear (the
    ...                fine-tune models list loads asynchronously), clicks the row
    ...                actions button, and selects Deploy.
    ...                The Deploy action is only visible for Ready/Complete models —
    ...                test setup must seed the CR with Ready status first.
    [Arguments]    ${model_name}

    VAR    ${row}    css=${FINE_TUNE_MODELS_SELECTOR} table tbody tr:has-text("${model_name}")
    Wait For Elements State    ${row}    visible    timeout=30s
    ${actions_btn}=    Get Element    ${row} >> ${FINE_TUNE_MODELS_ROW_ACTION_BTN}
    Click    ${actions_btn}
    Wait For Elements State    ${FINE_TUNE_MODELS_DEPLOY_OPTION}    visible    timeout=5s
    Click    ${FINE_TUNE_MODELS_DEPLOY_OPTION}

Wait for custom model deploy drawer
    [Documentation]    Waits for the custom-model deploy drawer to mount, anchored on the
    ...                runtime-profile slot (stable ``data-testid``). For a model with no
    ...                profiles to choose from the slot is an empty <div>, which Playwright
    ...                never reports as "visible" (zero bounding box) — assert presence
    ...                (attached) instead so both kinds of model are covered.

    Wait For Elements State    ${CUSTOM_DEPLOY_DRAWER_SELECTOR}    attached    timeout=15s

Deploy drawer should show profile selector
    [Documentation]    Verifies the profile selector is present in the deploy drawer.

    Wait For Elements State    ${CUSTOM_DEPLOY_PROFILE_SELECT}    visible    timeout=15s

Deploy drawer should show profile information
    [Documentation]    Verifies the panel describing the selected profile is present.

    Wait For Elements State    ${CUSTOM_DEPLOY_PROFILE_DETAILS}    visible    timeout=15s

Open deploy drawer profile options
    [Documentation]    Opens the profile dropdown and waits for its listbox to render.

    Wait For Elements State    ${CUSTOM_DEPLOY_PROFILE_TRIGGER}    visible    timeout=15s
    Click    ${CUSTOM_DEPLOY_PROFILE_TRIGGER}
    Wait For Elements State    ${CUSTOM_DEPLOY_PROFILE_LISTBOX}    visible    timeout=10s

Choose deploy drawer profile named "${name}"
    [Documentation]    Opens the profile dropdown and picks the option carrying the given
    ...                label. Matched on the option's text because the label is what the
    ...                user reads; a profile that is offered as unavailable cannot be picked.

    Open deploy drawer profile options
    VAR    ${option}    ${CUSTOM_DEPLOY_PROFILE_LISTBOX} >> css=[role="option"]:has-text("${name}")
    Wait For Elements State    ${option}    visible    timeout=10s
    Click    ${option}
    Wait For Elements State    ${CUSTOM_DEPLOY_PROFILE_LISTBOX}    detached    timeout=10s

Get deploy drawer selected profile text
    [Documentation]    Returns the label the profile selector currently shows.

    ${text}=    Get Text    ${CUSTOM_DEPLOY_PROFILE_TRIGGER}
    RETURN    ${text}

Deploy drawer header should show model name
    [Documentation]    Verifies the deploy drawer header shows the model name as a
    ...                prominent heading (text-2xl). The component renders model.name
    ...                in a div with class text-2xl.
    [Arguments]    ${model_name}

    VAR    ${selector}    css=.text-2xl:has-text("${model_name}")
    Wait For Elements State    ${selector}    visible    timeout=10s

Deploy drawer header should show namespace
    [Documentation]    Verifies the deploy drawer shows the "Deploying into ..." namespace
    ...                label, confirming the header section rendered correctly.

    Wait For Elements State    text=Deploying into    visible    timeout=10s

Deploy drawer should show display name input
    [Documentation]    Verifies the deployment-name (displayName) input is present
    ...                and interactive in the deploy drawer.

    Wait For Elements State    ${CUSTOM_DEPLOY_DISPLAY_NAME_INPUT}    visible    timeout=10s

Deploy drawer should show autoscaling toggle
    [Documentation]    Verifies the autoscaling enable toggle is visible in the
    ...                deploy drawer. The toggle carries data-testid="autoscaling-toggle".

    Wait For Elements State    ${CUSTOM_DEPLOY_AUTOSCALING_TOGGLE}    visible    timeout=10s

Submit custom model deploy drawer
    [Documentation]    Clicks the Deploy (confirm) button in the drawer footer to
    ...                submit the form with whatever values are currently set.
    ...                The button is identified by aria-label="Deploy".

    Wait For Elements State    ${CUSTOM_DEPLOY_SUBMIT_BTN}    visible    timeout=10s
    Wait For Elements State    ${CUSTOM_DEPLOY_SUBMIT_BTN}    enabled    timeout=10s
    Click    ${CUSTOM_DEPLOY_SUBMIT_BTN}

Custom model deploy drawer should be closed
    [Documentation]    Verifies the custom-model deploy drawer is gone. Anchored on the
    ...                runtime-profile placeholder, which is an empty reserved <div>: it is
    ...                only in the DOM while the drawer is mounted, so assert it has detached
    ...                rather than "hidden" (an empty div counts as hidden even when open).

    Wait For Elements State    ${CUSTOM_DEPLOY_DRAWER_SELECTOR}    detached    timeout=5s

Open fine-tune action from model row
    [Documentation]    Opens the row actions menu for the given model row and clicks the Fine-tune option.
    ...                Waits for the model row to appear (the fine-tune models list loads asynchronously)
    ...                and then clicks the row actions button and selects Fine-tune.
    [Arguments]    ${model_name}

    VAR    ${row}    css=${FINE_TUNE_MODELS_SELECTOR} table tbody tr:has-text("${model_name}")
    Wait For Elements State    ${row}    visible    timeout=30s
    ${actions_btn}=    Get Element    ${row} >> ${FINE_TUNE_MODELS_ROW_ACTION_BTN}
    Click    ${actions_btn}
    Wait For Elements State    ${FINE_TUNE_MODELS_FINETUNE_OPTION}    visible    timeout=5s
    Click    ${FINE_TUNE_MODELS_FINETUNE_OPTION}

Wait for fine-tune models table to load
    [Documentation]    Waits for the fine-tune models table to render at least one row.

    Wait For Elements State    ${FINE_TUNE_MODELS_TABLE_ROW}    visible    timeout=30s

Wait for fine-tune models table to settle
    [Documentation]    Waits until the table's asynchronous data loading is complete.

    Wait For Elements State    ${FINETUNE_BTN_SELECTOR}    enabled    timeout=30s

Get fine-tune models row count
    [Documentation]    Returns the number of rows currently displayed in the fine-tune models table body.

    ${elements}=    Get Elements    ${FINE_TUNE_MODELS_TABLE_ROW}
    ${count}=    Get Length    ${elements}
    RETURN    ${count}

Wait for fine-tune models pagination controls
    [Documentation]    Waits for the table's pagination control to appear. Pagination only
    ...                renders when there is more than one page, so this implicitly verifies
    ...                that pageSize < total.

    Wait For Elements State    ${FINE_TUNE_MODELS_PAGINATION}    visible    timeout=30s

Click fine-tune models next page button
    [Documentation]    Clicks the next-page control on the fine-tune models table pagination.

    Wait For Elements State    ${FINE_TUNE_MODELS_NEXT_PAGE_BTN}    visible    timeout=10s
    Wait For Elements State    ${FINE_TUNE_MODELS_NEXT_PAGE_BTN}    enabled    timeout=10s
    Click    ${FINE_TUNE_MODELS_NEXT_PAGE_BTN}

Get fine-tune models first row text
    [Documentation]    Returns the text content of the first row in the fine-tune models table.
    ...                Useful for verifying that the rendered page changed between paginations
    ...                without depending on the absolute model name (which varies by seed batch).

    Wait For Elements State    ${FINE_TUNE_MODELS_TABLE_ROW}    visible    timeout=15s
    ${elements}=    Get Elements    ${FINE_TUNE_MODELS_TABLE_ROW}
    ${text}=    Get Text    ${elements}[0]
    RETURN    ${text}

Get fine-tune models row text
    [Documentation]    Returns the text content of the fine-tune model row matching the given name.
    [Arguments]    ${model_name}

    VAR    ${row}    ${FINE_TUNE_MODELS_TABLE_ROW}:has-text("${model_name}")
    Wait For Elements State    ${row}    visible    timeout=30s
    ${text}=    Get Text    ${row}
    RETURN    ${text}

Get fine-tune model name cell text
    [Documentation]    Returns the Name cell text for the fine-tuned model matching the given name.
    [Arguments]    ${model_name}

    VAR    ${row}    ${FINE_TUNE_MODELS_TABLE_ROW}:has-text("${model_name}")
    Wait For Elements State    ${row}    visible    timeout=30s
    ${text}=    Get Text    ${row} >> css=td:nth-child(1)
    RETURN    ${text}

Get fine-tune models table header text
    [Documentation]    Returns the text content of the fine-tune models table header.

    ${text}=    Get Text    css=${FINE_TUNE_MODELS_SELECTOR} table thead
    RETURN    ${text}

Fine-tune models row is visible
    [Documentation]    Returns whether a fine-tuned model row with the given name is visible.
    [Arguments]    ${model_name}

    Wait for fine-tune models table to settle
    VAR    ${row}    ${FINE_TUNE_MODELS_TABLE_ROW}:has-text("${model_name}")
    ${count}=    Get Element Count    ${row}
    ${visible}=    Evaluate    ${count} > 0
    RETURN    ${visible}

Click base model option with name
    [Documentation]    Selects a specific base model option by canonical name.
    [Arguments]    ${canonical_name}

    VAR    ${selector}    css=[data-testid="model-select-${canonical_name}"]
    Wait For Elements State    ${selector}    visible    timeout=10s
    Click    ${selector}

HF token section should be present
    [Documentation]    Verifies the Hugging Face Authentication section is visible in the wizard.
    ...                The section is only mounted when the selected base model is gated.

    Wait For Elements State    ${HF_TOKEN_SECTION_SELECTOR}    visible    timeout=10s

HF token section should not be present
    [Documentation]    Verifies the Hugging Face Authentication section is not in the DOM.
    ...                The section is unmounted when the selected base model is not gated.

    Wait For Elements State    ${HF_TOKEN_SECTION_SELECTOR}    detached    timeout=10s

Click finetune wizard submit button
    [Documentation]    Clicks the "Start training" button in the fine-tuning wizard.

    Click    ${FINETUNE_CONFIRM_BTN_SELECTOR}

Fine-tuning success toast link should be visible
    [Documentation]    Verifies the fine-tuning success toast contains the expected link.
    [Arguments]    ${link_label}

    VAR    ${toast_link}    css=[data-slot="toast"]:has-text("Fine-tuning started") a:has-text("${link_label}")
    Wait For Elements State    ${toast_link}    visible    timeout=30s

Fill finetune display name
    [Documentation]    Types a display name into the fine-tuning wizard's model name input.
    [Arguments]    ${name}

    Fill Text    ${FINETUNE_DISPLAY_NAME_INPUT}    ${name}

Fill finetune description
    [Documentation]    Types a description into the fine-tuning wizard's description input.
    [Arguments]    ${description}

    Fill Text    ${FINETUNE_DESCRIPTION_INPUT}    ${description}

Open details action from model row
    [Documentation]    Opens the row actions menu for the given model and selects Details.
    [Arguments]    ${model_name}

    VAR    ${row}    css=${FINE_TUNE_MODELS_SELECTOR} table tbody tr:has-text("${model_name}")
    Wait For Elements State    ${row}    visible    timeout=30s
    ${actions_btn}=    Get Element    ${row} >> ${FINE_TUNE_MODELS_ROW_ACTION_BTN}
    Click    ${actions_btn}
    Wait For Elements State    ${FINE_TUNE_MODELS_DETAILS_OPTION}    visible    timeout=5s
    Click    ${FINE_TUNE_MODELS_DETAILS_OPTION}

Model details should show description
    [Documentation]    Verifies the open model details dialog contains a description.
    [Arguments]    ${description}

    VAR    ${dialog}    css=[role="dialog"]:has-text("Description"):has-text("${description}")
    Wait For Elements State    ${dialog}    visible    timeout=10s

Custom models empty state should be visible
    [Documentation]    Waits for the empty-state placeholder shown when a project has no
    ...                imported custom models. This is distinct from the filtered empty
    ...                state which appears when a search or status filter yields no results.

    Wait For Elements State    ${CUSTOM_MODELS_EMPTY_STATE_SELECTOR}    visible    timeout=15s

Custom model card with text "${text}" should be visible
    [Documentation]    Asserts that at least one custom model card contains the given text.
    ...                Used to verify a specific display name or label is shown on a card.

    Wait For Elements State    css=[data-testid="custom-model-card"]:has-text("${text}")    visible    timeout=30s

Click deploy button on custom model card
    [Documentation]    Clicks the deploy button of a Ready custom model card. The button is
    ...                enabled only for deployable models, and a Ready card renders no status pill
    ...                — so the enabled button, not a "Ready" text match, is the deployability
    ...                signal. Waits for an enabled deploy button and acts on [0] to avoid strict
    ...                mode with several cards.

    Wait For Elements State    ${CUSTOM_MODEL_CARD_SELECTOR}    visible    timeout=30s
    VAR    ${enabled_deploy}    ${CUSTOM_MODEL_CARD_DEPLOY_BUTTON_SELECTOR}:not([disabled])
    Wait For Elements State    ${enabled_deploy}    visible    timeout=60s
    ${buttons}=    Get Elements    ${enabled_deploy}
    Should Be True    len($buttons) > 0    msg=Expected at least one enabled (Ready) custom model card deploy button
    Click    ${buttons}[0]

Custom model deploy success toast should be shown
    [Documentation]    Waits for the success toast emitted by DeployCustomAIMDrawer after a
    ...                successful deploy POST. The message is "Model deployment started".

    Wait For Elements State    text=Model deployment started    visible    timeout=30s

Deployed models table should contain a model with display name "${name}"
    [Documentation]    Waits for a row in the Deployed Models table whose text includes the
    ...                given display name. The row appears quickly after the AIMService CR
    ...                is created, regardless of whether the deployment has reached Running.

    Wait For Elements State    css=${DEPLOYED_MODELS_SELECTOR} tr:has-text("${name}")    visible    timeout=60s

Click undeploy action for deployed model with display name "${name}"
    [Documentation]    Opens the row-actions menu for the deployed model row identified by
    ...                display name and selects the "Undeploy" option. The option is
    ...                available for any non-Deleted status.

    VAR    ${row}    css=${DEPLOYED_MODELS_SELECTOR} tr:has-text("${name}")
    Wait For Elements State    ${row}    visible    timeout=30s
    Click    ${row} >> css=button[aria-label="Actions"]
    Wait For Elements State    css=[data-testid="undeploy"]    visible    timeout=10s
    Click    css=[data-testid="undeploy"]

Undeploy confirmation modal should be visible
    [Documentation]    Waits for the undeploy confirmation modal to appear. The modal uses
    ...                the shared ConfirmationModal component.

    Wait For Elements State    css=[data-testid="confirmation-modal"]    visible    timeout=10s

Confirm model undeploy in modal
    [Documentation]    Clicks the confirm button in the undeploy confirmation modal.

    Click    css=[data-testid="confirm-button"]

Undeploy success toast should be shown
    [Documentation]    Waits for the "Workload deletion started" toast shown after the undeploy
    ...                is confirmed. Deletion is async — the backend kicks off finalizers rather
    ...                than completing synchronously, so the toast signals initiation, not completion.

    Wait For Elements State    text=Workload deletion started    visible    timeout=30s

Deployed models table should not contain a model with display name "${name}"
    [Documentation]    Asserts that no row in the Deployed Models table matches the given
    ...                display name, confirming the undeploy removed the entry.
    ...                Uses a 2 min timeout because the row disappears only once the AIMService
    ...                CR is physically gone, after Kubernetes finalizers complete.

    Wait For Elements State    css=${DEPLOYED_MODELS_SELECTOR} tr:has-text("${name}")    hidden    timeout=2min
