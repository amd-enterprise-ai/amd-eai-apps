<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AIRM Cluster Agent

A Kubernetes cluster agent responsible for dispatching commands between the AIRM API and Kubernetes clusters, as well as enforcing cluster policies.

## Overview

This repository contains two applications:

- **Agent** (`cmd/agent`): Manages Kubernetes resources, processes commands from AIRM API via RabbitMQ, and reports cluster state
- **Webhook** (`cmd/webhooks`): Admission webhook that enforces quota and policy constraints on workload deployments

The agent can run locally for development or in a Kubernetes cluster for production. The webhook must run in a Kubernetes cluster.

## Prerequisites

- Go 1.25 or later
- Docker (for building images)
- kubectl (for Kubernetes deployments)
- Access to AIRM API and RabbitMQ instance

## Building

All build commands should be run from the agent directory:

```bash
cd apps/agent
```

Build both binaries:

```bash
make build
```

Build individually:

```bash
make build-agent    # Agent only
make build-webhook  # Webhook only
```

## Development

### Option 1: Local Kubernetes Cluster (kind)

Deploy both agent and webhook in a local Kubernetes cluster using kind. This is the recommended approach for full-stack development and testing the complete AIRM integration.

#### Prerequisites

Install the following tools:

- [kind](https://kind.sigs.k8s.io/docs/user/quick-start/) - Kubernetes in Docker
- [kubectl](https://kubernetes.io/docs/tasks/tools/) - Kubernetes CLI
- [Docker](https://docs.docker.com/get-docker/) - Container runtime
- [Helm v3](https://helm.sh/docs/intro/install/) - Package manager for Kubernetes

#### Repository Setup

Clone required repositories side-by-side with the `core` repository:

```
└── projects/
    ├── amd-eai-apps/   # This repository
    ├── kaiwo/          # Queue configuration CRD
    └── aim-engine/     # AIMService CRD
```

Clone the repositories:

```bash
cd projects/
git clone https://github.com/amd-enterprise-ai/amd-eai-apps.git
git clone https://github.com/silogen/kaiwo.git
git clone https://github.com/amd-enterprise-ai/aim-engine.git
```

#### Create and Configure Cluster

Create a kind cluster from the root of the `amd-eai-apps/` repository:

```bash
cd amd-eai-apps/
kind create cluster --config ./apps/agent/local/kind-config.yaml
```

This creates a local Kubernetes cluster with the necessary port mappings and configurations for AIRM development.

Verify cluster access:

```bash
kubectl cluster-info --context kind-kind
kubectl config use-context kind-kind
```

#### Install Kubernetes Dependencies

Install required CRDs and operators in the cluster:

- **Kaiwo** - Queue Configuration CRD for workload queuing. [Installation Guide](https://silogen.github.io/kaiwo/admin/installation/)
- **AIM Engine** - AIMService CRD for AI model inference services. [Installation Guide](https://github.com/amd-enterprise-ai/aim-engine)
- **External Secrets Operator** - For managing secrets from external sources like Vault. [Installation Guide](https://external-secrets.io/main/introduction/getting-started/#installing-with-helm)

#### Onboard Cluster with AIRM

Onboard your kind cluster to obtain RabbitMQ credentials:

- Make sure the AMD Resource Manager API and corresponding docker compose are running. See the [AIRM API README](../api/README.md) for setup instructions.
- Onboard the kind cluster via AMD Resource Manager and copy the values of the **Auth ID** and **Connection Token** that are provided as part of the cluster onboarding.
- Set up environment variables by first copying the `.env.example` file and replace the `RABBITMQ_USER` and `RABBITMQ_PASSWORD` in the `.env` file with the values for Auth ID and Connection Token respectively.

#### Build/cache dependencies

Due to corporate proxies and other MITM, proxy.golang.org is inaccessible from within the cluster, and going directly to repositories leads to different checksums.
As a workaround, when deploying locally in a cluster, we use `go mod vendor` prior to deployment to cache a local copy of dependencies under `apps/agent/vendor/` (on your `/code` mount).

Run the following from root of the `core/` repository:

```bash
make -C apps/agent vendor
```

#### Deploy Agent and Webhook

Deploy both applications to the cluster from the root of the `core/` repository:

```bash
kubectl kustomize apps/agent/local --enable-helm | kubectl apply -f -
```

This deploys the agent and webhook in the `airm` namespace with service accounts, RBAC permissions, webhook certificates, and all necessary services. If deployment succeeds, the applications are volume-mounted from your local filesystem with hot-reloading enabled via Air. Any code changes (including `.env` file changes) will automatically trigger a rebuild and restart.

### Option 2: Local Agent Development

Run the agent locally on your machine while connected to a remote Kubernetes cluster. This approach is faster for rapid iteration and debugging agent-specific functionality. Note that the webhook cannot be run locally as it must be accessible from the Kubernetes API server.

#### Prerequisites

- Access to a Kubernetes cluster (can be remote or local kind cluster)
- AIRM API running with RabbitMQ. See [AIRM API README](../api/README.md) for setup instructions
- Valid kubeconfig on your local machine pointing to your cluster
- Cluster onboarded via AIRM UI to obtain RabbitMQ credentials

#### Configuration

Ensure your kubeconfig is configured:

```bash
export KUBECONFIG=~/.kube/config
kubectl cluster-info  # Verify connection
```

Create `.env` file in the agent directory:

```bash
cd apps/agent
cp .env.example .env
```

Edit `.env` with credentials from AIRM cluster onboarding:

```bash
RABBITMQ_USER=<Auth ID>
RABBITMQ_PASSWORD=<Connection Token>
KUBE_CLUSTER_NAME=<your-cluster-name>
HTTP_PORT=8000
HEALTH_PORT=8081
```

#### Run with Live Reloading

For development with automatic reload on code changes:

```bash
cd apps/agent
make dev
```

This uses Air to watch for file changes and automatically rebuild and restart the agent.

#### Run Directly

To run without live reloading:

```bash
cd apps/agent
make run
# or
go run ./cmd/agent
```

The agent will connect to your Kubernetes cluster and start processing commands from the AIRM API.

## Testing

All test commands should be run from the agent directory:

```bash
cd apps/agent
```

### Run Tests

```bash
make test              # Run all tests
make test-verbose      # Run with verbose output
make test-coverage     # Generate coverage report
make test-coverage-html # Generate HTML coverage report
```

The HTML coverage report will be generated at `coverage.html` and can be opened in your browser.

## Additional Commands

All commands should be run from the agent directory (`apps/agent`):

```bash
make clean    # Remove build artifacts (bin/, tmp/) and coverage files
make tidy     # Run go mod tidy to clean up module dependencies
make format   # Format code with gofmt
make lint     # Lint code with golangci-lint
make lint-fix # Lint and auto-fix issues where possible
```

## Uninstall

First, remove the deployed resources to stop the agent from re-adding finalizers:

```bash
kubectl kustomize apps/agent/local --enable-helm | kubectl delete -f -
```

The agent adds finalizers to Kubernetes resources it manages (namespaces, workloads, secrets, storage configmaps, and quota configs). If these finalizers are not removed after the agent is deleted, affected resources can get stuck in `Terminating` state. Strip them with the cleanup tool:

```bash
go run ./cmd/cleanup --dry-run
go run ./cmd/cleanup
```

## License

Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
