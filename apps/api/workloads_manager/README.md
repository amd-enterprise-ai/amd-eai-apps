<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Workloads Manager

## TL;DR

Set your token into `TOKEN` environment variable and just run register - it will do everything:

```bash
cd apps/api/workloads_manager
uv run wm register
```

This will initialize the repository, apply patches, and register the workload to AIRM API at localhost:8001.
To register to a different API endpoint, use the `--url` option:

```bash
uv run wm register --url http://your-api-server:8003
```

## Overview

A package for managing and registering AI workloads using `uv`.

### Setup

1. Make sure you have a `TOKEN` environment variable set for API access:

   ```bash
   export TOKEN=your_token_here
   ```

2. Or copy the template and edit it:
   ```bash
   cp apps/api/workloads_manager/.env.example apps/api/workloads_manager/.env
   # Edit the .env file with your credentials
   ```

## Available Commands

All commands should be run from the `apps/api/workloads_manager` directory:

```bash
# Register a workload template (will initialize repository if needed)
uv run wm register

# Register a specific workload template
uv run wm register llm-finetune-silogen-engine

# Register with auto-yes to all prompts
uv run wm register llm-finetune-silogen-engine --yes

# Register to a specific API endpoint
uv run wm register --url http://your-api-server:8001

# Initialize or reset the repository
uv run wm init

# Force reset (discard local changes)
uv run wm init --force

# Reset repository without applying patches
uv run wm init --force --skip-patches

# Update the repository
uv run wm update

# Create patches from your changes
uv run wm create-patches

# Check status of workloads and patches
uv run wm status
```

### Patch failures

`wm init` exits non-zero if any patch fails to apply. A failed three-way merge writes
conflict markers into the chart files, so the checkout it leaves behind is not safe to
package or register — fix the patches and re-run rather than continuing. `wm update` is
the exception: conflicts are the expected result of moving to a newer upstream version,
so it reports them and leaves the tree for you to resolve by hand.

To check a patched checkout independently — for conflict markers and unparseable chart
YAML — run `tooling/validate_patched_workloads.py`, which is what CI does before the
image is built:

```bash
uv run python ../../../tooling/validate_patched_workloads.py
```

## Creating Custom Patches

To create your own patches for workloads:

1. Reset the repository without applying patches:

   ```bash
   uv run wm init --force --skip-patches
   ```

2. Make your changes to the workload files manually

3. Create patches from your changes:

   ```bash
   uv run wm create-patches
   ```

4. Add the new patch files to git and commit them:

   ```bash
   git add workloads_manager/data/patches/*.patch
   git commit -m "Add new patches for workloads"
   ```

5. Update PATCHED_VERSION file to the current ai-workloads commit hash

## Troubleshooting

### Common Issues

1. **API Connection Errors**:
   - Check your TOKEN environment variable
   - Verify the API server is running and accessible

2. **UV Run Errors**:
   - If you get warnings about virtual environment paths, use `--active` flag:
     ```bash
     uv run --active wm register
     ```
     or activate the virtual environment manually:
     ```bash
     source .venv/bin/activate
     uv run wm register
     ```

### Debug Mode

To see more detailed logs:

```bash
uv run wm --debug register
```

## Environment Variables

- `TOKEN`: API token for authentication (required)
- `WM_API_URL`: API server URL (default: http://127.0.0.1:8001/v1)

See `.env.example` for all available options.
