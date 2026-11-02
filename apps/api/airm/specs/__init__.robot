# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       End to end tests for AIRM service

Resource            resources/deployment.resource
Resource            resources/airm_keywords.resource
Resource            resources/api/health.resource
Resource            resources/authorization.resource
Resource            resources/airm_projects.resource

Suite Setup         Verify AIRM Service Health
# Shared projects — whether this run adopted them or created them — are removed once, here, after
# every suite has finished with them, never by a per-test teardown, which would delete a shared
# project other tests are still using. Keeps the "an interrupted run must not leak a project"
# guarantee.
Suite Teardown      Clean Up Adopted Projects


*** Keywords ***
Verify AIRM Service Health
    [Documentation]    Verifies AIRM service is healthy before running tests
    ...                Includes validation of authentication setup for better error reporting
    ...                Extended retry window (30s) allows port forward recreation if needed

    # First validate kubectl OIDC configuration
    Validate Kubectl Config

    # Then verify AIRM service health with extended timeout for port forward recovery
    # Port forward recreation can take several seconds, so we need more time than 10s
    Wait until keyword succeeds    30 s    2 s    Verify AIRM health
