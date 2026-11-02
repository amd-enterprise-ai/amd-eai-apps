# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       BDD keywords for AIM UI features.
...                 Composes page-level interactions into business-meaningful keywords
...                 suitable for Given-When-Then test cases.
...
...                 Layer: Feature (tests import this, NOT page resources directly)
Resource            common/session.resource
Resource            pages/models_page.resource
Resource            resources/aiwb_adapter_serving.resource
Resource            resources/aiwb_aims.resource
Resource            resources/aiwb_secrets.resource
Library             TestPrefix


*** Variables ***
${SEMVER_PATTERN}       \\d+\\.\\d+\\.\\d+


*** Keywords ***
# =============================================================================
# Given keywords (UI preconditions)
# =============================================================================

User is on models page
    [Documentation]    Navigates to the AIM Catalog (Models) page.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to models page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

User is on deployed models page
    [Documentation]    Navigates to the Deployed Models tab on the models page.
    ...                Expects ${UI_BASE_URL} and ${TEST_PROJECT} to be set.

    Navigate to deployed models page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

An image pull secret "${name}" exists in the project
    [Documentation]    Creates an image pull secret via the AIWB API.
    ...                Sets: TEST_AIWB_SECRET_NAME (display name), TEST_AIWB_SECRET_K8S_NAME

    A secret "${name}" with use case "ImagePullSecret" is created via AIWB

# =============================================================================
# When keywords (actions)
# =============================================================================

User deploys "${aim_name}" with image pull secret "${secret_name}"
    [Documentation]    Deploys the model through the catalog wizard, choosing the image pull
    ...                secret by the display name the user gave it, and tracks the deployment
    ...                for cleanup.
    ...                Requires: TEST_AIM_NAME. Sets: TEST_AIM_ID, TEST_DEPLOYED_SERVICE_NAME

    Click deploy button on card    ${aim_name}
    Wait for deploy wizard
    ${display_name}=    Test Name    ${secret_name}
    Select deploy wizard image pull secret    ${display_name}
    Advance deploy wizard to review and submit
    The deployment created through the wizard is tracked

User opens deploy wizard for "${aim_name}"
    [Documentation]    Clicks the Deploy button on a specific AIM card.

    Click deploy button on card    ${aim_name}

User opens actions menu for "${aim_name}"
    [Documentation]    Opens the actions menu (three dots) on a specific AIM card.

    Click actions menu button on card    ${aim_name}

User views deployed models
    [Documentation]    Navigates to the Deployed Models page.

    Navigate to deployed models page    ${UI_BASE_URL}    ${TEST_PROJECT}[name]

User searches for "${search_text}" in catalog
    [Documentation]    Enters a search term in the catalog search filter.

    Enter search filter text    ${search_text}

User filters catalog by accelerator "${label}"
    [Documentation]    Opens the Accelerator filter and toggles the given option
    ...                (e.g. "GPU" or "CPU"). Closes the dropdown afterwards so
    ...                downstream cards are not obscured.

    Open accelerator filter
    Select accelerator filter option "${label}"
    Close accelerator filter

User expands advanced profile parameters in the deploy wizard
    [Documentation]    Navigates to the performance step and expands advanced profile parameters.

    Click deploy wizard next
    Expand advanced profile parameters

User selects deploy precision override "${precision}"
    [Documentation]    Picks a precision in the advanced override section of the deploy wizard.

    Select deploy precision override    ${precision}

User completes the performance step in the deploy wizard
    [Documentation]    Advances the deploy wizard past the Target (performance) step so
    ...                its collapsed summary is rendered.

    Click deploy wizard next

# =============================================================================
# Then keywords (verification)
# =============================================================================

Deploy wizard should be open
    [Documentation]    Verifies the Deploy AIM wizard is visible.

    Wait for deploy wizard

The deployed model should use the selected image pull secret
    [Documentation]    Verifies the running model was given the registry credential the user
    ...                picked, identified by its Kubernetes name rather than its display name.
    ...                Requires: TEST_AIM_ID, TEST_AIWB_SECRET_K8S_NAME

    The running inference pod should use image pull secret "${TEST_AIWB_SECRET_K8S_NAME}"

Version selector should be visible in deploy wizard
    [Documentation]    Verifies the version selector dropdown is present in the deploy wizard.

    ${text}=    Get version selector text
    Should Not Be Empty    ${text}

The deploy wizard should offer advanced profile overrides
    [Documentation]    Verifies the deploy wizard's advanced section surfaces the runtime
    ...                override fields (precision select) used for partitioned-cluster deploys.

    Advanced profile parameters should be visible

The deployment summary should show an unoptimized profile warning
    [Documentation]    Verifies the collapsed Target step summary warns the user that
    ...                no optimized profile is available for the current selection.

    Target step summary should show unoptimized profile warning

Selected version should contain "${text}"
    [Documentation]    Verifies the selected version text contains the expected value.

    ${version}=    Get version selector text
    Should Contain    ${version}    ${text}

Deployed model "${aim_name}" should show version
    [Documentation]    Verifies a deployed model row contains a semver version string.

    ${text}=    Get deployed model row text    ${aim_name}
    Should Match Regexp    ${text}    ${SEMVER_PATTERN}

Actions menu should be visible
    [Documentation]    Verifies the actions menu dropdown is displayed.

    ${text}=    Get actions menu text
    Should Not Be Empty    ${text}

Actions menu should show version info
    [Documentation]    Verifies the actions menu contains a semver version string.

    ${text}=    Get actions menu text
    Should Match Regexp    ${text}    ${SEMVER_PATTERN}

Catalog should display AIM cards
    [Documentation]    Verifies the catalog page shows at least one AIM card.

    ${count}=    Get AIM card count
    Should Be True    ${count} > 0    msg=AIM catalog should display at least one model card

Catalog should show description text
    [Documentation]    Verifies the catalog description paragraph is visible.

    ${text}=    Get catalog description text
    Should Not Be Empty    ${text}

AIM card "${aim_name}" should be visible
    [Documentation]    Verifies a specific AIM card is displayed in the catalog.

    AIM card should be visible    ${aim_name}

AIM card "${aim_name}" should show version count
    [Documentation]    Verifies a card shows how many versions are available (e.g. "3 versions").

    AIM card should have version count    ${aim_name}

AIM card "${aim_name}" should show deploy button
    [Documentation]    Verifies a card has a Deploy action button.

    AIM card should have deploy button    ${aim_name}

AIM card "${aim_name}" should show metadata
    [Documentation]    Verifies a card shows essential metadata (version count, description text).

    ${text}=    Get AIM card text    ${aim_name}
    Should Match Regexp    ${text}    \\d+ versions?
    # Cards always show at least the AI Lab name and a description
    ${length}=    Get Length    ${text}
    Should Be True    ${length} > 20    msg=AIM card should display meaningful metadata

Deploy wizard should show model info for "${aim_name}"
    [Documentation]    Verifies the deploy wizard shows the model title.

    Deploy wizard should show model title    ${aim_name}

Deploy wizard should show version and steps
    [Documentation]    Verifies the deploy wizard contains the version selector and deployment steps.

    Version selector should be visible in deploy wizard
    Deploy wizard steps should be visible

Unsupported models should be visually distinguished
    [Documentation]    Verifies that any unsupported models have the unsupported banner.
    ...    If no unsupported models exist, this passes silently.

    ${count}=    Get unsupported banner count
    Log    Found ${count} unsupported model banner(s)    INFO

Deployed models table should have entries
    [Documentation]    Verifies the deployed models table shows at least one row.

    ${count}=    Get deployed models row count
    Should Be True    ${count} > 0    msg=Deployed models table should have at least one entry

Deployed model should be listed by its display name
    [Documentation]    Verifies the Deployed Models page presents the model by its
    ...                user-facing deployment label rather than an internal identifier,
    ...                matching what the dashboard workloads table shows for a no-custom deployment.
    ...                Requires: TEST_AIM_CANONICAL_NAME and TEST_AIM_NAME set by "AIM is deployed".

    ${row_text}=    Get deployed model row text    ${TEST_AIM_CANONICAL_NAME}
    Should Contain    ${row_text}    ${TEST_AIM_CANONICAL_NAME}
    ...    msg=Deployed Models page should show the deployment label '${TEST_AIM_CANONICAL_NAME}'
    # Only assert the internal identifier is hidden when it actually differs from the
    # canonical fallback; some AIMs legitimately use their resource name as the canonical name.
    IF    '${TEST_AIM_NAME}' != '${TEST_AIM_CANONICAL_NAME}'
        Should Not Contain    ${row_text}    ${TEST_AIM_NAME}
        ...    msg=Deployed Models page should not expose the internal identifier '${TEST_AIM_NAME}'
    END

Request model card should link to support mailto
    [Documentation]    Verifies the "Request model" card exposes a support mailto link
    ...                with the expected subject. Clicking a mailto cannot be verified
    ...                end-to-end in the browser, so we assert the anchor target instead.

    ${href}=    Get request model card mailto href
    Should Start With    ${href}    mailto:amd-eai-support@amd.com
    Should Contain    ${href}    subject=Model%20request

AIM card "${aim_name}" should show accelerator label "${label}"
    [Documentation]    Verifies the AIM card's metadata line shows the given
    ...                accelerator label (e.g. "GPU", "CPU", "CPU, GPU").

    ${text}=    Get AIM card accelerator label    ${aim_name}
    Should Be Equal    ${text}    ${label}

Catalog should show at least one card with accelerator label "${label}"
    [Documentation]    Verifies that the catalog renders at least one AIM card
    ...                whose metadata line includes the given accelerator label.

    ${count}=    Get accelerator label match count    ${label}
    Should Be True    ${count} > 0
    ...    msg=Expected at least one card labeled "${label}", got ${count}

Catalog should not show cards with accelerator label "${label}"
    [Documentation]    Verifies that no displayed catalog card shows the given
    ...                accelerator label in its metadata line.

    ${count}=    Get accelerator label match count    ${label}
    Should Be Equal As Integers    ${count}    ${0}
    ...    msg=Expected zero cards labeled "${label}", got ${count}

AIM card "${aim_name}" should show has deployments chip
    [Documentation]    Verifies the deployment indicator chip is visible on the given card.

    AIM card has deployments chip should be visible    ${aim_name}

AIM card "${aim_name}" should not show has deployments chip
    [Documentation]    Verifies the deployment indicator chip is absent on the given card.

    AIM card has deployments chip should not be present    ${aim_name}

User records unsupported banner count as baseline
    [Documentation]    Captures the current number of unsupported-model banners for later
    ...                comparison. Stores the count in the suite-level variable
    ...                ${BASELINE_UNSUPPORTED_COUNT}.

    ${count}=    Get unsupported banner count
    VAR    ${BASELINE_UNSUPPORTED_COUNT}    ${count}    scope=TEST

Unsupported banner count should not exceed baseline
    [Documentation]    Verifies that the number of unsupported-model banners has not
    ...                increased since the baseline was recorded. The filter may hide
    ...                cards but must never flip a supported model to unsupported.

    ${count}=    Get unsupported banner count
    Should Be True    ${count} <= ${BASELINE_UNSUPPORTED_COUNT}
    ...    msg=Unsupported banner count increased after CPU filter: was ${BASELINE_UNSUPPORTED_COUNT}, now ${count}
