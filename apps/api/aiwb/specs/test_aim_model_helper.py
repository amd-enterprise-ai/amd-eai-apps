# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the Kubernetes resources built by AIMModelHelper."""

import importlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from robot.api.exceptions import SkipExecution

sys.path.insert(0, str(Path(__file__).parent / "libraries"))
sys.path.insert(0, str(Path(__file__).parents[4] / "testing" / "libraries"))

import AIMModelHelper


def test_fine_tuning_adapter_fixture_references_project_storage_credentials(monkeypatch):
    applied: dict[str, str] = {}

    def capture_yaml(yaml_body: str, namespace: str, error_label: str) -> None:
        applied.update(yaml_body=yaml_body, namespace=namespace, error_label=error_label)

    monkeypatch.setattr(AIMModelHelper, "_apply_yaml", capture_yaml)

    AIMModelHelper.apply_aim_artifact_cr("adapter-one", "project-one")

    manifest = yaml.safe_load(applied["yaml_body"])
    env = {entry["name"]: entry for entry in manifest["spec"]["env"]}
    assert env == {
        "AWS_ACCESS_KEY_ID": {
            "name": "AWS_ACCESS_KEY_ID",
            "valueFrom": {
                "secretKeyRef": {
                    "name": "minio-credentials",
                    "key": "minio-access-key",
                }
            },
        },
        "AWS_SECRET_ACCESS_KEY": {
            "name": "AWS_SECRET_ACCESS_KEY",
            "valueFrom": {
                "secretKeyRef": {
                    "name": "minio-credentials",
                    "key": "minio-secret-key",
                }
            },
        },
        "AWS_ENDPOINT_URL": {
            "name": "AWS_ENDPOINT_URL",
            "value": AIMModelHelper._S3_BUCKET_URL,
        },
    }


def test_fine_tuning_run_output_is_laid_out_like_a_completed_lora_run(monkeypatch):
    """The reclaim scenarios only prove anything if the run folder has the shape a real run leaves."""
    written: list[str] = []

    class RecordingClient:
        def put_object(self, bucket: str, key: str, data: Any, length: int) -> None:
            written.append(key)

    monkeypatch.setattr(AIMModelHelper, "_minio_client", lambda namespace: RecordingClient())

    run_uri = AIMModelHelper.write_fine_tuning_run_output_to_project_storage("project-one", "example-org/base")
    adapter_uri = AIMModelHelper.fine_tuned_adapter_location_in_run(run_uri)

    run_prefix = AIMModelHelper._prefix_from_storage_location(run_uri)
    parts = run_prefix.rstrip("/").split("/")
    assert parts[:2] == ["project-one", "finetuned-models"]
    assert parts[2:-1] == ["example-org", "base"]
    assert str(uuid.UUID(parts[-1])) == parts[-1]
    assert adapter_uri == f"{run_uri}checkpoint-final-adapter"
    assert all(key.startswith(run_prefix) for key in written)
    assert f"{run_prefix}checkpoint-final-adapter/adapter_config.json" in written
    assert f"{run_prefix}checkpoint-final-adapter/adapter_model.safetensors" in written
    assert any("/" not in key.removeprefix(run_prefix) for key in written), "no run-level file beside the weights"


def test_w_series_accelerator_selects_radeon_onboard_family() -> None:
    families = [
        {"familyId": "aim-base", "repository": "amdenterpriseai/aim-base", "tags": ["0.13.1"]},
        {"familyId": "aim-radeon-base", "repository": "amdenterpriseai/aim-radeon-base", "tags": ["0.12"]},
    ]
    accelerators = [{"acceleratorType": "gpu", "acceleratorModel": "W7900", "acceleratorVendor": "amd"}]

    assert (
        AIMModelHelper.resolve_onboard_base_image_family_from_cluster_discovery(families, accelerators)
        == "aim-radeon-base"
    )


def test_alternate_onboard_image_prefers_a_different_family() -> None:
    families = [
        {"familyId": "aim-base", "repository": "amdenterpriseai/aim-base", "tags": ["0.13.1"]},
        {"familyId": "aim-radeon-base", "repository": "amdenterpriseai/aim-radeon-base", "tags": ["0.12"]},
    ]
    accelerators = [{"acceleratorType": "gpu", "acceleratorModel": "MI300X", "acceleratorVendor": "amd"}]

    assert (
        AIMModelHelper.resolve_alternate_onboard_image_from_cluster_discovery(
            families, accelerators, "amdenterpriseai/aim-base:0.13.1"
        )
        == "amdenterpriseai/aim-radeon-base:0.12"
    )


def test_alternate_onboard_image_falls_back_to_another_tag() -> None:
    families = [
        {"familyId": "aim-radeon-base", "repository": "amdenterpriseai/aim-radeon-base", "tags": ["0.11", "0.12"]},
    ]
    accelerators = [{"acceleratorType": "gpu", "acceleratorModel": "W7900", "acceleratorVendor": "amd"}]

    assert (
        AIMModelHelper.resolve_alternate_onboard_image_from_cluster_discovery(
            families, accelerators, "amdenterpriseai/aim-radeon-base:0.12"
        )
        == "amdenterpriseai/aim-radeon-base:0.11"
    )


def test_alternate_onboard_image_skips_when_catalog_has_one_image() -> None:
    families = [
        {"familyId": "aim-radeon-base", "repository": "amdenterpriseai/aim-radeon-base", "tags": ["0.12"]},
    ]
    accelerators = [{"acceleratorType": "gpu", "acceleratorModel": "W7900", "acceleratorVendor": "amd"}]

    with pytest.raises(SkipExecution):
        AIMModelHelper.resolve_alternate_onboard_image_from_cluster_discovery(
            families, accelerators, "amdenterpriseai/aim-radeon-base:0.12"
        )


def test_conflicting_tag_returns_another_tag_of_the_same_family() -> None:
    families = [
        {"familyId": "aim-radeon-base", "repository": "amdenterpriseai/aim-radeon-base", "tags": ["0.11", "0.12"]},
        {"familyId": "aim-base", "repository": "amdenterpriseai/aim-base", "tags": ["0.13.1"]},
    ]

    assert (
        AIMModelHelper.resolve_conflicting_tag_of_onboard_image(families, "amdenterpriseai/aim-radeon-base:0.12")
        == "amdenterpriseai/aim-radeon-base:0.11"
    )


def test_published_base_images_preserve_digest_separator() -> None:
    families = [
        {
            "familyId": "aim-base",
            "repository": "amdenterpriseai/aim-base",
            "tags": ["sha256:abcdef0123456789"],
        }
    ]

    assert AIMModelHelper._published_base_images(families) == [
        ("aim-base", "amdenterpriseai/aim-base@sha256:abcdef0123456789")
    ]
    assert (
        AIMModelHelper.build_catalog_image_ref("amdenterpriseai/aim-base", "sha256:abcdef0123456789")
        == "amdenterpriseai/aim-base@sha256:abcdef0123456789"
    )
    assert AIMModelHelper.build_catalog_image_ref("amdenterpriseai/aim-base", "0.13.1") == (
        "amdenterpriseai/aim-base:0.13.1"
    )


def test_aim_model_spec_image_reads_cluster_scoped_base(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert cmd[:4] == ["kubectl", "get", "aimclustermodels", "aim-base-013"]
        assert "-n" not in cmd
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"spec": {"image": "amdenterpriseai/aim-base:0.13"}}), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert (
        AIMModelHelper.aim_model_spec_image("aim-base-013", "project-one", "Cluster") == "amdenterpriseai/aim-base:0.13"
    )


def test_aim_model_should_use_runtime_family_from_cluster_scoped_base(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_image = "amdenterpriseai/aim-base:0.13"

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        payload: dict[str, Any]
        if "aimclustermodels" in cmd:
            payload = {"spec": {"image": expected_image}}
        else:
            payload = {
                "spec": {
                    "profiles": {
                        "derivedFrom": {"selector": {"modelRef": {"name": "aim-base-013", "scope": "Cluster"}}},
                        "overrides": {"image": expected_image},
                    }
                }
            }
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    AIMModelHelper.aim_model_should_use_runtime_family_from_image("custom-model", "project-one", expected_image)


def test_aim_model_should_use_runtime_family_from_namespaced_base(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_image = "amdenterpriseai/aim-radeon-base:0.12"

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert "aimclustermodels" not in cmd
        payload: dict[str, Any]
        if cmd[:4] == ["kubectl", "get", "aimmodels", "aim-radeon-base"]:
            payload = {"spec": {"image": expected_image}}
        else:
            payload = {
                "spec": {
                    "profiles": {
                        "derivedFrom": {"selector": {"modelRef": {"name": "aim-radeon-base", "scope": "Namespace"}}},
                        "overrides": {"image": expected_image},
                    }
                }
            }
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    AIMModelHelper.aim_model_should_use_runtime_family_from_image("custom-model", "project-one", expected_image)


def test_cluster_gpu_accelerator_model_picks_first_gpu_model():
    accelerators = [
        {"acceleratorType": "cpu", "acceleratorModel": "EPYC_9654"},
        {"acceleratorType": "gpu", "acceleratorModel": ""},
        {"acceleratorType": "GPU", "acceleratorModel": "MI300X"},
    ]
    assert AIMModelHelper.cluster_gpu_accelerator_model(accelerators) == "MI300X"


def test_cluster_gpu_accelerator_model_is_empty_without_a_gpu():
    assert (
        AIMModelHelper.cluster_gpu_accelerator_model([{"acceleratorType": "cpu", "acceleratorModel": "EPYC_9654"}])
        == ""
    )


def test_cluster_gpu_accelerator_model_ignores_a_whitespace_only_model():
    accelerators = [
        {"acceleratorType": "gpu", "acceleratorModel": "   "},
        {"acceleratorType": "gpu", "acceleratorModel": " MI300X "},
    ]
    assert AIMModelHelper.cluster_gpu_accelerator_model(accelerators) == "MI300X"


def test_cluster_gpu_accelerator_model_matches_the_onboard_image_family_on_a_mixed_cluster():
    accelerators = [
        {"acceleratorType": "gpu", "acceleratorModel": "W7900", "acceleratorVendor": "amd"},
        {"acceleratorType": "gpu", "acceleratorModel": "MI300X", "acceleratorVendor": "amd"},
    ]
    assert (
        AIMModelHelper.cluster_gpu_accelerator_model(accelerators, "docker.io/amdenterpriseai/aim-base:0.13.1")
        == "MI300X"
    )
    assert (
        AIMModelHelper.cluster_gpu_accelerator_model(accelerators, "docker.io/amdenterpriseai/aim-radeon-base:0.13.1")
        == "W7900"
    )


def test_cluster_gpu_accelerator_model_is_empty_when_no_gpu_fits_the_onboard_image_family():
    accelerators = [{"acceleratorType": "gpu", "acceleratorModel": "W7900", "acceleratorVendor": "amd"}]
    assert AIMModelHelper.cluster_gpu_accelerator_model(accelerators, "docker.io/amdenterpriseai/aim-base:1") == ""


def test_deployment_ids_pinning_custom_models_keeps_other_suites_deployments():
    custom_models = [{"metadata": {"name": "qwen-import-1"}}, {"metadata": {"name": "qwen-import-2"}}]
    deployments = [
        {"id": "svc-a", "spec": {"model": {"name": "qwen-import-1"}}},
        {"id": "svc-b", "spec": {"model": {"name": "aim-catalog-model"}}},
        {"id": "svc-c", "spec": {"model": {"name": "qwen-import-2"}}},
        {"id": None, "spec": {"model": {"name": "qwen-import-1"}}},
        {"id": "svc-d", "spec": {}},
    ]
    assert AIMModelHelper.deployment_ids_pinning_custom_models(deployments, custom_models) == ["svc-a", "svc-c"]


def test_deployment_ids_pinning_custom_models_is_empty_without_custom_models():
    deployments = [{"id": "svc-a", "spec": {"model": {"name": ""}}}]
    assert AIMModelHelper.deployment_ids_pinning_custom_models(deployments, []) == []


def _model_stamped(name, run_id=None):
    labels = {"e2e.silogen.ai/run-id": run_id} if run_id is not None else {}
    return {"metadata": {"name": name, "labels": labels}}


def test_models_stamped_by_another_run_selects_only_other_runs_stamps():
    models = [_model_stamped("old", "111-aaaa"), _model_stamped("mine", "222-bbbb"), _model_stamped("bare")]
    selected = AIMModelHelper.models_stamped_by_another_run(models, "222-bbbb")
    assert [m["metadata"]["name"] for m in selected] == ["old"]


def test_models_stamped_by_another_run_never_selects_unstamped_or_empty_stamps():
    models = [_model_stamped("bare"), _model_stamped("blank", ""), {"metadata": {"name": "nolabels"}}, {}]
    assert AIMModelHelper.models_stamped_by_another_run(models, "222-bbbb") == []


def test_models_without_a_run_stamp_lists_what_is_only_reported():
    models = [_model_stamped("old", "111-aaaa"), _model_stamped("bare"), _model_stamped("blank", "")]
    assert [m["metadata"]["name"] for m in AIMModelHelper.models_without_a_run_stamp(models)] == ["bare", "blank"]


def test_new_e2e_run_id_is_unique_per_invocation_and_carries_the_ci_run(monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "36959181936")
    first, second = AIMModelHelper.new_e2e_run_id(), AIMModelHelper.new_e2e_run_id()
    assert first.startswith("36959181936-") and first != second
    monkeypatch.delenv("GITHUB_RUN_ID")
    assert AIMModelHelper.new_e2e_run_id().startswith("local-")


def test_stamp_aim_model_with_run_id_reports_failure_instead_of_raising(monkeypatch):
    class _Failed:
        returncode = 1
        stderr = "forbidden"

    monkeypatch.setattr(AIMModelHelper.subprocess, "run", lambda *a, **k: _Failed())
    assert AIMModelHelper.stamp_aim_model_with_run_id("m", "ns", "1-a") is False

    def _missing(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(AIMModelHelper.subprocess, "run", _missing)
    assert AIMModelHelper.stamp_aim_model_with_run_id("m", "ns", "1-a") is False


def test_stamp_aim_model_with_run_id_labels_the_model_with_kubectl(monkeypatch):
    calls = []

    class _Ok:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(AIMModelHelper.subprocess, "run", lambda cmd, **k: calls.append(cmd) or _Ok())
    assert AIMModelHelper.stamp_aim_model_with_run_id("m", "ns", "1-a") is True
    assert calls == [["kubectl", "label", "aimmodels", "m", "-n", "ns", "e2e.silogen.ai/run-id=1-a", "--overwrite"]]


def _fresh_test_prefix(monkeypatch, *, run_id=None, user="apiserver"):
    TestPrefix = importlib.import_module("TestPrefix")
    monkeypatch.setattr(TestPrefix, "_cached_prefix", None)
    for variable in ("E2E_TEST_PREFIX", "GITHUB_RUN_ID", "CI_RUN_ID"):
        monkeypatch.delenv(variable, raising=False)
    if run_id is not None:
        monkeypatch.setenv("GITHUB_RUN_ID", run_id)
    monkeypatch.setattr(TestPrefix.getpass, "getuser", lambda: user)
    return TestPrefix


def test_shared_test_project_name_in_the_runner_pod_is_the_apiserver_project(monkeypatch):
    # The runner pod carries no CI run id and runs as `apiserver`, so the suite's shared project,
    # which the leftover-model sweep resolves through the same call, is e2e-apiserver-testing.
    assert _fresh_test_prefix(monkeypatch).test_name("testing") == "e2e-apiserver-testing"


def test_shared_test_project_name_follows_the_ci_run_id_when_one_is_set(monkeypatch):
    assert _fresh_test_prefix(monkeypatch, run_id="36959181936").test_name("testing") == "e2e-ci36959181936-testing"


def test_a_local_invocation_never_sweeps_any_models():
    models = [_model_stamped("ci", "111-aaaa"), _model_stamped("local", "local-aaaa")]
    assert AIMModelHelper.models_stamped_by_another_run(models, "local-bbbb") == []
    unswept = AIMModelHelper.models_stamped_by_an_unswept_run(models, "local-bbbb")
    assert [m["metadata"]["name"] for m in unswept] == ["ci", "local"]


def test_a_ci_run_never_sweeps_a_local_invocations_models():
    models = [
        _model_stamped("ci", "111-aaaa"),
        _model_stamped("local", "local-aaaa"),
        _model_stamped("mine", "222-bbbb"),
    ]
    selected = AIMModelHelper.models_stamped_by_another_run(models, "222-bbbb")
    assert [m["metadata"]["name"] for m in selected] == ["ci"]
    unswept = AIMModelHelper.models_stamped_by_an_unswept_run(models, "222-bbbb")
    assert [m["metadata"]["name"] for m in unswept] == ["local"]


def test_run_id_uses_the_ci_run_id_the_workflow_passes_into_the_runner(monkeypatch):
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    run_id = AIMModelHelper.new_e2e_run_id("36959181936")
    assert run_id.startswith("36959181936-")
    models = [_model_stamped("old", "111-aaaa")]
    assert [m["metadata"]["name"] for m in AIMModelHelper.models_stamped_by_another_run(models, run_id)] == ["old"]


def test_run_id_without_any_ci_id_is_local(monkeypatch):
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    assert AIMModelHelper.new_e2e_run_id().startswith("local-")


def test_cluster_gpu_accelerator_model_gives_the_epyc_image_no_gpu_override():
    accelerators = [{"acceleratorType": "gpu", "acceleratorModel": "MI300X"}]
    assert AIMModelHelper.cluster_gpu_accelerator_model(accelerators, "ghcr.io/example/aim-epyc-base:1.0") == ""
