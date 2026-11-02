<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# AI Workbench (AIWB) End-to-End Tests

End-to-end tests for AI Workbench features including AIMs (AI Models), datasets, models, workspaces, charts, and fine-tuning workflows.

## Quick Start

### Prerequisites

See the main AIRM E2E test README for complete prerequisites: `../../airm/specs/README.md`

Key requirements:

1. Install `uv` and `kubectl`
2. Configure Kubernetes authentication in kubeconfig
3. Set active Kubernetes context

### Running Tests

Tests are run using Robot Framework via `uv run robot`. The specs directory includes an `arguments.txt` file with recommended settings.

**Note:** The `arguments.txt` file includes pythonpath to AIRM specs for shared resources (authorization, deployment, common libraries).

#### Setup

```bash
# Install AIWB dev dependencies (includes Robot Framework and all required libraries)
cd apps/api/aiwb
uv sync --dev

# Navigate to the specs directory
cd specs
```

#### Running Tests

```bash
# Run all tests using arguments.txt (recommended)
uv run --project .. robot --argumentfile arguments.txt .

# Run everything except the AIM catalog — the usual choice, see "AIM Catalog Tests" below
uv run --project .. robot --argumentfile arguments.txt --exclude aim-catalog .

# Run smoke tests (quick validation)
uv run --project .. robot --argumentfile arguments.txt --include smoke .

# Exclude GPU-intensive tests
uv run --project .. robot --argumentfile arguments.txt --exclude gpu .

# Run a single test suite
uv run --project .. robot --argumentfile arguments.txt aims.robot

# Run a specific test by name
uv run --project .. robot --argumentfile arguments.txt --test "Deploy AIM successfully" .

# Override output directory if needed
uv run --project .. robot --argumentfile arguments.txt --outputdir /custom/path .

# Rerun only failed tests
uv run --project .. robot --argumentfile arguments.txt --rerunfailed results/output.xml .
```

**Common tag filtering patterns:**

```bash
# Quick smoke test (no GPU required)
uv run --project .. robot --argumentfile arguments.txt --include smoke --exclude gpu .

# Run all tests except GPU-intensive ones
uv run --project .. robot --argumentfile arguments.txt --exclude gpu .

# Run against a cluster that publishes no AIM image catalog (Custom Models and adapter
# serving cannot pick a model there). A device and a catalog are separate things, so this
# exclusion is separate from --exclude gpu and each is dropped on its own.
uv run --project .. robot --argumentfile arguments.txt --exclude gpu --exclude needs-aim-images .

# Run only AIM-related tests
uv run --project .. robot --argumentfile arguments.txt --include aims .

# Run only dataset tests
uv run --project .. robot --argumentfile arguments.txt --include datasets .
```

## Test Suites

AI Workbench test suites cover AIMs, API keys, charts, datasets, finetuning, models, workspaces, and AIM catalog testing. List suites with `ls *.robot`.

## Test Architecture

### Directory Structure

```
specs/
├── *.robot                              # Test suite files
├── config/                              # AIM model catalog configuration
├── libraries/                           # Python libraries (AIM catalog generator)
├── resources/
│   ├── aiwb_*.resource                  # Business logic keywords (high-level)
│   ├── api/                             # Low-level HTTP operation keywords
│   └── aims/                            # AIMS-specific resources (API keys)
└── test_data/                           # Sample datasets and chart templates
```

### Shared Resources from AIRM

AIWB tests use shared infrastructure resources from AIRM via pythonpath (authorization, deployment, project management, safe HTTP wrappers, etc.). See `arguments.txt` for the pythonpath configuration.

### Import Pattern

AIWB test files use `resources/` prefix for imports. The pythonpath configuration resolves these:

- Local AIWB resources from `apps/api/aiwb/specs/resources/`
- Shared AIRM resources from `apps/api/airm/specs/resources/`

Example:

```robot
*** Settings ***
# Local AIWB resources
Resource    resources/aiwb_aims.resource
Resource    resources/api/aims.resource

# Shared AIRM resources (via pythonpath)
Resource    resources/authorization.resource
Resource    resources/deployment.resource
Resource    resources/airm_projects.resource
Library     libraries.KubeConnection
```

## AIM Catalog Tests

The `aim_catalog.robot` suite auto-discovers AIM models from the cluster and tests each one (deploy → verify → inference → metrics → undeploy).

It is by far the most expensive suite in AIWB: one GPU deployment per discovered model, with a 100-minute per-test timeout (`Test Timeout`) of which up to 90 minutes can go to waiting for the model to reach Running (`${AIM_DEPLOY_TIMEOUT}`). On a cluster with a populated catalog, a full AIWB run spends nearly all its time here. Most of the time you want the rest of the AIWB suite without it.

### Skipping the catalog

The suite is tagged `aim-catalog`, and that is an ordinary Robot Framework tag — no special mechanism, no bespoke flag. It selects the suite the same way any other tag selects tests:

```bash
# Whole AIWB suite, no catalog
uv run --project .. robot --argumentfile arguments.txt --exclude aim-catalog .

# Only the catalog
uv run --project .. robot --argumentfile arguments.txt --include aim-catalog .
```

With `--exclude` the suite is dropped before it starts: no models are discovered, nothing is deployed, and the cluster catalog API is never contacted. The rest of the AIWB suites run normally. The tag lives on every static test the suite file declares, and RF applies CLI tag filters before the generator runs — so excluding the tag empties the suite at build time and takes the whole thing with it. Any static test added to `aim_catalog.robot` must carry `aim-catalog` for this to keep working; `test_every_static_test_carries_the_aim_catalog_tag` enforces it.

The generator also honours a variable, which does the same thing from inside the run:

```bash
uv run --project .. robot --argumentfile arguments.txt --variable EXCLUDE_TAGS:aim-catalog .
```

With the variable the suite still appears in the report, as **skipped with 0 tests**; with `--exclude` it is absent entirely. Either way nothing is deployed.

Two things to know:

- **Tag filtering can only take the catalog as a whole.** The per-model tests are generated at runtime by `libraries/AimCatalogGenerator.py`, after Robot Framework has already applied `--include` / `--exclude` / `--test`. To select among models, use the variables below.
- **Excluding the catalog while running only the catalog is an error.** `robot ... --exclude aim-catalog aim_catalog.robot` leaves the run with zero tests, which Robot Framework reports with exit code 252. The combination is contradictory; the exclusion is meant for runs that include other suites.

### Running the catalog

```bash
# Run full catalog (all models from cluster)
uv run --project .. robot --argumentfile arguments.txt aim_catalog.robot

# Run a specific release list from a config file (see config/ for examples)
uv run --project .. robot --argumentfile arguments.txt \
  --variable AIM_CATALOG_FILTER:config/silogen-0.11.0.txt \
  aim_catalog.robot

# Test a specific docker image ref inline (no config file needed)
uv run --project .. robot --argumentfile arguments.txt \
  --variable "AIM_CATALOG_FILTER:ghcr.io/silogen/aim-openai-gpt-oss-20b:0.11.0" \
  aim_catalog.robot

# Test multiple models inline (comma-separated)
uv run --project .. robot --argumentfile arguments.txt \
  --variable "AIM_CATALOG_FILTER:ghcr.io/silogen/aim-openai-gpt-oss-20b:0.11.0,ghcr.io/silogen/aim-qwen-qwen3-32b:0.11.0" \
  aim_catalog.robot

# Test a specific model (use INCLUDE_TAGS — --test doesn't work with dynamically generated tests)
uv run --project .. robot --argumentfile arguments.txt \
  --variable INCLUDE_TAGS:model:Qwen3-32B \
  aim_catalog.robot

# Skip models requiring HuggingFace token
uv run --project .. robot --argumentfile arguments.txt \
  --variable EXCLUDE_TAGS:requires-hf-token \
  aim_catalog.robot

# Test only version 0.8.5
uv run --project .. robot --argumentfile arguments.txt \
  --variable AIM_VERSION:0.8.5 \
  aim_catalog.robot

# Test versions >= 0.9.0
uv run --project .. robot --argumentfile arguments.txt \
  --variable AIM_VERSION:>=0.9.0 \
  aim_catalog.robot
```

| Variable             | Required         | Description                                                                                                                                                                                                                                                            |
| -------------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `EXCLUDE_TAGS`       | Optional         | Exclude matching generated tests, e.g. `requires-hf-token`. The special value `aim-catalog` skips the whole suite (see above) and short-circuits before any per-model filtering, so the two uses cannot be combined in one run.                                        |
| `INCLUDE_TAGS`       | Optional         | Restrict generated tests: `model:Qwen3-32B`, `gpus:1`, `version:0.8.5`. Use this instead of `--test`, which cannot select generated tests.                                                                                                                             |
| `HF_TOKEN`           | For gated models | HuggingFace token for meta-llama and similar gated models                                                                                                                                                                                                              |
| `AIM_CATALOG_FILTER` | Optional         | File path or inline comma-separated model spec. Accepts `model_image:aim_version` (e.g., `ghcr.io/silogen/aim-openai-gpt-oss-20b:0.11.0`) or HuggingFace model ID (e.g., `openai/gpt-oss-20b`). Can be a `.txt` config file (see `config/`) or passed inline via flag. |
| `AIM_VERSION`        | Optional         | Version filter: `0.8.5` (exact), `>=0.9.0` (range), `latest` (default)                                                                                                                                                                                                 |
| `AIWB_API_URL`       | Optional         | Override API URL (auto-resolved from cluster)                                                                                                                                                                                                                          |
| `AIWB_API_TOKEN`     | Optional         | Override OIDC token (auto-acquired from kubectl)                                                                                                                                                                                                                       |

## Configuration

The `arguments.txt` file contains common Robot Framework settings. You can override any argument:

```bash
# Override log level for debugging
uv run --project .. robot --argumentfile arguments.txt --loglevel TRACE .

# Change output directory
uv run --project .. robot --argumentfile arguments.txt --outputdir /tmp/results .
```

Per-test timeout overrides use `Test Timeout` in a suite's `*** Settings ***` table or `[Timeout]` in a test case.

See `arguments.txt` for available options and AIM catalog filtering.

## Analyzing Test Results

See the main AIRM E2E test README for complete documentation on test result analysis: `../../airm/specs/README.md`

Quick reference:

- HTML reports in `results/`: `log.html`, `report.html`

## Related Documentation

- **[AIRM E2E README](../../airm/specs/README.md)** - Complete E2E testing documentation
- **[Robot Framework User Guide](https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html)** - Official documentation
