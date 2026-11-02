<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AI Workbench API

## Overview

The AI Workbench (AIWB) API provides AI development and deployment features independently from the AI Resource Manager (AIRM). This standalone deployment is suitable for scenarios where you want AI Workbench capabilities (AIMs, workloads, workspaces, fine-tuning) without integrated cluster resource management.

## Deployment Modes

The AI Workbench can be deployed in three modes:

### Standalone AIWB

Deploy only AI Workbench features without integrated resource management. This service provides:

- AIMs (AMD Inference Microservices) catalog and deployment
- AI Workloads management (Managing, Tracking & Metrics, Chatting, etc.)
- AI Workspaces (JupyterLab, VS Code, etc.)
- Model fine-tuning
- Dataset management
- Secrets management
- API keys for programmatic access

In standalone mode, the API is scoped to a single Kubernetes namespace configured via `DEFAULT_NAMESPACE` (default: `workbench`). This namespace is created and configured during Helm installation along with the required Kyverno policies and secrets. The API rejects requests targeting any other namespace because standalone mode lacks the group-based authorization that AIRM provides, and the platform has no control over permissions or resources outside the namespace it manages.

Authentication is handled via Keycloak, but namespace-level authorization relies on the single-namespace constraint rather than JWT group claims.

### Standalone AIRM

Deploy only AI Resource Manager features. See [`apps/api/airm/README.md`](../airm/README.md) for standalone AIRM deployment.

### Combined AIWB + AIRM

Deploy both services together for full integration of AI development tools with enterprise resource management. See [`apps/api/airm/README.md`](../airm/README.md) for combined deployment configuration.

## Local Development Setup

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) - For running PostgreSQL and other services
- [uv](https://docs.astral.sh/uv/) - Python package manager
- Access to a Kubernetes cluster (for full functionality)

### Quick Start

1. **Initialize the project** (first time setup):

   ```bash
   make init
   ```

   This will:
   - Install all dependencies (API packages and workloads_manager)
   - Initialize the workloads repository
   - Start Docker services

2. **Configure Kubernetes access**:

   Make sure that you have a Kubernetes cluster configured and accessible. The API will attempt to connect to the cluster on startup. If `USE_LOCAL_KUBE_CONTEXT=true` which is set by default, it will use your local kubeconfig context.

3. **Run the API**:

   ```bash
   make dev
   ```

4. **Access the API**:
   - API: http://localhost:8002
   - Swagger docs: http://localhost:8002/docs

### Available Make Targets

```bash
make init         # Initialize project (first time setup)
make dev          # Run the API server (default)
make test         # Run tests
make docker-up    # Start Docker services (PostgreSQL, etc.)
make docker-down  # Stop and remove Docker services
```

### Environment Variables

Create a `.env` file (copy from `.env.example`). Key configurations include:

- **Database**: PostgreSQL connection string
- **AIWB**: Deployment mode and namespace configuration
  - `STANDALONE_MODE`: Set to `true` or `false` (default: `true`)
  - `DEFAULT_NAMESPACE`: Name of the namespace to use in standalone mode (default: `workbench`)
  - When `STANDALONE_MODE=true`: All API access is restricted to `DEFAULT_NAMESPACE`. The API returns 403 for requests targeting any other namespace. The UI hides the project selector.
  - When `STANDALONE_MODE=false`: Users can access namespaces matching their JWT group claims. Namespace lifecycle is managed by AIRM.
- **Keycloak/Auth**: OpenID Connect client credentials (required for user authentication)
- **MinIO**: Object storage endpoint and credentials (for dataset and model storage)
- **Kubernetes**: Cluster access configuration for workload deployment

See `.env.example` for complete configuration options.

### Deleted Project Cleanup

AIWB can reclaim API keys, dataset records, and storage objects left behind when a project is
deleted. Cleanup is disabled by default because reclamation is irreversible.

Configure scheduled cleanup with:

- `DELETED_PROJECT_CLEANUP_ENABLED`: Set to `true` to enable the hourly poller.
- `DELETED_PROJECT_CLEANUP_INTERVAL_SECONDS`: Interval between cleanup runs (default: `3600`).
- `DELETED_PROJECT_CLEANUP_SKEW_MARGIN_SECONDS`: Timestamp safety margin for reused project names
  (default: `3600`).

To run cleanup immediately instead of waiting for the poller:

```bash
uv run reclaim-orphans --dry-run   # preview; deletes nothing
uv run reclaim-orphans             # reclaim
```

The command requires database, Kubernetes and MinIO access, plus OpenBao to reclaim. It refuses
to reclaim without OpenBao credentials, or when no Kubernetes namespaces are visible. `--dry-run`
reaches the same verdicts through the same traversal and reports them without deleting anything,
so what it names is what a real run would remove.

### API Endpoints

The AIWB API definition can be found under the Swagger UI at http://localhost:8002/docs for interactive API documentation.

### Development Workflow

1. **Database Setup**: The PostgreSQL database is managed via Docker Compose. Migrations are applied automatically on startup.

2. **Running Tests**:

   ```bash
   make test
   ```

3. **Dependency Management**: Uses `uv` for fast Python dependency management. Run `make init` to install dependencies, or `uv sync` directly when dependencies change.
