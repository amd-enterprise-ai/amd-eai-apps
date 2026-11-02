// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import wrapper from '@/__tests__/ProviderWrapper';
import { FinetuneWizard } from '@/components/features/models/FinetuneWizard';
import {
  MAX_DESCRIPTION_LENGTH,
  MAX_DISPLAY_NAME_LENGTH,
} from '@/components/features/models/FinetuneWizard/types';
import { getAimClusterProfiles } from '@/lib/app/aims';
import { listAllAdapterArtifacts } from '@/lib/app/artifacts';
import { getAllDatasets } from '@/lib/app/datasets';
import { listProjectFineTunedModels } from '@/lib/app/models';
import { fetchProjectSecrets } from '@/lib/app/secrets';
import { listAllWorkloads } from '@/lib/app/workloads';
import type { FinetunableModel, Model } from '@/types/models';

const { fetchQueryMock } = vi.hoisted(() => ({
  fetchQueryMock: vi.fn(),
}));

vi.mock('@tanstack/react-query', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/react-query')>()),
  useQueryClient: () => ({ fetchQuery: fetchQueryMock }),
}));

vi.mock('next-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/contexts/ProjectContext', () => ({
  useProject: () => ({ activeProject: 'project-1' }),
}));

vi.mock('@/lib/app/datasets', () => ({
  getAllDatasets: vi.fn(),
}));

vi.mock('@/lib/app/aims', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/app/aims')>()),
  getAimClusterProfiles: vi.fn(),
}));

vi.mock('@/lib/app/artifacts', () => ({
  listAllAdapterArtifacts: vi.fn(),
}));

vi.mock('@/lib/app/models', () => ({
  listProjectFineTunedModels: vi.fn(),
}));

vi.mock('@/lib/app/secrets', () => ({
  fetchProjectSecrets: vi.fn(),
}));

vi.mock('@/lib/app/workloads', () => ({
  listAllWorkloads: vi.fn(),
}));

vi.mock('@/components/shared/HuggingFaceTokenSelector', () => ({
  ProjectHuggingFaceTokenSelector: ({
    value,
    onChange,
  }: {
    value: string | null;
    onChange: (name: string) => void;
  }) => (
    <label>
      hfTokenSecretName
      <select
        data-testid="hf-token-select"
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="" />
        <option value="hf-token-secret">hf-token-secret</option>
      </select>
    </label>
  ),
}));

const { useRealDebounceRef } = vi.hoisted(() => ({
  useRealDebounceRef: { current: false },
}));

// A synchronous passthrough keeps most tests fast and deterministic; the
// dedicated debounce-race test below flips `useRealDebounceRef` to exercise
// the real, timer-based implementation and its supersede logic.
vi.mock('lodash', async (importOriginal) => {
  const actual = await importOriginal<typeof import('lodash')>();
  return {
    ...actual,
    debounce: (callback: (...args: unknown[]) => unknown, wait?: number) =>
      useRealDebounceRef.current ? actual.debounce(callback, wait) : callback,
  };
});

vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const React = await import('react');
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();

  const SelectItem = ({
    children,
    value,
  }: {
    children: React.ReactNode;
    value?: string;
  }) => <option value={value}>{children}</option>;

  const FormSelect = ({
    form,
    name,
    label,
    children,
    isDisabled,
    ...props
  }: {
    form: {
      register: (name: string) => Record<string, unknown>;
    };
    name: string;
    label: string;
    children: React.ReactNode;
    isDisabled?: boolean;
    'data-testid'?: string;
  }) => (
    <label>
      {label}
      <select
        {...form.register(name)}
        data-testid={props['data-testid']}
        disabled={isDisabled}
      >
        <option value="" />
        {React.Children.map(children, (child) =>
          React.isValidElement(child)
            ? React.cloneElement(
                child as React.ReactElement<{ value?: string }>,
                { value: String(child.key) },
              )
            : child,
        )}
      </select>
    </label>
  );

  const ActionsToolbar = ({ canClear = true }: { canClear?: boolean }) =>
    canClear ? (
      <button type="button" data-testid="clear-filters-button">
        Clear filters
      </button>
    ) : null;
  const ClientSideDataTable = ({
    data,
    selectedKeys,
    onSelectionChange,
  }: {
    data: Array<{ id: string; name: string }>;
    selectedKeys: Set<string> | 'all';
    onSelectionChange: (keys: Set<string>) => void;
  }) => (
    <div>
      {data.map((dataset) => (
        <label key={dataset.id}>
          <input
            type="checkbox"
            checked={selectedKeys === 'all' || selectedKeys.has(dataset.id)}
            onChange={(event) => {
              const next =
                selectedKeys === 'all'
                  ? new Set(data.map(({ id }) => id))
                  : new Set(selectedKeys);
              if (event.target.checked) next.add(dataset.id);
              else next.delete(dataset.id);
              onSelectionChange(next);
            }}
          />
          {dataset.name}
        </label>
      ))}
    </div>
  );

  return {
    ...actual,
    ActionsToolbar,
    ClientSideDataTable,
    FormSelect,
    SelectItem,
  };
});

const model: Model = {
  id: 'model-id',
  name: 'Existing model',
  canonicalName: 'example/model',
  sourceUri: 's3://models/existing',
};

const loraRecipe: FinetunableModel = {
  canonicalName: 'example/lora-model',
  gpuCount: 1,
  compatibleAccelerators: [],
  compatibleAcceleratorNames: [],
  hfTokenRequired: false,
  trainingType: 'lora',
  hyperparameters: {
    batchSize: null,
    epochs: null,
    learningRate: null,
    lora: null,
  },
};
const anotherLoraRecipe: FinetunableModel = {
  ...loraRecipe,
  canonicalName: 'example/another-lora-model',
};

const renderWizard = (
  options: {
    selectedModel?: Model;
    finetunableModels?: FinetunableModel[];
  } = {},
) => {
  const selectedModel =
    'selectedModel' in options ? options.selectedModel : model;
  const finetunableModels = options.finetunableModels ?? [];
  const onClose = vi.fn();
  const onConfirmAction = vi.fn();
  render(
    <FinetuneWizard
      model={selectedModel}
      finetunableModels={finetunableModels}
      onClose={onClose}
      onConfirmAction={onConfirmAction}
    />,
    { wrapper },
  );
  return { onClose, onConfirmAction };
};

const goNext = async (user: ReturnType<typeof userEvent.setup>) => {
  const next = screen.getByRole('button', { name: 'actions.next' });
  await waitFor(() => expect(next).toBeEnabled());
  await user.click(next);
};

describe('FinetuneWizard', () => {
  beforeEach(() => {
    fetchQueryMock.mockResolvedValue([]);
    vi.mocked(getAllDatasets).mockResolvedValue([
      { id: 'dataset-1', name: 'Training data' },
    ] as Awaited<ReturnType<typeof getAllDatasets>>);
    vi.mocked(listProjectFineTunedModels).mockResolvedValue({
      data: [],
      pagination: { page: 1, pageSize: 100, total: 0 },
    });
    vi.mocked(getAimClusterProfiles).mockResolvedValue([]);
    vi.mocked(listAllAdapterArtifacts).mockResolvedValue([]);
    vi.mocked(fetchProjectSecrets).mockResolvedValue({ data: [] });
    vi.mocked(listAllWorkloads).mockResolvedValue([]);
  });

  it('renders target and hyper-parameters as separate steps', async () => {
    const user = userEvent.setup();
    renderWizard();

    await goNext(user);
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);
    expect(screen.getByTestId('wizard-step-target')).toBeInTheDocument();
    fireEvent.change(
      screen.getByLabelText('finetuneWizard.fields.modelName.label'),
      { target: { value: 'fine-tuned-model' } },
    );
    await goNext(user);
    expect(
      screen.getByTestId('wizard-step-hyperparameters'),
    ).toBeInTheDocument();
  });

  it('calls onClose from the wizard cancel button', () => {
    const { onClose } = renderWizard();

    fireEvent.click(
      screen.getByRole('button', { name: 'actions.cancel.title' }),
    );

    expect(onClose).toHaveBeenCalledOnce();
  });

  it('blocks the Model step until a base model is selected', async () => {
    const user = userEvent.setup();
    renderWizard({
      selectedModel: undefined,
      finetunableModels: [loraRecipe, anotherLoraRecipe],
    });

    const next = screen.getByRole('button', { name: 'actions.next' });
    expect(next).toBeDisabled();

    await user.selectOptions(
      screen.getByTestId('baseModelSelect'),
      loraRecipe.canonicalName,
    );

    await waitFor(() => expect(next).toBeEnabled());
  });

  it('blocks the Training step until at least one dataset is selected', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goNext(user);

    const next = screen.getByRole('button', { name: 'actions.next' });
    expect(next).toBeDisabled();

    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );

    await waitFor(() => expect(next).toBeEnabled());
  });

  it('blocks the Hyperparameters step when a customized value is out of range', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goNext(user);
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);
    fireEvent.change(
      await screen.findByLabelText('finetuneWizard.fields.modelName.label'),
      { target: { value: 'fine-tuned-model' } },
    );
    await goNext(user);
    await user.click(
      await screen.findByRole('switch', {
        name: 'finetuneWizard.fields.hyperparameters.customize',
      }),
    );

    const next = screen.getByRole('button', { name: 'actions.next' });
    expect(next).toBeEnabled();

    // `NumberField` only commits its typed text to the form on blur, so
    // each edit below is followed by a tab out of the field.
    const batchSizeInput = screen.getByLabelText(
      'finetuneWizard.fields.batchSize.label',
    );
    await user.type(batchSizeInput, '0');
    await user.tab();
    await waitFor(() => expect(next).toBeDisabled());

    await user.clear(batchSizeInput);
    await user.type(batchSizeInput, '4');
    await user.tab();
    await waitFor(() => expect(next).toBeEnabled());
  });

  it('does not show a clear filters button for training datasets', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goNext(user);

    expect(
      screen.queryByTestId('clear-filters-button'),
    ).not.toBeInTheDocument();
  });

  it('submits the guided flow with automatic hyper-parameters', async () => {
    const user = userEvent.setup();
    const { onConfirmAction } = renderWizard();
    await goNext(user);
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);
    fireEvent.change(
      await screen.findByLabelText('finetuneWizard.fields.modelName.label'),
      { target: { value: 'fine-tuned-model' } },
    );
    fireEvent.change(
      screen.getByLabelText('finetuneWizard.fields.description.label'),
      { target: { value: 'Trained for sentiment classification' } },
    );
    await goNext(user);
    expect(
      screen.queryByTestId('finetune-hyperparameters'),
    ).not.toBeInTheDocument();
    await goNext(user);
    await user.click(
      screen.getByRole('button', {
        name: 'finetuneWizard.actions.submit',
      }),
    );

    await waitFor(() => {
      expect(onConfirmAction).toHaveBeenCalledWith({
        id: 'model-id',
        params: {
          displayName: 'fine-tuned-model',
          datasetIds: ['dataset-1'],
          description: 'Trained for sentiment classification',
        },
      });
    });
  });

  it('keeps the Hyperparameters step enabled after batch size is cleared without typing', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goNext(user);
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);
    fireEvent.change(
      screen.getByLabelText('finetuneWizard.fields.modelName.label'),
      { target: { value: 'fine-tuned-model' } },
    );
    await goNext(user);
    await user.click(
      await screen.findByRole('switch', {
        name: 'finetuneWizard.fields.hyperparameters.customize',
      }),
    );

    const batchSize = await screen.findByLabelText(
      'finetuneWizard.fields.batchSize.label',
    );
    await user.type(batchSize, '4');
    await user.clear(batchSize);
    await user.tab();

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'actions.next' }),
      ).toBeEnabled(),
    );
  });

  it('reveals hyper-parameters only when customization is enabled', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goNext(user);
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);
    fireEvent.change(
      screen.getByLabelText('finetuneWizard.fields.modelName.label'),
      { target: { value: 'fine-tuned-model' } },
    );
    await goNext(user);

    expect(
      screen.queryByTestId('finetune-hyperparameters'),
    ).not.toBeInTheDocument();
    await user.click(
      await screen.findByRole('switch', {
        name: 'finetuneWizard.fields.hyperparameters.customize',
      }),
    );
    expect(
      await screen.findByTestId('finetune-hyperparameters'),
    ).toBeInTheDocument();
  });

  it('blocks the Target step when the description is too long', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goNext(user);
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);
    fireEvent.change(
      await screen.findByLabelText('finetuneWizard.fields.modelName.label'),
      { target: { value: 'fine-tuned-model' } },
    );

    const description = screen.getByLabelText(
      'finetuneWizard.fields.description.label',
    );
    const next = screen.getByRole('button', { name: 'actions.next' });
    fireEvent.change(description, {
      target: { value: 'a'.repeat(MAX_DESCRIPTION_LENGTH + 1) },
    });

    await waitFor(() => expect(next).toBeDisabled());

    fireEvent.change(description, {
      target: { value: 'a'.repeat(MAX_DESCRIPTION_LENGTH) },
    });
    await waitFor(() => expect(next).toBeEnabled());
  });

  it('only enables Full for a full-parameter recipe', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goNext(user);

    expect(
      screen.getByRole('radio', {
        name: 'finetuneWizard.fields.fineTuningType.full.label',
      }),
    ).toBeEnabled();
    expect(
      screen.getByRole('radio', {
        name: 'finetuneWizard.fields.fineTuningType.merged.label',
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole('radio', {
        name: 'finetuneWizard.fields.fineTuningType.lora.label',
      }),
    ).toBeDisabled();
  });

  it('preserves LoRA when switching between compatible base models', async () => {
    const user = userEvent.setup();
    renderWizard({
      selectedModel: undefined,
      finetunableModels: [loraRecipe, anotherLoraRecipe],
    });

    await user.selectOptions(
      screen.getByTestId('baseModelSelect'),
      loraRecipe.canonicalName,
    );
    await goNext(user);
    const full = screen.getByRole('radio', {
      name: 'finetuneWizard.fields.fineTuningType.full.label',
    });
    const lora = screen.getByRole('radio', {
      name: 'finetuneWizard.fields.fineTuningType.lora.label',
    });
    await user.click(lora);
    expect(lora).toBeChecked();
    expect(full).toBeDisabled();

    await user.click(
      screen.getByRole('button', { name: 'actions.back.title' }),
    );
    await user.selectOptions(
      screen.getByTestId('baseModelSelect'),
      anotherLoraRecipe.canonicalName,
    );
    await goNext(user);

    expect(lora).toBeChecked();
    expect(full).toBeDisabled();
  });

  it('moves off LoRA when the chosen base model cannot serve adapters', async () => {
    const user = userEvent.setup();
    vi.mocked(getAimClusterProfiles).mockImplementation(async (aimId) =>
      aimId === anotherLoraRecipe.canonicalName
        ? [
            {
              metadata: { name: 'profile-plain', labels: {} },
              spec: {
                aimId,
                modelName: aimId,
                metric: 'latency',
                features: [],
              },
              status: { status: 'Ready' },
            },
          ]
        : [],
    );
    renderWizard({
      selectedModel: undefined,
      finetunableModels: [loraRecipe, anotherLoraRecipe],
    });

    await user.selectOptions(
      screen.getByTestId('baseModelSelect'),
      loraRecipe.canonicalName,
    );
    await goNext(user);
    const lora = screen.getByRole('radio', {
      name: 'finetuneWizard.fields.fineTuningType.lora.label',
    });
    await user.click(lora);
    expect(lora).toBeChecked();

    await user.click(
      screen.getByRole('button', { name: 'actions.back.title' }),
    );
    await user.selectOptions(
      screen.getByTestId('baseModelSelect'),
      anotherLoraRecipe.canonicalName,
    );
    await goNext(user);

    await waitFor(() => expect(lora).toBeDisabled());
    expect(lora).not.toBeChecked();
    expect(
      screen.getByRole('radio', {
        name: 'finetuneWizard.fields.fineTuningType.merged.label',
      }),
    ).toBeChecked();
  });

  it('keeps Merged selected when the Training step registers its fields', async () => {
    const user = userEvent.setup();
    renderWizard({
      selectedModel: {
        id: 'lora-model-id',
        name: 'LoRA-capable model',
        canonicalName: loraRecipe.canonicalName,
        sourceUri: 's3://models/lora-capable',
      },
      finetunableModels: [loraRecipe],
    });

    await goNext(user);
    const merged = screen.getByRole('radio', {
      name: 'finetuneWizard.fields.fineTuningType.merged.label',
    });
    expect(merged).toBeChecked();
    expect(
      screen.getByRole('radio', {
        name: 'finetuneWizard.fields.fineTuningType.full.label',
      }),
    ).toBeDisabled();

    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    expect(merged).toBeChecked();
  });

  it('configures and submits a LoRA adapter for a LoRA recipe', async () => {
    const user = userEvent.setup({ delay: null });
    const { onConfirmAction } = renderWizard({
      selectedModel: {
        id: 'lora-model-id',
        name: 'LoRA-capable model',
        canonicalName: loraRecipe.canonicalName,
        sourceUri: 's3://models/lora-capable',
      },
      finetunableModels: [loraRecipe],
    });
    await goNext(user);
    const full = screen.getByRole('radio', {
      name: 'finetuneWizard.fields.fineTuningType.full.label',
    });
    const merged = screen.getByRole('radio', {
      name: 'finetuneWizard.fields.fineTuningType.merged.label',
    });
    const lora = screen.getByRole('radio', {
      name: 'finetuneWizard.fields.fineTuningType.lora.label',
    });

    expect(full).toBeDisabled();
    expect(merged).toBeEnabled();
    expect(lora).toBeEnabled();
    await user.click(lora);
    expect(
      screen.queryByLabelText('finetuneWizard.fields.loraName.label'),
    ).not.toBeInTheDocument();
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);
    fireEvent.change(
      screen.getByLabelText('finetuneWizard.fields.loraName.label'),
      { target: { value: 'fine-tuned-lora' } },
    );
    await goNext(user);
    await user.click(
      await screen.findByRole('switch', {
        name: 'finetuneWizard.fields.hyperparameters.customize',
      }),
    );
    await user.type(
      await screen.findByLabelText('finetuneWizard.fields.learningRate.label'),
      '1.4000000000000004',
    );
    await user.type(
      await screen.findByLabelText('finetuneWizard.fields.loraRank.label'),
      '16',
    );
    await user.type(
      screen.getByLabelText('finetuneWizard.fields.loraAlpha.label'),
      '32',
    );
    await user.type(
      screen.getByLabelText('finetuneWizard.fields.loraDropout.label'),
      '0.054000000000000006',
    );
    await goNext(user);
    await user.click(
      screen.getByRole('button', {
        name: 'finetuneWizard.actions.submit',
      }),
    );

    await waitFor(() => {
      expect(onConfirmAction).toHaveBeenCalledWith({
        id: 'lora-model-id',
        params: {
          displayName: 'fine-tuned-lora',
          datasetIds: ['dataset-1'],
          batchSize: undefined,
          epochs: undefined,
          learningRate: 1.4,
          output: 'adapter',
          lora: { rank: 16, alpha: 32, dropout: 0.054 },
        },
      });
    });
  });

  it('explains why a Hugging Face token is required', async () => {
    render(
      <FinetuneWizard
        model={{
          id: 'gated-model-id',
          name: 'Gated model',
          canonicalName: 'example/gated-model',
          hfTokenRequired: true,
        }}
        finetunableModels={[]}
        onClose={vi.fn()}
        onConfirmAction={vi.fn()}
      />,
      { wrapper },
    );

    expect(
      await screen.findByText(
        'finetuneWizard.fields.huggingFaceToken.description',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('finetuneWizard.fields.huggingFaceToken.title'),
    ).toBeInTheDocument();
  });

  it('includes the Hugging Face token secret name for a gated base model', async () => {
    const user = userEvent.setup();
    const onConfirmAction = vi.fn();
    render(
      <FinetuneWizard
        model={{
          id: 'gated-model-id',
          name: 'Gated model',
          canonicalName: 'example/gated-model',
          hfTokenRequired: true,
        }}
        finetunableModels={[]}
        onClose={vi.fn()}
        onConfirmAction={onConfirmAction}
      />,
      { wrapper },
    );

    await user.selectOptions(
      screen.getByTestId('hf-token-select'),
      'hf-token-secret',
    );
    await goNext(user);
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);
    fireEvent.change(
      await screen.findByLabelText('finetuneWizard.fields.modelName.label'),
      { target: { value: 'fine-tuned-model' } },
    );
    await goNext(user);
    await goNext(user);
    await user.click(
      screen.getByRole('button', { name: 'finetuneWizard.actions.submit' }),
    );

    await waitFor(() => {
      expect(onConfirmAction).toHaveBeenCalledWith({
        id: 'gated-model-id',
        params: {
          displayName: 'fine-tuned-model',
          datasetIds: ['dataset-1'],
          hfTokenSecretName: 'hf-token-secret',
        },
      });
    });
  });

  it('handles model name availability check failures without blocking the user', async () => {
    const consoleErrorSpy = vi
      .spyOn(console, 'error')
      .mockImplementation(() => {});
    fetchQueryMock.mockRejectedValue(new Error('network error'));
    const user = userEvent.setup();
    renderWizard();

    try {
      await goNext(user);
      await user.click(
        await screen.findByRole('checkbox', { name: 'Training data' }),
      );
      await goNext(user);
      const nameInput = await screen.findByLabelText(
        'finetuneWizard.fields.modelName.label',
      );
      fireEvent.change(nameInput, { target: { value: 'available-name' } });

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Error checking model name availability:',
          expect.any(Error),
        );
      });
      expect(nameInput).not.toBeInvalid();
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  it('blocks a duplicate model name before review', async () => {
    const user = userEvent.setup();
    fetchQueryMock.mockResolvedValue([
      {
        metadata: {
          labels: { 'aiwb.apps.eai.amd.com/model-name': 'duplicate-name' },
        },
      },
    ]);
    renderWizard();

    await goNext(user);
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);
    fireEvent.change(
      await screen.findByLabelText('finetuneWizard.fields.modelName.label'),
      { target: { value: 'duplicate name!' } },
    );

    expect(
      await screen.findByText('finetuneWizard.validation.modelNameUnique'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'actions.next' })).toBeDisabled();
  });

  it('blocks a duplicate LoRA adapter name before review', async () => {
    const user = userEvent.setup();
    vi.mocked(listAllAdapterArtifacts).mockResolvedValue([
      { displayName: 'duplicate LoRA' },
    ] as Awaited<ReturnType<typeof listAllAdapterArtifacts>>);
    fetchQueryMock.mockImplementation(
      ({
        queryKey,
        queryFn,
      }: {
        queryKey: string[];
        queryFn: () => Promise<unknown>;
      }) => (queryKey.includes('workloads') ? Promise.resolve([]) : queryFn()),
    );
    renderWizard({
      selectedModel: {
        id: 'lora-model-id',
        name: 'LoRA-capable model',
        canonicalName: loraRecipe.canonicalName,
        sourceUri: 's3://models/lora-capable',
      },
      finetunableModels: [loraRecipe],
    });
    await goNext(user);
    await user.click(
      screen.getByRole('radio', {
        name: 'finetuneWizard.fields.fineTuningType.lora.label',
      }),
    );
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);
    fireEvent.change(
      screen.getByLabelText('finetuneWizard.fields.loraName.label'),
      { target: { value: 'duplicate LoRA' } },
    );

    expect(
      await screen.findByText('finetuneWizard.validation.loraNameUnique'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'actions.next' })).toBeDisabled();
    expect(listAllAdapterArtifacts).toHaveBeenCalledWith('project-1');
  });

  it('blocks the Target step when the model name is empty', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goNext(user);
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);

    const next = screen.getByRole('button', { name: 'actions.next' });
    expect(next).toBeDisabled();
  });

  it('blocks the Target step when the model name is too long', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goNext(user);
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);
    fireEvent.change(
      await screen.findByLabelText('finetuneWizard.fields.modelName.label'),
      { target: { value: 'a'.repeat(MAX_DISPLAY_NAME_LENGTH + 1) } },
    );

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'actions.next' }),
      ).toBeDisabled(),
    );
  });

  it('blocks the Target step while the uniqueness check is in flight', async () => {
    const user = userEvent.setup();
    const pendingResolves: Array<(value: unknown) => void> = [];
    fetchQueryMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          pendingResolves.push(resolve);
        }),
    );
    renderWizard();
    await goNext(user);
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);
    fireEvent.change(
      await screen.findByLabelText('finetuneWizard.fields.modelName.label'),
      { target: { value: 'pending-name' } },
    );

    const next = screen.getByRole('button', { name: 'actions.next' });
    await waitFor(() => expect(next).toBeDisabled());

    for (const resolve of pendingResolves) {
      resolve([]);
    }
    await waitFor(() => expect(next).toBeEnabled());
  });

  it('returns to the Target step when submit rejects a duplicate model name', async () => {
    const user = userEvent.setup();
    const onConfirmAction = vi.fn();
    let modelCheckCount = 0;
    fetchQueryMock.mockImplementation(
      ({
        queryKey,
        queryFn,
      }: {
        queryKey: string[];
        queryFn?: () => Promise<unknown>;
      }) => {
        if (queryKey.includes('workloads')) {
          return Promise.resolve([]);
        }
        if (
          queryKey.includes('models') ||
          queryKey.includes('artifacts') ||
          queryKey.includes('name-check')
        ) {
          modelCheckCount++;
          if (modelCheckCount === 1) {
            return queryFn ? queryFn() : Promise.resolve([]);
          }
          return Promise.resolve([
            {
              metadata: {
                labels: {
                  'aiwb.apps.eai.amd.com/model-name': 'fine-tuned-model',
                },
              },
            },
          ]);
        }
        return queryFn ? queryFn() : Promise.resolve([]);
      },
    );
    render(
      <FinetuneWizard
        model={model}
        finetunableModels={[]}
        onClose={vi.fn()}
        onConfirmAction={onConfirmAction}
      />,
      { wrapper },
    );

    await goNext(user);
    await user.click(
      await screen.findByRole('checkbox', { name: 'Training data' }),
    );
    await goNext(user);
    fireEvent.change(
      await screen.findByLabelText('finetuneWizard.fields.modelName.label'),
      { target: { value: 'fine-tuned-model' } },
    );
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'actions.next' }),
      ).toBeEnabled(),
    );
    await goNext(user);
    await goNext(user);
    await user.click(
      screen.getByRole('button', { name: 'finetuneWizard.actions.submit' }),
    );

    await waitFor(() => {
      expect(onConfirmAction).not.toHaveBeenCalled();
      expect(
        screen.getByText('finetuneWizard.validation.modelNameUnique'),
      ).toBeInTheDocument();
      expect(screen.getByTestId('wizard-step-target')).toBeInTheDocument();
    });
  });

  it('coalesces rapid name edits into a single availability check via the real debounce', async () => {
    // `debouncedCheck` is created once, at mount, from whichever `debounce`
    // implementation is active then — flip this before rendering.
    useRealDebounceRef.current = true;
    try {
      renderWizard();
      fireEvent.click(screen.getByRole('button', { name: 'actions.next' }));
      fireEvent.click(
        await screen.findByRole('checkbox', { name: 'Training data' }),
      );
      fireEvent.click(screen.getByRole('button', { name: 'actions.next' }));

      const nameInput = await screen.findByLabelText(
        'finetuneWizard.fields.modelName.label',
      );
      fetchQueryMock.mockClear();

      // Fake timers are scoped to the edits themselves so the earlier
      // `find*` queries above still resolve on the real clock.
      vi.useFakeTimers();
      fireEvent.change(nameInput, { target: { value: 'first-name' } });
      await vi.advanceTimersByTimeAsync(300);
      fireEvent.change(nameInput, { target: { value: 'second-name' } });
      await vi.advanceTimersByTimeAsync(300);
      fireEvent.change(nameInput, { target: { value: 'final-name' } });
      await vi.advanceTimersByTimeAsync(700);
      vi.useRealTimers();

      // `checkModelName` issues two `fetchQuery` calls (models-or-artifacts
      // + workloads) per invocation. Exactly two calls despite three edits
      // within the 700ms window proves the debounce collapsed them into a
      // single check for the final name, rather than checking on every
      // keystroke — the behavior `resolvePrevious?.(true)` exists to make
      // safe by optimistically resolving the superseded in-flight checks.
      await waitFor(() => expect(fetchQueryMock).toHaveBeenCalledTimes(2));

      const next = screen.getByRole('button', { name: 'actions.next' });
      await waitFor(() => expect(next).toBeEnabled());
    } finally {
      vi.useRealTimers();
      useRealDebounceRef.current = false;
    }
  });
});
