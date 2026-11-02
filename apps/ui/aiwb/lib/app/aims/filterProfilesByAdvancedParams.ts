// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { AIMClusterProfile } from '@/types/aims';

/** Form sentinel: control does not narrow profiles for that dimension (automatic selection). */
export const ADVANCED_PARAM_AUTOMATIC = '__automatic__';

export const formatAccelerator = (profile: AIMClusterProfile): string => {
  const gpu = profile.spec?.acceleratorModel;
  const count = profile.spec?.acceleratorCount;
  if (!gpu) return '—';
  return count == null ? gpu : `${gpu} × ${count}`;
};

export const formatClass = (type?: string): string =>
  type ? type.charAt(0).toUpperCase() + type.slice(1) : '—';

export type FilterProfilesByAdvancedParamsFilters = {
  selectedMetric?: string;
  profileName?: string;
  optimizationClass?: string;
  gpuModel?: string;
  precision?: string;
  gpuCount?: string;
};

/**
 * Narrows profiles for the profile dropdown using metric + advanced profile fields.
 *
 * **Automatic** (`ADVANCED_PARAM_AUTOMATIC`): that control is not used to filter; deploy may
 * choose automatically for that dimension. A field is also treated as automatic when empty.
 *
 * **Order of checks** (profile is excluded on first failed check):
 * 1. Metric — if the user selected a metric, `spec.metric` must match.
 * 2. If optimization class, accelerator model, precision, and accelerator count are all
 *    automatic → keep any profile that passed (1).
 * 3. Otherwise require equality on each non-automatic field vs `spec`: type
 *    (optimization class), acceleratorModel, precision, acceleratorCount (compared as
 *    string to form value).
 */
export function filterProfilesByAdvancedParams(
  profiles: AIMClusterProfile[],
  filters: FilterProfilesByAdvancedParamsFilters,
): AIMClusterProfile[] {
  if (filters.profileName && filters.profileName !== ADVANCED_PARAM_AUTOMATIC) {
    const match = profiles.find(
      (profile) => profile.metadata.name === filters.profileName,
    );
    return match ? [match] : [];
  }
  const isAutomatic = (v: string | undefined) =>
    !v || v === ADVANCED_PARAM_AUTOMATIC;
  const matchesOrAutomatic = (
    selected: string | undefined,
    actual: string | null | undefined,
  ) => isAutomatic(selected) || actual === selected;

  const { selectedMetric, optimizationClass, gpuModel, precision, gpuCount } =
    filters;

  const allFiltersAutomatic =
    isAutomatic(optimizationClass) &&
    isAutomatic(gpuModel) &&
    isAutomatic(precision) &&
    isAutomatic(gpuCount);

  const metricFiltered = profiles.filter((p) => {
    if (!selectedMetric || selectedMetric === '') return true;
    return p.spec?.metric === selectedMetric;
  });

  if (allFiltersAutomatic) return metricFiltered;

  return metricFiltered.filter((p) => {
    const spec = p.spec;
    return (
      matchesOrAutomatic(optimizationClass, spec?.type) &&
      matchesOrAutomatic(gpuModel, spec?.acceleratorModel) &&
      matchesOrAutomatic(precision, spec?.precision) &&
      (isAutomatic(gpuCount) || String(spec?.acceleratorCount) === gpuCount)
    );
  });
}
