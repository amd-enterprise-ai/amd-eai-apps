# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def admin_token():
    """Default admin token for testing."""
    return os.getenv("ADMIN_TOKEN", "mock-admin-token")


class TestCreateApiKey:
    """Test API key creation endpoint."""

    def test_create_api_key_success(self, client, admin_token):
        """Test successful API key creation."""
        response = client.post(
            "/apikey/create",
            json={
                "ttl": "1h",
                "num_uses": 0,
                "meta": {"test": "data"},
                "renewable": True,
            },
            headers={"X-Admin-Token": admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "api_key" in data
        assert "key_id" in data
        assert "entity_id" in data
        assert data["ttl"] == "1h"
        assert data["renewable"] is True

    def test_create_api_key_no_auth(self, client):
        """Test API key creation without authentication."""
        response = client.post(
            "/apikey/create",
            json={"ttl": "1h"},
        )
        assert response.status_code == 401

    def test_create_api_key_invalid_token(self, client):
        """Test API key creation with invalid token."""
        response = client.post(
            "/apikey/create",
            json={"ttl": "1h"},
            headers={"X-Admin-Token": "invalid-token"},
        )
        assert response.status_code == 403

    def test_create_api_key_never_expires(self, client, admin_token):
        """Test API key creation with TTL=0 (never expires)."""
        response = client.post(
            "/apikey/create",
            json={"ttl": "0"},
            headers={"X-Admin-Token": admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["expire_time"] is None
        assert data["lease_duration"] == 0


class TestRevokeApiKey:
    """Test API key revocation endpoint."""

    def test_revoke_api_key_success(self, client, admin_token):
        """Test successful API key revocation."""
        # First create a key
        create_response = client.post(
            "/apikey/create",
            json={"ttl": "1h"},
            headers={"X-Admin-Token": admin_token},
        )
        key_id = create_response.json()["key_id"]

        # Revoke it
        revoke_response = client.post(
            "/apikey/revoke",
            json={"key_id": key_id},
            headers={"X-Admin-Token": admin_token},
        )
        assert revoke_response.status_code == 200

        # Verify it's revoked by looking it up
        lookup_response = client.post(
            "/apikey/lookup",
            json={"key_id": key_id},
            headers={"X-Admin-Token": admin_token},
        )
        assert lookup_response.status_code == 200
        assert lookup_response.json()["revoked"] is True

    def test_revoke_nonexistent_key(self, client, admin_token):
        """Test revoking a non-existent API key."""
        response = client.post(
            "/apikey/revoke",
            json={"key_id": "nonexistent-key-id"},
            headers={"X-Admin-Token": admin_token},
        )
        assert response.status_code == 404


class TestRenewApiKey:
    """Test API key renewal endpoint."""

    def test_renew_api_key_success(self, client, admin_token):
        """Test successful API key renewal."""
        # Create a renewable key
        create_response = client.post(
            "/apikey/create",
            json={"ttl": "1h", "renewable": True},
            headers={"X-Admin-Token": admin_token},
        )
        key_id = create_response.json()["key_id"]

        # Renew it
        renew_response = client.post(
            "/apikey/renew",
            json={"key_id": key_id, "increment": "2h"},
            headers={"X-Admin-Token": admin_token},
        )
        assert renew_response.status_code == 200
        data = renew_response.json()
        assert "lease_duration" in data
        assert data["lease_duration"] == 7200  # 2 hours in seconds

    def test_renew_non_renewable_key(self, client, admin_token):
        """Test renewing a non-renewable key."""
        # Create a non-renewable key
        create_response = client.post(
            "/apikey/create",
            json={"ttl": "1h", "renewable": False},
            headers={"X-Admin-Token": admin_token},
        )
        key_id = create_response.json()["key_id"]

        # Try to renew it
        renew_response = client.post(
            "/apikey/renew",
            json={"key_id": key_id},
            headers={"X-Admin-Token": admin_token},
        )
        assert renew_response.status_code == 400

    def test_renew_revoked_key(self, client, admin_token):
        """Test renewing a revoked key."""
        # Create and revoke a key
        create_response = client.post(
            "/apikey/create",
            json={"ttl": "1h", "renewable": True},
            headers={"X-Admin-Token": admin_token},
        )
        key_id = create_response.json()["key_id"]

        client.post(
            "/apikey/revoke",
            json={"key_id": key_id},
            headers={"X-Admin-Token": admin_token},
        )

        # Try to renew it
        renew_response = client.post(
            "/apikey/renew",
            json={"key_id": key_id},
            headers={"X-Admin-Token": admin_token},
        )
        assert renew_response.status_code == 400


class TestLookupApiKey:
    """Test API key lookup endpoint."""

    def test_lookup_api_key_success(self, client, admin_token):
        """Test successful API key lookup."""
        # Create a key
        create_response = client.post(
            "/apikey/create",
            json={"ttl": "1h", "meta": {"test": "value"}},
            headers={"X-Admin-Token": admin_token},
        )
        key_id = create_response.json()["key_id"]

        # Look it up
        lookup_response = client.post(
            "/apikey/lookup",
            json={"key_id": key_id},
            headers={"X-Admin-Token": admin_token},
        )
        assert lookup_response.status_code == 200
        data = lookup_response.json()
        assert data["key_id"] == key_id
        assert data["meta"] == {"test": "value"}
        assert data["revoked"] is False

    def test_lookup_nonexistent_key(self, client, admin_token):
        """Test looking up a non-existent API key."""
        response = client.post(
            "/apikey/lookup",
            json={"key_id": "nonexistent-key-id"},
            headers={"X-Admin-Token": admin_token},
        )
        assert response.status_code == 404


class TestCreateGroup:
    """Test group creation endpoint."""

    def test_create_group_success(self, client, admin_token):
        """Test successful group creation."""
        response = client.post(
            "/apikey/group",
            json={"name": "test-group"},
            headers={"X-Admin-Token": admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["name"] == "test-group"

    def test_create_group_with_id(self, client, admin_token):
        """Test creating a group with a specific ID."""
        response = client.post(
            "/apikey/group",
            json={"name": "test-group", "id": "custom-group-id"},
            headers={"X-Admin-Token": admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "custom-group-id"
        assert data["name"] == "test-group"


class TestDeleteGroup:
    """Test group deletion endpoint."""

    def test_delete_group_success(self, client, admin_token):
        """Test successful group deletion."""
        # Create a group
        create_response = client.post(
            "/apikey/group",
            json={"name": "test-group"},
            headers={"X-Admin-Token": admin_token},
        )
        group_id = create_response.json()["id"]

        # Delete it
        delete_response = client.delete(
            f"/apikey/group?id={group_id}",
            headers={"X-Admin-Token": admin_token},
        )
        assert delete_response.status_code == 200

    def test_delete_nonexistent_group(self, client, admin_token):
        """Test deleting a non-existent group."""
        response = client.delete(
            "/apikey/group?id=nonexistent-group-id",
            headers={"X-Admin-Token": admin_token},
        )
        assert response.status_code == 404


class TestBindApiKey:
    """Test API key binding endpoint."""

    def test_bind_api_key_to_group_success(self, client, admin_token):
        """Test successful API key binding to group."""
        # Create a key and a group
        create_key_response = client.post(
            "/apikey/create",
            json={"ttl": "1h"},
            headers={"X-Admin-Token": admin_token},
        )
        key_id = create_key_response.json()["key_id"]

        create_group_response = client.post(
            "/apikey/group",
            json={"name": "test-group"},
            headers={"X-Admin-Token": admin_token},
        )
        group_id = create_group_response.json()["id"]

        # Bind them
        bind_response = client.post(
            "/apikey/bind",
            json={"key_id": key_id, "group_id": group_id},
            headers={"X-Admin-Token": admin_token},
        )
        assert bind_response.status_code == 200
        assert group_id in bind_response.json()["groups"]

        # Verify by looking up the key
        lookup_response = client.post(
            "/apikey/lookup",
            json={"key_id": key_id},
            headers={"X-Admin-Token": admin_token},
        )
        assert group_id in lookup_response.json()["groups"]

    def test_bind_nonexistent_key(self, client, admin_token):
        """Test binding a non-existent key."""
        create_group_response = client.post(
            "/apikey/group",
            json={"name": "test-group"},
            headers={"X-Admin-Token": admin_token},
        )
        group_id = create_group_response.json()["id"]

        response = client.post(
            "/apikey/bind",
            json={"key_id": "nonexistent-key-id", "group_id": group_id},
            headers={"X-Admin-Token": admin_token},
        )
        assert response.status_code == 404

    def test_bind_to_nonexistent_group(self, client, admin_token):
        """Test binding to a non-existent group."""
        create_key_response = client.post(
            "/apikey/create",
            json={"ttl": "1h"},
            headers={"X-Admin-Token": admin_token},
        )
        key_id = create_key_response.json()["key_id"]

        response = client.post(
            "/apikey/bind",
            json={"key_id": key_id, "group_id": "nonexistent-group-id"},
            headers={"X-Admin-Token": admin_token},
        )
        assert response.status_code == 404


class TestUnbindApiKey:
    """Test API key unbinding endpoint."""

    def test_unbind_api_key_from_group_success(self, client, admin_token):
        """Test successful API key unbinding from group."""
        # Create a key and a group, then bind them
        create_key_response = client.post(
            "/apikey/create",
            json={"ttl": "1h"},
            headers={"X-Admin-Token": admin_token},
        )
        key_id = create_key_response.json()["key_id"]

        create_group_response = client.post(
            "/apikey/group",
            json={"name": "test-group"},
            headers={"X-Admin-Token": admin_token},
        )
        group_id = create_group_response.json()["id"]

        client.post(
            "/apikey/bind",
            json={"key_id": key_id, "group_id": group_id},
            headers={"X-Admin-Token": admin_token},
        )

        # Unbind them
        unbind_response = client.post(
            "/apikey/unbind",
            json={"key_id": key_id, "group_id": group_id},
            headers={"X-Admin-Token": admin_token},
        )
        assert unbind_response.status_code == 200
        assert group_id not in unbind_response.json()["groups"]

        # Verify by looking up the key
        lookup_response = client.post(
            "/apikey/lookup",
            json={"key_id": key_id},
            headers={"X-Admin-Token": admin_token},
        )
        assert group_id not in lookup_response.json()["groups"]


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
