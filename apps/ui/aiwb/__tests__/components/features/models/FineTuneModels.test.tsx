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
import userEvent from '@testing-library/user-event';

import { mockModels } from '@/__mocks__/services/app/models.data';
import { mockWorkloads } from '@/__mocks__/services/app/workloads.data';
import {
  finetuneModel,
  getFinetunableModels,
  listAllProjectFineTunedModels,
} from '@/lib/app/models';
import { listAllWorkloads } from '@/lib/app/workloads';
import { listAllInferenceDeployments } from '@/lib/app/inference';

import { FinetunableModel, ModelFinetuneParams } from '@/types/models';
import FineTuneModels from '@/components/features/models/FineTuneModels';
import { SUBMITTER_ANNOTATION } from '@/types/artifacts';
import {
  AIM_MODEL_SOURCE_DESCRIPTION_ANNOTATION,
  AIM_MODEL_TRAINING_OUTPUT_ANNOTATION,
} from '@/types/aims';

import wrapper from '@/__tests__/ProviderWrapper';
import { Mock, vi } from 'vitest';

type MockFinetuneSubmission = {
  id: string;
  params: ModelFinetuneParams;
};

const { mockToastSuccess, mockWizardState } = vi.hoisted(() => ({
  mockToastSuccess: vi.fn(),
  mockWizardState: {
    submission: null as MockFinetuneSubmission | null,
  },
}));

// Assuming Workload type exists here

// Mock the API services
vi.mock('@/lib/app/models', async (importOriginal) => ({
  ...(await importOriginal()),
  finetuneModel: vi.fn(),
  deleteModel: vi.fn(),
  listAllProjectFineTunedModels: vi.fn(),
  getFinetunableModels: vi.fn(),
}));

vi.mock('@/lib/app/workloads', async (importOriginal) => ({
  ...(await importOriginal()),
  listAllWorkloads: vi.fn(),
}));

vi.mock('@/lib/app/inference', () => ({
  listAllInferenceDeployments: vi.fn().mockResolvedValue([]),
}));

// Mock useSystemToast for testing
vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  useSystemToast: () => ({
    toast: {
      success: mockToastSuccess,
      error: vi.fn(),
    },
  }),
}));

vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  return {
    ...actual,
    DateDisplay: ({ date }: { date: string }) => (
      <time dateTime={date}>{date}</time>
    ),
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

vi.mock(
  '@/components/features/models/FinetuneWizard',
  async (importOriginal) => {
    const original =
      await importOriginal<
        typeof import('@/components/features/models/FinetuneWizard')
      >();
    const OriginalFinetuneWizard = original.FinetuneWizard;
    return {
      ...original,
      FinetuneWizard: (props: Parameters<typeof OriginalFinetuneWizard>[0]) =>
        mockWizardState.submission ? (
          <button
            type="button"
            onClick={() => props.onConfirmAction(mockWizardState.submission!)}
          >
            Submit mock fine-tuning
          </button>
        ) : (
          <OriginalFinetuneWizard {...props} />
        ),
    };
  },
);

vi.mock('next/router', () => ({
  useRouter: vi.fn(),
}));

// Mock Tabler icons
vi.mock('@tabler/icons-react', async (importOriginal) => {
  const original = (await importOriginal()) ?? {};
  return {
    ...original,
    IconDotsVertical: ({ className }: any) => (
      <span className={className}>action-dot-icon</span>
    ),
    IconAffiliate: () => <span data-testid="affiliate-icon" />,
    IconCpu: () => <span data-testid="cpu-icon" />,
  };
});

describe('Fine-tune models', () => {
  const mockFinetunableModels: FinetunableModel[] = [
    {
      canonicalName: 'org/model-1',
      gpuCount: 0,
      compatibleAccelerators: [],
      compatibleAcceleratorNames: [],
      hfTokenRequired: false,
      trainingType: 'full',
      hyperparameters: {
        batchSize: null,
        epochs: 1,
        learningRate: 1.0,
        lora: null,
      },
    },
    {
      canonicalName: 'org/model-6',
      gpuCount: 0,
      compatibleAccelerators: [],
      compatibleAcceleratorNames: [],
      hfTokenRequired: false,
      trainingType: 'full',
      hyperparameters: {
        batchSize: null,
        epochs: 1,
        learningRate: 1.0,
        lora: null,
      },
    },
  ];

  beforeEach(() => {
    vi.resetAllMocks();
    mockWizardState.submission = null;
    (finetuneModel as Mock).mockResolvedValue({
      id: 'new-finetune-workload',
      name: 'new-model',
    });
    (listAllProjectFineTunedModels as Mock).mockResolvedValue(mockModels);
    (getFinetunableModels as Mock).mockResolvedValue(mockFinetunableModels);
    (listAllWorkloads as Mock).mockResolvedValue(mockWorkloads);
    (listAllInferenceDeployments as Mock).mockResolvedValue([]);
  });

  it('renders the fine-tuned models table and excludes deleted/unknown workloads from the query', async () => {
    await act(async () => {
      render(<FineTuneModels />, { wrapper });
    });

    // Wait for the models to load
    await waitFor(() => {
      expect(listAllProjectFineTunedModels).toHaveBeenCalled();
    });

    // Deleted and Unknown workloads should be excluded from the query
    expect(listAllWorkloads).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        statusFilter: expect.not.arrayContaining(['Deleted', 'Unknown']),
      }),
    );

    await waitFor(() => {
      expect(screen.getByText('model-1')).toBeInTheDocument();
      expect(screen.getByText('model-2')).toBeInTheDocument();
      expect(screen.getByText('model-3')).toBeInTheDocument();
    });
  });

  it('presents model identity and creation metadata in a compact row', async () => {
    const model = {
      ...mockModels[0],
      metadata: {
        ...mockModels[0].metadata,
        annotations: {
          [AIM_MODEL_SOURCE_DESCRIPTION_ANNOTATION]:
            'Trained for support requests',
          [SUBMITTER_ANNOTATION]: 'owner@example.com',
          [AIM_MODEL_TRAINING_OUTPUT_ANNOTATION]: 'merged',
        },
      },
    };
    (listAllProjectFineTunedModels as Mock).mockResolvedValue([model]);

    render(<FineTuneModels />, { wrapper });

    const displayName = await screen.findByText('model-1');
    const nameCell = displayName.closest('td');
    expect(nameCell).not.toBeNull();
    expect(displayName.parentElement).toHaveProperty('childElementCount', 3);
    const description = within(nameCell!).getByText(
      'Trained for support requests',
      { selector: 'span' },
    );
    expect(description).toHaveClass('truncate');
    expect(description.closest('[data-testid="mock-tooltip"]')).toHaveAttribute(
      'data-disabled',
      'true',
    );
    expect(within(nameCell!).getByTestId('cpu-icon')).toBeInTheDocument();
    expect(within(nameCell!).getByText('org/model-1')).toBeInTheDocument();
    expect(within(nameCell!).getByText('•')).toBeInTheDocument();
    expect(within(nameCell!).getByTestId('affiliate-icon')).toBeInTheDocument();
    expect(
      within(nameCell!).getByText('list.fineTuningTypes.merged'),
    ).toBeInTheDocument();

    const row = displayName.closest('tr');
    expect(within(row!).getByText('2026-01-01T00:00:00Z')).toBeInTheDocument();
    expect(within(row!).getByText('owner@example.com')).toBeInTheDocument();

    const headers = screen.getAllByRole('columnheader');
    expect(headers).toHaveLength(6);
    expect(headers[0]).toHaveClass('w-full', 'min-w-64', 'max-w-0');
    for (const header of headers.slice(1, 5)) {
      expect(header).toHaveClass('w-0', 'whitespace-nowrap');
    }
    expect(headers.map((header) => header.textContent)).not.toEqual(
      expect.arrayContaining([
        expect.stringContaining('canonicalName'),
        expect.stringContaining('output'),
      ]),
    );
  });

  it('enables the description tooltip only when the text is truncated', async () => {
    vi.spyOn(HTMLElement.prototype, 'scrollWidth', 'get').mockReturnValue(200);
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(100);
    const model = {
      ...mockModels[0],
      metadata: {
        ...mockModels[0].metadata,
        annotations: {
          [AIM_MODEL_SOURCE_DESCRIPTION_ANNOTATION]: 'A long model description',
        },
      },
    };
    (listAllProjectFineTunedModels as Mock).mockResolvedValue([model]);

    render(<FineTuneModels />, { wrapper });

    const description = await screen.findByText('A long model description', {
      selector: 'span',
    });
    const tooltip = description.closest('[data-testid="mock-tooltip"]');
    await waitFor(() =>
      expect(tooltip).toHaveAttribute('data-disabled', 'false'),
    );
  });

  it('falls back to workload creator and omits missing name metadata', async () => {
    const model = {
      ...mockModels[0],
      metadata: {
        ...mockModels[0].metadata,
        annotations: {
          [AIM_MODEL_TRAINING_OUTPUT_ANNOTATION]: 'unsupported',
        },
      },
      spec: {
        ...mockModels[0].spec,
        profiles: { overrides: { modelSources: [] } },
      },
    };
    (listAllProjectFineTunedModels as Mock).mockResolvedValue([model]);
    (listAllWorkloads as Mock).mockResolvedValue([
      {
        ...mockWorkloads[3],
        id: '1',
        createdBy: 'workload-owner@example.com',
        status: 'Complete',
      },
    ]);

    render(<FineTuneModels />, { wrapper });

    const displayName = await screen.findByText('model-1');
    expect(displayName.parentElement).toHaveProperty('childElementCount', 1);
    expect(
      within(displayName.closest('tr')!).getByText(
        'workload-owner@example.com',
      ),
    ).toBeInTheDocument();
  });

  it('filters models by search query', async () => {
    await act(async () => {
      render(<FineTuneModels />, { wrapper });
    });

    // Wait for the models to load
    await waitFor(() => {
      expect(listAllProjectFineTunedModels).toHaveBeenCalled();
    });

    const searchInput = screen.getByPlaceholderText(
      'customModels.list.filters.search.placeholder',
    );
    fireEvent.change(searchInput, { target: { value: 'model-1' } });

    // Wait for debounced search to trigger
    await waitFor(() => {
      expect(screen.queryByText('model-1')).toBeInTheDocument();
      expect(screen.queryByText('model-2')).not.toBeInTheDocument();
      expect(screen.queryByText('model-3')).not.toBeInTheDocument();
    });
  });

  it('clears filters', async () => {
    await act(async () => {
      render(<FineTuneModels />, { wrapper });
    });

    // Wait for the models to load
    await waitFor(() => {
      expect(listAllProjectFineTunedModels).toHaveBeenCalled();
    });

    // All models should be visible since type filtering is removed
    expect(screen.queryByText('model-1')).toBeInTheDocument();
    expect(screen.queryByText('model-2')).toBeInTheDocument();
    expect(screen.queryByText('model-3')).toBeInTheDocument();

    // Click clear filters button
    const clearButton = screen.getByText('actions.clearFilters.title');
    await act(async () => {
      fireEvent.click(clearButton);
    });

    // After clearing filters, all models should be visible again including model-3
    await waitFor(() => {
      expect(screen.queryByText('model-3')).toBeInTheDocument();
      expect(screen.queryByText('model-1')).toBeInTheDocument();
      expect(screen.queryByText('model-2')).toBeInTheDocument();
    });
  });

  it('opens the fine-tune wizard', async () => {
    await act(async () => {
      render(<FineTuneModels />, { wrapper });
    });

    await waitFor(() => {
      expect(listAllProjectFineTunedModels).toHaveBeenCalled();
    });

    const createNewButton = screen.getByText(
      'customModels.list.actions.finetune.title',
    );
    fireEvent.click(createNewButton);

    await waitFor(() => {
      expect(getFinetunableModels).toHaveBeenCalled();
    });
  });

  it('links a full fine-tuning success toast to fine-tuned models', async () => {
    const user = userEvent.setup();
    mockWizardState.submission = {
      id: 'model-id',
      params: {
        displayName: 'fine-tuned-model',
        datasetIds: ['dataset-1'],
      },
    };
    render(<FineTuneModels />, { wrapper });

    await user.click(
      await screen.findByText('customModels.list.actions.finetune.title'),
    );
    await user.click(
      screen.getByRole('button', { name: 'Submit mock fine-tuning' }),
    );

    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalled());
    expect(mockToastSuccess.mock.calls[0][0].props).toMatchObject({
      href: '/project1/fine-tuning/models',
      linkLabel: 'finetuneWizard.notifications.viewModels',
    });
  });

  it('links a LoRA fine-tuning success toast to LoRAs', async () => {
    const user = userEvent.setup();
    mockWizardState.submission = {
      id: 'model-id',
      params: {
        displayName: 'fine-tuned-lora',
        datasetIds: ['dataset-1'],
        output: 'adapter',
      },
    };
    render(<FineTuneModels />, { wrapper });

    await user.click(
      await screen.findByText('customModels.list.actions.finetune.title'),
    );
    await user.click(
      screen.getByRole('button', { name: 'Submit mock fine-tuning' }),
    );

    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalled());
    expect(mockToastSuccess.mock.calls[0][0].props).toMatchObject({
      href: '/project1/fine-tuning/loras',
      linkLabel: 'finetuneWizard.notifications.viewLoras',
    });
  });

  it('refreshes the models list', async () => {
    await act(async () => {
      render(<FineTuneModels />, { wrapper });
    });

    // Wait for initial models load
    await waitFor(() => {
      expect(listAllProjectFineTunedModels).toHaveBeenCalledTimes(1);
    });

    const refreshButton = screen.getByRole('button', { name: /refresh/i });

    fireEvent.click(refreshButton);

    await waitFor(() => {
      // listAllProjectFineTunedModels should be called again on refresh
      expect(listAllProjectFineTunedModels).toHaveBeenCalledTimes(2);
    });
  });

  it('allows deleting a model', async () => {
    await act(async () => {
      render(<FineTuneModels />, { wrapper });
    });

    await waitFor(() => {
      expect(listAllProjectFineTunedModels).toHaveBeenCalled();
      expect(screen.getByText('model-1')).toBeInTheDocument();
    });

    const actionButtons = await screen.findAllByText('action-dot-icon');
    await act(async () => {
      fireEvent.click(actionButtons[0]);
    });

    const deleteOption = await screen.findByTestId('delete');
    expect(deleteOption).toBeInTheDocument();
  });

  it('shows AIM deployment count in workloads column', async () => {
    (listAllInferenceDeployments as Mock).mockResolvedValue([
      {
        id: 'aim-svc-1',
        metadata: {
          name: 'svc-1',
          creationTimestamp: '2026-01-01T00:00:00Z',
          annotations: {},
        },
        spec: { model: { name: 'wb-finetune-cr-1' } },
        status: {
          status: 'Running',
        },
      },
      {
        id: 'aim-svc-2',
        metadata: {
          name: 'svc-2',
          creationTimestamp: '2026-01-01T00:00:00Z',
          annotations: {},
        },
        spec: { model: { name: 'wb-finetune-cr-1' } },
        status: {
          status: 'Running',
        },
      },
    ]);

    await act(async () => {
      render(<FineTuneModels />, { wrapper });
    });

    await waitFor(() => {
      expect(listAllInferenceDeployments).toHaveBeenCalled();
    });

    // model-1's resourceName is 'wb-finetune-cr-1', matching both AIM services
    const model1Row = (await screen.findByText('model-1')).closest('tr');
    expect(model1Row).not.toBeNull();
    expect(within(model1Row!).getByText('2')).toBeInTheDocument();
  });

  it('renders active model-output rows with the user-chosen name and creation metadata', async () => {
    await act(async () => {
      render(<FineTuneModels />, { wrapper });
    });

    await waitFor(() => {
      expect(listAllProjectFineTunedModels).toHaveBeenCalled();
      expect(listAllWorkloads).toHaveBeenCalled();
    });

    // workload-14 is a Running FINE_TUNING workload whose internal k8s name is
    // 'Merged Fine-tuning Workload' and whose user-chosen displayName is
    // 'Merged Fine-tuning Model'. The Name column must show displayName.
    const displayNameCell = await screen.findByText('Merged Fine-tuning Model');
    expect(displayNameCell).toBeInTheDocument();

    const row = displayNameCell.closest('tr');
    expect(row).not.toBeNull();

    // Resource (k8s) name must NOT leak into the Name column.
    expect(
      within(row!).queryByText('Merged Fine-tuning Workload'),
    ).not.toBeInTheDocument();

    expect(within(row!).getAllByText('Merged Fine-tuning Model')).toHaveLength(
      1,
    );
    expect(within(row!).getByText('2023-01-14T00:00:00Z')).toBeInTheDocument();
    expect(within(row!).getByText('test-user')).toBeInTheDocument();
  });

  it('shows active model outputs and omits LoRA adapter jobs', async () => {
    await act(async () => {
      render(<FineTuneModels />, { wrapper });
    });

    const fullRow = (await screen.findByText('Model fine-tuning Job')).closest(
      'tr',
    );
    const mergedRow = (
      await screen.findByText('Merged Fine-tuning Model')
    ).closest('tr');

    expect(
      within(fullRow!).getByText('list.fineTuningTypes.full'),
    ).toBeInTheDocument();
    expect(
      within(mergedRow!).getByText('list.fineTuningTypes.merged'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Fine-tuning Model with Dataset'),
    ).not.toBeInTheDocument();
  });

  it('shows completed model types and leaves unknown values unclassified', async () => {
    await act(async () => {
      render(<FineTuneModels />, { wrapper });
    });

    const fullRow = (await screen.findByText('model-1')).closest('tr');
    const mergedRow = (await screen.findByText('model-2')).closest('tr');
    const adapterRow = (await screen.findByText('model-3')).closest('tr');
    const legacyRow = (await screen.findByText('model-4')).closest('tr');
    const unknownRow = (await screen.findByText('model-5')).closest('tr');

    expect(
      within(fullRow!).getByText('list.fineTuningTypes.full'),
    ).toBeInTheDocument();
    expect(
      within(mergedRow!).getByText('list.fineTuningTypes.merged'),
    ).toBeInTheDocument();
    expect(
      within(adapterRow!).getByText('list.fineTuningTypes.lora'),
    ).toBeInTheDocument();
    expect(
      within(legacyRow!).getByText('list.fineTuningTypes.full'),
    ).toBeInTheDocument();
    expect(
      within(unknownRow!).queryByText(/list\.fineTuningTypes\./),
    ).not.toBeInTheDocument();
  });

  it('does not show deploy action when model status is not complete', async () => {
    await act(async () => {
      render(<FineTuneModels />, { wrapper });
    });

    // Wait for initial models load
    await waitFor(() => {
      expect(listAllProjectFineTunedModels).toHaveBeenCalledTimes(1);
    });

    // Find the row for model-2 which has Pending status
    const model2Row = await screen.findByText('model-2');
    expect(model2Row).toBeInTheDocument();

    // Find the table row containing model-2
    const tableRow = model2Row.closest('tr');
    expect(tableRow).not.toBeNull();

    // Find the context menu button within that specific row
    const actionButton = tableRow
      ? await within(tableRow).findByText('action-dot-icon')
      : null;
    expect(actionButton).not.toBeNull();

    // Click the action button for model-2
    await act(async () => {
      if (actionButton) fireEvent.click(actionButton);
    });

    // Check that the Deploy option is not present since model-2 has Pending status
    const deployOption = screen.queryByTestId('deploy');
    expect(deployOption).not.toBeInTheDocument();

    // Also test with model-4 which has Failed status
    const model4Row = await screen.findByText('model-4');
    expect(model4Row).toBeInTheDocument();

    const tableRow4 = model4Row.closest('tr');
    expect(tableRow4).not.toBeNull();

    const actionButton4 = tableRow4
      ? await within(tableRow4).findByText('action-dot-icon')
      : null;
    expect(actionButton4).not.toBeNull();

    // Click the action button for model-4
    await act(async () => {
      if (actionButton4) fireEvent.click(actionButton4);
    });

    // Check that the Deploy option is not present for model-4 with Failed status
    const deployOption4 = screen.queryByTestId('deploy');
    expect(deployOption4).not.toBeInTheDocument();
  });

  it('shows fine-tune action for completed custom model rows', async () => {
    await act(async () => {
      render(<FineTuneModels />, { wrapper });
    });

    await waitFor(() => {
      expect(listAllProjectFineTunedModels).toHaveBeenCalled();
    });

    const model1Row = (await screen.findByText('model-1')).closest('tr');
    expect(model1Row).not.toBeNull();

    const actionButton = model1Row
      ? await within(model1Row).findByText('action-dot-icon')
      : null;
    expect(actionButton).not.toBeNull();

    await act(async () => {
      if (actionButton) fireEvent.click(actionButton);
    });

    expect(await screen.findByTestId('finetune')).toBeInTheDocument();
  });

  it('opens fine-tune wizard from completed model action with locked base model', async () => {
    await act(async () => {
      render(<FineTuneModels />, { wrapper });
    });

    await waitFor(() => {
      expect(listAllProjectFineTunedModels).toHaveBeenCalled();
    });

    const model1Row = (await screen.findByText('model-1')).closest('tr');
    expect(model1Row).not.toBeNull();

    const actionButton = model1Row
      ? await within(model1Row).findByText('action-dot-icon')
      : null;
    expect(actionButton).not.toBeNull();

    await act(async () => {
      if (actionButton) fireEvent.click(actionButton);
    });

    fireEvent.click(await screen.findByTestId('finetune'));

    const baseModelSelectButton = screen.getByRole('button', {
      name: /finetuneWizard\.fields\.baseModel\.label/i,
    });

    expect(baseModelSelectButton).toHaveTextContent('model-1');
    expect(baseModelSelectButton).toHaveAttribute('data-disabled', 'true');
    expect(
      screen.queryByRole('button', {
        name: /huggingFaceTokenDrawer\.fields\.selectToken\.label/i,
      }),
    ).not.toBeInTheDocument();
  });
});
