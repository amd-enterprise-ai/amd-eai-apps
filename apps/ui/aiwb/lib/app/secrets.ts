// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError } from '@amdenterpriseai/utils/app';
import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';
import type { components } from '@/types/api';

import { fetchAllPages } from './pagination';

type SecretResponse = components['schemas']['SecretResponse'];
type SecretUseCase = components['schemas']['SecretUseCase'];
type SecretCreate = components['schemas']['SecretCreate'];

const fetchSecretsPage = async (
  projectId: string,
  page: number,
  pageSize: number,
  useCase?: SecretUseCase,
) => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/secrets',
    {
      params: {
        path: { project: projectId },
        query: { page, pageSize, useCase },
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get project secrets: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

export const fetchProjectSecrets = async (
  projectId: string,
  useCase?: SecretUseCase,
): Promise<{ data: SecretResponse[] }> => {
  if (!projectId) {
    throw new APIRequestError('Project ID is required', 400);
  }
  // Walks every page via the shared fetchAllPages utility (bounded
  // concurrency, throttled). A follow-up ticket will migrate the secrets
  // table to server-side pagination so this loader can be retired in
  // favour of a paginated table.
  const data = await fetchAllPages<SecretResponse>((page, pageSize) =>
    fetchSecretsPage(projectId, page, pageSize, useCase),
  );
  return { data };
};

export const deleteProjectSecret = async (
  projectId: string,
  secretId: string,
): Promise<void> => {
  const { error, response } = await apiClient.DELETE(
    '/api/projects/{project}/secrets/{secret_name}',
    { params: { path: { project: projectId, secret_name: secretId } } },
  );
  if (error) {
    throw new APIRequestError(
      `Failed to delete secret: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
};

export const createProjectSecret = async (
  projectId: string,
  request: SecretCreate,
): Promise<SecretResponse> => {
  const { data, error, response } = await apiClient.POST(
    '/api/projects/{project}/secrets',
    { params: { path: { project: projectId } }, body: request },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to create secret: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};
