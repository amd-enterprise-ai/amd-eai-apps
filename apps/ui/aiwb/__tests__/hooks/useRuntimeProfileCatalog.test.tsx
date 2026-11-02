// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  RUNTIME_PROFILE_ACCELERATORS_QUERY_KEY,
  RUNTIME_PROFILE_AIM_IMAGES_QUERY_KEY,
  RUNTIME_PROFILE_OPTIONS_QUERY_KEY,
  useRuntimeProfileCatalog,
} from '@/hooks/useRuntimeProfileCatalog';
import { getAimImages, getClusterAccelerators } from '@/lib/app/cluster';
import { getRuntimeProfileOptions } from '@/lib/app/custom-models';

vi.mock('@/lib/app/cluster', () => ({
  getAimImages: vi.fn(),
  getClusterAccelerators: vi.fn(),
}));

vi.mock('@/lib/app/custom-models', () => ({
  getRuntimeProfileOptions: vi.fn(),
}));

const wrapper =
  (client: QueryClient) =>
  ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

describe('useRuntimeProfileCatalog', () => {
  it('loads image families and accelerators', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.mocked(getAimImages).mockResolvedValue({
      data: [
        {
          familyId: 'automatic',
          displayName: 'Automatic',
          repository: null,
          tags: [],
        },
      ],
    });
    vi.mocked(getClusterAccelerators).mockResolvedValue({
      data: [
        {
          acceleratorType: 'gpu',
          acceleratorVendor: 'amd',
          deviceId: '74a1',
          productName: 'AMD Instinct MI300X',
          allocatableCount: 4,
          acceleratorModel: 'MI300X',
        },
      ],
    });
    const { result } = renderHook(() => useRuntimeProfileCatalog(), {
      wrapper: wrapper(client),
    });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.imageFamilies).toHaveLength(1);
    expect(result.current.accelerators).toHaveLength(1);
    expect(result.current.isError).toBe(false);
  });

  it('invalidates all catalog queries on retry', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
    vi.mocked(getAimImages).mockResolvedValue({ data: [] });
    vi.mocked(getClusterAccelerators).mockResolvedValue({ data: [] });
    const { result } = renderHook(() => useRuntimeProfileCatalog(), {
      wrapper: wrapper(client),
    });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    await act(async () => {
      result.current.invalidateCatalog();
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: RUNTIME_PROFILE_AIM_IMAGES_QUERY_KEY,
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: RUNTIME_PROFILE_ACCELERATORS_QUERY_KEY,
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: RUNTIME_PROFILE_OPTIONS_QUERY_KEY,
    });
  });

  it('does not fetch base-template options without a project', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.mocked(getAimImages).mockResolvedValue({ data: [] });
    vi.mocked(getClusterAccelerators).mockResolvedValue({ data: [] });
    const { result } = renderHook(() => useRuntimeProfileCatalog(), {
      wrapper: wrapper(client),
    });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(getRuntimeProfileOptions).not.toHaveBeenCalled();
    expect(result.current.runtimeOptions).toBeNull();
  });

  it('fetches base-template runtime options for a project', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.mocked(getAimImages).mockResolvedValue({ data: [] });
    vi.mocked(getClusterAccelerators).mockResolvedValue({ data: [] });
    vi.mocked(getRuntimeProfileOptions).mockResolvedValue({
      acceleratorModels: ['MI300X'],
      precisions: ['fp16'],
      acceleratorCounts: [1, 2, 4, 8],
      optimizationClasses: ['general'],
      profilesAvailable: false,
    });
    const { result } = renderHook(() => useRuntimeProfileCatalog('proj-a'), {
      wrapper: wrapper(client),
    });
    await waitFor(() => {
      expect(result.current.runtimeOptions).not.toBeNull();
    });
    expect(getRuntimeProfileOptions).toHaveBeenCalledWith('proj-a');
    expect(result.current.runtimeOptions?.precisions).toEqual(['fp16']);
  });
});
