# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Prometheus query label selectors
WORKLOAD_ID_METRIC_LABEL = "workload_id"
NAMESPACE_METRIC_LABEL = "namespace"
CLUSTER_NAME_METRIC_LABEL = "kube_cluster_name"
VLLM_POD_METRIC_LABEL = "service_instance_id"
GPU_POD_METRIC_LABEL = "pod"

# Series label for the synthesized GPU allocation ceiling appended to the
# device-utilization timeseries — must match the frontend's expected label.
ALLOCATED_GPUS_SERIES_LABEL = "allocated_gpus"

# kubeletstats pod-scoped metrics (cluster-forge otel-collector-metrics-kubelet).
# CPU utilization is reported in cores despite the "_ratio" suffix (OTel unit tag).
POD_CPU_USAGE_METRIC = "k8s_pod_cpu_utilization_ratio"
POD_MEMORY_WORKING_SET_METRIC = "k8s_pod_memory_working_set_bytes"

# Series labels for CPU/memory usage and their availability ceilings (limits
# resolved from the workload's pods) — must match the frontend's expected labels.
CPU_USAGE_SERIES_LABEL = "cpu_usage"
CPU_AVAILABLE_SERIES_LABEL = "cpu_available"
SYSTEM_MEMORY_USAGE_SERIES_LABEL = "system_memory_usage"
SYSTEM_MEMORY_AVAILABLE_SERIES_LABEL = "system_memory_available"

# Namespace-level allocation ceilings (project CPU/memory quota or cluster capacity),
# appended to the usage timeseries like allocated_gpus — must match the frontend labels.
ALLOCATED_CPU_SERIES_LABEL = "allocated_cpu"
ALLOCATED_SYSTEM_MEMORY_SERIES_LABEL = "allocated_system_memory"

# API key metric label selectors — sourced from ext-proc metricsRequestHeaderAttributes
API_KEY_ID_METRIC_LABEL = "api_key_id"
AIM_SERVICE_ID_METRIC_LABEL = "aim_service_id"

# ext-proc Prometheus metric names (OTel Semantic Conventions for Generative AI)
EXTPROC_TOKEN_USAGE_METRIC = (
    "gen_ai_client_token_usage_sum"  # `_sum`: cumulative-sum series; increase() gives the period delta
)
EXTPROC_REQUEST_DURATION_COUNT_METRIC = "gen_ai_server_request_duration_seconds_count"
GEN_AI_TOKEN_TYPE_LABEL = "gen_ai_token_type"

MAX_DAYS_FOR_TIMESERIES = 8
MAX_DAYS_FOR_METRICS = 30

# OTel collector scrape interval — drives minimum lookback window
SCRAPE_INTERVAL_SECONDS = 30

PROMETHEUS_NAN_STRING = "NaN"
PROMETHEUS_INF_STRING = "Inf"
PROMETHEUS_MINUS_INF_STRING = "-Inf"

# FastAPI Query parameter documentation
METRICS_START_TIME_DOC = (
    "Start time for metrics range (ISO 8601 with timezone, e.g. UTC: ...Z or +00:00). Prometheus expects UTC."
)
METRICS_END_TIME_DOC = (
    "End time for metrics range (ISO 8601 with timezone, e.g. UTC: ...Z or +00:00). Prometheus expects UTC."
)
