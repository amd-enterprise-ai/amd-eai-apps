// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError, getErrorMessage } from '@amdenterpriseai/utils/app';
import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';

import type { components } from '@/types/api';
import {
  MODEL_SOURCE_TYPE,
  type ModelOnboardingStatusResponse,
  type ModelSourceType,
} from '@/types/model-import';

type PreviewRequest = components['schemas']['PreviewRequest'];
type PreviewResponse = components['schemas']['PreviewResponse'];
type OnboardRequest = components['schemas']['OnboardRequest'];

/** Credential fields an onboard request carries for its source family. */
type OnboardSourceFields = Pick<
  OnboardRequest,
  'sourceType' | 'hfTokenSecretName' | 's3StorageName'
>;

/** Step 1 inputs, before either source family's fields have been selected. */
export interface ModelSourceSelection {
  sourceType: ModelSourceType;
  source: string;
  hfTokenSecretName?: string;
  s3StorageName?: string;
}

function parseJsonEnvelope<T>(json: unknown): T {
  if (json && typeof json === 'object' && 'data' in json) {
    return (json as { data: T }).data;
  }
  return json as T;
}

/**
 * Whether a string is an S3 URI the backend will accept as a model source.
 *
 * A prefix is mandatory: `s3://bucket` alone would make preview scan an entire
 * bucket, so the backend rejects it and the wizard blocks it up front.
 */
export function isValidS3Uri(source: string): boolean {
  const match = /^s3:\/\/([^/\s]+)\/(.+)$/.exec(source.trim());
  return Boolean(match && match[2].replace(/\/+$/, '').length > 0);
}

/**
 * Picks the credential field belonging to the selected source family.
 *
 * The backend rejects a request carrying the other family's credential, so the
 * unused field is omitted rather than sent empty.
 */
export function buildOnboardSourceFields({
  sourceType,
  hfTokenSecretName,
  s3StorageName,
}: ModelSourceSelection): OnboardSourceFields {
  if (sourceType === MODEL_SOURCE_TYPE.S3) {
    const storage = s3StorageName?.trim();
    return { sourceType, ...(storage ? { s3StorageName: storage } : {}) };
  }
  const token = hfTokenSecretName?.trim();
  return { sourceType, ...(token ? { hfTokenSecretName: token } : {}) };
}

/** Assembles the preview payload for the selected source family. */
export function buildPreviewRequest(
  selection: ModelSourceSelection,
): PreviewRequest {
  return {
    ...buildOnboardSourceFields(selection),
    source: selection.source.trim(),
  };
}

/**
 * Resolves a Hugging Face reference into metadata and candidate weight files.
 *
 * Calls the BFF at `POST /api/projects/{project}/models/preview`, which
 * proxies to the upstream AIWB endpoint
 * `POST /v1/projects/{project_name}/models/preview`.
 */
export async function previewModelSource(
  projectName: string,
  body: PreviewRequest,
): Promise<PreviewResponse> {
  if (!projectName.trim()) {
    throw new APIRequestError('No project selected', 422);
  }
  if (!body.source?.trim()) {
    throw new APIRequestError('Model source is required', 422);
  }
  if (body.sourceType === MODEL_SOURCE_TYPE.S3 && !body.s3StorageName?.trim()) {
    throw new APIRequestError('An S3 storage is required for S3 sources', 422);
  }
  const { data, error, response } = await apiClient.POST(
    '/api/projects/{project}/models/preview',
    { params: { path: { project: projectName } }, body },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to preview model source: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
}

/**
 * Persists a previewed Hugging Face source with the selected runtime profile.
 *
 * Calls the BFF at `POST /api/projects/{project}/models/onboard`, which
 * proxies to the upstream AIWB endpoint
 * `POST /v1/projects/{project_name}/models/onboard`. The upstream endpoint
 * responds with 204 No Content on success, so there is no body to return.
 */
export async function onboardModel(
  projectName: string,
  body: OnboardRequest,
): Promise<void> {
  if (!projectName.trim()) {
    throw new APIRequestError('No project selected', 422);
  }
  if (!body.repoId?.trim()) {
    throw new APIRequestError('Model repo id is required', 422);
  }
  if (!body.revision?.trim()) {
    throw new APIRequestError('Model revision is required', 422);
  }
  if (!body.sha?.trim()) {
    throw new APIRequestError('Model sha is required', 422);
  }
  if (!body.displayName?.trim()) {
    throw new APIRequestError('Model display name is required', 422);
  }
  if (!body.image?.trim()) {
    throw new APIRequestError('Container image is required', 422);
  }
  if (body.sourceType === MODEL_SOURCE_TYPE.S3 && !body.s3StorageName?.trim()) {
    throw new APIRequestError('An S3 storage is required for S3 sources', 422);
  }
  const { error, response } = await apiClient.POST(
    '/api/projects/{project}/models/onboard',
    { params: { path: { project: projectName } }, body },
  );
  if (!response.ok) {
    throw new APIRequestError(
      `Failed to start model onboarding: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
}

/**
 * Polls onboarding progress for a model created via {@link onboardModel}.
 *
 * Calls the BFF at `GET /api/projects/{project}/models/{modelId}/onboarding`,
 * which proxies to the upstream AIWB endpoint
 * `GET /v1/projects/{project_name}/models/{model_id}/onboarding`.
 */
export async function getModelOnboardingStatus(
  projectName: string,
  modelId: string,
): Promise<ModelOnboardingStatusResponse> {
  if (!projectName.trim()) {
    throw new APIRequestError('No project selected', 422);
  }
  if (!modelId.trim()) {
    throw new APIRequestError('Model id is required', 422);
  }
  const response = await fetch(
    `/api/projects/${encodeURIComponent(projectName)}/models/${encodeURIComponent(modelId)}/onboarding`,
  );
  if (!response.ok) {
    const errorMessage = await getErrorMessage(response);
    throw new APIRequestError(
      `Failed to fetch model onboarding status: ${errorMessage}`,
      response.status,
    );
  }
  const json: unknown = await response.json();
  return parseJsonEnvelope<ModelOnboardingStatusResponse>(json);
}
