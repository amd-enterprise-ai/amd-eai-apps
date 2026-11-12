# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for registration module."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

from workloads_manager.core.api import make_api_request
from workloads_manager.core.registration import (
    get_chart_id,
    get_overlay_id,
    process_single_overlay,
    prune_overlays_absent_from_workload,
    register_workload,
)
from workloads_manager.models import (
    ProcessingStatus,
    WorkloadRegistrationResult,
)


@patch("httpx.Client")
def test_make_api_request_preserves_template_paths(mock_client_class):
    """Test that make_api_request preserves directory structure for template files."""
    # Setup mock response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}

    mock_client = Mock()
    mock_client_class.return_value.__enter__.return_value = mock_client
    mock_client.request.return_value = mock_response

    # Create temporary files with helm directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create helm directory structure
        helm_dir = temp_path / "test-workload" / "helm"
        templates_dir = helm_dir / "templates"
        templates_dir.mkdir(parents=True)

        # Create template files
        deployment_file = templates_dir / "deployment.yaml"
        deployment_file.write_text("apiVersion: apps/v1\nkind: Deployment")

        helpers_file = templates_dir / "_helpers.tpl"
        helpers_file.write_text('{{- define "test" -}}')

        # Create root level files
        chart_file = helm_dir / "Chart.yaml"
        chart_file.write_text("apiVersion: v2\nname: test")

        values_file = helm_dir / "values.yaml"
        values_file.write_text("key: value")

        # Test file upload with directory structure
        files = {"files": [str(deployment_file), str(helpers_file), str(chart_file), str(values_file)]}

        # Make API request
        success, response = make_api_request(
            "POST", "charts", httpx.URL("http://test-api.com"), data={"name": "test-chart"}, files=files
        )

        # Verify the request was made
        assert success
        mock_client.request.assert_called_once()

        # Get the files argument from the request
        call_args = mock_client.request.call_args
        request_files = call_args[1]["files"]

        # Convert to dict for easier checking
        file_dict = {filename: content for field, (filename, content, content_type) in request_files}

        # Verify template files preserve directory structure
        assert "templates/deployment.yaml" in file_dict
        assert "templates/_helpers.tpl" in file_dict

        # Verify root files don't have extra path
        assert "Chart.yaml" in file_dict
        assert "values.yaml" in file_dict

        # Verify we don't have incorrect paths (the bug this test catches)
        assert "deployment.yaml" not in file_dict  # This would be the bug
        assert "_helpers.tpl" not in file_dict  # This would be the bug

        # Verify file contents are correct
        assert b"apiVersion: apps/v1" in file_dict["templates/deployment.yaml"]
        assert b'{{- define "test" -}}' in file_dict["templates/_helpers.tpl"]
        assert b"apiVersion: v2" in file_dict["Chart.yaml"]


@patch("httpx.Client")
def test_make_api_request_handles_non_helm_files(mock_client_class):
    """Test that make_api_request handles files outside helm directory correctly."""
    # Setup mock response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}

    mock_client = Mock()
    mock_client_class.return_value.__enter__.return_value = mock_client
    mock_client.request.return_value = mock_response

    # Create temporary files without helm directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create files not in helm directory
        readme_file = temp_path / "README.md"
        readme_file.write_text("# Test Project")

        config_file = temp_path / "config.json"
        config_file.write_text('{"test": true}')

        # Test file upload
        files = {"files": [str(readme_file), str(config_file)]}

        # Make API request
        success, response = make_api_request("POST", "test", httpx.URL("http://test-api.com"), files=files)

        # Verify the request was made
        assert success
        mock_client.request.assert_called_once()

        # Get the files argument from the request
        call_args = mock_client.request.call_args
        request_files = call_args[1]["files"]

        # Convert to dict for easier checking
        file_dict = {filename: content for field, (filename, content, content_type) in request_files}

        # For non-helm files, should just use filename
        assert "README.md" in file_dict
        assert "config.json" in file_dict

        # Verify file contents are correct
        assert b"# Test Project" in file_dict["README.md"]
        assert b'{"test": true}' in file_dict["config.json"]


@patch("workloads_manager.core.registration.make_api_request")
def test_get_chart_id_success(mock_api_request):
    """Test get_chart_id with successful response."""
    # Mock API response - API returns {"data": [...]} envelope
    mock_api_request.return_value = (True, {"data": [{"id": "chart-123", "name": "test-chart"}]})

    result = get_chart_id("test-chart", httpx.URL(httpx.URL("http://api.test")))

    assert result == "chart-123"
    mock_api_request.assert_called_once_with("GET", "charts", httpx.URL(httpx.URL("http://api.test")))


@patch("workloads_manager.core.registration.make_api_request")
def test_get_chart_id_not_found(mock_api_request):
    """Test get_chart_id when chart not found."""
    # Mock API response
    mock_api_request.return_value = (True, [])

    result = get_chart_id("nonexistent-chart", httpx.URL("http://api.test"))

    assert result is None


@patch("workloads_manager.core.registration.make_api_request")
def test_get_chart_id_api_error(mock_api_request):
    """Test get_chart_id with API error."""
    # Mock API error
    mock_api_request.return_value = (False, {"error": "API error"})

    result = get_chart_id("test-chart", httpx.URL("http://api.test"))

    assert result is None


@patch("workloads_manager.core.registration.make_api_request")
def test_get_overlay_id_matches_the_recipe_file(mock_api_request):
    """Recipes for the same model are told apart by the file they were registered from."""
    mock_api_request.return_value = (
        True,
        {
            "data": [
                {"id": "overlay-123", "canonicalName": "model/test", "sourcePath": "overrides/models/general.yaml"},
                {"id": "overlay-456", "canonicalName": "model/test", "sourcePath": "overrides/models/mi350p.yaml"},
            ]
        },
    )

    result = get_overlay_id("chart-123", "overrides/models/mi350p.yaml", "model/test", httpx.URL("http://api.test"))

    assert result == "overlay-456"
    mock_api_request.assert_called_once_with("GET", "overlays?chartId=chart-123", httpx.URL("http://api.test"))


@patch("workloads_manager.core.registration.make_api_request")
def test_get_overlay_id_adopts_an_overlay_registered_without_a_file(mock_api_request):
    """An overlay AIWB registered before source tracking is reused for its model rather than duplicated."""
    mock_api_request.return_value = (
        True,
        {
            "data": [
                {"id": "overlay-123", "canonicalName": "model/test", "sourcePath": None, "createdBy": "system"},
                {"id": "overlay-456", "canonicalName": "model/other", "sourcePath": None, "createdBy": "system"},
            ]
        },
    )

    result = get_overlay_id("chart-123", "overrides/models/test.yaml", "model/test", httpx.URL("http://api.test"))

    assert result == "overlay-123"


@patch("workloads_manager.core.registration.make_api_request")
def test_get_overlay_id_never_adopts_an_overlay_authored_through_the_api(mock_api_request):
    """A user's override for the same model stays theirs: the recipe gets a row of its own."""
    mock_api_request.return_value = (
        True,
        {
            "data": [
                {
                    "id": "overlay-123",
                    "canonicalName": "model/test",
                    "sourcePath": None,
                    "createdBy": "user@example.com",
                }
            ]
        },
    )

    result = get_overlay_id("chart-123", "overrides/models/test.yaml", "model/test", httpx.URL("http://api.test"))

    assert result is None


@patch("workloads_manager.core.registration.make_api_request")
def test_get_overlay_id_does_not_adopt_another_files_recipe(mock_api_request):
    """A recipe registered from a different file is not reused just because it declares the same model."""
    mock_api_request.return_value = (
        True,
        {"data": [{"id": "overlay-123", "canonicalName": "model/test", "sourcePath": "overrides/models/general.yaml"}]},
    )

    result = get_overlay_id("chart-123", "overrides/models/mi350p.yaml", "model/test", httpx.URL("http://api.test"))

    assert result is None


@patch("workloads_manager.core.registration.make_api_request")
def test_get_overlay_id_not_found(mock_api_request):
    """Test get_overlay_id when overlay not found."""
    # Mock API response
    mock_api_request.return_value = (True, [])

    result = get_overlay_id(
        "chart-123", "overrides/models/nonexistent.yaml", "model/nonexistent", httpx.URL("http://api.test")
    )

    assert result is None


@patch("workloads_manager.core.registration.make_api_request")
def test_get_overlay_id_api_error(mock_api_request):
    """Test get_overlay_id with API error."""
    # Mock API error
    mock_api_request.return_value = (False, {"error": "API error"})

    result = get_overlay_id("chart-123", "overrides/models/test.yaml", "model/test", httpx.URL("http://api.test"))

    assert result is None


@patch("workloads_manager.core.registration.make_api_request")
def test_prune_removes_only_file_backed_overlays_the_workload_no_longer_ships(mock_api_request):
    """A renamed recipe's old row goes; API-authored overlays and AIWB's own registrations stay."""
    overlays = [
        {"id": "kept", "sourcePath": "overrides/models/current.yaml", "createdBy": "user@example.com"},
        {"id": "renamed", "sourcePath": "overrides/models/old-name.yaml", "createdBy": "user@example.com"},
        {"id": "service-owned", "sourcePath": "overrides/models/bundled.yaml", "createdBy": "system"},
        {"id": "api-authored", "sourcePath": None, "createdBy": "user@example.com"},
    ]
    mock_api_request.side_effect = lambda method, *_args, **_kwargs: (
        (True, {"data": overlays}) if method == "GET" else (True, {})
    )

    pruned = prune_overlays_absent_from_workload("chart-123", {"kept"}, httpx.URL("http://api.test"))

    assert pruned == ["renamed"]
    deletes = [call.args[1] for call in mock_api_request.call_args_list if call.args[0] == "DELETE"]
    assert deletes == ["overlays/renamed"]


def make_registerable_workload(overlay_count: int) -> Mock:
    """A registerable workload shipping `overlay_count` recipe files and no other files."""
    workload = Mock()
    workload.dir_name = "test-workload"
    workload.chart_name = "test-chart"
    workload.is_registerable = True
    workload.get_overlay_files.return_value = [
        (Path(f"recipe-{index}.yaml"), f"overrides/models/recipe-{index}.yaml") for index in range(overlay_count)
    ]
    workload._iter_files.return_value = []
    return workload


@patch("workloads_manager.core.registration.prune_overlays_absent_from_workload")
@patch("workloads_manager.core.registration.process_single_overlay")
@patch("workloads_manager.core.registration.upload_chart", return_value="chart-123")
@patch("workloads_manager.core.registration.check_api_server", return_value=True)
@patch("workloads_manager.core.registration.get_workloads")
@patch("workloads_manager.config.TOKEN", "test-token")
def test_register_workload_prunes_against_the_recipes_it_registered(
    mock_get_workloads, _mock_check_api, _mock_upload_chart, mock_process_overlay, mock_prune
):
    """Once every recipe is registered, overlays for files the workload no longer ships are removed."""
    mock_get_workloads.return_value = [make_registerable_workload(2)]
    mock_process_overlay.side_effect = [
        (ProcessingStatus.SUCCESS, "overlay-0"),
        (ProcessingStatus.SUCCESS, "overlay-1"),
    ]

    register_workload("test-workload", httpx.URL("http://api.test"))

    mock_prune.assert_called_once_with("chart-123", {"overlay-0", "overlay-1"}, httpx.URL("http://api.test"))


@patch("workloads_manager.core.registration.prune_overlays_absent_from_workload")
@patch("workloads_manager.core.registration.process_single_overlay")
@patch("workloads_manager.core.registration.upload_chart", return_value="chart-123")
@patch("workloads_manager.core.registration.check_api_server", return_value=True)
@patch("workloads_manager.core.registration.get_workloads")
@patch("workloads_manager.config.TOKEN", "test-token")
def test_register_workload_keeps_overlays_when_a_recipe_fails_to_register(
    mock_get_workloads, _mock_check_api, _mock_upload_chart, mock_process_overlay, mock_prune
):
    """A failed upload leaves the run's recipes incomplete, so nothing is removed against them."""
    mock_get_workloads.return_value = [make_registerable_workload(2)]
    mock_process_overlay.side_effect = [(ProcessingStatus.SUCCESS, "overlay-0"), (ProcessingStatus.FAILED, "")]

    register_workload("test-workload", httpx.URL("http://api.test"))

    mock_prune.assert_not_called()


@patch("workloads_manager.core.registration.temp_file_with_content")
@patch("workloads_manager.core.registration.make_api_request")
@patch("workloads_manager.core.registration.get_overlay_id")
def test_process_single_overlay_model_file_success(
    mock_get_overlay_id, mock_api_request, mock_temp_file, temp_yaml_file
):
    """Test process_single_overlay with model file - successful upload."""
    # Setup mocks
    mock_temp_file.return_value.__enter__ = Mock(return_value="/tmp/test.yaml")
    mock_temp_file.return_value.__exit__ = Mock(return_value=None)
    mock_get_overlay_id.return_value = None  # No existing overlay
    mock_api_request.return_value = (True, {"id": "overlay-123"})

    # Create test file using fixture
    test_file = temp_yaml_file({"model": "gpt-4", "config": "test"})

    status, file_id = process_single_overlay(
        test_file, "overrides/models/gpt-4.yaml", httpx.URL("http://api.test"), "chart-123"
    )

    assert status == ProcessingStatus.SUCCESS
    assert file_id == "overlay-123"

    # Verify API was called for overlay creation
    mock_api_request.assert_called_once()
    call_args = mock_api_request.call_args
    assert call_args[0][0] == "POST"  # POST for new overlay
    assert "chartId" in call_args[1]["data"]
    assert "canonicalName" in call_args[1]["data"]
    assert call_args[1]["data"]["sourcePath"] == "overrides/models/gpt-4.yaml"
    mock_get_overlay_id.assert_called_once_with(
        "chart-123", "overrides/models/gpt-4.yaml", "gpt-4", httpx.URL("http://api.test")
    )


@patch("workloads_manager.core.registration.temp_file_with_content")
@patch("workloads_manager.core.registration.make_api_request")
@patch("workloads_manager.core.registration.get_overlay_id")
def test_process_single_overlay_non_model_file(mock_get_overlay_id, mock_api_request, mock_temp_file, temp_yaml_file):
    """Test process_single_overlay with non-model file."""
    # Setup mocks
    mock_temp_file.return_value.__enter__ = Mock(return_value="/tmp/test.yaml")
    mock_temp_file.return_value.__exit__ = Mock(return_value=None)
    mock_get_overlay_id.return_value = None
    mock_api_request.return_value = (True, {"id": "overlay-123"})

    # Create test file without model field using fixture
    test_file = temp_yaml_file({"config": "test", "other": "value"})

    status, file_id = process_single_overlay(
        test_file, "overrides/models/config.yaml", httpx.URL("http://api.test"), "chart-123"
    )

    assert status == ProcessingStatus.SUCCESS
    assert file_id == "overlay-123"

    # Verify API call was made with canonical name from filename
    mock_api_request.assert_called_once()
    call_args = mock_api_request.call_args
    # The canonical name should be the filename stem with underscores converted to slashes
    expected_canonical_name = test_file.stem.replace("_", "/").replace(":", "/")
    assert call_args[1]["data"]["canonicalName"] == expected_canonical_name


@patch("workloads_manager.core.registration.temp_file_with_content")
@patch("workloads_manager.core.registration.make_api_request")
@patch("workloads_manager.core.registration.get_overlay_id")
def test_process_single_overlay_api_error(mock_get_overlay_id, mock_api_request, mock_temp_file, temp_yaml_file):
    """Test process_single_overlay with API error."""
    # Setup mocks
    mock_temp_file.return_value.__enter__ = Mock(return_value="/tmp/test.yaml")
    mock_temp_file.return_value.__exit__ = Mock(return_value=None)
    mock_get_overlay_id.return_value = None
    mock_api_request.return_value = (False, {"error": "Upload failed"})

    # Create test file using fixture
    test_file = temp_yaml_file({"test": "content"})

    status, file_id = process_single_overlay(
        test_file, "overrides/models/test.yaml", httpx.URL("http://api.test"), "chart-123"
    )

    assert status == ProcessingStatus.FAILED
    assert file_id == ""


def test_process_single_overlay_file_read_error():
    """Test process_single_overlay with file read error."""
    # Use non-existent file to trigger exception
    non_existent_file = Path("/non/existent/file.yaml")

    status, file_id = process_single_overlay(
        non_existent_file, "overrides/models/test.yaml", httpx.URL("http://api.test"), "chart-123"
    )

    assert status == ProcessingStatus.FAILED
    assert file_id == "Error processing file"


@patch("workloads_manager.core.registration.get_workloads")
@patch("workloads_manager.core.registration.check_api_server")
@patch("workloads_manager.config.TOKEN", "test-token")
def test_register_workload_workload_not_found(mock_check_api, mock_get_workloads):
    """Test register_workload when workload not found."""
    # Setup mocks
    mock_get_workloads.return_value = []
    mock_check_api.return_value = True

    result = register_workload("nonexistent-workload", httpx.URL("http://api.test"))

    assert isinstance(result, WorkloadRegistrationResult)
    assert not result.success
    assert "not found" in result.error


@patch("workloads_manager.core.registration.get_workloads")
@patch("workloads_manager.core.registration.check_api_server")
@patch("workloads_manager.config.TOKEN", "test-token")
def test_register_workload_not_registerable(mock_check_api, mock_get_workloads):
    """Test register_workload when workload is not registerable."""
    # Setup mocks
    mock_workload = Mock()
    mock_workload.dir_name = "test-workload"
    mock_workload.is_registerable = False
    mock_get_workloads.return_value = [mock_workload]
    mock_check_api.return_value = True

    result = register_workload("test-workload", httpx.URL("http://api.test"))

    assert isinstance(result, WorkloadRegistrationResult)
    assert not result.success
    assert "not registerable" in result.error


@patch("workloads_manager.core.registration.get_workloads")
@patch("workloads_manager.core.registration.check_api_server")
@patch("workloads_manager.config.TOKEN", None)
def test_register_workload_no_token(mock_check_api, mock_get_workloads):
    """Test register_workload when TOKEN is not set."""
    # Setup mocks
    mock_workload = Mock()
    mock_workload.dir_name = "test-workload"
    mock_workload.is_registerable = True
    mock_get_workloads.return_value = [mock_workload]
    mock_check_api.return_value = True

    result = register_workload("test-workload", httpx.URL("http://api.test"))

    assert isinstance(result, WorkloadRegistrationResult)
    assert not result.success
    assert "TOKEN environment variable not set" in result.error


@patch("workloads_manager.core.registration.get_workloads")
@patch("workloads_manager.core.registration.check_api_server")
@patch("workloads_manager.config.TOKEN", "test-token")
def test_register_workload_api_server_not_accessible(mock_check_api, mock_get_workloads):
    """Test register_workload when API server is not accessible."""
    # Setup mocks
    mock_workload = Mock()
    mock_workload.dir_name = "test-workload"
    mock_workload.is_registerable = True
    mock_get_workloads.return_value = [mock_workload]
    mock_check_api.return_value = False

    result = register_workload("test-workload", httpx.URL("http://api.test"))

    assert isinstance(result, WorkloadRegistrationResult)
    assert not result.success
    assert "API server at http://api.test is not accessible" in result.error
