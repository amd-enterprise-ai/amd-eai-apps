// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { SessionProvider } from 'next-auth/react';

import {
  mockWorkspaceCatalogItems,
  mockProjectScopedWorkspaceCatalogItems,
} from '@/__mocks__/services/app/workspaces.data';
import { listAllWorkloads, deleteWorkspace } from '@/lib/app/workloads';
import { listCharts } from '@/lib/app/charts';

import { generateMockWorkspaceWorkloads } from '@/__mocks__/utils/workloads-mock';

import WorkspacesPage from '@/pages/[project]/workspaces';

import wrapper from '@/__tests__/ProviderWrapper';
import { Mock, vi } from 'vitest';

vi.mock('@/lib/app/workloads', async (importOriginal) => ({
  ...(await importOriginal()),
  listAllWorkloads: vi.fn(),
  deleteWorkspace: vi.fn(),
}));

vi.mock('@/lib/app/charts', async (importOriginal) => ({
  ...(await importOriginal()),
  listCharts: vi.fn(),
}));

// Mock RequestSoftware to avoid loading its bg.svg asset in jsdom
vi.mock('@/components/shared/RequestSoftware/RequestSoftware', () => ({
  RequestSoftware: () => <div data-testid="request-software" />,
}));

vi.mock('@amdenterpriseai/components', async (importOriginal) => ({
  ...(await importOriginal()),
  ActionsDropdown: ({ children, actions }: any) => (
    <div data-testid="nested-dropdown">
      {children}
      <div data-testid="dropdown-content">
        {actions?.map((action: any) => (
          <button
            key={action.key}
            type="button"
            disabled={action.isDisabled}
            onClick={() => action.onPress?.()}
          >
            {action.label}
          </button>
        ))}
      </div>
    </div>
  ),
}));

// Mock next/image: the real component rejects relative srcs and requires a
// configured loader, neither of which exist in jsdom.
vi.mock('next/image', () => ({
  default: ({ src, alt, width, height, className }: any) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt}
      width={width}
      height={height}
      className={className}
    />
  ),
}));

// The global setup mock drops interpolation options, so the undeploy copy would
// render identically for every workspace. Echo the name to keep it observable.
vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { name?: string }) =>
      options?.name ? `${key}:${options.name}` : key,
    i18n: {
      language: 'en',
      changeLanguage: vi.fn(),
    },
  }),
  Trans: ({
    children,
    i18nKey,
  }: {
    children?: React.ReactNode;
    i18nKey?: string;
  }) => children ?? i18nKey ?? null,
  appWithTranslation: (Component: React.ComponentType) => Component,
}));

const mockSession = {
  error: null as any,
  expires: '2125-01-01T00:00:00',
  user: {
    id: 'test',
    email: 'user@example.com',
    roles: [],
  },
};

describe('Catalog Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listCharts as Mock).mockResolvedValue(mockWorkspaceCatalogItems);
    (listAllWorkloads as Mock).mockResolvedValue([]);
  });

  it('renders the catalog page', async () => {
    await act(async () => {
      render(
        <SessionProvider session={mockSession}>
          <WorkspacesPage />
        </SessionProvider>,
        { wrapper },
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Test workload 1')).toBeInTheDocument();
      expect(screen.getByText('Test workload 2')).toBeInTheDocument();
    });
  });

  it.skip('allows filtering catalog items by category', async () => {
    await act(async () => {
      render(
        <SessionProvider session={mockSession}>
          <WorkspacesPage />
        </SessionProvider>,
        { wrapper },
      );
    });

    const filterButton = screen.getByTestId('catalog-category-filter');
    await act(async () => {
      fireEvent.click(filterButton);
    });

    const developmentOption = await screen.findByTestId('development-option');
    await act(async () => {
      fireEvent.click(developmentOption);
    });

    expect(screen.getByText('Test workload 2')).toBeInTheDocument();
    expect(screen.queryByText('Test workload 1')).not.toBeInTheDocument();
  });

  it('allows searching catalog items by text', async () => {
    await act(async () => {
      render(
        <SessionProvider session={mockSession}>
          <WorkspacesPage />
        </SessionProvider>,
        { wrapper },
      );
    });

    const searchInput = screen.getByPlaceholderText(
      'actions.search.placeholder',
    );
    fireEvent.change(searchInput, { target: { value: 'Test workload 2' } });

    await waitFor(() => {
      expect(screen.getByText('Test workload 2')).toBeInTheDocument();
      expect(screen.queryByText('Test workload 1')).not.toBeInTheDocument();
    });
  });

  it('allows refreshing the catalog', async () => {
    await act(async () => {
      render(
        <SessionProvider session={mockSession}>
          <WorkspacesPage />
        </SessionProvider>,
        { wrapper },
      );
    });

    // Wait for the initial query to complete
    await waitFor(() => {
      expect(listCharts).toHaveBeenCalledTimes(1);
    });

    // Reset the mock to clearly track the second call
    vi.clearAllMocks();
    const refreshButton = screen.getByRole('button', { name: /refresh/i });
    await act(async () => {
      fireEvent.click(refreshButton);
    });

    await waitFor(() => {
      expect(listCharts).toHaveBeenCalledTimes(1);
    });
  });

  it('renders the catalog page with user scope without running workloads', async () => {
    (listCharts as Mock).mockResolvedValue([mockWorkspaceCatalogItems[0]]);
    (listAllWorkloads as Mock).mockResolvedValue([]);

    await act(async () => {
      render(
        <SessionProvider session={mockSession}>
          <WorkspacesPage />
        </SessionProvider>,
        { wrapper },
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Test workload 1')).toBeInTheDocument();
      expect(screen.getByText('list.actions.deploy')).toBeInTheDocument();
    });
  });

  it('renders the catalog page with user scope with running workloads', async () => {
    (listCharts as Mock).mockResolvedValue([mockWorkspaceCatalogItems[0]]);

    (listAllWorkloads as Mock).mockResolvedValue(
      generateMockWorkspaceWorkloads(
        1,
        mockWorkspaceCatalogItems[0].name,
        'Running',
        'WORKSPACE',
      ),
    );

    await act(async () => {
      render(
        <SessionProvider session={mockSession}>
          <WorkspacesPage />
        </SessionProvider>,
        { wrapper },
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Test workload 1')).toBeInTheDocument();
      expect(screen.queryByText('list.actions.deploy')).not.toBeInTheDocument();
      expect(screen.getByText('list.actions.undeploy')).toBeInTheDocument();
      expect(screen.getByText('list.actions.launch')).toBeInTheDocument();
    });
  });

  it('renders the catalog page with project scope without running workloads', async () => {
    (listCharts as Mock).mockResolvedValue(
      mockProjectScopedWorkspaceCatalogItems,
    );
    (listAllWorkloads as Mock).mockResolvedValue([]);

    await act(async () => {
      render(
        <SessionProvider session={mockSession}>
          <WorkspacesPage />
        </SessionProvider>,
        { wrapper },
      );
    });

    await waitFor(() => {
      expect(
        screen.getAllByText('MLflow Tracking Server')[0],
      ).toBeInTheDocument();
      expect(screen.getByText('list.actions.deploy')).toBeInTheDocument();
    });
  });

  it('renders the catalog page with project scope with running workloads', async () => {
    (listCharts as Mock).mockResolvedValue(
      mockProjectScopedWorkspaceCatalogItems,
    );

    (listAllWorkloads as Mock).mockResolvedValue(
      generateMockWorkspaceWorkloads(
        1,
        mockProjectScopedWorkspaceCatalogItems[0].name,
        'Running',
        'WORKSPACE',
      ),
    );

    await act(async () => {
      render(
        <SessionProvider session={mockSession}>
          <WorkspacesPage />
        </SessionProvider>,
        { wrapper },
      );
    });

    await waitFor(() => {
      expect(
        screen.getAllByText('MLflow Tracking Server')[0],
      ).toBeInTheDocument();
      expect(screen.queryByText('list.actions.deploy')).not.toBeInTheDocument();
      expect(screen.getByText('list.actions.undeploy')).toBeInTheDocument();
      expect(screen.getByText('list.actions.launch')).toBeInTheDocument();
    });
  });

  it('Workspace page calls listAllWorkloads with type WORKSPACE and status RUNNING, PENDING, FAILED', async () => {
    await act(async () => {
      render(
        <SessionProvider session={mockSession}>
          <WorkspacesPage />
        </SessionProvider>,
        { wrapper },
      );
    });

    expect(listAllWorkloads).toHaveBeenCalledWith('project1', {
      workloadType: ['WORKSPACE'],
      statusFilter: ['Running', 'Pending', 'Failed'],
    });
  });

  it('shows disabled launch button when workload is pending', async () => {
    (listCharts as Mock).mockResolvedValue([mockWorkspaceCatalogItems[0]]);

    (listAllWorkloads as Mock).mockResolvedValue(
      generateMockWorkspaceWorkloads(
        1,
        mockWorkspaceCatalogItems[0].name,
        'Pending',
        'WORKSPACE',
      ),
    );

    await act(async () => {
      render(
        <SessionProvider session={mockSession}>
          <WorkspacesPage />
        </SessionProvider>,
        { wrapper },
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Test workload 1')).toBeInTheDocument();
      expect(screen.getByText('list.actions.launch')).toBeDisabled();
      expect(
        screen.queryByText('list.actions.pending'),
      ).not.toBeInTheDocument();
    });
  });

  it('shows Failed chip and Delete failed workload when a workload has FAILED status', async () => {
    (listCharts as Mock).mockResolvedValue([mockWorkspaceCatalogItems[0]]);

    const failedWorkloadsResponse = generateMockWorkspaceWorkloads(
      1,
      mockWorkspaceCatalogItems[0].name,
      'Failed',
      'WORKSPACE',
    );
    (listAllWorkloads as Mock).mockResolvedValue(failedWorkloadsResponse);

    await act(async () => {
      render(
        <SessionProvider session={mockSession}>
          <WorkspacesPage />
        </SessionProvider>,
        { wrapper },
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Test workload 1')).toBeInTheDocument();
      expect(screen.getByText('status.Failed')).toBeInTheDocument();
      expect(
        screen.getByText('list.actions.deleteFailedWorkload'),
      ).toBeInTheDocument();
      expect(screen.queryByText('list.actions.deploy')).not.toBeInTheDocument();
      expect(
        screen.queryByText('list.actions.undeploy'),
      ).not.toBeInTheDocument();
    });
  });

  it('names the workspace in the undeploy confirmation and undeploys the running workload', async () => {
    (listCharts as Mock).mockResolvedValue([mockWorkspaceCatalogItems[0]]);

    const runningWorkloads = generateMockWorkspaceWorkloads(
      1,
      mockWorkspaceCatalogItems[0].name,
      'Running',
      'WORKSPACE',
    );
    (listAllWorkloads as Mock).mockResolvedValue(runningWorkloads);
    (deleteWorkspace as Mock).mockResolvedValue(undefined);

    await act(async () => {
      render(
        <SessionProvider session={mockSession}>
          <WorkspacesPage />
        </SessionProvider>,
        { wrapper },
      );
    });

    await waitFor(() => {
      expect(screen.getByText('list.actions.undeploy')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText('list.actions.undeploy'));
    });

    await waitFor(() => {
      const modal = screen.getByTestId('confirmation-modal');
      expect(
        within(modal).getByText('description:Test workload 1'),
      ).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText('actions.confirm.title'));
    });

    await waitFor(() => {
      expect(deleteWorkspace).toHaveBeenCalledWith(
        'project1',
        runningWorkloads[0].id,
      );
    });
  });

  it('calls deleteWorkspace with failed workspace id when Delete failed workload is confirmed', async () => {
    (listCharts as Mock).mockResolvedValue([mockWorkspaceCatalogItems[0]]);

    const failedWorkloadsResponse = generateMockWorkspaceWorkloads(
      1,
      mockWorkspaceCatalogItems[0].name,
      'Failed',
      'WORKSPACE',
    );
    const failedWorkloadId = failedWorkloadsResponse[0].id;
    (listAllWorkloads as Mock).mockResolvedValue(failedWorkloadsResponse);
    (deleteWorkspace as Mock).mockResolvedValue(undefined);

    await act(async () => {
      render(
        <SessionProvider session={mockSession}>
          <WorkspacesPage />
        </SessionProvider>,
        { wrapper },
      );
    });

    await waitFor(() => {
      expect(
        screen.getByText('list.actions.deleteFailedWorkload'),
      ).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText('list.actions.deleteFailedWorkload'));
    });

    await waitFor(() => {
      const modal = screen.getByTestId('confirmation-modal');
      expect(within(modal).getByText('title')).toBeInTheDocument();
      expect(
        within(modal).getByText('description:Test workload 1'),
      ).toBeInTheDocument();
    });

    const confirmButton = screen.getByText('actions.confirm.title');
    await act(async () => {
      fireEvent.click(confirmButton);
    });

    await waitFor(() => {
      expect(deleteWorkspace).toHaveBeenCalledWith(
        'project1',
        failedWorkloadId,
      );
    });
  });
});
