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
import { describe, expect, it, vi, Mock } from 'vitest';

import CustomModels from '@/components/features/models/CustomModels';
import { AggregatedAIM, AIMWorkloadStatus, OnboardPhase } from '@/types/aims';
import wrapper from '@/__tests__/ProviderWrapper';

const mockPush = vi.fn();
vi.mock('next/router', () => ({
  useRouter: () => ({
    push: mockPush,
    pathname: '/[project]/models/custom-models',
    query: { project: 'test-project' },
    asPath: '/test-project/models/custom-models',
  }),
}));

const customModelsApiMocks = vi.hoisted(() => ({
  listCustomModels: vi.fn(),
  deleteCustomModel: vi.fn(),
}));

vi.mock('@/lib/app/custom-models', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/lib/app/custom-models')>();
  return {
    ...actual,
    listCustomModels: customModelsApiMocks.listCustomModels,
    deleteCustomModel: customModelsApiMocks.deleteCustomModel,
  };
});

vi.mock('@/contexts/ProjectContext', () => ({
  useProject: () => ({
    activeProject: 'test-project',
    projectPath: (path: string) => `/test-project${path}`,
  }),
}));

const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  useSystemToast: () => ({
    toast: { success: mockToastSuccess, error: mockToastError, info: vi.fn() },
  }),
}));

// Keep deploy drawer as a stub so this test stays focused on card-grid behavior.
// It reports the props the grid hands over, which is what decides whether the
// deploy offers a profile to serve with.
vi.mock('@/components/features/models/DeployCustomAIMDrawer', () => ({
  DeployCustomAIMDrawer: ({
    model,
    supportsProfileSelection,
  }: {
    model: { resourceName?: string };
    supportsProfileSelection?: boolean;
  }) => (
    <div data-testid="deploy-custom-aim-drawer-stub">
      {`${model?.resourceName}/${supportsProfileSelection}`}
    </div>
  ),
}));
vi.mock('@/components/features/models/CustomModelCard', () => ({
  CustomModelCard: ({
    aggregatedAim,
    onDelete,
    onDeploy,
  }: {
    aggregatedAim: AggregatedAIM;
    onDelete: (aim: AggregatedAIM) => void;
    onDeploy: (aim: AggregatedAIM) => void;
  }) => (
    <div data-testid={`custom-model-card-${aggregatedAim.repository}`}>
      <span>{aggregatedAim.aggregated.title}</span>
      <button data-testid="custom-model-card-actions" />
      <button onClick={() => onDelete(aggregatedAim)}>
        customModels.card.actions.delete.label
      </button>
      <button
        data-testid="custom-model-card-deploy"
        onClick={() => onDeploy(aggregatedAim)}
      />
    </div>
  ),
}));

const zeroCounts = Object.fromEntries(
  Object.values(AIMWorkloadStatus).map((s) => [s, 0]),
) as Record<AIMWorkloadStatus, number>;

function buildAggregatedAIM(
  overrides: Partial<AggregatedAIM> & {
    aggregatedOverrides?: Partial<AggregatedAIM['aggregated']>;
    onboardPhase?: OnboardPhase;
  } = {},
): AggregatedAIM {
  const { aggregatedOverrides, onboardPhase = 'Ready', ...rest } = overrides;
  const title = aggregatedOverrides?.title ?? 'Test';
  const canonicalName = aggregatedOverrides?.canonicalName ?? 'org/test';

  const parsedAIM = {
    model: 'aim-test',
    aimId: 'org/test',
    imageReference: 'docker.io/test:1.0.0',
    annotations: {},
    description: { short: 'desc', full: 'full' },
    title,
    imageVersion: '1.0.0',
    canonicalName,
    tags: [],
    status: 'Ready',
    workloadStatuses: [],
    isPreview: false,
    isHfTokenRequired: false,
    isCustomImport: true,
    sourceUri: undefined,
  };

  return {
    repository: 'aim-test',
    parsedAIMs: [parsedAIM],
    latestAim: parsedAIM,
    isSupported: true,
    deploymentCounts: zeroCounts,
    aggregated: {
      title,
      aiLabName: 'org',
      canonicalName,
      latestImageVersion: '1.0.0',
      isHfTokenRequired: false,
      isCustomImport: true,
      tags: [],
      description: { short: 'desc', full: 'full' },
      onboardPhase,
      ...aggregatedOverrides,
    },
    ...rest,
  };
}

describe('CustomModels (card grid)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders custom model cards returned by listCustomModels', async () => {
    (customModelsApiMocks.listCustomModels as Mock).mockResolvedValue([
      buildAggregatedAIM({ aggregatedOverrides: { title: 'Imported model' } }),
    ]);

    await act(async () => {
      render(<CustomModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Imported model')).toBeInTheDocument();
    });
  });

  it('shows the empty state when listCustomModels returns an empty list', async () => {
    (customModelsApiMocks.listCustomModels as Mock).mockResolvedValue([]);

    await act(async () => {
      render(<CustomModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByTestId('custom-models-empty')).toBeInTheDocument();
    });
    expect(
      screen.getByText('customModels.list.description'),
    ).toBeInTheDocument();
  });

  it('shows the filtered-empty state when search hides all results', async () => {
    (customModelsApiMocks.listCustomModels as Mock).mockResolvedValue([
      buildAggregatedAIM({
        aggregatedOverrides: {
          title: 'Imported model',
          canonicalName: 'sony/virtue-7b',
        },
      }),
    ]);

    await act(async () => {
      render(<CustomModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Imported model')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(
      'customModels.list.filters.search.placeholder',
    );
    fireEvent.change(searchInput, { target: { value: 'no-such-model' } });

    await waitFor(() => {
      expect(
        screen.getByTestId('custom-models-empty-filtered'),
      ).toBeInTheDocument();
    });
    expect(screen.queryByTestId('custom-models-empty')).not.toBeInTheDocument();
    expect(
      screen.getByText('customModels.list.empty.filtered.title'),
    ).toBeInTheDocument();
  });

  it('matches search against the AIM CR name (repository), not only the display title', async () => {
    (customModelsApiMocks.listCustomModels as Mock).mockResolvedValue([
      buildAggregatedAIM({
        repository: 'cr-abc-unique',
        aggregatedOverrides: {
          title: 'Friendly display name',
          canonicalName: 'org/repo',
        },
      }),
    ]);

    await act(async () => {
      render(<CustomModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Friendly display name')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(
      'customModels.list.filters.search.placeholder',
    );
    fireEvent.change(searchInput, { target: { value: 'cr-abc-unique' } });

    await waitFor(() => {
      expect(screen.getByText('Friendly display name')).toBeInTheDocument();
    });
  });

  it('navigates to the import wizard when the Import model button is clicked', async () => {
    (customModelsApiMocks.listCustomModels as Mock).mockResolvedValue([]);

    await act(async () => {
      render(<CustomModels />, { wrapper });
    });

    await waitFor(() => {
      expect(
        screen.getByTestId('custom-models-import-model'),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('custom-models-import-model'));

    expect(mockPush).toHaveBeenCalledWith(
      '/test-project/models/custom-models/onboard',
    );
  });

  it('shows only importing models when "Onboarding" status filter is selected', async () => {
    (customModelsApiMocks.listCustomModels as Mock).mockResolvedValue([
      buildAggregatedAIM({
        repository: 'importing-model',
        onboardPhase: 'Importing',
        aggregatedOverrides: { title: 'Importing Model' },
      }),
      buildAggregatedAIM({
        repository: 'ready-model',
        onboardPhase: 'Ready',
        aggregatedOverrides: { title: 'Ready Model' },
      }),
    ]);

    await act(async () => {
      render(<CustomModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Importing Model')).toBeInTheDocument();
      expect(screen.getByText('Ready Model')).toBeInTheDocument();
    });

    const statusDropdown = screen.getByRole('button', {
      name: /customModels\.list\.filters\.status/,
    });
    await act(async () => {
      fireEvent.click(statusDropdown);
    });
    await act(async () => {
      fireEvent.click(
        screen.getByRole('option', {
          name: 'customModels.card.status.onboarding',
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Importing Model')).toBeInTheDocument();
      expect(screen.queryByText('Ready Model')).not.toBeInTheDocument();
    });
  });

  it('shows only ready models when "Ready" status filter is selected', async () => {
    (customModelsApiMocks.listCustomModels as Mock).mockResolvedValue([
      buildAggregatedAIM({
        repository: 'importing-model',
        onboardPhase: 'Importing',
        aggregatedOverrides: { title: 'Importing Model' },
      }),
      buildAggregatedAIM({
        repository: 'ready-model',
        onboardPhase: 'Ready',
        aggregatedOverrides: { title: 'Ready Model' },
      }),
    ]);

    await act(async () => {
      render(<CustomModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Ready Model')).toBeInTheDocument();
    });

    const statusDropdown = screen.getByRole('button', {
      name: /customModels\.list\.filters\.status/,
    });
    await act(async () => {
      fireEvent.click(statusDropdown);
    });
    await act(async () => {
      fireEvent.click(
        screen.getByRole('option', { name: 'customModels.card.status.ready' }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Ready Model')).toBeInTheDocument();
      expect(screen.queryByText('Importing Model')).not.toBeInTheDocument();
    });
  });

  it('shows only failed models when "Failed" status filter is selected', async () => {
    (customModelsApiMocks.listCustomModels as Mock).mockResolvedValue([
      buildAggregatedAIM({
        repository: 'failed-model',
        onboardPhase: 'Failed',
        aggregatedOverrides: { title: 'Failed Model' },
      }),
      buildAggregatedAIM({
        repository: 'importing-model',
        onboardPhase: 'Importing',
        aggregatedOverrides: { title: 'Importing Model' },
      }),
    ]);

    await act(async () => {
      render(<CustomModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Failed Model')).toBeInTheDocument();
      expect(screen.getByText('Importing Model')).toBeInTheDocument();
    });

    const statusDropdown = screen.getByRole('button', {
      name: /customModels\.list\.filters\.status/,
    });
    await act(async () => {
      fireEvent.click(statusDropdown);
    });
    await act(async () => {
      fireEvent.click(
        screen.getByRole('option', { name: 'customModels.card.status.failed' }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Failed Model')).toBeInTheDocument();
      expect(screen.queryByText('Importing Model')).not.toBeInTheDocument();
    });
  });

  it('offers a profile to serve with on a deploy started from a card', async () => {
    (customModelsApiMocks.listCustomModels as Mock).mockResolvedValue([
      buildAggregatedAIM({
        repository: 'my-cr-name',
        aggregatedOverrides: { title: 'My display' },
      }),
    ]);

    await act(async () => {
      render(<CustomModels />, { wrapper });
    });
    await waitFor(() => {
      expect(screen.getByText('My display')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('custom-model-card-deploy'));

    await waitFor(() => {
      expect(
        screen.getByTestId('deploy-custom-aim-drawer-stub'),
      ).toHaveTextContent('aim-test/true');
    });
  });

  it('opens delete confirmation and calls deleteCustomModel with CR name on confirm', async () => {
    (customModelsApiMocks.listCustomModels as Mock).mockResolvedValue([
      buildAggregatedAIM({
        repository: 'my-cr-name',
        aggregatedOverrides: { title: 'My display' },
      }),
    ]);
    (customModelsApiMocks.deleteCustomModel as Mock).mockResolvedValue(
      undefined,
    );

    await act(async () => {
      render(<CustomModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('My display')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('custom-model-card-actions'));
    fireEvent.click(screen.getByText('customModels.card.actions.delete.label'));

    await waitFor(() => {
      expect(screen.getByTestId('confirmation-modal')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('confirm-button'));

    await waitFor(() => {
      expect(customModelsApiMocks.deleteCustomModel).toHaveBeenCalledWith(
        'test-project',
        'my-cr-name',
      );
    });
  });
});
