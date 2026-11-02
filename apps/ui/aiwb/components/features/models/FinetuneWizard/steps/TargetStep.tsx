// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { FormInput, Spinner, Wizard } from '@amdenterpriseai/components';
import { useTranslation } from 'next-i18next';
import type { UseFormReturn } from 'react-hook-form';
import { z } from 'zod';

import {
  FINE_TUNING_TYPES,
  type FineTuningType,
  MAX_DESCRIPTION_LENGTH,
  MAX_DISPLAY_NAME_LENGTH,
  type FinetuneFormValues,
} from '../types';

export const createTargetStepFieldsSchema = ({
  requiredMessage,
  tooLongMessage,
  descriptionTooLongMessage,
}: {
  requiredMessage: string;
  tooLongMessage: string;
  descriptionTooLongMessage: string;
}) =>
  z.object({
    displayName: z
      .string()
      .trim()
      .min(1, requiredMessage)
      .max(MAX_DISPLAY_NAME_LENGTH, tooLongMessage),
    description: z
      .string()
      .trim()
      .max(MAX_DESCRIPTION_LENGTH, descriptionTooLongMessage),
    fineTuningType: z.enum(FINE_TUNING_TYPES),
  });

export const createTargetStepSchema = ({
  requiredMessage,
  tooLongMessage,
  descriptionTooLongMessage,
  duplicateModelMessage,
  duplicateLoraMessage,
  checkNameAvailable,
}: {
  requiredMessage: string;
  tooLongMessage: string;
  descriptionTooLongMessage: string;
  duplicateModelMessage: string;
  duplicateLoraMessage: string;
  checkNameAvailable: (
    name: string,
    fineTuningType: FineTuningType,
  ) => Promise<boolean>;
}) =>
  createTargetStepFieldsSchema({
    requiredMessage,
    tooLongMessage,
    descriptionTooLongMessage,
  }).superRefine(async ({ displayName, fineTuningType }, context) => {
    if (!displayName || displayName.length > MAX_DISPLAY_NAME_LENGTH) return;
    if (await checkNameAvailable(displayName, fineTuningType)) return;
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['displayName'],
      message:
        fineTuningType === 'lora'
          ? duplicateLoraMessage
          : duplicateModelMessage,
    });
  });

type TargetStepFieldsProps = {
  form: UseFormReturn<FinetuneFormValues>;
  uniqueCheckInProgress: boolean;
};

export const TargetStepFields = ({
  form,
  uniqueCheckInProgress,
}: TargetStepFieldsProps) => {
  const { t } = useTranslation('models');
  const isLora = form.watch('fineTuningType') === 'lora';

  return (
    <>
      <FormInput
        form={form}
        name="displayName"
        label={t(
          isLora
            ? 'finetuneWizard.fields.loraName.label'
            : 'finetuneWizard.fields.modelName.label',
        )}
        placeholder={t(
          isLora
            ? 'finetuneWizard.fields.loraName.placeholder'
            : 'finetuneWizard.fields.modelName.placeholder',
        )}
        isRequired
        endContent={
          uniqueCheckInProgress ? (
            <Spinner size="sm" color="primary" />
          ) : undefined
        }
      />
      <FormInput
        form={form}
        name="description"
        label={t(
          isLora
            ? 'finetuneWizard.fields.loraDescription.label'
            : 'finetuneWizard.fields.description.label',
        )}
        placeholder={t(
          isLora
            ? 'finetuneWizard.fields.loraDescription.placeholder'
            : 'finetuneWizard.fields.description.placeholder',
        )}
      />
    </>
  );
};

export const TargetStepSummary = ({ data }: { data: FinetuneFormValues }) => {
  const { t } = useTranslation('models');
  const isLora = data.fineTuningType === 'lora';
  return (
    <>
      <Wizard.SummaryRow
        label={t(
          isLora
            ? 'finetuneWizard.summary.loraName'
            : 'finetuneWizard.summary.modelName',
        )}
        value={data.displayName}
      />
      {data.description ? (
        <Wizard.SummaryRow
          label={t(
            isLora
              ? 'finetuneWizard.summary.loraDescription'
              : 'finetuneWizard.summary.description',
          )}
          value={data.description}
        />
      ) : null}
    </>
  );
};
