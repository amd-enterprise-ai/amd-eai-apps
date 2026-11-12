# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Shared OIDC JWT authentication.

AIWB verifies its tokens here. Any OIDC issuer works: the token is verified
with the keys of the JWKS endpoint in the configuration. AIRM uses only
OpenIdAuthorization and keeps its own token validation.
"""

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OpenIdConnect
from jwt import ExpiredSignatureError, PyJWKClient
from loguru import logger

from .config import (
    DISABLE_JWT_VALIDATION,
    OIDC_ADMIN_GROUPS,
    OIDC_AUDIENCE,
    OIDC_ISSUER,
    OIDC_JWKS_URL,
    OPENID_CONFIGURATION_URL,
)

ALLOWED_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]

# The realm role AIRM grants its administrators, carried in `realm_access.roles`.
PLATFORM_ADMINISTRATOR_ROLE = "Platform Administrator"

# The client fetches the keys on first use and caches them. An unknown key id
# triggers a refresh, so a key rotation on the issuer needs no restart.
JWK_CLIENT = PyJWKClient(OIDC_JWKS_URL, cache_keys=True)


class OpenIdAuthorization(OpenIdConnect):
    """Return 401 with correct headers instead of 403 when auth is missing."""

    async def __call__(self, request: Request) -> str | None:
        authorization = request.headers.get("Authorization")
        if not authorization:
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unauthorized",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                return None
        return authorization


BearerToken = OpenIdAuthorization(openIdConnectUrl=OPENID_CONFIGURATION_URL, auto_error=True)


def decode_token(token: str) -> dict:
    """Verify the token with the issuer keys and return its claims."""
    if DISABLE_JWT_VALIDATION:
        return jwt.decode(token, options={"verify_signature": False})
    signing_key = JWK_CLIENT.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=ALLOWED_ALGORITHMS,
        issuer=OIDC_ISSUER,
        audience=OIDC_AUDIENCE,
        options={"verify_aud": OIDC_AUDIENCE is not None},
    )


def auth_token_claimset(authorization: str = Depends(BearerToken)) -> dict:
    """Parse and verify JWT token from Authorization header."""
    if authorization is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No Authorization header")
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token scheme. Please include Bearer in Authorization header.",
            )
        decoded = decode_token(token)
        logger.debug(f"Decoded token claims: email={decoded.get('email')}, groups={decoded.get('groups')}")
        return decoded
    except HTTPException:
        raise
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except Exception as exc:
        logger.exception("Exception while reading token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Validation of token failed: {exc}")


def get_user_email(claimset: dict = Depends(auth_token_claimset)) -> str:
    """Extract user email from JWT token."""
    email = claimset.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No user email in token")
    return email


def get_user_groups(claimset: dict = Depends(auth_token_claimset)) -> list[str]:
    """Extract group names from JWT token."""
    groups = claimset.get("groups", [])
    return groups if isinstance(groups, list) else []


def ensure_platform_administrator(claimset: dict = Depends(auth_token_claimset)) -> None:
    """Reject callers who are not Platform Administrators.

    Guards cluster-wide state that no single project owns. The realm role grants it,
    and so does membership of a group in OIDC_ADMIN_GROUPS. A token with neither,
    such as one from an issuer without realm roles and no admin group configured,
    gets 403, so the guarded routes stay closed.
    """
    realm_access = claimset.get("realm_access")
    roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
    if isinstance(roles, list) and PLATFORM_ADMINISTRATOR_ROLE in roles:
        return
    groups = claimset.get("groups")
    if isinstance(groups, list) and OIDC_ADMIN_GROUPS.intersection(g for g in groups if isinstance(g, str)):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Missing required role: {PLATFORM_ADMINISTRATOR_ROLE}",
    )
