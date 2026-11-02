// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useForm } from 'react-hook-form';
import { describe, expect, it, vi } from 'vitest';

import {
  hyperparametersStepSchema,
  HyperparametersStepFields,
  HyperparametersStepSummary,
} from '@/components/features/models/FinetuneWizard/steps/HyperparametersStep';
import {
  DEFAULT_FINETUNE_VALUES,
  type FinetuneFormValues,
} from '@/components/features/models/FinetuneWizard/types';
import type { FinetunableModel } from '@/types/models';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const values = {
  customizeHyperparameters: false,
  batchSize: undefined,
  epochs: undefined,
  learningRate: undefined,
};

const multiGpuRecipe: FinetunableModel = {
  canonicalName: 'example/multi-gpu',
  gpuCount: 4,
  compatibleAccelerators: [],
  compatibleAcceleratorNames: [],
  hfTokenRequired: false,
  trainingType: 'full',
  hyperparameters: {
    batchSize: null,
    epochs: null,
    learningRate: null,
    lora: null,
  },
};

const loraRecipe: FinetunableModel = {
  ...multiGpuRecipe,
  canonicalName: 'example/lora',
  trainingType: 'lora',
  hyperparameters: {
    batchSize: 8,
    epochs: 3,
    learningRate: 1,
    lora: {
      rank: 64,
      alpha: 16,
      dropout: 0.05,
    },
  },
};

const HyperparametersStepHarness = ({
  finetunableModels = [multiGpuRecipe],
}: {
  finetunableModels?: FinetunableModel[];
}) => {
  const form = useForm<FinetuneFormValues>({
    defaultValues: {
      ...DEFAULT_FINETUNE_VALUES,
      canonicalName: finetunableModels[0].canonicalName,
      fineTuningType: finetunableModels[0].trainingType,
      customizeHyperparameters: true,
    },
  });
  return (
    <HyperparametersStepFields
      form={form}
      finetunableModels={finetunableModels}
    />
  );
};

describe('hyperparametersStepSchema', () => {
  it('validates customized hyper-parameter ranges', () => {
    expect(
      hyperparametersStepSchema.safeParse({
        ...values,
        customizeHyperparameters: true,
        batchSize: 0,
      }).success,
    ).toBe(false);
    expect(
      hyperparametersStepSchema.safeParse({
        ...values,
        customizeHyperparameters: true,
        batchSize: 4,
        epochs: 3,
        learningRate: 1.5,
      }).success,
    ).toBe(true);
  });

  it.each([
    ['minimum rank', { loraRank: 1 }, true],
    ['maximum rank', { loraRank: 512 }, true],
    ['rank below minimum', { loraRank: 0 }, false],
    ['rank above maximum', { loraRank: 513 }, false],
    ['fractional rank', { loraRank: 1.5 }, false],
    ['minimum alpha', { loraAlpha: 1 }, true],
    ['fractional alpha', { loraAlpha: 1.5 }, false],
    ['alpha below minimum', { loraAlpha: 0 }, false],
    ['minimum dropout', { loraDropout: 0 }, true],
    ['dropout below maximum', { loraDropout: 0.999 }, true],
    ['dropout at maximum', { loraDropout: 1 }, false],
  ])('validates LoRA %s', (_case, fields, expected) => {
    expect(
      hyperparametersStepSchema.safeParse({
        ...values,
        ...fields,
      }).success,
    ).toBe(expected);
  });
});

describe('HyperparametersStepFields', () => {
  it('derives batch size min and step from the recipe GPU count', async () => {
    const user = userEvent.setup();
    render(<HyperparametersStepHarness />);

    const batchSize = screen.getByLabelText(
      'finetuneWizard.fields.batchSize.label',
    ) as HTMLInputElement;
    const [batchSizeIncrease] = screen.getAllByRole('button', {
      name: 'numberField.increase',
    });
    await user.click(batchSizeIncrease);

    await waitFor(() => {
      expect(batchSize.value).toBe('4');
    });
  });

  it('uses the selected recipe values as placeholders', () => {
    render(<HyperparametersStepHarness finetunableModels={[loraRecipe]} />);

    expect(
      screen.getByLabelText('finetuneWizard.fields.batchSize.label'),
    ).toHaveAttribute('placeholder', '8');
    expect(
      screen.getByLabelText('finetuneWizard.fields.epochs.label'),
    ).toHaveAttribute('placeholder', '3');
    expect(
      screen.getByLabelText('finetuneWizard.fields.learningRate.label'),
    ).toHaveAttribute('placeholder', '1');
    expect(
      screen.getByLabelText('finetuneWizard.fields.loraRank.label'),
    ).toHaveAttribute('placeholder', '64');
    expect(
      screen.getByLabelText('finetuneWizard.fields.loraAlpha.label'),
    ).toHaveAttribute('placeholder', '16');
    expect(
      screen.getByLabelText('finetuneWizard.fields.loraDropout.label'),
    ).toHaveAttribute('placeholder', '0.05');
  });

  it('steps untouched recipe-backed values from their recommendations', () => {
    render(<HyperparametersStepHarness finetunableModels={[loraRecipe]} />);

    const increases = screen.getAllByRole('button', {
      name: 'numberField.increase',
    });
    fireEvent.click(increases[0]);
    fireEvent.click(increases[1]);
    fireEvent.click(increases[2]);
    fireEvent.click(increases[3]);
    fireEvent.click(increases[4]);
    fireEvent.click(increases[5]);

    expect(
      (
        screen.getByLabelText(
          'finetuneWizard.fields.batchSize.label',
        ) as HTMLInputElement
      ).value,
    ).toBe('12');
    expect(
      (
        screen.getByLabelText(
          'finetuneWizard.fields.epochs.label',
        ) as HTMLInputElement
      ).value,
    ).toBe('4');
    expect(
      (
        screen.getByLabelText(
          'finetuneWizard.fields.learningRate.label',
        ) as HTMLInputElement
      ).value,
    ).toBe('1.1');
    expect(
      (
        screen.getByLabelText(
          'finetuneWizard.fields.loraAlpha.label',
        ) as HTMLInputElement
      ).value,
    ).toBe('17');
    expect(
      (
        screen.getByLabelText(
          'finetuneWizard.fields.loraRank.label',
        ) as HTMLInputElement
      ).value,
    ).toBe('65');
    expect(
      (
        screen.getByLabelText(
          'finetuneWizard.fields.loraDropout.label',
        ) as HTMLInputElement
      ).value,
    ).toBe('0.051');
  });
});

describe('HyperparametersStepSummary', () => {
  it('shows recipe values when hyperparameters are not customized', () => {
    render(
      <HyperparametersStepSummary
        data={{
          ...DEFAULT_FINETUNE_VALUES,
          canonicalName: loraRecipe.canonicalName,
          fineTuningType: 'lora',
        }}
        finetunableModels={[loraRecipe]}
      />,
    );

    expect(
      screen.getByText('finetuneWizard.summary.automatic'),
    ).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('1.0')).toBeInTheDocument();
    expect(screen.getByText('64')).toBeInTheDocument();
    expect(screen.getByText('16')).toBeInTheDocument();
    expect(screen.getByText('0.050')).toBeInTheDocument();
  });

  it('prefers customized values over recipe values', () => {
    render(
      <HyperparametersStepSummary
        data={{
          ...DEFAULT_FINETUNE_VALUES,
          canonicalName: loraRecipe.canonicalName,
          fineTuningType: 'lora',
          customizeHyperparameters: true,
          epochs: 5,
        }}
        finetunableModels={[loraRecipe]}
      />,
    );

    expect(
      screen.getByText('finetuneWizard.summary.customized'),
    ).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('1.0')).toBeInTheDocument();
  });

  it('hides LoRA rows for merged output', () => {
    render(
      <HyperparametersStepSummary
        data={{
          ...DEFAULT_FINETUNE_VALUES,
          canonicalName: loraRecipe.canonicalName,
          fineTuningType: 'merged',
        }}
        finetunableModels={[loraRecipe]}
      />,
    );

    expect(screen.queryByText('64')).toBeNull();
    expect(screen.queryByText('0.050')).toBeNull();
  });

  it('ignores stale customized values when customization is disabled', () => {
    render(
      <HyperparametersStepSummary
        data={{
          ...DEFAULT_FINETUNE_VALUES,
          batchSize: 16,
          canonicalName: loraRecipe.canonicalName,
          epochs: 5,
          fineTuningType: 'lora',
          learningRate: 2,
          loraAlpha: 32,
          loraDropout: 0.1,
          loraRank: 128,
        }}
        finetunableModels={[loraRecipe]}
      />,
    );

    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('1.0')).toBeInTheDocument();
    expect(screen.getByText('64')).toBeInTheDocument();
    expect(screen.getByText('16')).toBeInTheDocument();
    expect(screen.getByText('0.050')).toBeInTheDocument();
    expect(screen.queryByText('128')).toBeNull();
    expect(screen.queryByText('0.100')).toBeNull();
  });

  it('formats customized decimal values to their step precision', () => {
    render(
      <HyperparametersStepSummary
        data={{
          ...DEFAULT_FINETUNE_VALUES,
          canonicalName: loraRecipe.canonicalName,
          fineTuningType: 'lora',
          customizeHyperparameters: true,
          learningRate: 1.4000000000000004,
          loraDropout: 0.054000000000000006,
        }}
        finetunableModels={[loraRecipe]}
      />,
    );

    expect(screen.getByText('1.4')).toBeInTheDocument();
    expect(screen.getByText('0.054')).toBeInTheDocument();
  });
});
