# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the patched-workloads validation script CI gates the Docker build on.

The script lives under ``tooling/`` (no pytest runner there) rather than in an
installable package, so it is imported by file path instead of a normal import.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[4] / "tooling/validate_patched_workloads.py"


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_patched_workloads", _SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_patched_workloads = _load_validator()


@pytest.fixture
def chart_dir(tmp_path: Path) -> Path:
    """A helm chart directory laid out like a vendored ai-workloads checkout."""
    helm_dir = tmp_path / "workloads" / "demo" / "helm"
    helm_dir.mkdir(parents=True)
    (helm_dir / "Chart.yaml").write_text("name: demo\nversion: 0.1.0\n")
    (helm_dir / "values.yaml").write_text("replicaCount: 1\n")
    templates_dir = helm_dir / "templates"
    templates_dir.mkdir()
    (templates_dir / "deployment.yaml").write_text("apiVersion: apps/v1\nkind: Deployment\n")
    overrides_dir = helm_dir / "overrides"
    overrides_dir.mkdir()
    (overrides_dir / "recipe.yaml").write_text("canonical_name: demo-recipe\n")
    return tmp_path


def _run_validator(monkeypatch: pytest.MonkeyPatch, workloads_dir: Path) -> int:
    monkeypatch.setattr("sys.argv", ["validate_patched_workloads.py", str(workloads_dir)])
    return validate_patched_workloads.main()


def test_clean_tree_passes(chart_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_validator(monkeypatch, chart_dir) == 0


def test_conflict_marker_in_values_fails(chart_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values_file = chart_dir / "workloads" / "demo" / "helm" / "values.yaml"
    values_file.write_text("<<<<<<< HEAD\nreplicaCount: 1\n=======\nreplicaCount: 2\n>>>>>>> patch\n")

    assert _run_validator(monkeypatch, chart_dir) == 1


def test_conflict_marker_in_overrides_fails(chart_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override_file = chart_dir / "workloads" / "demo" / "helm" / "overrides" / "recipe.yaml"
    override_file.write_text(
        "<<<<<<< HEAD\ncanonical_name: demo-recipe\n=======\ncanonical_name: other\n>>>>>>> patch\n"
    )

    assert _run_validator(monkeypatch, chart_dir) == 1


def test_conflict_marker_in_helm_template_fails(chart_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Templates are excluded from the YAML parse check, so only the marker scan covers them.

    Go templating is not valid YAML, so `_find_unparseable_yaml` skips
    `templates/`. That makes the conflict-marker scan the only defence over the
    largest surface of every chart, and this pins it on a path the YAML check
    cannot reach.
    """
    template = chart_dir / "workloads" / "demo" / "helm" / "templates" / "deployment.yaml"
    template.write_text("<<<<<<< HEAD\nkind: Deployment\n=======\nkind: StatefulSet\n>>>>>>> patch\n")

    assert _run_validator(monkeypatch, chart_dir) == 1


def test_unparseable_yaml_in_overrides_without_conflict_marker_fails(
    chart_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A patch can garble YAML without ever writing a conflict marker.

    This is the case that motivated checking overrides content, not just conflict
    markers: a bad patch can silently apply and still leave invalid YAML behind.
    """
    override_file = chart_dir / "workloads" / "demo" / "helm" / "overrides" / "recipe.yaml"
    override_file.write_text("canonical_name: [unterminated\n")

    assert _run_validator(monkeypatch, chart_dir) == 1


def test_missing_workloads_directory_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_dir = tmp_path / "does-not-exist"

    assert _run_validator(monkeypatch, missing_dir) == 1
    # A missing directory also has no Helm files, so assert on the reason to keep
    # this test from passing via the unrelated no-helm-files guard.
    assert "Workloads directory not found" in capsys.readouterr().err


def test_directory_with_no_helm_files_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty_dir = tmp_path / "ai-workloads"
    empty_dir.mkdir()

    assert _run_validator(monkeypatch, empty_dir) == 1
