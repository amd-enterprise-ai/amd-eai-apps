# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for metrics service functions."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.metrics.constants import (
    AIM_SERVICE_ID_METRIC_LABEL,
    ALLOCATED_CPU_SERIES_LABEL,
    ALLOCATED_GPUS_SERIES_LABEL,
    ALLOCATED_SYSTEM_MEMORY_SERIES_LABEL,
    API_KEY_ID_METRIC_LABEL,
    CPU_AVAILABLE_SERIES_LABEL,
    CPU_USAGE_SERIES_LABEL,
    EXTPROC_REQUEST_DURATION_COUNT_METRIC,
    EXTPROC_TOKEN_USAGE_METRIC,
    GPU_POD_METRIC_LABEL,
    NAMESPACE_METRIC_LABEL,
    POD_CPU_USAGE_METRIC,
    POD_MEMORY_WORKING_SET_METRIC,
    SYSTEM_MEMORY_AVAILABLE_SERIES_LABEL,
    SYSTEM_MEMORY_USAGE_SERIES_LABEL,
    VLLM_POD_METRIC_LABEL,
    WORKLOAD_ID_METRIC_LABEL,
)
from app.metrics.service import (
    _escape_promql_label_value,
    _pod_selector,
    get_cpu_usage_for_namespace,
    get_cpu_usage_metric,
    get_e2e_latency_metric,
    get_gpu_device_utilization_for_namespace,
    get_gpu_device_utilization_metric,
    get_gpu_memory_utilization_metric,
    get_input_tokens_by_api_key,
    get_inter_token_latency_metric,
    get_kv_cache_usage_metric,
    get_max_requests_metric,
    get_output_tokens_by_api_key,
    get_requests_by_api_key,
    get_system_memory_usage_for_namespace,
    get_system_memory_usage_metric,
    get_total_tokens_metric,
    get_ttft_latency_metric,
    get_workload_resource_limits,
)
from app.projects.crds import Namespace


@pytest.mark.asyncio
async def test_max_requests_metric_returns_peak_value(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    """Verify MAX_REQUESTS metric calculates peak concurrent requests correctly."""
    start, end = time_range
    workload_id = "test-workload-456"

    # Mock Prometheus response with peak concurrent requests value
    mock_prometheus_client.custom_query = Mock(return_value=[{"metric": {}, "value": [end.timestamp(), "42"]}])

    result = await get_max_requests_metric(
        workload_id=workload_id,
        start=start,
        end=end,
        prometheus_client=mock_prometheus_client,
    )

    # Verify the metric returns the expected peak value
    assert result.data == 42.0
    assert result.range.start == start
    assert result.range.end == end


@pytest.mark.asyncio
async def test_max_requests_metric_handles_no_data(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    """Verify MAX_REQUESTS metric returns 0 when no data available."""
    start, end = time_range
    workload_id = "test-workload-empty"

    # Mock empty Prometheus response
    mock_prometheus_client.custom_query = Mock(return_value=[])

    result = await get_max_requests_metric(
        workload_id=workload_id,
        start=start,
        end=end,
        prometheus_client=mock_prometheus_client,
    )

    # Should return 0 when no data
    assert result.data == 0
    assert result.range.start == start
    assert result.range.end == end


@pytest.mark.asyncio
async def test_max_requests_query_uses_correct_lookback(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    """Verify MAX_REQUESTS uses the correct lookback window."""
    start, end = time_range
    workload_id = "test-workload-789"

    mock_prometheus_client.custom_query = Mock(return_value=[{"metric": {}, "value": [end.timestamp(), "10"]}])

    await get_max_requests_metric(
        workload_id=workload_id,
        start=start,
        end=end,
        prometheus_client=mock_prometheus_client,
    )

    # Verify the query was called
    mock_prometheus_client.custom_query.assert_called_once()
    call_args = mock_prometheus_client.custom_query.call_args

    # Extract the query string
    query = call_args.kwargs["query"]

    # Verify the query includes the workload_id and uses max_over_time
    assert f'workload_id="{workload_id}"' in query
    assert "max_over_time" in query
    assert "vllm:num_requests_running" in query
    assert "vllm:num_requests_waiting" in query


@pytest.mark.asyncio
async def test_gpu_metrics_use_simple_queries(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    """Verify GPU metrics use simple count/sum without avg_over_time wrapping."""
    start, end = time_range
    workload_id = "test-workload-simple"
    step = 60.0

    mock_prometheus_client.custom_query_range = Mock(
        return_value=[
            {
                "metric": {},
                "values": [[start.timestamp(), "50"]],
            }
        ]
    )

    await get_gpu_device_utilization_metric(
        workload_id=workload_id,
        start=start,
        end=end,
        step=step,
        prometheus_client=mock_prometheus_client,
    )

    call_args = mock_prometheus_client.custom_query_range.call_args
    query = call_args.kwargs["query"]

    assert "count" in query
    assert "gpu_gfx_activity" in query
    assert "avg_over_time" not in query
    assert "max_over_time" not in query


@pytest.mark.asyncio
async def test_all_timeseries_metrics_return_valid_structure(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    """Verify all timeseries metrics return the expected structure."""
    start, end = time_range
    workload_id = "test-workload-integrity"
    step = 60.0
    lookback = "2m"

    # Mock response for timeseries metrics
    mock_response = [
        {
            "metric": {},
            "values": [
                [start.timestamp(), "100"],
                [end.timestamp(), "150"],
            ],
        }
    ]

    gpu_metrics = [
        get_gpu_device_utilization_metric,
        get_gpu_memory_utilization_metric,
    ]
    lookback_metrics = [
        get_ttft_latency_metric,
        get_inter_token_latency_metric,
        get_e2e_latency_metric,
    ]

    for metric_func in gpu_metrics:
        mock_prometheus_client.custom_query_range = Mock(return_value=mock_response)

        result = await metric_func(
            workload_id=workload_id,
            start=start,
            end=end,
            step=step,
            prometheus_client=mock_prometheus_client,
        )

        assert hasattr(result, "data"), f"{metric_func.__name__} should have data"
        assert hasattr(result, "range"), f"{metric_func.__name__} should have range"
        assert len(result.data) > 0, f"{metric_func.__name__} should return data"

    for metric_func in lookback_metrics:
        mock_prometheus_client.custom_query_range = Mock(return_value=mock_response)

        result = await metric_func(
            workload_id=workload_id,
            start=start,
            end=end,
            step=step,
            lookback=lookback,
            prometheus_client=mock_prometheus_client,
        )

        # Verify structure
        assert hasattr(result, "data"), f"{metric_func.__name__} should have data"
        assert hasattr(result, "range"), f"{metric_func.__name__} should have range"
        assert len(result.data) > 0, f"{metric_func.__name__} should return data"


@pytest.mark.asyncio
async def test_scalar_metrics_return_valid_structure(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    """Verify scalar metrics return the expected structure."""
    start, end = time_range
    workload_id = "test-workload-scalar"

    # Test KV cache (scalar with range)
    mock_prometheus_client.custom_query = Mock(return_value=[{"metric": {}, "value": [end.timestamp(), "85.5"]}])

    kv_result = await get_kv_cache_usage_metric(
        workload_id=workload_id,
        start=start,
        end=end,
        prometheus_client=mock_prometheus_client,
    )

    assert hasattr(kv_result, "data")
    assert hasattr(kv_result, "range")
    assert isinstance(kv_result.data, (int, float))

    # Test total tokens (scalar without range)
    mock_prometheus_client.custom_query = Mock(return_value=[{"metric": {}, "value": [end.timestamp(), "1234"]}])

    tokens_result = await get_total_tokens_metric(
        workload_id=workload_id,
        prometheus_client=mock_prometheus_client,
    )

    assert hasattr(tokens_result, "data")
    assert isinstance(tokens_result.data, (int, float))


# =============================================================================
# _pod_selector
# =============================================================================


def test_pod_selector_returns_empty_string_when_no_pod_name() -> None:
    """Returns empty string so callers can safely append it to any query."""
    assert _pod_selector(None) == ""


def test_pod_selector_returns_label_selector_with_default_label() -> None:
    """Returns a formatted Prometheus label selector using service_instance_id."""
    result = _pod_selector("pod-abc123")
    assert result == f', {VLLM_POD_METRIC_LABEL}="pod-abc123"'


def test_pod_selector_with_custom_label() -> None:
    """Accepts an explicit label name for GPU metrics that use 'pod' instead."""
    result = _pod_selector("pod-abc123", label=GPU_POD_METRIC_LABEL)
    assert result == f', {GPU_POD_METRIC_LABEL}="pod-abc123"'


# =============================================================================
# pod_name filter in Prometheus queries
# =============================================================================


@pytest.mark.asyncio
async def test_vllm_metric_includes_service_instance_id_when_pod_name_set(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    """When pod selector is provided, vLLM metric queries filter by service_instance_id."""
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[{"metric": {}, "value": [end.timestamp(), "10"]}])

    await get_total_tokens_metric(
        workload_id="wl-123",
        prometheus_client=mock_prometheus_client,
        pod=_pod_selector("pod-abc"),
    )

    query = mock_prometheus_client.custom_query.call_args.kwargs["query"]
    assert f'{VLLM_POD_METRIC_LABEL}="pod-abc"' in query


@pytest.mark.asyncio
async def test_vllm_metric_omits_pod_filter_when_pod_name_not_set(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    """When no pod selector is given, the query contains no service_instance_id filter."""
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[{"metric": {}, "value": [end.timestamp(), "10"]}])

    await get_total_tokens_metric(workload_id="wl-123", prometheus_client=mock_prometheus_client)

    query = mock_prometheus_client.custom_query.call_args.kwargs["query"]
    assert VLLM_POD_METRIC_LABEL not in query


@pytest.mark.asyncio
async def test_gpu_metric_includes_pod_label_when_pod_name_set(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    """GPU metrics use the 'pod' label (not service_instance_id) for per-replica filtering."""
    start, end = time_range
    mock_prometheus_client.custom_query_range = Mock(
        return_value=[{"metric": {}, "values": [[start.timestamp(), "50"]]}]
    )

    await get_gpu_device_utilization_metric(
        workload_id="wl-123",
        start=start,
        end=end,
        step=60.0,
        prometheus_client=mock_prometheus_client,
        pod=_pod_selector("pod-abc", GPU_POD_METRIC_LABEL),
    )

    query = mock_prometheus_client.custom_query_range.call_args.kwargs["query"]
    assert f'{GPU_POD_METRIC_LABEL}="pod-abc"' in query
    assert VLLM_POD_METRIC_LABEL not in query


# =============================================================================
# get_input_tokens_by_api_key
# =============================================================================


@pytest.mark.asyncio
async def test_input_tokens_returns_value_when_data_present(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[{"metric": {}, "value": [end.timestamp(), "150"]}])

    result = await get_input_tokens_by_api_key("my-key", start, end, mock_prometheus_client)

    assert result.data == 150.0
    assert result.range.start == start
    assert result.range.end == end


@pytest.mark.asyncio
async def test_input_tokens_returns_zero_when_no_data(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[])

    result = await get_input_tokens_by_api_key("my-key", start, end, mock_prometheus_client)

    assert result.data == 0


@pytest.mark.asyncio
async def test_input_tokens_query_contains_api_key_id_and_token_type(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[])

    await get_input_tokens_by_api_key("test-api-key", start, end, mock_prometheus_client)

    query = mock_prometheus_client.custom_query.call_args.kwargs["query"]
    assert f'{API_KEY_ID_METRIC_LABEL}="test-api-key"' in query
    assert 'gen_ai_token_type="input"' in query
    assert EXTPROC_TOKEN_USAGE_METRIC in query


@pytest.mark.asyncio
async def test_input_tokens_query_includes_aim_service_id_when_provided(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[])

    await get_input_tokens_by_api_key("my-key", start, end, mock_prometheus_client, aim_service_id="svc-abc")

    query = mock_prometheus_client.custom_query.call_args.kwargs["query"]
    assert f'{AIM_SERVICE_ID_METRIC_LABEL}="svc-abc"' in query


@pytest.mark.asyncio
async def test_input_tokens_query_omits_aim_service_id_when_not_provided(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[])

    await get_input_tokens_by_api_key("my-key", start, end, mock_prometheus_client)

    query = mock_prometheus_client.custom_query.call_args.kwargs["query"]
    assert AIM_SERVICE_ID_METRIC_LABEL not in query


# =============================================================================
# get_output_tokens_by_api_key
# =============================================================================


@pytest.mark.asyncio
async def test_output_tokens_returns_value_when_data_present(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[{"metric": {}, "value": [end.timestamp(), "75"]}])

    result = await get_output_tokens_by_api_key("my-key", start, end, mock_prometheus_client)

    assert result.data == 75.0


@pytest.mark.asyncio
async def test_output_tokens_returns_zero_when_no_data(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[])

    result = await get_output_tokens_by_api_key("my-key", start, end, mock_prometheus_client)

    assert result.data == 0


@pytest.mark.asyncio
async def test_output_tokens_query_contains_api_key_id_and_token_type(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[])

    await get_output_tokens_by_api_key("test-api-key", start, end, mock_prometheus_client)

    query = mock_prometheus_client.custom_query.call_args.kwargs["query"]
    assert f'{API_KEY_ID_METRIC_LABEL}="test-api-key"' in query
    assert 'gen_ai_token_type="output"' in query
    assert EXTPROC_TOKEN_USAGE_METRIC in query


@pytest.mark.asyncio
async def test_output_tokens_query_includes_aim_service_id_when_provided(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[])

    await get_output_tokens_by_api_key("my-key", start, end, mock_prometheus_client, aim_service_id="svc-xyz")

    query = mock_prometheus_client.custom_query.call_args.kwargs["query"]
    assert f'{AIM_SERVICE_ID_METRIC_LABEL}="svc-xyz"' in query


# =============================================================================
# get_requests_by_api_key
# =============================================================================


@pytest.mark.asyncio
async def test_requests_returns_value_when_data_present(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[{"metric": {}, "value": [end.timestamp(), "10"]}])

    result = await get_requests_by_api_key("my-key", start, end, mock_prometheus_client)

    assert result.data == 10.0


@pytest.mark.asyncio
async def test_requests_returns_zero_when_no_data(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[])

    result = await get_requests_by_api_key("my-key", start, end, mock_prometheus_client)

    assert result.data == 0


@pytest.mark.asyncio
async def test_requests_query_contains_api_key_id_and_uses_ceil(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[])

    await get_requests_by_api_key("test-api-key", start, end, mock_prometheus_client)

    query = mock_prometheus_client.custom_query.call_args.kwargs["query"]
    assert f'{API_KEY_ID_METRIC_LABEL}="test-api-key"' in query
    assert "ceil(" in query
    assert EXTPROC_REQUEST_DURATION_COUNT_METRIC in query


@pytest.mark.asyncio
async def test_requests_query_includes_aim_service_id_when_provided(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query = Mock(return_value=[])

    await get_requests_by_api_key("my-key", start, end, mock_prometheus_client, aim_service_id="svc-abc")

    query = mock_prometheus_client.custom_query.call_args.kwargs["query"]
    assert f'{AIM_SERVICE_ID_METRIC_LABEL}="svc-abc"' in query


# =============================================================================
# _escape_promql_label_value
# =============================================================================


def test_escape_promql_label_value_passes_clean_values_through() -> None:
    assert _escape_promql_label_value("my-api-key") == "my-api-key"


def test_escape_promql_label_value_escapes_double_quotes() -> None:
    assert _escape_promql_label_value('key"name') == 'key\\"name'


def test_escape_promql_label_value_escapes_backslashes() -> None:
    assert _escape_promql_label_value("key\\name") == "key\\\\name"


def test_escape_promql_label_value_escapes_backslash_before_quote() -> None:
    assert _escape_promql_label_value('key\\"') == 'key\\\\\\"'


# =============================================================================
# get_gpu_device_utilization_for_namespace
# =============================================================================


@pytest.mark.asyncio
async def test_gpu_device_utilization_for_namespace_appends_allocation_series(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    namespace = Namespace(name="team-a")
    mock_prometheus_client.custom_query_range = Mock(
        return_value=[{"metric": {}, "values": [[start.timestamp(), "2"]]}]
    )

    with patch("app.metrics.service.get_project_gpu_allocation_ceiling", AsyncMock(return_value=8)):
        result = await get_gpu_device_utilization_for_namespace(namespace, start, end, mock_prometheus_client, Mock())

    labels = [series.metadata.label for series in result.data]
    assert ALLOCATED_GPUS_SERIES_LABEL in labels
    allocation_series = next(series for series in result.data if series.metadata.label == ALLOCATED_GPUS_SERIES_LABEL)
    assert all(value.value == 8 for value in allocation_series.values)
    assert len(allocation_series.values) == len(result.range.timestamps)


@pytest.mark.asyncio
async def test_gpu_device_utilization_for_namespace_omits_allocation_series_when_unresolved(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    namespace = Namespace(name="team-a")
    mock_prometheus_client.custom_query_range = Mock(
        return_value=[{"metric": {}, "values": [[start.timestamp(), "2"]]}]
    )

    with patch("app.metrics.service.get_project_gpu_allocation_ceiling", AsyncMock(return_value=None)):
        result = await get_gpu_device_utilization_for_namespace(namespace, start, end, mock_prometheus_client, Mock())

    labels = [series.metadata.label for series in result.data]
    assert ALLOCATED_GPUS_SERIES_LABEL not in labels


# =============================================================================
# CPU / system-memory workload metrics
# =============================================================================


@pytest.mark.asyncio
async def test_get_workload_resource_limits_sums_pod_container_limits() -> None:
    pods: list[dict] = [
        {"spec": {"containers": [{"resources": {"limits": {"cpu": "32", "memory": "32Gi"}}}]}},
        {"spec": {"containers": [{"resources": {"limits": {"cpu": "500m", "memory": "512Mi"}}}]}},
    ]
    with patch("app.metrics.service.list_aim_service_replicas", AsyncMock(return_value=pods)):
        cpu_cores, memory_bytes = await get_workload_resource_limits(
            "team-a", "11111111-1111-1111-1111-111111111111", Mock()
        )

    # 32000 + 500 milli-cores -> 32.5 cores; 32Gi + 512Mi in bytes
    assert cpu_cores == 32.5
    assert memory_bytes == 32 * 1024**3 + 512 * 1024**2


@pytest.mark.asyncio
async def test_get_workload_resource_limits_scopes_to_single_pod_when_pod_name_set() -> None:
    pods: list[dict] = [
        {
            "metadata": {"name": "replica-a"},
            "spec": {"containers": [{"resources": {"limits": {"cpu": "6", "memory": "40Gi"}}}]},
        },
        {
            "metadata": {"name": "replica-b"},
            "spec": {"containers": [{"resources": {"limits": {"cpu": "6", "memory": "40Gi"}}}]},
        },
    ]
    with patch("app.metrics.service.list_aim_service_replicas", AsyncMock(return_value=pods)):
        cpu_cores, memory_bytes = await get_workload_resource_limits(
            "team-a", "11111111-1111-1111-1111-111111111111", Mock(), pod_name="replica-b"
        )

    # Only replica-b counts, so the ceiling matches a single pod, not the summed 2x.
    assert cpu_cores == 6.0
    assert memory_bytes == 40 * 1024**3


@pytest.mark.asyncio
async def test_get_workload_resource_limits_returns_none_without_limits() -> None:
    pods: list[dict] = [{"spec": {"containers": [{"resources": {}}]}}]
    with patch("app.metrics.service.list_aim_service_replicas", AsyncMock(return_value=pods)):
        cpu_cores, memory_bytes = await get_workload_resource_limits(
            "team-a", "11111111-1111-1111-1111-111111111111", Mock()
        )

    assert cpu_cores is None
    assert memory_bytes is None


@pytest.mark.asyncio
async def test_get_workload_resource_limits_returns_none_on_failure() -> None:
    with patch("app.metrics.service.list_aim_service_replicas", AsyncMock(side_effect=RuntimeError("boom"))):
        result = await get_workload_resource_limits("team-a", "11111111-1111-1111-1111-111111111111", Mock())

    assert result == (None, None)


@pytest.mark.asyncio
async def test_cpu_usage_query_sums_pod_metric_by_workload_id(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    workload_id = "wl-cpu-1"
    mock_prometheus_client.custom_query_range = Mock(
        return_value=[{"metric": {}, "values": [[start.timestamp(), "0.5"]]}]
    )

    with patch("app.metrics.service.get_workload_resource_limits", AsyncMock(return_value=(None, None))):
        result = await get_cpu_usage_metric(workload_id, start, end, 60.0, mock_prometheus_client, Mock(), "team-a")

    query = mock_prometheus_client.custom_query_range.call_args.kwargs["query"]
    assert POD_CPU_USAGE_METRIC in query
    assert f'{WORKLOAD_ID_METRIC_LABEL}="{workload_id}"' in query
    assert query.strip().startswith("sum(")
    assert [series.metadata.label for series in result.data] == [CPU_USAGE_SERIES_LABEL]


@pytest.mark.asyncio
async def test_cpu_usage_appends_available_ceiling_from_limit(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query_range = Mock(
        return_value=[{"metric": {}, "values": [[start.timestamp(), "0.5"]]}]
    )

    with patch("app.metrics.service.get_workload_resource_limits", AsyncMock(return_value=(32.0, None))):
        result = await get_cpu_usage_metric("wl", start, end, 60.0, mock_prometheus_client, Mock(), "team-a")

    ceiling = next(s for s in result.data if s.metadata.label == CPU_AVAILABLE_SERIES_LABEL)
    assert all(value.value == 32.0 for value in ceiling.values)
    assert len(ceiling.values) == len(result.range.timestamps)


@pytest.mark.asyncio
async def test_cpu_usage_omits_ceiling_when_limit_unresolved(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    mock_prometheus_client.custom_query_range = Mock(
        return_value=[{"metric": {}, "values": [[start.timestamp(), "0.5"]]}]
    )

    with patch("app.metrics.service.get_workload_resource_limits", AsyncMock(return_value=(None, None))):
        result = await get_cpu_usage_metric("wl", start, end, 60.0, mock_prometheus_client, Mock(), "team-a")

    assert CPU_AVAILABLE_SERIES_LABEL not in [s.metadata.label for s in result.data]


@pytest.mark.asyncio
async def test_system_memory_usage_query_and_available_ceiling(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    workload_id = "wl-mem-1"
    memory_limit = float(32 * 1024**3)
    mock_prometheus_client.custom_query_range = Mock(
        return_value=[{"metric": {}, "values": [[start.timestamp(), "1048576"]]}]
    )

    with patch("app.metrics.service.get_workload_resource_limits", AsyncMock(return_value=(None, memory_limit))):
        result = await get_system_memory_usage_metric(
            workload_id, start, end, 60.0, mock_prometheus_client, Mock(), "team-a"
        )

    query = mock_prometheus_client.custom_query_range.call_args.kwargs["query"]
    assert POD_MEMORY_WORKING_SET_METRIC in query
    assert f'{WORKLOAD_ID_METRIC_LABEL}="{workload_id}"' in query
    labels = [s.metadata.label for s in result.data]
    assert SYSTEM_MEMORY_USAGE_SERIES_LABEL in labels
    ceiling = next(s for s in result.data if s.metadata.label == SYSTEM_MEMORY_AVAILABLE_SERIES_LABEL)
    assert all(value.value == memory_limit for value in ceiling.values)


# =============================================================================
# Namespace-level CPU / system-memory metrics
# =============================================================================


@pytest.mark.asyncio
async def test_cpu_usage_for_namespace_sums_and_appends_ceiling(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    namespace = Namespace(name="team-a")
    mock_prometheus_client.custom_query_range = Mock(
        return_value=[{"metric": {}, "values": [[start.timestamp(), "3.5"]]}]
    )

    with patch("app.metrics.service.get_project_cpu_allocation_ceiling", AsyncMock(return_value=112.0)):
        result = await get_cpu_usage_for_namespace(namespace, start, end, mock_prometheus_client, Mock())

    query = mock_prometheus_client.custom_query_range.call_args.kwargs["query"]
    assert POD_CPU_USAGE_METRIC in query
    assert f'{NAMESPACE_METRIC_LABEL}="{namespace.name}"' in query
    ceiling = next(s for s in result.data if s.metadata.label == ALLOCATED_CPU_SERIES_LABEL)
    assert all(value.value == 112.0 for value in ceiling.values)
    assert len(ceiling.values) == len(result.range.timestamps)


@pytest.mark.asyncio
async def test_cpu_usage_for_namespace_omits_ceiling_when_unresolved(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    namespace = Namespace(name="team-a")
    mock_prometheus_client.custom_query_range = Mock(
        return_value=[{"metric": {}, "values": [[start.timestamp(), "3.5"]]}]
    )

    with patch("app.metrics.service.get_project_cpu_allocation_ceiling", AsyncMock(return_value=None)):
        result = await get_cpu_usage_for_namespace(namespace, start, end, mock_prometheus_client, Mock())

    assert ALLOCATED_CPU_SERIES_LABEL not in [s.metadata.label for s in result.data]


@pytest.mark.asyncio
async def test_system_memory_usage_for_namespace_sums_and_appends_ceiling(
    mock_prometheus_client: Mock, time_range: tuple[datetime, datetime]
) -> None:
    start, end = time_range
    namespace = Namespace(name="team-a")
    ceiling_bytes = float(256 * 1024**3)
    mock_prometheus_client.custom_query_range = Mock(
        return_value=[{"metric": {}, "values": [[start.timestamp(), "1048576"]]}]
    )

    with patch("app.metrics.service.get_project_memory_allocation_ceiling", AsyncMock(return_value=ceiling_bytes)):
        result = await get_system_memory_usage_for_namespace(namespace, start, end, mock_prometheus_client, Mock())

    query = mock_prometheus_client.custom_query_range.call_args.kwargs["query"]
    assert POD_MEMORY_WORKING_SET_METRIC in query
    assert f'{NAMESPACE_METRIC_LABEL}="{namespace.name}"' in query
    assert SYSTEM_MEMORY_USAGE_SERIES_LABEL in [s.metadata.label for s in result.data]
    ceiling = next(s for s in result.data if s.metadata.label == ALLOCATED_SYSTEM_MEMORY_SERIES_LABEL)
    assert all(value.value == ceiling_bytes for value in ceiling.values)
