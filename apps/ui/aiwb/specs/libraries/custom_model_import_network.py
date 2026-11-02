# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Helpers for custom-model import UI specs (JSON request bodies from Browser)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from robot.api.deco import keyword

_KUBECTL_TIMEOUT = 60


@keyword
def normalize_json_post_payload(post_data: Any) -> dict[str, Any]:
    """Return ``postData`` as a dict whether Browser passed JSON text or a mapping."""
    if isinstance(post_data, Mapping):
        return dict(post_data)
    if isinstance(post_data, str):
        return json.loads(post_data)
    msg = f"Unsupported postData type: {type(post_data).__name__}"
    raise ValueError(msg)


@keyword("Resolve S3 storage Kubernetes name")
def resolve_s3_storage_kubernetes_name(namespace: str, display_name: str) -> str:
    """Return the storage ConfigMap name for a project-visible display name."""
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "configmap",
                "-n",
                namespace,
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("kubectl not found on PATH — cannot resolve S3 storage ConfigMap name") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"kubectl get configmap timed out after {_KUBECTL_TIMEOUT}s while resolving storage '{display_name}'"
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            "kubectl get configmap failed while resolving storage "
            f"'{display_name}' in namespace '{namespace}': {result.stderr}"
        )

    payload = json.loads(result.stdout or "{}")
    items = payload.get("items", [])
    matches: list[str] = []
    for item in items:
        metadata = item.get("metadata") or {}
        data = item.get("data") or {}
        labels = metadata.get("labels") or {}
        annotations = metadata.get("annotations") or {}
        storage_type = data.get("TYPE") or data.get("type") or labels.get("airm.silogen.ai/storage-type")
        if storage_type != "S3":
            continue
        if annotations.get("aiwb.apps.eai.amd.com/storage-display-name") != display_name:
            continue
        name = metadata.get("name")
        if isinstance(name, str) and name:
            matches.append(name)

    if not matches:
        raise RuntimeError(
            f"No S3 storage ConfigMap found for display name '{display_name}' in namespace '{namespace}'."
        )
    if len(matches) > 1:
        raise RuntimeError(
            "Expected exactly one S3 storage ConfigMap for display name "
            f"'{display_name}' in namespace '{namespace}', found {len(matches)}."
        )
    return matches[0]


def _sanitize_label_value(value: str, max_length: int = 63) -> str:
    """Mirror the backend's ``sanitize_label_value`` so the seeded CR's model-name
    label matches what real onboarding stamps (``sanitize_label_value(display_name)``).

    Kept in sync with ``apps/api/aiwb/app/dispatch/utils.py``: keep alphanumerics
    and ``-_.``, map spaces and ``/`` to ``-``, drop other characters, trim to
    leading/trailing alphanumerics, and cap at 63 chars.
    """
    if not value:
        return ""
    chars = [c if (c.isalnum() or c in ("-", "_", ".")) else "-" if c in (" ", "/") else "" for c in value]
    sanitized = "".join(chars).strip("-_.")
    while sanitized and not sanitized[0].isalnum():
        sanitized = sanitized[1:]
    while sanitized and not sanitized[-1].isalnum():
        sanitized = sanitized[:-1]
    return sanitized[:max_length] or "unknown"


@keyword("Seed Custom Model With Display Name")
def seed_custom_model_with_display_name(name: str, display_name: str, namespace: str) -> str:
    """Apply a minimal custom AIMModel CR so the project's custom-model list contains one entry.

    The duplicate-name warning is driven entirely by ``GET .../models`` (the
    custom-model list filtered on the ``model-source-type=custom`` label) and
    the ``model-display-name`` annotation the card reads for its title — so a
    bare CR carrying just those is enough to exercise the warning without
    onboarding real Hugging Face weights. The ``model-name`` label is set to the
    sanitized display name so the seeded CR matches what real onboarding stamps.
    The CR is cleaned up by namespace cascade when the project is torn down.
    """
    model_name_label = _sanitize_label_value(display_name)
    # json.dumps produces a valid YAML double-quoted scalar, so arbitrary names
    # (quotes, backslashes, newlines) cannot break out of the manifest.
    yaml_body = (
        "apiVersion: aim.eai.amd.com/v1alpha2\n"
        "kind: AIMModel\n"
        "metadata:\n"
        f"  name: {json.dumps(name)}\n"
        "  labels:\n"
        '    aiwb.apps.eai.amd.com/model-source-type: "custom"\n'
        f"    aiwb.apps.eai.amd.com/model-name: {json.dumps(model_name_label)}\n"
        "  annotations:\n"
        f"    aiwb.apps.eai.amd.com/model-display-name: {json.dumps(display_name)}\n"
        "spec:\n"
        '  image: "fake-registry/dummy:latest"\n'
    )
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
        handle.write(yaml_body)
        tmp_path = Path(handle.name)
    try:
        result = subprocess.run(
            ["kubectl", "apply", "-f", str(tmp_path), "-n", namespace],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("kubectl not found on PATH — cannot seed custom AIMModel CR") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"kubectl apply timed out after {_KUBECTL_TIMEOUT}s for custom AIMModel {name}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"kubectl apply failed for custom AIMModel {name}: {result.stderr}")
    return name
