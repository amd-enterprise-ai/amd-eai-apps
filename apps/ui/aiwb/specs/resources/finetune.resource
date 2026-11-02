# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for fine-tuning wizard UI features.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)
Library             Collections
Library             String
Library             Process
Resource            common/session.resource
Resource            pages/models_page.resource
Resource            pages/workloads_page.resource
Resource            resources/airm_clusters.resource
Resource            resources/airm_projects.resource
Resource            resources/aiwb_common.resource
Resource            resources/aiwb_datasets.resource
Resource            resources/aiwb_models.resource
Resource            resources/aiwb_aims.resource
Resource            resources/aiwb_secrets.resource
Library             libraries/FinetuneRecipeSelector.py


*** Keywords ***
# =============================================================================
# Given keywords (preconditions)
# =============================================================================

A cluster with no GPU hardware exists
    [Documentation]    Skips the test if the cluster has GPU hardware. Fine-tuning recipes
    ...    are filtered by GPU compatibility, so the empty-state message only appears on
    ...    CPU-only clusters where no recipes match the available hardware.
    ${gpu_count}=    Get cluster GPU capacity
    Skip If    ${gpu_count} > 0    Cluster has ${gpu_count} GPUs — recipes will match, empty state not expected

A completed fine-tuned model exists for the test project
    [Documentation]    Creates a minimal AIMModel CR and patches its status to Ready,
    ...    so the UI treats the row as Complete and displays the Fine-tune row action.
    ...    Delegates to the API resource keyword to avoid duplication and drift.
    A completed fine-tuned model exists in the namespace

A completed described fine-tuned model exists for the test project
    [Documentation]    Creates a completed fine-tuned model with its user-supplied description.
    A completed described fine-tuned model exists in the namespace

A LoRA-output fine-tuning job exists
    [Documentation]    Starts a fine-tuning job that produces a standalone LoRA adapter.
    An adapter-output fine-tuning job is started

A base model that can be fine-tuned with LoRA but cannot serve adapters exists
    [Documentation]    Picks a base model this cluster can train a LoRA adapter for, but whose
    ...                serving profiles can never load that adapter afterwards — the situation
    ...                in which the wizard is expected to withhold LoRA output. Records the
    ...                choice for the later "user selects the base model that cannot serve
    ...                adapters" step.
    ...
    ...                Skips when every LoRA-capable base model here can serve adapters: there
    ...                is then no cause to withhold anything, and failing would report a
    ...                missing restriction that is correctly absent.

    ${response}=    Get finetunable models    expected_status=200
    VAR    ${models}    ${response.json()["data"]}
    ${profiles}=    All inference profiles
    ${canonical_name}=    Find LoRA recipe without adapter support    ${models}    ${profiles}
    Skip If    $canonical_name == ''
    ...    Every LoRA-capable base model on this cluster can serve adapters — nothing to withhold
    VAR    ${LORA_NO_ADAPTER_BASE_MODEL}    ${canonical_name}    scope=TEST
    Log    Base model that cannot serve adapters: ${canonical_name}    INFO

A base model that can be fine-tuned with LoRA and can serve adapters exists
    [Documentation]    Picks a base model this cluster can train a LoRA adapter for and whose
    ...                serving profiles can load that adapter afterwards — the case in which
    ...                LoRA output stays on offer. Records the choice for the later "user
    ...                selects the base model that can serve adapters" step.
    ...
    ...                Any scenario that goes on to choose LoRA output needs this: picking a
    ...                LoRA recipe without regard to adapter serving lands on a base model
    ...                for which the wizard now withholds LoRA, and the run would wait on an
    ...                option that never becomes selectable.
    ...
    ...                Skips when no LoRA-capable base model here can serve adapters: LoRA
    ...                output cannot be exercised at all on such a cluster.

    ${response}=    Get finetunable models    expected_status=200
    VAR    ${models}    ${response.json()["data"]}
    ${profiles}=    All inference profiles
    ${canonical_name}=    Find LoRA recipe with adapter support    ${models}    ${profiles}
    Skip If    $canonical_name == ''
    ...    No LoRA-capable base model on this cluster can serve adapters — LoRA output is not offered
    VAR    ${LORA_ADAPTER_BASE_MODEL}    ${canonical_name}    scope=TEST
    Log    Base model that can serve adapters: ${canonical_name}    INFO

More fine-tuned models exist in the namespace than fit a single page
    [Documentation]    Seeds enough AIMModel CRs to force at least two pages at the default
    ...                page size (10). Uses kubectl so no GPU is required — the CRs share the
    ...                same shape the UI consumes from the live cluster.
    ...                Idempotent across re-runs: kubectl apply patches existing CRs in place.
    ${namespace}=    Get Project Namespace
    Apply Multiple Dummy AIMModel CRs    ${namespace}    12

Test project is selected
    [Documentation]    Selects the current test project via the toolbar.
    ...                Extracts the project name from TEST_PROJECT and selects it via the toolbar.

    Project "${TEST_PROJECT}[name]" is selected

User is on fine-tune models page
    [Documentation]    Navigates to the Fine-tune Models tab on the models page.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.
    ...                The fine-tune table lives on its own tab, not the Custom Models
    ...                tab; scenarios that used to navigate to
    ...                "user is on custom models page" should now use this.

    Navigate to fine-tune models page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

# =============================================================================
# When keywords (actions)
# =============================================================================

User opens fine-tuning wizard
    [Documentation]    Clicks the Fine-tune button to open the fine-tuning wizard.

    Open finetune wizard

User opens the base model selector
    [Documentation]    Clicks the base model select to expand the option list.

    Click base model select

User selects the first compatible recipe
    [Documentation]    Opens the base model dropdown and selects the first listed recipe.
    ...                Skips when the cluster has no GPU-compatible recipes.

    Click base model select
    TRY
        Wait Until Keyword Succeeds    30s    500ms    Base model options should be non-empty
    EXCEPT
        Skip    No GPU-compatible fine-tuning recipes available for this cluster
    END
    ${option_text}=    Get base model option text
    ${recipe_name}=    Evaluate    $option_text.split("\n")[0]
    VAR    ${SELECTED_FINETUNING_RECIPE}    ${recipe_name}    scope=TEST
    Click first base model option

User selects a gated base model
    [Documentation]    Opens the base model dropdown and selects the first recipe whose
    ...                hfTokenRequired flag is true in the finetunable catalog API.
    ...                Skips when no gated recipes are available on the cluster.

    ${response}=    Get finetunable models    expected_status=200
    VAR    ${models}    ${response.json()["data"]}
    VAR    ${gated_name}    ${None}
    FOR    ${m}    IN    @{models}
        IF    $m.get("hfTokenRequired") is True
            VAR    ${gated_name}    ${m["canonicalName"]}
            BREAK
        END
    END
    Skip If    $gated_name is None    No gated fine-tuning recipes available on this cluster
    Click base model select
    Wait Until Keyword Succeeds    10s    500ms    Base model options should be non-empty
    Click base model option with name    ${gated_name}

User selects the existing HuggingFace token
    [Documentation]    Opens the HuggingFace token dropdown in the fine-tuning wizard and
    ...                selects the token created by the "a secret ... is created via AIWB"
    ...                Given step.
    ...                Requires: TEST_AIWB_SECRET_NAME (set by that Given step)

    Open project Hugging Face token dropdown
    Click Hugging Face token option labeled    ${TEST_AIWB_SECRET_NAME}

User creates a new HuggingFace token via the token selector
    [Documentation]    Opens the HuggingFace token dropdown, clicks "Add new", fills in a
    ...                unique display name and a syntactically valid dummy token, and submits
    ...                the popover. Exercises the inline token-creation flow a user follows
    ...                when a gated model needs a token the project doesn't have yet. The
    ...                selector auto-selects the newly created token on success.

    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    Open project Hugging Face token dropdown
    Click Hugging Face token add new button
    Fill Hugging Face token dialog fields    finetune-hf-${suffix}    hf_dummytoken1234567890abcdef
    Click Hugging Face token dialog submit button
    Wait For Elements State    ${HF_TOKEN_DIALOG_SUBMIT_SELECTOR}    detached    timeout=15s

User continues to training settings
    [Documentation]    Advances from model selection to training data.

    Click fine-tuning wizard next button

User selects the first training dataset
    [Documentation]    Selects the first available fine-tuning dataset.

    Select first training dataset

User selects LoRA fine-tuning type
    [Documentation]    Chooses LoRA training for a recipe that supports it.

    Select LoRA fine-tuning type

User selects ${count:\d+} training datasets
    [Documentation]    Selects the requested number of available fine-tuning datasets.

    FOR    ${index}    IN RANGE    ${count}
        Select training dataset by index    ${index}
    END

User selects all training datasets
    [Documentation]    Selects every available fine-tuning dataset.

    Select all training datasets

Training datasets should show their file sizes
    [Documentation]    Verifies available training datasets include their file sizes.

    Dataset selector should show file sizes

User continues to target settings
    [Documentation]    Advances from training data to output settings.

    Click fine-tuning wizard next button

User names the fine-tuned model and continues
    [Documentation]    Names the output model on the Target step and advances.
    [Arguments]    ${name}

    Fill finetune display name    ${name}
    Click fine-tuning wizard next button

User goes back in fine-tuning wizard
    [Documentation]    Returns to the previous wizard step.

    Click fine-tuning wizard back button

User continues to hyper-parameter settings
    [Documentation]    Names the output model and advances to optional hyper-parameters.

    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    Fill finetune display name    finetune-hyperparameters-${suffix}
    Click fine-tuning wizard next button

User enables hyper-parameter customization
    [Documentation]    Enables the optional custom hyper-parameter fields.

    Enable hyper-parameter customization

User continues to confirmation
    [Documentation]    Advances from hyperparameter settings to the wizard confirmation step.

    Click fine-tuning wizard next button

User sets custom decimal hyperparameters
    [Documentation]    Enters decimal values whose confirmation display should match field precision.

    Fill learning rate    1.4
    Fill LoRA dropout    0.054

Format hyperparameter placeholder
    [Documentation]    Matches JavaScript String formatting for recipe values.
    [Arguments]    ${value}

    IF    $value is None
        RETURN    Auto
    END
    ${text}=    Evaluate    str(int($value)) if isinstance($value, float) and $value.is_integer() else str($value)
    RETURN    ${text}

The hyperparameter defaults should show the selected recipe's values
    [Documentation]    Confirms that placeholders match the selected recipe, or Auto when
    ...    that recipe does not define a value.

    ${response}=    Get finetunable models    expected_status=200
    VAR    ${recipes}    ${response.json()["data"]}
    ${recipe}=    Evaluate
    ...    next(recipe for recipe in $recipes if recipe["canonicalName"] == $SELECTED_FINETUNING_RECIPE)
    ${hyperparameters}=    Get From Dictionary    ${recipe}    hyperparameters
    ${expected_epochs}=    Format hyperparameter placeholder    ${hyperparameters["epochs"]}
    ${expected_learning_rate}=    Format hyperparameter placeholder    ${hyperparameters["learningRate"]}
    ${epochs}    ${learning_rate}=    Get hyperparameter input placeholders
    Should Be Equal    ${epochs}    ${expected_epochs}
    Should Be Equal    ${learning_rate}    ${expected_learning_rate}

The confirmation should format decimal hyperparameters to their step precision
    [Documentation]    Verifies the collapsed summary uses one decimal for learning rate and
    ...    three decimals for dropout.

    ${summary}=    Get hyperparameters summary text
    Should Match Regexp    ${summary}    (?s).*Learning rate multiplier\\s+1\\.4\\s+.*
    Should Match Regexp    ${summary}    (?s).*Dropout\\s+0\\.054(?:\\s|$).*

User submits the fine-tuning form
    [Documentation]    Completes the remaining wizard steps and starts training.

    Click fine-tuning wizard next button
    Select first training dataset
    Click fine-tuning wizard next button
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    Fill finetune display name    finetune-defaults-${suffix}
    Click fine-tuning wizard next button
    Click fine-tuning wizard next button
    Click finetune wizard submit button

User submits fine-tuning leaving the batch size field at its default
    [Documentation]    Advances through the remaining wizard steps, enables hyper-parameter
    ...                customization, and interacts with the batch size field the way a
    ...                user accepting the default (Auto) value would: focusing it and
    ...                moving on without typing anything, then starts training.
    ...
    ...                Regression coverage: a HeroUI v3 migration left the shared
    ...                number-input control briefly surfacing an invalid empty-string/NaN
    ...                sentinel for an untouched optional field once it was focused and
    ...                blurred, which could block submission or reach the backend as a
    ...                validation error.

    Click fine-tuning wizard next button
    Select first training dataset
    Click fine-tuning wizard next button
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    Fill finetune display name    finetune-defaults-${suffix}
    Click fine-tuning wizard next button
    Enable hyper-parameter customization
    Focus and blur batch size input
    Click fine-tuning wizard next button
    Click finetune wizard submit button

User submits the fine-tuning form with a description
    [Documentation]    Completes the wizard with a description and starts training.

    Click fine-tuning wizard next button
    Select first training dataset
    Click fine-tuning wizard next button
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${TEST_FINETUNING_DISPLAY_NAME}    finetune-described-${suffix}    scope=TEST
    Fill finetune display name    ${TEST_FINETUNING_DISPLAY_NAME}
    Fill finetune description    ${FINETUNED_MODEL_DESCRIPTION}
    Click fine-tuning wizard next button
    Click fine-tuning wizard next button
    Click finetune wizard submit button

User submits fine-tuning with the selected training datasets
    [Documentation]    Completes the wizard using the datasets already selected.

    Click fine-tuning wizard next button
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    Fill finetune display name    finetune-multiple-${suffix}
    Click fine-tuning wizard next button
    Click fine-tuning wizard next button
    Click finetune wizard submit button

User selects a non-gated base model
    [Documentation]    Opens the base model dropdown and selects the first recipe whose
    ...                hfTokenRequired flag is explicitly false in the finetunable catalog API.
    ...                Skips when no non-gated recipes are available on the cluster.

    ${response}=    Get finetunable models    expected_status=200
    VAR    ${models}    ${response.json()["data"]}
    VAR    ${non_gated_name}    ${None}
    FOR    ${m}    IN    @{models}
        IF    $m.get("hfTokenRequired") is False
            VAR    ${non_gated_name}    ${m["canonicalName"]}
            BREAK
        END
    END
    Skip If    $non_gated_name is None    No non-gated fine-tuning recipes available on this cluster
    Click base model select
    Wait Until Keyword Succeeds    10s    500ms    Base model options should be non-empty
    Click base model option with name    ${non_gated_name}

User selects the base model that can serve adapters
    [Documentation]    Selects the LoRA-capable base model with adapter-serving support
    ...                that the matching Given step picked for this cluster.

    Click base model select
    Wait Until Keyword Succeeds    10s    500ms    Base model options should be non-empty
    Click base model option with name    ${LORA_ADAPTER_BASE_MODEL}

User selects the base model that cannot serve adapters
    [Documentation]    Selects the LoRA-capable base model without adapter-serving support
    ...                that the matching Given step picked for this cluster.

    Click base model select
    Wait Until Keyword Succeeds    10s    500ms    Base model options should be non-empty
    Click base model option with name    ${LORA_NO_ADAPTER_BASE_MODEL}

User submits LoRA adapter fine-tuning
    [Documentation]    Completes the wizard with representative LoRA hyper-parameters.
    Click fine-tuning wizard next button
    Select LoRA fine-tuning type
    Select first training dataset
    Click fine-tuning wizard next button
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    Fill finetune display name    finetune-lora-${suffix}
    Click fine-tuning wizard next button
    Enable hyper-parameter customization
    Fill LoRA rank    16
    Fill LoRA alpha    32
    Fill LoRA dropout    0.05
    Click fine-tuning wizard next button
    Click finetune wizard submit button

# =============================================================================
# Then keywords (verification)
# =============================================================================

The HuggingFace token section should be visible
    [Documentation]    Verifies the Hugging Face Authentication section is shown in the wizard.
    ...                The section is mounted only when the selected base model is gated.

    HF token section should be present

The HuggingFace token section should not be visible
    [Documentation]    Verifies the Hugging Face Authentication section is absent from the wizard.
    ...                The section is unmounted when the selected base model is not gated.

    HF token section should not be present

Continuing without a token should be blocked
    [Documentation]    Verifies the wizard cannot leave the model step without the required token.

    Fine-tuning wizard next button should be disabled
    HF token section should be present

Compatible fine-tuning recipes should be listed with hardware names
    [Documentation]    Verifies the base model dropdown contains options and that each option
    ...    displays a non-empty hardware name below the model name.
    ...    Polls for async load; skips gracefully if no compatible recipes exist for this cluster.

    TRY
        Wait Until Keyword Succeeds    30s    500ms    Base model options should be non-empty
    EXCEPT
        Skip    No GPU-compatible fine-tuning recipes available for this cluster
    END

    # Each option shows the model name on the first line and compatible hardware on the second.
    ${count}=    Get base model option count
    FOR    ${i}    IN RANGE    ${count}
        ${text}=    Get base model option text    ${i}
        ${lines}=    Evaluate    [l.strip() for l in '''${text}'''.split('\\n') if l.strip()]
        Should Be True    len($lines) >= 2
        ...    msg=Base model option ${i} should display a hardware name description below the model name
        Should Not Be Empty    ${lines}[1]
        ...    msg=Hardware name description should not be empty for base model option ${i}
    END

Each base model should appear at most once in the recipe list
    [Documentation]    Verifies no model name appears more than once in the base model dropdown.
    ...    A duplicate would mean an incompatible hardware variant was not filtered out
    ...    for the cluster's GPU type. Polls for async load; skips if no recipes available.

    TRY
        Wait Until Keyword Succeeds    30s    500ms    Base model options should be non-empty
    EXCEPT
        Skip    No GPU-compatible fine-tuning recipes available for this cluster
    END

    ${count}=    Get base model option count
    VAR    @{seen_names}
    FOR    ${i}    IN RANGE    ${count}
        ${text}=    Get base model option text    ${i}
        ${name}=    Evaluate    '''${text}'''.split('\\n')[0].strip()
        Should Not Contain    ${seen_names}    ${name}
        ...    msg=Model '${name}' appears more than once — incompatible hardware variant not filtered
        Append To List    ${seen_names}    ${name}
    END

The fine-tuning job should start without a validation error
    [Documentation]    Verifies the wizard closed after the fine-tune mutation succeeded.

    Fine-tuning wizard should be closed

Fine-tuning workload details should show its description
    [Documentation]    Finds the submitted job and verifies its description on workload details.

    ${workload}=    Wait Until Keyword Succeeds
    ...    2 min
    ...    5 sec
    ...    Resolve submitted fine-tuning workload
    Navigate to workload details page by id
    ...    ${UI_BASE_URL}
    ...    ${TEST_PROJECT}[name]
    ...    ${workload}[id]
    ${description}=    Get workload description text
    Should Be Equal    ${description}    ${FINETUNED_MODEL_DESCRIPTION}

Resolve submitted fine-tuning workload
    [Documentation]    Returns the workload created by the current wizard submission.

    ${namespace}=    Get Project Namespace
    ${response}=    Get AIWB workloads
    ...    ${namespace}
    ...    workload_type=FINE_TUNING
    ...    expected_status=200
    VAR    ${workloads}    ${response.json()}[data]
    ${matches}=    Evaluate
    ...    [item for item in $workloads if item["displayName"] == $TEST_FINETUNING_DISPLAY_NAME]
    Length Should Be    ${matches}    1
    VAR    ${TEST_FINETUNING_WORKLOAD_ID}    ${matches}[0][id]    scope=TEST
    RETURN    ${matches}[0]

User opens details for the completed fine-tuned model
    [Documentation]    Opens the details dialog for the prepared fine-tuned model.

    Open details action from model row    ${TEST_MODEL_NAME}

Fine-tuned model details should show its description
    [Documentation]    Verifies the prepared model's description is visible in its details.

    Model details should show description    ${FINETUNED_MODEL_DESCRIPTION}

The training dataset selection limit should be shown
    [Documentation]    Verifies the wizard explains that at most ten datasets may be selected.

    Wait For Elements State    ${FINETUNE_DATASET_LIMIT_TOAST_SELECTOR}    visible    timeout=10s

The fine-tuning success toast should offer navigation to fine-tuned models
    [Documentation]    Verifies a submitted model training job offers navigation to its listing.

    Fine-tuning success toast link should be visible    View models

The fine-tuning success toast should offer navigation to LoRAs
    [Documentation]    Verifies a submitted LoRA training job offers navigation to its listing.

    Fine-tuning success toast link should be visible    View LoRAs

LoRA fine-tuning should not be offered
    [Documentation]    Verifies the user cannot choose an output this base model could never
    ...                have deployed. Offering it would send the user down a path the run is
    ...                refused at the end of.

    ${enabled}=    Get LoRA fine-tuning type enabled state
    Should Not Be True    ${enabled}
    ...    msg=LoRA output should be unavailable for a base model whose adapters could never be served

The wizard should explain that adapters for this model cannot be deployed
    [Documentation]    Verifies the unavailable option says why. A silently unavailable choice
    ...                leaves the user to guess whether the product is broken or their base
    ...                model is the wrong one.

    ${text}=    Get fine-tuning type options text
    Should Match Regexp    ${text}    (?i)adapter
    ...    msg=The unavailable option should mention adapters so the user can tell what is missing
    Should Match Regexp    ${text}    (?i)deploy
    ...    msg=The unavailable option should say the adapter could not be deployed

A usable fine-tuning type should be chosen instead
    [Documentation]    Verifies the wizard does not leave the form resting on an output the
    ...                user can no longer pick, which would block the run with nothing to
    ...                change on screen.

    ${checked}=    Get LoRA fine-tuning type checked state
    Should Not Be True    ${checked}    msg=An unavailable output should not stay chosen
    ${chosen}=    Get chosen fine-tuning type name
    Should Not Be Empty    ${chosen}    msg=The wizard should move to an output the user can still run

Fine-tuning wizard should show no compatible recipes message
    [Documentation]    Verifies the base model select shows a message that no fine-tuning
    ...    recipes are available for the cluster's GPU hardware.

    Base model select should show empty state

The batch size input should require multiples of the recipe's GPU count
    [Documentation]    Verifies the first batch-size increment starts from the selected
    ...                recipe recommendation and then adds the recipe's GPU count.
    ...
    Batch size input should be enabled
    ${response}=    Get finetunable models    expected_status=200
    VAR    ${recipes}    ${response.json()["data"]}
    ${recipe}=    Evaluate
    ...    next(recipe for recipe in $recipes if recipe["canonicalName"] == $SELECTED_FINETUNING_RECIPE)
    ${hyperparameters}=    Get From Dictionary    ${recipe}    hyperparameters
    ${gpu_count}=    Get From Dictionary    ${recipe}    gpuCount
    ${recipe_batch_size}=    Get From Dictionary    ${hyperparameters}    batchSize
    IF    $recipe_batch_size is not None
        ${expected}=    Evaluate    $recipe_batch_size + $gpu_count
        Click batch size increment button
        ${value}=    Get batch size value
        Should Be Equal As Integers    ${value}    ${expected}
        ...    msg=Expected the first increment to start from the recipe recommendation (${recipe_batch_size}) and add ${gpu_count}, got ${value}
    ELSE
        Click batch size increment button
        ${value}=    Get batch size value
        Should Be Equal As Integers    ${value}    ${gpu_count}
        Skip If    ${gpu_count} <= 1
        ...    Selected recipe uses ${gpu_count} GPU; multiple-of constraint does not apply
        Click batch size increment button
        ${value}=    Get batch size value
        ${expected}=    Evaluate    2 * $gpu_count
        Should Be Equal As Integers    ${value}    ${expected}
        ...    msg=Expected the second increment to add ${gpu_count}, got ${value}
    END

The completed fine-tuned model identity should be presented together
    [Documentation]    Verifies the model's name, description, base model, and tuning type
    ...    are grouped in the Name cell.
    ${name_cell_text}=    Get fine-tune model name cell text    ${TEST_MODEL_NAME}
    Should Contain    ${name_cell_text}    ${TEST_MODEL_NAME}
    Should Contain    ${name_cell_text}    ${FINETUNED_MODEL_DESCRIPTION}
    Should Contain    ${name_cell_text}    ${FINETUNED_MODEL_BASE_MODEL}
    Should Contain    ${name_cell_text}    Full

Its operational and creation details should remain visible
    [Documentation]    Verifies the compact table preserves the model's status, workloads,
    ...    creation time, and creator columns.
    ${headers}=    Get fine-tune models table header text
    Should Contain    ${headers}    Status
    Should Contain    ${headers}    Workloads
    Should Contain    ${headers}    Created at
    Should Contain    ${headers}    Created by

# =============================================================================
# Keywords for fine-tuning from completed model row action
# =============================================================================

User opens fine-tune action on the completed model row
    [Documentation]    Finds the completed model row in the custom models table, opens its row
    ...    actions menu, and clicks the Fine-tune option.

    Open fine-tune action from model row    ${TEST_MODEL_NAME}

The user can submit the fine-tuning form without a token
    [Documentation]    Fills in the display name and submits the wizard for a re-fine-tuned
    ...                source, then confirms the HuggingFace token section never appears —
    ...                the source keeps its weights in project storage, so no token is
    ...                requested and the submission is not gated on one.

    Wait For Elements State    ${BASE_MODEL_SELECT_SELECTOR}    visible    timeout=15s
    Click fine-tuning wizard next button
    Select first training dataset
    Click fine-tuning wizard next button
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    Fill finetune display name    refinetune-${suffix}
    Click fine-tuning wizard next button
    Click fine-tuning wizard next button
    Click finetune wizard submit button
    HF token section should not be present

Fine-tuning wizard should be open
    [Documentation]    Verifies the fine-tuning wizard is visible (base model select is shown).

    Wait For Elements State    ${BASE_MODEL_SELECT_SELECTOR}    visible    timeout=15s

The base model selector should be locked to the completed model
    [Documentation]    Verifies the base model selector is disabled and shows the completed
    ...    model's name, proving the row action pre-selected the correct model rather than
    ...    locking on an unrelated state (e.g., no-recipes lock).

    Wait For Elements State    ${BASE_MODEL_SELECT_SELECTOR}    disabled    timeout=10s
    ${selector_text}=    Get Text    ${BASE_MODEL_SELECT_SELECTOR}
    Should Contain    ${selector_text}    ${TEST_MODEL_NAME}
    ...    msg=Base model selector should show the completed model name but shows: ${selector_text}

# =============================================================================
# Keywords for paginated fine-tune models table
# =============================================================================

The fine-tune models table shows the first page of fine-tuned models
    [Documentation]    Verifies the table renders only one page worth of rows on initial load,
    ...                proving the UI consumed the paginated envelope and did not eagerly fetch
    ...                every fine-tuned model. Default page size is 10.
    Wait for fine-tune models table to load
    ${row_count}=    Get fine-tune models row count
    Should Be True    ${row_count} <= 10
    ...    msg=Expected at most 10 rows on the first page; got ${row_count}
    # Remember the first row's text so the next-page assertion can prove the page changed.
    ${first_row_text}=    Get fine-tune models first row text
    VAR    ${PAGE_1_FIRST_ROW_TEXT}    ${first_row_text}    scope=TEST

Pagination controls are visible on the fine-tune models table
    [Documentation]    Verifies the pagination component is rendered. It only appears when
    ...                the total count exceeds the page size, so this implicitly checks
    ...                that the UI received pagination metadata from the envelope.
    Wait for fine-tune models pagination controls

User navigates to the next page of fine-tune models
    [Documentation]    Clicks the next-page control on the pagination component, triggering
    ...                a new fetch for page 2.
    Click fine-tune models next page button

The fine-tune models table shows the next page of fine-tuned models
    [Documentation]    Verifies that navigating to page 2 changed the rendered set — the first
    ...                row's text must differ from what was shown on page 1.
    Wait for fine-tune models table to load
    Wait Until Keyword Succeeds    10s    500ms    Fine-tune models first row should differ from page 1

Fine-tune models first row should differ from page 1
    [Documentation]    Single-poll check used by Wait Until Keyword Succeeds. Fails when the
    ...                first row text still matches the text captured on page 1.
    ${current}=    Get fine-tune models first row text
    Should Not Be Equal    ${current}    ${PAGE_1_FIRST_ROW_TEXT}
    ...    msg=First row on page 2 should differ from page 1 (${PAGE_1_FIRST_ROW_TEXT})

# =============================================================================
# Keywords for custom-model deploy drawer
# =============================================================================

User opens the deploy drawer for the custom model
    [Documentation]    Finds the ready custom model's row in the fine-tune models table,
    ...                opens its row actions menu, and clicks the Deploy option.
    ...                Returns after the menu action; scenarios should assert drawer
    ...                visibility in Then steps (e.g. ``Wait for custom model deploy drawer``).
    ...                Requires: TEST_MODEL_NAME (set by "A completed fine-tuned model exists for the test project")

    Open deploy action from model row    ${TEST_MODEL_NAME}

The deploy drawer should show the custom model's details
    [Documentation]    Verifies the deploy drawer header shows the custom model name
    ...                and the namespace (deploy target) so the user knows which model
    ...                and where it will be deployed.
    ...                Requires: TEST_MODEL_NAME

    Wait for custom model deploy drawer
    Deploy drawer header should show model name    ${TEST_MODEL_NAME}
    Deploy drawer header should show namespace

The deploy drawer should offer a deployment name and autoscaling
    [Documentation]    Verifies the deploy drawer contains the deployment-name input
    ...                and the autoscaling toggle — the two primary user-controlled
    ...                settings in the custom deploy drawer.

    Deploy drawer should show display name input
    Deploy drawer should show autoscaling toggle

User deploys the model with default settings
    [Documentation]    Submits the deploy drawer without modifying any field,
    ...                accepting all default values (empty display name, autoscaling off).
    ...                Waits for the drawer to close, which signals the deploy mutation
    ...                completed successfully and the success toast was shown.

    Submit custom model deploy drawer
    Wait Until Keyword Succeeds    30s    2s    Custom model deploy drawer should be closed

A deployment for the custom model should exist in the project
    [Documentation]    Verifies via the AIWB API that an AIMService CR was created in
    ...                the project namespace referencing the fine-tuned model.
    ...                Polls to tolerate the short lag between UI form submit and K8s
    ...                reconciliation.
    ...                Requires: TEST_MODEL_NAME

    Wait Until Keyword Succeeds    2 min    10s
    ...    AIMService should reference model    ${TEST_MODEL_NAME}

The deployed model should be ready to chat
    [Documentation]    Verifies the AIMService created from the custom model appears in
    ...                the AIWB inference list filtered to chat-capable deployments.
    ...                Polls until the service is chat-accessible (requires GPU — the
    ...                service must be Running before it surfaces in the chat filter).
    ...                Requires: TEST_AIM_ID (set by "A deployment for the custom model should exist in the project")

    Wait Until Keyword Succeeds    30 min    30s
    ...    Deployed fine-tuned model should be accessible for inference

AIMService should reference model
    [Documentation]    Single-poll check used by Wait Until Keyword Succeeds.
    ...                Searches the AIM services list for an entry whose spec.model.name
    ...                matches the expected fine-tuned model resource name, then stores
    ...                the AIMService ID in TEST_AIM_ID for subsequent steps.
    [Arguments]    ${model_resource_name}
    ${namespace}=    Get Project Namespace
    ${existing}=    Find Existing Fine-Tuned AIM Service    ${namespace}    ${model_resource_name}
    Should Not Be Equal    ${existing}    ${None}
    ...    msg=No AIMService found referencing fine-tuned model '${model_resource_name}' in namespace ${namespace}
    ${service_id}=    Get From Dictionary    ${existing}    id
    VAR    ${TEST_AIM_ID}    ${service_id}    scope=TEST
    Log    AIMService ${service_id} found for model ${model_resource_name}    INFO
