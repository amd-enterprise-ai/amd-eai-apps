// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Divider,
  FormInput,
  Input,
  Radio,
  RadioGroup,
} from '@amdenterpriseai/components';
import { useTranslation } from 'next-i18next';
import { Controller, useController, type UseFormReturn } from 'react-hook-form';

import { ProjectHuggingFaceTokenSelector } from '@/components/shared/HuggingFaceTokenSelector';
import { ProjectS3StorageSelector } from '@/components/shared/S3StorageSelector';
import { MODEL_SOURCE_TYPE, type ModelSourceType } from '@/types/model-import';

import type { CustomModelImportFormValues } from '../types';

interface Props {
  form: UseFormReturn<CustomModelImportFormValues>;
  namespace: string;
  /**
   * Edit mode: the import source and its credential are immutable post-onboard,
   * so the source field is disabled (and read-only), the credential selectors
   * are hidden, and the wizard skips the preview call entirely.
   */
  readOnly?: boolean;
}

/**
 * Step 1 — choose where the model's weights come from and how to authenticate.
 *
 * The source family drives the rest of the step: Hugging Face takes a repo
 * reference and an optional token, S3 takes a bucket URI and a mandatory
 * credential. Switching families clears the previous one's inputs so a stale
 * value cannot ride along on the request — the backend rejects a payload
 * carrying the other family's credential.
 */
export const StepModelSource = ({
  form,
  namespace,
  readOnly = false,
}: Props) => {
  const { t } = useTranslation('models', {
    keyPrefix: 'customModels.import.steps.source',
  });
  const sourceType = form.watch('sourceType');
  const isS3 = sourceType === MODEL_SOURCE_TYPE.S3;

  // Both credentials are registered for as long as this step exists, even
  // though only one selector is on screen. Unmounting a field's control makes
  // React Hook Form drop it from the form values, and a missing key fails the
  // schema's object parse — which aborts before any refinement runs, silently
  // skipping the source checks instead of reporting them.
  const hfToken = useController({
    control: form.control,
    name: 'hfTokenSecretName',
  });
  const s3Storage = useController({
    control: form.control,
    name: 's3StorageName',
  });

  if (readOnly) {
    return (
      <div className="flex flex-col gap-6">
        <header className="flex flex-col gap-1">
          <h2 className="text-xl font-semibold">{t('title')}</h2>
          <p className="text-sm text-muted">{t('readOnlyDescription')}</p>
        </header>

        <Input
          label={t('fields.sourceType.label')}
          value={t(`sourceTypes.${sourceType}.label`)}
          isReadOnly
          isDisabled
          data-testid="custom-model-import-source-type"
        />

        <Input
          label={t('fields.source.label')}
          value={form.watch('source') ?? ''}
          description={t('fields.source.immutableHint')}
          isReadOnly
          isDisabled
          data-testid="custom-model-import-source"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold">{t('title')}</h2>
        <p className="text-sm text-muted">{t('description')}</p>
      </header>

      <Controller
        control={form.control}
        name="sourceType"
        render={({ field }) => (
          <RadioGroup
            label={t('fields.sourceType.label')}
            orientation="horizontal"
            value={field.value}
            onChange={(value: string) => {
              field.onChange(value as ModelSourceType);
              form.setValue('source', '');
              form.setValue('hfTokenSecretName', '');
              form.setValue('s3StorageName', '');
              form.clearErrors([
                'source',
                'hfTokenSecretName',
                's3StorageName',
              ]);
            }}
            data-testid="custom-model-import-source-type"
          >
            <Radio
              value={MODEL_SOURCE_TYPE.HUGGING_FACE}
              data-testid="custom-model-import-source-type-huggingFace"
            >
              {t('sourceTypes.huggingFace.label')}
            </Radio>
            <Radio
              value={MODEL_SOURCE_TYPE.S3}
              data-testid="custom-model-import-source-type-s3"
            >
              {t('sourceTypes.s3.label')}
            </Radio>
          </RadioGroup>
        )}
      />

      <FormInput<CustomModelImportFormValues>
        form={form}
        name="source"
        label={t('fields.source.label')}
        placeholder={
          isS3
            ? t('fields.source.s3Placeholder')
            : t('fields.source.placeholder')
        }
        description={
          isS3
            ? t('fields.source.s3Description')
            : t('fields.source.description')
        }
        isRequired
        data-testid="custom-model-import-source"
      />

      <Divider />

      <div className="flex flex-col gap-3">
        <header className="flex flex-col gap-1">
          <h3 className="text-base font-semibold">
            {isS3 ? t('fields.s3.title') : t('fields.huggingFace.title')}
          </h3>
          <p className="text-sm text-muted">
            {isS3
              ? t('fields.s3.description')
              : t('fields.huggingFace.description')}
          </p>
        </header>

        {isS3 ? (
          <ProjectS3StorageSelector
            namespace={namespace}
            value={s3Storage.field.value || null}
            onChange={s3Storage.field.onChange}
            isRequired
            isInvalid={Boolean(s3Storage.fieldState.error?.message)}
            errorMessage={s3Storage.fieldState.error?.message}
          />
        ) : (
          <ProjectHuggingFaceTokenSelector
            namespace={namespace}
            value={hfToken.field.value || null}
            onChange={hfToken.field.onChange}
            isInvalid={Boolean(hfToken.fieldState.error?.message)}
            errorMessage={hfToken.fieldState.error?.message}
          />
        )}
      </div>
    </div>
  );
};

export default StepModelSource;
