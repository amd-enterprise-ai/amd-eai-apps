// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  SelectItem,
  FormFileUpload,
  FormInput,
  FormSelect,
  selectiveZodResolver,
  ModalForm,
  Link,
  Spinner,
} from '@amdenterpriseai/components';
import { IconExternalLink } from '@tabler/icons-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useState } from 'react';
import { FieldValues, Resolver } from 'react-hook-form';

import { useTranslation } from 'next-i18next';

import { useSystemToast } from '@amdenterpriseai/hooks';

import { listDatasets, uploadDataset } from '@/lib/app/datasets';
import { useProject } from '@/contexts/ProjectContext';

import { DATASET_FILESIZE_LIMIT } from '@/lib/app/datasets';
import { displayBytesInOptimalUnit } from '@amdenterpriseai/utils/app';

import type { DatasetType } from '@/types/datasets';

import { debounce } from 'lodash';
import { ZodType, z } from 'zod';

interface UploadDatasetFormData {
  name: string;
  description?: string;
  datasetType: DatasetType;
  file: File;
}

interface UploadDatasetParams {
  name: string;
  description: string;
  datasetType: DatasetType;
  file: File;
}

interface Props {
  onClose: () => void;
  refresh: () => void;
  isOpen: boolean;
}

const AVAILABLE_DATASET_TYPES: DatasetType[] = ['Fine-tuning'];

export const DatasetUpload = ({ onClose, isOpen, refresh }: Props) => {
  const { toast } = useSystemToast();
  const { t } = useTranslation('datasets');
  const { activeProject } = useProject();
  const queryClient = useQueryClient();

  const [uniqueCheckInProgress, setUniqueCheckInProgress] =
    useState<boolean>(false);

  const { mutate: uploadDatasetMutation, isPending: isUploading } = useMutation(
    {
      mutationFn: ({
        name,
        description,
        datasetType,
        file,
      }: UploadDatasetParams) => {
        return uploadDataset(
          name,
          description,
          datasetType,
          file,
          activeProject!,
        );
      },
      onSuccess: (): void => {
        toast.success(t('modals.upload.messages.success'));
        refresh();
        onClose();
      },
      onError: (error): void => {
        console.error('Error checking dataset name availability:', error);
        toast.error(t('modals.upload.messages.error'));
      },
    },
  );

  const handleUpload = (data: UploadDatasetFormData): void => {
    uploadDatasetMutation({
      name: data.name,
      description: data.description ?? '',
      datasetType: data.datasetType,
      file: data.file,
    });
  };

  const checkDatasetNameAvailability = useCallback(
    async (name: string, resolve: (result: boolean) => void): Promise<void> => {
      setUniqueCheckInProgress(true);
      try {
        // Server-side filter: a unique name is one with zero matching rows.
        // pageSize:1 keeps the request minimal — we only need the total count.
        const params = { name, pageSize: 1 };
        const datasetsWithName = await queryClient.fetchQuery({
          queryKey: ['project', activeProject, 'datasets', params],
          queryFn: () => listDatasets(activeProject!, params),
          staleTime: 0,
        });
        resolve(datasetsWithName.pagination.total === 0);
      } catch (error) {
        console.error('Error checking dataset name availability:', error);
        resolve(true);
      } finally {
        setUniqueCheckInProgress(false);
      }
    },
    [queryClient, activeProject],
  );

  const debouncedCheckDatasetNameAvailability = useMemo(
    () => debounce(checkDatasetNameAvailability, 700),
    [checkDatasetNameAvailability],
  );

  const validateDatasetName = useCallback(
    (desiredName: string): Promise<boolean> => {
      if (!desiredName || desiredName.trim().length === 0)
        return Promise.resolve(false);
      return new Promise((resolve) => {
        debouncedCheckDatasetNameAvailability(desiredName, resolve);
      });
    },
    [debouncedCheckDatasetNameAvailability],
  );

  const formSchema = useMemo(
    () =>
      z.object({
        name: z
          .string()
          .trim()
          .nonempty({
            message: t('modals.upload.form.datasetName.emptyNameError'),
          })
          .max(253, {
            message: t('modals.upload.form.datasetName.nameTooLongError'),
          })
          .refine(async (name) => validateDatasetName(name), {
            message: t('modals.upload.form.datasetName.nonUniqueNameError'),
          }),
        file: z
          .instanceof(File, {
            message: t('modals.upload.form.fileUpload.emptyError'),
          })
          .refine((file) => file.name.endsWith('.jsonl'), {
            message: t('modals.upload.form.fileUpload.formatError'),
          })
          .refine((file) => file.size <= DATASET_FILESIZE_LIMIT, {
            message: t('modals.upload.form.fileUpload.filesizeError', {
              value: displayBytesInOptimalUnit(DATASET_FILESIZE_LIMIT),
            }),
          }),
        datasetType: z.string().trim(),
        description: z.string().trim().optional(),
      }),
    [t, validateDatasetName],
  );

  const defaultDatasetType =
    AVAILABLE_DATASET_TYPES.length === 1
      ? AVAILABLE_DATASET_TYPES[0]
      : undefined;

  return (
    <ModalForm
      isOpen={isOpen}
      title={t('modals.upload.title')}
      confirmText={t('modals.upload.actions.confirm')}
      cancelText={t('modals.upload.actions.cancel')}
      validationSchema={formSchema}
      onCancel={onClose}
      onFormSuccess={(data: FieldValues) => {
        handleUpload(data as UploadDatasetFormData);
      }}
      resolver={selectiveZodResolver as (schema: ZodType) => Resolver}
      isActioning={isUploading}
      defaultValues={
        defaultDatasetType ? { datasetType: defaultDatasetType } : undefined
      }
      renderFields={(form) => (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <p className="text-sm dark:text-muted text-foreground">
              {t('modals.upload.body')}
            </p>
            <Link
              className="text-sm"
              href="https://enterprise-ai.docs.amd.com/en/latest/workbench/training/datasets.html#data-formats"
              target="_blank"
              rel="noopener noreferrer"
            >
              {t('modals.upload.docs')}
              <IconExternalLink size="16" stroke="2" />
            </Link>
          </div>
          <FormInput
            form={form}
            name="name"
            label={t('modals.upload.form.datasetName.label')}
            placeholder={t('modals.upload.form.datasetName.placeholder')}
            data-testid="datasetName"
            isDisabled={isUploading}
            isRequired
            endContent={
              uniqueCheckInProgress && <Spinner size="sm" color="primary" />
            }
          />
          <FormSelect
            form={form}
            label={t('modals.upload.form.datasetType.label')}
            placeholder={t('modals.upload.form.datasetType.placeholder')}
            data-testid="datasetSelect"
            disallowEmptySelection
            isRequired
            isDisabled={AVAILABLE_DATASET_TYPES.length === 1 || isUploading}
            name="datasetType"
          >
            {AVAILABLE_DATASET_TYPES.map((type) => (
              <SelectItem
                data-testid={`dataset-type-option-${type}`}
                key={type}
              >
                {t(`types.${type}`)}
              </SelectItem>
            ))}
          </FormSelect>
          <FormInput
            form={form}
            isDisabled={isUploading}
            name="description"
            label={t('modals.upload.form.description.label')}
            placeholder={t('modals.upload.form.description.placeholder')}
          />
          <FormFileUpload
            form={form}
            name="file"
            label={t('modals.upload.form.fileUpload.label')}
            placeholder={t('modals.upload.form.fileUpload.placeholder', {
              value: displayBytesInOptimalUnit(DATASET_FILESIZE_LIMIT),
            })}
            accept=".jsonl"
            isDisabled={isUploading}
            isRequired
          />
        </div>
      )}
    />
  );
};
