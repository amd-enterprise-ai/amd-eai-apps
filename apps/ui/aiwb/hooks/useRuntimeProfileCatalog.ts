// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useQuery, useQueryClient } from '@tanstack/react-query';

import { getAimImages, getClusterAccelerators } from '@/lib/app/cluster';
import { getRuntimeProfileOptions } from '@/lib/app/custom-models';
import type { components } from '@/types/api';
import type { AimImageFamily, ClusterAccelerator } from '@/types/cluster';

type RuntimeProfileOptions = components['schemas']['RuntimeProfileOptions'];

export const RUNTIME_PROFILE_AIM_IMAGES_QUERY_KEY = [
  'cluster',
  'aim-images',
] as const;

export const RUNTIME_PROFILE_ACCELERATORS_QUERY_KEY = [
  'cluster',
  'accelerators',
] as const;

export const RUNTIME_PROFILE_OPTIONS_QUERY_KEY = [
  'project',
  'runtime-profile-options',
] as const;

export type RuntimeProfileCatalogState = {
  project?: string;
  imageFamilies: AimImageFamily[];
  accelerators: ClusterAccelerator[];
  /**
   * Base-template runtime matrix for the project (accelerator models,
   * precisions, counts, metrics, optimization classes) a custom model inherits.
   * Null until loaded or when no project is supplied; consumers fall back to
   * static defaults when its arrays are empty.
   */
  runtimeOptions: RuntimeProfileOptions | null;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  invalidateCatalog: () => void;
};

/**
 * Loads the runtime-profile catalog for the onboard/edit wizard.
 *
 * Cluster image families and accelerators are always fetched. When a `project`
 * is supplied, the project's base-template runtime options are fetched too so
 * the wizard can preset/constrain its runtime selectors; failures there are
 * non-fatal (the wizard degrades to static defaults) and do not flip the
 * catalog into an error state.
 */
export function useRuntimeProfileCatalog(
  project?: string,
): RuntimeProfileCatalogState {
  const queryClient = useQueryClient();
  const aimImagesQuery = useQuery({
    queryKey: RUNTIME_PROFILE_AIM_IMAGES_QUERY_KEY,
    queryFn: getAimImages,
  });
  const acceleratorsQuery = useQuery({
    queryKey: RUNTIME_PROFILE_ACCELERATORS_QUERY_KEY,
    queryFn: getClusterAccelerators,
  });
  const runtimeOptionsQuery = useQuery({
    queryKey: [...RUNTIME_PROFILE_OPTIONS_QUERY_KEY, project],
    queryFn: () => getRuntimeProfileOptions(project as string),
    enabled: Boolean(project),
  });
  const invalidateCatalog = () => {
    void queryClient.invalidateQueries({
      queryKey: RUNTIME_PROFILE_AIM_IMAGES_QUERY_KEY,
    });
    void queryClient.invalidateQueries({
      queryKey: RUNTIME_PROFILE_ACCELERATORS_QUERY_KEY,
    });
    void queryClient.invalidateQueries({
      queryKey: RUNTIME_PROFILE_OPTIONS_QUERY_KEY,
    });
  };
  return {
    project,
    imageFamilies: aimImagesQuery.data?.data ?? [],
    accelerators: acceleratorsQuery.data?.data ?? [],
    runtimeOptions: runtimeOptionsQuery.data ?? null,
    // Fold in the options query so the wizard waits for the runtime matrix before
    // seeding selectors; otherwise it renders "ready" against static defaults and
    // reintroduces the precision/count prefill bug. A disabled (no-project) query
    // reports isLoading false, so this never hangs. Its failures stay out of
    // isError/error below — they are non-fatal and degrade to static defaults.
    isLoading:
      aimImagesQuery.isLoading ||
      acceleratorsQuery.isLoading ||
      runtimeOptionsQuery.isLoading,
    isError: aimImagesQuery.isError || acceleratorsQuery.isError,
    error:
      (aimImagesQuery.error as Error | null) ??
      (acceleratorsQuery.error as Error | null),
    invalidateCatalog,
  };
}
