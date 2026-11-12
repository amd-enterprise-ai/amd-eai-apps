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

import json
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


def _parse_admin_groups(raw: str) -> frozenset[str]:
    """Parse OIDC_ADMIN_GROUPS, a JSON list of group names, refusing anything else.

    A JSON list keeps every name intact, so a name containing a comma, such as an
    LDAP distinguished name, stays one group instead of widening the trusted set.
    Names are kept exactly as written, because the groups claim is matched exactly.
    """
    if not raw.strip():
        return frozenset()
    try:
        groups = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OIDC_ADMIN_GROUPS must be a JSON list of group names: {exc}") from None
    if not isinstance(groups, list) or not all(isinstance(group, str) and group for group in groups):
        raise RuntimeError("OIDC_ADMIN_GROUPS must be a JSON list of non-empty group names")
    return frozenset(groups)


# Groups of the `groups` claim whose members are Platform Administrators, for an
# issuer that emits no Keycloak realm roles. Empty: only the realm role grants it.
# Every client of an issuer gets the same groups in its tokens, so trusting a group
# needs the audience check to reject a token minted for another client.
OIDC_ADMIN_GROUPS = _parse_admin_groups(os.getenv("OIDC_ADMIN_GROUPS", ""))
if OIDC_ADMIN_GROUPS and OIDC_AUDIENCE is None:
    raise RuntimeError("OIDC_ADMIN_GROUPS is set without OIDC_AUDIENCE; set the audience the API requires")
