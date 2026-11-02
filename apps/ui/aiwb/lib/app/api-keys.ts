// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError } from '@amdenterpriseai/utils/app';
import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';
import type { components } from '@/types/api';

import { fetchAllPages } from './pagination';

type ApiKeyResponse = components['schemas']['ApiKeyResponse'];

const fetchApiKeysPage = async (
  projectId: string,
  page: number,
  pageSize: number,
) => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/api-keys',
    { params: { path: { project: projectId }, query: { page, pageSize } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch API keys: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

export const fetchProjectApiKeys = async (
  projectId: string,
): Promise<{ data: ApiKeyResponse[] }> => {
  // Walks every page via the shared fetchAllPages utility (bounded
  // concurrency, throttled).
  // TODO: migrate ApiKeysTable to ServerSideDataTable so this
  // loader can be retired in favour of a server-side paginated table.
  const data = await fetchAllPages<ApiKeyResponse>((page, pageSize) =>
    fetchApiKeysPage(projectId, page, pageSize),
  );
  return { data };
};

export const deleteApiKey = async (
  projectId: string,
  apiKeyId: string,
): Promise<void> => {
  const { error, response } = await apiClient.DELETE(
    '/api/projects/{project}/api-keys/{api_key_id}',
    { params: { path: { project: projectId, api_key_id: apiKeyId } } },
  );
  if (!response.ok) {
    throw new APIRequestError(
      `Failed to delete API key: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
};

export const createApiKey = async (
  projectId: string,
  data: { displayName: string; ttl?: string; aimIds?: string[] },
) => {
  const {
    data: created,
    error,
    response,
  } = await apiClient.POST('/api/projects/{project}/api-keys', {
    params: { path: { project: projectId } },
    // ApiKeyCreate types ttl/renewable/numUses/explicitMaxTtl/period as
    // required because they carry OpenAPI defaults, but the backend fills
    // them server-side; the UI only sends the fields the user set.
    body: data as components['schemas']['ApiKeyCreate'],
  });
  if (error || !created) {
    throw new APIRequestError(
      `Failed to create API key: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return created;
};

export const fetchApiKeyDetails = async (
  projectId: string,
  apiKeyId: string,
) => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/api-keys/{api_key_id}',
    { params: { path: { project: projectId, api_key_id: apiKeyId } } },
  );

  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch API key details: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }

  return data;
};

export const fetchApiKeyMetrics = async (
  projectId: string,
  apiKeyId: string,
  params: { start: string; end: string },
) => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/api-keys/{api_key_id}/metrics',
    {
      params: {
        path: { project: projectId, api_key_id: apiKeyId },
        query: { start: params.start, end: params.end },
      },
    },
  );

  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch API key metrics: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }

  return data;
};

export const updateApiKeyBindings = async (
  projectId: string,
  apiKeyId: string,
  aimIds: string[],
) => {
  const { data, error, response } = await apiClient.PATCH(
    '/api/projects/{project}/api-keys/{api_key_id}',
    {
      params: { path: { project: projectId, api_key_id: apiKeyId } },
      body: { aimIds },
    },
  );

  if (error || !data) {
    throw new APIRequestError(
      `Failed to update API key bindings: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }

  return data;
};
