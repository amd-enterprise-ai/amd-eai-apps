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
import { useRouter } from 'next/router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { APIRequestError } from '@amdenterpriseai/utils/app';
import { useProject } from '@/contexts/ProjectContext';
import type { AIMService, AIMClusterModel, ParsedAIM } from '@/types/aims';
import {
  aimParser,
  getAIMServiceStatusVariants,
  getAimClusterProfileByName,
  getProjectAimProfileByName,
} from '@/lib/app/aims';
import {
  deleteInferenceDeployment,
  getInferenceDeployment,
  getInferenceModel,
  getInferenceReplicas,
  listAllInferenceDeployments,
} from '@/lib/app/inference';
import { getCustomModel } from '@/lib/app/custom-models';
import { getAdapterArtifacts } from '@/lib/app/artifacts';
import {
  AIM_DISPLAY_NAME_ANNOTATION,
  NAMESPACE_AIM_MODEL_LABEL,
} from '@/types/aims';
import { useScalingConvergence } from '@/hooks/useScalingConvergence';
import AimDetailsPage from '@/pages/[project]/aims/[id]/index';
import wrapper from '@/__tests__/ProviderWrapper';
import '@testing-library/jest-dom';
import { Mock, vi } from 'vitest';

vi.mock('next/router', () => ({
  useRouter: vi.fn(),
}));

vi.mock('@/contexts/ProjectContext', async (importOriginal) => ({
  ...(await importOriginal()),
  useProject: vi.fn(),
}));

vi.mock('@/lib/app/aims', async (importOriginal) => ({
  ...(await importOriginal()),
  aimParser: vi.fn(),
  getAIMServiceStatusVariants: vi.fn(() => ({})),
  getProjectAimProfileByName: vi.fn(),
  getAimClusterProfileByName: vi.fn(),
}));

vi.mock('@/lib/app/inference', () => ({
  deleteInferenceDeployment: vi.fn(),
  getInferenceDeployment: vi.fn(),
  getInferenceModel: vi.fn(),
  getInferenceReplicas: vi.fn(),
  listAllInferenceDeployments: vi.fn(),
}));

vi.mock('@/lib/app/custom-models', () => ({
  getCustomModel: vi.fn(),
}));

vi.mock('@/lib/app/artifacts', () => ({
  getAdapterArtifacts: vi.fn(),
}));

vi.mock('@/hooks/useScalingConvergence', () => ({
  useScalingConvergence: vi.fn(),
  CONVERGENCE_POLL_INTERVAL_MS: 5000,
}));

vi.mock('@/components/features/workloads/ScalingStatusCard', () => ({
  ScalingStatusCard: vi.fn(({ onSettingsSaved }) => (
    <div data-testid="scaling-status-card">
      <button
        data-testid="trigger-settings-saved"
        onClick={() =>
          onSettingsSaved?.({
            minReplicas: 2,
            maxReplicas: 5,
            metricQuery: 'vllm:num_requests_running',
            operationOverTime: 'avg',
            targetType: 'Value',
            targetValue: 10,
          })
        }
      >
        Save Settings
      </button>
    </div>
  )),
}));

vi.mock('@/components/features/workloads/DeleteWorkloadModal', () => ({
  __esModule: true,
  default: vi.fn(() => <div data-testid="delete-modal" />),
}));

vi.mock('@/components/features/workloads/WorkloadLogsModal', () => ({
  __esModule: true,
  default: vi.fn(() => <div data-testid="logs-modal" />),
}));

vi.mock('@/components/features/workloads/InferenceMetrics', () => ({
  __esModule: true,
  default: vi.fn(() => <div data-testid="inference-metrics" />),
}));

vi.mock('@/components/features/models/AIMConnectModal', () => ({
  __esModule: true,
  default: vi.fn(() => <div data-testid="aim-connect-modal" />),
}));

vi.mock('@/components/features/workloads/EditLoraAdaptersModal', () => ({
  EditLoraAdaptersModal: ({
    isOpen,
    onSuccess,
  }: {
    isOpen: boolean;
    onSuccess?: () => void;
  }) =>
    isOpen ? (
      <button data-testid="save-lora-adapters" onClick={onSuccess}>
        Save LoRA adapters
      </button>
    ) : null,
}));

vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  __esModule: true,
  useSystemToast: () => ({
    toast: mockToast,
  }),
}));

vi.mock('next-i18next', () => ({
  Trans: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTranslation: () => ({
    t: (key: string, options?: any) => {
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

Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn().mockResolvedValue(undefined),
  },
});

const mockToast = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
};

const mockStartPolling = vi.fn();

const mockAimService: AIMService = {
  id: 'aim-service-1',
  metadata: {
    name: 'aim-llama-8b',
    namespace: 'test-project',
    uid: 'uid-1',
    labels: {},
    annotations: { 'eai.amd.com/submitter': 'test-user' },
    creationTimestamp: '2025-01-01T00:00:00Z',
    ownerReferences: [],
  },
  spec: {
    model: { name: 'aim-llama-8b' },
    replicas: 1,
    routing: { annotations: {}, enabled: false },
    runtimeConfigName: 'default',
    minReplicas: 1,
    maxReplicas: 5,
    autoScaling: {
      metrics: [
        {
          type: 'PodMetric',
          podmetric: {
            metric: {
              backend: 'opentelemetry',
              metricNames: ['vllm:num_requests_running'],
              query: 'vllm:num_requests_running',
              operationOverTime: 'avg',
            },
            target: { type: 'Value', value: '10' },
          },
        },
      ],
    },
  },
  status: {
    status: 'Running',
    conditions: [
      {
        type: 'CacheReady',
        status: 'True',
        reason: 'CacheReady',
        message: 'Cache is ready',
        observedGeneration: 1,
        lastTransitionTime: '2025-01-01T00:00:00Z',
      },
      {
        type: 'InferenceReady',
        status: 'False',
        reason: 'InferenceFailed',
        message: 'Inference failed',
        observedGeneration: 1,
        lastTransitionTime: '2025-01-01T00:00:00Z',
      },
    ],
    runtime: {
      currentReplicas: 2,
      desiredReplicas: 3,
      minReplicas: 1,
      maxReplicas: 5,
    },
    resolvedModel: { name: 'aim-llama-8b' },
    resolvedProfile: { name: 'profile-1' },
  },
  statusValue: '',
  endpoints: {
    external: 'https://example.com/aim',
    internal: 'http://aim.default.svc.cluster.local',
  },
};

const mockAimClusterModel: AIMClusterModel = {
  metadata: {
    name: 'aim-llama-8b',
    namespace: null,
    uid: 'uid-2',
    labels: {},
    annotations: {
      'aim.eai.amd.com/source-registry': 'ghcr.io',
      'aim.eai.amd.com/source-repository': 'amdenterpriseai/aim-llama-8b',
      'aim.eai.amd.com/source-tag': '0.7.0',
    },
    creationTimestamp: '2025-01-01T00:00:00Z',
    ownerReferences: [],
  },
  spec: {
    image: 'ghcr.io/amdenterpriseai/aim-llama-8b:0.7.0',
  },
  status: {
    status: 'Available' as any,
    imageMetadata: {
      model: {
        canonicalName: 'meta-llama/Llama-3.1-8B-Instruct',
        title: 'Llama 3.1 8B Instruct',
        tags: [],
        descriptionFull: 'Full description',
        hfTokenRequired: false,
      },
      oci: {
        title: 'Llama 3.1 8B Instruct',
        description: 'A large language model',
        version: '0.7.0',
      },
    } as any,
  },
};

const mockParsedAim: ParsedAIM = {
  model: 'aim-llama-8b',
  aimId: 'meta-llama/Llama-3.1-8B-Instruct',
  imageReference: 'ghcr.io/amdenterpriseai/aim-llama-8b:0.7.0',
  annotations: mockAimClusterModel.metadata.annotations ?? {},
  description: { short: 'A large language model', full: 'Full description' },
  title: 'Llama 3.1 8B Instruct',
  imageVersion: '0.7.0',
  canonicalName: 'meta-llama/Llama-3.1-8B-Instruct',
  tags: [],
  status: 'Available' as any,
  workloadStatuses: ['Deployed' as any],
  isPreview: false,
  isHfTokenRequired: false,
  deployedService: mockAimService,
  deployedServices: [mockAimService],
};

describe('AimDetailsPage', () => {
  const mockPush = vi.fn();
  const mockBack = vi.fn();
  const mockReload = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    (useRouter as Mock).mockReturnValue({
      query: { id: 'aim-service-1', project: 'test-project' },
      push: mockPush,
      back: mockBack,
      reload: mockReload,
    });
    (useProject as Mock).mockReturnValue({
      activeProject: 'test-project',
      projectPath: (path: string) =>
        `/test-project${path.startsWith('/') ? path : `/${path}`}`,
      projectUrl: (path: string) =>
        `/test-project${path.startsWith('/') ? path : `/${path}`}`,
    });
    (getInferenceDeployment as Mock).mockResolvedValue(mockAimService);
    (getInferenceModel as Mock).mockResolvedValue(mockAimClusterModel);
    (listAllInferenceDeployments as Mock).mockResolvedValue([]);
    (getInferenceReplicas as Mock).mockResolvedValue([]);
    (aimParser as Mock).mockReturnValue(mockParsedAim);
    (getAIMServiceStatusVariants as Mock).mockReturnValue({});
    (getAdapterArtifacts as Mock).mockResolvedValue([]);
    (getProjectAimProfileByName as Mock).mockResolvedValue(undefined);
    (getAimClusterProfileByName as Mock).mockResolvedValue(undefined);
    (useScalingConvergence as Mock).mockReturnValue({
      startPolling: mockStartPolling,
    });
  });

  describe('Rendering', () => {
    it('renders AIM details with basic information', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.getAllByText('meta-llama/Llama-3.1-8B-Instruct').length,
        ).toBeGreaterThan(0);
        expect(
          screen.getByText('details.sections.basicInformation'),
        ).toBeInTheDocument();
        expect(screen.getByText('details.sections.status')).toBeInTheDocument();
      });
    });

    it('renders profile section with model details', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(screen.getByText('details.profile.title')).toBeInTheDocument();
        expect(
          screen.getByText('details.profile.performanceMetric'),
        ).toBeInTheDocument();
        expect(
          screen.getByText('details.profile.accelerator'),
        ).toBeInTheDocument();
      });
    });

    it('renders output section with endpoints', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(screen.getByText('details.sections.output')).toBeInTheDocument();
        expect(
          screen.getByText('details.fields.externalHost'),
        ).toBeInTheDocument();
        expect(
          screen.getByText('details.fields.internalHost'),
        ).toBeInTheDocument();
      });
    });

    it('renders the unified AI gateway inference URL when the gateway is enabled and configured', async () => {
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
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
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

    it('renders status section with conditions accordion', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(screen.getByText('details.sections.status')).toBeInTheDocument();
        expect(
          screen.getByText('list.headers.createdBy.title'),
        ).toBeInTheDocument();
      });
    });

    it('renders ScalingStatusCard when autoscaling is configured', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(screen.getByTestId('scaling-status-card')).toBeInTheDocument();
      });
    });

    it('renders action buttons', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(screen.getByText('list.actions.chat.label')).toBeInTheDocument();
        expect(screen.getByText('list.actions.logs.label')).toBeInTheDocument();
        expect(
          screen.getByText('list.actions.delete.label'),
        ).toBeInTheDocument();
      });
    });

    it('prefers AIM service display name in the title when it differs from resource name', async () => {
      const serviceWithDisplayName: AIMService = {
        ...mockAimService,
        metadata: {
          ...mockAimService.metadata,
          name: 'aim-llama-8b',
          annotations: {
            ...mockAimService.metadata.annotations,
            [AIM_DISPLAY_NAME_ANNOTATION]: 'Llama 8B Friendly Deploy Name',
          },
        },
      };
      (getInferenceDeployment as Mock).mockResolvedValue(
        serviceWithDisplayName,
      );
      (aimParser as Mock).mockReturnValue({
        ...mockParsedAim,
        deployedService: serviceWithDisplayName,
        deployedServices: [serviceWithDisplayName],
      });

      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.getByText('Llama 8B Friendly Deploy Name'),
        ).toBeInTheDocument();
      });
    });

    it('hides the chat action for a transcription deployment', async () => {
      (aimParser as Mock).mockReturnValue({
        ...mockParsedAim,
        tags: ['transcription'],
      });

      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(screen.getByText('list.actions.logs.label')).toBeInTheDocument();
      });
      // Transcription deployments have no chat playground surface.
      expect(
        screen.queryByText('list.actions.chat.label'),
      ).not.toBeInTheDocument();
    });

    it('renders inference metrics for running service', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(screen.getByTestId('inference-metrics')).toBeInTheDocument();
      });
    });
  });

  // The page used to send every scope that was not exactly `Namespace` to the
  // cluster catalog, while the hook resolves those references namespace-first.
  // A namespace-only overlay was therefore missed, and a namesake existing in
  // both scopes answered with the wrong weights.
  describe('resolved profile scope', () => {
    const NAMESPACE_GPU = 'MI300X-from-namespace';
    const CLUSTER_GPU = 'MI300X-from-cluster';
    // The accelerator cell carries an "automatic" suffix when the value is not
    // an override, so the spec that won is matched inside the rendered string.
    const shownAs = (gpu: string) => new RegExp(gpu);

    const renderWithProfileScope = async (scope?: string) => {
      const scopedService = {
        ...mockAimService,
        status: {
          ...mockAimService.status,
          resolvedProfile: { name: 'profile-1', ...(scope ? { scope } : {}) },
        },
      } as AIMService;
      (getInferenceDeployment as Mock).mockResolvedValue(scopedService);
      (aimParser as Mock).mockReturnValue({
        ...mockParsedAim,
        deployedService: scopedService,
        deployedServices: [scopedService],
      });

      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });
    };

    beforeEach(() => {
      // Same name in both scopes, different weights behind it — the case the
      // old cluster-only lookup could not tell apart.
      (getProjectAimProfileByName as Mock).mockResolvedValue({
        metadata: { name: 'profile-1' },
        spec: { acceleratorModel: NAMESPACE_GPU },
      });
      (getAimClusterProfileByName as Mock).mockResolvedValue({
        metadata: { name: 'profile-1' },
        spec: { acceleratorModel: CLUSTER_GPU },
      });
    });

    it.each([
      ['an absent scope', undefined],
      ['Merged', 'Merged'],
      ['Unknown', 'Unknown'],
    ])(
      'resolves a namespace-only profile referenced with %s',
      async (_label, scope) => {
        await renderWithProfileScope(scope);

        await waitFor(() =>
          expect(getProjectAimProfileByName).toHaveBeenCalledWith(
            'test-project',
            'profile-1',
          ),
        );
        // The project answered, so the cluster namesake is never consulted and
        // its weights can never reach the page.
        expect(getAimClusterProfileByName).not.toHaveBeenCalled();
        expect(
          await screen.findByText(shownAs(NAMESPACE_GPU)),
        ).toBeInTheDocument();
        expect(
          screen.queryByText(shownAs(CLUSTER_GPU)),
        ).not.toBeInTheDocument();
      },
    );

    it('falls back to the cluster profile when the project has none', async () => {
      (getProjectAimProfileByName as Mock).mockRejectedValue(
        new APIRequestError('not found', 404),
      );

      await renderWithProfileScope('Merged');

      await waitFor(() =>
        expect(getAimClusterProfileByName).toHaveBeenCalledWith('profile-1'),
      );
      expect(await screen.findByText(shownAs(CLUSTER_GPU))).toBeInTheDocument();
    });

    it('reads a Cluster-scoped reference from the cluster catalog only', async () => {
      await renderWithProfileScope('Cluster');

      await waitFor(() =>
        expect(getAimClusterProfileByName).toHaveBeenCalledWith('profile-1'),
      );
      expect(getProjectAimProfileByName).not.toHaveBeenCalled();
      expect(await screen.findByText(shownAs(CLUSTER_GPU))).toBeInTheDocument();
    });

    it('reads a Namespace-scoped reference from the project only', async () => {
      await renderWithProfileScope('Namespace');

      await waitFor(() =>
        expect(getProjectAimProfileByName).toHaveBeenCalledWith(
          'test-project',
          'profile-1',
        ),
      );
      expect(getAimClusterProfileByName).not.toHaveBeenCalled();
      expect(
        await screen.findByText(shownAs(NAMESPACE_GPU)),
      ).toBeInTheDocument();
    });
  });

  describe('LoRA adapters', () => {
    const loraService: AIMService = {
      ...mockAimService,
      spec: {
        ...mockAimService.spec,
        adapterMode: 'dynamic',
        adapters: [{ name: 'adapter-1' }],
        adapterRuntime: { maxRank: 64 },
      } as any,
    };

    const renderWithLoraService = async () => {
      (getInferenceDeployment as Mock).mockResolvedValue(loraService);
      (aimParser as Mock).mockReturnValue({
        ...mockParsedAim,
        deployedService: loraService,
        deployedServices: [loraService],
      });
      (getAdapterArtifacts as Mock).mockResolvedValue([
        {
          id: 'adapter-1',
          name: 'adapter-1',
          displayName: 'Support LoRA',
          compatibleWith: [],
          rank: 16,
        },
      ]);

      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });
    };

    it('renders attached LoRA details for a dynamic deployment', async () => {
      await renderWithLoraService();

      await waitFor(() => {
        expect(screen.getByTestId('lora-adapters-card')).toBeInTheDocument();
        expect(screen.getByText('64')).toBeInTheDocument();
        expect(screen.getByText('Support LoRA')).toBeInTheDocument();
        expect(
          screen.getByTestId('edit-lora-adapters-button'),
        ).toBeInTheDocument();
      });
    });

    it('does not render the LoRA card without adapters or a rank limit', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.queryByTestId('lora-adapters-card'),
        ).not.toBeInTheDocument();
      });
    });

    it('refetches deployment details after LoRA adapters are updated', async () => {
      await renderWithLoraService();

      const editButton = await screen.findByTestId('edit-lora-adapters-button');
      fireEvent.click(editButton);
      fireEvent.click(await screen.findByTestId('save-lora-adapters'));

      await waitFor(() => {
        expect(getInferenceDeployment).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe('Error State', () => {
    it('renders error message when AIM cluster model fails to load', async () => {
      (getInferenceModel as Mock).mockRejectedValue(new Error('Not Found'));

      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.getByText('errors.workloadNotFound.title'),
        ).toBeInTheDocument();
      });
    });
  });

  describe('User Interactions', () => {
    it('navigates back when back button is clicked', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      const backButton = await screen.findByRole('button', {
        name: (_content, element) =>
          element?.querySelector('.tabler-icon-arrow-left') !== null,
      });
      await act(async () => {
        fireEvent.click(backButton);
      });

      expect(mockBack).toHaveBeenCalled();
    });

    it('opens logs modal when logs button is clicked', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      const logsButton = await waitFor(() =>
        screen.getByText('list.actions.logs.label'),
      );

      await act(async () => {
        fireEvent.click(logsButton);
      });

      await waitFor(() => {
        expect(screen.getByTestId('logs-modal')).toBeInTheDocument();
      });
    });
  });

  describe('Convergence Polling', () => {
    it('calls startPolling and refetch when settings are saved', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      const saveButton = await waitFor(() =>
        screen.getByTestId('trigger-settings-saved'),
      );

      await act(async () => {
        fireEvent.click(saveButton);
      });

      expect(mockStartPolling).toHaveBeenCalledWith({
        minReplicas: 2,
        maxReplicas: 5,
        metricQuery: 'vllm:num_requests_running',
        operationOverTime: 'avg',
        targetType: 'Value',
        targetValue: 10,
      });
    });

    it('passes stopConvergencePolling as onConverged to useScalingConvergence', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      expect(useScalingConvergence as Mock).toHaveBeenCalledWith(
        expect.objectContaining({
          onConverged: expect.any(Function),
          onTimeout: expect.any(Function),
          isPolling: false,
        }),
      );
    });

    it('passes handleConvergenceTimeout as onTimeout to useScalingConvergence', async () => {
      let capturedOnTimeout: (() => void) | undefined;
      (useScalingConvergence as Mock).mockImplementation((params) => {
        capturedOnTimeout = params.onTimeout;
        return { startPolling: mockStartPolling };
      });

      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      expect(capturedOnTimeout).toBeDefined();
      act(() => {
        capturedOnTimeout!();
      });

      expect(mockToast.warning).toHaveBeenCalledWith(
        'autoscaling:notifications.convergenceTimeout',
      );
    });
  });

  describe('Service without autoscaling', () => {
    it('does not render ScalingStatusCard when autoscaling is absent', async () => {
      const serviceWithoutAutoscaling = {
        ...mockAimService,
        spec: { ...mockAimService.spec, autoScaling: undefined },
      };
      (getInferenceDeployment as Mock).mockResolvedValue(
        serviceWithoutAutoscaling,
      );

      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.queryByTestId('scaling-status-card'),
        ).not.toBeInTheDocument();
      });
    });
  });

  describe('Connect to model button', () => {
    it('renders connect to model button when endpoints exist', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.getByTestId('connect-to-model-button'),
        ).toBeInTheDocument();
      });
    });

    it('opens connect modal when connect to model button is clicked', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
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

    it('does not render connect to model button when endpoints are missing', async () => {
      const serviceWithoutEndpoints = {
        ...mockAimService,
        endpoints: { internal: '', external: '' },
      };
      (getInferenceDeployment as Mock).mockResolvedValue(
        serviceWithoutEndpoints,
      );
      (aimParser as Mock).mockReturnValue({
        ...mockParsedAim,
        deployedService: serviceWithoutEndpoints,
        deployedServices: [serviceWithoutEndpoints],
      });

      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(screen.getByText('list.actions.logs.label')).toBeInTheDocument();
      });
      expect(
        screen.queryByTestId('connect-to-model-button'),
      ).not.toBeInTheDocument();
    });
  });

  describe('Service without endpoints', () => {
    it('does not render output section when endpoints are missing', async () => {
      const serviceWithoutEndpoints = {
        ...mockAimService,
        endpoints: { internal: '', external: '' },
      };
      (getInferenceDeployment as Mock).mockResolvedValue(
        serviceWithoutEndpoints,
      );
      (aimParser as Mock).mockReturnValue({
        ...mockParsedAim,
        deployedService: serviceWithoutEndpoints,
        deployedServices: [serviceWithoutEndpoints],
      });

      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.queryByText('details.sections.output'),
        ).not.toBeInTheDocument();
      });
    });
  });

  describe('Historical / Deleted AIM', () => {
    // Wrapper with retry enabled so we can exercise the per-query `retry`
    // override on the live query. The default ProviderWrapper sets
    // `retry: false` for all queries, which would mask the override.
    const RetryEnabledWrapper = ({
      children,
    }: {
      children: React.ReactNode;
    }) => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: 3, retryDelay: 0 } },
      });
      return (
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      );
    };

    it('does NOT call listAllInferenceDeployments when live AIM loads successfully', async () => {
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.getByText('details.sections.basicInformation'),
        ).toBeInTheDocument();
      });

      expect(listAllInferenceDeployments).not.toHaveBeenCalled();
    });

    it('calls listAllInferenceDeployments when live AIM returns 404', async () => {
      const historicalService = {
        ...mockAimService,
        status: { ...mockAimService.status, status: 'Deleted' },
      };
      (getInferenceDeployment as Mock).mockRejectedValue(
        new APIRequestError('not found', 404),
      );
      (listAllInferenceDeployments as Mock).mockResolvedValue([
        historicalService,
      ]);
      (aimParser as Mock).mockReturnValue({
        ...mockParsedAim,
        deployedService: historicalService,
        deployedServices: [historicalService],
      });

      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(listAllInferenceDeployments).toHaveBeenCalled();
      });
      await waitFor(() => {
        expect(
          screen.getByText('details.sections.basicInformation'),
        ).toBeInTheDocument();
      });
    });

    it('renders error fallback when live AIM returns non-404 error', async () => {
      (getInferenceDeployment as Mock).mockRejectedValue(
        new APIRequestError('boom', 500),
      );

      // Use retry-enabled wrapper with zero delay so the per-query `retry`
      // override (which retries 3x on non-404 errors) finishes quickly.
      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, {
          wrapper: RetryEnabledWrapper,
        });
      });

      await waitFor(
        () => {
          expect(
            screen.getByText('errors.workloadNotFound.title'),
          ).toBeInTheDocument();
        },
        { timeout: 3000 },
      );
      expect(listAllInferenceDeployments).not.toHaveBeenCalled();
    });

    it('does not retry live query on 404', async () => {
      (getInferenceDeployment as Mock).mockRejectedValue(
        new APIRequestError('not found', 404),
      );
      (listAllInferenceDeployments as Mock).mockResolvedValue([]);

      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, {
          wrapper: RetryEnabledWrapper,
        });
      });

      // History query fires once the live query 404s; wait on that observable
      // signal to guarantee the live query reached its terminal state.
      await waitFor(() => {
        expect(listAllInferenceDeployments).toHaveBeenCalled();
      });

      expect(getInferenceDeployment).toHaveBeenCalledTimes(1);
    });
  });

  describe('Custom (BYOM) model', () => {
    it('calls getCustomModel instead of getInferenceModel for namespace-scoped AIM services', async () => {
      const byomService: AIMService = {
        ...mockAimService,
        metadata: {
          ...mockAimService.metadata,
          labels: { [NAMESPACE_AIM_MODEL_LABEL]: 'true' },
        },
        spec: {
          ...mockAimService.spec!,
          model: { name: 'my-byom-model-cr' },
        },
        status: {
          ...mockAimService.status!,
          resolvedModel: { name: 'my-byom-model-cr', scope: 'Namespace' },
        },
      };
      (getInferenceDeployment as Mock).mockResolvedValue(byomService);
      (getCustomModel as Mock).mockResolvedValue({
        metadata: {
          name: 'my-byom-model-cr',
          namespace: 'test-project',
          labels: {},
          annotations: {
            'aiwb.apps.eai.amd.com/model-display-name': 'My Custom Model',
          },
          creationTimestamp: '2025-01-01T00:00:00Z',
        },
        spec: { aimId: null, image: '', modelSources: [], profiles: {} },
        phase: {
          state: 'Ready',
          status: 'Ready',
          templateReady: true,
          artifactPhase: null,
          artifactLastError: null,
        },
        status: null,
        profiles: [],
      });

      await act(async () => {
        render(<AimDetailsPage id="aim-service-1" />, { wrapper });
      });

      await waitFor(() => {
        expect(getCustomModel).toHaveBeenCalledWith(
          'test-project',
          'my-byom-model-cr',
        );
      });
      expect(getInferenceModel).not.toHaveBeenCalled();
    });
  });
});
