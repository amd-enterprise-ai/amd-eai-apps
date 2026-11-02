// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';

export const getClusterResources = async () => {
  const { data, error, response } = await apiClient.GET('/api/resources');
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch cluster resources: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

export const getAimImages = async () => {
  const { data, error, response } = await apiClient.GET(
    '/api/cluster/aim-images',
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch aim-engine image families: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

export const getClusterAccelerators = async () => {
  const { data, error, response } = await apiClient.GET(
    '/api/cluster/accelerators',
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch cluster accelerators: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};
