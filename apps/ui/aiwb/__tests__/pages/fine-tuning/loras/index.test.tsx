// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  type Mock,
  vi,
} from 'vitest';

import wrapper from '@/__tests__/ProviderWrapper';
import {
  deleteAdapterArtifact,
  getAdapterArtifact,
  listAllAdapterArtifacts,
  waitForAdapterArtifactRemoval,
} from '@/lib/app/artifacts';
import { listInferenceDeployments } from '@/lib/app/inference';
import { cancelFineTuningJob, getFinetunableModels } from '@/lib/app/models';
import { listAllWorkloads } from '@/lib/app/workloads';
import LorasPage from '@/pages/[project]/fine-tuning/loras';
import { AIM_MODEL_TRAINING_OUTPUT_ANNOTATION } from '@/types/aims';

const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      key === 'list.compatibleWithMoreCount' &&
      typeof options?.count === 'number'
        ? `+${options.count} more`
        : key,
  }),
  Trans: ({ children }: { children?: React.ReactNode }) => children ?? null,
}));

vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  return {
    ...actual,
    Tooltip: ({
      children,
      content,
      isDisabled,
    }: {
      children: React.ReactNode;
      content?: React.ReactNode;
      isDisabled?: boolean;
    }) => (
      <div data-disabled={isDisabled} data-testid="mock-tooltip">
        <div data-testid="tooltip-trigger">{children}</div>
        <div data-testid="tooltip-content">{content}</div>
      </div>
    ),
  };
});

vi.mock('@amdenterpriseai/hooks', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/hooks')>();
  return {
    ...actual,
    useSystemToast: () => ({
      toast: {
        success: mockToastSuccess,
        error: mockToastError,
      },
    }),
  };
});

vi.mock('@/lib/app/artifacts', () => ({
  listAllAdapterArtifacts: vi.fn(),
  getAdapterArtifact: vi.fn(),
  deleteAdapterArtifact: vi.fn(),
  waitForAdapterArtifactRemoval: vi.fn(),
}));

vi.mock('@/lib/app/models', () => ({
  cancelFineTuningJob: vi.fn(),
  finetuneModel: vi.fn(),
  getFinetunableModels: vi.fn(),
}));

vi.mock('@/lib/app/inference', () => ({
  attachAdapterToDeployment: vi.fn(),
  listInferenceDeployments: vi.fn(),
}));

/** Wraps deployments in the single-page envelope `listInferenceDeployments` returns. */
const pageOfDeployments = (data: unknown[]) => ({
  data,
  pagination: { total: data.length, page: 1, pageSize: 100 },
});

vi.mock('@/lib/app/workloads', () => ({
  listAllWorkloads: vi.fn(),
}));

vi.mock('@/components/features/models/FinetuneWizard', () => ({
  FinetuneWizard: () => <div data-testid="finetune-wizard" />,
}));

// The real modal pulls in Select/react-aria and its own catalog query; that's
// exercised by AttachLoraModal's own tests. Here we only need proof the page
// wires the selected adapter through to it.
vi.mock('@/components/features/loras/AttachLoraModal', () => ({
  AttachLoraModal: ({
    adapter,
    isOpen,
  }: {
    adapter?: { displayName: string };
    isOpen: boolean;
  }) =>
    isOpen ? (
      <div data-testid="attach-lora-modal">{adapter?.displayName}</div>
    ) : null,
}));

const adapter = {
  id: 'adapter-uid',
  name: 'adapter-1',
  displayName: 'Support LoRA',
  description: 'Customer support adapter',
  modelId: 'example-org/support-lora',
  compatibleWith: ['example-org/base-model'],
  rank: 16,
  status: 'Ready' as const,
  readiness: 'NotReady' as const,
  uri: 's3://example-bucket/project/adapters/adapter-1/',
  createdAt: '2026-08-11T12:31:31Z',
  createdBy: 'user@example.com',
};

const adapterDetails: Awaited<ReturnType<typeof getAdapterArtifact>> = {
  storage: {
    readiness: 'Ready',
    uri: adapter.uri,
  },
  artifact: {
    metadata: {
      name: adapter.name,
      annotations: {
        'aiwb.apps.eai.amd.com/display-name': adapter.displayName,
      },
    },
    spec: {
      type: 'adapter',
      modelId: adapter.modelId,
      compatibleWith: adapter.compatibleWith,
      rank: adapter.rank,
    },
    status: {
      status: 'Ready',
      conditions: [],
    },
  },
};

const otherAdapter = {
  ...adapter,
  id: 'adapter-uid-2',
  name: 'adapter-2',
  displayName: 'Legal LoRA',
  description: 'Contract review adapter',
  compatibleWith: ['example-org/legal-model'],
};

const adapterWithoutDescription = {
  ...adapter,
  description: '   ',
};

const readyAdapter = { ...adapter, readiness: 'Ready' as const };

const multiBaseModelAdapter = {
  ...adapter,
  compatibleWith: [
    'example-org/base-model',
    'example-org/second-model',
    'example-org/third-model',
  ],
};

const loraWorkload = {
  id: 'workload-1',
  name: 'internal-lora-job',
  displayName: 'Customer support training',
  createdBy: 'user@example.com',
  updatedBy: null,
  namespace: 'project1',
  endpoints: {},
  type: 'FINE_TUNING' as const,
  createdAt: '2026-08-12T12:31:31Z',
  updatedAt: '2026-08-12T12:32:31Z',
  status: 'Running' as const,
  annotations: { [AIM_MODEL_TRAINING_OUTPUT_ANNOTATION]: 'lora' },
};

describe('LoRAs page', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    (listAllAdapterArtifacts as Mock).mockResolvedValue([adapter]);
    (listAllWorkloads as Mock).mockResolvedValue([]);
    (getAdapterArtifact as Mock).mockResolvedValue(adapterDetails);
    (deleteAdapterArtifact as Mock).mockResolvedValue(undefined);
    (waitForAdapterArtifactRemoval as Mock).mockResolvedValue(undefined);
    (cancelFineTuningJob as Mock).mockResolvedValue(undefined);
    (getFinetunableModels as Mock).mockResolvedValue([]);
    (listInferenceDeployments as Mock).mockResolvedValue(pageOfDeployments([]));
  });

  it('lists adapter compatibility and readiness information', async () => {
    render(<LorasPage />, { wrapper });

    const displayName = await screen.findByText('Support LoRA');
    const nameCell = displayName.closest('td');
    const descriptionTrigger = screen
      .getAllByTestId('tooltip-trigger')
      .find((trigger) =>
        within(trigger).queryByText('Customer support adapter'),
      );
    const compactCells = Array.from(
      nameCell?.parentElement?.querySelectorAll('td') ?? [],
    ).slice(1, 4);

    expect(nameCell).toHaveClass('w-full', 'min-w-64', 'max-w-0');
    expect(compactCells).toHaveLength(3);
    for (const cell of compactCells) {
      expect(cell).toHaveClass('w-0', 'whitespace-nowrap');
    }
    expect(displayName.parentElement).toHaveProperty('childElementCount', 3);
    expect(
      within(descriptionTrigger!).getByText('Customer support adapter'),
    ).toHaveClass('block', 'w-full', 'truncate', 'text-xs', 'text-muted');
    expect(
      within(descriptionTrigger!.parentElement!).getByTestId('tooltip-content'),
    ).toHaveTextContent('Customer support adapter');
    expect(descriptionTrigger!.parentElement).toHaveAttribute(
      'data-disabled',
      'true',
    );
    expect(screen.getByText('example-org/base-model')).toBeInTheDocument();
    expect(screen.getByText('•')).toBeInTheDocument();
    expect(screen.getByText('16')).toBeInTheDocument();
    expect(screen.getByText('status.Pending')).toBeInTheDocument();
  });

  it('enables the description tooltip only when the text is truncated', async () => {
    vi.spyOn(HTMLElement.prototype, 'scrollWidth', 'get').mockReturnValue(200);
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(100);
    render(<LorasPage />, { wrapper });

    const description = await screen.findByText('Customer support adapter', {
      selector: 'span',
    });
    const tooltip = description.closest('[data-testid="mock-tooltip"]');

    await waitFor(() => {
      expect(tooltip).toHaveAttribute('data-disabled', 'false');
    });
  });

  it('omits the description line when the description is empty', async () => {
    (listAllAdapterArtifacts as Mock).mockResolvedValue([
      adapterWithoutDescription,
    ]);
    render(<LorasPage />, { wrapper });

    const displayName = await screen.findByText('Support LoRA');
    expect(displayName.parentElement).toHaveTextContent(
      'Support LoRAexample-org/base-model•16',
    );
    expect(displayName.parentElement).toHaveProperty('childElementCount', 2);
  });

  it('truncates additional base models behind a more indicator', async () => {
    (listAllAdapterArtifacts as Mock).mockResolvedValue([
      multiBaseModelAdapter,
    ]);
    render(<LorasPage />, { wrapper });

    expect(
      await screen.findByText('example-org/base-model'),
    ).toBeInTheDocument();
    expect(screen.getByText('•')).toBeInTheDocument();
    const baseModelsTrigger = screen
      .getAllByTestId('tooltip-trigger')
      .find((trigger) => within(trigger).queryByText('+2 more'));
    expect(within(baseModelsTrigger!).getByText('+2 more')).toBeInTheDocument();
    const tooltipContent = within(
      baseModelsTrigger!.parentElement!,
    ).getByTestId('tooltip-content');
    expect(
      within(tooltipContent).getByText('example-org/second-model'),
    ).toBeInTheDocument();
    expect(
      within(tooltipContent).getByText('example-org/third-model'),
    ).toBeInTheDocument();
  });

  it('requests all adapters for the active project', async () => {
    render(<LorasPage />, { wrapper });

    await waitFor(() => {
      expect(listAllAdapterArtifacts).toHaveBeenCalledWith('project1');
    });
  });

  it('surfaces an error toast when the initial adapter load fails', async () => {
    (listAllAdapterArtifacts as Mock).mockRejectedValue(
      new Error('network unreachable'),
    );
    render(<LorasPage />, { wrapper });

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        'notifications.refresh.adaptersError',
      );
    });
  });

  it('surfaces an error toast when the workloads load fails', async () => {
    (listAllWorkloads as Mock).mockRejectedValue(
      new Error('network unreachable'),
    );
    render(<LorasPage />, { wrapper });

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        'notifications.refresh.workloadsError',
      );
    });
  });

  it('shows an inline load-error alert without hiding the loaded rows', async () => {
    (listAllWorkloads as Mock).mockRejectedValue(
      new Error('network unreachable'),
    );
    render(<LorasPage />, { wrapper });

    expect(
      await screen.findByText('notifications.refresh.loadErrorTitle'),
    ).toBeInTheDocument();
  });

  it('counts every deployment that references an adapter, regardless of status', async () => {
    // A Pending/Failed/Stopped deployment still blocks backend deletion, so
    // the displayed count (and the delete guard) must include it too — not
    // just Running deployments.
    (listInferenceDeployments as Mock).mockResolvedValue(
      pageOfDeployments([
        {
          statusValue: 'Running',
          spec: { adapters: [{ name: adapter.name }] },
        },
        {
          status: { status: 'Running' },
          spec: { adapters: [{ name: adapter.name }] },
        },
        {
          statusValue: 'Failed',
          spec: { adapters: [{ name: adapter.name }] },
        },
      ]),
    );
    render(<LorasPage />, { wrapper });

    const row = (await screen.findByText('Support LoRA')).closest('tr');
    await waitFor(() => {
      expect(row!.querySelectorAll('td')[2]).toHaveTextContent('3');
    });
  });

  it('shows an mdash when an adapter or fine-tuning job is not deployed', async () => {
    (listAllWorkloads as Mock).mockResolvedValue([loraWorkload]);
    render(<LorasPage />, { wrapper });

    const adapterRow = (await screen.findByText('Support LoRA')).closest('tr');
    const workloadRow = screen
      .getByText('Customer support training')
      .closest('tr');
    expect(adapterRow!.querySelectorAll('td')[2]).toHaveTextContent('—');
    expect(workloadRow!.querySelectorAll('td')[2]).toHaveTextContent('—');
  });

  it('lists active LoRA fine-tuning workloads with their status', async () => {
    (listAllWorkloads as Mock).mockResolvedValue([
      loraWorkload,
      {
        ...loraWorkload,
        id: 'workload-2',
        displayName: 'Merged model training',
        annotations: {
          [AIM_MODEL_TRAINING_OUTPUT_ANNOTATION]: 'merged',
        },
      },
    ]);
    render(<LorasPage />, { wrapper });

    expect(
      await screen.findByText('Customer support training'),
    ).toBeInTheDocument();
    expect(screen.getByText('status.Running')).toBeInTheDocument();
    expect(screen.queryByText('Merged model training')).not.toBeInTheDocument();
    expect(listAllWorkloads).toHaveBeenCalledWith('project1', {
      workloadType: ['FINE_TUNING'],
      statusFilter: ['Pending', 'Starting', 'Running', 'Failed'],
    });
  });

  it('lists failed LoRA fine-tuning jobs with their status', async () => {
    (listAllAdapterArtifacts as Mock).mockResolvedValue([]);
    (listAllWorkloads as Mock).mockResolvedValue([
      {
        ...loraWorkload,
        id: 'workload-failed',
        displayName: 'Failed training run',
        status: 'Failed' as const,
      },
    ]);
    render(<LorasPage />, { wrapper });

    expect(await screen.findByText('Failed training run')).toBeInTheDocument();
    expect(screen.getByText('status.Failed')).toBeInTheDocument();
  });

  it('offers a delete action for a running workload', async () => {
    (listAllAdapterArtifacts as Mock).mockResolvedValue([]);
    (listAllWorkloads as Mock).mockResolvedValue([loraWorkload]);
    render(<LorasPage />, { wrapper });

    const row = (await screen.findByText('Customer support training')).closest(
      'tr',
    );
    expect(row).not.toBeNull();
    expect(
      within(row!).getByLabelText('list.actions.label'),
    ).toBeInTheDocument();
  });

  it('cancels a running LoRA fine-tuning job after confirmation', async () => {
    (listAllAdapterArtifacts as Mock).mockResolvedValue([]);
    (listAllWorkloads as Mock).mockResolvedValue([loraWorkload]);
    render(<LorasPage />, { wrapper });

    const row = (await screen.findByText('Customer support training')).closest(
      'tr',
    );
    fireEvent.click(within(row!).getByLabelText('list.actions.label'));
    fireEvent.click(await screen.findByText('actions.delete.label'));
    await act(async () => {
      fireEvent.click(await screen.findByTestId('confirm-button'));
    });

    await waitFor(() => {
      expect(cancelFineTuningJob).toHaveBeenCalledWith(
        'workload-1',
        'project1',
      );
    });
    expect(mockToastSuccess).toHaveBeenCalledWith(
      'actions.delete.workloadNotification.success',
    );
  });

  it.each([
    ['Support', 'name'],
    ['Customer support', 'description'],
    ['example-org/base-model', 'base model'],
  ])('searches adapters by %s in the %s', async (query) => {
    (listAllAdapterArtifacts as Mock).mockResolvedValue([
      adapter,
      otherAdapter,
    ]);
    render(<LorasPage />, { wrapper });

    await screen.findByText('Legal LoRA');
    fireEvent.change(
      screen.getByPlaceholderText('list.filters.search.placeholder'),
      { target: { value: query } },
    );

    await waitFor(() => {
      expect(screen.getByText('Support LoRA')).toBeInTheDocument();
      expect(screen.queryByText('Legal LoRA')).not.toBeInTheDocument();
    });
  });

  it('filters adapters by compatible base model', async () => {
    (listAllAdapterArtifacts as Mock).mockResolvedValue([
      adapter,
      otherAdapter,
    ]);
    render(<LorasPage />, { wrapper });

    await screen.findByText('Legal LoRA');
    fireEvent.click(
      screen.getByRole('button', {
        name: 'list.filters.baseModels.label',
      }),
    );
    fireEvent.click(
      await screen.findByRole('option', {
        name: 'example-org/base-model',
      }),
    );

    await waitFor(() => {
      expect(screen.getByText('Support LoRA')).toBeInTheDocument();
      expect(screen.queryByText('Legal LoRA')).not.toBeInTheDocument();
    });
  });

  it('opens fine-tuning from the toolbar without adding a row action', async () => {
    render(<LorasPage />, { wrapper });

    await screen.findByText('Support LoRA');
    fireEvent.click(screen.getByTestId('loras-finetune'));

    expect(await screen.findByTestId('finetune-wizard')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('list.actions.label'));

    expect(await screen.findByTestId('delete')).toBeInTheDocument();
    expect(screen.queryByTestId('finetune')).not.toBeInTheDocument();
  });

  it('opens adapter details from the row actions', async () => {
    render(<LorasPage />, { wrapper });

    await screen.findByText('Support LoRA');
    fireEvent.click(screen.getByLabelText('list.actions.label'));
    fireEvent.click(await screen.findByText('actions.details'));

    expect(
      await screen.findByText('example-org/support-lora'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('lora-details-modal')).toBeInTheDocument();
    expect(getAdapterArtifact).toHaveBeenCalledWith('project1', 'adapter-1');
  });
  it('opens the attach modal for the selected Ready adapter from the row actions', async () => {
    (listAllAdapterArtifacts as Mock).mockResolvedValue([readyAdapter]);
    render(<LorasPage />, { wrapper });

    const row = (await screen.findByText('Support LoRA')).closest('tr');
    fireEvent.click(within(row!).getByLabelText('list.actions.label'));
    fireEvent.click(await screen.findByText('actions.attach.label'));

    expect(await screen.findByTestId('attach-lora-modal')).toHaveTextContent(
      'Support LoRA',
    );
  });
  it('disables deletion for an adapter used by a deployment', async () => {
    (listInferenceDeployments as Mock).mockResolvedValue(
      pageOfDeployments([
        {
          statusValue: 'Running',
          spec: { adapters: [{ name: adapter.name }] },
        },
      ]),
    );
    render(<LorasPage />, { wrapper });

    const row = (await screen.findByText('Support LoRA')).closest('tr');
    await waitFor(() => {
      expect(row!.querySelectorAll('td')[2]).toHaveTextContent('1');
    });
    fireEvent.click(within(row!).getByLabelText('list.actions.label'));

    expect(await screen.findByTestId('delete')).toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });

  it('fails closed and keeps deletion disabled when deployment usage cannot be loaded', async () => {
    (listInferenceDeployments as Mock).mockRejectedValue(
      new Error('network unreachable'),
    );
    render(<LorasPage />, { wrapper });

    const row = (await screen.findByText('Support LoRA')).closest('tr');
    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        'notifications.refresh.deploymentsError',
      );
    });
    fireEvent.click(within(row!).getByLabelText('list.actions.label'));

    expect(await screen.findByTestId('delete')).toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });
  it('keeps deletion disabled while deployment usage is being refetched', async () => {
    (listInferenceDeployments as Mock)
      .mockResolvedValueOnce(pageOfDeployments([]))
      .mockImplementationOnce(() => new Promise(() => {}));
    // The table caches row cells per row object, so the adapter refetch has to
    // return changed data for the row — and with it the delete action — to be
    // re-rendered while the deployment refetch is still in flight.
    (listAllAdapterArtifacts as Mock)
      .mockResolvedValueOnce([adapter])
      .mockResolvedValueOnce([{ ...adapter, description: 'Updated adapter' }]);
    render(<LorasPage />, { wrapper });

    const row = (await screen.findByText('Support LoRA')).closest('tr');
    const refreshButton = screen.getByRole('button', {
      name: 'actions.refresh.title',
    });
    await waitFor(() => {
      expect(refreshButton).not.toBeDisabled();
    });
    // A refetch in flight means the usage count on screen is stale rather than
    // zero, so deletion has to stay closed until the new count lands.
    fireEvent.click(refreshButton);
    await screen.findAllByText('Updated adapter');
    fireEvent.click(within(row!).getByLabelText('list.actions.label'));

    expect(await screen.findByTestId('delete')).toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });

  it('deletes an adapter after confirmation', async () => {
    render(<LorasPage />, { wrapper });

    await screen.findByText('Support LoRA');
    fireEvent.click(screen.getByLabelText('list.actions.label'));
    fireEvent.click(await screen.findByText('actions.delete.label'));
    await act(async () => {
      fireEvent.click(await screen.findByTestId('confirm-button'));
    });

    await waitFor(() => {
      expect(deleteAdapterArtifact).toHaveBeenCalledWith(
        'project1',
        'adapter-1',
      );
    });
    expect(mockToastSuccess).toHaveBeenCalledWith(
      'actions.delete.notification.success',
    );
  });

  it('confirms removal before refetching adapters after a delete', async () => {
    let resolveRemoval: () => void = () => {};
    (waitForAdapterArtifactRemoval as Mock).mockReturnValue(
      new Promise<void>((resolve) => {
        resolveRemoval = resolve;
      }),
    );
    render(<LorasPage />, { wrapper });

    await screen.findByText('Support LoRA');
    fireEvent.click(screen.getByLabelText('list.actions.label'));
    fireEvent.click(await screen.findByText('actions.delete.label'));
    await act(async () => {
      fireEvent.click(await screen.findByTestId('confirm-button'));
    });

    await waitFor(() => {
      expect(waitForAdapterArtifactRemoval).toHaveBeenCalledWith(
        'project1',
        'adapter-1',
      );
    });
    expect(listAllAdapterArtifacts).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveRemoval();
    });

    await waitFor(() => {
      expect(listAllAdapterArtifacts).toHaveBeenCalledTimes(2);
    });
  });

  it('refetches adapters when an active LoRA fine-tuning job drops out of the active list', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    (listAllWorkloads as Mock).mockResolvedValue([loraWorkload]);

    render(
      <QueryClientProvider client={queryClient}>
        <LorasPage />
      </QueryClientProvider>,
    );

    await screen.findByText('Customer support training');
    expect(listAllAdapterArtifacts).toHaveBeenCalledTimes(1);

    // Simulate the workload transitioning out of the active-job list, as
    // happens on the query's own 30s refetchInterval once a job completes
    // or fails.
    (listAllWorkloads as Mock).mockResolvedValue([]);
    await act(async () => {
      await queryClient.refetchQueries({
        queryKey: ['project', 'project1', 'workloads', 'lora-fine-tuning-jobs'],
      });
    });

    await waitFor(() => {
      expect(listAllAdapterArtifacts).toHaveBeenCalledTimes(2);
    });
  });
});
