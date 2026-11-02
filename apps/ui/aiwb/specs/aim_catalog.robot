# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Frontend E2E tests for AIM catalog browsing and deployment wizard UI.
...
...                 These tests verify catalog display, model metadata, deployment wizard
...                 interactions, and incompatibility indicators. They do NOT require GPU
...                 hardware or active deployments (except where noted).
...
...                 Suite Efficiency Design:
...                 Uses Suite Setup/Teardown for project tracking and cleanup. Each test
...                 declares its own preconditions via Given steps. Catalog browsing tests
...                 skip deployment for fast execution.

# UI resources (feature layer + browser setup)
Resource            resources/common/browser_setup.resource
Resource            resources/aims.resource
Resource            resources/workloads.resource

# API resources (infrastructure preconditions, resolved via pythonpath)
Resource            resources/aiwb_aims.resource
Resource            resources/airm_projects.resource

Suite Teardown      Run Keywords    Clean Up All Created AIWB Secrets    AND    Clean Up All Created Projects
Test Setup          Open test browser
Test Teardown       Close test browser


*** Test Cases ***
# =============================================================================
# Browse Catalog UI
# =============================================================================

AIM catalog page displays model cards with metadata
    [Documentation]    Verify that the AIM catalog page loads and displays model cards
    ...                with essential metadata: version count, description, and tags.
    [Tags]    ui    aims    catalog    smoke

    Given a ready project with user access exists
    And an AIM exists in system
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    Then catalog should display AIM cards
    And catalog should show description text
    And AIM card "${TEST_AIM_DISPLAY_NAME}" should show metadata

AIM catalog cards show version count and deploy button
    [Documentation]    Verify that each AIM card shows the number of available versions
    ...                and provides a Deploy action button.
    [Tags]    ui    aims    catalog    smoke

    Given a ready project with user access exists
    And an AIM exists in system
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    Then AIM card "${TEST_AIM_DISPLAY_NAME}" should show version count
    And AIM card "${TEST_AIM_DISPLAY_NAME}" should show deploy button

Incompatible models are visually distinguished in catalog
    [Documentation]    Verify that models incompatible with the current hardware show
    ...                an unsupported banner. This test always passes - it validates
    ...                the mechanism exists when incompatible models are present.
    [Tags]    ui    aims    catalog    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    Then unsupported models should be visually distinguished

# =============================================================================
# Deploy Through Wizard
# =============================================================================

Deploy wizard shows model info and deployment steps
    [Documentation]    Verify that opening the deploy wizard for an AIM shows the model
    ...                title, description, version selector, and deployment steps.
    [Tags]    ui    aims    deploy    catalog

    Given a ready project with user access exists
    And an AIM exists in system
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user opens deploy wizard for "${TEST_AIM_DISPLAY_NAME}"
    Then deploy wizard should be open
    And deploy wizard should show model info for "${TEST_AIM_DISPLAY_NAME}"
    And deploy wizard should show version and steps

Deploy wizard exposes advanced runtime profile overrides
    [Documentation]    The catalog deploy wizard offers advanced runtime profile overrides
    ...                (precision, accelerator, count) so users can deploy onto partitioned
    ...                clusters. Verify the advanced section expands and surfaces the override
    ...                fields. Override propagation to the AIMService and inference pod is
    ...                covered by the API suite.
    [Tags]    ui    aims    deploy    profile    catalog

    Given a ready project with user access exists
    And an AIM exists in system
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user opens deploy wizard for "${TEST_AIM_DISPLAY_NAME}"
    And user expands advanced profile parameters in the deploy wizard
    Then the deploy wizard should offer advanced profile overrides

Deploy wizard warns when a model has no optimized profile for the selection
    [Documentation]    A model whose profiles are all unoptimized can still be deployed,
    ...                but the wizard must surface that tradeoff before the user commits
    ...                to it. Verify the Target step's collapsed summary shows the
    ...                unoptimized-profile warning once that step is completed.
    [Tags]    ui    aims    deploy    profile    catalog

    Given a ready project with user access exists
    And an AIM exists in system    unoptimized
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user opens deploy wizard for "${TEST_AIM_DISPLAY_NAME}"
    And user completes the performance step in the deploy wizard
    Then the deployment summary should show an unoptimized profile warning

Deployed model uses the image pull secret the user picked by name
    [Documentation]    Verify that a user can pick a private-registry credential by the name
    ...                they gave it when deploying a model, and that the running model is
    ...                given that credential.
    [Tags]    ui    aims    deploy    secrets    kubectl    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And an AIM exists in system
    And the selected model has no deployment in the project
    And an image pull secret "aim-registry" exists in the project
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user deploys "${TEST_AIM_DISPLAY_NAME}" with image pull secret "aim-registry"
    Then the deployed model should use the selected image pull secret
    [Teardown]    Run Keywords    Remove AIM deployment if present    AND    Close test browser

# =============================================================================
# Deployment Status & Management
# =============================================================================

Deployed models list shows active deployments with status
    [Documentation]    Verify that the Deployed Models tab shows all active deployments
    ...                with their status indicators.
    [Tags]    ui    aims    workloads    deployed    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And AIM is deployed without custom deployment name and running
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user views deployed models
    Then deployed models table should have entries

Deployed model shows its display name consistently on dashboard and deployed models page
    [Documentation]    Verify that a deployed model is presented by the same user-facing
    ...                display name on both the project dashboard workloads table and the
    ...                Deployed Models page, instead of an internal identifier such as the
    ...                generated resource name that does not match the name users see elsewhere.
    [Tags]    ui    aims    workloads    deployed    display-name    gpu

    Given a ready project with user access exists
    And AIM is deployed
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on workloads page
    Then inference workload should be listed by its model display name
    When user is on deployed models page
    Then deployed model should be listed by its display name

Deployed model card shows has deployments chip in catalog
    [Documentation]    Verify that a deployed model's catalog card shows the "Has deployments"
    ...                chip so users can identify active deployments at a glance.
    [Tags]    ui    aims    catalog    deployments    gpu

    Given a ready project with user access exists
    And AIM is deployed
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    Then AIM card "${TEST_AIM_DISPLAY_NAME}" should show has deployments chip

Non-deployed model card does not show has deployments chip in catalog
    [Documentation]    Verify that a model with no active deployments does not show
    ...                the "Has deployments" chip in the catalog.
    [Tags]    ui    aims    catalog    deployments    smoke

    Given a ready project with user access exists
    And an AIM exists in system
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    Then AIM card "${TEST_AIM_DISPLAY_NAME}" should not show has deployments chip

AIM details page shows logs and metrics access
    [Documentation]    Verify that the AIM details page provides access to logs and
    ...                shows the performance metric for the deployment.
    [Tags]    ui    aims    workloads    details    gpu

    Given a ready project with user access exists
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And AIM is deployed without custom deployment name and running
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on workloads page
    When user opens inference workload details
    Then AIM details title should show default model name when no custom deployment name is set
    And workload details should show logs button
    And workload details should show performance metric

AIM details page title prefers custom deployment name
    [Documentation]    Verify that when an inference deployment is created with an explicit
    ...                custom deployment name, the AIM details title shows that user-facing
    ...                name instead of the model's default name.
    [Tags]    ui    aims    workloads    details    display-name    gpu

    Given a ready project with user access exists
    And an AIM exists in system
    And project quota is set to    gpu_count=2    cpu_milli_cores=8000    memory_bytes=68719476736
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And AIM is deployed with custom deployment name and running    ${TEST_AIM_DISPLAY_NAME} Deployment
    And user is on workloads page
    When user opens inference workload details
    Then AIM details title should show custom deployment name

Deleted AIM URL renders historical details
    [Documentation]    A user navigating to a stale URL of a deleted AIM deployment
    ...                should still see historical deployment details, with the
    ...                Delete button disabled.
    [Tags]    ui    aims    workloads    details    gpu

    Given a ready project with user access exists
    And AIM is deployed
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And AIM has been deleted
    When user navigates directly to the deleted AIM detail page by ID
    Then historical AIM details should be rendered
    And the delete button should be disabled

Deployments list shows workloads with status indicators
    [Documentation]    Verify the workloads dashboard shows inference workloads with
    ...                status indicators.
    [Tags]    ui    aims    workloads    deployed    gpu

    Given a ready project with user access exists
    And AIM is deployed
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    When user is on workloads page
    Then deployed workloads list should have entries
    And inference workload should show status in list

# =============================================================================
# Accelerator hardware display & filter
# =============================================================================

Catalog card metadata distinguishes CPU and GPU AIMs by accelerator label
    [Documentation]    Verifies that catalog cards surface a per-AIM accelerator
    ...                label so users can tell CPU and GPU AIMs apart at a glance.
    [Tags]    ui    aims    catalog    accelerator    smoke

    Given a ready project with user access exists
    And an AIM exists in system
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    Then catalog should show at least one card with accelerator label "GPU"

Filtering the catalog by GPU shows only GPU AIMs
    [Documentation]    Verifies that selecting "GPU" in the accelerator filter
    ...                narrows the catalog to GPU-capable AIMs and removes
    ...                CPU-only cards from view.
    [Tags]    ui    aims    catalog    accelerator    filter

    Given a ready project with user access exists
    And an AIM exists in system
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user filters catalog by accelerator "GPU"
    Then catalog should show at least one card with accelerator label "GPU"
    And catalog should not show cards with accelerator label "CPU"

CPU accelerator filter does not flip supported models to unsupported
    [Documentation]    Applying the CPU accelerator filter must not increase the
    ...                number of unsupported-model banners. A model that is supported
    ...                before filtering must still appear as supported afterwards;
    ...                the filter may only remove cards, never change their support status.
    [Tags]    ui    aims    catalog    accelerator    filter    smoke

    Given a ready project with user access exists
    And an AIM exists in system
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    When user records unsupported banner count as baseline
    And user filters catalog by accelerator "CPU"
    Then unsupported banner count should not exceed baseline

# =============================================================================
# Request Missing Model
# =============================================================================

Request model card links user to support mailto
    [Documentation]    Verify that the AIM catalog page shows a "Request model" card
    ...                linking to the support mailbox so users can ask for missing
    ...                models.
    [Tags]    ui    aims    catalog    request    smoke

    Given a ready project with user access exists
    And user is logged in
    And project "${TEST_PROJECT}[name]" is selected
    And user is on models page
    Then request model card should link to support mailto
