// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError, getErrorMessage } from '@amdenterpriseai/utils/app';

import { ChipDisplayVariant } from '@amdenterpriseai/types';
import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';
import type { components, operations } from '@/types/api';
import type { DatasetType } from '@/types/datasets';

import { fetchAllPages } from './pagination';

type DatasetResponse = components['schemas']['DatasetResponse'];

export const DATASET_FILESIZE_LIMIT = 100 * 1024 * 1024; // 100MB

export const getDatasetTypeVariants = (
  t: (key: string) => string,
): Record<DatasetType, ChipDisplayVariant> => ({
  'Fine-tuning': {
    label: t('types.Fine-tuning'),
    color: 'warning',
  },
});

type ListDatasetsQuery = NonNullable<
  operations['get_datasets_v1_projects__project__datasets_get']['parameters']['query']
>;

// TODO: Replace getAllDatasets callers (e.g. FinetuneWizard) with a
// server-side picker so the UI scales to projects with >100 datasets without
// walking every page.

/**
 * Fetches a single page of datasets for a project.
 *
 * Backed by GET /v1/projects/{project}/datasets. Returns the raw paginated
 * envelope so callers can drive UI pagination. The `type` filter is a single
 * exact match (backend does not support repeated values), and `name` matches
 * a single exact dataset name.
 *
 * @param {string} projectId - The project (1:1 with namespace) to list in.
 * @param {object} [options] - Optional filters and pagination controls.
 * @throws {APIRequestError} If the API request fails.
 */
export const listDatasets = async (
  projectId: string,
  options: ListDatasetsQuery = {},
) => {
  const { page = 1, pageSize = 10, ...filters } = options;
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/datasets',
    {
      params: {
        path: { project: projectId },
        query: {
          page,
          pageSize,
          type: filters.type,
          name: filters.name,
        },
      },
    },
  );

  if (error || !data) {
    throw new APIRequestError(
      `Failed to list datasets: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }

  return data;
};

/**
 * Lists every dataset for a project by walking all pages.
 *
 * Thin wrapper around fetchAllPages. Intended for callers that need an exhaustive
 * list (e.g., populating a fine-tuning dataset dropdown).
 */
export const getAllDatasets = (
  projectId: string,
  options: Pick<ListDatasetsQuery, 'type' | 'name'> = {},
): Promise<DatasetResponse[]> =>
  fetchAllPages<DatasetResponse>((page, pageSize) =>
    listDatasets(projectId, { ...options, page, pageSize }),
  );

/**
 * Retrieves a single dataset by ID.
 *
 * @param {string} id - The dataset ID
 * @param {string} projectId - The active project ID
 * @throws {APIRequestError} If the API request fails.
 */
export const getDataset = async (id: string, projectId: string) => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/datasets/{dataset_id}',
    { params: { path: { project: projectId, dataset_id: id } } },
  );

  if (error || !data) {
    throw new APIRequestError(
      `Failed to get dataset: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }

  return data;
};

export const deleteDataset = async (
  id: string,
  projectId: string,
): Promise<void> => {
  const { error, response } = await apiClient.DELETE(
    '/api/projects/{project}/datasets/{dataset_id}',
    { params: { path: { project: projectId, dataset_id: id } } },
  );
  if (!response.ok) {
    throw new APIRequestError(
      `Failed to delete dataset ${id}: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
};

export interface DeleteDatasetsResult {
  succeededIds: string[];
  failed: Array<{ id: string; error: APIRequestError | Error }>;
}

export const deleteDatasets = async (
  ids: string[],
  projectId: string,
): Promise<DeleteDatasetsResult> => {
  const results = await Promise.allSettled(
    ids.map((id) => deleteDataset(id, projectId)),
  );
  const succeededIds: string[] = [];
  const failed: DeleteDatasetsResult['failed'] = [];
  results.forEach((result, idx) => {
    const id = ids[idx];
    if (result.status === 'fulfilled') {
      succeededIds.push(id);
    } else {
      failed.push({ id, error: result.reason });
    }
  });
  return { succeededIds, failed };
};

export const downloadDatasetById = async (id: string, projectId: string) => {
  const response = await fetch(
    `/api/projects/${projectId}/datasets/${id}/download`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    },
  );
  if (!response.ok) {
    const errorMessage = await getErrorMessage(response);
    throw new APIRequestError(
      `Failed to download dataset: ${errorMessage}`,
      response.status,
    );
  }
  const blob = await response.blob();

  const disposition = response.headers.get('Content-Disposition');
  let filename = `dataset-${id}.jsonl`;

  if (disposition) {
    const match = disposition.match(/filename="?([^"]+)"?/);
    if (match?.[1]) filename = match[1];
  }
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
};

export const uploadDataset = async (
  name: string,
  description: string,
  type: DatasetType,
  dataset: File,
  projectId: string,
) => {
  const formData = new FormData();

  formData.append('name', name);
  formData.append('description', description);
  formData.append('jsonl', dataset);
  formData.append('type', type);

  const response = await fetch(`/api/projects/${projectId}/datasets`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorMessage = await getErrorMessage(response);
    throw new APIRequestError(
      `Failed to upload datasets: ${errorMessage}`,
      response.status,
    );
  }
  return await response.json();
};
