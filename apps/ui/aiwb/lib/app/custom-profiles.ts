// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

/**
 * Custom profile reads and writes for a custom model.
 *
 * These call the BFF proxies under
 * `/api/projects/{project}/models/{modelId}/profiles`, which forward to the
 * upstream AIWB endpoints.
 *
 * The read shapes and the create body come from the generated OpenAPI schema, so
 * `apiClient` addresses those paths directly. Update and delete still go through
 * plain `fetch`: `apiClient` derives its paths from that schema, and those two
 * endpoints are not published yet.
 */

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { apiClient, getApiClientErrorMessage } from '@/lib/api-client';
import { parseCustomModelDeleteErrorBody } from '@/lib/app/custom-models';

import {
  FINE_TUNED_LABEL,
  NAMESPACE_AIM_MODEL_LABEL,
  type AIMService,
  type ModelProfileSummaryFields,
} from '@/types/aims';
import type { components } from '@/types/api';
import type { EngineEnvEntry } from '@/types/model-import';

/** A deployment that currently references a profile, blocking edit and delete. */
export type ProfileInUseRef = components['schemas']['ProfileInUseRef'];

/** Reconciliation state of the profile's underlying resources. */
export type CustomProfileStatus = components['schemas']['CustomProfileStatus'];

/**
 * The narrowing axes the profile was authored with, which the server composes
 * `derivedFrom.selector` from. The edit drawer hydrates from these in preference
 * to the effective values on `profile.spec`.
 *
 * The wire type keeps the selector open so aim-engine filter axes the API does
 * not model stay round-trippable, which leaves the axes untyped; read them
 * through {@link selectorAxes} rather than indexing this directly.
 */
export type CustomProfileSelector = components['schemas']['ProfileSelector'];

/** The four narrowing axes, recovered from the open selector. */
export type CustomProfileSelectorAxes = {
  acceleratorModel?: string;
  acceleratorCount?: number;
  metric?: string;
  precision?: string;
};

/**
 * Reads the narrowing axes off an authored selector, dropping any value that is
 * not the expected primitive so a malformed selector degrades to "unset" rather
 * than seeding the drawer with a value the form cannot represent.
 */
export function selectorAxes(
  selector: CustomProfileSelector | null | undefined,
): CustomProfileSelectorAxes {
  const asString = (value: unknown) =>
    typeof value === 'string' && value ? value : undefined;
  return {
    acceleratorModel: asString(selector?.acceleratorModel),
    acceleratorCount:
      typeof selector?.acceleratorCount === 'number'
        ? selector.acceleratorCount
        : undefined,
    metric: asString(selector?.metric),
    precision: asString(selector?.precision),
  };
}

/**
 * Runtime configuration carried on a write request. Opaque to the server, which
 * merge-patches it onto the profile: a present key is set, an explicit `null`
 * resets to the aim-engine default, an omitted key is left unchanged.
 *
 * `acceleratorType` rides here rather than as a typed narrowing axis because
 * aim-engine resolves against the accelerator *model*; this mirrors what the
 * onboard flow already sends under `customProfile`.
 */
export type CustomProfileWriteConfig = {
  acceleratorType?: string;
  engineArgs?: Record<string, unknown> | null;
  engineEnv?: EngineEnvEntry[] | null;
};

/**
 * Authored configuration as read back. The server answers with an allowlist, so
 * this carries only the overrides it chooses to surface — and `engineEnv` comes
 * back as the map it was collapsed to on write, not as entries.
 */
export type CustomProfileConfig =
  components['schemas']['CustomProfileConfiguration'];

/**
 * One entry in a custom model's profile list, and the body every write returns.
 *
 * `name` is the AIMProfileSet resource name, or the reserved literal `default`
 * for the engine-owned Default set, which has no stored record of its own and
 * so cannot be deleted. `resourceName` always carries the real resource name.
 */
export type CustomProfileResponse =
  components['schemas']['CustomProfileResponse'];

/**
 * Body for POST …/profiles.
 *
 * The four narrowing axes are typed fields rather than opaque overrides: the
 * server composes both the selector and the profile overrides from them, so the
 * accelerator count cannot drift apart from `tensor-parallel-size` the way it
 * does on models onboarded with one overrides block stamped across every
 * derived profile.
 *
 * `customProfile` is narrowed from the schema's open map to the knobs this app
 * actually authors, so a typo in one of them fails the typecheck.
 */
export type CustomProfileCreateRequest = Omit<
  components['schemas']['CustomProfileCreateRequest'],
  'customProfile'
> & {
  customProfile?: CustomProfileWriteConfig;
};

/** Body for PATCH …/profiles/{profile}: all fields optional, at least one required. */
export type CustomProfilePatchRequest = Partial<CustomProfileCreateRequest>;

const PROFILE_READY_STATE = 'Ready';

/**
 * Whether a deployment can be served by this profile. A set that has derived no
 * profile yet reports no state at all, so both halves matter.
 */
export const isProfileDeployable = (profile: CustomProfileResponse): boolean =>
  Boolean(profile.profile) && profile.status?.state === PROFILE_READY_STATE;

/**
 * Thrown when a profile write or delete returns 409.
 *
 * Two distinct refusals share the status: a deployment still references the
 * profile, in which case `blockingServices` names them, or a sibling profile
 * already uses the requested display name, in which case it is empty.
 */
export class CustomProfileConflictError extends APIRequestError {
  readonly blockingServices: string[];

  constructor(message: string, blockingServices: string[]) {
    super(message, 409);
    this.name = 'CustomProfileConflictError';
    this.blockingServices = blockingServices;
  }
}

function profilesPath(project: string, modelName: string): string {
  return `/api/projects/${encodeURIComponent(project)}/models/${encodeURIComponent(modelName)}/profiles`;
}

/** Guards the path params every profile call needs before a request is made. */
function assertProfileScope(project: string, modelName: string): void {
  if (!project) {
    throw new APIRequestError('No project selected', 422);
  }
  if (!modelName) {
    throw new APIRequestError('No model selected', 422);
  }
}

/** Raises the conflict or failure a profile write answers with. */
function throwProfileWriteFailure(
  body: string,
  status: number,
  failureMessage: string,
): never {
  const { detail, blockingServices } = parseCustomModelDeleteErrorBody(body);
  if (status === 409) {
    throw new CustomProfileConflictError(detail, blockingServices);
  }
  throw new APIRequestError(`${failureMessage}: ${detail}`, status);
}

/**
 * Lists every profile saved against a custom model, Default first.
 *
 * Backed by GET /api/projects/{project}/models/{modelId}/profiles (BFF) →
 * GET /v1/projects/{project}/models/{model}/profiles (upstream). The envelope
 * is the unpaginated `ListResponse[T]`, so the whole set arrives in one call.
 *
 * @throws {APIRequestError} If the project/model is missing or the request fails.
 */
export async function listCustomProfiles(
  project: string,
  modelName: string,
): Promise<CustomProfileResponse[]> {
  assertProfileScope(project, modelName);
  const { data, error, response } = await apiClient.GET(
    '/api/projects/{project}/models/{model}/profiles',
    { params: { path: { project, model: modelName } } },
  );
  if (error || !data) {
    throw new APIRequestError(
      `Failed to fetch custom profiles: ${getApiClientErrorMessage(error, response)}`,
      response.status,
    );
  }
  return data.data ?? [];
}

/** The profile axes a custom profile runs, for the shared deployment summary line. */
export const profileSummaryFields = (
  profile: CustomProfileResponse,
): ModelProfileSummaryFields => {
  const spec = profile.profile?.spec;
  return {
    metric: spec?.metric ?? null,
    gpu: spec?.acceleratorModel ?? null,
    templateGpuCount: spec?.acceleratorCount ?? null,
    acceleratorType: spec?.acceleratorType ?? null,
    precision: spec?.precision ?? null,
  };
};

/**
 * The custom-model deployments among `services`.
 *
 * Fine-tuned deployments carry the namespace-model label too but have no
 * selectable profiles, so they are excluded.
 */
export function customModelServices(services: AIMService[]): AIMService[] {
  return services.filter(
    (service) =>
      service.metadata.labels?.[NAMESPACE_AIM_MODEL_LABEL] === 'true' &&
      service.metadata.labels?.[FINE_TUNED_LABEL] !== 'true',
  );
}

/** The AIMModel resource names of the custom models behind a set of deployments. */
export function customModelNamesFromServices(services: AIMService[]): string[] {
  const names = customModelServices(services)
    .map((service) => service.spec?.model?.name)
    .filter((name): name is string => !!name);
  return Array.from(new Set(names)).sort();
}

/** What a custom-model deployment runs: the authored profile label and its axes. */
export type CustomProfileDeployment = {
  displayName: string;
  profile: ModelProfileSummaryFields;
};

/**
 * Maps custom-model deployments to the profile each runs, keyed by AIMService id.
 * One request per distinct model, since both the authored label and the pinned
 * profile's axes are only surfaced by that model's own profiles endpoint.
 *
 * Read from `inUseBy` rather than by matching `status.resolvedProfile.name`
 * against the profile catalog: the server builds `inUseBy` from the profile a
 * deployment *pinned*, which stays a catalog profile even when the engine
 * resolves it to a service-owned overlay the catalog excludes. The row's
 * embedded profile is the pinned one too — the server picks it with the same
 * rule deploy uses.
 *
 * A model whose profiles cannot be read is skipped rather than failing the whole
 * map, so one unreadable model does not blank every other deployment's line.
 */
export async function resolveCustomProfileDeployments(
  project: string,
  modelNames: string[],
): Promise<Map<string, CustomProfileDeployment>> {
  const settled = await Promise.allSettled(
    modelNames.map((modelName) => listCustomProfiles(project, modelName)),
  );
  const byServiceId = new Map<string, CustomProfileDeployment>();
  for (const result of settled) {
    if (result.status === 'rejected') {
      console.warn('Failed to resolve a custom model profile:', result.reason);
      continue;
    }
    for (const profile of result.value) {
      for (const ref of profile.inUseBy ?? []) {
        if (ref.serviceId) {
          byServiceId.set(ref.serviceId, {
            displayName: profile.displayName,
            profile: profileSummaryFields(profile),
          });
        }
      }
    }
  }
  return byServiceId;
}

/**
 * Deletes a named custom profile from a custom model.
 *
 * Backed by DELETE /api/projects/{project}/models/{modelId}/profiles/{profileId}
 * (BFF) → DELETE /v1/projects/{project}/models/{model}/profiles/{profile}
 * (upstream). Returns on 204.
 *
 * The list screen already disables this action for in-use and Default rows from
 * `inUseBy` / `isDefault`, so the 409 and 422 paths here cover the race where
 * a deployment claims the profile between the list read and the delete.
 *
 * @throws {CustomProfileConflictError} When a deployment still references the profile (409).
 * @throws {APIRequestError} For other failures, including 404 and the 422 returned for `default`.
 */
export async function deleteCustomProfile(
  project: string,
  modelName: string,
  profileName: string,
): Promise<void> {
  assertProfileScope(project, modelName);
  if (!profileName) {
    throw new APIRequestError('No profile selected', 422);
  }
  const response = await fetch(
    `${profilesPath(project, modelName)}/${encodeURIComponent(profileName)}`,
    { method: 'DELETE' },
  );
  if (response.ok) {
    return;
  }
  const { detail, blockingServices } = parseCustomModelDeleteErrorBody(
    await response.text(),
  );
  if (response.status === 409) {
    throw new CustomProfileConflictError(detail, blockingServices);
  }
  throw new APIRequestError(
    `Failed to delete custom profile: ${detail}`,
    response.status,
  );
}

/**
 * Creates a new named profile on a custom model.
 *
 * Backed by POST /api/projects/{project}/models/{modelId}/profiles (BFF) →
 * POST /v1/projects/{project}/models/{model}/profiles (upstream), answering 201
 * with the created profile.
 *
 * The drawer already rejects a duplicate or reserved name inline, so the 409 and
 * 422 paths here cover the race where a sibling profile claims the name between
 * the list read and the create.
 *
 * @throws {CustomProfileConflictError} When a sibling profile already uses the display name (409).
 * @throws {APIRequestError} For other failures, including the 422 returned for a reserved or empty name.
 */
export async function createCustomProfile(
  project: string,
  modelName: string,
  request: CustomProfileCreateRequest,
): Promise<CustomProfileResponse> {
  assertProfileScope(project, modelName);
  if (!request.displayName.trim()) {
    throw new APIRequestError('No profile name provided', 422);
  }
  const { data, error, response } = await apiClient.POST(
    '/api/projects/{project}/models/{model}/profiles',
    { params: { path: { project, model: modelName } }, body: request },
  );
  if (error || !data) {
    // openapi-fetch has already drained the body, so the shared wire-error
    // parser is fed the re-serialized value rather than the response text.
    throwProfileWriteFailure(
      JSON.stringify(error ?? {}),
      response.status,
      'Failed to create custom profile',
    );
  }
  return data;
}

/**
 * Updates a named profile's display name, configuration, or both.
 *
 * Backed by PATCH /api/projects/{project}/models/{modelId}/profiles/{profileId}
 * (BFF) → PATCH /v1/projects/{project}/models/{model}/profiles/{profile}
 * (upstream), answering 200 with the updated profile.
 *
 * A rename never changes `profileName`: Kubernetes object names are immutable,
 * so the resource name is fixed at creation and only the display-name
 * annotation is rewritten.
 *
 * @throws {CustomProfileConflictError} When a deployment references the profile, or the new name is taken (409).
 * @throws {APIRequestError} For other failures, including the 422 returned for `default` (edited through model settings instead).
 */
export async function updateCustomProfile(
  project: string,
  modelName: string,
  profileName: string,
  request: CustomProfilePatchRequest,
): Promise<CustomProfileResponse> {
  assertProfileScope(project, modelName);
  if (!profileName) {
    throw new APIRequestError('No profile selected', 422);
  }
  if (Object.keys(request).length === 0) {
    throw new APIRequestError('No profile changes to save', 400);
  }
  // Plain `fetch` because the upstream PATCH is not published yet, so the
  // generated schema has no path for the typed client to address.
  const response = await fetch(
    `${profilesPath(project, modelName)}/${encodeURIComponent(profileName)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    },
  );
  if (!response.ok) {
    throwProfileWriteFailure(
      await response.text(),
      response.status,
      'Failed to update custom profile',
    );
  }
  return (await response.json()) as CustomProfileResponse;
}
