// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';
import type { components, operations } from '@/types/api';
import {
  ARTIFACT_DESCRIPTION_ANNOTATION,
  type LoraAdapter,
  SUBMITTER_ANNOTATION,
} from '@/types/artifacts';
import { AIM_DISPLAY_NAME_ANNOTATION } from '@/types/aims';

import { fetchAllPages } from './pagination';

/** Matches the paginated loader's bound so a single view can't burst the API. */
const ADAPTER_LOOKUP_CONCURRENCY = 4;

type ArtifactResponse = components['schemas']['ArtifactResponse'];
type ListArtifactsQuery = NonNullable<
  operations['list_artifacts_endpoint_v1_projects__project__artifacts_get']['parameters']['query']
>;

const toLoraAdapter = (item: ArtifactResponse): LoraAdapter => {
  const { metadata, spec, status } = item.artifact;
  const annotations = metadata.annotations ?? {};
  return {
    id: metadata.uid ?? metadata.name,
    name: metadata.name,
    displayName: annotations[AIM_DISPLAY_NAME_ANNOTATION] ?? metadata.name,
    description: annotations[ARTIFACT_DESCRIPTION_ANNOTATION],
    modelId: spec?.modelId,
    compatibleWith: spec?.compatibleWith ?? [],
    rank: spec?.rank,
    status: status?.status,
    readiness: item.storage.readiness,
    uri: item.storage.uri,
    createdAt: metadata.creationTimestamp,
    createdBy: annotations[SUBMITTER_ANNOTATION],
    servable: item.servable,
  };
};

export const listAdapterArtifacts = async (
  projectId: string,
  options: Pick<ListArtifactsQuery, 'page' | 'pageSize' | 'servableBy'> = {},
): Promise<{
  pagination: components['schemas']['PaginationMetadata'];
  data: LoraAdapter[];
}> => {
  const { page = 1, pageSize = 10, servableBy } = options;
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/artifacts',
    {
      params: {
        path: { project: projectId },
        query: { page, pageSize, type: ['adapter'], servableBy },
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to list adapters: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return {
    pagination: data.pagination,
    data: data.data.map(toLoraAdapter),
  };
};

export const listAllAdapterArtifacts = (
  projectId: string,
  /** Deployment whose resolved profile decides `servable` on each row. */
  servableBy?: string,
): Promise<LoraAdapter[]> =>
  fetchAllPages<LoraAdapter>((page, pageSize) =>
    listAdapterArtifacts(projectId, { page, pageSize, servableBy }),
  );

export const getAdapterArtifact = async (
  projectId: string,
  name: string,
): Promise<ArtifactResponse> => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/artifacts/{name}',
    { params: { path: { project: projectId, name } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to get adapter: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

export const getAdapterArtifacts = async (
  projectId: string,
  names: string[],
): Promise<LoraAdapter[]> => {
  const adapters: LoraAdapter[] = [];
  // A deployment may serve up to MAX_LORA_ADAPTERS adapters, so the by-name
  // lookups run in bounded batches rather than as one burst — same reasoning
  // (and bound) as the paginated loader in ./pagination.
  for (
    let batchStart = 0;
    batchStart < names.length;
    batchStart += ADAPTER_LOOKUP_CONCURRENCY
  ) {
    const batch = names.slice(
      batchStart,
      batchStart + ADAPTER_LOOKUP_CONCURRENCY,
    );
    const results = await Promise.allSettled(
      batch.map((name) => getAdapterArtifact(projectId, name)),
    );
    for (const result of results) {
      if (result.status === 'fulfilled') {
        adapters.push(toLoraAdapter(result.value));
        continue;
      }
      // A 404 means the adapter is genuinely gone from the project, so
      // dropping it reflects reality. Any other failure (network blip, 5xx) is
      // transient and must not be mistaken for removal — surfacing it lets the
      // query report an error and retry instead of silently hiding a
      // still-attached adapter.
      const error = result.reason;
      if (error instanceof APIRequestError && error.statusCode === 404) {
        continue;
      }
      throw error;
    }
  }
  return adapters;
};

export const deleteAdapterArtifact = async (
  projectId: string,
  name: string,
): Promise<void> => {
  const { error, response } = await apiClient.DELETE(
    '/api/projects/{project}/artifacts/{name}',
    { params: { path: { project: projectId, name }, query: {} } },
  );
  if (!response.ok) {
    throw new APIRequestError(
      getApiClientErrorMessage(error, response),
      response.status,
    );
  }
};

const ARTIFACT_REMOVAL_POLL_INTERVAL_MS = 500;
const ARTIFACT_REMOVAL_POLL_ATTEMPTS = 10;

/**
 * Waits for an adapter deleted via {@link deleteAdapterArtifact} to actually
 * disappear. The delete endpoint returns 202 once removal of the underlying
 * AIMArtifact CR is accepted, not once it has finished, so a caller that
 * refetches the adapter list immediately after can still see the artifact
 * briefly. Resolves silently if the artifact still exists once polling
 * attempts are exhausted, leaving reconciliation to the caller's own refresh.
 */
export const waitForAdapterArtifactRemoval = async (
  projectId: string,
  name: string,
): Promise<void> => {
  for (
    let attempt = 0;
    attempt < ARTIFACT_REMOVAL_POLL_ATTEMPTS;
    attempt += 1
  ) {
    try {
      await getAdapterArtifact(projectId, name);
    } catch (error) {
      if (error instanceof APIRequestError && error.statusCode === 404) {
        return;
      }
      throw error;
    }
    await new Promise((resolve) =>
      setTimeout(resolve, ARTIFACT_REMOVAL_POLL_INTERVAL_MS),
    );
  }
};
