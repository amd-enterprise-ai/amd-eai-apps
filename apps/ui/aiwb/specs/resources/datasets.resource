# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for dataset UI features.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)
Library             String
Resource            common/session.resource
Resource            pages/datasets_page.resource
Resource            resources/aiwb_datasets.resource


*** Variables ***
${UI_DATASET_FILE}    ${EXECDIR}/test_data/datasets/sample.jsonl
${UI_LARGE_DATASET_FILE}    ${EXECDIR}/test_data/datasets/large-sample.jsonl
# Default UI page size is 10; uploading 11 forces a second page.
${UI_DATASETS_PAGE_SIZE}    10
${UI_PAGINATION_DATASET_COUNT}    11


*** Keywords ***
# =============================================================================
# Given keywords (UI preconditions)
# =============================================================================

User is on datasets page
    [Documentation]    Navigates to the Datasets page via the sidebar link.
    ...                Expects ${TEST_PROJECT} to be set.

    Navigate to datasets page    ${TEST_PROJECT}[name]

The project contains more datasets than fit on a single page
    [Documentation]    Uploads enough datasets to spill onto a second page so the
    ...                pagination UI is exercised. Uses the existing API-level
    ...                ``Multiple datasets exist`` keyword for the actual upload.

    Multiple datasets exist    count=${UI_PAGINATION_DATASET_COUNT}

Datasets of different sizes exist
    [Documentation]    Uploads two datasets with distinct file sizes and tracks them for cleanup.
    ${random_suffix}=    Generate Random String    8    [LOWER][NUMBERS]
    VAR    ${small_name}    e2e-small-${random_suffix}
    VAR    ${large_name}    e2e-large-${random_suffix}
    ${namespace}=    Get Project Namespace
    ${small_response}=    Upload dataset
    ...    jsonl_file_path=${UI_DATASET_FILE}
    ...    name=${small_name}
    ...    namespace=${namespace}
    ...    description=Small dataset
    ...    dataset_type=Fine-tuning
    ...    expected_status=200
    ${large_response}=    Upload dataset
    ...    jsonl_file_path=${UI_LARGE_DATASET_FILE}
    ...    name=${large_name}
    ...    namespace=${namespace}
    ...    description=Large dataset
    ...    dataset_type=Fine-tuning
    ...    expected_status=200
    VAR    ${small_dataset}    ${small_response.json()}
    VAR    ${large_dataset}    ${large_response.json()}
    Track Dataset For Cleanup    ${small_dataset}[id]
    Track Dataset For Cleanup    ${large_dataset}[id]
    VAR    ${UI_SMALL_DATASET_NAME}    ${small_name}    scope=TEST
    VAR    ${UI_LARGE_DATASET_NAME}    ${large_name}    scope=TEST

# =============================================================================
# When keywords (actions)
# =============================================================================

User uploads a dataset through the UI
    [Documentation]    Uploads a dataset via the upload modal with a unique name.
    ...                Stores the generated name in ${UI_UPLOADED_DATASET_NAME} for verification.
    ...                Retries the full sequence because the modal can close on React re-renders.

    ${random_suffix}=    Generate Random String    8    [LETTERS][NUMBERS]
    VAR    ${name}    e2e-ui-upload-${random_suffix}
    Set Test Variable    ${UI_UPLOADED_DATASET_NAME}    ${name}
    Wait Until Keyword Succeeds    60s    3s    Open fill and submit upload form    ${name}

Open fill and submit upload form
    [Documentation]    Opens the upload modal, fills fields, selects a file, and submits.
    ...                Designed to be retried as a unit if the modal closes unexpectedly.
    [Arguments]    ${name}

    # Dismiss any modal left open from a previous failed attempt
    ${modal_open}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${UPLOAD_MODAL_TITLE}    visible    timeout=1s
    IF    ${modal_open}
        Keyboard Key    press    Escape
        Wait For Elements State    ${UPLOAD_MODAL_TITLE}    hidden    timeout=5s
    END

    Click upload button
    Fill dataset name    ${name}
    Select dataset file    ${UI_DATASET_FILE}
    Submit upload form
    Upload success toast should be visible

User triggers download for dataset "${dataset_name}"
    [Documentation]    Clicks the Download action in the row actions menu for the given dataset.

    Click download action on dataset row    ${dataset_name}

User dismisses the download indicator
    [Documentation]    Clicks the dismiss button on the download indicator and waits for it
    ...                to disappear.

    Click dismiss on download indicator
    Download indicator should be hidden

# =============================================================================
# Then keywords (verification)
# =============================================================================

Download indicator should be in preparing state
    [Documentation]    Verifies the download indicator shows the preparing state.

    Download indicator preparing state should be visible

Download indicator should be in done state
    [Documentation]    Verifies the download indicator transitions to the done state.

    Download indicator done state should be visible

Download indicator should not be visible
    [Documentation]    Verifies the download indicator is fully hidden.

    Download indicator should be hidden

Download indicator should not reappear after dismissal
    [Documentation]    Verifies the "Download ready" indicator does not appear after the indicator
    ...                was dismissed. Waits long enough for any in-flight download to complete,
    ...                confirming the dismissed state is permanent.

    Download done indicator should not appear within    15s

The uploaded dataset should appear in the dataset list
    [Documentation]    Verifies the UI-uploaded dataset appears in the table.

    Dataset row should be visible in table    ${UI_UPLOADED_DATASET_NAME}

Datasets should be listed with their metadata
    [Documentation]    Verifies the datasets table shows rows with name and type metadata.

    Dataset table should have rows
    Dataset row should contain metadata    ${TEST_DATASET}[name]    Fine-tuning

Dataset file sizes should be displayed
    [Documentation]    Verifies both dataset rows show a human-readable file size.
    ${small_row}=    Get dataset row text    ${UI_SMALL_DATASET_NAME}
    ${large_row}=    Get dataset row text    ${UI_LARGE_DATASET_NAME}
    Should Match Regexp    ${small_row}    \\d+(\\.\\d{2})? (B|KB|MB|GB|TB|PB)
    Should Match Regexp    ${large_row}    \\d+(\\.\\d{2})? (B|KB|MB|GB|TB|PB)

Track UI uploaded dataset for cleanup
    [Documentation]    Looks up the UI-uploaded dataset by name via API and tracks its ID
    ...                for cleanup at suite teardown. Silently skips if test variables are not set.

    ${name}=    Get Variable Value    ${UI_UPLOADED_DATASET_NAME}    ${None}
    IF    $name is None    RETURN
    TRY
        ${namespace}=    Get Project Namespace
        ${response}=    List datasets    ${namespace}    name=${name}    expected_status=200
        ${datasets}=    Evaluate    ${response.json()}["data"]
        ${length}=    Get Length    ${datasets}
        IF    ${length} > 0
            VAR    ${dataset_id}    ${datasets}[0][id]
            Track Dataset For Cleanup    ${dataset_id}
        END
    EXCEPT    AS    ${error}
        Log    Could not track UI-uploaded dataset for cleanup: ${error}    WARN
    END

The datasets table shows the first page of datasets
    [Documentation]    Verifies the dataset table contains exactly one page worth of rows.
    ...                With ${UI_PAGINATION_DATASET_COUNT} datasets uploaded and a page
    ...                size of ${UI_DATASETS_PAGE_SIZE}, the first page must be full.

    Dataset table should have rows
    Dataset table row count should equal    ${UI_DATASETS_PAGE_SIZE}

Pagination controls should be visible
    [Documentation]    Verifies the table's pagination navigation widget renders.

    Datasets pagination controls should be visible

The user can navigate to the next page
    [Documentation]    Clicks "next" on the pagination control and asserts that the
    ...                table re-renders with a different set of rows. Compares the
    ...                first row's text before and after to detect a real page swap
    ...                without coupling to specific dataset names.

    ${before}=    Get first dataset row text
    Click next page in datasets pagination
    Wait until first dataset row text changes from    ${before}
