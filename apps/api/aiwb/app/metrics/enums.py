# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from enum import StrEnum


class MetricName(StrEnum):
    """Supported metric names for workload-level metric retrieval."""

    GPU_DEVICE_UTILIZATION = "gpu_device_utilization"
    GPU_MEMORY_UTILIZATION = "gpu_memory_utilization"
    REQUESTS = "requests"
    TIME_TO_FIRST_TOKEN = "time_to_first_token_seconds"
    INTER_TOKEN_LATENCY = "inter_token_latency_seconds"
    E2E_LATENCY = "e2e_request_latency_seconds"
    MAX_REQUESTS = "max_requests"
    MIN_REQUESTS = "min_requests"
    AVG_REQUESTS = "avg_requests"
    TOTAL_REQUESTS = "total_requests"
    KV_CACHE_USAGE = "kv_cache_usage"
    TOTAL_TOKENS = "total_tokens"
    CPU_USAGE = "cpu_usage"
    SYSTEM_MEMORY_USAGE = "system_memory_usage"


class NamespaceMetricName(StrEnum):
    """Supported metric names for namespace-level metric retrieval."""

    GPU_DEVICE_UTILIZATION = "gpu_device_utilization"
    GPU_MEMORY_UTILIZATION = "gpu_memory_utilization"
    CPU_USAGE = "cpu_usage"
    SYSTEM_MEMORY_USAGE = "system_memory_usage"
