// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  FormInput,
  FormSelect,
  SelectItem,
  Spinner,
  Tooltip,
  Wizard,
} from '@amdenterpriseai/components';
import { IconInfoCircle } from '@tabler/icons-react';
import Image from 'next/image';
import { useEffect } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'next-i18next';
import { z } from 'zod';

import type { SecretResponseData } from '@/types/secrets';
import type { WorkspaceCatalogItem as CatalogItem } from '@/types/workspaces';
import { toSecretDisplayNames, toSecretNames } from '@/utils/secrets';

import type { DeployWorkspaceFormValues } from '../types';

export const createSettingsStepSchema = (t: (key: string) => string) =>
  z.object({
    containerImage: z
      .string()
      .min(1, {
        message: t('deployModal.settings.containerImage.emptyNameError'),
      })
      .refine(
        (s) =>
          /^(?:[a-z0-9]+(?:[._-][a-z0-9]+)*(?:\/[a-z0-9]+(?:[._-][a-z0-9]+)*)*\/)?[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[\w][\w.-]{0,127})?(?:@sha256:[a-f0-9]{64})?$/.test(
            s,
          ),
        t('deployModal.settings.containerImage.formatError'),
      )
      .optional(),
    imagePullSecrets: z
      .union([z.string(), z.array(z.string())])
      .transform(toSecretNames)
      .optional(),
  });

type SettingsStepFieldsProps = {
  form: UseFormReturn<DeployWorkspaceFormValues>;
  catalogItem: CatalogItem;
  containerImage?: string | null;
  isLoadingContainerImage: boolean;
  imagePullSecrets: SecretResponseData[];
};

export const SettingsStepFields = ({
  form,
  catalogItem,
  containerImage,
  isLoadingContainerImage,
  imagePullSecrets,
}: SettingsStepFieldsProps) => {
  const { t } = useTranslation('catalog');

  useEffect(() => {
    if (containerImage && !form.getFieldState('containerImage').isDirty) {
      form.setValue('containerImage', containerImage, {
        shouldValidate: true,
      });
    }
  }, [containerImage, form]);

  return (
    <>
      <div
        className="flex items-start justify-between gap-4 rounded-lg border border-default bg-surface p-4"
        data-testid="deploy-workspace-wizard-catalog-header"
      >
        <div className="min-w-0">
          <div className="text-lg font-semibold">
            {catalogItem.displayName ?? catalogItem.name}
          </div>
          <p className="text-sm text-muted">{catalogItem.description}</p>
          {catalogItem.longDescription ? (
            <p className="mt-2 whitespace-pre-wrap wrap-break-words text-sm text-muted">
              {catalogItem.longDescription.replace(/\\n/g, '\n')}
            </p>
          ) : null}
        </div>
        {catalogItem.featuredImage ? (
          <Image
            alt="workload icon"
            className="size-10 shrink-0 rounded-md object-cover"
            height={40}
            src={catalogItem.featuredImage}
            width={40}
            unoptimized
          />
        ) : null}
      </div>
      <FormInput
        name="containerImage"
        form={form}
        aria-label={t('deployModal.settings.containerImage.label')}
        label={
          <div className="flex items-center gap-1">
            <span>{t('deployModal.settings.containerImage.label')}</span>
            <Tooltip
              classNames={{
                content: 'max-w-md',
              }}
              content={t('deployModal.settings.containerImage.tooltip')}
            >
              <IconInfoCircle className="cursor-pointer text-muted" size={16} />
            </Tooltip>
          </div>
        }
        endContent={
          isLoadingContainerImage ? (
            <Spinner size="sm" color="primary" />
          ) : undefined
        }
      />
      <FormSelect
        name="imagePullSecrets"
        form={form}
        aria-label={t('deployModal.settings.imagePullSecrets.label')}
        selectionMode="multiple"
        label={
          <div className="flex items-center gap-1">
            <span>{t('deployModal.settings.imagePullSecrets.label')}</span>
            <Tooltip
              classNames={{
                content: 'max-w-md',
              }}
              content={t('deployModal.settings.imagePullSecrets.tooltip')}
            >
              <IconInfoCircle className="cursor-pointer text-muted" size={16} />
            </Tooltip>
          </div>
        }
        placeholder={
          imagePullSecrets.length === 0
            ? t('deployModal.settings.imagePullSecrets.noSecrets')
            : t('deployModal.settings.imagePullSecrets.placeholder')
        }
        isDisabled={imagePullSecrets.length === 0}
      >
        {imagePullSecrets.map((secret) => (
          <SelectItem key={secret.metadata.name} textValue={secret.displayName}>
            {secret.displayName}
          </SelectItem>
        ))}
      </FormSelect>
    </>
  );
};

type SettingsStepSummaryProps = {
  data: DeployWorkspaceFormValues;
  imagePullSecrets: SecretResponseData[];
};

export const SettingsStepSummary = ({
  data,
  imagePullSecrets: availableImagePullSecrets,
}: SettingsStepSummaryProps) => {
  const { t } = useTranslation('catalog');
  const imagePullSecrets = toSecretDisplayNames(
    toSecretNames(data.imagePullSecrets),
    availableImagePullSecrets,
  );

  return (
    <>
      {data.containerImage ? (
        <Wizard.SummaryRow
          label={t('deployModal.summary.containerImage')}
          value={data.containerImage}
        />
      ) : null}
      {imagePullSecrets.length > 0 ? (
        <Wizard.SummaryRow
          label={t('deployModal.summary.imagePullSecrets')}
          value={imagePullSecrets.join(', ')}
        />
      ) : null}
    </>
  );
};
