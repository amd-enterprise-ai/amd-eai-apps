// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AIMCard } from '@/components/features/models/AIMCard';
import { AggregatedAIM, AIMWorkloadStatus } from '@/types/aims';
import {
  mockAggregatedAims,
  mockAggregatedAimWithMultipleDeployments,
  mockUnsupportedAggregatedAim,
  mockAggregatedAimWithStarting,
} from '@/__mocks__/services/app/aims.data';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: any) => {
      // Handle translation keys with interpolation
      if (options?.name) {
        return `${key} ${options.name}`;
      }

      // Handle pluralization for version count
      if (
        key === 'aimCatalog.card.versionCount' &&
        options?.count !== undefined
      ) {
        return options.count === 1
          ? `${options.count} version`
          : `${options.count} versions`;
      }

      // Handle pluralization for deployments count
      if (
        key === 'aimCatalog.card.deploymentsCount' &&
        options?.count !== undefined
      ) {
        return `Deployments (${options.count})`;
      }

      // Handle specific translation keys
      const translations: Record<string, string> = {
        'aimCatalog.card.gated': 'Gated',
        'aimCatalog.card.actionsMenu': 'Actions menu',
        'aimCatalog.card.menuTrigger': 'Menu',
        'aimCatalog.card.hasDeployments': 'Has deployments',
        'aimCatalog.card.hasDeploymentsTooltip':
          'This model has active deployments',
        'aimCatalog.card.showMore': 'Show more',
        'aimCatalog.card.showLess': 'Show less',
        'aimCatalog.status.deploying': 'Deploying',
        'models:status.pending': 'Pending',
        'models:status.starting': 'Starting',
        'aimCatalog.actions.deploy.label': 'Deploy',
        'aimCatalog.actions.undeploy.label': 'Undeploy',
        'aimCatalog.actions.workloadDetails.label': 'Workload details',
        'aimCatalog.actions.chatWithModel.label': 'Chat with model',
        'aimCatalog.actions.connect.label': 'Connect to model',
        'aimCatalog.tooltips.hfTokenRequired':
          'This model requires a Hugging Face token for deployment',
        'performanceMetrics.values.latency': 'Latency',
        'performanceMetrics.values.throughput': 'Throughput',
        'performanceMetrics.values.default': 'Default',
        'aimCatalog.unsupported.message':
          'This model is not supported on your hardware. Please refer to the',
        'aimCatalog.unsupported.linkText':
          'hardware requirements documentation',
        'aimCatalog.unsupported.linkUrl':
          'https://github.com/amd-enterprise-ai/aim-build/tree/main/docs/docs-aim/{{canonicalName}}',
      };

      if (
        key === 'aimCatalog.unsupported.linkUrl' &&
        options?.canonicalName !== undefined
      ) {
        return `https://github.com/amd-enterprise-ai/aim-build/tree/main/docs/docs-aim/${options.canonicalName}`;
      }
      if (key === 'aimCatalog.card.tagsMoreCount' && options?.count) {
        return `+${options.count} more`;
      }

      return translations[key] || key;
    },
  }),
}));

vi.mock('@/components/shared/ModelIcons', () => ({
  ModelIcon: ({ iconName }: { iconName?: string }) => (
    <div data-testid={`model-icon-${iconName || 'default'}`} />
  ),
}));

vi.mock('@amdenterpriseai/components', async (importOriginal) => ({
  ...(await importOriginal()),
  Button: ({
    children,
    onPress,
    endContent,
    'aria-expanded': ariaExpanded,
    'aria-controls': ariaControls,
    className,
  }: any) => (
    <button
      onClick={() => onPress?.()}
      aria-expanded={ariaExpanded}
      aria-controls={ariaControls}
      className={className}
    >
      {children}
      {endContent}
    </button>
  ),
  ActionButton: ({
    children,
    onPress,
    icon,
    isDisabled,
    className,
    'aria-label': ariaLabel,
  }: any) => (
    <button
      onClick={() => onPress?.()}
      disabled={isDisabled}
      data-testid="action-button"
      className={className}
      aria-label={ariaLabel}
    >
      {children}
      {icon}
    </button>
  ),
  ActionsDropdown: ({ children, actions }: any) => (
    <div data-testid="nested-dropdown">
      {children}
      <div data-testid="dropdown-content">
        {actions?.map((action: any) => (
          <div key={action.key}>
            <div>{action.label}</div>
            {action.description && <div>{action.description}</div>}
            {action.actions?.map((subAction: any) => (
              <div key={subAction.key}>
                <div>{subAction.label}</div>
                {subAction.description && <div>{subAction.description}</div>}
                {subAction.actions?.map((nestedAction: any) => (
                  <div key={nestedAction.key}>
                    <div>{nestedAction.label}</div>
                    {nestedAction.description && (
                      <div>{nestedAction.description}</div>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  ),
}));

// Mock ResizeObserver
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Mock requestAnimationFrame
global.requestAnimationFrame = ((cb: any) => {
  setTimeout(cb, 0);
  return 0;
}) as any;

global.cancelAnimationFrame = (() => {}) as any;

describe('AIMCard', () => {
  const onDeploy = vi.fn();
  const onOpenDetails = vi.fn();
  const onChatWithModel = vi.fn();
  const onConnectToModel = vi.fn();
  const onUndeploy = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic rendering', () => {
    it('renders card with aggregated AIM details', () => {
      const aggregatedAim = mockAggregatedAims[0];
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(
        screen.getByText(aggregatedAim.aggregated.title),
      ).toBeInTheDocument();
      expect(
        screen.getByText(aggregatedAim.aggregated.description.short),
      ).toBeInTheDocument();
    });

    it('renders the model icon', () => {
      const aggregatedAim = mockAggregatedAims[0];
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(
        screen.getByTestId(
          `model-icon-${aggregatedAim.aggregated.canonicalName}`,
        ),
      ).toBeInTheDocument();
    });

    it('displays AI Lab name correctly', () => {
      const aggregatedAim = mockAggregatedAims[0];
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(
        screen.getByText(aggregatedAim.aggregated.aiLabName),
      ).toBeInTheDocument();
    });

    it('displays version count correctly', () => {
      const aggregatedAim = mockAggregatedAims[0];
      const { container } = render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const versionCount = aggregatedAim.parsedAIMs.length;
      const versionText = versionCount === 1 ? 'version' : 'versions';
      // Check for version count in the card using regex to handle split text
      expect(
        screen.getByText(new RegExp(`${versionCount}.*${versionText}`, 'i')),
      ).toBeInTheDocument();
    });

    it('renders tags', () => {
      const aggregatedAim = mockAggregatedAims[0];
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      aggregatedAim.aggregated.tags.forEach((tag: string) => {
        expect(screen.getByText(tag)).toBeInTheDocument();
      });
    });

    it('shows gated model indicator when HF token is required', () => {
      const aggregatedAim = mockAggregatedAims[0];
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(screen.getByText('Gated')).toBeInTheDocument();
    });

    it('does not show gated indicator when HF token is not required', () => {
      const aggregatedAim = mockAggregatedAims[1];
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(screen.queryByText('Gated')).not.toBeInTheDocument();
    });

    it('displays accelerator types in metadata line', () => {
      const aggregatedAim: AggregatedAIM = {
        ...mockAggregatedAims[0],
        aggregated: {
          ...mockAggregatedAims[0].aggregated,
          acceleratorTypes: ['cpu', 'gpu'],
        },
      };
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(
        screen.getByTestId('aim-card-accelerator-types'),
      ).toHaveTextContent('CPU, GPU');
    });

    it('hides accelerator label when no types are known', () => {
      const aggregatedAim: AggregatedAIM = {
        ...mockAggregatedAims[0],
        aggregated: {
          ...mockAggregatedAims[0].aggregated,
          acceleratorTypes: [],
        },
      };
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(
        screen.queryByTestId('aim-card-accelerator-types'),
      ).not.toBeInTheDocument();
    });
  });

  describe('Deployment status badges', () => {
    it('shows pending status badge when models are pending', () => {
      const aggregatedAim = mockAggregatedAims[2];
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(screen.getByText('Pending')).toBeInTheDocument();
    });

    it('does not show pending badge when no pending deployments', () => {
      const aggregatedAim = mockAggregatedAims[0];
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(screen.queryByText('Pending')).not.toBeInTheDocument();
    });

    it('shows starting status badge when models are starting', () => {
      render(
        <AIMCard
          aggregatedAim={mockAggregatedAimWithStarting}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(screen.getByText('Starting')).toBeInTheDocument();
    });

    it('does not show starting badge when no starting deployments', () => {
      const aggregatedAim = mockAggregatedAims[0];
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(screen.queryByText('Starting')).not.toBeInTheDocument();
    });

    it('shows has deployments chip when model has deployed instances', () => {
      const aggregatedAim = mockAggregatedAims[0]; // DEPLOYED: 1
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(
        screen.getByTestId('aim-card-has-deployments'),
      ).toBeInTheDocument();
      expect(screen.getByText('Has deployments')).toBeInTheDocument();
    });

    it('does not show has deployments chip when no active deployments', () => {
      const aggregatedAim = mockAggregatedAims[1]; // DEPLOYED: 0, DEGRADED: 0
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(
        screen.queryByTestId('aim-card-has-deployments'),
      ).not.toBeInTheDocument();
    });

    it('shows has deployments chip and enables actions menu when only degraded instances exist', () => {
      const aggregatedAim: AggregatedAIM = {
        ...mockAggregatedAims[0],
        aggregated: { ...mockAggregatedAims[0].aggregated },
        deploymentCounts: {
          ...mockAggregatedAims[0].deploymentCounts,
          [AIMWorkloadStatus.DEPLOYED]: 0,
          [AIMWorkloadStatus.DEGRADED]: 1,
        },
      };
      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(
        screen.getByTestId('aim-card-has-deployments'),
      ).toBeInTheDocument();
      const actionsButton = screen.getByRole('button', {
        name: /actions menu/i,
      });
      expect(actionsButton).not.toBeDisabled();
    });
  });

  describe('Deploy button', () => {
    it('triggers deploy with non-preview version when available', async () => {
      const user = userEvent.setup();
      const aggregatedAim = mockAggregatedAims[0];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const deployButton = screen.getByRole('button', { name: /^deploy$/i });
      await user.click(deployButton);

      expect(onDeploy).toHaveBeenCalledTimes(1);
    });

    it('triggers deploy with preview version when no stable version exists', async () => {
      const user = userEvent.setup();
      const aggregatedAim = mockAggregatedAims[2];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const deployButton = screen.getByRole('button', { name: /^deploy$/i });
      await user.click(deployButton);

      expect(onDeploy).toHaveBeenCalledTimes(1);
    });
  });

  describe('Actions dropdown with deployments', () => {
    it('shows deployments section when models are deployed', async () => {
      const user = userEvent.setup();
      const aggregatedAim = mockAggregatedAims[0];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const actionsButton = screen.getByRole('button', {
        name: /actions menu/i,
      });
      await user.click(actionsButton);

      await waitFor(() => {
        expect(screen.getByText(/Deployments \(1\)/i)).toBeInTheDocument();
      });
    });

    it('shows Connect to model action for running deployments', async () => {
      const user = userEvent.setup();
      const aggregatedAim = mockAggregatedAims[0];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const actionsButton = screen.getByRole('button', {
        name: /actions menu/i,
      });
      await user.click(actionsButton);

      await waitFor(() => {
        expect(screen.getByText('Connect to model')).toBeInTheDocument();
      });
    });

    it('offers the Chat action for a chat deployment', async () => {
      const user = userEvent.setup();
      const aggregatedAim = mockAggregatedAims[0];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      await user.click(screen.getByRole('button', { name: /actions menu/i }));

      await waitFor(() => {
        expect(screen.getByText('Chat with model')).toBeInTheDocument();
      });
    });

    it('omits the Chat action for a transcription deployment', async () => {
      const user = userEvent.setup();
      const base = mockAggregatedAims[0];
      const transcriptionAim: AggregatedAIM = {
        ...base,
        parsedAIMs: base.parsedAIMs.map((aim) => ({
          ...aim,
          tags: ['transcription'],
        })),
      };

      render(
        <AIMCard
          aggregatedAim={transcriptionAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      await user.click(screen.getByRole('button', { name: /actions menu/i }));

      // Connect stays available; the chat-playground action is suppressed.
      await waitFor(() => {
        expect(screen.getByText('Connect to model')).toBeInTheDocument();
      });
      expect(screen.queryByText('Chat with model')).not.toBeInTheDocument();
    });

    it('shows multiple deployments correctly', async () => {
      const user = userEvent.setup();
      const aggregatedAim = mockAggregatedAimWithMultipleDeployments;

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const actionsButton = screen.getByRole('button', {
        name: /actions menu/i,
      });
      await user.click(actionsButton);

      await waitFor(() => {
        expect(screen.getByText(/Deployments \(2\)/i)).toBeInTheDocument();
      });
    });

    it('displays deployment version and metric info', async () => {
      const user = userEvent.setup();
      const aggregatedAim = mockAggregatedAims[0];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const actionsButton = screen.getByRole('button', {
        name: /actions menu/i,
      });
      await user.click(actionsButton);

      // The dropdown content should be visible after click
      const dropdownContent = screen.getByTestId('dropdown-content');
      expect(dropdownContent).toBeInTheDocument();

      // Verify deployment info is in the component (metric uses performanceMetrics.values translation)
      expect(dropdownContent.textContent).toContain('2.0.1');
      expect(dropdownContent.textContent).toContain('Latency');
    });

    it('shows nested actions for each deployment', async () => {
      const user = userEvent.setup();
      const aggregatedAim = mockAggregatedAims[0];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const actionsButton = screen.getByRole('button', {
        name: /actions menu/i,
      });
      await user.click(actionsButton);

      // The deployments section should appear
      await waitFor(() => {
        expect(screen.getByText(/Deployments \(1\)/i)).toBeInTheDocument();
      });
    });

    it('has actions configured for deployments', async () => {
      const user = userEvent.setup();
      const aggregatedAim = mockAggregatedAims[0];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const actionsButton = screen.getByRole('button', {
        name: /actions menu/i,
      });
      await user.click(actionsButton);

      // Verify the actions dropdown opens
      await waitFor(() => {
        expect(screen.getByText(/Deployments \(1\)/i)).toBeInTheDocument();
      });
    });

    it('shows deployment info in actions menu', async () => {
      const user = userEvent.setup();
      const aggregatedAim = mockAggregatedAims[0];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const actionsButton = screen.getByRole('button', {
        name: /actions menu/i,
      });
      await user.click(actionsButton);

      // The deployment service name should be visible
      await waitFor(() => {
        expect(screen.getByText('llama-2-7b-service')).toBeInTheDocument();
      });
    });

    it('displays deployment service name in menu', async () => {
      const user = userEvent.setup();
      const aggregatedAim = mockAggregatedAims[0];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const actionsButton = screen.getByRole('button', {
        name: /actions menu/i,
      });
      await user.click(actionsButton);

      await waitFor(() => {
        // The service name should be in the dropdown
        expect(screen.getByText('llama-2-7b-service')).toBeInTheDocument();
      });
    });

    it('disables actions dropdown when no deployments exist', () => {
      const aggregatedAim = mockAggregatedAims[1];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const actionsButton = screen.getByRole('button', {
        name: /actions menu/i,
      });
      expect(actionsButton).toBeDisabled();
    });

    it('shows actions menu for pending deployments', async () => {
      const user = userEvent.setup();
      const aggregatedAim = mockAggregatedAims[2];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const actionsButton = screen.getByRole('button', {
        name: /actions menu/i,
      });
      await user.click(actionsButton);

      // The deployments section should appear
      await waitFor(() => {
        expect(screen.getByText(/Deployments \(1\)/i)).toBeInTheDocument();
      });
    });
  });

  describe('Description expand/collapse', () => {
    const renderCard = (aim = mockAggregatedAims[0]) =>
      render(
        <AIMCard
          aggregatedAim={aim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

    it('renders description text', () => {
      const aggregatedAim = mockAggregatedAims[0];
      renderCard(aggregatedAim);
      expect(
        screen.getByText(aggregatedAim.aggregated.description.short),
      ).toBeInTheDocument();
    });

    it('applies line-clamp-3 class to description paragraph initially', () => {
      const { container } = renderCard();
      expect(container.querySelector('p.line-clamp-3')).toBeInTheDocument();
    });

    it('description paragraph is not interactive — has no role=button', () => {
      const { container } = renderCard();
      const p = container.querySelector('p');
      expect(p).not.toHaveAttribute('role', 'button');
      expect(p).not.toHaveAttribute('tabindex');
    });

    describe('when description overflows 3 lines', () => {
      const originalScrollHeight = Object.getOwnPropertyDescriptor(
        HTMLElement.prototype,
        'scrollHeight',
      );

      beforeEach(() => {
        Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
          configurable: true,
          get: () => 200,
        });
      });

      afterEach(() => {
        if (originalScrollHeight) {
          Object.defineProperty(
            HTMLElement.prototype,
            'scrollHeight',
            originalScrollHeight,
          );
        } else {
          delete (HTMLElement.prototype as { scrollHeight?: number })
            .scrollHeight;
        }
      });

      it('shows "Show more" button', async () => {
        renderCard();
        await waitFor(() => {
          expect(
            screen.getByRole('button', { name: /show more/i }),
          ).toBeInTheDocument();
        });
      });

      it('"Show more" button starts with aria-expanded=false', async () => {
        renderCard();
        const button = await screen.findByRole('button', {
          name: /show more/i,
        });
        expect(button).toHaveAttribute('aria-expanded', 'false');
      });

      it('"Show more" button has aria-controls pointing to the description element', async () => {
        renderCard();
        const button = await screen.findByRole('button', {
          name: /show more/i,
        });
        const controlledId = button.getAttribute('aria-controls');
        expect(controlledId).toBeTruthy();
        expect(document.getElementById(controlledId!)).toBeInTheDocument();
      });

      it('clicking "Show more" changes button label to "Show less"', async () => {
        const user = userEvent.setup();
        renderCard();
        const showMore = await screen.findByRole('button', {
          name: /show more/i,
        });
        await user.click(showMore);
        expect(
          screen.getByRole('button', { name: /show less/i }),
        ).toBeInTheDocument();
        expect(
          screen.queryByRole('button', { name: /show more/i }),
        ).not.toBeInTheDocument();
      });

      it('clicking "Show more" sets aria-expanded=true', async () => {
        const user = userEvent.setup();
        renderCard();
        const showMore = await screen.findByRole('button', {
          name: /show more/i,
        });
        await user.click(showMore);
        expect(
          screen.getByRole('button', { name: /show less/i }),
        ).toHaveAttribute('aria-expanded', 'true');
      });

      it('clicking "Show more" removes line-clamp-3 from the description', async () => {
        const user = userEvent.setup();
        const { container } = renderCard();
        const showMore = await screen.findByRole('button', {
          name: /show more/i,
        });
        await user.click(showMore);
        expect(
          container.querySelector('p.line-clamp-3'),
        ).not.toBeInTheDocument();
      });

      it('does not mutate the description element while measuring expanded overflow', async () => {
        const user = userEvent.setup();
        const addSpy = vi.spyOn(DOMTokenList.prototype, 'add');
        const removeSpy = vi.spyOn(DOMTokenList.prototype, 'remove');
        renderCard();
        const showMore = await screen.findByRole('button', {
          name: /show more/i,
        });
        addSpy.mockClear();
        removeSpy.mockClear();

        await user.click(showMore);
        await waitFor(() => {
          expect(
            screen.getByRole('button', { name: /show less/i }),
          ).toBeInTheDocument();
        });

        expect(addSpy).not.toHaveBeenCalledWith('line-clamp-3');
        expect(removeSpy).not.toHaveBeenCalledWith('line-clamp-3');

        addSpy.mockRestore();
        removeSpy.mockRestore();
      });

      it('clicking "Show less" collapses back and restores "Show more" label', async () => {
        const user = userEvent.setup();
        renderCard();
        const showMore = await screen.findByRole('button', {
          name: /show more/i,
        });
        await user.click(showMore);
        const showLess = screen.getByRole('button', { name: /show less/i });
        await user.click(showLess);
        await waitFor(() => {
          expect(
            screen.getByRole('button', { name: /show more/i }),
          ).toHaveAttribute('aria-expanded', 'false');
        });
      });
    });

    describe('when description fits within 3 lines', () => {
      it('does not show "Show more" button', async () => {
        renderCard();
        // scrollHeight === clientHeight === 0 in jsdom — no overflow
        await new Promise((r) => setTimeout(r, 10));
        expect(
          screen.queryByRole('button', { name: /show more/i }),
        ).not.toBeInTheDocument();
      });
    });
  });

  describe('Status indicators', () => {
    it('does not show pending badge for deployed models', () => {
      const aggregatedAim = mockAggregatedAims[0];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      // No pending badge should be shown for fully deployed models
      expect(screen.queryByText('Pending')).not.toBeInTheDocument();
    });

    it('shows pending status badge for pending deployments', () => {
      const aggregatedAim = mockAggregatedAims[2];

      render(
        <AIMCard
          aggregatedAim={aggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(screen.getByText('Pending')).toBeInTheDocument();
    });
  });

  describe('Unsupported models', () => {
    it('shows unsupported banner when model is not supported', () => {
      render(
        <AIMCard
          aggregatedAim={mockUnsupportedAggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const banner = screen.getByTestId('unsupported-banner');
      expect(banner).toBeInTheDocument();
      expect(banner).toHaveAttribute('role', 'alert');
      expect(banner).toHaveTextContent(
        /This model is not supported on your hardware/,
      );
      expect(
        screen.getByText('hardware requirements documentation'),
      ).toBeInTheDocument();
    });

    it('does not show unsupported banner for supported models', () => {
      render(
        <AIMCard
          aggregatedAim={mockAggregatedAims[0]}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(
        screen.queryByTestId('unsupported-banner'),
      ).not.toBeInTheDocument();
    });

    it('does not show deploy button for unsupported models', () => {
      render(
        <AIMCard
          aggregatedAim={mockUnsupportedAggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      expect(
        screen.queryByRole('button', { name: /deploy/i }),
      ).not.toBeInTheDocument();
      expect(screen.getByTestId('unsupported-banner')).toBeInTheDocument();
    });

    it('applies muted opacity to card content when unsupported', () => {
      const { container } = render(
        <AIMCard
          aggregatedAim={mockUnsupportedAggregatedAim}
          onDeploy={onDeploy}
          onOpenDetails={onOpenDetails}
          onChatWithModel={onChatWithModel}
          onConnectToModel={onConnectToModel}
          onUndeploy={onUndeploy}
        />,
      );

      const mutedElements = container.querySelectorAll('.opacity-50');
      expect(mutedElements.length).toBeGreaterThan(0);
    });
  });
});
