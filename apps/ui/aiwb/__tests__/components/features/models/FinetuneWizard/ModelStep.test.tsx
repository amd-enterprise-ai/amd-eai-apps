// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { useForm } from 'react-hook-form';
import { describe, expect, it, vi } from 'vitest';

import {
  createModelStepSchema,
  ModelStepFields,
  ModelStepSummary,
} from '@/components/features/models/FinetuneWizard/steps/ModelStep';
import {
  DEFAULT_FINETUNE_VALUES,
  type FinetuneFormValues,
} from '@/components/features/models/FinetuneWizard/types';
import type { FinetunableModel, Model } from '@/types/models';
import type { SecretResponseData } from '@/types/secrets';
import { SecretUseCase } from '@amdenterpriseai/types';

vi.mock('@amdenterpriseai/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@amdenterpriseai/components')>()),
  FormSelect: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  SelectItem: ({
    children,
    description,
    'data-testid': testId,
  }: {
    children: ReactNode;
    description?: ReactNode;
    'data-testid'?: string;
  }) => (
    <div data-testid={testId}>
      <span>{children}</span>
      {description ? (
        <span data-testid={`${testId}-description`}>{description}</span>
      ) : null}
    </div>
  ),
}));

const recipe = (hfTokenRequired: boolean): FinetunableModel =>
  ({
    canonicalName: 'example/model',
    hfTokenRequired,
  }) as FinetunableModel;

const ModelStepFieldsHarness = ({
  finetunableModels,
}: {
  finetunableModels: FinetunableModel[];
}) => {
  const form = useForm<FinetuneFormValues>({
    defaultValues: DEFAULT_FINETUNE_VALUES,
  });
  return (
    <ModelStepFields
      form={form}
      finetunableModels={finetunableModels}
      namespace="default"
    />
  );
};

describe('ModelStepFields', () => {
  it('shows gated status before compatible accelerators', () => {
    const gatedRecipe = {
      ...recipe(true),
      canonicalName: 'example/gated-model',
      compatibleAcceleratorNames: ['MI300X'],
    };
    const publicRecipe = {
      ...recipe(false),
      canonicalName: 'example/public-model',
      compatibleAcceleratorNames: ['MI325X'],
    };

    render(
      <ModelStepFieldsHarness
        finetunableModels={[gatedRecipe, publicRecipe]}
      />,
    );

    expect(
      screen.getByTestId('model-select-example/gated-model-description'),
    ).toHaveTextContent('aimCatalog.card.gated•MI300X');
    expect(
      screen.getByTestId('model-select-example/public-model-description'),
    ).toHaveTextContent('MI325X');
    expect(screen.getAllByText('aimCatalog.card.gated')).toHaveLength(1);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
});

describe('createModelStepSchema', () => {
  it('requires a base model', () => {
    const schema = createModelStepSchema({
      finetunableModels: [],
      requiredModelMessage: 'required',
      requiredTokenMessage: 'token required',
    });

    expect(
      schema.safeParse({ canonicalName: '', hfTokenSecretName: '' }).success,
    ).toBe(false);
  });

  it('requires a token for a gated recipe', () => {
    const schema = createModelStepSchema({
      finetunableModels: [recipe(true)],
      requiredModelMessage: 'required',
      requiredTokenMessage: 'token required',
    });

    expect(
      schema.safeParse({
        canonicalName: 'example/model',
        hfTokenSecretName: '',
      }).success,
    ).toBe(false);
    expect(
      schema.safeParse({
        canonicalName: 'example/model',
        hfTokenSecretName: 'hf-token',
      }).success,
    ).toBe(true);
  });

  it('does not require a token for local fine-tuned weights', () => {
    const model = {
      name: 'Fine-tuned model',
      canonicalName: 'example/model',
      sourceUri: 's3://models/fine-tuned',
      hfTokenRequired: true,
    } satisfies Model;
    const schema = createModelStepSchema({
      finetunableModels: [recipe(true)],
      model,
      requiredModelMessage: 'required',
      requiredTokenMessage: 'token required',
    });

    expect(
      schema.safeParse({ canonicalName: '', hfTokenSecretName: '' }).success,
    ).toBe(true);
  });
});

describe('ModelStepSummary', () => {
  it('shows the Hugging Face token display name', () => {
    const hfTokens: SecretResponseData[] = [
      {
        metadata: {
          name: 'my-token-secret',
          namespace: 'default',
          creationTimestamp: '',
        },
        useCase: SecretUseCase.HUGGING_FACE,
        displayName: 'My HF Token',
      },
    ];

    render(
      <ModelStepSummary
        data={{
          ...DEFAULT_FINETUNE_VALUES,
          canonicalName: 'example/model',
          hfTokenSecretName: 'my-token-secret',
        }}
        finetunableModels={[recipe(true)]}
        hfTokens={hfTokens}
      />,
    );

    expect(screen.getByText('My HF Token')).toBeInTheDocument();
    expect(screen.queryByText('my-token-secret')).not.toBeInTheDocument();
  });
});
