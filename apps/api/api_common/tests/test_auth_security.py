# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import importlib
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt import PyJWKClient
from jwt.algorithms import RSAAlgorithm

from api_common.auth import config as auth_config
from api_common.auth import security as auth_security

ISSUER = "https://auth.example.com"
KID = "test-key"


@pytest.fixture(scope="module")
def key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, other_key


@pytest.fixture(scope="module")
def jwks(key_pair):
    private_key, _ = key_pair
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    return {"keys": [{**public_jwk, "kid": KID, "alg": "RS256", "use": "sig"}]}


def mint(private_key: rsa.RSAPrivateKey, **claims: Any) -> str:
    payload = {
        "iss": ISSUER,
        "sub": "user-1",
        "aud": "aiwb",
        "email": "user@example.com",
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
    }
    payload.update(claims)
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": KID})


@pytest.fixture
def security(monkeypatch, jwks):
    """Load the auth modules with the given environment and a fake JWKS."""

    def load(**env):
        for name in ("OIDC_JWKS_URL", "OIDC_ISSUER", "OIDC_AUDIENCE", "OIDC_ADMIN_GROUPS", "DISABLE_JWT_VALIDATION"):
            monkeypatch.delenv(name, raising=False)
        env.setdefault("OIDC_ISSUER", ISSUER)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        monkeypatch.setattr(PyJWKClient, "fetch_data", lambda self: jwks)
        importlib.reload(auth_config)
        return importlib.reload(auth_security)

    return load


def test_valid_token_returns_claims(security, key_pair):
    private_key, _ = key_pair
    module = security()

    claims = module.auth_token_claimset(f"Bearer {mint(private_key, groups=['team-a'])}")

    assert claims["email"] == "user@example.com"
    assert module.get_user_email(claims) == "user@example.com"
    assert module.get_user_groups(claims) == ["team-a"]


def test_expired_token_is_401(security, key_pair):
    private_key, _ = key_pair
    module = security()

    with pytest.raises(HTTPException) as exc:
        module.auth_token_claimset(f"Bearer {mint(private_key, exp=int(time.time()) - 10)}")

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token expired"


def test_token_from_another_key_is_401(security, key_pair):
    _, other_key = key_pair
    module = security()

    with pytest.raises(HTTPException) as exc:
        module.auth_token_claimset(f"Bearer {mint(other_key)}")

    assert exc.value.status_code == 401
    assert "Validation of token failed" in exc.value.detail


def test_unsigned_token_is_401(security, key_pair):
    private_key, _ = key_pair
    module = security()
    token = jwt.encode({"email": "x@example.com", "exp": int(time.time()) + 300}, "", algorithm="none")

    with pytest.raises(HTTPException) as exc:
        module.auth_token_claimset(f"Bearer {token}")

    assert exc.value.status_code == 401


def test_unsigned_token_with_a_known_key_id_is_401(security, key_pair):
    """The algorithm list rejects alg=none even when the key id resolves."""
    module = security()
    claims = {"iss": ISSUER, "email": "x@example.com", "exp": int(time.time()) + 300}
    token = jwt.encode(claims, "", algorithm="none", headers={"kid": KID})

    with pytest.raises(HTTPException) as exc:
        module.auth_token_claimset(f"Bearer {token}")

    assert exc.value.status_code == 401
    assert "Validation of token failed" in exc.value.detail


def test_wrong_scheme_is_401(security, key_pair):
    private_key, _ = key_pair
    module = security()

    with pytest.raises(HTTPException) as exc:
        module.auth_token_claimset(f"Basic {mint(private_key)}")

    assert exc.value.status_code == 401
    assert "Bearer" in exc.value.detail


def test_issuer_is_checked(security, key_pair):
    private_key, _ = key_pair
    module = security(OIDC_ISSUER=ISSUER)

    assert module.auth_token_claimset(f"Bearer {mint(private_key)}")

    with pytest.raises(HTTPException) as exc:
        module.auth_token_claimset(f"Bearer {mint(private_key, iss='https://other.example.com')}")
    assert exc.value.status_code == 401


def test_issuer_is_checked_without_oidc_issuer(security, monkeypatch, key_pair):
    """An empty OIDC_ISSUER falls back to the Keycloak issuer, it never turns the check off."""
    private_key, _ = key_pair
    monkeypatch.setenv("KEYCLOAK_PUBLIC_URL", "https://kc.example.com")
    monkeypatch.setenv("KEYCLOAK_REALM", "airm")
    module = security(OIDC_ISSUER="")

    assert module.auth_token_claimset(f"Bearer {mint(private_key, iss='https://kc.example.com/realms/airm')}")

    with pytest.raises(HTTPException) as exc:
        module.auth_token_claimset(f"Bearer {mint(private_key)}")
    assert exc.value.status_code == 401


def test_audience_is_checked_only_when_configured(security, key_pair):
    private_key, _ = key_pair

    module = security()
    assert module.auth_token_claimset(f"Bearer {mint(private_key, aud='account')}")

    module = security(OIDC_AUDIENCE="aiwb")
    assert module.auth_token_claimset(f"Bearer {mint(private_key, aud='aiwb')}")
    with pytest.raises(HTTPException) as exc:
        module.auth_token_claimset(f"Bearer {mint(private_key, aud='account')}")
    assert exc.value.status_code == 401


def test_disabled_validation_skips_the_signature(security, key_pair):
    _, other_key = key_pair
    module = security(DISABLE_JWT_VALIDATION="true")

    claims = module.auth_token_claimset(f"Bearer {mint(other_key)}")

    assert claims["email"] == "user@example.com"


def test_email_is_required(security):
    module = security()

    with pytest.raises(HTTPException) as exc:
        module.get_user_email({"sub": "user-1"})

    assert exc.value.status_code == 403


def test_groups_default_to_empty_list(security):
    module = security()

    assert module.get_user_groups({}) == []
    assert module.get_user_groups({"groups": "not-a-list"}) == []


def test_platform_administrator_role_is_accepted(security):
    module = security()

    assert (
        module.ensure_platform_administrator({"realm_access": {"roles": ["Team Member", "Platform Administrator"]}})
        is None
    )


@pytest.mark.parametrize(
    "claimset",
    [
        {},
        {"realm_access": {}},
        {"realm_access": {"roles": ["Team Member"]}},
        {"realm_access": {"roles": "Platform Administrator"}},
        {"realm_access": "Platform Administrator"},
        {"groups": ["Platform Administrator"]},
    ],
)
def test_platform_administrator_role_is_required(security, claimset):
    """A missing or malformed role claim, or the role name arriving as a group, never grants the role."""
    module = security()

    with pytest.raises(HTTPException) as exc:
        module.ensure_platform_administrator(claimset)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Missing required role: Platform Administrator"


def test_configured_admin_group_grants_the_role(security):
    """An issuer without realm roles can name the group whose members are administrators."""
    module = security(OIDC_ADMIN_GROUPS='["platform-admins", "ops"]', OIDC_AUDIENCE="aiwb")

    assert module.ensure_platform_administrator({"groups": ["team-a", "ops"]}) is None


def test_admin_group_name_with_a_comma_stays_one_group(security):
    """A comma inside a name, as in an LDAP distinguished name, must not split it into broader groups."""
    module = security(OIDC_ADMIN_GROUPS='["cn=admins,ou=groups"]', OIDC_AUDIENCE="aiwb")

    assert module.ensure_platform_administrator({"groups": ["cn=admins,ou=groups"]}) is None
    for partial in ("cn=admins", "ou=groups"):
        with pytest.raises(HTTPException) as exc:
            module.ensure_platform_administrator({"groups": [partial]})
        assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "raw",
    ["platform-admins", "platform-admins,ops", '"platform-admins"', '{"group": "x"}', '[""]', '["ok", 1]', "[null]"],
)
def test_malformed_admin_groups_refuse_to_start(security, raw):
    """Anything but a JSON list of non-empty names is a misconfiguration, never a guess at what was meant."""
    with pytest.raises(RuntimeError, match="OIDC_ADMIN_GROUPS must be a JSON list"):
        security(OIDC_ADMIN_GROUPS=raw, OIDC_AUDIENCE="aiwb")


@pytest.mark.parametrize(
    "claimset",
    [
        {"groups": ["team-a"]},
        {"groups": "platform-admins"},
        {"groups": [{"name": "platform-admins"}]},
        {"groups": ["/platform-admins"]},
    ],
)
def test_admin_group_must_match_exactly(security, claimset):
    """Only an exact group name in a list grants the role; a path, a string or an object does not."""
    module = security(OIDC_ADMIN_GROUPS='["platform-admins"]', OIDC_AUDIENCE="aiwb")

    with pytest.raises(HTTPException) as exc:
        module.ensure_platform_administrator(claimset)

    assert exc.value.status_code == 403


@pytest.mark.parametrize("groups", ["a", "team-a"])
def test_groups_claim_as_a_string_never_grants_the_role(security, groups):
    """A string claim iterates as characters, so only the list check stops it matching a one-character group."""
    module = security(OIDC_ADMIN_GROUPS='["a"]', OIDC_AUDIENCE="aiwb")

    with pytest.raises(HTTPException) as exc:
        module.ensure_platform_administrator({"groups": groups})

    assert exc.value.status_code == 403


def test_realm_role_still_grants_the_role_with_admin_groups(security):
    module = security(OIDC_ADMIN_GROUPS='["platform-admins"]', OIDC_AUDIENCE="aiwb")

    assert module.ensure_platform_administrator({"realm_access": {"roles": ["Platform Administrator"]}}) is None


def test_admin_groups_require_an_audience(security):
    """Every client of an issuer gets the same groups, so trusting one needs the audience check."""
    with pytest.raises(RuntimeError, match="OIDC_AUDIENCE"):
        security(OIDC_ADMIN_GROUPS='["platform-admins"]')


def test_empty_jwks_url_falls_back_to_keycloak(security):
    security(OIDC_JWKS_URL="", KEYCLOAK_INTERNAL_URL="http://kc.internal:8080", KEYCLOAK_REALM="airm")

    assert auth_config.OIDC_JWKS_URL == "http://kc.internal:8080/realms/airm/protocol/openid-connect/certs"
