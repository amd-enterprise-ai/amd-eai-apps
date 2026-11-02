# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       AIRM UI endpoint discovery for frontend E2E tests.
...                 Resolves the AIRM UI base URL from environment variable or kubeconfig context.
...                 Unlike API endpoints that use port-forwarding, browser tests need real external
...                 URLs because OAuth redirect URIs must match the actual hostname.
Library             OperatingSystem
Library             Process
Library             String


*** Variables ***
# Override via environment variable: AIRM_UI_URL=https://airmui.example.com
${AIRM_UI_URL}      ${EMPTY}


*** Keywords ***
AIRM UI endpoint
    [Documentation]    Returns the AIRM UI base URL.
    ...                Checks AIRM_UI_URL environment variable first, then derives from kubectl context.
    ...                Browser tests must use the real external URL (not port-forwarded localhost)
    ...                because the OAuth login redirect must match the registered redirect URI.

    # Return cached value if already resolved
    IF    "${AIRM_UI_URL}" != "${EMPTY}"
        RETURN    ${AIRM_UI_URL}
    END

    # Check environment variable
    ${env_url}=    Get Environment Variable    AIRM_UI_URL    default=${EMPTY}
    IF    "${env_url}" != "${EMPTY}"
        VAR    ${AIRM_UI_URL}    ${env_url}    scope=SUITE
        RETURN    ${env_url}
    END

    # Derive from kubectl context cluster domain
    ${url}=    Derive UI URL from kubectl context
    VAR    ${AIRM_UI_URL}    ${url}    scope=SUITE
    RETURN    ${url}

Derive UI URL from kubectl context
    [Documentation]    Derives the AIRM UI URL from the current kubectl context.
    ...                Extracts the cluster domain from the API server URL and constructs
    ...                the UI endpoint using the naming convention: airmui.<cluster-domain>.
    ...                Example: https://k8s.example.com:6443 -> https://airmui.example.com

    ${result}=    Run Process    kubectl    config    view    --minify    -o    jsonpath\={.clusters[0].cluster.server}
    IF    ${result.rc} != 0
        Fail    Failed to get cluster server from kubectl config: ${result.stderr}
    END

    # Extract cluster domain: https://k8s.example.com:6443 -> example.com
    ${server}=    Strip String    ${result.stdout}
    IF    "${server}" == "${EMPTY}"
        Fail    kubectl context returned an empty cluster server URL. Set AIRM_UI_URL explicitly or update the current kubeconfig context.
    END

    # Get hostname without protocol and port
    IF    "//" not in """${server}"""
        Fail    Invalid kubectl cluster server URL '${server}': expected a full URL containing '//'. Set AIRM_UI_URL explicitly or fix the current kubeconfig context.
    END
    ${hostname}=    Evaluate    "${server}".split("//", 1)[1].split(":")[0]
    IF    "${hostname}" == "${EMPTY}"
        Fail    Invalid kubectl cluster server URL '${server}': could not extract a hostname. Set AIRM_UI_URL explicitly or fix the current kubeconfig context.
    END

    # Remove first subdomain prefix to get cluster domain
    IF    "." not in """${hostname}"""
        Fail    Invalid kubectl cluster hostname '${hostname}' from server '${server}': expected at least one '.' to derive the UI URL. Set AIRM_UI_URL explicitly or fix the current kubeconfig context.
    END
    ${dot_index}=    Evaluate    "${hostname}".index(".")
    ${domain}=    Evaluate    "${hostname}"[${dot_index}+1:]

    VAR    ${url}    https://airmui.${domain}
    Log    Derived AIRM UI URL: ${url} (from server: ${server})    INFO
    RETURN    ${url}
