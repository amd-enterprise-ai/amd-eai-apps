# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for stdin-only Kubernetes secret provisioning."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "libraries"))

import KubernetesSecretHelper
from KubernetesSecretHelper import _run_kubectl, create_kubernetes_secret_from_value


class FakeSecret:
    def __init__(self, value: str):
        self.value = value

    def __str__(self) -> str:
        return "***"


def _result(code: int, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, stdout=stdout)


def test_existing_secret_is_a_noop(monkeypatch):
    calls = []

    def fake_run(args, stdin=None):
        calls.append((args, stdin))
        return _result(0)

    monkeypatch.setattr(KubernetesSecretHelper, "_run_kubectl", fake_run)
    create_kubernetes_secret_from_value("hf-token", "project", FakeSecret("secret-value"))
    assert calls == [(["get", "secret", "hf-token", "-n", "project"], None)]


def test_secret_value_is_passed_only_via_stdin(monkeypatch):
    calls = []

    def fake_run(args, stdin=None):
        calls.append((args, stdin))
        return _result(1) if args[0] == "get" else _result(0)

    monkeypatch.setattr(KubernetesSecretHelper, "_run_kubectl", fake_run)
    create_kubernetes_secret_from_value(
        "hf-token",
        "project",
        FakeSecret("secret-value"),
        "--from-file=token=/dev/stdin",
    )
    create_args, stdin = calls[1]
    assert not any("secret-value" in arg for arg in create_args)
    assert stdin == "secret-value"
    assert create_args == [
        "create",
        "secret",
        "generic",
        "hf-token",
        "--from-file=token=/dev/stdin",
        "-n",
        "project",
    ]


def test_already_exists_race_is_success(monkeypatch):
    monkeypatch.setattr(
        KubernetesSecretHelper,
        "_run_kubectl",
        lambda args, stdin=None: _result(1, "AlreadyExists"),
    )
    create_kubernetes_secret_from_value("hf-token", "project", FakeSecret("secret-value"))


def test_secret_creation_error_is_raised(monkeypatch):
    monkeypatch.setattr(
        KubernetesSecretHelper,
        "_run_kubectl",
        lambda args, stdin=None: _result(1, "Unauthorized"),
    )
    with pytest.raises(AssertionError, match="Unauthorized"):
        create_kubernetes_secret_from_value("hf-token", "project", FakeSecret("secret-value"))


def test_kubectl_timeout_is_retryable_and_does_not_leak_stdin(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(["kubectl", "create"], 15)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(AssertionError, match=r"kubectl get secret hf-token.*timed out after 15s") as error:
        _run_kubectl(["get", "secret", "hf-token"], stdin="secret-value")
    assert "secret-value" not in str(error.value)
