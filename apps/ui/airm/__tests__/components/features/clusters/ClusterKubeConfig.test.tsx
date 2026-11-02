// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen, waitFor } from '@testing-library/react';

import { fetchClusterKubeConfig } from '@/services/app';

import { generateClustersMock } from '@/__mocks__/utils/cluster-mock';

import wrapper from '@/__tests__/ProviderWrapper';
import { Mock } from 'vitest';
import ClusterKubeConfig from '@/components/features/clusters/ClusterKubeConfig';

vi.mock('@/services/app', () => ({
  fetchClusterKubeConfig: vi.fn(),
}));

const mockCluster = generateClustersMock(1)[0];

describe('ClusterKubeConfig', () => {
  beforeEach(() => {
    (fetchClusterKubeConfig as Mock).mockClear();
  });

  it('fetches kube config from the API and displays it', async () => {
    (fetchClusterKubeConfig as Mock).mockResolvedValueOnce({
      kubeConfig: 'mock-kube-config',
    });

    render(
      <ClusterKubeConfig
        onOpenChange={() => {}}
        isOpen={true}
        cluster={mockCluster}
      />,
      { wrapper },
    );

    await waitFor(() =>
      expect(screen.getByText('config.title')).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByDisplayValue('mock-kube-config')).toBeInTheDocument(),
    );
  });
});
