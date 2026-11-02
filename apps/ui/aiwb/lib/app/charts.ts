// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';
import type { components } from '@/types/api';

/**
 * Lists charts, optionally filtered by workload type.
 */
export const listCharts = async (
  type?: components['schemas']['WorkloadType'],
): Promise<components['schemas']['ChartListResponse'][]> => {
  const { data, error, response } = await apiClient.GET('/api/charts', {
    params: { query: type ? { type } : {} },
  });
  if (error || !data) {
    throw new APIRequestError(
      `Failed to list charts: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data.data;
};

/**
 * Retrieves a single chart by ID.
 */
export const getChart = async (
  id: string,
): Promise<components['schemas']['ChartResponse']> => {
  const { data, error, response } = await apiClient.GET(
    '/api/charts/{chart_id}',
    { params: { path: { chart_id: id } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get chart: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};
