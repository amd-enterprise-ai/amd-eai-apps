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
        for name in ("OIDC_JWKS_URL", "OIDC_ISSUER", "OIDC_AUDIENCE", "DISABLE_JWT_VALIDATION"):
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


def test_empty_jwks_url_falls_back_to_keycloak(security):
    security(OIDC_JWKS_URL="", KEYCLOAK_INTERNAL_URL="http://kc.internal:8080", KEYCLOAK_REALM="airm")

    assert auth_config.OIDC_JWKS_URL == "http://kc.internal:8080/realms/airm/protocol/openid-connect/certs"
