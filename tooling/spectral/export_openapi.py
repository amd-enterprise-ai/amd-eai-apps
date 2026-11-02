# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Export OpenAPI schema from FastAPI application.

This script extracts the OpenAPI specification from a FastAPI application without
starting the server. It avoids initializing database connections and external services
by accessing the schema directly.

Usage:
    cd apps/api/airm
    uv run python ../../../tooling/spectral/export_openapi.py [output_file]
"""

import json
import sys
from pathlib import Path

# Add current directory to path for importing app
api_dir = Path.cwd()
sys.path.insert(0, str(api_dir))

try:
    from app import app  # type: ignore[attr-defined]
except ImportError as e:
    print(
        f"Error: Could not import FastAPI app from current directory.\n"
        f"Make sure you're running from the API directory (e.g., apps/api/airm).\n"
        f"Details: {e}",
        file=sys.stderr,
    )
    sys.exit(1)


def export_openapi(output_file: str | None = None) -> None:
    """Export OpenAPI schema to file or stdout with validation and error handling."""
    try:
        if not hasattr(app, "openapi"):
            print(
                "Error: Imported 'app' object does not have an 'openapi()' method.\n"
                "Ensure 'app' is a FastAPI application instance.",
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            openapi_schema = app.openapi()
        except Exception as e:
            print(
                f"Error: Failed to generate OpenAPI schema.\nDetails: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        schema_json = json.dumps(openapi_schema, indent=2)

        if output_file:
            try:
                output_path = Path(output_file).resolve()

                # Security: Ensure output path is within current directory tree
                cwd = Path.cwd().resolve()
                if not str(output_path).startswith(str(cwd)):
                    print(
                        f"Error: Output path must be within current directory.\n"
                        f"Requested: {output_path}\n"
                        f"Current directory: {cwd}",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(schema_json)
                print(f"OpenAPI schema exported to {output_file}", file=sys.stderr)
            except OSError as e:
                print(
                    f"Error: Failed to write OpenAPI schema to {output_file}.\nDetails: {e}",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            print(schema_json)

    except Exception as e:
        print(
            f"Unexpected error during OpenAPI export.\nDetails: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else None
    export_openapi(output)
