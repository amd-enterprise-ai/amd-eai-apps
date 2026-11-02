# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for showing or hiding deleted workloads on the Deployed
...                 Models page.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)
...
...                 There is no on-screen control for the opt-in — it is handed out as a link
...                 and remembered for later visits. How that is expressed lives here so the
...                 scenarios can talk about opting in rather than about the link itself.
Resource            common/session.resource
Resource            pages/models_page.resource


*** Variables ***
${OPT_IN_TO_DELETED_WORKLOADS}      ?deleted=1
${OPT_OUT_OF_DELETED_WORKLOADS}     ?deleted=0
${DELETED_STATUS}                   Deleted
${DELETING_STATUS}                  Deleting


*** Keywords ***
# =============================================================================
# Given keywords (UI preconditions)
# =============================================================================

User is on the deployed models page
    [Documentation]    Navigates to the Deployed Models tab.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to deployed models page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

The user has opted in to showing deleted workloads
    [Documentation]    Puts the session in the opted-in state so a scenario can start from
    ...                there instead of exercising the opt-in itself.

    User opts in to showing deleted workloads

# =============================================================================
# When keywords (actions)
# =============================================================================

User opts in to showing deleted workloads
    [Documentation]    Follows the entry point that asks for deleted workloads to be listed.

    Navigate to deployed models page
    ...    ${UI_BASE_URL}    ${TEST_PROJECT}[name]    ${OPT_IN_TO_DELETED_WORKLOADS}

User opts out of showing deleted workloads
    [Documentation]    Follows the entry point that asks for deleted workloads to be hidden again.

    Navigate to deployed models page
    ...    ${UI_BASE_URL}    ${TEST_PROJECT}[name]    ${OPT_OUT_OF_DELETED_WORKLOADS}

User returns to the deployed models page
    [Documentation]    Revisits the page the ordinary way, without restating any preference,
    ...                so a scenario can check what the session remembered.

    User is on the deployed models page

User opens the workload status filter
    [Documentation]    Opens the status filter so its available values can be inspected.

    Open status filter

# =============================================================================
# Then keywords (verification)
# =============================================================================

The deleted deployment should be listed
    [Documentation]    Verifies the deployment that was deleted appears in the Deployed
    ...                Models list.
    ...                Requires: TEST_AIM_DISPLAY_NAME set by "AIM is deployed".

    Deployed models table should contain a model with display name "${TEST_AIM_DISPLAY_NAME}"

The deleted deployment should not be listed
    [Documentation]    Verifies the deployment that was deleted is absent from the Deployed
    ...                Models list.
    ...                Requires: TEST_AIM_DISPLAY_NAME set by "AIM is deployed".

    Deployed models table should not contain a model with display name "${TEST_AIM_DISPLAY_NAME}"

Deleted should be offered as a workload status to filter by
    [Documentation]    Verifies the open status filter offers Deleted as a value.

    ${count}=    Get status filter option count for "${DELETED_STATUS}"
    ${offered}=    Get status filter options text
    Should Be True    ${count} > 0
    ...    msg=Status filter should offer '${DELETED_STATUS}', but offered: ${offered}

Deleted should not be offered as a workload status to filter by
    [Documentation]    Verifies the open status filter does not offer Deleted as a value.

    ${count}=    Get status filter option count for "${DELETED_STATUS}"
    ${offered}=    Get status filter options text
    Should Be Equal As Integers    ${count}    ${0}
    ...    msg=Status filter should not offer '${DELETED_STATUS}', but offered: ${offered}

Live workload statuses should still be offered
    [Documentation]    Verifies the status filter is populated with the everyday statuses.
    ...                Pairs with the Deleted assertions so those cannot pass against an
    ...                empty or unrendered filter.

    ${count}=    Get status filter option count for "${DELETING_STATUS}"
    Should Be True    ${count} > 0
    ...    msg=Status filter should still offer '${DELETING_STATUS}'
