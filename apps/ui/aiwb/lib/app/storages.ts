// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError } from '@amdenterpriseai/utils/app';
import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';
import type { components } from '@/types/api';

type ProjectStorageResponse = components['schemas']['ProjectStorageResponse'];
type ProjectStorageCreateRequest =
  components['schemas']['ProjectStorageCreateRequest'];
type StorageType = components['schemas']['StorageType'];

export const fetchProjectStorages = async (
  projectId: string,
  type?: StorageType,
): Promise<{ data: ProjectStorageResponse[] }> => {
  if (!projectId) {
    throw new APIRequestError('Project ID is required', 400);
  }
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/storages',
    { params: { path: { project: projectId }, query: { type } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get project storages: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return { data: data.data };
};

export const createProjectStorage = async (
  projectId: string,
  request: ProjectStorageCreateRequest,
): Promise<ProjectStorageResponse> => {
  if (!projectId) {
    throw new APIRequestError('Project ID is required', 400);
  }
  const { data, error, response } = await apiClient.POST(
    '/api/projects/{project}/storages',
    { params: { path: { project: projectId } }, body: request },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to create storage: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};
