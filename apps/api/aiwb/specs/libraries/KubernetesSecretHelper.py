# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Robot Framework library for idempotent Kubernetes secret provisioning."""

from __future__ import annotations

import subprocess

from robot.api import logger
from robot.api.deco import keyword

_KUBECTL_TIMEOUT_SECONDS = 15


def _run_kubectl(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run kubectl within one retry interval and convert timeouts into retryable assertion failures."""
    try:
        return subprocess.run(
            ["kubectl", *args],
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=_KUBECTL_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # Never include stdin in the error: it can contain a secret value. Robot's
        # Wait Until Keyword Succeeds treats AssertionError as a retryable failure.
        raise AssertionError(f"kubectl {' '.join(args)} timed out after {_KUBECTL_TIMEOUT_SECONDS}s") from exc


@keyword("Create Kubernetes Secret From Value")
def create_kubernetes_secret_from_value(
    secret_name: str,
    namespace: str,
    secret_value: object,
    *create_args: str,
) -> None:
    """Idempotently create a secret while passing its masked value only over stdin."""
    existing = _run_kubectl(["get", "secret", secret_name, "-n", namespace])
    if existing.returncode == 0:
        logger.info(f"Secret {secret_name} already exists in namespace {namespace}")
        return

    # Robot's Secret object masks repr/str in logs. Its ``value`` property is the
    # plaintext needed for stdin; plain strings remain accepted for generic callers.
    plaintext = getattr(secret_value, "value", secret_value)
    result = _run_kubectl(
        ["create", "secret", "generic", secret_name, *create_args, "-n", namespace],
        stdin=str(plaintext),
    )
    if result.returncode == 0 or "AlreadyExists" in result.stdout:
        logger.info(f"Created secret {secret_name} in namespace {namespace}")
        return
    raise AssertionError(f"Failed to create secret {secret_name}: {result.stdout}")
