// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { AIMClusterProfile } from '@/types/aims';

/**
 * Label aim-engine stamps on a profile naming the AIM(Cluster)Model that
 * produced it. Mirrors `AIM_PROFILE_SOURCE_MODEL_LABEL` in
 * `apps/api/aiwb/app/aims/constants.py`; keep the two in step.
 *
 * `spec.aimId` only identifies the model architecture, which every version of
 * a model shares, so it cannot tell one published version's profiles from
 * another's. This label is the only per-version provenance on the resource.
 */
export const AIM_PROFILE_SOURCE_MODEL_LABEL = 'aim.eai.amd.com/source-model';

/**
 * Narrows a group-wide profile pool to the profiles published by one model
 * version, identified by its AIMClusterModel resource name
 * (`ParsedAIM.model`).
 *
 * A profile carrying no provenance label is unknown, not evidence of another
 * version, so it is kept: on a cluster whose engine does not stamp the label
 * the result degrades to the unnarrowed pool rather than hiding serving
 * options the version may well own. Dropping is reserved for a label that
 * positively names a different model.
 */
export const filterProfilesBySourceModel = (
  profiles: AIMClusterProfile[],
  modelName: string | null | undefined,
): AIMClusterProfile[] => {
  if (!modelName) {
    return profiles;
  }
  return profiles.filter((profile) => {
    const sourceModel =
      profile.metadata?.labels?.[AIM_PROFILE_SOURCE_MODEL_LABEL];
    return !sourceModel || sourceModel === modelName;
  });
};
