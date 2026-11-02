// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError } from '@amdenterpriseai/utils/app';

import type { components } from '@/types/api';
import { TimeSeriesResponse } from '@/types/metrics';

import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';

type MetricScalarResponse = components['schemas']['MetricsScalarWithRange'];

type MetricTimeRangeParams = {
  workloadId: string;
  namespace: string;
  start: Date;
  end: Date;
  podName?: string;
};

export const getTimeseriesMetric = async (
  params: MetricTimeRangeParams & {
    metric: components['schemas']['MetricName'];
  },
): Promise<TimeSeriesResponse> => {
  const { workloadId, namespace, start, end, metric, podName } = params;
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/inference/{id}/metrics/{metric}',
    {
      params: {
        path: {
          project: namespace,
          id: workloadId,
          metric,
        },
        query: {
          start: start.toISOString(),
          end: end.toISOString(),
          ...(podName ? { podName } : {}),
        },
      },
    },
  );
  if (error) {
    throw new APIRequestError(
      `Failed to get workload metric: ${metric}: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  // The endpoint types data as a metric union; the metric name fixes the member.
  return data as TimeSeriesResponse;
};

export const getScalarMetric = async (
  params: MetricTimeRangeParams & {
    metric: components['schemas']['MetricName'];
  },
): Promise<MetricScalarResponse> => {
  const { workloadId, namespace, start, end, metric, podName } = params;
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/inference/{id}/metrics/{metric}',
    {
      params: {
        path: {
          project: namespace,
          id: workloadId,
          metric,
        },
        query: {
          start: start.toISOString(),
          end: end.toISOString(),
          ...(podName ? { podName } : {}),
        },
      },
    },
  );
  if (error) {
    throw new APIRequestError(
      `Failed to get workload metric: ${metric}: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  // The endpoint types data as a metric union; the metric name fixes the member.
  return data as MetricScalarResponse;
};

// Timeseries metric wrappers
export const getTimeToFirstToken = (params: MetricTimeRangeParams) =>
  getTimeseriesMetric({ ...params, metric: 'time_to_first_token_seconds' });

export const getInterTokenLatency = (params: MetricTimeRangeParams) =>
  getTimeseriesMetric({ ...params, metric: 'inter_token_latency_seconds' });

export const getEndToEndLatency = (params: MetricTimeRangeParams) =>
  getTimeseriesMetric({ ...params, metric: 'e2e_request_latency_seconds' });

export const getInferenceRequests = (params: MetricTimeRangeParams) =>
  getTimeseriesMetric({ ...params, metric: 'requests' });

// Scalar metric wrappers
export const getMaxRequests = (params: MetricTimeRangeParams) =>
  getScalarMetric({ ...params, metric: 'max_requests' });

export const getMinRequests = (params: MetricTimeRangeParams) =>
  getScalarMetric({ ...params, metric: 'min_requests' });

export const getAvgRequests = (params: MetricTimeRangeParams) =>
  getScalarMetric({ ...params, metric: 'avg_requests' });

export const getTotalRequests = (params: MetricTimeRangeParams) =>
  getScalarMetric({ ...params, metric: 'total_requests' });

export const getTotalTokens = (params: MetricTimeRangeParams) =>
  getScalarMetric({ ...params, metric: 'total_tokens' });

export const getKVCacheUsage = (params: MetricTimeRangeParams) =>
  getScalarMetric({ ...params, metric: 'kv_cache_usage' });
