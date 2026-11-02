# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Enums for cluster resource APIs."""

from enum import StrEnum


class ClusterAcceleratorType(StrEnum):
    """Accelerator family type values returned by cluster accelerators endpoint."""

    CPU = "cpu"
    GPU = "gpu"
    APU = "apu"
    UNKNOWN = "unknown"
