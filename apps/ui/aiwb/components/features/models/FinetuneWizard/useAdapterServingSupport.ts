// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError } from '@amdenterpriseai/utils/app';
import { useQuery } from '@tanstack/react-query';

import { getAimClusterProfiles } from '@/lib/app/aims';
import type { AIMClusterProfile } from '@/types/aims';
import type { FinetunableModel, Model } from '@/types/models';

/**
 * Whether the base model publishes a serving profile that can serve LoRA
 * adapters, so an adapter trained from it would be deployable.
 *
 * `undefined` means unknown rather than unsupported: the catalog is still
 * loading, the lookup failed, or the model publishes no profiles at all.
 * Failing open on unknown is deliberate — only a published "no" withdraws the
 * option, because a model that declares nothing may still be servable and
 * withdrawing it would block runs the platform would happily accept.
 *
 * This wizard is currently the only thing standing between a user and a run
 * whose adapter could never be deployed; the fine-tuning run path does not yet
 * refuse one. The matching server-side refusal is being added there against the
 * same published "no", so the two agree once it lands and this stays a
 * convenience guard rather than the sole one.
 */
export const useAdapterServingSupport = (
  canonicalName: string | undefined,
  model: Model | undefined,
  trainingType: FinetunableModel['trainingType'],
): boolean | undefined => {
  // A recipe that cannot produce an adapter has nothing riding on the answer,
  // so it never asks. A re-fine-tune does ask, and asks about its base: the
  // adapter it produces is declared compatible with the base model's identity
  // rather than its own, so it can only ever attach to deployments of that
  // base — and those are served by the cluster-scoped profiles queried here. A
  // fine-tuned model's own canonical name already resolves to the base it was
  // derived from, which is why the same value answers for both cases.
  const aimId =
    trainingType !== 'lora'
      ? undefined
      : canonicalName || model?.canonicalName || undefined;
  const { data: profiles, isSuccess } = useQuery<AIMClusterProfile[]>({
    queryKey: ['aim-profiles', aimId],
    queryFn: () => getAimClusterProfiles(aimId ?? ''),
    enabled: !!aimId,
    staleTime: Infinity,
    retry: (failureCount, error) => {
      if (error instanceof APIRequestError && error.statusCode === 404) {
        return false;
      }
      return failureCount < 3;
    },
  });
  if (!isSuccess || profiles.length === 0) return undefined;
  return profiles.some(
    (profile) =>
      profile.status?.status === 'Ready' &&
      profile.spec?.features?.includes('adapters'),
  );
};
