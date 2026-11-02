---
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
name: cluster-environment-check
description: Checks a Kubernetes cluster for known, silent AI Workbench platform problems and reports a plain-language or JSON verdict — for install, in-flight, and E2E readiness. Flags Cilium MTU left unpinned (the model-download-hang risk), unhealthy shared storage and dead provisioners, stuck workloads, a broken GPU-metrics pipeline, app pods that look Running but crash-loop or silently fail, GPUs with no matching AIM profile, unsynced secrets, MinIO gaps, unhealthy AIWB API/UI, AIM route-hostname gaps, GPUs Kueue can't schedule, an E2E test identity missing the permissions its suites use, AIRM projects stuck deleting or lacking scheduling quota, an inference gateway erroring instead of refusing bad keys, and deployed AIRM/AIWB builds older than the specs about to run; also verifies images exist. Use when a user wants to check or troubleshoot cluster readiness or health for the AI Workbench, or asks why model downloads hang, storage won't mount, GPU metrics are missing, a model won't deploy, or an E2E suite failed on permissions, version skew, or timed out waiting for workloads. Use PROACTIVELY before an AIWB install, before running an E2E suite, and when triaging a cluster acting as if a component is silently failing. Do NOT activate for actually installing/deploying AIWB, onboarding models to AIM, or general kubectl/helm use unrelated to platform bugs.
allowed-tools: Bash, Read, Grep, Glob
---

# Cluster Environment Check

This is an AI instruction file. Follow it to check a Kubernetes cluster for known AI Workbench
platform problems and report a plain-language verdict an operator can act on.

The problems this skill finds are **silent**: a pod shows `Running`, metrics read zero, no error
surfaces — and the same multi-person confusion recurs each time. Your job is to run the read-only
checker, then translate its findings into what is wrong, why it matters, and the concrete fix.
**Never report a cluster healthy unless the checker actively proved every check passed** — an
unread check is not a pass.

## What this runs against

The checker uses `kubectl` with **the operator's own kubeconfig** — whatever cluster the current
context points at. It works both **before** a workbench install (readiness: is this cluster fit to
install onto?) and **after** (in-flight: is the running environment healthy?). Checks that are only
meaningful post-install (stuck workloads, GPU metrics, secrets, AIWB API/UI) report inconclusive
when the component isn't there yet, never a false failure. The checker only reads; it never mutates
the cluster.

The implementation is `scripts/environment_check.py` (the `.sh` entrypoint is a thin wrapper). It is
importable, so other lanes reuse its checks — e.g. `from environment_check import image_exists` — and
it exposes a stable `--json` verdict for automated gates.

Confirm a cluster is selected before running:

```bash
kubectl config current-context
```

If that fails or points at the wrong cluster, fix the kubeconfig/context first — the checker
cannot diagnose a cluster it cannot reach.

## Step 1 — Run the check

```bash
bash .agents/skills/cluster-environment-check/scripts/environment-check.sh
```

It runs every check, prints one `OK` / `WARN` / `INCONCLUSIVE` line per finding, and ends with a
`RESULT:` line. The exit code is the contract:

- **`0` HEALTHY** — every check actively passed. No known platform problems.
- **`1` PROBLEMS FOUND** — at least one `WARN`. Each problem line names the cause and the fix.
- **`2` CANNOT REACH CLUSTER** — kubectl cannot talk to the API server. Not a healthy result.
- **`3` INCONCLUSIVE** — no problems found, but a check could not read the state it needed. **Not
  a healthy result** — it means "not proven healthy," not "healthy with notes."

Useful flags:

- **`--json`** — emit a machine-readable verdict instead of human lines, for an automated gate to
  consume: `{"overall": "ok"|"problems"|"inconclusive"|"unreachable", "checks": [{name, status,
verdict, recommendation}]}`. Per-check `status` is `ok`/`warn`/`inconclusive`; the exit code is
  unchanged. In the `unreachable` case `checks` is a single synthetic `connectivity` entry with
  `status: "inconclusive"` — a gate should key off `overall`, not assume a fixed check list.
- **`--image REF`** (repeatable) — also verify a container image reference resolves as part of the
  run (e.g. an image an install/E2E depends on).
- **`--require-gpu`** — treat zero allocatable GPUs as a problem even on a cluster with no GPU nodes
  (for GPU E2E lanes that must have GPUs).
- **`--test-namespace NS`** (default `e2e-apiserver-testing`) — the namespace the E2E tests run in,
  checked for permission to create AIMArtifacts. Point it at the lane's real test namespace.
- **`--restart-threshold N`** (default `3`) — `app-pods-stable` warns when a Ready app pod has
  restarted at least N times (the crash-loop/flapping signal).
- **`--metrics-backend NS/SVC:PORT`** — the Prometheus/Mimir query service `gpu-metrics` queries to
  positively confirm GPU series arrive (e.g. `otel-lgtm-stack/lgtm-stack:9090`). Auto-discovered
  from a `:9090` service in a metrics namespace if omitted.
- **`--gateway-url URL`** — the inference gateway `gateway-auth` probes. Auto-discovered from the
  `aiwb-ui` deployment's `AI_GATEWAY_URL` if omitted.
- **`--gateway-key KEY`** — a valid inference API key. Optional: the invalid-key probe (a healthy
  gateway answers 401) needs no credentials, so `gateway-auth` runs without this. Supplying it adds
  the authorised half — a valid key must return 200/203.
- **`--e2e-oidc-user USER`** — the OIDC username the E2E runner authenticates as. When given,
  `eai-e2e-rbac` requires the role binding to name exactly this user; omit it to accept any OIDC user.
- **`--spec-revision REV --core-repo PATH`** — opt in to `release-spec-skew`: compare the deployed
  AIRM/AIWB service-image commits with the core revision whose specs will run. `PATH` must be a core
  Git checkout containing `REV` and the deployed release tags/commits (default: current directory).
  A deployed ancestor/diverged commit is a `WARN`; a tag or revision that cannot resolve is
  `INCONCLUSIVE`, never a false pass. Callers should pass the exact checked-out SHA, not a moving ref.

To run one focused check without the full cluster suite:

```bash
# One image reference:
bash .agents/skills/cluster-environment-check/scripts/environment-check.sh image-exists <ref> [--json]

# Deployed products against one spec revision:
bash .agents/skills/cluster-environment-check/scripts/environment-check.sh \
  release-spec-skew <spec-revision> --core-repo <path> [--json]
```

A definitive image "manifest not found" is a `WARN`; an auth-required/unreadable registry is
`INCONCLUSIVE` (a private repo is not proof the tag is missing), never a false failure. The focused
skew command returns the same per-check JSON and exit-code contract as its opt-in full-run form.

## Step 2 — Report the verdict honestly

Pick the honest outcome — the anti-silence rule is the whole point of this skill:

- **HEALTHY (0):** report that no known problems were found, and name what was checked so the
  operator knows the scope (it does not prove the cluster is perfect, only that these known bugs
  are absent).
- **PROBLEMS FOUND (1):** for each `WARN`, relay the plain-English problem, why it matters, and the
  fix the line names. Report **every** problem, not just the first — several can be present at once.
- **CANNOT REACH CLUSTER (2):** say the cluster is unreachable and help fix access. Never soften
  this into a healthy or empty result.
- **INCONCLUSIVE (3):** say plainly that the cluster is **not proven healthy** and name each check
  that could not confirm its state and why (usually a CRD is absent because the component isn't
  installed, or RBAC/an API error blocked a read). Do not present an inconclusive run as a pass.

To understand what each check reads, what a finding means, and which findings are expected before
vs. after install, read `references/checks.md`.

- `references/checks.md` — What each check inspects, the known bug behind it, and how to interpret
  OK / WARN / INCONCLUSIVE per check. **Load when** interpreting a finding or deciding whether an
  inconclusive result is expected for the cluster's install state.

## Intended consumers (other lanes)

This skill is meant to be the single home for these check implementations, so other work can consume
it rather than duplicate the logic. These consumers are being built separately (they do not live in
this repo yet):

- An E2E-readiness gate is intended to run the full check with `--json` (plus `--image` /
  `--require-gpu` as needed) and read the single `overall` verdict.
- A pre-bloom precheck is intended to reuse `image-exists` (subcommand or `image_exists()` import)
  instead of keeping its own registry-inspection copy.
- A deployment-triggered E2E gate can pass its checked-out core SHA as `--spec-revision` and stage a
  core checkout at `--core-repo`. That opts into a pre-assertion check that the deployed AIRM/AIWB
  builds contain the behavior described by those specs.

Keep the `--json` shape, `image-exists` interface, and `release-spec-skew` check name stable — they
are the contract those consumers will depend on.

## Tests

The stable test command runs two hermetic layers with no cluster or registry access:

```bash
bash .agents/skills/cluster-environment-check/tests/run-tests.sh
```

- Python regression tests stub the checker’s one side-effecting primitive (`run()`) and pin every
  false-pass edge.
- Robot Framework executable specifications in `specs/environment_check.robot` invoke the shipped
  shell/Python CLI as a black box. A fixture-backed `kubectl` executable supplies complete cluster
  transcripts, so the tests verify real JSON, exit-code, and operator-visible verdict behavior
  without importing the implementation. The `release-spec-skew` scenarios additionally build a
  throwaway Git repository so the deployed-vs-spec ancestry is exercised end to end.

Run both layers after any change to the checker. The generic `agent-skill-tests` CI job discovers
this command automatically.
