// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Alert,
  FormSelect,
  SelectItem,
  Wizard,
} from '@amdenterpriseai/components';
import { useEffect } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { Controller } from 'react-hook-form';
import { useTranslation } from 'next-i18next';
import { z } from 'zod';

import { ProjectHuggingFaceTokenSelector } from '@/components/shared/HuggingFaceTokenSelector/ProjectHuggingFaceTokenSelector';
import { ModelIcon } from '@/components/shared/ModelIcons';
import type { AggregatedAIM, ParsedAIM } from '@/types/aims';
import type { SecretResponseData } from '@/types/secrets';
import { toSecretDisplayNames, toSecretNames } from '@/utils/secrets';

import type { DeployAIMFormValues } from '../types';

export const formatVersionLabel = (
  aim: ParsedAIM,
  t: (
    key:
      | 'deployAIM.fields.version.latest'
      | 'deployAIM.fields.version.unsupported',
  ) => string,
): string => {
  const labels = [aim.imageVersion];
  if (aim.isLatest) labels.push(`(${t('deployAIM.fields.version.latest')})`);
  if (aim.status !== 'Ready') {
    labels.push(`(${t('deployAIM.fields.version.unsupported')})`);
  }
  return labels.join(' ');
};

export const createModelStepSchema = (
  isHfTokenRequired: boolean,
  t: (key: string) => string,
) =>
  z
    .object({
      model: z.string().min(1, 'Version is required'),
      hfTokenSecretName: z.string().optional(),
      imagePullSecrets: z
        .union([z.string(), z.array(z.string())])
        .transform(toSecretNames)
        .optional(),
    })
    .superRefine((data, ctx) => {
      if (!isHfTokenRequired) return;
      if (data.hfTokenSecretName?.trim()) return;
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: t('huggingFaceTokenSelector.validation.tokenRequired'),
        path: ['hfTokenSecretName'],
      });
    });

export const createModelStepDefaults = (
  model: string,
): Partial<DeployAIMFormValues> => ({
  model,
  hfTokenSecretName: '',
  imagePullSecrets: [],
});

type ModelStepFieldsProps = {
  form: UseFormReturn<DeployAIMFormValues>;
  aggregatedAim: AggregatedAIM;
  selectedAim: ParsedAIM;
  namespace: string;
  imagePullSecrets: SecretResponseData[];
  onAimChange: (aim: ParsedAIM) => void;
};

export const ModelStepFields = ({
  form,
  aggregatedAim,
  selectedAim,
  namespace,
  imagePullSecrets,
  onAimChange,
}: ModelStepFieldsProps) => {
  const { t } = useTranslation('models');
  const model = form.watch('model');

  useEffect(() => {
    const match = aggregatedAim.parsedAIMs.find((aim) => aim.model === model);
    if (match) onAimChange(match);
  }, [aggregatedAim.parsedAIMs, model, onAimChange]);

  return (
    <>
      <div
        className="flex items-start gap-4 rounded-lg border border-default bg-surface p-4"
        data-testid="deploy-aim-wizard-model-header"
      >
        <div className="size-12 shrink-0">
          <ModelIcon
            iconName={selectedAim.canonicalName}
            width={48}
            height={48}
          />
        </div>
        <div className="full-width">
          <div className="text-lg font-semibold">{selectedAim.title}</div>
          <p className="text-sm text-muted">{selectedAim.description.short}</p>
        </div>
      </div>
      <FormSelect
        label={t('deployAIM.fields.version.title')}
        name="model"
        form={form}
        aria-label={t('deployAIM.fields.version.label')}
        placeholder={t('deployAIM.fields.version.placeholder')}
        disabledKeys={aggregatedAim.parsedAIMs
          .filter((v) => v.status !== 'Ready')
          .map((v) => v.model)}
      >
        {aggregatedAim.parsedAIMs.map((version) => (
          <SelectItem key={version.model}>
            {formatVersionLabel(version, t)}
          </SelectItem>
        ))}
      </FormSelect>
      {selectedAim.isHfTokenRequired ? (
        <>
          <Alert
            status="warning"
            title={t('deployAIM.fields.huggingFaceToken.title')}
            description={t('deployAIM.fields.huggingFaceToken.description')}
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
      <FormSelect
        label={t('deployAIM.fields.imagePullSecrets.label')}
        tooltipContent={t('deployAIM.fields.imagePullSecrets.description')}
        name="imagePullSecrets"
        form={form}
        selectionMode="multiple"
        aria-label={t('deployAIM.fields.imagePullSecrets.label')}
        placeholder={t('deployAIM.fields.imagePullSecrets.placeholder')}
        className="[&_[data-slot=select-trigger]]:min-w-[16rem] [&_[data-slot=select-trigger]]:w-full"
        data-testid="deployAimImagePullSecretsSelect"
      >
        {imagePullSecrets.map((secret) => (
          <SelectItem
            key={secret.metadata.name}
            textValue={secret.displayName}
            data-testid={`deployAimImagePullSecretOption-${secret.metadata.name}`}
          >
            {secret.displayName}
          </SelectItem>
        ))}
      </FormSelect>
    </>
  );
};

type ModelStepSummaryProps = {
  data: DeployAIMFormValues;
  selectedAim: ParsedAIM;
  hfTokens: SecretResponseData[];
  imagePullSecrets: SecretResponseData[];
};

export const ModelStepSummary = ({
  data,
  selectedAim,
  hfTokens,
  imagePullSecrets: availableImagePullSecrets,
}: ModelStepSummaryProps) => {
  const { t } = useTranslation('models');
  const hfTokenDisplayName =
    hfTokens.find((secret) => secret.metadata.name === data.hfTokenSecretName)
      ?.displayName ?? data.hfTokenSecretName;
  const imagePullSecrets = toSecretDisplayNames(
    toSecretNames(data.imagePullSecrets),
    availableImagePullSecrets,
  );

  return (
    <>
      <Wizard.SummaryRow
        label={t('deployAIM.summary.model')}
        value={selectedAim.title}
      />
      <Wizard.SummaryRow
        label={t('deployAIM.summary.containerVersion')}
        value={formatVersionLabel(selectedAim, t)}
      />
      {selectedAim.isHfTokenRequired ? (
        <Wizard.SummaryRow
          label={t('deployAIM.summary.hfToken')}
          value={hfTokenDisplayName}
        />
      ) : null}
      {imagePullSecrets.length > 0 ? (
        <Wizard.SummaryRow
          label={t('deployAIM.summary.imagePullSecrets')}
          value={imagePullSecrets.join(', ')}
        />
      ) : null}
    </>
  );
};
