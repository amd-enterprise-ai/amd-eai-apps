# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       End-to-end testing of full AIM catalog.
...
...                 Auto-discovers Ready AIMs from the cluster API and generates one test
...                 per model: deploy, verify running, inference, metrics, undeploy. This
...                 is slow and GPU-hungry, so most runs of the AIWB suite want it skipped.
...
...                 This suite is tagged aim-catalog, an ordinary Robot Framework tag that
...                 works like any other — to leave the catalog out of a run:
...                 | --exclude aim-catalog
...                 or to run only it:
...                 | --include aim-catalog
...                 Every static test below carries the tag, and RF filters before the
...                 listener runs, so --exclude empties the suite before it starts: no
...                 models are discovered, nothing is deployed. Any static test added
...                 here must carry aim-catalog too, or the exclusion stops working.
...                 The generator also honours
...                 | --variable EXCLUDE_TAGS:aim-catalog
...                 which skips the suite the same way from inside the run.
...
...                 IMPORTANT: tag filtering can only take the suite as a whole. The
...                 per-model tests do not exist until this suite starts, so
...                 --include/--exclude/--test cannot select among them. Use variables:
...                 | --variable INCLUDE_TAGS:model:aim-name
...                 | --variable EXCLUDE_TAGS:requires-hf-token
...                 | --variable AIM_VERSION:>=0.9.0
...
...                 See README.md for the full set of options.

Resource            resources/aim_catalog.resource
Resource            resources/airm_projects.resource
Resource            resources/api/models.resource
Resource            resources/api_keys.resource
Library             AimCatalogGenerator
Suite Setup         Setup AIM catalog testing
Suite Teardown      Cleanup AIM catalog testing
Test Timeout        100 minutes


*** Variables ***
${TEST_MODE}        full        # Test mode: full, smoke, or quick
${AIM_CATALOG_MODEL}    ${None}    # One image name to test; ${None} tests all Ready AIMs
${SELECTED_AIM_RECORD}    ${None}    # Exact Ready AIM resolved by the listener for one-model runs
${SELECTED_AIM_IMAGE}    ${None}    # Exact Docker reference reused through the selected lifecycle
${SELECTED_AIM_HF}    ${False}    # HuggingFace token requirement for the selected AIM
${INCLUDE_TAGS}     ${None}     # Tags to include (set via --variable INCLUDE_TAGS:model:aim-xxx)
${EXCLUDE_TAGS}     ${None}     # Tags to exclude (set via --variable EXCLUDE_TAGS:requires-hf-token)
${AIM_VERSION}      ${None}     # Version filter: "0.8.5" (exact), ">=0.9.0" (range), "latest" (default dedup)
${MAX_GPU_COUNT}    1           # Set by listener to max gpu_count across all discovered models
${AIM_DEPLOY_TIMEOUT}    5400  # Seconds to wait for AIM to reach Running (90 min, covers 671B model first-time download + verify + GPU load)


*** Test Cases ***
Placeholder - Will be replaced by generated tests
    [Documentation]    Keeps Robot Framework from pruning this suite as empty before the
    ...                listener runs, and carries the aim-catalog tag so that --exclude
    ...                aim-catalog can prune the suite on purpose. The listener always
    ...                removes it — replaced by the generated per-model tests, or dropped
    ...                outright when EXCLUDE_TAGS opts out, so it never reports as a test.
    [Tags]    DYNAMIC_TEST_PLACEHOLDER    aims    aim-catalog
    No Operation

One selected Ready AIM completes its lifecycle
    [Documentation]    The workflow-selected AIM deploys, serves inference, and can be removed.
    [Tags]    SELECTED_AIM_LIFECYCLE    aims    aim-catalog    gpu    smoke    lifecycle
    Given a selected Ready AIM from the catalog
    When the selected AIM is deployed
    Then the selected AIM should reach Running state
    And the selected AIM should serve inference
    And the selected AIM should be removed when undeployed
