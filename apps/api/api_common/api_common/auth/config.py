# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Shared OIDC configuration.

Configuration of the AIWB token validation. AIRM validates its tokens on its
own path and does not read these values. The OIDC_* values are the generic
ones. Their defaults derive from the Keycloak values, so an installation that
sets only KEYCLOAK_* keeps its behaviour.
"""

import os

KEYCLOAK_INTERNAL_URL = os.getenv("KEYCLOAK_INTERNAL_URL", "http://localhost:8080")
KEYCLOAK_PUBLIC_URL = os.getenv("KEYCLOAK_PUBLIC_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "platform")
OPENID_CONFIGURATION_URL = os.getenv(
    "OPENID_CONFIGURATION_URL", f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}/.well-known/openid-configuration"
)
DISABLE_JWT_VALIDATION = os.getenv("DISABLE_JWT_VALIDATION", "false") == "true"

# The JWKS endpoint that signs the access tokens. It must be reachable from
# inside the cluster.
OIDC_JWKS_URL = (
    os.getenv("OIDC_JWKS_URL") or f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
)
# The `iss` claim is always checked. Without OIDC_ISSUER the value derives from
# the Keycloak values, the same way OPENID_CONFIGURATION_URL does, so no
# installation can lose the check by accident.
OIDC_ISSUER = os.getenv("OIDC_ISSUER") or f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}"
# The `aud` claim is checked only when OIDC_AUDIENCE is set. A Keycloak access
# token carries `account`, a Dex access token carries the client id.
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE") or None
