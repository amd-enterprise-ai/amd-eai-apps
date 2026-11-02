# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for the AIWB Datasets page.
...                 Contains selectors and atomic browser interactions only.
...                 Business logic and assertions belong in feature resources.


*** Variables ***
${DATASETS_PATH}                    /fine-tuning/datasets

# Page elements
${DATASETS_PAGE_TABLE}              css=table

# Row actions
${ROW_ACTIONS_BUTTON}               button[aria-label="Actions"]
${DOWNLOAD_ACTION_ITEM}             text="Download"

# Upload modal elements
${UPLOAD_BUTTON}                    css=button[aria-label="Upload"]
${UPLOAD_MODAL_TITLE}               text="Upload a dataset"
${UPLOAD_NAME_INPUT}                css=[data-testid="datasetName"]
${UPLOAD_FILE_INPUT}                css=input[type="file"][accept=".jsonl"]
${UPLOAD_CONFIRM_BUTTON}            css=[data-testid="modal-confirm"]
${UPLOAD_SUCCESS_TOAST}             text="Dataset successfully uploaded"

# Download indicator elements
${DOWNLOAD_INDICATOR_PREPARING}     text="Preparing download"
${DOWNLOAD_INDICATOR_DONE}          text="Download ready"
${DOWNLOAD_INDICATOR_DISMISS}       css=[data-slot="toast"]:has-text("Preparing download") >> css=button[aria-label="Close"]

# Pagination elements (HeroUI Pagination component default ARIA).
# Verified against @heroui/pagination dist/use-pagination.js — defaults are
# "pagination navigation" for the nav wrapper and "next page button" /
# "previous page button" for the controls.
${DATASETS_PAGINATION_NAV}          css=nav[aria-label="pagination navigation"]
${DATASETS_PAGINATION_NEXT}         css=nav[aria-label="pagination navigation"] button[aria-label="next page button"]
${DATASETS_FIRST_ROW}               css=table tbody tr:first-of-type


*** Keywords ***
Navigate to datasets page
    [Documentation]    Navigates to the Datasets page via the sidebar link.
    ...                Retries because SPA navigation can fail during project context
    ...                initialization.
    [Arguments]    ${project}

    Wait Until Keyword Succeeds    30s    2s    Navigate to datasets via sidebar    ${project}

Navigate to datasets via sidebar
    [Documentation]    Clicks the sidebar Datasets link and verifies the table loaded.
    [Arguments]    ${project}

    VAR    ${sidebar_link}    css=a[href="/${project}${DATASETS_PATH}"]
    Wait For Elements State    ${sidebar_link}    visible    timeout=5s
    Click    ${sidebar_link}
    Wait for datasets page

Wait for datasets page
    [Documentation]    Waits for the Datasets table to become visible.

    Wait For Elements State    ${DATASETS_PAGE_TABLE}    visible    timeout=15s

Click download action on dataset row
    [Documentation]    Opens the row actions menu for the given dataset and clicks Download.
    [Arguments]    ${dataset_name}

    VAR    ${row}    css=table tbody tr:has-text("${dataset_name}")
    ${actions_btn}=    Get Element    ${row} >> css=${ROW_ACTIONS_BUTTON}
    Click    ${actions_btn}
    Wait For Elements State    ${DOWNLOAD_ACTION_ITEM}    visible    timeout=5s
    Click    ${DOWNLOAD_ACTION_ITEM}

Download indicator preparing state should be visible
    [Documentation]    Verifies the download indicator is visible in the preparing state.

    Wait For Elements State    ${DOWNLOAD_INDICATOR_PREPARING}    visible    timeout=10s

Download indicator done state should be visible
    [Documentation]    Verifies the download indicator transitions to the done state.
    ...                Uses a generous timeout to account for download duration.

    Wait For Elements State    ${DOWNLOAD_INDICATOR_DONE}    visible    timeout=60s

Download indicator should be hidden
    [Documentation]    Verifies neither the preparing nor done indicator is visible.

    Wait For Elements State    ${DOWNLOAD_INDICATOR_PREPARING}    hidden    timeout=15s
    Wait For Elements State    ${DOWNLOAD_INDICATOR_DONE}    hidden    timeout=15s

Click dismiss on download indicator
    [Documentation]    Clicks the dismiss button on the download indicator.

    Wait For Elements State    ${DOWNLOAD_INDICATOR_DISMISS}    visible    timeout=10s
    Click    ${DOWNLOAD_INDICATOR_DISMISS}

Download done indicator should not appear within
    [Documentation]    Asserts the "Download ready" indicator never becomes visible during
    ...                the given window. Used to verify a dismissed indicator does not reappear
    ...                once the in-flight download resolves.
    ...                Works by waiting for the element to become visible (which should time out)
    ...                and asserting that wait failed — i.e., the element never appeared.
    [Arguments]    ${timeout}=15s

    ${appeared}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${DOWNLOAD_INDICATOR_DONE}    visible    timeout=${timeout}
    Should Be Equal    ${appeared}    ${FALSE}
    ...    msg=Download indicator reappeared after dismiss — in-flight handler ignored the dismissed ref

Click upload button
    [Documentation]    Clicks the Upload button to open the upload modal.
    ...                Waits for the modal opening animation to settle before returning.

    Wait For Elements State    ${UPLOAD_BUTTON}    visible    timeout=10s
    Click    ${UPLOAD_BUTTON}
    Wait For Elements State    ${UPLOAD_MODAL_TITLE}    visible    timeout=10s
    Wait For Elements State    ${UPLOAD_CONFIRM_BUTTON}    stable    timeout=10s

Fill dataset name
    [Documentation]    Fills in the dataset name in the upload modal.
    [Arguments]    ${name}

    Wait For Elements State    ${UPLOAD_NAME_INPUT}    visible    timeout=10s
    Wait For Elements State    ${UPLOAD_NAME_INPUT}    stable    timeout=5s
    Click    ${UPLOAD_NAME_INPUT}
    Fill Text    ${UPLOAD_NAME_INPUT}    ${name}
    Get Text    ${UPLOAD_NAME_INPUT}    ==    ${name}

Select dataset file
    [Documentation]    Selects a file for upload via the file input.
    [Arguments]    ${file_path}

    Upload File By Selector    ${UPLOAD_FILE_INPUT}    ${file_path}

Submit upload form
    [Documentation]    Clicks the confirm button on the upload modal.
    ...                Waits for the name uniqueness check to finish before clicking.

    Wait For Elements State    ${UPLOAD_CONFIRM_BUTTON}    enabled    timeout=10s
    Click    ${UPLOAD_CONFIRM_BUTTON}

Upload success toast should be visible
    [Documentation]    Verifies the success toast appears after upload.

    Wait For Elements State    ${UPLOAD_SUCCESS_TOAST}    visible    timeout=30s

Dataset row should be visible in table
    [Documentation]    Verifies a dataset with the given name appears in the table.
    [Arguments]    ${dataset_name}

    VAR    ${row}    css=table tbody tr:has-text("${dataset_name}")
    Wait For Elements State    ${row}    visible    timeout=15s

Dataset table should have rows
    [Documentation]    Verifies the dataset table contains at least one data row.

    VAR    ${rows}    css=table tbody tr
    Wait For Elements State    ${rows}    visible    timeout=15s

Dataset row should contain metadata
    [Documentation]    Verifies a dataset row shows its name and type.
    [Arguments]    ${dataset_name}    ${dataset_type}

    VAR    ${row}    css=table tbody tr:has-text("${dataset_name}")
    Wait For Elements State    ${row}    visible    timeout=15s
    Get Text    ${row}    contains    ${dataset_type}

Get dataset row text
    [Documentation]    Returns the text content of the named dataset row.
    [Arguments]    ${dataset_name}

    VAR    ${row}    css=table tbody tr:has-text("${dataset_name}")
    Wait For Elements State    ${row}    visible    timeout=15s
    ${text}=    Get Text    ${row}
    RETURN    ${text}

Dataset table row count should equal
    [Documentation]    Verifies the dataset table renders exactly ${expected} data rows.
    [Arguments]    ${expected}

    VAR    ${rows}    css=table tbody tr
    Get Element Count    ${rows}    ==    ${expected}

Datasets pagination controls should be visible
    [Documentation]    Verifies the pagination navigation widget is rendered for the
    ...                datasets table.

    Wait For Elements State    ${DATASETS_PAGINATION_NAV}    visible    timeout=15s

Get first dataset row text
    [Documentation]    Returns the textual content of the first data row. Used to
    ...                detect page changes without coupling to specific dataset names.

    Wait For Elements State    ${DATASETS_FIRST_ROW}    visible    timeout=15s
    ${text}=    Get Text    ${DATASETS_FIRST_ROW}
    RETURN    ${text}

Click next page in datasets pagination
    [Documentation]    Clicks the "next page" control of the datasets pagination widget.

    Wait For Elements State    ${DATASETS_PAGINATION_NEXT}    visible    timeout=10s
    Click    ${DATASETS_PAGINATION_NEXT}

Wait until first dataset row text changes from
    [Documentation]    Polls the first dataset row until its text differs from the given
    ...                baseline, confirming the table content has actually changed (i.e.,
    ...                pagination navigated to a new page).
    [Arguments]    ${baseline}

    Wait Until Keyword Succeeds    15s    1s    First dataset row text should differ from    ${baseline}

First dataset row text should differ from
    [Documentation]    Asserts the current first-row text is not equal to the given baseline.
    [Arguments]    ${baseline}

    ${current}=    Get Text    ${DATASETS_FIRST_ROW}
    Should Not Be Equal    ${current}    ${baseline}
