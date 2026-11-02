// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError } from '@amdenterpriseai/utils/app';
import type { QueryClient } from '@tanstack/react-query';

import {
  AIMClusterModel,
  AIMDeployPayload,
  AIMService,
  AIMServiceStatus,
  AIMStatus,
  AutoscalingPolicyConfig,
  ParsedAIM,
} from '@/types/aims';
import type { components, operations } from '@/types/api';

import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';
import { aimParser } from './aims';
import { fetchAllPages } from './pagination';

type ListInferenceDeploymentsQuery = NonNullable<
  operations['list_inference_deployments_endpoint_v1_projects__project__inference_get']['parameters']['query']
>;

type InferencePatchRequest = components['schemas']['InferencePatchRequest'];

/**
 * Refreshes deployment data after an adapter attachment or replacement.
 *
 * Covers both the project-scoped deployment lists and the deployment-details
 * query the AIM details page owns: that query disables `refetchOnMount`, so
 * without an explicit invalidation it keeps serving the pre-attach adapter
 * list for the lifetime of its cache entry.
 */
export const invalidateAdapterQueries = async (
  queryClient: QueryClient,
  project: string,
): Promise<void> => {
  await Promise.all([
    queryClient.invalidateQueries({
      queryKey: ['project', project, 'inference'],
    }),
    queryClient.invalidateQueries({ queryKey: ['aimService', project] }),
  ]);
};

type UpdateScalingPolicyPayload = {
  [Key in 'minReplicas' | 'maxReplicas']-?: NonNullable<
    InferencePatchRequest[Key]
  >;
} & {
  autoScaling: AutoscalingPolicyConfig;
};

/**
 * Gets a single base inference model from the cluster catalog by resource name.
 *
 * Backed by GET /v1/inference/models/{name}.
 *
 * @param {string} name - AIMClusterModel metadata.name.
 * @returns {Promise<AIMClusterModel>} The model resource.
 * @throws {APIRequestError} If the API request fails or the name is missing.
 */
export const getInferenceModel = async (
  name: string,
): Promise<AIMClusterModel> => {
  if (!name) {
    throw new APIRequestError('No inference model name provided', 422);
  }

  const { data, error, response } = await apiClient.GET(
    '/api/inference/models/{name}',
    { params: { path: { name } } },
  );

  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch inference model: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }

  return data;
};

/**
 * Fetches a single page of inference base models from the cluster catalog.
 *
 * Backed by GET /v1/inference/models. Returns the raw paginated envelope so
 * callers can drive UI pagination. `statusFilter` narrows the result set
 * server-side.
 *
 * @param {object} [options] - Optional filters and pagination controls.
 * @returns The requested page and pagination metadata.
 * @throws {APIRequestError} If the API request fails.
 */
export const listInferenceModels = async (
  options: {
    page?: number;
    pageSize?: number;
    statusFilter?: AIMStatus[];
  } = {},
): Promise<components['schemas']['InferenceModelsList']> => {
  const { page = 1, pageSize = 10, statusFilter } = options;
  const { data, error, response } = await apiClient.GET(
    '/api/inference/models',
    { params: { query: { page, pageSize, statusFilter } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch inference models: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

/**
 * Lists every inference base model in the cluster catalog by walking all pages.
 *
 * Thin wrapper around fetchAllPages. Returns `[]` on any failure so callers can
 * render an empty state without an error boundary.
 *
 * @param {AIMStatus[]} [statusFilter] - Optional model statuses to filter by.
 * @returns {Promise<AIMClusterModel[]>} All base models matching the filter.
 */
export const listAllInferenceModels = async (
  statusFilter?: AIMStatus[],
): Promise<AIMClusterModel[]> => {
  try {
    return await fetchAllPages<AIMClusterModel>((page, pageSize) =>
      listInferenceModels({ page, pageSize, statusFilter }),
    );
  } catch (error) {
    console.warn('Error fetching inference models:', error);
    return [];
  }
};

/**
 * Deploys a model for inference in the given project.
 *
 * Backed by POST /v1/projects/{project}/inference. The `model` field accepts
 * either a cluster-scoped AIMClusterModel name or a project-scoped fine-tuned
 * AIMModel name; the backend auto-detects.
 *
 * @param {string} project - The project (1:1 with namespace) to deploy in.
 * @param {AIMDeployPayload} payload - Deployment configuration.
 * @returns {Promise<AIMService>} The accepted deployment.
 * @throws {APIRequestError} If the API request fails or the project is missing.
 */
export const deployInference = async (
  project: string,
  payload: AIMDeployPayload,
): Promise<AIMService> => {
  if (!project) {
    throw new APIRequestError('No project selected', 422);
  }

  const { data, error, response } = await apiClient.POST(
    '/api/projects/{project}/inference',
    { params: { path: { project } }, body: payload },
  );

  if (error || !data) {
    throw new APIRequestError(
      `Failed to deploy inference: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }

  return data;
};

/**
 * Fetches a single page of inference deployments for a project.
 *
 * Backed by GET /v1/projects/{project}/inference. Returns the raw paginated
 * envelope so callers can drive UI pagination. `capability=chat` narrows the
 * list to deployments whose serving stack is fully ready AND whose model is
 * chat-capable. `statusFilter` further restricts by deployment status and is
 * sent as a repeated `statusFilter` query parameter.
 *
 * @param {string} project - The project (1:1 with namespace) to list in.
 * @param {object} [options] - Optional capability/status filters and pagination controls.
 * @returns The requested page and pagination metadata.
 * @throws {APIRequestError} If the API request fails.
 */
export const listInferenceDeployments = async (
  project: string,
  options: ListInferenceDeploymentsQuery = {},
): Promise<components['schemas']['InferenceDeploymentsList']> => {
  const { page = 1, pageSize = 10, ...filters } = options;
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/inference',
    {
      params: {
        path: { project },
        query: { page, pageSize, ...filters },
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch inference deployments: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

/**
 * Lists every inference deployment for a project by walking all pages.
 *
 * Thin wrapper around fetchAllPages. Returns `[]` on any failure so callers can
 * render an empty state without an error boundary.
 *
 * @param {string} project - The project (1:1 with namespace) to list in.
 * @param {object} [options] - Optional capability and status filters.
 * @returns {Promise<AIMService[]>} All inference deployments matching the filters.
 */
export const listAllInferenceDeployments = async (
  project: string,
  options: Partial<
    Pick<ListInferenceDeploymentsQuery, 'capability' | 'statusFilter'>
  > = {},
): Promise<AIMService[]> => {
  try {
    return await fetchAllPages<AIMService>((page, pageSize) =>
      listInferenceDeployments(project, { ...options, page, pageSize }),
    );
  } catch (error) {
    console.warn('Error fetching inference deployments:', error);
    return [];
  }
};

/**
 * Gets a single inference deployment by ID.
 *
 * Backed by GET /v1/projects/{project}/inference/{id}.
 *
 * @param {string} project - The project (1:1 with namespace).
 * @param {string} id - The UUID of the inference deployment.
 * @returns {Promise<AIMService>} The deployment.
 * @throws {APIRequestError} If the API request fails.
 */
export const getInferenceDeployment = async (
  project: string,
  id: string,
): Promise<AIMService> => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/inference/{id}',
    { params: { path: { project, id } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch inference deployment: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
};

/**
 * Lists per-pod replica info for an inference deployment.
 *
 * Backed by GET /v1/projects/{project}/inference/{id}/replicas. Returns a
 * subset of Kubernetes pod fields (name, phase, IP, containers, resource
 * limits, conditions) for each replica that is currently running.
 *
 * @param {string} project - The project (1:1 with namespace).
 * @param {string} id - The UUID of the inference deployment.
 * @returns {Promise<components['schemas']['InferenceReplicaResponse'][]>} List of per-pod replica info.
 * @throws {APIRequestError} If the API request fails.
 */
export const getInferenceReplicas = async (
  project: string,
  id: string,
): Promise<components['schemas']['InferenceReplicaResponse'][]> => {
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/inference/{id}/replicas',
    { params: { path: { project, id } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch inference replicas: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data.data ?? [];
};

/**
 * Updates the scaling policy of an inference deployment.
 *
 * Backed by PATCH /v1/projects/{project}/inference/{id}. All three scaling
 * fields (`minReplicas`, `maxReplicas`, `autoScaling`) must be provided
 * together — the backend rejects partial updates with HTTP 400.
 *
 * @param {string} project - The project (1:1 with namespace).
 * @param {string} id - The UUID of the inference deployment.
 * @param {UpdateScalingPolicyPayload} payload - Full scaling policy to apply.
 * @throws {APIRequestError} If the API request fails.
 */
export const updateInferenceScaling = async (
  project: string,
  id: string,
  payload: UpdateScalingPolicyPayload,
): Promise<void> => {
  const { error, response } = await apiClient.PATCH(
    '/api/projects/{project}/inference/{id}',
    { params: { path: { project, id } }, body: payload },
  );
  if (error) {
    throw new APIRequestError(
      `Failed to update inference scaling: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
};

/** Replaces the complete adapter set served by a dynamic deployment. */
export const updateInferenceAdapters = async (
  project: string,
  id: string,
  adapters: string[],
): Promise<void> => {
  const { error, response } = await apiClient.PATCH(
    '/api/projects/{project}/inference/{id}',
    {
      params: { path: { project, id } },
      body: { adapters },
    },
  );
  if (!response.ok) {
    throw new APIRequestError(
      `Failed to update inference adapters: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
};

/** Attaches an adapter without removing adapters already on the deployment. */
export const attachAdapterToDeployment = async (
  project: string,
  deployment: AIMService,
  adapterName: string,
): Promise<void> => {
  if (!deployment.id) {
    throw new APIRequestError('No inference deployment ID provided', 422);
  }

  // TODO: this read-then-replace can drop a concurrent attach made
  // between the read and the PATCH; revisit once the API supports merging.
  const latestDeployment = await getInferenceDeployment(project, deployment.id);
  const existingAdapters =
    latestDeployment.spec?.adapters?.map((adapter) => adapter.name) ?? [];
  const adapters = Array.from(new Set([...existingAdapters, adapterName]));
  await updateInferenceAdapters(project, deployment.id, adapters);
};

/**
 * Undeploys an inference deployment.
 *
 * Backed by DELETE /v1/projects/{project}/inference/{id}.
 *
 * @param {string} project - The project (1:1 with namespace).
 * @param {string} id - The UUID of the inference deployment to undeploy.
 * @throws {APIRequestError} If the API request fails or arguments are missing.
 */
export const deleteInferenceDeployment = async (
  project: string,
  id: string,
): Promise<void> => {
  if (!project) {
    throw new APIRequestError('No project provided', 422);
  }
  if (!id) {
    throw new APIRequestError('No deployment ID provided', 422);
  }
  const { error, response } = await apiClient.DELETE(
    '/api/projects/{project}/inference/{id}',
    { params: { path: { project, id } } },
  );
  if (error) {
    throw new APIRequestError(
      `Failed to undeploy inference deployment: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
};

/**
 * Fetches the cluster's inference model catalog joined with project-scoped
 * deployment status.
 *
 * Composes two backend calls — GET /v1/inference/models for the cluster catalog
 * (with optional server-side `statusFilter`) and GET /v1/projects/{project}/inference
 * for that project's deployments — then groups deployments per AIMClusterModel
 * via `spec.model.name` (the AIMClusterModel resource name AIWB sets at deploy
 * time; the backend backfills it from `status.resolvedModel.name` for legacy
 * v1alpha1 deploy-by-image services so consumers can always read it directly).
 *
 * @param {string} project - The project (1:1 with namespace) to check for deployed services.
 * @param {AIMStatus[]} statuses - Optional list of model statuses to filter by (server-side).
 * @returns {Promise<ParsedAIM[]>} The parsed models with deployment status.
 */
export const getInferenceCatalog = async (
  project?: string,
  statuses?: AIMStatus[],
): Promise<ParsedAIM[]> => {
  const aims = await listAllInferenceModels(statuses);
  const services = project ? await listAllInferenceDeployments(project) : [];

  const servicesByAimRef = new Map<string, AIMService[]>();
  services.forEach((service) => {
    const key = service.spec?.model?.name;
    if (!key) return;
    const existing = servicesByAimRef.get(key) ?? [];
    servicesByAimRef.set(key, [...existing, service]);
  });

  return aims.map((aim) => {
    const deployedServices = servicesByAimRef.get(aim.metadata.name);
    return aimParser(aim, deployedServices);
  });
};
