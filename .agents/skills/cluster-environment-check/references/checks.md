<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# What each check means

This is an AI instruction file. Use it to interpret `scripts/environment-check.sh` output — what
each check reads, the known platform bug it detects, and what OK / WARN / INCONCLUSIVE mean for
that check. Each check reports one of three states, and the distinction is the point of this skill:

- **OK** — the checker read the state it needed and found no problem.
- **WARN** — the checker read the state and found a real problem. The line names the fix.
- **INCONCLUSIVE** — the checker could not read the state it needed (the component's CRD is absent,
  RBAC denied the read, or the API errored). This is never treated as healthy: a silent bug must
  never pass by omission. An inconclusive check is often expected before install (the component
  isn't there yet) — say so, but never call the overall run healthy while one stands.

The overall result is **HEALTHY only when every check is OK**. Any WARN makes it PROBLEMS FOUND;
otherwise any INCONCLUSIVE makes it INCONCLUSIVE (not proven healthy).

## cilium-mtu — model downloads hang (scenario 4)

The bug: Cilium auto-detects the node MTU independently per node. On a cluster with mixed NICs the
effective MTUs diverge (observed 9100 on one node vs 1280 on another), and large model-weight
downloads then hang partway with no error. A cluster-wide pinned MTU in the `cilium-config`
ConfigMap removes the per-node auto-detect entirely.

Scope limit: the per-node _effective_ MTU lives on the node OS and is **not** exposed on the
`ciliumnodes` API objects (verified against a live cluster), so the checker cannot compare per-node
MTU from the API. It reports on whether MTU is pinned cluster-wide, and — because divergence cannot
be excluded from the API when MTU is left to auto-detect — treats an unpinned config as unconfirmed
rather than healthy.

- **OK (pinned)** — `cilium-config` pins `mtu` to a concrete value cluster-wide. No auto-detect
  divergence is possible.
- **OK (not applicable)** — the `ciliumnodes.cilium.io` CRD is _confirmed_ absent; not a Cilium
  cluster, so this Cilium-specific bug does not apply. Reported OK (not inconclusive) so it never
  blocks HEALTHY on a non-Cilium cluster.
- **INCONCLUSIVE (CRD unreadable)** — the CRD read failed for a reason other than a confirmed
  not-found (RBAC forbidden, timeout, API error). A failed read is never treated as "not
  applicable"; the state is simply unconfirmed.
- **INCONCLUSIVE (auto-detect)** — `cilium-config` leaves `mtu` unset (the Cilium default). The
  per-node effective MTU is not API-observable, so divergence and the resulting model-download hang
  cannot be ruled out. The check does not certify the cluster healthy: compare node MTUs and pin
  `cilium-config` mtu to reach a proven-healthy result.
- **INCONCLUSIVE** — `cilium-config` itself is unreadable (RBAC/API error).

## longhorn-health — shared storage unhealthy (scenario 5)

The bug: Longhorn RWX volumes backed by nfs-ganesha can hang (an `flock()` stall on Longhorn RWX),
leaving workloads unable to mount storage. The checker reads each Longhorn volume's `robustness`
and `state`.

- **OK** — every volume is `healthy` and `attached`/`detached`, or Longhorn is present with no
  volumes provisioned yet.
- **WARN** — one or more volumes are not healthy (faulted, degraded, or a blank/unknown robustness
  — anything that is not `healthy/attached|detached`). Workloads may fail to start or mount. Check
  the Longhorn UI and the nfs-ganesha pods and recover the volumes before deploying workloads.
- **INCONCLUSIVE** — no `volumes.longhorn.io` CRD (Longhorn not the storage layer), or the volume
  query failed. Shared-storage health is unconfirmed via Longhorn.

## storage-provisioner — provisioner not live (scenario 5)

The bug: a StorageClass whose backing CSI/provisioner pods are not Ready leaves every new PVC
`Pending` indefinitely. The checker lists StorageClasses and the CSI driver pods.

Each StorageClass is correlated to its own `.provisioner`, per provisioner — not a global pod
sweep — through three positive signals for that exact driver: (a) it is a registered `CSIDriver`;
(b) its node plugin is registered on at least one node (`CSINode.spec.drivers[].name`); and (c) its
controller — the `external-provisioner` sidecar that actually handles `CreateVolume` — is alive,
proven by a leader-election `Lease` named after the driver (e.g. `external-provisioner-leader-<driver>`)
whose `renewTime` is fresh (renewed within ~2 min). This ties liveness to the StorageClass's own
driver end to end, so an unrelated Ready CSI pod cannot vouch for it.

- **OK** — every StorageClass provisioner is a registered CSI driver with a live node plugin and a
  live controller (fresh leader lease) — or is an in-tree/non-CSI provisioner (`kubernetes.io/*`),
  which is exempt.
- **WARN** — a provisioner is not a registered CSIDriver, its node plugin is on no CSINode, or its
  controller's leader lease is stale (not renewing); new PVCs will stay Pending.
- **INCONCLUSIVE** — no StorageClass at all; the CSIDrivers / CSINodes / Leases can't be read; or no
  leader lease was found to establish controller liveness. Do not assume healthy.

## stuck-storage-pods — workloads stuck on storage (scenario 6)

An in-flight signal: pods stuck `Pending`, emitting `FailedMount` events, or Jobs/events ending in
`DeadlineExceeded` are workloads that cannot get storage or whose model download stopped making
progress. Pre-install there is usually nothing running, which is a clean pass (the checker read the
state and found none stuck) — not a false failure.

A Pending pod is attributed to storage **only** when its scheduling condition points at storage (an
unbound PVC / volume) — a pod Pending for CPU, affinity, or taint reasons is not counted. A
`FailedMount` event is always definitive storage evidence. `DeadlineExceeded` is reported
separately as a possible stalled model download, because the known Cilium MTU divergence manifests
as a download Job timing out rather than a FailedMount.

- **OK** — no workloads stuck waiting on storage or model downloads.
- **WARN** — a workload has a `FailedMount` event, is Pending with a scheduling condition naming an
  unbound PVC / volume, or a Job/event reports `DeadlineExceeded`. Resolve the underlying storage
  problem; for timed-out model downloads also check `cilium-mtu`, then retry.
- **INCONCLUSIVE** — pods, events, or Jobs could not be listed (RBAC/API error).

## gpu-metrics — broken metrics pipeline & silent failure (scenarios 7 and 8)

The pipeline is `amdgpu driver -> device-metrics-exporter -> OTel Collector scrape -> Mimir -> UI`.
The exporter and collector pods can show `Running`/`Ready` while silently failing, so the checker
never trusts Ready — it reads the function signal in the logs of **every** exporter pod (it is a
per-node DaemonSet) and the collector. This is the anti-silence core: a green pod that isn't doing
its job is still reported.

After the log-signature scan finds nothing, the check **positively** confirms delivery: it queries
the metrics backend (Prometheus/Mimir) via the API-server service proxy — a read-only `kubectl get
--raw` call, no port-forward, within cluster-reader RBAC — for a positive count of current GPU
series carrying a **non-blank `workload_id`** (`count(gpu_gfx_activity{workload_id!=""})`). That
directly encodes the incident signature: the exporter losing kube-apiserver access blanks the
labels, so series with a real `workload_id` disappear even though the pods are Ready. Prometheus
staleness means a returned value is current. The backend is auto-discovered (a `:9090` service in a
metrics namespace) or set with `--metrics-backend <ns>/<svc>:<port>`.

- **OK (delivering)** — the count of current GPU series with a non-blank `workload_id` is > 0:
  delivery is positively proven end to end.
- **OK (idle)** — the exporter/collector/backend are readable, the count is 0, and no Running pod
  requests or limits `amd.com/gpu`; zero workload-labelled series are expected when there is no GPU
  workload to report.
- **WARN** — an exporter/collector log shows a failure signature (broken hop named), OR an active GPU
  workload exists but the count is 0 / empty (no series, or blank labels — not delivering).
- **INCONCLUSIVE** — the exporter isn't present, logs are unreadable, the collector is absent, the
  metrics backend can't be found/queried, or workload state is unreadable when the count is zero.
  The check never asserts a pass it did not prove.
- **WARN (exporter -> kube-apiserver)** — an exporter pod logs an `i/o timeout` or a repeated
  `Failed to watch` reaching the kube-apiserver, so it cannot map pods to nodes and metric labels go
  blank; the UI shows workloads with 0 GPU/VRAM even though the pod is Ready. Restore node ->
  control-plane network reachability for the exporter pod (this often traces back to the same
  Cilium/network-policy problems as cilium-mtu).
- **WARN (OTel collector -> exporter)** — the collector logs a scrape failure against the exporter,
  so metrics never reach the backend. Check the exporter Service/endpoints and the collector's
  scrape config.
- **INCONCLUSIVE** — no exporter found (expected before install or on a cluster without GPUs), any
  exporter/collector logs are unreadable, or the exporter is present but no collector exists (the
  scrape hop is missing). Do not assume `Running` means healthy, and never pass with a hop unread.

## aim-profiles — GPUs with no matching AIM profile (scenario 9)

The bug: a GPU or partition with no matching AIM profile leaves the `aimclustermodels` at
`ManagedProfilesReady=False, reason=NoSupportedProfiles` (and therefore `Ready=False`), so models
silently never deploy — the single most repeated confusion in the support channel.

- **OK** — every defined cluster model is affirmatively `ManagedProfilesReady=True`, or AIM is
  present with no models defined.
- **WARN** — one or more models report `ManagedProfilesReady=False, reason=NoSupportedProfiles`;
  they cannot deploy on this hardware. The line names the affected models and GPU device-id(s).
- **INCONCLUSIVE** — AIM is absent / unreadable, or any model lacks the `ManagedProfilesReady`
  condition or has it `False` for another reason. The checker never claims every model is supported
  unless every model's condition actively proves it.

## required-secrets — unsynced ExternalSecrets

The bug: a required ExternalSecret in ns `aiwb` (e.g. `aiwb-openbao-token`, which the chart
omits by design when it runs with `openbaoToken.enabled: false`) that fails to sync
(`SecretSyncedError`) blocks `aiwb-api` from starting, even though every other secret on the store
syncs fine. The check reads each ExternalSecret's `Ready` condition.

- **OK** — every ExternalSecret in ns `aiwb` is `Ready=True`.
- **WARN** — one or more are not `Ready`; the line lists them with their reason. The secret backend
  (OpenBao/ESO) must mint those keys before the workbench (or E2E) can come up.
- **INCONCLUSIVE** — the list is unreadable, or there are no ExternalSecrets yet (cluster not
  installed / not fully synced).

## minio-ready — object storage present (two paths)

Object storage is needed on two paths, and an E2E run has failed on each:

- **AIRM path** — the MinIO tenant secret `default-minio-tenant-env-configuration` in ns
  `minio-tenant-default`.
- **AIWB path** — the per-project `minio-credentials` secret is minted **at test time** (AIRM's
  `minio-credentials-fetcher` ExternalSecret is assigned per project), so it does not exist pre-run
  and is not a pre-run gate. The real pre-run signal is that the OpenBao `ClusterSecretStore`
  `openbao-secret-store` is Ready, so the fetcher _can_ mint it from its source keys
  (`minio-api-access-key` / `minio-api-secret-key`).

- **OK** — the AIRM tenant secret is present and `openbao-secret-store` is Ready.
- **WARN** — the AIRM tenant namespace/secret is confirmed absent, or `openbao-secret-store` is
  absent or not Ready (per-project `minio-credentials` cannot be minted).
- **INCONCLUSIVE** — a read failed for a reason other than a confirmed not-found (RBAC/API error).

## aimartifact-rbac — permission to create AIMArtifacts

The test identity must be able to create AIMArtifact CRs in the test namespace; without it, adapter
tests fail with `Failed to create AIMArtifact CR <name>: Forbidden`. Checked with
`kubectl auth can-i create aimartifacts.aim.eai.amd.com -n <test-namespace>`.

- **OK** — the current kubectl identity can create AIMArtifacts. The verdict is explicit that this
  rules out the RBAC-_config_ variant only; a green result does **not** rule out an app-side
  Forbidden (the check tests the kubectl identity, not the app's runtime code path).
- **WARN** — it cannot (Forbidden); grant `create` on `aimartifacts` to the test identity there.
- **INCONCLUSIVE** — the AIMArtifact CRD is absent, or the access review could not be evaluated
  (never treat an unevaluable permission check as allowed).

## aim-route-hostnames-ready — catalog AIM deploys can get an HTTPRoute

The bug: on a **multi-listener** AIM gateway, aim-engine requires `spec.routing.hostnames` on the
effective AIMClusterRuntimeConfig. Without it the AIMService gets no HTTPRoute
(`ConfigValid=False` / `RouteHostnameRequired`) and catalog AIM deploys fail. AIWB's own default
runtimeconfig sets hostnames correctly; the failure mode is aim-engine's competing default
overriding it with none. The check resolves the gateway + runtimeconfig names from `aiwb-api`'s env
(`AIM_GATEWAY_NAMESPACE` / `AIM_GATEWAY_NAME` / `AIM_CLUSTER_RUNTIME_CONFIG_NAME`, defaulting to
`kgateway-system` / `https` / `default`).

- **OK** — the gateway has a single listener (per-route hostnames aren't required), or it is
  multi-listener and the effective AIMClusterRuntimeConfig sets routing hostnames, or routing is
  explicitly disabled (empty hostnames then cannot break anything).
- **WARN** — the gateway is multi-listener but the effective AIMClusterRuntimeConfig has routing
  enabled with no hostnames; catalog AIM deploys will fail with `RouteHostnameRequired`. The fix is
  usually to set `clusterRuntimeConfig.enable=false` on aim-engine so AIWB's hostname-bearing
  default is effective.
- **INCONCLUSIVE** — the gateway or the AIMClusterRuntimeConfig can't be read (CRD absent /
  RBAC / API error); or the config omits `routing.enabled` with no hostnames, where the CRD default
  (`enabled=true`) may still break deploys but can't be confirmed from here. Routing hostnames are
  unconfirmed either way; unconfirmed state is never counted healthy.

## eai-e2e-rbac — the E2E test identity has the permissions the suites use

The bug: the `e2e-aim-test-author` ClusterRole was absent from a bloomed release, and roughly twenty
AIWB tests failed deep into the suite with a `Forbidden` that read like a product bug. The suites
author AIM CRs with `kubectl` as the test identity to stage cases the API cannot express, so a
missing verb only surfaces mid-run.

The check reads the ClusterRole's rules and diffs them against what the suites actually do, then
confirms a ClusterRoleBinding of the same name binds that role to the OIDC test user. Required:
`aimartifacts` get/create/patch; `aimprofiles` get/list; `aimmodels` get/list/create/patch/delete;
`aimmodels/status` get/patch; `aimservices` get/list/create/patch/delete. Wildcard rules (`*`) satisfy any
verb; a `*/<subresource>` resource wildcard covers that subresource (the RBAC authorizer has no
`<parent>/*` form), and a `resourceNames`-restricted rule does not count (it grants only named
objects, while the suites create arbitrary ones).

Note `aimmodels/status` is a distinct resource from `aimmodels` — granting the parent does not grant
the subresource, and the fine-tuning cases need the status write to stage a model that reports Ready.

- **OK** — every required verb is granted and the role is bound to an OIDC user.
- **WARN** — the role is absent, a required verb is missing (the line names the resource and verbs),
  the binding is absent, it references a different role, or it binds no OIDC user.
- **INCONCLUSIVE** — the role or binding read failed for a reason other than a confirmed not-found.

## airm-quota-health — projects are provisioned and none is stuck deleting

An AIRM project is a database entity that materialises a namespace labelled
`airm.silogen.ai/project-id` plus a Kueue ClusterQueue named after the project. Two failures strand a
whole run, and both are visible without creating anything:

- **Stuck deleting (the finalizer race)** — a project namespace has been deleting for at least five
  minutes and an `airm.silogen.ai/*` finalizer is still held. Holding it during the five-minute grace
  is normal teardown and is not warned; after the grace, a rerun that reuses the name fails and the
  leftover keeps consuming quota.
- **No active quota object** — a live project's same-named ClusterQueue is missing or not `Active`.
  Do **not** require positive local `nominalQuota`: every AIRM project queue joins the `kaiwo` cohort
  with borrowing enabled, and zero-quota projects deliberately borrow free resources (covered by the
  quota-preemption E2E specification). Local zero is no guarantee, not an inability to admit.

- **OK** — every live project namespace has an Active same-named ClusterQueue; deleting namespaces
  are within the five-minute grace or no longer held by an AIRM finalizer;
  or there are no project namespaces at all.
- **WARN** — one or more lifecycle/quota problems exist; they are reported together rather than one
  masking another.
- **INCONCLUSIVE** — the namespace list is unreadable; deletion age cannot be parsed; or live projects
  exist but Kueue's ClusterQueues are absent/unreadable (quota unconfirmed — never assumed fine).

## gateway-auth — the inference gateway is serving auth decisions

The bug: a stale certificate left the gateway answering 5xx instead of making an auth decision,
which surfaces later as unexplained inference failures. The check probes `GET /v1/models`.

The invalid-key half needs **no credentials**: a synthesized garbage key must be refused with `401`.
That single probe distinguishes a healthy gateway (refuses cleanly) from a broken one (errors) and
from a misconfigured one (admits anything). The gateway URL comes from the `aiwb-ui` deployment's
`AI_GATEWAY_URL`, or `--gateway-url`.

Supplying `--gateway-key <key>` adds the authorised half: a valid key must return `200` (or `203`,
the ext_authz short-circuit for an authorised models call).

- **OK** — an invalid key is refused with 401 (and, when a key was supplied, a valid one succeeds);
  or the aiwb-ui deployment is readable but declares no `AI_GATEWAY_URL`, a confirmed "no inference
  gateway is wired to this workbench" — there is nothing to probe, so it is not-applicable (the same
  shape `cilium-mtu` uses on a non-Cilium cluster), not unproven health.
- **WARN** — any 5xx (a certificate/upstream failure, not an auth decision), an invalid key that is
  not refused, or a supplied valid key that is rejected.
- **INCONCLUSIVE** — the aiwb-ui deployment cannot be read (address unconfirmed, distinct from a
  confirmed no-gateway); a `--gateway-key` was supplied but no gateway address could be discovered;
  no HTTP response was obtained at all (DNS/connection failure — the gateway may only resolve
  in-cluster); or its certificate could not be verified from this host. The certificate case is
  called out separately because it is ambiguous: the gateway's certificate may be stale (a real
  problem) or this host may simply not trust the cluster CA. Settle it by re-running where the CA is
  trusted, or comparing with `curl -v` from the E2E runner — a host whose trust store differs will
  disagree.

## app-pods-stable — core app pods running and not flapping

Catches the silent case a plain deployment-Available check misses: a pod that is Ready **now** but
has been crash-looping is not stable, and intermittent restarts of a backend cause user-facing
failures like the UI's `/api/projects` "fetch failed". Scans pods in the `aiwb` and `airm`
namespaces.

- **OK** — every app pod is Running/Ready with no fatal waiting state and restarts below the
  threshold.
- **WARN** — a pod never got scheduled (no `containerStatuses` at all, e.g. `Unschedulable`) and is
  past the startup grace; a container (init or main) is waiting in a fatal reason (`CrashLoopBackOff`,
  `CreateContainerConfigError`, `ImagePullBackOff`, `ErrImagePull` — the first is how the `aiwb-api`
  openbao-token block manifests), a pod has stayed NotReady past a startup grace (~5 min, so a
  rollout in progress is not flagged), or a pod is Ready but has restarted at least
  `--restart-threshold` times (default 3; the flapping signal). The line names each offending pod;
  pods owned by a completed Job are ignored.
- **INCONCLUSIVE** — neither app namespace is present (before install), or the pod list is
  unreadable.

## aiwb-api-healthy / aiwb-ui-healthy — workbench deployments up

- **OK** — the deployment is `Available=True` with `readyReplicas > 0`.
- **WARN** — it exists but is not Available; a `CreateContainerConfigError` here usually means a
  required secret/config is missing (see required-secrets).
- **INCONCLUSIVE** — the deployment is not found (expected before install) or the read failed.

## gpu-schedulable — GPUs allocatable and admittable

Two conditions must both hold for GPU workloads to run: nodes advertise allocatable `amd.com/gpu`,
and the `--test-namespace` LocalQueue resolves to a ClusterQueue with `amd.com/gpu` quota. Quota on
an unrelated ClusterQueue cannot admit workloads from the test namespace and never counts as proof.
Zero local quota is only a failure outside a cohort: an AIRM project queue joins the `kaiwo` cohort
with borrowing enabled and admits GPU jobs by borrowing, so a zero-quota queue with a cohort is OK —
matching airm-quota-health, which treats the same shape as healthy.

- **OK** — GPUs are allocatable and the test namespace's LocalQueue is bound to a ClusterQueue with
  positive `amd.com/gpu` quota, or with zero local quota but a cohort to borrow from (or, with no GPU
  nodes and without `--require-gpu`, GPUs are simply not applicable on this cluster).
- **WARN** — GPU capacity exists but 0 is allocatable (the GPU operator has not rolled out drivers),
  the test namespace has no usable LocalQueue/ClusterQueue binding, its referenced ClusterQueue is
  missing or has zero GPU quota and no cohort, or `--require-gpu` was set and there are no GPUs.
- **INCONCLUSIVE** — nodes, the namespace's LocalQueues, or its referenced ClusterQueue cannot be
  read (admission unverified).

## release-spec-skew — the deployed products contain the specs about to run (opt-in)

The problem: deployment-triggered E2E runs specs from the branch under test against whatever
release image is already deployed. When the deployed AIRM/AIWB build predates a spec's behavior, that
spec fails permanently on the environment — surfacing as a plain assertion failure that reads like a
product defect (e.g. a `202` where the newer code returns `400`) rather than a version gap.

This check is **opt-in**: it runs only when the caller passes `--spec-revision REV`, because only the
caller knows which core commit's specs will run. It needs `--core-repo PATH` (a core Git checkout
that contains that revision plus the deployed release tags/commits) to resolve markers to commits.

For AIRM and AIWB independently, it reads the image actually serving a **completed** Deployment
rollout: it requires the rollout to be complete (observed generation current, and updated = ready =
available = desired replicas with none unavailable), then confirms every selected Ready pod runs the
chart's product container (`aiwb` / `airm`, never a sidecar) on one identical image tag **and** one
identical running `imageID` manifest digest. The digest check catches a partial retarget — some pods
still serving an older manifest under the same tag text — that the requested tag alone would hide. It
resolves that image tag to a commit using only **immutable** markers — an annotated/lightweight
release tag under `refs/tags` whose name is either SemVer (e.g. `2.0.2-rc.3`) or one of the
repository's established calendar-release forms (`v2025.08-rc.21`, `v2025.08.002`), else a Git
short/long SHA embedded at the end of the tag (`main-fdb389c`, `<branch>-product-de73d50`) — and
compares by ancestry against the spec revision. A mutable branch image tag (`main`), a digest-pinned
reference (`…@sha256:…`, whose tag is not manifest provenance), a missing running `imageID`, mixed
running digests across Ready pods, an in-progress or ambiguous rollout, and a shallow core checkout
are all INCONCLUSIVE, never OK/WARN.

**Convention assumption.** The check pins each product to its conventional Deployment name and
namespace (`aiwb-api` in `aiwb`, `airm-api` in `airm`) and its chart product container (`aiwb` /
`airm`). These follow from the standard release name/namespace; a non-default release name or
namespace makes the Deployment read "not found", so the check reports INCONCLUSIVE and never fires —
fail-safe, but it will not catch skew on an off-convention install. It is intended for the standard
E2E test deployment.

**Provenance limit (known residual gap).** This checker is offline (local checkout, no registry or
network), so it cannot bind the running `imageID` digest to a source commit through build
attestations. It resolves the deployed _tag text_ to a commit, which trusts the GitOps (Argo)
tag→digest binding. It therefore does catch a _partial_ retarget (mixed digests across pods, above),
but a registry tag _uniformly_ retargeted to a different build of the same name would still resolve by
tag text and pass. Closing that fully needs digest→commit resolution via the SLSA provenance the image
workflows publish, which requires registry/attestation access — a known follow-up outside this
checker. Until then, treat an OK from this check as "the deployed tag, as
bound by GitOps, contains the specs", not a cryptographic guarantee of the running manifest.

- **OK** — every deployed product's commit contains the spec revision (the spec commit is an ancestor
  of, or equal to, each deployed commit). The specs' behavior is present in what is running.
- **WARN** — a deployed product predates the spec revision (deployed is an ancestor of the spec
  commit), or the two have diverged (neither contains the other). The line names the product and both
  revisions. Deploy a build that contains the spec revision, or run the specs from the deployed
  release's branch, before the suite.
- **INCONCLUSIVE** — `--core-repo` is not a readable repo or has shallow history, the spec revision
  does not resolve in it, a product is not deployed or its rollout is incomplete/ambiguous, its image
  is digest-pinned or its tag resolves to no immutable commit, or a git comparison errors (including a
  negative ancestry answer that a shallow clone cannot prove). An unresolved marker is never treated
  as compatible.

Because both sides are reduced to commits and compared by `git merge-base --is-ancestor`, the verdict
is exact even when the deployed stack is not one coherent SemVer (mixed release + `main-<sha>` tags
are handled). Comparing release numbers, image timestamps, or Argo sync times would give false
results and is deliberately not done.

## image-exists — a container image reference resolves

Run as the `image-exists <ref>` subcommand or via `--image REF`. Used to catch an install/E2E that
references an image tag that was never published.

- **OK** — the manifest is present (via skopeo/crane/docker, or the public Docker Hub tag API).
- **WARN** — a definitive manifest-unknown / not-found from a registry that answered.
- **INCONCLUSIVE** — auth is required / the registry is unreachable / no inspection tool is
  available. A **private** repo commonly 404s on the public Hub API, which is NOT proof the tag is
  missing — so it is inconclusive, never a false WARN.

## Before vs. after install

The same checks run regardless of install state; interpret inconclusive results against it:

- **Before install**, a bare cluster legitimately lacks Longhorn, AIM, or the GPU exporter, so
  those checks are inconclusive — that is readiness information ("these components aren't here
  yet"), not a failure. cilium-mtu and storage-provisioner are the readiness-relevant ones.
- **After install**, an inconclusive result for a component that _should_ be present is itself worth
  investigating — it usually means an RBAC or API problem reading it, not that the component is
  absent.
