// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { components } from '@/types/api';
import type { AimImageFamily, ClusterAccelerator } from '@/types/cluster';
import {
  AUTOMATIC_IMAGE_FAMILY_ID,
  type RuntimeProfileSelectOption,
} from '@/types/runtime-profile';

export const RUNTIME_PROFILE_PRECISION_OPTIONS: RuntimeProfileSelectOption[] = [
  { key: 'bf16', label: 'bf16' },
  { key: 'fp16', label: 'fp16' },
  { key: 'fp8', label: 'fp8' },
];

export const RUNTIME_PROFILE_ACCELERATOR_TYPE_OPTIONS: RuntimeProfileSelectOption[] =
  [
    { key: 'gpu', label: 'GPU' },
    { key: 'cpu', label: 'CPU' },
  ];

function toAcceleratorTypeLabel(type: string): string {
  const normalized = type.trim().toLowerCase();
  if (!normalized) {
    return '';
  }
  return normalized.toUpperCase();
}

function normalizeAcceleratorType(type: string | null | undefined): string {
  return (type ?? '').trim().toLowerCase();
}

/**
 * Metrics aim-engine narrows profiles on, as the static superset. Unlike the
 * other axes these carry no label here: they are user-facing terms, so callers
 * resolve them through `getMetricTranslationKey`.
 *
 * Callers offer the metrics `GET .../runtime-profile-options` reports for the
 * project and keep this union for the fallback that endpoint's contract asks for
 * when the base template has emitted no profiles yet.
 */
export const RUNTIME_PROFILE_METRIC_KEYS: components['schemas']['OptimizationMetric'][] =
  ['latency', 'throughput'];

export function toImageSelectOptions(
  families: AimImageFamily[],
): RuntimeProfileSelectOption[] {
  return families.map((family) => ({
    key: family.familyId,
    label: family.displayName,
  }));
}

/** Image families exposed in runtime profile forms (excludes automatic). */
export function toSelectableImageSelectOptions(
  families: AimImageFamily[],
): RuntimeProfileSelectOption[] {
  return toImageSelectOptions(families).filter(
    (option) => option.key !== AUTOMATIC_IMAGE_FAMILY_ID,
  );
}

export function toTagSelectOptions(
  families: AimImageFamily[],
  selectedFamilyId: string,
): RuntimeProfileSelectOption[] {
  if (selectedFamilyId === AUTOMATIC_IMAGE_FAMILY_ID) {
    return [];
  }
  const family = families.find((entry) => entry.familyId === selectedFamilyId);
  if (!family?.repository) {
    return [];
  }
  return (family.tags ?? []).map((tag: string) => ({ key: tag, label: tag }));
}

export function toAcceleratorSelectOptions(
  accelerators: ClusterAccelerator[],
  resolveModelLabel?: (model: string) => string,
): RuntimeProfileSelectOption[] {
  return accelerators.map((entry) => ({
    key: entry.deviceId,
    label:
      entry.productName?.trim() ||
      (entry.acceleratorModel?.trim()
        ? (resolveModelLabel?.(entry.acceleratorModel.trim()) ??
          entry.acceleratorModel.trim())
        : ''),
  }));
}

/**
 * Accelerator types exposed by the cluster accelerators API, de-duplicated in
 * first-seen order.
 */
export function toAcceleratorTypeSelectOptions(
  accelerators: ClusterAccelerator[],
): RuntimeProfileSelectOption[] {
  const seen = new Set<string>();
  const options: RuntimeProfileSelectOption[] = [];
  for (const entry of accelerators) {
    const type = normalizeAcceleratorType(entry.acceleratorType);
    if (!type || seen.has(type)) {
      continue;
    }
    seen.add(type);
    options.push({
      key: type,
      label: toAcceleratorTypeLabel(type),
    });
  }
  return options;
}

/** Lowercase form of accelerator type (`cpu`, `gpu`, etc.) for comparisons. */
export function acceleratorTypeKey(type: string | null | undefined): string {
  return normalizeAcceleratorType(type);
}

export function findImageFamily(
  families: AimImageFamily[],
  familyId: string,
): AimImageFamily | undefined {
  return families.find((family) => family.familyId === familyId);
}

/** First non-automatic image family with a repository, in catalog order. */
export function getFirstSelectableImageFamily(
  families: AimImageFamily[],
): AimImageFamily | undefined {
  return families.find(
    (family) =>
      family.familyId !== AUTOMATIC_IMAGE_FAMILY_ID && family.repository,
  );
}

function parseVersionTagParts(tag: string): number[] {
  const normalized = tag.trim().replace(/^[vV]/, '');
  if (normalized === 'latest') {
    return [Number.MAX_SAFE_INTEGER];
  }
  const parts: number[] = [];
  for (const segment of normalized.split(/[.-]/)) {
    const match = segment.match(/^\d+/);
    if (match) {
      parts.push(Number(match[0]));
    }
  }
  return parts.length > 0 ? parts : [0];
}

function compareVersionTags(a: string, b: string): number {
  const aParts = parseVersionTagParts(a);
  const bParts = parseVersionTagParts(b);
  const length = Math.max(aParts.length, bParts.length);
  for (let index = 0; index < length; index += 1) {
    const diff = (aParts[index] ?? 0) - (bParts[index] ?? 0);
    if (diff !== 0) {
      return diff;
    }
  }
  return a.localeCompare(b);
}

/** Picks the newest semver-like tag from a family catalog entry. */
export function getLatestImageTag(tags: string[] | undefined): string {
  if (!tags || tags.length === 0) {
    return '';
  }
  if (tags.length === 1) {
    return tags[0];
  }
  return [...tags].sort(compareVersionTags).at(-1) ?? tags[0];
}

export function getDefaultImageFamilySelection(families: AimImageFamily[]): {
  familyId: string;
  tag: string;
} {
  const family = getFirstSelectableImageFamily(families);
  if (!family) {
    return { familyId: '', tag: '' };
  }
  return {
    familyId: family.familyId,
    tag: getLatestImageTag(family.tags),
  };
}

/**
 * Combines repository and tag into a container image ref (`repo:tag`).
 * Preserves an embedded tag when the repository string already includes one.
 */
export function buildContainerImageRef(
  repository: string,
  tag: string,
): string {
  const image = repository.trim();
  const version = tag.trim();
  if (!image) return '';
  const tagSeparator = image.lastIndexOf(':');
  const hasEmbeddedTag = tagSeparator > -1 && tagSeparator > image.indexOf('/');
  if (hasEmbeddedTag) return image;
  return version ? `${image}:${version}` : image;
}

/**
 * Resolves the onboard image ref from catalog metadata. Automatic selection
 * omits a concrete image so the backend/aim-engine default applies; the
 * interim onboard adapter supplies a fallback ref when the API requires one.
 */
export function resolveProfileImage(
  familyId: string,
  tag: string,
  families: AimImageFamily[],
): string | undefined {
  if (familyId === AUTOMATIC_IMAGE_FAMILY_ID) {
    return undefined;
  }
  const family = findImageFamily(families, familyId);
  if (!family?.repository) {
    return undefined;
  }
  return buildContainerImageRef(family.repository, tag);
}

function imageRefFromFamily(family: AimImageFamily): string | undefined {
  if (!family.repository) {
    return undefined;
  }
  if (family.tags && family.tags.length > 0) {
    return buildContainerImageRef(
      family.repository,
      getLatestImageTag(family.tags),
    );
  }
  return family.repository;
}

/** Fallback image ref when onboard requires `image` but no concrete ref was resolved. */
export function resolveDefaultOnboardImageRef(
  families: AimImageFamily[],
): string {
  const catalogFamily = getFirstSelectableImageFamily(families);
  const catalogRef = catalogFamily
    ? imageRefFromFamily(catalogFamily)
    : undefined;
  if (catalogRef) {
    return catalogRef;
  }

  return 'amdenterpriseai/aim-base';
}

export function getDefaultAcceleratorDeviceId(
  accelerators: ClusterAccelerator[],
): string {
  return accelerators[0]?.deviceId ?? '';
}

/**
 * Base-template supported counts capped by the cluster's allocatable device
 * count (unsupported sizes leave the profile `NotAvailable`). Falls back to the
 * full supported set if the cap empties it, so incomplete capacity data never
 * blocks onboarding. Returns `[]` when no supported counts are known.
 */
export function supportedAcceleratorCounts(
  baseCounts: number[],
  allocatableCount: number,
): number[] {
  const supported = Array.from(new Set(baseCounts))
    .filter((count) => Number.isInteger(count) && count > 0)
    .sort((a, b) => a - b);
  if (supported.length === 0) {
    return [];
  }
  const capped =
    allocatableCount > 0
      ? supported.filter((count) => count <= allocatableCount)
      : supported;
  return capped.length > 0 ? capped : supported;
}

/** Map a form device id to the catalog's canonical `acceleratorModel`. */
export function deviceIdToAcceleratorModel(
  deviceId: string,
  accelerators: ClusterAccelerator[],
): string {
  if (!deviceId) {
    return '';
  }
  const match = accelerators.find((entry) => entry.deviceId === deviceId);
  return match?.acceleratorModel ?? '';
}

/** Map a persisted `acceleratorModel` back to the form's device id for edit prefill. */
export function acceleratorModelToDeviceId(
  model: string | null | undefined,
  accelerators: ClusterAccelerator[],
): string {
  if (!model) {
    return '';
  }
  return (
    accelerators.find((entry) => entry.acceleratorModel === model)?.deviceId ??
    ''
  );
}

type RuntimeProfileCombination =
  components['schemas']['RuntimeProfileCombination'];

/** A partial four-axis selection; an absent axis is treated as "not yet chosen". */
export type RuntimeAxisSelection = {
  acceleratorModel?: string;
  acceleratorCount?: number;
  precision?: string;
  metric?: string;
};

/** The values still reachable per axis, given the current selection. */
export type ReachableRuntimeAxes = {
  acceleratorModels: string[];
  acceleratorCounts: number[];
  precisions: string[];
  metrics: string[];
};

const uniqueStrings = (values: string[]): string[] =>
  Array.from(new Set(values)).sort();

const uniqueNumbers = (values: number[]): number[] =>
  Array.from(new Set(values)).sort((a, b) => a - b);

/**
 * Narrows the four runtime axes to the combinations a base template actually
 * emits. The per-axis option lists say which values exist but not which coexist,
 * and a profile create/update must resolve its axes to exactly one base profile;
 * offering the cartesian product lets the form build a tuple the base never emits
 * (rejected with 400). This constrains each axis to values reachable from the
 * current selection.
 *
 * Axes cascade in priority order (model → count → precision → metric): each axis
 * is filtered by the higher-priority axes only, so its list never depends on a
 * lower-priority choice. A selected value that is not reachable given the
 * higher-priority axes is ignored rather than emptying the downstream lists, so
 * selectors never flash empty while the snap effects converge the selection back
 * onto a valid tuple.
 */
export function reachableRuntimeAxes(
  combinations: RuntimeProfileCombination[],
  selection: RuntimeAxisSelection,
): ReachableRuntimeAxes {
  const acceleratorModels = uniqueStrings(
    combinations.map((combination) => combination.acceleratorModel),
  );
  const model =
    selection.acceleratorModel &&
    acceleratorModels.includes(selection.acceleratorModel)
      ? selection.acceleratorModel
      : undefined;
  const byModel = model
    ? combinations.filter(
        (combination) => combination.acceleratorModel === model,
      )
    : combinations;
  const acceleratorCounts = uniqueNumbers(
    byModel.map((combination) => combination.acceleratorCount),
  );
  const count =
    selection.acceleratorCount != null &&
    acceleratorCounts.includes(selection.acceleratorCount)
      ? selection.acceleratorCount
      : undefined;
  const byCount =
    count != null
      ? byModel.filter((combination) => combination.acceleratorCount === count)
      : byModel;
  const precisions = uniqueStrings(
    byCount.map((combination) => combination.precision),
  );
  const precision =
    selection.precision && precisions.includes(selection.precision)
      ? selection.precision
      : undefined;
  const byPrecision = precision
    ? byCount.filter((combination) => combination.precision === precision)
    : byCount;
  const metrics = uniqueStrings(
    byPrecision.map((combination) => combination.metric),
  );
  return { acceleratorModels, acceleratorCounts, precisions, metrics };
}

/** Minimal matrix shape both runtime-options payloads share for readiness. */
type RuntimeMatrix = {
  combinations: RuntimeProfileCombination[];
  profilesAvailable: boolean;
};

const combinationKey = (combination: RuntimeProfileCombination): string =>
  [
    combination.acceleratorModel,
    combination.acceleratorCount,
    combination.precision,
    combination.metric,
  ].join('\u0000');

/** Combinations present in both matrices — the tuples the resolver accepts and the image emits. */
export function intersectCombinations(
  authoritative: RuntimeProfileCombination[],
  refining: RuntimeProfileCombination[],
): RuntimeProfileCombination[] {
  const refiningKeys = new Set(refining.map(combinationKey));
  return authoritative.filter((combination) =>
    refiningKeys.has(combinationKey(combination)),
  );
}

/**
 * Why the runtime selectors offer no valid choice, or `null` when they are
 * usable (or a safe static fallback applies). A non-null value must block the
 * save: submitting would resolve against no base profile and be rejected 400.
 *
 * - `noValidCombinations`: the base emitted profiles but none resolves to a
 *   single tuple (all ambiguous or incomplete) — the form must not fall back to
 *   the broad per-axis lists.
 *
 * The create/update resolver validates against the namespace base-role profiles,
 * so the namespace matrix is the authoritative gate; it is never relaxed by the
 * selected image's matrix (which only refines which options are shown). The
 * image matrix blocks only when the namespace has emitted nothing yet and the
 * loaded image is itself ambiguous-only, so the onboard wizard cannot pick an
 * unresolvable combination.
 */
export type RuntimeSelectionBlock = null | 'noValidCombinations';

const matrixBlock = (matrix: RuntimeMatrix | null): RuntimeSelectionBlock => {
  if (matrix && matrix.combinations.length > 0) return null;
  return matrix?.profilesAvailable ? 'noValidCombinations' : null;
};

export function runtimeSelectionBlock(params: {
  imageSelected: boolean;
  baseImageLoading: boolean;
  baseImageError: boolean;
  baseImageMatrix: RuntimeMatrix | null;
  namespaceMatrix: RuntimeMatrix | null;
}): RuntimeSelectionBlock {
  const namespaceBlock = matrixBlock(params.namespaceMatrix);
  if (namespaceBlock) {
    return namespaceBlock;
  }
  // Namespace has resolvable combinations, or emitted nothing yet. Only in the
  // latter (fallback) case does a settled, ambiguous-only image matrix block, so
  // the wizard cannot pick a combination that image cannot resolve.
  if (
    !params.namespaceMatrix?.profilesAvailable &&
    params.imageSelected &&
    !params.baseImageLoading &&
    !params.baseImageError &&
    params.baseImageMatrix &&
    params.baseImageMatrix.combinations.length === 0 &&
    params.baseImageMatrix.profilesAvailable
  ) {
    return 'noValidCombinations';
  }
  return null;
}
