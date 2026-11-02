# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Robot Framework helpers for capacity-aware quota preparation."""


def next_gpu_quota(current: int | str, available: int | str, allocated: int | str) -> int:
    """Return the smallest GPU quota increase that fits the cluster."""
    current_count = int(current)
    available_count = int(available)
    allocated_count = int(allocated)
    target = current_count + 1

    if allocated_count - current_count + target > available_count:
        raise AssertionError(
            "No GPU quota capacity is available for an increase: "
            f"current={current_count}, allocated={allocated_count}, available={available_count}"
        )

    return target
