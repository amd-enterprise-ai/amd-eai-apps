// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

/**
 * Reusable autoscaling form fields component.
 * Used in both deployment drawer and workload settings drawer.
 */

import {
  SelectItem,
  FormNumberInput,
  FormRangeSlider,
  FormSelect,
} from '@amdenterpriseai/components';
import { useTranslation } from 'next-i18next';
import type { UseFormReturn } from 'react-hook-form';

import {
  AIM_MAX_REPLICAS,
  DEFAULT_AUTOSCALING,
  SCALING_METRIC_KEYS,
  AGGREGATION_OPTION_KEYS,
  TARGET_TYPE_OPTION_KEYS,
} from '@/lib/app/aims';

interface Props {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  form: UseFormReturn<any>;
  className?: string;
}

export const AutoscalingFormFields = ({ form, className }: Props) => {
  const { t } = useTranslation('autoscaling');

  const minReplicas =
    form.watch('minReplicas') ?? DEFAULT_AUTOSCALING.minReplicas;
  const maxReplicas =
    form.watch('maxReplicas') ?? DEFAULT_AUTOSCALING.maxReplicas;
  const metricQuery = form.watch('metricQuery');
  const operationOverTime = form.watch('operationOverTime');
  const targetType = form.watch('targetType');

  // Autoscaling can be configured via CLI with values the UI doesn't offer,
  // so we detect custom values to render them as selectable options.
  const isCustomMetric =
    metricQuery && !SCALING_METRIC_KEYS.some((m) => m.key === metricQuery);
  const isCustomAggregation =
    operationOverTime &&
    !AGGREGATION_OPTION_KEYS.some((o) => o.key === operationOverTime);
  const isCustomTargetType =
    targetType && !TARGET_TYPE_OPTION_KEYS.some((o) => o.key === targetType);

  const getScalingMetricDescription = () => {
    if (isCustomMetric) return '';
    const metric =
      SCALING_METRIC_KEYS.find((m) => m.key === metricQuery) ??
      SCALING_METRIC_KEYS[0];
    return t(`scalingMetric.descriptions.${metric.translationKey}`);
  };

  // Get description for target value based on target type
  const getTargetValueDescription = () => {
    if (isCustomTargetType) return '';
    if (targetType === 'AverageValue') {
      return t('targetValue.descriptions.averageValue');
    }
    return t('targetValue.descriptions.value');
  };

  return (
    <div className={className || 'flex flex-col gap-4'}>
      {/* Replica Range Slider */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-sm text-foreground">{t('replicaRange')}</span>
          <span className="text-sm text-muted">
            {minReplicas} - {maxReplicas}
          </span>
        </div>
        <FormRangeSlider
          data-testid="replica-range-slider"
          aria-label={t('replicaRange')}
          form={form}
          minName="minReplicas"
          maxName="maxReplicas"
          step={1}
          minValue={1}
          maxValue={AIM_MAX_REPLICAS}
          className="max-w-full"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <FormSelect
          data-testid="scaling-metric-select"
          form={form}
          name="metricQuery"
          label={t('scalingMetric.label')}
          placeholder={t('scalingMetric.placeholder')}
          description={getScalingMetricDescription()}
        >
          {SCALING_METRIC_KEYS.map((metric) => (
            <SelectItem key={metric.key}>
              {t(`scalingMetric.options.${metric.translationKey}`)}
            </SelectItem>
          ))}
          {isCustomMetric && (
            <SelectItem key={metricQuery}>{metricQuery}</SelectItem>
          )}
        </FormSelect>

        <FormSelect
          data-testid="aggregation-select"
          form={form}
          name="operationOverTime"
          label={t('aggregation.label')}
          placeholder={t('aggregation.placeholder')}
          description={isCustomAggregation ? '' : t('aggregation.description')}
        >
          {AGGREGATION_OPTION_KEYS.map((option) => (
            <SelectItem
              key={option.key}
              description={t(`aggregation.tooltips.${option.translationKey}`)}
            >
              {t(`aggregation.options.${option.translationKey}`)}
            </SelectItem>
          ))}
          {isCustomAggregation && (
            <SelectItem key={operationOverTime}>{operationOverTime}</SelectItem>
          )}
        </FormSelect>

        <FormSelect
          data-testid="target-type-select"
          form={form}
          name="targetType"
          label={t('targetType.label')}
        >
          {TARGET_TYPE_OPTION_KEYS.map((option) => (
            <SelectItem
              key={option.key}
              description={t(`targetType.tooltips.${option.translationKey}`)}
            >
              {t(`targetType.options.${option.translationKey}`)}
            </SelectItem>
          ))}
          {isCustomTargetType && (
            <SelectItem key={targetType}>{targetType}</SelectItem>
          )}
        </FormSelect>

        <FormNumberInput
          data-testid="target-value-input"
          form={form}
          name="targetValue"
          label={t('targetValue.label')}
          minValue={1}
          description={getTargetValueDescription()}
        />
      </div>
    </div>
  );
};

export default AutoscalingFormFields;
