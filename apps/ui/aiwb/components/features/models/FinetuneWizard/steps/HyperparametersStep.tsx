// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  FormNumberInput,
  FormSwitch,
  Wizard,
} from '@amdenterpriseai/components';
import { useTranslation } from 'next-i18next';
import type { UseFormReturn } from 'react-hook-form';
import { z } from 'zod';

import type { FinetunableModel, Model } from '@/types/models';

import {
  getRecipeGpuCount,
  getRecipeHyperparameters,
  type FinetuneFormValues,
} from '../types';

export const hyperparametersStepSchema = z.object({
  customizeHyperparameters: z.boolean(),
  batchSize: z.number().int().min(1).max(128).optional(),
  epochs: z.number().int().min(1).max(10).optional(),
  learningRate: z.number().min(0.1).max(10).optional(),
  loraRank: z.number().int().min(1).max(512).optional(),
  loraAlpha: z.number().int().min(1).optional(),
  loraDropout: z.number().min(0).lt(1).optional(),
});

export const HyperparametersStepFields = ({
  form,
  model,
  finetunableModels,
}: {
  form: UseFormReturn<FinetuneFormValues>;
  model?: Model;
  finetunableModels: FinetunableModel[];
}) => {
  const { t } = useTranslation('models');
  const customizeHyperparameters = form.watch('customizeHyperparameters');
  const isLora = form.watch('fineTuningType') === 'lora';
  const gpuCount = getRecipeGpuCount(
    finetunableModels,
    form.watch('canonicalName'),
    model,
  );
  const hyperparameters = getRecipeHyperparameters(
    finetunableModels,
    form.watch('canonicalName'),
    model,
  );
  const placeholder = (
    value: number | null | undefined,
    fallback: string,
  ): string => (value == null ? fallback : String(value));

  return (
    <>
      <FormSwitch
        form={form}
        name="customizeHyperparameters"
        data-testid="customize-hyperparameters-toggle"
      >
        {t('finetuneWizard.fields.hyperparameters.customize')}
      </FormSwitch>
      {customizeHyperparameters ? (
        <div
          className="flex flex-col gap-4 "
          data-testid="finetune-hyperparameters"
        >
          <div className="flex flex-row gap-3 items-end">
            <div className="w-40 shrink-0">
              <FormNumberInput
                form={form}
                name="batchSize"
                label={t('finetuneWizard.fields.batchSize.label')}
                placeholder={placeholder(
                  hyperparameters?.batchSize,
                  t('finetuneWizard.fields.batchSize.placeholder'),
                )}
                emptyValue={hyperparameters?.batchSize ?? undefined}
                step={gpuCount}
                minValue={gpuCount}
                maxValue={128}
              />
            </div>

            <div className="text-muted text-xs min-h-9">
              {t('finetuneWizard.fields.batchSize.description')}
            </div>
          </div>
          <div className="flex flex-row gap-3 items-end">
            <div className="w-40 shrink-0">
              <FormNumberInput
                form={form}
                name="epochs"
                label={t('finetuneWizard.fields.epochs.label')}
                placeholder={placeholder(
                  hyperparameters?.epochs,
                  t('finetuneWizard.fields.epochs.placeholder'),
                )}
                emptyValue={hyperparameters?.epochs ?? undefined}
                minValue={1}
                maxValue={10}
              />
            </div>
            <div className="text-muted text-xs min-h-9">
              {t('finetuneWizard.fields.epochs.description')}
            </div>
          </div>
          <div className="flex flex-row gap-4 items-end">
            <div className="w-40 shrink-0">
              <FormNumberInput
                form={form}
                name="learningRate"
                label={t('finetuneWizard.fields.learningRate.label')}
                placeholder={placeholder(
                  hyperparameters?.learningRate,
                  t('finetuneWizard.fields.learningRate.placeholder'),
                )}
                emptyValue={hyperparameters?.learningRate ?? undefined}
                step={0.1}
                minValue={0.1}
                maxValue={10}
              />
            </div>
            <div className="text-muted text-xs min-h-9">
              {t('finetuneWizard.fields.learningRate.description')}
            </div>
          </div>
          {isLora ? (
            <div className="flex flex-col gap-4 mt-4">
              <h4 className="text-sm font-medium text-muted">
                {t('finetuneWizard.fields.hyperparameters.loraSectionTitle')}
              </h4>
              <div className="flex flex-row gap-3 items-end">
                <div className="w-40 shrink-0">
                  <FormNumberInput
                    form={form}
                    name="loraAlpha"
                    label={t('finetuneWizard.fields.loraAlpha.label')}
                    placeholder={placeholder(
                      hyperparameters?.lora?.alpha,
                      t('finetuneWizard.fields.loraAlpha.placeholder'),
                    )}
                    emptyValue={hyperparameters?.lora?.alpha ?? undefined}
                    step={1}
                    minValue={1}
                  />
                </div>
                <div className="text-muted text-xs min-h-9">
                  {t('finetuneWizard.fields.loraAlpha.description')}
                </div>
              </div>
              <div className="flex flex-row gap-3 items-end">
                <div className="w-40 shrink-0">
                  <FormNumberInput
                    form={form}
                    name="loraRank"
                    label={t('finetuneWizard.fields.loraRank.label')}
                    placeholder={placeholder(
                      hyperparameters?.lora?.rank,
                      t('finetuneWizard.fields.loraRank.placeholder'),
                    )}
                    emptyValue={hyperparameters?.lora?.rank ?? undefined}
                    minValue={1}
                    maxValue={512}
                  />
                </div>
                <div className="text-muted text-xs min-h-9">
                  {t('finetuneWizard.fields.loraRank.description')}
                </div>
              </div>
              <div className="flex flex-row gap-3 items-end">
                <div className="w-40 shrink-0">
                  <FormNumberInput
                    form={form}
                    name="loraDropout"
                    label={t('finetuneWizard.fields.loraDropout.label')}
                    placeholder={placeholder(
                      hyperparameters?.lora?.dropout,
                      t('finetuneWizard.fields.loraDropout.placeholder'),
                    )}
                    emptyValue={hyperparameters?.lora?.dropout ?? undefined}
                    step={0.001}
                    minValue={0}
                    maxValue={0.999}
                  />
                </div>
                <div className="text-muted text-xs min-h-9">
                  {t('finetuneWizard.fields.loraDropout.description')}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </>
  );
};

export const HyperparametersStepSummary = ({
  data,
  model,
  finetunableModels,
}: {
  data: FinetuneFormValues;
  model?: Model;
  finetunableModels: FinetunableModel[];
}) => {
  const { t } = useTranslation('models');
  const automatic = t('finetuneWizard.summary.automatic');
  const hyperparameters = getRecipeHyperparameters(
    finetunableModels,
    data.canonicalName,
    model,
  );
  const resolvedValue = (
    value: number | undefined,
    recipeValue: number | null | undefined,
  ): number | string =>
    (data.customizeHyperparameters ? value : undefined) ??
    recipeValue ??
    automatic;
  const formattedValue = (
    value: number | undefined,
    recipeValue: number | null | undefined,
    fractionDigits?: number,
  ): number | string => {
    const resolved = resolvedValue(value, recipeValue);
    return typeof resolved === 'number' && fractionDigits !== undefined
      ? resolved.toFixed(fractionDigits)
      : resolved;
  };

  return (
    <>
      <Wizard.SummaryRow
        label={t('finetuneWizard.summary.hyperparameters')}
        value={
          data.customizeHyperparameters
            ? t('finetuneWizard.summary.customized')
            : automatic
        }
      />
      <Wizard.SummaryRow
        label={t('finetuneWizard.fields.batchSize.label')}
        value={resolvedValue(data.batchSize, hyperparameters?.batchSize)}
      />
      <Wizard.SummaryRow
        label={t('finetuneWizard.fields.epochs.label')}
        value={resolvedValue(data.epochs, hyperparameters?.epochs)}
      />
      <Wizard.SummaryRow
        label={t('finetuneWizard.fields.learningRate.label')}
        value={formattedValue(
          data.learningRate,
          hyperparameters?.learningRate,
          1,
        )}
      />
      {data.fineTuningType === 'lora' && hyperparameters?.lora ? (
        <>
          <Wizard.SummaryRow
            label={t('finetuneWizard.fields.loraRank.label')}
            value={resolvedValue(data.loraRank, hyperparameters.lora.rank)}
          />
          <Wizard.SummaryRow
            label={t('finetuneWizard.fields.loraAlpha.label')}
            value={resolvedValue(data.loraAlpha, hyperparameters.lora.alpha)}
          />
          <Wizard.SummaryRow
            label={t('finetuneWizard.fields.loraDropout.label')}
            value={formattedValue(
              data.loraDropout,
              hyperparameters.lora.dropout,
              3,
            )}
          />
        </>
      ) : null}
    </>
  );
};
