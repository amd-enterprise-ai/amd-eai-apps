# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Real E2E regression for the AIM catalog cleanup keywords.
...
...                 test_aim_catalog_cleanup.py statically parses "Cleanup AIM catalog
...                 testing" to prove keyword call order and literal arguments are correct,
...                 but a static parse cannot execute the keyword or observe whether a
...                 tracked model's predictor actually disappears from the cluster. This
...                 suite drives the real "Undeploy all tracked AIM catalog services" keyword
...                 — the AIM-only half of "Cleanup AIM catalog testing", factored out so it can
...                 run before project deletion — against a genuinely deployed AIM, using the
...                 same suite-scoped tracking variables (${DEPLOYED_AIMS_LIST} /
...                 ${DEPLOYED_AIM_NAMES}) the dynamically generated aim_catalog.robot suite
...                 populates per model, and verifies the observable Kubernetes and API
...                 outcome while the project namespace still exists. Asserting after project
...                 deletion would make kubectl fail on a missing namespace — a false test
...                 failure, not a real proof — so this suite never calls "Cleanup AIM catalog
...                 testing" (the full wrapper, which also deletes the project) mid-test; the
...                 project is only torn down by Suite Teardown once every test has finished.
...
...                 Deploys a single small, non-gated catalog model — this suite regression
...                 tests the cleanup mechanism itself, not catalog coverage (that is
...                 aim_catalog.robot's job). Deploying an AIMService only waits for the API's
...                 asynchronous create to be accepted, not for aim-engine's controller to
...                 reconcile the predictor Deployment, so every test case confirms the
...                 predictor actually exists (bounded polling) before it does anything that
...                 claims to prove that predictor's later absence. All deploy/name-capture/
...                 already-404-setup/absence-check steps below call business-layer keywords in
...                 resources/aim_catalog.resource — this file never calls the API layer, a
...                 test template, or Kubernetes-check helpers directly.

Resource            resources/aim_catalog.resource
Resource            resources/airm_projects.resource
# aim_catalog.resource resolves a catalog record through this library's Resolve Ready AIM
# keyword but does not import it, so every suite using those keywords must. Registering it
# as a listener in arguments.txt does not make its keywords available.
Library             AimCatalogGenerator
Suite Setup         Setup AIM catalog testing
Suite Teardown      Cleanup AIM catalog testing
Test Timeout        20 minutes


*** Variables ***
${MAX_GPU_COUNT}                       1
${AIM_CATALOG_CLEANUP_SMOKE_IMAGE}     aim-openai-gpt-oss-20b    # small, non-gated; only needs to exist, not reach Running


*** Test Cases ***
Undeploy all tracked AIM catalog services removes a tracked model's predictor from kubernetes
    [Documentation]    Deploys one real AIM so suite-level tracking picks it up exactly as the
    ...    generated catalog tests do, then confirms (bounded polling) that its predictor
    ...    Deployment actually exists in Kubernetes before anything below claims to prove its
    ...    absence — closing the race between the API's asynchronous AIMService create and
    ...    aim-engine's controller reconciling the predictor. Before cleanup runs, proves the
    ...    Kubernetes-level absence assertion actually has teeth — it must fail while the
    ...    predictor is still genuinely running, otherwise a leaking cleanup could pass without
    ...    ever being challenged. Then drives the real "Undeploy all tracked AIM catalog
    ...    services" keyword as an explicit test step — the same AIM-cleanup logic "Cleanup AIM
    ...    catalog testing" runs before it deletes the project — and confirms it leaves the
    ...    predictor Deployment gone from Kubernetes and the AIMService 404 from the API, while
    ...    the project namespace still exists. Static AST parsing
    ...    (test_aim_catalog_cleanup.py) can only prove the keyword is *called* correctly; this
    ...    proves it *works*.
    [Tags]    aims    cleanup    gpu    kubectl
    Given A catalog AIM is deployed for cleanup testing    ${AIM_CATALOG_CLEANUP_SMOKE_IMAGE}
    And The catalog AIM's predictor should be running in kubernetes
    And The deployed catalog AIM's Kubernetes name is captured
    Then Predictor absence verification should fail while the predictor exists
    When Undeploy all tracked AIM catalog services
    Then The deployed catalog AIM should no longer exist in the API
    And The predictor Deployment for the deployed catalog AIM should no longer exist in kubernetes

Undeploy all tracked AIM catalog services still confirms kubernetes removal when the API record is already gone
    [Documentation]    Exercises the per-service loop's already-404 branch inside "Undeploy all
    ...    tracked AIM catalog services": deploys one real AIM and confirms (bounded polling)
    ...    that its predictor actually exists in Kubernetes first, then undeploys via the API
    ...    directly — bypassing the per-model Undeploy test template, so the tracked service is
    ...    gone from the API but the suite tracking lists still carry it, mirroring a model
    ...    whose own Undeploy test failed or was excluded — then drives the real cleanup keyword
    ...    and confirms it still verifies Kubernetes-level predictor absence rather than
    ...    trusting the API's 404 alone, while the project namespace still exists.
    [Tags]    aims    cleanup    gpu    kubectl
    Given A catalog AIM is deployed for cleanup testing    ${AIM_CATALOG_CLEANUP_SMOKE_IMAGE}
    And The catalog AIM's predictor should be running in kubernetes
    And The deployed catalog AIM's Kubernetes name is captured
    When The deployed catalog AIM is undeployed directly via the API
    Then The deployed catalog AIM should no longer exist in the API
    When Undeploy all tracked AIM catalog services
    Then The predictor Deployment for the deployed catalog AIM should no longer exist in kubernetes
