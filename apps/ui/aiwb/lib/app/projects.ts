// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError } from '@amdenterpriseai/utils/app';
import type { TimeSeriesResponse } from '@/types/metrics';
import type { ProjectsResponse } from '@/types/projects';
import type { components, operations } from '@/types/api';
import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';

export type FetchProjectWorkloadMetricsParams = NonNullable<
  operations['get_project_workload_metrics_v1_projects__project__workloads_metrics_get']['parameters']['query']
>;

export const fetchProjectWorkloadMetrics = async (
  project: string,
  options: FetchProjectWorkloadMetricsParams = {},
): Promise<components['schemas']['WorkloadMetricsListPaginated']> => {
  const {
    page = 1,
    pageSize = 10,
    sortBy,
    sortOrder,
    workloadType,
    statusFilter,
  } = options;
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/workloads/metrics',
    {
      params: {
        path: { project },
        query: {
          page,
          pageSize,
          ...(sortBy
            ? {
                sortBy,
                sortOrder,
              }
            : {}),
          workloadType,
          statusFilter,
        },
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get project workload metrics: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

export const fetchProjectWorkloadStats = async (
  project: string,
): Promise<components['schemas']['WorkloadStatsCounts']> => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/workloads/stats',
    { params: { path: { project } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get project workload stats: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

export const fetchProjectGPUMemoryUtilization = async (
  project: string,
  start: Date,
  end: Date,
): Promise<TimeSeriesResponse> => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/workloads/metrics/{metric}',
    {
      params: {
        path: { project, metric: 'gpu_memory_utilization' },
        query: { start: start.toISOString(), end: end.toISOString() },
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get project GPU memory utilization: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

export const fetchProjectGPUDeviceUtilization = async (
  project: string,
  start: Date,
  end: Date,
): Promise<TimeSeriesResponse> => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/workloads/metrics/{metric}',
    {
      params: {
        path: { project, metric: 'gpu_device_utilization' },
        query: { start: start.toISOString(), end: end.toISOString() },
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get project GPU device utilization: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

export const fetchProjectCpuUsage = async (
  project: string,
  start: Date,
  end: Date,
): Promise<TimeSeriesResponse> => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/workloads/metrics/{metric}',
    {
      params: {
        path: { project, metric: 'cpu_usage' },
        query: { start: start.toISOString(), end: end.toISOString() },
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get project CPU usage: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

export const fetchProjectSystemMemory = async (
  project: string,
  start: Date,
  end: Date,
): Promise<TimeSeriesResponse> => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/workloads/metrics/{metric}',
    {
      params: {
        path: { project, metric: 'system_memory_usage' },
        query: { start: start.toISOString(), end: end.toISOString() },
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get project system memory usage: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

export const fetchProjectQuota = async (
  project: string,
): Promise<components['schemas']['ProjectQuotaResponse']> => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/quota',
    { params: { path: { project } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get project quota: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

export const fetchProjects = async (): Promise<ProjectsResponse> => {
  const { data, error, response } = await apiClient.GET('/api/projects');
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get projects: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};
