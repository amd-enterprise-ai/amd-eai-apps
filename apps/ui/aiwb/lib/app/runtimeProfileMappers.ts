// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { parse as parseYaml, stringify as stringifyYaml } from 'yaml';

import { selectorAxes } from '@/lib/app/custom-profiles';

import type {
  CustomProfileConfig,
  CustomProfileCreateRequest,
  CustomProfilePatchRequest,
  CustomProfileResponse,
} from '@/lib/app/custom-profiles';
import type { components } from '@/types/api';
import type { AimImageFamily, ClusterAccelerator } from '@/types/cluster';
import type { EngineEnvEntry, ModelCustomProfile } from '@/types/model-import';

import {
  acceleratorModelToDeviceId,
  deviceIdToAcceleratorModel,
  findImageFamily,
  getDefaultAcceleratorDeviceId,
  getDefaultImageFamilySelection,
  getLatestImageTag,
  resolveDefaultOnboardImageRef,
  resolveProfileImage,
  RUNTIME_PROFILE_METRIC_KEYS,
} from './runtimeProfileCatalog';

type RuntimeProfileOverrides = {
  imageFamilyId: string;
  image?: string;
  acceleratorType: string;
  acceleratorModel: string;
  acceleratorCount: number;
  precision: string;
  engineArgsYaml?: string;
  envVarsYaml?: string;
};

type OnboardRequest = components['schemas']['OnboardRequest'];

/**
 * Which runtime YAML field failed to parse, so callers can surface a
 * field-specific message. The values match the form field names.
 */
type RuntimeProfileYamlField = 'engineArgsYaml' | 'envVarsYaml';

/** Raised when a runtime YAML textarea is not a valid `key: value` mapping. */
export class RuntimeProfileYamlError extends Error {
  constructor(readonly field: RuntimeProfileYamlField) {
    super(`Invalid YAML for ${field}`);
    this.name = 'RuntimeProfileYamlError';
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false;
  }
  const proto = Object.getPrototypeOf(value);
  return proto === null || proto === Object.prototype;
}

/**
 * Parse a runtime YAML textarea into the `key: value` mapping aim-engine
 * expects. Returns `undefined` for blank input; throws
 * {@link RuntimeProfileYamlError} when the text is not a top-level mapping
 * (e.g. a bare scalar or a list), so the wizard can block submit with a
 * field-specific error instead of silently dropping the value.
 */
export function parseRuntimeYamlMapping(
  raw: string | undefined,
  field: RuntimeProfileYamlField,
): Record<string, unknown> | undefined {
  const text = raw?.trim();
  if (!text) {
    return undefined;
  }
  let parsed: unknown;
  try {
    parsed = parseYaml(text);
  } catch {
    throw new RuntimeProfileYamlError(field);
  }
  if (!isPlainObject(parsed)) {
    throw new RuntimeProfileYamlError(field);
  }
  return parsed;
}

/** True when the textarea is blank or a valid YAML mapping (for schema validation). */
export function isRuntimeYamlMappingValid(raw: string | undefined): boolean {
  try {
    parseRuntimeYamlMapping(raw, 'engineArgsYaml');
    return true;
  } catch {
    return false;
  }
}

/**
 * Parse the env-vars YAML mapping into `[{name, value}]` entries. Names ride as
 * values (not keys) to keep UPPER_SNAKE_CASE env vars off the camelCase contract;
 * the server collapses them back into a map. Non-string values are serialized to
 * their YAML form.
 */
function parseEngineEnvYaml(
  raw: string | undefined,
): EngineEnvEntry[] | undefined {
  const mapping = parseRuntimeYamlMapping(raw, 'envVarsYaml');
  if (!mapping) {
    return undefined;
  }
  return Object.entries(mapping).map(([name, value]) => ({
    name,
    value: typeof value === 'string' ? value : stringifyYaml(value).trim(),
  }));
}

/** Serialize a persisted mapping back to a YAML textarea string for edit prefill. */
function stringifyRuntimeMapping(
  value: Record<string, unknown> | undefined | null,
): string | undefined {
  if (!value || Object.keys(value).length === 0) {
    return undefined;
  }
  return stringifyYaml(value).trim();
}

export type RuntimeProfileFormInput = {
  containerImage: string;
  containerVersion: string;
  acceleratorType: string;
  accelerator: string;
  /** Select-backed field: RHF may hold string keys even though zod can coerce to number elsewhere. */
  acceleratorCount: number | string;
  modelPrecision: string;
  engineArgsYaml: string;
  envVarsYaml: string;
};

/**
 * Runtime knobs as persisted on `AIMModel.spec.profiles.overrides`. Mirrors the
 * camelCase wire keys. Fields are optional on read for back-compat with older
 * imports and minimal payloads, even though current onboard/edit flows usually
 * persist canonical runtime fields.
 */
export type PersistedProfileOverrides = {
  image?: string | null;
  imageFamilyId?: string;
  acceleratorType?: string;
  acceleratorModel?: string;
  acceleratorCount?: number;
  precision?: string;
  /** Canonical aim-engine fields the onboard/edit flow now persists. */
  engineArgs?: Record<string, unknown> | null;
  engineEnv?: Record<string, string> | null;
  /** Legacy YAML-string fields kept for back-compat read-back of older imports. */
  engineArgsYaml?: string;
  envVarsYaml?: string;
};

export function formValuesToProfileOverrides(
  values: RuntimeProfileFormInput,
  imageFamilies: AimImageFamily[],
): RuntimeProfileOverrides {
  const image = resolveProfileImage(
    values.containerImage,
    values.containerVersion,
    imageFamilies,
  );
  const engineArgsYaml = values.engineArgsYaml.trim();
  const envVarsYaml = values.envVarsYaml.trim();
  return {
    imageFamilyId: values.containerImage,
    ...(image ? { image } : {}),
    acceleratorType: values.acceleratorType.trim(),
    acceleratorModel: values.accelerator.trim(),
    // The count select stores its key as a string; normalize so the onboard
    // payload always carries an integer (mirrors the patch path).
    acceleratorCount: normalizePositiveInt(values.acceleratorCount),
    precision: values.modelPrecision.trim(),
    ...(engineArgsYaml ? { engineArgsYaml } : {}),
    ...(envVarsYaml ? { envVarsYaml } : {}),
  };
}

/**
 * Build the customProfile block aim-engine bakes into the emitted AIMProfile.
 *
 * The selected precision is always included (so aim-engine never falls back to
 * a base-template default that misreports the precision), and the accelerator
 * is translated from the cluster device id to the canonical `acceleratorModel`
 * aim-engine resolves against (sending the raw device id leaves the profile
 * `NotAvailable`). Engine args are parsed from YAML into the canonical
 * `engineArgs` object; env vars become `[{name, value}]` entries (see
 * {@link parseEngineEnvYaml}).
 */
function overridesToCustomProfile(
  overrides: RuntimeProfileOverrides,
  accelerators: ClusterAccelerator[],
): ModelCustomProfile {
  const profile: ModelCustomProfile = {
    imageFamilyId: overrides.imageFamilyId,
    acceleratorType: overrides.acceleratorType,
    acceleratorModel: deviceIdToAcceleratorModel(
      overrides.acceleratorModel,
      accelerators,
    ),
    acceleratorCount: overrides.acceleratorCount,
    precision: overrides.precision,
  };
  const engineArgs = parseRuntimeYamlMapping(
    overrides.engineArgsYaml,
    'engineArgsYaml',
  );
  if (engineArgs) {
    profile.engineArgs = engineArgs;
  }
  const engineEnv = parseEngineEnvYaml(overrides.envVarsYaml);
  if (engineEnv) {
    profile.engineEnv = engineEnv;
  }
  return profile;
}

/**
 * Maps v1alpha2-shaped overrides to today's onboard request body. Uses
 * `customProfile` as the transport until onboard accepts nested overrides.
 *
 * The generated `OnboardRequest.description` is a required (server-defaulted)
 * field, so it is always emitted — falling back to an empty string when the
 * preview omitted a catalog description.
 */
export function profileOverridesToOnboardBody(
  overrides: RuntimeProfileOverrides,
  previewFields: Pick<
    OnboardRequest,
    | 'sourceType'
    | 'repoId'
    | 'revision'
    | 'sha'
    | 'displayName'
    | 'tags'
    | 'hfTokenSecretName'
    | 's3StorageName'
  > & {
    // Optional on input — preview may omit it; emitted unconditionally below.
    description?: OnboardRequest['description'];
  },
  imageFamilies: AimImageFamily[],
  accelerators: ClusterAccelerator[],
): OnboardRequest {
  const image = overrides.image ?? resolveDefaultOnboardImageRef(imageFamilies);
  return {
    ...previewFields,
    description: previewFields.description ?? '',
    image,
    customProfile: overridesToCustomProfile(
      overrides,
      accelerators,
    ) as OnboardRequest['customProfile'],
  };
}

/**
 * Strip an OCI digest suffix (`@sha256:hex`, etc.) so `:` inside the digest is not
 * mistaken for a `repo:tag` separator.
 */
function imageRefWithoutDigest(ref: string): string {
  const at = ref.indexOf('@');
  if (at === -1) {
    return ref;
  }
  const digest = ref.slice(at + 1);
  if (/^[a-z0-9][a-z0-9._-]*:[a-f0-9]+$/i.test(digest)) {
    return ref.slice(0, at);
  }
  return ref;
}

/**
 * Resolves a concrete container image ref (`repo:tag`) back to its catalog
 * image family and version tag. Returns the matching `familyId` when a family
 * advertises that repository, plus the embedded tag; either may be undefined
 * when the ref has no tag or no catalog family owns the repository.
 */
export function imageRefToFamilyTag(
  image: string | undefined | null,
  imageFamilies: AimImageFamily[],
): { familyId?: string; tag?: string } {
  const ref = image?.trim();
  if (!ref) {
    return {};
  }
  const withoutDigest = imageRefWithoutDigest(ref);
  const lastColon = withoutDigest.lastIndexOf(':');
  const lastSlash = withoutDigest.lastIndexOf('/');
  const hasTag = lastColon > -1 && lastColon > lastSlash;
  const repository = hasTag ? withoutDigest.slice(0, lastColon) : withoutDigest;
  const tag = hasTag ? withoutDigest.slice(lastColon + 1) : undefined;
  const family = imageFamilies.find((entry) => entry.repository === repository);
  return { familyId: family?.familyId, tag: tag || undefined };
}

/**
 * Reverse of {@link formValuesToProfileOverrides}: maps persisted overrides
 * back to step-3 form values for the edit wizard. Fields the import omitted
 * (because they matched catalog defaults) fall back to the same catalog
 * defaults the create flow seeds, so a never-customised model prefills cleanly.
 */
export function profileOverridesToFormValues(
  overrides: PersistedProfileOverrides | null | undefined,
  imageFamilies: AimImageFamily[],
  accelerators: ClusterAccelerator[],
): Omit<RuntimeProfileFormInput, 'acceleratorCount'> & {
  acceleratorCount: number;
} {
  const persisted = overrides ?? {};
  const catalogDefault = getDefaultImageFamilySelection(imageFamilies);
  const fromImage = imageRefToFamilyTag(persisted.image, imageFamilies);

  // Family priority: an explicit (still-valid) override family, then the family
  // inferred from the concrete image ref, then the catalog default.
  const overrideFamilyValid = Boolean(
    persisted.imageFamilyId &&
      findImageFamily(imageFamilies, persisted.imageFamilyId)?.repository,
  );
  const containerImage =
    (overrideFamilyValid ? persisted.imageFamilyId : undefined) ??
    fromImage.familyId ??
    catalogDefault.familyId;

  // Tag priority: the tag parsed from the image (only when it belongs to the
  // resolved family), then that family's latest tag, then the catalog default.
  const family = findImageFamily(imageFamilies, containerImage);
  const tagFromImage =
    fromImage.familyId === containerImage ? fromImage.tag : undefined;
  const containerVersion =
    tagFromImage ||
    (family ? getLatestImageTag(family.tags) : '') ||
    catalogDefault.tag;

  return {
    containerImage,
    containerVersion: containerVersion ?? '',
    acceleratorType: persisted.acceleratorType?.trim() || 'gpu',
    accelerator:
      acceleratorModelToDeviceId(persisted.acceleratorModel, accelerators) ||
      getDefaultAcceleratorDeviceId(accelerators),
    acceleratorCount:
      typeof persisted.acceleratorCount === 'number' &&
      persisted.acceleratorCount > 0
        ? persisted.acceleratorCount
        : 1,
    modelPrecision: persisted.precision?.trim() || 'bf16',
    engineArgsYaml:
      stringifyRuntimeMapping(persisted.engineArgs) ??
      persisted.engineArgsYaml ??
      '',
    envVarsYaml:
      stringifyRuntimeMapping(persisted.engineEnv) ??
      persisted.envVarsYaml ??
      '',
  };
}

/**
 * Builds the runtime-profile half of a PATCH body from step-3 form values.
 *
 * Unlike the onboard mapper, this always emits the *complete* desired profile
 * so the backend merge-patch fully reflects the form: catalog knobs are sent
 * explicitly, and cleared YAML fields are sent as `null` so the live profile
 * resets that field to the aim-engine default instead of keeping a stale value.
 * The image is carried top-level only (never inside customProfile) to avoid the
 * server's conflicting-image-ref rejection.
 */
function normalizePositiveInt(value: number | string): number {
  const n =
    typeof value === 'number' && Number.isFinite(value)
      ? Math.trunc(value)
      : Number.parseInt(String(value).trim(), 10);
  return Number.isFinite(n) && n > 0 ? n : 1;
}

/**
 * A named custom profile's form values: the shared runtime knobs plus the two
 * fields only a profile carries — its own display name and the performance
 * metric it is narrowed to.
 */
export type CustomProfileFormInput = RuntimeProfileFormInput & {
  displayName: string;
  metric: string;
};

/**
 * The narrowing axes and image, shared by the create and update bodies. Emitted
 * as typed fields (not opaque overrides) so the server composes the selector and
 * the profile overrides from one source and the accelerator count cannot drift
 * apart from `tensor-parallel-size`.
 */
function customProfileAxes(
  values: CustomProfileFormInput,
  imageFamilies: AimImageFamily[],
  accelerators: ClusterAccelerator[],
): Omit<CustomProfileCreateRequest, 'displayName' | 'customProfile'> {
  return {
    acceleratorModel: deviceIdToAcceleratorModel(
      values.accelerator.trim(),
      accelerators,
    ),
    acceleratorCount: normalizePositiveInt(values.acceleratorCount),
    precision: values.modelPrecision.trim(),
    metric: values.metric.trim(),
    image:
      resolveProfileImage(
        values.containerImage,
        values.containerVersion,
        imageFamilies,
      ) ?? resolveDefaultOnboardImageRef(imageFamilies),
  };
}

/**
 * Builds the POST body for a new profile. Blank YAML fields are omitted rather
 * than sent as `null`: on create there is no persisted value to reset, so the
 * profile simply inherits the aim-engine default.
 */
export function formValuesToCustomProfileCreate(
  values: CustomProfileFormInput,
  imageFamilies: AimImageFamily[],
  accelerators: ClusterAccelerator[],
): CustomProfileCreateRequest {
  const engineArgs = parseRuntimeYamlMapping(
    values.engineArgsYaml,
    'engineArgsYaml',
  );
  const engineEnv = parseEngineEnvYaml(values.envVarsYaml);
  return {
    displayName: values.displayName.trim(),
    ...customProfileAxes(values, imageFamilies, accelerators),
    customProfile: {
      acceleratorType: values.acceleratorType.trim(),
      ...(engineArgs ? { engineArgs } : {}),
      ...(engineEnv ? { engineEnv } : {}),
    },
  };
}

/**
 * Builds the PATCH body for an existing profile.
 *
 * Always emits the complete desired state so the merge-patch fully reflects the
 * form, and sends cleared YAML fields as `null` so the live profile resets them
 * to the aim-engine default instead of keeping a stale value.
 */
export function formValuesToCustomProfilePatch(
  values: CustomProfileFormInput,
  imageFamilies: AimImageFamily[],
  accelerators: ClusterAccelerator[],
): CustomProfilePatchRequest {
  return {
    displayName: values.displayName.trim(),
    ...customProfileAxes(values, imageFamilies, accelerators),
    customProfile: {
      acceleratorType: values.acceleratorType.trim(),
      engineArgs:
        parseRuntimeYamlMapping(values.engineArgsYaml, 'engineArgsYaml') ??
        null,
      engineEnv: parseEngineEnvYaml(values.envVarsYaml) ?? null,
    },
  };
}

/** Serialize read-back `[{name, value}]` env entries into a YAML textarea string. */
function stringifyEngineEnvEntries(
  engineEnv: CustomProfileConfig['engineEnv'],
): string | undefined {
  if (!engineEnv) {
    return undefined;
  }
  // Entries are collapsed to a map server-side, so a saved profile reads back as
  // a mapping even though it was written as [{name, value}]. Both spellings are
  // accepted so a profile written by an older client still prefills.
  if (!Array.isArray(engineEnv)) {
    return stringifyRuntimeMapping(engineEnv);
  }
  const named = engineEnv.filter(
    (entry): entry is { name: string; value: unknown } =>
      typeof entry?.name === 'string' && Boolean(entry.name),
  );
  if (!named.length) {
    return undefined;
  }
  return stringifyRuntimeMapping(
    Object.fromEntries(named.map(({ name, value }) => [name, value])),
  );
}

/**
 * Maps a saved profile back to drawer form values for editing.
 *
 * Prefers authored intent (`selector`, `customProfile`) over the effective
 * configuration on `profile.spec`, so reopening the drawer shows what the user
 * asked for rather than what aim-engine resolved it to. The synthetic Default
 * carries no authored record on some models, hence the spec fallback.
 */
export function customProfileToFormValues(
  profile: CustomProfileResponse,
  imageFamilies: AimImageFamily[],
  accelerators: ClusterAccelerator[],
): CustomProfileFormInput {
  const axes = selectorAxes(profile.selector);
  const config = profile.customProfile ?? {};
  const spec = profile.profile?.spec;
  const runtimeValues = profileOverridesToFormValues(
    {
      image: config.image ?? spec?.image,
      acceleratorType:
        config.acceleratorType ?? spec?.acceleratorType ?? undefined,
      acceleratorModel:
        axes.acceleratorModel ?? spec?.acceleratorModel ?? undefined,
      acceleratorCount:
        axes.acceleratorCount ?? spec?.acceleratorCount ?? undefined,
      precision: axes.precision ?? spec?.precision ?? undefined,
      engineArgs: config.engineArgs,
    },
    imageFamilies,
    accelerators,
  );
  return {
    ...runtimeValues,
    displayName: profile.displayName,
    metric: axes.metric ?? spec?.metric ?? RUNTIME_PROFILE_METRIC_KEYS[0],
    // `engineEnv` does not read back as the mapping the shared reverse mapper
    // expects, so it is serialized separately.
    envVarsYaml: stringifyEngineEnvEntries(config.engineEnv) ?? '',
  };
}

export function formValuesToProfilePatch(
  values: RuntimeProfileFormInput,
  imageFamilies: AimImageFamily[],
  accelerators: ClusterAccelerator[],
): { image: string; customProfile: Record<string, unknown> } {
  const image =
    resolveProfileImage(
      values.containerImage,
      values.containerVersion,
      imageFamilies,
    ) ?? resolveDefaultOnboardImageRef(imageFamilies);
  const engineArgs = parseRuntimeYamlMapping(
    values.engineArgsYaml,
    'engineArgsYaml',
  );
  const engineEnv = parseEngineEnvYaml(values.envVarsYaml);
  return {
    image,
    customProfile: {
      imageFamilyId: values.containerImage,
      acceleratorType: values.acceleratorType.trim(),
      acceleratorModel: deviceIdToAcceleratorModel(
        values.accelerator.trim(),
        accelerators,
      ),
      acceleratorCount: normalizePositiveInt(values.acceleratorCount),
      precision: values.modelPrecision.trim(),
      // Merge-patch: send null to reset a cleared field to the aim-engine default.
      engineArgs: engineArgs ?? null,
      engineEnv: engineEnv ?? null,
    },
  };
}
