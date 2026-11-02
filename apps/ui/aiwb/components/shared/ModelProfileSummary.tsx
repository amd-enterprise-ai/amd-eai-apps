// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { TFunction } from 'i18next';
import { Fragment } from 'react';
import { IconSquareRotatedAsterisk } from '@tabler/icons-react';

import { formatTemplateGpuCount } from '@/lib/app/modelDeploymentDisplay';
import {
  getMaxSupportedLoraRank,
  getMetricTranslationKey,
} from '@/lib/app/aims';
import { profileKey } from '@/lib/app/aims/profileKey';
import type {
  AIMProfileSpec,
  AIMService,
  ModelProfileSummaryFields,
} from '@/types/aims';

/**
 * Projects an AIMService's resolved-profile spec into the shape consumed by
 * `ModelProfileSummary` and `modelDeploymentDisplay`.
 *
 * The aim-engine status only carries the resolved profile's *name*; AIWB no
 * longer enriches the spec on the service response. Callers pass a
 * name → spec lookup built from the AIMProfile catalog endpoints — typically
 * via the `useProfileSpecsForServices` hook (which wraps
 * `getAimClusterProfilesByAimIds` and `getProjectAimProfilesByAimIds`).
 *
 * Returns a profile when either half is present: the catalog spec's hardware
 * axes, or the deployment's own max LoRA rank (from `spec.adapterRuntime`,
 * independent of the resolved profile). Only null when neither resolves —
 * e.g. the engine hasn't stamped `resolvedProfile` yet and the service has
 * no configured max rank — since either half alone is still worth showing.
 */
export function toProfileSummaryFields(
  service: AIMService | undefined | null,
  profileSpecByName: Map<string, AIMProfileSpec> | null | undefined,
): ModelProfileSummaryFields | null {
  const ref = service?.status?.resolvedProfile;
  const name = ref?.name;
  const spec = name
    ? profileSpecByName?.get(profileKey(ref?.scope, name))
    : undefined;
  const maxLoraRank = getMaxSupportedLoraRank(service?.spec);
  if (!spec && maxLoraRank == null) return null;
  return {
    metric: spec?.metric ?? null,
    gpu: spec?.acceleratorModel ?? null,
    templateGpuCount: spec?.acceleratorCount ?? null,
    acceleratorType: spec?.acceleratorType ?? null,
    precision: spec?.precision ?? null,
    maxLoraRank,
  };
}

type Props = {
  profile: ModelProfileSummaryFields | null | undefined;
  t: TFunction<'models'>;
};

/** Second line under deployment name: profile label (custom models) or metric • GPU • count • precision. */
export function ModelProfileSummary({ profile, t }: Props) {
  if (!profile) {
    return null;
  }
  const parts: string[] = [];
  if (profile.profileDisplayName) {
    parts.push(profile.profileDisplayName);
  } else {
    if (profile.metric) {
      parts.push(
        String(
          t(getMetricTranslationKey(profile.metric), {
            defaultValue: profile.metric,
          }),
        ),
      );
    }
    if (profile.gpu) {
      parts.push(profile.gpu);
    }
    if (profile.templateGpuCount != null) {
      parts.push(
        formatTemplateGpuCount(
          profile.templateGpuCount,
          profile.acceleratorType,
        ),
      );
    }
    if (profile.precision) {
      parts.push(profile.precision);
    }
  }
  if (parts.length === 0 && profile.maxLoraRank == null) {
    return null;
  }
  return (
    <span className="flex flex-wrap items-center gap-1 text-xs text-muted">
      {parts.map((part, index) => (
        <Fragment key={`${part}-${index}`}>
          {index > 0 ? <span aria-hidden>•</span> : null}
          <span>{part}</span>
        </Fragment>
      ))}
      {profile.maxLoraRank != null ? (
        <>
          {parts.length > 0 ? <span aria-hidden>•</span> : null}
          <span className="inline-flex items-center gap-1">
            <IconSquareRotatedAsterisk aria-hidden size={14} />
            {t('profileSummary.maxRank', { rank: profile.maxLoraRank })}
          </span>
        </>
      ) : null}
    </span>
  );
}
