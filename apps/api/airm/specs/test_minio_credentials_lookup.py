# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Guards the MinIO-credentials-fetcher lookup in universal project setup."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_SPECS = pathlib.Path(__file__).resolve().parent
_RESOURCE = _SPECS / "resources" / "airm_projects.resource"
_LIBRARY = _SPECS / "libraries" / "SecretLookup.py"
_SPEC = importlib.util.spec_from_file_location("SecretLookup", _LIBRARY)
assert _SPEC is not None and _SPEC.loader is not None
secret_lookup = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("SecretLookup", secret_lookup)
_SPEC.loader.exec_module(secret_lookup)

SECRET_NAME = "minio-credentials-fetcher"


class _Resp:
    def __init__(self, body: object) -> None:
        self._body = body

    def json(self) -> object:
        return self._body


def test_finds_secret_when_name_is_nested() -> None:
    expected = {"id": "B", "secret": {"name": SECRET_NAME}}
    body = {"data": [{"id": "A", "secret": {"name": "other"}}, expected]}
    assert secret_lookup.find_secret_by_name(_Resp(body), SECRET_NAME) == expected


def test_finds_secret_when_name_is_top_level() -> None:
    expected = {"id": "B", "name": SECRET_NAME, "projectSecrets": []}
    body = {"data": [{"id": "A", "name": "other"}, expected]}
    assert secret_lookup.find_secret_by_name(_Resp(body), SECRET_NAME) == expected


def test_returns_none_without_raising_on_error_body() -> None:
    assert secret_lookup.find_secret_by_name(_Resp({"detail": "Forbidden"}), SECRET_NAME) is None


def test_returns_none_when_absent() -> None:
    body = {"data": [{"id": "A", "name": "unrelated"}]}
    assert secret_lookup.find_secret_by_name(_Resp(body), SECRET_NAME) is None


@pytest.mark.parametrize(
    "body",
    [{"data": None}, {"data": "oops"}, [], None, {"data": [None, "x", {"name": "unrelated"}]}],
    ids=["data-null", "data-string", "list-body", "null-body", "non-dict-items"],
)
def test_returns_none_without_raising_on_non_data_shapes(body: object) -> None:
    """A null/non-list data field, or non-dict items, must yield None rather than raise."""
    assert secret_lookup.find_secret_by_name(_Resp(body), SECRET_NAME) is None


def _keyword_block() -> str:
    text = _RESOURCE.read_text()
    start = text.index("MinIO credentials are available in the current project")
    end = text.index("\nAssign fresh MinIO credentials fetcher to current project", start)
    return text[start:end]


def test_robot_keyword_delegates_lookup_without_evaluate() -> None:
    """Local Robot variables must not cross a generator scope inside Evaluate."""
    block = _keyword_block()
    assert "${match}=    Find Secret By Name    ${response}    ${secret_name}" in block
    assert "${match}=    Evaluate" not in block
    assert "TRY" in block and "EXCEPT" in block, "MinIO setup keyword must remain best-effort"


def test_keyword_uses_additive_project_assignment() -> None:
    """Project setup must never replace the shared secret's complete assignment set."""
    block = _keyword_block()
    assert "Assign secret to project" in block
    assert "Assign secret to projects" not in block
    assert "projectSecrets" not in block
