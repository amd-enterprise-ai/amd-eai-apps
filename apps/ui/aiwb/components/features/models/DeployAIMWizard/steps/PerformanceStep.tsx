// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  FormInput,
  FormRadioGroup,
  Radio,
  Wizard,
} from '@amdenterpriseai/components';
import type { UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'next-i18next';
import { z } from 'zod';

import { getMetricTranslationKey } from '@/lib/app/aims';
import {
  ADVANCED_PARAM_AUTOMATIC,
  filterProfilesByAdvancedParams,
  formatAccelerator,
  formatClass,
} from '@/lib/app/aims/filterProfilesByAdvancedParams';
import {
  AIM_PROFILE_TYPE_OPTIMIZED,
  type AIMClusterProfile,
} from '@/types/aims';

import { AdvancedProfileFields } from '../AdvancedProfileFields';
import {
  UnoptimizedAlert,
  UnoptimizedProfileBadge,
} from '../UnoptimizedProfileBadge';
import {
  PERFORMANCE_MODE_ADVANCED,
  type AdvancedProfileOptions,
  type DeployAIMFormValues,
} from '../types';

export const performanceStepSchema = z.object({
  displayName: z.union([z.literal(''), z.string().min(2).max(253)]).optional(),
  performanceMode: z.enum(['latency', 'throughput', PERFORMANCE_MODE_ADVANCED]),
  optimizationClass: z.string().optional(),
  gpuModel: z.string().optional(),
  precision: z.string().optional(),
  gpuCount: z.string().optional(),
  profileName: z.string().optional(),
});

export const performanceStepDefaults: Partial<DeployAIMFormValues> = {
  displayName: '',
  performanceMode: 'latency',
  optimizationClass: ADVANCED_PARAM_AUTOMATIC,
  gpuModel: ADVANCED_PARAM_AUTOMATIC,
  precision: ADVANCED_PARAM_AUTOMATIC,
  gpuCount: ADVANCED_PARAM_AUTOMATIC,
  profileName: ADVANCED_PARAM_AUTOMATIC,
};

type PerformanceStepFieldsProps = {
  form: UseFormReturn<DeployAIMFormValues>;
  metricsStatusMap: Record<string, boolean>;
  isAtleastOneOptimized: boolean;
  profilesLoading: boolean;
  advancedProfileOptions: AdvancedProfileOptions;
};

export const PerformanceStepFields = ({
  form,
  metricsStatusMap,
  isAtleastOneOptimized,
  profilesLoading,
  advancedProfileOptions,
}: PerformanceStepFieldsProps) => {
  const { t } = useTranslation('models');
  const [performanceMode, optimizationClass, gpuModel, precision, gpuCount] =
    form.watch([
      'performanceMode',
      'optimizationClass',
      'gpuModel',
      'precision',
      'gpuCount',
    ]);
  const selectedMetric =
    performanceMode === PERFORMANCE_MODE_ADVANCED ? undefined : performanceMode;
  const filteredProfiles = filterProfilesByAdvancedParams(
    advancedProfileOptions.profiles,
    {
      selectedMetric,
      optimizationClass,
      gpuModel,
      precision,
      gpuCount,
    },
  );
  const noProfileMatches = !profilesLoading && filteredProfiles.length === 0;
  const hasNoProfiles = advancedProfileOptions.profiles.length === 0;
  const selectedMetricOptimized =
    !selectedMetric || metricsStatusMap[selectedMetric] === true;
  const showWarning =
    performanceMode !== PERFORMANCE_MODE_ADVANCED &&
    (!isAtleastOneOptimized || !selectedMetricOptimized);

  return (
    <>
      <FormInput<DeployAIMFormValues>
        name="displayName"
        form={form}
        label={t('deployAIM.fields.displayName.title')}
        placeholder={t('deployAIM.fields.displayName.placeholder')}
      />
      <FormRadioGroup
        name="performanceMode"
        orientation="horizontal"
        form={form}
        label={t('deployAIM.fields.metric.title')}
        tooltipContent={t('deployAIM.fields.metric.description')}
        data-testid="deployAimPerformanceModeGroup"
      >
        {(['latency', 'throughput'] as const).map((metric) => (
          <Radio
            key={metric}
            value={metric}
            className="flex-1"
            description={t(
              `deployAIM.fields.metric.options.${metric}.description`,
            )}
            isDisabled={hasNoProfiles || metricsStatusMap[metric] === undefined}
            data-testid={`deployAimPerformanceMode-${metric}`}
          >
            <span className="inline-flex items-center gap-2 capitalize">
              {t(getMetricTranslationKey(metric))}
              {metricsStatusMap[metric] === false ? (
                <UnoptimizedProfileBadge />
              ) : null}
            </span>
          </Radio>
        ))}
        <Radio
          value={PERFORMANCE_MODE_ADVANCED}
          className="flex-1"
          description={t(
            'deployAIM.fields.metric.options.advanced.description',
          )}
          isDisabled={hasNoProfiles}
          data-testid="deployAimPerformanceMode-advanced"
        >
          {t('deployAIM.fields.metric.options.advanced.label')}
        </Radio>
      </FormRadioGroup>
      {performanceMode === PERFORMANCE_MODE_ADVANCED ? (
        <AdvancedProfileFields
          form={form}
          advancedProfileOptions={advancedProfileOptions}
          filteredProfiles={filteredProfiles}
          noProfileMatches={noProfileMatches}
        />
      ) : null}
      {showWarning ? (
        <UnoptimizedAlert hasOptimizedAlternative={isAtleastOneOptimized} />
      ) : null}
    </>
  );
};

type PerformanceStepSummaryProps = {
  data: DeployAIMFormValues;
  readyProfiles: AIMClusterProfile[];
};

export const PerformanceStepSummary = ({
  data,
  readyProfiles,
}: PerformanceStepSummaryProps) => {
  const { t } = useTranslation('models');
  const isAdvancedMode = data.performanceMode === PERFORMANCE_MODE_ADVANCED;

  const matches = filterProfilesByAdvancedParams(readyProfiles, {
    selectedMetric: isAdvancedMode ? undefined : data.performanceMode,
    profileName: isAdvancedMode ? data.profileName : undefined,
    optimizationClass: isAdvancedMode ? data.optimizationClass : undefined,
    gpuModel: isAdvancedMode ? data.gpuModel : undefined,
    precision: isAdvancedMode ? data.precision : undefined,
    gpuCount: isAdvancedMode ? data.gpuCount : undefined,
  });
  const isAnyMatchOptimized = matches.some(
    (p) => p.spec?.type === AIM_PROFILE_TYPE_OPTIMIZED,
  );
  const showWarning = matches.length > 0 && !isAnyMatchOptimized;
  const resolvedProfile = matches.length === 1 ? matches[0] : undefined;
  const modelHasAnyOptimizedProfile = readyProfiles.some(
    (p) => p.spec?.type === AIM_PROFILE_TYPE_OPTIMIZED,
  );

  const metricValue =
    isAdvancedMode && resolvedProfile?.spec?.metric
      ? t(getMetricTranslationKey(String(resolvedProfile.spec.metric)))
      : isAdvancedMode
        ? t('deployAIM.fields.metric.options.advanced.label')
        : t(getMetricTranslationKey(data.performanceMode));

  const precisionValue = resolvedProfile
    ? resolvedProfile.spec?.precision
    : data.precision && data.precision !== ADVANCED_PARAM_AUTOMATIC
      ? data.precision
      : undefined;

  return (
    <>
      {data.displayName ? (
        <Wizard.SummaryRow
          label={t('deployAIM.summary.displayName')}
          value={data.displayName}
        />
      ) : null}
      <Wizard.SummaryRow
        label={t('deployAIM.summary.metric')}
        value={metricValue}
      />
      {precisionValue ? (
        <Wizard.SummaryRow
          label={t('deployAIM.summary.precision')}
          value={precisionValue}
        />
      ) : null}
      {resolvedProfile ? (
        <>
          <Wizard.SummaryRow
            label={t('deployAIM.summary.accelerator')}
            value={formatAccelerator(resolvedProfile)}
          />
          <Wizard.SummaryRow
            label={t('deployAIM.summary.optimizationClass')}
            value={formatClass(resolvedProfile.spec?.type ?? undefined)}
          />
        </>
      ) : null}
      {showWarning ? (
        <UnoptimizedAlert
          hasOptimizedAlternative={modelHasAnyOptimizedProfile}
        />
      ) : null}
    </>
  );
};
