// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';
import { FinetunableModel, ModelFinetuneParams } from '@/types/models';
import type { components } from '@/types/api';

import { fetchAllPages } from './pagination';

/** AIMModel CRD resource as returned by the fine-tuning list/read endpoints. */
type AIMModelResource = components['schemas']['AIMModelResource'];

/**
 * Retrieves a list of models that can be fine-tuned.
 *
 * @returns {Promise<FinetunableModel[]>} A promise that resolves to an array of finetunable model objects.
 * @throws {APIRequestError} If the API request fails.
 */
export const getFinetunableModels = async (): Promise<FinetunableModel[]> => {
  const { data, error, response } = await apiClient.GET(
    '/api/fine-tuning/models',
  );

  if (error || !data) {
    throw new APIRequestError(
      `Failed to get finetunable models: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }

  return (data.data ?? []).map((model) => ({
    canonicalName: model.canonicalName,
    gpuCount: model.gpuCount ?? null,
    compatibleAccelerators: model.compatibleAccelerators ?? [],
    compatibleAcceleratorNames: model.compatibleAcceleratorNames ?? [],
    hfTokenRequired: model.hfTokenRequired,
    trainingType: model.trainingType,
    hyperparameters: model.hyperparameters,
  }));
};

// TODO: replace load-all UI consumers with server-side
// paginated tables; until then `listAllProjectFineTunedModels` walks
// every page via the shared fetchAllPages utility.

/**
 * Fetches a single page of fine-tuned models for a project.
 *
 * Backed by GET /v1/projects/{project}/fine-tuning/models. Returns the raw
 * paginated envelope so callers can drive UI pagination.
 *
 * @param {string} projectId - The project (1:1 with namespace) to list in.
 * @param {object} [options] - Optional pagination controls.
 * @returns The requested page and pagination metadata.
 * @throws {APIRequestError} If the API request fails.
 */
export const listProjectFineTunedModels = async (
  projectId: string,
  options: { page?: number; pageSize?: number } = {},
): Promise<components['schemas']['FineTuningModelsList']> => {
  if (!projectId) {
    throw new APIRequestError('No project selected', 422);
  }
  const { page = 1, pageSize = 10 } = options;
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/fine-tuning/models',
    {
      params: {
        path: { project: projectId },
        query: { page, pageSize },
      },
    },
  );

  if (error || !data) {
    throw new APIRequestError(
      `Failed to get fine-tuned models: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }

  return data;
};

/**
 * Lists every fine-tuned model in a project by walking all pages.
 *
 * Thin wrapper around fetchAllPages. Returns `[]` on any failure so callers
 * (joins against deployments / workloads) can render empty state
 * without an error boundary — matches `listAllInferenceDeployments`.
 *
 * Note: this is a philosophical shift from the previous `getProjectFineTunedModels`
 * stop-gap, which deliberately re-threw on failure to drive React Query error
 * states. Consumers that still need that behavior should switch to
 * `listProjectFineTunedModels` and handle the error themselves.
 *
 * @param {string} projectId - The project (1:1 with namespace) to list in.
 * @returns {Promise<AIMModelResource[]>} All fine-tuned models in the project.
 */
export const listAllProjectFineTunedModels = async (
  projectId: string,
): Promise<AIMModelResource[]> => {
  try {
    return await fetchAllPages<AIMModelResource>((page, pageSize) =>
      listProjectFineTunedModels(projectId, { page, pageSize }),
    );
  } catch (error) {
    console.warn('Error fetching fine-tuned models:', error);
    return [];
  }
};

type FineTuningJobRequest = components['schemas']['FineTuningJobRequest'];

// `output` is the only field the generated type marks as required:
// openapi-typescript's --default-non-nullable treats a nullable field with a
// non-null default as non-optional, and `output` defaults to `"model"`. The
// backend's actual OpenAPI `required` list omits it, so widen it back to
// optional and the request body can leave it out. The three hyperparameters and
// `lora` all default to null, so they stay optional without any widening.
type FineTuningJobRequestBody = Omit<FineTuningJobRequest, 'output'> &
  Partial<Pick<FineTuningJobRequest, 'output'>>;

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

export const finetuneModel = async (
  baseModelId: string,
  params: ModelFinetuneParams,
  projectId: string,
) => {
  const { data, error, response } = await apiClient.POST(
    '/api/projects/{project}/fine-tuning/jobs',
    {
      params: { path: { project: projectId } },
      body: {
        baseModel: baseModelId,
        displayName: params.displayName,
        datasetIds: params.datasetIds,
        ...(params.description ? { description: params.description } : {}),
        // Omit untouched Advanced Settings entirely rather than sending null,
        // so the run trains with the base model recipe's own values, exactly as
        // it would for any other caller that never sends the key.
        ...(isFiniteNumber(params.epochs) ? { epochs: params.epochs } : {}),
        ...(isFiniteNumber(params.learningRate)
          ? { learningRate: params.learningRate }
          : {}),
        ...(isFiniteNumber(params.batchSize)
          ? { batchSize: params.batchSize }
          : {}),
        ...(params.hfTokenSecretName
          ? { hfTokenSecretName: params.hfTokenSecretName }
          : {}),
        ...(params.output ? { output: params.output } : {}),
        ...(params.lora
          ? {
              lora: {
                ...params.lora,
              },
            }
          : {}),
      } satisfies FineTuningJobRequestBody as FineTuningJobRequest,
    },
  );

  if (error || !data) {
    throw new APIRequestError(
      `Failed to finetune model: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }

  return data;
};

/**
 * Cancels an in-progress fine-tuning job.
 *
 * @param jobId - Workload UUID of the fine-tuning job.
 * @param projectId - The project / namespace.
 * @throws {APIRequestError} If the API request fails.
 */
export const cancelFineTuningJob = async (
  jobId: string,
  projectId: string,
): Promise<void> => {
  const { error, response } = await apiClient.DELETE(
    '/api/projects/{project}/fine-tuning/jobs/{job_id}',
    { params: { path: { project: projectId, job_id: jobId } } },
  );

  if (error) {
    throw new APIRequestError(
      `Failed to cancel fine-tuning job: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
};

export const deleteModel = async (
  name: string,
  projectId: string,
  force?: boolean,
) => {
  const { error, response } = await apiClient.DELETE(
    '/api/projects/{project}/fine-tuning/models/{model_id}',
    {
      params: {
        path: { project: projectId, model_id: name },
        ...(force ? { query: { force: true } } : {}),
      },
    },
  );

  if (error) {
    throw new APIRequestError(
      `Failed to delete model: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  // 204 No Content — no body to parse
};
