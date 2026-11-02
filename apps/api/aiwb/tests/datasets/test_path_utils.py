# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Tests for the dataset path utilities, without requiring Docker.
"""

import pytest

from api_common.slugs import slugify
from app.datasets.utils import clean_s3_path, derive_name_from_path, get_object_key


def test_basic_slugification():
    """Test basic slugification of a string with spaces."""
    assert slugify("Dataset Name") == "dataset-name"


def test_complex_string_with_symbols():
    """Test slugification of a string with symbols and spaces."""
    assert slugify("Complex! Name with symbols & spaces") == "complex-name-with-symbols-spaces"


def test_underscores_preserved():
    """Test that underscores are preserved during slugification."""
    assert slugify("name_with_underscores") == "name_with_underscores"


def test_hyphens_preserved():
    """Test that hyphens are preserved during slugification."""
    assert slugify("names-with-hyphens") == "names-with-hyphens"


def test_unicode_characters_preserved():
    """Test that Unicode characters are preserved during slugification."""
    assert slugify("Téśt Dàtáśét") == "téśt-dàtáśét"


def test_generate_object_key():
    """Test generating an S3 object key from a dataset ID and project name."""
    project_name = "Test Project"

    # Expected format is {slugified_project_name}/datasets/{dataset_id}.jsonl
    result = get_object_key("test-dataset-uuid", project_name)
    expected = "test-project/datasets/test-dataset-uuid.jsonl"
    assert result == expected


def test_generate_object_key_with_special_chars():
    """Test generating an S3 object key with special characters in the project name."""
    project_name = "Test Project With Spaces & Symbols!"

    # Expected format is {slugified_project_name}/datasets/{dataset_id}.jsonl
    # The dataset ID is used as-is; only the project/namespace is slugified
    result = get_object_key("abc123-uuid", project_name)
    expected = "test-project-with-spaces-symbols/datasets/abc123-uuid.jsonl"
    assert result == expected


def test_derive_name_from_nested_path():
    """Test deriving a name from a nested path."""
    assert derive_name_from_path("datasets/user/cluster/test-dataset.jsonl") == "Test Dataset"


def test_derive_name_from_simple_path():
    """Test deriving a name from a simple path."""
    assert derive_name_from_path("datasets/some-dataset-name.jsonl") == "Some Dataset Name"


def test_derive_name_with_underscores():
    """Test deriving a name from a path with underscores."""
    assert derive_name_from_path("path/to/dataset_with_underscores.jsonl") == "Dataset With Underscores"


def test_simple_path_without_bucket():
    """Test cleaning a simple path without a bucket prefix."""
    assert clean_s3_path("datasets/test.jsonl") == "datasets/test.jsonl"


def test_path_with_s3_protocol():
    """Test cleaning a path with the s3:// protocol."""
    assert clean_s3_path("s3://bucket/datasets/test.jsonl") == "bucket/datasets/test.jsonl"


def test_path_with_correct_bucket():
    """Test cleaning a path with the correct bucket prefix."""
    assert clean_s3_path("default-bucket/datasets/test.jsonl") == "datasets/test.jsonl"


def test_path_with_different_bucket():
    """Test cleaning a path with a different bucket prefix."""
    assert clean_s3_path("different-bucket/datasets/test.jsonl") == "different-bucket/datasets/test.jsonl"


def test_upload_flow():
    """Test the integration of functions for the dataset upload flow."""
    project_name = "My Test Project"

    # Step 1: Generate the object key from a dataset UUID and project name
    dataset_id = "my-dataset-uuid-1234"
    object_key = get_object_key(dataset_id, project_name)

    # The path follows the format: {slugified_project_name}/datasets/{dataset_id}.jsonl
    expected_key = "my-test-project/datasets/my-dataset-uuid-1234.jsonl"
    assert object_key == expected_key


def test_registration_flow():
    """Test the integration of functions for the dataset registration flow."""
    # Step 1: User provides a path, we clean it
    user_path = "s3://default-bucket/datasets/my-custom-dataset.jsonl"

    cleaned_path = clean_s3_path(user_path)
    assert cleaned_path == "datasets/my-custom-dataset.jsonl"

    # Step 2: Derive a name from the path
    derived_name = derive_name_from_path(cleaned_path)
    assert derived_name == "My Custom Dataset"


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
