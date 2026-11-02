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
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CustomProfilesPage } from '@/components/features/models/CustomProfiles/CustomProfilesPage';
import { getCustomModel } from '@/lib/app/custom-models';
import type { AggregatedAIM, OnboardPhase } from '@/types/aims';
import { mockAggregatedAims } from '@/__mocks__/services/app/aims.data';

import wrapper from '@/__tests__/ProviderWrapper';

const { mockUseProject } = vi.hoisted(() => ({
  mockUseProject: vi.fn(),
}));

// The page reads the single model fresh and maps it to an AggregatedAIM. The
// mapper is exercised by its own unit tests, so here it is an identity pass so
// the test can hand `getCustomModel` a ready-made AggregatedAIM.
vi.mock('@/lib/app/custom-models', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/app/custom-models')>()),
  getCustomModel: vi.fn(),
  customModelToAggregatedAIM: vi.fn((model: AggregatedAIM) => model),
}));

vi.mock('@/contexts/ProjectContext', () => ({
  useProject: () => mockUseProject(),
}));

// The table owns its own query; stub it so this test stays on the page frame.
// The stub also exposes the row callbacks, which are the page's other entry
// points into the two drawers.
vi.mock(
  '@/components/features/models/CustomProfiles/CustomProfilesTable',
  () => ({
    CustomProfilesTable: ({
      project,
      modelId,
      onEditProfile,
      onDeployProfile,
      isModelDeployable,
    }: {
      project: string;
      modelId: string;
      onEditProfile: (profileName: string) => void;
      onDeployProfile: (profile: { name: string }) => void;
      isModelDeployable: boolean;
    }) => (
      <div data-testid="custom-profiles-table-stub">
        {`${project}/${modelId}/${isModelDeployable}`}
        <button
          type="button"
          data-testid="stub-edit-profile"
          onClick={() => onEditProfile('low-latency-7f3b6c8e')}
        />
        <button
          type="button"
          data-testid="stub-deploy-profile"
          onClick={() => onDeployProfile({ name: 'low-latency-7f3b6c8e' })}
        />
      </div>
    ),
  }),
);

vi.mock('@/components/features/models/DeployCustomAIMDrawer', () => ({
  DeployCustomAIMDrawer: ({
    model,
    namespace,
    initialProfile,
    supportsProfileSelection,
    onClose,
  }: {
    model: { resourceName?: string };
    namespace: string;
    initialProfile?: { name: string };
    supportsProfileSelection?: boolean;
    onClose: () => void;
  }) => (
    <div data-testid="deploy-custom-aim-drawer-stub">
      {`${namespace}/${model.resourceName}/${initialProfile?.name}/${supportsProfileSelection}`}
      <button
        type="button"
        data-testid="stub-close-deploy-drawer"
        onClick={onClose}
      />
    </div>
  ),
}));

vi.mock(
  '@/components/features/models/CustomProfiles/CustomProfileDrawer',
  () => ({
    CustomProfileDrawer: ({
      profileName,
      modelName,
      onClose,
      onSaveAndDeploy,
    }: {
      profileName?: string;
      modelName: string;
      onClose: () => void;
      onSaveAndDeploy?: (profile: { name: string }) => void;
    }) => (
      <div data-testid="custom-profile-drawer-stub">
        {`${profileName ?? 'new'}/${modelName}`}
        <button
          type="button"
          data-testid="stub-close-drawer"
          onClick={onClose}
        />
        <button
          type="button"
          data-testid="stub-save-and-deploy"
          onClick={() => {
            onSaveAndDeploy?.({ name: 'just-created-1a2b3c4d' });
            onClose();
          }}
        />
      </div>
    ),
  }),
);

const mockPush = vi.fn();
vi.mock('next/router', () => ({
  useRouter: () => ({ push: mockPush, query: { project: 'project1' } }),
}));

// Overrides the shared key-only stub: the heading interpolates the resolved
// model name, which is what this test is about.
vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { modelName?: string }) =>
      options?.modelName ? `${key} ${options.modelName}` : key,
  }),
}));

const mockGetCustomModel = vi.mocked(getCustomModel);
const baseModel = mockAggregatedAims[0];
// A custom model carries the phase of its weight import, which the page reads to
// tell whether the model can be deployed at all.
const onboardedAs = (
  onboardPhase: OnboardPhase | undefined,
): AggregatedAIM => ({
  ...baseModel,
  aggregated: { ...baseModel.aggregated, onboardPhase },
});
const model = onboardedAs('Ready');

// `getCustomModel` resolves the raw wire type, but the identity-mocked mapper
// lets the tests drive it with a ready-made AggregatedAIM; cast to satisfy the
// mock's return signature.
const resolveModel = (aggregated: AggregatedAIM) =>
  mockGetCustomModel.mockResolvedValue(aggregated as never);

beforeEach(() => {
  vi.clearAllMocks();
  mockUseProject.mockReturnValue({ activeProject: 'project1' });
  resolveModel(model);
});

describe('CustomProfilesPage', () => {
  it('titles the page with the model display name once the list resolves', async () => {
    await act(async () => {
      render(<CustomProfilesPage modelId={model.repository} />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByRole('heading')).toHaveTextContent(
        `title titleForModel ${model.aggregated.title}`,
      );
    });
    expect(screen.getByTestId('custom-profiles-table-stub')).toHaveTextContent(
      `project1/${model.repository}`,
    );
  });

  it('returns to the custom models list from the back button', async () => {
    await act(async () => {
      render(<CustomProfilesPage modelId={model.repository} />, { wrapper });
    });

    fireEvent.click(screen.getByTestId('custom-profiles-back'));

    expect(mockPush).toHaveBeenCalledWith('/project1/models/custom-models');
  });

  it('keeps the route project when project context is still loading', async () => {
    mockUseProject.mockReturnValue({ activeProject: null });
    await act(async () => {
      render(<CustomProfilesPage modelId={model.repository} />, { wrapper });
    });

    fireEvent.click(screen.getByTestId('custom-profiles-back'));

    expect(mockPush).toHaveBeenCalledWith('/project1/models/custom-models');
  });

  it('opens the drawer for a new profile, naming the model', async () => {
    await act(async () => {
      render(<CustomProfilesPage modelId={model.repository} />, { wrapper });
    });
    await waitFor(() => {
      expect(
        screen.getByTestId('custom-profiles-table-stub'),
      ).toBeInTheDocument();
    });

    expect(
      screen.queryByTestId('custom-profile-drawer-stub'),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('custom-profiles-new-profile'));

    expect(screen.getByTestId('custom-profile-drawer-stub')).toHaveTextContent(
      `new/${model.aggregated.title}`,
    );
  });

  it('opens the drawer for the profile the table asks to edit', async () => {
    await act(async () => {
      render(<CustomProfilesPage modelId={model.repository} />, { wrapper });
    });

    fireEvent.click(screen.getByTestId('stub-edit-profile'));

    expect(screen.getByTestId('custom-profile-drawer-stub')).toHaveTextContent(
      'low-latency-7f3b6c8e',
    );
  });

  it('deploys the model on the profile the table asks for', async () => {
    await act(async () => {
      render(<CustomProfilesPage modelId={model.repository} />, { wrapper });
    });
    await waitFor(() => {
      expect(
        screen.getByTestId('custom-profiles-table-stub'),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('stub-deploy-profile'));

    const deployAim = model.latestAim ?? model.parsedAIMs[0];
    expect(
      screen.getByTestId('deploy-custom-aim-drawer-stub'),
    ).toHaveTextContent(
      `project1/${deployAim.model}/low-latency-7f3b6c8e/true`,
    );
  });

  it('deploys a profile that was saved for deploying', async () => {
    await act(async () => {
      render(<CustomProfilesPage modelId={model.repository} />, { wrapper });
    });
    await waitFor(() => {
      expect(
        screen.getByTestId('custom-profiles-table-stub'),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('custom-profiles-new-profile'));

    fireEvent.click(screen.getByTestId('stub-save-and-deploy'));

    expect(
      screen.queryByTestId('custom-profile-drawer-stub'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId('deploy-custom-aim-drawer-stub'),
    ).toHaveTextContent('just-created-1a2b3c4d');
  });

  it('marks the model deployable once its onboard phase is ready', async () => {
    await act(async () => {
      render(<CustomProfilesPage modelId={model.repository} />, { wrapper });
    });

    await waitFor(() => {
      expect(
        screen.getByTestId('custom-profiles-table-stub'),
      ).toHaveTextContent(`project1/${model.repository}/true`);
    });
  });

  it('offers no deploy at all while the model is still importing its weights', async () => {
    resolveModel(onboardedAs('Importing'));
    await act(async () => {
      render(<CustomProfilesPage modelId={model.repository} />, { wrapper });
    });
    await waitFor(() => {
      expect(
        screen.getByTestId('custom-profiles-table-stub'),
      ).toHaveTextContent(`project1/${model.repository}/false`);
    });

    fireEvent.click(screen.getByTestId('custom-profiles-new-profile'));
    fireEvent.click(screen.getByTestId('stub-save-and-deploy'));

    expect(
      screen.queryByTestId('deploy-custom-aim-drawer-stub'),
    ).not.toBeInTheDocument();
  });

  it('discards the deploy drawer when it is cancelled', async () => {
    await act(async () => {
      render(<CustomProfilesPage modelId={model.repository} />, { wrapper });
    });
    await waitFor(() => {
      expect(
        screen.getByTestId('custom-profiles-table-stub'),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('stub-deploy-profile'));

    fireEvent.click(screen.getByTestId('stub-close-deploy-drawer'));

    expect(
      screen.queryByTestId('deploy-custom-aim-drawer-stub'),
    ).not.toBeInTheDocument();
  });

  it('discards the drawer when it is cancelled', async () => {
    await act(async () => {
      render(<CustomProfilesPage modelId={model.repository} />, { wrapper });
    });
    fireEvent.click(screen.getByTestId('custom-profiles-new-profile'));

    fireEvent.click(screen.getByTestId('stub-close-drawer'));

    expect(
      screen.queryByTestId('custom-profile-drawer-stub'),
    ).not.toBeInTheDocument();
  });
});
