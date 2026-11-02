<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AMD Resource Manager UI

The frontend interface for AMD AI Resource Manager. This UI connects to the AIRM API and provides resource management features including cluster onboarding, quota allocation, project management, and job monitoring.

## Settings

### Environment variables

The app has various settings and features that can be set or toggled using environment variables:

- NEXTAUTH_SECRET: the secret used by next-auth for authentication. See the `.env.local.example` file.
- NEXTAUTH_URL: the url the app will run on. This is used by next-auth for authentication. See the `.env.local.example` file.
- OIDC_CLIENT_ID: ID for the OIDC client used by next-auth for authentication
- OIDC_CLIENT_SECRET: the secret for the OIDC authentication client used by next-auth for authentication
- OIDC_ISSUER: the URL to the OIDC issuer (e.g., `https://kc.<your-domain>/realms/airm`)
- OIDC_ISSUER_INTERNAL_URL: the issuer URL as the app reaches it, when it differs from `OIDC_ISSUER` (optional)

The app also accepts the older `KEYCLOAK_ID`, `KEYCLOAK_SECRET`, `KEYCLOAK_ISSUER` and `KEYCLOAK_ISSUER_INTERNAL_URL` names as a fallback.
- AIRM_API_SERVICE_URL: the URL for the AIRM SERVICE API (for local development set to `http://localhost:8001`)

## Running locally

You will need all the values specified in the [environment variables section](#environment-variables) - If you are running the AIRM API locally, you can use the pre-populated values for all environment variables.
However, if your UI is connecting to the AIRM API in a different environment (OCI for example), the following 3 variables need to correspond to the environment where the API is running (ask a colleague)

- `OIDC_CLIENT_SECRET`, `OIDC_CLIENT_ID`, and `OIDC_ISSUER` for authentication.

Here are the instructions for running locally:

- Install pnpm: https://pnpm.io/installation
- Run `pnpm install`
- Copy the `.env.local.example` to `.env.local` and configure the variables.

  - setup connection to other services, for example locally:

    - `AIRM_API_SERVICE_URL=http://localhost:8001`

  - Configure authentication:
    - Setup OIDC authentication by configuring the environment variables `OIDC_CLIENT_SECRET`, `OIDC_CLIENT_ID`
      and `OIDC_ISSUER` if you are not running the AIRM API locally.
      The easiest way is to get these values from someone in the team.

- Run `pnpm dev`
- Access the app at http://localhost:8010

> **Note:** The default username and password is `devuser@amd.com` and `password`.

## Code quality hooks

See [Repository Setup](../../../README.md#repository-setup) for installing prek hooks. Use `git commit --no-verify` or `git push --no-verify` to skip hooks for a single command.

## Running tests locally

Prior to submitting a pull request, make sure that the tests pass locally.
To run tests, run the following from the root of the UI code base

```bash
pnpm test
```

## Builds and deployment

### Build the docker image

Docker image building process is done at each push event for each branch, main included.
The docker images have the following format:

```txt
amdenterpriseai/airm-ui:<branch-name>-<commit-hash>
```

E.g. amdenterpriseai/airm-ui:main-b973967
