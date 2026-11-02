<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AMD Enterprise AI Reference Stack

> [!CAUTION]
> If you are looking to just install the AMD enterprise AI reference stack, the instructions for most users are here https://enterprise-ai.docs.amd.com/en/latest/platform-infrastructure/on-premises-installation.html The instructions in this GitHub are targeted for more advanced usage/development.

This repository contains the main services and common Python packages that power the AMD enterprise AI reference stack. The reference stack is composed of **AI Workbench** (an interface for developers to manage the lifecycle of their AI workloads, including features like AI workspaces, AIMs catalog and fine-tuning) and **Resource Manager** (the infrastructure layer for authentication, access control, and cluster coordination). The components are organized under the `apps/` directory.

## Architecture and Deployment Modes

The platform supports three deployment modes to accommodate different use cases:

- **Standalone AI Workbench**: Deploy only AI Workbench features (AIMs, workloads, workspaces, fine-tuning) without resource management capabilities. Located in `apps/api/aiwb/`.
- **Standalone Resource Manager**: Deploy only Resource Manager features (cluster management, authentication, quota management) without AI development tools. Located in `apps/api/airm/`.
- **Combined AI Workbench + Resource Manager**: Deploy both services together for a full-featured platform with AI development tools and resource management.

The main components include:

- **AIWB API**: AI Workbench API for managing AIMs, workloads, workspaces, and fine-tuning jobs. Can run standalone or integrated with Resource Manager.
- **AIRM API**: Resource Manager API handling authentication, access control, cluster coordination, and quota management. Can run standalone or integrated with AI Workbench.
- **AIWB UI**: Frontend interface for AI Workbench features (AIMs catalog, workspaces, fine-tuning, chat). Located in `apps/ui/aiwb/`.
- **AIRM UI**: Frontend interface for Resource Manager features (cluster management, quota allocation, project management). Located in `apps/ui/airm/`.
- **Agent**: A Kubernetes cluster agent that handles resource management, messaging, and heartbeats for the Resource Manager system.

---

## Components Overview

### AIWB API

The AI Workbench API provides features for AI development and deployment, including AIMs (AMD Inference Microservices) deployment, model fine-tuning, dataset management, AI workspaces, and API keys for programmatic access. This service can run standalone or be integrated with Resource Manager for combined deployment.

- **Docs**: [`apps/api/aiwb/README.md`](apps/api/aiwb/README.md)
- **Tech**: FastAPI, PostgreSQL, Kubernetes API, MinIO
- **Testing**: `uv run pytest`

### AIRM API

The Resource Manager API handles authentication, access control, cluster coordination, and quota management across organizations, projects, and environments. This service can run standalone or be integrated with AI Workbench for combined deployment.

- **Docs**: [`apps/api/airm/README.md`](apps/api/airm/README.md)
- **Tech**: FastAPI, PostgreSQL, Keycloak, RabbitMQ, Vault
- **Testing**: `uv run pytest`

### AIWB UI

The AI Workbench UI provides the frontend interface for AI development features including interactive chat, AI workspaces management, AIMs catalog browsing and deployment, and fine-tuning job configuration.

- **Docs**: [`apps/ui/aiwb/README.md`](apps/ui/aiwb/README.md)
- **Tech**: Next.js, Hero UI, Keycloak SSO
- **Testing**: `pnpm test`

### AIRM UI

The Resource Manager UI provides the frontend interface for resource management features including cluster onboarding, quota allocation, project management, and job monitoring.

- **Docs**: [`apps/ui/airm/README.md`](apps/ui/airm/README.md)
- **Tech**: Next.js, Hero UI, Keycloak SSO
- **Testing**: `pnpm test`

### Agent

A Kubernetes cluster agent that handles resource management, messaging, and heartbeats for the Resource Manager system. Written in Go for efficient resource monitoring and cluster communication.

- **Docs**: [`apps/agent/README.md`](apps/agent/README.md)
- **Tech**: Go, Kubernetes, RabbitMQ
- **Testing**: `make test`

---

## Helm Installation

For step-by-step instructions on deploying the full platform to a Kubernetes cluster
using Helm (including all dependencies, secrets, and E2E validation), see the
[Helm Installation Guide](helm/INSTALL.md).

---

## Setup Instructions

### Prerequisites

- Python 3.13
- Go 1.25 for agent development
- prek (`brew install prek` or `uv tool install prek`)
- Docker & Docker Compose
- Node.js & `pnpm` for frontend
- `uv` for Python dependency management

> Windows users should use [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) for full compatibility.

### Repository Setup

```bash
git clone <this-repo>
cd <repo>

# Install prek hooks (both pre-commit and pre-push)
prek install --prepare-hooks --hook-type pre-commit --hook-type pre-push
```

> **Note**: The pre-push hooks run tests for any changed components and exit at the first failure:
>
> - **AIRM UI**: Vitest with coverage in `apps/ui/airm`
> - **AIWB UI**: Vitest with coverage in `apps/ui/aiwb`
> - **AIRM API**: pytest in `apps/api/airm`
> - **AIWB API**: pytest in `apps/api/aiwb`
> - **Agent**: Go tests in `apps/agent`
> - **Robot dry-run**: Validates Robot Framework syntax in `apps/api/aiwb`, `apps/api/airm`, and `apps/ui/aiwb`
>
> These hooks catch issues before pushing to remote and ensure code quality standards are met.
> If the pre-push stage is too slow for your workflow, you can disable it and rely on CI instead:
>
> ```bash
> prek uninstall -t pre-push
> ```
