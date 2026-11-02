// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import {
  DrawerForm,
  FormFieldComponent,
  FormSelect,
  Link,
  SelectItem,
} from '@amdenterpriseai/components';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo } from 'react';
import { DefaultValues } from 'react-hook-form';

import { useTranslation } from 'next-i18next';

import { useSystemToast } from '@amdenterpriseai/hooks';

import { createStorage } from '@/services/app';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { SecretStatus } from '@/types/enums/secrets';
import { SecretUseCase } from '@amdenterpriseai/types';
import { StorageScope, StorageType } from '@/types/enums/storages';
import { FormField } from '@amdenterpriseai/types';
import { Project } from '@/types/projects';
import { Secret, SecretsResponse } from '@/types/secrets';
import {
  AddS3StorageFormData,
  CreateStorageRequest,
  Storage,
} from '@/types/storages';

import { ZodType, z } from 'zod';
import { fetchSecrets } from '@/services/app';

type BaseProps = {
  isOpen: boolean;
  storages: Storage[];
  secrets: Secret[];
  disabledProjectIds?: string[];
  onClose: () => void;
  openAddSecret: () => void;
};

type Props =
  | (BaseProps & { projects: Project[]; project?: undefined })
  | (BaseProps & { project: Project; projects?: undefined });

const DEFAULT_ACCESS_KEY_NAME = 'storage-access-key';
const DEFAULT_SECRET_KEY_NAME = 'storage-secret-key';
const STORAGE_S3_DOCUMENTATION_URL =
  'https://enterprise-ai.docs.amd.com/en/latest/resource-manager/storage/overview.html';

export const AddS3Storage: React.FC<Props> = ({
  isOpen,
  projects,
  storages,
  secrets,
  onClose,
  disabledProjectIds = [],
  project,
  openAddSecret,
}) => {
  const { t } = useTranslation('storages');
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();

  const disabledSecretIds = secrets
    .filter((secret) => secret.status === SecretStatus.DELETING)
    .map((secret) => secret.id);

  const { data: secretsData } = useQuery<SecretsResponse>({
    queryKey: ['secrets'],
    queryFn: () => fetchSecrets(),
    initialData: {
      data: secrets,
    },
  });

  const filteredSecrets = useMemo(
    () =>
      secretsData.data.filter((secret) => secret.useCase === SecretUseCase.S3),
    [secretsData.data],
  );

  const { mutate: addStorage, isPending } = useMutation({
    mutationFn: async (data: CreateStorageRequest) => {
      return createStorage(data);
    },
    onSuccess: () => {
      if (project) {
        queryClient.invalidateQueries({
          queryKey: ['project-storages', project.id],
        });
      }
      queryClient.invalidateQueries({ queryKey: ['storages'] });
      toast.success(t('form.add.notification.success'));
    },
    onError: (error) => {
      toast.error(t('form.add.notification.error'), error as APIRequestError);
    },
  });

  const handleAddStorageSubmit = useCallback(
    async (data: AddS3StorageFormData): Promise<void> => {
      addStorage({
        type: StorageType.S3,
        name: data.name,
        spec: {
          bucketUrl: data?.bucketUrl,
          accessKeyName: data?.accessKeyName,
          secretKeyName: data?.secretKeyName,
        },
        secretId: data.secretId,
        scope: StorageScope.ORGANIZATION,
        projectIds: project ? [project.id] : data.projectIds,
      });
    },
    [addStorage, project],
  );

  const defaultFormValues = useMemo(
    () =>
      ({
        name: '',
        secretId: '',
        bucketUrl: '',
        accessKeyName: '',
        secretKeyName: '',
        projectIds: project ? [project.id] : [],
        type: StorageType.S3,
      }) as DefaultValues<AddS3StorageFormData>,
    [project],
  );

  const formSchema = useMemo(() => {
    const nameRegex = /^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$/;
    return z.object({
      projectIds: z.preprocess((val: unknown) => {
        if (Array.isArray(val)) return val;
        if (typeof val === 'string' && val !== '') return val.split(',');
        return [];
      }, z.array(z.string())),
      secretId: z
        .string()
        .min(1, { message: t('form.add.field.secretId.error.required') }),
      type: z.custom<StorageType>(),
      bucketUrl: z
        .string()
        .min(1, { message: t('form.add.field.bucketUrl.error.required') })
        .url({ message: t('form.add.field.bucketUrl.error.invalidUrl') })
        .max(2043, {
          message: t('form.add.field.bucketUrl.error.maxLength', {
            max: 2043,
          }),
        })
        .refine(
          (value) =>
            value.startsWith('http://') || value.startsWith('https://'),
          { message: t('form.add.field.bucketUrl.error.invalidUrl') },
        ),
      accessKeyName: z.string(),
      secretKeyName: z.string(),
      name: z
        .string()
        .min(2, {
          message: t('form.add.field.name.error.minLength', {
            min: 2,
          }),
        })
        .max(253, {
          message: t('form.add.field.name.error.maxLength', {
            max: 253,
          }),
        })
        .regex(nameRegex, {
          message: t('form.add.field.name.error.invalidName'),
        })
        .refine(
          (value) => !storages.some((storage) => storage.name === value),
          {
            message: t('form.add.field.name.error.duplicateName'),
          },
        ),
    }) as ZodType<AddS3StorageFormData>;
  }, [t, storages]);

  const formContent: FormField<AddS3StorageFormData>[] = [
    {
      name: 'name',
      label: t('form.add.field.name.label'),
      placeholder: t('form.add.field.name.placeholder'),
      isRequired: true,
    },
    {
      name: 'bucketUrl',
      label: t('form.add.field.bucketUrl.label'),
      placeholder: t('form.add.field.bucketUrl.placeholder'),
      isRequired: true,
    },
    {
      name: 'secretId',
      label: t('form.add.field.secretId.label'),
      placeholder: t('form.add.field.secretId.placeholder'),
      secondaryAction: {
        label: t('form.add.field.secretId.actions.createSecret'),
        callback: () => {
          openAddSecret();
        },
      },
      isRequired: true,
      component: (formElemProps) => (
        <FormSelect {...formElemProps} disabledKeys={disabledSecretIds}>
          {filteredSecrets.map((secret) => (
            <SelectItem key={secret.id} textValue={secret.name}>
              {secret.name}
            </SelectItem>
          ))}
        </FormSelect>
      ),
    },
    {
      name: 'accessKeyName',
      label: t('form.add.field.accessKeyName.label'),
      placeholder: DEFAULT_ACCESS_KEY_NAME,
      description: t('form.add.field.accessKeyName.description', {
        defaultAccessKeyName: DEFAULT_ACCESS_KEY_NAME,
      }),
      isRequired: false,
    },
    {
      name: 'secretKeyName',
      label: t('form.add.field.secretKeyName.label'),
      placeholder: DEFAULT_SECRET_KEY_NAME,
      description: t('form.add.field.secretKeyName.description', {
        defaultSecretKeyName: DEFAULT_SECRET_KEY_NAME,
      }),
      isRequired: false,
    },
    {
      name: 'projectIds',
      label: t('form.add.field.projectIds.label'),
      placeholder: t('form.add.field.projectIds.placeholder'),
      isRequired: false,
      component: (formElemProps) => (
        <FormSelect
          selectionMode="multiple"
          {...formElemProps}
          disabledKeys={disabledProjectIds}
          isDisabled={!!project}
        >
          {(project ? [project] : projects).map((proj) => (
            <SelectItem key={proj.id} textValue={proj.name}>
              {proj.name}
            </SelectItem>
          ))}
        </FormSelect>
      ),
    },
  ];

  return (
    <DrawerForm<AddS3StorageFormData>
      isOpen={isOpen}
      isActioning={isPending}
      onFormSuccess={(values) => {
        handleAddStorageSubmit({
          projectIds: values.projectIds,
          name: values.name,
          secretId: values.secretId,
          bucketUrl: values.bucketUrl,
          accessKeyName: values.accessKeyName,
          secretKeyName: values.secretKeyName,
        });
        onClose();
      }}
      onCancel={onClose}
      title={t('form.add.title')}
      confirmText={t('form.add.actions.add.label')}
      cancelText={t('form.add.actions.cancel.label')}
      renderFields={(form) => (
        <div className="flex flex-col gap-4">
          <span className="text-sm">
            {t('form.add.description')}{' '}
            <Link size="sm" href={STORAGE_S3_DOCUMENTATION_URL}>
              {t('form.add.documentLink')}
            </Link>
          </span>

          {formContent.map((field) => (
            <FormFieldComponent<AddS3StorageFormData>
              key={field.name}
              formField={field}
              form={form}
            />
          ))}
        </div>
      )}
      defaultValues={defaultFormValues}
      validationSchema={formSchema}
    />
  );
};

export default AddS3Storage;
