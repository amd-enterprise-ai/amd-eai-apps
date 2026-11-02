# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for AIMPodInspector runtime-profile resolution."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "libraries"))

import AIMPodInspector


def _pod(*, profile_id: str | None = None, env: list[dict] | None = None, args: list[str] | None = None) -> dict:
    container_env = list(env or [])
    volumes = []
    volume_mounts = []
    if profile_id is not None:
        container_env.append({"name": "AIM_PROFILE_ID", "value": profile_id})
        volumes.append({"name": "aim-profile", "configMap": {"name": "runtime-profile"}})
        volume_mounts.append(
            {
                "name": "aim-profile",
                "mountPath": "/workspace/aim-runtime/profiles/custom/example/model",
            }
        )
    return {
        "metadata": {"name": "service-predictor-pod"},
        "spec": {
            "volumes": volumes,
            "containers": [
                {
                    "name": "kserve-container",
                    "env": container_env,
                    "args": args or [],
                    "volumeMounts": volume_mounts,
                    "resources": {"limits": {"amd.com/gpu": "2"}},
                }
            ],
        },
    }


def _patch_pod(monkeypatch: pytest.MonkeyPatch, pod: dict) -> None:
    monkeypatch.setattr(AIMPodInspector, "_predictor_pod", lambda service_name, namespace: pod)


def test_runtime_config_reads_engine_settings_from_mounted_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    pod = _pod(profile_id="custom/example/model/vllm-mi300x-fp4-tp2-latency")
    _patch_pod(monkeypatch, pod)
    profile = {
        "env_vars": {"VLLM_LOGGING_LEVEL": "DEBUG"},
        "engine_args": {"max-model-len": 8192},
    }

    def fake_kubectl(args: list[str], action: str) -> str:
        assert args == ["get", "configmap", "runtime-profile", "-n", "project", "-o", "json"]
        assert "runtime profile ConfigMap" in action
        return json.dumps(
            {
                "data": {
                    "vllm-mi300x-fp4-tp2-latency.yaml": AIMPodInspector.yaml.safe_dump(profile),
                }
            }
        )

    monkeypatch.setattr(AIMPodInspector, "_run_kubectl", fake_kubectl)

    config = AIMPodInspector.get_inference_pod_runtime_config("service", "project")

    assert config["env"]["VLLM_LOGGING_LEVEL"] == "DEBUG"
    assert config["engineArgs"] == {"max-model-len": 8192}
    assert config["argTokens"] == []


def test_mounted_engine_env_wins_over_container_env(monkeypatch: pytest.MonkeyPatch) -> None:
    pod = _pod(
        profile_id="custom/example/model/vllm-mi300x-fp4-tp2-latency",
        env=[{"name": "VLLM_LOGGING_LEVEL", "value": "INFO"}],
    )
    _patch_pod(monkeypatch, pod)
    monkeypatch.setattr(
        AIMPodInspector,
        "_run_kubectl",
        lambda args, action: json.dumps(
            {
                "data": {
                    "vllm-mi300x-fp4-tp2-latency.yaml": """
engine_args: {}
env_vars:
  VLLM_LOGGING_LEVEL: DEBUG
""",
                }
            }
        ),
    )

    config = AIMPodInspector.get_inference_pod_runtime_config("service", "project")

    assert config["env"]["VLLM_LOGGING_LEVEL"] == "DEBUG"


def test_runtime_assertions_support_mounted_aim_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    pod = _pod(profile_id="custom/example/model/vllm-mi300x-fp4-tp2-latency")
    _patch_pod(monkeypatch, pod)
    monkeypatch.setattr(
        AIMPodInspector,
        "_run_kubectl",
        lambda args, action: json.dumps(
            {
                "data": {
                    "vllm-mi300x-fp4-tp2-latency.yaml": """
engine_args:
  max-model-len: 8192
env_vars:
  VLLM_LOGGING_LEVEL: DEBUG
""",
                }
            }
        ),
    )

    AIMPodInspector.inference_pod_should_use_engine_env("service", "project", "VLLM_LOGGING_LEVEL", "DEBUG")
    AIMPodInspector.inference_pod_should_carry_engine_arg("service", "project", "8192")


def test_runtime_assertions_preserve_direct_engine_env_and_args(monkeypatch: pytest.MonkeyPatch) -> None:
    pod = _pod(
        env=[{"name": "VLLM_LOGGING_LEVEL", "value": "DEBUG"}],
        args=["--max-model-len=8192"],
    )
    _patch_pod(monkeypatch, pod)
    monkeypatch.setattr(
        AIMPodInspector,
        "_run_kubectl",
        lambda args, action: pytest.fail(f"direct engine must not read a profile ConfigMap: {args} ({action})"),
    )

    AIMPodInspector.inference_pod_should_use_engine_env("service", "project", "VLLM_LOGGING_LEVEL", "DEBUG")
    AIMPodInspector.inference_pod_should_carry_engine_arg("service", "project", "8192")


def test_image_pull_secrets_assertion_accepts_selected_among_cluster_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    pod = _pod()
    pod["spec"]["imagePullSecrets"] = [{"name": "cluster-default"}, {"name": "wb-secret-a"}, {"name": "wb-secret-b"}]
    _patch_pod(monkeypatch, pod)

    AIMPodInspector.inference_pod_should_use_image_pull_secrets("service", "project", "wb-secret-a", "wb-secret-b")


def test_image_pull_secrets_assertion_names_missing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    pod = _pod()
    pod["spec"]["imagePullSecrets"] = [{"name": "wb-secret-a"}]
    _patch_pod(monkeypatch, pod)

    with pytest.raises(AssertionError, match=r"missing image pull secrets \['wb-secret-b'\]"):
        AIMPodInspector.inference_pod_should_use_image_pull_secrets("service", "project", "wb-secret-a", "wb-secret-b")


def test_image_pull_secrets_assertion_fails_when_pod_has_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pod(monkeypatch, _pod())

    with pytest.raises(AssertionError, match="missing image pull secrets"):
        AIMPodInspector.inference_pod_should_use_image_pull_secrets("service", "project", "wb-secret-a")


def test_image_pull_secrets_assertion_tolerates_null_list_and_unnamed_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    pod = _pod()
    pod["spec"]["imagePullSecrets"] = None
    _patch_pod(monkeypatch, pod)

    with pytest.raises(AssertionError, match=r"it uses \[\]"):
        AIMPodInspector.inference_pod_should_use_image_pull_secrets("service", "project", "wb-secret-a")

    pod["spec"]["imagePullSecrets"] = [{}, {"name": "wb-secret-b"}]

    with pytest.raises(AssertionError, match=r"it uses \['wb-secret-b'\]"):
        AIMPodInspector.inference_pod_should_use_image_pull_secrets("service", "project", "wb-secret-a")


def test_image_pull_secrets_assertion_requires_an_expected_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pod(monkeypatch, _pod())

    with pytest.raises(ValueError, match="At least one expected image pull secret"):
        AIMPodInspector.inference_pod_should_use_image_pull_secrets("service", "project")


def test_runtime_profile_must_contain_selected_key(monkeypatch: pytest.MonkeyPatch) -> None:
    pod = _pod(profile_id="custom/example/model/selected-profile")
    _patch_pod(monkeypatch, pod)
    monkeypatch.setattr(
        AIMPodInspector,
        "_run_kubectl",
        lambda args, action: json.dumps({"data": {"different-profile.yaml": "engine_args: {}"}}),
    )

    with pytest.raises(AssertionError, match="selected-profile.yaml.*absent"):
        AIMPodInspector.get_inference_pod_runtime_config("service", "project")
