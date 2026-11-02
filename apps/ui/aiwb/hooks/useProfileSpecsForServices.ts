// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useMemo } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import {
  getAimClusterProfileByName,
  getAimClusterProfilesByAimIds,
  getProjectAimProfileByName,
  getProjectAimProfilesByAimIds,
} from '@/lib/app/aims';
import { profileKey } from '@/lib/app/aims/profileKey';
import type {
  AIMClusterProfile,
  AIMProfile,
  AIMProfileSpec,
} from '@/types/aims';

/** Profile specs are effectively immutable for the session — they only
 *  change when the aim-engine / chart is reinstalled. `Infinity` keeps
 *  React Query from ever marking the data stale, so workload polling never
 *  re-fetches profiles. */
const PROFILE_CACHE_MS = Infinity;

/**
 * The profile a bare name refers to: the project's own copy, else the
 * cluster-wide one.
 *
 * Only a 404 means the project does not have it; any other failure is the
 * project's answer being unreadable rather than absent, and falling through to
 * the cluster there would hand back a namesake's spec as if it were the one the
 * deployment runs.
 */
const fetchProfileNamespaceFirst = async (
  project: string,
  name: string,
): Promise<AIMProfile | AIMClusterProfile> => {
  try {
    return await getProjectAimProfileByName(project, name);
  } catch (error) {
    if (error instanceof APIRequestError && error.statusCode === 404) {
      return getAimClusterProfileByName(name);
    }
    throw error;
  }
};

/**
 * The query a single resolved-profile reference is read through.
 *
 * Exported because the rule is not the hook's own: any caller resolving a
 * `status.resolvedProfile` has to apply it, and a second hand-written copy is
 * what let the details page send `Merged`, `Unknown` and absent-scope
 * references straight to the cluster catalog — handing back a namesake's spec,
 * or nothing, wherever the profile was a namespace-only overlay.
 *
 * The key carries the scope it was resolved under for the same reason
 * `profileKey` does: two same-named profiles in different scopes are different
 * objects and must not share a cache entry.
 */
export const resolvedProfileQuery = ({
  project,
  name,
  scope,
}: {
  project: string | null | undefined;
  name: string | null | undefined;
  scope?: string | null;
}) => {
  const isClusterProfile = scope === 'Cluster';
  const isNamespaceProfile = scope === 'Namespace';
  // A reference stating no scope AIWB can act on — absent, `Merged`,
  // `Unknown`, or a scope a newer engine knows and this code does not —
  // identifies no single object, so it is read the way the API's own bare-name
  // lookup reads it: the project's own copy first, the cluster-wide one only
  // when the project has none. Going straight to the cluster would miss every
  // namespace-scoped overlay profile.
  const isBareLookup = !isClusterProfile && !isNamespaceProfile && !!project;
  return {
    queryKey: isNamespaceProfile
      ? ['aim-profile', 'project', project, name]
      : isBareLookup
        ? ['aim-profile', 'bare', project, name]
        : ['aim-profile', 'cluster', name],
    queryFn: () => {
      if (isNamespaceProfile)
        return getProjectAimProfileByName(project!, name!);
      if (!isBareLookup) return getAimClusterProfileByName(name!);
      return fetchProfileNamespaceFirst(project!, name!);
    },
    enabled: !!name && (!isNamespaceProfile || !!project),
    staleTime: PROFILE_CACHE_MS,
  };
};

/**
 * Returns a `(scope + profile name) → spec` map by fetching both profile
 * catalogs (AIMClusterProfile + AIMProfile) for the given aimIds and indexing
 * them by a composite `profileKey(scope, name)`.
 *
 * Callers compute the aimId union at the call site — typically the
 * `status.aimId` of every cluster model from `useInferenceModelsByName` plus
 * every fine-tuned AIMModel CR — and must wait for those upstream fetches to
 * settle before passing the result, otherwise the partially-populated array
 * will trigger one profile fetch per per-name fan-out completion.
 *
 * AIMService-owned overlay profiles are excluded from the catalogs, so
 * missing resolved-profile names are fetched directly.
 *
 * A reference stating no scope AIWB can act on is served by a bare-name entry,
 * which resolves namespace-before-cluster the way the API's own bare-name
 * lookup does. Only such a reference reaches it: one that names its scope is
 * answered by that scope's entry and can never be handed a namesake's spec.
 */
export const useProfileSpecsForServices = ({
  aimIds,
  project,
  resolvedProfiles = [],
}: {
  aimIds: string[];
  project: string | null | undefined;
  resolvedProfiles?: Array<
    { name?: string | null; scope?: string | null } | null | undefined
  >;
}): {
  specByName: Map<string, AIMProfileSpec>;
  isLoading: boolean;
  isError: boolean;
  refetch: () => Promise<unknown>;
} => {
  // Each query self-gates on `length > 0` — when the caller is still waiting
  // for upstream models to land it passes `[]` and no fetch fires.
  const {
    data: clusterProfiles = [],
    isLoading: isLoadingCluster,
    isError: isClusterError,
    refetch: refetchCluster,
  } = useQuery({
    queryKey: ['aim-cluster-profiles', aimIds],
    queryFn: () => getAimClusterProfilesByAimIds(aimIds),
    enabled: aimIds.length > 0,
    staleTime: PROFILE_CACHE_MS,
  });

  const {
    data: namespaceProfiles = [],
    isLoading: isLoadingNamespace,
    isError: isNamespaceError,
    refetch: refetchNamespace,
  } = useQuery({
    queryKey: ['project', project, 'aim-profiles', aimIds],
    queryFn: () => getProjectAimProfilesByAimIds(project!, aimIds),
    enabled: !!project && aimIds.length > 0,
    staleTime: PROFILE_CACHE_MS,
  });

  const catalogSpecByName = useMemo((): Map<string, AIMProfileSpec> => {
    const map = new Map<string, AIMProfileSpec>();
    for (const p of clusterProfiles) {
      if (p.metadata.name && p.spec) {
        map.set(profileKey('Cluster', p.metadata.name), p.spec);
        map.set(profileKey(null, p.metadata.name), p.spec);
      }
    }
    // Second, so a namespace profile wins the bare key: that is the precedence
    // the API's bare-name lookup applies, and it is reached only by references
    // that state no scope of their own.
    for (const p of namespaceProfiles) {
      if (p.metadata.name && p.spec) {
        map.set(profileKey('Namespace', p.metadata.name), p.spec);
        map.set(profileKey(null, p.metadata.name), p.spec);
      }
    }
    return map;
  }, [clusterProfiles, namespaceProfiles]);

  const missingProfiles = useMemo(() => {
    if (isLoadingCluster || isLoadingNamespace) return [];
    return Array.from(
      new Map(
        resolvedProfiles
          .filter(
            (profile): profile is { name: string; scope?: string | null } =>
              !!profile?.name &&
              !catalogSpecByName.has(profileKey(profile.scope, profile.name)),
          )
          .map((profile) => [profileKey(profile.scope, profile.name), profile]),
      ).values(),
    );
  }, [
    catalogSpecByName,
    isLoadingCluster,
    isLoadingNamespace,
    resolvedProfiles,
  ]);
  const profileQueries = useQueries({
    // Overlay profiles are exactly what is absent from the catalogs above, and
    // so are what reaches this fetch in the first place.
    queries: missingProfiles.map(({ name, scope }) =>
      resolvedProfileQuery({ project, name, scope }),
    ),
  });
  const specByName = useMemo(() => {
    const map = new Map(catalogSpecByName);
    for (let i = 0; i < profileQueries.length; i++) {
      const profile = profileQueries[i].data;
      const ref = missingProfiles[i];
      if (profile?.metadata.name && profile.spec && ref) {
        map.set(profileKey(ref.scope, profile.metadata.name), profile.spec);
      }
    }
    return map;
  }, [catalogSpecByName, missingProfiles, profileQueries]);

  // A catalog or per-profile fetch that failed leaves `specByName` empty, which
  // is indistinguishable from "no profile can serve this" to a caller that only
  // sees the map. Callers that draw a conclusion from an empty map need the
  // failure — and a way back out of it — surfaced alongside the data.
  const refetch = () =>
    Promise.all([
      refetchCluster(),
      refetchNamespace(),
      ...profileQueries.map(({ refetch: refetchProfile }) => refetchProfile()),
    ]);

  return {
    specByName,
    isLoading:
      isLoadingCluster ||
      isLoadingNamespace ||
      profileQueries.some(({ isLoading }) => isLoading),
    isError:
      isClusterError ||
      isNamespaceError ||
      profileQueries.some(({ isError }) => isError),
    refetch,
  };
};
