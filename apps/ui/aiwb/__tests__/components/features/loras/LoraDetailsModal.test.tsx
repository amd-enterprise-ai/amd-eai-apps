// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import wrapper from '@/__tests__/ProviderWrapper';
import { LoraDetailsModal } from '@/components/features/loras/LoraDetailsModal';
import { getAdapterArtifact } from '@/lib/app/artifacts';
import {
  ARTIFACT_DESCRIPTION_ANNOTATION,
  SUBMITTER_ANNOTATION,
} from '@/types/artifacts';
import { AIM_DISPLAY_NAME_ANNOTATION } from '@/types/aims';

vi.mock('@/lib/app/artifacts', () => ({
  getAdapterArtifact: vi.fn(),
}));

// The default ProviderWrapper disables retries for every query, which would
// hide a missing retry override on the details query. This wrapper keeps
// retries on (so a non-404 failure still exercises them) but with no delay,
// so tests asserting retry behavior finish quickly.
const RetryEnabledWrapper = ({ children }: { children: ReactNode }) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: 3, retryDelay: 0 } },
  });
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

const adapterDetails: Awaited<ReturnType<typeof getAdapterArtifact>> = {
  storage: {
    readiness: 'Ready',
    uri: 's3://example-bucket/project/adapters/adapter-1/',
  },
  artifact: {
    metadata: {
      name: 'adapter-1',
      creationTimestamp: '2026-08-11T12:31:31Z',
      annotations: {
        [AIM_DISPLAY_NAME_ANNOTATION]: 'Support LoRA',
        [SUBMITTER_ANNOTATION]: 'user@example.com',
      },
    },
    spec: {
      type: 'adapter',
      modelId: 'example-org/support-lora',
      compatibleWith: ['example-org/base-model', 'example-org/second-model'],
      rank: 16,
    },
    status: {
      status: 'Ready',
      conditions: [
        {
          type: 'FilesReady',
          status: 'True',
          reason: 'FilesAvailable',
          message: 'Adapter files are available',
        },
      ],
    },
  },
};

describe('LoraDetailsModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getAdapterArtifact).mockResolvedValue(adapterDetails);
  });

  it('does not fetch or render while closed', () => {
    render(
      <LoraDetailsModal
        name="adapter-1"
        isOpen={false}
        onOpenChange={vi.fn()}
      />,
      { wrapper },
    );

    expect(screen.queryByTestId('lora-details-modal')).not.toBeInTheDocument();
    expect(getAdapterArtifact).not.toHaveBeenCalled();
  });

  it('displays a loading state while adapter details are fetched', () => {
    vi.mocked(getAdapterArtifact).mockReturnValue(new Promise(() => {}));

    render(
      <LoraDetailsModal
        name="adapter-1"
        isOpen={true}
        onOpenChange={vi.fn()}
      />,
      { wrapper },
    );

    expect(screen.getByTestId('lora-details-loading')).toBeInTheDocument();
  });

  it('displays adapter fields and conditions', async () => {
    render(
      <LoraDetailsModal
        name="adapter-1"
        isOpen={true}
        onOpenChange={vi.fn()}
      />,
      { wrapper },
    );

    expect(await screen.findByText('Support LoRA')).toBeInTheDocument();
    expect(screen.getByText('adapter-1')).toBeInTheDocument();
    expect(screen.getByText('example-org/support-lora')).toBeInTheDocument();
    expect(screen.getByText('example-org/base-model')).toBeInTheDocument();
    expect(screen.getByText('example-org/second-model')).toBeInTheDocument();
    expect(screen.getByText('16')).toBeInTheDocument();
    expect(screen.getByText('user@example.com')).toBeInTheDocument();
    expect(
      screen.getByText('s3://example-bucket/project/adapters/adapter-1/'),
    ).toBeInTheDocument();
    expect(screen.getByText('Files')).toBeInTheDocument();
    expect(screen.getByText('Adapter files are available')).toBeInTheDocument();
    expect(getAdapterArtifact).toHaveBeenCalledWith('project1', 'adapter-1');
  });

  it('shows a no-data placeholder when the storage URI is absent', async () => {
    vi.mocked(getAdapterArtifact).mockResolvedValue({
      ...adapterDetails,
      storage: { ...adapterDetails.storage, uri: null },
    });

    render(
      <LoraDetailsModal
        name="adapter-1"
        isOpen={true}
        onOpenChange={vi.fn()}
      />,
      { wrapper },
    );

    expect(await screen.findByText('Support LoRA')).toBeInTheDocument();
    expect(
      screen.queryByText('s3://example-bucket/project/adapters/adapter-1/'),
    ).not.toBeInTheDocument();
  });

  it('displays the description when its annotation is present', async () => {
    vi.mocked(getAdapterArtifact).mockResolvedValue({
      ...adapterDetails,
      artifact: {
        ...adapterDetails.artifact,
        metadata: {
          ...adapterDetails.artifact.metadata,
          annotations: {
            ...adapterDetails.artifact.metadata.annotations,
            [ARTIFACT_DESCRIPTION_ANNOTATION]: 'Customer support adapter',
          },
        },
      },
    });

    render(
      <LoraDetailsModal
        name="adapter-1"
        isOpen={true}
        onOpenChange={vi.fn()}
      />,
      { wrapper },
    );

    expect(
      await screen.findByText('details.modal.fields.description'),
    ).toBeInTheDocument();
    expect(screen.getByText('Customer support adapter')).toHaveClass(
      'whitespace-pre-wrap',
      'break-words',
    );
  });

  it('omits the description when its annotation is absent', async () => {
    render(
      <LoraDetailsModal
        name="adapter-1"
        isOpen={true}
        onOpenChange={vi.fn()}
      />,
      { wrapper },
    );

    expect(await screen.findByText('Support LoRA')).toBeInTheDocument();
    expect(
      screen.queryByText('details.modal.fields.description'),
    ).not.toBeInTheDocument();
  });

  it('displays a generic error when adapter details cannot be loaded', async () => {
    vi.mocked(getAdapterArtifact).mockRejectedValue(new Error('boom'));

    render(
      <LoraDetailsModal name="missing" isOpen={true} onOpenChange={vi.fn()} />,
      // A non-404 error retries per the details query's own retry override,
      // so use the fast retry-enabled wrapper instead of the default one.
      { wrapper: RetryEnabledWrapper },
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('details.error');
  });

  it('displays the not-found message when the adapter no longer exists', async () => {
    vi.mocked(getAdapterArtifact).mockRejectedValue(
      new APIRequestError('Failed to get adapter: Not Found', 404),
    );

    render(
      <LoraDetailsModal name="missing" isOpen={true} onOpenChange={vi.fn()} />,
      { wrapper },
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'details.modal.notFound',
    );
  });

  it('does not retry the details query on a 404 response', async () => {
    vi.mocked(getAdapterArtifact).mockRejectedValue(
      new APIRequestError('Failed to get adapter: Not Found', 404),
    );

    render(
      <LoraDetailsModal name="missing" isOpen={true} onOpenChange={vi.fn()} />,
      { wrapper: RetryEnabledWrapper },
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'details.modal.notFound',
    );
    expect(getAdapterArtifact).toHaveBeenCalledTimes(1);
  });
});
