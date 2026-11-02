// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  FormSelect,
  SelectItem,
  DrawerForm,
  FormFieldComponent,
} from '@amdenterpriseai/components';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo } from 'react';

import { useTranslation } from 'next-i18next';

import { useSystemToast } from '@amdenterpriseai/hooks';

import { assignStorageToProject } from '@/services/app';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { StorageStatus } from '@/types/enums/storages';
import { FormField } from '@amdenterpriseai/types';
import { Project } from '@/types/projects';
import { Storage } from '@/types/storages';

import { z } from 'zod';

interface AssignStorageToProjectFormData {
  storageId: string;
}

interface Props {
  isOpen: boolean;
  project: Project;
  storages: Storage[];
  existingStorageIds: string[];
  onClose: () => void;
}

export const AssignStorageToProject: React.FC<Props> = ({
  isOpen,
  project,
  storages,
  existingStorageIds,
  onClose,
}) => {
  const { t } = useTranslation('storages');
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();

  const { mutate: assignStorage, isPending } = useMutation({
    mutationFn: async (data: AssignStorageToProjectFormData) => {
      return assignStorageToProject(project.id, data.storageId);
    },
    onSuccess: () => {
      toast.success(t('form.assignToProject.notification.success'));
      queryClient.invalidateQueries({
        queryKey: ['project-storages', project.id],
      });
      queryClient.invalidateQueries({ queryKey: ['storages'] });
      onClose();
    },
    onError: (error) => {
      toast.error(
        t('form.assignToProject.notification.error'),
        error as APIRequestError,
      );
    },
  });

  const formSchema = useMemo(
    () =>
      z.object({
        storageId: z.string().min(1, {
          message: t('form.assignToProject.field.storageId.error.required'),
        }),
      }) as z.ZodType<AssignStorageToProjectFormData>,
    [t],
  );

  const handleFormSubmit = useCallback(
    async (data: AssignStorageToProjectFormData): Promise<void> => {
      assignStorage(data);
    },
    [assignStorage],
  );

  const availableStorages = useMemo(() => {
    return storages.filter(
      (storage) =>
        !existingStorageIds.includes(storage.id) &&
        storage.status !== StorageStatus.DELETING,
    );
  }, [storages, existingStorageIds]);

  const disabledStorageIds = useMemo(() => {
    return storages
      .filter((storage) => storage.status === StorageStatus.DELETING)
      .map((storage) => storage.id);
  }, [storages]);

  const formContent: FormField<AssignStorageToProjectFormData>[] = [
    {
      name: 'storageId',
      label: t('form.assignToProject.field.storageId.label'),
      placeholder: t('form.assignToProject.field.storageId.placeholder'),
      isRequired: true,
      component: (formElemProps) => (
        <FormSelect disabledKeys={disabledStorageIds} {...formElemProps}>
          {availableStorages.map((storage: Storage) => {
            return (
              <SelectItem key={storage.id} textValue={storage.name}>
                {storage.name}
              </SelectItem>
            );
          })}
        </FormSelect>
      ),
    },
  ];

  return (
    <DrawerForm<AssignStorageToProjectFormData>
      isOpen={isOpen}
      isActioning={isPending}
      onFormSuccess={(values) => {
        handleFormSubmit({
          storageId: values.storageId,
        });
      }}
      onCancel={onClose}
      title={t('form.assignToProject.title')}
      confirmText={t('form.assignToProject.action.assign')}
      cancelText={t('form.assignToProject.action.cancel')}
      renderFields={(form) => (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-gray-500">
            {t('form.assignToProject.description')}{' '}
            <strong>{project.name}</strong>
          </p>
          {availableStorages.length === 0 ? (
            <p className="text-sm text-warning">
              {t('form.assignToProject.noAvailableStorages')}
            </p>
          ) : (
            formContent.map((field) => (
              <FormFieldComponent<AssignStorageToProjectFormData>
                key={field.name}
                formField={field}
                errorMessage={form.formState.errors[field.name]?.message}
                form={form}
              />
            ))
          )}
        </div>
      )}
      validationSchema={formSchema}
    />
  );
};

export default AssignStorageToProject;
