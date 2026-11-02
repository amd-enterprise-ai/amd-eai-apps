#!/usr/bin/env python3
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Provision the non-administrator identity the E2E RBAC suites authenticate as.

The realm ships with a single administrator account, so every suite that needs a
second, unprivileged identity has nothing to log in as. This script creates that
account (or repairs it) through the Keycloak Admin REST API using the same
service-account client AIRM itself uses for user management.

Two properties of the account are load-bearing and easy to lose:

* ``firstName``/``lastName`` must be set. AIRM only lists Keycloak users with a
  complete profile under ``GET /v1/users``, and the suites find the account there
  to add it to a project.
* ``requiredActions`` must stay empty. Keycloak refuses a direct password grant
  while any action is pending, which is what an invite-flow account would carry.

Standard library only: the Job runs on a stock Python image with nothing installed.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

# Keycloak may still be starting, or external-secrets may not have reconciled the
# realm's clients yet, when the chart is applied. Keep retrying for a few minutes
# rather than leaving the realm without the account until the next chart apply.
STARTUP_TIMEOUT_SECONDS = 300
RETRY_INTERVAL_SECONDS = 10
REQUEST_TIMEOUT_SECONDS = 15

Transport = Callable[..., tuple[int, str]]


class KeycloakError(Exception):
    """A Keycloak request returned a status the caller cannot proceed from."""


def http_request(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
) -> tuple[int, str]:
    """Perform one HTTP request and return its status and decoded body.

    Error *statuses* come back as values so callers can branch on them; transport
    failures (Keycloak not up, DNS not resolving) propagate as ``OSError`` so the
    retry loop can tell "not ready yet" from "answered, and said no".
    """
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed http(s) URL from config
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


class KeycloakAdmin:
    """Minimal Admin REST API client for the handful of calls this script makes."""

    def __init__(self, base_url: str, realm: str, transport: Transport = http_request):
        self._base_url = base_url.rstrip("/")
        self._realm = realm
        self._transport = transport
        self._token: str | None = None

    @staticmethod
    def _decode_json(payload: str, operation: str) -> dict | list:
        try:
            return json.loads(payload)
        except (json.JSONDecodeError, TypeError) as exc:
            raise KeycloakError(f"{operation} returned malformed JSON: {exc}") from exc

    def authenticate(self, client_id: str, client_secret: str) -> None:
        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            }
        ).encode()
        status, payload = self._transport(
            "POST",
            f"{self._base_url}/realms/{self._realm}/protocol/openid-connect/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if status != 200:
            raise KeycloakError(f"admin token request failed ({status}): {payload}")
        token_response = self._decode_json(payload, "admin token request")
        if not isinstance(token_response, dict) or not token_response.get("access_token"):
            raise KeycloakError("admin token response has no access_token")
        self._token = str(token_response["access_token"])

    def _admin_request(self, method: str, path: str, body: dict | None = None) -> tuple[int, str]:
        if self._token is None:
            # Deliberately not a KeycloakError: the retry loop in main() treats those as
            # "Keycloak is not up yet" and would spend the whole startup budget retrying a
            # mistake no amount of waiting fixes.
            raise RuntimeError("KeycloakAdmin.authenticate() must be called before any admin request")
        headers = {"Authorization": f"Bearer {self._token}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        return self._transport(
            method,
            f"{self._base_url}/admin/realms/{self._realm}{path}",
            data=data,
            headers=headers,
        )

    def find_user(self, username: str) -> dict | None:
        query = urllib.parse.urlencode({"username": username, "exact": "true"})
        status, payload = self._admin_request("GET", f"/users?{query}")
        if status != 200:
            raise KeycloakError(f"user lookup for {username!r} failed ({status}): {payload}")
        users = self._decode_json(payload, f"user lookup for {username!r}")
        if not isinstance(users, list):
            raise KeycloakError(f"user lookup for {username!r} returned a non-list JSON value")
        return users[0] if users else None

    def create_user(self, profile: dict) -> None:
        status, payload = self._admin_request("POST", "/users", profile)
        if status != 201:
            raise KeycloakError(f"user creation failed ({status}): {payload}")

    def update_user(self, user_id: str, profile: dict) -> None:
        status, payload = self._admin_request("PUT", f"/users/{user_id}", profile)
        if status not in (200, 204):
            raise KeycloakError(f"user update failed ({status}): {payload}")

    def set_password(self, user_id: str, password: str) -> None:
        status, payload = self._admin_request(
            "PUT",
            f"/users/{user_id}/reset-password",
            {"type": "password", "value": password, "temporary": False},
        )
        if status not in (200, 204):
            raise KeycloakError(f"password reset failed ({status}): {payload}")


def user_profile(username: str, first_name: str, last_name: str) -> dict:
    return {
        "username": username,
        "email": username,
        "firstName": first_name,
        "lastName": last_name,
        "emailVerified": True,
        "enabled": True,
        "requiredActions": [],
    }


def provision(admin: KeycloakAdmin, username: str, password: str, first_name: str, last_name: str) -> bool:
    """Create or repair the account and set its password. Returns True when created.

    Repair matters as much as creation: an account left over from an invite flow is
    present but unusable, and re-running has to converge it to a working state.
    """
    profile = user_profile(username, first_name, last_name)
    existing = admin.find_user(username)

    if existing is None:
        admin.create_user(profile)
        user = admin.find_user(username)
        if user is None:
            raise KeycloakError(f"Keycloak accepted the creation of {username!r} but the account is not queryable")
    else:
        user = existing
        # Keycloak rejects a username change when editUsernameAllowed is off, so an
        # update must not restate it even though the value is unchanged.
        admin.update_user(user["id"], {k: v for k, v in profile.items() if k != "username"})

    admin.set_password(user["id"], password)
    return existing is None


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"ERROR: {name} is required")
    return value


def resolve_profile_name(value: str | None, default: str) -> str:
    """Return a non-empty profile name even when an env var is blank or padded."""
    return (value or "").strip() or default


def main() -> int:
    keycloak_url = _required_env("KEYCLOAK_URL")
    realm = _required_env("KEYCLOAK_REALM")
    client_id = _required_env("KEYCLOAK_ADMIN_CLIENT_ID")
    client_secret = _required_env("KEYCLOAK_ADMIN_CLIENT_SECRET")
    username = _required_env("TEAM_MEMBER_USERNAME")
    password = _required_env("TEAM_MEMBER_PASSWORD")
    # `or`, not a get() default: an env var set to the empty string would otherwise pass
    # through and leave the profile incomplete, which AIRM reports as an invited rather
    # than an active user. The account then never appears in the user list the suites
    # search, so they fail to find a team member that Keycloak holds perfectly well.
    first_name = resolve_profile_name(os.environ.get("TEAM_MEMBER_FIRST_NAME"), "Team")
    last_name = resolve_profile_name(os.environ.get("TEAM_MEMBER_LAST_NAME"), "Member")

    admin = KeycloakAdmin(keycloak_url, realm)
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS

    while True:
        try:
            admin.authenticate(client_id, client_secret)
            created = provision(admin, username, password, first_name, last_name)
        except (KeycloakError, OSError) as exc:
            if time.monotonic() >= deadline:
                print(f"ERROR: could not provision {username!r} in realm {realm!r}: {exc}", flush=True)
                return 1
            print(f"Keycloak not ready ({exc}); retrying in {RETRY_INTERVAL_SECONDS}s", flush=True)
            time.sleep(RETRY_INTERVAL_SECONDS)
            continue

        action = "Created" if created else "Updated"
        print(f"{action} team member {username!r} in realm {realm!r}", flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
