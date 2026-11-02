// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useQuery } from '@tanstack/react-query';

import {
  customModelNamesFromServices,
  customModelServices,
  resolveCustomProfileDeployments,
  type CustomProfileDeployment,
} from '@/lib/app/custom-profiles';
import type { AIMService } from '@/types/aims';

const EMPTY_DEPLOYMENTS = new Map<string, CustomProfileDeployment>();

/**
 * Returns an `AIMService id → pinned custom profile` map for the custom-model
 * deployments among `services`, carrying both the authored label and the
 * profile's axes.
 *
 * Non-custom deployments are absent from the map; callers resolve those through
 * the profile catalog instead. The query is keyed on the model names and the
 * *custom-model* deployment ids only — so a second deployment of an already-listed
 * model still refreshes the map, without churning every time an unrelated
 * (non-custom) deployment comes or goes.
 */
export const useCustomProfileDeployments = ({
  services,
  project,
}: {
  services: AIMService[];
  project: string | null | undefined;
}): {
  profileByServiceId: Map<string, CustomProfileDeployment>;
  isLoading: boolean;
} => {
  const customServices = customModelServices(services);
  const modelNames = customModelNamesFromServices(customServices);
  const serviceIds = customServices
    .map((service) => service.id)
    .filter((id): id is string => !!id)
    .sort();
  const { data, isLoading } = useQuery({
    queryKey: [
      'project',
      project,
      'custom-profile-deployments',
      modelNames,
      serviceIds,
    ],
    queryFn: () => resolveCustomProfileDeployments(project!, modelNames),
    enabled: !!project && modelNames.length > 0,
  });

  return { profileByServiceId: data ?? EMPTY_DEPLOYMENTS, isLoading };
};
