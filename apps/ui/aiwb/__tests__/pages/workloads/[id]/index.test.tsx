// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import { useRouter } from 'next/router';

import { useProject } from '@/contexts/ProjectContext';
import { cancelFineTuningJob } from '@/lib/app/models';
import { getProjectFineTunedModel } from '@/lib/app/aims';
import {
  deleteWorkspace,
  getWorkload,
  getWorkloadMetrics,
} from '@/lib/app/workloads';
import { deleteInferenceDeployment } from '@/lib/app/inference';
import { getDataset } from '@/lib/app/datasets';
import { getChart } from '@/lib/app/charts';

import type { Workload } from '@/types/workloads';

import WorkloadDetailsPage from '@/pages/[project]/workloads/[id]/index';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import wrapper from '@/__tests__/ProviderWrapper';
import '@testing-library/jest-dom';
import { Mock, vi } from 'vitest';

// Mock the router
vi.mock('next/router', () => ({
  useRouter: vi.fn(),
}));

// Mock useProject
vi.mock('@/contexts/ProjectContext', async (importOriginal) => ({
  ...(await importOriginal()),
  useProject: vi.fn(),
}));

// Mock the internal services
vi.mock('@/lib/app/workloads', async (importOriginal) => ({
  ...(await importOriginal()),
  getWorkload: vi.fn(),
  deleteWorkspace: vi.fn(),
  getWorkloadMetrics: vi.fn(),
}));

vi.mock('@/lib/app/inference', async (importOriginal) => ({
  ...(await importOriginal()),
  deleteInferenceDeployment: vi.fn(),
}));

vi.mock('@/components/features/models/AIMConnectModal', () => ({
  __esModule: true,
  default: vi.fn(() => <div data-testid="aim-connect-modal" />),
}));

vi.mock('@/components/features/workloads/DeleteWorkloadModal', () => ({
  default: ({
    isOpen,
    workload,
    onConfirmAction,
  }: {
    isOpen: boolean;
    workload: any;
    onConfirmAction: (id: string) => void;
    onOpenChange: (open: boolean) => void;
  }) =>
    isOpen && workload ? (
      <button
        data-testid="confirm-delete"
        onClick={() => onConfirmAction(workload.id)}
      >
        Confirm Delete
      </button>
    ) : null,
}));

vi.mock('@/lib/app/charts', async (importOriginal) => ({
  ...(await importOriginal()),
  getChart: vi.fn(),
}));

vi.mock('@/lib/app/datasets', async (importOriginal) => ({
  ...(await importOriginal()),
  getDataset: vi.fn(),
}));

// Mock the workload services
vi.mock('@/lib/app/models', async (importOriginal) => ({
  ...(await importOriginal()),
  cancelFineTuningJob: vi.fn(),
}));

vi.mock('@/lib/app/aims', async (importOriginal) => ({
  ...(await importOriginal()),
  getProjectFineTunedModel: vi.fn(),
}));

// Mock useSystemToast
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

// Mock translations
vi.mock('next-i18next', () => ({
  Trans: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTranslation: () => ({
    t: (key: string, options?: any) => {
      // Handle interpolation
      if (options && typeof options === 'object') {
        let result = key;
        Object.keys(options).forEach((optionKey) => {
          result = result.replace(`{{${optionKey}}}`, options[optionKey]);
        });
        return result;
      }
      return key;
    },
    i18n: { language: 'en' },
  }),
}));

// Mock clipboard API
Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn().mockResolvedValue(undefined),
  },
});

// Mock window.open
Object.assign(window, {
  open: vi.fn(),
});

describe('WorkloadDetailsPage', () => {
  const mockPush = vi.fn();
  const mockBack = vi.fn();

  const mockWorkload: Workload = {
    id: 'workload-1',
    name: 'Llama 7B Inference',
    displayName: 'Llama 7B Inference',
    description: null,
    createdBy: 'test-user',
    updatedBy: 'test-user',
    namespace: 'test-project',
    chartId: 'chart-1',
    datasetId: null,
    type: 'INFERENCE',
    status: 'Running',
    createdAt: '2023-01-01T00:00:00Z',
    updatedAt: '2023-01-01T01:00:00Z',
    endpoints: {
      external: 'https://example.com/external',
      internal: 'http://workload-1.default.svc.cluster.local',
    },
  };

  const mockWorkspaceWorkload: Workload = {
    ...mockWorkload,
    id: 'workspace-1',
    type: 'WORKSPACE',
    status: 'Running',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(navigator.clipboard.writeText).mockResolvedValue(undefined);
    (useRouter as Mock).mockReturnValue({
      query: { id: 'workload-1', project: 'test-project' },
      push: mockPush,
      back: mockBack,
    });
    (useProject as Mock).mockReturnValue({
      activeProject: 'test-project',
      projectPath: (path: string) =>
        `/test-project${path.startsWith('/') ? path : `/${path}`}`,
      projectUrl: (path: string) =>
        `/test-project${path.startsWith('/') ? path : `/${path}`}`,
    });
    (getWorkload as Mock).mockResolvedValue(mockWorkload);
    (getWorkloadMetrics as Mock).mockResolvedValue({ data: [] });
    (deleteWorkspace as Mock).mockResolvedValue({});
    (deleteInferenceDeployment as Mock).mockResolvedValue(undefined);
    (cancelFineTuningJob as Mock).mockResolvedValue(undefined);
    (getProjectFineTunedModel as Mock).mockResolvedValue({
      id: 'model-1',
      displayName: null,
      workloadId: null,
      metadata: {
        name: 'Test Model',
        creationTimestamp: '2026-01-01T00:00:00Z',
      },
      spec: {
        image: 'amdenterpriseai/aim-base:0.10',
        modelSources: [
          { modelId: 'org/test-model', sourceUri: 's3://bucket/model' },
        ],
      },
      status: { status: 'Ready' },
    });
    (getDataset as Mock).mockResolvedValue({
      id: 'dataset-1',
      name: 'Test Dataset',
      description: 'Test dataset description',
    });
    (getChart as Mock).mockResolvedValue({
      id: 'chart-1',
      name: 'Test Chart',
      description: 'Test chart description',
    });
  });

  describe('Rendering', () => {
    it('renders workload details correctly', async () => {
      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      // Check header elements
      await waitFor(() => {
        expect(
          screen.getAllByText('Llama 7B Inference')[0],
        ).toBeInTheDocument();
        expect(
          screen.getByText('details.sections.basicInformation'),
        ).toBeInTheDocument();
        expect(
          screen.getByText('details.sections.resources'),
        ).toBeInTheDocument();
        expect(
          screen.getByText('details.sections.timeline'),
        ).toBeInTheDocument();
      });
    });

    it('renders all workload information sections', async () => {
      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        // Basic Information
        expect(
          screen.getByText('details.sections.basicInformation'),
        ).toBeInTheDocument();
        expect(
          screen.getAllByText('Llama 7B Inference')[0],
        ).toBeInTheDocument();
        expect(screen.getByText('workload-1')).toBeInTheDocument();
      });

      // Resources
      expect(
        screen.getByText('details.sections.resources'),
      ).toBeInTheDocument();

      // Timeline
      expect(screen.getByText('details.sections.timeline')).toBeInTheDocument();
      expect(screen.getByText('test-user')).toBeInTheDocument();

      // Chart section should display chart info
      await waitFor(() => {
        expect(screen.getByText('Test Chart')).toBeInTheDocument();
      });

      // Output
      expect(screen.getByText('details.sections.output')).toBeInTheDocument();
    });

    it('renders workload without model or dataset', async () => {
      const workloadWithoutModel = {
        ...mockWorkload,
        model: undefined,
        dataset: undefined,
        datasetId: undefined,
      };

      // Mock the service to return the workload without model/dataset
      (getWorkload as Mock).mockResolvedValue(workloadWithoutModel);

      await act(async () => {
        render(<WorkloadDetailsPage />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(
          screen.queryByText('details.sections.modelAndDataset'),
        ).not.toBeInTheDocument();
      });
    });

    it('renders the unified AI gateway inference URL for inference workloads when the gateway is enabled', async () => {
      (useProject as Mock).mockReturnValue({
        activeProject: 'test-project',
        projectPath: (path: string) =>
          `/test-project${path.startsWith('/') ? path : `/${path}`}`,
        projectUrl: (path: string) =>
          `/test-project${path.startsWith('/') ? path : `/${path}`}`,
        aiGatewayEnabled: true,
        aiGatewayUrl: 'https://ai.example.com',
      });

      await act(async () => {
        render(<WorkloadDetailsPage />, {
          wrapper,
        });
      });

      await waitFor(() => {
        // The unified inference URL replaces the per-service external host.
        expect(
          screen.getByText(
            'models:aimCatalog.actions.connect.modal.inferenceUrl',
          ),
        ).toBeInTheDocument();
        expect(
          screen.queryByText('details.fields.externalHost'),
        ).not.toBeInTheDocument();
        // The per-service internal host stays.
        expect(
          screen.getByText('details.fields.internalHost'),
        ).toBeInTheDocument();
      });
    });

    it('renders workload without output data', async () => {
      const workloadWithoutOutput = {
        ...mockWorkload,
        endpoints: undefined,
      };

      (getWorkload as Mock).mockResolvedValue(workloadWithoutOutput);

      await act(async () => {
        render(<WorkloadDetailsPage />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(
          screen.queryByText('details.sections.output'),
        ).not.toBeInTheDocument();
      });
    });

    it('renders the description when present', async () => {
      (getWorkload as Mock).mockResolvedValue({
        ...mockWorkload,
        description: 'A helpful description',
      });

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.getByText('list.headers.description.title'),
        ).toBeInTheDocument();
        expect(screen.getByText('A helpful description')).toBeInTheDocument();
      });
    });

    it('omits the description row when no description is present', async () => {
      (getWorkload as Mock).mockResolvedValue({
        ...mockWorkload,
        description: null,
      });

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.getByText('details.sections.basicInformation'),
        ).toBeInTheDocument();
      });

      expect(
        screen.queryByText('list.headers.description.title'),
      ).not.toBeInTheDocument();
    });
  });

  describe('Action Buttons', () => {
    it('shows workspace button for running workspace workload', async () => {
      // Mock the service to return the workspace workload
      (getWorkload as Mock).mockResolvedValue(mockWorkspaceWorkload);

      await act(async () => {
        render(<WorkloadDetailsPage />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(
          screen.getByText('list.actions.openWorkspace.label'),
        ).toBeInTheDocument();
      });
    });

    it('shows chat button for inference workload', async () => {
      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(screen.getByText('list.actions.chat.label')).toBeInTheDocument();
      });
    });

    it('shows logs button', async () => {
      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(screen.getByText('list.actions.logs.label')).toBeInTheDocument();
      });
    });

    it('shows delete button for non-deleted workload', async () => {
      // Default mockWorkload is INFERENCE which is now non-deletable on the
      // detail page (raw inference workloads have no capability delete).
      // Use a workspace to verify the Delete button surfaces for deletable
      // capability-backed workloads.
      (getWorkload as Mock).mockResolvedValue(mockWorkspaceWorkload);

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.getByText('list.actions.delete.label'),
        ).toBeInTheDocument();
      });
    });

    it('does not show delete button for deleted workload', async () => {
      const deletedWorkload = {
        ...mockWorkload,
        status: 'Deleted',
      };

      // Mock the service to return the deleted workload
      (getWorkload as Mock).mockResolvedValue(deletedWorkload);

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.queryByText('list.actions.delete.label'),
        ).not.toBeInTheDocument();
      });
    });

    it('does not show workspace button for non-running workload', async () => {
      const pendingWorkspaceWorkload = {
        ...mockWorkspaceWorkload,
        status: 'Pending',
      };

      // Mock the service to return the pending workspace workload
      (getWorkload as Mock).mockResolvedValue(pendingWorkspaceWorkload);

      await act(async () => {
        render(<WorkloadDetailsPage />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(
          screen.queryByText('list.actions.openWorkspace.label'),
        ).not.toBeInTheDocument();
      });
    });

    it('does not show chat button for workspace workload', async () => {
      const workloadWithoutChat = {
        ...mockWorkload,
        type: 'WORKSPACE',
      };

      // Mock the service to return workspace workload
      (getWorkload as Mock).mockResolvedValue(workloadWithoutChat);

      await act(async () => {
        render(<WorkloadDetailsPage />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(
          screen.queryByText('list.actions.chat.label'),
        ).not.toBeInTheDocument();
      });
    });
  });

  describe('User Interactions', () => {
    it('navigates back when back button is clicked', async () => {
      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      // Find the back button by looking for the SVG with arrow-left icon
      const backButton = await screen.findByRole('button', {
        name: (content, element) => {
          return element?.querySelector('.tabler-icon-arrow-left') !== null;
        },
      });
      await act(async () => {
        fireEvent.click(backButton);
      });

      expect(mockBack).toHaveBeenCalled();
    });

    it('opens chat when chat button is clicked', async () => {
      (getWorkload as Mock).mockResolvedValue(mockWorkload);

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      const chatButton = await waitFor(() =>
        screen.getByText('list.actions.chat.label'),
      );

      await act(async () => {
        fireEvent.click(chatButton);
      });

      expect(mockPush).toHaveBeenCalledWith(
        '/test-project/chat?workload=workload-1',
      );
    });

    it('opens workspace in new window when workspace button is clicked', async () => {
      (getWorkload as Mock).mockResolvedValue(mockWorkspaceWorkload);

      await act(async () => {
        render(<WorkloadDetailsPage />, {
          wrapper,
        });
      });

      const workspaceButton = await waitFor(() =>
        screen.getByText('list.actions.openWorkspace.label'),
      );

      await act(async () => {
        fireEvent.click(workspaceButton);
      });

      expect(window.open).toHaveBeenCalledWith(
        'https://example.com/external',
        '_blank',
      );
    });

    it('opens logs modal when logs button is clicked', async () => {
      (getWorkload as Mock).mockResolvedValue(mockWorkload);

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      const logsButton = await waitFor(() =>
        screen.getByText('list.actions.logs.label'),
      );

      await act(async () => {
        fireEvent.click(logsButton);
      });
    });

    it('opens delete modal when delete button is clicked', async () => {
      // Default mockWorkload is INFERENCE, which no longer surfaces Delete on
      // this page. Use a workspace to exercise the modal-open path.
      (getWorkload as Mock).mockResolvedValue(mockWorkspaceWorkload);

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      const deleteButton = await waitFor(() =>
        screen.getByText('list.actions.delete.label'),
      );

      await act(async () => {
        fireEvent.click(deleteButton);
      });
    });

    it('fetches model using workload.id for fine-tuning workloads when complete', async () => {
      // For FINE_TUNING, the workload itself IS the model — use workload.id directly
      // to look up the AIMModel via WORKLOAD_ID_LABEL. model_id is not used.
      const mockFTWorkload = {
        ...mockWorkload,
        id: 'ft-workload-id',
        name: 'wb-llm-finetune-abc123-job',
        type: 'FINE_TUNING',
        status: 'Complete',
      };

      (getWorkload as Mock).mockResolvedValue(mockFTWorkload);
      (useRouter as Mock).mockReturnValue({
        query: { id: 'ft-workload-id', project: 'test-project' },
        push: mockPush,
        back: mockBack,
      });

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(getProjectFineTunedModel).toHaveBeenCalledWith(
          'ft-workload-id',
          'test-project',
        );
      });
    });

    it('does not fetch model for in-progress fine-tuning workloads', async () => {
      // AIMModel CR doesn't exist until training completes — skip model fetch.
      const mockFTWorkload = {
        ...mockWorkload,
        id: 'ft-workload-id',
        name: 'wb-llm-finetune-abc123-job',
        type: 'FINE_TUNING',
        status: 'Running',
      };

      (getWorkload as Mock).mockResolvedValue(mockFTWorkload);
      (useRouter as Mock).mockReturnValue({
        query: { id: 'ft-workload-id', project: 'test-project' },
        push: mockPush,
        back: mockBack,
      });

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(getProjectFineTunedModel).not.toHaveBeenCalled();
      });
    });

    it('fetches model for fine-tuning workloads using workload id', async () => {
      const mockFTWorkload = {
        ...mockWorkload,
        id: 'ft-workload-id',
        type: 'FINE_TUNING',
        status: 'Complete',
      };

      (getWorkload as Mock).mockResolvedValue(mockFTWorkload);
      (useRouter as Mock).mockReturnValue({
        query: { id: 'ft-workload-id', project: 'test-project' },
        push: mockPush,
        back: mockBack,
      });

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(getProjectFineTunedModel).toHaveBeenCalledWith(
          'ft-workload-id',
          'test-project',
        );
      });
    });

    it('calls cancelFineTuningJob for fine-tuning workloads', async () => {
      const mockFTWorkload = {
        ...mockWorkload,
        id: 'workload-4',
        name: 'Model fine-tuning',
        type: 'FINE_TUNING',
        status: 'Running',
      };

      (getWorkload as Mock).mockResolvedValue(mockFTWorkload);

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      const deleteButton = await waitFor(() =>
        screen.getByText('list.actions.delete.label'),
      );

      await act(async () => {
        fireEvent.click(deleteButton);
      });

      const confirmButton = await waitFor(() =>
        screen.getByTestId('confirm-delete'),
      );

      await act(async () => {
        fireEvent.click(confirmButton);
      });

      await waitFor(() => {
        expect(cancelFineTuningJob).toHaveBeenCalledWith(
          'workload-4',
          'test-project',
        );
      });
    });

    it('hides the Delete action for raw inference workloads', async () => {
      // AIM-service-backed inference deployments link to /aims/[id], so an
      // INFERENCE row on this page is a raw workload-table row. The
      // inference capability DELETE expects an AIM service id and would 404
      // on a workload-table id, so the Delete action must be hidden.
      const mockInferenceWorkload = {
        ...mockWorkload,
        id: 'inference-7',
        type: 'INFERENCE',
        status: 'Running',
      };

      (getWorkload as Mock).mockResolvedValue(mockInferenceWorkload);

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(screen.getByText('list.actions.logs.label')).toBeInTheDocument();
      });

      expect(
        screen.queryByText('list.actions.delete.label'),
      ).not.toBeInTheDocument();
      expect(deleteInferenceDeployment).not.toHaveBeenCalled();
    });

    it('calls deleteWorkspace for workspace workloads', async () => {
      const mockWorkspace = {
        ...mockWorkload,
        id: 'workspace-5',
        name: 'wb-vscode-abc',
        type: 'WORKSPACE',
        status: 'Running',
      };

      (getWorkload as Mock).mockResolvedValue(mockWorkspace);

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      const deleteButton = await waitFor(() =>
        screen.getByText('list.actions.delete.label'),
      );

      await act(async () => {
        fireEvent.click(deleteButton);
      });

      const confirmButton = await waitFor(() =>
        screen.getByTestId('confirm-delete'),
      );

      await act(async () => {
        fireEvent.click(confirmButton);
      });

      await waitFor(() => {
        expect(deleteWorkspace).toHaveBeenCalledWith(
          'test-project',
          'workspace-5',
        );
      });
    });
  });

  describe('Connect to model button', () => {
    it('renders connect to model button for inference workload with endpoints', async () => {
      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.getByTestId('connect-to-model-button'),
        ).toBeInTheDocument();
      });
    });

    it('opens connect modal when connect to model button is clicked', async () => {
      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      const connectButton = await waitFor(() =>
        screen.getByTestId('connect-to-model-button'),
      );

      await act(async () => {
        fireEvent.click(connectButton);
      });

      await waitFor(() => {
        expect(screen.getByTestId('aim-connect-modal')).toBeInTheDocument();
      });
    });

    it('does not render connect to model button for non-inference workloads', async () => {
      (getWorkload as Mock).mockResolvedValue(mockWorkspaceWorkload);

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(screen.getByText('list.actions.logs.label')).toBeInTheDocument();
      });
      expect(
        screen.queryByTestId('connect-to-model-button'),
      ).not.toBeInTheDocument();
    });

    it('does not render connect to model button for inference workload without endpoints', async () => {
      (getWorkload as Mock).mockResolvedValue({
        ...mockWorkload,
        endpoints: undefined,
      });

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(screen.getByText('list.actions.logs.label')).toBeInTheDocument();
      });
      expect(
        screen.queryByTestId('connect-to-model-button'),
      ).not.toBeInTheDocument();
    });
  });

  describe('Clipboard Functionality', () => {
    it('copies external host URL when the copy button is clicked', async () => {
      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.getByDisplayValue(
            'https://example.com/external/v1/chat/completions',
          ),
        ).toBeInTheDocument();
      });

      const copyButtons = screen.getAllByRole('button', {
        name: 'actions.copy.title',
      });
      fireEvent.click(copyButtons[0]);

      await waitFor(() => {
        expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
          'https://example.com/external/v1/chat/completions',
        );
      });
    });
  });

  describe('Query keys', () => {
    it('includes activeProject in the workload query key so cache invalidates on project switch', async () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      const localWrapper = ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      );

      await act(async () => {
        render(<WorkloadDetailsPage />, { wrapper: localWrapper });
      });

      await waitFor(() => {
        const workloadQuery = queryClient
          .getQueryCache()
          .getAll()
          .find((q) => q.queryKey[0] === 'workload' && q.queryKey.length === 3);
        expect(workloadQuery?.queryKey).toEqual([
          'workload',
          'test-project',
          'workload-1',
        ]);
      });
    });
  });

  describe('Edge Cases', () => {
    it('handles workload with null GPU resources', async () => {
      const workloadWithNullGPU = {
        ...mockWorkload,
        allocatedResources: {
          gpuCount: null,
          vram: null,
        },
      };

      // Mock the service to return the workload with null GPU resources
      (getWorkload as Mock).mockResolvedValue(workloadWithNullGPU);

      await act(async () => {
        render(<WorkloadDetailsPage />, {
          wrapper,
        });
      });

      await waitFor(() => {
        // Should render NoDataDisplay components for null resources
        expect(
          screen.getByText('details.sections.resources'),
        ).toBeInTheDocument();
      });
    });

    it('handles workload without allocated resources', async () => {
      const workloadWithoutResources = {
        ...mockWorkload,
        allocatedResources: {
          gpuCount: null,
          vram: null,
        },
      };

      // Mock the service to return the workload without allocated resources
      (getWorkload as Mock).mockResolvedValue(workloadWithoutResources);

      await act(async () => {
        render(<WorkloadDetailsPage />, {
          wrapper,
        });
      });

      await waitFor(() => {
        expect(
          screen.getByText('details.sections.resources'),
        ).toBeInTheDocument();
      });
    });

    it('handles workload with dataset', async () => {
      const workloadWithDataset = {
        ...mockWorkload,
        datasetId: 'dataset-1',
      };

      (getWorkload as Mock).mockResolvedValue(workloadWithDataset);

      await act(async () => {
        render(<WorkloadDetailsPage />, {
          wrapper,
        });
      });

      // Should display the dataset name from the mocked dataset
      await waitFor(() => {
        expect(screen.getByText('Test Dataset')).toBeInTheDocument();
      });
    });
  });
});
