# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from api_common.exceptions import ValidationException
from app.charts.models import Chart, ChartFile
from app.charts.utils import chart_directory, render_helm_template
from app.workloads.enums import WorkloadType

# =============================================================================
# chart_directory() context manager tests
# =============================================================================


def test_chart_directory_creates_temp_dir() -> None:
    """Test that chart_directory creates a temporary directory with chart files."""
    # Create a chart with multiple files including nested paths
    chart = Chart(
        name="test-chart",
        type=WorkloadType.INFERENCE,
        signature={"model": "test"},
        files=[
            ChartFile(path="Chart.yaml", content="apiVersion: v2\nname: test-chart"),
            ChartFile(path="values.yaml", content="replicas: 1\nimage: test"),
            ChartFile(path="templates/deployment.yaml", content="apiVersion: apps/v1\nkind: Deployment"),
            ChartFile(path="templates/service.yaml", content="apiVersion: v1\nkind: Service"),
        ],
    )

    # Use the context manager
    with chart_directory(chart) as chart_path:
        # Verify the path exists and is a directory
        assert chart_path.exists()
        assert chart_path.is_dir()

        # Verify all files were created with correct content
        chart_yaml = chart_path / "Chart.yaml"
        assert chart_yaml.exists()
        assert chart_yaml.read_text() == "apiVersion: v2\nname: test-chart"

        values_yaml = chart_path / "values.yaml"
        assert values_yaml.exists()
        assert values_yaml.read_text() == "replicas: 1\nimage: test"

        # Verify nested directory was created
        templates_dir = chart_path / "templates"
        assert templates_dir.exists()
        assert templates_dir.is_dir()

        deployment_yaml = templates_dir / "deployment.yaml"
        assert deployment_yaml.exists()
        assert deployment_yaml.read_text() == "apiVersion: apps/v1\nkind: Deployment"

        service_yaml = templates_dir / "service.yaml"
        assert service_yaml.exists()
        assert service_yaml.read_text() == "apiVersion: v1\nkind: Service"


def test_chart_directory_cleanup() -> None:
    """Test that chart_directory cleans up temporary directory after use."""
    chart = Chart(
        name="cleanup-test-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[
            ChartFile(path="Chart.yaml", content="apiVersion: v2"),
        ],
    )

    temp_path = None
    with chart_directory(chart) as chart_path:
        temp_path = chart_path
        # Verify directory exists during context
        assert temp_path.exists()

    # Verify directory was cleaned up after context exits
    assert not temp_path.exists()


def test_chart_directory_cleanup_on_exception() -> None:
    """Test that chart_directory cleans up even when an exception occurs."""
    chart = Chart(
        name="exception-test-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[
            ChartFile(path="Chart.yaml", content="apiVersion: v2"),
        ],
    )

    temp_path = None
    with pytest.raises(RuntimeError, match="Intentional error"):
        with chart_directory(chart) as chart_path:
            temp_path = chart_path
            # Verify directory exists during context
            assert temp_path.exists()
            # Raise an exception to test cleanup
            raise RuntimeError("Intentional error")

    # Verify directory was still cleaned up despite the exception
    assert not temp_path.exists()


def test_chart_directory_with_deeply_nested_paths() -> None:
    """Test chart_directory with deeply nested file paths."""
    chart = Chart(
        name="nested-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[
            ChartFile(path="a/b/c/deep.yaml", content="deep: nested"),
            ChartFile(path="x/y/z/deeper.yaml", content="even: deeper"),
        ],
    )

    with chart_directory(chart) as chart_path:
        # Verify deeply nested directories were created
        deep_file = chart_path / "a" / "b" / "c" / "deep.yaml"
        assert deep_file.exists()
        assert deep_file.read_text() == "deep: nested"

        deeper_file = chart_path / "x" / "y" / "z" / "deeper.yaml"
        assert deeper_file.exists()
        assert deeper_file.read_text() == "even: deeper"


def test_chart_directory_with_no_files() -> None:
    """Test chart_directory with a chart that has no files."""
    chart = Chart(
        name="empty-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[],
    )

    with chart_directory(chart) as chart_path:
        # Directory should still be created
        assert chart_path.exists()
        assert chart_path.is_dir()

        # But it should be empty
        assert list(chart_path.iterdir()) == []


def _assert_chart_directory_rejects(malicious_path: str, tmp_path: Path, temp_base: Path) -> None:
    chart = Chart(
        name="malicious-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[
            ChartFile(path="Chart.yaml", content="apiVersion: v2"),
            ChartFile(path=malicious_path, content="pwned"),
        ],
    )

    with pytest.raises(ValidationException, match="outside the chart directory"), chart_directory(chart):
        pytest.fail("chart_directory should not yield for an escaping path")

    assert not (tmp_path / "escaped.yaml").exists()
    assert not (temp_base / "escaped.yaml").exists()
    assert not (temp_base / "outside").exists()
    # The temp directory itself is still cleaned up on rejection.
    assert list(temp_base.iterdir()) == []


@pytest.fixture
def temp_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Root tempfile under tmp_path so writes escaping the chart temp dir are observable."""
    base = tmp_path / "base"
    base.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(base))
    return base


@pytest.mark.parametrize(
    "malicious_path",
    ["../escaped.yaml", "templates/../../escaped.yaml", "../outside/escaped.yaml", "."],
)
def test_chart_directory_rejects_relative_paths_escaping_temp_dir(
    malicious_path: str, tmp_path: Path, temp_base: Path
) -> None:
    """Stored relative paths that resolve outside the temp directory must never be written."""
    _assert_chart_directory_rejects(malicious_path, tmp_path, temp_base)


def test_chart_directory_rejects_absolute_path(tmp_path: Path, temp_base: Path) -> None:
    """Absolute stored paths would discard the temp dir prefix on join and must be rejected."""
    _assert_chart_directory_rejects(str(tmp_path / "escaped.yaml"), tmp_path, temp_base)


def test_chart_directory_allows_dot_segments_that_stay_inside() -> None:
    """Paths that normalize to a location inside the chart are still materialized."""
    chart = Chart(
        name="dot-segment-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[ChartFile(path="templates/../values.yaml", content="replicas: 1")],
    )

    with chart_directory(chart) as chart_path:
        assert (chart_path / "values.yaml").read_text() == "replicas: 1"


# =============================================================================
# render_helm_template() function tests
# =============================================================================


@pytest.mark.asyncio
async def test_render_helm_template_success() -> None:
    """Test successful Helm template rendering without overlays."""
    chart = Chart(
        name="render-test-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[
            ChartFile(path="Chart.yaml", content="apiVersion: v2\nname: test"),
            ChartFile(path="values.yaml", content="replicas: 1"),
        ],
    )

    # Mock the subprocess to simulate successful helm template execution
    mock_process = AsyncMock(spec=asyncio.subprocess.Process)
    mock_process.returncode = 0
    mock_process.communicate.return_value = (
        b"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: test-workload",
        b"",
    )

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        result = await render_helm_template(
            chart=chart,
            name="test-workload",
            namespace="test-namespace",
        )

        # Verify subprocess was called with correct arguments
        mock_exec.assert_awaited_once()
        call_args = mock_exec.await_args[0]  # type: ignore[index]
        assert call_args[0] == "helm"
        assert call_args[1] == "template"
        assert "--namespace" in call_args
        assert "test-namespace" in call_args
        assert "--name-template" in call_args
        assert "test-workload" in call_args
        assert "--set" in call_args
        # Verify fullnameOverride is set
        fullname_override_found = any("fullnameOverride=test-workload" in str(arg) for arg in call_args)
        assert fullname_override_found

        # Verify the rendered output
        assert result == "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: test-workload"


@pytest.mark.asyncio
async def test_render_helm_template_with_overlays() -> None:
    """Test Helm template rendering with overlay values."""
    chart = Chart(
        name="overlay-test-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[
            ChartFile(path="Chart.yaml", content="apiVersion: v2\nname: test"),
            ChartFile(path="values.yaml", content="replicas: 1"),
        ],
    )

    overlay_values = [
        {"replicas": 3, "image": "nginx:latest"},
        {"resources": {"limits": {"memory": "1Gi"}}},
    ]

    mock_process = AsyncMock(spec=asyncio.subprocess.Process)
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"rendered: manifest", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        result = await render_helm_template(
            chart=chart,
            name="test-workload",
            namespace="test-namespace",
            overlays_values=overlay_values,
        )

        # Verify subprocess was called
        mock_exec.assert_awaited_once()
        call_args = mock_exec.await_args[0]  # type: ignore[index]

        # Verify overlay files were passed via --values flag
        assert "--values" in call_args
        # There should be 2 --values flags (one for each overlay)
        values_count = sum(1 for arg in call_args if arg == "--values")
        assert values_count == 2

        # Verify the result
        assert result == "rendered: manifest"


@pytest.mark.asyncio
async def test_render_helm_template_invalid_template() -> None:
    """Test ValidationException is raised when Helm template rendering fails."""
    chart = Chart(
        name="invalid-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[
            ChartFile(path="Chart.yaml", content="invalid: yaml: ["),
        ],
    )

    # Mock subprocess to simulate helm failure
    mock_process = AsyncMock(spec=asyncio.subprocess.Process)
    mock_process.returncode = 1
    mock_process.communicate.return_value = (
        b"",
        b"Error: template: mychart/templates/deployment.yaml:10:2: executing",
    )

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(ValidationException) as exc_info:
            await render_helm_template(
                chart=chart,
                name="test-workload",
                namespace="test-namespace",
            )

        # Verify exception message and detail
        assert "Failed to render Helm template" in str(exc_info.value)
        assert "executing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_render_helm_template_helm_failure() -> None:
    """Test error handling when helm command fails with various error codes."""
    chart = Chart(
        name="fail-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[
            ChartFile(path="Chart.yaml", content="apiVersion: v2"),
        ],
    )

    # Test with different error codes
    for error_code in [1, 2, 127]:
        mock_process = AsyncMock(spec=asyncio.subprocess.Process)
        mock_process.returncode = error_code
        mock_process.communicate.return_value = (b"", b"helm command failed")

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(ValidationException) as exc_info:
                await render_helm_template(
                    chart=chart,
                    name="test-workload",
                    namespace="test-namespace",
                )

            assert "Failed to render Helm template" in str(exc_info.value)
            assert "helm command failed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_render_helm_template_with_complex_overlays() -> None:
    """Test rendering with complex nested overlay values."""
    chart = Chart(
        name="complex-overlay-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[
            ChartFile(path="Chart.yaml", content="apiVersion: v2\nname: test"),
        ],
    )

    # Complex overlay with nested structures
    overlay_values = [
        {
            "deployment": {
                "replicas": 5,
                "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0}},
            },
            "service": {"type": "LoadBalancer", "ports": [{"name": "http", "port": 80}]},
        }
    ]

    mock_process = AsyncMock(spec=asyncio.subprocess.Process)
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"complex: manifest", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        # Mock yaml.dump to verify overlay content
        with patch("app.charts.utils.yaml.dump") as mock_yaml_dump:
            result = await render_helm_template(
                chart=chart,
                name="complex-workload",
                namespace="test-namespace",
                overlays_values=overlay_values,
            )

            # Verify yaml.dump was called with the overlay values
            mock_yaml_dump.assert_called_once()
            dumped_values = mock_yaml_dump.call_args[0][0]
            assert dumped_values == overlay_values[0]

            assert result == "complex: manifest"


@pytest.mark.asyncio
async def test_render_helm_template_creates_overlay_files_in_chart_dir() -> None:
    """Test that overlay files are created in the chart directory."""
    chart = Chart(
        name="overlay-file-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[
            ChartFile(path="Chart.yaml", content="apiVersion: v2"),
        ],
    )

    overlay_values = [{"key1": "value1"}, {"key2": "value2"}]

    mock_process = AsyncMock(spec=asyncio.subprocess.Process)
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"manifest", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        await render_helm_template(
            chart=chart,
            name="test-workload",
            namespace="test-namespace",
            overlays_values=overlay_values,
        )

        # Verify subprocess was called with overlay files
        mock_exec.assert_awaited_once()
        call_args = mock_exec.await_args[0]  # type: ignore[index]

        # Verify overlay files were passed via --values flag
        assert "--values" in call_args
        # There should be 2 --values flags (one for each overlay)
        values_count = sum(1 for arg in call_args if arg == "--values")
        assert values_count == 2

    # Note: We can't verify files exist after context exits because cleanup happens
    # But we verified the subprocess was called with correct --values arguments


@pytest.mark.asyncio
async def test_render_helm_template_empty_overlays_list() -> None:
    """Test rendering with empty overlays list (default parameter)."""
    chart = Chart(
        name="no-overlay-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[
            ChartFile(path="Chart.yaml", content="apiVersion: v2"),
        ],
    )

    mock_process = AsyncMock(spec=asyncio.subprocess.Process)
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"simple: manifest", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        result = await render_helm_template(
            chart=chart,
            name="test-workload",
            namespace="test-namespace",
            overlays_values=[],  # Empty list
        )

        # Verify no --values flags were added
        call_args = mock_exec.await_args[0]  # type: ignore[index]
        assert "--values" not in call_args

        assert result == "simple: manifest"


@pytest.mark.asyncio
async def test_render_helm_template_special_characters_in_name() -> None:
    """Test rendering with workload name containing special characters."""
    chart = Chart(
        name="special-char-chart",
        type=WorkloadType.INFERENCE,
        signature={},
        files=[
            ChartFile(path="Chart.yaml", content="apiVersion: v2"),
        ],
    )

    # Workload name with hyphens and numbers (common in k8s)
    workload_name = "test-workload-123-abc"

    mock_process = AsyncMock(spec=asyncio.subprocess.Process)
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"manifest", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        await render_helm_template(
            chart=chart,
            name=workload_name,
            namespace="test-namespace",
        )

        call_args = mock_exec.await_args[0]  # type: ignore[index]
        assert workload_name in call_args
        # Verify fullnameOverride is set correctly
        fullname_override_found = any(f"fullnameOverride={workload_name}" in str(arg) for arg in call_args)
        assert fullname_override_found
