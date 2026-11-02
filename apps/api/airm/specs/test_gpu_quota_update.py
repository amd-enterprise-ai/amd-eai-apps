# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Regression tests for capacity-aware GPU quota updates."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

LIBRARY = Path(__file__).resolve().parent / "libraries" / "Quota.py"
RESOURCE = Path(__file__).resolve().parent / "resources" / "airm_projects.resource"


def _load_library() -> ModuleType:
    spec = importlib.util.spec_from_file_location("quota_test_library", LIBRARY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_selects_smallest_gpu_quota_increase() -> None:
    quota = _load_library()

    assert quota.next_gpu_quota(current=2, available=8, allocated=7) == 3


def test_rejects_increase_when_cluster_quota_is_fully_allocated() -> None:
    quota = _load_library()

    with pytest.raises(AssertionError, match="No GPU quota capacity is available"):
        quota.next_gpu_quota(current=0, available=8, allocated=8)


def test_existing_project_quota_is_not_counted_as_headroom() -> None:
    quota = _load_library()

    with pytest.raises(AssertionError, match="No GPU quota capacity is available"):
        quota.next_gpu_quota(current=2, available=8, allocated=8)


def test_gpu_update_preparation_waits_for_live_capacity() -> None:
    text = RESOURCE.read_text()
    start = text.index("Updated GPU Quota Is Prepared")
    end = text.index("\nUpdated Quota Data Is Prepared", start)
    block = text[start:end]

    assert "Wait Until Keyword Succeeds" in block
    assert "Get cluster    ${TEST_CLUSTER_ID}" in block
    assert "Next GPU Quota" in block
    assert "Convert To Integer    3" not in block
