// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import {
  resolvedProfileQuery,
  useProfileSpecsForServices,
} from '@/hooks/useProfileSpecsForServices';
import { profileKey } from '@/lib/app/aims/profileKey';
import {
  getAimClusterProfileByName,
  getAimClusterProfilesByAimIds,
  getProjectAimProfileByName,
  getProjectAimProfilesByAimIds,
} from '@/lib/app/aims';
import type {
  AIMClusterProfile,
  AIMProfile,
  AIMProfileSpec,
} from '@/types/aims';

vi.mock('@/lib/app/aims', () => ({
  getAimClusterProfileByName: vi.fn(),
  getAimClusterProfilesByAimIds: vi.fn(),
  getProjectAimProfileByName: vi.fn(),
  getProjectAimProfilesByAimIds: vi.fn(),
}));

const wrapper =
  (client: QueryClient) =>
  ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

const newClient = () =>
  new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });

const buildClusterProfile = (
  name: string,
  spec: Partial<AIMProfileSpec> = {},
): AIMClusterProfile =>
  ({
    metadata: { name, labels: {} },
    spec: spec as AIMProfileSpec,
    status: { status: 'Ready' },
  }) as AIMClusterProfile;

const buildNamespaceProfile = (
  name: string,
  spec: Partial<AIMProfileSpec> = {},
): AIMProfile =>
  ({
    metadata: { name, labels: {} },
    spec: spec as AIMProfileSpec,
    status: { status: 'Ready' },
  }) as AIMProfile;

describe('useProfileSpecsForServices', () => {
  it('does not fetch when aimIds is empty', async () => {
    const client = newClient();
    const { result } = renderHook(
      () => useProfileSpecsForServices({ aimIds: [], project: 'p1' }),
      { wrapper: wrapper(client) },
    );
    // Both queries self-gate on `aimIds.length > 0`; neither fetcher should
    // fire and the returned map must be empty.
    expect(getAimClusterProfilesByAimIds).not.toHaveBeenCalled();
    expect(getProjectAimProfilesByAimIds).not.toHaveBeenCalled();
    expect(result.current.specByName.size).toBe(0);
  });

  it('keeps cluster and namespace profiles with the same name in separate map entries', async () => {
    const clusterSpec = {
      aimId: 'm',
      precision: 'fp16',
    } as AIMProfileSpec;
    const namespaceSpec = {
      aimId: 'm',
      precision: 'bf16',
    } as AIMProfileSpec;
    vi.mocked(getAimClusterProfilesByAimIds).mockResolvedValue([
      buildClusterProfile('profile-x', clusterSpec),
    ]);
    vi.mocked(getProjectAimProfilesByAimIds).mockResolvedValue([
      buildNamespaceProfile('profile-x', namespaceSpec),
    ]);

    const client = newClient();
    const { result } = renderHook(
      () => useProfileSpecsForServices({ aimIds: ['a1'], project: 'p1' }),
      { wrapper: wrapper(client) },
    );

    await waitFor(() => {
      expect(result.current.specByName.size).toBe(3);
    });
    // Each scope occupies its own key, so a cluster-scoped deployment is judged
    // against the cluster profile and a namespace-scoped one against its own.
    expect(
      result.current.specByName.get(profileKey('Cluster', 'profile-x')),
    ).toEqual(clusterSpec);
    expect(
      result.current.specByName.get(profileKey('Namespace', 'profile-x')),
    ).toEqual(namespaceSpec);
  });

  it('resolves a cluster-scoped deployment against the cluster profile when a namesake namespace profile exists', async () => {
    const clusterSpec = {
      aimId: 'cluster-model',
      precision: 'fp16',
    } as AIMProfileSpec;
    const namespaceSpec = {
      aimId: 'namespace-model',
      precision: 'bf16',
    } as AIMProfileSpec;
    vi.mocked(getAimClusterProfilesByAimIds).mockResolvedValue([
      buildClusterProfile('shared-name', clusterSpec),
    ]);
    vi.mocked(getProjectAimProfilesByAimIds).mockResolvedValue([
      buildNamespaceProfile('shared-name', namespaceSpec),
    ]);

    const client = newClient();
    const { result } = renderHook(
      () => useProfileSpecsForServices({ aimIds: ['a1'], project: 'p1' }),
      { wrapper: wrapper(client) },
    );

    await waitFor(() => {
      expect(result.current.specByName.size).toBe(3);
    });
    // A cluster-scoped deployment that carries scope='Cluster' in its
    // resolvedProfile must find the cluster spec, not the namespace namesake.
    expect(
      result.current.specByName.get(profileKey('Cluster', 'shared-name')),
    ).toEqual(clusterSpec);
    expect(
      result.current.specByName.get(profileKey('Namespace', 'shared-name')),
    ).toEqual(namespaceSpec);
    // The bare key is reached only by a reference stating no scope, and then
    // resolves namespace-before-cluster the way the API's own lookup does.
    expect(
      result.current.specByName.get(profileKey(null, 'shared-name')),
    ).toEqual(namespaceSpec);
  });

  it('skips the namespace fetcher when project is null', async () => {
    vi.mocked(getAimClusterProfilesByAimIds).mockResolvedValue([]);
    vi.mocked(getProjectAimProfilesByAimIds).mockResolvedValue([]);

    const client = newClient();
    renderHook(
      () => useProfileSpecsForServices({ aimIds: ['a1'], project: null }),
      { wrapper: wrapper(client) },
    );

    await waitFor(() => {
      expect(getAimClusterProfilesByAimIds).toHaveBeenCalledTimes(1);
    });
    expect(getAimClusterProfilesByAimIds).toHaveBeenCalledWith(['a1']);
    expect(getProjectAimProfilesByAimIds).not.toHaveBeenCalled();
  });

  it('fetches resolved profiles missing from the catalogs by name', async () => {
    const namespaceSpec = {
      aimId: 'a1',
      precision: 'bf16',
    } as AIMProfileSpec;
    const clusterSpec = {
      aimId: 'a1',
      precision: 'fp16',
    } as AIMProfileSpec;
    vi.mocked(getAimClusterProfilesByAimIds).mockResolvedValue([]);
    vi.mocked(getProjectAimProfilesByAimIds).mockResolvedValue([]);
    vi.mocked(getProjectAimProfileByName).mockResolvedValue(
      buildNamespaceProfile('namespace-overlay', namespaceSpec),
    );
    vi.mocked(getAimClusterProfileByName).mockResolvedValue(
      buildClusterProfile('cluster-overlay', clusterSpec),
    );

    const client = newClient();
    const { result } = renderHook(
      () =>
        useProfileSpecsForServices({
          aimIds: ['a1'],
          project: 'p1',
          resolvedProfiles: [
            { name: 'namespace-overlay', scope: 'Namespace' },
            { name: 'cluster-overlay', scope: 'Cluster' },
          ],
        }),
      { wrapper: wrapper(client) },
    );

    await waitFor(() => {
      expect(result.current.specByName.size).toBe(2);
    });
    expect(getProjectAimProfileByName).toHaveBeenCalledWith(
      'p1',
      'namespace-overlay',
    );
    expect(getAimClusterProfileByName).toHaveBeenCalledWith('cluster-overlay');
    expect(
      result.current.specByName.get(
        profileKey('Namespace', 'namespace-overlay'),
      ),
    ).toEqual(namespaceSpec);
    expect(
      result.current.specByName.get(profileKey('Cluster', 'cluster-overlay')),
    ).toEqual(clusterSpec);
  });

  // A reference that names no scope AIWB can act on identifies no single
  // object, so it is read the way the API's own bare-name lookup reads it.
  // Overlay profiles are namespace-scoped and absent from both catalogs, so a
  // cluster-only direct fetch never finds one.
  it.each([
    ['an absent scope', undefined],
    ['Merged', 'Merged'],
    ['Unknown', 'Unknown'],
  ])(
    'resolves a namespace-only profile for %s',
    async (_label, scope: string | undefined) => {
      const namespaceSpec = {
        aimId: 'a1',
        precision: 'bf16',
      } as AIMProfileSpec;
      vi.mocked(getAimClusterProfilesByAimIds).mockResolvedValue([]);
      vi.mocked(getProjectAimProfilesByAimIds).mockResolvedValue([]);
      vi.mocked(getProjectAimProfileByName).mockResolvedValue(
        buildNamespaceProfile('namespace-overlay', namespaceSpec),
      );
      vi.mocked(getAimClusterProfileByName).mockRejectedValue(
        new APIRequestError('not found', 404),
      );

      const client = newClient();
      const { result } = renderHook(
        () =>
          useProfileSpecsForServices({
            aimIds: ['a1'],
            project: 'p1',
            resolvedProfiles: [{ name: 'namespace-overlay', scope }],
          }),
        { wrapper: wrapper(client) },
      );

      await waitFor(() => {
        expect(
          result.current.specByName.get(profileKey(scope, 'namespace-overlay')),
        ).toEqual(namespaceSpec);
      });
      expect(getProjectAimProfileByName).toHaveBeenCalledWith(
        'p1',
        'namespace-overlay',
      );
      expect(result.current.isError).toBe(false);
    },
  );

  it('falls back to the cluster profile when a bare name is not in the project', async () => {
    const clusterSpec = { aimId: 'a1', precision: 'fp16' } as AIMProfileSpec;
    vi.mocked(getAimClusterProfilesByAimIds).mockResolvedValue([]);
    vi.mocked(getProjectAimProfilesByAimIds).mockResolvedValue([]);
    vi.mocked(getProjectAimProfileByName).mockRejectedValue(
      new APIRequestError('not found', 404),
    );
    vi.mocked(getAimClusterProfileByName).mockResolvedValue(
      buildClusterProfile('shared-overlay', clusterSpec),
    );

    const client = newClient();
    const { result } = renderHook(
      () =>
        useProfileSpecsForServices({
          aimIds: ['a1'],
          project: 'p1',
          resolvedProfiles: [{ name: 'shared-overlay', scope: 'Merged' }],
        }),
      { wrapper: wrapper(client) },
    );

    await waitFor(() => {
      expect(
        result.current.specByName.get(profileKey('Merged', 'shared-overlay')),
      ).toEqual(clusterSpec);
    });
    expect(getAimClusterProfileByName).toHaveBeenCalledWith('shared-overlay');
  });

  it('reads only the cluster for a bare name when there is no project to ask', async () => {
    const clusterSpec = { aimId: 'a1', precision: 'fp16' } as AIMProfileSpec;
    vi.mocked(getAimClusterProfilesByAimIds).mockResolvedValue([]);
    vi.mocked(getProjectAimProfilesByAimIds).mockResolvedValue([]);
    vi.mocked(getAimClusterProfileByName).mockResolvedValue(
      buildClusterProfile('shared-overlay', clusterSpec),
    );

    const client = newClient();
    const { result } = renderHook(
      () =>
        useProfileSpecsForServices({
          aimIds: ['a1'],
          project: null,
          resolvedProfiles: [{ name: 'shared-overlay', scope: 'Unknown' }],
        }),
      { wrapper: wrapper(client) },
    );

    await waitFor(() => {
      expect(
        result.current.specByName.get(profileKey('Unknown', 'shared-overlay')),
      ).toEqual(clusterSpec);
    });
    expect(getProjectAimProfileByName).not.toHaveBeenCalled();
  });

  it('does not fetch a bare-scope profile the catalogs already carry', async () => {
    const namespaceSpec = { aimId: 'a1', precision: 'bf16' } as AIMProfileSpec;
    vi.mocked(getAimClusterProfilesByAimIds).mockResolvedValue([
      buildClusterProfile('catalogued', {
        aimId: 'a1',
        precision: 'fp16',
      } as AIMProfileSpec),
    ]);
    vi.mocked(getProjectAimProfilesByAimIds).mockResolvedValue([
      buildNamespaceProfile('catalogued', namespaceSpec),
    ]);

    const client = newClient();
    const { result } = renderHook(
      () =>
        useProfileSpecsForServices({
          aimIds: ['a1'],
          project: 'p1',
          resolvedProfiles: [{ name: 'catalogued', scope: 'Merged' }],
        }),
      { wrapper: wrapper(client) },
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    // The catalog merge already answers a bare name namespace-before-cluster;
    // the direct lookup exists for what the catalogs do not carry.
    expect(
      result.current.specByName.get(profileKey('Merged', 'catalogued')),
    ).toEqual(namespaceSpec);
    expect(getProjectAimProfileByName).not.toHaveBeenCalled();
    expect(getAimClusterProfileByName).not.toHaveBeenCalled();
  });
});

// The rule the details page reads a `status.resolvedProfile` through. It is
// exported precisely so that page does not carry a third hand-written copy of
// it, so it is worth pinning on its own.
describe('resolvedProfileQuery', () => {
  const keyFor = (scope?: string) =>
    JSON.stringify(
      resolvedProfileQuery({ project: 'p1', name: 'shared-name', scope })
        .queryKey,
    );

  it('gives two same-named profiles in different scopes separate cache keys', () => {
    const scoped = [keyFor('Namespace'), keyFor('Cluster'), keyFor('Merged')];

    expect(new Set(scoped).size).toBe(scoped.length);
  });

  it('keys every unactionable scope the same way a bare name is keyed', () => {
    // `Merged`, `Unknown`, an absent scope and a scope a newer engine knows all
    // identify no single object, so they must share one entry rather than
    // fragmenting the cache or colliding with a real scope.
    expect(keyFor(undefined)).toBe(keyFor('Merged'));
    expect(keyFor('Unknown')).toBe(keyFor('Merged'));
    expect(keyFor('SomethingNewer')).toBe(keyFor('Merged'));
    expect(keyFor('Merged')).not.toBe(keyFor('Cluster'));
  });

  it.each([[undefined], ['Merged'], ['Unknown']])(
    'reads a %s-scope reference from the project before the cluster',
    async (scope) => {
      (
        getProjectAimProfileByName as ReturnType<typeof vi.fn>
      ).mockResolvedValue(
        buildNamespaceProfile('shared-name', { modelId: 'namespace-weights' }),
      );

      await resolvedProfileQuery({
        project: 'p1',
        name: 'shared-name',
        scope,
      }).queryFn();

      expect(getProjectAimProfileByName).toHaveBeenCalledWith(
        'p1',
        'shared-name',
      );
      expect(getAimClusterProfileByName).not.toHaveBeenCalled();
    },
  );

  it('falls back to the cluster only on a 404 from the project', async () => {
    (getProjectAimProfileByName as ReturnType<typeof vi.fn>).mockRejectedValue(
      new APIRequestError('not found', 404),
    );
    (getAimClusterProfileByName as ReturnType<typeof vi.fn>).mockResolvedValue(
      buildClusterProfile('shared-name', { modelId: 'cluster-weights' }),
    );

    await resolvedProfileQuery({
      project: 'p1',
      name: 'shared-name',
      scope: 'Merged',
    }).queryFn();

    expect(getAimClusterProfileByName).toHaveBeenCalledWith('shared-name');
  });

  it('keeps an unreadable project answer from becoming a cluster namesake', async () => {
    (getProjectAimProfileByName as ReturnType<typeof vi.fn>).mockRejectedValue(
      new APIRequestError('boom', 500),
    );

    await expect(
      resolvedProfileQuery({
        project: 'p1',
        name: 'shared-name',
        scope: 'Merged',
      }).queryFn(),
    ).rejects.toThrow('boom');
    expect(getAimClusterProfileByName).not.toHaveBeenCalled();
  });

  it('stays disabled until the reference names a profile', () => {
    expect(
      resolvedProfileQuery({ project: 'p1', name: null, scope: 'Merged' })
        .enabled,
    ).toBe(false);
  });
});
