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

import { updateStorageAssignment } from '@/services/app';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { FormField } from '@amdenterpriseai/types';
import { Project } from '@/types/projects';
import { AssignStorageFormData, Storage } from '@/types/storages';

import { z } from 'zod';

interface Props {
  isOpen: boolean;
  storage: Storage;
  project?: Project;
  projects: Project[];
  selectedProjectIds: string[];
  disabledProjectIds: string[];
  onClose: () => void;
}

export const AssignStorage: React.FC<Props> = ({
  isOpen,
  project,
  projects,
  storage,
  selectedProjectIds,
  disabledProjectIds = [],
  onClose,
}) => {
  const { t } = useTranslation('storages');
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();

  const { mutate: updateAssignment, isPending } = useMutation({
    mutationFn: async (data: AssignStorageFormData) => {
      if (!storage) {
        throw new Error('Storage is null');
      }
      return updateStorageAssignment(storage.id, {
        projectIds: data.projectIds,
      });
    },
    onSuccess: () => {
      toast.success(t('form.assign.notification.success'));
      queryClient.invalidateQueries({
        queryKey: project?.id ? ['storage', project?.id] : ['storages'],
      });
      onClose();
    },
    onError: (error) => {
      toast.error(
        t('form.assign.notification.error'),
        error as APIRequestError,
      );
    },
  });

  const formSchema = useMemo(
    () =>
      z.object({
        projectIds: z.preprocess((val: unknown) => {
          if (Array.isArray(val)) return val as string[];
          if (typeof val === 'string' && val !== '') return val.split(',');
          return [];
        }, z.array(z.string())),
      }) as z.ZodType<AssignStorageFormData>,
    [],
  );

  const handleFormSubmit = useCallback(
    async (data: AssignStorageFormData): Promise<void> => {
      updateAssignment(data);
    },
    [updateAssignment],
  );

  const assignDrawerDefaultValues = useMemo(
    () => ({ projectIds: selectedProjectIds }),
    [selectedProjectIds],
  );

  const formContent: FormField<AssignStorageFormData>[] = [
    {
      name: 'projectIds',
      label: t('form.assign.field.projectIds.label'),
      placeholder: t('form.assign.field.projectIds.placeholder'),
      isRequired: false,
      component: (formElemProps) => (
        <FormSelect
          selectionMode="multiple"
          disabledKeys={disabledProjectIds}
          {...formElemProps}
        >
          {projects.map((project: Project) => (
            <SelectItem key={project.id} textValue={project.name}>
              {project.name}
            </SelectItem>
          ))}
        </FormSelect>
      ),
    },
  ];

  return (
    <DrawerForm<AssignStorageFormData>
      key={storage.id}
      isOpen={isOpen}
      isActioning={isPending}
      defaultValues={assignDrawerDefaultValues}
      onFormSuccess={(values) => {
        handleFormSubmit({
          projectIds: values.projectIds,
        });
      }}
      onCancel={onClose}
      title={t('form.assign.title')}
      confirmText={t('form.assign.action.save')}
      cancelText={t('form.assign.action.cancel')}
      renderFields={(form) => (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-gray-500">
            {t('form.assign.description')} <strong>{storage.name}</strong>
          </p>
          {formContent.map((field) => (
            <FormFieldComponent<AssignStorageFormData>
              key={field.name}
              formField={field}
              errorMessage={form.formState.errors[field.name]?.message}
              form={form}
            />
          ))}
        </div>
      )}
      validationSchema={formSchema}
    />
  );
};

export default AssignStorage;
