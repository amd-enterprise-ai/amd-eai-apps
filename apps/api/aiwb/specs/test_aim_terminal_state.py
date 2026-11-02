# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the fail-fast terminal-state check.

The AIM inference suites failed wholesale
because a *superseded* predictor pod was crash-looping while its replacement came up.
aim-engine can publish the predictor Deployment before the profile ConfigMap it mounts
exists, so revision 1 starts without a profile and exits immediately; revision 2 —
which carries the ConfigMap and the weights volume — then spends minutes pulling
weights, leaving the abandoned pod visibly CrashLoopBackOff for the whole window.

"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "libraries"))

from AIMPodInspector import aim_pods_should_not_be_in_a_terminal_state  # noqa: E402

AIM = "wb-aim-example"


def _pod(name, replica_set=None, container="kserve-container", reason=None, *, init=False):
    owner = [{"kind": "ReplicaSet", "name": replica_set}] if replica_set else []
    state = {"waiting": {"reason": reason}} if reason else {"running": {}}
    status_key = "initContainerStatuses" if init else "containerStatuses"
    return {
        "metadata": {"name": name, "ownerReferences": owner},
        "status": {status_key: [{"name": container, "state": state}]},
    }


def _replica_set(name, deployment, revision, created="2026-08-25T16:44:49Z"):
    return {
        "metadata": {
            "name": name,
            "creationTimestamp": created,
            "annotations": {"deployment.kubernetes.io/revision": str(revision)},
            "ownerReferences": [{"kind": "Deployment", "name": deployment}],
        }
    }


@pytest.fixture()
def cluster(monkeypatch):
    """Stub kubectl so the keyword reads the pods/replicasets a test declares."""
    state = {"pods": [], "replicasets": [], "fail": False, "fail_replicasets": False}

    def fake_json(args, action):
        listing = "replicasets" if "replicasets" in args else "pods"
        if state["fail"] or (listing == "replicasets" and state["fail_replicasets"]):
            return None
        return {"items": state[listing]}

    monkeypatch.setattr("AIMPodInspector._try_kubectl_json", fake_json)
    return state


# -- Terminal-state fail-fast --


def test_crash_loop_on_superseded_replica_set_is_ignored(cluster):
    """The abandoned revision-1 pod must not fail the deploy.

    This is the exact shape observed on a test cluster: revision 1 crash-loops on a missing
    profile while revision 2 is still in ContainerCreating pulling weights.
    """
    deployment = f"{AIM}-abcdef-predictor"
    cluster["replicasets"] = [
        _replica_set(f"{deployment}-rs-old", deployment, revision=1, created="2026-08-25T16:44:49Z"),
        _replica_set(f"{deployment}-rs-new", deployment, revision=2, created="2026-08-25T16:44:50Z"),
    ]
    cluster["pods"] = [
        _pod(f"{deployment}-rs-old-pod-a", f"{deployment}-rs-old", reason="CrashLoopBackOff"),
        _pod(f"{deployment}-rs-new-pod-b", f"{deployment}-rs-new", reason="ContainerCreating"),
    ]

    aim_pods_should_not_be_in_a_terminal_state(AIM, "qa-test")


def test_crash_loop_on_current_replica_set_still_fails_fast(cluster):
    """A genuinely broken image crash-loops on the *current* revision and must fail."""
    deployment = f"{AIM}-abcdef-predictor"
    cluster["replicasets"] = [_replica_set(f"{deployment}-rs-new", deployment, revision=2)]
    cluster["pods"] = [_pod(f"{deployment}-rs-new-pod-b", f"{deployment}-rs-new", reason="CrashLoopBackOff")]

    with pytest.raises(AssertionError, match="CrashLoopBackOff"):
        aim_pods_should_not_be_in_a_terminal_state(AIM, "qa-test")


def test_image_pull_failure_on_current_replica_set_fails_fast(cluster):
    """An unpullable image is terminal too — the check is not crash-loop specific."""
    deployment = f"{AIM}-abcdef-predictor"
    cluster["replicasets"] = [_replica_set(f"{deployment}-rs-new", deployment, revision=1)]
    cluster["pods"] = [_pod(f"{deployment}-rs-new-pod-b", f"{deployment}-rs-new", reason="ImagePullBackOff")]

    with pytest.raises(AssertionError, match="ImagePullBackOff"):
        aim_pods_should_not_be_in_a_terminal_state(AIM, "qa-test")


def test_terminal_init_container_on_current_replica_set_fails_fast(cluster):
    """Terminal waiting states on init containers are checked too."""
    deployment = f"{AIM}-abcdef-predictor"
    replica_set = f"{deployment}-rs-new"
    cluster["replicasets"] = [_replica_set(replica_set, deployment, revision=1)]
    cluster["pods"] = [
        _pod(f"{replica_set}-pod-b", replica_set, container="storage-initializer", reason="ErrImagePull", init=True)
    ]

    with pytest.raises(AssertionError, match="storage-initializer=ErrImagePull"):
        aim_pods_should_not_be_in_a_terminal_state(AIM, "qa-test")


def test_pods_of_other_aims_are_not_considered(cluster):
    """Only pods of the AIM under test can fail it — namespaces are shared."""
    other = "wb-aim-other-abcdef-predictor"
    cluster["replicasets"] = [_replica_set(f"{other}-abc", other, revision=1)]
    cluster["pods"] = [_pod(f"{other}-abc-xyz", f"{other}-abc", reason="CrashLoopBackOff")]

    aim_pods_should_not_be_in_a_terminal_state(AIM, "qa-test")


def test_no_pods_yet_is_not_a_failure(cluster):
    """Early Pending, before any pod exists, is a normal part of deploying."""
    aim_pods_should_not_be_in_a_terminal_state(AIM, "qa-test")


def test_unavailable_kubectl_is_a_no_op(cluster):
    """The check is best-effort — a missing kubectl must not invent a test failure."""
    cluster["fail"] = True

    aim_pods_should_not_be_in_a_terminal_state(AIM, "qa-test")


def test_unreadable_replica_sets_spares_owned_pods(cluster):
    """Without the ReplicaSets, an owned pod could be superseded — so it is not judged.

    Judging it anyway (e.g. when RBAC allows listing pods but not ReplicaSets) would
    resurrect the false failure this keyword exists to prevent.
    """
    deployment = f"{AIM}-abcdef-predictor"
    cluster["fail_replicasets"] = True
    cluster["pods"] = [_pod(f"{deployment}-rs-old-pod-a", f"{deployment}-rs-old", reason="CrashLoopBackOff")]

    aim_pods_should_not_be_in_a_terminal_state(AIM, "qa-test")


def test_unreadable_replica_sets_still_judges_unowned_pods(cluster):
    """A pod with no ReplicaSet owner has no newer revision that could supersede it.

    Losing the ReplicaSet listing says nothing about such a pod, so it keeps its
    fail-fast rather than being swept up in the narrowing.
    """
    cluster["fail_replicasets"] = True
    cluster["pods"] = [_pod(f"{AIM}-standalone", replica_set=None, reason="CrashLoopBackOff")]

    with pytest.raises(AssertionError, match="CrashLoopBackOff"):
        aim_pods_should_not_be_in_a_terminal_state(AIM, "qa-test")


def test_pod_without_replica_set_owner_is_still_checked(cluster):
    """A bare pod has no revision to supersede it, so it is judged on its own state."""
    cluster["pods"] = [_pod(f"{AIM}-standalone", replica_set=None, reason="CreateContainerConfigError")]

    with pytest.raises(AssertionError, match="CreateContainerConfigError"):
        aim_pods_should_not_be_in_a_terminal_state(AIM, "qa-test")


def test_creation_time_breaks_tie_when_revision_annotation_is_missing(cluster):
    """Older ReplicaSets are still ignored when revision annotations are absent."""
    deployment = f"{AIM}-abcdef-predictor"
    old = _replica_set(f"{deployment}-rs-old", deployment, revision=1, created="2026-08-25T16:44:49Z")
    new = _replica_set(f"{deployment}-rs-new", deployment, revision=2, created="2026-08-25T16:44:50Z")
    old["metadata"]["annotations"] = {}
    new["metadata"]["annotations"] = {}
    cluster["replicasets"] = [old, new]
    cluster["pods"] = [_pod(f"{deployment}-rs-old-pod-a", f"{deployment}-rs-old", reason="CrashLoopBackOff")]

    aim_pods_should_not_be_in_a_terminal_state(AIM, "qa-test")


def test_superseded_revision_is_decided_per_deployment(cluster):
    """Revision numbers restart per Deployment, so ranking must not be global.

    A revision-1 ReplicaSet of one Deployment is current even when another Deployment
    in the namespace has reached revision 3.
    """
    mine = f"{AIM}-abcdef-predictor"
    theirs = "wb-aim-third-abcdef-predictor"
    cluster["replicasets"] = [
        _replica_set(f"{mine}-only", mine, revision=1),
        _replica_set(f"{theirs}-old", theirs, revision=2),
        _replica_set(f"{theirs}-new", theirs, revision=3),
    ]
    cluster["pods"] = [_pod(f"{mine}-only-pod", f"{mine}-only", reason="CrashLoopBackOff")]

    with pytest.raises(AssertionError, match="CrashLoopBackOff"):
        aim_pods_should_not_be_in_a_terminal_state(AIM, "qa-test")
