// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, vi } from 'vitest';

import { LoraAdaptersCard } from '@/components/features/workloads/LoraAdaptersCard';
import { getAdapterArtifacts } from '@/lib/app/artifacts';
import wrapper from '@/__tests__/ProviderWrapper';
import type { AIMProfileSpec, AIMService } from '@/types/aims';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: { rank?: number }) =>
      values?.rank == null ? key : `Rank: ${values.rank}`,
  }),
}));

vi.mock('@/lib/app/artifacts', () => ({
  getAdapterArtifacts: vi.fn(),
}));

vi.mock('@/components/features/workloads/EditLoraAdaptersModal', () => ({
  EditLoraAdaptersModal: ({
    isOpen,
    onSuccess,
    resolvedProfileSpec,
  }: {
    isOpen: boolean;
    onSuccess?: () => void;
    resolvedProfileSpec: AIMProfileSpec | null;
  }) =>
    isOpen ? (
      <button
        data-testid="edit-lora-modal"
        data-profile-model-id={resolvedProfileSpec?.modelId ?? ''}
        onClick={onSuccess}
      >
        Save
      </button>
    ) : null,
}));

vi.mock('@amdenterpriseai/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@amdenterpriseai/components')>()),
  Button: ({
    children,
    onPress,
    startContent: _startContent,
    ...props
  }: React.PropsWithChildren<{
    onPress?: () => void;
    startContent?: React.ReactNode;
  }>) => (
    <button onClick={onPress} {...props}>
      {children}
    </button>
  ),
  Card: ({ children, ...props }: React.PropsWithChildren) => (
    <div {...props}>{children}</div>
  ),
  CardHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardBody: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  NoDataDisplay: () => <span data-testid="no-data">—</span>,
  Skeleton: (props: React.HTMLAttributes<HTMLDivElement>) => (
    <div data-testid="skeleton" {...props} />
  ),
  CopySnippet: ({
    value,
    copyButtonAriaLabel,
  }: {
    value: string;
    copyButtonAriaLabel: string;
  }) => (
    <button
      aria-label={copyButtonAriaLabel}
      onClick={() => navigator.clipboard.writeText(value)}
    />
  ),
}));

const resolvedProfileSpec = {
  aimId: 'example-org/base-model',
  modelId: 'example-org/base-model-fp8',
  features: ['adapters'],
} as AIMProfileSpec;

const mockGetAdapterArtifacts = vi.mocked(getAdapterArtifacts);
const createDeployment = ({
  adapterNames = [],
  maxRank = 64,
  adapterMode = 'dynamic',
}: {
  adapterNames?: string[];
  maxRank?: number;
  adapterMode?: 'dynamic' | 'static';
} = {}): AIMService =>
  ({
    id: 'deployment-id',
    metadata: { name: 'deployment', labels: {}, annotations: {} },
    spec: {
      adapterMode,
      adapters: adapterNames.map((name) => ({ kind: 'AIMArtifact', name })),
      adapterRuntime: { maxRank },
    },
  }) as unknown as AIMService;

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

it('shows max rank and adapter details', async () => {
  mockGetAdapterArtifacts.mockResolvedValue([
    {
      id: 'adapter-id',
      name: 'adapter-k8s-name',
      displayName: 'Adapter display name',
      compatibleWith: [],
      rank: 16,
      readiness: 'Ready',
    },
  ]);

  render(
    <LoraAdaptersCard
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      deployment={createDeployment({
        adapterNames: ['adapter-k8s-name'],
      })}
    />,
    { wrapper },
  );

  expect(screen.getByText('64')).toBeInTheDocument();
  expect(await screen.findByText('Adapter display name')).toBeInTheDocument();
  expect(screen.getByText('adapter-k8s-name')).toBeInTheDocument();
  expect(screen.getByText('16')).toBeInTheDocument();
  expect(mockGetAdapterArtifacts).toHaveBeenCalledWith('project', [
    'adapter-k8s-name',
  ]);

  fireEvent.click(
    screen.getByRole('button', { name: 'details.loraAdapters.copyName' }),
  );
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
    'adapter-k8s-name',
  );
});

it('names each adapter rank for assistive technology', async () => {
  mockGetAdapterArtifacts.mockResolvedValue([
    {
      id: 'adapter-id',
      name: 'adapter-k8s-name',
      displayName: 'Adapter display name',
      compatibleWith: [],
      rank: 16,
      readiness: 'Ready',
    },
  ]);

  render(
    <LoraAdaptersCard
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      deployment={createDeployment({ adapterNames: ['adapter-k8s-name'] })}
    />,
    { wrapper },
  );

  // The digit alone is announced without meaning, so it is hidden in favour of
  // a labelled equivalent.
  expect(await screen.findByText('Rank: 16')).toBeInTheDocument();
  expect(screen.getByText('16')).toHaveAttribute('aria-hidden');
});

it('shows skeletons while adapter details load', () => {
  mockGetAdapterArtifacts.mockReturnValue(new Promise(() => {}));

  render(
    <LoraAdaptersCard
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      deployment={createDeployment({
        adapterNames: ['adapter-one', 'adapter-two'],
      })}
    />,
    { wrapper },
  );

  expect(screen.getAllByTestId('skeleton')).toHaveLength(2);
});

it('shows the empty-state copy for an empty adapter list', () => {
  render(
    <LoraAdaptersCard
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      deployment={createDeployment()}
    />,
    { wrapper },
  );

  expect(screen.getByText('details.loraAdapters.empty')).toBeInTheDocument();
  expect(mockGetAdapterArtifacts).not.toHaveBeenCalled();
});

it('falls back to the Kubernetes name when an artifact is unavailable', async () => {
  mockGetAdapterArtifacts.mockResolvedValue([]);

  render(
    <LoraAdaptersCard
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      deployment={createDeployment({
        adapterNames: ['missing-adapter'],
      })}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(screen.getAllByText('missing-adapter')).toHaveLength(2),
  );
  expect(screen.getByText('—')).toBeInTheDocument();
  expect(
    screen.getByText('details.loraAdapters.rankUnavailable'),
  ).toBeInTheDocument();
});

it('opens the editor only for dynamic deployments', () => {
  const onAdaptersUpdated = vi.fn();
  const { rerender } = render(
    <LoraAdaptersCard
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      deployment={createDeployment()}
      onAdaptersUpdated={onAdaptersUpdated}
    />,
    { wrapper },
  );

  fireEvent.click(screen.getByTestId('edit-lora-adapters-button'));
  // The editor decides adapter eligibility from the profile actually serving
  // the deployment, which only this card knows.
  expect(screen.getByTestId('edit-lora-modal')).toHaveAttribute(
    'data-profile-model-id',
    'example-org/base-model-fp8',
  );
  fireEvent.click(screen.getByTestId('edit-lora-modal'));
  expect(onAdaptersUpdated).toHaveBeenCalledOnce();

  rerender(
    <LoraAdaptersCard
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      deployment={createDeployment({ adapterMode: 'static' })}
    />,
  );
  expect(
    screen.queryByTestId('edit-lora-adapters-button'),
  ).not.toBeInTheDocument();
});
