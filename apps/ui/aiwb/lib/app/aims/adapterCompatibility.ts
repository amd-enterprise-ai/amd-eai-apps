// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { AIMProfileSpec } from '@/types/aims';

/** Profile capability token marking a runtime that can serve LoRA adapters. */
export const ADAPTER_FEATURE = 'adapters';

/**
 * Whether a profile's runtime can serve LoRA adapters at all.
 *
 * `features` is an unordered capability set owned by the engine, so unknown
 * entries are simply ignored rather than treated as an error.
 */
export const isAdapterCapableProfileSpec = (
  spec: AIMProfileSpec | null | undefined,
): boolean => !!spec?.features?.includes(ADAPTER_FEATURE);

/**
 * Whether any of the given profiles can serve the adapter, on either identity.
 *
 * `modelId` is the identity that actually decides this: an adapter is trained
 * against one set of weights, and a profile serves one set. `aimId` is coarser
 * — every quantised variant of a model shares it — so matching on it can admit
 * an adapter the running variant cannot load.
 *
 * It is accepted anyway because nothing on the platform writes a modelId into
 * `compatibleWith` yet; every producer writes an aimId, AIWB's own fine-tuning
 * output included, and on the families where the two differ a modelId-only rule
 * would hide every adapter the platform itself made. This has to be the rule the
 * deploy and attach endpoints apply — `adapter_serves` in
 * `apps/api/aiwb/app/aims/utils.py` — or the wizard hides adapters the API would
 * have accepted. Delete the aimId arm on both sides together, once producers
 * record the profile's modelId.
 *
 * Pass a single-element list to test one already-resolved profile, and the full
 * candidate set when nothing has resolved yet and existence is the strongest
 * signal available.
 */
export function canProfilesServeAdapter({
  adapter,
  profileSpecs,
}: {
  adapter: { compatibleWith: string[] };
  profileSpecs: Array<AIMProfileSpec | null | undefined>;
}): boolean {
  const declared = new Set(adapter.compatibleWith);
  return profileSpecs.some(
    (spec) =>
      isAdapterCapableProfileSpec(spec) &&
      ((!!spec?.modelId && declared.has(spec.modelId)) ||
        (!!spec?.aimId && declared.has(spec.aimId))),
  );
}
