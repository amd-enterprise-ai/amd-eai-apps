// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  PlotPoint,
  TimeRangePeriod,
  TimeSeriesData,
} from '@amdenterpriseai/types';
import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';
import { WorkspaceDeploymentPayload } from '@/types/workspaces';
import type { components, operations } from '@/types/api';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import { fetchAllPages } from './pagination';

type WorkloadMetricResult =
  | components['schemas']['MetricsTimeseries']
  | components['schemas']['MetricsScalar']
  | components['schemas']['MetricsScalarWithRange'];

/** Workload as returned by the API (single source of truth for list/read). */
type WorkloadResponse = components['schemas']['WorkloadResponse'];

export type WorkloadsResponse = components['schemas']['WorkloadsList'];

type ListWorkloadsQuery = NonNullable<
  operations['list_project_workloads_v1_projects__project__workloads_get']['parameters']['query']
>;

/**
 * Fetches a single page of workloads for a project.
 *
 * Backed by GET /v1/projects/{project}/workloads. Returns the raw paginated
 * envelope so callers can drive UI pagination. If `pageSize` is omitted
 * the backend applies its own default.
 */
export const listWorkloadsPage = async (
  projectId: string,
  page: number = 1,
  pageSize?: number,
  filters?: Pick<ListWorkloadsQuery, 'workloadType' | 'statusFilter'>,
): Promise<WorkloadsResponse> => {
  if (!projectId) {
    throw new APIRequestError('No project selected', 422);
  }
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/workloads',
    {
      params: {
        path: { project: projectId },
        query: {
          page,
          // Omit pageSize when not specified so the backend applies its own
          // default — the FE shouldn't mirror the backend's pagination defaults.
          ...(pageSize !== undefined ? { pageSize } : {}),
          workloadType: filters?.workloadType,
          statusFilter: filters?.statusFilter,
        },
      },
    },
  );

  if (error || !data) {
    throw new APIRequestError(
      `Failed to list workloads: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }

  return data;
};

/**
 * Lists every workload for a project by walking all pages.
 *
 * Thin wrapper around fetchAllPages. Intended for callers that need an exhaustive
 * list (e.g., joining workloads against AIM services or models).
 *
 * Errors propagate to the caller so React Query can surface them; see
 * `listAllInferenceDeployments` / `listAllProjectFineTunedModels` for
 * the alternative silent-degrade pattern used in join paths.
 */
export const listAllWorkloads = async (
  projectId: string,
  filters?: Pick<ListWorkloadsQuery, 'workloadType' | 'statusFilter'>,
): Promise<WorkloadResponse[]> => {
  if (!projectId) {
    throw new APIRequestError('No project selected', 422);
  }
  return fetchAllPages<WorkloadResponse>((page, pageSize) =>
    listWorkloadsPage(projectId, page, pageSize, filters),
  );
};

export const getWorkload = async (
  workloadId: string,
  projectId?: string,
): Promise<WorkloadResponse> => {
  if (!projectId) {
    throw new APIRequestError('No project selected', 422);
  }

  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/workloads/{workload_id}',
    {
      params: { path: { project: projectId, workload_id: workloadId } },
    },
  );

  if (error || !data) {
    throw new APIRequestError(
      `Failed to get workload: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }

  return data;
};

export const getWorkloadMetrics = async (
  workloadId: string,
  projectId: string,
  start: Date,
  end: Date,
  metric: components['schemas']['MetricName'],
): Promise<WorkloadMetricResult> => {
  if (!projectId) {
    throw new APIRequestError('No project selected', 422);
  }
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/workloads/{workload_id}/metrics/{metric}',
    {
      params: {
        path: {
          project: projectId,
          workload_id: workloadId,
          metric,
        },
        query: { start: start.toISOString(), end: end.toISOString() },
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get workload metrics: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

export const deleteWorkspace = async (
  projectId: string,
  workloadId: string,
) => {
  const { error, response } = await apiClient.DELETE(
    '/api/projects/{project}/workspaces/{workload_id}',
    { params: { path: { project: projectId, workload_id: workloadId } } },
  );
  if (error) {
    throw new APIRequestError(
      `Failed to terminate workspace: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
};

type WorkloadLogParams = NonNullable<
  operations['get_workload_logs_endpoint_v1_projects__project__workloads__workload_id__logs_get']['parameters']['query']
>;

export const getWorkloadLogs = async (
  projectId: string,
  workloadId: string,
  params: WorkloadLogParams,
): Promise<components['schemas']['WorkloadLogsResponse']> => {
  let pageToken = params.pageToken;
  // Ensure the pageToken carries timezone info: if it doesn't end with 'Z' or
  // contain a timezone offset (+/-), assume UTC and append 'Z'.
  if (
    pageToken &&
    !pageToken.endsWith('Z') &&
    !/[+-]\d{2}:\d{2}$/.test(pageToken)
  ) {
    pageToken = pageToken + 'Z';
  }
  // openapi-fetch omits undefined query params, so pass optionals through directly.
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/workloads/{workload_id}/logs',
    {
      params: {
        path: { project: projectId, workload_id: workloadId },
        query: {
          start: params.start,
          end: params.end,
          pageToken,
          level: params.level,
          limit: params.limit,
          direction: params.direction,
          logType: params.logType,
        },
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get workload logs: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

/**
 * Transforms time series data into chart-ready format with data points and categories.
 *
 * @param tsd - Array of time series data entries
 * @param timestamps - Array of timestamp strings for the x-axis
 * @param metadataKey - Key in metadata to use for category names
 * @returns Object with data array and categories array
 */
export const transformTimeSeriesDataToChartData = (
  tsd: TimeSeriesData[],
  timestamps: string[],
  metadataKey: string,
) => {
  return {
    data: timestamps.map((timestamp) => {
      return tsd.reduce(
        (acc: PlotPoint, group) => {
          const matchingData = group.values.find(
            (entry) => entry.timestamp === timestamp,
          );
          const meta = group.metadata[metadataKey];
          const categoryName =
            typeof meta === 'object' && meta !== null && 'name' in meta
              ? (meta as { name: string }).name
              : String(meta);
          acc[categoryName] = matchingData ? (matchingData.value ?? null) : 0;
          return acc;
        },
        { date: timestamp },
      );
    }),
    categories: tsd.map((data) => {
      const meta = data.metadata[metadataKey];
      return typeof meta === 'object' && meta !== null && 'name' in meta
        ? (meta as { name: string }).name
        : String(meta);
    }),
  };
};

/**
 * Returns the tick gap for chart x-axis based on time range period.
 * Used to reduce label density for shorter time ranges (1h, 24h).
 *
 * @param timePeriodRange - The selected time range period
 * @returns Tick gap value (36) for 1h/24h, undefined otherwise
 */
export const getTickGap = (
  timePeriodRange?: TimeRangePeriod,
): number | undefined => {
  return timePeriodRange === TimeRangePeriod['24H'] ||
    timePeriodRange === TimeRangePeriod['1H']
    ? 36
    : undefined;
};

export const deployWorkspace = async (
  projectId: string,
  payload: WorkspaceDeploymentPayload,
): Promise<components['schemas']['WorkloadResponse']> => {
  const {
    template,
    displayName,
    gpus,
    memoryPerGpu,
    cpuPerGpu,
    image,
    imagePullSecrets,
  } = payload;
  const { data, error, response } = await apiClient.POST(
    '/api/projects/{project}/workspaces',
    {
      params: {
        path: { project: projectId },
        query: displayName ? { displayName } : {},
      },
      body: {
        workspaceType: template,
        gpus,
        memoryPerGpu,
        cpuPerGpu,
        image,
        imagePullSecrets,
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to deploy catalog item: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};
