// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { useCustomProfileDeployments } from '@/hooks/useCustomProfileDeployments';
import { resolveCustomProfileDeployments } from '@/lib/app/custom-profiles';
import {
  FINE_TUNED_LABEL,
  NAMESPACE_AIM_MODEL_LABEL,
  type AIMService,
} from '@/types/aims';

vi.mock('@/lib/app/custom-profiles', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/app/custom-profiles')>()),
  resolveCustomProfileDeployments: vi.fn(),
}));

const wrapper =
  (client: QueryClient) =>
  ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

const newClient = () =>
  new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });

const buildService = (
  id: string,
  modelName: string,
  labels: Record<string, string>,
): AIMService =>
  ({
    id,
    metadata: { name: id, labels, annotations: {} },
    spec: { model: { name: modelName } },
  }) as AIMService;

const customService = buildService('svc-byom', 'model-a', {
  [NAMESPACE_AIM_MODEL_LABEL]: 'true',
});

describe('useCustomProfileDeployments', () => {
  it('does not fetch when no deployment is backed by a custom model', () => {
    const services = [
      buildService('svc-catalog', 'aim-llama-3.2-3b', {}),
      buildService('svc-ft', 'ft-model', {
        [NAMESPACE_AIM_MODEL_LABEL]: 'true',
        [FINE_TUNED_LABEL]: 'true',
      }),
    ];

    const { result } = renderHook(
      () => useCustomProfileDeployments({ services, project: 'p1' }),
      { wrapper: wrapper(newClient()) },
    );

    expect(resolveCustomProfileDeployments).not.toHaveBeenCalled();
    expect(result.current.profileByServiceId.size).toBe(0);
  });

  it('does not fetch when no project is selected', () => {
    renderHook(
      () =>
        useCustomProfileDeployments({
          services: [customService],
          project: null,
        }),
      { wrapper: wrapper(newClient()) },
    );

    expect(resolveCustomProfileDeployments).not.toHaveBeenCalled();
  });

  it('requests only the custom models behind the given deployments', async () => {
    vi.mocked(resolveCustomProfileDeployments).mockResolvedValue(new Map());

    renderHook(
      () =>
        useCustomProfileDeployments({
          services: [
            customService,
            buildService('svc-catalog', 'aim-llama-3.2-3b', {}),
          ],
          project: 'p1',
        }),
      { wrapper: wrapper(newClient()) },
    );

    await waitFor(() => {
      expect(resolveCustomProfileDeployments).toHaveBeenCalledWith('p1', [
        'model-a',
      ]);
    });
  });

  it('returns the resolved profile keyed by deployment id', async () => {
    vi.mocked(resolveCustomProfileDeployments).mockResolvedValue(
      new Map([
        [
          'svc-byom',
          {
            displayName: 'High speed',
            profile: {
              metric: 'latency',
              gpu: 'MI300X',
              templateGpuCount: 2,
              acceleratorType: 'gpu',
              precision: 'fp8',
            },
          },
        ],
      ]),
    );

    const { result } = renderHook(
      () =>
        useCustomProfileDeployments({
          services: [customService],
          project: 'p1',
        }),
      { wrapper: wrapper(newClient()) },
    );

    await waitFor(() => {
      expect(result.current.profileByServiceId.size).toBe(1);
    });
    expect(result.current.profileByServiceId.get('svc-byom')).toEqual({
      displayName: 'High speed',
      profile: {
        metric: 'latency',
        gpu: 'MI300X',
        templateGpuCount: 2,
        acceleratorType: 'gpu',
        precision: 'fp8',
      },
    });
  });
});
