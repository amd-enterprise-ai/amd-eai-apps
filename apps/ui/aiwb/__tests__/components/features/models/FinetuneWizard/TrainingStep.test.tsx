// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useForm } from 'react-hook-form';
import {
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type MockInstance,
} from 'vitest';

import wrapper from '@/__tests__/ProviderWrapper';
import {
  createTrainingStepSchema,
  TrainingStepFields,
} from '@/components/features/models/FinetuneWizard/steps/TrainingStep';
import {
  DEFAULT_FINETUNE_VALUES,
  MAX_FINETUNE_DATASETS,
  type FineTuningType,
  type FinetuneFormValues,
} from '@/components/features/models/FinetuneWizard/types';
import * as aimsLib from '@/lib/app/aims';
import type { AIMClusterProfile, AIMProfileSpec } from '@/types/aims';
import type { components } from '@/types/api';
import type { FinetunableModel, Model } from '@/types/models';

const { toastErrorMock } = vi.hoisted(() => ({
  toastErrorMock: vi.fn(),
}));

vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@amdenterpriseai/hooks')>()),
  useSystemToast: () => ({ toast: { error: toastErrorMock } }),
}));

vi.mock('@amdenterpriseai/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@amdenterpriseai/components')>()),
  ClientSideDataTable: ({
    data,
    onSelectionChange,
  }: {
    data: Array<{ id: string }>;
    onSelectionChange: (selection: 'all' | Set<string>) => void;
  }) => (
    <div>
      <button
        type="button"
        onClick={() =>
          onSelectionChange(new Set(data.slice(0, 2).map(({ id }) => id)))
        }
      >
        Select two
      </button>
      <button
        type="button"
        onClick={() => onSelectionChange(new Set(data.map(({ id }) => id)))}
      >
        Select all rows
      </button>
      <button type="button" onClick={() => onSelectionChange('all')}>
        Select all
      </button>
    </div>
  ),
}));

type Dataset = components['schemas']['DatasetResponse'];

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

const fullRecipe: FinetunableModel = {
  ...loraRecipe,
  canonicalName: 'example/full-model',
  trainingType: 'full',
};

const finetunedModel: Model = {
  name: 'my-finetuned-model',
  canonicalName: loraRecipe.canonicalName,
};

// `spec` is optional on AIMClusterProfile, so derive sibling fixtures from this
// non-optional spec rather than spreading `someProfile.spec`, which would widen
// the required `aimId` to `string | undefined`.
const adapterCapableSpec: AIMProfileSpec = {
  aimId: loraRecipe.canonicalName,
  modelName: loraRecipe.canonicalName,
  metric: 'latency',
  features: ['adapters'],
};

const adapterCapableProfile: AIMClusterProfile = {
  metadata: { name: 'profile-adapters', labels: {} },
  spec: adapterCapableSpec,
  status: { status: 'Ready' },
};

const LORA_LABEL = 'finetuneWizard.fields.fineTuningType.lora.label';

const plainProfile: AIMClusterProfile = {
  ...adapterCapableProfile,
  metadata: { name: 'profile-plain', labels: {} },
  spec: { ...adapterCapableSpec, features: [] },
};

const TrainingStepHarness = ({
  datasets = [],
  datasetIds = [],
  recipe = loraRecipe,
  model,
  canonicalName = recipe.canonicalName,
  fineTuningType = 'full',
}: {
  datasets?: Dataset[];
  datasetIds?: string[];
  recipe?: FinetunableModel;
  model?: Model;
  // Overridable so a re-fine-tune can be rendered as the wizard renders it:
  // no canonical name in the form, only the fine-tuned model it started from.
  canonicalName?: string;
  fineTuningType?: FineTuningType;
}) => {
  const form = useForm<FinetuneFormValues>({
    defaultValues: {
      ...DEFAULT_FINETUNE_VALUES,
      canonicalName,
      fineTuningType,
      datasetIds,
    },
  });

  return (
    <>
      <TrainingStepFields
        form={form}
        datasets={datasets}
        model={model}
        finetunableModels={[recipe]}
      />
      <output>{form.watch('datasetIds').join(',')}</output>
    </>
  );
};

const datasets = Array.from(
  { length: MAX_FINETUNE_DATASETS + 1 },
  (_, index) =>
    ({
      id: `dataset-${index + 1}`,
      name: `Training data ${index + 1}`,
      description: '',
    }) as Dataset,
);

describe('createTrainingStepSchema', () => {
  const schema = createTrainingStepSchema(
    'dataset required',
    'too many datasets',
  );

  it('requires at least one training dataset', () => {
    expect(schema.safeParse({ datasetIds: [] }).success).toBe(false);
  });

  it('accepts up to ten training datasets', () => {
    expect(
      schema.safeParse({
        datasetIds: Array.from(
          { length: 10 },
          (_, index) => `dataset-${index}`,
        ),
      }).success,
    ).toBe(true);
  });

  it('rejects more than ten training datasets', () => {
    expect(
      schema.safeParse({
        datasetIds: Array.from(
          { length: 11 },
          (_, index) => `dataset-${index}`,
        ),
      }).success,
    ).toBe(false);
  });
});

describe('TrainingStepFields', () => {
  let clusterProfilesSpy: MockInstance<typeof aimsLib.getAimClusterProfiles>;

  beforeEach(() => {
    vi.restoreAllMocks();
    toastErrorMock.mockClear();
    clusterProfilesSpy = vi
      .spyOn(aimsLib, 'getAimClusterProfiles')
      .mockResolvedValue([]);
  });

  it('selects multiple training datasets', async () => {
    const user = userEvent.setup();
    render(<TrainingStepHarness datasets={datasets} />, { wrapper });

    await user.click(screen.getByRole('button', { name: 'Select two' }));

    expect(screen.getByRole('status')).toHaveTextContent('dataset-1,dataset-2');
  });

  it('rejects selections above the dataset limit', async () => {
    const user = userEvent.setup();
    render(<TrainingStepHarness datasets={datasets} />, { wrapper });

    await user.click(screen.getByRole('button', { name: 'Select all rows' }));

    expect(toastErrorMock).toHaveBeenCalledWith(
      'finetuneWizard.validation.datasetsMaxReached',
    );
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
  });

  it('deduplicates existing datasets when selecting all', async () => {
    const user = userEvent.setup();
    render(
      <TrainingStepHarness
        datasets={datasets.slice(0, 2)}
        datasetIds={['dataset-1']}
      />,
      { wrapper },
    );

    await user.click(screen.getByRole('button', { name: 'Select all' }));

    expect(screen.getByRole('status')).toHaveTextContent('dataset-1,dataset-2');
  });

  it('withdraws LoRA when the published profiles cannot serve adapters', async () => {
    clusterProfilesSpy.mockResolvedValue([plainProfile]);
    render(<TrainingStepHarness />, { wrapper });

    await waitFor(() =>
      expect(screen.getByRole('radio', { name: LORA_LABEL })).toBeDisabled(),
    );
    expect(
      screen.getByText(
        'finetuneWizard.fields.fineTuningType.lora.unavailableDescription',
      ),
    ).toBeInTheDocument();
  });

  // Merged is where the wizard parks a LoRA recipe, so it is the only state from
  // which the user ever reads the LoRA option. Deferring either the lookup or the
  // explanation until LoRA is the selected output would put both out of reach: the
  // option is withdrawn, so it can never become the selection.
  it('withdraws LoRA and says why while Merged is the selected output', async () => {
    clusterProfilesSpy.mockResolvedValue([plainProfile]);
    render(<TrainingStepHarness fineTuningType="merged" />, { wrapper });

    await waitFor(() =>
      expect(screen.getByRole('radio', { name: LORA_LABEL })).toBeDisabled(),
    );
    expect(clusterProfilesSpy).toHaveBeenCalledWith(loraRecipe.canonicalName);
    expect(
      screen.getByText(
        'finetuneWizard.fields.fineTuningType.lora.unavailableDescription',
      ),
    ).toBeInTheDocument();
  });

  it('offers LoRA when a profile can serve adapters', async () => {
    clusterProfilesSpy.mockResolvedValue([adapterCapableProfile]);
    render(<TrainingStepHarness />, { wrapper });

    await waitFor(() => expect(clusterProfilesSpy).toHaveBeenCalled());

    expect(screen.getByRole('radio', { name: LORA_LABEL })).toBeEnabled();
  });

  // Unknown is not absent: the API refuses only on a published capability, so
  // a model publishing no profiles at all must keep the option offered.
  it('offers LoRA when the model publishes no profiles at all', async () => {
    render(<TrainingStepHarness />, { wrapper });

    await waitFor(() => expect(clusterProfilesSpy).toHaveBeenCalled());

    expect(screen.getByRole('radio', { name: LORA_LABEL })).toBeEnabled();
    expect(
      screen.queryByText(
        'finetuneWizard.fields.fineTuningType.lora.unavailableDescription',
      ),
    ).not.toBeInTheDocument();
  });

  it('skips the profile lookup for a full-parameter recipe', () => {
    render(<TrainingStepHarness recipe={fullRecipe} />, { wrapper });

    expect(clusterProfilesSpy).not.toHaveBeenCalled();
    expect(screen.getByRole('radio', { name: LORA_LABEL })).toBeDisabled();
    // The recipe, not the cluster, rules LoRA out here, so the user needs no
    // explanation beyond the base model they already picked.
    expect(
      screen.queryByText(
        'finetuneWizard.fields.fineTuningType.lora.unavailableDescription',
      ),
    ).not.toBeInTheDocument();
  });

  // A re-fine-tune carries no canonical name of its own in the form, so the
  // base identity has to come off the model — and it is the base, not the
  // fine-tuned model, whose profiles decide whether the adapter can deploy.
  it('asks about the base model when re-fine-tuning a fine-tuned model', async () => {
    clusterProfilesSpy.mockResolvedValue([plainProfile]);
    render(<TrainingStepHarness model={finetunedModel} canonicalName="" />, {
      wrapper,
    });

    await waitFor(() =>
      expect(screen.getByRole('radio', { name: LORA_LABEL })).toBeDisabled(),
    );
    expect(clusterProfilesSpy).toHaveBeenCalledWith(loraRecipe.canonicalName);
  });

  it('offers LoRA when re-fine-tuning a base model that can serve adapters', async () => {
    clusterProfilesSpy.mockResolvedValue([adapterCapableProfile]);
    render(<TrainingStepHarness model={finetunedModel} canonicalName="" />, {
      wrapper,
    });

    await waitFor(() => expect(clusterProfilesSpy).toHaveBeenCalled());

    expect(screen.getByRole('radio', { name: LORA_LABEL })).toBeEnabled();
  });
});
