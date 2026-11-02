// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { Mock, vi } from 'vitest';

import { fetchProjectSecrets } from '@/lib/app/secrets';
import { SecretResponseData } from '@/types/secrets';
import { SecretUseCase } from '@amdenterpriseai/types';

import { WorkbenchSecretsPageContent } from '@/components/features/secrets/WorkbenchSecretsPageContent';

import wrapper from '@/__tests__/ProviderWrapper';

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: { user: { name: 'Test User' } },
    status: 'authenticated',
  }),
}));

vi.mock('@/lib/app/secrets', () => ({
  fetchProjectSecrets: vi.fn(),
}));

const mockFetchProjectSecrets = vi.mocked(fetchProjectSecrets);

const awsSecret: SecretResponseData = {
  displayName: 'AWS API Key',
  useCase: SecretUseCase.GENERIC,
  metadata: {
    name: 'wb-secret-a1b2c3d4',
    namespace: 'project1',
    creationTimestamp: '2024-01-01T00:00:00Z',
  },
};

const hfSecret: SecretResponseData = {
  displayName: 'HuggingFace Token',
  useCase: SecretUseCase.HUGGING_FACE,
  metadata: {
    name: 'wb-secret-uniquehex1',
    namespace: 'project1',
    creationTimestamp: '2024-01-02T00:00:00Z',
  },
};

describe('WorkbenchSecretsPageContent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (mockFetchProjectSecrets as Mock).mockResolvedValue({
      data: [awsSecret, hfSecret],
    });
  });

  it('filters secrets by displayName shown in the Name column', async () => {
    await act(async () => {
      render(<WorkbenchSecretsPageContent />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText(awsSecret.displayName)).toBeInTheDocument();
      expect(screen.getByText(hfSecret.displayName)).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(
      'list.filter.search.placeholder',
    );
    fireEvent.change(searchInput, { target: { value: 'AWS' } });

    await waitFor(() => {
      expect(screen.getByText(awsSecret.displayName)).toBeInTheDocument();
      expect(screen.queryByText(hfSecret.displayName)).not.toBeInTheDocument();
    });
  });

  it('does not match the internal Kubernetes resource name', async () => {
    await act(async () => {
      render(<WorkbenchSecretsPageContent />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText(awsSecret.displayName)).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(
      'list.filter.search.placeholder',
    );
    fireEvent.change(searchInput, {
      target: { value: awsSecret.metadata.name },
    });

    await waitFor(() => {
      expect(screen.queryByText(awsSecret.displayName)).not.toBeInTheDocument();
      expect(screen.queryByText(hfSecret.displayName)).not.toBeInTheDocument();
    });
  });
});
