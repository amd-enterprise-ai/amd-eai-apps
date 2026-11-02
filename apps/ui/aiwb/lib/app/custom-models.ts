// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError } from '@amdenterpriseai/utils/app';
import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';

import {
  AggregatedAIM,
  AIMWorkloadStatus,
  OnboardPhase,
  ParsedAIM,
} from '@/types/aims';
import type { components } from '@/types/api';
import type { Model } from '@/types/models';

type CustomModelResponse = components['schemas']['CustomModelResponse'];
type CustomProfileResponse = components['schemas']['CustomProfileResponse'];
type CustomModelPatchRequest = components['schemas']['CustomModelPatchRequest'];
type RuntimeProfileOptions = components['schemas']['RuntimeProfileOptions'];
type RuntimeProfileCombination =
  components['schemas']['RuntimeProfileCombination'];
export type BaseImageRuntimeProfileOptions = {
  imageRepository: string;
  imageTag: string;
  acceleratorTypes: string[];
  acceleratorModels: string[];
  acceleratorCountsByModel: Record<string, number[]>;
  precisionsByModel: Record<string, string[]>;
  metricsByModel: Record<string, string[]>;
  optimizationClassesByModel: Record<string, string[]>;
  /**
   * The four-axis tuples the base image actually emits. The per-model lists say
   * which values exist but not which coexist; consumers narrow their
   * count/precision/metric selectors to these combinations so the form cannot
   * assemble a tuple the base never emits.
   */
  combinations: RuntimeProfileCombination[];
  /**
   * Whether the image discovered any runtime profiles. Distinguishes an empty
   * `combinations` that means 'not ready' (false) from 'profiles exist but none
   * resolvable' (true), where the client blocks the save instead of falling back.
   */
  profilesAvailable: boolean;
};

/**
 * The AIM version a deploy of this custom model targets, and the model shape the
 * deploy drawer takes. Latest official ready release, else any ready version,
 * else the first known one, matching what the catalog drawer defaults to.
 * `ParsedAIM.model` is the AIMModel resource name the deploy request is keyed on.
 */
export function customModelDeployTarget(
  aggregated: AggregatedAIM,
): { aim: ParsedAIM; model: Model } | null {
  const aim =
    aggregated.latestAim ??
    aggregated.parsedAIMs.find((entry) => entry.status === 'Ready') ??
    aggregated.parsedAIMs[0];
  if (!aim) {
    return null;
  }
  return {
    aim,
    model: {
      name: aim.title,
      canonicalName: aim.canonicalName,
      resourceName: aim.model,
    },
  };
}

/** Thrown when DELETE custom model returns 409; carries blocking AIMService names when the API provides them. */
export class CustomModelDeleteConflictError extends APIRequestError {
  readonly blockingServices: string[];

  constructor(message: string, blockingServices: string[]) {
    super(message, 409);
    this.name = 'CustomModelDeleteConflictError';
    this.blockingServices = blockingServices;
  }
}

// Annotation keys stamped by the backend onboarding flow.
// Must stay in sync with apps/api/aiwb/app/custom_models/constants.py.
const MODEL_DISPLAY_NAME_ANNOTATION =
  'aiwb.apps.eai.amd.com/model-display-name';
const CANONICAL_REPO_ID_ANNOTATION = 'aiwb.apps.eai.amd.com/canonical-repo-id';
const SOURCE_DESCRIPTION_ANNOTATION =
  'aiwb.apps.eai.amd.com/source-description';
const SOURCE_TAGS_ANNOTATION = 'aiwb.apps.eai.amd.com/source-tags';
const REVISION_ANNOTATION = 'airm.silogen.ai/revision';
// Durable store for the onboard-chosen runtime precision. The AIMModel CRD
// prunes spec.profiles.overrides.precision, so the backend records it here.
const MODEL_PRECISION_ANNOTATION = 'aiwb.apps.eai.amd.com/precision';

function parseTags(raw: string | undefined): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/**
 * Extracts the organisation name from a HuggingFace repo ID.
 *
 * e.g. "meta-llama/Llama-3.2-1B-Instruct" → "meta-llama"
 */
function extractOrgName(repoId: string): string {
  return repoId.split('/')[0] ?? repoId;
}

/**
 * Maps a single CustomModel API response to an AggregatedAIM so the existing
 * CustomModelCard component can render it without changes.
 *
 * Each custom model CR is its own family (one version per card). The repository
 * key is the CR metadata name so cards remain stable across refreshes.
 */
export function customModelToAggregatedAIM(
  model: CustomModelResponse,
): AggregatedAIM {
  const annotations = model.metadata.annotations ?? {};

  const displayName =
    annotations[MODEL_DISPLAY_NAME_ANNOTATION] ?? model.metadata.name;
  const canonicalName =
    annotations[CANONICAL_REPO_ID_ANNOTATION] ?? model.metadata.name;
  const description = annotations[SOURCE_DESCRIPTION_ANNOTATION] ?? '';
  const tags = parseTags(annotations[SOURCE_TAGS_ANNOTATION]);
  // Revision label stamped at onboard time (e.g. "main" or a branch name).
  const revision = annotations[REVISION_ANNOTATION] ?? '';
  // Onboard-chosen precision (survives on an annotation because the CRD prunes
  // it from overrides); seeds the deploy drawer's precision default.
  const preferredPrecision =
    annotations[MODEL_PRECISION_ANNOTATION] || undefined;

  // For v1alpha2 onboarded models, image and weight sources live under
  // spec.profiles.overrides rather than the top-level spec fields.
  const overrides = model.spec?.profiles?.overrides;
  const firstSource = overrides?.modelSources?.[0];
  const imageReference = overrides?.image ?? model.spec?.image ?? '';
  const sourceUri = firstSource?.sourceUri ?? undefined;
  // HF token is wired as a per-source env entry during onboarding; its
  // presence signals that the model requires a token to download weights.
  const isHfTokenRequired = (firstSource?.env ?? []).some(
    (e: { name?: string | null }) => e.name === 'HF_TOKEN',
  );

  const status = model.phase?.status ?? '';
  // Deployability keys off the composed lifecycle state, not templateReady. An
  // AIMProfile (templateReady) derives from the base image and can exist while
  // the weight import is still running or has failed, so templateReady is true
  // even when the model has no usable weights. Only state==='Ready' means the
  // model is actually deployable.
  const isReady = model.phase?.state === OnboardPhase.READY;

  const parsedAIM: ParsedAIM = {
    model: model.metadata.name,
    aimId: model.spec?.aimId ?? null,
    imageReference,
    annotations,
    description: { short: description, full: description },
    title: displayName,
    imageVersion: revision,
    canonicalName,
    tags,
    status,
    workloadStatuses: [],
    isPreview: false,
    isHfTokenRequired,
    isCustomImport: true,
    sourceUri,
  };

  const zeroDeploymentCounts = Object.fromEntries(
    Object.values(AIMWorkloadStatus).map((s) => [s, 0]),
  ) as Record<AIMWorkloadStatus, number>;

  // The backend orders the Default profile first, but select it by its
  // isDefault flag rather than by position so the card's summary never keys
  // off an arbitrary row. Leave it undefined when no row is flagged Default,
  // rather than falling back to profiles[0] and summarising the wrong profile.
  const profiles: CustomProfileResponse[] = model.profiles ?? [];
  const defaultProfile = profiles.find((profile) => profile.isDefault);

  return {
    repository: model.metadata.name,
    parsedAIMs: [parsedAIM],
    latestAim: isReady ? parsedAIM : null,
    isSupported: isReady,
    deploymentCounts: zeroDeploymentCounts,
    aggregated: {
      title: displayName,
      aiLabName: extractOrgName(canonicalName),
      canonicalName,
      latestImageVersion: revision,
      isHfTokenRequired,
      isCustomImport: true,
      tags,
      description: { short: description, full: description },
      onboardPhase: model.phase?.state,
      preferredPrecision,
      profileCount: profiles.length,
      defaultProfile,
    },
  };
}

/**
 * Normalizes a custom-model display name for duplicate detection.
 *
 * The onboarding flow keys its dedupe on the display name, so two names that
 * differ only by surrounding whitespace or letter case should be treated as the
 * same when warning the user about an overwrite. This is an advisory comparison
 * for the wizard warning, intentionally broader than the backend's exact
 * label-value collision.
 */
export function normalizeCustomModelDisplayName(name: string): string {
  return name.trim().toLowerCase();
}

/**
 * Builds the set of normalized display names already used by custom models in
 * the project, so the import/edit wizard can warn when a name would overwrite
 * an existing model.
 *
 * @param models - The project's custom models (aggregated card view).
 * @param excludeRepository - In edit mode, the resource name of the model being
 *   edited, so its own current name does not count as a duplicate.
 */
export function collectExistingDisplayNames(
  models: AggregatedAIM[],
  excludeRepository?: string,
): Set<string> {
  const names = new Set<string>();
  for (const model of models) {
    if (excludeRepository && model.repository === excludeRepository) {
      continue;
    }
    const normalized = normalizeCustomModelDisplayName(model.aggregated.title);
    if (normalized) {
      names.add(normalized);
    }
  }
  return names;
}

/** Display metadata for the edit wizard's "Model information" step. */
export type CustomModelDisplayMetadata = {
  displayName: string;
  description: string;
  tags: string[];
};

/**
 * Extracts the editable display metadata (name, description, tags) from a
 * custom model CR's annotations. Used to prefill the edit wizard's step 2;
 * falls back to the CR name when the display-name annotation is absent.
 */
export function extractCustomModelDisplayMetadata(
  model: CustomModelResponse,
): CustomModelDisplayMetadata {
  const annotations = model.metadata.annotations ?? {};
  return {
    displayName:
      annotations[MODEL_DISPLAY_NAME_ANNOTATION] ?? model.metadata.name,
    description: annotations[SOURCE_DESCRIPTION_ANNOTATION] ?? '',
    tags: parseTags(annotations[SOURCE_TAGS_ANNOTATION]),
  };
}

/**
 * Resolves the canonical upstream repo id for a custom model from its
 * annotations, falling back to the CR name. Shown read-only in the edit
 * wizard's source step since the import source is immutable post-onboard.
 */
export function extractCustomModelCanonicalName(
  model: CustomModelResponse,
): string {
  const annotations = model.metadata.annotations ?? {};
  return annotations[CANONICAL_REPO_ID_ANNOTATION] ?? model.metadata.name;
}

/**
 * Resolves the onboard-chosen runtime precision from a custom model CR's
 * annotations. The AIMModel CRD prunes `spec.profiles.overrides.precision`, so
 * the backend records the value on an annotation instead; this is the only
 * durable source of the user's choice. Returns `undefined` for models
 * onboarded before precision was tracked (edit/deploy then fall back to their
 * existing defaults).
 */
export function extractCustomModelPrecision(
  model: CustomModelResponse,
): string | undefined {
  const annotations = model.metadata.annotations ?? {};
  return annotations[MODEL_PRECISION_ANNOTATION] || undefined;
}

/**
 * Fetches all custom models for a project from the AIWB API.
 *
 * Backed by GET /api/projects/{project}/models (BFF) →
 * GET /v1/projects/{project}/models (upstream).
 *
 * @param project - The project namespace to list custom models for.
 * @returns Parsed AggregatedAIM list ready for the CustomModels tab.
 * @throws {APIRequestError} If the request fails.
 */
export async function listCustomModels(
  project: string,
): Promise<AggregatedAIM[]> {
  if (!project) {
    throw new APIRequestError('No project selected', 422);
  }
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/models',
    { params: { path: { project } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch custom models: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return (data.data ?? []).map(customModelToAggregatedAIM);
}

/**
 * Fetches the runtime-profile options a custom model will support in a project.
 *
 * Backed by GET /api/projects/{project}/models/runtime-profile-options (BFF) →
 * GET /v1/projects/{project}/models/runtime-profile-options (upstream). The
 * onboard wizard uses the returned matrix to preset/constrain its runtime
 * selectors. Returns empty arrays when the base model has not emitted profiles
 * yet so callers fall back to static defaults.
 *
 * @throws {APIRequestError} If the project is missing or the request fails.
 */
export async function getRuntimeProfileOptions(
  project: string,
): Promise<RuntimeProfileOptions> {
  if (!project) {
    throw new APIRequestError('No project selected', 422);
  }
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/models/runtime-profile-options',
    { params: { path: { project } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch runtime profile options: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
}

/**
 * Fetches runtime options discovered for one selected base image.
 *
 * Backed by GET /api/projects/{project}/models/runtime-profile-options/base-image.
 * Returns per-accelerator-model counts/precisions so runtime selectors can be
 * constrained by the selected image's discovered matrix.
 */
export async function getBaseImageRuntimeProfileOptions(
  project: string,
  imageRepository: string,
  imageTag: string,
): Promise<BaseImageRuntimeProfileOptions> {
  if (!project) {
    throw new APIRequestError('No project selected', 422);
  }
  if (!imageRepository.trim() || !imageTag.trim()) {
    throw new APIRequestError(
      'Both image repository and image tag are required',
      422,
    );
  }
  const client = apiClient as unknown as {
    GET: (
      path: string,
      options: {
        params: {
          path: { project: string };
          query: { imageRepository: string; imageTag: string };
        };
      },
    ) => Promise<{
      data?: unknown;
      error?: unknown;
      response: { ok: boolean; status: number };
    }>;
  };
  const { data, error, response } = await client.GET(
    '/api/projects/{project}/models/runtime-profile-options/base-image',
    {
      params: {
        path: { project },
        query: {
          imageRepository: imageRepository.trim(),
          imageTag: imageTag.trim(),
        },
      },
    },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch base-image runtime profile options: ${getApiClientErrorMessage(error, response as never)}`,
      response.status,
    );
  }
  return data as BaseImageRuntimeProfileOptions;
}

/**
 * Fetches a single custom model (raw CR + composed status + profile collection).
 *
 * Backed by GET /api/projects/{project}/models/{modelId} (BFF) →
 * GET /v1/projects/{project}/models/{model_name} (upstream). Returns the raw
 * CR shape — not the aggregated card view — so the edit wizard can prefill from
 * annotations and spec.profiles.overrides. The response also carries the
 * model's `profiles` collection (Default first), matching the dedicated
 * profiles endpoint.
 *
 * @throws {APIRequestError} If the project/modelId is missing or the request fails.
 */
export async function getCustomModel(
  project: string,
  modelId: string,
): Promise<CustomModelResponse> {
  if (!project) {
    throw new APIRequestError('No project selected', 422);
  }
  if (!modelId) {
    throw new APIRequestError('No model selected', 422);
  }
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/models/{model_name}',
    { params: { path: { project, model_name: modelId } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch custom model: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data;
}

/**
 * Applies a partial update to a custom model (display metadata and/or runtime
 * profile) in one request.
 *
 * Backed by PATCH /api/projects/{project}/models/{modelId} (BFF) →
 * PATCH /v1/projects/{project}/models/{model_name} (upstream). The caller is
 * responsible for sending only changed fields and, for runtime-profile edits,
 * the complete desired profile (merge-patch semantics; see CustomModelPatchRequest).
 *
 * @throws {APIRequestError} If the project/modelId/body is missing or the request fails.
 */
export async function patchCustomModel(
  project: string,
  modelId: string,
  body: CustomModelPatchRequest,
): Promise<void> {
  if (!project) {
    throw new APIRequestError('No project selected', 422);
  }
  if (!modelId) {
    throw new APIRequestError('No model selected', 422);
  }
  if (Object.keys(body).length === 0) {
    throw new APIRequestError('No changes to save', 422);
  }
  const { error, response } = await apiClient.PATCH(
    '/api/projects/{project}/models/{model_name}',
    { params: { path: { project, model_name: modelId } }, body },
  );
  if (!response.ok) {
    // A cluster whose BFF/proxy rejects PATCH (405 Method Not Allowed) predates
    // custom-model editing; surface an actionable admin message rather than the
    // raw method-not-allowed body.
    const errorMessage =
      response.status === 405
        ? 'The server does not support saving these changes. An administrator may need to update the deployment.'
        : getApiClientErrorMessage(error, response);
    throw new APIRequestError(
      `Failed to update custom model: ${errorMessage}`,
      response.status,
    );
  }
}

function parseWireErrorJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

/**
 * Reads blocking-deployment names out of a conflict body's service list.
 *
 * Model delete sends bare name strings, while profile delete sends
 * `{ serviceId, displayName }` objects, so both encodings are accepted and
 * anything unrecognised is dropped rather than rendered as `[object Object]`.
 */
function toBlockingServiceNames(raw: unknown[]): string[] {
  return raw
    .map((entry): string | undefined => {
      if (typeof entry === 'string') {
        return entry;
      }
      if (entry && typeof entry === 'object') {
        const o = entry as Record<string, unknown>;
        const name = o.displayName ?? o.name ?? o.serviceId;
        return typeof name === 'string' ? name : undefined;
      }
      return undefined;
    })
    .filter((name): name is string => Boolean(name && name.length > 0));
}

/** Extracts human-readable message from `detail` or BFF `error`, plus optional blocking service names. */
export function parseCustomModelDeleteErrorBody(text: string): {
  detail: string;
  blockingServices: string[];
} {
  const json = parseWireErrorJson(text);
  if (!json || typeof json !== 'object') {
    return { detail: text || 'Request failed', blockingServices: [] };
  }
  const o = json as Record<string, unknown>;
  const detailFromDetail =
    typeof o.detail === 'string' && o.detail.length > 0 ? o.detail : undefined;
  const detailFromError =
    typeof o.error === 'string' && o.error.length > 0 ? o.error : undefined;
  const detail = detailFromDetail ?? detailFromError ?? 'Request failed';
  const info = o.additionalInfo ?? o.additional_info;
  let blockingServices: string[] = [];
  if (Array.isArray(info)) {
    blockingServices = toBlockingServiceNames(info);
  } else if (info && typeof info === 'object') {
    const d = info as Record<string, unknown>;
    const raw =
      d.blockingServices ??
      d.blockingServiceNames ??
      d.services ??
      d.blockingDeployments;
    if (Array.isArray(raw)) {
      blockingServices = toBlockingServiceNames(raw);
    }
  }
  return { detail, blockingServices };
}

/**
 * Deletes an onboarded (BYOM) custom model for a project.
 *
 * Backed by DELETE /api/projects/{project}/models/{modelId} (BFF) →
 * DELETE /v1/projects/{project}/models/{model_name} (upstream). Returns on
 * 204 No Content.
 *
 * @throws {CustomModelDeleteConflictError} When the model is still referenced by deployments (409).
 * @throws {APIRequestError} For other failures (including 404).
 */
export async function deleteCustomModel(
  project: string,
  modelName: string,
): Promise<void> {
  if (!project) {
    throw new APIRequestError('No project selected', 422);
  }
  if (!modelName) {
    throw new APIRequestError('No model selected', 422);
  }
  const { error, response } = await apiClient.DELETE(
    '/api/projects/{project}/models/{model_name}',
    { params: { path: { project, model_name: modelName } } },
  );
  if (response.ok) {
    return;
  }
  // The 409 conflict body carries blocking-service names the typed client
  // cannot model (it varies by proxy vs. upstream shape). openapi-fetch has
  // already drained the body into `error` (parsed JSON when possible, else the
  // raw string), so re-reading `response.text()` would throw "body already
  // read"; re-serialize `error` and parse it here instead so the modal can list
  // what still references the model.
  const text =
    (typeof error === 'string' ? error : JSON.stringify(error)) ?? '';
  const { detail, blockingServices } = parseCustomModelDeleteErrorBody(text);
  if (response.status === 409) {
    throw new CustomModelDeleteConflictError(detail, blockingServices);
  }
  throw new APIRequestError(
    `Failed to delete custom model: ${detail}`,
    response.status,
  );
}

/**
 * Copies an onboarded custom model in a project.
 *
 * @param project - Project namespace that owns the source model.
 * @param sourceModelName - Source custom-model resource name (`metadata.name`).
 * @throws {APIRequestError} When the copy request fails.
 */
export async function copyCustomModel(
  project: string,
  sourceModelName: string,
): Promise<void> {
  if (!project) {
    throw new APIRequestError('No project selected', 422);
  }
  if (!sourceModelName) {
    throw new APIRequestError('No source custom model name provided', 422);
  }
  const { error, response } = await apiClient.POST(
    '/api/projects/{project}/models/{model_name}/copy',
    { params: { path: { project, model_name: sourceModelName } } },
  );
  if (!response.ok) {
    throw new APIRequestError(
      `Failed to copy custom model: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
}
