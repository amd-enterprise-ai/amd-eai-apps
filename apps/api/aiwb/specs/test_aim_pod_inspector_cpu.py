# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for AIMPodInspector CPU/EPYC placement assertion logic."""

import sys
from pathlib import Path

import pytest

# Add libraries to path so AIMPodInspector is importable
sys.path.insert(0, str(Path(__file__).parent / "libraries"))

import AIMPodInspector
from AIMPodInspector import (
    inference_pod_should_be_scheduled_on_accelerator,
    inference_pod_should_request_no_accelerators,
)


def _pod(*containers: dict) -> dict:
    return {"metadata": {"name": "predictor-pod"}, "spec": {"containers": list(containers)}}


def _container(name: str, gpu: int | None = None) -> dict:
    limits = {"amd.com/gpu": str(gpu)} if gpu is not None else {}
    return {"name": name, "resources": {"limits": limits}}


@pytest.fixture()
def patch_pod(monkeypatch):
    def _install(pod):
        monkeypatch.setattr(AIMPodInspector, "_predictor_pod", lambda service_name, namespace: pod)

    return _install


def test_no_accelerators_passes_when_all_containers_are_cpu(patch_pod):
    patch_pod(_pod(_container("kserve-container", gpu=0), _container("queue-proxy")))
    inference_pod_should_request_no_accelerators("svc", "ns")  # no raise


def test_no_accelerators_fails_when_model_server_requests_gpu(patch_pod):
    # The finding: a GPU-pinned model server alongside a no-GPU sidecar must NOT pass.
    patch_pod(_pod(_container("kserve-container", gpu=1), _container("queue-proxy")))
    with pytest.raises(AssertionError, match="GPU-requesting container"):
        inference_pod_should_request_no_accelerators("svc", "ns")


def test_no_accelerators_fails_when_only_container_requests_gpu(patch_pod):
    patch_pod(_pod(_container("kserve-container", gpu=2)))
    with pytest.raises(AssertionError, match="expected all zero"):
        inference_pod_should_request_no_accelerators("svc", "ns")


def test_no_accelerators_fails_when_init_container_requests_gpu(patch_pod):
    pod = _pod(_container("kserve-container"))
    pod["spec"]["initContainers"] = [_container("model-init", gpu=1)]
    patch_pod(pod)
    with pytest.raises(AssertionError, match="GPU-requesting container"):
        inference_pod_should_request_no_accelerators("svc", "ns")


def test_no_accelerators_fails_when_pod_has_no_containers(patch_pod):
    patch_pod({"metadata": {"name": "empty-pod"}, "spec": {}})
    with pytest.raises(AssertionError, match="has no regular or init containers"):
        inference_pod_should_request_no_accelerators("svc", "ns")


def test_accelerator_matches_positive_node_selector_key(patch_pod):
    pod = _pod(_container("kserve-container"))
    pod["spec"]["nodeSelector"] = {"feature.node.kubernetes.io/aim-accelerator.EPYC_9965": "1"}
    patch_pod(pod)
    inference_pod_should_be_scheduled_on_accelerator("svc", "ns", "EPYC_9965")


def test_accelerator_does_not_match_false_node_selector_value(patch_pod):
    pod = _pod(_container("kserve-container"))
    pod["spec"]["nodeSelector"] = {"feature.node.kubernetes.io/aim-accelerator.EPYC_9965": "0"}
    patch_pod(pod)
    with pytest.raises(AssertionError, match="not constrained"):
        inference_pod_should_be_scheduled_on_accelerator("svc", "ns", "EPYC_9965")


def test_generic_cpu_label_key_is_not_placement_proof(patch_pod):
    pod = _pod(_container("kserve-container"))
    pod["spec"]["nodeSelector"] = {"feature.node.kubernetes.io/aim-accelerator.CPU": "1"}
    patch_pod(pod)
    with pytest.raises(AssertionError, match="not constrained"):
        inference_pod_should_be_scheduled_on_accelerator("svc", "ns", "CPU")


def test_accelerator_matches_literal_node_selector_value(patch_pod):
    pod = _pod(_container("kserve-container"))
    pod["spec"]["nodeSelector"] = {"accelerator": "EPYC_9965"}
    patch_pod(pod)
    inference_pod_should_be_scheduled_on_accelerator("svc", "ns", "EPYC_9965")


def test_accelerator_matches_epyc_affinity_expression_key(patch_pod):
    pod = _pod(_container("kserve-container"))
    pod["spec"]["affinity"] = {
        "nodeAffinity": {
            "requiredDuringSchedulingIgnoredDuringExecution": {
                "nodeSelectorTerms": [
                    {
                        "matchExpressions": [
                            {
                                "key": "feature.node.kubernetes.io/aim-accelerator.EPYC_9965",
                                "operator": "Exists",
                            }
                        ]
                    }
                ]
            }
        }
    }
    patch_pod(pod)
    inference_pod_should_be_scheduled_on_accelerator("svc", "ns", "EPYC_9965")


def test_accelerator_matches_in_operator_values(patch_pod):
    pod = _pod(_container("kserve-container"))
    pod["spec"]["affinity"] = {
        "nodeAffinity": {
            "requiredDuringSchedulingIgnoredDuringExecution": {
                "nodeSelectorTerms": [
                    {
                        "matchExpressions": [
                            {
                                "key": "node.kubernetes.io/instance-type",
                                "operator": "In",
                                "values": ["EPYC_9965"],
                            }
                        ]
                    }
                ]
            }
        }
    }
    patch_pod(pod)
    inference_pod_should_be_scheduled_on_accelerator("svc", "ns", "EPYC_9965")


def test_accelerator_does_not_match_negative_affinity_operator(patch_pod):
    pod = _pod(_container("kserve-container"))
    pod["spec"]["affinity"] = {
        "nodeAffinity": {
            "requiredDuringSchedulingIgnoredDuringExecution": {
                "nodeSelectorTerms": [
                    {
                        "matchExpressions": [
                            {
                                "key": "feature.node.kubernetes.io/aim-accelerator.EPYC_9965",
                                "operator": "DoesNotExist",
                            }
                        ]
                    }
                ]
            }
        }
    }
    patch_pod(pod)
    with pytest.raises(AssertionError, match="not constrained"):
        inference_pod_should_be_scheduled_on_accelerator("svc", "ns", "EPYC_9965")


def test_accelerator_matches_scheduled_node_label_key(monkeypatch, patch_pod):
    pod = _pod(_container("kserve-container"))
    pod["spec"]["nodeName"] = "cpu-node"
    patch_pod(pod)
    monkeypatch.setattr(
        AIMPodInspector,
        "_run_kubectl",
        lambda args, action: '{"metadata":{"labels":{"feature.node.kubernetes.io/aim-accelerator.EPYC_9965":"1"}}}',
    )
    inference_pod_should_be_scheduled_on_accelerator("svc", "ns", "EPYC_9965")


def test_epyc_label_on_gpu_node_is_not_cpu_placement_proof(monkeypatch, patch_pod):
    pod = _pod(_container("kserve-container"))
    pod["spec"]["nodeName"] = "gpu-node"
    pod["spec"]["nodeSelector"] = {"feature.node.kubernetes.io/aim-accelerator.EPYC_9965": "1"}
    patch_pod(pod)
    monkeypatch.setattr(
        AIMPodInspector,
        "_run_kubectl",
        lambda args, action: (
            '{"metadata":{"labels":{'
            '"feature.node.kubernetes.io/aim-accelerator.EPYC_9965":"1",'
            '"feature.node.kubernetes.io/aim-accelerator.GPU":"1"}}}'
        ),
    )
    with pytest.raises(AssertionError, match="scheduled on GPU node"):
        inference_pod_should_be_scheduled_on_accelerator("svc", "ns", "EPYC_9965")


def test_false_gpu_label_does_not_reject_epyc_node(monkeypatch, patch_pod):
    pod = _pod(_container("kserve-container"))
    pod["spec"]["nodeName"] = "cpu-node"
    patch_pod(pod)
    monkeypatch.setattr(
        AIMPodInspector,
        "_run_kubectl",
        lambda args, action: (
            '{"metadata":{"labels":{'
            '"feature.node.kubernetes.io/aim-accelerator.EPYC_9965":"1",'
            '"feature.node.kubernetes.io/aim-accelerator.GPU":"0"}}}'
        ),
    )
    inference_pod_should_be_scheduled_on_accelerator("svc", "ns", "EPYC_9965")
