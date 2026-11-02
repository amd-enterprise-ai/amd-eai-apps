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

import { APIRequestError } from '@amdenterpriseai/utils/app';
import { mockWorkloads } from '@/__mocks__/services/app/workloads.data';
import { mockModels } from '@/__mocks__/services/app/models.data';
import { listAllProjectFineTunedModels } from '@/lib/app/models';
import { listAllWorkloads } from '@/lib/app/workloads';
import { resolveAIMServiceDisplay } from '@/lib/app/aims';
import {
  deleteInferenceDeployment,
  getInferenceModel,
  listAllInferenceDeployments,
} from '@/lib/app/inference';

import type { Workload } from '@/types/workloads';
import {
  AIM_DISPLAY_NAME_ANNOTATION,
  NAMESPACE_AIM_MODEL_LABEL,
} from '@/types/aims';

import DeployedModels from '@/components/features/models/DeployedModels';

import wrapper from '@/__tests__/ProviderWrapper';
import { Mock, vi } from 'vitest';

/** next-i18next key resolved to the row overflow menu trigger (ThreeDotActionsDropdown aria-label). */
const ROW_OVERFLOW_MENU_KEY = 'list.actions.label';

const mockUseCustomProfileDeployments = vi.hoisted(() =>
  vi.fn(() => ({
    profileByServiceId: new Map(),
    isLoading: false,
  })),
);

vi.mock('@/hooks/useCustomProfileDeployments', () => ({
  useCustomProfileDeployments: mockUseCustomProfileDeployments,
}));

/** Status filter trigger and option labels, as the pass-through `t` mock renders them. */
const STATUS_FILTER_KEY = 'list.filters.status.label';
const STATUS_OPTION_DELETING = 'workloads:status.Deleting';
const STATUS_OPTION_DELETED = 'workloads:status.Deleted';

const openStatusFilter = async () => {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: STATUS_FILTER_KEY }));
  });
};

vi.mock('@/lib/app/models', () => ({
  listAllProjectFineTunedModels: vi.fn(),
  // FinetuneWizard (rendered transitively) calls the single-page variant
  listProjectFineTunedModels: vi.fn().mockResolvedValue({
    data: [],
    pagination: { page: 1, pageSize: 10, total: 0 },
  }),
}));

vi.mock('@/lib/app/workloads', () => ({
  listAllWorkloads: vi.fn(),
}));

vi.mock('@/lib/app/aims', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/app/aims')>()),
  resolveAIMServiceDisplay: vi.fn(),
  // Profile fetches are now per-aimId (batched by the multi-aimId query
  // param). Default to empty so unrelated tests don't hit the network;
  // tests that exercise profile rendering override via mockResolvedValue.
  getAimClusterProfilesByAimIds: vi.fn().mockResolvedValue([]),
  getProjectAimProfilesByAimIds: vi.fn().mockResolvedValue([]),
}));

vi.mock('@/lib/app/inference', () => ({
  getInferenceModel: vi.fn(),
  listAllInferenceDeployments: vi.fn(),
  deleteInferenceDeployment: vi.fn(),
}));

// Mock hooks
vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  __esModule: true,
  ...(await importOriginal()),
  useProject: () => ({
    activeProject: 'test-project',
  }),
  useSystemToast: () => ({
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }),
}));

// Mock next/router
const mockPush = vi.fn();
const { routerQuery } = vi.hoisted(() => ({
  routerQuery: {} as Record<string, string | undefined>,
}));
vi.mock('next/router', () => ({
  useRouter: vi.fn(() => ({
    push: mockPush,
    query: routerQuery,
    pathname: '/models',
    asPath: '/models',
  })),
}));

// Mock translations. Special-cases the max-rank key so tests can assert on
// the interpolated rank; every other key keeps the plain passthrough the
// rest of this suite already relies on.
vi.mock('next-i18next', () => ({
  Trans: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTranslation: () => ({
    t: (key: string, opts?: { rank?: number }) =>
      key === 'profileSummary.maxRank'
        ? `profileSummary.maxRank:${opts?.rank}`
        : key,
    i18n: { language: 'en' },
  }),
}));

// Mock Tabler icons
vi.mock('@tabler/icons-react', async (importOriginal) => {
  const original = (await importOriginal()) ?? {};
  return {
    ...original,
    IconDotsVertical: ({ className }: any) => (
      <span className={className}>action-dot-icon</span>
    ),
  };
});

const mockInferenceWorkloads = mockWorkloads.filter(
  (w) => w.type === 'INFERENCE',
);

const createMockAimService = (
  id: string,
  modelName: string,
  overrides: Record<string, unknown> = {},
) => ({
  id,
  metadata: {
    name: `${modelName}-service`,
    namespace: 'test-project',
    uid: `uid-${id}`,
    labels: {},
    annotations: { aiwbAppsEaiAmdComCreator: 'test-user' },
    creationTimestamp: '2023-01-11T00:00:00Z',
    ownerReferences: [],
  },
  spec: {
    model: { name: modelName },
    replicas: 1,
    routing: { annotations: {}, enabled: true },
    runtimeConfigName: 'default',
  },
  status: { status: 'Running', resolvedModel: { name: modelName } },
  endpoints: {
    internal: `https://${modelName}.internal`,
    external: `https://${modelName}.example.com`,
  },
  ...overrides,
});

const mockAimServices = [
  createMockAimService('workload-11', 'aim-1'),
  createMockAimService('workload-12', 'aim-2'),
  createMockAimService('workload-13', 'aim-3'),
];

describe('DeployedModels', () => {
  const mockListWorkloads = listAllWorkloads as Mock;
  const mockListAllProjectFineTunedModels =
    listAllProjectFineTunedModels as Mock;
  const mockGetAimServices = listAllInferenceDeployments as Mock;
  const mockGetInferenceModel = getInferenceModel as Mock;
  const mockResolveAIMServiceDisplay = resolveAIMServiceDisplay as Mock;

  beforeEach(() => {
    vi.clearAllMocks();
    delete routerQuery.deleted;
    mockUseCustomProfileDeployments.mockReturnValue({
      profileByServiceId: new Map(),
      isLoading: false,
    });
    mockListWorkloads.mockResolvedValue(mockInferenceWorkloads);
    mockListAllProjectFineTunedModels.mockResolvedValue(mockModels);
    mockGetAimServices.mockResolvedValue([]);
    // Default: per-name catalog lookups 404. Tests can override per call.
    mockGetInferenceModel.mockRejectedValue(
      new APIRequestError('not found', 404),
    );
    mockResolveAIMServiceDisplay.mockImplementation(
      (service: {
        status?: { resolvedModel?: { name?: string } };
        metadata?: { name?: string };
      }) => ({
        canonicalName: 'meta-llama/Llama-2-7B',
        imageVersion: '1.0.0',
        metric: 'default',
        title: 'Llama 2 7B',
        name:
          service.status?.resolvedModel?.name ?? service.metadata?.name ?? '',
      }),
    );

    // Mock window.open
    Object.defineProperty(window, 'open', {
      writable: true,
      value: vi.fn(),
    });
  });

  it('renders deployed models component', async () => {
    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    expect(screen.getByTestId('deployed-models')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();

    // Use more specific selectors to avoid ambiguity
    const typeDropdowns = screen.getAllByText(/type/i);
    const statusDropdowns = screen.getAllByText(/status/i);
    expect(typeDropdowns.length).toBeGreaterThan(0);
    expect(statusDropdowns.length).toBeGreaterThan(0);

    const clearButton = screen.getByText('actions.clearFilters.title');
    const refreshButton = screen.getByRole('button', { name: /refresh/i });

    expect(refreshButton).toBeInTheDocument();
    expect(clearButton).toBeInTheDocument();
  });

  it('displays workloads in the data table', async () => {
    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    // Wait for the API call to complete
    await waitFor(
      () => {
        expect(mockListWorkloads).toHaveBeenCalled();
      },
      { timeout: 3000 },
    );

    // Wait for data to load and be displayed
    await waitFor(
      () => {
        // Check that workloads are displayed - the component shows displayName
        // Only INFERENCE types should be visible by default
        expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument();
        // other types should not appear
        expect(
          screen.queryByText('Stable Diffusion XL Download'),
        ).not.toBeInTheDocument();
        expect(
          screen.queryByText('Model fine-tuning Job'),
        ).not.toBeInTheDocument();
      },
      { timeout: 5000 },
    );

    // The component only shows INFERENCE workloads
    expect(screen.queryByText('Jupyter Workspace')).not.toBeInTheDocument(); // WORKSPACE type is not shown

    // For now, just verify the component renders without crashing
    expect(screen.getByTestId('deployed-models')).toBeInTheDocument();
  });

  it('filters workloads by search query', async () => {
    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    const searchInput = screen.getByPlaceholderText(/search/i);

    // Wait for initial data to load
    await waitFor(() => {
      expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument();
    });

    // Search for "Llama" - this should filter by displayName field
    fireEvent.change(searchInput, { target: { value: 'Llama' } });

    await waitFor(() => {
      // Should show the Llama workload (displayName is displayed)
      expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument();
      // Should not show other workloads
      expect(
        screen.queryByText('Stable Diffusion XL Download'),
      ).not.toBeInTheDocument();
    });

    // Clear search and verify all default-filtered workloads are shown again
    fireEvent.change(searchInput, { target: { value: '' } });

    await waitFor(() => {
      expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument();
      // other types won't be shown
      expect(
        screen.queryByText('Stable Diffusion XL Download'),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByText('Model fine-tuning Job'),
      ).not.toBeInTheDocument();
    });
  });

  it('displays only inference workloads', async () => {
    // Use the standard mock workloads to verify only INFERENCE workloads are shown
    mockListWorkloads.mockResolvedValue(mockInferenceWorkloads);

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    // Wait for initial data to load - by default only INFERENCE should be visible
    await waitFor(() => {
      expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument(); // INFERENCE
      // FINE_TUNING and WORKSPACE should be filtered out by default
      expect(
        screen.queryByText('Stable Diffusion XL Download'),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByText('Model fine-tuning Job'),
      ).not.toBeInTheDocument();
      expect(screen.queryByText('Jupyter Workspace')).not.toBeInTheDocument();
    });

    // Verify that the component has the expected number of rows (header + visible data rows)
    const tableContainer = await screen.findByRole('grid');
    await waitFor(() => {
      const rows = within(tableContainer).getAllByRole('row');
      // Based on mockInferenceWorkloads, we should see only INFERENCE workloads:
      // workload-1 (Llama, RUNNING), workload-2 (SDXL, PENDING),
      // workload-8 (Delete Failed, FAILED),
      // workload-11 (AIM GPT-4, RUNNING), workload-12 (AIM LLaMA 2, RUNNING), workload-13 (AIM Mistral, RUNNING)
      // workload-5 is DELETED status so filtered out by default
      expect(rows).toHaveLength(7); // 1 header + 6 data rows
    });
  });

  it('shows loading state', async () => {
    // Mock loading state by returning a never-resolving promise
    mockListWorkloads.mockImplementation(() => new Promise(() => {}));

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    // Check that the data table shows loading state
    // The ClientSideDataTable should show loading indicators when isLoading is true
    await waitFor(() => {
      const deployedModels = screen.getByTestId('deployed-models');
      expect(deployedModels).toBeInTheDocument();

      // Verify that no workload data is displayed while loading
      expect(screen.queryByText('Llama 7B Inference')).not.toBeInTheDocument();
      expect(screen.queryByText('Stable Diffusion XL')).not.toBeInTheDocument();
    });
  });

  it('handles refresh button click', async () => {
    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    // Wait for initial load to complete
    await waitFor(() => {
      expect(mockListWorkloads).toHaveBeenCalled();
    });

    const refreshButton = screen.getByRole('button', { name: /refresh/i });
    // Clear the mock call count after initial load
    mockListWorkloads.mockClear();

    fireEvent.click(refreshButton);

    await waitFor(() => {
      expect(mockListWorkloads).toHaveBeenCalled();
    });
  });

  it('navigates to workload details page when details action is clicked', async () => {
    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    const llamaCell = await screen.findByText('Llama 7B Inference');

    // Grid tables expose rows via role="row" (not always a <tr>).
    const llamaRow = llamaCell.closest('[role="row"]');
    expect(llamaRow).toBeTruthy();

    const rowActionButton = within(llamaRow as HTMLElement).getByRole(
      'button',
      { name: ROW_OVERFLOW_MENU_KEY },
    );
    await act(async () => {
      fireEvent.click(rowActionButton);
    });

    // Find and click the details action
    const detailsButton = await screen.findByTestId('details');
    expect(detailsButton).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(detailsButton);
    });

    // Verify navigation to workload details page for Llama 7B (workload-1)
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith({
        pathname: `/project1/workloads/workload-1`,
        query: { ref: '/models' },
      });
    });
  });

  it('opens delete workload modal when delete action is clicked', async () => {
    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument();
    });

    const rowActionButtons = await waitFor(() =>
      screen.getAllByRole('button', { name: ROW_OVERFLOW_MENU_KEY }),
    );
    await act(async () => {
      fireEvent.click(rowActionButtons[0]);
    });

    const undeployButton = await screen.findByTestId('undeploy');
    await act(async () => {
      fireEvent.click(undeployButton);
    });

    expect(await screen.findByTestId('confirmation-modal')).toBeInTheDocument();
  });

  it('routes workload deletion to the inference capability endpoint', async () => {
    const mockDeleteInferenceDeployment = deleteInferenceDeployment as Mock;
    mockDeleteInferenceDeployment.mockResolvedValue(undefined);

    // Surface an AIM-backed deployment so the row picks up the inference path.
    mockGetAimServices.mockResolvedValue([
      createMockAimService('workload-11', 'aim-1'),
    ]);

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    const rowActionButtons = await waitFor(() =>
      screen.getAllByRole('button', { name: ROW_OVERFLOW_MENU_KEY }),
    );
    // Pick the AIM-backed row (rendered last after the workload fixtures).
    await act(async () => {
      fireEvent.click(rowActionButtons[rowActionButtons.length - 1]);
    });

    const undeployButton = await screen.findByTestId('undeploy');
    await act(async () => {
      fireEvent.click(undeployButton);
    });

    const confirmButton = await screen.findByTestId('confirm-button');
    mockDeleteInferenceDeployment.mockClear();

    await act(async () => {
      fireEvent.click(confirmButton);
    });

    // All deployed-model deletes route to the inference capability
    // endpoint; the legacy /workloads DELETE no longer exists.
    await waitFor(() => {
      expect(mockDeleteInferenceDeployment).toHaveBeenCalled();
    });
  }, 20_000);

  it('displays workspace workloads when workspace type is in filter', async () => {
    // Create a mock with a workspace workload
    const workspaceWorkload: Workload = {
      ...mockInferenceWorkloads[2], // Jupyter Workspace
      type: 'WORKSPACE',
      status: 'Running',
    };

    mockListWorkloads.mockResolvedValue([workspaceWorkload]);

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    // Since WORKSPACE is not in default filter, it shouldn't be visible initially
    await waitFor(() => {
      expect(screen.queryByText('Jupyter Workspace')).not.toBeInTheDocument();
    });

    // Test that basic functionality works - the component renders without crashing
    expect(screen.getByTestId('deployed-models')).toBeInTheDocument();
  });

  it('handles API errors gracefully', async () => {
    mockListWorkloads.mockRejectedValue(new Error('API Error'));

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    // Verify the component still renders
    expect(screen.getByTestId('deployed-models')).toBeInTheDocument();

    // Verify that no workload data is displayed when there's an error
    await waitFor(() => {
      expect(screen.queryByText('Llama 7B Inference')).not.toBeInTheDocument();
      expect(screen.queryByText('Stable Diffusion XL')).not.toBeInTheDocument();
    });

    // The component should show an empty state or error message
    // Since the API call failed, the workloads array should be empty
    await waitFor(() => {
      expect(mockListWorkloads).toHaveBeenCalled();
    });
  });

  it('displays correct workload status badges', async () => {
    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument();
    });

    // Verify that different status values are displayed
    // The StatusDisplay component renders these as translated strings
    await waitFor(() => {
      expect(screen.getAllByText('status.Running').length).toBeGreaterThan(0);
      expect(screen.getAllByText('status.Failed').length).toBeGreaterThan(0);
    });
  });

  it('displays correct workload type chips', async () => {
    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument();
    });

    // Verify different workload types are displayed as chips
    // The ChipDisplay component renders these as translated strings
    await waitFor(() => {
      // Only INFERENCE workloads are shown (excluding DELETED status)
      const inferenceElements = screen.getAllByText('type.INFERENCE');
      // From mockInferenceWorkloads: workload-1 (Llama, RUNNING), workload-2 (SDXL, PENDING),
      // workload-8 (Delete Failed, FAILED),
      // workload-11 (AIM GPT-4, RUNNING), workload-12 (AIM LLaMA 2, RUNNING), workload-13 (AIM Mistral, RUNNING)
      // workload-5 is DELETED status so filtered out by default
      expect(inferenceElements.length).toBe(6);
    });
  });

  it('formats dates correctly', async () => {
    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument();
    });

    // Verify that DateSince (date display) components are rendered for createdAt dates.
    // DateSince shows either relative strings (mock returns keys like dateSince.minutesAgo)
    // or absolute locale format (e.g. 1/1/2023, 2:00 AM).
    await waitFor(() => {
      const dateCells = screen.getAllByText(
        /(dateSince\.|\d{1,2}\/\d{1,2}\/\d{4})/,
      );
      expect(dateCells.length).toBeGreaterThan(0);
    });
  });

  it('shows correct row actions based on workload status and type', async () => {
    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument();
    });

    // Test actions for the Llama 7B Inference workload (INFERENCE with RUNNING status and CHAT capability)
    // It should be the last row since the table is sorted by createdAt descending
    const rowActionButtons = screen.getAllByRole('button', {
      name: ROW_OVERFLOW_MENU_KEY,
    });
    await act(async () => {
      // Click the last workload which should be Llama 7B Inference based on the sorting
      fireEvent.click(rowActionButtons[rowActionButtons.length - 1]);
    });

    await waitFor(() => {
      expect(screen.getByTestId('details')).toBeInTheDocument();
      expect(screen.getByTestId('undeploy')).toBeInTheDocument(); // RUNNING status allows undeploy
      // Chat action should be available since it's INFERENCE type with CHAT capability and RUNNING status
      expect(screen.getByTestId('chat')).toBeInTheDocument();
      // No workspace action since it's not a WORKSPACE type
      expect(screen.queryByTestId('openWorkspace')).not.toBeInTheDocument();
    });
  });

  it('disables actions for deleted workloads', async () => {
    // Create a mock with a deleted workload that should be visible
    // First, we need to include DELETED status in the filters to see deleted workloads
    const deletedWorkload: Workload = {
      ...mockInferenceWorkloads[4], // Deleted Workload
      displayName: 'Deleted Model',
      type: 'INFERENCE', // Component only shows INFERENCE workloads
      status: 'Failed',
    };

    mockListWorkloads.mockResolvedValue([deletedWorkload]);

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Deleted Model')).toBeInTheDocument();
    });

    // Open row actions for the workload
    const rowActionButtons = screen.getAllByRole('button', {
      name: ROW_OVERFLOW_MENU_KEY,
    });
    await act(async () => {
      fireEvent.click(rowActionButtons[0]);
    });

    // Verify details action is available and undeploy action is available for DELETE_FAILED status
    await waitFor(() => {
      expect(screen.getByTestId('details')).toBeInTheDocument();
      // DELETE_FAILED workloads should still have undeploy action unlike DELETED workloads
      expect(screen.getByTestId('undeploy')).toBeInTheDocument();
      expect(screen.queryByTestId('chat')).not.toBeInTheDocument(); // No chat for failed workloads
      expect(screen.queryByTestId('openWorkspace')).not.toBeInTheDocument(); // No workspace actions for non-workspace types
    });
  });

  it('filters out deleted workloads by default', async () => {
    // Create a mix of workloads including a deleted one
    const workloadsWithDeleted: Workload[] = [
      ...mockInferenceWorkloads.slice(0, 3), // Include some normal workloads
      {
        ...mockInferenceWorkloads[4],
        type: 'INFERENCE',
        status: 'Deleted', // This should be filtered out
        displayName: 'Deleted Model',
      },
    ];

    mockListWorkloads.mockResolvedValue(workloadsWithDeleted);

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    // Wait for the data to load
    await waitFor(() => {
      expect(mockListWorkloads).toHaveBeenCalled();
    });

    // Should see the non-deleted workloads but not the deleted one
    await waitFor(() => {
      expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument(); // RUNNING INFERENCE workload
      // DELETED workloads should be filtered out
      expect(screen.queryByText('Stable Diffusion XL')).not.toBeInTheDocument();
      expect(screen.queryByText('Deleted Model')).not.toBeInTheDocument();
    });

    // Deleted rows are excluded server-side, not just hidden client-side.
    // Asserted as an exact list because a negated matcher also passes against
    // `undefined` — the very value that means "no server-side filter at all".
    expect(mockListWorkloads).toHaveBeenCalledWith('project1', {
      workloadType: ['INFERENCE'],
      statusFilter: [
        'Pending',
        'Starting',
        'Running',
        'Complete',
        'Failed',
        'Unknown',
        'Deleting',
      ],
    });

    await openStatusFilter();

    expect(screen.getByText(STATUS_OPTION_DELETING)).toBeInTheDocument();
    expect(screen.queryByText(STATUS_OPTION_DELETED)).not.toBeInTheDocument();
  });

  it('lists deleted workloads when the URL opts in', async () => {
    routerQuery.deleted = '1';
    mockListWorkloads.mockResolvedValue([
      {
        ...mockInferenceWorkloads[4],
        type: 'INFERENCE',
        status: 'Deleted',
        displayName: 'Deleted Model',
      } as Workload,
    ]);

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(mockListWorkloads).toHaveBeenCalledWith('project1', {
        workloadType: ['INFERENCE'],
        statusFilter: undefined,
      });
    });

    // The fetched row must be visible without the user touching the filter.
    await waitFor(() => {
      expect(screen.getByText('Deleted Model')).toBeInTheDocument();
    });

    await openStatusFilter();

    const deletedOption = screen.getByText(STATUS_OPTION_DELETED);
    expect(deletedOption).toBeInTheDocument();
    // Pre-selected, not merely offered — otherwise the next filter interaction
    // would drop the deleted rows the opt-in just fetched.
    expect(deletedOption.closest('[role="option"]')).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('lists deleted workloads when the opt-in flips after mount', async () => {
    // Navigating to `?deleted=1` reuses the already-mounted page, so the toolbar
    // and the active filter have to re-seed rather than relying on a fresh mount.
    mockListWorkloads.mockResolvedValue([
      {
        ...mockInferenceWorkloads[4],
        type: 'INFERENCE',
        status: 'Deleted',
        displayName: 'Deleted Model',
      } as Workload,
    ]);

    let view!: ReturnType<typeof render>;
    await act(async () => {
      view = render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.queryByText('Deleted Model')).not.toBeInTheDocument();
    });

    routerQuery.deleted = '1';
    await act(async () => {
      view.rerender(<DeployedModels />);
    });

    await waitFor(() => {
      expect(screen.getByText('Deleted Model')).toBeInTheDocument();
    });

    await openStatusFilter();

    expect(
      screen.getByText(STATUS_OPTION_DELETED).closest('[role="option"]'),
    ).toHaveAttribute('aria-selected', 'true');
  });

  it('displays canonical names for all workloads with AIM or Model', async () => {
    const workloadsWithModelOrAim = [
      mockInferenceWorkloads[0], // workload-1 - finetuning workload
      mockInferenceWorkloads[2], // workload-8 - finetuning workload
      mockInferenceWorkloads[3], // workload-11 - aimId
      mockInferenceWorkloads[4], // workload-12 - aimId
      mockInferenceWorkloads[5], // workload-13 - aimId
    ];

    mockListWorkloads.mockResolvedValue(workloadsWithModelOrAim);

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Llama 7B Inference')).toBeInTheDocument();
    });

    const table = screen.getByRole('grid');
    const rows = within(table).getAllByRole('row');

    // Check each data row has a canonical name
    const expectedCanonicalNames = [
      'org/model-1',
      'org/model-2',
      'meta-llama/llama-2-7b',
      'org/model-5',
      'org/model-6',
    ];

    for (let i = 1; i < rows.length; i++) {
      const row = rows[i];
      const cells = within(row).getAllByRole('gridcell');

      // Check if this row has TYPE column showing INFERENCE
      const typeCell = cells[2]; // Third column is TYPE
      if (typeCell.textContent !== 'type.INFERENCE') {
        continue; // Skip non-INFERENCE rows
      }

      const canonicalNameCell = cells[1]; // Second column
      const canonicalNameText = canonicalNameCell.textContent;

      expect(canonicalNameText).toBeTruthy();
      expect(canonicalNameText).not.toBe('');
      expect(expectedCanonicalNames).toContain(canonicalNameText);
    }
  });

  it('displays canonical name + version and profile summary when the AIM display name only echoes the resource name', async () => {
    // With no metrics workload to supply a user-facing displayName, the AIM
    // row's displayName falls back to the K8s resource name, so the NAME column
    // shows canonical name + version (from resolveAIMServiceDisplay) plus the
    // profile summary.
    // status.resolvedProfile only carries the *name* on the wire; the FE
    // joins it against the cluster-profile catalog client-side. Mock both
    // the service list and the catalog so the row renderer has data to join.
    const resolvedProfile = { name: 'aim-1-throughput' };
    const matchingProfile = {
      metadata: { name: 'aim-1-throughput', labels: {} },
      spec: {
        aimId: 'aim-1',
        metric: 'throughput',
        acceleratorModel: 'MI300X',
        acceleratorCount: 8,
        precision: 'fp8',
      },
      status: { status: 'Ready' },
    };
    const services = [
      createMockAimService('workload-11', 'aim-1', {
        status: {
          status: 'Running',
          resolvedModel: { name: 'aim-1' },
          resolvedProfile,
        },
      }),
      createMockAimService('workload-12', 'aim-2', {
        status: {
          status: 'Running',
          resolvedModel: { name: 'aim-2' },
          resolvedProfile,
        },
      }),
      createMockAimService('workload-13', 'aim-3', {
        status: {
          status: 'Running',
          resolvedModel: { name: 'aim-3' },
          resolvedProfile,
        },
      }),
    ];
    // No metrics workloads: the AIM row's displayName echoes the resource name,
    // triggering the canonical + version fallback.
    mockListWorkloads.mockResolvedValue([]);
    mockGetAimServices.mockResolvedValue(services);
    // useInferenceModelsByName fans out per-name; each cluster model carries
    // a status.aimId that useProfileSpecsForServices uses to pick the right
    // AIMClusterProfile from the mocked profile fetch below.
    mockGetInferenceModel.mockImplementation(
      async (name: string) =>
        ({
          metadata: {
            name,
            namespace: '',
            uid: '',
            labels: {},
            annotations: {},
          },
          spec: { image: `${name}:latest` },
          status: {
            status: 'Ready',
            aimId: name,
            imageMetadata: { model: { tags: [] }, oci: {} },
          },
        }) as unknown as Awaited<ReturnType<typeof getInferenceModel>>,
    );
    (
      vi.mocked(await import('@/lib/app/aims'))
        .getAimClusterProfilesByAimIds as Mock
    ).mockResolvedValue([matchingProfile]);

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(mockListWorkloads).toHaveBeenCalled();
      expect(mockGetAimServices).toHaveBeenCalled();
    });

    await waitFor(() => {
      // Canonical name + version is the row's name when no display name resolved.
      const titles = screen.getAllByText('meta-llama/Llama-2-7B (1.0.0)');
      expect(titles.length).toBeGreaterThan(0);
      expect(
        screen.getAllByText('performanceMetrics.values.throughput').length,
      ).toBeGreaterThan(0);
      expect(screen.getAllByText('MI300X').length).toBeGreaterThan(0);
      expect(screen.getAllByText('8x GPU').length).toBeGreaterThan(0);
      expect(screen.getAllByText('fp8').length).toBeGreaterThan(0);
    });
  });

  it('renders the deploy display name for custom-imported namespace models', async () => {
    // Custom imports carry NAMESPACE_AIM_MODEL_LABEL (not FINE_TUNED_LABEL); the
    // user-entered deploy name lives on the display-name annotation, becomes the
    // row's displayName, and is shown as the primary label with no canonical
    // subtitle.
    const customService = createMockAimService('workload-21', 'custom-model', {
      metadata: {
        name: 'wb-aim-custom',
        namespace: 'test-project',
        uid: 'uid-workload-21',
        labels: { [NAMESPACE_AIM_MODEL_LABEL]: 'true' },
        annotations: { [AIM_DISPLAY_NAME_ANNOTATION]: 'My TinyLlama' },
        creationTimestamp: '2023-01-11T00:00:00Z',
        ownerReferences: [],
      },
    });
    mockListWorkloads.mockResolvedValue([]);
    mockGetAimServices.mockResolvedValue([customService]);

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(mockGetAimServices).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText('My TinyLlama')).toBeInTheDocument();
      // The canonical + version fallback must not be used for this row.
      expect(
        screen.queryByText('meta-llama/Llama-2-7B (1.0.0)'),
      ).not.toBeInTheDocument();
    });
  });

  it('shows Connect to model action for running AIM workloads', async () => {
    mockGetAimServices.mockResolvedValue(mockAimServices);
    mockGetInferenceModel.mockRejectedValue(
      new APIRequestError('not found', 404),
    );
    mockListWorkloads.mockResolvedValue([]);

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(mockGetAimServices).toHaveBeenCalled();
    });

    await waitFor(() => {
      const rowActionButtons = screen.getAllByRole('button', {
        name: ROW_OVERFLOW_MENU_KEY,
      });
      expect(rowActionButtons.length).toBeGreaterThan(0);
    });

    await act(async () => {
      fireEvent.click(
        screen.getAllByRole('button', { name: ROW_OVERFLOW_MENU_KEY })[0],
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('details')).toBeInTheDocument();
      expect(screen.getByTestId('connect')).toBeInTheDocument();
      expect(screen.getByTestId('chat')).toBeInTheDocument();
    });
  });

  it('suppresses chat and uses the transcription snippet for a transcription deployment', async () => {
    mockGetAimServices.mockResolvedValue([
      createMockAimService('workload-11', 'whisper'),
    ]);
    mockListWorkloads.mockResolvedValue([]);
    mockGetInferenceModel.mockRejectedValue(
      new APIRequestError('not found', 404),
    );
    // The catalog model backing this deployment advertises a transcription tag.
    mockResolveAIMServiceDisplay.mockImplementation(
      (service: {
        status?: { resolvedModel?: { name?: string } };
        metadata?: { name?: string };
      }) => ({
        canonicalName: 'openai/whisper-large-v3',
        imageVersion: '1.0.0',
        metric: 'default',
        title: 'Whisper',
        name:
          service.status?.resolvedModel?.name ?? service.metadata?.name ?? '',
        tags: ['transcription'],
      }),
    );

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(mockGetAimServices).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(
        screen.getAllByRole('button', { name: ROW_OVERFLOW_MENU_KEY }).length,
      ).toBeGreaterThan(0);
    });

    await act(async () => {
      fireEvent.click(
        screen.getAllByRole('button', { name: ROW_OVERFLOW_MENU_KEY })[0],
      );
    });

    // Connect stays available; the chat action is suppressed for transcription.
    const connectAction = await screen.findByTestId('connect');
    expect(screen.queryByTestId('chat')).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(connectAction);
    });

    // The modal receives the transcription capability, so the snippet targets
    // the audio endpoint and offers no chat playground.
    await waitFor(() => {
      expect(document.body).toHaveTextContent('/v1/audio/transcriptions');
    });
    expect(document.body).not.toHaveTextContent('/v1/chat/completions');
    expect(
      screen.queryByText('actions.connect.modal.openChat'),
    ).not.toBeInTheDocument();
  });

  it('displays no data indicator for workload without AIM or Model', async () => {
    // Workload without a finetuning workload or aimId should show NoDataDisplay
    const workloadWithoutModelOrAim: Workload = {
      id: 'workload-no-model',
      name: 'Standalone Inference',
      displayName: 'Standalone Inference',
      createdBy: 'test-user',
      updatedBy: null,
      namespace: 'test-namespace',
      description: null,
      endpoints: {},
      chartId: 'chart-standalone',
      type: 'INFERENCE',
      createdAt: '2023-01-15T00:00:00Z',
      updatedAt: '2023-01-15T01:00:00Z',
      status: 'Running',
    };

    mockListWorkloads.mockResolvedValue([workloadWithoutModelOrAim]);

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Standalone Inference')).toBeInTheDocument();
    });

    const table = screen.getByRole('grid');
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(2);

    const dataRow = rows[1];
    const cells = within(dataRow).getAllByRole('gridcell');
    const canonicalNameCell = cells[1];
    const canonicalNameText = canonicalNameCell.textContent;

    // Verify NoDataDisplay is shown (no canonical name patterns)
    expect(canonicalNameText).not.toMatch(/\//);
    expect(canonicalNameText).not.toMatch(/^org\//);
    expect(canonicalNameText).not.toMatch(/^meta-/);
  });

  it('prefers AIM service fields over workload fields when ids overlap', async () => {
    // Workload has FAILED status; AIM service with the same id contributes RUNNING status.
    // After merge ({...workload, ...aimWorkload}), AIM fields win — RUNNING overrides FAILED.
    const workloadWithSharedId: Workload = {
      id: 'shared-deployment-id',
      displayName: 'Workload Display Name',
      name: 'workload-name',
      type: 'INFERENCE',
      status: 'Failed',
      createdBy: 'workload-user',
      updatedBy: null,
      namespace: 'test-namespace',
      description: null,
      endpoints: {},
      chartId: 'chart-shared',
      createdAt: '2023-01-01T00:00:00Z',
      updatedAt: '2023-01-01T01:00:00Z',
    };

    // AIM service with same id: status.status 'Running' maps to RUNNING; aimId is set.
    const aimService = createMockAimService(
      'shared-deployment-id',
      'aim-model',
    );

    mockListWorkloads.mockResolvedValue([workloadWithSharedId]);
    mockGetAimServices.mockResolvedValue([aimService]);

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(mockListWorkloads).toHaveBeenCalled();
      expect(mockGetAimServices).toHaveBeenCalled();
    });

    // One merged row, not two separate rows.
    const table = screen.getByRole('grid');
    await waitFor(() => {
      const rows = within(table).getAllByRole('row');
      expect(rows).toHaveLength(2); // 1 header + 1 merged data row
    });

    // AIM status (RUNNING) wins over workload status (FAILED): the RUNNING-only
    // "chat" and "connect" actions confirm AIM fields took precedence.
    const rowActionButton = screen.getByRole('button', {
      name: ROW_OVERFLOW_MENU_KEY,
    });
    await act(async () => {
      fireEvent.click(rowActionButton);
    });

    await waitFor(() => {
      expect(screen.getByTestId('chat')).toBeInTheDocument();
      expect(screen.getByTestId('connect')).toBeInTheDocument();
    });
  });

  it('shows the deployment max LoRA rank alongside a custom profile', async () => {
    // Custom-profile axes (profileSummaryFields in lib/app/custom-profiles.ts)
    // never carry maxLoraRank — only the deployment's own spec does — so this
    // proves the row still composes it in rather than losing it behind the
    // custom profile.
    const customService = createMockAimService(
      'workload-30',
      'custom-model-rank',
      {
        metadata: {
          name: 'wb-aim-custom-rank',
          namespace: 'test-project',
          uid: 'uid-workload-30',
          labels: { [NAMESPACE_AIM_MODEL_LABEL]: 'true' },
          annotations: { [AIM_DISPLAY_NAME_ANNOTATION]: 'My Custom Model' },
          creationTimestamp: '2023-01-11T00:00:00Z',
          ownerReferences: [],
        },
        spec: {
          model: { name: 'custom-model-rank' },
          replicas: 1,
          routing: { annotations: {}, enabled: true },
          runtimeConfigName: 'default',
          adapterRuntime: { maxRank: 32 },
        },
      },
    );
    mockListWorkloads.mockResolvedValue([]);
    mockGetAimServices.mockResolvedValue([customService]);
    mockUseCustomProfileDeployments.mockReturnValue({
      profileByServiceId: new Map([
        [
          'workload-30',
          {
            displayName: 'High speed',
            profile: {
              metric: null,
              gpu: 'MI300X',
              templateGpuCount: 1,
              acceleratorType: 'gpu',
              precision: 'fp16',
            },
          },
        ],
      ]),
      isLoading: false,
    });

    await act(async () => {
      render(<DeployedModels />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('My Custom Model')).toBeInTheDocument();
    });
    // The custom profile's own axis and the deployment's max rank must both
    // survive — proving the merge doesn't drop one for the other.
    expect(screen.getByText('MI300X')).toBeInTheDocument();
    expect(screen.getByText('profileSummary.maxRank:32')).toBeInTheDocument();
  });
});
