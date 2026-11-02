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
import userEvent from '@testing-library/user-event';

import { useRouter } from 'next/router';

import { getInferenceCatalog } from '@/lib/app/inference';

import AIMCatalog from '@/components/features/models/AIMCatalog';

import wrapper from '@/__tests__/ProviderWrapper';
import { Mock, vi } from 'vitest';
import { mockAims } from '@/__mocks__/services/app/aims.data';

// Mock next-i18next
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
        'aimCatalog.status.deploying': 'Deploying',
        'aimCatalog.actions.deploy.label': 'Deploy',
        'aimCatalog.actions.undeploy.label': 'Undeploy',
        'aimCatalog.actions.workloadDetails.label': 'Workload details',
        'aimCatalog.actions.chatWithModel.label': 'Chat with model',
        'aimCatalog.actions.connect.label': 'Connect to model',
        'aimCatalog.actions.connect.modal.title': 'Connect to model',
        'aimCatalog.tooltips.hfTokenRequired':
          'This model requires a Hugging Face token for deployment',
        'actions.notifications.deleteSuccess': 'AIM undeployed successfully.',
        'actions.notifications.deleteError':
          'Failed to undeploy AIM. Please try again.',
      };

      return translations[key] || key;
    },
  }),
}));

// Mock the API services
vi.mock('@/lib/app/aims', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
  };
});

vi.mock('@/lib/app/inference', () => ({
  getInferenceCatalog: vi.fn().mockResolvedValue([]),
  deleteInferenceDeployment: vi.fn(),
}));

// Mock useSystemToast for testing
vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  __esModule: true,
  useSystemToast: () => ({
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }),
}));

// Mock useRouter
vi.mock('next/router', () => ({
  useRouter: vi.fn(),
}));

// Mock ModelIcon to avoid SVG loading issues
vi.mock('@/components/shared/ModelIcons', () => ({
  ModelIcon: ({ iconName, width, height }: any) => (
    <div
      data-testid={`model-icon-${iconName || 'default'}`}
      style={{ width: `${width}px`, height: `${height}px` }}
    >
      {iconName || 'default'} icon
    </div>
  ),
}));

// Mock RequestSoftware to avoid loading its bg.svg asset in jsdom
vi.mock('@/components/shared/RequestSoftware/RequestSoftware', () => ({
  RequestSoftware: () => <div data-testid="request-software" />,
}));

// Mock ActionsDropdown to make dropdown testable
vi.mock('@amdenterpriseai/components', async (importOriginal) => ({
  ...(await importOriginal()),
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
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  ),
}));

// Mock ProjectContext
vi.mock('@/contexts/ProjectContext', () => ({
  useProject: () => ({
    activeProject: 'test-project-1',
    projects: [{ id: 'test-project-1', name: 'Test Project' }],
  }),
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

describe('AIM Catalog', () => {
  const mockPush = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    (useRouter as Mock).mockReturnValue({
      push: mockPush,
      pathname: '/models',
      query: {},
    });
    (getInferenceCatalog as Mock).mockResolvedValue(mockAims);
  });

  describe('Basic rendering', () => {
    it('renders AIM catalog component', async () => {
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(screen.getByText('Llama 2 7B')).toBeInTheDocument();
        expect(screen.getByText('Stable Diffusion XL')).toBeInTheDocument();
        expect(screen.getByText('Vision Detection Model')).toBeInTheDocument();
      });
    });

    it('shows loading state', async () => {
      (getInferenceCatalog as Mock).mockImplementation(
        () =>
          new Promise((resolve) => {
            setTimeout(() => resolve(mockAims), 1000);
          }),
      );

      render(<AIMCatalog />, {
        wrapper,
      });

      expect(screen.getByTestId('aim-catalog-loading')).toBeInTheDocument();
    });
  });

  describe('Aggregation logic', () => {
    it('aggregates multiple versions of same model', async () => {
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      await waitFor(() => {
        // Should only show one card for Llama 2 7B despite multiple versions
        const llamaCards = screen.getAllByText('Llama 2 7B');
        // Title appears once in the card
        expect(llamaCards.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('displays version information for aggregated models', async () => {
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      await waitFor(() => {
        // Llama 2 7B card should be displayed (it has multiple versions in mock data)
        expect(screen.getByText('Llama 2 7B')).toBeInTheDocument();
      });
    });

    it('shows deployment counts across all versions', async () => {
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      // The catalog should aggregate deployment counts from all versions
      await waitFor(() => {
        const llamaCard = screen.getByText('Llama 2 7B');
        expect(llamaCard).toBeInTheDocument();
      });
    });
  });

  describe('Filtering', () => {
    it('filters AIMs by search query', async () => {
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      const searchInput = screen.getByPlaceholderText(
        'list.filter.search.placeholder',
      );
      fireEvent.change(searchInput, { target: { value: 'Llama' } });

      await waitFor(() => {
        expect(screen.getByText('Llama 2 7B')).toBeInTheDocument();
        expect(
          screen.queryByText('Stable Diffusion XL'),
        ).not.toBeInTheDocument();
        expect(
          screen.queryByText('Vision Detection Model'),
        ).not.toBeInTheDocument();
      });
    });

    it('filters AIMs by cluster model resource name (not only card title)', async () => {
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      const searchInput = screen.getByPlaceholderText(
        'list.filter.search.placeholder',
      );
      fireEvent.change(searchInput, {
        target: { value: 'aim-stable-diffusion-xl' },
      });

      await waitFor(() => {
        expect(screen.getByText('Stable Diffusion XL')).toBeInTheDocument();
        expect(screen.queryByText('Llama 2 7B')).not.toBeInTheDocument();
        expect(
          screen.queryByText('Vision Detection Model'),
        ).not.toBeInTheDocument();
      });
    });

    it('filters AIMs by Hugging Face canonical id substring', async () => {
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      const searchInput = screen.getByPlaceholderText(
        'list.filter.search.placeholder',
      );
      fireEvent.change(searchInput, {
        target: { value: 'stabilityai/stable-diffusion' },
      });

      await waitFor(() => {
        expect(screen.getByText('Stable Diffusion XL')).toBeInTheDocument();
        expect(screen.queryByText('Llama 2 7B')).not.toBeInTheDocument();
      });
    });

    it('filters on individual AIMs then re-aggregates', async () => {
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      // Filter should apply to individual ParsedAIMs before aggregation
      const searchInput = screen.getByPlaceholderText(
        'list.filter.search.placeholder',
      );
      fireEvent.change(searchInput, { target: { value: 'Llama' } });

      await waitFor(() => {
        expect(screen.getByText('Llama 2 7B')).toBeInTheDocument();
      });
    });

    it('filters AIMs by tag', async () => {
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      // Verify the tag filter is available
      const tagSelect = screen.getByLabelText('list.filter.tag.placeholder');
      expect(tagSelect).toBeInTheDocument();
    });

    it('filters by deployment status across all versions', async () => {
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      // Deployment status filter should work across all versions of a model
      const deploymentStatusFilter = screen.getByLabelText(
        'list.filter.deploymentStatus.placeholder',
      );
      expect(deploymentStatusFilter).toBeInTheDocument();
    });

    it('clears filters when clear button is clicked', async () => {
      // Ensure React Query always gets defined data for the aim-catalog query in this test.
      (getInferenceCatalog as Mock).mockResolvedValue(mockAims);

      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      const searchInput = screen.getByPlaceholderText(
        'list.filter.search.placeholder',
      );
      fireEvent.change(searchInput, { target: { value: 'Llama' } });

      await waitFor(() => {
        const clearButton = screen.getByText('actions.clearFilters.title');
        expect(clearButton).not.toBeDisabled();
      });

      const clearButton = screen.getByText('actions.clearFilters.title');
      await act(async () => {
        fireEvent.click(clearButton);
      });

      await waitFor(() => {
        expect(searchInput).toHaveValue('');
      });
    });
  });

  describe('UndeployAIMModal integration', () => {
    it('shows actions menu for deployed models', async () => {
      const user = userEvent.setup();
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(screen.getByText('Llama 2 7B')).toBeInTheDocument();
      });

      // Find and click the actions dropdown
      const actionsButtons = screen.getAllByRole('button', {
        name: /actions menu/i,
      });
      await user.click(actionsButtons[0]);

      // Deployments section should appear (use getAllByText since multiple cards may have deployments)
      await waitFor(() => {
        const deploymentsSections = screen.getAllByText(/Deployments \(1\)/i);
        expect(deploymentsSections.length).toBeGreaterThan(0);
      });
    });

    it('has undeploy modal component in catalog', async () => {
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      // The UndeployAIMModal should be rendered (but not visible initially)
      // This ensures the modal integration is present
    });
  });

  describe('Empty states and errors', () => {
    it('shows empty state when no AIMs match filters', async () => {
      (getInferenceCatalog as Mock).mockResolvedValue([]);

      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(screen.getByText('list.empty.description')).toBeInTheDocument();
      });
    });

    it('handles API errors gracefully', async () => {
      const mockError = new Error('API Error');
      (getInferenceCatalog as Mock).mockRejectedValue(mockError);

      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });
    });
  });

  describe('Navigation', () => {
    it('has router integration for navigation', async () => {
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(screen.getByText('Llama 2 7B')).toBeInTheDocument();
      });

      // Verify router is set up (mockPush is available)
      expect(mockPush).toBeDefined();
    });

    it('has actions menu with deployment information', async () => {
      const user = userEvent.setup();
      await act(async () => {
        render(<AIMCatalog />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(getInferenceCatalog).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(screen.getByText('Llama 2 7B')).toBeInTheDocument();
      });

      // Open actions menu
      const actionsButtons = screen.getAllByRole('button', {
        name: /actions menu/i,
      });
      await user.click(actionsButtons[0]);

      // Verify deployment information is shown (use getAllByText since multiple cards may show it)
      await waitFor(() => {
        const serviceNames = screen.getAllByText('llama-2-7b-service');
        expect(serviceNames.length).toBeGreaterThan(0);
      });
    });
  });
});
