// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { FormSwitch, Wizard } from '@amdenterpriseai/components';
import type { UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'next-i18next';
import { z } from 'zod';

import { AutoscalingFormFields } from '@/components/features/models/AutoscalingFormFields';
import {
  AGGREGATION_OPTION_KEYS,
  DEFAULT_AUTOSCALING,
  SCALING_METRIC_KEYS,
  TARGET_TYPE_OPTION_KEYS,
} from '@/lib/app/aims';

import type { DeployAIMFormValues } from '../types';

export const scalingStepSchema = z
  .object({
    autoscalingEnabled: z.boolean(),
    minReplicas: z.number().min(1).max(30).optional(),
    maxReplicas: z.number().min(1).max(30).optional(),
    metricQuery: z.string().optional(),
    operationOverTime: z.string().optional(),
    targetType: z.string().optional(),
    targetValue: z.number().min(1).optional(),
  })
  .superRefine((data, ctx) => {
    if (
      data.autoscalingEnabled &&
      data.minReplicas &&
      data.maxReplicas &&
      data.minReplicas > data.maxReplicas
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Min replicas must be less than or equal to max replicas',
        path: ['maxReplicas'],
      });
    }
  });

export const scalingStepDefaults: Partial<DeployAIMFormValues> = {
  autoscalingEnabled: false,
  ...DEFAULT_AUTOSCALING,
};

type ScalingStepFieldsProps = {
  form: UseFormReturn<DeployAIMFormValues>;
};

export const ScalingStepFields = ({ form }: ScalingStepFieldsProps) => {
  const { t } = useTranslation('models');

  return (
    <>
      <FormSwitch
        form={form}
        name="autoscalingEnabled"
        data-testid="autoscaling-toggle"
      >
        {t('deployAIM.fields.autoscaling.enable')}
      </FormSwitch>
      {form.watch('autoscalingEnabled') ? (
        <AutoscalingFormFields
          form={form}
          className="flex flex-col gap-4 pl-1"
        />
      ) : null}
    </>
  );
};

type ScalingStepSummaryProps = {
  data: DeployAIMFormValues;
};

export const ScalingStepSummary = ({ data }: ScalingStepSummaryProps) => {
  const { t } = useTranslation('models');

  if (!data.autoscalingEnabled) {
    return (
      <Wizard.SummaryRow
        label={t('deployAIM.summary.autoscaling')}
        value={t('deployAIM.summary.disabled')}
      />
    );
  }
  const minReplicas = data.minReplicas ?? DEFAULT_AUTOSCALING.minReplicas;
  const maxReplicas = data.maxReplicas ?? DEFAULT_AUTOSCALING.maxReplicas;
  const translatedOption = (
    options: readonly { key: string; translationKey: string }[],
    value: string | undefined,
    prefix: string,
  ) => {
    const key = options.find((option) => option.key === value)?.translationKey;
    return key
      ? (t(`${prefix}.options.${key}` as never, {
          ns: 'autoscaling',
        }) as string)
      : value;
  };
  const targetValue = data.targetValue ?? DEFAULT_AUTOSCALING.targetValue;
  return (
    <>
      <Wizard.SummaryRow
        label={t('replicaRange', { ns: 'autoscaling' })}
        value={`${minReplicas} - ${maxReplicas}`}
      />
      <Wizard.SummaryRow
        label={t('scalingMetric.label', { ns: 'autoscaling' })}
        value={translatedOption(
          SCALING_METRIC_KEYS,
          data.metricQuery,
          'scalingMetric',
        )}
      />
      <Wizard.SummaryRow
        label={t('aggregation.label', { ns: 'autoscaling' })}
        value={translatedOption(
          AGGREGATION_OPTION_KEYS,
          data.operationOverTime,
          'aggregation',
        )}
      />
      <Wizard.SummaryRow
        label={t('targetType.label', { ns: 'autoscaling' })}
        value={translatedOption(
          TARGET_TYPE_OPTION_KEYS,
          data.targetType,
          'targetType',
        )}
      />
      <Wizard.SummaryRow
        label={t('targetValue.label', { ns: 'autoscaling' })}
        value={targetValue}
      />
    </>
  );
};
