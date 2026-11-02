// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { TFunction } from 'i18next';
import { getMetricTranslationKey } from './aims';

export type ModelProfileSubtitleInput = {
  imageVersion?: string;
  metric?: string;
  gpu?: string | null;
  templateGpuCount?: number | null;
  acceleratorType?: string | null;
  precision?: string | null;
  /** Authored profile label, set only for custom-model deployments. */
  profileDisplayName?: string | null;
};

type DeploymentNameInput = {
  displayName?: string | null;
  resourceName?: string | null;
  canonicalName?: string | null;
  imageVersion?: string | null;
};

/**
 * Shared deployment-name rule used by list/table/select surfaces.
 *
 * Prefer a user-entered deploy name when it differs from the K8s resource
 * name. Otherwise fall back to canonical model name (+ optional version).
 */
export function resolveModelDeploymentName({
  displayName,
  resourceName,
  canonicalName,
  imageVersion,
}: DeploymentNameInput): string {
  const normalizedDisplayName = displayName?.trim();
  const normalizedResourceName = resourceName?.trim();
  const normalizedCanonicalName = canonicalName?.trim();
  const normalizedImageVersion = imageVersion?.trim();
  const canonicalWithVersion = normalizedCanonicalName
    ? `${normalizedCanonicalName} ${
        normalizedImageVersion ? `(${normalizedImageVersion})` : ''
      }`.trim()
    : '';

  if (
    normalizedDisplayName &&
    normalizedResourceName &&
    normalizedDisplayName !== normalizedResourceName
  ) {
    return normalizedDisplayName;
  }
  if (canonicalWithVersion) return canonicalWithVersion;
  if (normalizedDisplayName) return normalizedDisplayName;
  return normalizedResourceName ?? '';
}

/** Same accelerator count label as tables and {@link ModelProfileSummary} (e.g. 8x GPU, 8x CPU). */
export function formatTemplateGpuCount(
  count: number,
  acceleratorType?: string | null,
): string {
  return acceleratorType?.trim().toLowerCase() === 'cpu'
    ? `${count}x CPU`
    : `${count}x GPU`;
}

/**
 * Subtitle line for model deployment selects (version · metric · hardware · …).
 *
 * A custom model's profiles are what distinguish its deployments from each
 * other, and several can share the same hardware axes, so the authored label
 * identifies them where those axes would not.
 */
export function formatModelDeploymentSubtitle(
  t: TFunction<'models'>,
  info: ModelProfileSubtitleInput,
): string {
  if (info.profileDisplayName) {
    return info.profileDisplayName;
  }
  const metricLabel = info.metric
    ? t(getMetricTranslationKey(info.metric), {
        ns: 'models',
        defaultValue: info.metric,
      })
    : '';
  const countPart =
    info.templateGpuCount != null
      ? formatTemplateGpuCount(info.templateGpuCount, info.acceleratorType)
      : null;
  const parts = [
    info.imageVersion,
    metricLabel,
    info.gpu,
    countPart,
    info.precision,
  ].filter((p): p is string => Boolean(p && String(p).trim() !== ''));
  return parts.join(' · ');
}
