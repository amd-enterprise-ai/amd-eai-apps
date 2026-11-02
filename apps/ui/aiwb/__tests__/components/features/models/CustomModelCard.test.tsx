// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CustomModelCard } from '@/components/features/models/CustomModelCard';
import { mockAggregatedAims } from '@/__mocks__/services/app/aims.data';
import { AggregatedAIM } from '@/types/aims';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (
        key === 'aimCatalog.card.versionCount' &&
        typeof options?.count === 'number'
      ) {
        return options.count === 1
          ? `${options.count} version`
          : `${options.count} versions`;
      }
      if (
        key === 'customModels.card.tagsMoreCount' &&
        typeof options?.count === 'number'
      ) {
        return `+${options.count}`;
      }
      if (
        key === 'customModels.card.profileCount' &&
        typeof options?.count === 'number'
      ) {
        return options.count === 1
          ? `${options.count} profile`
          : `${options.count} profiles`;
      }
      return key;
    },
  }),
}));

vi.mock('@amdenterpriseai/components', async (importOriginal) => ({
  ...(await importOriginal()),
  // Render dropdown actions inline so the test can interact with them
  // without going through HeroUI's portalled menu.
  ActionsDropdown: ({
    children,
    actions,
  }: {
    children: React.ReactNode;
    actions: { key: string; label: string; onPress: () => void }[];
  }) => (
    <div data-testid="nested-dropdown">
      {children}
      <div data-testid="dropdown-content">
        {actions.map((action) => (
          <button
            key={action.key}
            data-testid={`menu-item-${action.key}`}
            onClick={() => action.onPress()}
          >
            {action.label}
          </button>
        ))}
      </div>
    </div>
  ),
}));

const baseAim: AggregatedAIM = mockAggregatedAims[0];

/** baseAim with a specific composed onboard phase (deployability gates on this). */
const withPhase = (
  onboardPhase: AggregatedAIM['aggregated']['onboardPhase'],
): AggregatedAIM => ({
  ...baseAim,
  aggregated: { ...baseAim.aggregated, onboardPhase },
});

const readyAim = withPhase('Ready');

describe('CustomModelCard', () => {
  const handlers = {
    onModelSettings: vi.fn(),
    onProfiles: vi.fn(),
    onDelete: vi.fn(),
    onDeploy: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the action menu items (settings, profiles, delete)', () => {
    render(<CustomModelCard aggregatedAim={baseAim} {...handlers} />);

    expect(screen.getByTestId('menu-item-settings')).toHaveTextContent(
      'customModels.card.actions.settings.label',
    );
    expect(screen.getByTestId('menu-item-profiles')).toHaveTextContent(
      'customModels.card.actions.profiles.label',
    );
    expect(screen.getByTestId('menu-item-delete')).toHaveTextContent(
      'customModels.card.actions.delete.label',
    );
  });

  it('invokes the matching handler when an action is selected', () => {
    render(<CustomModelCard aggregatedAim={baseAim} {...handlers} />);

    fireEvent.click(screen.getByTestId('menu-item-settings'));
    expect(handlers.onModelSettings).toHaveBeenCalledWith(baseAim);

    fireEvent.click(screen.getByTestId('menu-item-profiles'));
    expect(handlers.onProfiles).toHaveBeenCalledWith(baseAim);

    fireEvent.click(screen.getByTestId('menu-item-delete'));
    expect(handlers.onDelete).toHaveBeenCalledWith(baseAim);
  });

  it('routes the Deploy button click to onDeploy when the model is Ready', () => {
    render(<CustomModelCard aggregatedAim={readyAim} {...handlers} />);

    fireEvent.click(screen.getByTestId('custom-model-card-deploy'));

    expect(handlers.onDeploy).toHaveBeenCalledWith(readyAim);
  });

  it('enables Deploy and shows no status pill when the model is Ready', () => {
    render(<CustomModelCard aggregatedAim={readyAim} {...handlers} />);

    expect(screen.getByTestId('custom-model-card-deploy')).toBeEnabled();
    expect(
      screen.queryByText('customModels.card.status.failed'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('customModels.card.status.importing'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('customModels.card.status.onboarding'),
    ).not.toBeInTheDocument();
  });

  it('shows Importing status pill and disables Deploy while weights are being imported', () => {
    render(
      <CustomModelCard aggregatedAim={withPhase('Importing')} {...handlers} />,
    );

    expect(screen.getByTestId('custom-model-card-deploy')).toBeDisabled();
    expect(
      screen.getByText('customModels.card.status.importing'),
    ).toBeInTheDocument();
  });

  it('shows Failed status pill and disables Deploy when onboarding failed', () => {
    // The bug guard: a failed weight import composes to phase 'Failed' even
    // when an AIMProfile exists. The card must surface the failure and keep
    // Deploy disabled so the user cannot deploy a model with missing weights.
    render(
      <CustomModelCard aggregatedAim={withPhase('Failed')} {...handlers} />,
    );

    expect(screen.getByTestId('custom-model-card-deploy')).toBeDisabled();
    expect(
      screen.getByText('customModels.card.status.failed'),
    ).toBeInTheDocument();
  });

  it('shows Onboarding status pill and disables Deploy for Pending phase', () => {
    render(
      <CustomModelCard aggregatedAim={withPhase('Pending')} {...handlers} />,
    );

    expect(screen.getByTestId('custom-model-card-deploy')).toBeDisabled();
    expect(
      screen.getByText('customModels.card.status.onboarding'),
    ).toBeInTheDocument();
  });

  it('renders the profile count and Default summary without a per-model query', () => {
    const withProfiles: AggregatedAIM = {
      ...readyAim,
      aggregated: {
        ...readyAim.aggregated,
        profileCount: 2,
        defaultProfile: {
          name: 'default',
          displayName: 'Default',
          isDefault: true,
          resourceName: 'model-default',
          profile: {
            spec: {
              metric: 'throughput',
              acceleratorModel: 'MI300X',
              acceleratorCount: 1,
              acceleratorType: 'gpu',
              precision: 'fp8',
            },
          },
        } as AggregatedAIM['aggregated']['defaultProfile'],
      },
    };
    render(<CustomModelCard aggregatedAim={withProfiles} {...handlers} />);
    expect(
      screen.getByTestId('custom-model-card-profile-count'),
    ).toHaveTextContent('2 profiles');
    const summary = screen.getByTestId('custom-model-card-default-profile');
    expect(summary).toHaveTextContent('MI300X');
    expect(summary).toHaveTextContent('fp8');
  });

  it('omits the Default summary when the Default has no effective profile yet', () => {
    // A just-onboarded model can carry a Default row whose effective profile is
    // not emitted yet. The summary would be all-null, so the card must not render
    // an empty summary container.
    const withoutEffectiveProfile: AggregatedAIM = {
      ...readyAim,
      aggregated: {
        ...readyAim.aggregated,
        profileCount: 1,
        defaultProfile: {
          name: 'default',
          displayName: 'Default',
          isDefault: true,
          resourceName: 'model-default',
        } as AggregatedAIM['aggregated']['defaultProfile'],
      },
    };
    render(
      <CustomModelCard aggregatedAim={withoutEffectiveProfile} {...handlers} />,
    );
    expect(
      screen.getByTestId('custom-model-card-profile-count'),
    ).toHaveTextContent('1 profile');
    expect(
      screen.queryByTestId('custom-model-card-default-profile'),
    ).not.toBeInTheDocument();
  });

  it('omits the profile count and Default summary for catalog-style aggregated AIMs', () => {
    // A stock catalog AggregatedAIM leaves profileCount/defaultProfile unset;
    // the card must still render without profile metadata.
    render(<CustomModelCard aggregatedAim={readyAim} {...handlers} />);
    expect(
      screen.queryByTestId('custom-model-card-profile-count'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('custom-model-card-default-profile'),
    ).not.toBeInTheDocument();
  });
});
