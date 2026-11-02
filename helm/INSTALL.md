<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AMD enterprise AI reference stack - Helm Installation Guide

This guide provides step-by-step instructions for deploying the AMD enterprise AI reference stack
on a Kubernetes cluster using the Helm charts in this repository.

> **Automated deployment**: For production deployments, consider using
> [Cluster Forge](https://github.com/silogen/cluster-forge), which automates the entire
> stack deployment including all dependencies via GitOps.
>
> **Official documentation**: For comprehensive platform documentation, visit
> <https://enterprise-ai.docs.amd.com>.
>
> **Agent-guided install**: The product-owned source for AMD's guided AI Workbench install skill
> is `.agents/skills/guided-workbench-install/`. It adds read-only preflight and post-install
> health gates around this command-by-command runbook. Use this file for exact Helm commands and
> values. The legacy `cluster-auth` entries below are retained only to explain the ungated
> `cluster-auth-admin-token` ExternalSecret that remains in the external-secrets chart; the
> current AIWB app does not consume cluster-auth.

---

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Deployment Modes](#deployment-modes)
- [Step 1: Install Cluster Dependencies](#step-1-install-cluster-dependencies)
  - [Tier 1 - Operators and CRDs](#tier-1---operators-and-crds)
  - [Tier 2 - Platform Services](#tier-2---platform-services)
  - [Tier 3 - AI/ML Stack (Compute Plane)](#tier-3---aiml-stack-compute-plane)
  - [Optional Dependencies](#optional-dependencies)
  - [Example Gateway for app routing](#example-gateway-for-app-routing)
  - [Bringing Your Own Infrastructure](#bringing-your-own-infrastructure)
  - [Example Keycloak install](#example-keycloak-install)
  - [Keycloak Realm Setup](#keycloak-realm-setup)
  - [StorageClass Requirements](#storageclass-requirements)
  - [Node Requirements for CNPG Clusters](#node-requirements-for-cnpg-clusters)
  - [Scripted Installation for Standalone AIWB](#scripted-installation-for-standalone-aiwb)
- [Step 2: Create Secrets](#step-2-create-secrets)
  - [Option A: External Secrets Operator](#option-a-external-secrets-operator)
  - [Option B: Manual Secret Creation](#option-b-manual-secret-creation)
- [Step 3: Install Infrastructure Charts](#step-3-install-infrastructure-charts)
- [Step 4: Install Application Charts](#step-4-install-application-charts)
  - [AIRM (AI Resource Manager)](#airm-ai-resource-manager)
  - [AIWB (AI Workbench)](#aiwb-ai-workbench)
  - [AI Gateway Discovery](#ai-gateway-discovery)
  - [Chart defaults that assume cluster-forge service names](#chart-defaults-that-assume-cluster-forge-service-names)
  - [Upgrading](#upgrading)
- [Step 5: Onboard a Cluster](#step-5-onboard-a-cluster)
- [Verification](#verification)
- [Local Development Notes](#local-development-notes)
- [Validation with E2E Tests](#validation-with-e2e-tests)

---

## Overview

The AMD enterprise AI reference stack consists of two main applications:

- **AI Resource Manager (AIRM)** -- Multi-tenant resource management, authentication,
  cluster coordination, and resource allocation.
- **AI Workbench (AIWB)** -- AI development tools including model deployment (AIMs),
  workspaces, fine-tuning, and dataset management.

The Helm charts are organized as follows:

```
helm/
├── airm/                          # AIRM umbrella chart (API + UI + Agent)
│   └── charts/
│       ├── airm-api/              # AIRM API and UI
│       └── airm-agent/            # AIRM cluster agent
├── aiwb/                          # AIWB API and UI
├── ai-gateway-discovery/          # Inference-route discovery and API-key auth
├── infrastructure/
│   ├── airm-cnpg/                 # PostgreSQL cluster for AIRM
│   ├── aiwb-cnpg/                 # PostgreSQL cluster for AIWB
│   ├── airm-rabbitmq/             # RabbitMQ cluster for AIRM
│   ├── airm-external-secrets/     # ExternalSecret resources for AIRM
│   └── aiwb-external-secrets/     # ExternalSecret resources for AIWB
└── eai-e2e/                       # E2E test support (optional)
```

## Prerequisites

- **Kubernetes** 1.28+ cluster with AMD GPUs
- **Helm** 3.x or 4.x
- **kubectl** configured for your cluster
- A **domain name** for ingress routing (referred to as `<YOUR-DOMAIN>` throughout this guide)
- A **Gateway API** implementation and a `Gateway` the app charts can attach
  `HTTPRoute`s to. These charts do not install a controller. Chart defaults
  (`https` in `envoy-gateway-system`) match cluster-forge naming; any Gateway
  API controller works if you point the charts at your Gateway. See
  [Example Gateway for app routing](#example-gateway-for-app-routing).
- **OpenBao** (AIWB modes only — not required for standalone AIRM): a
  Vault-compatible backend with a Ready `ClusterSecretStore`, unless you
  disable the API-key store (`openBao.enabled: false` on the AIWB chart and
  `openbaoToken.enabled: false` on `aiwb-external-secrets`). Bootstrap
  secrets can still be created as Kubernetes Secrets by hand (see
  [Option B](#option-b-manual-secret-creation)). With OpenBao enabled, AIWB
  API-key creation requires External Secrets Operator plus this store at
  runtime. The charts default to a store named `openbao-secret-store`.
  Standalone AIRM still defaults `airm-api.airm.includeDemoSetup` to `true`,
  and that Job creates a demo ExternalSecret for `openbao-secret-store` plus
  MinIO storage — pass `--set airm-api.airm.includeDemoSetup=false` if you
  are not providing that store.
- A **StorageClass** available in your cluster. The infrastructure charts default to a
  StorageClass named `default`. If your cluster uses a different name (e.g., `standard`
  on kind clusters), override it with the per-chart key in
  [StorageClass Requirements](#storageclass-requirements) — a single
  `--set storage.storageClass=` does not cover RabbitMQ.

## Deployment Modes

The platform supports three deployment modes:

| Mode                       | Description                                               | Charts to Install                                                                                                           |
| -------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Combined (AIRM + AIWB)** | Full platform with resource management and AI workbench   | `airm` + `aiwb` + all infrastructure. Optional: `ai-gateway-discovery` (inference front door and `workloads.<domain>` auth) |
| **Standalone AIRM**        | Resource management only                                  | `airm` + AIRM infrastructure                                                                                                |
| **Standalone AIWB**        | Single-namespace AI workbench without resource management | `aiwb` + AIWB infrastructure (set `standAloneMode: true`). Optional: `ai-gateway-discovery`                                 |

---

## Step 1: Install Cluster Dependencies

The following components must be installed on the cluster before deploying the
application charts. They are organized into tiers based on install order.

### Tier 1 - Operators and CRDs

These operators and CRD providers must be installed first, as other components depend on them.

| Component                                   | Purpose                                                                                                                                                                                                                                                                                                                                                                                                           | Substitutable?                                                                                        | Installation                                                                                                                                                                                                                                                                                                                 |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **cert-manager**                            | TLS certificate management. Used by RabbitMQ for TLS and by the AIRM agent for webhook certificates.                                                                                                                                                                                                                                                                                                              | No                                                                                                    | [cert-manager docs](https://cert-manager.io/docs/installation/helm/)                                                                                                                                                                                                                                                         |
| **CloudNative-PG (CNPG) Operator**          | Manages PostgreSQL database clusters. AIRM and AIWB each require a PostgreSQL instance.                                                                                                                                                                                                                                                                                                                           | Yes — see [Bringing Your Own Infrastructure](#bringing-your-own-infrastructure)                       | [CNPG docs](https://cloudnative-pg.io/documentation/current/installation_upgrade/)                                                                                                                                                                                                                                           |
| **RabbitMQ Cluster Operator**               | Manages RabbitMQ clusters. Used for messaging between the AIRM API and the cluster Agent. Not required for standalone AIWB.                                                                                                                                                                                                                                                                                       | No                                                                                                    | [RabbitMQ Operator docs](https://www.rabbitmq.com/kubernetes/operator/install-operator). Recommended: install via `kubectl apply -f https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml`                                                                                              |
| **External Secrets Operator**               | Synchronizes secrets from an external backend (Vault, OpenBao, etc.) into Kubernetes Secrets. [Option B](#option-b-manual-secret-creation) replaces ESO only for _bootstrap_ secrets. With OpenBao enabled (the default), ESO and a Ready `ClusterSecretStore` remain required at runtime because AIWB creates per-key `ExternalSecret` objects. With `openBao.enabled: false` and Option B, ESO is not required. | Bootstrap: Yes — manual secrets. Runtime: No, unless OpenBao is disabled.                             | [ESO docs](https://external-secrets.io/latest/introduction/getting-started/)                                                                                                                                                                                                                                                 |
| **Gateway API CRDs + a Gateway controller** | Kubernetes-native HTTP routing. AIRM and AIWB create `HTTPRoute`s that attach to a Gateway you provide (chart defaults: name `https` in namespace `envoy-gateway-system`). Any Gateway API implementation is fine; those default names are cluster-forge conventions, not a requirement to use Envoy Gateway. Deprecated `kgateway.*` Helm keys still override if set.                                            | Yes — any Gateway API implementation                                                                  | `kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.1/standard-install.yaml`. Then a controller ([Gateway API docs](https://gateway-api.sigs.k8s.io/guides/#installing-gateway-api)). Worked example: [Example Gateway for app routing](#example-gateway-for-app-routing). |
| **Gateway API Inference Extension**         | `InferencePool` CRDs used by `ai-gateway-discovery` to route to KServe predictor pods. Skip unless you install that chart.                                                                                                                                                                                                                                                                                        | No for the `ai-gateway-discovery` path                                                                | `kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/v1.6.1/manifests.yaml`. [Inference Extension docs](https://gateway-api-inference-extension.sigs.k8s.io/)                                                                                                |
| **OpenTelemetry Operator**                  | Manages OpenTelemetry collectors. AIWB deploys a DaemonSet collector on AIM accelerator nodes (GPU or supported EPYC) for vLLM inference metrics. **The Operator CRDs are required even when you will not scrape metrics**: the AIWB chart always creates an `OpenTelemetryCollector`, so `helm install aiwb` fails without `opentelemetry.io/v1beta1`.                                                           | No for the AIWB chart install; the collector itself is unused on clusters that are not serving models | [OTel Operator docs](https://opentelemetry.io/docs/platforms/kubernetes/operator/)                                                                                                                                                                                                                                           |
| **KEDA**                                    | Event-driven autoscaler. Required by KServe for autoscaling `InferenceService` pods based on metrics.                                                                                                                                                                                                                                                                                                             | No                                                                                                    | [KEDA docs](https://keda.sh/docs/latest/deploy/). Optionally add the [Kedify OTEL Scaler](https://kedify.io/scalers/otel) for OpenTelemetry-based scaling triggers.                                                                                                                                                          |
| **Prometheus Operator CRDs**                | `ServiceMonitor`, `PodMonitor`, and related CRDs required by the LGTM observability stack. Install the CRDs even if you bring your own Prometheus.                                                                                                                                                                                                                                                                | No                                                                                                    | Included in the [kube-prometheus-stack](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack) chart, or install CRDs standalone from [prometheus-operator releases](https://github.com/prometheus-operator/prometheus-operator/releases).                                              |

### Tier 2 - Platform Services

These services should be deployed after the operators are running.

| Component                      | Purpose                                                                                                                                                                                                                                                                                                                                                                                                             | Substitutable?                                                                               | Installation                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Keycloak**                   | Identity and access management. AIRM uses the Keycloak Admin API (`python-keycloak`) for user, group, and role management at runtime — a generic OIDC provider is not sufficient. The AIRM API **exits on startup** if it cannot reach Keycloak. See [Example Keycloak install](#example-keycloak-install) and [Keycloak Realm Setup](#keycloak-realm-setup).                                                       | No                                                                                           | Example Deployment below, or the [Keycloak Operator](https://www.keycloak.org/operator/installation)                                                                                                                                                                                                                                                                                                                                          |
| **MinIO Operator + Tenant**    | S3-compatible object storage. Used by AIWB for dataset and model storage. Not required for standalone AIRM deployments.                                                                                                                                                                                                                                                                                             | Yes — see [Bringing Your Own Infrastructure](#bringing-your-own-infrastructure)              | [MinIO Operator docs](https://min.io/docs/minio/kubernetes/upstream/operations/install-deploy-manage/deploy-operator-helm.html)                                                                                                                                                                                                                                                                                                               |
| **Observability Stack (LGTM)** | Prometheus, Loki, Grafana, Tempo, Mimir. Provides metrics, logs, and traces. Both AIRM and AIWB query Prometheus for GPU and workload metrics.                                                                                                                                                                                                                                                                      | Yes — any Prometheus-compatible stack                                                        | [Grafana LGTM docs](https://grafana.com/docs/grafana/latest/)                                                                                                                                                                                                                                                                                                                                                                                 |
| **OpenBao**                    | API-key KV store. AIWB writes keys here and ESO materializes them as Kubernetes Secrets. Default `ClusterSecretStore` name: `openbao-secret-store` (`openBao.secretStoreRef` on the AIWB chart, `externalSecretStore` on the ESO charts). Disable with `openBao.enabled: false` (AIWB) and `openbaoToken.enabled: false` (`aiwb-external-secrets`) when API keys are not needed.                                    | Yes — HashiCorp Vault if the ClusterSecretStore can talk to it; or disable the API-key store | [OpenBao Helm docs](https://openbao.org/docs/platform/k8s/helm/)                                                                                                                                                                                                                                                                                                                                                                              |
| **Envoy AI Gateway**           | Needed for the bundled `ai.<domain>` front door **and** for fail-closed auth on AIM serving routes (`workloads.<domain>`). `ai-gateway-discovery` writes Envoy AI Gateway `AIGatewayRoute` objects and Envoy Gateway `SecurityPolicy` objects (including `workloads-extauth`). Skip this chart, and this dependency, only for API/UI-only installs; model serving needs that chart or an equivalent Gateway policy. | No for the `ai-gateway-discovery` path                                                       | CRDs then controller (v1.1.0): `helm upgrade -i aieg-crd oci://docker.io/envoyproxy/ai-gateway-crds-helm --version v1.1.0 -n envoy-ai-gateway-system --create-namespace` and `helm upgrade -i aieg oci://docker.io/envoyproxy/ai-gateway-helm --version v1.1.0 -n envoy-ai-gateway-system --create-namespace`. Commands also in [AI Gateway Discovery](#ai-gateway-discovery). [Envoy AI Gateway docs](https://aigateway.envoyproxy.io/docs/) |
| **cluster-auth (legacy)**      | Not an AIWB prerequisite. The current AIWB app chart does not consume cluster-auth; gateway authentication uses ai-gateway-discovery and OpenBao/ESO instead.                                                                                                                                                                                                                                                       | N/A                                                                                          | Do not install cluster-auth for current AIWB. The external-secrets chart still renders one legacy `cluster-auth-admin-token` ExternalSecret; see [Option A](#option-a-external-secrets-operator).                                                                                                                                                                                                                                             |

### Tier 3 - AI/ML Stack (Compute Plane)

These components enable GPU workloads and AI model serving on compute clusters.

| Component                       | Purpose                                                                                                                                                                                                                                                                     | Substitutable? | Installation                                                                                              |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- | --------------------------------------------------------------------------------------------------------- |
| **AMD GPU Operator**            | GPU device plugin, drivers, and node feature discovery for AMD GPUs.                                                                                                                                                                                                        | No             | [AMD GPU Operator docs](https://github.com/ROCm/gpu-operator)                                             |
| **AMD Device Metrics Exporter** | Exports per-GPU metrics (utilization, VRAM, temperature, power, PCIe). AIRM relies on these metrics for all GPU dashboards and workload monitoring. Must be deployed on every GPU node. See the [configuration note](#amd-device-metrics-exporter-configuration) below.     | No             | [Device Metrics Exporter docs](https://instinct.docs.amd.com/projects/device-metrics-exporter/en/latest/) |
| **Kaiwo**                       | AI workload orchestration. Manages job scheduling, queue configuration, and GPU resource allocation. Includes its own dependencies: **Kueue** (job queueing) and **KubeRay** (distributed computing).                                                                       | No             | [Kaiwo docs](https://github.com/silogen/kaiwo)                                                            |
| **AIM Engine**                  | Operator for `AIMService` CRDs. Handles AI model deployment, discovery (`AIMClusterModel`), and inference routing. Includes **KServe** as a transitive dependency for `InferenceService` management. **KServe should be configured for `RawDeployment` mode** (no Knative). | No             | [AIM Engine docs](https://github.com/amd-enterprise-ai/aim-engine)                                        |

#### AMD Device Metrics Exporter Configuration

The AMD Device Metrics Exporter requires a ConfigMap named `gpu-config` in the
`kube-amd-gpu` namespace. This ConfigMap controls which GPU fields are collected and,
critically, includes the custom labels that AIRM needs to associate metrics with clusters,
projects, and workloads.

A reference configuration is available at
[cluster-forge/sources/amd-gpu-operator-config](https://github.com/silogen/cluster-forge/blob/main/sources/amd-gpu-operator-config/ConfigMap_amd-gpu-metrics-exporter-config.yaml).

Apply it to your cluster (replace `<YOUR-CLUSTER-NAME>` with the name you will register
in AIRM):

```bash
kubectl create namespace kube-amd-gpu 2>/dev/null || true

kubectl apply -f - <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: gpu-config
  namespace: kube-amd-gpu
data:
  config.json: |
    {
      "GPUConfig": {
        "Fields": [
          "GPU_NODES_TOTAL",
          "GPU_PACKAGE_POWER",
          "GPU_AVERAGE_PACKAGE_POWER",
          "GPU_EDGE_TEMPERATURE",
          "GPU_JUNCTION_TEMPERATURE",
          "GPU_MEMORY_TEMPERATURE",
          "GPU_HBM_TEMPERATURE",
          "GPU_GFX_ACTIVITY",
          "GPU_UMC_ACTIVITY",
          "GPU_MMA_ACTIVITY",
          "GPU_VCN_ACTIVITY",
          "GPU_JPEG_ACTIVITY",
          "GPU_VOLTAGE",
          "GPU_GFX_VOLTAGE",
          "GPU_MEMORY_VOLTAGE",
          "PCIE_SPEED",
          "PCIE_MAX_SPEED",
          "PCIE_BANDWIDTH",
          "GPU_ENERGY_CONSUMED",
          "PCIE_REPLAY_COUNT",
          "PCIE_RECOVERY_COUNT",
          "PCIE_REPLAY_ROLLOVER_COUNT",
          "PCIE_NACK_SENT_COUNT",
          "PCIE_NAC_RECEIVED_COUNT",
          "GPU_CLOCK",
          "GPU_POWER_USAGE",
          "GPU_TOTAL_VRAM",
          "GPU_USED_VRAM",
          "GPU_FREE_VRAM",
          "GPU_TOTAL_VISIBLE_VRAM",
          "GPU_USED_VISIBLE_VRAM",
          "GPU_FREE_VISIBLE_VRAM",
          "GPU_TOTAL_GTT",
          "GPU_USED_GTT",
          "GPU_FREE_GTT",
          "GPU_ECC_CORRECT_TOTAL",
          "GPU_ECC_UNCORRECT_TOTAL"
        ],
        "Labels": [
          "GPU_UUID",
          "SERIAL_NUMBER",
          "GPU_ID",
          "POD",
          "NAMESPACE",
          "CONTAINER",
          "CLUSTER_NAME",
          "CARD_SERIES",
          "CARD_MODEL",
          "CARD_VENDOR",
          "DRIVER_VERSION",
          "VBIOS_VERSION",
          "HOSTNAME"
        ],
        "ExtraPodLabels": {
          "WORKLOAD_ID": "airm.silogen.ai/workload-id",
          "PROJECT_ID": "airm.silogen.ai/project-id"
        },
        "CustomLabels": {
          "KUBE_CLUSTER_NAME": "<YOUR-CLUSTER-NAME>"
        }
      }
    }
EOF
```

**Key fields explained:**

| Field                            | Purpose                                                                                                                                                                                                                                                                                                    |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ExtraPodLabels.WORKLOAD_ID`     | Maps the `airm.silogen.ai/workload-id` pod label into GPU metrics so AIRM can attribute utilization to individual workloads.                                                                                                                                                                               |
| `ExtraPodLabels.PROJECT_ID`      | Maps the `airm.silogen.ai/project-id` pod label so metrics roll up to projects.                                                                                                                                                                                                                            |
| `CustomLabels.KUBE_CLUSTER_NAME` | **Must match the cluster name registered in AIRM** (e.g., `demo-cluster`). This is the primary identifier AIRM uses to correlate GPU metrics with the correct cluster. If the exporter is not deployed or this label is absent, the AIRM Agent falls back to its `KUBE_CLUSTER_NAME` environment variable. |

> **Important**: The cluster name must be consistent across three places:
>
> 1. The `KUBE_CLUSTER_NAME` value in this ConfigMap
> 2. The cluster name registered in AIRM during [Step 5](#step-5-onboard-a-cluster)
> 3. The Agent deployment's `KUBE_CLUSTER_NAME` environment variable, set from
>    `airm.agent.clusterName` (default `demo-cluster` in
>    [airm-agent/values.yaml](airm/charts/airm-agent/values.yaml); umbrella override:
>    `--set airm-agent.airm.agent.clusterName=<NAME>`).
>    See the [Agent README](airm/charts/airm-agent/README.md) for configuration details.
>
> If these drift out of sync, GPU metrics will not appear in the AIRM dashboards.

### Optional Dependencies

| Component   | When Needed                                                                                                                                                                                                                             | Installation                                                  |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| **Kyverno** | Only when deploying AIWB in standalone mode (`standAloneMode: true`). Provides a `ClusterPolicy` that auto-labels workloads with `workload-id`. Not needed for the default combined AIRM + AIWB deployment where AIRM handles labeling. | [Kyverno docs](https://kyverno.io/docs/installation/methods/) |

### Example Gateway for app routing

These charts do not install an ingress or gateway controller. They create
Kubernetes Gateway API `HTTPRoute` objects. You provide:

1. The **Gateway API CRDs**.
2. A **controller** that implements Gateway API **with `RegularExpression`
   `HTTPRoute` matches** (an Extended, not Core, feature). The app charts
   match the `Host` header — and some paths — with `RegularExpression`, so a
   Core-only controller rejects those routes. Envoy Gateway, kgateway, and
   Istio support it; confirm before substituting another implementation.
3. A **`Gateway`** resource that controller will program.

Chart defaults (`name: https`, `namespace: envoy-gateway-system`) match
cluster-forge naming so a Helm install works without extra `--set` flags.
They are not a requirement to use Envoy Gateway. If your Gateway uses a
different name or namespace, add these flags to the [Step 4](#step-4-install-application-charts)
`helm install` commands (do not run a second install here — the releases
would already exist and the Step 4 commands would fail):

```bash
# AIRM umbrella — the top-level `gateway.*` key is ignored; set airm-api.*
--set airm-api.gateway.namespace=<NS>
--set airm-api.gateway.gatewayName=<NAME>

# AIWB
--set gateway.namespace=<NS>
--set gateway.gatewayName=<NAME>
```

Deprecated `kgateway.namespace` / `kgateway.gatewayName` still take
precedence when set.

#### Hostnames the routes match

AIRM and AIWB HTTPRoutes match the `Host` header with `<prefix>\..*` (any
domain after the prefix). A Gateway listener should therefore allow those
hosts — typically `hostname: "*.<YOUR-DOMAIN>"`, or no hostname restriction.

| Host                                           | Created by                                                                                           |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `airmapi.<YOUR-DOMAIN>`                        | AIRM `HTTPRoute`                                                                                     |
| `airmui.<YOUR-DOMAIN>`                         | AIRM `HTTPRoute`                                                                                     |
| `aiwbapi.<YOUR-DOMAIN>`                        | AIWB `HTTPRoute`                                                                                     |
| `aiwbui.<YOUR-DOMAIN>`                         | AIWB `HTTPRoute`                                                                                     |
| `workloads.<YOUR-DOMAIN>`                      | AIM Engine, using the Gateway ref on `AIMClusterRuntimeConfig` (defaults to `workloads.<appDomain>`) |
| `ai.<YOUR-DOMAIN>`                             | `ai-gateway-discovery` (inference path only)                                                         |
| `kc.<YOUR-DOMAIN>`, `workspaces.<YOUR-DOMAIN>` | Not created by these app charts. Add HTTPRoutes for Keycloak and workspace services separately.      |

HTTPRoutes live in the `airm` and `aiwb` namespaces (the Keycloak example
lives in `keycloak`; standalone AIWB adds its `defaultNamespace`, default
`workbench`). Allow only those namespaces with a label selector.
`allowedRoutes.namespaces.from: All` is a local-only shortcut on an
isolated cluster; on a shared cluster it lets any namespace attach routes
to this Gateway.

AIM serving HTTPRoutes are created later in **per-project namespaces** that
AIRM provisions on demand, and neither AIRM nor the standalone AIWB chart
adds the `airm.silogen.ai/gateway-routes` label. With a `Selector` listener
those routes stay unbound until each project namespace carries the label.
Label every project namespace as it is created (or reconcile the label with
a controller/policy), or keep `from: All` on an isolated cluster where the
open listener is acceptable.

#### Installing a controller (worked example: Envoy Gateway)

The `Gateway` below is vanilla Gateway API. A controller must own
`<your-gateway-class>` or routes stay unprogrammed. Any implementation is
fine; this example uses Envoy Gateway because cluster-forge does, not
because the app charts require it.

Install the Gateway API CRDs first (same command as
[Tier 1](#tier-1---operators-and-crds)). If they are **already** on the
cluster, skip that first `kubectl apply`. Do **not** let the controller
Helm chart re-apply those CRDs — Helm fails with field-manager conflicts
on `gatewayclasses.gateway.networking.k8s.io` and related CRDs. Then
install the controller's own CRDs, then the controller with CRD install
disabled:

```bash
kubectl apply --server-side \
  -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.1/standard-install.yaml

kubectl apply --server-side \
  -f https://github.com/envoyproxy/gateway/releases/download/v1.9.1/envoy-gateway-crds.yaml

helm upgrade --install eg oci://docker.io/envoyproxy/gateway-helm \
  --version v1.9.1 \
  -n envoy-gateway-system --create-namespace \
  --set crds.enabled=false
```

Create the `GatewayClass` that controller owns, then the `Gateway`:

```bash
kubectl apply -f - <<'EOF'
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: eg
spec:
  controllerName: gateway.envoyproxy.io/gatewayclass-controller
EOF
```

Other controllers swap in their own class name and `controllerName`
(`kgateway`, `istio`, `nginx`, …). That is the only vendor-specific piece.

#### Example Gateway

Replace `<your-gateway-class>` with that `GatewayClass` (`eg` in the Envoy
example above). Replace `<tls-secret>` with a TLS Secret in the Gateway's
namespace. The `Namespace` document is a no-op if the Helm install above
already created `envoy-gateway-system`.

```bash
# Namespaces that attach HTTPRoutes. Helm --create-namespace later is a no-op.
# Add "workbench" (or your defaultNamespace) for standalone AIWB, and label
# each AIRM project namespace the same way as it is created.
for ns in airm aiwb keycloak; do
  kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f -
  kubectl label namespace "$ns" airm.silogen.ai/gateway-routes=true --overwrite
done

kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: envoy-gateway-system
---
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: https
  namespace: envoy-gateway-system
spec:
  gatewayClassName: <your-gateway-class>
  listeners:
    - name: https
      protocol: HTTPS
      port: 443
      hostname: "*.<YOUR-DOMAIN>"
      tls:
        mode: Terminate
        certificateRefs:
          - name: <tls-secret>
      allowedRoutes:
        namespaces:
          from: Selector
          selector:
            matchLabels:
              airm.silogen.ai/gateway-routes: "true"
EOF
```

For local HTTP (kind, minikube), include a listener like this in the Gateway
spec **before** you apply it. An HTTP listener alone does not make the UIs
work over HTTP; see [Local Development Notes](#local-development-notes).

```yaml
- name: http
  protocol: HTTP
  port: 80
  hostname: "*.localhost"
  allowedRoutes:
    namespaces:
      from: Selector
      selector:
        matchLabels:
          airm.silogen.ai/gateway-routes: "true"
```

Helm does not require a `Gateway` object to exist: the charts still create
`HTTPRoute`s, and a missing parent is accepted by the API server. A
controller-less or dummy `Gateway` only supplies a parent name; it does not
program data-plane routing (`Accepted=False`). Traffic needs a programmed
Gateway. After installing the app charts, confirm the parent is accepted:

```bash
kubectl get httproute -n airm
kubectl get httproute -n aiwb
```

The inference / API-key path is separate. `ai-gateway-discovery` currently
emits Envoy AI Gateway `AIGatewayRoute` and Envoy Gateway `SecurityPolicy`
objects (including `workloads-extauth`), so that chart needs those CRDs.
Skip it only for API/UI-only installs; model serving needs that chart or
an equivalent Gateway policy on `workloads.<domain>`.

### Bringing Your Own Infrastructure

Several components marked **Substitutable** above can be replaced with your own
managed services or existing infrastructure. This is common in cloud environments
where managed databases, object storage, and load balancers are preferred.

| Component             | BYO Alternative                                        | What to Change                                                                                                                                                                                                                                                                                                                                                                                                                      |
| --------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **PostgreSQL (CNPG)** | Any PostgreSQL 14+ (RDS, Cloud SQL, self-hosted, etc.) | Skip the CNPG Operator and `*-cnpg` infrastructure charts. Create the `airm` and `aiwb` databases manually, then create the Kubernetes Secrets (`airm-cnpg-user`, `aiwb-cnpg-user`, etc.) pointing at your instance. Set host/port/database on the application charts: AIRM `airm-api.airm.postgresql.host` / `port` / `database` / `userSecretName`; AIWB `postgresql.host` / `port` / `database` / `username` / `userSecretName`. |
| **MinIO**             | AWS S3, GCS, Azure Blob Storage                        | Skip the MinIO Operator. Create the `minio-credentials` Secret with your cloud storage access keys. Configure the AIWB chart's S3 endpoint and bucket settings via Helm values, including `minio.externalUrl` -- the default targets the SeaweedFS convention and will not resolve for another object store.                                                                                                                        |
| **Gateway**           | Any Gateway API implementation                         | Install a controller and create a `Gateway` it will program. Override `airm-api.gateway.*` / `gateway.*` if it is not named `https` in `envoy-gateway-system`. See [Example Gateway for app routing](#example-gateway-for-app-routing). The bundled `ai-gateway-discovery` path is Envoy-specific; skip it only for API/UI-only installs — model serving needs that chart or equivalent `workloads.<domain>` auth.                  |
| **LGTM Stack**        | Existing Prometheus + Grafana                          | Ensure Prometheus is scraping GPU metrics from the AMD Device Metrics Exporter. Configure the AIRM and AIWB chart values to point at your Prometheus query endpoint.                                                                                                                                                                                                                                                                |

> **Note**: For AIRM, Keycloak is **not** substitutable. AIRM uses the Keycloak
> Admin API at runtime for user, group, and role management. A generic OIDC
> provider cannot replace it without re-implementing these admin operations.
>
> Standalone AIWB logs in through any OIDC issuer. See
> [AIWB with another OIDC issuer](#aiwb-with-another-oidc-issuer).

### AIWB with another OIDC issuer

The AIWB chart has an `oidc` block. When it is empty, the chart derives the
values from the `keycloak` block, so an installation with Keycloak needs no
change. To use another issuer, set the block:

```yaml
oidc:
  issuer: https://auth.example.com # the public issuer URL, the `iss` of the tokens
  internalUrl: http://dex.dex.svc:5556 # the issuer as the Pods reach it, optional
  clientId: aiwb
  secretName: aiwb-oidc-client-secret # key `value` holds the client secret
  jwksUrl: http://dex.dex.svc:5556/keys # the JWKS as the API reaches it, required
  audience: aiwb # optional, empty means not checked
  scopes: "openid profile email" # optional, this is also the default
```

`jwksUrl` is required as soon as `issuer` or `internalUrl` is set. The chart
knows the JWKS path of Keycloak only, so it does not derive one for another
issuer.

The issuer must give a confidential client with the authorization code flow
and the redirect URI `https://<aiwbui host>/api/auth/callback/oidc`. The
access token must be a signed JWT with the `email` claim, and with the
`groups` claim when the installation is not standalone. The UI reads the
token, userinfo and JWKS endpoints from the discovery document of
`internalUrl` and replaces the `issuer` prefix of each with `internalUrl`.

The discovery document that the issuer serves on `internalUrl` must name the
public `issuer`. The UI rejects a document with another issuer, and a token
minted through `internalUrl` would carry that other issuer as `iss`, which the
API rejects. Keycloak gives the public issuer on every address when
`KC_HOSTNAME` is set to the public URL. cluster-forge sets it, and so does the
manual installation. An installation with its own Keycloak must set it before
the upgrade to this release.

The chart renders the block as environment variables. The UI reads
`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ISSUER` and
`OIDC_ISSUER_INTERNAL_URL`, and accepts the former names `KEYCLOAK_ID`,
`KEYCLOAK_SECRET`, `KEYCLOAK_ISSUER` and `KEYCLOAK_ISSUER_INTERNAL_URL` as a
fallback, so a chart or a `.env.local` file that still sets the former names
works. The fallback is temporary and goes away in a later release. The UI also
reads `OIDC_SCOPES`, which the chart renders from `oidc.scopes`; the default is
`openid profile email`. The API reads `OIDC_JWKS_URL`, `OIDC_ISSUER` and
`OIDC_AUDIENCE`; without them it derives the JWKS URL and the issuer from
`KEYCLOAK_INTERNAL_URL`, `KEYCLOAK_PUBLIC_URL` and `KEYCLOAK_REALM`.

The API always checks the `iss` claim of the access token against
`OIDC_ISSUER`. There is no value that turns the check off. A token from
another issuer gets 401. The audience check is different: it stays off until
`oidc.audience` gives a value, because a Keycloak access token and a Dex
access token carry different audiences.

### Example Keycloak install

These charts do not install Keycloak. They expect a Service at
`keycloak.keycloak.svc.cluster.local:8080` (override with
`airm-api.airm.keycloak.internalUrl` / `keycloak.internalUrl`) and a
browser-facing URL `https://kc.<YOUR-DOMAIN>` (override with
`airm-api.airm.keycloak.publicUrl` / `keycloak.publicUrl`).

The example below is a **dev-mode** Keycloak (`start-dev`) that imports
[apps/api/airm-realm.json](../apps/api/airm-realm.json) — the same realm file
docker-compose uses. It is enough for a local or evaluation cluster. Use the
Keycloak Operator (or cluster-forge) in production.

The committed realm file contains client secrets (including the
`realm-management/realm-admin` admin client and the confidential `k8s` OIDC
client) and a known `devuser` password hash. **Rotate every client secret and
set a fresh `devuser` password before import** (the commands below do that).
Do not reuse the repository values on a cluster that is reachable beyond your
laptop.

Run from `helm/` so the realm path resolves:

```bash
# Replace with your domain. Quote it so the unreplaced placeholder is not
# parsed as a shell redirection.
DOMAIN='<YOUR-DOMAIN>'

kubectl create namespace keycloak 2>/dev/null || true
kubectl label namespace keycloak airm.silogen.ai/gateway-routes=true --overwrite

# Add this cluster's UI callback URLs onto the chart-default UI client before import.
# Chart default clientId is 354a0fa1-35ac-4a6d-9c4d-d661129c2cd0 (not "k8s").
# configure.sh authenticates as devuser@<appDomain>, so rewrite the sample user to match.
# Rotate EVERY committed client secret — they are public. The admin client is
# realm-admin, and AIRM reads the confidential `k8s` client secret live from
# Keycloak to build onboarded-cluster kubeconfigs, so rotate it too (or delete
# the `k8s` client if you do not need cluster OIDC).
# Also set devuser's password: the committed realm ships a known hash, and
# rotating client secrets does not change it. DEV_USER_PASSWORD must match the
# airm-user-credentials Secret below. Provide a non-default value beyond local dev.
# HTTPS-only by default. Set LOCAL_HTTP=true ONLY on an isolated local cluster
# to also allow plaintext http:// OAuth redirects — never on a shared install.
LOCAL_HTTP=${LOCAL_HTTP:-false}
DEV_USER_PASSWORD=${DEV_USER_PASSWORD:-$(openssl rand -hex 24)}
KC_ADMIN_PASSWORD=${KC_ADMIN_PASSWORD:-$(openssl rand -hex 24)}
UI_SECRET=$(openssl rand -hex 24)
ADMIN_SECRET=$(openssl rand -hex 24)
K8S_SECRET=$(openssl rand -hex 24)
jq --arg d "$DOMAIN" --arg ui "$UI_SECRET" --arg adm "$ADMIN_SECRET" \
   --arg k8s "$K8S_SECRET" --arg pw "$DEV_USER_PASSWORD" --arg http "$LOCAL_HTTP" '
  .clients |= map(
    if .clientId == "354a0fa1-35ac-4a6d-9c4d-d661129c2cd0" then
      .secret = $ui
      | .redirectUris = (.redirectUris
        + ["https://airmui.\($d)/*", "https://aiwbui.\($d)/*"]
        + (if $http == "true" then ["http://airmui.\($d)/*", "http://aiwbui.\($d)/*"] else [] end)
        | unique)
      | .webOrigins = (.webOrigins
        + ["https://airmui.\($d)", "https://aiwbui.\($d)"]
        + (if $http == "true" then ["http://airmui.\($d)", "http://aiwbui.\($d)"] else [] end)
        | unique)
    elif .clientId == "k8s" then
      .secret = $k8s
    elif (.serviceAccountsEnabled == true and .secret != null) then
      .secret = $adm
    else . end)
  | .users |= map(
    if (.username | startswith("devuser@")) then
      .username = "devuser@\($d)" | .email = "devuser@\($d)"
      | .credentials = [{"type": "password", "value": $pw, "temporary": false}]
    else . end)
' ../apps/api/airm-realm.json > /tmp/airm-realm.json
# Realm JSON includes the rotated realm-admin client secret; keep it out of ConfigMaps.
kubectl -n keycloak create secret generic airm-realm \
  --from-file=airm-realm.json=/tmp/airm-realm.json

kubectl -n keycloak create secret generic keycloak-bootstrap-admin \
  --from-literal=username=admin \
  --from-literal=password="$KC_ADMIN_PASSWORD"

# If your Gateway is not named https in envoy-gateway-system, edit parentRefs.
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: keycloak
  namespace: keycloak
spec:
  replicas: 1
  selector:
    matchLabels:
      app: keycloak
  template:
    metadata:
      labels:
        app: keycloak
    spec:
      containers:
        - name: keycloak
          image: keycloak/keycloak:26.2
          args:
            - start-dev
            - --import-realm
            - --http-enabled=true
            - --hostname-strict=false
            - --proxy-headers=xforwarded
          env:
            - name: KC_BOOTSTRAP_ADMIN_USERNAME
              valueFrom:
                secretKeyRef:
                  name: keycloak-bootstrap-admin
                  key: username
            - name: KC_BOOTSTRAP_ADMIN_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: keycloak-bootstrap-admin
                  key: password
            - name: KC_HOSTNAME
              value: kc.${DOMAIN}
            - name: KC_HTTP_ENABLED
              value: "true"
          ports:
            - containerPort: 8080
              name: http
          readinessProbe:
            httpGet:
              path: /realms/master
              port: http
            initialDelaySeconds: 30
            periodSeconds: 10
          resources:
            requests:
              cpu: 200m
              memory: 768Mi
            limits:
              memory: 1Gi
          volumeMounts:
            - name: realm
              mountPath: /opt/keycloak/data/import
              readOnly: true
      volumes:
        - name: realm
          secret:
            secretName: airm-realm
---
apiVersion: v1
kind: Service
metadata:
  name: keycloak
  namespace: keycloak
spec:
  selector:
    app: keycloak
  ports:
    - name: http
      port: 8080
      targetPort: http
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: keycloak
  namespace: keycloak
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: https
      namespace: envoy-gateway-system
  hostnames:
    - kc.${DOMAIN}
  rules:
    - backendRefs:
        - name: keycloak
          port: 8080
      matches:
        - path:
            type: PathPrefix
            value: /
EOF
```

Wait until Keycloak is Ready (`kubectl wait -n keycloak --timeout=5m --for=condition=Ready pod -l app=keycloak`)
before installing the AIRM chart. The readiness probe delays its first check
by 30s, so a short default timeout can expire before the pod reports Ready. Put the rotated client secrets from the
**imported** realm file (`/tmp/airm-realm.json` after the rewrite above)
into the secret path you use; do not invent new client IDs, and do not copy
secrets from the repository file.

- **Option A**: update the backend keys `airm-keycloak-admin-client-id`,
  `airm-keycloak-admin-client-secret`, and `airm-ui-keycloak-secret` (see
  [Option A](#option-a-external-secrets-operator)) so ESO syncs credentials
  that match the imported realm.
- **Option B**: copy the same values into the Kubernetes Secrets (see
  [Option B](#option-b-manual-secret-creation)).

### Keycloak Realm Setup

The AIRM application requires a realm (default name: `airm`) with the following
resources. Importing `apps/api/airm-realm.json` as in the example above
creates them. You can also create them manually in the Keycloak Admin Console.

Keycloak must run with `KC_HOSTNAME` set to its public URL, so that the
discovery document names the public issuer on the in-cluster address too. See
[AIWB with another OIDC issuer](#aiwb-with-another-oidc-issuer).

**Required Clients:**

| Client Purpose           | Type         | Helm Value / Secret                                                                                                                                                                                                        | Notes                                                                                                                                                                                                                                                                                      |
| ------------------------ | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **UI login client**      | Confidential | Client ID `airm-api.airm.keycloak.clientId` / `keycloak.clientId` (chart default: `354a0fa1-35ac-4a6d-9c4d-d661129c2cd0`). Secret in `airm-keycloak-ui-creds` (`KEYCLOAK_SECRET`) and `aiwb-ui-keycloak-secret` (`value`). | Used by the AIRM and AIWB UIs for user login (OIDC authorization code flow). Add redirect URIs for `airmui.<YOUR-DOMAIN>` and `aiwbui.<YOUR-DOMAIN>`. The realm file also contains a `k8s` client (wildcard redirects) used by kube OIDC / E2E, not by the app charts' default `clientId`. |
| **Admin service client** | Confidential | Client ID and secret in the `airm-keycloak-admin-client` Secret (`client-id`, `client-secret`). In `airm-realm.json` this is the client whose service account has `realm-management/realm-admin`.                          | Used by the AIRM API for server-to-server Keycloak operations at startup.                                                                                                                                                                                                                  |

**Required Realm Roles:**

| Role                     | Purpose                                                   |
| ------------------------ | --------------------------------------------------------- |
| `Platform Administrator` | Grants full platform access. Assign to at least one user. |

**Client Mappers (on the UI login client):**

Add protocol mappers so that the OIDC token includes the user's realm roles:

- **Mapper type**: User Realm Role → Token Claim Name: `realm_access.roles`
- **Mapper type**: User Attribute (email, firstName, lastName) → Token Claims

**Initial User:**

Create at least one user with a verified email, first name, last name, and the
`Platform Administrator` role assigned. This user will be used during
[Step 5: Onboard a Cluster](#step-5-onboard-a-cluster). The onboarding Job logs
in as `devuser@<appDomain>` (the same value as `airm-api.airm.appDomain` /
`appDomain`). The jq rewrite above maps the sample user in `airm-realm.json`
to that email and sets its password from `DEV_USER_PASSWORD` (rotating the
committed client secrets does not change the shipped password hash). Put the
same value in `airm-user-credentials` (`USER_PASSWORD`); the two must match or
onboarding fails. Use a non-default password for anything beyond an isolated
local cluster — the value documented in
[apps/api/airm/README.md](../apps/api/airm/README.md) is a known Platform
Administrator credential.

> **Automated import**: Prefer [apps/api/airm-realm.json](../apps/api/airm-realm.json)
> with the example Deployment above. [cluster-forge](https://github.com/silogen/cluster-forge)
> has a production-oriented realm import as well.

### StorageClass Requirements

The infrastructure charts default to a StorageClass named `default`. If your
cluster uses a different name, override it during installation. Note that each
chart uses a different Helm value key:

| Chart           | Override Key                                                             |
| --------------- | ------------------------------------------------------------------------ |
| `airm-cnpg`     | `--set storage.storageClass=<NAME> --set walStorage.storageClass=<NAME>` |
| `aiwb-cnpg`     | `--set storage.storageClass=<NAME> --set walStorage.storageClass=<NAME>` |
| `airm-rabbitmq` | `--set persistence.storageClassName=<NAME>`                              |

> **cluster-forge note**: The [cluster-forge](https://github.com/silogen/cluster-forge)
> deployment scripts additionally create `multinode` (ReadWriteMany) and
> `mlstorage` (high-throughput) StorageClasses for AIWB workspace and dataset
> PVCs. These are cluster-forge-specific and not required by the Helm charts in
> this repository — the charts use whatever StorageClass is set in their values.
> See the [cluster-forge StorageClasses docs](https://github.com/silogen/cluster-forge/tree/main/docs/manual_helm_install/components/storage_classes.md)
> for details.

> **Tip**: On local development clusters (kind, minikube), you typically only
> have a single `standard` StorageClass. Pass that name with the per-chart key
> in the table above (`storage.storageClass` plus `walStorage.storageClass` for
> CNPG; `persistence.storageClassName` for RabbitMQ).

### Node Requirements for CNPG Clusters

The `airm-cnpg` and `aiwb-cnpg` charts spread PostgreSQL instances across
distinct nodes, so that losing one node cannot take down more than one instance.
The spread is a scheduling preference by default
(`podAntiAffinityType: preferred` on `topologyKey: kubernetes.io/hostname`), so
instances land on separate nodes where the cluster has them and co-schedule
where it does not. `aiwb-cnpg` defaults to 3 instances, `airm-cnpg` to 1.

A cluster with fewer schedulable nodes than instances still comes up, but the
co-scheduled instances share a failure domain, and draining that node disrupts
all of them at once. To make the spread binding instead, set
`podAntiAffinityType: required`, which holds surplus instances `Pending` until
enough nodes exist.

A `PodDisruptionBudget` guards the primary against eviction while a replica is
still catching up. It only means something when there is a second replica to
keep serving, so it follows the instance count: off for a single instance, on
for two or more. A single-instance PDB permits zero disruptions, which blocks
`kubectl drain` on the node hosting it and stalls node maintenance until someone
disables it by hand. Set `enablePDB` explicitly to override in either direction.

Both charts accept the same overrides:

| Override Key                         | Effect                                    |
| ------------------------------------ | ----------------------------------------- |
| `--set instances=<N>`                | Number of PostgreSQL instances            |
| `--set enablePDB=false`              | Never create a PDB, never block a drain   |
| `--set podAntiAffinityType=required` | Require the spread, leave surplus Pending |
| `--set topologyKey=<KEY>`            | Spread across a different failure domain  |

> **Tip**: On single-node clusters (kind, minikube, single-node evaluation
> deployments), install `aiwb-cnpg` with `--set instances=1`. Three instances on
> one node cost three times the resources for no added resilience, and the PDB
> switches itself off so node maintenance is not blocked.

### Scripted Installation for Standalone AIWB

For standalone AIWB deployments (without AIRM), the
[cluster-forge manual install scripts](https://github.com/silogen/cluster-forge/tree/main/docs/manual_helm_install)
provide an automated `install_base.sh` that installs all dependencies and the
AIWB chart in a single command. This is useful for quick setup, demos, or as a
reference for which components and versions are needed.

```bash
# Example: standalone AIWB using cluster-forge scripts
git clone https://github.com/silogen/cluster-forge.git
cd cluster-forge/docs/manual_helm_install/scripts
bash install_base.sh
```

See the [cluster-forge manual install README](https://github.com/silogen/cluster-forge/tree/main/docs/manual_helm_install)
for details on pluggable component flags and customization.

---

## Step 2: Create Secrets

The application charts expect certain Kubernetes Secrets to exist before installation.
There are two approaches to providing these secrets.

### Option A: External Secrets Operator

If you have External Secrets Operator installed with a configured `ClusterSecretStore`,
use the infrastructure ExternalSecret charts to sync secrets from your backend.

The charts expect a `ClusterSecretStore` named `openbao-secret-store` by default
(configurable via the `externalSecretStore` value in each chart).

An installation without OpenBao sets `openBao.enabled: false` in the AIWB
chart, and sets `openbaoToken.enabled: false` in the `aiwb-external-secrets`
chart. The charts then render no OpenBao configuration and need no
`aiwb-openbao-token` Secret. The API refuses to create, rebind or delete API
keys with an error, and the UI hides the API-key page. Set the two values
together: they live in two separate releases and nothing checks that they
agree. The other bootstrap Secrets still need the `ClusterSecretStore` when
this chart syncs them.

This is an install-time choice. Do not disable OpenBao on an installation that
already has API keys: the API refuses to start, because a key without its
store cannot be revoked. To resolve it, restore `openBao.enabled: true` and
`openbaoToken.enabled: true`, delete every API key, and only then disable
OpenBao again.

Your secret backend must contain the following keys. Each key must be stored as an
object with a `value` field (e.g., `{"value": "postgres"}`), not as a raw string,
because the ExternalSecret templates read `property: value` from each entry.

**AIRM Secrets** (synced by `infrastructure/airm-external-secrets`):

| Secret Name                  | Backend Keys                                                         | Purpose                           |
| ---------------------------- | -------------------------------------------------------------------- | --------------------------------- |
| `airm-cnpg-superuser`        | `airm-cnpg-superuser-username`, `airm-cnpg-superuser-password`       | PostgreSQL superuser credentials  |
| `airm-cnpg-user`             | `airm-cnpg-user-username`, `airm-cnpg-user-password`                 | PostgreSQL application user       |
| `airm-keycloak-admin-client` | `airm-keycloak-admin-client-id`, `airm-keycloak-admin-client-secret` | Keycloak admin client credentials |
| `airm-keycloak-ui-creds`     | `airm-ui-keycloak-secret`                                            | Keycloak UI client secret         |
| `airm-user-credentials`      | `keycloak-initial-devuser-password`                                  | Initial dev user password         |
| `airm-rabbitmq-admin`        | `airm-rabbitmq-user-username`, `airm-rabbitmq-user-password`         | RabbitMQ admin credentials        |
| `airm-secrets-airm`          | `airm-ui-auth-nextauth-secret`                                       | AIRM UI NextAuth secret           |

**AIWB Secrets** (synced by `infrastructure/aiwb-external-secrets`):

| Secret Name                | Backend Keys                                                   | Purpose                                                                                                                                               |
| -------------------------- | -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `aiwb-cnpg-superuser`      | `aiwb-cnpg-superuser-username`, `aiwb-cnpg-superuser-password` | PostgreSQL superuser credentials                                                                                                                      |
| `aiwb-cnpg-user`           | `aiwb-cnpg-user-password` (username set from chart values)     | PostgreSQL application user                                                                                                                           |
| `aiwb-ui-keycloak-secret`  | `airm-ui-keycloak-secret`                                      | OIDC client secret of the UI (Keycloak by default)                                                                                                    |
| `aiwb-nextauth-secret`     | `aiwb-ui-auth-nextauth-secret`                                 | AIWB UI NextAuth secret                                                                                                                               |
| `minio-credentials`        | `minio-api-access-key`, `minio-api-secret-key`                 | MinIO access credentials                                                                                                                              |
| `cluster-auth-admin-token` | `cluster-auth-admin-token`                                     | Legacy external-secrets chart input; not consumed by the AIWB app. Keep the backend key only to let the chart's ungated leftover ExternalSecret sync. |
| `aiwb-openbao-token`       | `aiwb-openbao-token`                                           | Scoped OpenBao write token (`apikeys-write-policy`) for the API-key KV path. Not needed when `openbaoToken.enabled: false`.                           |

### Option B: Manual Secret Creation

Option B replaces only _bootstrap_ secret synchronization. Skip the
`infrastructure/*-external-secrets` chart installations and create the secrets
directly in the appropriate namespaces.

With OpenBao enabled (the default), External Secrets Operator and a Ready
`ClusterSecretStore` are still required at runtime: AIWB creates per-key
`ExternalSecret` objects, and ESO materializes the gateway credential Secrets.
With `openBao.enabled: false` (AIWB) and `openbaoToken.enabled: false`
(`aiwb-external-secrets`), there is no API-key store and Option B needs no
`ClusterSecretStore` for AIWB. A combined AIRM install still defaults
`airm-api.airm.includeDemoSetup` to `true`, and `airm-configure` creates an
ExternalSecret targeting `openbao-secret-store` and waits for it. Pass
`--set airm-api.airm.includeDemoSetup=false` and onboard another way (see
[Step 5](#step-5-onboard-a-cluster)) if you are not providing that store.

MinIO key names differ by layer: the secret backend (Option A) uses
`minio-api-access-key` / `minio-api-secret-key`. The Kubernetes Secret that
AIWB reads uses `minio-access-key` / `minio-secret-key`. Put the K8s key names
in a manual Secret; do not copy the backend names into `kubectl create secret`.

Create the namespaces first:

```bash
kubectl create namespace airm 2>/dev/null || true
kubectl create namespace aiwb 2>/dev/null || true
kubectl label namespace airm aiwb airm.silogen.ai/gateway-routes=true --overwrite
```

**AIRM Secrets** (namespace: `airm`):

| Secret Name                  | Required Data Keys                          |
| ---------------------------- | ------------------------------------------- |
| `airm-cnpg-superuser`        | `username`, `password`                      |
| `airm-cnpg-user`             | `username`, `password`                      |
| `airm-keycloak-admin-client` | `client-id`, `client-secret`                |
| `airm-keycloak-ui-creds`     | `KEYCLOAK_SECRET`                           |
| `airm-user-credentials`      | `USER_PASSWORD`                             |
| `airm-rabbitmq-admin`        | `username`, `password`, `default_user.conf` |
| `airm-secrets-airm`          | `NEXTAUTH_SECRET`                           |

**AIWB Secrets** (namespace: `aiwb`):

| Secret Name               | Required Data Keys                           |
| ------------------------- | -------------------------------------------- |
| `aiwb-cnpg-superuser`     | `username`, `password`                       |
| `aiwb-cnpg-user`          | `username`, `password`                       |
| `aiwb-ui-keycloak-secret` | `value`                                      |
| `aiwb-nextauth-secret`    | `NEXTAUTH_SECRET`                            |
| `minio-credentials`       | `minio-access-key`, `minio-secret-key`       |
| `aiwb-openbao-token`      | `value` (omit when `openBao.enabled: false`) |

**Standalone AIWB extras** (only when `standAloneMode: true`):

| Secret Name         | Namespace                                | Required Data Keys                     |
| ------------------- | ---------------------------------------- | -------------------------------------- |
| `minio-credentials` | `defaultNamespace` (default `workbench`) | `minio-access-key`, `minio-secret-key` |

Create that namespace before this MinIO secret. When using Option A, pass
`--set standAloneMode=true` on the `aiwb-external-secrets` chart so it renders
these extras. If you override `defaultNamespace`, set the same value on both
the `aiwb` chart and `aiwb-external-secrets` — they default to `workbench`
independently.

Standalone `aiwb-external-secrets` also renders an `aiwb-user-credentials`
Secret (`USER_PASSWORD`), but the current AIWB chart and workloads do not
consume it. It is a leftover; no manual creation is required.

Example commands:

```bash
# PostgreSQL credentials
kubectl create secret generic airm-cnpg-user -n airm \
  --from-literal=username=airm_user \
  --from-literal=password='<your-secure-password>'

kubectl create secret generic airm-cnpg-superuser -n airm \
  --from-literal=username=postgres \
  --from-literal=password='<your-secure-password>'

# Keycloak clients — copy secrets from the realm file you imported (after
# rotating them). Do not use apps/api/airm-realm.json as-is: those secrets
# are public and the admin service account has realm-admin.
REALM=/tmp/airm-realm.json
UI_CLIENT_ID='354a0fa1-35ac-4a6d-9c4d-d661129c2cd0'
UI_SECRET=$(jq -r --arg id "$UI_CLIENT_ID" '.clients[] | select(.clientId==$id) | .secret' "$REALM")
ADMIN_ID=$(jq -r '.clients[] | select(.serviceAccountsEnabled==true and .secret != null) | .clientId' "$REALM")
ADMIN_SECRET=$(jq -r '.clients[] | select(.serviceAccountsEnabled==true and .secret != null) | .secret' "$REALM")

kubectl create secret generic airm-keycloak-admin-client -n airm \
  --from-literal=client-id="$ADMIN_ID" \
  --from-literal=client-secret="$ADMIN_SECRET"

kubectl create secret generic airm-keycloak-ui-creds -n airm \
  --from-literal=KEYCLOAK_SECRET="$UI_SECRET"

kubectl create secret generic aiwb-ui-keycloak-secret -n aiwb \
  --from-literal=value="$UI_SECRET"

# Initial user password (used by configure.sh). Must equal the DEV_USER_PASSWORD
# set on the devuser credential in the jq rewrite above, or the onboarding token
# grant fails. Reuse the same shell variable if you are still in that session.
kubectl create secret generic airm-user-credentials -n airm \
  --from-literal=USER_PASSWORD="${DEV_USER_PASSWORD:?set DEV_USER_PASSWORD to the value imported into the realm}"

# RabbitMQ admin -- password and default_user.conf must match
RABBITMQ_ADMIN_PASSWORD='<your-secure-password>'
kubectl create secret generic airm-rabbitmq-admin -n airm \
  --from-literal=username=admin \
  --from-literal=password="${RABBITMQ_ADMIN_PASSWORD}" \
  --from-literal=default_user.conf="$(printf 'default_user = admin\ndefault_pass = %s' "${RABBITMQ_ADMIN_PASSWORD}")"

# AIRM UI NextAuth secret
kubectl create secret generic airm-secrets-airm -n airm \
  --from-literal=NEXTAUTH_SECRET='<random-string>'

# AIWB PostgreSQL credentials
kubectl create secret generic aiwb-cnpg-user -n aiwb \
  --from-literal=username=aiwb_user \
  --from-literal=password='<your-secure-password>'

kubectl create secret generic aiwb-cnpg-superuser -n aiwb \
  --from-literal=username=postgres \
  --from-literal=password='<your-secure-password>'

# AIWB NextAuth secret
kubectl create secret generic aiwb-nextauth-secret -n aiwb \
  --from-literal=NEXTAUTH_SECRET='<random-string>'

# MinIO credentials
kubectl create secret generic minio-credentials -n aiwb \
  --from-literal=minio-access-key='<minio-access-key>' \
  --from-literal=minio-secret-key='<minio-secret-key>'

# OpenBao write token (omit when openBao.enabled=false)
kubectl create secret generic aiwb-openbao-token -n aiwb \
  --from-literal=value='<openbao-apikeys-write-token>'

# Standalone AIWB only. Use the same defaultNamespace as the aiwb chart
# (default: workbench) for this MinIO secret.
# kubectl create namespace "${AIWB_DEFAULT_NS:-workbench}"
# kubectl create secret generic minio-credentials -n "${AIWB_DEFAULT_NS:-workbench}" \
#   --from-literal=minio-access-key='<minio-access-key>' \
#   --from-literal=minio-secret-key='<minio-secret-key>'

```

---

## Step 3: Install Infrastructure Charts

Install the infrastructure charts in the following order from the `helm/` directory.
These create the PostgreSQL databases and RabbitMQ cluster that the application charts
depend on.

**1. ExternalSecret resources** (skip if using [Option B](#option-b-manual-secret-creation)):

```bash
# AIRM secrets
helm install airm-infra-external-secrets ./infrastructure/airm-external-secrets \
  -n airm --create-namespace

# AIWB secrets
helm install aiwb-infra-external-secrets ./infrastructure/aiwb-external-secrets \
  -n aiwb --create-namespace
```

If the `ClusterSecretStore` is not named `openbao-secret-store`, pass the same
name on every ESO chart (`--set externalSecretStore=<NAME>`) **and** on the
AIWB app chart (`--set openBao.secretStoreRef=<NAME>`). Combined AIRM still
defaults `airm-api.airm.includeDemoSetup` to `true`, and `airm-configure`
hard-codes `secretStoreRef.name: openbao-secret-store` on its demo
ExternalSecret. Keep a store with that default name for the demo Job, or
pass `--set airm-api.airm.includeDemoSetup=false` and onboard another way
(see [Step 5](#step-5-onboard-a-cluster)). For standalone AIWB, also pass
`--set standAloneMode=true` so the chart renders the workload-namespace
MinIO secret. If you override `defaultNamespace`
on the `aiwb` chart, pass the same `--set defaultNamespace=<NS>` here. When
OpenBao is disabled, pass `--set openbaoToken.enabled=false` so the chart
does not wait on `aiwb-openbao-token`. Skipping these charts (Option B)
with OpenBao disabled does not skip `airm-configure`: pass
`--set airm-api.airm.includeDemoSetup=false` on AIRM unless that store exists.

Wait for the ExternalSecret resources to sync and the corresponding Kubernetes Secrets to
be created before proceeding:

```bash
kubectl get externalsecrets -n airm
kubectl get externalsecrets -n aiwb
```

All ExternalSecrets should show `SecretSynced` status, with one expected exception:
`cluster-auth-admin-token` stays un-synced unless you provisioned that key in your backend.
It is a legacy leftover the chart still renders (see the cluster-auth row in Tier 2), not a
failed install, and nothing in the current AIWB app consumes it.

**2. PostgreSQL clusters** (requires CNPG operator and database secrets to exist):

```bash
# AIRM database
helm install airm-infra-cnpg ./infrastructure/airm-cnpg \
  -n airm --create-namespace

# AIWB database
helm install aiwb-infra-cnpg ./infrastructure/aiwb-cnpg \
  -n aiwb --create-namespace
```

If your cluster's StorageClass is not named `default`, override it:

```bash
helm install airm-infra-cnpg ./infrastructure/airm-cnpg \
  -n airm \
  --set storage.storageClass=<YOUR-STORAGE-CLASS> \
  --set walStorage.storageClass=<YOUR-STORAGE-CLASS>
```

**3. RabbitMQ cluster** (requires cert-manager, RabbitMQ operator, and admin secret):

```bash
helm install airm-infra-rabbitmq ./infrastructure/airm-rabbitmq \
  -n airm --create-namespace
```

To override the StorageClass for RabbitMQ:

```bash
helm install airm-infra-rabbitmq ./infrastructure/airm-rabbitmq \
  -n airm \
  --set persistence.storageClassName=<YOUR-STORAGE-CLASS>
```

Wait for all infrastructure components to become ready before proceeding:

```bash
# PostgreSQL clusters should be "Cluster in healthy state"
kubectl get clusters.postgresql.cnpg.io -n airm
kubectl get clusters.postgresql.cnpg.io -n aiwb

# RabbitMQ cluster should be running
kubectl get rabbitmqclusters -n airm
```

---

## Step 4: Install Application Charts

### AIRM (AI Resource Manager)

The AIRM umbrella chart deploys the API, UI, and Agent. See the individual chart READMEs
for detailed configuration options:

- [airm/README.md](airm/README.md) -- Umbrella chart overview
- [airm/charts/airm-api/README.md](airm/charts/airm-api/README.md) -- API and UI configuration
- [airm/charts/airm-agent/README.md](airm/charts/airm-agent/README.md) -- Agent configuration

```bash
# From a git checkout, stamp published image tags. Empty tag inherits Chart.appVersion
# 0.0.0 and pods stay ImagePullBackOff. OCI charts already stamp a release tag.
# Example: GitHub release 2.0.3
APP_IMAGE_TAG=2.0.3

helm install airm ./airm \
  -n airm --create-namespace \
  --set airm-api.airm.appDomain=<YOUR-DOMAIN> \
  --set airm-api.airm.backend.image.tag=${APP_IMAGE_TAG} \
  --set airm-api.airm.frontend.image.tag=${APP_IMAGE_TAG} \
  --set airm-agent.airm.image.tag=${APP_IMAGE_TAG}
```

Standalone AIRM without OpenBao/MinIO: the default `airm-configure` Job still
creates a demo ExternalSecret targeting `openbao-secret-store`. Pass
`--set airm-api.airm.includeDemoSetup=false` for that mode.

> **Image keys**: `airm-api.airm.backend.image.tag`, `airm-api.airm.frontend.image.tag`,
> `airm-agent.airm.image.tag`. AIWB: `backend.image.tag`, `frontend.image.tag`.
> The `ai-gateway-discovery` chart defaults to `silogenai/ai-gateway-discovery:0.1.0`.
> Published `amdenterpriseai/*` tags are typically `linux/amd64`; on Apple Silicon
> kind they run under emulation if the node allows it.

> **Gateway configuration**: The charts create `HTTPRoute` resources; they do
> not install a gateway controller. Defaults attach to a Gateway named `https`
> in `envoy-gateway-system` (cluster-forge naming). Override with
> `--set airm-api.gateway.namespace=<NS> --set airm-api.gateway.gatewayName=<NAME>`
> (AIRM) and `--set gateway.namespace=<NS> --set gateway.gatewayName=<NAME>`
> (AIWB). See [Example Gateway for app routing](#example-gateway-for-app-routing).

### AIWB (AI Workbench)

> **Note**: The AIWB chart creates an `AIMClusterRuntimeConfig` resource, which requires
> AIM Engine CRDs to be installed on the cluster first (see
> [Tier 3 dependencies](#tier-3---aiml-stack-compute-plane)).

**Combined deployment** (default, with AIRM managing namespaces and authorization):

```bash
APP_IMAGE_TAG=2.0.3

helm install aiwb ./aiwb \
  -n aiwb --create-namespace \
  --set appDomain=<YOUR-DOMAIN> \
  --set backend.image.tag=${APP_IMAGE_TAG} \
  --set frontend.image.tag=${APP_IMAGE_TAG}
```

If you skip `ai-gateway-discovery`, add `--set aiGateway.enabled=false` so the
UI does not advertise `https://ai.<appDomain>`. Re-enable it when you install
that chart. If the `ClusterSecretStore` is not named `openbao-secret-store`,
add `--set openBao.secretStoreRef=<NAME>` (must match `externalSecretStore`
on the ESO charts). Combined AIRM's demo Job still hard-codes
`openbao-secret-store`; keep that store name for `includeDemoSetup` or
disable it (see [Step 3](#step-3-install-infrastructure-charts)). To disable
the API-key store, pass `--set openBao.enabled=false` here and
`--set openbaoToken.enabled=false` on `aiwb-external-secrets`.

**Standalone deployment** (single namespace, without AIRM -- requires Kyverno):

```bash
APP_IMAGE_TAG=2.0.3

helm install aiwb ./aiwb \
  -n aiwb --create-namespace \
  --set appDomain=<YOUR-DOMAIN> \
  --set standAloneMode=true \
  --set backend.image.tag=${APP_IMAGE_TAG} \
  --set frontend.image.tag=${APP_IMAGE_TAG}
```

If you override `defaultNamespace` (default `workbench`), pass the same
`--set defaultNamespace=<NS>` on `aiwb-external-secrets`. The same
`aiGateway.enabled` / `openBao.secretStoreRef` flags as the combined install
apply here.

### AI Gateway Discovery

Optional. Needed for the bundled OpenAI-compatible inference front door
(`ai.<YOUR-DOMAIN>`) **and** for fail-closed auth on AIM serving routes
(`workloads.<YOUR-DOMAIN>`). This chart reconciles the `workloads-extauth`
`SecurityPolicy`. Skip it only if you need AIRM/AIWB APIs and UIs and will
not serve models; without this chart or an equivalent Gateway policy, the
AIWB `workloads.<domain>` routes are unauthenticated. If you skip it, pass
`--set aiGateway.enabled=false` on the AIWB chart.

This chart currently emits Envoy AI Gateway `AIGatewayRoute` and Envoy
Gateway `SecurityPolicy` objects, plus Gateway API Inference Extension
`InferencePool`s. Install those CRDs and the AI Gateway controller first.
`SecurityPolicy` comes with the Envoy Gateway CRDs in
[Example Gateway for app routing](#example-gateway-for-app-routing). The
controller refuses to start if `controller.gateway.routeHostname` is empty.

```bash
kubectl apply --server-side \
  -f https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/v1.6.1/manifests.yaml

helm upgrade -i aieg-crd oci://docker.io/envoyproxy/ai-gateway-crds-helm \
  --version v1.1.0 \
  -n envoy-ai-gateway-system --create-namespace

helm upgrade -i aieg oci://docker.io/envoyproxy/ai-gateway-helm \
  --version v1.1.0 \
  -n envoy-ai-gateway-system --create-namespace

# The v1.1.0 chart names its deployment from the release (aieg-ai-gateway-helm),
# so wait on the release label rather than a fixed deployment name.
kubectl wait --timeout=5m -n envoy-ai-gateway-system \
  --for=condition=Available deployment -l app.kubernetes.io/instance=aieg

helm install ai-gateway-discovery ./ai-gateway-discovery \
  -n envoy-ai-gateway-system --create-namespace \
  --set controller.gateway.routeHostname=ai.<YOUR-DOMAIN>
```

The chart defaults `controller.gateway.name` to `https` and
`controller.gateway.namespace` to `envoy-gateway-system` (the same Gateway
the app HTTPRoutes use). Some cluster-forge deployments use a dedicated
Gateway named `ai-gateway` on a separate data plane. Use this instead of the
install above when that Gateway exists (`helm upgrade --install` is safe to
re-run). Set `controller.gateway.namespace` too whenever that Gateway is not
in `envoy-gateway-system`, or the generated `AIGatewayRoute`s attach to the
wrong namespace and stay unprogrammed:

```bash
helm upgrade --install ai-gateway-discovery ./ai-gateway-discovery \
  -n envoy-ai-gateway-system --create-namespace \
  --set controller.gateway.routeHostname=ai.<YOUR-DOMAIN> \
  --set controller.gateway.name=ai-gateway \
  --set controller.gateway.namespace=<GATEWAY-NS>
```

#### Audio (speech-to-text) request policy on the workloads route

Speech-to-text deployments serve multipart uploads at
`/v1/audio/transcriptions`. The AIWB UI points those at the per-service
workloads route
(`workloads.<YOUR-DOMAIN>/<namespace>/<workload-id>/...`), not the unified
`ai.<YOUR-DOMAIN>` front door. Two properties of that route make large audio
requests work:

- **Access control does not touch the body.** The `workloads-extauth`
  `SecurityPolicy` forwards each request to the workloads ext_authz handler,
  which makes the decision from the request **path** (which carries the workload
  id) plus the `Authorization` header. Because the policy sets no
  `bodyToExtAuth`, the request body is never sent to the handler — so a
  `multipart/form-data` upload is authorized without being decoded as JSON and
  without being buffered to a size ceiling. (The unified `ai.<YOUR-DOMAIN>`
  header-less path is different: it buffers the body up to the
  `ai-gateway-discovery` chart's `controller.bodyAuthMaxRequestBytes` (4 MiB by
  default) to read the model name — which is why the UI uses the per-service
  workloads URL for audio.)
- **The request timeout is sized for batch transcription.** Every generated
  AIM serving route inherits `aim.routing.requestTimeout` (default `30m`),
  which is the ceiling that matters for long transcription jobs.
  Tune it with `--set aim.routing.requestTimeout=<duration>` on the AIWB chart.

Because the workloads route **streams** the upload rather than buffering it,
these charts do not impose a hard per-route maximum body size; the effective
limit comes from your Gateway's connection buffering and the request timeout
above. A hard per-route upload-size cap would have to be set on the
AIM-engine-generated route itself and is planned as a follow-up.

### Chart defaults that assume cluster-forge service names

The AIWB chart's in-cluster URLs default to names cluster-forge publishes.
Override them on any other cluster or the API will talk to hosts that do not
exist:

| Value               | Chart default                                              |
| ------------------- | ---------------------------------------------------------- |
| `openBao.url`       | `http://openbao.cf-openbao.svc.cluster.local:8200`         |
| `minio.url`         | `http://filer-s3.seaweedfs-instance.svc.cluster.local:80`  |
| `minio.externalUrl` | empty, which falls back to `https://seaweed.<appDomain>`   |
| `prometheus.url`    | `http://lgtm-stack.otel-lgtm-stack.svc.cluster.local:9090` |

### Upgrading

To upgrade an existing installation after changing values or chart versions.
`--reuse-values` keeps Gateway, secret-store, standalone, and OpenBao
overrides from the original install; still `--set` any values you intend
to change (image tags here). Skip the `ai-gateway-discovery` upgrade if
you did not install that chart.

```bash
APP_IMAGE_TAG=2.0.3

helm upgrade airm ./airm \
  -n airm \
  --reuse-values \
  --set airm-api.airm.backend.image.tag=${APP_IMAGE_TAG} \
  --set airm-api.airm.frontend.image.tag=${APP_IMAGE_TAG} \
  --set airm-agent.airm.image.tag=${APP_IMAGE_TAG}

helm upgrade aiwb ./aiwb \
  -n aiwb \
  --reuse-values \
  --set backend.image.tag=${APP_IMAGE_TAG} \
  --set frontend.image.tag=${APP_IMAGE_TAG}

# Skip if you did not install the inference chart
helm upgrade ai-gateway-discovery ./ai-gateway-discovery \
  -n envoy-ai-gateway-system \
  --reuse-values \
  --set controller.gateway.routeHostname=ai.<YOUR-DOMAIN>
```

> **Note**: The `airm-configure` Job (see [Step 5](#step-5-onboard-a-cluster)) has a
> fixed name and no Helm hook, so `helm upgrade` does not re-run it even when
> `configure.sh` changes. To pick up a fix to the onboarding script on an existing
> install, delete the completed Job first so the upgrade recreates it:
>
> ```bash
> kubectl delete job airm-configure -n airm
> ```

---

## Step 5: Onboard a Cluster

After the AIRM API is running, you must register (onboard) the Kubernetes cluster so the
AIRM Agent can communicate with the API.

The AIRM chart includes a
[configure.sh](airm/charts/airm-api/files/configure.sh) script that automates this
process: it registers the cluster, creates the Agent's RabbitMQ credentials, sets up a
default project, and adds a dev user.

When `airm-api.airm.includeDemoSetup` is `true` (the default), the Helm chart creates a
Kubernetes Job that waits for the AIRM API to become healthy and then runs the script
automatically. Monitor it with:

```bash
kubectl get jobs -n airm
kubectl logs job/airm-configure -n airm -f
```

Once the Job completes successfully, proceed to [Verification](#verification).

If you set `airm-api.airm.includeDemoSetup: false`, you can run the script manually or use the
AIRM API directly. See the script source and
[airm/charts/airm-agent/README.md](airm/charts/airm-agent/README.md) for details on the
onboarding flow and Agent configuration.

---

## Verification

After installation, verify that the core components are running:

```bash
# Check AIRM pods are running
kubectl get pods -n airm

# Check AIWB pods are running
kubectl get pods -n aiwb

# Verify PostgreSQL clusters are healthy
kubectl get clusters.postgresql.cnpg.io -n airm
kubectl get clusters.postgresql.cnpg.io -n aiwb

# Verify RabbitMQ is running
kubectl get rabbitmqclusters -n airm

# Verify HTTPRoutes are attached (parent should be Accepted=True)
kubectl get httproutes -n airm
kubectl get httproutes -n aiwb

# Skip if you did not install the inference chart
kubectl get deploy -n envoy-ai-gateway-system
```

Once all pods are running, the services should be accessible at:

- **AIRM UI**: `https://airmui.<YOUR-DOMAIN>`
- **AIRM API**: `https://airmapi.<YOUR-DOMAIN>`
- **AIWB UI**: `https://aiwbui.<YOUR-DOMAIN>`
- **AIWB API**: `https://aiwbapi.<YOUR-DOMAIN>`
- **Keycloak**: `https://kc.<YOUR-DOMAIN>` (after applying the example HTTPRoute, or your own)
- **Inference gateway**: `https://ai.<YOUR-DOMAIN>` (only if you installed `ai-gateway-discovery`)
- **Workloads**: `https://workloads.<YOUR-DOMAIN>` (AIM Engine, not these app charts)
- **Workspaces**: `https://workspaces.<YOUR-DOMAIN>` (not created by these app charts; add an HTTPRoute separately)

---

## Local Development Notes

When running the platform on a local Kubernetes cluster (kind, minikube, Docker
Desktop), there are several differences from a production environment:

- **No GPU nodes**: The GPU operator, Device Metrics Exporter, and Kaiwo can be
  skipped. Model deployment and workload features will not be functional, but
  the AIRM and AIWB APIs and UIs will still be operational. **AIM Engine CRDs
  cannot be skipped**: the AIWB chart always creates an `AIMClusterRuntimeConfig`
  (`aim.eai.amd.com/v1alpha1`), so `helm install aiwb` fails unless those CRDs
  exist. Install AIM Engine (or at least its CRDs) even on a local cluster that
  will not serve models.
- **Local access without TLS**: The AIRM and AIWB UIs hard-code `NEXTAUTH_URL`
  to `https://airmui.<appDomain>` and `https://aiwbui.<appDomain>` with no Helm
  override. AIWB also defaults inference, workloads, workspaces, and Seaweed
  URLs to `https://`. An HTTP Gateway listener plus
  `--set airm-api.airm.keycloak.publicUrl=http://kc.localhost`
  `--set keycloak.publicUrl=http://kc.localhost` only changes Keycloak;
  browser OAuth still redirects to HTTPS. For a working local install, terminate
  TLS on the Gateway, or `kubectl port-forward` to the API/UI Services for
  health checks and skip Gateway-based login. A dummy `Gateway` with no
  controller is not required for Helm; it only names a parent and leaves
  HTTPRoutes unaccepted until a controller programs the Gateway.
- **Email needs a TLD**: APIs and UIs come up with `appDomain=localhost`, but
  onboarding and E2E beyond health checks use the user `devuser@<appDomain>`.
  AIRM rejects `devuser@localhost` because it is not an email with a TLD. For
  Step 5 and Robot suites other than health, use a domain with a TLD
  (`local.test`, `example.com`) and point `*.local.test` (or equivalent) at
  the Gateway.
- **Project Ready needs Kaiwo**: Skipping Kaiwo (typical on a GPU-less laptop)
  leaves new projects in `Failed` because the AIRM agent updates a
  `KaiwoQueueConfig` named `kaiwo`. Health checks still pass; project-provisioning
  E2E will not.
- **kind has no LoadBalancer**: Envoy Gateway's default data-plane Service is
  `type: LoadBalancer`, so the Gateway stays `Programmed=False`
  (`AddressNotAssigned`) even when HTTPRoutes are `Accepted`. Point the Gateway
  at an `EnvoyProxy` whose `envoyService.type` is `ClusterIP` or `NodePort`,
  install MetalLB / `cloud-provider-kind`, or `kubectl port-forward` to the
  data-plane Service. HTTPRoute `Accepted=True` is the routing check; an
  assigned address is only needed to hit the Gateway from outside the cluster.

  Example `EnvoyProxy` + Gateway attachment for kind:

  ```yaml
  apiVersion: gateway.envoyproxy.io/v1alpha1
  kind: EnvoyProxy
  metadata:
    name: local
    namespace: envoy-gateway-system
  spec:
    provider:
      type: Kubernetes
      kubernetes:
        envoyService:
          type: ClusterIP
  ```

  Set `spec.infrastructure.parametersRef` on the Gateway to
  `group: gateway.envoyproxy.io`, `kind: EnvoyProxy`, `name: local`.

- **StorageClass**: The infrastructure charts expect a StorageClass named
  `default` when no override is provided. Local clusters typically use a
  different name (e.g., `standard` on kind), so override with the appropriate
  key per chart (see [StorageClass Requirements](#storageclass-requirements)).
- **CNPG instance count**: Install `aiwb-cnpg` with `--set instances=1` on a
  single-node cluster.
- **OpenTelemetry Operator CRDs**: required for `helm install aiwb` even on a
  local cluster. The chart always creates an `OpenTelemetryCollector`; without
  the CRDs the install fails with `no matches for kind "OpenTelemetryCollector"`.
  The collector pods themselves can stay idle if you are not serving models.
  Wait until the operator webhook is Ready before installing AIWB, or Helm
  server-side apply fails calling `mopentelemetrycollectorbeta.kb.io`.
- **Resource constraints**: Reduce resource requests for AIRM/AIWB components if
  your local machine has limited CPU/memory. Consider scaling down non-essential
  services (observability, KEDA) to free up resources.

---

## Validation with E2E Tests

The repository includes Robot Framework end-to-end test suites that validate a live
deployment. These cover AIRM API, AIWB API, and AIWB UI functionality. Running them
against your cluster is the recommended way to confirm the platform is working correctly
after installation.

Each test suite has its own README with prerequisites (kubeconfig OIDC setup, tooling),
commands, tag reference, and troubleshooting:

| Suite        | README                                                            |
| ------------ | ----------------------------------------------------------------- |
| **AIRM API** | [apps/api/airm/specs/README.md](../apps/api/airm/specs/README.md) |
| **AIWB API** | [apps/api/aiwb/specs/README.md](../apps/api/aiwb/specs/README.md) |
| **AIWB UI**  | [apps/ui/aiwb/README.md](../apps/ui/aiwb/README.md)               |

The optional `helm/eai-e2e` chart provisions the E2E test identity and RBAC.
