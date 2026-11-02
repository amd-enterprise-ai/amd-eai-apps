# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Page object for autoscaling-related UI elements.
...                 Contains selectors and atomic browser interactions only.
...                 Business logic and assertions belong in feature resources.
*** Variables ***
${SCALING_STATUS_CARD_SELECTOR}         css=[data-testid="scaling-status-card"]
${SETTINGS_BUTTON_SELECTOR}             css=[data-testid="scaling-settings-button"]
${DEPLOYMENT_SETTINGS_DRAWER_SELECTOR}  css=[data-testid="deployment-settings-drawer"]
${AUTOSCALING_TOGGLE_SELECTOR}          css=[role="switch"][aria-label="Enable autoscaling"]
${SCALING_METRIC_LABEL_SELECTOR}        text="Scaling metric"
${TARGET_VALUE_LABEL_SELECTOR}          text="Target value"
${REPLICAS_TOGGLE_SELECTOR}             css=button[aria-label="Toggle replicas table"]
${REPLICAS_TABLE_SELECTOR}              css=[data-testid="scaling-status-card"] [role="grid"]
${REPLICA_ROW_SELECTOR}                 css=[data-testid="scaling-status-card"] [role="row"]:has([role="gridcell"])


*** Keywords ***
Wait for autoscaling toggle
    [Documentation]    Waits for the autoscaling toggle to become visible in the deploy wizard.

    Wait For Elements State    ${AUTOSCALING_TOGGLE_SELECTOR}    visible    timeout=15s

Click autoscaling toggle
    [Documentation]    Clicks the autoscaling enable/disable toggle in the deploy wizard.

    Wait For Elements State    ${AUTOSCALING_TOGGLE_SELECTOR}    visible    timeout=15s
    # HeroUI Switch uses a checkbox internally; Check Checkbox toggles it reliably
    Check Checkbox    ${AUTOSCALING_TOGGLE_SELECTOR}

Wait for autoscaling fields
    [Documentation]    Waits for all autoscaling configuration fields to become visible.

    Wait For Elements State    text=Replica range    visible    timeout=10s
    Wait For Elements State    ${SCALING_METRIC_LABEL_SELECTOR}    visible    timeout=5s
    Wait For Elements State    ${TARGET_VALUE_LABEL_SELECTOR}    visible    timeout=5s

Check autoscaling toggle state
    [Documentation]    Returns whether the autoscaling toggle is enabled (True/False).

    ${result}=    Get Checkbox State    ${AUTOSCALING_TOGGLE_SELECTOR}
    RETURN    ${result}

Get scaling status card text
    [Documentation]    Returns the text content of the autoscaling status card.

    Wait For Elements State    ${SCALING_STATUS_CARD_SELECTOR}    visible    timeout=10s
    ${text}=    Get Text    ${SCALING_STATUS_CARD_SELECTOR}
    RETURN    ${text}

Click settings button on scaling card
    [Documentation]    Clicks the Settings button on the autoscaling status card.

    Wait For Elements State    ${SETTINGS_BUTTON_SELECTOR}    visible    timeout=10s
    Click    ${SETTINGS_BUTTON_SELECTOR}

Wait for deployment settings drawer
    [Documentation]    Waits for the deployment settings drawer to become visible.

    Wait For Elements State    text="Autoscaling settings"    visible    timeout=15s

Check deployment settings drawer has autoscaling toggle
    [Documentation]    Returns whether the autoscaling toggle is visible in the settings drawer.

    ${visible}=    Get Element States    ${AUTOSCALING_TOGGLE_SELECTOR}    then    bool(value & visible)
    RETURN    ${visible}

Get scaling metric text
    [Documentation]    Returns the scaling metric text from the scaling status card.

    Wait For Elements State    ${SCALING_METRIC_LABEL_SELECTOR}    visible    timeout=10s
    ${parent}=    Get Element    ${SCALING_METRIC_LABEL_SELECTOR} >> xpath=..
    ${text}=    Get Text    ${parent}
    RETURN    ${text}

Get target value text
    [Documentation]    Returns the target value text from the scaling status card.

    Wait For Elements State    ${TARGET_VALUE_LABEL_SELECTOR}    visible    timeout=10s
    ${parent}=    Get Element    ${TARGET_VALUE_LABEL_SELECTOR} >> xpath=..
    ${text}=    Get Text    ${parent}
    RETURN    ${text}

Click replicas toggle button
    [Documentation]    Clicks the chevron button that toggles the replica list expansion.

    Wait For Elements State    ${REPLICAS_TOGGLE_SELECTOR}    visible    timeout=15s
    Click    ${REPLICAS_TOGGLE_SELECTOR}

Wait for replicas table
    [Documentation]    Waits for the replicas table to become visible after expansion.

    Wait For Elements State    ${REPLICAS_TABLE_SELECTOR}    visible    timeout=10s

Check replicas table visible
    [Documentation]    Returns whether the replicas table is currently visible.

    ${visible}=    Get Element States    ${REPLICAS_TABLE_SELECTOR}    then    bool(value & visible)
    RETURN    ${visible}

Get replica row count
    [Documentation]    Returns the number of data rows in the replicas table (excluding header row).

    ${rows}=    Get Elements    ${REPLICA_ROW_SELECTOR}
    ${count}=    Get Length    ${rows}
    RETURN    ${count}
