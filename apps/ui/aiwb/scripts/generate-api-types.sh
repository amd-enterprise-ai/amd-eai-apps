#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Generate TypeScript types from the AIWB API OpenAPI schema.
#
# Exports the FastAPI OpenAPI spec (offline, no DB/server) and runs
# openapi-typescript to emit types/api.generated.ts. The generated file is
# gitignored and regenerated inside `pnpm typecheck`, so it is always fresh
# whenever the UI is type-checked (backend-only PRs don't retrigger UI CI, so a
# schema change is caught on the next UI-touching PR, not the backend one).
#
# Robust to any cwd: all paths resolve relative to this script's location.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# scripts -> aiwb -> ui -> apps -> repo root
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

API_DIR="$REPO_ROOT/apps/api/aiwb"
UI_DIR="$REPO_ROOT/apps/ui/aiwb"
OPENAPI_JSON="$API_DIR/openapi.json"
OUTPUT="$UI_DIR/types/api.generated.ts"
EXPORT_SCRIPT="$REPO_ROOT/tooling/spectral/export_openapi.py"

# The generator imports the FastAPI app via uv and resolves openapi-typescript
# through pnpm; a missing tool otherwise fails with a cryptic "command not found".
command -v uv >/dev/null || {
  echo "error: 'uv' not found. Run: cd apps/api/aiwb && uv sync" >&2
  exit 1
}
command -v pnpm >/dev/null || {
  echo "error: 'pnpm' not found. Install pnpm and run 'pnpm i' in apps/ui." >&2
  exit 1
}

echo "Exporting OpenAPI schema from apps/api/aiwb..." >&2
(cd "$API_DIR" && uv run python "$EXPORT_SCRIPT" openapi.json)

echo "Generating TypeScript types..." >&2
# Resolve the openapi-typescript binary from the UI workspace, not the caller's
# cwd, so the script works regardless of where it is invoked from.
(cd "$UI_DIR" && pnpm exec openapi-typescript "$OPENAPI_JSON" -o "$OUTPUT")

# Prepend the repo-standard copyright/SPDX header plus a do-not-edit notice.
# Stream through a temp file so the generated output is never loaded into memory
# and its newlines are preserved exactly.
TMP_OUTPUT="$(mktemp)"
trap 'rm -f "$TMP_OUTPUT"' EXIT
cat > "$TMP_OUTPUT" <<'EOF'
// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
//
// This file is auto-generated from the AIWB API OpenAPI schema. Do not edit manually.
// Run 'pnpm generate:api-types' to regenerate (also runs inside 'pnpm typecheck').

EOF
cat "$OUTPUT" >> "$TMP_OUTPUT"
mv "$TMP_OUTPUT" "$OUTPUT"

# Clean up the intermediate schema (gitignored, but tidy up like run_spectral.sh).
rm -f "$OPENAPI_JSON"

echo "Generated $OUTPUT" >&2
