#!/usr/bin/env python3

# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
"""Read-only environment check for a cluster that runs (or will run) the AI Workbench.

Detects known, *silent* platform problems and reports a plain-language verdict per check,
usable before an install (readiness) and after it (in-flight health). It never mutates the
cluster.

Anti-silence contract (the whole reason this exists): a check that CANNOT read the state it
needs returns INCONCLUSIVE, and the overall result is HEALTHY only when EVERY check actively
passed. An unread check is never counted as healthy, so a silent bug can never pass by omission.

Output: human OK / WARN / INCONCLUSIVE lines by default, or a machine-readable verdict with
--json. The JSON contract is stable and consumed by other skills:

    {
      "overall": "ok" | "problems" | "inconclusive" | "unreachable",
      "checks": [ {"name", "status": "ok"|"warn"|"inconclusive", "verdict", "recommendation"} ]
    }

Exit codes: 0 HEALTHY, 1 PROBLEMS FOUND (>=1 warn), 2 CANNOT REACH CLUSTER, 3 INCONCLUSIVE
(no problems but a check could not confirm its state). Only exit 0 is "all clear".

image-exists is also exposed as a subcommand so other lanes can reuse it without duplicating
the private-registry logic:  environment_check.py image-exists <ref>
"""
from __future__ import annotations

import argparse
import datetime
import http.client
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

OK, WARN, INCONCLUSIVE = "ok", "warn", "inconclusive"


@dataclass
class CheckResult:
    name: str
    status: str
    verdict: str
    recommendation: str = ""


def run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a command read-only and return (returncode, stdout, stderr), all stripped.

    A missing binary is returncode 127 and a timeout is 124 — both are surfaced to the caller
    as an inconclusive read rather than being mistaken for a clean result.
    """
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"


def kubectl_json(args: list[str], timeout: int = 30) -> tuple[bool, Any, str]:
    """Run `kubectl <args> -o json` and parse it. Returns (read_ok, parsed_or_None, error).

    read_ok is False when the command failed OR the output did not parse — either way the state
    could not be read, which every caller turns into INCONCLUSIVE (never a pass).
    """
    rc, out, err = run(["kubectl", *args, "-o", "json"], timeout)
    if rc != 0:
        return False, None, err[:160]
    try:
        return True, json.loads(out), ""
    except json.JSONDecodeError as e:
        return False, None, f"unparseable output: {e}"


def _is_not_found(err: str) -> bool:
    """True when a kubectl error definitively means the object does not exist (vs an access/API
    error). A forbidden/timeout read is NOT a confirmed absence and must stay inconclusive."""
    low = err.lower()
    # run() emits "not found: <binary>" when the command itself is missing (e.g. kubectl not on
    # PATH). That is a tooling failure, NOT an object-absent signal — misreading it would drive a
    # check down the "not applicable / OK" path and violate the anti-silence contract.
    if low.startswith("not found:"):
        return False
    # kubectl reports an unregistered resource type (e.g. a CRD whose operator is not installed)
    # as "the server doesn't have a resource type \"X\"" — a confirmed absence, not an access error.
    if "doesn't have a resource type" in low or "could not find the requested resource" in low:
        return True
    return "not found" in low or "notfound" in low.replace(" ", "")


def crd_state(name: str) -> str:
    """Return 'present' | 'absent' | 'unreadable' for a CRD.

    A read that fails for any reason other than a confirmed not-found (RBAC forbidden, timeout,
    missing kubectl, API 500) is 'unreadable' — NOT 'absent'. Collapsing those into a single
    boolean is how a failed read turns into a false "not applicable / healthy" verdict, which the
    anti-silence contract forbids.
    """
    rc, _, err = run(["kubectl", "get", "crd", name], 20)
    if rc == 0:
        return "present"
    return "absent" if _is_not_found(err) else "unreadable"


# --- Null-safe accessors: kubectl -o json fields can be null or the wrong type (e.g. status:null,
# conditions:null while a resource reconciles). Iterating those raises and would abort the whole
# run, breaking the stable --json contract — so every parse goes through these. ---
def _dict(x: Any) -> dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _list(x: Any) -> list[Any]:
    return x if isinstance(x, list) else []


def _conditions(obj: Any) -> list[dict[str, Any]]:
    """Return obj.status.conditions as a list of dict conditions, tolerating null/non-list/non-dict."""
    return [c for c in _list(_dict(_dict(obj).get("status")).get("conditions")) if isinstance(c, dict)]


def _condition_is_true(obj: Any, cond_type: str) -> bool:
    return any(c.get("type") == cond_type and c.get("status") == "True" for c in _conditions(obj))


def _rfc3339_age_seconds(ts: str) -> float | None:
    """Age in seconds of an RFC3339 timestamp (fractional seconds / offsets tolerated), or None."""
    if not ts:
        return None
    try:
        when = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return (datetime.datetime.now(datetime.timezone.utc) - when).total_seconds()


def crd_gate(name: str, check: str, absent_msg: str) -> CheckResult | None:
    """Shared CRD precondition: return an INCONCLUSIVE CheckResult when the CRD is absent (with
    absent_msg) or unreadable (distinct message so the two are never conflated), or None when the
    CRD is present and the caller should proceed."""
    state = crd_state(name)
    if state == "unreadable":
        return CheckResult(check, INCONCLUSIVE, f"cannot read the {name} CRD (RBAC/API error) — state unconfirmed")
    if state == "absent":
        return CheckResult(check, INCONCLUSIVE, absent_msg)
    return None


# --------------------------------------------------------------------------------------------
# Image existence — handles PRIVATE registries correctly: an auth-required response is
# INCONCLUSIVE, not a failure (a Docker Hub tag-API 404 on a private repo is not proof the tag
# is missing). Exposed for reuse by other lanes; do not duplicate this logic.
# --------------------------------------------------------------------------------------------
def image_exists(ref: str) -> tuple[str, str]:
    """Return (status, detail) for a container image reference.

    Prefers a real manifest read (skopeo/crane/docker) and only reports WARN on a definitive
    manifest-unknown/not-found; anything auth-related or otherwise unreadable is INCONCLUSIVE.
    """
    if shutil.which("skopeo"):
        rc, _, err = run(["skopeo", "inspect", f"docker://{ref}"], 60)
        if rc == 0:
            return OK, "manifest present (skopeo)"
        low = err.lower()
        if "manifest unknown" in low or "not found" in low or "manifest for" in low:
            return WARN, f"skopeo: {err[:140]}"
        return INCONCLUSIVE, f"skopeo could not confirm (auth/network?): {err[:140]}"
    if shutil.which("crane"):
        rc, _, err = run(["crane", "manifest", ref], 60)
        if rc == 0:
            return OK, "manifest present (crane)"
        low = err.lower()
        if "manifest unknown" in low or "not found" in low:
            return WARN, f"crane: {err[:140]}"
        return INCONCLUSIVE, f"crane could not confirm (auth/network?): {err[:140]}"
    if shutil.which("docker"):
        rc, _, err = run(["docker", "manifest", "inspect", ref], 60)
        if rc == 0:
            return OK, "manifest present (docker)"
        low = err.lower()
        if "no such manifest" in low or "manifest unknown" in low or "not found" in low:
            return WARN, f"docker manifest: {err[:140]}"
        if "unauthorized" in low or "denied" in low or "authentication" in low:
            return INCONCLUSIVE, "registry auth required (private?) — cannot confirm from here"
        return INCONCLUSIVE, f"docker manifest inconclusive: {err[:140]}"
    # Last resort: the Docker Hub public tag API. Only meaningful for public repos; a 404 here
    # may just mean the repo is private, so it is INCONCLUSIVE, never WARN. A digest ref
    # (name@sha256:...) can't be validated by the tag API — only a manifest tool can — so skip it.
    if ":" in ref and "@" not in ref:
        path, tag = ref.rsplit(":", 1)
        path = path.replace("docker.io/", "").replace("registry-1.docker.io/", "")
        first = path.split("/")[0]
        # Map the ref to a Hub repository path, or None if it isn't a Hub ref:
        #   owner/name -> owner/name   (first component must not be a registry host)
        #   name       -> library/name (official image with no owner)
        # A first component with "." or ":" is a registry host (e.g. ghcr.io, localhost:5000), which
        # the public Hub tag API can't answer for.
        hub_path: str | None = None
        if "/" in path:
            if "." not in first and ":" not in first:
                hub_path = path
        elif "." not in path and ":" not in path:
            hub_path = f"library/{path}"
        if hub_path:
            url = f"https://hub.docker.com/v2/repositories/{hub_path}/tags/{tag}"
            try:
                with urllib.request.urlopen(url, timeout=15) as r:  # noqa: S310 (fixed https host)
                    if r.status == 200:
                        return OK, "tag present (hub api)"
                    return INCONCLUSIVE, f"hub api {r.status}"
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return INCONCLUSIVE, "hub api 404 — repo may be PRIVATE; cannot confirm without registry creds"
                return INCONCLUSIVE, f"hub api {e.code}"
            except urllib.error.URLError as e:
                return INCONCLUSIVE, f"hub api error: {e.reason}"
    return INCONCLUSIVE, "no image-inspection tool available (install skopeo/crane) and not a public hub ref"


def check_image(ref: str) -> CheckResult:
    status, detail = image_exists(ref)
    rec = ""
    if status == WARN:
        rec = "Publish/retag this image or fix the reference to a published tag."
    elif status == INCONCLUSIVE:
        rec = "Confirm with registry creds (skopeo/crane inspect) or verify it pulls on-cluster."
    return CheckResult(f"image-exists:{ref}", status, f"{ref}: {detail}", rec)


# ============================ CLUSTER PLATFORM CHECKS ============================
def check_cilium_mtu() -> CheckResult:
    n = "cilium-mtu"
    state = crd_state("ciliumnodes.cilium.io")
    if state == "unreadable":
        return CheckResult(n, INCONCLUSIVE, "cannot read the ciliumnodes CRD (RBAC/API error) — Cilium MTU state unconfirmed")
    if state == "absent":
        # Confirmed not a Cilium cluster — the download-hang bug is Cilium-specific, so it does not
        # apply. A clean pass (nothing to detect), not an unread check that would block HEALTHY.
        return CheckResult(n, OK, "Cilium not in use (no ciliumnodes.cilium.io CRD) — MTU divergence bug not applicable")
    # The reliable, API-observable signal is whether MTU is pinned cluster-wide in cilium-config.
    # A pinned value eliminates the per-node auto-detect divergence that hangs downloads. The
    # per-node effective MTU itself lives on the node OS (not exposed on ciliumnodes — verified),
    # so an unpinned configuration cannot be certified healthy from the Kubernetes API alone.
    ok, cm, err = kubectl_json(["get", "configmap", "cilium-config", "-n", "kube-system"])
    if not ok:
        return CheckResult(n, INCONCLUSIVE, f"cannot read cilium-config: {err}", "Grant read access to kube-system, then re-run.")
    mtu = _dict(_dict(cm).get("data")).get("mtu", "")
    if mtu and mtu != "0":
        return CheckResult(n, OK, f"MTU pinned cluster-wide to {mtu} in cilium-config — no per-node auto-detect divergence possible")
    return CheckResult(
        n, INCONCLUSIVE,
        "Cilium MTU is auto-detected (cilium-config mtu unset) — effective per-node MTU is not exposed by the Kubernetes API, so divergence and model-download hangs cannot be ruled out",
        "Compare MTU on every node and pin cilium-config mtu cluster-wide before treating the cluster as proven healthy.",
    )


def check_longhorn_health() -> CheckResult:
    n = "longhorn-health"
    gate = crd_gate("volumes.longhorn.io", n, "Longhorn not detected (no volumes.longhorn.io CRD) — shared-storage health unconfirmed via Longhorn")
    if gate:
        return gate
    ok, obj, err = kubectl_json(["get", "volumes.longhorn.io", "-A"])
    if not ok:
        return CheckResult(n, INCONCLUSIVE, f"cannot query Longhorn volumes: {err}")
    items = _list((obj or {}).get("items"))
    if not items:
        return CheckResult(n, OK, "Longhorn present, no volumes provisioned yet — nothing unhealthy")
    bad = []
    for v in items:
        st = _dict(_dict(v).get("status"))
        robustness, state = st.get("robustness", ""), st.get("state", "")
        if not (robustness == "healthy" and state in ("attached", "detached")):
            bad.append(f"{_dict(_dict(v).get('metadata')).get('name', '?')}({robustness or 'unknown'}/{state or 'unknown'})")
    if bad:
        return CheckResult(
            n, WARN,
            f"shared storage is unhealthy — workloads may fail to start or mount. Unhealthy volumes: {', '.join(bad)}",
            "Check the Longhorn UI / nfs-ganesha pods and recover the volumes before deploying workloads.",
        )
    return CheckResult(n, OK, f"all {len(items)} Longhorn volume(s) healthy")


_NON_CSI_PROVISIONER_PREFIXES = ("kubernetes.io/", "rancher.io/local-path")
# A CSI leader-election Lease renews every ~15s; older than this means the holder is not alive.
_LEASE_FRESH_SECONDS = 120


def check_storage_provisioner() -> CheckResult:
    n = "storage-provisioner"
    ok, scobj, err = kubectl_json(["get", "storageclass"])
    if not ok:
        return CheckResult(n, INCONCLUSIVE, f"cannot list StorageClasses: {err}")
    sc_items = _list((scobj or {}).get("items"))
    # Map each StorageClass to its provisioner (the CSI driver name it depends on).
    sc_prov = {_dict(_dict(s).get("metadata")).get("name", "?"): str(_dict(s).get("provisioner") or "") for s in sc_items}
    if not sc_prov:
        return CheckResult(n, INCONCLUSIVE, "no StorageClass found — cannot confirm a working storage provisioner (a workbench install needs one)")
    # A StorageClass with a blank/missing provisioner cannot be correlated to any driver; treating
    # it as fine would pass a class we know nothing about. Collect it as a caveat rather than
    # returning early — a real WARN from a *different* StorageClass must still win and be reported
    # (every problem gets surfaced, never masked by an unrelated unreadable one).
    no_prov = sorted(sc for sc, prov in sc_prov.items() if not prov)
    no_prov_note = (
        f" (also: StorageClass(es) with no usable provisioner field, backing driver unidentifiable: {', '.join(no_prov)})"
        if no_prov else ""
    )

    # Correlate each StorageClass to a *registered* CSI driver, so a healthy but unrelated CSI pod
    # cannot vouch for a StorageClass whose own provisioner is absent. Non-CSI/in-tree provisioners
    # (kubernetes.io/*, rancher.io/local-path) have no CSIDriver object and are exempt (not a false
    # pass).
    ok_cd, cdobj, err_cd = kubectl_json(["get", "csidrivers.storage.k8s.io"])
    if not ok_cd:
        return CheckResult(n, INCONCLUSIVE, f"cannot read csidrivers to correlate StorageClass provisioners: {err_cd}")
    registered = {_dict(_dict(d).get("metadata")).get("name", "") for d in _list((cdobj or {}).get("items"))}
    csi_provs = {
        prov for prov in sc_prov.values()
        if prov and not any(prov.startswith(p) for p in _NON_CSI_PROVISIONER_PREFIXES)
    }
    unbacked = sorted(
        f"{sc} (provisioner {prov})"
        for sc, prov in sc_prov.items()
        if prov in csi_provs and prov not in registered
    )
    if unbacked:
        return CheckResult(
            n, WARN,
            f"StorageClass(es) reference a CSI provisioner that is not a registered CSIDriver — new PVCs will stay Pending: {', '.join(unbacked)}{no_prov_note}",
            "Install/repair the CSI driver for that StorageClass before deploying workloads.",
        )

    # Per-provisioner liveness: a CSI provisioner is live only if its node plugin has registered on
    # at least one node. CSINode.spec.drivers[].name lists exactly that, keyed to the driver name —
    # so this ties liveness to each StorageClass's OWN provisioner, not a global csi-driver pod
    # sweep (which an unrelated Ready pod could satisfy). Without CSINodes we cannot establish the
    # mapping, so the result is inconclusive, never a false OK.
    live_csi = [prov for sc, prov in sc_prov.items() if prov in registered]
    if live_csi:
        ok_cn, cnobj, err_cn = kubectl_json(["get", "csinodes.storage.k8s.io"])
        if not ok_cn:
            return CheckResult(n, INCONCLUSIVE, f"StorageClass provisioners are registered, but cannot read csinodes to confirm each is live: {err_cn}")
        node_registered: set[str] = set()
        for cn in _list((cnobj or {}).get("items")):
            for drv in _list(_dict(_dict(cn).get("spec")).get("drivers")):
                name = _dict(drv).get("name")
                if name:
                    node_registered.add(name)
        not_live = sorted(
            f"{sc} (provisioner {prov})"
            for sc, prov in sc_prov.items()
            if prov in registered and prov not in node_registered
        )
        if not_live:
            return CheckResult(
                n, WARN,
                f"a storage provisioner's node plugin is not registered on any node — new PVCs will stay Pending: {', '.join(not_live)}{no_prov_note}",
                "Restart/repair the CSI node plugin (DaemonSet) for that provisioner before deploying workloads.",
            )

        # Controller liveness: the node plugin registering is not enough — the external-provisioner
        # sidecar (which handles CreateVolume) must be alive. It holds a leader-election Lease named
        # after the driver (e.g. driver-longhorn-io / external-provisioner-leader-<driver>) and
        # renews it every ~15s, so a Lease whose renewTime is recent proves the controller is live
        # NOW. No matching Lease means we cannot establish controller liveness -> inconclusive.
        ok_l, lobj, err_l = kubectl_json(["get", "leases.coordination.k8s.io", "-A"])
        if not ok_l:
            return CheckResult(n, INCONCLUSIVE, f"node plugins registered, but cannot read leases to confirm the provisioner controllers are live: {err_l}")
        # Leases are namespaced, so two namespaces can hold a lease with the same name; keep every
        # lease in a list (not a name-keyed dict, which would drop one duplicate) and pair each with
        # its name for the substring match below.
        all_leases = [(_dict(_dict(le).get("metadata")).get("name", ""), le) for le in _list((lobj or {}).get("items"))]
        stale, unproven = [], []
        for prov in sorted(set(live_csi)):
            dashed = prov.replace(".", "-").replace("/", "-")
            # Match ONLY the external-provisioner (CreateVolume) lease — not the attacher/resizer/
            # snapshotter sidecar leases, which also embed the driver name. A fresh attacher lease
            # must not vouch that the provisioner is live. The provisioner lease is either the bare
            # driver name (e.g. driver-longhorn-io) or an explicit external-provisioner-* lease.
            matched = [
                le for name, le in all_leases
                if name == dashed or (dashed in name and "provisioner" in name)
            ]
            if not matched:
                unproven.append(prov)
                continue
            ages = [_rfc3339_age_seconds(str(_dict(_dict(le).get("spec")).get("renewTime") or "")) for le in matched]
            fresh = [a for a in ages if a is not None and a <= _LEASE_FRESH_SECONDS]
            if not fresh:
                stale.append(prov)
        if stale:
            return CheckResult(
                n, WARN,
                f"a storage provisioner's controller is not renewing its leader lease (not live) — CreateVolume will not run: {', '.join(stale)}{no_prov_note}",
                "Restart/repair the CSI controller (external-provisioner) Deployment for that provisioner.",
            )
        if unproven:
            return CheckResult(
                n, INCONCLUSIVE,
                f"node plugins are live, but no leader lease was found to confirm the CreateVolume controller for: {', '.join(unproven)} — controller liveness unproven{no_prov_note}",
                "Confirm the CSI controller (external-provisioner) is running for that provisioner.",
            )
    csi_ok = sorted(set(live_csi))
    intree = sorted({
        prov for prov in sc_prov.values()
        if prov and any(prov.startswith(p) for p in _NON_CSI_PROVISIONER_PREFIXES)
    })
    parts = []
    if csi_ok:
        parts.append(f"CSI provisioner(s) registered with a live node plugin and controller: {', '.join(csi_ok)}")
    if intree:
        parts.append(f"in-tree/non-CSI provisioner(s) present (not CSI-verifiable): {', '.join(intree)}")
    summary = "; ".join(parts) or f"StorageClass provisioner(s) present: {', '.join(sorted(v for v in sc_prov.values() if v))}"
    if no_prov:
        # Nothing worse was found, but a class we could not identify at all remains unproven.
        return CheckResult(
            n, INCONCLUSIVE,
            f"StorageClass(es) have no usable provisioner field, so their backing driver cannot be identified: {', '.join(no_prov)}. Others checked: {summary}",
            "Verify those StorageClasses and their backing provisioner manually.",
        )
    return CheckResult(n, OK, summary)


def _is_model_download(meta: dict[str, Any]) -> bool:
    """Identify timeout evidence owned by the model-download path, not arbitrary Jobs."""
    labels = _dict(meta.get("labels"))
    annotations = _dict(meta.get("annotations"))
    identity = " ".join(
        [
            str(meta.get("name") or ""),
            *(f"{key}={value}" for key, value in labels.items()),
            *(f"{key}={value}" for key, value in annotations.items()),
        ]
    ).lower()
    return any(marker in identity for marker in ("model-download", "model_downloader", "model-downloader", "artifact-download"))


def check_stuck_storage_pods() -> CheckResult:
    n = "stuck-storage-pods"
    ok, pobj, err = kubectl_json(["get", "pods", "-A", "--field-selector=status.phase=Pending"])
    if not ok:
        return CheckResult(n, INCONCLUSIVE, f"cannot list pods: {err}")
    ok2, eobj, err2 = kubectl_json(["get", "events", "-A", "--field-selector", "reason=FailedMount"])
    if not ok2:
        return CheckResult(n, INCONCLUSIVE, f"cannot list FailedMount events: {err2}")
    ok3, dobj, err3 = kubectl_json(["get", "events", "-A", "--field-selector", "reason=DeadlineExceeded"])
    if not ok3:
        return CheckResult(n, INCONCLUSIVE, f"cannot list DeadlineExceeded events: {err3}")
    ok4, jobj, err4 = kubectl_json(["get", "jobs", "-A"])
    if not ok4:
        return CheckResult(n, INCONCLUSIVE, f"cannot list Jobs for model-download timeouts: {err4}")

    # FailedMount is definitive storage evidence. DeadlineExceeded on an event or failed Job is the
    # durable signal left by a model download that stopped making progress until its active deadline.
    stuck = {
        f"{_dict(_dict(e).get('involvedObject')).get('namespace', '?')}/{_dict(_dict(e).get('involvedObject')).get('name', '?')}"
        for e in _list((eobj or {}).get("items"))
    }
    timed_out = set()
    for event in _list((dobj or {}).get("items")):
        involved = _dict(_dict(event).get("involvedObject"))
        if _is_model_download(involved):
            timed_out.add(f"{involved.get('namespace', '?')}/{involved.get('name', '?')}")
    for job in _list((jobj or {}).get("items")):
        meta = _dict(_dict(job).get("metadata"))
        if _is_model_download(meta) and any(
            c.get("type") == "Failed" and c.get("status") == "True" and c.get("reason") == "DeadlineExceeded"
            for c in _conditions(job)
        ):
            timed_out.add(f"{meta.get('namespace', '?')}/{meta.get('name', '?')}")

    # A Pending pod counts as storage-stuck ONLY when its scheduling condition points at storage
    # (an unbound PVC / volume). A pod Pending for CPU, affinity, or taint reasons is not a storage
    # problem, so it must not be attributed to storage.
    storage_kw = ("persistentvolumeclaim", "unbound", "volume")
    for p in _list((pobj or {}).get("items")):
        for c in _conditions(p):
            if c.get("type") == "PodScheduled" and c.get("status") != "True":
                msg = str(c.get("message") or "").lower()
                if any(k in msg for k in storage_kw):
                    meta = _dict(_dict(p).get("metadata"))
                    stuck.add(f"{meta.get('namespace', '?')}/{meta.get('name', '?')}")
    if stuck or timed_out:
        evidence = []
        if stuck:
            evidence.append(f"storage wait (Pending / FailedMount): {', '.join(sorted(stuck))}")
        if timed_out:
            evidence.append(f"DeadlineExceeded (possible stalled model download): {', '.join(sorted(timed_out))}")
        return CheckResult(
            n, WARN,
            f"workloads are stuck: {'; '.join(evidence)}",
            "Resolve the underlying storage problem; for DeadlineExceeded model downloads, also check cilium-mtu for per-node divergence before retrying.",
        )
    return CheckResult(n, OK, "no workloads stuck waiting on storage or model downloads")


_METRICS_BACKEND_NAMESPACES = ("otel-lgtm-stack", "monitoring", "mimir", "prometheus")


def _discover_metrics_backend() -> str | None:
    """Best-effort discovery of a Prometheus/Mimir query service ('<ns>/<svc>:9090') so a
    kubectl-only probe can query it through the API-server service proxy. None if not found."""
    ok, obj, _ = kubectl_json(["get", "svc", "-A"])
    if not ok:
        return None
    for s in _list((obj or {}).get("items")):
        meta = _dict(_dict(s).get("metadata"))
        ns, name = meta.get("namespace", ""), meta.get("name", "")
        if ns not in _METRICS_BACKEND_NAMESPACES:
            continue
        for port in _list(_dict(_dict(s).get("spec")).get("ports")):
            if _as_int(_dict(port).get("port")) == 9090:
                return f"{ns}/{name}:9090"
    return None


def _prom_instant_query(backend: str, promql: str) -> tuple[bool, Any]:
    """Run an instant PromQL query against '<ns>/<svc>:<port>' via the API-server service proxy
    (read-only, no port-forward). Returns (read_ok, data) where data is Prometheus' `data` object
    (resultType + result); read_ok=False means the query could not be read/parsed."""
    try:
        nssvc, port = backend.rsplit(":", 1)
        ns, svc = nssvc.split("/", 1)
    except ValueError:
        return False, None
    path = (
        f"/api/v1/namespaces/{ns}/services/{svc}:{port}/proxy/api/v1/query"
        f"?query={urllib.parse.quote(promql)}"
    )
    rc, out, _ = run(["kubectl", "get", "--raw", path], 30)
    if rc != 0:
        return False, None
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError:
        return False, None
    if _dict(parsed).get("status") != "success":
        return False, None
    return True, _dict(parsed).get("data")


def _prom_numeric(data: Any) -> float | None:
    """Extract the numeric value from a Prometheus instant-query `data` object, handling both a
    scalar result ([ts, "v"]) and a vector result ([{value: [ts, "v"]}, ...]). None if empty/absent
    — so an empty result vector (no series matched) is distinct from a real 0."""
    rtype = _dict(data).get("resultType")
    result = _dict(data).get("result")
    if rtype == "scalar" and isinstance(result, list) and len(result) == 2:
        return _as_float(result[1])
    if rtype == "vector" and isinstance(result, list) and result:
        val = _dict(result[0]).get("value")
        if isinstance(val, list) and len(val) == 2:
            return _as_float(val[1])
    return None


def _pod_log_signature(namespace: str, pod: str, patterns: tuple[str, ...]) -> tuple[bool, str | None]:
    """Return (read_ok, matched_pattern_or_None). read_ok=False means the logs were unreadable."""
    rc, out, _ = run(["kubectl", "logs", "-n", namespace, pod, "--tail=200"], 30)
    if rc != 0:
        return False, None
    for pat in patterns:
        if pat in out:
            return True, pat
    return True, None


def _active_gpu_workload_present() -> tuple[bool, bool]:
    """(read_ok, present). present is True when a Running pod requests/limits amd.com/gpu — i.e.
    a GPU workload is actually consuming GPUs, so GPU series are expected to exist. On an idle
    cluster (no such pod) a zero series count is legitimate, not a broken pipeline."""
    ok, obj, _ = kubectl_json(["get", "pods", "-A", "--field-selector=status.phase=Running"])
    if not ok:
        return False, False
    for p in _list((obj or {}).get("items")):
        for c in _list(_dict(_dict(p).get("spec")).get("containers")):
            res = _dict(_dict(c).get("resources"))
            for key in ("requests", "limits"):
                if _as_int(_dict(res.get(key)).get("amd.com/gpu", 0)) > 0:
                    return True, True
    return True, False


def check_gpu_metrics(metrics_backend: str | None = None) -> CheckResult:
    n = "gpu-metrics"
    ok, obj, err = kubectl_json(["get", "pods", "-A", "-l", "app.kubernetes.io/name=device-metrics-exporter"])
    if not ok:
        return CheckResult(n, INCONCLUSIVE, f"cannot query the GPU metrics exporter: {err}")
    exporters = _list((obj or {}).get("items"))
    if not exporters:
        return CheckResult(n, INCONCLUSIVE, "GPU metrics exporter not found — no pipeline to check (expected before install or on a cluster without GPUs)")
    # The exporter is a per-node DaemonSet: read EVERY pod, so a single silently-failing node is
    # not masked by a healthy replica. Ready proves nothing — the failure is in the logs.
    for p in exporters:
        meta = _dict(_dict(p).get("metadata"))
        ns = meta.get("namespace", "?")
        name = meta.get("name", "?")
        read_ok, hit = _pod_log_signature(ns, name, ("i/o timeout", "Failed to watch"))
        if not read_ok:
            return CheckResult(n, INCONCLUSIVE, f"exporter pod {ns}/{name} logs are unreadable — cannot confirm it is exporting metrics (do NOT assume Running == healthy)")
        if hit:
            return CheckResult(
                n, WARN,
                f"the GPU metrics exporter ({ns}/{name}) is Running but failing — it cannot reach the kube-apiserver (log signature: '{hit}'), so metric labels are blank and dashboards show no GPU utilization; broken hop: exporter -> kube-apiserver",
                "Restore node -> control-plane network reachability (check Cilium MTU / network policy) for the exporter pod.",
            )
    ok2, cobj, err2 = kubectl_json(["get", "pods", "-n", "otel-lgtm-stack", "-l", "app.kubernetes.io/name=otel-collector"])
    if not ok2:
        return CheckResult(n, INCONCLUSIVE, f"cannot query the OTel collector: {err2} — the exporter->collector scrape hop is unconfirmed")
    collectors = _list((cobj or {}).get("items"))
    if not collectors:
        return CheckResult(n, INCONCLUSIVE, "exporter present but no OTel collector found — the scrape hop that carries GPU metrics to the backend is missing; pipeline health unconfirmed")
    for c in collectors:
        name = _dict(_dict(c).get("metadata")).get("name", "?")
        read_ok, hit = _pod_log_signature("otel-lgtm-stack", name, ("Failed to scrape",))
        if not read_ok:
            return CheckResult(n, INCONCLUSIVE, f"OTel collector {name} logs are unreadable — cannot confirm it is scraping the exporter")
        if hit:
            return CheckResult(
                n, WARN,
                f"the OTel collector ({name}) cannot scrape the GPU metrics exporter (scrape failure), so GPU metrics never reach the backend; broken hop: OTel collector -> exporter",
                "Check the exporter Service/endpoints and the collector's scrape config.",
            )
    # Absence of the known failure signatures is not positive proof; the anti-silence contract
    # (scenario 7) requires proving series actually reach the backend. Query the metrics backend
    # (Prometheus/Mimir) through the API-server service proxy — a read-only kubectl call, no
    # port-forward — for a current GPU series. Prometheus staleness means a non-empty result IS
    # fresh: OK. Empty result -> the pipeline is not delivering -> WARN. Backend not
    # discoverable/reachable -> INCONCLUSIVE (never a pass we did not prove).
    backend = metrics_backend or _discover_metrics_backend()
    if not backend:
        return CheckResult(
            n, INCONCLUSIVE,
            "exporter and collector present with no failure signature, but the metrics backend could not be found to positively confirm delivery",
            "Pass --metrics-backend <ns>/<svc>:<port> (Prometheus/Mimir) so the check can query GPU series freshness.",
        )
    # Require a POSITIVE count of current GPU series that carry a non-blank workload_id — the
    # incident's signature is the exporter losing kube-apiserver access so labels go blank and the
    # UI shows 0 GPU/VRAM even while series technically exist. A count of 0 (or a scalar zero) is
    # therefore NOT a pass.
    read_ok, data = _prom_instant_query(backend, 'count(gpu_gfx_activity{workload_id!=""})')
    if not read_ok:
        return CheckResult(
            n, INCONCLUSIVE,
            f"exporter and collector present with no failure signature, but the metrics backend query ({backend}) failed — delivery unconfirmed",
            "Confirm the metrics backend is reachable / the --metrics-backend target is correct.",
        )
    count = _prom_numeric(data)
    if count is not None and count > 0:
        return CheckResult(n, OK, f"{int(count)} current GPU series with a non-blank workload_id in the backend ({backend}) — exporter/collector healthy and metrics are arriving")

    workload_read_ok, active_workload = _active_gpu_workload_present()
    if not workload_read_ok:
        return CheckResult(
            n, INCONCLUSIVE,
            f"the metrics backend ({backend}) has no current GPU series, but active GPU workloads cannot be read — zero-series health is unconfirmed",
            "Grant read access to running pods, then re-run so the check can distinguish an idle cluster from a broken pipeline.",
        )
    if not active_workload:
        return CheckResult(
            n, OK,
            f"no active GPU workload is running, so zero workload-labelled GPU series in the backend ({backend}) is expected",
        )
    return CheckResult(
        n, WARN,
        f"an active GPU workload is running but no current GPU metrics with a non-blank workload_id are in the backend ({backend}) — series are not reaching it or labels are blank; the pipeline is not delivering",
        "Check the exporter -> kube-apiserver access and the exporter -> collector -> backend scrape path; GPU dashboards will be empty.",
    )


def check_aim_profiles() -> CheckResult:
    n = "aim-profiles"
    gate = crd_gate("aimclustermodels.aim.eai.amd.com", n, "AIM not detected (no aimclustermodels CRD) — cannot check model/GPU profile compatibility")
    if gate:
        return gate
    ok, obj, err = kubectl_json(["get", "aimclustermodels.aim.eai.amd.com", "-A"])
    if not ok:
        return CheckResult(n, INCONCLUSIVE, f"cannot query aimclustermodels: {err}")
    items = _list((obj or {}).get("items"))
    if not items:
        return CheckResult(n, OK, "AIM present, no cluster models defined yet — nothing incompatible")
    unsupported = []       # confirmed NoSupportedProfiles -> WARN
    unproven = []          # condition missing/unparseable or a different not-ready reason -> INCONCLUSIVE
    for m in items:
        # Null-safe against malformed CR data (status: null, conditions: null / not-a-list, non-dict
        # entries) — a parse crash here would abort the whole run and break the --json contract.
        name = _dict(_dict(m).get("metadata")).get("name", "?")
        cond = next((c for c in _conditions(m) if c.get("type") == "ManagedProfilesReady"), None)
        if cond is None:
            unproven.append(f"{name}(no ManagedProfilesReady condition)")
        elif cond.get("status") == "True":
            continue  # affirmatively proven ready
        elif cond.get("reason") == "NoSupportedProfiles":
            unsupported.append(name)
        else:
            unproven.append(f"{name}({cond.get('reason') or 'NotReady'})")
    if unsupported:
        return CheckResult(
            n, WARN,
            f"models cannot be deployed on this hardware — no supported AIM profile matches the cluster's GPUs. Models: {', '.join(unsupported)}. GPU device-id(s) on nodes: {_gpu_device_ids() or 'unknown'}",
            "Onboard an AIM profile for that GPU/partition, or deploy on matching hardware.",
        )
    if unproven:
        # Anti-silence: a model whose readiness we could not affirmatively confirm must NOT be
        # counted as healthy — report it as inconclusive rather than a silent OK.
        return CheckResult(
            n, INCONCLUSIVE,
            f"cannot confirm every model has a supported profile — unresolved: {', '.join(unproven)}",
            "Wait for these aimclustermodels to reconcile, or inspect their ManagedProfilesReady condition.",
        )
    return CheckResult(n, OK, "every cluster model is affirmatively ManagedProfilesReady=True")


def _gpu_device_ids() -> str:
    ok, obj, _ = kubectl_json(["get", "nodes"])
    if not ok:
        return ""
    ids = {
        _dict(_dict(_dict(i).get("metadata")).get("labels")).get("amd.com/gpu.device-id", "")
        for i in _list((obj or {}).get("items"))
    }
    return ", ".join(sorted(x for x in ids if x))


# ============================ E2E-READINESS CHECKS ============================
def _deploy_env(name: str, namespace: str) -> tuple[bool, dict[str, str], str]:
    """Read a deployment's container env without hiding an unreadable deployment."""
    ok, obj, err = kubectl_json(["get", "deploy", name, "-n", namespace])
    if not ok:
        return False, {}, err
    env: dict[str, str] = {}
    containers = _list(_dict(_dict(_dict(_dict(obj).get("spec")).get("template")).get("spec")).get("containers"))
    for c in containers:
        for e in _list(_dict(c).get("env")):
            if isinstance(e, dict) and e.get("name") and e.get("value") is not None:
                env[e["name"]] = e["value"]
    return True, env, ""


def check_aim_route_hostnames() -> CheckResult:
    """Catch the catalog-AIM-deploy failure pre-run: on a multi-listener AIM gateway, aim-engine
    requires spec.routing.hostnames on the effective AIMClusterRuntimeConfig, or the AIMService
    gets no HTTPRoute (ConfigValid=False / RouteHostnameRequired) and catalog AIM deploys fail.
    AIWB's own default runtimeconfig sets hostnames; the failure mode is aim-engine's competing
    default overriding it with none.
    """
    n = "aim-route-hostnames-ready"
    # Resolve gateway + runtimeconfig names from aiwb-api env. Defaults are trustworthy only after
    # the deployment was read successfully; otherwise they could make us inspect unrelated objects.
    env_ok, env, env_err = _deploy_env("aiwb-api", "aiwb")
    if not env_ok:
        return CheckResult(
            n, INCONCLUSIVE,
            f"cannot read aiwb/aiwb-api deployment to resolve gateway/runtimeconfig coordinates: {env_err} — default coordinates were not assumed",
            "Confirm the deployment exists and grant read access, then re-run.",
        )
    gw_ns = env.get("AIM_GATEWAY_NAMESPACE") or "kgateway-system"
    gw_name = env.get("AIM_GATEWAY_NAME") or "https"
    rc_name = env.get("AIM_CLUSTER_RUNTIME_CONFIG_NAME") or "default"

    ok, gw, err = kubectl_json(["get", "gateway", gw_name, "-n", gw_ns])
    if not ok:
        return CheckResult(n, INCONCLUSIVE, f"cannot read the AIM gateway {gw_ns}/{gw_name}: {err}",
                           "Confirm the AIM gateway exists and kube access is available.")
    listeners = _list(_dict(_dict(gw).get("spec")).get("listeners"))
    if len(listeners) <= 1:
        # aim-engine only requires per-route hostnames on a multi-listener gateway.
        return CheckResult(n, OK, f"AIM gateway {gw_ns}/{gw_name} is single-listener — route hostnames not required")

    ok2, rcfg, err2 = kubectl_json(["get", "aimclusterruntimeconfig", rc_name])
    if not ok2:
        return CheckResult(n, INCONCLUSIVE, f"AIM gateway is multi-listener but cannot read AIMClusterRuntimeConfig '{rc_name}': {err2}",
                           "AIM CRDs may be absent or unreadable; cannot confirm routing hostnames.")
    routing = _dict(_dict(_dict(rcfg).get("spec")).get("routing"))
    hostnames = _list(routing.get("hostnames"))
    enabled = routing.get("enabled")
    if enabled and not hostnames:
        return CheckResult(
            n, WARN,
            f"AIM gateway {gw_name} has {len(listeners)} listeners but the effective AIMClusterRuntimeConfig '{rc_name}' has routing enabled with NO hostnames — catalog AIM deploys will fail with RouteHostnameRequired (aim-engine issue #142)",
            "The aim-engine default ClusterRuntimeConfig is likely overriding AIWB's hostname-bearing default; set clusterRuntimeConfig.enable=false on aim-engine so AIWB's 'default' is effective.",
        )
    if enabled is None and not hostnames:
        # routing.enabled omitted: the CRD defaults it to true, so an empty hostnames list may still
        # break catalog deploys — but we cannot read the CRD default from here. Never call this OK on
        # unconfirmed state (anti-silence): the WARN case above proves the exact failure mode.
        return CheckResult(
            n, INCONCLUSIVE,
            f"AIM gateway {gw_name} has {len(listeners)} listeners and the effective AIMClusterRuntimeConfig '{rc_name}' omits routing.enabled with NO hostnames — if the CRD defaults enabled to true, catalog AIM deploys will fail with RouteHostnameRequired",
            "Set routing.enabled explicitly on the effective AIMClusterRuntimeConfig (or add hostnames) so readiness can be confirmed.",
        )
    return CheckResult(n, OK, f"AIMClusterRuntimeConfig '{rc_name}' sets {len(hostnames)} routing hostname(s) on a {len(listeners)}-listener gateway")


def check_required_secrets() -> CheckResult:
    n = "required-secrets"
    ok, obj, err = kubectl_json(["get", "externalsecret", "-n", "aiwb"])
    if not ok:
        return CheckResult(n, INCONCLUSIVE, f"cannot read ExternalSecrets in ns aiwb: {err}", "Ensure read access to the cluster.")
    items = _list((obj or {}).get("items"))
    if not items:
        return CheckResult(n, INCONCLUSIVE, "no ExternalSecrets in ns aiwb yet (cluster not installed / not fully synced?)")
    bad = []
    for i in items:
        conds = _conditions(i)
        if not _condition_is_true(i, "Ready"):
            reason = next((c.get("reason") for c in conds if c.get("type") == "Ready"), None) or "NotReady"
            bad.append(f"{_dict(_dict(i).get('metadata')).get('name', '?')}({reason})")
    if bad:
        return CheckResult(
            n, WARN,
            f"{len(bad)} ExternalSecret(s) not synced: {', '.join(bad)}",
            "The secret backend (OpenBao/ESO) must mint these keys; a SecretSyncedError here blocks aiwb-api.",
        )
    return CheckResult(n, OK, f"all {len(items)} aiwb ExternalSecret(s) synced")


def _secret_state(name: str, namespace: str) -> tuple[str, str]:
    """Return (state, detail) for a secret read, distinguishing present / absent / unreadable.

    state is one of "present", "absent", "unreadable" — an unreadable secret (forbidden, API
    error) is never reported as absent, so a missing-secret WARN is only raised on a confirmed
    not-found.
    """
    rc, out, err = run(["kubectl", "get", "secret", name, "-n", namespace, "-o", "name"], 20)
    if rc == 0 and out:
        return "present", ""
    if rc != 0 and not _is_not_found(err):
        return "unreadable", err[:120]
    return "absent", ""


def check_minio() -> CheckResult:
    n = "minio-ready"
    # AIRM path: the MinIO tenant config secret in the tenant namespace.
    airm_state, airm_err = _secret_state("default-minio-tenant-env-configuration", "minio-tenant-default")
    if airm_state == "unreadable":
        return CheckResult(n, INCONCLUSIVE, f"cannot read the MinIO tenant secret: {airm_err}")
    if airm_state == "absent":
        rc2, _, err2 = run(["kubectl", "get", "ns", "minio-tenant-default"], 15)
        if rc2 != 0 and not _is_not_found(err2):
            return CheckResult(n, INCONCLUSIVE, f"cannot confirm MinIO tenant namespace: {err2[:120]}")
        where = "namespace/secret absent" if rc2 != 0 else "ns exists but env-configuration secret missing"
        return CheckResult(
            n, WARN, f"AIRM MinIO tenant {where} (minio-tenant-default)",
            "AIRM S3 storage tests need the MinIO tenant; provision it or skip S3-data tests.",
        )
    # AIWB path: the per-namespace `minio-credentials` secret is minted PER PROJECT at
    # test time (AIRM's minio-credentials-fetcher ExternalSecret), so it does NOT exist pre-run and
    # is not a pre-run gate. The real pre-run readiness signal is that the OpenBao ClusterSecretStore
    # is Ready, so the fetcher CAN mint minio-credentials (from source keys minio-api-access-key /
    # minio-api-secret-key on openbao-secret-store).
    ok, store, err = kubectl_json(["get", "clustersecretstores.external-secrets.io", "openbao-secret-store"])
    if not ok:
        if _is_not_found(err):
            return CheckResult(
                n, WARN, "OpenBao ClusterSecretStore 'openbao-secret-store' not found — the per-project minio-credentials fetcher cannot mint S3 creds",
                "Ensure ESO + the openbao-secret-store ClusterSecretStore are installed so AIWB S3 secrets can be minted at test time.",
            )
        return CheckResult(n, INCONCLUSIVE, f"AIRM MinIO tenant present, but cannot read the openbao-secret-store ClusterSecretStore: {err}")
    if not _condition_is_true(store, "Ready"):
        return CheckResult(
            n, WARN, "OpenBao ClusterSecretStore 'openbao-secret-store' is not Ready — minio-credentials cannot be minted for projects",
            "Fix the ESO ClusterSecretStore (OpenBao reachability / source keys minio-api-access-key, minio-api-secret-key) before the run.",
        )
    return CheckResult(n, OK, "MinIO tenant secret present and openbao-secret-store Ready (per-project minio-credentials can be minted)")


def check_aimartifact_rbac(test_namespace: str) -> CheckResult:
    n = "aimartifact-rbac"
    gate = crd_gate("aimartifacts.aim.eai.amd.com", n, "AIMArtifact CRD not present (aimartifacts.aim.eai.amd.com) — cannot check create permission")
    if gate:
        return gate
    # `kubectl auth can-i` prints yes/no on stdout as the authoritative answer (and exits non-zero
    # for a definitive "no"), so the stdout answer — not the exit code — is what we read. Some
    # versions prepend a warning line, so take the last non-empty line; anything that is not
    # yes/no means the access review could not be evaluated, which is inconclusive.
    _, out, err = run(["kubectl", "auth", "can-i", "create", "aimartifacts.aim.eai.amd.com", "-n", test_namespace], 20)
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    verdict = lines[-1].strip().lower() if lines else ""
    if verdict not in ("yes", "no"):
        return CheckResult(n, INCONCLUSIVE, f"cannot evaluate AIMArtifact create permission in ns {test_namespace}: {err[:120]}")
    if verdict == "yes":
        return CheckResult(
            n, OK,
            f"current kubectl identity can create AIMArtifacts in ns {test_namespace} — rules out the RBAC-config denial, but not an app-side Forbidden (the check tests the kubectl identity, not the app's runtime path)",
        )
    return CheckResult(
        n, WARN, f"cannot create AIMArtifacts in ns {test_namespace} (Forbidden)",
        "Adapter tests fail with 'Failed to create AIMArtifact CR ...: Forbidden'; grant create on aimartifacts to the test identity in this namespace.",
    )


_E2E_RBAC_ROLE = "e2e-aim-test-author"
# What the E2E suites actually exercise as the test identity, resource -> required verbs. The
# adapter/model/custom-model suites author these CRs with kubectl to stage cases the API cannot
# express, so a missing verb surfaces as a mid-suite Forbidden rather than a setup error.
_E2E_RBAC_REQUIRED: dict[str, set[str]] = {
    "aimartifacts": {"get", "create", "patch"},
    "aimprofiles": {"get", "list"},
    # The custom-model precision rounds read both collections back with kubectl to confirm the
    # project is empty before the next round reuses it, so these need list as well as get.
    "aimmodels": {"get", "list", "create", "patch", "delete"},
    # kubectl patch --subresource=status reads before writing, so the deployed role (and the
    # least-privilege guard) grant get+patch; require both here or a role missing get would pass.
    "aimmodels/status": {"get", "patch"},
    "aimservices": {"get", "list", "create", "patch", "delete"},
}
_AIM_API_GROUP = "aim.eai.amd.com"


def _rule_covers(rule: dict[str, Any], resource: str) -> bool:
    """True when an RBAC rule's apiGroups/resources select this AIM resource.

    Matches the Kubernetes authorizer (ResourceMatches, k8s.io/kubernetes pkg/apis/rbac): a rule
    resource matches on literal ``*``, an exact string match, or the ``*/<subresource>`` form (which
    grants that subresource across all resources). Note there is no ``<parent>/*`` form in RBAC.
    """
    # A resourceNames-restricted rule grants access only to specific named objects. The suites
    # create arbitrary AIM objects (and create itself cannot be name-restricted), so such a rule
    # must not count as satisfying the requirement — otherwise the check is OK while the suite 403s.
    if _list(rule.get("resourceNames")):
        return False
    groups = {str(g) for g in _list(rule.get("apiGroups"))}
    resources = {str(r) for r in _list(rule.get("resources"))}
    if not (_AIM_API_GROUP in groups or "*" in groups):
        return False
    if "*" in resources or resource in resources:
        return True
    # "*/<subresource>" grants that subresource on every resource (the only subresource wildcard RBAC has).
    return "/" in resource and f"*/{resource.split('/', 1)[1]}" in resources


def check_e2e_rbac(expected_oidc_user: str | None = None) -> CheckResult:
    """Assert the E2E test identity is granted what the suites actually do with kubectl.

    A missing ClusterRole here took out ~20 AIWB tests in one night: every case that authors an
    AIM CR failed deep into the suite with a Forbidden that read like a product bug.

    With expected_oidc_user set, the binding must bind that exact user (the cluster's OIDC prefix
    'oidc:' or the legacy 'oidc' form) — otherwise a binding to the WRONG OIDC user would pass. When
    it is None the check keeps the looser "any OIDC user" acceptance for ad-hoc runs.
    """
    n = "eai-e2e-rbac"
    ok, role, err = kubectl_json(["get", "clusterrole", _E2E_RBAC_ROLE])
    if not ok:
        if _is_not_found(err):
            return CheckResult(
                n, WARN,
                f"the E2E test identity has no permissions — ClusterRole '{_E2E_RBAC_ROLE}' does not exist; every test that authors an AIM resource will be refused",
                "Install/upgrade the eai-e2e chart so the E2E RBAC is applied before the suite runs.",
            )
        return CheckResult(n, INCONCLUSIVE, f"cannot read ClusterRole '{_E2E_RBAC_ROLE}': {err}")

    granted: dict[str, set[str]] = {}
    for rule in _list(_dict(role).get("rules")):
        rule = _dict(rule)
        verbs = {str(v) for v in _list(rule.get("verbs"))}
        for resource in _E2E_RBAC_REQUIRED:
            if _rule_covers(rule, resource):
                granted.setdefault(resource, set()).update(verbs)
    missing = {
        resource: sorted(required - granted.get(resource, set()))
        for resource, required in _E2E_RBAC_REQUIRED.items()
        if "*" not in granted.get(resource, set()) and not required <= granted.get(resource, set())
    }
    if missing:
        detail = "; ".join(f"{res} missing {', '.join(verbs)}" for res, verbs in sorted(missing.items()))
        return CheckResult(
            n, WARN,
            f"the E2E test identity is missing permissions the suites use — ClusterRole '{_E2E_RBAC_ROLE}': {detail}",
            "Upgrade the eai-e2e chart so the role grants these verbs; otherwise those tests fail mid-run with Forbidden.",
        )

    ok_b, binding, err_b = kubectl_json(["get", "clusterrolebinding", _E2E_RBAC_ROLE])
    if not ok_b:
        if _is_not_found(err_b):
            return CheckResult(
                n, WARN,
                f"ClusterRole '{_E2E_RBAC_ROLE}' grants the right verbs but no ClusterRoleBinding of that name exists — nothing is bound to the test identity",
                "Install/upgrade the eai-e2e chart so the ClusterRoleBinding is applied.",
            )
        return CheckResult(n, INCONCLUSIVE, f"role is complete, but cannot read ClusterRoleBinding '{_E2E_RBAC_ROLE}': {err_b}")
    ref = _dict(_dict(binding).get("roleRef"))
    if ref.get("kind") != "ClusterRole" or ref.get("name") != _E2E_RBAC_ROLE:
        return CheckResult(
            n, WARN,
            f"ClusterRoleBinding '{_E2E_RBAC_ROLE}' does not reference ClusterRole '{_E2E_RBAC_ROLE}' (points at {ref.get('kind') or '?'}/{ref.get('name') or '?'}) — the test identity does not get these permissions",
            "Correct the binding's roleRef so the E2E permissions actually apply.",
        )
    # The cluster prefixes OIDC users with 'oidc:' (a legacy 'oidc' form is also bound), so any User
    # subject carrying that prefix is an OIDC identity.
    subjects = _list(_dict(binding).get("subjects"))
    users = [str(_dict(s).get("name", "")) for s in subjects if _dict(s).get("kind") == "User"]
    oidc_users = [u for u in users if u.startswith("oidc")]
    if not oidc_users:
        # List every subject (kind/name), not just Users — otherwise a ServiceAccount-only binding
        # renders "(subjects: none)", which misleads someone troubleshooting.
        rendered = ", ".join(f"{_dict(s).get('kind', '?')}/{_dict(s).get('name', '?')}" for s in subjects) or "none"
        return CheckResult(
            n, WARN,
            f"ClusterRoleBinding '{_E2E_RBAC_ROLE}' binds no OIDC user — the E2E test identity is not granted these permissions (subjects: {rendered})",
            "Bind the E2E test user to the role (the eai-e2e chart does this from its configured username).",
        )
    if expected_oidc_user:
        # Require the binding to name THIS user, under either prefix the chart emits. Without this an
        # otherwise-complete binding to a DIFFERENT OIDC user would pass while the real runner 403s.
        wanted = {f"oidc:{expected_oidc_user}", f"oidc{expected_oidc_user}"}
        if not wanted & set(oidc_users):
            return CheckResult(
                n, WARN,
                f"ClusterRoleBinding '{_E2E_RBAC_ROLE}' is not bound to the expected E2E user '{expected_oidc_user}' — bound OIDC users: {', '.join(oidc_users)}",
                "Bind the role to the OIDC user the E2E runner authenticates as, or drop --e2e-oidc-user if any OIDC user is acceptable.",
            )
        return CheckResult(
            n, OK,
            f"the E2E test identity has the permissions the suites use — ClusterRole '{_E2E_RBAC_ROLE}' grants every required verb and is bound to the expected user '{expected_oidc_user}'",
        )
    return CheckResult(
        n, OK,
        f"the E2E test identity has the permissions the suites use — ClusterRole '{_E2E_RBAC_ROLE}' grants every required verb and is bound to {', '.join(oidc_users)}",
    )


_PROJECT_LABEL = "airm.silogen.ai/project-id"
_AIRM_FINALIZER_PREFIX = "airm.silogen.ai/"
_AIRM_DELETION_GRACE_SECONDS = 300


def check_airm_quota_health() -> CheckResult:
    """Detect the dominant AIRM failure path from its residue, without creating anything.

    An AIRM project is a database entity that materialises a labelled namespace plus a Kueue
    ClusterQueue named after it. Two failures strand a whole E2E run: a namespace left half-deleted
    behind an AIRM finalizer PAST a grace window (holding it briefly is normal teardown), and a live
    project whose same-named ClusterQueue is missing or not Active. Both are reported together, and
    an unreadable state is INCONCLUSIVE, never a pass.
    """
    n = "airm-quota-health"
    ok, obj, err = kubectl_json(["get", "namespaces", "-l", _PROJECT_LABEL])
    if not ok:
        return CheckResult(n, INCONCLUSIVE, f"cannot list AIRM project namespaces: {err}")
    projects = _list((obj or {}).get("items"))
    if not projects:
        return CheckResult(n, OK, "no AIRM project namespaces present — nothing stuck deleting and no quota to verify")

    problems: list[str] = []
    unconfirmed: list[str] = []
    live: list[str] = []
    deleting = 0
    for ns in projects:
        meta = _dict(_dict(ns).get("metadata"))
        name = str(meta.get("name", "?"))
        deletion_ts = str(meta.get("deletionTimestamp") or "")
        if not deletion_ts:
            live.append(name)
            continue
        deleting += 1
        held = [str(f) for f in _list(meta.get("finalizers")) if str(f).startswith(_AIRM_FINALIZER_PREFIX)]
        if not held:
            continue
        # Holding an AIRM finalizer during deletion is normal; only past the grace is it "stuck".
        age = _rfc3339_age_seconds(deletion_ts)
        if age is None:
            unconfirmed.append(f"{name}(deletion age unreadable)")
        elif age >= _AIRM_DELETION_GRACE_SECONDS:
            problems.append(f"{name}(stuck deleting; {', '.join(held)})")

    if live:
        ok_q, qobj, err_q = kubectl_json(["get", "clusterqueues.kueue.x-k8s.io"])
        if not ok_q:
            detail = (
                "Kueue ClusterQueues are absent (is Kueue installed?)"
                if _is_not_found(err_q)
                else f"ClusterQueues unreadable: {err_q}"
            )
            unconfirmed.append(f"quota for {len(live)} live project(s): {detail}")
        else:
            queues = {
                str(_dict(_dict(q).get("metadata")).get("name", "")): q
                for q in _list((qobj or {}).get("items"))
            }
            # A project's ClusterQueue carries the project name; Active=True is Kueue's own statement
            # that it can admit work. Zero local quota is NOT flagged — every project queue joins the
            # kaiwo cohort with borrowing enabled, so a zero-quota project borrows (quota_preemption).
            for name in live:
                queue = queues.get(name)
                if queue is None:
                    problems.append(f"{name}(no ClusterQueue)")
                elif not _condition_is_true(queue, "Active"):
                    problems.append(f"{name}(ClusterQueue not Active)")

    if problems:
        suffix = f"; also unconfirmed: {', '.join(unconfirmed)}" if unconfirmed else ""
        return CheckResult(
            n, WARN,
            f"AIRM project lifecycle/quota problems will block the suite: {', '.join(sorted(problems))}{suffix}",
            "For stuck deletion, inspect airm-agent finalizer errors. For missing/inactive quota, inspect airm-agent and the Kueue controller before the run.",
        )
    if unconfirmed:
        return CheckResult(
            n, INCONCLUSIVE,
            f"cannot confirm every AIRM project is healthy: {', '.join(unconfirmed)}",
            "Restore the failed read (if ClusterQueues are absent, confirm Kueue is installed and its controller is running) or inspect the malformed deletion timestamp, then re-run; unconfirmed state is never counted healthy.",
        )
    return CheckResult(
        n, OK,
        f"all {len(live)} live AIRM project namespace(s) have an Active ClusterQueue; {deleting} deleting namespace(s) are within the {_AIRM_DELETION_GRACE_SECONDS}s grace or no longer held by AIRM",
    )


_GATEWAY_MODELS_PATH = "/v1/models"
# Deliberately not a plausible key: it must be rejected, and it must never collide with a real one.
_GATEWAY_INVALID_KEY = "environment-check-invalid-key-expect-401"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse to follow redirects. urllib's default handler replays the Authorization header across
    origins (unlike curl/requests), so a 3xx to another host would leak the bearer key. Returning
    None makes urllib raise the 3xx as an HTTPError instead, which the caller surfaces as a status."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        return None


# Pass an instance (not the class): build_opener replaces the default HTTPRedirectHandler with any
# subclass it is given, so redirects are suppressed either way, but an instance is unambiguous.
_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect())


def _http_status(url: str, bearer: str, timeout: int = 20) -> tuple[int | None, str]:
    """GET url with a Bearer token and return (status_code, error). status_code is None when no
    HTTP response was obtained at all (DNS/TLS/connection failure or a malformed URL), which is
    not a 5xx. Redirects are not followed, so the bearer key never crosses an origin."""
    try:
        # Build the Request inside the try: an invalid URL raises ValueError here, not at open().
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}"}, method="GET")
        with _NO_REDIRECT_OPENER.open(req, timeout=timeout) as r:  # noqa: S310 (scheme validated by caller)
            return int(r.status), ""
    except urllib.error.HTTPError as e:
        # A refused redirect arrives here as its 3xx code; a real 4xx/5xx likewise.
        return int(e.code), ""
    except urllib.error.URLError as e:
        return None, str(e.reason)
    # http.client.HTTPException (BadStatusLine, InvalidURL, ...) and ValueError (a malformed URL from
    # --gateway-url / AI_GATEWAY_URL) are NOT OSError, so without these an odd endpoint would raise
    # out of the eager run_all_checks list and destroy the whole --json contract.
    except (TimeoutError, OSError, http.client.HTTPException, ValueError) as e:
        return None, str(e)


def check_gateway_auth(gateway_url: str | None = None, gateway_key: str | None = None) -> CheckResult:
    """Prove the inference gateway is serving auth decisions rather than failing.

    The invalid-key half needs no credentials: a healthy gateway answers 401. A 5xx instead is the
    stale-certificate breakage, which otherwise surfaces as unexplained inference failures mid-suite.
    """
    n = "gateway-auth"
    if gateway_url:
        url = gateway_url
    else:
        # An unreadable deployment is not the same as one without the variable, and reporting the
        # latter for the former sends the operator looking for a config gap that does not exist.
        env_ok, env, env_err = _deploy_env("aiwb-ui", "aiwb")
        if not env_ok:
            return CheckResult(
                n, INCONCLUSIVE,
                f"cannot read the aiwb-ui deployment to discover the inference gateway address: {env_err} — gateway health unconfirmed",
                "Restore deployment read access or pass --gateway-url <url>.",
            )
        url = env.get("AI_GATEWAY_URL", "")
        if not url:
            # A readable aiwb-ui with no AI_GATEWAY_URL is a confirmed "no inference gateway is
            # wired to this workbench" — there is no gateway to be broken, so this is not-applicable
            # (like cilium-mtu on a non-Cilium cluster), not unproven health. But if the caller
            # supplied a key to validate, they expect a gateway; not finding one is then inconclusive.
            if gateway_key:
                return CheckResult(
                    n, INCONCLUSIVE,
                    "a gateway key was supplied but no inference gateway address could be discovered (aiwb-ui has no AI_GATEWAY_URL) — cannot validate the key",
                    "Pass --gateway-url <url> alongside --gateway-key.",
                )
            return CheckResult(
                n, OK,
                "no inference gateway is configured for this workbench (aiwb-ui has no AI_GATEWAY_URL) — no gateway auth to probe",
            )
    # A scheme-less value (including a bare host:port, which urlparse would misread as a scheme)
    # defaults to https; but a value carrying a NON-http(s) scheme (e.g. file://) must be refused,
    # not passed to the opener — its FileHandler yields a status-less response, and int(None) would
    # raise out of the eager run_all_checks list and destroy the --json contract. A real scheme is
    # exactly the part before "://"; a bare host:port has no "://".
    if url.lower().startswith(("http://", "https://")):
        pass
    elif "://" in url:
        return CheckResult(
            n, INCONCLUSIVE,
            f"the inference gateway address has an unsupported scheme '{url.split('://', 1)[0]}://' — only http/https can be probed",
            "Set --gateway-url / AI_GATEWAY_URL to an http(s) URL.",
        )
    else:
        url = f"https://{url}"
    endpoint = f"{url.rstrip('/')}{_GATEWAY_MODELS_PATH}"

    status, err = _http_status(endpoint, _GATEWAY_INVALID_KEY)
    if status is None:
        # A TLS verification failure is genuinely ambiguous from here: the gateway's certificate may
        # be bad (a real problem), or this host may simply not trust the issuing CA (not one). Saying
        # which would be a guess, so name the ambiguity and how to settle it rather than warning.
        if "certificate_verify_failed" in err.lower().replace(" ", "_"):
            return CheckResult(
                n, INCONCLUSIVE,
                f"the inference gateway at {endpoint} presented a certificate this host does not trust ({err}) — that is either a gateway certificate problem or a missing CA here, and the check cannot tell which",
                "Re-run where the cluster CA is trusted (or compare with `curl -v` from the E2E runner): if the certificate is genuinely stale, inference tests will fail.",
            )
        return CheckResult(n, INCONCLUSIVE, f"the inference gateway at {endpoint} could not be reached: {err} — gateway health unconfirmed",
                           "Confirm the gateway URL is reachable from here (it may only resolve in-cluster).")
    if status >= 500:
        return CheckResult(
            n, WARN,
            f"the inference gateway is not serving requests correctly — it answered {status} to an invalid key instead of refusing it (a certificate/upstream failure, not an auth decision)",
            "Check the gateway's certificate and upstream health before the run; inference tests will fail unexplained.",
        )
    if status != 401:
        return CheckResult(
            n, WARN,
            f"the inference gateway did not refuse an invalid key — it answered {status} where 401 was expected, so key enforcement is not behaving as the tests assume",
            "Check the gateway's auth configuration (ext_authz) before relying on inference test results.",
        )
    if not gateway_key:
        return CheckResult(n, OK, f"the inference gateway refuses an invalid key cleanly (401 from {endpoint})")

    ok_status, ok_err = _http_status(endpoint, gateway_key)
    if ok_status is None:
        return CheckResult(n, INCONCLUSIVE, f"invalid keys are refused, but the valid-key probe could not reach {endpoint}: {ok_err}")
    if ok_status >= 500:
        return CheckResult(
            n, WARN,
            f"the inference gateway refuses invalid keys but answered {ok_status} to a valid key — it is failing to serve authorised requests",
            "Check the gateway's upstream/model routing before the run.",
        )
    # 203 is the ext_authz short-circuit the gateway returns for an authorised models call.
    if ok_status not in (200, 203):
        return CheckResult(
            n, WARN,
            f"the inference gateway rejected the supplied valid key ({ok_status}) — authorised inference calls will fail",
            "Confirm the key is current and authorised for this gateway.",
        )
    return CheckResult(n, OK, f"the inference gateway refuses an invalid key (401) and serves a valid one ({ok_status}) at {endpoint}")


_APP_NAMESPACES = ("aiwb", "airm")
_WAITING_FATAL = ("CrashLoopBackOff", "CreateContainerConfigError", "ImagePullBackOff", "ErrImagePull")
# A pod that has been NotReady longer than this is a real problem; younger than this it is likely
# still starting up or mid-rolling-update, so a bare NotReady is not yet flagged (a fatal waiting
# reason or a restart count still is, immediately, regardless of age).
_NOTREADY_GRACE_SECONDS = 300


def _pod_age_seconds(pod: dict[str, Any]) -> float | None:
    ts = _dict(_dict(pod).get("status")).get("startTime") or _dict(_dict(pod).get("metadata")).get("creationTimestamp")
    if not ts:
        return None
    # Kubernetes timestamps are RFC3339, usually "...Z" at second precision but sometimes with
    # fractional seconds (RFC3339Nano) or a numeric offset. Parse via fromisoformat (which handles
    # fractional seconds and offsets) after normalizing a trailing Z; a parse failure yields None.
    try:
        started = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=datetime.timezone.utc)
    return (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()


def check_app_pods_stable(restart_threshold: int) -> CheckResult:
    """Flag app pods that are not stably running — a container (init or main) waiting in a fatal
    reason (CrashLoopBackOff / CreateContainerConfigError / ImagePullBackOff / ErrImagePull), a
    pod that has stayed NotReady past the startup grace, or a pod that is Ready NOW but has
    crash-looped (restarts over the threshold).

    A Ready pod with a high restart count is the silent case a plain Available check misses: the
    pod recovered but was flapping, which is how a downstream call intermittently 'fetch failed'.
    """
    n = "app-pods-stable"
    problems: list[str] = []
    read_any = False
    for ns in _APP_NAMESPACES:
        ok, obj, err = kubectl_json(["get", "pods", "-n", ns])
        if not ok:
            if _is_not_found(err):
                continue  # namespace not installed yet — nothing to judge here
            return CheckResult(n, INCONCLUSIVE, f"cannot list pods in ns {ns}: {err}")
        read_any = True
        for pod in _list((obj or {}).get("items")):
            meta, status = _dict(_dict(pod).get("metadata")), _dict(_dict(pod).get("status"))
            name = meta.get("name", "?")
            # Skip pods that are meant to run to completion (Jobs), not stay up.
            if status.get("phase") in ("Succeeded", "Failed") and _owned_by_job(meta):
                continue
            # Init containers only complete or fail; a fatal waiting reason on one blocks the pod
            # from ever starting its main containers, so surface it (named as init).
            for c in _list(status.get("initContainerStatuses")):
                wr = _dict(_dict(_dict(c).get("state")).get("waiting")).get("reason", "")
                if wr in _WAITING_FATAL:
                    problems.append(f"{ns}/{name}[init:{_dict(c).get('name', '?')}]={wr}")
            containers = _list(status.get("containerStatuses"))
            if not containers:
                # A pod that never got scheduled has NO containerStatuses at all — the normal shape
                # of a Pending/Unschedulable pod. Skipping it silently would let the check assert
                # "all app pods Running/Ready" while a workload cannot start, so surface it once it
                # is past the startup grace (a just-created pod is still being scheduled).
                # Only when the pod is genuinely NOT scheduled — a scheduled pod with no
                # containerStatuses is running its init containers, already covered above, and
                # labelling it "Unscheduled" would be wrong.
                sched = next((c for c in _conditions(pod) if c.get("type") == "PodScheduled"), None)
                scheduled = sched is not None and sched.get("status") == "True"
                if not scheduled and status.get("phase") not in ("Succeeded", "Failed"):
                    # A pod with no containerStatuses that is not affirmatively scheduled cannot be
                    # certified healthy: it may be genuinely unschedulable or have malformed/empty
                    # conditions. Surface it once past the startup grace rather than falling through
                    # to the all-clear (an old Pending pod with empty conditions must not pass).
                    age = _pod_age_seconds(pod)
                    if age is None or age >= _NOTREADY_GRACE_SECONDS:
                        reason = _dict(sched).get("reason") if sched is not None else None
                        reason = reason or status.get("phase") or "NotScheduled"
                        problems.append(f"{ns}/{name}=Unscheduled({reason})")
                continue
            for c in containers:
                c = _dict(c)
                waiting_reason = _dict(_dict(c.get("state")).get("waiting")).get("reason", "")
                if waiting_reason in _WAITING_FATAL:
                    problems.append(f"{ns}/{name}[{c.get('name', '?')}]={waiting_reason}")
                    continue
                restarts = _as_int(c.get("restartCount", 0))
                if c.get("ready") and restarts >= restart_threshold:
                    last = _dict(_dict(c.get("lastState")).get("terminated"))
                    reason = last.get("reason", "restarted")
                    problems.append(f"{ns}/{name}[{c.get('name', '?')}]=Ready-but-{restarts}-restarts({reason})")
                elif not c.get("ready") and status.get("phase") not in ("Succeeded",):
                    # Don't flag a pod that is still within its startup grace — that is a rollout in
                    # progress, not a fault. An unknown age (no timestamp) errs toward surfacing.
                    age = _pod_age_seconds(pod)
                    if age is None or age >= _NOTREADY_GRACE_SECONDS:
                        problems.append(f"{ns}/{name}[{c.get('name', '?')}]=NotReady")
    if not read_any:
        return CheckResult(n, INCONCLUSIVE, f"no app namespaces present ({', '.join(_APP_NAMESPACES)}) — nothing to check (expected before install)")
    if problems:
        return CheckResult(
            n, WARN,
            f"app pods not stably running: {', '.join(problems)}",
            "A fatal waiting reason blocks the component; a Ready-but-repeatedly-restarted pod was flapping and can cause intermittent downstream failures (e.g. UI 'fetch failed'). Inspect the pod's logs/events and its dependencies.",
        )
    return CheckResult(n, OK, f"all app pods in {', '.join(_APP_NAMESPACES)} Running/Ready with no crash-loop or fatal waiting state")


def _owned_by_job(meta: dict[str, Any]) -> bool:
    return any(_dict(ref).get("kind") == "Job" for ref in _list(_dict(meta).get("ownerReferences")))


def _check_deploy_healthy(name: str, namespace: str, check_name: str) -> CheckResult:
    ok, obj, err = kubectl_json(["get", "deploy", name, "-n", namespace])
    if not ok:
        if _is_not_found(err):
            return CheckResult(check_name, INCONCLUSIVE, f"{name} deployment not found in ns {namespace} (expected before install)")
        return CheckResult(check_name, INCONCLUSIVE, f"cannot read {name} deploy: {err}")
    avail = _condition_is_true(obj, "Available")
    ready = _as_int(_dict(_dict(obj).get("status")).get("readyReplicas", 0))
    if avail and ready:
        return CheckResult(check_name, OK, f"{name} Available (readyReplicas={ready})")
    return CheckResult(
        check_name, WARN,
        f"{name} not Available (readyReplicas={ready})",
        f"Check {name} pod (CreateContainerConfigError => a required secret/config is missing).",
    )


def check_aiwb_api() -> CheckResult:
    return _check_deploy_healthy("aiwb-api", "aiwb", "aiwb-api-healthy")


def check_aiwb_ui() -> CheckResult:
    return _check_deploy_healthy("aiwb-ui", "aiwb", "aiwb-ui-healthy")


def check_gpu_schedulable(require_gpu: bool, test_namespace: str) -> CheckResult:
    n = "gpu-schedulable"
    ok, obj, err = kubectl_json(["get", "nodes"])
    if not ok:
        return CheckResult(n, INCONCLUSIVE, f"cannot read nodes: {err}")
    nodes = _list((obj or {}).get("items"))
    capacity = 0
    allocatable = 0
    for x in nodes:
        st = _dict(_dict(x).get("status"))
        capacity += _as_int(_dict(st.get("capacity")).get("amd.com/gpu", 0))
        allocatable += _as_int(_dict(st.get("allocatable")).get("amd.com/gpu", 0))
    if capacity == 0 and not require_gpu:
        return CheckResult(n, OK, "no GPU nodes on this cluster (amd.com/gpu capacity is 0) — GPU workloads not applicable")
    if allocatable == 0:
        return CheckResult(
            n, WARN,
            f"no amd.com/gpu allocatable (capacity={capacity}) — GPU workloads/tests will stay Pending",
            "Check the AMD GPU Operator: drivers may not have rolled out even though the operator is installed.",
        )
    # GPUs are allocatable; confirm the E2E namespace's own LocalQueue resolves to a ClusterQueue
    # with GPU quota. An unrelated queue elsewhere in the cluster cannot admit jobs from this ns.
    ok2, lqobj, err2 = kubectl_json(["get", "localqueues.kueue.x-k8s.io", "-n", test_namespace])
    if not ok2:
        return CheckResult(
            n, INCONCLUSIVE,
            f"{allocatable} amd.com/gpu allocatable, but Kueue admission for namespace {test_namespace} is unverified (cannot read LocalQueues: {err2})",
            f"Confirm namespace {test_namespace} has a readable LocalQueue bound to a ClusterQueue with amd.com/gpu quota.",
        )
    local_queues = _list((lqobj or {}).get("items"))
    if not local_queues:
        return CheckResult(
            n, WARN,
            f"{allocatable} amd.com/gpu allocatable, but namespace {test_namespace} has no LocalQueue — GPU jobs submitted there will not admit",
            f"Create a LocalQueue in {test_namespace} bound to a ClusterQueue with amd.com/gpu quota.",
        )
    # AIRM binds workloads to the LocalQueue named after the project (queue name == project ==
    # namespace). Select that queue by name; API list order is not a contract, so an arbitrary
    # local_queues[0] could follow an unrelated queue. If the project-named queue is absent, fall
    # back to a sole queue, but treat several unnamed candidates as ambiguous rather than healthy.
    selected = next(
        (q for q in local_queues if _dict(_dict(q).get("metadata")).get("name") == test_namespace),
        None,
    )
    if selected is None:
        if len(local_queues) == 1:
            selected = local_queues[0]
        else:
            names = ", ".join(sorted(_dict(_dict(q).get("metadata")).get("name", "?") for q in local_queues))
            return CheckResult(
                n, INCONCLUSIVE,
                f"namespace {test_namespace} has multiple LocalQueues ({names}) and none is named for the project — cannot tell which admits its GPU jobs",
                f"Name the project LocalQueue {test_namespace}, or point the workloads at a single queue.",
            )
    lq_name = _dict(_dict(selected).get("metadata")).get("name", "?")
    cluster_queue = str(_dict(_dict(selected).get("spec")).get("clusterQueue") or "")
    if not cluster_queue:
        return CheckResult(
            n, WARN,
            f"namespace {test_namespace} LocalQueue {lq_name} has no ClusterQueue binding — GPU jobs will not admit",
            "Set spec.clusterQueue on the LocalQueue to a ClusterQueue with amd.com/gpu quota.",
        )
    ok3, cq, err3 = kubectl_json(["get", "clusterqueues.kueue.x-k8s.io", cluster_queue])
    if not ok3:
        if _is_not_found(err3):
            return CheckResult(
                n, WARN,
                f"namespace {test_namespace} LocalQueue references missing ClusterQueue {cluster_queue} — GPU jobs will not admit",
                "Create the referenced ClusterQueue or update the LocalQueue binding.",
            )
        return CheckResult(
            n, INCONCLUSIVE,
            f"namespace {test_namespace} LocalQueue references ClusterQueue {cluster_queue}, but it cannot be read: {err3}",
            "Grant read access to ClusterQueues, then re-run.",
        )
    cq_spec = _dict(_dict(cq).get("spec"))
    gpu_quota = 0.0
    for rg in _list(cq_spec.get("resourceGroups")):
        for fl in _list(_dict(rg).get("flavors")):
            for res in _list(_dict(fl).get("resources")):
                if _dict(res).get("name") == "amd.com/gpu":
                    gpu_quota += _as_float(_dict(res).get("nominalQuota", 0))
    if gpu_quota <= 0:
        # Zero local quota is only a failure outside a cohort. AIRM project queues join the kaiwo
        # cohort with borrowing enabled, so a zero-quota project admits GPU jobs by borrowing —
        # check_airm_quota_health treats this same shape as healthy, and flagging it here would be a
        # spurious readiness failure contradicting that sibling check.
        cohort = str(cq_spec.get("cohort") or "")
        if not cohort:
            return CheckResult(
                n, WARN,
                f"{allocatable} amd.com/gpu allocatable, but namespace {test_namespace} is bound to ClusterQueue {cluster_queue} with no amd.com/gpu quota and no cohort to borrow from — GPU jobs will not admit",
                f"Add amd.com/gpu nominalQuota to ClusterQueue {cluster_queue}, or join it to a cohort with GPU quota.",
            )
        return CheckResult(
            n, OK,
            f"{allocatable} amd.com/gpu allocatable and namespace {test_namespace} is bound to ClusterQueue {cluster_queue}, which has no local amd.com/gpu quota but borrows from cohort {cohort}",
        )
    return CheckResult(
        n, OK,
        f"{allocatable} amd.com/gpu allocatable and namespace {test_namespace} is bound to ClusterQueue {cluster_queue} with {gpu_quota:g} GPU quota",
    )


def _as_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _as_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ============================ RELEASE-SPEC SKEW ============================
# The E2E specs come from the branch under test, but the services come from whatever release is
# deployed. When the deployed product predates a spec's behaviour, that spec fails permanently on the
# environment. This check proves the relation instead of letting it surface as an assertion failure —
# but only when the caller supplies the spec revision, so it stays opt-in.
#
# For each product, the deployment named below carries the product-code image; its tag is the
# observable deployed marker. It is resolved to a commit in a supplied core checkout and compared by
# ancestry against the spec revision.
_SKEW_PRODUCTS: dict[str, tuple[str, str, str]] = {
    # product: (Deployment, namespace, product container). The chart container names are `aiwb` and
    # `airm`, not the Deployment names. Never fall back to the first container: that can be a sidecar.
    "aiwb": ("aiwb-api", "aiwb", "aiwb"),
    "airm": ("airm-api", "airm", "airm"),
}
# A deployed image tag ending in a git short/long SHA (e.g. main-fdb389c, <branch>-product-de73d50).
# Anchored to the end so it matches the build SHA, not an unrelated hex run earlier in the tag.
_TAG_TRAILING_SHA = re.compile(r"(?:^|[-_./])([0-9a-f]{7,40})$")
# Exact tag-name resolution is allowed only for established release-shaped tags. A bare branch image
# tag (`main`) is mutable and must not resolve to the current branch tip. The repository has used both
# SemVer without a v prefix and legacy calendar releases: vYYYY.MM-rc.N / vYYYY.MM.NNN.
_RELEASE_TAG = re.compile(
    r"^(?:"
    r"[0-9]+\.[0-9]+\.[0-9]+(?:[-.][0-9A-Za-z][0-9A-Za-z.-]*)?"
    r"|v[0-9]{4}\.[0-9]{2}(?:-rc\.[0-9]+|\.[0-9]{3})"
    r")$"
)


def _image_tag(image: str) -> str | None:
    """Return a tag only for an unpinned image reference.

    Any ref containing `@` is digest-pinned. Even `repo:tag@sha256:...` selects the digest, so its tag
    is not provenance for that manifest and cannot be used to infer a source commit.
    """
    if "@" in image:
        return None
    if ":" in image:
        candidate = image.rsplit(":", 1)[1]
        if "/" not in candidate:
            return candidate
    return None


def _selector_arg(selector: Any) -> str | None:
    """Convert a Deployment's matchLabels selector to kubectl's stable key=value form."""
    labels = _dict(_dict(selector).get("matchLabels"))
    if not labels or _dict(selector).get("matchExpressions"):
        return None
    return ",".join(f"{key}={labels[key]}" for key in sorted(labels))


def _pod_is_ready(pod: Any) -> bool:
    return (
        not _dict(_dict(pod).get("metadata")).get("deletionTimestamp")
        and _dict(_dict(pod).get("status")).get("phase") == "Running"
        and _condition_is_true(pod, "Ready")
    )


def _image_digest(image_id: str) -> str | None:
    """Return the sha256 manifest digest from a container status imageID, or None.

    imageID is the manifest the runtime actually pulled (e.g.
    'registry.example.com/product-api@sha256:abcd…' or 'docker-pullable://…@sha256:abcd…'); the
    requested .image tag can drift from it if a registry tag is retargeted. Only the digest identifies
    the running build."""
    marker = "@sha256:"
    idx = image_id.rfind(marker)
    if idx == -1:
        return None
    digest = image_id[idx + 1:]
    return digest if len(digest) > len("sha256:") else None


def _deployed_product_image(name: str, namespace: str, container_name: str) -> tuple[str | None, str]:
    """Return the image tag actually serving a completed Deployment rollout.

    A Deployment template is only desired state. During a rolling update old Ready pods can still
    serve traffic, so require rollout completion and inspect every selected Ready pod. Both the
    requested .image tag AND the running .imageID manifest digest must be identical across every Ready
    pod: a uniform digest rules out a partial retarget where some pods run an older manifest under the
    same tag text. Any incomplete, ambiguous, or mixed state is unconfirmed and must not produce an
    OK/WARN skew verdict.

    Provenance limit: tag text is then resolved to a source commit via the local checkout, which
    trusts the GitOps (Argo) tag->digest binding. This checker is offline and cannot bind the running
    digest to a commit through build attestations, so a registry tag uniformly retargeted to a
    different build of the same name is a known residual gap (closing it needs registry/attestation
    access).
    """
    ok, obj, err = kubectl_json(["get", "deploy", name, "-n", namespace])
    if not ok:
        return None, err
    meta, spec, status = _dict(_dict(obj).get("metadata")), _dict(_dict(obj).get("spec")), _dict(_dict(obj).get("status"))
    generation = _as_int(meta.get("generation"))
    desired = _as_int(spec.get("replicas", 1))
    rollout_complete = (
        desired > 0
        and _as_int(status.get("observedGeneration")) >= generation
        and _as_int(status.get("updatedReplicas")) == desired
        and _as_int(status.get("readyReplicas")) == desired
        and _as_int(status.get("availableReplicas")) == desired
        and _as_int(status.get("unavailableReplicas")) == 0
    )
    if not rollout_complete:
        return None, f"{name} rollout is incomplete; deployed image is not stable"
    selector = _selector_arg(spec.get("selector"))
    if not selector:
        return None, f"{name} has no unambiguous matchLabels pod selector"
    ok_pods, pod_obj, pod_err = kubectl_json(["get", "pods", "-n", namespace, "-l", selector])
    if not ok_pods:
        return None, f"cannot read {name} pods: {pod_err}"
    pods = [pod for pod in _list(_dict(pod_obj).get("items")) if _pod_is_ready(pod)]
    if len(pods) != desired:
        return None, f"{name} has {len(pods)} Ready serving pod(s), expected {desired}; rollout state is ambiguous"
    images: set[str] = set()
    digests: set[str] = set()
    for pod in pods:
        statuses = [
            _dict(item) for item in _list(_dict(_dict(pod).get("status")).get("containerStatuses"))
            if _dict(item).get("name") == container_name
        ]
        pod_name = _dict(_dict(pod).get("metadata")).get("name", "?")
        if len(statuses) != 1 or not statuses[0].get("image"):
            return None, f"Ready pod {pod_name} does not expose exactly one {container_name!r} product container image"
        images.add(str(statuses[0]["image"]))
        digest = _image_digest(str(statuses[0].get("imageID") or ""))
        if digest is None:
            return None, f"Ready pod {pod_name} exposes no running image digest for {container_name!r} — cannot confirm the serving manifest"
        digests.add(digest)
    if len(images) != 1:
        return None, f"{name} Ready pods serve mixed product images: {', '.join(sorted(images))}"
    if len(digests) != 1:
        return None, f"{name} Ready pods serve one tag but different running manifests (retarget in progress): {', '.join(sorted(digests))}"
    return next(iter(images)), ""


def _git(repo: str, args: list[str], timeout: int = 20) -> tuple[bool, str, str]:
    rc, out, err = run(["git", "-C", repo, *args], timeout)
    return rc == 0, out, err


def _resolve_tag_to_commit(repo: str, tag: str) -> tuple[str | None, str]:
    """Resolve a deployed image tag to a commit in the core repo, using only IMMUTABLE markers so a
    later comparison is trustworthy: an annotated/lightweight release tag under refs/tags (e.g.
    2.0.2-rc.3), else a git short/long SHA embedded at the end of the tag (main-<sha>,
    <branch>-product-<sha>). A bare branch name is deliberately NOT accepted — the image workflows
    publish moving branch tags, and resolving `main` to the current branch tip instead of the build
    commit would silently compare the wrong revision. Returns (commit, detail) or (None, reason).
    """
    # refs/tags/<tag> only, and only for release-shaped names: a tag named `main` is itself mutable
    # in image-publishing practice, even though Git stores it under refs/tags.
    if _RELEASE_TAG.fullmatch(tag):
        ok, out, _ = _git(repo, ["rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"])
        if ok and out:
            return out, f"release tag {tag}"
    m = _TAG_TRAILING_SHA.search(tag)
    if m:
        sha = m.group(1)
        # A short SHA is immutable content, but rev-parse would also happily resolve a branch/tag
        # whose *name* is all hex. Require the resolved object to be a commit reachable as a SHA, and
        # confirm the token really is an object id (not a ref name) by checking it as a commit-ish.
        ok2, out2, _ = _git(repo, ["rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"])
        if ok2 and out2 and out2.startswith(sha):
            return out2, f"commit {sha} (from image tag {tag})"
    return None, f"image tag {tag!r} does not resolve to an immutable release tag or commit in the core repo"


def _is_shallow(repo: str) -> bool | None:
    """Whether the checkout has truncated history. None means Git could not establish it, which is
    also inconclusive because a negative ancestry answer would then be unsafe to trust."""
    ok, out, _ = _git(repo, ["rev-parse", "--is-shallow-repository"])
    if not ok or out.strip() not in ("true", "false"):
        return None
    return out.strip() == "true"


def _is_ancestor(repo: str, ancestor: str, descendant: str, shallow: bool) -> bool | None:
    """True when `ancestor` is an ancestor of (or equal to) `descendant`. None means indeterminate —
    a git error (rc not 0/1), OR a negative answer in a shallow repo, where history beyond the
    boundary could still contain the ancestor. An indeterminate answer must never become a false
    OK/WARN, so callers route it to INCONCLUSIVE."""
    rc, _, _ = run(["git", "-C", repo, "merge-base", "--is-ancestor", ancestor, descendant], 20)
    if rc == 0:
        return True
    if rc == 1:
        # In a full clone rc=1 is definitive "not an ancestor"; in a shallow clone it may only mean
        # "not within the fetched history", which is not proof.
        return None if shallow else False
    return None


def check_release_spec_skew(spec_revision: str, core_repo: str) -> CheckResult:
    """Warn when a deployed product predates the specs about to run against it.

    Opt-in: only invoked when --spec-revision is given. Anti-silence: any unresolvable input, image,
    tag, or comparison is INCONCLUSIVE, never a false OK or WARN.
    """
    n = "release-spec-skew"
    ok_repo, _, err_repo = _git(core_repo, ["rev-parse", "--is-inside-work-tree"])
    if not ok_repo:
        return CheckResult(
            n, INCONCLUSIVE,
            f"--core-repo {core_repo!r} is not a readable git repository: {err_repo[:120]} — cannot compare deployed to spec",
            "Point --core-repo at a core checkout that contains the release history.",
        )
    ok_spec, spec_commit, _ = _git(core_repo, ["rev-parse", "--verify", "--quiet", f"{spec_revision}^{{commit}}"])
    if not (ok_spec and spec_commit):
        return CheckResult(
            n, INCONCLUSIVE,
            f"the spec revision {spec_revision!r} does not resolve in --core-repo — cannot establish what the tests require",
            "Pass a --spec-revision present in --core-repo (fetch it first if the checkout is shallow).",
        )

    shallow = _is_shallow(core_repo)
    if shallow is None:
        return CheckResult(
            n, INCONCLUSIVE,
            "cannot establish whether --core-repo has complete history — ancestry results would be unsafe to trust",
            "Use a readable full core checkout, then re-run.",
        )
    problems: list[str] = []
    unconfirmed: list[str] = []
    confirmed: list[str] = []
    for product, (deploy, ns, container_name) in sorted(_SKEW_PRODUCTS.items()):
        image, ierr = _deployed_product_image(deploy, ns, container_name)
        if image is None:
            if _is_not_found(ierr):
                unconfirmed.append(f"{product}: {deploy} not deployed in ns {ns}")
            else:
                unconfirmed.append(f"{product}: cannot read {deploy} image ({ierr[:80]})")
            continue
        tag = _image_tag(image)
        if not tag:
            unconfirmed.append(f"{product}: {deploy} runs a digest-pinned or untagged image with no trusted commit provenance")
            continue
        deployed_commit, detail = _resolve_tag_to_commit(core_repo, tag)
        if deployed_commit is None:
            unconfirmed.append(f"{product}: {detail}")
            continue
        spec_in_deployed = _is_ancestor(core_repo, spec_commit, deployed_commit, shallow)
        if spec_in_deployed is None:
            reason = "checkout is shallow" if shallow else "git error"
            unconfirmed.append(f"{product}: cannot compare deployed {tag} to the spec revision ({reason})")
            continue
        if spec_in_deployed:
            confirmed.append(f"{product} ({detail})")
            continue
        deployed_in_spec = _is_ancestor(core_repo, deployed_commit, spec_commit, shallow)
        if deployed_in_spec is None:
            reason = "checkout is shallow" if shallow else "git error"
            unconfirmed.append(f"{product}: cannot establish the relationship between deployed {tag} and the spec revision ({reason})")
        elif deployed_in_spec:
            problems.append(
                f"{product}: deployed {tag} ({deployed_commit[:9]}) predates the spec revision "
                f"{spec_revision} ({spec_commit[:9]}) — specs written for newer behaviour will fail"
            )
        else:
            problems.append(
                f"{product}: deployed {tag} ({deployed_commit[:9]}) has diverged from the spec revision "
                f"{spec_revision} ({spec_commit[:9]}) — it does not contain those specs' behaviour"
            )

    if problems:
        suffix = f"; also unconfirmed: {', '.join(unconfirmed)}" if unconfirmed else ""
        return CheckResult(
            n, WARN,
            f"a deployed product is out of sync with the specs about to run: {'; '.join(problems)}{suffix}",
            "Deploy a build that contains the spec revision (or run the specs from the deployed release's branch) before the suite.",
        )
    if unconfirmed:
        return CheckResult(
            n, INCONCLUSIVE,
            f"cannot confirm every deployed product contains the spec revision: {', '.join(unconfirmed)}",
            "Restore the failed read, or ensure --core-repo contains the deployed tags/commits, then re-run.",
        )
    return CheckResult(
        n, OK,
        f"every deployed product contains the spec revision {spec_revision}: {', '.join(confirmed)}",
    )


# ============================ RUNNER ============================
def aggregate_overall(results: list[CheckResult]) -> str:
    statuses = {r.status for r in results}
    if WARN in statuses:
        return "problems"
    if INCONCLUSIVE in statuses:
        return "inconclusive"
    return "ok"


_OVERALL_EXIT = {"ok": 0, "problems": 1, "unreachable": 2, "inconclusive": 3}
_HUMAN_LABEL = {OK: "OK          ", WARN: "WARN        ", INCONCLUSIVE: "INCONCLUSIVE"}


def run_all_checks(images: list[str], require_gpu: bool, test_namespace: str, restart_threshold: int,
                   metrics_backend: str | None = None, gateway_url: str | None = None,
                   gateway_key: str | None = None, e2e_oidc_user: str | None = None,
                   spec_revision: str | None = None, core_repo: str = ".") -> list[CheckResult]:
    results = [
        check_cilium_mtu(),
        check_longhorn_health(),
        check_storage_provisioner(),
        check_stuck_storage_pods(),
        check_gpu_metrics(metrics_backend),
        check_aim_profiles(),
        check_app_pods_stable(restart_threshold),
        check_required_secrets(),
        check_minio(),
        check_aimartifact_rbac(test_namespace),
        check_e2e_rbac(e2e_oidc_user),
        check_airm_quota_health(),
        check_gateway_auth(gateway_url, gateway_key),
        check_aim_route_hostnames(),
        check_aiwb_api(),
        check_aiwb_ui(),
        check_gpu_schedulable(require_gpu, test_namespace),
    ]
    # Opt-in: the deployed-vs-spec skew check runs only when the caller states which spec revision
    # will run, so an ordinary readiness run is unaffected.
    if spec_revision:
        results.append(check_release_spec_skew(spec_revision, core_repo))
    results.extend(check_image(ref) for ref in images)
    return results


def emit(results: list[CheckResult], overall: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps(
            {"overall": overall, "checks": [r.__dict__ for r in results]},
            indent=2,
        ))
        return
    print("== Cluster environment check ==")
    for r in results:
        print(f"{_HUMAN_LABEL[r.status]} {r.name}: {r.verdict}")
        if r.recommendation and r.status != OK:
            print(f"             -> {r.recommendation}")
    warns = sum(1 for r in results if r.status == WARN)
    inconc = sum(1 for r in results if r.status == INCONCLUSIVE)
    print(f"\nSUMMARY: warnings={warns} inconclusive={inconc}")
    print(f"RESULT: {overall.upper()}")


def main(argv: list[str] | None = None) -> int:
    # --json lives on a shared parent parser so it is accepted both before the subcommand and after
    # `image-exists REF` — a single subparser copy would otherwise shadow the parent value by order.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="Emit a machine-readable verdict.")
    ap = argparse.ArgumentParser(description="Read-only AI Workbench cluster environment check.", parents=[common])
    sub = ap.add_subparsers(dest="subcommand")
    img = sub.add_parser("image-exists", parents=[common], help="Check one container image reference and exit (reusable by other lanes).")
    img.add_argument("ref")
    skew = sub.add_parser("release-spec-skew", parents=[common], help="Check whether deployed AIRM/AIWB builds contain one core spec revision.")
    skew.add_argument("spec_revision", metavar="REV")
    # No default here: --core-repo shares its dest with the top-level flag, so a concrete default would
    # overwrite a value the user passed BEFORE the subcommand. SUPPRESS makes the subparser set
    # core_repo only when --core-repo is given after the subcommand; otherwise the top-level value (or
    # its "." default) stands.
    skew.add_argument("--core-repo", default=argparse.SUPPRESS, metavar="PATH",
                      help="Core git checkout containing REV and deployed release tags/commits (defaults to the top-level --core-repo, i.e. the current directory).")
    ap.add_argument("--image", action="append", default=[], metavar="REF",
                    help="Also check that this image reference resolves (repeatable).")
    ap.add_argument("--require-gpu", action="store_true",
                    help="Treat 0 allocatable GPUs as a problem even on a cluster with no GPU nodes (for GPU E2E lanes).")
    ap.add_argument("--test-namespace", default="e2e-apiserver-testing", metavar="NS",
                    help="Namespace the E2E tests run in, checked for AIMArtifact create permission (default: e2e-apiserver-testing).")
    ap.add_argument("--restart-threshold", type=int, default=3, metavar="N",
                    help="app-pods-stable warns when a Ready app pod has restarted at least N times (default: 3).")
    ap.add_argument("--metrics-backend", default=None, metavar="NS/SVC:PORT",
                    help="Prometheus/Mimir query service for gpu-metrics to positively confirm GPU series arrive (e.g. otel-lgtm-stack/lgtm-stack:9090). Auto-discovered if omitted.")
    ap.add_argument("--gateway-url", default=None, metavar="URL",
                    help="Inference gateway base URL for gateway-auth. Auto-discovered from the aiwb-ui deployment if omitted.")
    ap.add_argument("--gateway-key", default=None, metavar="KEY",
                    help="A valid inference API key. When given, gateway-auth also confirms an authorised call succeeds (the invalid-key probe needs no key).")
    ap.add_argument("--e2e-oidc-user", default=None, metavar="USER",
                    help="The OIDC username the E2E runner authenticates as. When given, eai-e2e-rbac requires the role binding to name exactly this user (else any OIDC user is accepted).")
    ap.add_argument("--spec-revision", default=None, metavar="REV",
                    help="The core commit/ref whose specs will run. When given, release-spec-skew warns if a deployed product predates it. Requires --core-repo to contain that revision and the deployed tags.")
    ap.add_argument("--core-repo", default=".", metavar="PATH",
                    help="Path to a core git checkout used to resolve deployed image tags and --spec-revision to commits for the release-spec-skew check (default: current directory).")
    args = ap.parse_args(argv)

    if args.subcommand == "image-exists":
        result = check_image(args.ref)
        overall = {OK: "ok", WARN: "problems", INCONCLUSIVE: "inconclusive"}[result.status]
        emit([result], overall, getattr(args, "json", False))
        return _OVERALL_EXIT[overall]

    if args.subcommand == "release-spec-skew":
        result = check_release_spec_skew(args.spec_revision, args.core_repo)
        overall = {OK: "ok", WARN: "problems", INCONCLUSIVE: "inconclusive"}[result.status]
        emit([result], overall, getattr(args, "json", False))
        return _OVERALL_EXIT[overall]

    # Connectivity gate — no cluster access is reported clearly and NEVER as healthy.
    if run(["kubectl", "cluster-info"], 20)[0] != 0:
        conn = CheckResult(
            "connectivity", INCONCLUSIVE,
            "cannot reach the cluster — kubectl cannot talk to the API server",
            "Fix kubeconfig / context / network access, then re-run. No checks could run, so health is UNKNOWN.",
        )
        emit([conn], "unreachable", getattr(args, "json", False))
        return _OVERALL_EXIT["unreachable"]

    results = run_all_checks(args.image, args.require_gpu, args.test_namespace, args.restart_threshold,
                             args.metrics_backend, args.gateway_url, args.gateway_key, args.e2e_oidc_user,
                             args.spec_revision, args.core_repo)
    overall = aggregate_overall(results)
    emit(results, overall, getattr(args, "json", False))
    return _OVERALL_EXIT[overall]


if __name__ == "__main__":
    sys.exit(main())
