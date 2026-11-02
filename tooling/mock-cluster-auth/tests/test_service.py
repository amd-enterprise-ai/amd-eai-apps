# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import pytest

from app.service import ClusterAuthService


@pytest.fixture
def service():
    """Create a fresh service instance for each test."""
    return ClusterAuthService()


class TestTtlParsing:
    """Test TTL parsing functionality."""

    def test_parse_hours(self, service):
        """Test parsing hours."""
        assert service._parse_ttl("1h") == 3600
        assert service._parse_ttl("24h") == 86400

    def test_parse_days(self, service):
        """Test parsing days."""
        assert service._parse_ttl("1d") == 86400
        assert service._parse_ttl("7d") == 604800

    def test_parse_minutes(self, service):
        """Test parsing minutes."""
        assert service._parse_ttl("30m") == 1800
        assert service._parse_ttl("5m") == 300

    def test_parse_seconds(self, service):
        """Test parsing seconds."""
        assert service._parse_ttl("60s") == 60
        assert service._parse_ttl("300s") == 300

    def test_parse_never_expires(self, service):
        """Test parsing '0' for never expires."""
        assert service._parse_ttl("0") == 0
        assert service._parse_ttl("") == 0

    def test_parse_numeric_seconds(self, service):
        """Test parsing numeric values as seconds."""
        assert service._parse_ttl("100") == 100


class TestApiKeyGeneration:
    """Test API key generation."""

    def test_generate_api_key_format(self, service):
        """Test API key format."""
        api_key = service._generate_api_key()
        assert api_key.startswith("amd_aim_api_key_")
        assert len(api_key) > len("amd_aim_api_key_") + 10  # Should have hex after prefix

    def test_generate_key_id_format(self, service):
        """Test key ID format (UUID)."""
        key_id = service._generate_key_id()
        assert len(key_id) == 36  # UUID format
        assert key_id.count("-") == 4


class TestCreateApiKey:
    """Test API key creation."""

    @pytest.mark.asyncio
    async def test_create_api_key_defaults(self, service):
        """Test creating API key with defaults."""
        result = await service.create_api_key()
        assert "api_key" in result
        assert "key_id" in result
        assert "entity_id" in result
        assert result["ttl"] == "0"
        assert result["renewable"] is True
        assert result["expire_time"] is None

    @pytest.mark.asyncio
    async def test_create_api_key_with_ttl(self, service):
        """Test creating API key with TTL."""
        result = await service.create_api_key(ttl="1h")
        assert result["ttl"] == "1h"
        assert result["lease_duration"] == 3600
        assert result["expire_time"] is not None

    @pytest.mark.asyncio
    async def test_create_api_key_with_meta(self, service):
        """Test creating API key with metadata."""
        meta = {"test": "value", "number": 42}
        result = await service.create_api_key(meta=meta)
        lookup_result = await service.lookup_api_key(result["key_id"])
        assert lookup_result["meta"] == meta


class TestRevokeApiKey:
    """Test API key revocation."""

    @pytest.mark.asyncio
    async def test_revoke_api_key(self, service):
        """Test revoking an API key."""
        result = await service.create_api_key()
        key_id = result["key_id"]

        await service.revoke_api_key(key_id)

        lookup_result = await service.lookup_api_key(key_id)
        assert lookup_result["revoked"] is True

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_key(self, service):
        """Test revoking a non-existent key."""
        with pytest.raises(KeyError):
            await service.revoke_api_key("nonexistent-key-id")


class TestRenewApiKey:
    """Test API key renewal."""

    @pytest.mark.asyncio
    async def test_renew_api_key(self, service):
        """Test renewing an API key."""
        result = await service.create_api_key(ttl="1h", renewable=True)
        key_id = result["key_id"]

        renew_result = await service.renew_api_key(key_id, increment="2h")
        assert renew_result["lease_duration"] == 7200  # 2 hours

    @pytest.mark.asyncio
    async def test_renew_non_renewable_key(self, service):
        """Test renewing a non-renewable key."""
        result = await service.create_api_key(ttl="1h", renewable=False)
        key_id = result["key_id"]

        with pytest.raises(ValueError, match="not renewable"):
            await service.renew_api_key(key_id)

    @pytest.mark.asyncio
    async def test_renew_revoked_key(self, service):
        """Test renewing a revoked key."""
        result = await service.create_api_key(ttl="1h", renewable=True)
        key_id = result["key_id"]

        await service.revoke_api_key(key_id)

        with pytest.raises(ValueError, match="revoked"):
            await service.renew_api_key(key_id)


class TestGroupOperations:
    """Test group operations."""

    @pytest.mark.asyncio
    async def test_create_group_defaults(self, service):
        """Test creating group with defaults."""
        result = await service.create_group()
        assert "id" in result
        assert "name" in result
        assert result["name"] == result["id"]  # Name defaults to ID

    @pytest.mark.asyncio
    async def test_create_group_with_name(self, service):
        """Test creating group with name."""
        result = await service.create_group(name="test-group")
        assert result["name"] == "test-group"

    @pytest.mark.asyncio
    async def test_create_group_with_id(self, service):
        """Test creating group with custom ID."""
        result = await service.create_group(name="test-group", group_id="custom-id")
        assert result["id"] == "custom-id"
        assert result["name"] == "test-group"

    @pytest.mark.asyncio
    async def test_delete_group(self, service):
        """Test deleting a group."""
        result = await service.create_group(name="test-group")
        group_id = result["id"]

        await service.delete_group(group_id)

        # Verify it's deleted
        with pytest.raises(KeyError):
            await service.delete_group(group_id)


class TestBindingOperations:
    """Test API key to group binding operations."""

    @pytest.mark.asyncio
    async def test_bind_api_key_to_group(self, service):
        """Test binding API key to group."""
        key_result = await service.create_api_key()
        key_id = key_result["key_id"]

        group_result = await service.create_group(name="test-group")
        group_id = group_result["id"]

        bind_result = await service.bind_api_key_to_group(key_id, group_id)
        assert group_id in bind_result["groups"]

        # Verify by looking up the key
        lookup_result = await service.lookup_api_key(key_id)
        assert group_id in lookup_result["groups"]

    @pytest.mark.asyncio
    async def test_unbind_api_key_from_group(self, service):
        """Test unbinding API key from group."""
        key_result = await service.create_api_key()
        key_id = key_result["key_id"]

        group_result = await service.create_group(name="test-group")
        group_id = group_result["id"]

        await service.bind_api_key_to_group(key_id, group_id)
        unbind_result = await service.unbind_api_key_from_group(key_id, group_id)

        assert group_id not in unbind_result["groups"]

        # Verify by looking up the key
        lookup_result = await service.lookup_api_key(key_id)
        assert group_id not in lookup_result["groups"]

    @pytest.mark.asyncio
    async def test_delete_group_removes_from_keys(self, service):
        """Test that deleting a group removes it from all keys."""
        key_result = await service.create_api_key()
        key_id = key_result["key_id"]

        group_result = await service.create_group(name="test-group")
        group_id = group_result["id"]

        await service.bind_api_key_to_group(key_id, group_id)

        # Verify key has group
        lookup_result = await service.lookup_api_key(key_id)
        assert group_id in lookup_result["groups"]

        # Delete group
        await service.delete_group(group_id)

        # Verify group removed from key
        lookup_result = await service.lookup_api_key(key_id)
        assert group_id not in lookup_result["groups"]
