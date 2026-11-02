#!/usr/bin/env python3

# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
"""Regression tests for the environment-check probe.

The probe's whole job is to never claim a cluster is healthy without actively proving it, so
each case pins a way it could otherwise report a false pass (or misclassify a problem). Tests
stub the probe's single side-effecting primitive — run() — so no cluster, kubectl, or registry
tooling is required and nothing is mutated. Each stub maps a kubectl/tool argv to a canned
(returncode, stdout, stderr), letting a test inject one unhealthy or unreadable signal against
an otherwise-healthy baseline.
"""
from __future__ import annotations

import contextlib
import datetime
import importlib.util
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from typing import Any, Callable


def _ts_ago(seconds: int) -> str:
    """RFC3339 timestamp `seconds` in the past, for pod startTime/creationTimestamp fixtures."""
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

_MOD_PATH = Path(__file__).resolve().parent.parent / "scripts" / "environment_check.py"
_spec = importlib.util.spec_from_file_location("environment_check", _MOD_PATH)
assert _spec and _spec.loader
# Typed as Any so mypy does not flag attribute rebinding (run/shutil) done for stubbing.
ec: Any = importlib.util.module_from_spec(_spec)
sys.modules["environment_check"] = ec  # dataclass introspection resolves the module by name
_spec.loader.exec_module(ec)


def _jsonlist(items: list[dict[str, Any]]) -> str:
    return json.dumps({"items": items})


# The full rule set the E2E suites exercise as the test identity; the healthy baseline grants it.
_E2E_RULES_COMPLETE = [
    {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimartifacts"], "verbs": ["get", "create", "patch"]},
    {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimprofiles"], "verbs": ["get", "list"]},
    {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimmodels"], "verbs": ["get", "list", "create", "patch", "delete"]},
    {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimmodels/status"], "verbs": ["get", "patch"]},
    {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimservices"], "verbs": ["get", "list", "create", "patch", "delete"]},
]


def _baseline() -> dict[str, tuple[int, str, str]]:
    """Return a fresh mapping of 'joined argv' -> (rc, stdout, stderr) for a fully HEALTHY run.

    Keys are matched as substrings of the joined command, longest-key-first, so a test can
    override one behaviour by adding a more specific (or equal) key.
    """
    return {
        "kubectl cluster-info": (0, "ok", ""),
        "kubectl get crd ciliumnodes.cilium.io": (0, "", ""),
        "kubectl get configmap cilium-config -n kube-system -o json": (0, json.dumps({"data": {"mtu": "9000"}}), ""),
        "kubectl get crd volumes.longhorn.io": (0, "", ""),
        "kubectl get volumes.longhorn.io -A -o json": (0, _jsonlist([{"metadata": {"name": "v1"}, "status": {"robustness": "healthy", "state": "attached"}}]), ""),
        "kubectl get storageclass -o json": (0, _jsonlist([{"metadata": {"name": "multinode"}, "provisioner": "csi.example.com"}]), ""),
        "kubectl get csidrivers.storage.k8s.io -o json": (0, _jsonlist([{"metadata": {"name": "csi.example.com"}}]), ""),
        "kubectl get csinodes.storage.k8s.io -o json": (0, _jsonlist([{"metadata": {"name": "node-0"}, "spec": {"drivers": [{"name": "csi.example.com"}]}}]), ""),
        "kubectl get leases.coordination.k8s.io -A -o json": (0, _jsonlist([{"metadata": {"name": "external-provisioner-leader-csi-example-com", "namespace": "kube-system"}, "spec": {"renewTime": _ts_ago(10)}}]), ""),
        "kubectl get pods -A -l app.kubernetes.io/component=csi-driver -o json": (0, _jsonlist([{"metadata": {"namespace": "kube-system", "name": "csi-0"}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}}]), ""),
        "kubectl get pods -A --field-selector=status.phase=Pending -o json": (0, _jsonlist([]), ""),
        "kubectl get events -A --field-selector reason=FailedMount -o json": (0, _jsonlist([]), ""),
        "kubectl get events -A --field-selector reason=DeadlineExceeded -o json": (0, _jsonlist([]), ""),
        "kubectl get jobs -A -o json": (0, _jsonlist([]), ""),
        "kubectl get pods -A -l app.kubernetes.io/name=device-metrics-exporter -o json": (0, _jsonlist([{"metadata": {"namespace": "kube-amd-gpu", "name": "exp-0"}}]), ""),
        "kubectl logs -n kube-amd-gpu exp-0 --tail=200": (0, "exporting metrics ok", ""),
        "kubectl get pods -n otel-lgtm-stack -l app.kubernetes.io/name=otel-collector -o json": (0, _jsonlist([{"metadata": {"name": "otel-0"}}]), ""),
        "kubectl logs -n otel-lgtm-stack otel-0 --tail=200": (0, "scrape ok", ""),
        "kubectl get svc -A -o json": (0, _jsonlist([{"metadata": {"namespace": "otel-lgtm-stack", "name": "lgtm-stack"}, "spec": {"ports": [{"port": 9090}]}}]), ""),
        "kubectl get pods -A --field-selector=status.phase=Running -o json": (0, _jsonlist([{"metadata": {"namespace": "proj", "name": "gpu-workload"}, "spec": {"containers": [{"resources": {"requests": {"amd.com/gpu": "1"}}}]}, "status": {"phase": "Running"}}]), ""),
        "get --raw": (0, json.dumps({"status": "success", "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1735000000, "8"]}]}}), ""),
        "kubectl get crd aimclustermodels.aim.eai.amd.com": (0, "", ""),
        "kubectl get aimclustermodels.aim.eai.amd.com -A -o json": (0, _jsonlist([{"metadata": {"name": "m1"}, "status": {"conditions": [{"type": "ManagedProfilesReady", "status": "True", "reason": "SupportedProfilesFound"}]}}]), ""),
        "kubectl get nodes -o json": (0, _jsonlist([{"metadata": {"labels": {"amd.com/gpu.device-id": "7551"}}, "status": {"capacity": {"amd.com/gpu": "8"}, "allocatable": {"amd.com/gpu": "8"}}}]), ""),
        "kubectl get externalsecret -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "aiwb-openbao-token"}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}}]), ""),
        "kubectl get secret default-minio-tenant-env-configuration -n minio-tenant-default -o name": (0, "secret/default-minio-tenant-env-configuration", ""),
        "kubectl get clustersecretstores.external-secrets.io openbao-secret-store -o json": (0, json.dumps({"status": {"conditions": [{"type": "Ready", "status": "True"}]}}), ""),
        "kubectl get gateway https -n kgateway-system -o json": (0, json.dumps({"spec": {"listeners": [{"name": "l1"}]}}), ""),
        "kubectl get crd aimartifacts.aim.eai.amd.com": (0, "", ""),
        "kubectl auth can-i create aimartifacts.aim.eai.amd.com -n e2e-apiserver-testing": (0, "yes", ""),
        "kubectl get clusterrole e2e-aim-test-author -o json": (0, json.dumps({"rules": _E2E_RULES_COMPLETE}), ""),
        "kubectl get clusterrolebinding e2e-aim-test-author -o json": (0, json.dumps({
            "roleRef": {"kind": "ClusterRole", "name": "e2e-aim-test-author"},
            "subjects": [{"kind": "User", "name": "oidc:devuser@example.com"}],
        }), ""),
        "kubectl get namespaces -l airm.silogen.ai/project-id -o json": (0, _jsonlist([{"metadata": {"name": "proj-a"}}]), ""),
        "kubectl get clusterqueues.kueue.x-k8s.io -o json": (0, _jsonlist([
            {"metadata": {"name": "proj-a"}, "status": {"conditions": [{"type": "Active", "status": "True"}]}},
            {"spec": {"resourceGroups": [{"flavors": [{"resources": [{"name": "amd.com/gpu", "nominalQuota": "8"}]}]}]}},
        ]), ""),
        "kubectl get deploy aiwb-ui -n aiwb -o json": (0, json.dumps({
            "status": {"conditions": [{"type": "Available", "status": "True"}], "readyReplicas": 1},
            "spec": {"template": {"spec": {"containers": [{"env": [{"name": "AI_GATEWAY_URL", "value": "https://ai.example.com"}]}]}}},
        }), ""),
        "kubectl get pods -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "aiwb-api-x"}, "status": {"phase": "Running", "containerStatuses": [{"name": "aiwb", "ready": True, "restartCount": 0, "state": {"running": {}}}]}}]), ""),
        "kubectl get pods -n airm -o json": (0, _jsonlist([{"metadata": {"name": "airm-api-x"}, "status": {"phase": "Running", "containerStatuses": [{"name": "airm", "ready": True, "restartCount": 0, "state": {"running": {}}}]}}]), ""),
        "kubectl get deploy aiwb-api -n aiwb -o json": (0, json.dumps({"status": {"conditions": [{"type": "Available", "status": "True"}], "readyReplicas": 1}}), ""),
        "kubectl get localqueues.kueue.x-k8s.io -n e2e-apiserver-testing -o json": (0, _jsonlist([{"metadata": {"name": "default"}, "spec": {"clusterQueue": "project-queue"}}]), ""),
        "kubectl get clusterqueues.kueue.x-k8s.io project-queue -o json": (0, json.dumps({"metadata": {"name": "project-queue"}, "spec": {"resourceGroups": [{"flavors": [{"resources": [{"name": "amd.com/gpu", "nominalQuota": "8"}]}]}]}}), ""),
    }


class ProbeTest(unittest.TestCase):
    def _run(self, overrides: dict[str, tuple[int, str, str]] | None = None,
             argv: list[str] | None = None,
             which: Callable[[str], str | None] | None = None,
             http: dict[str, tuple[int | None, str]] | None = None) -> tuple[int, dict[str, Any]]:
        table = _baseline()
        table.update(overrides or {})
        # Longest key first so a specific override wins over a generic prefix.
        keys = sorted(table, key=len, reverse=True)
        # gateway-auth probes over HTTP rather than kubectl, so it is stubbed separately, keyed by
        # the bearer token: a healthy gateway refuses the invalid key with 401.
        http_table: dict[str, tuple[int | None, str]] = {"invalid": (401, "")}
        http_table.update(http or {})

        def fake_http(url: str, bearer: str, timeout: int = 20) -> tuple[int | None, str]:
            key = "invalid" if bearer.startswith("environment-check-invalid-key") else bearer
            if key not in http_table:
                raise AssertionError(f"unhandled gateway probe (add a fixture): {url!r} key={key!r}")
            return http_table[key]

        def fake_run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
            joined = " ".join(cmd)
            for k in keys:
                if k in joined:
                    return table[k]
            # Fail fast on an unmodelled kubectl/tool call rather than returning a bland success —
            # a silent (0,"","") default is exactly how a new/changed invocation could slip through
            # and let a check report a false "all green". A test must add the fixture explicitly.
            raise AssertionError(f"unhandled command in stub (add a fixture): {joined!r}")

        orig_run, orig_which, orig_http = ec.run, ec.shutil.which, ec._http_status
        ec.run = fake_run
        ec.shutil.which = which or (lambda _name: None)
        ec._http_status = fake_http
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                # Append --json so it routes to the subparser for `image-exists ...` and to the
                # top-level parser for a full run — matching how a caller actually passes it.
                code = ec.main([*(argv or []), "--json"])
            payload = json.loads(out.getvalue())
        finally:
            ec.run = orig_run
            ec.shutil.which = orig_which
            ec._http_status = orig_http
        return code, payload

    def _status_of(self, payload: dict[str, Any], name: str) -> str:
        for c in payload["checks"]:
            if c["name"] == name:
                return c["status"]
        self.fail(f"check {name!r} not present in {[c['name'] for c in payload['checks']]}")

    # ---- overall / connectivity ----
    def test_healthy_cluster_is_ok(self) -> None:
        # Every signal is positively confirmed — including GPU series present in the metrics backend
        # and the storage controller/node-plugin live — so the run reaches HEALTHY.
        code, p = self._run()
        self.assertEqual(p["overall"], "ok", p)
        self.assertEqual(code, 0)
        self.assertTrue(all(c["status"] == "ok" for c in p["checks"]), p)

    def test_unreachable_cluster_is_unreachable_not_healthy(self) -> None:
        code, p = self._run({"kubectl cluster-info": (1, "", "connection refused")})
        self.assertEqual(p["overall"], "unreachable")
        self.assertEqual(code, 2)
        self.assertNotEqual(p["overall"], "ok")

    # ---- cilium ----
    def test_cilium_autodetect_is_inconclusive_not_false_ok(self) -> None:
        # Effective per-node MTU is not exposed by the Kubernetes API. With auto-detect enabled,
        # divergence cannot be excluded, so the check must not certify the cluster healthy.
        code, p = self._run({"kubectl get configmap cilium-config -n kube-system -o json": (0, json.dumps({"data": {}}), "")})
        self.assertEqual(self._status_of(p, "cilium-mtu"), "inconclusive")
        self.assertNotEqual(p["overall"], "ok")
        self.assertEqual(code, 3)

    def test_non_cilium_cluster_is_not_applicable_and_ok(self) -> None:
        _, p = self._run({"kubectl get crd ciliumnodes.cilium.io": (1, "", "not found")})
        self.assertEqual(self._status_of(p, "cilium-mtu"), "ok")

    def test_missing_kubectl_binary_is_not_treated_as_crd_absent(self) -> None:
        # run()'s "not found: kubectl" sentinel (missing binary) must NOT read as an absent CRD and
        # send cilium down the "not applicable / OK" path — it is unreadable/inconclusive.
        self.assertFalse(ec._is_not_found("not found: kubectl"))
        _, p = self._run({"kubectl get crd ciliumnodes.cilium.io": (127, "", "not found: kubectl")})
        self.assertEqual(self._status_of(p, "cilium-mtu"), "inconclusive")

    def test_unreadable_cilium_crd_is_inconclusive_not_false_ok(self) -> None:
        # A CRD read that fails for a non-not-found reason (RBAC/timeout) must NOT be reported as
        # "not applicable / OK": a failed read is never a confirmed absence.
        code, p = self._run({"kubectl get crd ciliumnodes.cilium.io": (1, "", "Error from server (Forbidden): crds is forbidden")})
        self.assertEqual(self._status_of(p, "cilium-mtu"), "inconclusive")
        self.assertNotEqual(p["overall"], "ok")

    def test_cilium_pinned_is_ok(self) -> None:
        _, p = self._run()
        self.assertEqual(self._status_of(p, "cilium-mtu"), "ok")

    # ---- storage ----
    def test_unhealthy_longhorn_is_problem(self) -> None:
        code, p = self._run({"kubectl get volumes.longhorn.io -A -o json": (0, _jsonlist([{"metadata": {"name": "v-a"}, "status": {"robustness": "faulted", "state": "detached"}}]), "")})
        self.assertEqual(self._status_of(p, "longhorn-health"), "warn")
        self.assertEqual(code, 1)

    def test_blank_robustness_longhorn_still_flagged(self) -> None:
        _, p = self._run({"kubectl get volumes.longhorn.io -A -o json": (0, _jsonlist([{"metadata": {"name": "v-b"}, "status": {"robustness": "", "state": "attached"}}]), "")})
        self.assertEqual(self._status_of(p, "longhorn-health"), "warn")

    def test_unreadable_storageclass_is_inconclusive(self) -> None:
        _, p = self._run({"kubectl get storageclass -o json": (1, "", "forbidden")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "inconclusive")

    def test_storageclass_provisioner_not_registered_is_problem(self) -> None:
        # A StorageClass whose CSI provisioner is not a registered CSIDriver must WARN even if an
        # unrelated CSI pod is Ready (the false-pass this correlation closes).
        _, p = self._run({"kubectl get storageclass -o json": (0, _jsonlist([{"metadata": {"name": "sc-x"}, "provisioner": "absent.csi.driver"}]), "")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "storage-provisioner")
        self.assertIn("absent.csi.driver", verdict)

    def test_csidrivers_unreadable_is_inconclusive(self) -> None:
        _, p = self._run({"kubectl get csidrivers.storage.k8s.io -o json": (1, "", "Error from server (Forbidden)")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "inconclusive")

    def test_provisioner_node_plugin_not_registered_is_problem(self) -> None:
        # The provisioner is a registered CSIDriver but its node plugin is on no CSINode (not live);
        # an unrelated Ready CSI pod must not cover for it.
        _, p = self._run({"kubectl get csinodes.storage.k8s.io -o json": (0, _jsonlist([{"metadata": {"name": "node-0"}, "spec": {"drivers": [{"name": "some.other.driver"}]}}]), "")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "storage-provisioner")
        self.assertIn("node plugin", verdict)

    def test_csinodes_unreadable_is_inconclusive(self) -> None:
        _, p = self._run({"kubectl get csinodes.storage.k8s.io -o json": (1, "", "Error from server (Forbidden)")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "inconclusive")

    def test_unrelated_ready_csi_pod_does_not_false_pass(self) -> None:
        # A registered driver whose node plugin is NOT on any node, with only an unrelated Ready CSI
        # pod present, must not return OK — liveness must come from the StorageClass's own driver.
        _, p = self._run({
            "kubectl get storageclass -o json": (0, _jsonlist([{"metadata": {"name": "sc-x"}, "provisioner": "driver.longhorn.io"}]), ""),
            "kubectl get csidrivers.storage.k8s.io -o json": (0, _jsonlist([{"metadata": {"name": "driver.longhorn.io"}}]), ""),
            "kubectl get csinodes.storage.k8s.io -o json": (0, _jsonlist([{"metadata": {"name": "node-0"}, "spec": {"drivers": [{"name": "unrelated.csi.driver"}]}}]), ""),
        })
        self.assertEqual(self._status_of(p, "storage-provisioner"), "warn")

    def test_provisioner_controller_lease_stale_is_problem(self) -> None:
        # Node plugin registered, but the controller's leader lease has not been renewed (not live)
        # -> CreateVolume won't run -> WARN.
        _, p = self._run({"kubectl get leases.coordination.k8s.io -A -o json": (0, _jsonlist([{"metadata": {"name": "external-provisioner-leader-csi-example-com", "namespace": "kube-system"}, "spec": {"renewTime": _ts_ago(3600)}}]), "")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "storage-provisioner")
        self.assertIn("controller", verdict)

    def test_provisioner_controller_no_lease_is_inconclusive(self) -> None:
        # No leader lease for the provisioner -> controller liveness cannot be established -> not OK.
        _, p = self._run({"kubectl get leases.coordination.k8s.io -A -o json": (0, _jsonlist([{"metadata": {"name": "unrelated-lease", "namespace": "kube-system"}, "spec": {"renewTime": _ts_ago(5)}}]), "")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "inconclusive")

    def test_provisioner_leases_unreadable_is_inconclusive(self) -> None:
        _, p = self._run({"kubectl get leases.coordination.k8s.io -A -o json": (1, "", "Error from server (Forbidden)")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "inconclusive")

    def test_other_sidecar_lease_not_mistaken_for_provisioner(self) -> None:
        # Only the external-attacher/resizer leases are fresh (no external-provisioner lease). A
        # fresh attacher lease must NOT vouch that the CreateVolume controller is live -> not OK.
        _, p = self._run({"kubectl get leases.coordination.k8s.io -A -o json": (0, _jsonlist([
            {"metadata": {"name": "external-attacher-leader-csi-example-com", "namespace": "kube-system"}, "spec": {"renewTime": _ts_ago(5)}},
            {"metadata": {"name": "external-resizer-csi-example-com", "namespace": "kube-system"}, "spec": {"renewTime": _ts_ago(5)}},
        ]), "")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "inconclusive")

    def test_bare_driver_name_provisioner_lease_is_accepted(self) -> None:
        # Some drivers (e.g. Longhorn) name the external-provisioner lease with the bare driver name.
        _, p = self._run({"kubectl get leases.coordination.k8s.io -A -o json": (0, _jsonlist([
            {"metadata": {"name": "external-attacher-leader-csi-example-com", "namespace": "kube-system"}, "spec": {"renewTime": _ts_ago(5)}},
            {"metadata": {"name": "csi-example-com", "namespace": "kube-system"}, "spec": {"renewTime": _ts_ago(5)}},
        ]), "")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "ok")

    def test_duplicate_lease_names_across_namespaces_do_not_mask_liveness(self) -> None:
        # Leases are namespaced: a stale same-named lease in another namespace must not overwrite
        # the fresh provisioner lease and make the controller look dead.
        _, p = self._run({"kubectl get leases.coordination.k8s.io -A -o json": (0, _jsonlist([
            {"metadata": {"name": "external-provisioner-leader-csi-example-com", "namespace": "other-ns"}, "spec": {"renewTime": _ts_ago(9999)}},
            {"metadata": {"name": "external-provisioner-leader-csi-example-com", "namespace": "kube-system"}, "spec": {"renewTime": _ts_ago(5)}},
        ]), "")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "ok")

    def test_non_csi_provisioner_not_flagged(self) -> None:
        # An in-tree / non-CSI provisioner has no CSIDriver object and must not be flagged unbacked.
        _, p = self._run({"kubectl get storageclass -o json": (0, _jsonlist([{"metadata": {"name": "local"}, "provisioner": "kubernetes.io/no-provisioner"}]), "")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "ok")

    def test_stuck_pod_is_surfaced(self) -> None:
        # A Pending pod counts only with storage evidence: a scheduling condition pointing at a PVC.
        _, p = self._run({"kubectl get pods -A --field-selector=status.phase=Pending -o json": (0, _jsonlist([{"metadata": {"namespace": "proj", "name": "train-0"}, "status": {"conditions": [{"type": "PodScheduled", "status": "False", "message": "pod has unbound immediate PersistentVolumeClaims"}]}}]), "")})
        self.assertEqual(self._status_of(p, "stuck-storage-pods"), "warn")

    def test_pending_pod_without_storage_evidence_not_flagged(self) -> None:
        # A pod Pending for a non-storage reason (insufficient CPU) is not a storage problem.
        _, p = self._run({"kubectl get pods -A --field-selector=status.phase=Pending -o json": (0, _jsonlist([{"metadata": {"namespace": "proj", "name": "train-0"}, "status": {"conditions": [{"type": "PodScheduled", "status": "False", "message": "0/3 nodes are available: 3 Insufficient cpu"}]}}]), "")})
        self.assertEqual(self._status_of(p, "stuck-storage-pods"), "ok")

    def test_failed_mount_event_is_storage_evidence(self) -> None:
        _, p = self._run({"kubectl get events -A --field-selector reason=FailedMount -o json": (0, _jsonlist([{"involvedObject": {"namespace": "proj", "name": "train-0"}}]), "")})
        self.assertEqual(self._status_of(p, "stuck-storage-pods"), "warn")

    def test_deadline_exceeded_job_is_model_download_evidence(self) -> None:
        _, p = self._run({"kubectl get jobs -A -o json": (0, _jsonlist([{
            "metadata": {"namespace": "proj", "name": "model-download"},
            "status": {"conditions": [{"type": "Failed", "status": "True", "reason": "DeadlineExceeded"}]},
        }]), "")})
        self.assertEqual(self._status_of(p, "stuck-storage-pods"), "warn")
        result = next(c for c in p["checks"] if c["name"] == "stuck-storage-pods")
        self.assertIn("model-download", result["verdict"])
        self.assertIn("cilium-mtu", result["recommendation"])

    def test_deadline_exceeded_event_is_model_download_evidence(self) -> None:
        _, p = self._run({
            "kubectl get events -A --field-selector reason=DeadlineExceeded -o json": (
                0, _jsonlist([{"involvedObject": {"namespace": "proj", "name": "model-download-abc"}}]), "",
            ),
        })
        self.assertEqual(self._status_of(p, "stuck-storage-pods"), "warn")

    def test_unrelated_deadline_exceeded_job_is_not_flagged(self) -> None:
        # A DeadlineExceeded on an unrelated maintenance Job must not be read as a stalled model
        # download; only work owned by the download path counts.
        _, p = self._run({"kubectl get jobs -A -o json": (0, _jsonlist([{
            "metadata": {"namespace": "maintenance", "name": "database-backup"},
            "status": {"conditions": [{"type": "Failed", "status": "True", "reason": "DeadlineExceeded"}]},
        }]), "")})
        self.assertEqual(self._status_of(p, "stuck-storage-pods"), "ok")

    def test_model_download_job_identified_by_label(self) -> None:
        _, p = self._run({"kubectl get jobs -A -o json": (0, _jsonlist([{
            "metadata": {"namespace": "proj", "name": "job-xyz", "labels": {"app": "model-downloader"}},
            "status": {"conditions": [{"type": "Failed", "status": "True", "reason": "DeadlineExceeded"}]},
        }]), "")})
        self.assertEqual(self._status_of(p, "stuck-storage-pods"), "warn")

    def test_unreadable_jobs_are_inconclusive_not_silent(self) -> None:
        _, p = self._run({"kubectl get jobs -A -o json": (1, "", "Error from server (Forbidden)")})
        self.assertEqual(self._status_of(p, "stuck-storage-pods"), "inconclusive")

    # ---- gpu metrics (anti-silence core) ----
    def test_running_but_failing_exporter_caught(self) -> None:
        _, p = self._run({"kubectl logs -n kube-amd-gpu exp-0 --tail=200": (0, "k8s.go:191 dial tcp 10.243.0.1:443: i/o timeout", "")})
        self.assertEqual(self._status_of(p, "gpu-metrics"), "warn")

    def test_failing_non_first_exporter_pod_caught(self) -> None:
        _, p = self._run({
            "kubectl get pods -A -l app.kubernetes.io/name=device-metrics-exporter -o json": (0, _jsonlist([
                {"metadata": {"namespace": "kube-amd-gpu", "name": "exp-0"}},
                {"metadata": {"namespace": "kube-amd-gpu", "name": "exp-1"}},
            ]), ""),
            "kubectl logs -n kube-amd-gpu exp-1 --tail=200": (0, "dial tcp 10.243.0.1:443: i/o timeout", ""),
        })
        self.assertEqual(self._status_of(p, "gpu-metrics"), "warn")

    def test_unreadable_collector_logs_inconclusive(self) -> None:
        _, p = self._run({"kubectl logs -n otel-lgtm-stack otel-0 --tail=200": (1, "", "forbidden")})
        self.assertEqual(self._status_of(p, "gpu-metrics"), "inconclusive")

    def test_absent_collector_inconclusive(self) -> None:
        _, p = self._run({"kubectl get pods -n otel-lgtm-stack -l app.kubernetes.io/name=otel-collector -o json": (0, _jsonlist([]), "")})
        self.assertEqual(self._status_of(p, "gpu-metrics"), "inconclusive")

    def test_failed_to_watch_signature_reported_verbatim(self) -> None:
        # The verdict must name the matched log signature, not hard-code "i/o timeout".
        _, p = self._run({"kubectl logs -n kube-amd-gpu exp-0 --tail=200": (0, "reflector.go: Failed to watch *v1.Node", "")})
        self.assertEqual(self._status_of(p, "gpu-metrics"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "gpu-metrics")
        self.assertIn("Failed to watch", verdict)

    def test_gpu_metrics_confirmed_via_backend_is_ok(self) -> None:
        # A positive count of current GPU series with non-blank workload_id proves delivery -> OK.
        _, p = self._run()
        self.assertEqual(self._status_of(p, "gpu-metrics"), "ok")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "gpu-metrics")
        self.assertIn("non-blank workload_id", verdict)

    def test_gpu_metrics_empty_backend_series_is_problem(self) -> None:
        # Exporter + collector present, no failure signature, but the backend has no GPU series ->
        # the pipeline is not delivering -> WARN.
        _, p = self._run({"get --raw": (0, json.dumps({"status": "success", "data": {"resultType": "vector", "result": []}}), "")})
        self.assertEqual(self._status_of(p, "gpu-metrics"), "warn")

    def test_gpu_metrics_zero_count_vector_is_problem(self) -> None:
        # A vector whose count value is "0" must NOT pass — no series with a non-blank workload_id.
        _, p = self._run({"get --raw": (0, json.dumps({"status": "success", "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1735000000, "0"]}]}}), "")})
        self.assertEqual(self._status_of(p, "gpu-metrics"), "warn")

    def test_gpu_metrics_scalar_zero_is_problem(self) -> None:
        # A Prometheus scalar zero must NOT pass while a GPU workload is active.
        _, p = self._run({"get --raw": (0, json.dumps({"status": "success", "data": {"resultType": "scalar", "result": [1735000000, "0"]}}), "")})
        self.assertEqual(self._status_of(p, "gpu-metrics"), "warn")

    def test_gpu_metrics_zero_series_on_idle_cluster_is_ok(self) -> None:
        _, p = self._run({
            "get --raw": (0, json.dumps({"status": "success", "data": {"resultType": "vector", "result": []}}), ""),
            "kubectl get pods -A --field-selector=status.phase=Running -o json": (0, _jsonlist([]), ""),
        })
        self.assertEqual(self._status_of(p, "gpu-metrics"), "ok")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "gpu-metrics")
        self.assertIn("no active GPU workload", verdict)

    def test_gpu_metrics_zero_series_with_unreadable_workloads_is_inconclusive(self) -> None:
        _, p = self._run({
            "get --raw": (0, json.dumps({"status": "success", "data": {"resultType": "vector", "result": []}}), ""),
            "kubectl get pods -A --field-selector=status.phase=Running -o json": (1, "", "forbidden"),
        })
        self.assertEqual(self._status_of(p, "gpu-metrics"), "inconclusive")

    def test_gpu_metrics_backend_undiscoverable_is_inconclusive(self) -> None:
        # No backend service and none configured -> cannot positively confirm -> INCONCLUSIVE.
        _, p = self._run({"kubectl get svc -A -o json": (0, _jsonlist([]), "")})
        self.assertEqual(self._status_of(p, "gpu-metrics"), "inconclusive")

    def test_gpu_metrics_backend_query_error_is_inconclusive(self) -> None:
        _, p = self._run({"get --raw": (1, "", "error")})
        self.assertEqual(self._status_of(p, "gpu-metrics"), "inconclusive")

    def test_metrics_backend_flag_used(self) -> None:
        # --metrics-backend overrides discovery; the check queries the given target.
        _, p = self._run(argv=["--metrics-backend", "mon/prom:9090"])
        self.assertEqual(self._status_of(p, "gpu-metrics"), "ok")

    def test_otel_scrape_failure_is_problem(self) -> None:
        _, p = self._run({"kubectl logs -n otel-lgtm-stack otel-0 --tail=200": (0, "Failed to scrape Prometheus endpoint", "")})
        self.assertEqual(self._status_of(p, "gpu-metrics"), "warn")

    def test_absent_exporter_inconclusive_not_silent_pass(self) -> None:
        _, p = self._run({"kubectl get pods -A -l app.kubernetes.io/name=device-metrics-exporter -o json": (0, _jsonlist([]), "")})
        self.assertEqual(self._status_of(p, "gpu-metrics"), "inconclusive")

    # ---- aim profiles ----
    def test_no_supported_profile_is_problem_and_names_gpu(self) -> None:
        _, p = self._run({"kubectl get aimclustermodels.aim.eai.amd.com -A -o json": (0, _jsonlist([{"metadata": {"name": "aim-epyc-llama"}, "status": {"conditions": [{"type": "ManagedProfilesReady", "status": "False", "reason": "NoSupportedProfiles"}]}}]), "")})
        self.assertEqual(self._status_of(p, "aim-profiles"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "aim-profiles")
        self.assertIn("7551", verdict)

    def test_missing_managed_profiles_condition_is_inconclusive_not_false_ok(self) -> None:
        _, p = self._run({"kubectl get aimclustermodels.aim.eai.amd.com -A -o json": (0, _jsonlist([{"metadata": {"name": "unreconciled-model"}, "status": {"conditions": []}}]), "")})
        self.assertEqual(self._status_of(p, "aim-profiles"), "inconclusive")

    def test_managed_profiles_false_other_reason_is_inconclusive_not_false_ok(self) -> None:
        _, p = self._run({"kubectl get aimclustermodels.aim.eai.amd.com -A -o json": (0, _jsonlist([{"metadata": {"name": "pending-model"}, "status": {"conditions": [{"type": "ManagedProfilesReady", "status": "False", "reason": "Reconciling"}]}}]), "")})
        self.assertEqual(self._status_of(p, "aim-profiles"), "inconclusive")

    def test_every_model_affirmatively_ready_is_ok(self) -> None:
        _, p = self._run()
        self.assertEqual(self._status_of(p, "aim-profiles"), "ok")

    def test_malformed_model_status_does_not_crash_the_run(self) -> None:
        # status:null / conditions:null / non-dict condition must not raise and abort the whole run
        # (that would break the --json contract). They resolve to inconclusive, not a crash.
        _, p = self._run({"kubectl get aimclustermodels.aim.eai.amd.com -A -o json": (0, _jsonlist([
            {"metadata": {"name": "null-status"}, "status": None},
            {"metadata": {"name": "null-conditions"}, "status": {"conditions": None}},
            {"metadata": {"name": "bad-condition"}, "status": {"conditions": ["not-a-dict"]}},
        ]), "")})
        self.assertEqual(self._status_of(p, "aim-profiles"), "inconclusive")

    # ---- required secrets ----
    def test_unsynced_externalsecret_is_problem(self) -> None:
        _, p = self._run({"kubectl get externalsecret -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "aiwb-openbao-token"}, "status": {"conditions": [{"type": "Ready", "status": "False", "reason": "SecretSyncedError"}]}}]), "")})
        self.assertEqual(self._status_of(p, "required-secrets"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "required-secrets")
        self.assertIn("SecretSyncedError", verdict)

    def test_no_externalsecrets_is_inconclusive_not_ok(self) -> None:
        _, p = self._run({"kubectl get externalsecret -n aiwb -o json": (0, _jsonlist([]), "")})
        self.assertEqual(self._status_of(p, "required-secrets"), "inconclusive")

    def test_unsynced_secret_reports_ready_condition_reason(self) -> None:
        # The reported reason must come from the Ready-type condition, not the first condition,
        # even when an unrelated condition precedes it.
        _, p = self._run({"kubectl get externalsecret -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "aiwb-openbao-token"}, "status": {"conditions": [
            {"type": "Deleting", "status": "False", "reason": "NotDeleting"},
            {"type": "Ready", "status": "False", "reason": "SecretSyncedError"},
        ]}}]), "")})
        self.assertEqual(self._status_of(p, "required-secrets"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "required-secrets")
        self.assertIn("SecretSyncedError", verdict)
        self.assertNotIn("NotDeleting", verdict)

    # ---- minio ----
    def test_minio_namespace_absent_is_problem(self) -> None:
        _, p = self._run({
            "kubectl get secret default-minio-tenant-env-configuration -n minio-tenant-default -o name": (1, "", "not found"),
            "kubectl get ns minio-tenant-default": (1, "", 'namespaces "minio-tenant-default" not found'),
        })
        self.assertEqual(self._status_of(p, "minio-ready"), "warn")

    def test_minio_read_error_is_inconclusive_not_problem(self) -> None:
        # Secret read forbidden but the namespace is readable: the secret was never actually read,
        # so "missing" cannot be asserted — must be inconclusive, not a false WARN.
        _, p = self._run({
            "kubectl get secret default-minio-tenant-env-configuration -n minio-tenant-default -o name": (1, "", "Error from server (Forbidden): secrets is forbidden"),
            "kubectl get ns minio-tenant-default": (0, "minio-tenant-default", ""),
        })
        self.assertEqual(self._status_of(p, "minio-ready"), "inconclusive")

    def test_minio_ns_read_error_is_inconclusive(self) -> None:
        _, p = self._run({
            "kubectl get secret default-minio-tenant-env-configuration -n minio-tenant-default -o name": (1, "", "not found"),
            "kubectl get ns minio-tenant-default": (1, "", "Error from server (Forbidden): namespaces is forbidden"),
        })
        self.assertEqual(self._status_of(p, "minio-ready"), "inconclusive")

    def test_aiwb_openbao_store_not_ready_is_problem(self) -> None:
        # minio-credentials is minted per-project at test time from openbao-secret-store,
        # so the pre-run signal is that the store is Ready (not a pre-existing per-ns secret).
        _, p = self._run({"kubectl get clustersecretstores.external-secrets.io openbao-secret-store -o json": (0, json.dumps({"status": {"conditions": [{"type": "Ready", "status": "False"}]}}), "")})
        self.assertEqual(self._status_of(p, "minio-ready"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "minio-ready")
        self.assertIn("openbao-secret-store", verdict)

    def test_aiwb_openbao_store_absent_is_problem(self) -> None:
        _, p = self._run({"kubectl get clustersecretstores.external-secrets.io openbao-secret-store -o json": (1, "", 'clustersecretstores.external-secrets.io "openbao-secret-store" not found')})
        self.assertEqual(self._status_of(p, "minio-ready"), "warn")

    def test_aiwb_openbao_store_unreadable_is_inconclusive(self) -> None:
        _, p = self._run({"kubectl get clustersecretstores.external-secrets.io openbao-secret-store -o json": (1, "", "Error from server (Forbidden)")})
        self.assertEqual(self._status_of(p, "minio-ready"), "inconclusive")

    # ---- aimartifact rbac ----
    def test_aimartifact_cannot_create_is_problem(self) -> None:
        _, p = self._run({"kubectl auth can-i create aimartifacts.aim.eai.amd.com -n e2e-apiserver-testing": (1, "no", "")})
        self.assertEqual(self._status_of(p, "aimartifact-rbac"), "warn")

    def test_aimartifact_can_create_is_ok(self) -> None:
        _, p = self._run()
        self.assertEqual(self._status_of(p, "aimartifact-rbac"), "ok")

    def test_aimartifact_crd_absent_is_inconclusive(self) -> None:
        _, p = self._run({"kubectl get crd aimartifacts.aim.eai.amd.com": (1, "", "not found")})
        self.assertEqual(self._status_of(p, "aimartifact-rbac"), "inconclusive")

    def test_aimartifact_unevaluable_is_inconclusive(self) -> None:
        # A can-i that errors without a yes/no answer must be inconclusive, not a silent pass.
        _, p = self._run({"kubectl auth can-i create aimartifacts.aim.eai.amd.com -n e2e-apiserver-testing": (1, "", "error: unable to evaluate")})
        self.assertEqual(self._status_of(p, "aimartifact-rbac"), "inconclusive")

    def test_aimartifact_respects_test_namespace(self) -> None:
        _, p = self._run(
            {
                "kubectl auth can-i create aimartifacts.aim.eai.amd.com -n custom-ns": (1, "no", ""),
                "kubectl get localqueues.kueue.x-k8s.io -n custom-ns -o json": (0, _jsonlist([{"spec": {"clusterQueue": "project-queue"}}]), ""),
            },
            argv=["--test-namespace", "custom-ns"],
        )
        self.assertEqual(self._status_of(p, "aimartifact-rbac"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "aimartifact-rbac")
        self.assertIn("custom-ns", verdict)

    # ---- eai-e2e-rbac ----
    def test_e2e_rbac_complete_is_ok(self) -> None:
        _, p = self._run()
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "ok")

    def test_e2e_rbac_missing_collection_list_is_problem(self) -> None:
        # The custom-model precision rounds read both collections back with kubectl to confirm the
        # project is empty before the next round. A role carrying only get reads one named object,
        # so the suite would 403 mid-run on a cluster this check would otherwise call healthy.
        rules = [
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimartifacts"], "verbs": ["get", "create", "patch"]},
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimprofiles"], "verbs": ["get", "list"]},
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimmodels"], "verbs": ["get", "create", "patch", "delete"]},
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimmodels/status"], "verbs": ["get", "patch"]},
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimservices"], "verbs": ["get", "create", "patch", "delete"]},
        ]
        _, p = self._run({"kubectl get clusterrole e2e-aim-test-author -o json": (0, json.dumps({"rules": rules}), "")})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "eai-e2e-rbac")
        self.assertIn("aimmodels missing list", verdict)
        self.assertIn("aimservices missing list", verdict)

    def test_e2e_rbac_role_absent_is_problem(self) -> None:
        # The ~20-failure night: the ClusterRole was simply not applied to the release.
        _, p = self._run({"kubectl get clusterrole e2e-aim-test-author -o json": (1, "", 'clusterroles.rbac.authorization.k8s.io "e2e-aim-test-author" not found')})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "warn")

    def test_e2e_rbac_role_unreadable_is_inconclusive(self) -> None:
        # A forbidden/API error is not proof the role is missing.
        _, p = self._run({"kubectl get clusterrole e2e-aim-test-author -o json": (1, "", "forbidden")})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "inconclusive")

    def test_e2e_rbac_missing_status_subresource_verb_is_problem(self) -> None:
        # aimmodels/status patch is what stages a Ready model for fine-tuning cases; granting
        # aimmodels alone does NOT cover the subresource, and the suite fails mid-run.
        rules = [r for r in _E2E_RULES_COMPLETE if r["resources"] != ["aimmodels/status"]]
        _, p = self._run({"kubectl get clusterrole e2e-aim-test-author -o json": (0, json.dumps({"rules": rules}), "")})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "eai-e2e-rbac")
        self.assertIn("aimmodels/status", verdict)

    def test_e2e_rbac_partial_verbs_is_problem(self) -> None:
        # A role that can create but not delete leaves the UI copy suite failing at cleanup.
        rules = [
            dict(r, verbs=["get", "create"]) if r["resources"] == ["aimmodels"] else r
            for r in _E2E_RULES_COMPLETE
        ]
        _, p = self._run({"kubectl get clusterrole e2e-aim-test-author -o json": (0, json.dumps({"rules": rules}), "")})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "eai-e2e-rbac")
        self.assertIn("delete", verdict)

    def test_e2e_rbac_missing_aimservices_is_problem(self) -> None:
        # The adapter/custom-model/adapter-serving suites author AIMService CRs as the test identity;
        # granting only the other resources gives a green check while those suites still 403 mid-run.
        rules = [r for r in _E2E_RULES_COMPLETE if r["resources"] != ["aimservices"]]
        _, p = self._run({"kubectl get clusterrole e2e-aim-test-author -o json": (0, json.dumps({"rules": rules}), "")})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "eai-e2e-rbac")
        self.assertIn("aimservices", verdict)

    def test_e2e_rbac_wildcard_rule_is_accepted(self) -> None:
        # A cluster granting the group wholesale satisfies every required verb; flagging it would
        # be a false positive.
        rules = [{"apiGroups": ["*"], "resources": ["*"], "verbs": ["*"]}]
        _, p = self._run({"kubectl get clusterrole e2e-aim-test-author -o json": (0, json.dumps({"rules": rules}), "")})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "ok")

    def test_e2e_rbac_star_subresource_wildcard_covers_status(self) -> None:
        # The real RBAC subresource wildcard is "*/status" (grants that subresource on all
        # resources), which the Kubernetes authorizer honours; it satisfies aimmodels/status.
        rules = [
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimartifacts"], "verbs": ["get", "create", "patch"]},
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimprofiles"], "verbs": ["get", "list"]},
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimmodels"], "verbs": ["get", "list", "create", "patch", "delete"]},
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["*/status"], "verbs": ["get", "patch"]},
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimservices"], "verbs": ["get", "list", "create", "patch", "delete"]},
        ]
        _, p = self._run({"kubectl get clusterrole e2e-aim-test-author -o json": (0, json.dumps({"rules": rules}), "")})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "ok")

    def test_e2e_rbac_parent_slash_star_does_not_cover_status(self) -> None:
        # "aimmodels/*" is NOT a real RBAC form — the API server would deny aimmodels/status — so the
        # check must NOT treat it as covering the subresource (else a false pass on the headline bug).
        rules = [
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimartifacts"], "verbs": ["get", "create", "patch"]},
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimprofiles"], "verbs": ["get", "list"]},
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimmodels", "aimmodels/*"], "verbs": ["get", "list", "create", "patch", "delete"]},
            {"apiGroups": ["aim.eai.amd.com"], "resources": ["aimservices"], "verbs": ["get", "list", "create", "patch", "delete"]},
        ]
        _, p = self._run({"kubectl get clusterrole e2e-aim-test-author -o json": (0, json.dumps({"rules": rules}), "")})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "eai-e2e-rbac")
        self.assertIn("aimmodels/status", verdict)

    def test_e2e_rbac_binding_absent_is_problem(self) -> None:
        # A complete role that is bound to nobody grants nothing.
        _, p = self._run({"kubectl get clusterrolebinding e2e-aim-test-author -o json": (1, "", "not found")})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "warn")

    def test_e2e_rbac_binding_readable_but_errored_is_inconclusive(self) -> None:
        # Role is complete, but the binding read fails for a non-not-found reason (Forbidden/API
        # error): the identity is unconfirmed, so INCONCLUSIVE — never a silent pass.
        _, p = self._run({"kubectl get clusterrolebinding e2e-aim-test-author -o json": (1, "", "Error from server (Forbidden)")})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "inconclusive")

    def test_e2e_rbac_binding_without_oidc_user_is_problem(self) -> None:
        # Bound only to a ServiceAccount, the human OIDC test identity still gets nothing. The
        # message must name the actual subject, not render "(subjects: none)".
        _, p = self._run({"kubectl get clusterrolebinding e2e-aim-test-author -o json": (0, json.dumps({
            "roleRef": {"kind": "ClusterRole", "name": "e2e-aim-test-author"},
            "subjects": [{"kind": "ServiceAccount", "name": "runner", "namespace": "e2e"}],
        }), "")})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "eai-e2e-rbac")
        self.assertIn("ServiceAccount/runner", verdict)
        self.assertNotIn("subjects: none", verdict)

    def test_e2e_rbac_binding_to_wrong_role_is_problem(self) -> None:
        _, p = self._run({"kubectl get clusterrolebinding e2e-aim-test-author -o json": (0, json.dumps({
            "roleRef": {"kind": "ClusterRole", "name": "some-other-role"},
            "subjects": [{"kind": "User", "name": "oidc:devuser@example.com"}],
        }), "")})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "warn")

    def test_e2e_rbac_name_restricted_rule_does_not_cover_dynamic_objects(self) -> None:
        # A resourceNames-restricted rule grants only named objects; the suites create arbitrary
        # AIM objects, so it must not count — else the check is OK while the suite 403s.
        rules = [dict(r, resourceNames=["one-fixed-name"]) for r in _E2E_RULES_COMPLETE]
        _, p = self._run({"kubectl get clusterrole e2e-aim-test-author -o json": (0, json.dumps({"rules": rules}), "")})
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "warn")

    def test_e2e_rbac_expected_oidc_user_matched_is_ok(self) -> None:
        _, p = self._run(argv=["--e2e-oidc-user", "devuser@example.com"])
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "ok")

    def test_e2e_rbac_expected_oidc_user_mismatch_is_problem(self) -> None:
        # A complete binding to a DIFFERENT OIDC user would otherwise pass while the real runner 403s.
        _, p = self._run(argv=["--e2e-oidc-user", "someone-else@example.com"])
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "eai-e2e-rbac")
        self.assertIn("someone-else@example.com", verdict)

    def test_e2e_rbac_expected_oidc_user_legacy_prefix_matched_is_ok(self) -> None:
        # The chart also binds the legacy no-colon 'oidc<user>' form; either satisfies the match.
        _, p = self._run(
            {"kubectl get clusterrolebinding e2e-aim-test-author -o json": (0, json.dumps({
                "roleRef": {"kind": "ClusterRole", "name": "e2e-aim-test-author"},
                "subjects": [{"kind": "User", "name": "oidcdevuser@example.com"}],
            }), "")},
            argv=["--e2e-oidc-user", "devuser@example.com"],
        )
        self.assertEqual(self._status_of(p, "eai-e2e-rbac"), "ok")

    # ---- airm-quota-health ----
    def test_airm_projects_healthy_is_ok(self) -> None:
        _, p = self._run()
        self.assertEqual(self._status_of(p, "airm-quota-health"), "ok")

    def test_airm_no_projects_is_ok(self) -> None:
        _, p = self._run({"kubectl get namespaces -l airm.silogen.ai/project-id -o json": (0, _jsonlist([]), "")})
        self.assertEqual(self._status_of(p, "airm-quota-health"), "ok")

    def test_airm_project_stuck_terminating_is_problem(self) -> None:
        # The finalizer-race signature: deletion started but an AIRM finalizer still holds it.
        _, p = self._run({"kubectl get namespaces -l airm.silogen.ai/project-id -o json": (0, _jsonlist([
            {"metadata": {"name": "proj-a", "deletionTimestamp": _ts_ago(600),
                          "finalizers": ["airm.silogen.ai/namespace-finalizer"]}},
        ]), "")})
        self.assertEqual(self._status_of(p, "airm-quota-health"), "warn")

    def test_airm_project_recently_deleting_with_airm_finalizer_is_ok(self) -> None:
        # Holding the finalizer is normal during the five-minute deletion grace.
        _, p = self._run({"kubectl get namespaces -l airm.silogen.ai/project-id -o json": (0, _jsonlist([
            {"metadata": {"name": "proj-a", "deletionTimestamp": _ts_ago(5),
                          "finalizers": ["airm.silogen.ai/namespace-finalizer"]}},
        ]), "")})
        self.assertEqual(self._status_of(p, "airm-quota-health"), "ok")

    def test_airm_project_unparseable_deletion_time_is_inconclusive(self) -> None:
        _, p = self._run({"kubectl get namespaces -l airm.silogen.ai/project-id -o json": (0, _jsonlist([
            {"metadata": {"name": "proj-a", "deletionTimestamp": "not-a-time",
                          "finalizers": ["airm.silogen.ai/namespace-finalizer"]}},
        ]), "")})
        self.assertEqual(self._status_of(p, "airm-quota-health"), "inconclusive")

    def test_airm_project_active_zero_quota_can_borrow_from_cohort(self) -> None:
        # AIRM puts every project queue in the kaiwo cohort with borrowing enabled. Zero local
        # nominalQuota means no guarantee, not no admission; quota-preemption.robot verifies this.
        _, p = self._run({"kubectl get clusterqueues.kueue.x-k8s.io -o json": (0, _jsonlist([
            {"metadata": {"name": "proj-a"}, "spec": {"cohort": "kaiwo", "resourceGroups": [{"flavors": [{"resources": [
                {"name": "cpu", "nominalQuota": "0"}, {"name": "memory", "nominalQuota": "0"},
            ]}]}]}, "status": {"conditions": [{"type": "Active", "status": "True"}]}},
        ]), "")})
        self.assertEqual(self._status_of(p, "airm-quota-health"), "ok")

    def test_airm_stuck_deletion_and_missing_quota_reported_together(self) -> None:
        _, p = self._run({
            "kubectl get namespaces -l airm.silogen.ai/project-id -o json": (0, _jsonlist([
                {"metadata": {"name": "old", "deletionTimestamp": _ts_ago(600), "finalizers": ["airm.silogen.ai/namespace-finalizer"]}},
                {"metadata": {"name": "live"}},
            ]), ""),
            "kubectl get clusterqueues.kueue.x-k8s.io -o json": (0, _jsonlist([]), ""),
        })
        self.assertEqual(self._status_of(p, "airm-quota-health"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "airm-quota-health")
        self.assertIn("old(stuck deleting", verdict)
        self.assertIn("live(no ClusterQueue)", verdict)

    def test_airm_project_deleting_without_airm_finalizer_is_ok(self) -> None:
        # A namespace mid-deletion held only by Kubernetes' own finalizer is deleting normally.
        _, p = self._run({"kubectl get namespaces -l airm.silogen.ai/project-id -o json": (0, _jsonlist([
            {"metadata": {"name": "proj-a", "deletionTimestamp": _ts_ago(5), "finalizers": ["kubernetes"]}},
        ]), "")})
        self.assertEqual(self._status_of(p, "airm-quota-health"), "ok")

    def test_airm_project_without_clusterqueue_is_problem(self) -> None:
        _, p = self._run({"kubectl get clusterqueues.kueue.x-k8s.io -o json": (0, _jsonlist([
            {"spec": {"resourceGroups": [{"flavors": [{"resources": [{"name": "amd.com/gpu", "nominalQuota": "8"}]}]}]}},
        ]), "")})
        self.assertEqual(self._status_of(p, "airm-quota-health"), "warn")

    def test_airm_project_clusterqueue_not_active_is_problem(self) -> None:
        _, p = self._run({"kubectl get clusterqueues.kueue.x-k8s.io -o json": (0, _jsonlist([
            {"metadata": {"name": "proj-a"}, "status": {"conditions": [{"type": "Active", "status": "False"}]}},
        ]), "")})
        self.assertEqual(self._status_of(p, "airm-quota-health"), "warn")

    def test_airm_namespaces_unreadable_is_inconclusive(self) -> None:
        _, p = self._run({"kubectl get namespaces -l airm.silogen.ai/project-id -o json": (1, "", "forbidden")})
        self.assertEqual(self._status_of(p, "airm-quota-health"), "inconclusive")

    def test_airm_kueue_absent_is_inconclusive_not_pass(self) -> None:
        # Projects exist but Kueue is not installed: quota is unconfirmed, never assumed fine.
        # kubectl reports an unregistered type as "doesn't have a resource type", which _is_not_found
        # now recognises so the verdict is the actionable "Kueue absent", not a generic read error.
        _, p = self._run({"kubectl get clusterqueues.kueue.x-k8s.io -o json": (1, "", "error: the server doesn't have a resource type \"clusterqueues\"")})
        self.assertEqual(self._status_of(p, "airm-quota-health"), "inconclusive")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "airm-quota-health")
        self.assertIn("Kueue", verdict)

    # ---- gateway-auth ----
    def test_gateway_refuses_invalid_key_is_ok(self) -> None:
        _, p = self._run()
        self.assertEqual(self._status_of(p, "gateway-auth"), "ok")

    def test_gateway_5xx_on_invalid_key_is_problem(self) -> None:
        # The stale-certificate breakage: the gateway errors instead of making an auth decision.
        _, p = self._run(http={"invalid": (503, "")})
        self.assertEqual(self._status_of(p, "gateway-auth"), "warn")

    def test_gateway_accepting_invalid_key_is_problem(self) -> None:
        # If a garbage key is admitted, key enforcement is not what the tests assume.
        _, p = self._run(http={"invalid": (200, "")})
        self.assertEqual(self._status_of(p, "gateway-auth"), "warn")

    def test_gateway_unreachable_is_inconclusive(self) -> None:
        _, p = self._run(http={"invalid": (None, "connection refused")})
        self.assertEqual(self._status_of(p, "gateway-auth"), "inconclusive")

    def test_gateway_untrusted_certificate_is_inconclusive_naming_the_ambiguity(self) -> None:
        # Observed on a real cluster: curl trusted the gateway (401) where Python did not. A cert
        # this host cannot verify is either a stale gateway cert or a missing local CA — warning
        # would be a false positive, so the verdict must name both possibilities.
        _, p = self._run(http={"invalid": (None, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")})
        self.assertEqual(self._status_of(p, "gateway-auth"), "inconclusive")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "gateway-auth")
        self.assertIn("certificate", verdict)

    def test_gateway_not_configured_is_not_applicable_ok(self) -> None:
        # A readable aiwb-ui with no AI_GATEWAY_URL is a confirmed "no gateway wired" — nothing to
        # probe, so it is OK (not-applicable), the same shape cilium-mtu uses off a non-Cilium cluster.
        _, p = self._run({"kubectl get deploy aiwb-ui -n aiwb -o json": (0, json.dumps(
            {"status": {"conditions": [{"type": "Available", "status": "True"}], "readyReplicas": 1}}), "")})
        self.assertEqual(self._status_of(p, "gateway-auth"), "ok")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "gateway-auth")
        self.assertIn("no inference gateway is configured", verdict)

    def test_gateway_key_supplied_but_no_url_is_inconclusive(self) -> None:
        # Supplying a key means the caller expects a gateway; not finding one cannot validate it.
        _, p = self._run(
            {"kubectl get deploy aiwb-ui -n aiwb -o json": (0, json.dumps(
                {"status": {"conditions": [{"type": "Available", "status": "True"}], "readyReplicas": 1}}), "")},
            argv=["--gateway-key", "real-key"],
        )
        self.assertEqual(self._status_of(p, "gateway-auth"), "inconclusive")

    def test_gateway_valid_key_accepted_is_ok(self) -> None:
        _, p = self._run(argv=["--gateway-key", "real-key"], http={"real-key": (200, "")})
        self.assertEqual(self._status_of(p, "gateway-auth"), "ok")

    def test_gateway_valid_key_short_circuit_203_is_ok(self) -> None:
        # 203 is the ext_authz short-circuit for an authorised models call.
        _, p = self._run(argv=["--gateway-key", "real-key"], http={"real-key": (203, "")})
        self.assertEqual(self._status_of(p, "gateway-auth"), "ok")

    def test_gateway_valid_key_rejected_is_problem(self) -> None:
        _, p = self._run(argv=["--gateway-key", "real-key"], http={"real-key": (401, "")})
        self.assertEqual(self._status_of(p, "gateway-auth"), "warn")

    def test_gateway_non_http_scheme_is_inconclusive_not_crash(self) -> None:
        # A non-http(s) URL (e.g. file://) must be refused, not handed to the opener — otherwise its
        # FileHandler yields a status-less response and int(None) crashes the whole run.
        _, p = self._run(argv=["--gateway-url", "file:///tmp/gw"])
        self.assertEqual(self._status_of(p, "gateway-auth"), "inconclusive")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "gateway-auth")
        self.assertIn("unsupported scheme", verdict)

    def test_gateway_scheme_less_host_port_is_probed_not_rejected(self) -> None:
        # A bare host:port has no scheme (urlparse would misread "host" as one); it must default to
        # https and be probed, not rejected as an unsupported scheme.
        _, p = self._run(argv=["--gateway-url", "gateway.internal:8443"])
        self.assertEqual(self._status_of(p, "gateway-auth"), "ok")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "gateway-auth")
        self.assertIn("gateway.internal:8443", verdict)
        self.assertNotIn("unsupported scheme", verdict)

    def test_gateway_valid_key_5xx_is_problem(self) -> None:
        _, p = self._run(argv=["--gateway-key", "real-key"], http={"real-key": (503, "")})
        self.assertEqual(self._status_of(p, "gateway-auth"), "warn")

    def test_gateway_valid_key_probe_unreachable_is_inconclusive(self) -> None:
        _, p = self._run(argv=["--gateway-key", "real-key"], http={"real-key": (None, "timeout")})
        self.assertEqual(self._status_of(p, "gateway-auth"), "inconclusive")

    def test_gateway_url_flag_overrides_discovery(self) -> None:
        _, p = self._run(argv=["--gateway-url", "https://gw.example.com"])
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "gateway-auth")
        self.assertIn("gw.example.com", verdict)

    # ---- _http_status (the real function, not the stub) ----
    def test_real_http_status_malformed_url_does_not_raise(self) -> None:
        # A URL with a space raises http.client.InvalidURL (an HTTPException, NOT an OSError). The
        # real function must swallow it and return (None, reason) so an odd gateway endpoint can
        # never abort the eager run_all_checks list and destroy the --json contract.
        status, err = ec._http_status("http://gw.example.com/v1 models", "bogus-key")
        self.assertIsNone(status)
        self.assertTrue(err)

    def test_real_http_status_urlerror_returns_none(self) -> None:
        # A connection/DNS failure is a URLError; the function must return (None, reason), not raise.
        # Patch the opener to fail deterministically so the unit suite never touches the network.
        class _Boom:
            def open(self, *_a: Any, **_k: Any) -> Any:
                raise urllib.error.URLError("name resolution failed")

        orig = ec._NO_REDIRECT_OPENER
        ec._NO_REDIRECT_OPENER = _Boom()
        try:
            status, err = ec._http_status("http://gw.example.com/v1/models", "bogus-key")
        finally:
            ec._NO_REDIRECT_OPENER = orig
        self.assertIsNone(status)
        self.assertIn("name resolution failed", err)

    def test_no_redirect_opener_does_not_follow_redirects(self) -> None:
        # The opener must refuse redirects so a bearer key can never cross an origin. Its handler
        # returns None (redirect suppressed), which urllib turns into the 3xx surfacing as a status.
        handler = ec._NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "http://elsewhere.example"))

    # ---- aim-route-hostnames-ready ----
    def test_single_listener_gateway_is_ok(self) -> None:
        _, p = self._run()  # baseline gateway is single-listener
        self.assertEqual(self._status_of(p, "aim-route-hostnames-ready"), "ok")

    def test_multi_listener_missing_hostnames_is_problem(self) -> None:
        _, p = self._run({
            "kubectl get gateway https -n kgateway-system -o json": (0, json.dumps({"spec": {"listeners": [{"name": "l1"}, {"name": "l2"}]}}), ""),
            "kubectl get aimclusterruntimeconfig default -o json": (0, json.dumps({"spec": {"routing": {"enabled": True, "hostnames": []}}}), ""),
        })
        self.assertEqual(self._status_of(p, "aim-route-hostnames-ready"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "aim-route-hostnames-ready")
        self.assertIn("RouteHostnameRequired", verdict)

    def test_multi_listener_with_hostnames_is_ok(self) -> None:
        _, p = self._run({
            "kubectl get gateway https -n kgateway-system -o json": (0, json.dumps({"spec": {"listeners": [{"name": "l1"}, {"name": "l2"}]}}), ""),
            "kubectl get aimclusterruntimeconfig default -o json": (0, json.dumps({"spec": {"routing": {"enabled": True, "hostnames": ["workloads.example.com"]}}}), ""),
        })
        self.assertEqual(self._status_of(p, "aim-route-hostnames-ready"), "ok")

    def test_multi_listener_enabled_omitted_no_hostnames_is_inconclusive(self) -> None:
        # routing.enabled omitted: the CRD defaults it to true, so empty hostnames may still break
        # catalog deploys. Never report OK on unconfirmed state (anti-silence).
        _, p = self._run({
            "kubectl get gateway https -n kgateway-system -o json": (0, json.dumps({"spec": {"listeners": [{"name": "l1"}, {"name": "l2"}]}}), ""),
            "kubectl get aimclusterruntimeconfig default -o json": (0, json.dumps({"spec": {"routing": {"hostnames": []}}}), ""),
        })
        self.assertEqual(self._status_of(p, "aim-route-hostnames-ready"), "inconclusive")

    def test_multi_listener_enabled_false_no_hostnames_is_ok(self) -> None:
        # Routing explicitly disabled: empty hostnames cannot break anything.
        _, p = self._run({
            "kubectl get gateway https -n kgateway-system -o json": (0, json.dumps({"spec": {"listeners": [{"name": "l1"}, {"name": "l2"}]}}), ""),
            "kubectl get aimclusterruntimeconfig default -o json": (0, json.dumps({"spec": {"routing": {"enabled": False, "hostnames": []}}}), ""),
        })
        self.assertEqual(self._status_of(p, "aim-route-hostnames-ready"), "ok")

    def test_unreadable_aim_gateway_is_inconclusive(self) -> None:
        _, p = self._run({"kubectl get gateway https -n kgateway-system -o json": (1, "", "Error from server (Forbidden)")})
        self.assertEqual(self._status_of(p, "aim-route-hostnames-ready"), "inconclusive")

    def test_multi_listener_unreadable_runtimeconfig_is_inconclusive(self) -> None:
        _, p = self._run({
            "kubectl get gateway https -n kgateway-system -o json": (0, json.dumps({"spec": {"listeners": [{"name": "l1"}, {"name": "l2"}]}}), ""),
            "kubectl get aimclusterruntimeconfig default -o json": (1, "", 'the server doesn\'t have a resource type "aimclusterruntimeconfig"'),
        })
        self.assertEqual(self._status_of(p, "aim-route-hostnames-ready"), "inconclusive")

    def test_gateway_name_resolved_from_aiwb_api_env(self) -> None:
        # aiwb-api env overrides the gateway coordinates; the check must read the env-named gateway.
        _, p = self._run({
            "kubectl get deploy aiwb-api -n aiwb -o json": (0, json.dumps({"status": {"conditions": [{"type": "Available", "status": "True"}], "readyReplicas": 1}, "spec": {"template": {"spec": {"containers": [{"env": [{"name": "AIM_GATEWAY_NAMESPACE", "value": "custom-gw-ns"}, {"name": "AIM_GATEWAY_NAME", "value": "custom-gw"}]}]}}}}), ""),
            "kubectl get gateway custom-gw -n custom-gw-ns -o json": (0, json.dumps({"spec": {"listeners": [{"name": "l1"}]}}), ""),
        })
        self.assertEqual(self._status_of(p, "aim-route-hostnames-ready"), "ok")

    def test_unreadable_aiwb_api_env_is_inconclusive_not_default_fallback(self) -> None:
        _, p = self._run({
            "kubectl get deploy aiwb-api -n aiwb -o json": (1, "", "Error from server (Forbidden)"),
        })
        self.assertEqual(self._status_of(p, "aim-route-hostnames-ready"), "inconclusive")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "aim-route-hostnames-ready")
        self.assertIn("default coordinates were not assumed", verdict)

    # ---- app-pods-stable ----
    def test_app_pods_all_running_is_ok(self) -> None:
        _, p = self._run()
        self.assertEqual(self._status_of(p, "app-pods-stable"), "ok")

    def test_crashloop_pod_is_problem(self) -> None:
        _, p = self._run({"kubectl get pods -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "aiwb-api-x"}, "status": {"phase": "Pending", "containerStatuses": [{"name": "aiwb", "ready": False, "restartCount": 7, "state": {"waiting": {"reason": "CrashLoopBackOff"}}}]}}]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "app-pods-stable")
        self.assertIn("CrashLoopBackOff", verdict)

    def test_create_container_config_error_is_problem(self) -> None:
        # The aiwb-api openbao-token block manifests as CreateContainerConfigError.
        _, p = self._run({"kubectl get pods -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "aiwb-api-x"}, "status": {"phase": "Pending", "containerStatuses": [{"name": "aiwb", "ready": False, "restartCount": 0, "state": {"waiting": {"reason": "CreateContainerConfigError"}}}]}}]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "warn")

    def test_ready_but_crash_looped_pod_is_problem(self) -> None:
        # A pod Ready NOW but repeatedly restarted was flapping and must still warn — intermittent
        # backend restarts surface to users as sporadic request failures.
        _, p = self._run({"kubectl get pods -n airm -o json": (0, _jsonlist([{"metadata": {"name": "airm-api-x"}, "status": {"phase": "Running", "containerStatuses": [{"name": "airm", "ready": True, "restartCount": 5, "state": {"running": {}}, "lastState": {"terminated": {"reason": "Error"}}}]}}]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "app-pods-stable")
        self.assertIn("5-restarts", verdict)

    def test_ready_with_restarts_below_threshold_is_ok(self) -> None:
        _, p = self._run({"kubectl get pods -n airm -o json": (0, _jsonlist([{"metadata": {"name": "airm-api-x"}, "status": {"phase": "Running", "containerStatuses": [{"name": "airm", "ready": True, "restartCount": 2, "state": {"running": {}}}]}}]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "ok")

    def test_restart_threshold_is_tunable(self) -> None:
        _, p = self._run(
            {"kubectl get pods -n airm -o json": (0, _jsonlist([{"metadata": {"name": "airm-api-x"}, "status": {"phase": "Running", "containerStatuses": [{"name": "airm", "ready": True, "restartCount": 2, "state": {"running": {}}}]}}]), "")},
            argv=["--restart-threshold", "2"],
        )
        self.assertEqual(self._status_of(p, "app-pods-stable"), "warn")

    def test_completed_job_pod_is_ignored(self) -> None:
        _, p = self._run({"kubectl get pods -n airm -o json": (0, _jsonlist([{"metadata": {"name": "airm-configure-x", "ownerReferences": [{"kind": "Job"}]}, "status": {"phase": "Succeeded", "containerStatuses": [{"name": "c", "ready": False, "restartCount": 0, "state": {"terminated": {"reason": "Completed"}}}]}}]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "ok")

    def test_unschedulable_pod_is_surfaced_not_skipped(self) -> None:
        # A pod that never got scheduled has NO containerStatuses; skipping it would let the check
        # claim "all app pods Running/Ready" while a workload cannot start at all.
        _, p = self._run({"kubectl get pods -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "aiwb-job-x"}, "status": {"phase": "Pending", "startTime": _ts_ago(3600), "conditions": [{"type": "PodScheduled", "status": "False", "reason": "Unschedulable", "message": "0/3 nodes are available: insufficient cpu"}]}}]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "app-pods-stable")
        self.assertIn("Unschedulable", verdict)

    def test_recently_created_unscheduled_pod_within_grace_is_ok(self) -> None:
        # Still being scheduled is not yet a fault.
        _, p = self._run({"kubectl get pods -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "aiwb-job-x"}, "status": {"phase": "Pending", "startTime": _ts_ago(10), "conditions": [{"type": "PodScheduled", "status": "False", "reason": "Unschedulable"}]}}]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "ok")

    def test_completed_job_pod_without_container_statuses_ignored(self) -> None:
        _, p = self._run({"kubectl get pods -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "done-x", "ownerReferences": [{"kind": "Job"}]}, "status": {"phase": "Succeeded", "startTime": _ts_ago(3600)}}]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "ok")

    def test_restart_threshold_boundary(self) -> None:
        # Exactly at the threshold warns; one below does not.
        def pod(restarts: int) -> str:
            return _jsonlist([{"metadata": {"name": "airm-api-x"}, "status": {"phase": "Running", "containerStatuses": [{"name": "airm", "ready": True, "restartCount": restarts, "state": {"running": {}}}]}}])
        _, at = self._run({"kubectl get pods -n airm -o json": (0, pod(3), "")})
        _, below = self._run({"kubectl get pods -n airm -o json": (0, pod(2), "")})
        self.assertEqual(self._status_of(at, "app-pods-stable"), "warn")
        self.assertEqual(self._status_of(below, "app-pods-stable"), "ok")

    def test_lease_freshness_boundary(self) -> None:
        # A lease just inside the freshness window proves liveness; just outside does not.
        def lease(age: int) -> str:
            return _jsonlist([{"metadata": {"name": "external-provisioner-leader-csi-example-com", "namespace": "kube-system"}, "spec": {"renewTime": _ts_ago(age)}}])
        _, fresh = self._run({"kubectl get leases.coordination.k8s.io -A -o json": (0, lease(ec._LEASE_FRESH_SECONDS - 30), "")})
        _, stale = self._run({"kubectl get leases.coordination.k8s.io -A -o json": (0, lease(ec._LEASE_FRESH_SECONDS + 30), "")})
        self.assertEqual(self._status_of(fresh, "storage-provisioner"), "ok")
        self.assertEqual(self._status_of(stale, "storage-provisioner"), "warn")

    def test_storageclass_without_provisioner_is_inconclusive(self) -> None:
        _, p = self._run({"kubectl get storageclass -o json": (0, _jsonlist([{"metadata": {"name": "sc-x"}}]), "")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "inconclusive")

    def test_blank_provisioner_does_not_mask_unbacked_driver_warn(self) -> None:
        # Report every problem: an unidentifiable StorageClass is only a caveat; a different class
        # whose real driver is not registered is a confirmed WARN and must win.
        _, p = self._run({"kubectl get storageclass -o json": (0, _jsonlist([
            {"metadata": {"name": "blank-sc"}},
            {"metadata": {"name": "broken-sc"}, "provisioner": "missing.csi.driver"},
        ]), "")})
        self.assertEqual(self._status_of(p, "storage-provisioner"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "storage-provisioner")
        self.assertIn("missing.csi.driver", verdict)
        self.assertIn("blank-sc", verdict)

    def test_scheduled_init_failure_not_mislabelled_unscheduled(self) -> None:
        # The pod has been scheduled and is stuck in an init container. It should be named by the
        # init failure only, not also as Unscheduled(Pending).
        _, p = self._run({"kubectl get pods -n aiwb -o json": (0, _jsonlist([{
            "metadata": {"name": "aiwb-api-x"},
            "status": {
                "phase": "Pending", "startTime": _ts_ago(3600),
                "conditions": [{"type": "PodScheduled", "status": "True"}],
                "initContainerStatuses": [{"name": "wait-for-db", "state": {"waiting": {"reason": "ImagePullBackOff"}}}],
            },
        }]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "app-pods-stable")
        self.assertIn("init:wait-for-db", verdict)
        self.assertNotIn("Unscheduled", verdict)

    def test_old_pending_pod_without_conditions_is_surfaced(self) -> None:
        # An old Pending pod with no containerStatuses and no PodScheduled condition must not fall
        # through to the all-clear; it is not affirmatively scheduled.
        _, p = self._run({"kubectl get pods -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "old-pending"}, "status": {"phase": "Pending", "startTime": _ts_ago(3600)}}]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "app-pods-stable")
        self.assertIn("Unscheduled", verdict)

    def test_app_namespaces_absent_is_inconclusive(self) -> None:
        _, p = self._run({
            "kubectl get pods -n aiwb -o json": (1, "", 'namespaces "aiwb" not found'),
            "kubectl get pods -n airm -o json": (1, "", 'namespaces "airm" not found'),
        })
        self.assertEqual(self._status_of(p, "app-pods-stable"), "inconclusive")

    def test_app_pods_unreadable_is_inconclusive(self) -> None:
        _, p = self._run({"kubectl get pods -n aiwb -o json": (1, "", "Error from server (Forbidden)")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "inconclusive")

    def test_notready_pod_within_startup_grace_is_ok(self) -> None:
        # A freshly-created NotReady pod is a rollout in progress, not a fault — must NOT warn.
        _, p = self._run({"kubectl get pods -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "aiwb-api-x"}, "status": {"phase": "Running", "startTime": _ts_ago(10), "containerStatuses": [{"name": "aiwb", "ready": False, "restartCount": 0, "state": {"running": {}}}]}}]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "ok")

    def test_notready_pod_within_grace_fractional_timestamp(self) -> None:
        # A fractional-second (RFC3339Nano) startTime must still parse, so a just-started NotReady
        # pod stays within grace and is not flagged.
        recent = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%S.123456Z")
        _, p = self._run({"kubectl get pods -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "aiwb-api-x"}, "status": {"phase": "Running", "startTime": recent, "containerStatuses": [{"name": "aiwb", "ready": False, "restartCount": 0, "state": {"running": {}}}]}}]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "ok")

    def test_notready_pod_past_grace_is_problem(self) -> None:
        _, p = self._run({"kubectl get pods -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "aiwb-api-x"}, "status": {"phase": "Running", "startTime": _ts_ago(3600), "containerStatuses": [{"name": "aiwb", "ready": False, "restartCount": 0, "state": {"running": {}}}]}}]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "app-pods-stable")
        self.assertIn("NotReady", verdict)

    def test_init_container_imagepull_is_problem(self) -> None:
        # An init container stuck pulling blocks the pod from ever starting — flag it, named init.
        _, p = self._run({"kubectl get pods -n airm -o json": (0, _jsonlist([{"metadata": {"name": "airm-api-x"}, "status": {"phase": "Pending", "startTime": _ts_ago(30), "initContainerStatuses": [{"name": "wait-for-db", "ready": False, "restartCount": 0, "state": {"waiting": {"reason": "ImagePullBackOff"}}}], "containerStatuses": []}}]), "")})
        self.assertEqual(self._status_of(p, "app-pods-stable"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "app-pods-stable")
        self.assertIn("init:wait-for-db", verdict)

    def test_aimartifact_answer_after_warning_line_is_read(self) -> None:
        # kubectl may print a warning line before the yes/no answer on stdout; the last line wins.
        _, p = self._run({"kubectl auth can-i create aimartifacts.aim.eai.amd.com -n e2e-apiserver-testing": (0, "Warning: resource requires --subresource\nyes", "")})
        self.assertEqual(self._status_of(p, "aimartifact-rbac"), "ok")

    # ---- aiwb deployments ----
    def test_aiwb_api_not_available_is_problem(self) -> None:
        _, p = self._run({"kubectl get deploy aiwb-api -n aiwb -o json": (0, json.dumps({"status": {"conditions": [{"type": "Available", "status": "False"}], "readyReplicas": 0}}), "")})
        self.assertEqual(self._status_of(p, "aiwb-api-healthy"), "warn")

    def test_aiwb_api_absent_is_inconclusive(self) -> None:
        _, p = self._run({"kubectl get deploy aiwb-api -n aiwb -o json": (1, "", 'deployments.apps "aiwb-api" not found')})
        self.assertEqual(self._status_of(p, "aiwb-api-healthy"), "inconclusive")

    # ---- gpu schedulable ----
    def test_no_gpu_nodes_is_ok_without_require(self) -> None:
        _, p = self._run({"kubectl get nodes -o json": (0, _jsonlist([{"metadata": {"labels": {}}, "status": {"capacity": {}, "allocatable": {}}}]), "")})
        self.assertEqual(self._status_of(p, "gpu-schedulable"), "ok")

    def test_no_gpu_nodes_is_problem_with_require(self) -> None:
        _, p = self._run(
            {"kubectl get nodes -o json": (0, _jsonlist([{"metadata": {"labels": {}}, "status": {"capacity": {}, "allocatable": {}}}]), "")},
            argv=["--require-gpu"],
        )
        self.assertEqual(self._status_of(p, "gpu-schedulable"), "warn")

    def test_gpu_capacity_but_zero_allocatable_is_problem(self) -> None:
        _, p = self._run({"kubectl get nodes -o json": (0, _jsonlist([{"metadata": {"labels": {}}, "status": {"capacity": {"amd.com/gpu": "8"}, "allocatable": {"amd.com/gpu": "0"}}}]), "")})
        self.assertEqual(self._status_of(p, "gpu-schedulable"), "warn")

    def test_gpu_allocatable_but_linked_queue_has_no_quota_is_problem(self) -> None:
        _, p = self._run({
            "kubectl get clusterqueues.kueue.x-k8s.io project-queue -o json": (0, json.dumps({"spec": {"resourceGroups": []}}), ""),
        })
        self.assertEqual(self._status_of(p, "gpu-schedulable"), "warn")

    def test_gpu_zero_quota_but_cohort_borrowing_is_ok(self) -> None:
        # AIRM project queues join the kaiwo cohort with borrowing enabled, so zero local quota still
        # admits GPU jobs. gpu-schedulable must not contradict check_airm_quota_health, which treats
        # this same shape as healthy.
        _, p = self._run({
            "kubectl get clusterqueues.kueue.x-k8s.io project-queue -o json": (0, json.dumps({"spec": {"cohort": "kaiwo", "resourceGroups": []}}), ""),
        })
        self.assertEqual(self._status_of(p, "gpu-schedulable"), "ok")

    def test_gpu_allocatable_unreadable_localqueue_is_inconclusive(self) -> None:
        _, p = self._run({"kubectl get localqueues.kueue.x-k8s.io -n e2e-apiserver-testing -o json": (1, "", "no such CRD")})
        self.assertEqual(self._status_of(p, "gpu-schedulable"), "inconclusive")

    def test_gpu_allocatable_without_localqueue_is_problem(self) -> None:
        _, p = self._run({"kubectl get localqueues.kueue.x-k8s.io -n e2e-apiserver-testing -o json": (0, _jsonlist([]), "")})
        self.assertEqual(self._status_of(p, "gpu-schedulable"), "warn")

    def test_unrelated_clusterqueue_quota_does_not_false_pass(self) -> None:
        _, p = self._run({
            "kubectl get clusterqueues.kueue.x-k8s.io project-queue -o json": (0, json.dumps({"metadata": {"name": "project-queue"}, "spec": {"resourceGroups": []}}), ""),
            "kubectl get clusterqueues.kueue.x-k8s.io -o json": (0, _jsonlist([{"metadata": {"name": "unrelated"}, "spec": {"resourceGroups": [{"flavors": [{"resources": [{"name": "amd.com/gpu", "nominalQuota": "8"}]}]}]}}]), ""),
        })
        self.assertEqual(self._status_of(p, "gpu-schedulable"), "warn")

    def test_missing_linked_clusterqueue_is_problem(self) -> None:
        _, p = self._run({
            "kubectl get clusterqueues.kueue.x-k8s.io project-queue -o json": (1, "", 'clusterqueues.kueue.x-k8s.io "project-queue" not found'),
        })
        self.assertEqual(self._status_of(p, "gpu-schedulable"), "warn")

    def test_multiple_localqueues_selected_by_project_name(self) -> None:
        # The queue named for the project is chosen even when the API lists another first.
        _, p = self._run({
            "kubectl get localqueues.kueue.x-k8s.io -n e2e-apiserver-testing -o json": (0, _jsonlist([
                {"metadata": {"name": "other-queue"}, "spec": {"clusterQueue": "gpu-cq"}},
                {"metadata": {"name": "e2e-apiserver-testing"}, "spec": {"clusterQueue": "project-queue"}},
            ]), ""),
            "kubectl get clusterqueues.kueue.x-k8s.io gpu-cq -o json": (0, json.dumps({"spec": {"resourceGroups": [{"flavors": [{"resources": [{"name": "amd.com/gpu", "nominalQuota": "8"}]}]}]}}), ""),
            "kubectl get clusterqueues.kueue.x-k8s.io project-queue -o json": (0, json.dumps({"spec": {"resourceGroups": []}}), ""),
        })
        # The project queue has no quota, so following the arbitrary first queue would false-pass.
        self.assertEqual(self._status_of(p, "gpu-schedulable"), "warn")

    def test_multiple_unnamed_localqueues_are_ambiguous(self) -> None:
        _, p = self._run({
            "kubectl get localqueues.kueue.x-k8s.io -n e2e-apiserver-testing -o json": (0, _jsonlist([
                {"metadata": {"name": "queue-a"}, "spec": {"clusterQueue": "cq-a"}},
                {"metadata": {"name": "queue-b"}, "spec": {"clusterQueue": "cq-b"}},
            ]), ""),
        })
        self.assertEqual(self._status_of(p, "gpu-schedulable"), "inconclusive")

    def test_test_namespace_selects_its_own_localqueue(self) -> None:
        _, p = self._run(
            {
                "kubectl get localqueues.kueue.x-k8s.io -n custom-ns -o json": (0, _jsonlist([{"spec": {"clusterQueue": "custom-queue"}}]), ""),
                "kubectl get clusterqueues.kueue.x-k8s.io custom-queue -o json": (0, json.dumps({"spec": {"resourceGroups": [{"flavors": [{"resources": [{"name": "amd.com/gpu", "nominalQuota": "4"}]}]}]}}), ""),
                "kubectl auth can-i create aimartifacts.aim.eai.amd.com -n custom-ns": (0, "yes", ""),
            },
            argv=["--test-namespace", "custom-ns"],
        )
        self.assertEqual(self._status_of(p, "gpu-schedulable"), "ok")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "gpu-schedulable")
        self.assertIn("custom-ns", verdict)

    # ---- multiple problems ----
    def test_multiple_problems_all_reported(self) -> None:
        code, p = self._run({
            "kubectl get volumes.longhorn.io -A -o json": (0, _jsonlist([{"metadata": {"name": "v-a"}, "status": {"robustness": "faulted", "state": "detached"}}]), ""),
            "kubectl get pods -A --field-selector=status.phase=Pending -o json": (0, _jsonlist([{"metadata": {"namespace": "proj", "name": "train-0"}, "status": {"conditions": [{"type": "PodScheduled", "status": "False", "message": "pod has unbound immediate PersistentVolumeClaims"}]}}]), ""),
        })
        self.assertEqual(code, 1)
        self.assertEqual(self._status_of(p, "longhorn-health"), "warn")
        self.assertEqual(self._status_of(p, "stuck-storage-pods"), "warn")

    # ---- release-spec-skew (opt-in) ----
    # Fake commit ids the stubbed git resolves tags to. Distinct and hex-shaped.
    _SPEC = "aaaaaaaaaaaa1111"
    _AIWB_DEP = "bbbbbbbbbbbb2222"
    _AIRM_DEP = "cccccccccccc3333"
    # Running-manifest digests (imageID), distinct per product so a uniform digest is proven.
    _AIWB_DIGEST = "sha256:" + "b" * 64
    _AIRM_DIGEST = "sha256:" + "c" * 64

    def _skew_git(self, *, spec_resolves: bool = True,
                  aiwb_tag: str = "2.0.2-rc.2", airm_tag: str = "2.0.2-rc.3",
                  aiwb_commit: str | None = None, airm_commit: str | None = None,
                  aiwb_spec_in_dep: int = 0, airm_spec_in_dep: int = 0,
                  aiwb_dep_in_spec: int = 0, airm_dep_in_spec: int = 0,
                  extra: dict[str, tuple[int, str, str]] | None = None) -> dict[str, tuple[int, str, str]]:
        """Build the git + deployment stub table for a skew scenario.

        *_spec_in_dep / *_dep_in_spec are the `merge-base --is-ancestor` return codes
        (0 = ancestor, 1 = not an ancestor, any other value such as 128 = git error). aiwb_commit /
        airm_commit default to a resolvable commit id; to make a deployed tag unresolvable, override
        its `--verify --quiet refs/tags/<tag>` entry to a non-zero rc (see the unresolvable-tag tests).
        """
        aiwb_commit = self._AIWB_DEP if aiwb_commit is None else aiwb_commit
        airm_commit = self._AIRM_DEP if airm_commit is None else airm_commit
        t: dict[str, tuple[int, str, str]] = {
            "rev-parse --is-inside-work-tree": (0, "true", ""),
            "rev-parse --is-shallow-repository": (0, "false", ""),
            f"rev-parse --verify --quiet {self._SPEC}^{{commit}}": (
                (0, self._SPEC, "") if spec_resolves else (1, "", "")),
            "kubectl get deploy aiwb-api -n aiwb -o json": (0, json.dumps({
                "metadata": {"generation": 4},
                "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "aiwb-api"}}},
                "status": {"observedGeneration": 4, "updatedReplicas": 1, "readyReplicas": 1,
                           "availableReplicas": 1, "unavailableReplicas": 0},
            }), ""),
            "kubectl get deploy airm-api -n airm -o json": (0, json.dumps({
                "metadata": {"generation": 7},
                "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "airm-api"}}},
                "status": {"observedGeneration": 7, "updatedReplicas": 1, "readyReplicas": 1,
                           "availableReplicas": 1, "unavailableReplicas": 0},
            }), ""),
            "kubectl get pods -n aiwb -l app=aiwb-api -o json": (0, _jsonlist([{
                "metadata": {"name": "aiwb-api-1"},
                "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}],
                           "containerStatuses": [{"name": "aiwb", "image": f"registry.example.com/aiwb-api:{aiwb_tag}",
                                                  "imageID": f"registry.example.com/aiwb-api@{self._AIWB_DIGEST}"}]},
            }]), ""),
            "kubectl get pods -n airm -l app=airm-api -o json": (0, _jsonlist([{
                "metadata": {"name": "airm-api-1"},
                "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}],
                           "containerStatuses": [{"name": "airm", "image": f"registry.example.com/airm-api:{airm_tag}",
                                                  "imageID": f"registry.example.com/airm-api@{self._AIRM_DIGEST}"}]},
            }]), ""),
        }
        # Each product's release tag resolves to its commit, plus both ancestry comparisons. A test
        # that wants an unresolvable tag overrides the matching refs/tags entry to a non-zero rc.
        t[f"--verify --quiet refs/tags/{aiwb_tag}^{{commit}}"] = (0, aiwb_commit, "")
        t[f"--verify --quiet refs/tags/{airm_tag}^{{commit}}"] = (0, airm_commit, "")
        t[f"merge-base --is-ancestor {self._SPEC} {aiwb_commit}"] = (aiwb_spec_in_dep, "", "")
        t[f"merge-base --is-ancestor {aiwb_commit} {self._SPEC}"] = (aiwb_dep_in_spec, "", "")
        t[f"merge-base --is-ancestor {self._SPEC} {airm_commit}"] = (airm_spec_in_dep, "", "")
        t[f"merge-base --is-ancestor {airm_commit} {self._SPEC}"] = (airm_dep_in_spec, "", "")
        t.update(extra or {})
        return t

    def _skew_argv(self) -> list[str]:
        return ["--spec-revision", self._SPEC, "--core-repo", "/core"]

    def test_skew_not_run_without_spec_revision(self) -> None:
        # The check is opt-in: an ordinary run must not include it (and must not touch git).
        _, p = self._run()
        names = [c["name"] for c in p["checks"]]
        self.assertNotIn("release-spec-skew", names)

    def test_skew_focused_subcommand_returns_one_check(self) -> None:
        code, p = self._run(
            self._skew_git(aiwb_spec_in_dep=0, airm_spec_in_dep=0),
            argv=["release-spec-skew", self._SPEC, "--core-repo", "/core"],
        )
        self.assertEqual(code, 0)
        self.assertEqual([c["name"] for c in p["checks"]], ["release-spec-skew"])

    def _capture_skew_args(self, argv: list[str]) -> dict[str, str]:
        """Run main() with the skew check stubbed, capturing the (spec_revision, core_repo) it wires."""
        captured: dict[str, str] = {}

        def fake(spec_revision: str, core_repo: str) -> Any:
            captured["spec"] = spec_revision
            captured["repo"] = core_repo
            return ec.CheckResult("release-spec-skew", ec.OK, "stub")

        orig = ec.check_release_spec_skew
        ec.check_release_spec_skew = fake
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                ec.main([*argv, "--json"])
        finally:
            ec.check_release_spec_skew = orig
        return captured

    def test_skew_core_repo_before_subcommand_is_honored(self) -> None:
        # Regression: --core-repo passed BEFORE the subcommand must reach the check, not be clobbered
        # by the subparser's default (the argparse shared-dest footgun).
        captured = self._capture_skew_args(["--core-repo", "/before", "release-spec-skew", "abc123"])
        self.assertEqual(captured["repo"], "/before")
        self.assertEqual(captured["spec"], "abc123")

    def test_skew_core_repo_after_subcommand_is_honored(self) -> None:
        captured = self._capture_skew_args(["release-spec-skew", "abc123", "--core-repo", "/after"])
        self.assertEqual(captured["repo"], "/after")

    def test_skew_core_repo_defaults_to_cwd_when_unset(self) -> None:
        captured = self._capture_skew_args(["release-spec-skew", "abc123"])
        self.assertEqual(captured["repo"], ".")

    def test_skew_deployed_contains_spec_is_ok(self) -> None:
        # Both deployed products contain the spec revision (spec is an ancestor of each deployed commit).
        _, p = self._run(self._skew_git(aiwb_spec_in_dep=0, airm_spec_in_dep=0), argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "ok")

    def test_skew_deployed_predates_spec_is_problem(self) -> None:
        # aiwb deployed predates the spec: spec not ancestor of deployed (1), deployed ancestor of spec (0).
        _, p = self._run(self._skew_git(aiwb_spec_in_dep=1, aiwb_dep_in_spec=0), argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "release-spec-skew")
        self.assertIn("aiwb", verdict)
        self.assertIn("predates", verdict)

    def test_skew_diverged_deployment_is_problem(self) -> None:
        # Neither ancestor relation holds -> diverged -> WARN (deployment lacks the specs' behaviour).
        _, p = self._run(self._skew_git(airm_spec_in_dep=1, airm_dep_in_spec=1), argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "warn")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "release-spec-skew")
        self.assertIn("diverged", verdict)

    def test_skew_main_sha_tag_resolves_via_trailing_sha(self) -> None:
        # A main-<sha> tag with no matching release tag falls back to the trailing git short SHA.
        git = self._skew_git(airm_tag="main-fdb389c", airm_commit=None)
        git["--verify --quiet refs/tags/main-fdb389c^{commit}"] = (1, "", "")
        git["--verify --quiet fdb389c^{commit}"] = (0, "fdb389c" + "1" * 33, "")
        git[f"merge-base --is-ancestor {self._SPEC} {'fdb389c' + '1' * 33}"] = (0, "", "")
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "ok")

    def test_skew_calendar_rc_release_tag_resolves(self) -> None:
        _, p = self._run(
            self._skew_git(aiwb_tag="v2025.08-rc.21", aiwb_spec_in_dep=0, airm_spec_in_dep=0),
            argv=self._skew_argv(),
        )
        self.assertEqual(self._status_of(p, "release-spec-skew"), "ok")

    def test_skew_calendar_final_release_tag_resolves(self) -> None:
        _, p = self._run(
            self._skew_git(airm_tag="v2025.08.002", aiwb_spec_in_dep=0, airm_spec_in_dep=0),
            argv=self._skew_argv(),
        )
        self.assertEqual(self._status_of(p, "release-spec-skew"), "ok")

    def test_skew_unresolvable_tag_is_inconclusive(self) -> None:
        # A deployed tag that matches neither a release tag nor a trailing SHA cannot be placed.
        git = self._skew_git(airm_tag="weird-opaque", airm_commit=None)
        git["--verify --quiet refs/tags/weird-opaque^{commit}"] = (1, "", "")
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_mutable_branch_tag_is_inconclusive(self) -> None:
        # A bare image tag `main` must not resolve through refs/heads/main or even a moving tag of the
        # same name; it is not one of the established immutable release-name families.
        _, p = self._run(self._skew_git(airm_tag="main", airm_commit=None), argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_branch_like_calendar_tag_is_inconclusive(self) -> None:
        # Calendar-looking branch names do not become releases without one of the exact known forms.
        _, p = self._run(self._skew_git(airm_tag="v2025.08-main", airm_commit=None), argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_spec_revision_unresolvable_is_inconclusive(self) -> None:
        _, p = self._run(self._skew_git(spec_resolves=False), argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_bad_core_repo_is_inconclusive(self) -> None:
        git = self._skew_git()
        git["rev-parse --is-inside-work-tree"] = (128, "", "not a git repository")
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_absent_deployment_is_inconclusive_not_ok(self) -> None:
        # A product not deployed cannot be confirmed compatible; with the other one OK it stays INCONCLUSIVE.
        git = self._skew_git(aiwb_spec_in_dep=0)
        git["kubectl get deploy airm-api -n airm -o json"] = (1, "", 'deployments.apps "airm-api" not found')
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_digest_only_image_is_inconclusive(self) -> None:
        git = self._skew_git(aiwb_spec_in_dep=0)
        git["kubectl get pods -n airm -l app=airm-api -o json"] = (0, _jsonlist([{
            "metadata": {"name": "airm-api-1"},
            "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}],
                       "containerStatuses": [{"name": "airm", "image": "registry.example.com/airm-api@sha256:" + "a" * 64,
                                              "imageID": f"registry.example.com/airm-api@{self._AIRM_DIGEST}"}]},
        }]), "")
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_tag_plus_digest_is_inconclusive(self) -> None:
        # OCI selects the digest, not the optional tag before it. Without trusted digest provenance,
        # the tag cannot establish which source commit is running.
        git = self._skew_git(aiwb_spec_in_dep=0)
        git["kubectl get pods -n airm -l app=airm-api -o json"] = (0, _jsonlist([{
            "metadata": {"name": "airm-api-1"},
            "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}],
                       "containerStatuses": [{"name": "airm", "image": "registry.example.com/airm-api:2.0.2-rc.3@sha256:" + "a" * 64,
                                              "imageID": f"registry.example.com/airm-api@{self._AIRM_DIGEST}"}]},
        }]), "")
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_incomplete_rollout_is_inconclusive(self) -> None:
        git = self._skew_git(aiwb_spec_in_dep=0)
        git["kubectl get deploy airm-api -n airm -o json"] = (0, json.dumps({
            "metadata": {"generation": 8},
            "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "airm-api"}}},
            "status": {"observedGeneration": 8, "updatedReplicas": 1, "readyReplicas": 1,
                       "availableReplicas": 1, "unavailableReplicas": 1},
        }), "")
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_mixed_ready_pod_images_are_inconclusive(self) -> None:
        git = self._skew_git(aiwb_spec_in_dep=0)
        git["kubectl get deploy airm-api -n airm -o json"] = (0, json.dumps({
            "metadata": {"generation": 8},
            "spec": {"replicas": 2, "selector": {"matchLabels": {"app": "airm-api"}}},
            "status": {"observedGeneration": 8, "updatedReplicas": 2, "readyReplicas": 2,
                       "availableReplicas": 2, "unavailableReplicas": 0},
        }), "")
        git["kubectl get pods -n airm -l app=airm-api -o json"] = (0, _jsonlist([
            {"metadata": {"name": "airm-api-old"}, "status": {"phase": "Running",
             "conditions": [{"type": "Ready", "status": "True"}], "containerStatuses": [
                 {"name": "airm", "image": "registry.example.com/airm-api:2.0.2-rc.2",
                  "imageID": f"registry.example.com/airm-api@{self._AIRM_DIGEST}"}]}},
            {"metadata": {"name": "airm-api-new"}, "status": {"phase": "Running",
             "conditions": [{"type": "Ready", "status": "True"}], "containerStatuses": [
                 {"name": "airm", "image": "registry.example.com/airm-api:2.0.2-rc.3",
                  "imageID": f"registry.example.com/airm-api@{self._AIRM_DIGEST}"}]}},
        ]), "")
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_mixed_running_digests_under_one_tag_is_inconclusive(self) -> None:
        # The partial-retarget case: both Ready pods advertise the same tag text, but their running
        # imageID manifests differ — some pods serve an older build. Never OK/WARN.
        git = self._skew_git(aiwb_spec_in_dep=0)
        git["kubectl get deploy airm-api -n airm -o json"] = (0, json.dumps({
            "metadata": {"generation": 8},
            "spec": {"replicas": 2, "selector": {"matchLabels": {"app": "airm-api"}}},
            "status": {"observedGeneration": 8, "updatedReplicas": 2, "readyReplicas": 2,
                       "availableReplicas": 2, "unavailableReplicas": 0},
        }), "")
        git["kubectl get pods -n airm -l app=airm-api -o json"] = (0, _jsonlist([
            {"metadata": {"name": "airm-api-a"}, "status": {"phase": "Running",
             "conditions": [{"type": "Ready", "status": "True"}], "containerStatuses": [
                 {"name": "airm", "image": "registry.example.com/airm-api:2.0.2-rc.3",
                  "imageID": "registry.example.com/airm-api@sha256:" + "1" * 64}]}},
            {"metadata": {"name": "airm-api-b"}, "status": {"phase": "Running",
             "conditions": [{"type": "Ready", "status": "True"}], "containerStatuses": [
                 {"name": "airm", "image": "registry.example.com/airm-api:2.0.2-rc.3",
                  "imageID": "registry.example.com/airm-api@sha256:" + "2" * 64}]}},
        ]), "")
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "release-spec-skew")
        self.assertIn("different running manifests", verdict)

    def test_skew_missing_running_digest_is_inconclusive(self) -> None:
        # imageID absent (never pulled / status not populated): the serving manifest is unknown.
        git = self._skew_git(aiwb_spec_in_dep=0)
        git["kubectl get pods -n airm -l app=airm-api -o json"] = (0, _jsonlist([{
            "metadata": {"name": "airm-api-1"},
            "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}],
                       "containerStatuses": [{"name": "airm", "image": "registry.example.com/airm-api:2.0.2-rc.3"}]},
        }]), "")
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_missing_product_container_is_inconclusive_not_sidecar(self) -> None:
        # Never fall back to a sidecar when the chart's explicit product container is absent.
        git = self._skew_git(aiwb_spec_in_dep=0)
        git["kubectl get pods -n airm -l app=airm-api -o json"] = (0, _jsonlist([{
            "metadata": {"name": "airm-api-1"},
            "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}],
                       "containerStatuses": [{"name": "metrics-sidecar", "image": "example.com/sidecar:2.0.2-rc.3"}]},
        }]), "")
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_problem_wins_over_unconfirmed(self) -> None:
        # A confirmed older product WARNs even if the other product is unreadable (report the problem).
        git = self._skew_git(aiwb_spec_in_dep=1, aiwb_dep_in_spec=0)
        git["kubectl get deploy airm-api -n airm -o json"] = (1, "", "Error from server (Forbidden)")
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "warn")

    def test_skew_git_comparison_error_is_inconclusive(self) -> None:
        # merge-base returning a non 0/1 code (e.g. bad object) is not a definitive answer.
        _, p = self._run(self._skew_git(aiwb_spec_in_dep=128, airm_spec_in_dep=0), argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_second_git_comparison_error_is_inconclusive_not_diverged(self) -> None:
        # The first comparison definitively says the deployment does not contain the specs, but the
        # reverse comparison errors. That does NOT prove divergence; it remains INCONCLUSIVE.
        _, p = self._run(
            self._skew_git(aiwb_spec_in_dep=1, aiwb_dep_in_spec=128, airm_spec_in_dep=0),
            argv=self._skew_argv(),
        )
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")
        verdict = next(c["verdict"] for c in p["checks"] if c["name"] == "release-spec-skew")
        self.assertNotIn("diverged", verdict)

    def test_skew_negative_ancestry_in_shallow_repo_is_inconclusive(self) -> None:
        # A real ancestor may sit beyond the shallow boundary, where merge-base returns 1. Never
        # turn that absence-from-fetched-history into a WARN.
        git = self._skew_git(aiwb_spec_in_dep=1, aiwb_dep_in_spec=0, airm_spec_in_dep=0)
        git["rev-parse --is-shallow-repository"] = (0, "true", "")
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    def test_skew_unreadable_shallow_state_is_inconclusive(self) -> None:
        git = self._skew_git()
        git["rev-parse --is-shallow-repository"] = (128, "", "git error")
        _, p = self._run(git, argv=self._skew_argv())
        self.assertEqual(self._status_of(p, "release-spec-skew"), "inconclusive")

    # ---- image-exists subcommand ----
    def test_image_exists_not_found_via_skopeo_is_problem(self) -> None:
        code, p = self._run(
            {"skopeo inspect docker://reg/repo:tag": (1, "", "manifest unknown: manifest tagged tag not found")},
            argv=["image-exists", "reg/repo:tag"],
            which=lambda name: "/usr/bin/skopeo" if name == "skopeo" else None,
        )
        self.assertEqual(p["overall"], "problems")
        self.assertEqual(code, 1)
        self.assertEqual(p["checks"][0]["status"], "warn")

    def test_image_exists_auth_required_is_inconclusive_not_problem(self) -> None:
        code, p = self._run(
            {"skopeo inspect docker://reg/private:tag": (1, "", "unauthorized: authentication required")},
            argv=["image-exists", "reg/private:tag"],
            which=lambda name: "/usr/bin/skopeo" if name == "skopeo" else None,
        )
        self.assertEqual(p["overall"], "inconclusive")
        self.assertEqual(code, 3)
        self.assertEqual(p["checks"][0]["status"], "inconclusive")

    def test_official_image_maps_to_library_on_hub(self) -> None:
        # An owner-less official image (ubuntu:latest) is checkable via the Hub library/<name> path
        # even with no inspection tool present. Patch which->None and urlopen so no network is hit.
        captured: dict[str, str] = {}

        class _Resp:
            status = 200

            def __enter__(self) -> _Resp:
                return self

            def __exit__(self, *a: object) -> None:
                return None

        def fake_urlopen(url: str, timeout: int = 15) -> _Resp:
            captured["url"] = url
            return _Resp()

        orig_which, orig_open = ec.shutil.which, ec.urllib.request.urlopen
        ec.shutil.which = lambda _n: None
        ec.urllib.request.urlopen = fake_urlopen
        try:
            status, detail = ec.image_exists("ubuntu:latest")
        finally:
            ec.shutil.which, ec.urllib.request.urlopen = orig_which, orig_open
        self.assertIn("library/ubuntu/tags/latest", captured.get("url", ""))
        self.assertEqual(status, "ok")

    def test_digest_ref_not_routed_to_hub_tag_api(self) -> None:
        # A digest ref (name@sha256:...) can't be validated by the Hub tag API; with no inspection
        # tool present it must stay inconclusive, not build a bogus tag URL.
        orig_which, orig_open = ec.shutil.which, ec.urllib.request.urlopen

        def _boom(*_a: object, **_k: object) -> None:
            raise AssertionError("urlopen must not be called for a digest ref")

        ec.shutil.which = lambda _n: None
        ec.urllib.request.urlopen = _boom
        try:
            status, detail = ec.image_exists("ubuntu@sha256:" + "a" * 64)
        finally:
            ec.shutil.which, ec.urllib.request.urlopen = orig_which, orig_open
        self.assertEqual(status, "inconclusive")

    def test_host_port_registry_not_routed_to_hub(self) -> None:
        # With no inspection tool available, a host:port registry ref (localhost:5000/repo:tag) must
        # NOT be treated as a Docker Hub owner and hit the Hub tag API — it stays inconclusive.
        code, p = self._run(
            {},  # no skopeo/crane/docker on PATH (which defaults to None)
            argv=["image-exists", "localhost:5000/repo:tag"],
        )
        self.assertEqual(p["checks"][0]["status"], "inconclusive")
        self.assertNotIn("hub api", p["checks"][0]["verdict"].lower())
        self.assertEqual(code, 3)

    def test_image_exists_present_is_ok(self) -> None:
        code, p = self._run(
            {"skopeo inspect docker://reg/repo:good": (0, "{}", "")},
            argv=["image-exists", "reg/repo:good"],
            which=lambda name: "/usr/bin/skopeo" if name == "skopeo" else None,
        )
        self.assertEqual(code, 0)
        self.assertEqual(p["checks"][0]["status"], "ok")

    # ---- optional image in a full run ----
    def test_full_run_with_image_flag_includes_image_check(self) -> None:
        _, p = self._run(
            {"skopeo inspect docker://reg/repo:tag": (0, "{}", "")},
            argv=["--image", "reg/repo:tag"],
            which=lambda name: "/usr/bin/skopeo" if name == "skopeo" else None,
        )
        self.assertEqual(self._status_of(p, "image-exists:reg/repo:tag"), "ok")

    def test_json_flag_works_before_the_subcommand(self) -> None:
        # `--json image-exists REF` must emit JSON too (the shared parent parser fix); previously a
        # subparser-local --json shadowed the parent value by argument order.
        def fake_run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
            return (0, "{}", "") if "skopeo inspect docker://reg/repo:good" in " ".join(cmd) else (1, "", "no")
        orig_run, orig_which = ec.run, ec.shutil.which
        ec.run = fake_run
        ec.shutil.which = lambda name: "/usr/bin/skopeo" if name == "skopeo" else None
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = ec.main(["--json", "image-exists", "reg/repo:good"])
            payload = json.loads(out.getvalue())
        finally:
            ec.run, ec.shutil.which = orig_run, orig_which
        self.assertEqual(code, 0)
        self.assertEqual(payload["checks"][0]["status"], "ok")

    # ---- null-safety: malformed kubectl JSON must never crash the run (--json always returns) ----
    def test_null_conditions_across_checks_do_not_crash(self) -> None:
        # status:null / conditions:null on the resources that scan conditions must resolve to a
        # verdict, not raise and abort the whole run.
        code, p = self._run({
            "kubectl get externalsecret -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "es"}, "status": None}]), ""),
            "kubectl get clustersecretstores.external-secrets.io openbao-secret-store -o json": (0, json.dumps({"status": {"conditions": None}}), ""),
            "kubectl get deploy aiwb-api -n aiwb -o json": (0, json.dumps({"status": {"conditions": None, "readyReplicas": None}}), ""),
            "kubectl get pods -A -l app.kubernetes.io/component=csi-driver -o json": (0, _jsonlist([{"metadata": {"namespace": "ns", "name": "csi"}, "status": {"conditions": None}}]), ""),
            "kubectl get pods -n aiwb -o json": (0, _jsonlist([{"metadata": {"name": "p"}, "status": None}]), ""),
        })
        # The run completes and returns a valid overall verdict rather than crashing.
        self.assertIn(p["overall"], {"ok", "problems", "inconclusive", "unreachable"})
        # required-secrets: a not-Ready (null-status) secret is a problem, not a crash.
        self.assertEqual(self._status_of(p, "required-secrets"), "warn")

    def test_unreadable_crd_distinct_from_absent_across_checks(self) -> None:
        # A forbidden CRD read must be reported as unreadable/unconfirmed, not "not detected".
        for crd, check in [
            ("volumes.longhorn.io", "longhorn-health"),
            ("aimclustermodels.aim.eai.amd.com", "aim-profiles"),
            ("aimartifacts.aim.eai.amd.com", "aimartifact-rbac"),
        ]:
            _, p = self._run({f"kubectl get crd {crd}": (1, "", "Error from server (Forbidden): crds is forbidden")})
            self.assertEqual(self._status_of(p, check), "inconclusive")
            verdict = next(c["verdict"] for c in p["checks"] if c["name"] == check)
            self.assertIn("cannot read", verdict.lower())

    # ---- JSON contract shape ----
    def test_json_contract_shape(self) -> None:
        _, p = self._run()
        self.assertIn("overall", p)
        self.assertIn("checks", p)
        for c in p["checks"]:
            self.assertEqual(set(c.keys()), {"name", "status", "verdict", "recommendation"})
            self.assertIn(c["status"], {"ok", "warn", "inconclusive"})
        self.assertIn(p["overall"], {"ok", "problems", "inconclusive", "unreachable"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
