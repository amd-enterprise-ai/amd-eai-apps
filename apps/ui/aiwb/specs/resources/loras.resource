# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for the project LoRA adapter listing.
...                 Composes API preconditions and page-level interactions.
Resource            common/session.resource
Resource            pages/loras_page.resource
Resource            pages/models_page.resource
Resource            pages/workloads_page.resource
Resource            resources/aiwb_adapters.resource
Resource            resources/aiwb_adapter_serving.resource
Resource            resources/aiwb_aims.resource


*** Variables ***
${UI_LORAS_PAGE_SIZE}    10
${UI_PAGINATION_LORA_COUNT}    11


*** Keywords ***
User is on LoRAs page
    [Documentation]    Opens the selected project's registered adapter list.

    Navigate to LoRAs page    ${TEST_PROJECT}[name]

The project contains more LoRA adapters than fit on a single page
    [Documentation]    Creates enough registered adapters to require pagination.

    Multiple adapter artifacts exist in the project    count=${UI_PAGINATION_LORA_COUNT}

A registered LoRA adapter exists in the project
    [Documentation]    Creates a registered adapter for details scenarios.

    A fine-tuning adapter artifact exists in the project

Several registered LoRA adapters exist in the project
    [Documentation]    Creates adapters with distinct names for list filtering.

    A fine-tuning adapter artifact exists in the project
    VAR    ${TEST_LORA_SEARCH_TARGET}    ${TEST_ADAPTER_NAME}    scope=TEST
    A fine-tuning adapter artifact exists in the project

A registered LoRA adapter that is not in use exists in the project
    [Documentation]    Creates a registered adapter without a referencing deployment.

    A fine-tuning adapter artifact exists in the project

An unready LoRA adapter exists in the project
    [Documentation]    Registers an adapter without uploading its weights.

    An adapter registered for upload whose weights never arrived

A registered LoRA adapter in use by a deployment exists in the project
    [Documentation]    Creates an adapter and a deployment that references it.

    A fine-tuning adapter artifact exists in the project
    An AIM deployment attaching the adapter artifact exists in the project

A dynamic LoRA deployment exists in the project
    [Documentation]    Deploys a model with dynamic adapter support and a rank ceiling.

    ${deploy_data}=    Valid AIM deploy data is prepared
    Remove From Dictionary    ${deploy_data}    profileName
    VAR    ${rank}    ${16}
    Set To Dictionary
    ...    ${deploy_data}
    ...    maxLoraRank=${rank}
    ...    adapterMode=dynamic
    Deploy The Selected Model With    ${deploy_data}    expected_status=202
    VAR    ${TEST_DYNAMIC_LORA_RANK}    ${rank}    scope=TEST

A running deployment already serving a compatible adapter exists
    [Documentation]    Deploys the selected model with its compatible adapter already attached.

    The model is deployed with a compatible adapter attached
    The deployment should become ready and serve the adapter
    VAR    ${TEST_ADAPTER_NAME}    ${TEST_SERVABLE_ADAPTER_NAME}    scope=TEST

An eligible running deployment with no adapters exists
    [Documentation]    Deploys the selected model onto adapter-capable hardware with dynamic
    ...    adapter support enabled and no adapters attached, then waits for it to run — a
    ...    deployment the registered adapter can be attached to.

    The model is deployed onto that hardware with no adapters but free to change them
    Wait for AIM workload to be running
    VAR    ${TEST_ADAPTER_NAME}    ${TEST_SERVABLE_ADAPTER_NAME}    scope=TEST

A running deployment that cannot accept the adapter exists
    [Documentation]    Deploys the selected model without dynamic adapter support, so it is
    ...    visible in attachment choices but unavailable to receive the registered adapter.

    The model is deployed without adapters and cannot change them
    VAR    ${TEST_ADAPTER_NAME}    ${TEST_SERVABLE_ADAPTER_NAME}    scope=TEST

Base weights and hardware of the variant these scenarios serve on
    [Documentation]    Returns the base model id published by the variant these scenarios pin for
    ...    serving, together with the precision that variant runs at. The model's own grouping id
    ...    spans several variants that load different weights, so it is not something an adapter
    ...    can be matched against; only the chosen variant names the weights that will actually be
    ...    loaded.
    ...
    ...    The precision comes back alongside because it is the axis a deployment is steered onto
    ...    a variant by, and the two have to name the same variant: an adapter seeded for one
    ...    variant and judged against another is withheld for a reason the scenario is not about.

    ${aim_id}=    Wait Until Keyword Succeeds    2 min    5 sec
    ...    Resolve Cluster Model aimId    ${TEST_AIM_NAME}
    ${response}=    List AIM Profiles    ${aim_id}    expected_status=200
    VAR    ${variants}    ${response.json()}[data]
    FOR    ${variant}    IN    @{variants}
        ${variant_name}=    Evaluate    $variant.get('metadata', {}).get('name')
        IF    '${variant_name}' == '${TEST_ADAPTER_CAPABLE_PROFILE_NAME}'
            ${model_id}=    Evaluate    $variant.get('spec', {}).get('modelId')
            ${precision}=    Evaluate    $variant.get('spec', {}).get('precision')
            Should Not Be Empty    ${model_id}
            ...    msg=Variant '${variant_name}' names no base weights, so no adapter can match it
            Should Not Be Empty    ${precision}
            ...    msg=Variant '${variant_name}' names no precision, so no deployment can be steered onto it
            RETURN    ${model_id}    ${precision}
        END
    END
    Fail    Variant '${TEST_ADAPTER_CAPABLE_PROFILE_NAME}' is absent from the catalog for '${aim_id}'

An adapter an available variant of the model can serve exists in the project
    [Documentation]    Seeds a ready adapter declaring the base weights of the very variant the
    ...    deployment will run, the way a fine-tuning run against that variant leaves one behind.
    ...    The declaration is read off the chosen variant at test time rather than off the model,
    ...    because the model groups variants that load different weights and an adapter is only
    ...    servable when it and the loaded weights agree. Its weights are written to storage
    ...    first: an adapter with nothing to download is withheld for being unready, which would
    ...    let the scenario pass without the lineage ever being consulted.

    ${namespace}=    Get Project Namespace
    ${model_id}    ${precision}=    Base weights and hardware of the variant these scenarios serve on
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${name}    e2e-serves-${suffix}
    VAR    ${display_name}    E2E LoRA adapter
    ${uri}=    Write Adapter Weights To Project Storage    ${namespace}    ${name}
    Track Adapter Weights For Cleanup    ${namespace}    ${uri}
    Apply AIMArtifact CR
    ...    ${name}
    ...    ${namespace}
    ...    compatible_with=${model_id}
    ...    display_name=${display_name}
    ...    rank=${ADAPTER_RANK}
    Track Adapter Artifact For Cleanup    ${namespace}    ${name}
    VAR    ${TEST_SERVABLE_ADAPTER_NAME}    ${name}    scope=TEST
    VAR    ${TEST_SERVABLE_ADAPTER_DISPLAY_NAME}    ${display_name}    scope=TEST
    VAR    ${TEST_SERVABLE_ADAPTER_RANK}    ${ADAPTER_RANK}    scope=TEST
    VAR    ${TEST_SERVABLE_ADAPTER_PRECISION}    ${precision}    scope=TEST

An adapter no available variant of the model can serve exists in the project
    [Documentation]    Seeds a ready adapter whose declared base weights belong to a lineage none
    ...    of the model's variants provide. Its weights are written to storage first: an adapter
    ...    with nothing to download is withheld for being unready, which would let the scenario
    ...    pass without the lineage ever being consulted.

    ${namespace}=    Get Project Namespace
    ${suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${name}    e2e-unservable-${suffix}
    VAR    ${display_name}    Unservable LoRA adapter
    ${uri}=    Write Adapter Weights To Project Storage    ${namespace}    ${name}
    Track Adapter Weights For Cleanup    ${namespace}    ${uri}
    Apply AIMArtifact CR
    ...    ${name}
    ...    ${namespace}
    ...    compatible_with=${ADAPTER_OTHER_BASE_MODEL_ID}
    ...    display_name=${display_name}
    ...    rank=${ADAPTER_RANK}
    Track Adapter Artifact For Cleanup    ${namespace}    ${name}
    VAR    ${TEST_UNSERVABLE_ADAPTER_NAME}    ${name}    scope=TEST
    VAR    ${TEST_UNSERVABLE_ADAPTER_DISPLAY_NAME}    ${display_name}    scope=TEST

User sets up a deployment of that model on the hardware that adapter was trained for
    [Documentation]    Opens the catalog deploy wizard for the selected model and steers it onto
    ...    the variant the seeded adapter declares, the way a user who knows which hardware their
    ...    adapter was trained for would.
    ...
    ...    Left to choose for itself the wizard considers only the variants matching the model's
    ...    default precision, which need not include the one the adapter names — the adapter would
    ...    then be withheld for being judged against weights it was never trained for, and the
    ...    scenario would report a verdict it did not mean to ask for. Steering by precision is
    ...    what makes the two name the same variant, because a model's variants are exactly its
    ...    quantisations and each names its own weights.

    Navigate to models page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]
    Click deploy button on card    ${TEST_AIM_DISPLAY_NAME}
    Wait for deploy wizard
    Expand advanced profile parameters
    Select deploy precision override    ${TEST_SERVABLE_ADAPTER_PRECISION}

User chooses adapters for that deployment
    [Documentation]    Advances the wizard to the step where adapters are chosen, with dynamic
    ...    adapter support switched on.

    Click deploy wizard next
    Enable dynamic LoRA adapters
    Wait for deploy wizard LoRA adapter choices

That adapter should not be offered
    [Documentation]    Verifies an adapter the model's variants cannot serve is withheld, while
    ...    the picker is demonstrably populated — an empty picker would satisfy the absence
    ...    check without the filter having run.

    ${offered}=    Deploy wizard LoRA adapter row is visible
    ...    ${TEST_UNSERVABLE_ADAPTER_DISPLAY_NAME}
    Should Be Equal    ${offered}    ${FALSE}
    ${servable}=    Deploy wizard LoRA adapter row is visible
    ...    ${TEST_SERVABLE_ADAPTER_DISPLAY_NAME}
    Should Be Equal    ${servable}    ${TRUE}

The adapter should be offered
    [Documentation]    Verifies an adapter a servable variant can load is present in the picker.

    ${offered}=    Deploy wizard LoRA adapter row is visible
    ...    ${TEST_SERVABLE_ADAPTER_DISPLAY_NAME}
    Should Be Equal    ${offered}    ${TRUE}

User attaches that adapter and deploys the model
    [Documentation]    Selects the servable adapter in the picker and completes the wizard.

    Select LoRA adapter named "${TEST_SERVABLE_ADAPTER_DISPLAY_NAME}"
    Click deploy wizard next
    Click deploy wizard next
    Click deploy wizard next
    Submit deploy wizard
    The deployment created through the wizard is tracked

The deployment should start and serve the adapter
    [Documentation]    Verifies the deployment reaches a running state carrying the adapter,
    ...    which is the outcome an adapter the engine refuses never reaches.

    The deployment should become ready and serve the adapter

User looks for adapters to attach to that deployment
    [Documentation]    Opens the running deployment's adapter editor from its details page.

    Navigate to AIM details page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]    ${TEST_AIM_ID}
    Open LoRA adapters editor

Only adapters that deployment can serve should be offered
    [Documentation]    Verifies the editor offers the adapter this deployment's weights can load
    ...    and withholds the one belonging to a different lineage.

    ${servable}=    LoRA adapters editor row is visible
    ...    ${TEST_SERVABLE_ADAPTER_DISPLAY_NAME}
    Should Be Equal    ${servable}    ${TRUE}
    ${unservable}=    LoRA adapters editor row is visible
    ...    ${TEST_UNSERVABLE_ADAPTER_DISPLAY_NAME}
    Should Be Equal    ${unservable}    ${FALSE}

User deploys the model with dynamic LoRA adapters and maximum rank "${rank}"
    [Documentation]    Completes the catalog deployment wizard with a selected adapter and rank.

    Navigate to models page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]
    Click deploy button on card    ${TEST_AIM_DISPLAY_NAME}
    Wait for deploy wizard
    Click deploy wizard next
    Enable dynamic LoRA adapters
    Select maximum LoRA rank    ${rank}
    Select LoRA adapter named "${TEST_SERVABLE_ADAPTER_DISPLAY_NAME}"
    Click deploy wizard next
    Click deploy wizard next
    Click deploy wizard next
    Submit deploy wizard
    The deployment created through the wizard is tracked

User views project deployments
    [Documentation]    Opens the selected project's Dashboard workloads list.

    Navigate to dashboard    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

The dynamic LoRA deployment should describe its profile and adapter capacity
    [Documentation]    Verifies the profile summary includes resolved profile data and the rank ceiling.

    Wait Until Keyword Succeeds    2 min    3s
    ...    The dynamic LoRA deployment profile summary should be visible

The dynamic LoRA deployment profile summary should be visible
    [Documentation]    Single-poll check for the asynchronously resolved deployment profile.

    ${summary}=    Get workload name cell text    ${TEST_AIM_ID}
    Should Contain    ${summary}    •
    Should Contain    ${summary}    max rank ${TEST_DYNAMIC_LORA_RANK}

LoRA adapters should be listed with their base models
    [Documentation]    Verifies a registered adapter and its compatible model are visible.

    ${row_text}=    Get LoRA row text    ${TEST_ADAPTER_NAME}
    Should Contain    ${row_text}    ${ADAPTER_BASE_MODEL_ID}

The adapter should show no deployments
    [Documentation]    Verifies an unused adapter has no deployment count.

    ${count}=    Get LoRA deployment count text    ${TEST_ADAPTER_NAME}
    Should Be Equal    ${count}    —

The adapter should show one deployment
    [Documentation]    Verifies the adapter's deployment usage is visible.

    ${count}=    Get LoRA deployment count text    ${TEST_ADAPTER_NAME}
    Should Be Equal As Integers    ${count}    1

The running LoRA fine-tuning job should be listed
    [Documentation]    Verifies the active adapter-output job appears with its workload status.

    Wait Until Keyword Succeeds
    ...    30s
    ...    2s
    ...    The running LoRA fine-tuning job row should be visible

The running LoRA fine-tuning job row should be visible
    [Documentation]    Single-poll check used while the workload list refreshes.

    ${row_text}=    Get LoRA row text    ${TEST_FINETUNING_DISPLAY_NAME}
    Should Contain    ${row_text}    Running

The running LoRA fine-tuning job should not be listed
    [Documentation]    Verifies adapter-output jobs are excluded from fine-tuned models.

    ${visible}=    Fine-tune models row is visible    ${TEST_FINETUNING_DISPLAY_NAME}
    Should Be Equal    ${visible}    ${FALSE}

The registered LoRA adapter list should be empty
    [Documentation]    Verifies the project has no registered adapters to display.

    ${visible}=    LoRAs empty state is visible
    Should Be Equal    ${visible}    ${TRUE}

The LoRAs table should show a full first page
    [Documentation]    Verifies one page of registered adapters is visible.

    Wait for LoRAs table to load
    ${count}=    Get LoRA table row count
    Should Be Equal As Integers    ${count}    ${UI_LORAS_PAGE_SIZE}

LoRAs pagination controls should be visible
    [Documentation]    Verifies users can browse beyond the first adapter page.

    ${visible}=    LoRAs pagination is visible
    Should Be Equal    ${visible}    ${TRUE}

The user can navigate to the next LoRAs page
    [Documentation]    Verifies the next page displays a different adapter row.

    ${before}=    Get first LoRA row text
    Click next LoRAs page
    Wait Until Keyword Succeeds
    ...    15s
    ...    1s
    ...    First LoRA row text should differ from
    ...    ${before}

First LoRA row text should differ from
    [Documentation]    Verifies the first row changed after pagination.
    [Arguments]    ${baseline}

    ${current}=    Get first LoRA row text
    Should Not Be Equal    ${current}    ${baseline}

User searches for a LoRA adapter
    [Documentation]    Searches the adapter list for the selected target.

    Search LoRAs    ${TEST_LORA_SEARCH_TARGET}

User manually refreshes the LoRAs list
    [Documentation]    Triggers a manual refresh and waits for the reload to finish.

    Click LoRAs refresh
    Wait for LoRAs table to load

User filters LoRAs by the first adapter's base model
    [Documentation]    Selects the base-model filter option matching the primary test adapter.

    Filter LoRAs by base model    ${ADAPTER_BASE_MODEL_ID}

User opens fine-tuning wizard from LoRAs page
    [Documentation]    Starts a new fine-tuning workflow from the LoRAs toolbar.

    Open fine-tuning wizard from LoRAs

Only the matching LoRA adapter should be listed
    [Documentation]    Verifies search leaves only the selected adapter visible.

    Wait Until Keyword Succeeds    15s    1s
    ...    The matching LoRA adapter should be the only visible row

The matching LoRA adapter should be the only visible row
    [Documentation]    Verifies the target is the sole visible table row.

    ${row_text}=    Get LoRA row text    ${TEST_LORA_SEARCH_TARGET}
    Should Contain    ${row_text}    ${TEST_LORA_SEARCH_TARGET}
    ${count}=    Get LoRA table row count
    Should Be Equal As Integers    ${count}    1

Only the adapter with the selected base model should be listed
    [Documentation]    Verifies the base-model filter hides adapters attached to other models.

    Wait Until Keyword Succeeds    15s    1s
    ...    The matching base model adapter should be the only visible row

The matching base model adapter should be the only visible row
    [Documentation]    Verifies the primary test adapter is shown and the other-model adapter is not.

    ${row_text}=    Get LoRA row text    ${TEST_ADAPTER_NAME}
    Should Contain    ${row_text}    ${ADAPTER_BASE_MODEL_ID}
    ${visible}=    LoRA row is visible    ${TEST_OTHER_ADAPTER_NAME}
    Should Be Equal    ${visible}    ${FALSE}

Unregistered adapter weights should not be listed
    [Documentation]    Verifies storage without a registered adapter stays hidden.

    ${unregistered_name}=    Evaluate
    ...    $TEST_UNCLAIMED_ADAPTER_URI.rstrip('/').rsplit('/', 1)[-1]
    Wait for LoRAs table to load
    ${table_text}=    Get LoRAs table text
    Should Not Contain    ${table_text}    ${unregistered_name}

User opens the adapter details
    [Documentation]    Opens the registered adapter's details from its row actions.

    Navigate to LoRAs page    ${TEST_PROJECT}[name]
    Open LoRA row actions    ${TEST_ADAPTER_NAME}
    Click LoRA details action

User tries to attach the adapter
    [Documentation]    Opens deployment attachment for the registered adapter.

    Navigate to LoRAs page    ${TEST_PROJECT}[name]
    Open LoRA row actions    ${TEST_ADAPTER_NAME}
    Click LoRA attach action

The unready adapter should be unavailable for attachment
    [Documentation]    Verifies an adapter whose weights are not ready cannot be attached.

    Open LoRA row actions    ${TEST_ADAPTER_NAME}
    ${disabled}=    Get LoRA attach action disabled state
    Should Be Equal    ${disabled}    true

User opens the deployment choices
    [Documentation]    Opens the deployment picker in the attachment modal.

    Open LoRA attachment deployment picker

User attaches the adapter to that deployment
    [Documentation]    Opens the attachment modal for the registered adapter, picks the
    ...    eligible running deployment, and confirms attaching it.

    Navigate to LoRAs page    ${TEST_PROJECT}[name]
    Open LoRA row actions    ${TEST_ADAPTER_NAME}
    Click LoRA attach action
    Open LoRA attachment deployment picker
    Select LoRA attachment deployment    ${TEST_DEPLOYED_SERVICE_NAME}
    Confirm LoRA attachment

The attachment should be accepted
    [Documentation]    Verifies the attachment request succeeded.

    LoRA attachment success toast should be visible

The adapter usage count should update to reflect the attachment
    [Documentation]    Waits for the LoRAs table to reflect the newly attached deployment
    ...    once the attachment request completes and the table refreshes.

    Wait Until Keyword Succeeds    30s    2s
    ...    The adapter should show one deployment

The attached deployment should remain visible but unavailable
    [Documentation]    Verifies attached deployments stay discoverable without allowing duplicates.

    ${picker_text}=    Get LoRA attachment deployment picker text
    Should Contain    ${picker_text}    Compatible
    Should Not Contain    ${picker_text}    Incompatible
    ${disabled}=    Get LoRA attachment deployment disabled state    ${TEST_DEPLOYED_SERVICE_NAME}
    Should Be Equal    ${disabled}    true
    ${marked}=    LoRA attachment deployment has attached marker    ${TEST_DEPLOYED_SERVICE_NAME}
    Should Be Equal    ${marked}    ${TRUE}

The incompatible deployment should remain visible but unavailable
    [Documentation]    Verifies a deployment without dynamic adapter support explains why it
    ...    cannot receive the adapter.

    ${picker_text}=    Get LoRA attachment deployment picker text
    Should Contain    ${picker_text}    Incompatible
    Should Contain    ${picker_text}    dynamic adapters disabled
    ${disabled}=    Get LoRA attachment deployment disabled state    ${TEST_DEPLOYED_SERVICE_NAME}
    Should Be Equal    ${disabled}    true

The deployment should show maximum LoRA rank "${rank}"
    [Documentation]    Verifies the rank chosen in the deployment wizard is shown on the
    ...    project dashboard after the deployment has been created.

    Navigate to dashboard    ${UI_BASE_URL}    ${TEST_PROJECT}[name]
    Wait Until Keyword Succeeds    2 min    3s
    ...    Workloads grid should show maximum LoRA rank    ${rank}

Workloads grid should show maximum LoRA rank
    [Documentation]    Performs one dashboard poll for the selected maximum rank.
    [Arguments]    ${rank}

    ${workloads}=    Get workloads grid text
    Should Contain    ${workloads}    max rank ${rank}

The deployment requirements should be explained
    [Documentation]    Verifies the empty state explains how to deploy an eligible model.

    ${message}=    Get LoRA attachment empty state text
    Should Contain    ${message}    No deployments available
    Should Contain    ${message}    ${ADAPTER_BASE_MODEL_ID}
    Should Contain    ${message}    dynamic adapter support
    Should Contain    ${message}    maximum LoRA rank
    Should Contain    ${message}    ${ADAPTER_RANK}

The adapter full details should be displayed
    [Documentation]    Verifies the registered adapter's identifying details are shown.

    Wait Until Keyword Succeeds
    ...    15s
    ...    1s
    ...    The adapter details content should be visible

The adapter details content should be visible
    [Documentation]    Single-poll check used while the details modal loads its content.

    ${details}=    Get LoRA details text
    Should Contain    ${details}    ${TEST_ADAPTER_NAME}
    Should Contain    ${details}    ${ADAPTER_BASE_MODEL_ID}
    Should Contain    ${details}    ${ADAPTER_DESCRIPTION}
User deletes the adapter
    [Documentation]    Opens the adapter delete action and confirms it.

    Open LoRA row actions    ${TEST_ADAPTER_NAME}
    Click LoRA delete action
    Confirm LoRA deletion

User opens the adapter actions
    [Documentation]    Opens the registered adapter's row actions.

    Open LoRA row actions    ${TEST_ADAPTER_NAME}

User attempts to delete the adapter
    [Documentation]    Confirms deletion for an adapter whose use should block removal.

    User deletes the adapter

User cancels the running LoRA fine-tuning job
    [Documentation]    Opens the active job's delete action and confirms cancellation.

    Open LoRA row actions    ${TEST_FINETUNING_DISPLAY_NAME}
    Click LoRA delete action
    Confirm LoRA deletion

The running LoRA fine-tuning job should no longer be listed
    [Documentation]    Verifies cancellation feedback and removal from the LoRAs table.

    ${success_visible}=    LoRA cancel success is visible
    Should Be Equal    ${success_visible}    ${TRUE}
    Wait Until Keyword Succeeds    30s    2s
    ...    The running LoRA fine-tuning job row should be absent

The running LoRA fine-tuning job row should be absent
    [Documentation]    Verifies the canceled job row is not visible.

    ${visible}=    LoRA row is visible    ${TEST_FINETUNING_DISPLAY_NAME}
    Should Be Equal    ${visible}    ${FALSE}

The adapter should no longer be listed
    [Documentation]    Verifies successful deletion is reflected in the LoRAs table.

    ${success_visible}=    LoRA delete success is visible
    Should Be Equal    ${success_visible}    ${TRUE}
    Wait Until Keyword Succeeds    30s    2s
    ...    The adapter row should be absent

The adapter row should be absent
    [Documentation]    Verifies the deleted adapter row is not visible.

    ${visible}=    LoRA row is visible    ${TEST_ADAPTER_NAME}
    Should Be Equal    ${visible}    ${FALSE}

The deletion should be blocked with an explanation of what is using it
    [Documentation]    Verifies the blocking deployment is named and the adapter remains listed.

    ${error_text}=    Get LoRA delete error text    ${TEST_BLOCKING_SERVICE_NAME}
    Should Contain    ${error_text}    ${TEST_BLOCKING_SERVICE_NAME}
    ${visible}=    LoRA row is visible    ${TEST_ADAPTER_NAME}
    Should Be Equal    ${visible}    ${TRUE}

The adapter delete action should be disabled
    [Documentation]    Verifies an adapter in use cannot be deleted.

    ${state}=    Get LoRA delete action disabled state
    Should Be Equal    ${state}    true
