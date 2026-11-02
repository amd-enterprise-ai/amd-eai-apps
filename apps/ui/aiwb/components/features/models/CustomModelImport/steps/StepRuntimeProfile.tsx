// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { FormTextarea, Link } from '@amdenterpriseai/components';
import { useTranslation, Trans } from 'next-i18next';
import type { UseFormReturn } from 'react-hook-form';

import type { RuntimeProfileCatalogState } from '@/hooks/useRuntimeProfileCatalog';

import {
  RuntimeProfileFields,
  type RuntimeProfileSelectionState,
} from '../../runtime-profile';
import type { CustomModelImportFormValues } from '../types';

interface Props {
  form: UseFormReturn<CustomModelImportFormValues>;
  catalog: RuntimeProfileCatalogState;
  /**
   * Edit mode: runtime edits require a derived AIMProfile, which only exists
   * once the model finishes importing. While it is missing the fields render
   * disabled and {@link disabledNotice} explains why.
   */
  isDisabled?: boolean;
  disabledNotice?: string;
  /** Lifts the runtime-selection block so the wizard can gate its Next/submit. */
  onSelectionStateChange?: (state: RuntimeProfileSelectionState) => void;
}

const ENGINE_ARGS_REFERENCE_URL =
  'https://docs.vllm.ai/en/stable/configuration/engine_args/';
const ENV_VARS_REFERENCE_URL =
  'https://docs.vllm.ai/en/stable/configuration/env_vars/';
const PUBLISHED_AIM_PROFILES_URL =
  'https://github.com/amd-enterprise-ai/aim-build/tree/main/assets';

const SectionHeader = ({ title }: { title: string }) => (
  <h3 className="text-base font-semibold">{title}</h3>
);

/**
 * Step 3 — runtime configuration for the import. Profile parameters are
 * sourced from cluster catalog APIs; engine args and env vars use YAML textareas.
 */
export const StepRuntimeProfile = ({
  form,
  catalog,
  isDisabled = false,
  disabledNotice,
  onSelectionStateChange,
}: Props) => {
  const { t } = useTranslation('models', {
    keyPrefix: 'customModels.import.steps.runtime',
  });
  const catalogDisabled = catalog.isLoading || catalog.isError || isDisabled;
  const fieldLabels = {
    containerImage: {
      label: t('fields.containerImage.label'),
      placeholder: t('fields.containerImage.placeholder'),
    },
    containerVersion: {
      label: t('fields.containerVersion.label'),
      placeholder: t('fields.containerVersion.placeholder'),
    },
    acceleratorType: {
      label: t('fields.acceleratorType.label'),
      placeholder: t('fields.acceleratorType.placeholder'),
    },
    accelerator: {
      label: t('fields.accelerator.label'),
      placeholder: t('fields.accelerator.placeholder'),
    },
    acceleratorCount: {
      label: t('fields.acceleratorCount.label'),
    },
    modelPrecision: {
      label: t('fields.modelPrecision.label'),
      placeholder: t('fields.modelPrecision.placeholder'),
    },
    catalogLoading: t('catalog.loading'),
    catalogError: t('catalog.error'),
    catalogRetry: t('catalog.retry'),
    baseImageOptionsWarning: t('catalog.baseImageOptionsWarning'),
    noValidCombinationsWarning: t('catalog.noValidCombinations'),
    emptyAccelerators: t('catalog.emptyAccelerators'),
  };

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold">{t('title')}</h2>
      </header>

      {isDisabled && disabledNotice && (
        <div
          className="rounded-medium border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-foreground"
          data-testid="custom-model-import-runtime-disabled-notice"
        >
          {disabledNotice}
        </div>
      )}

      <section className="flex flex-col gap-4">
        <SectionHeader title={t('profileParameters.title')} />
        <p className="text-sm text-muted">{t('profileParameters.subtitle')}</p>
        <RuntimeProfileFields
          form={form}
          catalog={catalog}
          labels={fieldLabels}
          isDisabled={isDisabled}
          onSelectionStateChange={onSelectionStateChange}
        />
      </section>

      <section className="flex flex-col gap-4">
        <SectionHeader title={t('engineArguments.title')} />
        <p className="text-sm text-foreground">
          <Trans
            i18nKey="customModels.import.steps.runtime.engineArguments.body"
            ns="models"
            components={{
              docs: (
                <Link
                  href={ENGINE_ARGS_REFERENCE_URL}
                  isExternal
                  showAnchorIcon={false}
                  className="text-accent underline"
                />
              ),
              profiles: (
                <Link
                  href={PUBLISHED_AIM_PROFILES_URL}
                  isExternal
                  showAnchorIcon={false}
                  className="text-accent underline"
                />
              ),
            }}
          />
        </p>
        <FormTextarea<CustomModelImportFormValues>
          form={form}
          name="engineArgsYaml"
          label={t('engineArguments.field.label')}
          placeholder={t('engineArguments.field.placeholder')}
          minRows={4}
          isDisabled={catalogDisabled}
          data-testid="custom-model-import-engine-args-yaml"
        />
      </section>

      <section className="flex flex-col gap-4">
        <SectionHeader title={t('environmentVariables.title')} />
        <p className="text-sm text-foreground">
          <Trans
            i18nKey="customModels.import.steps.runtime.environmentVariables.body"
            ns="models"
            components={{
              docs: (
                <Link
                  href={ENV_VARS_REFERENCE_URL}
                  isExternal
                  showAnchorIcon={false}
                  className="text-accent underline"
                />
              ),
              profiles: (
                <Link
                  href={PUBLISHED_AIM_PROFILES_URL}
                  isExternal
                  showAnchorIcon={false}
                  className="text-accent underline"
                />
              ),
            }}
          />
        </p>
        <FormTextarea<CustomModelImportFormValues>
          form={form}
          name="envVarsYaml"
          label={t('environmentVariables.field.label')}
          placeholder={t('environmentVariables.field.placeholder')}
          minRows={4}
          isDisabled={catalogDisabled}
          data-testid="custom-model-import-env-vars-yaml"
        />
      </section>
    </div>
  );
};

export default StepRuntimeProfile;
