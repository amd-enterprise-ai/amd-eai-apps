// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Alert,
  FormSelect,
  SelectItem,
  Wizard,
} from '@amdenterpriseai/components';
import { IconLock } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';
import { useEffect } from 'react';
import { Controller, type UseFormReturn } from 'react-hook-form';
import { z } from 'zod';

import { ProjectHuggingFaceTokenSelector } from '@/components/shared/HuggingFaceTokenSelector';
import type { FinetunableModel, Model } from '@/types/models';
import type { SecretResponseData } from '@/types/secrets';

import { isBaseModelGated, type FinetuneFormValues } from '../types';

export const createModelStepSchema = ({
  finetunableModels,
  model,
  requiredModelMessage,
  requiredTokenMessage,
}: {
  finetunableModels: FinetunableModel[];
  model?: Model;
  requiredModelMessage: string;
  requiredTokenMessage: string;
}) =>
  z
    .object({
      canonicalName: z.string().default(''),
      hfTokenSecretName: z.string().default(''),
    })
    .superRefine((data, context) => {
      const canonicalName = data.canonicalName || model?.canonicalName;
      if (!canonicalName) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: requiredModelMessage,
          path: ['canonicalName'],
        });
        return;
      }
      if (
        !model?.sourceUri &&
        isBaseModelGated(finetunableModels, canonicalName, model) &&
        !data.hfTokenSecretName
      ) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: requiredTokenMessage,
          path: ['hfTokenSecretName'],
        });
      }
    });

type ModelStepFieldsProps = {
  form: UseFormReturn<FinetuneFormValues>;
  model?: Model;
  finetunableModels: FinetunableModel[];
  namespace: string;
};

export const ModelStepFields = ({
  form,
  model,
  finetunableModels,
  namespace,
}: ModelStepFieldsProps) => {
  const { t } = useTranslation('models');
  const canonicalName = form.watch('canonicalName');
  const showTokenSelector =
    !model?.sourceUri &&
    Boolean(canonicalName || model) &&
    isBaseModelGated(finetunableModels, canonicalName, model);

  useEffect(() => {
    form.setValue('batchSize', undefined);
  }, [canonicalName, form]);

  return (
    <>
      <FormSelect
        form={form}
        disallowEmptySelection
        isDisabled={Boolean(model) || finetunableModels.length === 0}
        isRequired
        name="canonicalName"
        label={t('finetuneWizard.fields.baseModel.label')}
        placeholder={
          model
            ? model.name
            : finetunableModels.length === 0
              ? t('finetuneWizard.fields.baseModel.noCompatibleRecipes')
              : t('finetuneWizard.fields.baseModel.placeholder')
        }
        data-testid="baseModelSelect"
      >
        {finetunableModels.map((finetunableModel) => (
          <SelectItem
            key={finetunableModel.canonicalName}
            data-testid={`model-select-${finetunableModel.canonicalName}`}
            description={
              finetunableModel.hfTokenRequired ? (
                <span className="flex items-center gap-1">
                  <span className="flex items-center gap-0.5">
                    <IconLock size={12} />
                    {t('aimCatalog.card.gated')}
                  </span>
                  {finetunableModel.compatibleAcceleratorNames.length > 0 ? (
                    <>
                      <span>&bull;</span>
                      {finetunableModel.compatibleAcceleratorNames.join(', ')}
                    </>
                  ) : null}
                </span>
              ) : finetunableModel.compatibleAcceleratorNames.length > 0 ? (
                finetunableModel.compatibleAcceleratorNames.join(', ')
              ) : undefined
            }
          >
            {finetunableModel.canonicalName}
          </SelectItem>
        ))}
      </FormSelect>

      {showTokenSelector ? (
        <>
          <Alert
            status="warning"
            title={t('finetuneWizard.fields.huggingFaceToken.title')}
            description={t(
              'finetuneWizard.fields.huggingFaceToken.description',
            )}
          />
          <Controller
            control={form.control}
            name="hfTokenSecretName"
            render={({ field, fieldState }) => (
              <ProjectHuggingFaceTokenSelector
                namespace={namespace}
                value={field.value || null}
                onChange={field.onChange}
                isRequired
                isInvalid={Boolean(fieldState.error?.message)}
                errorMessage={fieldState.error?.message}
              />
            )}
          />
        </>
      ) : null}
    </>
  );
};

export const ModelStepSummary = ({
  data,
  model,
  finetunableModels,
  hfTokens,
}: {
  data: FinetuneFormValues;
  model?: Model;
  finetunableModels: FinetunableModel[];
  hfTokens: SecretResponseData[];
}) => {
  const { t } = useTranslation('models');
  const canonicalName = data.canonicalName || model?.canonicalName;
  const hfTokenDisplayName =
    hfTokens.find((secret) => secret.metadata.name === data.hfTokenSecretName)
      ?.displayName ?? data.hfTokenSecretName;

  return (
    <>
      <Wizard.SummaryRow
        label={t('finetuneWizard.summary.baseModel')}
        value={model?.name || canonicalName}
      />
      {!model?.sourceUri &&
      isBaseModelGated(finetunableModels, canonicalName, model) ? (
        <Wizard.SummaryRow
          label={t('finetuneWizard.summary.hfToken')}
          value={hfTokenDisplayName}
        />
      ) : null}
    </>
  );
};
