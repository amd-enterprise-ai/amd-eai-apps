# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import pytest
from pydantic import ValidationError

from app.models import (
    BindApiKeyRequest,
    CreateApiKeyRequest,
    CreateGroupRequest,
    LookupApiKeyRequest,
    RenewApiKeyRequest,
    RevokeApiKeyRequest,
    UnbindApiKeyRequest,
)


class TestCreateApiKeyRequest:
    """Test CreateApiKeyRequest model."""

    def test_default_values(self):
        """Test default values."""
        request = CreateApiKeyRequest()
        assert request.ttl == "0"
        assert request.num_uses == 0
        assert request.meta is None
        assert request.period == ""
        assert request.renewable is True
        assert request.explicit_max_ttl == ""

    def test_custom_values(self):
        """Test custom values."""
        request = CreateApiKeyRequest(
            ttl="2h",
            num_uses=5,
            meta={"key": "value"},
            renewable=False,
        )
        assert request.ttl == "2h"
        assert request.num_uses == 5
        assert request.meta == {"key": "value"}
        assert request.renewable is False


class TestRevokeApiKeyRequest:
    """Test RevokeApiKeyRequest model."""

    def test_required_key_id(self):
        """Test that key_id is required."""
        with pytest.raises(ValidationError):
            RevokeApiKeyRequest()

    def test_valid_request(self):
        """Test valid request."""
        request = RevokeApiKeyRequest(key_id="test-key-id")
        assert request.key_id == "test-key-id"


class TestRenewApiKeyRequest:
    """Test RenewApiKeyRequest model."""

    def test_required_key_id(self):
        """Test that key_id is required."""
        with pytest.raises(ValidationError):
            RenewApiKeyRequest()

    def test_with_increment(self):
        """Test request with increment."""
        request = RenewApiKeyRequest(key_id="test-key-id", increment="1h")
        assert request.key_id == "test-key-id"
        assert request.increment == "1h"

    def test_without_increment(self):
        """Test request without increment."""
        request = RenewApiKeyRequest(key_id="test-key-id")
        assert request.key_id == "test-key-id"
        assert request.increment is None


class TestLookupApiKeyRequest:
    """Test LookupApiKeyRequest model."""

    def test_required_key_id(self):
        """Test that key_id is required."""
        with pytest.raises(ValidationError):
            LookupApiKeyRequest()

    def test_valid_request(self):
        """Test valid request."""
        request = LookupApiKeyRequest(key_id="test-key-id")
        assert request.key_id == "test-key-id"


class TestCreateGroupRequest:
    """Test CreateGroupRequest model."""

    def test_default_values(self):
        """Test default values."""
        request = CreateGroupRequest()
        assert request.name is None
        assert request.id is None

    def test_with_name(self):
        """Test with name."""
        request = CreateGroupRequest(name="test-group")
        assert request.name == "test-group"

    def test_with_id(self):
        """Test with ID."""
        request = CreateGroupRequest(id="test-group-id")
        assert request.id == "test-group-id"


class TestBindApiKeyRequest:
    """Test BindApiKeyRequest model."""

    def test_required_fields(self):
        """Test that both fields are required."""
        with pytest.raises(ValidationError):
            BindApiKeyRequest()

    def test_valid_request(self):
        """Test valid request."""
        request = BindApiKeyRequest(key_id="test-key-id", group_id="test-group-id")
        assert request.key_id == "test-key-id"
        assert request.group_id == "test-group-id"


class TestUnbindApiKeyRequest:
    """Test UnbindApiKeyRequest model."""

    def test_required_fields(self):
        """Test that both fields are required."""
        with pytest.raises(ValidationError):
            UnbindApiKeyRequest()

    def test_valid_request(self):
        """Test valid request."""
        request = UnbindApiKeyRequest(key_id="test-key-id", group_id="test-group-id")
        assert request.key_id == "test-key-id"
        assert request.group_id == "test-group-id"
