# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Business-logic keywords comparing the fine-tuning catalog against the recipes
...                 registered for the cluster. Read-only: recipes are global, so registering one
...                 would let concurrent scenarios that pick a base model choose it.
Resource            api/overlays.resource
Resource            api/cluster.resource
Resource            aiwb_charts.resource
Resource            aiwb_aims.resource
Library             ModelCatalog


*** Variables ***
${FINETUNING_CHART_NAME}                    llm-finetune-silogen-engine
@{TEST_RECIPES_THE_CLUSTER_SHOULD_OFFER}


*** Keywords ***
The cluster has fine-tuning recipes for models it can serve on its GPUs
    [Documentation]    Records the base models the fine-tuning catalog must offer: every registered
    ...    recipe whose model has a Ready profile and that supports one of the cluster's GPUs,
    ...    however the recipe writes the GPU ID. Decided without consulting the catalog under
    ...    test, so a catalog that wrongly drops a model fails the scenario instead of skipping it.
    ${chart_id}=    Find chart ID by name    ${FINETUNING_CHART_NAME}    variable_name=TEST_FINETUNING_CHART_ID
    IF    $chart_id is None
        Skip    The fine-tuning chart is not registered on this cluster
    END
    ${recipes}=    List overlays request    chart_id=${chart_id}    expected_status=200
    ${profiles}=    All inference profiles
    ${accelerators}=    List cluster accelerators    expected_status=200
    ${expected}=    Get Recipes The Cluster Should Offer
    ...    ${recipes.json()}[data]    ${profiles}    ${accelerators.json()}[data]
    IF    not $expected
        Skip    No registered fine-tuning recipe supports this cluster's GPUs for a model it can serve
    END
    VAR    @{TEST_RECIPES_THE_CLUSTER_SHOULD_OFFER}    @{expected}    scope=TEST

Every recipe that supports the cluster's GPUs should be offered as a base model
    [Documentation]    Verifies the fine-tuning catalog offers every base model recorded as expected.
    ...    Requires: ${TEST_RESPONSE} from the fine-tuning catalog request.
    Should Not Be Empty    ${TEST_RECIPES_THE_CLUSTER_SHOULD_OFFER}
    ...    msg=No expected base models were recorded for this scenario
    Assert Finetuning Catalog Offers    ${TEST_RESPONSE.json()}[data]    ${TEST_RECIPES_THE_CLUSTER_SHOULD_OFFER}
