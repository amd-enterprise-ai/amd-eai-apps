# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Helpers for exporting a service's OpenAPI specification to a file.

The exported spec is rendered into the public documentation site, so it must be
**deterministic** — independent of
the environment it is generated in. ``FastAPI.openapi()`` is already stable for
a given codebase except for the OpenID Connect discovery URL, which is derived
from ``KEYCLOAK_*`` environment variables (see ``api_common.auth.config``).
We replace that single environment-derived value with a documented placeholder
so a developer with a local ``.env`` produces the same file as CI.
"""

import json
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI

# Stand-in for the per-deployment Keycloak discovery URL. The real value is
# environment-specific; readers obtain their host from a platform administrator.
OPENID_CONNECT_URL_PLACEHOLDER = "https://<keycloak-host>/realms/<realm>/.well-known/openid-configuration"

# Some models declare a ``default`` evaluated at class-definition time (e.g. the
# current time), which bakes a fresh timestamp into the schema on every run.
# Pin any datetime-valued ``default`` to a fixed instant so the exported spec is
# reproducible (and so the value reads as an illustrative placeholder in docs).
_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")
_CANONICAL_DATETIME = "2024-01-01T00:00:00Z"


def _pin_dynamic_defaults(node: Any) -> None:
    """Recursively replace datetime-valued ``default`` entries with a fixed value."""
    if isinstance(node, dict):
        default = node.get("default")
        if isinstance(default, str) and _ISO_DATETIME.match(default):
            node["default"] = _CANONICAL_DATETIME
        for value in node.values():
            _pin_dynamic_defaults(value)
    elif isinstance(node, list):
        for item in node:
            _pin_dynamic_defaults(item)


def sanitize_openapi(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip environment- and time-specific values from an OpenAPI schema in place."""
    schemes = schema.get("components", {}).get("securitySchemes", {})
    for scheme in schemes.values():
        if scheme.get("type") == "openIdConnect" and "openIdConnectUrl" in scheme:
            scheme["openIdConnectUrl"] = OPENID_CONNECT_URL_PLACEHOLDER
    _pin_dynamic_defaults(schema)
    return schema


def export_openapi(app: FastAPI, output_path: str | Path) -> Path:
    """Write *app*'s sanitized OpenAPI spec to *output_path* as pretty JSON."""
    spec = sanitize_openapi(app.openapi())
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
