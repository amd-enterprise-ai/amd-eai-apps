# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for CollectorAffinityGuard: the CPU/EPYC selector allowlist vs. the collector chart."""

import sys
from pathlib import Path

import pytest

# Add libraries to path so CollectorAffinityGuard is importable
sys.path.insert(0, str(Path(__file__).parent / "libraries"))

from CollectorAffinityGuard import (
    check_collector_epyc_allowlist,
    collector_epyc_models_from_chart,
)


def test_collector_supported_epyc_models_match_helm_chart():
    check_collector_epyc_allowlist()


def test_collector_guard_rejects_non_exists_operator():
    chart = """
    - matchExpressions:
        - key: feature.node.kubernetes.io/aim-accelerator.EPYC_ZEN4
          operator: DoesNotExist
    """
    with pytest.raises(AssertionError, match="operator: Exists"):
        collector_epyc_models_from_chart(chart)


def test_collector_guard_rejects_epyc_models_anded_in_one_term():
    chart = """
    - matchExpressions:
        - key: feature.node.kubernetes.io/aim-accelerator.EPYC_ZEN4
          operator: Exists
        - key: feature.node.kubernetes.io/aim-accelerator.EPYC_ZEN5
          operator: Exists
    """
    with pytest.raises(AssertionError, match="one OR-ed nodeSelectorTerm"):
        collector_epyc_models_from_chart(chart)


def test_collector_guard_ignores_commented_out_epyc_key():
    chart = """
    - matchExpressions:
        # - key: feature.node.kubernetes.io/aim-accelerator.EPYC_ZEN4
        #   operator: Exists
        - key: feature.node.kubernetes.io/aim-accelerator.EPYC_ZEN5
          operator: Exists
    """
    assert collector_epyc_models_from_chart(chart) == {"EPYC_ZEN5"}
