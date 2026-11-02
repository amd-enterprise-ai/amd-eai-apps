# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for dispatch utility functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kubernetes_asyncio.client import ApiException, V1CustomResourceDefinition, V1CustomResourceDefinitionSpec

from app.dispatch.utils import get_resource_version, sanitize_label_value

# =============================================================================
# sanitize_label_value tests
# =============================================================================


def test_sanitize_label_value_empty_string():
    """Test sanitizing empty string returns empty string."""
    assert sanitize_label_value("") == ""


def test_sanitize_label_value_valid_label():
    """Test valid label is unchanged."""
    assert sanitize_label_value("valid-label") == "valid-label"
    assert sanitize_label_value("valid_label") == "valid_label"
    assert sanitize_label_value("valid.label") == "valid.label"
    assert sanitize_label_value("abc123") == "abc123"


def test_sanitize_label_value_with_spaces():
    """Test spaces are converted to hyphens."""
    assert sanitize_label_value("hello world") == "hello-world"
    assert sanitize_label_value("a b c") == "a-b-c"


def test_sanitize_label_value_with_slashes():
    """Test slashes are converted to hyphens."""
    assert sanitize_label_value("meta-llama/Llama-3.1-8B") == "meta-llama-Llama-3.1-8B"
    assert sanitize_label_value("docker.io/image") == "docker.io-image"


def test_sanitize_label_value_with_special_characters():
    """Test special characters are removed."""
    assert sanitize_label_value("test@example!com") == "testexamplecom"
    assert sanitize_label_value("hello#world$test") == "helloworldtest"


def test_sanitize_label_value_leading_trailing_non_alphanumeric():
    """Test leading/trailing non-alphanumeric characters are removed."""
    assert sanitize_label_value("-test-") == "test"
    assert sanitize_label_value("_test_") == "test"
    assert sanitize_label_value(".test.") == "test"
    assert sanitize_label_value("---test---") == "test"


def test_sanitize_label_value_max_length():
    """Test truncation to max length (default 63)."""
    long_string = "a" * 100
    result = sanitize_label_value(long_string)
    assert len(result) == 63
    assert result == "a" * 63


def test_sanitize_label_value_custom_max_length():
    """Test truncation with custom max length."""
    long_string = "abcdefghij"
    result = sanitize_label_value(long_string, max_length=5)
    assert len(result) == 5
    assert result == "abcde"


def test_sanitize_label_value_all_invalid_returns_unknown():
    """Test all invalid characters returns 'unknown'."""
    assert sanitize_label_value("!!!") == "unknown"
    assert sanitize_label_value("@@@") == "unknown"
    assert sanitize_label_value("---") == "unknown"


def test_sanitize_label_value_real_world_examples():
    """Test real-world model names and identifiers."""
    # Model canonical names
    assert sanitize_label_value("meta-llama/Llama-3.1-8B") == "meta-llama-Llama-3.1-8B"
    assert sanitize_label_value("microsoft/phi-2") == "microsoft-phi-2"

    # Email addresses
    assert sanitize_label_value("user@example.com") == "userexample.com"

    # URLs (multiple slashes become hyphens)
    assert sanitize_label_value("https://example.com") == "https--example.com"

    # Workload display names
    assert sanitize_label_value("My Fine-tuning Job") == "My-Fine-tuning-Job"


def test_sanitize_label_value_mixed_case():
    """Test mixed case is preserved."""
    assert sanitize_label_value("TestLabel") == "TestLabel"
    assert sanitize_label_value("CamelCase123") == "CamelCase123"


def test_sanitize_label_value_unicode_characters():
    """Test unicode characters are removed."""
    assert sanitize_label_value("test✓label") == "testlabel"
    assert sanitize_label_value("hello😀world") == "helloworld"


def test_sanitize_label_value_starts_ends_alphanumeric():
    """Test result always starts and ends with alphanumeric."""
    result = sanitize_label_value("_-test-model-_")
    assert result[0].isalnum()
    assert result[-1].isalnum()


def test_sanitize_label_value_preserves_internal_separators():
    """Test internal hyphens, underscores, and dots are preserved."""
    assert sanitize_label_value("my-test_label.v1") == "my-test_label.v1"
    assert sanitize_label_value("a-b_c.d") == "a-b_c.d"


# =============================================================================
# get_resource_version tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_resource_version_core_api_returns_v1():
    """Test core API resources (empty group) return 'v1' without querying."""
    result = await get_resource_version(group="", plural="services")
    assert result == "v1"


@pytest.mark.asyncio
async def test_get_resource_version_core_api_any_plural_returns_v1():
    """Test any core API resource returns 'v1'."""
    result = await get_resource_version(group="", plural="configmaps")
    assert result == "v1"

    result = await get_resource_version(group="", plural="pods")
    assert result == "v1"


@pytest.mark.asyncio
@patch("app.dispatch.utils.get_kube_client")
async def test_get_resource_version_crd_returns_storage_version(mock_get_client):
    """Test CRD returns the storage version."""
    mock_client = MagicMock(spec=["api_extensions"])
    mock_get_client.return_value = mock_client

    version1 = MagicMock(storage=False, served=True)
    version1.name = "v1alpha2"
    version2 = MagicMock(storage=True, served=True)
    version2.name = "v1"

    mock_crd = MagicMock(spec=V1CustomResourceDefinition)
    mock_crd.spec = MagicMock(spec=V1CustomResourceDefinitionSpec)
    mock_crd.spec.versions = [version1, version2]
    mock_client.api_extensions.read_custom_resource_definition = AsyncMock(return_value=mock_crd)

    result = await get_resource_version(group="example.com", plural="testresources")

    assert result == "v1"
    mock_client.api_extensions.read_custom_resource_definition.assert_called_once_with("testresources.example.com")


@pytest.mark.asyncio
@patch("app.dispatch.utils.get_kube_client")
async def test_get_resource_version_crd_falls_back_to_served_version(mock_get_client):
    """Test CRD falls back to first served version if no storage version."""
    mock_client = MagicMock(spec=["api_extensions"])
    mock_get_client.return_value = mock_client

    version1 = MagicMock(storage=False, served=True)
    version1.name = "v1beta1"
    version2 = MagicMock(storage=False, served=False)
    version2.name = "v1alpha2"

    mock_crd = MagicMock(spec=V1CustomResourceDefinition)
    mock_crd.spec = MagicMock(spec=V1CustomResourceDefinitionSpec)
    mock_crd.spec.versions = [version1, version2]
    mock_client.api_extensions.read_custom_resource_definition = AsyncMock(return_value=mock_crd)

    result = await get_resource_version(group="example.com", plural="testresources")

    assert result == "v1beta1"


@pytest.mark.asyncio
@patch("app.dispatch.utils.get_kube_client")
async def test_get_resource_version_crd_not_found_returns_none(mock_get_client):
    """Test CRD not found returns None."""
    mock_client = MagicMock(spec=["api_extensions"])
    mock_get_client.return_value = mock_client
    mock_client.api_extensions.read_custom_resource_definition = AsyncMock(
        side_effect=ApiException(status=404, reason="Not Found")
    )

    result = await get_resource_version(group="example.com", plural="missingresources")

    assert result is None


@pytest.mark.asyncio
@patch("app.dispatch.utils.get_kube_client")
async def test_get_resource_version_crd_api_error_returns_none(mock_get_client):
    """Test CRD API error returns None."""
    mock_client = MagicMock(spec=["api_extensions"])
    mock_get_client.return_value = mock_client
    mock_client.api_extensions.read_custom_resource_definition = AsyncMock(
        side_effect=ApiException(status=500, reason="Internal Server Error")
    )

    result = await get_resource_version(group="example.com", plural="testresources")

    assert result is None


@pytest.mark.asyncio
@patch("app.dispatch.utils.get_kube_client")
async def test_get_resource_version_crd_no_versions_returns_none(mock_get_client):
    """Test CRD with no served versions returns None."""
    mock_client = MagicMock(spec=["api_extensions"])
    mock_get_client.return_value = mock_client

    version = MagicMock(storage=False, served=False)
    version.name = "v1"

    mock_crd = MagicMock(spec=V1CustomResourceDefinition)
    mock_crd.spec = MagicMock(spec=V1CustomResourceDefinitionSpec)
    mock_crd.spec.versions = [version]
    mock_client.api_extensions.read_custom_resource_definition = AsyncMock(return_value=mock_crd)

    result = await get_resource_version(group="example.com", plural="testresources")

    assert result is None


@pytest.mark.asyncio
@patch("app.dispatch.utils.get_kube_client")
async def test_get_resource_version_crd_empty_versions_list(mock_get_client):
    """Test CRD with empty versions list returns None."""
    mock_client = MagicMock(spec=["api_extensions"])
    mock_get_client.return_value = mock_client

    mock_crd = MagicMock(spec=V1CustomResourceDefinition)
    mock_crd.spec = MagicMock(spec=V1CustomResourceDefinitionSpec)
    mock_crd.spec.versions = []
    mock_client.api_extensions.read_custom_resource_definition = AsyncMock(return_value=mock_crd)

    result = await get_resource_version(group="example.com", plural="testresources")

    assert result is None


@pytest.mark.asyncio
@patch("app.dispatch.utils.get_kube_client")
async def test_get_resource_version_multiple_storage_versions(mock_get_client):
    """Test CRD with multiple storage versions returns first storage version."""
    mock_client = MagicMock(spec=["api_extensions"])
    mock_get_client.return_value = mock_client

    version1 = MagicMock(storage=True, served=True)
    version1.name = "v1"
    version2 = MagicMock(storage=True, served=True)
    version2.name = "v2"

    mock_crd = MagicMock(spec=V1CustomResourceDefinition)
    mock_crd.spec = MagicMock(spec=V1CustomResourceDefinitionSpec)
    mock_crd.spec.versions = [version1, version2]
    mock_client.api_extensions.read_custom_resource_definition = AsyncMock(return_value=mock_crd)

    result = await get_resource_version(group="example.com", plural="testresources")

    # Should return first storage version
    assert result == "v1"


@pytest.mark.asyncio
@patch("app.dispatch.utils.get_kube_client")
async def test_get_resource_version_generic_exception(mock_get_client):
    """Test get_resource_version propagates generic exceptions (not ApiException)."""
    mock_client = MagicMock(spec=["api_extensions"])
    mock_get_client.return_value = mock_client
    mock_client.api_extensions.read_custom_resource_definition = AsyncMock(side_effect=Exception("Unexpected error"))

    # Generic exceptions are propagated, not caught
    with pytest.raises(Exception, match="Unexpected error"):
        await get_resource_version(group="example.com", plural="testresources")


def test_sanitize_label_value_consecutive_separators():
    """Test consecutive separators are preserved."""
    assert sanitize_label_value("test--value") == "test--value"
    assert sanitize_label_value("test__value") == "test__value"
    assert sanitize_label_value("test..value") == "test..value"


def test_sanitize_label_value_mixed_separators():
    """Test mixed separators are preserved correctly."""
    assert sanitize_label_value("test-_value") == "test-_value"
    assert sanitize_label_value("test._value") == "test._value"


def test_sanitize_label_value_only_separators_returns_unknown():
    """Test label with only separators returns 'unknown'."""
    assert sanitize_label_value("---___...") == "unknown"
    assert sanitize_label_value("-_.-_.-_.") == "unknown"


def test_sanitize_label_value_ends_with_separator_after_truncation():
    """Test label ending with separator after truncation is handled."""
    # Create a string that ends with a separator when truncated
    value = "a" * 62 + "-b"
    result = sanitize_label_value(value, max_length=63)
    assert len(result) == 62
    assert result == "a" * 62
    assert result[-1].isalnum()


def test_sanitize_label_value_s3_uri_truncation_keeps_valid_ending():
    """Long S3-style source labels remain valid after truncation."""
    value = "s3://default-bucket/qa-test/custom-models/llama-3-2-1b-instruct-clyde-import-bcfa0293/weights/"
    result = sanitize_label_value(value, max_length=63)
    assert len(result) <= 63
    assert result[0].isalnum()
    assert result[-1].isalnum()


def test_sanitize_label_value_numeric_start_and_end():
    """Test labels starting and ending with numbers."""
    assert sanitize_label_value("1test2") == "1test2"
    assert sanitize_label_value("123") == "123"


def test_sanitize_label_value_single_character():
    """Test single character labels."""
    assert sanitize_label_value("a") == "a"
    assert sanitize_label_value("1") == "1"
    assert sanitize_label_value("-") == "unknown"


def test_sanitize_label_value_double_slash_conversion():
    """Test consecutive slashes convert to hyphens."""
    assert sanitize_label_value("https://example.com") == "https--example.com"
    assert sanitize_label_value("path/to/file") == "path-to-file"


def test_sanitize_label_value_complex_mixed_characters():
    """Test complex strings with mixed valid and invalid characters."""
    assert sanitize_label_value("test@#$%label!") == "testlabel"
    # Leading/trailing separators are stripped, special chars removed
    assert sanitize_label_value("_-@test#label$-_") == "testlabel"


def test_sanitize_label_value_exact_max_length():
    """Test string exactly at max length is unchanged if valid."""
    value = "a" * 63
    result = sanitize_label_value(value)
    assert result == value
    assert len(result) == 63


def test_sanitize_label_value_strip_leading_separator_before_alphanumeric():
    """Test leading separators before alphanumeric are removed."""
    assert sanitize_label_value("-_-test") == "test"
    assert sanitize_label_value("...test") == "test"
