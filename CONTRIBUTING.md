<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Contributing to AMD Resource Manager and AMD AI Workbench

Thank you for your interest in contributing. This document explains how to get started, how work is tracked, and what to expect from the review process.

## Code of Conduct

By participating in this project you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Issue Tracking

- **Bug reports and feature requests** — open a [GitHub Issue](../../issues).

## Branch and Commit Naming

Use a short descriptive branch name and a clear commit message that explains _why_ the change is needed.

## Development Setup

See [README.md](README.md) for full prerequisites and setup instructions. The short version:

```bash
git clone <this-repo>
cd <repo>
prek install --prepare-hooks --hook-type pre-commit --hook-type pre-push
```

`prek` runs linters on commit and tests on push. If the pre-push stage is too slow for your workflow you can disable it:

```bash
prek uninstall -t pre-push
```

### Component toolchains

| Component                    | Language             | Test command    |
| ---------------------------- | -------------------- | --------------- |
| `apps/api/aiwb`              | Python               | `uv run pytest` |
| `apps/api/airm`              | Python               | `uv run pytest` |
| `apps/api/api_common`        | Python               | `uv run pytest` |
| `apps/api/workloads_manager` | Python               | `uv run pytest` |
| `apps/ui/aiwb`               | TypeScript / Next.js | `pnpm test`     |
| `apps/ui/airm`               | TypeScript / Next.js | `pnpm test`     |
| `apps/agent`                 | Go                   | `make test`     |
| `apps/ai-gateway-discovery`  | Go                   | `make test`     |

## Making Changes

1. **Fork** the repository and create a branch from `main`.
2. **Make your changes.** Keep commits focused — one logical change per commit.
3. **Add or update tests.** Every new feature or behavior change must include corresponding E2E tests using Robot Framework with BDD-style Given/When/Then syntax. Unit tests are welcome too.
4. **Run the relevant test suite** before opening a PR.
5. **Open a pull request** against `main` with a clear title and description.

### Pull Request Title

Use a short summary of what changed and why.

### What reviewers look for

- Tests cover the new behavior (E2E + unit where applicable)
- No implementation details leaked into BDD/E2E scenario steps
- No secrets, credentials, or internal hostnames in committed files
- Third-party dependencies declared in the appropriate lock file; `THIRD-PARTY-NOTICES.md` and `sbom.json` updated if new dependencies are added (run `python3 scripts/generate-notices.py` and `python3 scripts/generate-sbom.py`)

## Reporting Security Issues

Do **not** open a public GitHub Issue for security vulnerabilities. See [SECURITY.md](SECURITY.md) for the responsible disclosure process.

## License

By contributing you agree that your contributions will be licensed under the [MIT License](LICENSE.TXT).
