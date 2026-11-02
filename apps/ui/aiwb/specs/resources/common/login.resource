# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

*** Settings ***
Documentation       Keycloak browser login flow for UI E2E tests.
...                 Handles the three-step login: NextAuth → Keycloak email → password → redirect.
...                 Credentials are extracted from the kubeconfig OIDC configuration.
Library             UICredentials


*** Variables ***
${LOGIN_TIMEOUT}    30s
# The NextAuth page names the button after the provider. The name is OIDC, and
# an environment before the OIDC login still says Keycloak.
${SIGN_IN_BUTTON}    button >> text=/^Sign in with (OIDC|Keycloak)$/


*** Keywords ***
Log in via Keycloak
    [Documentation]    Performs full browser login via Keycloak using kubeconfig credentials.
    ...                Navigates directly to /api/auth/signin to bypass JS redirect delay,
    ...                then completes Keycloak OAuth flow: username → password → redirect.
    ...                Expects a browser page to already be open.
    [Arguments]    ${base_url}

    ${username}=    Get UI Username
    ${password}=    Get UI Password
    Log in via Keycloak With Credentials    ${base_url}    ${username}    ${password}

Log in via Keycloak With Credentials
    [Documentation]    Performs full browser login via Keycloak with explicit credentials.
    ...                Navigates directly to /api/auth/signin to bypass JS redirect delay,
    ...                then completes Keycloak OAuth flow: username → password → redirect.
    ...                Expects a browser page to already be open.
    [Arguments]    ${base_url}    ${username}    ${password}

    Go To    ${base_url}/api/auth/signin

    # Step 1: NextAuth page - click the sign-in button
    Wait For Elements State    ${SIGN_IN_BUTTON}    visible    timeout=${LOGIN_TIMEOUT}
    Click    ${SIGN_IN_BUTTON}

    # Step 2: Keycloak login form - enter username/email and submit
    Wait For Elements State    css=#username    visible    timeout=${LOGIN_TIMEOUT}
    Fill Text    css=#username    ${username}
    Click    css=#kc-login

    # Step 3: Enter password and submit
    Wait For Elements State    css=#password    visible    timeout=${LOGIN_TIMEOUT}
    Fill Text    css=#password    ${password}
    Click    css=#kc-login

    # Wait for redirect back to the app (main content loads)
    Wait For Elements State    css=main    visible    timeout=${LOGIN_TIMEOUT}
    Log    Successfully logged in as ${username}    INFO

User logs out
    [Documentation]    Logs out the current user from AIWB by clearing the session.
    ...                Uses Browser Library to delete session cookies, navigate to the sign-in page,
    ...                and wait until the sign-in prompt is visible to confirm logout completed.
    [Arguments]    ${base_url}

    # Delete all cookies to clear the session
    Delete All Cookies
    # Navigate to the app sign-in route and verify the logged-out state is visible
    Go To    ${base_url}/api/auth/signin
    Wait For Elements State    ${SIGN_IN_BUTTON}    visible    timeout=${LOGIN_TIMEOUT}
    Log    User logged out    INFO
