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
  within,
} from '@testing-library/react';

import { APIRequestError } from '@amdenterpriseai/utils/app';
import { fetchProjectWorkloadMetrics } from '@/lib/app/projects';
import { resolveAIMServiceDisplay } from '@/lib/app/aims';
import {
  deleteInferenceDeployment,
  getInferenceModel,
  listAllInferenceDeployments,
} from '@/lib/app/inference';
import { deleteWorkspace } from '@/lib/app/workloads';
import { cancelFineTuningJob } from '@/lib/app/models';

import type { EnrichedWorkloadMetrics } from '@/types/projects';
import {
  AIM_CANONICAL_NAME_ANNOTATION,
  NAMESPACE_AIM_MODEL_LABEL,
} from '@/types/aims';
import type { AIMService } from '@/types/aims';

import wrapper from '@/__tests__/ProviderWrapper';
import { Mock, vi } from 'vitest';

const mockUseCustomProfileDeployments = vi.hoisted(() =>
  vi.fn(() => ({
    profileByServiceId: new Map(),
    isLoading: false,
  })),
);

vi.mock('@/hooks/useCustomProfileDeployments', () => ({
  useCustomProfileDeployments: mockUseCustomProfileDeployments,
}));

vi.mock('@/lib/app/projects', async (importOriginal) => {
  return {
    ...(await importOriginal()),
    fetchProjectWorkloadMetrics: vi.fn(),
  };
});

vi.mock('@/lib/app/workloads', () => ({
  deleteWorkspace: vi.fn(),
}));

vi.mock('@/lib/app/models', () => ({
  cancelFineTuningJob: vi.fn(),
}));

vi.mock('@/lib/app/aims', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/app/aims')>()),
  resolveAIMServiceDisplay: vi.fn(),
}));

vi.mock('@/lib/app/inference', () => ({
  getInferenceModel: vi.fn(),
  listAllInferenceDeployments: vi.fn(),
  deleteInferenceDeployment: vi.fn(),
}));

import { NamespaceWorkloadsTable } from '@/components/features/projects/NamespaceWorkloadsTable';

const mockPush = vi.fn();
vi.mock('next/router', () => ({
  useRouter: () => ({
    push: mockPush,
    query: {},
    pathname: '/',
    asPath: '/',
  }),
}));

vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  __esModule: true,
  ...(await importOriginal()),
  useSystemToast: () => ({
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }),
}));

// Special-cases the max-rank key so tests can assert on the interpolated
// rank; every other key keeps the plain passthrough the rest of this suite
// already relies on.
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

vi.mock('@tabler/icons-react', async (importOriginal) => {
  const actual = (await importOriginal()) ?? {};
  return {
    ...actual,
    IconDotsVertical: () => <span>action-dots</span>,
    IconEye: () => null,
    IconFileText: () => null,
    IconLink: () => null,
    IconMessage: () => null,
    IconTrash: () => null,
  };
});

const createMockResourceMetrics = (
  overrides: Partial<EnrichedWorkloadMetrics> = {},
): EnrichedWorkloadMetrics => ({
  id: 'workload-1',
  name: 'workload-1',
  displayName: 'Test Workload',
  type: 'INFERENCE',
  status: 'Running',
  gpuCount: 1,
  templateGpuCount: null,
  gpu: null,
  acceleratorType: null,
  metric: null,
  precision: null,
  vram: 2 * 1024 * 1024 * 1024,
  createdAt: '2024-01-01T00:00:00Z',
  createdBy: 'test-user',
  resourceType: 'Deployment',
  ...overrides,
});

const mockNamespaceMetricsResponse = {
  data: [
    createMockResourceMetrics({
      id: 'workload-1',
      displayName: 'Regular Workload',
      resourceType: 'Deployment',
    }),
    createMockResourceMetrics({
      id: 'aim-service-1',
      displayName: 'AIM Service',
      resourceType: 'AIMService',
    }),
  ],
  pagination: { page: 1, pageSize: 20, total: 2 },
};

describe('NamespaceWorkloadsTable', () => {
  const mockFetchNamespaceMetrics = fetchProjectWorkloadMetrics as Mock;
  const mockListInferenceDeployments = listAllInferenceDeployments as Mock;
  const mockGetInferenceModel = getInferenceModel as Mock;
  const mockCancelFineTuningJob = cancelFineTuningJob as Mock;
  const mockDeleteInferenceDeployment = deleteInferenceDeployment as Mock;
  const mockDeleteWorkspace = deleteWorkspace as Mock;
  const mockResolveAIMServiceDisplay = resolveAIMServiceDisplay as Mock;

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseCustomProfileDeployments.mockReturnValue({
      profileByServiceId: new Map(),
      isLoading: false,
    });
    mockFetchNamespaceMetrics.mockResolvedValue(mockNamespaceMetricsResponse);
    mockListInferenceDeployments.mockResolvedValue([]);
    // Default: per-name catalog lookups 404. Tests that exercise cluster-catalog
    // enrichment override this with a per-name resolved value.
    mockGetInferenceModel.mockRejectedValue(
      new APIRequestError('not found', 404),
    );
    mockResolveAIMServiceDisplay.mockImplementation(
      (_service: unknown, _parsedAIMs: unknown[]) => ({
        canonicalName: 'test/model',
        imageVersion: '1.0',
        metric: 'default',
        title: 'Test Model',
        name: 'test-model',
      }),
    );
    Object.defineProperty(window, 'open', {
      writable: true,
      value: vi.fn(),
    });
  });

  it('renders table with loading state then data', async () => {
    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(mockFetchNamespaceMetrics).toHaveBeenCalledWith(
        'test-ns',
        expect.any(Object),
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Regular Workload')).toBeInTheDocument();
      expect(screen.getByText('AIM Service')).toBeInTheDocument();
    });
  });

  it('navigates to workload details when details action is clicked', async () => {
    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Regular Workload')).toBeInTheDocument();
    });

    const row = screen.getByText('Regular Workload').closest('tr');
    expect(row).not.toBeNull();
    const trigger = within(row!).getByRole('button', {
      name: 'list.actions.label',
    });
    await act(async () => {
      fireEvent.click(trigger);
    });

    const detailsAction = await screen.findByTestId('details');
    await act(async () => {
      fireEvent.click(detailsAction);
    });

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith({
        pathname: '/project1/workloads/workload-1',
        query: { ref: '/' },
      });
    });
  });

  it('navigates to AIM details when details action is clicked for AIM service', async () => {
    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('AIM Service')).toBeInTheDocument();
    });

    const rows = screen.getAllByRole('row');
    const aimRow = rows.find((r) => r.textContent?.includes('AIM Service'));
    expect(aimRow).toBeDefined();
    const trigger = within(aimRow!).getByRole('button', {
      name: 'list.actions.label',
    });
    await act(async () => {
      fireEvent.click(trigger);
    });

    const detailsAction = await screen.findByTestId('details');
    await act(async () => {
      fireEvent.click(detailsAction);
    });

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith({
        pathname: '/project1/aims/aim-service-1',
        query: { ref: '/' },
      });
    });
  });

  it('opens chat in new tab when chat action is clicked', async () => {
    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Regular Workload')).toBeInTheDocument();
    });

    const row = screen.getByText('Regular Workload').closest('tr');
    const trigger = within(row!).getByRole('button', {
      name: 'list.actions.label',
    });
    await act(async () => {
      fireEvent.click(trigger);
    });

    const chatAction = await screen.findByTestId('chat');
    await act(async () => {
      fireEvent.click(chatAction);
    });

    expect(window.open).toHaveBeenCalledWith(
      '/project1/chat?workload=workload-1',
      '_blank',
    );
  });

  it('shows Connect to model action for running AIM workloads', async () => {
    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('AIM Service')).toBeInTheDocument();
    });

    const rows = screen.getAllByRole('row');
    const aimRow = rows.find((r) => r.textContent?.includes('AIM Service'));
    const trigger = within(aimRow!).getByRole('button', {
      name: 'list.actions.label',
    });
    await act(async () => {
      fireEvent.click(trigger);
    });

    await waitFor(() => {
      expect(screen.getByTestId('connect')).toBeInTheDocument();
    });
  });

  it('suppresses chat and uses the transcription snippet for a transcription AIM row', async () => {
    const whisperService: AIMService = {
      id: 'aim-service-1',
      metadata: {
        name: 'whisper-service',
        namespace: 'test-ns',
        uid: 'uid-whisper',
        labels: {},
        annotations: {},
        creationTimestamp: '2024-01-01T00:00:00Z',
        ownerReferences: [],
      },
      spec: {
        model: { name: 'whisper' },
        replicas: 1,
        runtimeConfigName: 'default',
      },
      status: { status: 'Running', resolvedModel: { name: 'whisper' } },
      statusValue: '',
      endpoints: {
        external: 'https://whisper.example.com',
        internal: 'http://whisper.test-ns.svc.cluster.local',
      },
    };
    mockGetInferenceModel.mockRejectedValue(
      new APIRequestError('not found', 404),
    );
    mockListInferenceDeployments.mockResolvedValue([whisperService]);
    // The catalog model backing this row advertises a transcription tag.
    mockResolveAIMServiceDisplay.mockImplementation(() => ({
      canonicalName: 'openai/whisper-large-v3',
      imageVersion: '1.0',
      metric: 'default',
      title: 'Whisper',
      name: 'whisper',
      tags: ['transcription'],
    }));

    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('AIM Service')).toBeInTheDocument();
    });

    const rows = screen.getAllByRole('row');
    const aimRow = rows.find((r) => r.textContent?.includes('AIM Service'));
    const trigger = within(aimRow!).getByRole('button', {
      name: 'list.actions.label',
    });
    await act(async () => {
      fireEvent.click(trigger);
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

  it('renders the served model id (status.resolvedModel.name) in the connect snippet', async () => {
    // The served id lives on the AIMService's status.resolvedModel.name and is
    // populated for fine-tuned services too. The connect snippet emits that id
    // directly — never the annotation display name, which silently 404s against
    // the engine.
    const fineTunedAnnotationCanonicalName = 'meta-llama/Llama-3-8B-finetuned';
    const fineTunedAimService: AIMService = {
      id: 'aim-service-1',
      metadata: {
        name: 'fine-tuned-aim-service',
        namespace: 'test-ns',
        uid: 'uid-ft-1',
        labels: {},
        annotations: {
          [AIM_CANONICAL_NAME_ANNOTATION]: fineTunedAnnotationCanonicalName,
        },
        creationTimestamp: '2024-01-01T00:00:00Z',
        ownerReferences: [],
      },
      spec: {
        model: { name: 'fine-tuned-model-ref' },
        replicas: 1,
        runtimeConfigName: 'default',
      },
      status: {
        status: 'Running',
        resolvedModel: { name: 'fine-tuned-model-ref' },
      },
      statusValue: '',
      endpoints: {
        internal: 'http://fine-tuned-service.test-ns.svc.cluster.local',
      },
    };

    // Cluster catalog returns no entries — the served id no longer depends on a
    // catalog join; it is read straight off status.resolvedModel.name.
    mockGetInferenceModel.mockRejectedValue(
      new APIRequestError('not found', 404),
    );
    mockListInferenceDeployments.mockResolvedValue([fineTunedAimService]);

    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('AIM Service')).toBeInTheDocument();
    });

    const rows = screen.getAllByRole('row');
    const aimRow = rows.find((r) => r.textContent?.includes('AIM Service'));
    const trigger = within(aimRow!).getByRole('button', {
      name: 'list.actions.label',
    });
    await act(async () => {
      fireEvent.click(trigger);
    });

    const connectAction = await screen.findByTestId('connect');
    await act(async () => {
      fireEvent.click(connectAction);
    });

    // The snippet renders the served id from status.resolvedModel.name, and the
    // annotation display name must NOT leak into it.
    await waitFor(() => {
      expect(document.body).toHaveTextContent(
        '"model": "fine-tuned-model-ref"',
      );
    });
    expect(document.body).not.toHaveTextContent(
      fineTunedAnnotationCanonicalName,
    );
  });

  it('opens logs modal when logs action is clicked', async () => {
    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Regular Workload')).toBeInTheDocument();
    });

    const row = screen.getByText('Regular Workload').closest('tr');
    const trigger = within(row!).getByRole('button', {
      name: 'list.actions.label',
    });
    await act(async () => {
      fireEvent.click(trigger);
    });

    const logsAction = await screen.findByTestId('logs');
    await act(async () => {
      fireEvent.click(logsAction);
    });

    await screen.findByText('list.actions.logs.modal.title');
  });

  it('opens delete modal when delete action is clicked', async () => {
    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await screen.findByText('AIM Service');

    // Use the AIM_SERVICE row — Delete is only offered for rows the mutation
    // can dispatch to (AIM service / fine-tuning / workspace).
    const rows = screen.getAllByRole('row');
    const aimRow = rows.find((r) => r.textContent?.includes('AIM Service'));
    const trigger = within(aimRow!).getByRole('button', {
      name: 'list.actions.label',
    });
    await act(async () => {
      fireEvent.click(trigger);
    });

    const deleteAction = await screen.findByTestId('delete');
    await act(async () => {
      fireEvent.click(deleteAction);
    });

    expect(screen.getByTestId('confirmation-modal')).toBeInTheDocument();
  });

  it('does not offer Delete action for non-AIM INFERENCE deployment rows', async () => {
    // The Regular Workload row is type: INFERENCE, resourceType: DEPLOYMENT.
    // The mutation can only dispatch by resourceType === AIM_SERVICE for
    // inference rows; bare INFERENCE deployments have no capability surface,
    // so Delete must be filtered out (would otherwise hit the defensive throw).
    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Regular Workload')).toBeInTheDocument();
    });

    const row = screen.getByText('Regular Workload').closest('tr');
    const trigger = within(row!).getByRole('button', {
      name: 'list.actions.label',
    });
    await act(async () => {
      fireEvent.click(trigger);
    });

    await screen.findByTestId('logs');
    expect(screen.queryByTestId('delete')).not.toBeInTheDocument();
  });

  it('calls deleteInferenceDeployment when confirming delete for an AIM-service row', async () => {
    mockDeleteInferenceDeployment.mockResolvedValue(undefined);

    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('AIM Service')).toBeInTheDocument();
    });

    const row = screen.getByText('AIM Service').closest('tr');
    const trigger = within(row!).getByRole('button', {
      name: 'list.actions.label',
    });
    await act(async () => {
      fireEvent.click(trigger);
    });

    const deleteAction = await screen.findByTestId('delete');
    await act(async () => {
      fireEvent.click(deleteAction);
    });

    const confirmButton = await screen.findByTestId('confirm-button');
    await act(async () => {
      fireEvent.click(confirmButton);
    });

    await waitFor(() => {
      expect(mockDeleteInferenceDeployment).toHaveBeenCalledWith(
        'test-ns',
        'aim-service-1',
      );
    });
  });

  it('calls deleteWorkspace when confirming delete for workspace workload', async () => {
    mockDeleteWorkspace.mockResolvedValue(undefined);
    mockFetchNamespaceMetrics.mockResolvedValue({
      data: [
        createMockResourceMetrics({
          id: 'workspace-1',
          displayName: 'Workspace Workload',
          type: 'WORKSPACE',
          resourceType: 'Deployment',
        }),
      ],
      pagination: { page: 1, pageSize: 20, total: 1 },
    });

    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Workspace Workload')).toBeInTheDocument();
    });

    const row = screen.getByText('Workspace Workload').closest('tr');
    const trigger = within(row!).getByRole('button', {
      name: 'list.actions.label',
    });
    await act(async () => {
      fireEvent.click(trigger);
    });

    const deleteAction = await screen.findByTestId('delete');
    await act(async () => {
      fireEvent.click(deleteAction);
    });

    const confirmButton = await screen.findByTestId('confirm-button');
    await act(async () => {
      fireEvent.click(confirmButton);
    });

    await waitFor(() => {
      expect(mockDeleteWorkspace).toHaveBeenCalledWith(
        'test-ns',
        'workspace-1',
      );
    });
  });

  it('calls deleteInferenceDeployment when confirming delete for AIM service', async () => {
    mockDeleteInferenceDeployment.mockResolvedValue(undefined);

    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('AIM Service')).toBeInTheDocument();
    });

    const rows = screen.getAllByRole('row');
    const aimRow = rows.find((r) => r.textContent?.includes('AIM Service'));
    const trigger = within(aimRow!).getByRole('button', {
      name: 'list.actions.label',
    });
    await act(async () => {
      fireEvent.click(trigger);
    });

    const deleteAction = await screen.findByTestId('delete');
    await act(async () => {
      fireEvent.click(deleteAction);
    });

    const confirmButton = await screen.findByTestId('confirm-button');
    await act(async () => {
      fireEvent.click(confirmButton);
    });

    await waitFor(() => {
      expect(mockDeleteInferenceDeployment).toHaveBeenCalledWith(
        'test-ns',
        'aim-service-1',
      );
    });
  });

  it('calls cancelFineTuningJob when confirming delete for fine-tuning workload', async () => {
    mockCancelFineTuningJob.mockResolvedValue(undefined);
    mockFetchNamespaceMetrics.mockResolvedValue({
      data: [
        createMockResourceMetrics({
          id: 'ft-workload-1',
          displayName: 'Fine-tuning Job',
          type: 'FINE_TUNING',
          resourceType: 'Deployment',
        }),
      ],
      pagination: { page: 1, pageSize: 20, total: 1 },
    });

    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Fine-tuning Job')).toBeInTheDocument();
    });

    const row = screen.getByText('Fine-tuning Job').closest('tr');
    const trigger = within(row!).getByRole('button', {
      name: 'list.actions.label',
    });
    await act(async () => {
      fireEvent.click(trigger);
    });

    const deleteAction = await screen.findByTestId('delete');
    await act(async () => {
      fireEvent.click(deleteAction);
    });

    const confirmButton = await screen.findByTestId('confirm-button');
    await act(async () => {
      fireEvent.click(confirmButton);
    });

    await waitFor(() => {
      expect(mockCancelFineTuningJob).toHaveBeenCalledWith(
        'ft-workload-1',
        'test-ns',
      );
    });
  });

  it('displays createdAt and createdBy directly from namespace metrics response', async () => {
    // The API now returns createdAt/createdBy populated for fine-tuned AIMs
    // (sourced from K8s metadata when no DB row exists), so the FE no longer
    // needs to merge values from the AIMService CR.
    const metricsCreatedBy = 'metrics-user@example.com';
    const metricsCreatedAt = '2024-01-01T00:00:00Z';
    const metricsResponse = {
      data: [
        createMockResourceMetrics({
          id: 'aim-service-1',
          displayName: 'Fine-tuned AIM',
          resourceType: 'AIMService',
          createdAt: metricsCreatedAt,
          createdBy: metricsCreatedBy,
        }),
      ],
      pagination: { page: 1, pageSize: 20, total: 1 },
    };
    mockFetchNamespaceMetrics.mockResolvedValue(metricsResponse);

    // Provide an AIMService whose annotation/creationTimestamp differ from the
    // metrics row — proving the FE no longer overrides metrics-row values.
    const divergentAimService: AIMService = {
      id: 'aim-service-1',
      metadata: {
        name: 'fine-tuned-aim-service',
        namespace: 'test-ns',
        uid: 'uid-ft-1',
        labels: {},
        annotations: {
          'silogen.ai/submitter': 'cr-user@example.com',
        },
        creationTimestamp: '2099-12-31T23:59:59Z',
        ownerReferences: [],
      },
      spec: {
        model: { name: 'fine-tuned-model-ref' },
        replicas: 1,
        runtimeConfigName: 'default',
      },
      status: {
        status: 'Running',
        resolvedModel: { name: 'fine-tuned-model-ref' },
      },
      statusValue: '',
      endpoints: {
        internal: 'http://fine-tuned-service.test-ns.svc.cluster.local',
      },
    };
    mockListInferenceDeployments.mockResolvedValue([divergentAimService]);

    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Fine-tuned AIM')).toBeInTheDocument();
    });

    const row = screen.getByText('Fine-tuned AIM').closest('tr');
    expect(row).not.toBeNull();
    expect(within(row!).getByText(metricsCreatedBy)).toBeInTheDocument();
    expect(
      within(row!).queryByText('cr-user@example.com'),
    ).not.toBeInTheDocument();
    // DateDisplay renders the metrics-row createdAt; for a date this old it
    // shows an absolute format that always includes the source year.
    const expectedYear = new Date(metricsCreatedAt).getFullYear().toString();
    expect(
      within(row!).getByText(new RegExp(expectedYear)),
    ).toBeInTheDocument();
  });

  it('shows canonical name + version when the metrics display name only echoes the resource name', async () => {
    // When the BE could not resolve a user-facing name, the metrics row's
    // displayName just echoes the K8s resource name. In that case the row falls
    // back to canonical name + version from resolveAIMServiceDisplay. This
    // requires a resolvable cluster model so parsedAIMs is non-empty.
    mockFetchNamespaceMetrics.mockResolvedValue({
      data: [
        createMockResourceMetrics({
          id: 'aim-service-1',
          name: 'cluster-aim-service',
          displayName: 'cluster-aim-service',
          resourceType: 'AIMService',
        }),
      ],
      pagination: { page: 1, pageSize: 20, total: 1 },
    });
    const clusterAimService: AIMService = {
      id: 'aim-service-1',
      metadata: {
        name: 'cluster-aim-service',
        namespace: 'test-ns',
        uid: 'uid-cluster-1',
        labels: {},
        annotations: {},
        creationTimestamp: '2024-01-01T00:00:00Z',
        ownerReferences: [],
      },
      spec: {
        model: { name: 'cluster-model' },
        replicas: 1,
        runtimeConfigName: 'default',
      },
      status: {
        status: 'Running',
        resolvedModel: { name: 'cluster-model' },
      },
      statusValue: '',
      endpoints: {
        internal: 'http://cluster-aim-service.test-ns.svc.cluster.local',
      },
    };
    mockListInferenceDeployments.mockResolvedValue([clusterAimService]);
    // Resolve the cluster model so useInferenceModelsByName populates parsedAIMs.
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

    await act(async () => {
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      // The row shows canonical name + version, not the echoed resource name.
      expect(screen.getByText('test/model (1.0)')).toBeInTheDocument();
    });
    expect(screen.queryByText('cluster-aim-service')).not.toBeInTheDocument();
    const aimRow = screen
      .getAllByRole('row')
      .find((r) => r.textContent?.includes('test/model (1.0)'));
    expect(aimRow).toBeDefined();
    expect(within(aimRow!).getByText('test/model (1.0)')).toBeInTheDocument();
  });

  it('shows the custom model profile display name beneath the deployment name', async () => {
    const profileLabel = 'High speed';
    mockFetchNamespaceMetrics.mockResolvedValue({
      data: [
        createMockResourceMetrics({
          id: 'custom-aim-service-1',
          name: 'custom-aim-service-1',
          displayName: 'My Custom Model',
          resourceType: 'AIMService',
        }),
      ],
      pagination: { page: 1, pageSize: 20, total: 1 },
    });
    const customAimService: AIMService = {
      id: 'custom-aim-service-1',
      metadata: {
        name: 'custom-aim-service-1',
        namespace: 'test-ns',
        uid: 'uid-custom-1',
        labels: { [NAMESPACE_AIM_MODEL_LABEL]: 'true' },
        annotations: {},
        creationTimestamp: '2024-01-01T00:00:00Z',
        ownerReferences: [],
      },
      spec: {
        model: { name: 'custom-model-ref' },
        replicas: 1,
        runtimeConfigName: 'default',
      },
      status: {
        status: 'Running',
        resolvedModel: { name: 'custom-model-ref' },
      },
      statusValue: '',
      endpoints: {
        internal: 'http://custom-aim-service.test-ns.svc.cluster.local',
      },
    };
    mockListInferenceDeployments.mockResolvedValue([customAimService]);
    mockUseCustomProfileDeployments.mockReturnValue({
      profileByServiceId: new Map([
        [
          'custom-aim-service-1',
          {
            displayName: profileLabel,
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
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('My Custom Model')).toBeInTheDocument();
      expect(screen.getByText(profileLabel)).toBeInTheDocument();
    });
    expect(screen.queryByText('MI300X')).not.toBeInTheDocument();
  });

  it('shows the deployment max LoRA rank alongside the custom profile display name', async () => {
    // Custom-profile axes (profileSummaryFields in lib/app/custom-profiles.ts)
    // never carry maxLoraRank — only the deployment's own spec does — so this
    // proves the row still composes it in rather than losing it behind the
    // custom profile.
    const profileLabel = 'High speed';
    mockFetchNamespaceMetrics.mockResolvedValue({
      data: [
        createMockResourceMetrics({
          id: 'custom-aim-service-2',
          name: 'custom-aim-service-2',
          displayName: 'My Custom Model With Rank',
          resourceType: 'AIMService',
        }),
      ],
      pagination: { page: 1, pageSize: 20, total: 1 },
    });
    const customAimService: AIMService = {
      id: 'custom-aim-service-2',
      metadata: {
        name: 'custom-aim-service-2',
        namespace: 'test-ns',
        uid: 'uid-custom-2',
        labels: { [NAMESPACE_AIM_MODEL_LABEL]: 'true' },
        annotations: {},
        creationTimestamp: '2024-01-01T00:00:00Z',
        ownerReferences: [],
      },
      spec: {
        model: { name: 'custom-model-ref-2' },
        replicas: 1,
        runtimeConfigName: 'default',
        adapterRuntime: { maxRank: 64 },
      },
      status: {
        status: 'Running',
        resolvedModel: { name: 'custom-model-ref-2' },
      },
      statusValue: '',
      endpoints: {
        internal: 'http://custom-aim-service-2.test-ns.svc.cluster.local',
      },
    };
    mockListInferenceDeployments.mockResolvedValue([customAimService]);
    mockUseCustomProfileDeployments.mockReturnValue({
      profileByServiceId: new Map([
        [
          'custom-aim-service-2',
          {
            displayName: profileLabel,
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
      render(<NamespaceWorkloadsTable namespace="test-ns" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('My Custom Model With Rank')).toBeInTheDocument();
      expect(screen.getByText(profileLabel)).toBeInTheDocument();
    });
    expect(screen.getByText('profileSummary.maxRank:64')).toBeInTheDocument();
  });
});
